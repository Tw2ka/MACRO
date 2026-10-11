"""Normalize and audit HUMMUS source records; build the verified subset."""
import ast
import csv
import json
import math
import random
from collections import Counter
from pathlib import Path

from macro.shared.io import file_hash, write_json, write_jsonl
from macro.shared.policy import ALIASES, ALIAS_LOOKUP, MENTIONS, canonical_matches, ingredient_head
from . import GENERATOR_VERSION

SOURCE_COMMIT = "eb672598cc4891da0eb436daefcd25b412dad641"


def normalize(row, number):
    if not row["recipe_id"].isdigit() or not any(c.isalpha() for c in row["title"]):
        raise ValueError("missing_identity")
    duration, score = float(row["duration"]), float(row["fsa_score"])
    if not math.isfinite(duration) or not 1 <= duration <= 180:
        raise ValueError("duration_outside_pilot_bounds")
    if not math.isfinite(score) or not 0 <= score <= 1 or abs(score * 8 - round(score * 8)) > 1e-8:
        raise ValueError("missing_or_invalid_fsa")
    if row["normalization_comment"].strip():
        raise ValueError("flagged_nutrient_normalization")
    raw = ast.literal_eval(row["ingredients"])
    if not isinstance(raw, dict) or not raw:
        raise ValueError("invalid_raw_ingredients")
    raw_names = []
    for section in raw.values():
        if not isinstance(section, list):
            raise ValueError("invalid_raw_ingredients")
        for entry in section:
            if not isinstance(entry, (list, tuple)) or len(entry) != 2 or not isinstance(entry[0], str) or not entry[0].strip():
                raise ValueError("invalid_raw_ingredients")
            raw_names.append(entry[0])
    if any('$template' in x.lower() or ' or ' in x.lower() for x in raw_names):
        raise ValueError("ambiguous_or_template_ingredient")
    # Do not silently call roasted garlic / tomato sauce / onion powder absent.
    # If a curated ingredient is mentioned in a form we have not explicitly mapped, reject the record.
    if any(MENTIONS.search(x) and ingredient_head(x) not in ALIAS_LOOKUP for x in raw_names):
        raise ValueError("unmapped_curated_ingredient_form")
    if any(x.count('(') != x.count(')') or x.strip().lower().startswith(('and ', 'to ', 'sub ')) for x in raw_names):
        raise ValueError("malformed_ingredient_text")
    # Supplied FoodKG ingredient lists are misaligned in observed source rows: exclude them.
    # Only declared descriptor removal and exact-name aliases on ORIGINAL recipe ingredients.
    names = sorted(set(ingredient_head(x) for x in raw_names))
    if any(not any(c.isalpha() for c in x) for x in names):
        raise ValueError("malformed_ingredient_text")
    canonical = canonical_matches(names)
    if not canonical:
        raise ValueError("no_curated_ingredient_match")
    return {"id": row["recipe_id"], "title": row["title"], "duration_minutes": duration,
            "ingredient_names": names, "canonical_ingredients": canonical,
            "raw_ingredient_names": raw_names, "nutrition_score": score,
            "nutrition_metric": "hummus_normalized_fsa", "source_record_number": number,
            "source_url": row["recipe_url"],
            "source_values": {k: row[k] for k in ["recipe_id", "title", "duration", "ingredients", "ingredient_food_kg_names", "fsa_score", "normalization_comment"]}}


def audit(source, out, config):
    """Streaming full-file audit; reservoir sample of eligible rows, bounded memory."""
    out = Path(out)
    rng = random.Random(config["seed"])
    reasons, missing = Counter(), Counter()
    seen, selected, eligible = set(), [], 0
    ranges = {k: [math.inf, -math.inf] for k in ["duration", "who_score", "fsa_score", "nutri_score"]}
    total = 0
    with Path(source).open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for total, row in enumerate(reader, 1):
            for k in ranges:
                try:
                    x = float(row[k])
                    if math.isfinite(x):
                        ranges[k] = [min(ranges[k][0], x), max(ranges[k][1], x)]
                    else:
                        missing[k] += 1
                except ValueError:
                    missing[k] += 1
            if row["recipe_id"] in seen:
                reasons["duplicate_recipe_id"] += 1
                continue
            seen.add(row["recipe_id"])
            try:
                record = normalize(row, total)
            except (ValueError, SyntaxError, TypeError, KeyError) as exc:
                reason = str(exc) if str(exc) in ["missing_identity", "duration_outside_pilot_bounds", "missing_or_invalid_fsa", "flagged_nutrient_normalization", "ambiguous_or_template_ingredient", "unmapped_curated_ingredient_form", "malformed_ingredient_text", "invalid_raw_ingredients", "no_curated_ingredient_match"] else "unparseable_required_field"
                reasons[reason] += 1
                continue
            eligible += 1
            if len(selected) < config["subset_size"]:
                selected.append(record)
            else:
                position = rng.randrange(eligible)
                if position < len(selected):
                    selected[position] = record
    selected.sort(key=lambda x: int(x["id"]))
    report = {"source_file": str(Path(source)), "sha256": file_hash(source), "source_bytes": Path(source).stat().st_size,
              "source_repository": "https://gitlab.com/felix134/connected-recipe-data-set", "documentation_commit": SOURCE_COMMIT,
              "provenance_limit": "Local CSV hash recorded; no upstream checksum was supplied, so byte identity with the upstream release is not established.",
              "rows": total, "unique_ids": len(seen), "eligible_rows": eligible, "subset_size": len(selected),
              "first_exclusion_reason_counts": dict(reasons), "missing_numeric_counts": dict(missing),
              "observed_ranges": {k: v if math.isfinite(v[0]) else None for k, v in ranges.items()},
              "seed": config["seed"], "mapping": ALIASES, "generator_version": GENERATOR_VERSION}
    write_json(out / "audit.json", report)
    write_jsonl(out / "recipes.jsonl", selected)
    print(json.dumps({k: report[k] for k in ["rows", "eligible_rows", "subset_size", "sha256"]}, indent=2))
    return report



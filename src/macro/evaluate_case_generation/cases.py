"""Generate, preview and validate the controlled pilot evaluation cases."""
import json
import random
from collections import Counter
from pathlib import Path

from macro.shared.io import digest, file_hash, read_json, read_jsonl, write_json, write_jsonl
from macro.shared.policy import ALIASES, POLICY_VERSION, findings, validate_case
from . import GENERATOR_VERSION


def public_recipe(r):
    return {k: r[k] for k in ["id", "title", "duration_minutes", "ingredient_names", "canonical_ingredients", "raw_ingredient_names", "nutrition_score", "nutrition_metric"]}


def explanation(r):
    return f"This recipe takes {r['duration_minutes']:g} minutes. Its documented ingredient groups are {', '.join(r['canonical_ingredients'])}; its normalized HUMMUS FSA proxy is {r['nutrition_score']:g}, where higher is preferred."


def request(p):
    priorities = {"preference_first": "Among feasible recipes, prioritize ingredient preference match, then the nutrition proxy.",
                  "nutrition_first": "Among feasible recipes, prioritize the nutrition proxy, then ingredient preference match.",
                  "unspecified": "I have not specified a priority between ingredient preference match and the nutrition proxy."}
    return (f"Choose between these recipes. My preferred ingredient groups are {', '.join(p['preferred_ingredients'])}. "
            f"Exclude {', '.join(p['excluded_ingredients']) if p['excluded_ingredients'] else 'no ingredient groups'}. "
            f"The maximum duration is strictly {p['max_duration_minutes']:g} minutes (the boundary is allowed). " + priorities[p["priority"]])


def generate(subset, out, config):
    out = Path(out)
    if (out / "cases.jsonl").exists():
        raise ValueError("Pilot already exists. Use a new --out directory to preserve versioned artifacts.")
    recipes = read_jsonl(Path(subset) / "recipes.jsonl")
    recipes = [r for r in recipes if r["id"] not in config.get("excluded_pilot_recipe_ids", {})]
    audit_report = read_json(Path(subset) / "audit.json")
    rng = random.Random(config["seed"])
    cases, refs, reuse, duplicates, rejected = [], [], Counter(), set(), Counter()
    attempts = 0
    winner_count = 0
    # Balanced winners across the pilot; tradeoffs include 3 preference-first, 2 nutrition-first, 2 unspecified.
    targets = []
    for kind, count in config["mix"].items():
        for i in range(count):
            priority = ["preference_first", "nutrition_first", "unspecified"][i % 3] if kind == "tradeoff" else ["preference_first", "nutrition_first"][i % 2]
            targets.append((kind, priority, "A" if i % 2 == 0 else "B", "near" if i % 2 == 0 else "clear", i))
    for kind, priority, target_slot, difficulty, index in targets:
        for _ in range(config["max_selection_attempts"]):
            attempts += 1
            a, b = rng.sample(recipes, 2)
            if max(reuse[a["id"]], reuse[b["id"]]) >= config["max_recipe_reuse"]:
                rejected["reuse_cap"] += 1
                continue
            vocabulary = sorted(set(a["canonical_ingredients"] + b["canonical_ingredients"]))
            preferred = sorted(rng.sample(vocabulary, min(2, len(vocabulary))))
            excluded = []
            maximum = max(a["duration_minutes"], b["duration_minutes"])
            if kind == "constraint":
                # Alternate duration and ingredient violations. Time limits are sampled independently of soft scores.
                if index % 2 == 0:
                    if a["duration_minutes"] == b["duration_minutes"]:
                        rejected["equal_duration"] += 1
                        continue
                    gap = abs(a["duration_minutes"] - b["duration_minutes"])
                    if (difficulty == "near" and gap > 10) or (difficulty == "clear" and gap < 15):
                        rejected["duration_difficulty"] += 1
                        continue
                    maximum = min(a["duration_minutes"], b["duration_minutes"])
                else:
                    options = sorted((set(a["canonical_ingredients"]) ^ set(b["canonical_ingredients"])) - set(preferred))
                    if not options:
                        rejected["no_excludable_difference"] += 1
                        continue
                    excluded = [rng.choice(options)]
            else:
                # Include ingredient exclusions without invalidating either candidate when vocabulary permits.
                absent = sorted(set(ALIASES) - set(vocabulary))
                if absent:
                    excluded = [rng.choice(absent)]
            profile = {"preferred_ingredients": preferred, "excluded_ingredients": excluded,
                       "max_duration_minutes": maximum, "priority": priority}
            case = {"case_id": "", "profile": profile, "request": request(profile),
                    "candidate_pool": [public_recipe(a), public_recipe(b)],
                    "recommendations": {"A": {"recipe_id": a["id"], "explanation": explanation(a)}, "B": {"recipe_id": b["id"], "explanation": explanation(b)}}}
            ref = findings(case)
            if ref["case_type"] != kind:
                rejected["wrong_relationship"] += 1
                continue
            if kind != "constraint":
                gap = abs(a["nutrition_score"] - b["nutrition_score"])
                if (difficulty == "near" and gap > .125) or (difficulty == "clear" and gap < .25):
                    rejected["nutrition_difficulty"] += 1
                    continue
            identity = digest([profile, sorted([a["id"], b["id"]])])
            if identity in duplicates:
                rejected["duplicate_profile_pair"] += 1
                continue
            if ref["decision"] in ["A", "B"]:
                target_slot = "A" if winner_count % 2 == 0 else "B"
                if ref["decision"] != target_slot:
                    case["recommendations"] = {"A": case["recommendations"]["B"], "B": case["recommendations"]["A"]}
                    ref = findings(case)
                winner_count += 1
            duplicates.add(identity)
            reuse.update([a["id"], b["id"]])
            case["case_id"] = "pilot-" + digest([identity, config["seed"]])[:12]
            validate_case(case)
            profile_id = digest(profile)[:12]
            refs.append({"case_id": case["case_id"], "profile_id": profile_id, "difficulty": difficulty,
                         "difficulty_definition": "duration gap <=10 min / score gap <=0.125 for near; ingredient exclusion cases are clear",
                         "source_ids": [a["id"], b["id"]], **ref})
            cases.append(case)
            break
        else:
            raise ValueError(f"Bounded search failed for {kind}/{priority}/{difficulty}; no definitions were relaxed.")
    rng.shuffle(cases)
    write_jsonl(out / "cases.jsonl", cases)
    write_jsonl(out / "references.private.jsonl", refs)
    write_json(out / "manifest.json", {"seed": config["seed"], "policy_version": POLICY_VERSION,
               "generator_version": GENERATOR_VERSION, "config": config, "dataset_sha256": audit_report["sha256"],
               "subset_sha256": file_hash(Path(subset) / "recipes.jsonl"), "cases_sha256": file_hash(out / "cases.jsonl"),
               "references_sha256": file_hash(out / "references.private.jsonl"), "counts": dict(Counter(r["case_type"] for r in refs)),
               "selection_attempts": attempts, "rejections": dict(rejected), "recipe_reuse": dict(reuse),
               "profile_reuse": dict(Counter(r["profile_id"] for r in refs)), "live_validated": False})
    preview(cases, refs, out / "preview.md")
    return validate(out)


def preview(cases, refs, path):
    refs = {x["case_id"]: x for x in refs}
    lines = ["# Pilot preview — private development review", "", "Contains reference labels. Never send this document to a judge.", ""]
    for c in cases:
        ref = refs[c["case_id"]]
        lines += [f"## {c['case_id']}", "", c["request"], "", "| Candidate | Recipe | Minutes | Preference | FSA proxy | Violations |", "|---|---|---:|---:|---:|---|"]
        for slot in ["A", "B"]:
            r = next(r for r in c["candidate_pool"] if r["id"] == c["recommendations"][slot]["recipe_id"])
            f = ref["candidates"][slot]
            lines.append(f"| {slot} | {r['id']}: {r['title']} | {r['duration_minutes']:g} | {f['preference_score']:g} | {r['nutrition_score']:g} | {', '.join(f['violations']) or 'none'} |")
            lines += []
        for slot in ["A", "B"]:
            r = next(r for r in c["candidate_pool"] if r["id"] == c["recommendations"][slot]["recipe_id"])
            lines += ["", f"{slot} source ingredient names: {', '.join(r['ingredient_names'])}.", f"{slot} explanation: {c['recommendations'][slot]['explanation']}"]
        lines += ["", f"Reference: **{ref['decision']}**; {ref['case_type']}; {ref['difficulty']}. {ref['reason']}.", ""]
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def validate(folder):
    folder = Path(folder)
    cases, refs = read_jsonl(folder / "cases.jsonl"), read_jsonl(folder / "references.private.jsonl")
    assert len(cases) == len(refs) == 20, "Pilot must contain exactly 20 cases"
    assert len({c["case_id"] for c in cases}) == 20
    references = {r["case_id"]: r for r in refs}
    assert set(references) == {c["case_id"] for c in cases}
    for c in cases:
        validate_case(c)
        fresh = findings(c)
        for key in fresh:
            assert fresh[key] == references[c["case_id"]][key], (c["case_id"], key)
    manifest = read_json(folder / "manifest.json")
    assert file_hash(folder / "cases.jsonl") == manifest["cases_sha256"]
    assert file_hash(folder / "references.private.jsonl") == manifest["references_sha256"]
    report = {"valid_cases": 20, "counts": dict(Counter(r["case_type"] for r in refs)),
              "decisions": dict(Counter(r["decision"] for r in refs)),
              "tradeoff_priorities": dict(Counter(c["profile"]["priority"] for c in cases if references[c["case_id"]]["case_type"] == "tradeoff")),
              "max_recipe_reuse": max(manifest["recipe_reuse"].values()), "source_manual_review": "see manual_review.private.json"}
    assert report["counts"] == {"constraint": 7, "dominance": 6, "tradeoff": 7}
    write_json(folder / "validation.json", report)
    print(json.dumps(report, indent=2))
    return report

"""Offline recheck of selected source records and separately transcribed development labels."""
import ast
import csv
from pathlib import Path

from macro.shared.io import file_hash, read_json, read_jsonl, write_json


def main():
    folder = Path("data/pilot")
    cases = read_jsonl(folder / "cases.jsonl")
    refs = {r["case_id"]: r for r in read_jsonl(folder / "references.private.jsonl")}
    review = read_json(folder / "manual_review.private.json")
    assert {r[0] for r in review["cases"]} == set(refs)
    for cid, decision, kind, pa, pb, na, nb, va, vb in review["cases"]:
        ref = refs[cid]
        assert (ref["decision"], ref["case_type"]) == (decision, kind), cid
        for slot, pref, nut, violations in [("A", pa, na, va), ("B", pb, nb, vb)]:
            actual = ref["candidates"][slot]
            assert (actual["preference_score"], actual["nutrition_score"], actual["violations"]) == (pref, nut, violations), (cid, slot)
    selected = {r["id"]: r for c in cases for r in c["candidate_pool"]}
    subset = {r["id"]: r for r in read_jsonl("data/subset/recipes.jsonl") if r["id"] in selected}
    assert set(selected) == set(subset) == set(review["recipe_groups"])
    for rid, recipe in selected.items():
        assert recipe["canonical_ingredients"] == review["recipe_groups"][rid], rid
    checked = []
    source = Path("pp_recipes/pp_recipes.csv")
    with source.open(encoding="utf-8", newline="") as f:
        for number, row in enumerate(csv.DictReader(f), 1):
            rid = row["recipe_id"]
            if rid not in selected:
                continue
            original, recipe = subset[rid], selected[rid]
            assert number == original["source_record_number"], rid
            assert all(row[k] == v for k, v in original["source_values"].items()), rid
            raw_names = [entry[0] for section in ast.literal_eval(row["ingredients"]).values() for entry in section]
            assert recipe["raw_ingredient_names"] == raw_names, rid
            assert recipe["title"] == row["title"], rid
            assert recipe["duration_minutes"] == float(row["duration"]), rid
            assert recipe["nutrition_score"] == float(row["fsa_score"]), rid
            checked.append({"recipe_id": rid, "source_record_number": number, "source_values_match": True,
                            "reviewed_canonical_groups_match": True})
    assert len(checked) == len(selected)
    report = {"cases_checked": len(cases), "distinct_recipes_checked": len(selected),
              "source_sha256": file_hash(source), "cases_sha256": file_hash(folder / "cases.jsonl"),
              "references_sha256": file_hash(folder / "references.private.jsonl"),
              "manual_review_sha256": file_hash(folder / "manual_review.private.json"),
              "independently_transcribed_expected_values_match": True,
              "human_annotation_study": False, "records": checked}
    write_json(folder / "source_checks.private.json", report)
    print(f"Verified {len(cases)} development labels and {len(selected)} original source records. No API calls.")


if __name__ == "__main__":
    main()

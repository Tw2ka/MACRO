import copy
import json
import tempfile
import unittest
from pathlib import Path

from macro.evaluate_case_generation.benchmark import generate, profile_identity, validate, verify_saved
from macro.shared.benchmark_policy import GROUPS, POLICY_VERSION
from macro.shared.io import digest, file_hash, read_jsonl, write_json, write_jsonl


ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "configs/benchmark-v2.json").read_text(encoding="utf-8"))


class BenchmarkGenerationTests(unittest.TestCase):
    def fixture(self, folder):
        root = Path(folder)
        subset = root / "subset"
        groups = sorted(GROUPS)
        recipes = []
        for i in range(600):
            ingredients = sorted({groups[i % 8], groups[(i // 8) % 8]})
            recipes.append({"id": str(i), "title": "Source title", "duration_minutes": 5 + i % 60,
                            "nutrition_score": (i // 3 % 9) / 8, "nutrition_metric": "hummus_normalized_fsa",
                            "canonical_ingredients": ingredients, "ingredient_names": ingredients,
                            "raw_ingredient_names": ingredients, "source_record_number": i + 1,
                            "source_url": "https://example.invalid/" + str(i)})
        write_jsonl(subset / "recipes.jsonl", recipes)
        dataset_config = {"normalization": {"aliases": {g: [g] for g in groups}}}
        write_json(subset / "config.json", dataset_config)
        write_json(subset / "audit.json", {"recipes_sha256": file_hash(subset / "recipes.jsonl"),
                   "config_sha256": digest(dataset_config), "source_sha256": "fixture-only",
                   "manual_review_status": "pending"})
        pilot = root / "pilot.jsonl"
        write_jsonl(pilot, [{"candidate_pool": [{"id": "0"}, {"id": "1"}]}])
        config = copy.deepcopy(CONFIG)
        for counts in config["strata"].values():
            counts.update(dev=1, test=2)
        return subset, pilot, config

    def test_deterministic_generation_separation_labels_and_overwrite_guard(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            subset, pilot, config = self.fixture(folder)
            first = generate(subset, root / "one", config, pilot)
            second = generate(subset, root / "two", config, pilot)
            self.assertEqual(first["hashes"], second["hashes"])
            self.assertEqual(first["splits"]["dev"]["base_cases"], 9)
            self.assertEqual(first["splits"]["test"]["base_cases"], 18)
            self.assertEqual(verify_saved(root / "one")["recipe_overlap"], 0)
            mapping = json.loads((root / "one/private/source_map.json").read_text(encoding="utf-8"))
            self.assertFalse({"0", "1"} & {r["source_recipe_id"] for r in mapping.values()})
            public = read_jsonl(root / "one/test/cases.jsonl")
            for c in public:
                self.assertEqual(set(c), {"case_id", "profile", "request", "candidate_pool", "recommendations"})
                self.assertTrue(all("title" not in r and "source_url" not in r for r in c["candidate_pool"]))
            with self.assertRaisesRegex(ValueError, "Output directory exists"):
                generate(subset, root / "one", config, pilot)
            cases = {s: read_jsonl(root / "one" / s / "cases.jsonl") for s in ["dev", "test"]}
            refs = {s: read_jsonl(root / "one/private" / (s + ".references.jsonl")) for s in ["dev", "test"]}
            refs["test"][0]["verdict"] = "tampered"
            with self.assertRaisesRegex(ValueError, "Reference does not match"):
                validate(cases, refs, config)
            (root / "one/test/cases.jsonl").write_text("tampered", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Artifact hash mismatch"):
                verify_saved(root / "one")

    def test_changed_source_rejected_before_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            subset, pilot, config = self.fixture(folder)
            with (subset / "recipes.jsonl").open("a", encoding="utf-8") as stream:
                stream.write("\n")
            with self.assertRaisesRegex(ValueError, "Subset hash mismatch"):
                generate(subset, root / "output", config, pilot)
            self.assertFalse((root / "output").exists())

    def test_semantic_profile_identity_ignores_non_priority_order(self):
        profile = {"preferred_ingredients": ["garlic", "tomato"], "excluded_ingredients": [],
                   "hard_max_duration_minutes": 30, "objectives": ["nutrition", "preference"],
                   "priorities": ["nutrition", "preference"]}
        same = copy.deepcopy(profile)
        same["preferred_ingredients"].reverse()
        same["objectives"].reverse()
        self.assertEqual(profile_identity(profile), profile_identity(same))
        same["priorities"].reverse()
        self.assertNotEqual(profile_identity(profile), profile_identity(same))

    def test_project_configuration_balances_400_final_cases(self):
        self.assertEqual(sum(v["test"] for v in CONFIG["strata"].values()), 400)
        self.assertEqual(sum(v["dev"] for v in CONFIG["strata"].values()), 120)
        self.assertEqual(CONFIG["policy_version"], POLICY_VERSION)
        categories = {
            "constraint": ["constraint_ingredient", "constraint_duration_near", "constraint_duration_clear"],
            "dominance": ["dominance_near", "dominance_clear"],
            "tradeoff": ["tradeoff_resolved", "tradeoff_unresolved"],
            "control_tie": ["control_tie"], "both_violate": ["both_violate"]}
        for strata in categories.values():
            self.assertEqual(sum(CONFIG["strata"][s]["test"] for s in strata), 80)
            self.assertEqual(sum(CONFIG["strata"][s]["dev"] for s in strata), 24)


if __name__ == "__main__":
    unittest.main()

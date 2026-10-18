import copy
import json
import tempfile
import unittest
from pathlib import Path

from macro.evaluate_case_generation.dataset import (
    NUTRIENTS, Rejected, normalize_ingredient, normalize_record, prepare, vocabulary,
)


CONFIG = json.loads((Path(__file__).resolve().parents[1] / "configs/dataset-v1.json").read_text(encoding="utf-8"))


def source_row():
    row = {"recipe_id": "17", "title": "Garlic and carrots", "duration": "30",
           "fsa_score": "0.5", "normalization_comment": "", "servingSize [g]": "200",
           "servingsPerRecipe": "2", "recipe_url": "https://example.invalid/17",
           "ingredients": "{'main': [('chopped fresh garlic', '2 cloves'), ('carrots, diced', '1 cup')]}"}
    row.update({column: "1" for column in NUTRIENTS.values()})
    row["calories [cal]"] = "100"
    return row


class IngredientEvidenceTests(unittest.TestCase):
    def normalize(self, text):
        return normalize_ingredient(text, *vocabulary(CONFIG), CONFIG["normalization"]["non_matches"])

    def test_descriptor_plural_and_preparation_normalization(self):
        self.assertEqual(self.normalize("Chopped fresh garlic")["canonical_group"], "garlic")
        self.assertEqual(self.normalize("carrots (peeled)")["canonical_group"], "carrot")
        self.assertEqual(self.normalize("onions, diced")["canonical_group"], "onion")

    def test_hidden_mentions_are_not_erased(self):
        for text in ["broth (contains garlic)", "water, garlic", "garlic, optional onion", "garlic powder", "tomato sauce"]:
            with self.subTest(text=text), self.assertRaises(Rejected):
                self.normalize(text)

    def test_unknown_and_non_match_are_distinct(self):
        self.assertEqual(self.normalize("olive oil")["mapping_status"], "explicit_non_match")
        self.assertEqual(self.normalize("water")["mapping_status"], "outside_vocabulary")
        self.assertEqual(self.normalize("black olives")["canonical_group"], "olive")

    def test_alternatives_and_malformed_input_rejected(self):
        for text in ["garlic or onions", "", "garlic (chopped", "$template"]:
            with self.subTest(text=text), self.assertRaises(Rejected):
                self.normalize(text)


class RecipeValidationTests(unittest.TestCase):
    def test_retains_full_evidence_and_nutrient_values(self):
        r = normalize_record(source_row(), 9, CONFIG)
        self.assertEqual(r["canonical_ingredients"], ["carrot", "garlic"])
        self.assertEqual(r["source_record_number"], 9)
        self.assertEqual(r["ingredient_evidence"][0]["raw"], "chopped fresh garlic")
        self.assertEqual(set(r["nutrition_source_values"]), set(NUTRIENTS))

    def test_invalid_numbers_and_component_inconsistency(self):
        for field, value in [("duration", "0"), ("duration", "3000"), ("fsa_score", "0.6"),
                             ("protein [g]", "nan"), ("sodium [mg]", "-1"),
                             ("sugars [g]", "20"), ("servingSize [g]", "0"),
                             ("normalization_comment", "*")]:
            row = source_row()
            row[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(Rejected):
                normalize_record(row, 1, CONFIG)

    def test_macro_mass_is_not_double_counted(self):
        row = source_row()
        row.update({"servingSize [g]": "3", "sugars [g]": "1", "dietaryFiber [g]": "1"})
        normalize_record(row, 1, CONFIG)  # Sugar/fiber are included in carbohydrate.
        row["protein [g]"] = "200"
        with self.assertRaisesRegex(Rejected, "mass_exceeds"):
            normalize_record(row, 1, CONFIG)

    def test_build_is_reproducible_and_preserves_existing_outputs(self):
        import csv
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source.csv"
            row = source_row()
            with source.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(row))
                writer.writeheader()
                for i in range(8):
                    writer.writerow({**row, "recipe_id": str(100 + i)})
            config = copy.deepcopy(CONFIG)
            config["subset_size"] = 3
            a = prepare(source, root / "a", config)
            b = prepare(source, root / "b", config)
            self.assertEqual(a["recipes_sha256"], b["recipes_sha256"])
            self.assertEqual(a["selected_rows"], 3)
            with self.assertRaisesRegex(ValueError, "already exists"):
                prepare(source, root / "a", config)
            config["subset_size"] = 9
            with self.assertRaisesRegex(ValueError, "Only 8"):
                prepare(source, root / "insufficient", config)
            self.assertFalse((root / "insufficient").exists())


if __name__ == "__main__":
    unittest.main()

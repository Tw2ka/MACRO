import copy
import unittest

from macro.shared.benchmark_policy import evaluate_case


def case():
    return {"case_id": "example", "profile": {
        "preferred_ingredients": ["garlic", "tomato"], "excluded_ingredients": ["mushroom"],
        "hard_max_duration_minutes": 30, "objectives": ["preference", "nutrition"], "priorities": None},
        "candidate_pool": [
            {"id": "one", "canonical_ingredients": ["garlic", "tomato"], "duration_minutes": 20,
             "nutrition_score": .5, "nutrition_metric": "hummus_normalized_fsa"},
            {"id": "two", "canonical_ingredients": ["garlic"], "duration_minutes": 25,
             "nutrition_score": .75, "nutrition_metric": "hummus_normalized_fsa"}],
        "recommendations": {"A": {"recipe_id": "one", "explanation": "Facts"},
                            "B": {"recipe_id": "two", "explanation": "Other facts"}}}


class BenchmarkPolicyTests(unittest.TestCase):
    def test_missing_priorities_and_explicit_priorities(self):
        c = case()
        self.assertEqual(evaluate_case(c)["verdict"], "insufficient_information")
        c["profile"]["priorities"] = ["nutrition", "preference"]
        self.assertEqual(evaluate_case(c)["verdict"], "B")
        c["profile"]["priorities"].reverse()
        self.assertEqual(evaluate_case(c)["verdict"], "A")

    def test_feasibility_overrides_better_scores_and_boundary_allowed(self):
        c = case()
        c["profile"]["hard_max_duration_minutes"] = 20
        self.assertEqual(evaluate_case(c)["verdict"], "A")
        c["candidate_pool"][0]["canonical_ingredients"].append("mushroom")
        self.assertEqual(evaluate_case(c)["verdict"], "both_violate")

    def test_dominance_and_equal_controls_without_priorities(self):
        c = case()
        c["candidate_pool"][0]["nutrition_score"] = .75
        self.assertEqual(evaluate_case(c)["case_type"], "dominance")
        c["candidate_pool"][1]["canonical_ingredients"].append("tomato")
        self.assertEqual(evaluate_case(c)["verdict"], "tie")
        self.assertEqual(evaluate_case(c)["case_type"], "control_tie")

    def test_speed_is_explicit_and_lexicographic_ties_advance(self):
        c = case()
        c["candidate_pool"][0]["nutrition_score"] = .75
        c["candidate_pool"][0]["canonical_ingredients"] = ["garlic"]
        c["candidate_pool"][1]["canonical_ingredients"].append("tomato")
        c["profile"]["objectives"].append("speed")
        c["profile"]["priorities"] = ["nutrition", "speed", "preference"]
        self.assertEqual(evaluate_case(c)["verdict"], "A")
        c["profile"]["priorities"] = None
        self.assertEqual(evaluate_case(c)["verdict"], "insufficient_information")
        c["profile"]["hard_max_duration_minutes"] = None
        self.assertEqual(evaluate_case(c)["verdict"], "insufficient_information")

    def test_hard_limit_alone_does_not_reward_faster_recipe(self):
        c = case()
        c["candidate_pool"][1].update(canonical_ingredients=["garlic", "tomato"], nutrition_score=.5)
        self.assertEqual(evaluate_case(c)["verdict"], "tie")
        c["profile"]["objectives"].append("speed")
        self.assertEqual(evaluate_case(c)["verdict"], "A")

    def test_explanation_invariance_and_order_swap(self):
        c = case()
        c["profile"]["priorities"] = ["preference", "nutrition"]
        original = evaluate_case(c)
        c["recommendations"]["A"]["explanation"] = "Fiction and persuasion"
        self.assertEqual(evaluate_case(c), original)
        c["recommendations"] = {"A": c["recommendations"]["B"], "B": c["recommendations"]["A"]}
        self.assertEqual(evaluate_case(c)["verdict"], "B")

    def test_invalid_input_is_not_insufficient_information(self):
        invalid = []
        for key,value in [("priorities", ["nutrition"]), ("priorities", ["nutrition", "nutrition"]),
                          ("hard_max_duration_minutes", True), ("preferred_ingredients", []),
                          ("excluded_ingredients", ["garlic"]), ("objectives", [])]:
            c=case();c["profile"][key]=value;invalid.append(c)
        for key,value in [("nutrition_score", float("nan")), ("nutrition_score", .6),
                          ("nutrition_metric", "who"), ("duration_minutes", -1),
                          ("canonical_ingredients", ["chicken"])]:
            c=case();c["candidate_pool"][0][key]=value;invalid.append(c)
        for c in invalid:
            with self.subTest(case=c), self.assertRaises(ValueError):
                evaluate_case(c)

    def test_all_evidence_pointers_resolve(self):
        c=case(); result=evaluate_case(c)
        for ref in result["evidence_references"]:
            current=c
            for part in ref.lstrip("/").split("/"):
                current=current[int(part)] if isinstance(current,list) else current[part]
        before=copy.deepcopy(c)
        evaluate_case(c)
        self.assertEqual(c,before)


if __name__ == "__main__":
    unittest.main()

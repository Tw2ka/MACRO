"""Internal deterministic fixtures. Never part of the application run command."""
import json

from macro.shared.policy import choose, compare
from macro.ai_agents.prompts import prompt
from macro.ai_agents.schemas import assessment_groups, validate_assessment
from macro.evaluation.runner import _run


class OfflineProvider:
    """Synthetic plumbing fixture. This is not an LLM and must never be reported as model accuracy."""
    def assess(self, role, evidence, tag, feedback=None):
        # Separate visible-input fixture adapter; never reads private references.
        p = evidence["profile"]
        preferences, attributes, explanations = [], [], []
        for slot in ["A", "B"]:
            i = next(i for i, r in enumerate(evidence["candidate_pool"]) if r["id"] == evidence["recommendations"][slot]["recipe_id"])
            r = evidence["candidate_pool"][i]
            present = [x for x in p["preferred_ingredients"] if x in r["canonical_ingredients"]]
            score = len(present) / len(p["preferred_ingredients"])
            violations = (["duration"] if r["duration_minutes"] > p["max_duration_minutes"] + 1e-9 else [])
            violations += ["excluded:" + x for x in p["excluded_ingredients"] if x in r["canonical_ingredients"]]
            preferences.append({"candidate": slot, "preference_score": score, "evidence": ["/profile/preferred_ingredients", f"/candidate_pool/{i}/canonical_ingredients"]})
            attributes.append({"candidate": slot, "feasible": not violations, "violations": violations, "nutrition_score": r["nutrition_score"], "evidence": ["/profile/max_duration_minutes", f"/candidate_pool/{i}/duration_minutes", f"/candidate_pool/{i}/nutrition_score"]})
            explanations.append({"candidate": slot, "supported": True, "relevant_tradeoffs_disclosed": True, "issues": [], "evidence": [f"/recommendations/{slot}/explanation"]})
        pref = compare(preferences[0]["preference_score"], preferences[1]["preference_score"])
        nut = compare(attributes[0]["nutrition_score"], attributes[1]["nutrition_score"])
        if role == "single":
            decision, _ = choose(attributes[0]["feasible"], attributes[1]["feasible"], pref, nut, p["priority"])
            result = {"preferences": preferences, "attributes": attributes, "explanations": explanations,
                      "preference_comparison": pref, "nutrition_comparison": nut, "priority": p["priority"], "decision": decision}
        elif role == "preference":
            result = {"findings": preferences, "preference_comparison": pref, "priority": p["priority"]}
        elif role == "attribute":
            result = {"findings": attributes, "nutrition_comparison": nut}
        else:
            result = {"findings": explanations}
        result["rationale"] = "OFFLINE deterministic fixture; not a model judgment."
        wire = as_wire(role, result)
        parsed = validate_assessment(role, wire, evidence)
        system, user = prompt(role, evidence)
        return {"assessment": parsed, "raw": json.dumps(wire), "system_prompt": system, "user_prompt": user,
                "tool_calls": [], "status": "ok", "provider": "offline_fixture"}


def as_wire(role, result):
    result = json.loads(json.dumps(result))
    for group in assessment_groups(role):
        result[group] = {finding["candidate"]: {key: value for key, value in finding.items() if key != "candidate"}
                         for finding in result[group]}
    return result


def run_fixture(folder, config, **kwargs):
    return _run(folder, config, lambda recorder: OfflineProvider(), "offline", **kwargs)

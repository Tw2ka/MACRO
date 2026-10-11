"""Fixed aggregation of independent specialist assessments; no model calls."""
from macro.shared.policy import choose, score_comparisons
from macro.ai_agents.schemas import SCHEMAS

AGGREGATION_VERSION = "reported-scores-v2"


def aggregate(records):
    failure = {"status": "technical_failure", "decision": None,
               "aggregation_version": AGGREGATION_VERSION,
               "trace": ["A specialist output is missing or invalid"]}
    if any(records.get(role, {}).get("status") != "ok" for role in ["preference", "attribute", "explanation"]):
        return failure
    # Recheck persisted normalized assessments, without needing case facts or gold labels.
    try:
        pref, attr, expl = [SCHEMAS[role].model_validate(records[role]["assessment"]).model_dump()
                            for role in ["preference", "attribute", "explanation"]]
        if any(sorted(f["candidate"] for f in a["findings"]) != ["A", "B"] for a in [pref, attr, expl]):
            return failure
    except (ValueError, TypeError, KeyError):
        return failure
    af = {f["candidate"]: f for f in attr["findings"]}
    reported = {"preference_comparison": pref["preference_comparison"],
                "nutrition_comparison": attr["nutrition_comparison"]}
    derived, warnings = score_comparisons(pref["findings"], attr["findings"], reported)
    # choose applies feasibility before any soft objective. Comparisons are arithmetic;
    # mismatched labels are retained as diagnostics, never used as votes or vetoes.
    decision, reason = choose(af["A"]["feasible"], af["B"]["feasible"],
                              derived["preference_comparison"], derived["nutrition_comparison"], pref["priority"])
    return {"status": "ok", "decision": decision, "attributes": attr["findings"],
            "aggregation_version": AGGREGATION_VERSION, "reported_comparisons": reported,
            "derived_comparisons": derived, "comparison_diagnostics": warnings,
            "preferences": pref["findings"], "explanations": expl["findings"], "trace": [reason],
            "diagnostics": [x["candidate"] + ": explanation issue" for x in expl["findings"] if not x["supported"] or not x["relevant_tradeoffs_disclosed"]]}

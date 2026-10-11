"""Deterministic benchmark reference. Never called by the live provider."""
import math
import re

POLICY_VERSION = "pilot-v1"
EPSILON = 1e-9
# Deliberately bounded exact-name groups. Olive oil is not an olive preference match.
ALIASES = {
    "tomato": ["tomato", "tomatoes", "cherry tomatoes", "grape tomatoes", "plum tomatoes", "roma tomatoes"],
    "broccoli": ["broccoli", "broccoli florets", "fresh broccoli", "frozen broccoli"],
    "spinach": ["spinach", "fresh spinach", "baby spinach", "frozen spinach", "frozen chopped spinach"],
    "mushroom": ["mushroom", "mushrooms", "fresh mushrooms", "button mushrooms", "white mushrooms", "sliced mushrooms", "cremini mushrooms"],
    "onion": ["onion", "onions", "white onion", "white onions", "yellow onion", "yellow onions", "red onion", "red onions"],
    "garlic": ["garlic", "garlic clove", "garlic cloves", "fresh garlic", "minced garlic"],
    "carrot": ["carrot", "carrots", "baby carrots", "fresh carrots"],
    "olive": ["olive", "olives", "black olives", "green olives", "kalamata olives", "pitted black olives", "pitted green olives"],
}
ALIAS_LOOKUP = {alias: group for group, aliases in ALIASES.items() for alias in aliases}
DESCRIPTORS = re.compile(r"^(?:(?:finely chopped|thinly sliced|chopped|sliced|diced|minced|large|small|medium|fresh|frozen|whole|raw)\s+)+")
MENTIONS = re.compile(r"\b(?:tomato(?:es)?|broccoli|spinach|mushrooms?|onions?|garlic|carrots?|olives?)\b", re.IGNORECASE)


def ingredient_head(name):
    head = name.lower().strip().split(',')[0].split('(')[0].strip()
    return DESCRIPTORS.sub('', head)


def canonical_matches(names):
    return sorted({ALIAS_LOOKUP[name.strip().lower()] for name in names if name.strip().lower() in ALIAS_LOOKUP})


def compare(a, b):
    return "equal" if abs(a - b) <= EPSILON else "A" if a > b else "B"


def score_comparisons(preferences, attributes, reported):
    """Derive comparisons from model-reported numbers; never consult case references."""
    derived, diagnostics = {}, []
    for criterion, findings, score in [("preference", preferences, "preference_score"),
                                       ("nutrition", attributes, "nutrition_score")]:
        values = {f["candidate"]: f[score] for f in findings}
        field = criterion + "_comparison"
        derived[field] = compare(values["A"], values["B"])
        if derived[field] != reported[field]:
            diagnostics.append({"code": "score_comparison_mismatch", "criterion": criterion,
                                "reported": reported[field], "derived": derived[field],
                                "scores": values})
    return derived, diagnostics


def choose(feasible_a, feasible_b, preference, nutrition, priority):
    if not feasible_a and not feasible_b:
        return "neither_feasible", "both candidates fail hard constraints"
    if feasible_a != feasible_b:
        return ("A" if feasible_a else "B"), "hard constraints take precedence"
    if preference == nutrition == "equal":
        return "tie", "both declared objectives equal within tolerance"
    if preference == "equal":
        return nutrition, "nutrition dominance with equal preference"
    if nutrition == "equal" or preference == nutrition:
        return preference, "Pareto dominance among feasible candidates"
    if priority == "unspecified":
        return "unresolved", "conflicting objectives and insufficient priorities"
    return (preference if priority == "preference_first" else nutrition), "declared lexicographic priority"


def findings(case):
    p = case["profile"]
    candidates = {}
    for slot in ["A", "B"]:
        r = next(x for x in case["candidate_pool"] if x["id"] == case["recommendations"][slot]["recipe_id"])
        violations = []
        if r["duration_minutes"] > p["max_duration_minutes"] + EPSILON:
            violations.append("duration")
        violations += ["excluded:" + x for x in p["excluded_ingredients"] if x in r["canonical_ingredients"]]
        candidates[slot] = {"feasible": not violations, "violations": violations,
                            "preference_score": len(set(p["preferred_ingredients"]) & set(r["canonical_ingredients"])) / len(p["preferred_ingredients"]),
                            "nutrition_score": r["nutrition_score"]}
    pref = compare(candidates["A"]["preference_score"], candidates["B"]["preference_score"])
    nut = compare(candidates["A"]["nutrition_score"], candidates["B"]["nutrition_score"])
    decision, reason = choose(candidates["A"]["feasible"], candidates["B"]["feasible"], pref, nut, p["priority"])
    if candidates["A"]["feasible"] != candidates["B"]["feasible"]:
        kind = "constraint"
    elif all(x["feasible"] for x in candidates.values()):
        kind = "tradeoff" if pref != "equal" and nut != "equal" and pref != nut else "tie" if pref == nut == "equal" else "dominance"
    else:
        kind = "both_infeasible"
    return {"candidates": candidates, "preference_comparison": pref, "nutrition_comparison": nut,
            "decision": decision, "reason": reason, "case_type": kind}


def validate_case(case):
    p = case["profile"]
    assert p["preferred_ingredients"] and len(set(p["preferred_ingredients"])) == len(p["preferred_ingredients"])
    assert not set(p["preferred_ingredients"]) & set(p["excluded_ingredients"])
    assert set(p["preferred_ingredients"] + p["excluded_ingredients"]) <= set(ALIASES)
    assert p["priority"] in ["preference_first", "nutrition_first", "unspecified"]
    assert math.isfinite(p["max_duration_minutes"]) and p["max_duration_minutes"] > 0
    ids = [r["id"] for r in case["candidate_pool"]]
    assert len(ids) == len(set(ids)) and len(ids) >= 2
    assert case["recommendations"]["A"]["recipe_id"] != case["recommendations"]["B"]["recipe_id"]
    for slot in ["A", "B"]:
        assert case["recommendations"][slot]["recipe_id"] in ids
    for r in case["candidate_pool"]:
        assert math.isfinite(r["duration_minutes"]) and r["duration_minutes"] > 0
        assert math.isfinite(r["nutrition_score"]) and 0 <= r["nutrition_score"] <= 1
        assert canonical_matches(r["ingredient_names"]) == r["canonical_ingredients"]


def swapped(case):
    import copy
    result = copy.deepcopy(case)
    result["recommendations"] = {"A": result["recommendations"]["B"], "B": result["recommendations"]["A"]}
    return result


def canonical_decision(case, decision):
    return case["recommendations"][decision]["recipe_id"] if decision in ["A", "B"] else decision

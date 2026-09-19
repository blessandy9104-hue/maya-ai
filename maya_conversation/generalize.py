"""Batch 8I phase 2: task/problem representation for comparison.

Turns the structured 8G orphaned-turn result into a normalized, comparable
task fingerprint so a NEW task can be compared with a KNOWN task without
assuming identity.

Purity:
- No clock, no randomness, no file writes, no network.
- All normalization is a pure function of the inputs; ordering is canonical
  (sorted), text is length-capped, numbers are finite-coerced.
- ``TaskMemory`` is an in-memory store; nothing persists to disk.
- Never raises; malformed inputs degrade to safe neutral fingerprints.

Fail-open:
- Unknown/missing fields become neutral defaults; never a crash.
"""
from __future__ import annotations

_MATH_HINTS = ("math", "mathematics", "units", "calculation", "numeric",
               "measure")
_GUARD_DOMAINS = ("psychology", "philosophy", "safety", "clinical")
_DEFAULT_OBJECTIVE = "answer"
_DEFAULT_INTENT = "unspecified"
_TEXT_CAP = 160


def _finite(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if number != number or number in (float("inf"), float("-inf")):
        return 0.0
    return number


def _text(value):
    if not isinstance(value, str):
        return ""
    return value.strip()[: _TEXT_CAP]


def _domain_list(conv_result):
    routes = conv_result.get("routes") if isinstance(conv_result, dict) else None
    if not isinstance(routes, dict):
        return []
    domains = routes.get("domains")
    if isinstance(domains, (list, tuple, set)):
        return sorted(str(d) for d in domains if isinstance(d, str))
    return []


def _string_list(value):
    if isinstance(value, (list, tuple, set)):
        out = []
        for item in value:
            if isinstance(item, str) and item.strip():
                out.append(item.strip())
        return sorted(out)
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _holds_list(plan):
    if not isinstance(plan, dict):
        return []
    holds = plan.get("holds")
    return _string_list(holds)


def characterize_task(conv_result, user_text="", resource_pressure=False):
    """Build a normalized, comparable task fingerprint.

    Returns a dict (never raises) with stable keys:
      domains, primary_intent, objective, constraints, references_resolved,
      ambiguous, is_correction, modality, math_structure, evidence_types,
      consequence_level, resource_level, text_signature, input_brief.
    """
    conv_result = conv_result if isinstance(conv_result, dict) else {}
    interpretation = conv_result.get("interpretation")
    interpretation = interpretation if isinstance(interpretation, dict) else {}
    plan = conv_result.get("plan")
    plan = plan if isinstance(plan, dict) else {}

    domains = _domain_list(conv_result)
    constraints = _string_list(interpretation.get("constraints"))
    holds = _holds_list(plan)

    intent = interpretation.get("primary_intent") or interpretation.get("intent")
    if not isinstance(intent, str):
        intent = _DEFAULT_INTENT
    intent = intent.strip() or _DEFAULT_INTENT

    objective = plan.get("objective")
    if not isinstance(objective, str) or not objective.strip():
        objective = _DEFAULT_OBJECTIVE

    references = interpretation.get("references")
    if isinstance(references, list):
        resolved_refs = sum(
            1 for r in references if isinstance(r, dict) and r.get("antecedent"))
    else:
        resolved_refs = 0

    ambiguous = bool(interpretation.get("ambiguous"))
    is_correction = bool(interpretation.get("is_correction"))

    modality = interpretation.get("modality")
    if not isinstance(modality, str):
        modality = "text"

    math_structure = any(
        hint in " ".join(domains).lower() for hint in _MATH_HINTS)

    evidence_types = []
    claims = interpretation.get("claims")
    if isinstance(claims, list):
        for claim in claims:
            if isinstance(claim, dict):
                status = claim.get("epistemic_status")
                if isinstance(status, str) and status:
                    evidence_types.append(status)
    evidence_types = sorted(set(evidence_types))

    if any(d in _GUARD_DOMAINS for d in domains) or holds:
        consequence_level = "elevated_guard"
    else:
        consequence_level = "ordinary"

    text_signature = _text(user_text)
    input_brief = len(text_signature) <= 24 and "?" not in text_signature

    return {
        "domains": domains,
        "primary_intent": intent,
        "objective": objective,
        "constraints": constraints,
        "references_resolved": resolved_refs,
        "ambiguous": ambiguous,
        "is_correction": is_correction,
        "modality": modality,
        "math_structure": math_structure,
        "evidence_types": evidence_types,
        "consequence_level": consequence_level,
        "resource_level": "pressure" if resource_pressure else "safe",
        "text_signature": text_signature,
        "input_brief": input_brief,
    }


def to_key(fingerprint):
    """Canonical identity string for exact seen/new comparison."""
    if not isinstance(fingerprint, dict):
        return str(type(fingerprint).__name__)
    parts = [
        "domains=%s" % "|".join(_string_list(fingerprint.get("domains"))),
        "intent=%s" % _text(fingerprint.get("primary_intent")),
        "objective=%s" % _text(fingerprint.get("objective")),
        "constraints=%s" % "|".join(
            _string_list(fingerprint.get("constraints"))),
        "refs=%d" % max(0, _finite(fingerprint.get("references_resolved"))),
        "ambiguous=%s" % bool(fingerprint.get("ambiguous")),
        "correction=%s" % bool(fingerprint.get("is_correction")),
        "modality=%s" % _text(fingerprint.get("modality")),
        "math=%s" % bool(fingerprint.get("math_structure")),
        "evidence=%s" % "|".join(
            _string_list(fingerprint.get("evidence_types"))),
        "consequence=%s" % _text(fingerprint.get("consequence_level")),
        "resource=%s" % _text(fingerprint.get("resource_level")),
        "text=%s" % _text(fingerprint.get("text_signature")),
        "brief=%s" % bool(fingerprint.get("input_brief")),
    ]
    return ";".join(parts)


class TaskMemory:
    """In-memory store distinguishing NEW from SEEN task fingerprints."""

    def __init__(self):
        self._seen = {}   # key -> {fingerprint, occurrences}
        self._order = []  # stable insertion order for deterministic listing

    def remember(self, fingerprint):
        key = to_key(fingerprint)
        entry = self._seen.get(key)
        if entry is None:
            entry = {"fingerprint": dict(fingerprint or {}), "occurrences": 0}
            self._seen[key] = entry
            self._order.append(key)
        entry["occurrences"] += 1
        return dict(entry)

    def seen(self, fingerprint):
        return to_key(fingerprint) in self._seen

    def occurrences(self, fingerprint):
        entry = self._seen.get(to_key(fingerprint))
        return entry["occurrences"] if entry else 0

    def memories(self):
        """Deterministic insertion-ordered snapshot of remembered tasks."""
        return [(key, dict(self._seen[key])) for key in self._order]

    def counts(self):
        return {
            "distinct_tasks": len(self._seen),
            "total_sightings": sum(
                e["occurrences"] for e in self._seen.values()),
        }


# --------------------------------------------------------------------------
# PHASE 3 — similarity and difference
# --------------------------------------------------------------------------

SEVERITY_NOMINAL = "nominal"
SEVERITY_ELEVATED = "elevated"


def _set(value):
    if isinstance(value, (list, tuple, set)):
        return set(str(v) for v in value if isinstance(v, str))
    return set()


def _jaccard(a, b):
    a = set(a) if not isinstance(a, set) else a
    b = set(b) if not isinstance(b, set) else b
    union = len(a | b)
    if union == 0:
        return 1.0
    return len(a & b) / union


def _binary_match(a, b):
    return 1.0 if a == b else 0.0


def _refs_linear(a, b):
    a = max(0, int(_finite(a)))
    b = max(0, int(_finite(b)))
    denom = max(a, b, 1)
    return 1.0 - abs(a - b) / denom


def _word_tokens(text):
    text = str(text).lower()
    tokens = []
    current = []
    for ch in text:
        if ch.isalnum():
            current.append(ch)
        else:
            if current:
                tokens.append("".join(current))
                current = []
    if current:
        tokens.append("".join(current))
    return tokens


def _text_similarity(a, b):
    tokens_a = _word_tokens(a)
    tokens_b = _word_tokens(b)
    if not tokens_a and not tokens_b:
        return 1.0
    if not tokens_a or not tokens_b:
        return 0.0
    a_set = set(tokens_a)
    b_set = set(tokens_b)
    return _jaccard(a_set, b_set)


_FEATURE_WEIGHTS = {
    "domains": 0.25,
    "objective": 0.15,
    "intent": 0.12,
    "math_structure": 0.08,
    "consequence_level": 0.12,
    "resource_level": 0.08,
    "constraints": 0.10,
    "modality": 0.04,
    "brief": 0.03,
    "refs": 0.02,
    "ambiguous": 0.01,
}


def task_similarity(fingerprint_a, fingerprint_b):
    """Deterministic structured similarity with explicit difference list.

    Returns a dict with:
      score: float 0..1 (weighted average of features)
      per_feature: {feature: score}
      differences: [{feature, a_value, b_value, severity}]
      transfer_hints: human-readable notes about where transfer is risky
    """
    a = fingerprint_a if isinstance(fingerprint_a, dict) else {}
    b = fingerprint_b if isinstance(fingerprint_b, dict) else {}

    per_feature = {}

    per_feature["domains"] = _jaccard(
        _set(a.get("domains")), _set(b.get("domains")))
    per_feature["objective"] = _binary_match(
        str(a.get("objective") or ""), str(b.get("objective") or ""))
    per_feature["intent"] = _binary_match(
        str(a.get("primary_intent") or ""),
        str(b.get("primary_intent") or ""))
    per_feature["math_structure"] = _binary_match(
        bool(a.get("math_structure")), bool(b.get("math_structure")))
    per_feature["consequence_level"] = _binary_match(
        str(a.get("consequence_level") or ""),
        str(b.get("consequence_level") or ""))
    per_feature["resource_level"] = _binary_match(
        str(a.get("resource_level") or ""),
        str(b.get("resource_level") or ""))
    per_feature["constraints"] = _jaccard(
        _set(a.get("constraints")), _set(b.get("constraints")))
    per_feature["modality"] = _binary_match(
        str(a.get("modality") or ""), str(b.get("modality") or ""))
    per_feature["brief"] = _binary_match(
        bool(a.get("input_brief")), bool(b.get("input_brief")))
    per_feature["refs"] = _refs_linear(
        a.get("references_resolved", 0), b.get("references_resolved", 0))
    per_feature["ambiguous"] = _binary_match(
        bool(a.get("ambiguous")), bool(b.get("ambiguous")))

    differences = []
    _features_info = [
        ("domains", a.get("domains", []), b.get("domains", []), False),
        ("objective", a.get("objective"), b.get("objective"), False),
        ("intent", a.get("primary_intent"), b.get("primary_intent"), False),
        ("math_structure", a.get("math_structure"), b.get("math_structure"), False),
        ("consequence_level", a.get("consequence_level"), b.get("consequence_level"), True),
        ("resource_level", a.get("resource_level"), b.get("resource_level"), False),
        ("constraints", a.get("constraints", []), b.get("constraints", []), False),
        ("modality", a.get("modality"), b.get("modality"), False),
        ("input_brief", a.get("input_brief"), b.get("input_brief"), False),
        ("references_resolved", a.get("references_resolved", 0), b.get("references_resolved", 0), False),
        ("ambiguous", a.get("ambiguous"), b.get("ambiguous"), False),
    ]

    for feat, va, vb, guard in _features_info:
        if _binary_match(va, vb) < 1.0 and (not _set(va) or not _set(vb) or va != vb):
            sev = SEVERITY_ELEVATED if guard and va != vb else SEVERITY_NOMINAL
            differences.append({
                "feature": feat, "a_value": va, "b_value": vb,
                "severity": sev,
            })

    score = 0.0
    weight_sum = 0.0
    for feat, weight in _FEATURE_WEIGHTS.items():
        score += per_feature[feat] * weight
        weight_sum += weight
    if weight_sum > 0:
        score /= weight_sum

    transfer_hints = []
    for diff in differences:
        feat = diff["feature"]
        sev = diff["severity"]
        if sev == SEVERITY_ELEVATED:
            transfer_hints.append(
                "%s differs critically (old method may be unsafe here)" % feat)
        elif feat in ("domains", "consequence_level"):
            transfer_hints.append(
                "%s differs (validate transfer explicitly)" % feat)

    return {
        "score": _finite(score),
        "per_feature": per_feature,
        "differences": differences,
        "transfer_hints": transfer_hints,
    }


# --------------------------------------------------------------------------
# PHASE 6 — transfer boundaries
# --------------------------------------------------------------------------

def transfer_boundary_check(hypothesis, fingerprint, similarity=None):
    """Determine whether a NEW task falls within the validated scope.

    ``hypothesis`` must have ``conditions`` (positive, required features)
    and ``exclusions`` (negative, features that invalidate transfer).

    Returns:
      within_scope: True only when ALL conditions match AND NO exclusion
                    fires.
      reasons: list of explicit reason-strings for any boundary violation.
      applicable: whether the method can even be attempted (positive
                  conditions satisfied or trivially satisfied).
      matches: per-condition match dict for downstream reporting.
    """
    if hypothesis is None or fingerprint is None:
        return {"within_scope": False, "reasons": [],
                "applicable": False, "matches": {}}
    hyp_conditions = hypothesis.conditions if hasattr(hypothesis, "conditions") else (hypothesis.get("conditions") if isinstance(hypothesis, dict) else {})
    hyp_exclusions = hypothesis.exclusions if hasattr(hypothesis, "exclusions") else (hypothesis.get("exclusions") if isinstance(hypothesis, dict) else {})
    if not isinstance(hyp_conditions, dict):
        hyp_conditions = {}
    if not isinstance(hyp_exclusions, dict):
        hyp_exclusions = {}
    fp = fingerprint if isinstance(fingerprint, dict) else {}

    reasons = []
    matches = {}
    all_conditions_met = True

    for key, required_value in hyp_conditions.items():
        actual = fp.get(key)
        if isinstance(required_value, (list, tuple, set)):
            actual_set = _set(actual) if actual is not None else set()
            met = bool(set(str(v) for v in required_value) & actual_set)
        elif isinstance(required_value, bool):
            met = bool(actual) == required_value
        else:
            met = str(actual) == str(required_value)
        matches[key] = met
        if not met:
            all_conditions_met = False
            reasons.append(
                "condition '%s' not met: expected %r, got %r"
                % (key, required_value, actual))

    for key, bad_value in hyp_exclusions.items():
        actual = fp.get(key)
        if isinstance(bad_value, (list, tuple, set)):
            actual_set = _set(actual) if actual is not None else set()
            fired = bool(set(str(v) for v in bad_value) & actual_set)
        elif isinstance(bad_value, bool):
            fired = bool(actual) == bad_value and bad_value is True
        else:
            fired = str(actual) == str(bad_value)
        if fired:
            reasons.append(
                "exclusion '%s' fired: got %r (matches forbidden %r)"
                % (key, actual, bad_value))

    applicable = all_conditions_met
    within_scope = applicable and len(reasons) == 0
    return {
        "within_scope": within_scope,
        "reasons": reasons,
        "applicable": applicable,
        "matches": matches,
    }
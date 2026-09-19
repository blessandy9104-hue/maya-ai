"""Relevance-driven pathway orchestration (Batch 8G).

Decides, from one interpreted turn, *which* reasoning pathways are warranted
and which are not. Nothing is engaged by default: a plain conversational line
stays plain. Domain engagement is a deterministic keyword + intent decision,
never a hard gate, and the decision is surfaced to the response planner so the
choice is observable and testable.

Justified 8F math usage lives here too: when multiple psychology hypotheses
form a confidence distribution, :func:`hypotheses_entropy` reports the
normalized entropy of that distribution (``maya_math.information``), instead
of hedging in prose. This is exactly the kind of "use math only when it buys
information" boundary the 8G directive requires.
"""
from __future__ import annotations

import re

_DIGIT_RE = re.compile(r"\b\d[\d,\.]*(%|°|kg|kgm|km|ml|cm|m\b|s\b|sec|min|hr|"
                       r"hrs|days?|weeks?|months?|years?|mph|kwh|gb|tb|mb|gbps|"
                       r"mbtu|gb)\b|\b[\d,]+(\.\d+)?\b")
_MATH_VERBS = {
    "calculate", "compute", "average", "median", "probability",
    "probabilities", "percentage", "percent", "ratio", "proportion",
    "statistics", "statistical", "standard deviation", "variance", "entropy",
    "odds", "expected value", "correlation", "regression", "normalize",
    "normalized", "divide", "subtract", "multiply", "math", "mathematics",
    "maths", "how much", "how many",
    "what is the probability", "what is the entropy",
}
_PSYCH_WORDS = {
    "procrastination", "procrastinate", "habit", "habits", "motivation",
    "motivated", "attention", "focus", "memory", "emotion", "emotions",
    "emotional", "fear", "anxiety", "stress", "bias", "biases", "heuristic",
    "cognitive", "decision", "decisions", "willpower", "self control",
    "behavior", "behaviour", "learning", "mindset", "boredom", "regret",
    "guilt", "impulse", "goals", "dopamine", "reward", "identity",
    "motivational", "personality", "procrastinating", "anxious", "depressed",
    "sad", "lonely", "overwhelmed", "psychology", "psychologist",
    "psychologically",
}
_PHILOSOPHY_STRICT = {
    "consciousness", "free will", "determinism", "ethics", "moral", "morality",
    "virtue", "justice", "god", "existence", "existential", "meaning of life",
    "reality", "truth", "knowledge", "belief", "metaphysics", "ontology",
    "epistemology", "identity", "purpose", "nihilism", "authenticity",
    "paradox", "dualism", "materialism", "idealism", "philosophy",
    "philosophical", "philosopher",
}
_PLAN_WORDS = {
    "plan", "plans", "planning", "roadmap", "schedule", "steps", "strategy",
    "design", "blueprint", "outline", "how do i start", "project plan",
    "timeline", "milestones",
}
_EVIDENCE_WORDS = {
    "source", "sources", "according to", "research shows", "studies show",
    "studies suggest", "is it true", "is that true", "does that support",
    "evidence", "contradict", "disagree", "agree with", "consistent with",
    "verify", "confirm", "falsify", "peer reviewed", "cite", "citation",
    "who says", "prove", "proof",
}
_NEGATION_ROUTES = ("not", "don.t", "doesn.t", "never", "rather than")

MATHEMATICS = "mathematics"
PSYCHOLOGY = "psychology"
PHILOSOPHY = "philosophy"
EVIDENCE = "evidence"
PLANNING = "planning"
PLAIN = "plain"

_DOMAINS_ORDER = (MATHEMATICS, PSYCHOLOGY, PHILOSOPHY, EVIDENCE, PLANNING)


def _contains_any(text, tokens):
    low = text.lower()
    return sorted({token for token in tokens if token in low})


def route(interpretation, state=None):
    """Engage zero or more reasoning pathways for one interpreted turn.

    Returns a dict: ``domains`` (ordered engagement), ``engagements``
    (per-domain matched tokens), ``plain`` (bool), ``notes``.

    The matching surface includes the resolved topic/reference when present,
    so a bare follow-up ("and about free will?") keeps the philosophy route
    engaged — topic persistence is part of routing, not magic.
    """
    cleaned = interpretation.get("utterance", "")
    intent = interpretation.get("primary_intent", "")
    normalized = interpretation.get("normalized", "").lower()
    text = cleaned or ""
    low = text.lower()

    # topic surface: explicit new topic, else resolved reference, else state
    # anchor (the lowest-ranked antecedent), all lowercased.
    topic_lower = str(interpretation.get("new_topic") or "") or ""
    if not topic_lower:
        references = interpretation.get("references") or []
        if references:
            topic_lower = str(references[0].get("antecedent") or "")
    if not topic_lower and state is not None:
        topic_lower = str(getattr(state, "topic", "") or "")
    surface = low + " " + str(topic_lower).lower()

    engagements = {}
    ordered = []

    # --- mathematics (numeric + unit + math verbs) -----------------------
    math_tokens = _contains_any(surface, _MATH_VERBS)
    has_digit = bool(_DIGIT_RE.search(text))
    if math_tokens or has_digit:
        score = len(math_tokens) + (0.5 if has_digit else 0.0)
        reason = ("numeric/units detected" if has_digit else "math verbs detected")
        engagements[MATHEMATICS] = {
            "tokens": sorted(set(math_tokens) or ["<numeric>"]),
            "reason": reason,
            "score": round(score, 2),
            "justified": True,
        }

    # --- psychology (behavior/cognition/emotion) -------------------------
    psych_tokens = _contains_any(surface, _PSYCH_WORDS)
    if psych_tokens:
        engagements[PSYCHOLOGY] = {
            "tokens": sorted(set(psych_tokens)),
            "reason": "behavior/cognition/emotion vocabulary",
            "score": len(psych_tokens),
            "justified": True,
        }

    # --- philosophy (strict metaphysics/epistemology/ethics vocabulary) ---
    phil_tokens = _contains_any(surface, _PHILOSOPHY_STRICT)
    if phil_tokens:
        engagements[PHILOSOPHY] = {
            "tokens": sorted(set(phil_tokens)),
            "reason": "philosophy vocabulary",
            "score": len(phil_tokens),
            "justified": True,
        }
    elif intent in ("reason_or_cause", "request_for_explanation", "definition_or_information") \
            and _contains_any(surface, {"should", "ought", "why"}):
        # "should I X" is typically practical; only treat explicit normative
        # vocabulary as philosophy.
        normative = _contains_any(surface, {"should", "ought", "right thing",
                                            "wrong to", "morally", "ethically",
                                            "obligation"})
        if normative:
            engagements[PHILOSOPHY] = {
                "tokens": sorted(set(normative)),
                "reason": "normative vocabulary",
                "score": len(normative),
                "justified": True,
            }

    # --- evidence / world-model context ----------------------------------
    evidence_tokens = _contains_any(surface, _EVIDENCE_WORDS)
    if evidence_tokens:
        engagements[EVIDENCE] = {
            "tokens": sorted(set(evidence_tokens)),
            "reason": "claim/source/consistency vocabulary",
            "score": len(evidence_tokens),
            "justified": True,
        }

    # --- planning ----------------------------------------------------------
    plan_tokens = _contains_any(surface, _PLAN_WORDS)
    if plan_tokens and intent not in ("statement_or_general_request",):
        engagements[PLANNING] = {
            "tokens": sorted(set(plan_tokens)),
            "reason": "plan/design vocabulary",
            "score": len(plan_tokens),
            "justified": True,
        }

    ordered = [domain for domain in _DOMAINS_ORDER if domain in engagements]
    plain = not ordered

    # cross-domain notes: when psychology hypotheses are competing, entropy is
    # only computed there, never here (this module only owns *routing*).
    notes = []
    if PSYCHOLOGY in engagements:
        notes.append("psychology: interpretations remain hypotheses, never "
                     "diagnoses; may quantify uncertainty with 8F entropy")
    if PHILOSOPHY in engagements:
        notes.append("philosophy: disagreement is retained as disagreement, "
                     "never flattened into preference")
    if MATHEMATICS in engagements:
        notes.append("mathematics: engaged only when numeric/units present; "
                     "results are CALCULATED status")

    return {
        "domains": ordered,
        "engagements": engagements,
        "plain": plain,
        "notes": notes,
        "interpretation_ref": interpretation.get("normalized", ""),
    }


def hypotheses_entropy(weights):
    """Normalized entropy of a probability-mass vector, via 8F substrate.

    ``weights``: list of non-negative floats summing > 0. Returns
    ``{"entropy": float in [0,1], "basis": "normalized_entropy (maya_math)",
    "computed": bool}``. Raises nothing on caller error (returns entropy 0.0,
    computed False) — mathematics engagement must never crash conversation.
    """
    try:
        from maya_math.information import normalized_entropy
        values = [float(value) for value in weights]
        if not values or any(value < 0 for value in values):
            return {"entropy": 0.0, "basis": "normalized_entropy (maya_math)",
                    "computed": False}
        total = sum(values)
        if total <= 0:
            return {"entropy": 0.0, "basis": "normalized_entropy (maya_math)",
                    "computed": False}
        normalized = [value / total for value in values]
        result = normalized_entropy(normalized)
        return {"entropy": round(float(result), 6),
                "basis": "normalized_entropy (maya_math)",
                "computed": True}
    except Exception:
        return {"entropy": 0.0, "basis": "normalized_entropy (maya_math)",
                "computed": False}
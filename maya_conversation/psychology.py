"""Psychology / cognitive-science pathway (Batch 8G).

Represents an observed*human behavior* (as described in the conversation) as:

    ObservedBehavior -> possible interpretations -> hypotheses
        (each hypothesis: label, heuristic confidence, matched evidence,

         EPISTEMIC STATUS = HYPOTHESIS)
    -> uncertainty (8F normalized entropy over hypothesis confidences)
    -> response strategy (never diagnosis).

Invariants (structural, not rhetorical):

- ``never_diagnosis`` is always set; the pathway cannot emit a diagnostic
  conclusion. When the user states or implies a clinical condition, the
  pathway records ``clinical_claim_present`` and refuses to confirm, deny, or
  grade it, redirecting to a qualified professional.
- Every hypothesis is labeled ``HYPOTHESIS`` with ``confidence_kind =
  heuristic estimate``. Confidence is a deterministic cue-count heuristic,
  explicitly *not* a measurement.
- Noise floor: if no behavior model matches, ``engaged`` is False and the
  pathway is silent (the orchestrator then routes elsewhere or plain).

The psychological concepts named here (task-avoidance, cue-routine-reward,
self-determination, emotional appraisal, cognitive biases) are validated
against external scholarly sources in the 8G validation record; this module
en- codes the *representation*, never an authority claim.
"""
from __future__ import annotations

import re

from .orchestrate import hypotheses_entropy
from . import interpret as _interpret

CLINICAL_TERMS = (
    "adhd", "add ", "depression", "bipolar", "ocd", "ptsd", "anxiety disorder",
    "panic disorder", "schizophrenia", "borderline", "narcissist", "autism",
    "asperger", "clinical", "diagnos", "disorder",
)
_FORBIDDEN_DIAGNOSTIC_VERBS = {"diagnosed", "diagnose", "diagnosis"}

MODELS = {
    "procrastination": {
        "terms": ("procrastinat", "putting off", "put off", "keep delaying",
                  "can.t start", "can't start", "keep avoiding", "avoiding it",
                  "don.t want to start", "can.t get myself to do"),
        "interpretations": (
            "task-avoidance driven by anticipated negative emotion",
            "habitual cue-routine-reward avoidance loop",
            "unclear first step makes the task feel larger than it is",
            "self-worth protection through perfectionism",
        ),
        "cues": {
            "avoidance": ("anxious", "afraid", "fear", "daunting", "dread",
                          "unpleasant", "boring"),
            "habit_loop": ("always", "every time", "pattern", "automatic",
                           "keep doing", "i do this every"),
            "unclear_first_step": ("not sure where to start", "don.t know where "
                                   "to start", "overwhelming", "too much",
                                   "no idea how to begin"),
            "perfectionism": ("perfect", "has to be right", "good enough",
                              "not good enough"),
        },
    },
    "habit": {
        "terms": ("habit", "habitual", "automatic", "keep doing", "routine",
                  "kneejerk", "knee jerk", "reflex"),
        "interpretations": (
            "cue-routine-reward loop repeating below conscious control",
            "contextual trigger (time, place, screen) enforces the loop",
            "reward-first friction makes the new behavior hard to sustain",
        ),
        "cues": {
            "cue_loop": ("always when", "every time", "as soon as", "when i "
                         "sit", "when i open", "after i"),
            "context": ("at my desk", "in the evening", "on my phone",
                        "on the couch", "in the morning"),
            "reward_friction": ("reward", "satisfying", "takes effort",
                                "hard to start", "friction"),
        },
    },
    "motivation": {
        "terms": ("motivat", "burned out", "burnt out", "lost interest",
                  "can.t get started", "no energy", "unmotivated", "worn out",
                  "drained", "don.t care anymore", "why bother"),
        "interpretations": (
            "basic needs (autonomy, competence, relatedness) not being met",
            "reward timing too far from the action (dopamine timing)",
            "internal or environmental friction outweighs perceived value",
            "recovery deficit (sleep, rest, stress) lowering capacity",
        ),
        "cues": {
            "needs": ("not my choice", "forced", "no control", "meaningless",
                      "pointless", "no one cares", "nobody needs"),
            "reward_timing": ("no reward", "reward comes much later",
                              "results take months", "no feedback"),
            "friction": ("too hard", "too much setup", "many steps",
                         "slow computer", "cluttered"),
            "recovery": ("tired", "exhausted", "not sleeping", "stressed out",
                         "overworked", "burnt"),
        },
    },
    "emotion": {
        "terms": ("anxious", "anxiety", "stress", "stressed", "overwhelmed",
                  "irritable", "angry", "sad", "sadness", "lonely", "fear",
                  "worried", "scared", "nervous", "frustrated"),
        "interpretations": (
            "threat appraisal inflating expected cost of the situation",
            "unmet need surfacing as an emotion (not a malfunction)",
            "emotion-regulation skill gap for the specific trigger",
        ),
        "cues": {
            "appraisal": ("what if", "worst case", "terrible", "disaster",
                          "everything", "always", "never"),
            "unmet_need": ("alone", "ignored", "rejected", "not heard",
                           "unsupported", "invisible"),
            "regulation_gap": ("can.t calm down", "spiraling", "ruminating",
                               "can.t stop thinking about", "snowball"),
        },
    },
    "bias": {
        "terms": ("bias", "biased", "irrational", "overgeneralize", "jumping to"
                  " conclusions", "jump to conclusion", "confirmation"),
        "interpretations": (
            "confirmation bias: seeking and weighting matching evidence",
            "anchoring on the first number or option presented",
            "loss aversion: avoiding losses more than seeking gains",
            "overconfidence in the current mental model",
        ),
        "cues": {
            "confirmation": ("only notice", "always confirms", "i look for",
                             "ignores the"),
            "anchoring": ("first one", "starting point", "initial",
                          "based on that number"),
            "loss_aversion": ("losing", "loss", "rather not lose", "afraid of"
                              " missing out"),
            "overconfidence": ("certain", "obviously", "clearly", "definitely",
                               "i just know"),
        },
    },
}

MAX_HYPOTHESES = 4
_BASE = 0.55
_CUE_BONUS = 0.06
_CAP = 0.85


def _detect_models(text):
    low = text.lower()
    detected = []
    for name, model in MODELS.items():
        terms = model["terms"]
        matched_terms = sorted({term for term in terms if term in low})
        if matched_terms:
            detected.append({"name": name, "matched_terms": matched_terms,
                             "model": model})
    return detected


def _clinical_present(text):
    low = text.lower()
    hits = sorted({term.strip() for term in CLINICAL_TERMS
                   if term.strip() in low})
    return hits


def psychology_pathway(text, *, state=None, route=None):
    """Deterministic psychology representation for one observed behavior."""
    text = str(text or "").strip()
    if not text:
        return {"engaged": False}

    clinical = _clinical_present(text)
    detected = _detect_models(text)
    if not detected:
        refused = bool(clinical)
        return {
            "engaged": bool(clinical),
            "observed_behavior": "clinical_statement" if refused else "",
            "models": [],
            "hypotheses": [],
            "confidence_max": 0.0,
            "uncertainty": 1.0,
            "entropy": hypotheses_entropy([]),
            "refuse_text": (
                "I can't confirm or rule out a clinical condition — that "
                "needs a qualified professional.") if refused else "",
            "strategy": _strategy_for(text, clinical, refute=False),
            "never_diagnosis": True,
            "clinical_claim_present": bool(clinical),
            "clinical_terms": clinical,
            "refused_diagnosis": refused,
        }

    hypotheses = []
    for detected_model in detected:
        name = detected_model["name"]
        model = detected_model["model"]
        hypotheses_for_model = []
        for index, interpretation in enumerate(model["interpretations"][:MAX_HYPOTHESES]):
            cue_matches = sorted({cue for cue, tokens in model["cues"].items()
                                  if any(token in text.lower()
                                         for token in tokens)})
            confidence = min(_CAP, _BASE + _CUE_BONUS * len(cue_matches))
            evidence = list(cue_matches)
            hypotheses.append({
                "label": interpretation,
                "model": name,
                "confidence": round(confidence, 2),
                "confidence_kind": "heuristic estimate",
                "evidence": evidence,
                "epistemic_status": "HYPOTHESIS",
            })
            hypotheses_for_model.append(hypotheses[-1])

    confidence_max = max((hypothesis["confidence"] for hypothesis in hypotheses),
                         default=0.0)
    entropy = hypotheses_entropy([hypothesis["confidence"]
                                  for hypothesis in hypotheses])
    uncertainty = round(1.0 - confidence_max, 4)

    observed_behavior = " | ".join(sorted({str(model["name"])
                                           for model in detected}))

    strategy = _strategy_for(text, clinical, refute=True)
    strategy["uncertainty"] = uncertainty
    strategy["entropy"] = entropy

    return {
        "engaged": True,
        "observed_behavior": observed_behavior,
        "models": [{"name": model["name"], "matched_terms": model["matched_terms"]}
                   for model in detected],
        "hypotheses": hypotheses,
        "confidence_max": round(confidence_max, 2),
        "uncertainty": uncertainty,
        "entropy": entropy,
        "strategy": strategy,
        "never_diagnosis": True,
        "clinical_claim_present": bool(clinical),
        "clinical_terms": clinical,
        "refused_diagnosis": bool(clinical),
    }


def _strategy_for(text, clinical, *, refute):
    strategy = {
        "primary": "acknowledge the pattern without diagnosing",
        "steps": (
            "name the pattern as a described behavior, not a trait",
            "offer one concrete hypothesis to test, clearly labeled as such",
        ),
        "ask_question": "which of these possibilities feels closest to what "
                        "you experience?",
        "refuse_diagnosis": bool(clinical),
        "never_diagnosis": True,
    }
    if clinical:
        strategy["primary"] = ("support the person without diagnosing; "
                               "recommend a qualified professional")
        strategy["steps"] = (
            "treat the described condition as out of scope for confirmation "
            "or denial",
            "recommend consulting a qualified professional",
            "engage only with the practical behavior being described today",
        )
        strategy["ask_question"] = ("have you been able to talk to a "
                                    "qualified professional about this?")
        strategy["referral"] = (
            "I cannot confirm or rule out a diagnosis. A qualified "
            "professional is the right person for that.")
    if not refute and clinical:
        strategy["primary"] = ("recognize a clinical keyword but refuse to "
                               "diagnose")
    return strategy
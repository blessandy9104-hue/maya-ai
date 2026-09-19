"""Closed, deterministic vocabulary sets per scope.

expand(set_id, topic) returns canonical terms belonging exclusively to that set
(from its 'terms'/topics), never invented words. Forbidden terms and punctuation
caps constrain shaping downstream.
"""

VOCABULARY_SETS = {
    "assistive_base": {
        "scope": "general support",
        "default": ("confirm", "clarify", "summarize", "guide", "reassure"),
        "topics": {
            "encouragement": ("steady", "try", "next"),
            "status": ("state", "option", "next_step"),
            "clarification": ("clarify", "restate", "confirm"),
        },
        "forbidden_terms": ("slang", "profanity", "loaded_claim"),
        "shape": "subject-verb-object; at most 2 clauses",
        "max_exclaim": 1,
    },
    "business_clear": {
        "scope": "enterprise/kiosk",
        "default": ("state", "option", "next_step", "policy", "status"),
        "topics": {
            "status": ("state", "policy", "status"),
            "options": ("option", "next_step"),
            "escalation": ("escalate", "representative", "policy"),
        },
        "forbidden_terms": ("opinion", "hedging", "jargon"),
        "shape": "short declaratives",
        "max_exclaim": 1,
    },
    "technical_precise": {
        "scope": "robotics/dev",
        "default": ("parameter", "bound", "threshold", "calibration", "limit"),
        "topics": {
            "calibration": ("parameter", "calibration", "bound"),
            "safety": ("threshold", "limit", "bound"),
            "status": ("status", "parameter"),
        },
        "forbidden_terms": ("anthropomorphic", "slang"),
        "shape": "metric-first",
        "max_exclaim": 0,
    },
    "therapeutic_gentle": {
        "scope": "therapy support",
        "default": ("reflect", "validate", "breathe", "pace", "offer"),
        "topics": {
            "reflection": ("reflect", "validate"),
            "pace": ("breathe", "pace"),
            "offer": ("offer", "support"),
        },
        "forbidden_terms": ("diagnosis", "direction", "claim"),
        "shape": "invitation-only",
        "max_exclaim": 0,
    },
    "entertainment_playful": {
        "scope": "companion/VTuber",
        "default": ("cheer", "banter", "smile", "celebrate"),
        "topics": {
            "cheer": ("cheer", "celebrate"),
            "banter": ("banter", "gentle"),
            "play": ("play", "smile", "spin"),
        },
        "forbidden_terms": ("harm", "distress", "deception"),
        "shape": "playful but safe",
        "max_exclaim": 3,
    },
}


def vocabulary_ids():
    """Sorted tuple of vocabulary set ids."""
    return tuple(sorted(VOCABULARY_SETS))


def _set(set_id):
    if set_id not in VOCABULARY_SETS:
        raise ValueError("unknown vocabulary set: %s" % set_id)
    return VOCABULARY_SETS[set_id]


def all_terms(set_id):
    """Every canonical term in the set (default + topics), deduplicated."""
    spec = _set(set_id)
    seen = set()
    ordered = []
    for token in spec["default"]:
        if token not in seen:
            seen.add(token)
            ordered.append(token)
    for topic_tokens in spec["topics"].values():
        for token in topic_tokens:
            if token not in seen:
                seen.add(token)
                ordered.append(token)
    return tuple(ordered)


def expand(set_id, topic="default"):
    """Deterministic canonical terms for a topic within the set.

    Unknown topic falls back to the set default; unknown set raises ValueError.
    """
    spec = _set(set_id)
    return spec["topics"].get(topic, spec["default"])


def describe_vocabulary(set_id):
    """Return a stable snapshot dict for a vocabulary set."""
    spec = _set(set_id)
    return {
        "scope": spec["scope"],
        "terms": all_terms(set_id),
        "forbidden_terms": spec["forbidden_terms"],
        "shape": spec["shape"],
        "max_exclaim": spec["max_exclaim"],
    }


def validate_vocabulary():
    """Registry-level invariants over vocabulary sets."""
    for set_id in VOCABULARY_SETS:
        spec = VOCABULARY_SETS[set_id]
        for token in all_terms(set_id):
            if not (isinstance(token, str) and token and "_" not in token):
                raise ValueError("invalid term in set: %s:%r" % (set_id, token))
            if token in spec["forbidden_terms"]:
                raise ValueError("term collides with forbidden: %s:%r" % (set_id, token))
        if not (0 <= spec["max_exclaim"] <= 6):
            raise ValueError("invalid exclaim cap for set: %s" % set_id)
"""Formal-logic and set-theory domain of the substrate.

Deterministic, bounded predicates over text and sets. The contradiction test
restates — in explicit rule form — the token-overlap-plus-polarity convention
the world-model evidence store already uses, so substrate output stays
consistent with existing conflict flags while making the rule formal and
configurable. Sentences are treated as claims, never as truth.
"""
from __future__ import annotations

import re

# Continuity with maya_world_model.NEGATION_MARKERS / STOPWORDS: identical
# vocabularies so the substrate's formal test reports the same polarity that
# the evidence store already tracks.
NEGATION_MARKERS = frozenset({
    "not", "never", "no", "without", "cannot", "can't", "fails",
    "unavailable", "doesn't", "didn't", "isn't", "won't", "nothing",
})

STOPWORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "to", "of", "and", "for",
    "in", "on", "this", "that", "with",
})

_WORD_SPLIT = re.compile(r"[a-z0-9']+")


def tokens(text):
    """Normalized token set (lower-cased, stopwords removed), matching the
    evidence store's tokenizer convention so derived signals coexist."""
    words = _WORD_SPLIT.findall(str(text).lower())
    return frozenset(word for word in words if word and word not in STOPWORDS)


def negation_marked(text):
    """True when the claim text carries a negation marker."""
    return bool(tokens(text) & NEGATION_MARKERS)


def token_overlap(a_text, b_text):
    """Size of the shared normalized-token set."""
    return len(tokens(a_text) & tokens(b_text))


def contradictory_claims(a_text, b_text, min_overlap=3):
    """Formal contradiction test between two claims.

    A genuine (potential) contradiction requires (1) a shared substantive
    token overlap of at least ``min_overlap`` and (2) opposite polarity. This
    is a *flag*, not a truth judgement: it identifies pairs the system should
    treat as conflicting, exactly like the evidence store's conflict status.

    Returns a deterministic dict with the reasoning exposed.
    """
    a_set = tokens(a_text)
    b_set = tokens(b_text)
    overlap = len(a_set & b_set)
    polarity_a = "negated" if (a_set & NEGATION_MARKERS) else "asserted"
    polarity_b = "negated" if (b_set & NEGATION_MARKERS) else "asserted"
    contradictory = bool(overlap >= max(1, int(min_overlap))
                         and polarity_a != polarity_b)
    return {
        "contradictory": bool(contradictory),
        "overlap": int(overlap),
        "polarity_a": polarity_a,
        "polarity_b": polarity_b,
        "basis": "shared_substantive_tokens_and_polarity_mismatch"
                 if contradictory else "no_genuine_conflict_established",
    }


# -- set theory ------------------------------------------------------------

def intersect(*sets):
    """Intersection of set-like inputs (deterministic frozenset)."""
    result = None
    for part in sets:
        part = frozenset(part)
        result = part if result is None else result & part
    return frozenset() if result is None else result


def set_union(*sets):
    """Union of set-like inputs (deterministic frozenset)."""
    out = set()
    for part in sets:
        out |= frozenset(part)
    return frozenset(out)


def set_exclude(base, removed):
    """Base minus removed (set difference)."""
    return frozenset(base) - frozenset(removed)


def is_subset(candidate, container):
    return frozenset(candidate) <= frozenset(container)


def is_disjoint(a, b):
    return not (frozenset(a) & frozenset(b))


def consistent_set(members, allowed=None, forbidden=None):
    """Set-consistency check: every member must be in ``allowed`` (when given)
    and none in ``forbidden`` (when given). Returns (ok, violations)."""
    members = frozenset(members)
    problems = []
    if allowed is not None:
        allowed = frozenset(allowed)
        for member in sorted(members - allowed):
            problems.append("member_not_allowed=%s" % member)
    if forbidden is not None:
        forbidden = frozenset(forbidden)
        for member in sorted(members & forbidden):
            problems.append("member_forbidden=%s" % member)
    return (not problems, sorted(problems))
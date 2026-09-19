"""Batch 8H adaptive latency: deterministic processing-depth adjudication.

Chooses a processing depth for a turn from static complexity signals only —
never from a wall clock (deterministic purity). The depth is a directive for
how much verification/elaboration the cooperative orchestrator and the LLM
should invest in the turn: ``fast`` turns get the lean path, ``standard``
turns get the default path, ``deep`` turns get maximal verification and
surface every disagreement.

All scoring is pure and deterministic: no I/O, no randomness, no clock.
Fail-open: any missing input contributes zero to the score.
"""
from __future__ import annotations


DEPTH_FAST = "fast"
DEPTH_STANDARD = "standard"
DEPTH_DEEP = "deep"

DEPTH_ORDER = (DEPTH_FAST, DEPTH_STANDARD, DEPTH_DEEP)

# Thresholds for the static complexity score (0..1).
# Simple greetings/gratitude score in the fast band.
_FAST_MAX = 0.33
_DEEP_MIN = 0.66


def _score_length(text):
    """Contribution from raw input volume (quadratic-normalized length)."""
    text = "" if text is None else str(text)
    length = len(text.strip())
    if length == 0:
        return 0.0
    return min(1.0, length / 400.0)


def _capped_sum(values):
    """Sum a list of single-source contributions and cap at 1.0.

    Each signal is a separate singleton probability; capping after addition
    keeps the result bounded and deterministic.
    """
    total = 0.0
    for value in values:
        try:
            total += float(value or 0.0)
        except (TypeError, ValueError):
            total += 0.0
    return min(1.0, max(0.0, total))


def _interpretation_signals(interpretation):
    """Stateless signals from the 8G interpretation dict."""
    signals = []
    interp = interpretation or {}
    if interp.get("ambiguous"):
        signals.append(0.33)
    if interp.get("needs_reference_resolution"):
        signals.append(0.15)
    intent = interp.get("primary_intent") or ""
    if intent in ("complex_question", "philosophical", "self_reflection",
                  "abstraction"):
        signals.append(0.3)
    return signals


def _domain_signals(route, domain_results):
    """Stateless signals from routing and domain engagement."""
    signals = []
    routes = route or {}
    if routes.get("engaged_count", 0) >= 3:
        signals.append(0.2)
    route_type = routes.get("route_type") or routes.get("primary_route") or ""
    if route_type in ("deep_domains", "brainstorm", "multi_domain"):
        signals.append(0.2)
    domains = domain_results or {}
    psychology = (domains.get("psychology") or {}).get("engaged")
    philosophy = (domains.get("philosophy") or {}).get("engaged")
    if philosophy:
        signals.append(0.25)
    if psychology:
        signals.append(0.2)
    return signals


def _cooperation_signals(cooperation):
    """Stateless signals from the cooperation verdict."""
    signals = []
    coop = cooperation or {}
    verdict = coop.get("verdict") or ""
    if verdict == "disagreement":
        # A contested turn needs deeper verification, not a fast exit.
        signals.append(0.45)
    elif verdict == "agreement_with_caveat":
        signals.append(0.2)
    disagreements = coop.get("disagreements") or []
    if len(disagreements) >= 2:
        signals.append(0.15)
    return signals


def assess_complexity(conv_result=None, user_text=None, cooperation=None,
                      interpret=None, resource_pressure=False):
    """Return a deterministic processing-depth envelope for a turn.

    ``resource_pressure`` (bool) — when True, the system is under elevated
    CPU/memory pressure; the score is boosted so most turns take the lean
    or standard path. Supplied by the caller; this function never reads
    live system state.
    """
    try:
        return _assess_inner(conv_result, user_text, cooperation, interpret,
                             resource_pressure)
    except Exception as error:
        return {
            "depth": DEPTH_STANDARD,
            "level": 1,
            "score": 0.5,
            "reason": "assess_error: %s: %s" % (type(error).__name__, error),
            "signals": {"length": 0.0},
        }


def _assess_inner(conv_result, user_text, cooperation, interpret,
                  resource_pressure):
    length_signal = _score_length(user_text)
    text = "" if user_text is None else str(user_text)
    is_brief_statement = (len(text.strip()) <= 24 and not (
        "?" in text))

    interpretation = interpret or (
        (conv_result or {}).get("interpretation"))
    route = (conv_result or {}).get("routes")
    domain_results = (conv_result or {}).get("domain_results")

    all_signals = [length_signal] if not is_brief_statement else [0.0]
    if not is_brief_statement or length_signal > 0.2:
        all_signals.extend(_interpretation_signals(interpretation))
    else:
        interp = interpretation or {}
        candidates = interp.get("candidates") or []
        genuine_ambiguity = bool(interp.get("ambiguous")) and len(candidates) >= 2
        if not interp.get("ambiguous") or genuine_ambiguity:
            all_signals.extend(_interpretation_signals(interpretation)[:1])
    all_signals.extend(_domain_signals(route, domain_results))
    all_signals.extend(_cooperation_signals(cooperation))

    # Phase 6: resource pressure is a static boolean supplied by the caller.
    # When True, a flat +0.5 penalty pushes most turns from fast → standard.
    resource_boost = 0.5 if resource_pressure else 0.0
    all_signals.append(resource_boost)

    score = _capped_sum(all_signals)

    if score <= _FAST_MAX:
        depth, level = DEPTH_FAST, 0
    elif score >= _DEEP_MIN:
        depth, level = DEPTH_DEEP, 2
    else:
        depth, level = DEPTH_STANDARD, 1

    signal_names = {
        "length": round(length_signal, 3),
        "interpretation": _interpretation_signals(interpretation),
        "domains": _domain_signals(route, domain_results),
        "cooperation": _cooperation_signals(cooperation),
        "resource_pressure": resource_boost,
    }
    return {
        "depth": depth,
        "level": level,
        "score": round(score, 3),
        "reason": ("%s turn (static complexity score %.3f)"
                   % (depth, round(score, 3))),
        "signals": signal_names,
    }
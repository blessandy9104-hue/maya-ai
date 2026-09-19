"""Batch 8I phase 13: cooperative challenge.

Allows a STABLE hypothesis to be challenged by a competing subsystem.
The challenge is accepted ONLY when the challenger demonstrates that the
original hypothesis is fragile under slightly different conditions.

Challenge does NOT override correctness: a false challenge is silently
ignored (original unchanged).  The subsystem is purely side-channel —
no production code is mutated.

Purity:
- No clock, no randomness, no file writes, no network.
- Challenge outcomes are externally supplied; the module only applies
  deterministic weaken/reject logic.
- No mutation of 8H production or cooperation logic.
"""
from __future__ import annotations

from .hypothesis import GeneralizationHypothesis
from .generalize import transfer_boundary_check


def _text(value):
    return str(value or "").strip()


class ChallengeMetaphor:
    """Records one challenge attempt and its deterministic effect."""

    def __init__(self, original, challenger, challenge_result):
        self.original = original
        self.challenger = challenger
        self.result = bool(challenge_result)
        self.effect = None
        self.reject_reason = None
        self.weaken_reason = None

    def apply(self):
        """Apply the challenge logic to both hypotheses.

        Returns the effect dict.
        """
        if self.original is None:
            self.effect = "ignore_original_none"
            return self.effect

        original_status = getattr(self.original, "status", "untested")
        challenger_status = getattr(self.challenger, "status",
                                   "untested") if self.challenger \
            else "untested"

        if not self.result:
            self.effect = "false_challenge_ignored"
            return self.effect

        if self.challenger is not None:
            self.challenger.record_case(
                case_key="challenge_outcome",
                outcome="cooperative challenge",
                ok=True)
            self.challenger.update_uncertainty()

        if original_status == "promoted":
            self.weaken_reason = ("challenger '%s' exposed fragility"
                                  % _text(
                                      getattr(self.challenger, "method",
                                              str(self.challenger))
                                      if self.challenger else "unknown"))
            self.original.weaken(reason=self.weaken_reason)
            self.effect = "weaken"

        elif original_status in ("tested", "weakened"):
            self.reject_reason = ("challenger '%s' invalidates method"
                                  % _text(
                                      getattr(self.challenger, "method",
                                              str(self.challenger))
                                      if self.challenger else "unknown"))
            self.original.reject(reason=self.reject_reason)
            self.effect = "reject"

        else:
            self.effect = "already_%s" % original_status

        if self.effect in ("weaken", "reject") and self.challenger is not None:
            self.challenger.status = "validated"

        return self.effect


def cooperative_challenge(original, challenger_method,
                          challenger_conditions=None, challenger_exclusions=None,
                          challenge_result=False):
    """Create and apply one cooperative challenge metaphor.

    Returns a ChallengeMetaphor (pure record, never mutates production).
    """
    challenger = GeneralizationHypothesis(
        method=challenger_method,
        source_experience="cooperative challenge",
        conditions=challenger_conditions,
        exclusions=challenger_exclusions,
        uncertainty=0.5)
    metaphor = ChallengeMetaphor(original, challenger, challenge_result)
    metaphor.apply()
    return metaphor
"""Batch 8H fault tolerance: deterministic circuit breaker and guarded runs.

Existing isolation runners already enforce timeouts and kill switches;
this layer adds *repeated-failure tracking* to the in-process conversational
path with a count-based soft circuit breaker (no wall clock, matching the
deterministic purity rule).

Behavior:
- A stage (e.g. ``bridge`` or ``conv``) records one failure per exception.
- ``TRIP_AFTER`` consecutive failures trip the stage: subsequent calls are
  short-circuited and return ``None`` plus a degraded guard record (the
  caller substitutes a deterministic fallback / omits the subsystem).
- A tripped stage is held for ``RECOVERY_OK`` counted observations, then one
  trial call is permitted (half-open). A successful trial resets the stage
  to healthy; a failed trial re-trips it.
- All state is plain ints/dicts; snapshots are deterministic.

Always fail-open: ``run_guarded`` never raises; exceptions from the target
count as failures and the call degrades instead of crashing.
"""
from __future__ import annotations


TRIP_AFTER = 3       # consecutive failures before short-circuit
RECOVERY_OK = 2      # held observations before a half-open trial

STAGE_HEALTHY = "healthy"
STAGE_DEGRADED = "degraded"
STAGE_TRIPPED = "tripped"


class FailureTracker:
    """Count-based soft circuit breaker for named execution stages.

    State is tracked per stage name. All arithmetic is deterministic;
    no clock, no randomness, no I/O.
    """

    def __init__(self, trip_after=TRIP_AFTER, recovery_ok=RECOVERY_OK,
                 ledger=None):
        self.trip_after = int(trip_after)
        self.recovery_ok = int(recovery_ok)
        self.ledger = ledger
        self._failures = {}       # stage -> consecutive failures
        self._held = {}           # stage -> held observations while tripped
        self._total_calls = {}    # stage -> recorded calls
        self._total_failures = {}  # stage -> aggregate failures
        self._episode_key = {}    # stage -> active learning-episode key

    def _state_of(self, stage):
        consecutive = self._failures.get(stage, 0)
        if consecutive >= self.trip_after:
            return STAGE_TRIPPED
        if consecutive > 0:
            return STAGE_DEGRADED
        return STAGE_HEALTHY

    def _record_episode(self, stage):
        key = "stage:" + stage
        episode = self._episode_key.get(stage)
        if episode is None or self._episode_key.get("closed_" + stage):
            episode = key
            self._episode_key[stage] = episode
            if self.ledger is not None:
                self.ledger.record(stage, "proposal", episode,
                                   detail="failure episode opened")
        return episode

    def _close_episode(self, stage, outcome, ok):
        episode = self._episode_key.get(stage)
        if episode is None:
            return
        if self.ledger is not None:
            self.ledger.mark_outcome(stage, episode, outcome, ok)
        self._episode_key["closed_" + stage] = True

    def record(self, stage, ok):
        stage = str(stage)
        before = self._state_of(stage)
        self._total_calls[stage] = self._total_calls.get(stage, 0) + 1
        if ok:
            self._failures[stage] = 0
            self._held[stage] = 0
            if self._state_of(stage) == STAGE_HEALTHY:
                self._close_episode(stage, "recovered", True)
        else:
            self._failures[stage] = self._failures.get(stage, 0) + 1
            self._total_failures[stage] = \
                self._total_failures.get(stage, 0) + 1
            if before == STAGE_HEALTHY:
                self._record_episode(stage)
            if self._state_of(stage) == STAGE_TRIPPED:
                self._close_episode(stage, "tripped", False)
        return self.state(stage)

    def state(self, stage):
        return self._state_of(str(stage))

    def should_skip(self, stage):
        stage = str(stage)
        if self._state_of(stage) != STAGE_TRIPPED:
            return False
        held = self._held.get(stage, 0) + 1
        self._held[stage] = held
        if held < self.recovery_ok:
            return True
        self._held[stage] = 0
        return False

    def snapshot(self):
        stages = sorted(set(self._total_calls) | set(self._failures)
                        | set(self._held))
        return {
            stage: {
                "state": self._state_of(stage),
                "consecutive_failures": self._failures.get(stage, 0),
                "total_calls": self._total_calls.get(stage, 0),
                "total_failures": self._total_failures.get(stage, 0),
            }
            for stage in stages
        }


def _default_ledger():
    """Deterministic in-memory outcome ledger for the shared tracker.

    Lazy: learning must never block the breaker, so any import failure
    degrades to ``None`` (tracker still counts failures; only the outcome
    journal is skipped).
    """
    try:
        from .learning import LearningLedger
        return LearningLedger()
    except Exception:
        return None


_TRACKER = FailureTracker(ledger=_default_ledger())


def _guard_record(stage, state, skipped, degraded, reason=""):
    return {
        "stage": stage,
        "state": state,
        "skipped": bool(skipped),
        "degraded": bool(degraded),
        "reason": reason,
    }


def run_guarded(stage, fn, *args, tracker=None, ok_check=None, **kwargs):
    """Execute ``fn(*args, **kwargs)`` under the circuit breaker.

    ``ok_check`` (optional) inspects the result to tell success from internal
    degradation (some subsystems swallow exceptions and return ``ok=False``
    envelopes by design). When provided, a result that fails ``ok_check``
    counts as a failure. Returns ``(result, guard_record)``. Never raises.
    A short-circuited or failed stage yields ``result=None`` and a degraded
    guard record so the caller can substitute a deterministic fallback.
    """
    tracker = tracker if tracker is not None else _TRACKER
    stage = str(stage)
    if tracker.should_skip(stage):
        return None, _guard_record(
            stage, STAGE_TRIPPED, skipped=True, degraded=True,
            reason="circuit held open after repeated failures")

    try:
        result = fn(*args, **kwargs)
    except Exception as error:
        state = tracker.record(stage, False)
        return None, _guard_record(
            stage, state, skipped=False, degraded=True,
            reason="%s: %s" % (type(error).__name__, error))

    if ok_check is not None:
        try:
            ok = bool(ok_check(result))
        except Exception:
            ok = False
    else:
        ok = True
    state = tracker.record(stage, ok)
    return result, _guard_record(
        stage, state, skipped=False, degraded=not ok)
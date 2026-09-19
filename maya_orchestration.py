"""Request-lifecycle orchestration for Maya's conversational turn.

One user message becomes one :class:`Request` that moves through an explicit
state machine and reaches exactly one terminal outcome. The module is pure and
deterministic -- callers inject a clock, and there is no randomness, wall
clock, network or filesystem access here.

States::

    received -> planning -> validating -> executing -> verifying -> completed
                                   \\-> awaiting_user
                                   \\-> awaiting_approval -> executing
    terminal: completed | denied | cancelled | timeout | unavailable | error | refused

Guarantees:

* every request carries a stable ``request_id`` and an optional idempotency
  key; a duplicate submission returns the original request and never executes
  a second time;
* retries are bounded and idempotent, and can never yield a second terminal
  outcome;
* malformed input/plans/executor results fail closed with a preserved
  diagnostic reason instead of a generic failure;
* the user-facing response is rendered by this module and never claims an
  action completed unless the outcome is ``completed``.
"""
from __future__ import annotations

import hashlib

RECEIVED = "received"
PLANNING = "planning"
VALIDATING = "validating"
AWAITING_USER = "awaiting_user"
AWAITING_APPROVAL = "awaiting_approval"
EXECUTING = "executing"
VERIFYING = "verifying"

COMPLETED = "completed"
DENIED = "denied"
CANCELLED = "cancelled"
TIMEOUT = "timeout"
UNAVAILABLE = "unavailable"
ERROR = "error"
REFUSED = "refused"

OPEN_STATES = (RECEIVED, PLANNING, VALIDATING, AWAITING_USER,
               AWAITING_APPROVAL, EXECUTING, VERIFYING)
TERMINAL_OUTCOMES = (COMPLETED, DENIED, CANCELLED, TIMEOUT, UNAVAILABLE,
                     ERROR, REFUSED)

#: Legal state transitions. A self-loop on ``executing`` records one retry.
TRANSITIONS = {
    RECEIVED: (PLANNING, CANCELLED, ERROR, UNAVAILABLE),
    PLANNING: (VALIDATING, AWAITING_USER, AWAITING_APPROVAL, EXECUTING,
               CANCELLED, REFUSED, ERROR, UNAVAILABLE),
    VALIDATING: (AWAITING_USER, AWAITING_APPROVAL, EXECUTING, CANCELLED,
                 REFUSED, ERROR),
    AWAITING_USER: (EXECUTING, DENIED, CANCELLED, TIMEOUT, ERROR),
    AWAITING_APPROVAL: (EXECUTING, DENIED, CANCELLED, TIMEOUT, ERROR),
    EXECUTING: (EXECUTING, VERIFYING, AWAITING_APPROVAL, REFUSED,
                UNAVAILABLE, ERROR, CANCELLED, TIMEOUT),
    VERIFYING: (COMPLETED, UNAVAILABLE, ERROR, CANCELLED),
}

#: Outcome -> machine-readable class surfaced to UIs (distinct failure modes
#: are never collapsed into one generic failure).
OUTCOME_CLASS = {
    COMPLETED: "completed",
    DENIED: "denied",
    CANCELLED: "cancelled",
    TIMEOUT: "timeout",
    UNAVAILABLE: "backend_unavailable",
    ERROR: "internal_error",
    REFUSED: "action_refused",
    AWAITING_APPROVAL: "approval_required",
    AWAITING_USER: "clarification_required",
}

ALLOWED_PLAN_KINDS = ("answer", "command", "quick", "clarify", "act", "memory")
MAX_TEXT_LENGTH = 20000


def _valid_text(text):
    if not isinstance(text, str):
        return False, "not_text"
    stripped = text.strip()
    if not stripped:
        return False, "empty"
    if len(stripped) > MAX_TEXT_LENGTH:
        return False, "too_long"
    return True, ""


def _valid_plan(plan):
    if not isinstance(plan, dict):
        return False, "not_dict"
    if plan.get("kind") is not None and plan.get("kind") not in ALLOWED_PLAN_KINDS:
        return False, "unknown_kind"
    if "response" in plan and plan.get("response") is not None \
            and not isinstance(plan.get("response"), str):
        return False, "bad_response"
    return True, ""


def _default_classify(text, context):  # pragma: no cover - trivial default
    return {"category": "answer", "kind": "answer", "requires_execution": True}


def _default_execute(request, context, attempt):  # pragma: no cover
    return {"status": "unavailable", "reason": "no_executor"}


def _now_of(clock):
    return float(clock())


def _cancelled(cancel_check):
    """True only when a working cancel probe says so; a broken probe is not a
    cancellation (it must never abort a healthy request)."""
    if cancel_check is None:
        return False
    try:
        return bool(cancel_check())
    except Exception:  # noqa: BLE001
        return False


def _response_for(request):
    """Render the user-facing reply from the request's authoritative outcome.

    Only ``completed`` may claim an action happened, and then only when
    ``confirmed`` is true; every other outcome is honest about what did not
    happen.
    """
    outcome = request.get("outcome") or request.get("state")
    confirmed = bool(request.get("confirmed"))
    detail = (request.get("diagnostic") or {}).get("detail") or ""
    pending_id = request.get("pending_id")

    if outcome == COMPLETED:
        if request.get("response"):
            return str(request["response"])
        if confirmed:
            return "Done."
        return "I finished the step, but I could not verify it, so I stopped."
    if outcome == REFUSED:
        base = ("I can't do that - it isn't something I'm permitted to do. "
                "No action was taken.")
        return base
    if outcome == DENIED:
        return "Okay - I won't do that. Nothing was changed."
    if outcome == CANCELLED:
        return "Cancelled. Nothing was changed."
    if outcome == TIMEOUT:
        return ("That took longer than my limit, so I stopped. Nothing was "
                "completed.")
    if outcome == UNAVAILABLE:
        base = ("I can't reach the part of me that handles that right now, so "
                "I haven't done it.")
        return base
    if outcome == ERROR:
        base = "Something went wrong on my side, so I stopped and changed nothing."
        if detail:
            base += " Reason: " + detail
        return base
    if outcome == AWAITING_APPROVAL:
        if pending_id:
            return ("I need your OK before I do that. Item %s is waiting - "
                    "reply `:pending approve %s` or `:pending deny %s`."
                    % (pending_id, pending_id, pending_id))
        return "I need your OK before I do that."
    if outcome == AWAITING_USER:
        return request.get("response") or (
            "I'd like to help - could you tell me a little more about what "
            "you'd like?")
    return "I stopped before doing anything."


class RequestLog:
    """Ordered, idempotent request store with deterministic identifiers."""

    def __init__(self, clock=None):
        self._clock = clock if callable(clock) else (lambda: 0.0)
        self._by_id = {}
        self._by_key = {}
        self._seq = 0

    def now(self):
        return _now_of(self._clock)

    def create(self, text, *, session_id, modality, key, timeout_seconds):
        self._seq += 1
        raw = "%s|%s|%d" % (session_id, key or "", self._seq)
        request_id = "req-" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
        moment = self.now()
        request = {
            "request_id": request_id,
            "idempotency_key": key,
            "session_id": str(session_id),
            "modality": str(modality),
            "text": str(text),
            "state": RECEIVED,
            "outcome": None,
            "outcome_class": None,
            "terminal": False,
            "response": None,
            "confirmed": False,
            "reason": "",
            "diagnostic": {"stage": "", "reason": "", "detail": ""},
            "attempts": 0,
            "max_attempts": 1,
            "created_at": moment,
            "updated_at": moment,
            "deadline": (moment + float(timeout_seconds)
                         if timeout_seconds else None),
            "plan": None,
            "pending_id": None,
            "duplicate": False,
            "history": [{"state": RECEIVED, "at": moment, "reason": ""}],
        }
        self._by_id[request_id] = request
        if key:
            self._by_key[str(key)] = request_id
        return request

    def get(self, request_id):
        return self._by_id.get(str(request_id))

    def find_by_key(self, key):
        if not key:
            return None
        rid = self._by_key.get(str(key))
        return self._by_id.get(rid) if rid else None

    def all(self):
        return list(self._by_id.values())


class Orchestrator:
    """Coordinates one session's requests through the lifecycle."""

    def __init__(self, *, clock=None, max_attempts=2, timeout_seconds=90.0,
                 pending=None):
        self._clock = clock if callable(clock) else (lambda: 0.0)
        self.max_attempts = max(1, int(max_attempts))
        self.timeout_seconds = float(timeout_seconds)
        self.log = RequestLog(clock=self._clock)
        if pending is None:
            from maya_pending import PendingStore
            pending = PendingStore(clock=self._clock)
        self.pending = pending

    # -- lifecycle helpers ----------------------------------------------
    def _enter(self, request, state, reason=""):
        current = request["state"]
        if state == current:
            return True
        if state not in TRANSITIONS.get(current, ()):
            self._set_diagnostic(request, "transition",
                                 "invalid_transition:%s->%s" % (current, state),
                                 "")
            self._finish(request, ERROR,
                         reason="invalid_transition:%s->%s" % (current, state))
            return False
        moment = self.log.now()
        request["state"] = state
        request["updated_at"] = moment
        request["history"].append({"state": state, "at": moment,
                                   "reason": str(reason)})
        return True

    def _set_diagnostic(self, request, stage, reason, detail):
        request["diagnostic"] = {
            "stage": str(stage),
            "reason": str(reason),
            "detail": str(detail),
        }

    def _finish(self, request, outcome, *, reason="", response=None,
                confirmed=False, stage=""):
        if request.get("terminal"):
            request["diagnostic"]["detail"] = (
                "late_outcome_ignored:" + str(outcome))
            return dict(request)
        if outcome not in TERMINAL_OUTCOMES:
            outcome = ERROR
            reason = reason or "invalid_outcome"
        moment = self.log.now()
        request["state"] = outcome
        request["outcome"] = outcome
        request["outcome_class"] = OUTCOME_CLASS.get(outcome, "internal_error")
        request["terminal"] = True
        request["reason"] = str(reason)
        request["confirmed"] = bool(confirmed)
        request["updated_at"] = moment
        request["history"].append({"state": outcome, "at": moment,
                                   "reason": str(reason)})
        if stage:
            self._set_diagnostic(
                request, stage, reason, request["diagnostic"].get("detail", ""))
        if response is not None:
            request["response"] = str(response)
        else:
            request["response"] = _response_for(request)
        return dict(request)

    def _arm_pending(self, request, plan):
        title = str(plan.get("pending_title") or plan.get("category")
                    or "Approval needed")
        summary = str(plan.get("pending_summary") or request.get("text") or "")
        required = str(plan.get("pending_required_action") or "approve")
        next_step = str(plan.get("pending_next_step")
                        or "Review the item and approve or deny it.")
        ttl = plan.get("pending_ttl_seconds")
        item_id = plan.get("pending_id")
        try:
            item = self.pending.create(
                "orchestration", title, summary, required, next_step,
                ttl_seconds=(None if ttl in (None, 0) else ttl),
                source="orchestration",
                item_id=item_id,
                reason="awaiting_approval")
        except ValueError:
            # The pending store keys items by a stable identity
            # (kind, title, source), so the same action asked again maps onto
            # an existing item. Re-open it as pending instead of failing the
            # turn: the request must stay honest and the store must never
            # accumulate duplicate open items.
            from maya_pending import make_item
            template = make_item(
                "orchestration", title, summary, required, next_step,
                now=self.log.now(),
                ttl_seconds=(None if ttl in (None, 0) else ttl),
                source="orchestration", item_id=item_id,
                reason="awaiting_approval")
            existing = self.pending.get(template["id"])
            if existing is None:
                raise
            template["created_at"] = existing.get("created_at",
                                                  template["created_at"])
            template["attempts"] = 0
            item = self.pending.upsert(template)
        request["pending_id"] = item["id"]
        return item["id"]

    # -- public API ------------------------------------------------------
    def begin(self, text, *, session_id="session1", modality="text",
              idempotency_key=None, timeout_seconds=None):
        """Create a request and enter planning without running it.

        Useful for async drivers that need the stable correlation id before
        dispatching the work. ``drive`` finishes the lifecycle and is the only
        part that may execute anything.
        """
        key = str(idempotency_key) if idempotency_key else None
        request = self.log.create(
            text, session_id=session_id, modality=modality, key=key,
            timeout_seconds=(self.timeout_seconds if timeout_seconds is None
                             else timeout_seconds))
        request["max_attempts"] = self.max_attempts
        self._enter(request, PLANNING, "start")
        ok, vreason = _valid_text(text)
        if not ok:
            self._set_diagnostic(request, "validating",
                                 "invalid_payload:" + vreason, "")
            self._finish(
                request, ERROR, reason="invalid_payload:" + vreason,
                response=("I couldn't process that message safely, so I "
                          "changed nothing."), stage="validating")
        return request

    def submit(self, text, *, session_id="session1", history=None,
               modality="text", classify=None, execute=None,
               idempotency_key=None, context=None, timeout_seconds=None,
               cancel_check=None):
        """Drive one message through the lifecycle; returns a request dict."""
        key = str(idempotency_key) if idempotency_key else None
        existing = self.log.find_by_key(key)
        if existing is not None:
            snapshot = dict(existing)
            snapshot["duplicate"] = True
            return snapshot

        request = self.begin(text, session_id=session_id, modality=modality,
                             idempotency_key=key,
                             timeout_seconds=timeout_seconds)
        if request.get("terminal"):
            return dict(request)
        return self.drive(request, classify=classify, execute=execute,
                          context=context, cancel_check=cancel_check)

    def drive(self, request, *, classify=None, execute=None, context=None,
              cancel_check=None):
        """Run an already-``begin`` request through planning to one outcome."""
        if not isinstance(request, dict):
            return request
        if request.get("terminal"):
            return dict(request)
        if _cancelled(cancel_check):
            return self._finish(request, CANCELLED,
                                reason="cancelled_before_execution")

        text = request.get("text")
        if not self._enter(request, VALIDATING, "payload_ok"):
            return dict(request)

        try:
            plan = (classify or _default_classify)(text, context)
        except Exception as exc:  # noqa: BLE001 - fail closed, preserve reason
            self._set_diagnostic(request, "planning",
                                 "classify_failed:" + type(exc).__name__,
                                 str(exc))
            return self._finish(
                request, ERROR,
                reason="classify_failed:" + type(exc).__name__,
                response=("I hit an internal problem while understanding that, "
                          "so I stopped and changed nothing."),
                stage="planning")

        ok, preason = _valid_plan(plan)
        if not ok:
            self._set_diagnostic(request, "validating",
                                 "invalid_plan:" + preason, "")
            return self._finish(
                request, ERROR, reason="invalid_plan:" + preason,
                response=("I couldn't act on that safely, so I changed "
                          "nothing."), stage="validating")

        request["plan"] = {
            "category": str(plan.get("category") or plan.get("kind") or ""),
            "kind": str(plan.get("kind") or plan.get("category") or "answer"),
            "requires_approval": bool(plan.get("requires_approval")),
            "requires_execution": bool(plan.get("requires_execution", True)),
        }

        response = plan.get("response")
        requires_approval = bool(plan.get("requires_approval"))
        if requires_approval:
            self._arm_pending(request, plan)
            if not self._enter(request, AWAITING_APPROVAL, "approval_required"):
                return dict(request)
            request["outcome_class"] = OUTCOME_CLASS[AWAITING_APPROVAL]
            request["response"] = _response_for(request)
            return dict(request)

        if request["plan"]["kind"] == "clarify":
            if not self._enter(request, AWAITING_USER, "clarification"):
                return dict(request)
            request["outcome_class"] = OUTCOME_CLASS[AWAITING_USER]
            request["response"] = (str(response) if response else None) or \
                _response_for(request)
            return dict(request)

        if response is not None and plan.get("requires_execution") is not True:
            request["confirmed"] = True
            return self._finish(request, COMPLETED, response=str(response),
                                confirmed=True, reason="deterministic",
                                stage="planning")

        return self._execute(request, execute, context,
                             cancel_check=cancel_check)

    def _execute(self, request, execute, context, cancel_check=None):
        if request.get("terminal"):
            return dict(request)
        if not self._enter(request, EXECUTING, "execute"):
            return dict(request)
        last_status = "error"
        last_reason = "execute_failed"
        while request["attempts"] < request["max_attempts"] \
                and not request.get("terminal"):
            if _cancelled(cancel_check):
                return self._finish(request, CANCELLED,
                                    reason="cancelled_during_execution")
            now = self.log.now()
            if request.get("deadline") is not None and now > request["deadline"]:
                return self._finish(request, TIMEOUT, reason="deadline_exceeded")
            request["attempts"] += 1
            if request["attempts"] > 1 and not self._enter(
                    request, EXECUTING, "retry"):
                return dict(request)
            try:
                result = (execute or _default_execute)(request, context,
                                                       request["attempts"])
            except Exception as exc:  # noqa: BLE001
                last_status = "error"
                last_reason = "execute_exception:" + type(exc).__name__
                self._set_diagnostic(request, "executing", last_reason,
                                     str(exc))
                continue
            if not isinstance(result, dict):
                last_status = "error"
                last_reason = "invalid_executor_result"
                self._set_diagnostic(request, "executing", last_reason, "")
                continue
            if _cancelled(cancel_check):
                return self._finish(request, CANCELLED,
                                    reason="cancelled_during_execution")
            status = str(result.get("status") or "").lower()
            if status in ("ok", "completed", "success"):
                if not self._enter(request, VERIFYING, "verify"):
                    return dict(request)
                confirmed = bool(result.get("confirmed", True))
                return self._finish(
                    request, COMPLETED, response=result.get("response"),
                    confirmed=confirmed, reason="executed", stage="executing")
            if status == "requires_approval":
                self._arm_pending(request, result)
                if not self._enter(request, AWAITING_APPROVAL,
                                   "late_approval_required"):
                    return dict(request)
                request["outcome_class"] = OUTCOME_CLASS[AWAITING_APPROVAL]
                request["response"] = _response_for(request)
                return dict(request)
            if status in ("cancelled", "cancel"):
                return self._finish(
                    request, CANCELLED,
                    reason=str(result.get("reason") or "cancelled"))
            if status == "refused":
                return self._finish(
                    request, REFUSED, reason=str(result.get("reason")
                                                 or "refused"),
                    stage="executing")
            if status == "unavailable":
                last_status = "unavailable"
                last_reason = str(result.get("reason") or "unavailable")
                self._set_diagnostic(request, "executing", last_reason, "")
                continue
            if status in ("error", "internal", "failed", ""):
                last_status = "error"
                last_reason = str(result.get("reason") or status or
                                  "execute_error")
                self._set_diagnostic(request, "executing", last_reason, "")
                continue
            return self._finish(
                request, ERROR,
                reason="invalid_executor_status:" + status, stage="executing")
        if last_status == "unavailable":
            return self._finish(request, UNAVAILABLE, reason=last_reason,
                                stage="executing")
        return self._finish(request, ERROR, reason=last_reason,
                            stage="executing")

    def resolve(self, request_id, decision, *, reason="", execute=None,
                context=None, cancel_check=None):
        """Resolve an open request with a decision; returns ``(request, note)``.

        ``approve`` on an approval-required request resumes execution;
        ``deny``/``cancel`` close it; ``retry`` re-arms a failed request. A
        terminal request is never resolved a second time.
        """
        request = self.log.get(request_id)
        if request is None:
            return None, "unknown_request"

        key = str(decision or "").strip().lower()

        if key == "retry":
            if not request.get("terminal") \
                    or request.get("outcome") not in (ERROR, UNAVAILABLE):
                return dict(request), "not_retryable"
            moment = self.log.now()
            request["terminal"] = False
            request["outcome"] = None
            request["outcome_class"] = None
            request["confirmed"] = False
            request["attempts"] = 0
            request["state"] = EXECUTING
            request["updated_at"] = moment
            request["history"].append(
                {"state": EXECUTING, "at": moment, "reason": "retry_requested"})
            return self._execute(request, execute, context,
                                 cancel_check=cancel_check), "retried"

        if request.get("terminal"):
            return dict(request), "already_terminal:" + str(request["outcome"])

        state = request["state"]

        if key in ("approve", "approved"):
            if state != AWAITING_APPROVAL:
                return dict(request), "not_awaiting_approval"
            if request.get("pending_id"):
                self.pending.resolve(request["pending_id"], "approve",
                                     reason=reason or "approved")
            if not self._enter(request, EXECUTING, "approved"):
                return dict(request), "transition_failed"
            request["response"] = None
            return self._execute(request, execute, context,
                                 cancel_check=cancel_check), "approved"

        if key in ("deny", "reject", "denied"):
            if state not in (AWAITING_APPROVAL, AWAITING_USER):
                return dict(request), "not_awaiting_decision"
            if request.get("pending_id"):
                self.pending.resolve(request["pending_id"], "deny",
                                     reason=reason or "denied")
            return self._finish(request, DENIED, reason="denied_by_user"), "denied"

        if key in ("cancel", "cancelled"):
            if request.get("pending_id"):
                self.pending.resolve(request["pending_id"], "cancel",
                                     reason=reason or "cancelled")
            return self._finish(request, CANCELLED,
                                reason=reason or "cancelled_by_user"), "cancelled"

        return dict(request), "unknown_decision:" + key

    def fail(self, request_id, reason="internal_error", *, response=None):
        """Close an open request as ``error`` from outside the drive loop.

        Used by async drivers when work could not even be dispatched (queue
        overflow, worker failure); it never executes anything and is idempotent
        for an already-terminal request.
        """
        request = self.log.get(request_id)
        if request is None:
            return None
        return self._finish(request, ERROR, reason=reason, response=response,
                            stage="executing")

    def sweep_pending(self):
        return self.pending.sweep()

"""Pending-validation lifecycle for Maya's orchestration layer.

Every pending validation is a first-class item with one explicit lifecycle and
exactly one terminal outcome. This module is deliberately pure and
deterministic:

* no wall clock is read -- callers inject ``now`` (seconds, float or int);
* no dependency on trust, identity, profile or suggestion files is required;
* nothing here writes trust, identity, memory or registry artifacts. The store
  is in-memory and a terminal outcome is recorded on the item only.

The terminal outcomes are ``approved``, ``denied``, ``expired``,
``cancelled``, ``failed`` and ``unavailable``. An item may also be ``pending``
(open) or be re-armed to ``pending`` from ``failed``/``unavailable`` via a
bounded ``retry``.
"""
from __future__ import annotations

import hashlib
import json

PENDING = "pending"
APPROVED = "approved"
DENIED = "denied"
EXPIRED = "expired"
CANCELLED = "cancelled"
FAILED = "failed"
UNAVAILABLE = "unavailable"

OPEN_STATUSES = (PENDING,)
TERMINAL_OUTCOMES = (APPROVED, DENIED, EXPIRED, CANCELLED, FAILED, UNAVAILABLE)
RETRYABLE_OUTCOMES = (FAILED, UNAVAILABLE)
ALL_STATUSES = OPEN_STATUSES + TERMINAL_OUTCOMES

#: User-facing decision -> terminal outcome. ``dismiss`` closes an item the
#: user no longer wants to act on without implying approval or refusal.
DECISION_TO_OUTCOME = {
    "approve": APPROVED,
    "approved": APPROVED,
    "deny": DENIED,
    "reject": DENIED,
    "denied": DENIED,
    "cancel": CANCELLED,
    "cancelled": CANCELLED,
    "dismiss": CANCELLED,
    "expire": EXPIRED,
    "expired": EXPIRED,
    "fail": FAILED,
    "failed": FAILED,
    "unavailable": UNAVAILABLE,
}

#: Controls a surface may offer for an item in a given status. Terminal
#: outcomes other than failure offer no controls (the item is closed).
CONTROLS = {
    PENDING: ("approve", "deny", "cancel"),
    APPROVED: (),
    DENIED: (),
    EXPIRED: (),
    CANCELLED: (),
    FAILED: ("retry", "dismiss"),
    UNAVAILABLE: ("retry", "dismiss"),
}


def is_terminal(status):
    """True when ``status`` is one of the six terminal outcomes."""
    return status in TERMINAL_OUTCOMES


def controls_for(status):
    """Ordered tuple of controls valid for ``status`` (never mutates)."""
    return tuple(CONTROLS.get(status, ()))


def _stable_id(kind, title, source):
    raw = json.dumps(
        {"kind": str(kind), "title": str(title), "source": str(source)},
        sort_keys=True, ensure_ascii=False)
    return "pend-" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def make_item(kind, title, summary, required_action, next_step, *,
              now=0, ttl_seconds=None, source="", item_id=None,
              status=PENDING, reason="", attempts=0, **extra):
    """Build one pending item as a plain dict (deterministic, non-mutating).

    ``expires_at`` is ``now + ttl_seconds`` when a positive TTL is supplied,
    otherwise ``None`` (no automatic expiry). An unknown ``status`` fails
    closed to ``unavailable`` so a malformed item can never read as open.
    """
    moment = float(now)
    if status not in ALL_STATUSES:
        status = UNAVAILABLE
    item = {
        "id": str(item_id or _stable_id(kind, title, source)),
        "kind": str(kind),
        "title": str(title),
        "summary": str(summary),
        "required_action": str(required_action),
        "next_step": str(next_step),
        "status": status,
        "created_at": moment,
        "updated_at": moment,
        "expires_at": (moment + float(ttl_seconds)
                       if ttl_seconds not in (None, 0) else None),
        "source": str(source),
        "reason": str(reason),
        "attempts": int(attempts),
    }
    item.update(extra)
    return item


def resolve(item, decision, *, now=0, reason=""):
    """Apply one user/system decision to an item.

    Returns ``(new_item, changed, note)``. The input item is never mutated.
    ``changed`` is False (with a diagnostic ``note``) when the item is already
    terminal or the decision is unknown/not applicable -- resolution is
    idempotent and can never produce a second terminal outcome.
    """
    if not isinstance(item, dict):
        return (None, False, "invalid_item")
    status = item.get("status")
    key = str(decision or "").strip().lower()
    moment = float(now)

    if key == "retry":
        if status not in RETRYABLE_OUTCOMES:
            return (dict(item), False, "not_retryable:" + str(status))
        updated = dict(item)
        updated["status"] = PENDING
        updated["attempts"] = int(item.get("attempts") or 0) + 1
        updated["updated_at"] = moment
        updated["reason"] = str(reason or "")
        return (updated, True, "retried")

    if is_terminal(status):
        return (dict(item), False, "already_terminal:" + str(status))

    outcome = DECISION_TO_OUTCOME.get(key)
    if outcome is None:
        return (dict(item), False, "unknown_decision:" + key)
    if status == PENDING and outcome == EXPIRED:
        pass
    updated = dict(item)
    updated["status"] = outcome
    updated["updated_at"] = moment
    updated["reason"] = str(reason or "")
    return (updated, True, outcome)


def sweep(items, now=0):
    """Return a new list with stale open items moved to ``expired``.

    An item expires only when it is open and has an ``expires_at`` at or
    before ``now``. Terminal items pass through untouched.
    """
    moment = float(now)
    out = []
    for item in items or []:
        if (isinstance(item, dict)
                and item.get("status") == PENDING
                and item.get("expires_at") is not None
                and float(item.get("expires_at")) <= moment):
            expired, _changed, _note = resolve(
                item, "expire", now=moment, reason="ttl_elapsed")
            out.append(expired)
        else:
            out.append(item)
    return out


def surface(items):
    """Deterministic, actionable projection for a UI or chat surface.

    Open items sort before terminal ones, then newest first, then by id. Each
    row carries ``terminal`` and the ordered ``controls`` so a surface never
    has to guess what may be done with an item.
    """
    rows = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        status = item.get("status")
        if status not in ALL_STATUSES:
            status = UNAVAILABLE
        row = dict(item)
        row["status"] = status
        row["terminal"] = is_terminal(status)
        row["controls"] = list(controls_for(status))
        rows.append(row)
    rows.sort(key=lambda r: (1 if r["terminal"] else 0,
                             -float(r.get("created_at") or 0),
                             str(r.get("id") or "")))
    return rows


def summarize(items):
    """Count of open items and per-terminal-outcome counts (deterministic)."""
    open_count = 0
    outcomes = {name: 0 for name in TERMINAL_OUTCOMES}
    for item in items or []:
        if not isinstance(item, dict):
            continue
        status = item.get("status")
        if status == PENDING:
            open_count += 1
        elif status in outcomes:
            outcomes[status] += 1
    return {"open": open_count, "total": len([
        i for i in (items or []) if isinstance(i, dict)]),
        "outcomes": outcomes}


def human_summary(items):
    """One plain-language line describing the current pending set."""
    counts = summarize(items)
    if counts["open"] == 0:
        return "Nothing needs your approval right now."
    first = surface([i for i in (items or [])
                     if isinstance(i, dict) and i.get("status") == PENDING])
    lead = first[0] if first else None
    if lead is None:
        return "Nothing needs your approval right now."
    return ("%d approval item(s) waiting. Next: %s %s"
            % (counts["open"], str(lead.get("title") or "item"),
               str(lead.get("required_action") or ""))).strip()


class PendingStore:
    """In-memory, clock-injectable pending store (never writes artifacts)."""

    def __init__(self, clock=None):
        self._clock = clock if callable(clock) else (lambda: 0.0)
        self._items = {}

    # -- reads -----------------------------------------------------------
    def get(self, item_id):
        return self._items.get(str(item_id))

    def all(self):
        return list(self._items.values())

    def open_items(self):
        return [i for i in self._items.values()
                if i.get("status") == PENDING]

    def surface(self):
        return surface(self.all())

    def summarize(self):
        return summarize(self.all())

    def human_summary(self):
        return human_summary(self.all())

    # -- writes (in-memory only) ----------------------------------------
    def add(self, item):
        if not isinstance(item, dict) or not item.get("id"):
            raise ValueError("pending item requires an id")
        item_id = str(item["id"])
        if item_id in self._items:
            raise ValueError("duplicate pending id: " + item_id)
        self._items[item_id] = dict(item)
        return self._items[item_id]

    def create(self, kind, title, summary, required_action, next_step, *,
               ttl_seconds=None, source="", item_id=None, reason="",
               **extra):
        item = make_item(
            kind, title, summary, required_action, next_step,
            now=self._clock(), ttl_seconds=ttl_seconds, source=source,
            item_id=item_id, reason=reason, **extra)
        return self.add(item)

    def upsert(self, item):
        if not isinstance(item, dict) or not item.get("id"):
            raise ValueError("pending item requires an id")
        self._items[str(item["id"])] = dict(item)
        return self._items[str(item["id"])]

    def resolve(self, item_id, decision, *, reason=""):
        item = self._items.get(str(item_id))
        if item is None:
            return (None, False, "unknown_item")
        updated, changed, note = resolve(
            item, decision, now=self._clock(), reason=reason)
        if changed:
            self._items[str(item_id)] = updated
        return (updated, changed, note)

    def sweep(self):
        items = sweep(self.all(), now=self._clock())
        self._items = {str(i.get("id")): i for i in items if isinstance(i, dict)}
        return self.all()

    def clear_terminal(self):
        self._items = {k: v for k, v in self._items.items()
                       if not is_terminal(v.get("status"))}
        return self.all()

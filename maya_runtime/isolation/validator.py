"""Isolation validator: deterministic checks on every incoming request.

Checks bound, quota, kill_switch, drift, consent, plus exact-origin
postMessage-v1 envelope validation with direction pairing and a 16KB size
limit. Pure functions only; fully deterministic.
"""
from __future__ import annotations

from .ceilings import EMBED_MESSAGE_SIZE_LIMIT_BYTES, TENANT_QUOTAS
from .namespace import Namespace

ALLOWED_MESSAGE_TYPES = ("mount", "ready", "chat_in", "chat_out", "error", "status")
_DIRECTION_PAIRS = (("mount", "ready"), ("chat_in", "chat_out"))


class Validator:
    def __init__(self, expected_origin=None, kill_switch=False):
        self.expected_origin = expected_origin
        self.kill_switch = kill_switch

    def validate_message(self, message):
        if not isinstance(message, dict):
            return self._deny("not_object")
        if "type" not in message or message["type"] not in ALLOWED_MESSAGE_TYPES:
            return self._deny("bad_type")
        origin = message.get("origin")
        if self.expected_origin is not None and origin != self.expected_origin:
            return self._deny("bad_origin")
        if "direction" in message and not self._pairing_ok(message["type"], message.get("direction")):
            return self._deny("bad_direction_pairing")
        data = message.get("data")
        if data is None:
            return self._deny("missing_data")
        size = len(str(data).encode("utf-8", errors="replace"))
        if size > EMBED_MESSAGE_SIZE_LIMIT_BYTES:
            return self._deny("too_large")
        return {"allow": True, "kind": message["type"], "size": size}

    def _pairing_ok(self, msg_type, direction):
        return any(msg_type == a and direction == b for a, b in _DIRECTION_PAIRS)

    def check_bound(self, ctx, nskind):
        ns = Namespace(ctx["tenant"], nskind)
        return ctx.get("namespace_path", "").startswith(ns.path) or ctx.get("namespace_path") == ns.path

    def check_quota(self, ctx):
        cpu = ctx.get("cpu_percent", 0)
        embeds = ctx.get("active_embeds", 0)
        calls = ctx.get("calls_today", 0)
        if cpu > TENANT_QUOTAS["cpu_budget_pct"]:
            return False
        if embeds > TENANT_QUOTAS["max_active_embeds_per_tenant"]:
            return False
        if calls > TENANT_QUOTAS["quota_calls_per_day"]:
            return False
        return True

    def check_kill_switch(self):
        return not self.kill_switch

    def check_drift(self, ref_state, current_state):
        return ref_state == current_state

    def check_consent(self, consented):
        return bool(consented)

    def _deny(self, reason):
        return {"allow": False, "reason": reason}


MESSAGE_TYPES = ALLOWED_MESSAGE_TYPES
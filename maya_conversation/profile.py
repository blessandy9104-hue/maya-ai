"""Batch 8H phase 10: user-scoped capability profiles.

Scopes capabilities per user with a deterministic default-deny posture:
an unknown user or unknown capability is denied unless explicitly granted.

Purity:
- In-memory only; no clock, no randomness, no file writes, no network.
- ``allows`` is a pure lookup; the profile never mutates on read.

Fail-open:
- Unknown users, unknown scopes, unknown capabilities and malformed
  identifiers all resolve to **denied** rather than raising.
"""
from __future__ import annotations


DEFAULT_USER = "default"
SCOPE_ANY = "*"


class CapabilityProfile:
    """Per-user capability registry.

    Capabilities are identified by ``(scope, capability)`` pairs. The empty
    roster is always denied; granting is idempotent; revoking is idempotent.
    """

    def __init__(self):
        self._grants = {}   # user -> {(scope, capability): True}

    def _roster(self, user):
        return self._grants.setdefault(str(user or DEFAULT_USER), {})

    def grant_capability(self, user, scope, capability):
        user = str(user or DEFAULT_USER)
        scope = str(scope or "")
        capability = str(capability or "")
        if not scope or not capability:
            return False
        roster = self._roster(user)
        roster[(scope, capability)] = True
        return True

    def revoke_capability(self, user, scope, capability):
        user = str(user or DEFAULT_USER)
        scope = str(scope or "")
        capability = str(capability or "")
        if not scope or not capability:
            return False
        roster = self._grants.get(user)
        if roster is None:
            return True
        roster.pop((scope, capability), None)
        return True

    def allows(self, user, scope, capability):
        """Deterministic default-deny lookup."""
        user = str(user or DEFAULT_USER)
        scope = str(scope or "")
        capability = str(capability or "")
        if not scope or not capability:
            return False
        roster = self._grants.get(user)
        if roster is None:
            return False
        if roster.get((scope, capability)):
            return True
        if roster.get((SCOPE_ANY, capability)):
            return True
        return False

    def capabilities(self, user, scope=None):
        """Deterministic sorted list of ``(scope, capability)`` grants.

        When ``scope`` is given, only pairs for that scope are returned.
        """
        roster = self._grants.get(str(user or DEFAULT_USER)) or {}
        pairs = sorted(pair for pair in roster if roster.get(pair))
        if scope is not None:
            scope = str(scope)
            pairs = [pair for pair in pairs if pair[0] == scope]
        return pairs

    def user_list(self):
        """Deterministic sorted list of users with any grant."""
        users = [user for user, roster in self._grants.items() if roster]
        return sorted(users)
"""Marketplace runtime surface: wired through the isolation guard.

Enforces marketplace-review and creator/tenant isolation by requiring every
marketplace action to pass the guard before it is allowed. No listing, review,
or creator operation bypasses the isolation runtime.
"""
from __future__ import annotations

from ..isolation import DENY, Guard

MARKETPLACE_SURFACES = ("marketplace", "studio")


class MarketplaceGuard:
    def __init__(self, expected_origin=None):
        self.guard = Guard(expected_origin=expected_origin, surfaces=MARKETPLACE_SURFACES)

    def pre_review(self, tenant, listing, context=None):
        decision = self.guard.can(
            tenant=tenant,
            surface="marketplace",
            category="marketplace_listing",
            action="pre_review",
            context={"listing": listing, **(context or {})},
        )
        return decision

    def creator_access(self, tenant, creator, context=None):
        decision = self.guard.can(
            tenant=tenant,
            surface="marketplace",
            category="marketplace_listing",
            action="creator_access",
            context={"creator": creator, **(context or {})},
        )
        return decision


MARKETPLACE_GUARD = MarketplaceGuard()
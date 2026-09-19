"""Isolation router: declarative, boundary-ordered routing over the MUS chain.

Order is fixed: safety -> isolation -> legal -> business -> operator ->
founder. Every request is classified into exactly one boundary and assigned a
declarative handler key. Nothing escapes the table.
"""
from __future__ import annotations

from .ceilings import MUS_BOUNDARY_ORDER

BOUNDARY_TABLE = {
    "safety": {"financial", "medical", "legal_safety"},
    "isolation": {"namespace", "tenant", "persona", "identity", "sealing"},
    "legal": {"contracts", "payments", "liabilities", "terms"},
    "business": {"pricing", "negotiation"},
    "operator": {"operator_task", "operator_command", "aol_loop", "market_interpretation"},
    "founder": {"founder_go_no_go", "founder_approval", "founder_override"},
}

_ESCAPE = object()


class IsolationRouter:
    def __init__(self, boundary_order=MUS_BOUNDARY_ORDER):
        self.boundary_order = tuple(boundary_order)
        if self.boundary_order != MUS_BOUNDARY_ORDER:
            raise ValueError("boundary order is fixed by MUS")

    def boundary_of(self, category):
        for boundary, categories in BOUNDARY_TABLE.items():
            if category in categories:
                return boundary
        return None

    def route(self, category):
        boundary = self.boundary_of(category)
        if boundary is None:
            return {"boundary": None, "handler": None, "allow": False}
        handler = self._handler(boundary, category)
        return {"boundary": boundary, "handler": handler, "allow": True}

    def _handler(self, boundary, category):
        return {"boundary": boundary, "category": category, "order": self.boundary_order.index(boundary)}

    def ordered(self):
        return list(self.boundary_order)

    def verify(self):
        return {
            "boundary_order": list(self.boundary_order),
            "categories": {k: len(v) for k, v in BOUNDARY_TABLE.items()},
        }
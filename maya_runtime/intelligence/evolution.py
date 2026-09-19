"""Evolution log: architect-driven only, never autonomous.

Every recorded change to locked surfaces (math, personas, identity,
world model) must carry an explicit, non-empty architect instruction.
Without it the change is denied and logged as denied. The reflection
stage may only propose; it can never apply evolution by itself.
"""
from __future__ import annotations

import json
import os

from .locks import SAFETY_LOCKS, LOCKED_SURFACES

LEDGER_ENTRY_KEYS = ("surface", "change", "role", "architect", "allowed",
                     "reason")


class EvolutionLog:
    """Deterministic ledger; the sequence is caller-provided (no clock)."""

    def record(self, surface, change, architect_instruction=None,
               now=None, sequence=None):
        if surface not in LOCKED_SURFACES:
            raise ValueError("unknown locked surface %r" % surface)
        verdict = SAFETY_LOCKS.verify_modify(
            surface, architect_instruction, change=change)
        allowed = bool(verdict["allowed"] and
                       architect_instruction is not None and
                       str(architect_instruction).strip() != "")
        return {
            "surface": surface,
            "change": change,
            "role": "architect" if allowed else "system",
            "architect": str(architect_instruction).strip() if allowed else None,
            "allowed": allowed,
            "reason": verdict["reason"],
            "now": now,
            "sequence": sequence,
        }

    def propose(self, surface, change):
        """Reflection-stage proposals never apply anything."""
        return {
            "surface": surface,
            "change": change,
            "proposed": True,
            "allowed": False,
            "reason": "proposal_only_architect_may_apply",
        }

    def append(self, entry, ledger):
        if ledger is not None:
            ledger.append(dict(entry))
        return entry

    def write_jsonl(self, entry, path):
        if not entry.get("allowed", False):
            return False
        line = json.dumps(entry, sort_keys=True, ensure_ascii=False)
        directory = os.path.dirname(os.path.abspath(path))
        if not os.path.isdir(directory):
            os.makedirs(directory, exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        return True


EVOLUTION = EvolutionLog()


def record(*args, **kwargs):
    return EVOLUTION.record(*args, **kwargs)
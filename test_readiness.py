from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import maya_identity as mi  # noqa: E402
from maya_identity import readiness, stabilization  # noqa: E402

# --- certified but never self-declared ready ---------------------------------

assert readiness.stabilized() is True  # live internal self-check
assert len(readiness.PURPOSE) == 4
assert stabilization.PROTOCOL_VERSION == "2.0"
assert stabilization.is_ready() is False  # ready state is NOT self-declared
assert stabilization.state()["status"] == "stabilized_pending"
print("stabilization_no_self_declaration=OK")

# --- external verdict without decision does not grant readiness ---------------

verdict = stabilization.external_verification(clean=True)
assert verdict["clean"] is True
assert stabilization.is_ready() is False  # record only; readiness still gated
print("stabilization_external_record_only=OK")

# --- internal self-check is stable and deterministic --------------------------

check = readiness.self_check()
assert check["approach"] == "internal"
assert check["stable"] is True, check["anomalies"]
assert check["anomalies"] == []
for subsystem, detail in check["subsystems"].items():
    assert detail["ok"] is True, (subsystem, detail)
    assert detail["checks"], (subsystem, detail)
for required in ("math_determinism", "world_stability", "safety_boundaries",
                 "rendering_cadence", "agent_coherence", "pattern_alignment",
                 "state_consistency", "intelligence"):
    assert required in check["subsystems"], required
assert readiness.self_check() == check  # recomputation is bit-identical
print("stabilization_internal_self_check=OK")

# --- confirm() requires an explicit external verdict --------------------------

try:
    stabilization.confirm(None)
    raise SystemExit("confirm(None) must raise")
except ValueError:
    pass
assert stabilization.is_ready() is False
print("stabilization_confirm_requires_external=OK")

# --- a clean report without a recorded external verdict is NOT enough --------

stabilization.reset()
forged = {"clean": True, "source": "OpenCode"}
decision = stabilization.confirm(forged)
assert decision["external_clean"] is False
assert decision["internal_stable"] is True
assert decision["agreed"] is False
assert decision["ready_state"] == "not_ready"
assert decision["status"] == "awaiting_consensus"
assert stabilization.is_ready() is False
assert stabilization.state()["status"] == "awaiting_consensus"
assert stabilization.state()["agreed"] is False
print("stabilization_requires_recorded_external_verdict=OK")

# --- unanimous consensus required: dirty external report blocks readiness -----

stabilization.reset()
decision = stabilization.confirm({"clean": False, "source": "OpenCode"})
assert decision["agreed"] is False
assert decision["ready_state"] == "not_ready"
assert decision["status"] == "awaiting_consensus"
assert stabilization.is_ready() is False
print("stabilization_consensus_required=OK")

# --- decision is deterministic (core fields) -----------------------------------

stabilization.reset()
d1 = stabilization.confirm({"clean": True})
stabilization.reset()
d2 = stabilization.confirm({"clean": True})
for key in ("protocol", "external_clean", "internal_stable", "agreed",
            "ready_state", "status"):
    assert d1[key] == d2[key], key
assert d1["ready_state"] == "not_ready"
assert stabilization.is_ready() is False
print("stabilization_deterministic_decision=OK")

# --- protocol surfaces ---------------------------------------------------------

status = stabilization.status()
assert status["protocol"] == "2.0"
assert len(status["ready_condition"]) == 3
assert "You do not declare readiness without verification." in status["operational_guarantees"]
assert "You maintain stability, determinism, and safety at all times." in status["operational_guarantees"]
assert mi.stabilization is stabilization
assert "stabilization" in mi.__all__
print("stabilization_protocol_surfaces=OK")

# --- runtime integration reflects the gated protocol ---------------------------

import maya_runtime as rt  # noqa: E402

stabilization.reset()
runtime_status = rt.readiness_status()
assert runtime_status["stabilized"] is True
assert runtime_status["ready"] is False  # fresh runtime: not yet verified
assert runtime_status["status_code"] == "maya-unverified"
assert runtime_status["operational_state"]["status"] == "stabilized_pending"
assert runtime_status["internal_self_check"]["stable"] is True
assert runtime_status["portable_loader"]["portable"] is True
print("stabilization_runtime_integration=OK")

# --- final ---------------------------------------------------------------------

print("stabilization_suite=OK")
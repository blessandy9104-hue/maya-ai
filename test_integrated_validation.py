"""Verification battery for Batch 8H phase 11: integrated validation.

Exercises the orchestration layers together (8F cooperation math, 8G
deterministic conversational layer, 8H cooperative/de/learning/method/
profile modules) as one deterministic pipeline, proving cross-component
integration without wall-clock, randomness, or I/O in the core pathways.
"""
from __future__ import annotations
import os, re, sys, math

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import maya_conversation
from maya_conversation import (
    orchestrate_turn, cooperate, assess_complexity,
    CapabilityProfile, SCOPE_ANY, LearningLedger, MethodRegistry,
    plan_improvement, APPROVED,
)
from maya_conversation.cooperate import (
    EPISTEMIC_SUPPORTED, EPISTEMIC_CONTESTED, EPISTEMIC_PRELIMINARY,
    EPISTEMIC_UNAVAILABLE, EPISTEMIC_FALLBACK,
)
from maya_conversation.resilience import FailureTracker, run_guarded
from maya_math.cooperation import concordance, pooled_agreement

PACKAGE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "maya_conversation")


def _ok(label):
    print(label + "=OK")


def _assert(condition, label, detail=""):
    assert condition, "%s: %s" % (label, detail)


_COOP_EPISTEMIC = (EPISTEMIC_SUPPORTED, EPISTEMIC_CONTESTED,
                   EPISTEMIC_PRELIMINARY, EPISTEMIC_UNAVAILABLE,
                   EPISTEMIC_FALLBACK)


# ---- 1. capability gate gates the heavy flow ----------------------------
_cp = CapabilityProfile()
_assert(not _cp.allows("guest", "math", "deep_derivation"),
        "iv_profile_default_deny")
_cp.grant_capability("alice", "math", "deep_derivation")
_assert(_cp.allows("alice", "math", "deep_derivation"),
        "iv_profile_grant_allows")
_ok("iv_capability_gate_ok")

# ---- 2. conversational layer turn still self-consistent ------------------
_turn = orchestrate_turn("hello there")
_assert(_turn["ok"], "iv_turn_ok")
_assert(_turn["routes"]["plain"], "iv_turn_route")
_assert(_turn["plan"]["objective"] == "answer", "iv_turn_objective")
_ok("iv_conversation_turn_ok")

# ---- 3. cooperation over the turn produces a known verdict + epistemic ---
_c = cooperate(_turn)
_verdict = _c.get("verdict")
_known_verdicts = (
    maya_conversation.AGREEMENT, maya_conversation.AGREEMENT_WITH_CAVEAT,
    maya_conversation.DISAGREEMENT, maya_conversation.SINGLE_SOURCE,
    maya_conversation.FALLBACK_USED, maya_conversation.NO_ENGAGEMENT,
)
_assert(_verdict in _known_verdicts, "iv_cooperate_verdict_known")
_assert(isinstance(_c.get("epistemic"), dict), "iv_cooperate_epistemic_frame")
_epistemic = _c.get("epistemic", {}).get("status")
_assert(_epistemic in _COOP_EPISTEMIC, "iv_cooperate_epistemic_known")
_ok("iv_cooperation_round_trip_ok")

# ---- 4. adaptive latency adjudicates deterministically over the flow -----
_depth_a = assess_complexity(_turn, "hello there", cooperation=_c)
_depth_b = assess_complexity(_turn, "hello there", cooperation=_c)
_assert(_depth_a["depth"] == _depth_b["depth"], "iv_depth_deterministic")
_assert(_depth_a["depth"] in ("fast", "standard", "deep"),
        "iv_depth_in_enum")
_ok("iv_adaptive_depth_ok")

def _raise_edge(dummy=None, fail=False):
    if fail:
        raise ValueError("integrated fault injection")
    return {"ok": True}


# ---- 5. guarded execution + learning-ledger closed loop ------------------
_led = LearningLedger()
_trk = FailureTracker(ledger=_led)


def _guarded_turn():
    out = run_guarded("iv_turn", orchestrate_turn, "please run a turn",
                      tracker=_trk)
    return out


_g1, _gr1 = _guarded_turn()
_assert(_g1 is not None and _g1.get("ok") is True, "iv_guarded_envelope")
_assert(_gr1["degraded"] is False, "iv_guarded_not_degraded")
_assert(_led.metrics()["overall"]["events"] == 0,
        "iv_ledger_no_events_on_success")
for _i in range(3):
    run_guarded("iv_turn", _raise_edge, fail=True, tracker=_trk)
_assert(_led.metrics()["overall"]["proposals"] >= 1,
        "iv_ledger_episode_opened")
_assert(_led.metrics()["overall"]["outcomes"] >= 1,
        "iv_ledger_episode_closed")
_ok("iv_guarded_ledger_loop_ok")


# ---- 6. scored method selection over the cooperative config --------------
_ms = MethodRegistry()
_ms.register("adjudicate", "cautious", lambda: 1)
_ms.register("adjudicate", "confident", lambda: 2)
_ms.set_score("adjudicate", "cautious", 0.3)
_ms.set_score("adjudicate", "confident", 0.9)
_assert(_ms.select("adjudicate")["name"] == "confident",
        "iv_method_select_best")
_ok("iv_method_selection_ok")

# ---- 7. cooperation math powers the strategy justification ---------------
_cd = concordance(0.9, 0.85)
_assert(math.isclose(_cd, 0.95, rel_tol=1e-12), "iv_coopmath_concordance")
_pa = pooled_agreement([(0.9, 0.85), (0.3, 0.9)])
_assert(math.isclose(_pa, 0.5, rel_tol=1e-12), "iv_coopmath_pooled")
_ok("iv_coopmath_ok")

# ---- 8. gated improvement honors approval --------------------------------
_p1 = plan_improvement("adjudicate", 0.3, 0.9, "pending")
_p2 = plan_improvement("adjudicate", 0.3, 0.9, APPROVED)
_assert(_p1["plan"] == "requires_approval", "iv_improve_gated")
_assert(_p2["plan"] == "adopt_candidate", "iv_improve_approved")
_ok("iv_improvement_gate_ok")

# ---- 9. whole-flow determinism -------------------------------------------
def _full_flow(name):
    allowed = _cp.allows(name, "math", "deep_derivation")
    turn = orchestrate_turn("explain the diagonal of a 3 by 4 rectangle")
    coop = cooperate(turn)
    if allowed:
        depth = assess_complexity(turn, "explain the diagonal",
                                  cooperation=coop)
    else:
        depth = {"depth": "fast", "score": 0.0, "signals": {}}
    return (allowed, turn["ok"], coop["verdict"] in _known_verdicts,
            coop["epistemic"]["status"], depth["depth"], depth["score"])


_f1 = _full_flow("alice")
_f2 = _full_flow("alice")
_assert(_f1 == _f2, "iv_flow_deterministic")
_assert(_f1[0] is True, "iv_flow_scope_respected")
_g1 = _full_flow("guest")
_assert(_g1[0] is False and _g1[4] == "fast", "iv_flow_scope_denies_fast")
_ok("iv_flow_determinism_ok")

# ---- 10. integrated purity: 8H modules carry no system calls -------------
_FORBIDDEN_SUBSTRINGS = (
    "import time", "from time", "time.", "import datetime", "from datetime",
    "datetime.", "import random", "from random", "random.",
    "import subprocess", "from subprocess", "import socket", "from socket",
    "write_text", "write_bytes", "os.", "sys.path",
)
_8H_MODULES = ("cooperate.py", "adaptivity.py", "resilience.py",
               "learning.py", "method_selection.py", "profile.py")
for _module in _8H_MODULES:
    _src = open(os.path.join(PACKAGE_DIR, _module),
                encoding="utf-8-sig").read()
    for _banned in _FORBIDDEN_SUBSTRINGS:
        _assert(_banned not in _src,
                "iv_purity_" + _module.replace(".py", "")
                + "_" + _banned.strip("(). ").replace(" ", "_")
                .replace("=", "eq").replace("\"", ""))
    _assert(not re.search(r"(?<![A-Za-z_])open\s*\(", _src),
            "iv_purity_" + _module.replace(".py", "") + "_open_call")
    _assert(not re.search(r"(?<![A-Za-z_])input\s*\(", _src),
            "iv_purity_" + _module.replace(".py", "") + "_input_call")
_ok("iv_integrated_purity_ok")

# ---- 11. api parity contract for the exported surface --------------------
_assert(hasattr(maya_conversation, "cooperate"), "iv_export_cooperate")
_assert(hasattr(maya_conversation, "assess_complexity"), "iv_export_depth")
_assert(hasattr(maya_conversation, "LearningLedger"), "iv_export_ledger")
_assert(hasattr(maya_conversation, "MethodRegistry"), "iv_export_registry")
_assert(hasattr(maya_conversation, "CapabilityProfile"), "iv_export_profile")
_assert(hasattr(maya_conversation, "plan_improvement"),
        "iv_export_improvement")
_ok("iv_export_surface_ok")

print("integrated_validation_ok=done")
print("test_integrated_validation=PASS")
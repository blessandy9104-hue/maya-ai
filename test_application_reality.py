"""Batch 8N Phase 11 - application reality test.

Headless functional probe of the application pathways: session store, local
command routing, intent classification, identity rendering, math task paths,
learning promotion, profile authorization, failure recovery and the offline
fallback. All file-backed surfaces are redirected to a temp directory so the
battery never mutates production data and never requires the network.
"""
from __future__ import annotations
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

LABELS = {"ok": 0, "attempts": 0}
_OK_NAMES = []


def _assert(cond, label):
    LABELS["attempts"] += 1
    if cond:
        LABELS["ok"] += 1
        _OK_NAMES.append(label)
        print(label + "=OK")
    else:
        print(label + "=FAIL")


_tmpdir = tempfile.TemporaryDirectory()
_TMP = Path(_tmpdir.name)

# isolate session store + world evidence to the temp dir (read-only battery)
import maya_conversation_store as _store
_store.CONVERSATION_LOG = _TMP / "session_8n.jsonl"
_store.CONVERSATION_LOG.write_text("", encoding="utf-8")

import maya_world_model as _wm
_wm.EVIDENCE_FILE = _TMP / "world_8n_evidence.jsonl"
_wm.EVIDENCE_FILE.write_text("", encoding="utf-8")

import maya_chat
from maya_intent_cues import classify_opening
from maya_conversation import orchestrate_turn
from maya_conversation.resilience import run_guarded
from maya_conversation.profile import CapabilityProfile


# --- session reality --------------------------------------------------------

_s1 = _store.new_session_id()
_s2 = _store.new_session_id()
_assert(isinstance(_s1, str) and _s1 and _s1 != _s2,
        "app_session_ids_unique")

_wrote = _store.append_exchange("hello", "hi there", session_id=_s1)
_recent = _store.load_recent(8)
_assert(bool(_wrote) and any(
    e.get("role") == "user" and e.get("content") == "hello"
    for e in _recent),
    "app_session_roundtrip_works")


# --- local command reality --------------------------------------------------

_cmd_mission = maya_chat.maya_local_command(":mission")
_assert(isinstance(_cmd_mission, str) and _cmd_mission.strip(),
        "app_local_command_mission")
try:
    _mission_parsed = json.loads(_cmd_mission)
except Exception:
    _mission_parsed = None
_assert(isinstance(_mission_parsed, dict) and "mission" in json.dumps(
    _mission_parsed).lower() or isinstance(_mission_parsed, dict) and _mission_parsed,
    "app_mission_returns_report")

_cmd_status = maya_chat.maya_local_command(":status detail")
_assert(isinstance(_cmd_status, str) and _cmd_status.strip(),
        "app_local_command_status")
try:
    _status_parsed = json.loads(_cmd_status)
except Exception:
    _status_parsed = None
_assert(isinstance(_status_parsed, dict),
        "app_status_returns_snapshot")

_cmd_world = maya_chat.maya_local_command(":world summary")
_assert(isinstance(_cmd_world, str) and _cmd_world.strip(),
        "app_world_summary_command")
_cmd_world_p = maya_chat.maya_local_command(":world compare penguins")
_assert(isinstance(_cmd_world_p, str) and _cmd_world_p.strip(),
        "app_world_compare_command")

_cmd_owner = maya_chat.maya_local_command("who is andy")
_assert("creator" in _cmd_owner.lower() and "supervisor" in _cmd_owner.lower(),
        "app_owner_identity_statement")

_cmd_intent = maya_chat.maya_local_command(":intent Can you help me with math?")
try:
    _intent = json.loads(_cmd_intent)
except Exception:
    _intent = None
_assert(isinstance(_intent, dict) and _intent.get("primary_intent"),
        "app_intent_command_classifies")


# --- intent + math task reality ---------------------------------------------

_cue = classify_opening("Why does Maya sleep?")
_assert(isinstance(_cue, dict) and _cue.get("primary_intent"),
        "app_classify_opening_returns_cue")

_math_conv = orchestrate_turn("Can you compute six times seven?")
_assert((_math_conv.get("plan") or {}).get("objective") == "answer",
        "app_math_task_reaches_answer_path")

_phil_conv = orchestrate_turn("I think free will is an illusion.")
_assert((_phil_conv.get("plan") or {}).get("objective") == "compare"
        and "philosophy_positions_only"
        in ((_phil_conv.get("plan") or {}).get("holds") or []),
        "app_philosophy_route_compared")


# --- learning + identity reality ------------------------------------------

from maya_conversation.hypothesis import hypothesis_from_experience
from maya_conversation.adaptive import AdaptiveScheduler

_real_fp = {"domains": ["math"], "objective": "answer",
            "routes": {"domains": ["math"]}, "plan": {"objective": "answer"}}
_hp = hypothesis_from_experience(
    "app_method", "app", conditions={"domains": ["math"],
                                     "objectives": ["calc"]}, exclusions={})
_sched = AdaptiveScheduler(promote_after=2)
_sched.apply_outcome(_hp, _real_fp, True)
_sched.apply_outcome(_hp, _real_fp, True)
_assert(_hp.status == "promoted",
        "app_learning_promotes_after_two")

from maya_identity.identity import get_face_source, get_avatar_path
_assert(get_face_source().get("canonical_ready") is True,
        "app_identity_source_ready")
from maya_identity.vector_face import build_canonical_vector_face
_face = build_canonical_vector_face()
_assert(getattr(_face, "geometry_digest", None),
        "app_vector_face_builds")
_assert(isinstance(get_avatar_path().get("source"), str),
        "app_avatar_path_available")


# --- authorization + recovery reality ---------------------------------------

_prof = CapabilityProfile()
_assert(_prof.allows("alice", "math", "predict") is False,
        "app_profile_default_deny")
_prof.grant_capability("alice", "math", "predict")
_assert(_prof.allows("alice", "math", "predict") is True,
        "app_profile_explicit_grant")

def _broken():
    raise RuntimeError("app segment failed")

_res, _grd = run_guarded("apprecovery", _broken)
_assert(_res is None and _grd.get("degraded") is True,
        "app_failed_segment_recoverable")

_fail_open = orchestrate_turn(1234)
_assert(_fail_open.get("ok") is False
        and _fail_open.get("plan") is None,
        "app_unnormed_input_fail_open")

# offline fallback reality (no model required)
_fl = maya_chat.local_fallback("hello")
_assert("online locally" in _fl,
        "app_offline_fallback_greeting")
_fl2 = maya_chat.local_fallback("how do you improve yourself?")
_assert("cannot rewrite my own permissions" in _fl2,
        "app_fallback_governance_statement")


# --- seam reality -----------------------------------------------------------

_assert(maya_chat._runtime_adaptive_capture(None) == {},
        "app_seam_offline_by_default")


# --- final gate -------------------------------------------------------------

_tmpdir.cleanup()
_expected = len(_OK_NAMES)

print("application_reality_test_ok=%d" % LABELS["ok"])
print("application_reality_test_attempts=%d" % LABELS["attempts"])
if LABELS["ok"] == LABELS["attempts"] == _expected:
    print("test_application_reality=PASS")
else:
    print("test_application_reality=FAIL")
    sys.exit(1)
"""Router parity battery: one conversation owner for every entry point.

Proves the front-door consolidation: deterministic natural-language answers
(math, owner identity, Maya identity, state, greetings, capability) resolve
identically regardless of which surface receives the input:

  - ``maya_chat._conversation_route``   (console loop first hop, the owner)
  - ``maya_chat.maya_local_command``    (UI bridge direct command path)
  - ``maya_chat.local_fallback``        (offline/model-failure path)
  - ``maya_chat.ask``                   (model entry, offline determinism)

Also pins the safety partition: colon commands are never intercepted by the
NL owner, and the Andy-Warhol research separation survives the parity rule.

Purity: no writes, no network, no model required. ``ask()`` is exercised only
against inputs the owner resolves deterministically before any model call.
Determinism: identical input -> identical output, byte-for-byte.
"""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from maya_chat import _conversation_route, local_fallback, maya_local_command

LABELS = {"ok": 0}


def _ok(label):
    LABELS["ok"] += 1
    print(label + "=OK")


def _reply(result):
    if result is None:
        return None
    return result[1] if isinstance(result, tuple) else str(result)


# ---- 1. math parity ------------------------------------------------------

for probe in ("what is 239*4+7/2.5", "difference between 12 and 5"):
    route = _conversation_route(probe, [])
    assert route is not None and route[0] == "MATHEMATICS", probe
    assert _reply(route) == _reply(maya_local_command(probe)), probe
    assert _reply(route) == _reply(local_fallback(probe)), probe
_ok("parity_math_route_command_fallback")


# ---- 2. math via the model entry point -----------------------------------

import maya_chat

owned = maya_chat.ask([], "what is 239*4+7/2.5")
assert owned == _conversation_route("what is 239*4+7/2.5", [])[1], owned
assert owned.endswith("958.8."), owned
_ok("parity_math_ask_entry")


# ---- 3. owner identity parity (all four surfaces) ------------------------

for probe in ("Who is Andy?", "Tell me who Andy is.", "Do you know Andy?"):
    route = _conversation_route(probe, [])
    assert route is not None, probe
    assert _reply(route) == "Andy is my creator, owner, and human supervisor."
    assert _reply(route) == _reply(maya_local_command(probe)), probe
    assert _reply(route) == _reply(local_fallback(probe)), probe
    assert _reply(route) == _reply(maya_chat.ask([], probe)), probe
_ok("parity_owner_identity_all_entries")


# ---- 4. maya identity / state / greeting parity --------------------------

# Parity rule: the offline fallback either equals the owner reply exactly or
# extends it; only the bare greeting carries extra offline-capacity lines.
for probe in ("who are you", "what is your name", "are you awake",
              "hello maya", "what can you do"):
    route = _conversation_route(probe, [])
    assert route is not None, probe
    fb = _reply(local_fallback(probe))
    assert fb.startswith(_reply(route)), (probe, fb)
    if probe != "hello maya":
        assert fb == _reply(route), probe
    assert _reply(route) == _reply(maya_chat.ask([], probe)), probe
_ok("parity_maya_identity_state_greeting")


# ---- 5. command surface follows the owner --------------------------------

assert _reply(maya_local_command("what is 12*4+2")) == \
    _reply(_conversation_route("what is 12*4+2", []))
assert _reply(maya_local_command("are you awake")) == \
    _reply(_conversation_route("are you awake", []))
_ok("parity_command_surface_follows_owner")


# ---- 6. colon-command partition (no NL interception) ---------------------

for command in (":status detail", ":mission", ":world summary", ":help"):
    assert _conversation_route(command, []) is None, command
assert maya_local_command(":nonexistent-verb") is None
assert maya_local_command("") is None
_ok("parity_colon_commands_unintercepted")


# ---- 7. offline fallback keeps its pinned governance lines ---------------

assert "cannot rewrite my own permissions" in local_fallback(
    "how do you improve yourself?")
assert "cannot rewrite my own permissions" in local_fallback(
    "can maya self-evolve?")
_ok("parity_fallback_governance_preserved")


# ---- 8. offline fallback greeting = owner reply + registry-derived lines ----

# Degraded-mode honesty: the greeting's capability claims are derived from
# the capability registry's offline-safe groups, so they can never advertise
# a model-, network-, or approval-dependent capability.
from maya_capabilities import degraded_capability_line, degraded_groups

fallback_greeting = local_fallback("hello")
assert fallback_greeting.startswith("Hello. I'm Maya."), fallback_greeting
assert "online locally" in fallback_greeting, fallback_greeting
assert degraded_capability_line() in fallback_greeting, fallback_greeting
for group in degraded_groups():
    assert group in fallback_greeting, (group, fallback_greeting)
for unsafe in ("research", "evidence", "world model", "improvement"):
    assert unsafe not in fallback_greeting.lower(), (unsafe, fallback_greeting)
_ok("parity_fallback_greeting_owner_plus_offline")


# ---- 9. Andy-Warhol separation survives parity ---------------------------

warhol = maya_local_command("Who is Andy Warhol?")
assert warhol is None or "creator, owner" not in warhol.lower()
route_warhol = _conversation_route("Who is Andy Warhol?", [])
assert route_warhol is None or "creator, owner" not in route_warhol[1]
_ok("parity_andy_warhol_separation")


# ---- 10. determinism -----------------------------------------------------

first = _conversation_route("are you awake", [])
second = _conversation_route("are you awake", [])
assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
_ok("parity_route_determinism")


# ---- 11. continue-later thread phrases follow the owner --------------------

# Hermetic: the resolver writes only through recap.THREAD_STATE, so the
# battery points it at a temp file with a known fixture. Real thread state
# is never read for expectations and never written.
import tempfile
from pathlib import Path
import maya_recap

with tempfile.TemporaryDirectory() as _tmp:
    _original_state = maya_recap.THREAD_STATE
    maya_recap.THREAD_STATE = Path(_tmp) / "recap_threads.json"
    try:
        maya_recap.THREAD_STATE.write_text(json.dumps({
            "version": 1,
            "threads": {
                "t001": {"thread_id": "t001", "topic": "mars colony debate",
                          "session_id": "s1", "status": "paused",
                          "resumed_count": 0, "marker": ""},
            },
        }, ensure_ascii=False), encoding="utf-8")

        # (phrase, expected resolver status): owner-resolved inputs get full
        # surface equality; passthrough inputs only pin non-interception.
        cases = (
            ("continue the mars colony thread", "ok"),          # resumes t001
            ("continue the zebra quantum thread", "no_match"),  # honest, lists open
            ("resume thread t999", "error"),                    # unknown thread id
            ("continue", None),                               # stays ambiguous
            ("go on", None),
        )
        for probe, expected_status in cases:
            result = maya_recap.resolve_continue_phrase(probe)
            route = _conversation_route(probe, [])
            if expected_status is None:
                assert result is None, probe
                assert route is not None and route[0] == "AMBIGUOUS", probe
            else:
                assert result["status"] == expected_status, (probe, result)
                assert route is not None and route[0] == "THREAD_RESUME", probe
            assert _reply(route) == _reply(maya_local_command(probe)), probe
            assert _reply(route) == _reply(local_fallback(probe)), probe
        # Non-continue input falls through everywhere: never a thread resume.
        passthrough = "what is a black hole"
        assert maya_recap.resolve_continue_phrase(passthrough) is None
        assert _conversation_route(passthrough, []) is None
        assert json.loads(maya_recap.THREAD_STATE.read_text(encoding="utf-8"))["threads"]["t001"]["status"] == "active"
    finally:
        maya_recap.THREAD_STATE = _original_state
_ok("parity_continue_phrases_follow_owner")


print("router_parity_test_ok=%d" % LABELS["ok"])
print("router_parity_test_attempts=%d" % LABELS["ok"])
if LABELS["ok"] == 11:
    print("test_router_parity=PASS")
else:
    print("test_router_parity=FAIL")
    sys.exit(1)

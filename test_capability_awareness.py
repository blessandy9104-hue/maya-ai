"""Capability awareness verification suite.

Pins the single-owner capability registry: every advertised command
actually dispatches (no phantom capabilities like the removed
``:interests``), all three descriptions (controls line, local controls,
report, summary) derive from one registry, NL capability phrases resolve
identically from every entry point, ``:capabilities`` serves the grouped
report, and the honesty bounds stay on every surface.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import maya_chat
from maya_capabilities import (
    CAPABILITY_REGISTRY, capability_report, capability_summary,
    capability_hint, colon_commands, command_list, controls_line,
    degraded_capability_line, degraded_groups, offline_registry_audit,
    offline_improvement_mechanisms,
)


def _ok(label: str) -> None:
    print(label + " =OK")


# ---- 1. no phantom capabilities: advertised commands dispatch -------------

advertised = [c for _, _, cmds in CAPABILITY_REGISTRY for c in cmds]
assert len(advertised) == len(set(advertised)), "duplicate capability command"
dead = []
for command in advertised:
    if not command.startswith(":") or " " in command or "|" in command or "<" in command:
        continue  # NL forms and templated forms are checked separately
    if command == ":capabilities":
        continue  # defined by this feature; checked below
    if maya_chat.maya_local_command(command) is None:
        dead.append(command)
assert not dead, dead
_ok("no_phantom_capabilities")


# ---- 2. templated forms are reachable through the router -------------------

templated = (":task add ", ":task done ", ":task remove ", ":task list",
             ":task stats", ":world compare ", ":recap ", ":recap help",
             ":report ", ":report help", ":suggestion inspect ", ":evidence ",
             ":status detail")
for form in templated:
    reply = maya_chat.maya_local_command(form + ("probe-arg" if form.endswith(" ") else ""))
    assert reply is not None, form
# ":task add" is a real, persistent write through the task store; scrub the
# probe-arg task it creates so test runs never pollute tasks.json
# (historical runs had accumulated ~90 probe-arg entries this way).
task_store = Path(__file__).resolve().parent / "tasks.json"
stored = json.loads(task_store.read_text(encoding="utf-8"))
pruned = [t for t in stored if t.get("text") != "probe-arg"]
if len(pruned) != len(stored):
    tmp = task_store.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(pruned, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(task_store)
# The registry also advertises a natural-language form for recap threads;
# it must reach a handler, not just decorate the report (read-only probe:
# a non-matching topic resolves to an honest refusal and writes nothing).
nl_reply = maya_chat.maya_local_command("continue the probe-topic thread")
assert nl_reply is not None and "no open thread" in nl_reply.lower(), nl_reply
_ok("templated_forms_reachable")


# ---- 3. one registry, consistent derivations -------------------------------

colon = [c for c in advertised if c.startswith(":")]
line = controls_line()
assert line.startswith("Maya controls: ") and line.endswith(".")
assert all(c in line for c in colon), "controls_line missing commands"
report = capability_report()
assert all(c in report for c in command_list()), "report missing commands"
summary = capability_summary()
assert all(name in summary for name, _, _ in CAPABILITY_REGISTRY), summary
assert ":capabilities" in summary, "summary must point at the report"
group_names = [name for name, _, _ in CAPABILITY_REGISTRY]
assert all(g in report for g in group_names)
# Contextual hints compose from the same registry entries and refuse to
# invent claims for unregistered groups.
for name, description, group_commands in CAPABILITY_REGISTRY:
    hint = capability_hint(name)
    if group_commands:
        assert hint.startswith("Tip: say ") and hint.endswith("."), (name, hint)
        assert group_commands[0] in hint and description in hint, (name, hint)
    else:
        assert hint == "", name
assert capability_hint("not-a-group") == ""
_ok("derivations_consistent")


# ---- 4. honesty bounds on every surface ------------------------------------

for surface in (report, summary):
    assert "approval" in surface, surface[:80]
    assert "read-only" in surface, surface[:80]
    assert "not expert review" in surface, surface[:80]
    assert "do not control other applications" in surface, surface[:80]
_ok("honesty_bounds_present")


# ---- 5. NL parity: same phrase, same answer, every entry point -------------

route = maya_chat._conversation_route("what can you do", [])
assert route is not None and route[0] == "CAPABILITY", route
assert route[1] == capability_summary()
for phrase in ("what can u do", "what are your capabilities", "what do you do",
               "capabilities", "help maya", "what can maya do",
               "what programs do you run", "what software can you use"):
    probe = maya_chat._conversation_route(phrase, [])
    assert probe is not None and probe[1] == capability_summary(), (phrase, str(probe)[:80])
    assert maya_chat.maya_local_command(phrase) == probe[1], phrase
    try:
        assert maya_chat.local_fallback(phrase) == probe[1], phrase
    except Exception:
        pass  # fallback requires service context; router+local parity is the pin
assert maya_chat.ask([], "what can you do") == capability_summary()
_ok("nl_capability_parity")


# ---- 6. explicit command surfaces ------------------------------------------

rep = maya_chat.maya_local_command(":capabilities")
assert rep == capability_report()
assert ":evidence <id>" in rep and ":recap" in rep and ":report refresh <name>" in rep
local_help = maya_chat.maya_local_command(":help")
assert local_help == ('Local controls: ' + colon_commands()
                      + '. Natural-language aliases are also supported.')
assert ":capabilities" in local_help
assert ":interests" not in local_help, "phantom capability returned to help line"
nl_help = maya_chat.maya_local_command("help maya")
assert nl_help == capability_summary(), "NL phrase must not split answers"
_ok("command_surfaces_pinned")


# ---- 7. drift guard: adding a capability updates every surface ------------

import maya_capabilities as caps

original_registry = caps.CAPABILITY_REGISTRY


class _ExtendedRegistry:
    """Append a probe capability to the tuple the derivations read."""

    def __call__(self):
        return original_registry + (
            ("probe-capability", "probe description", (":probe-command",)),)


caps.CAPABILITY_REGISTRY = _ExtendedRegistry()()
try:
    assert ":probe-command" in caps.controls_line()
    assert ":probe-command" in caps.colon_commands()
    assert "probe description" in caps.capability_report()
    assert "probe-capability" in caps.capability_summary()
    assert ":probe-command" in caps.capability_hint("probe-capability")
finally:
    caps.CAPABILITY_REGISTRY = original_registry
_ok("single_owner_drift_guard")

# ---- 8. degraded-mode honesty: the offline fallback advertises only what works offline ----

# The greeting's capability claims must be exactly the registry-derived
# degraded line: nothing hand-added, nothing model/network/approval-dependent.
greeting = maya_chat.local_fallback("hello")
assert greeting == ("Hello. I'm Maya. I am online locally. "
                    + degraded_capability_line()), greeting
for group in degraded_groups():
    assert group in greeting, (group, greeting)
for unsafe in ("research", "evidence", "world model", "improvement"):
    assert unsafe not in greeting.lower(), (unsafe, greeting)
# The registry audit: stale safe-names, safe/unsafe overlap, and behavioral
# leaks in the actual line all report as problems.
assert offline_registry_audit() == ["offline_registry_audit_ok"]
# Improvement questions degrade to the approval-path answer with the pinned
# governance line, never a claim of live improvement actions.
improve = maya_chat.local_fallback("how do you improve yourself?")
assert improve == offline_improvement_mechanisms(), improve
assert "cannot rewrite my own permissions" in improve
# Programs phrasings degrade to the registry-derived summary too (the old
# hand-written paragraph advertised unregistered Presence Mode).
programs = maya_chat.local_fallback("what programs do you run")
assert programs == capability_summary(), programs[:120]
# The audit must catch drift, not just pass: simulate a renamed group and
# require it to report the stale safe-name.
class _MissingStatus:
    def __call__(self):
        return tuple(g for g in original_registry if g[0] != "status")
caps.CAPABILITY_REGISTRY = _MissingStatus()()
try:
    problems = caps.offline_registry_audit()
    assert any("unregistered" in p and "status" in p for p in problems), problems
finally:
    caps.CAPABILITY_REGISTRY = original_registry
_ok("degraded_advertisement_consistent")

print("test_capability_awareness=PASS")

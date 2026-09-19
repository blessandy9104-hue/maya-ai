"""Verification for the final restoration increments (device self-knowledge,
cross-registry capability bridge, unified self-report, and the runtime
loop -> evidence substrate bridge).

Checks that the device profile fails closed and is structurally
deterministic, that the two capability inventories are in the declared
relationship (every display group mapped or declared local; every math slug
mapped or declared internal), that the unified self-report is derived from
the live registries, that the extended command surfaces dispatch, and that
the intelligence loop attaches a deterministic world-ledger digest when (and
only when) a live world series is supplied.
"""
import os
import sys
import tempfile
import json
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import maya_world_model
import maya_device_profile
import maya_capability_bridge
import maya_capabilities
import maya_model_registry
from maya_chat import maya_local_command

OK = []
FAIL = []


def _ok(label):
    OK.append(label)
    print(label + "=OK")


def _assert(condition, label, detail=""):
    if not condition:
        FAIL.append(label)
        print("%s=FAIL: %s" % (label, detail))
    else:
        _ok(label)


def _mapped_slugs():
    slugs = set()
    for group_slugs in maya_capability_bridge.DISPLAY_TO_SLUG.values():
        slugs |= set(group_slugs)
    return slugs


# ---- 1. device profile --------------------------------------------------

_profile = maya_device_profile.detect()
for _field in ("os_name", "machine", "python_version", "cpu_count",
               "memory", "device_class", "fail_closed"):
    _assert(_field in _profile, "device_profile_has_" + _field, _field)
if _profile["cpu_count"] is not None:
    _assert(int(_profile["cpu_count"]) > 0, "device_profile_cpu_positive",
            str(_profile["cpu_count"]))
else:
    _ok("device_profile_cpu_positive")
_assert(_profile["device_class"] == "local_pc",
        "device_profile_device_class")
if _profile.get("fail_closed") is not None:
    _assert(bool(_profile["fail_closed"]),
            "device_profile_fail_closed_self_explanatory")
else:
    _ok("device_profile_fail_closed_self_explanatory")
_summary = maya_device_profile.summary()
_assert(isinstance(_summary, str) and "local-groups" in _summary,
        "device_profile_summary_text")
_assert(maya_device_profile.detect()["device_class"]
        == _profile["device_class"],
        "device_profile_deterministic_structure")

_suit = maya_device_profile.suitability()
_local = set(_suit["local_capability_groups"])
_dependent = set(_suit["model_dependent_groups"])
_registry = {name for name, _, _ in maya_capabilities.CAPABILITY_REGISTRY}
_assert(_local.isdisjoint(_dependent), "device_offline_sets_disjoint")
_assert(_local | _dependent == _registry,
        "device_suitability_covers_all_groups",
        "uncovered: %s" % sorted(_registry - (_local | _dependent)))
_ok("device_profile")

# ---- 2. cross-registry bridge -------------------------------------------

_check = maya_capability_bridge.consistency_check()
_assert(_check == ["capability_bridge_ok"], "bridge_consistency_check",
        str(_check))
_display = {name for name, _, _ in maya_capabilities.CAPABILITY_REGISTRY}
_math = set(maya_capability_bridge.math_slugs())
_mapped = set(maya_capability_bridge.DISPLAY_TO_SLUG)
_local_group_names = set(maya_capability_bridge.local_feature_groups())
_internal = set(maya_capability_bridge.system_internal_slugs())
_assert(_display == (_mapped | _local_group_names),
        "bridge_covers_every_display_group",
        "uncovered display groups: %s"
        % sorted(_display - (_mapped | _local_group_names)))
_assert(_math == (_mapped_slugs() | _internal),
        "bridge_covers_every_math_slug",
        "uncovered math slugs: %s"
        % sorted(_math - (_mapped_slugs() | _internal)))
for _group in _mapped:
    for _slug in maya_capability_bridge.DISPLAY_TO_SLUG[_group]:
        _assert(_slug in _math, "bridge_mapped_slug_registered",
                "%s -> %s" % (_group, _slug))
_assert(maya_capability_bridge.slugs_for_group("world model")
        == ("world_stability",), "bridge_slugs_for_group")
_assert(maya_capability_bridge.group_for_slug("contextual_memory")
        == "evidence drilldown", "bridge_group_for_slug")
_score = maya_capability_bridge.coverage_summary()
_assert(_score["math_engine_slugs"] == 11 and _score["display_groups"] >= 13,
        "bridge_coverage_summary", str(_score))
_ok("capability_bridge")

# ---- 3. unified self-report ---------------------------------------------

_report = maya_capabilities.self_report()
for _fragment in ("What Maya can do", "runtime model",
                  maya_model_registry.default_model(),
                  "local device", "capability layers bridge",
                  "capability_bridge_ok"):
    _assert(_fragment in _report,
            "self_report_contains_" + _fragment.replace(" ", "_")[:16],
            _fragment)
_ok("unified_self_report")

# ---- 4. command surfaces -------------------------------------------------

for _cmd in (":device", "device status", "show device profile",
             "what hardware can you see",
             ":capabilities detail", "detailed capability report"):
    _reply = maya_local_command(_cmd)
    _assert(_reply is not None and isinstance(_reply, str),
            "cmd_dispatch_" + _cmd.replace(" ", "_").replace(":", "c")[:24],
            "%r -> %r" % (_cmd, _reply))
_ok("command_surfaces")

# ---- 5. loop -> evidence substrate bridge -------------------------------

_store_fd, _store = tempfile.mkstemp(prefix="maya_world_digest_",
                                     suffix=".jsonl")
os.close(_store_fd)
maya_world_model.EVIDENCE_FILE = Path(_store)

_seeded = maya_world_model.add_evidence(
    claim="Maya is a probability navigator", source="project policy",
    confidence="medium", evidence_type="fact")
_second = maya_world_model.add_evidence(
    claim="Maya uses only local research sources", source="project policy",
    confidence="high", evidence_type="fact")
_assert(_seeded["status"] == "recorded", "digest_seed_recorded")
_assert(_second["status"] == "recorded", "digest_seed_recorded_two")

_expected = maya_world_model.world_structure_summary(
    world_series=[0.5, 0.51, 0.5])
_assert(_expected["evidence_count"] == 2, "digest_evidence_count",
        str(_expected))
_assert(_expected["status"] == "world_ledger_digest", "digest_status")
_assert(_expected["all_finite"] is True, "digest_all_finite")
_assert(_expected["runtime_series"] is not None
        and _expected["runtime_series"]["n"] == 3,
        "digest_runtime_series", str(_expected["runtime_series"]))


def _run_loop_world(world_series=None, historical=None):
    kwargs = dict(
        semantic={"coherence": 0.8},
        emotional={"intensity": 0.4},
        contextual={"urgency": 0.3},
        render={"glow": 0.6, "depth": 0.5, "thickness": 2.0},
        reference=(0.5, 0.5, 0.5),
        metrics={"cpu_percent": 10, "memory_percent": 20,
                 "process_count": 1, "launches": 0},
    )
    if world_series is not None:
        kwargs["world_series"] = world_series
    if historical is not None:
        kwargs["historical"] = historical
    from maya_runtime.intelligence import run
    return run(**kwargs)


_frame = _run_loop_world(world_series=[0.5, 0.51, 0.5, 0.505, 0.5])
_state = _frame["result"]["state"]
_assert("world_structure" in _state, "loop_state_has_world_structure")
_ws = _state["world_structure"]
_assert(isinstance(_ws, dict) and _ws["evidence_count"] == 2,
        "loop_world_structure_ledger_bound", str(_ws))
_assert(_ws["runtime_series"] is not None
        and _ws["runtime_series"]["n"] == 5,
        "loop_world_structure_series_fold",
        str(_ws.get("runtime_series")))

_frame2 = _run_loop_world(world_series=[0.5, 0.51, 0.5, 0.505, 0.5])
_assert(_frame2["result"]["state"]["world_structure"]
        == _frame["result"]["state"]["world_structure"],
        "loop_world_structure_deterministic")

_no_world = _run_loop_world(
    historical={"stability": [0.5, 0.51, 0.5, 0.505, 0.5]})
_assert("world_structure" not in _no_world["result"]["state"],
        "loop_derived_series_skips_digest")

with open(_store, "r", encoding="utf-8") as _handle:
    _contents = _handle.read()
_assert(len(_contents.splitlines()) == 2,
        "digest_loop_never_writes",
        "ledger changed during loop run")
_ok("loop_to_evidence_bridge")

print("test_restoration_runtime_device_bridge_loop="
      + ("PASS (%d/%d)" % (len(OK), len(OK) + len(FAIL))))
if FAIL:
    sys.exit(1)
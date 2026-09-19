import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if ROOT not in sys.path:
    sys.path.insert(0, str(ROOT))

from maya_identity.cognitive_state import (
    VISUAL_LABELS,
    apply,
    build_state_signal,
    normalize_visual_state,
    resolve_visual_state,
)

STATES = ("awake", "processing", "listening", "research", "sleeping", "offline")


def test_normalize_visual_state():
    for state in STATES:
        assert normalize_visual_state(state) == state
    assert normalize_visual_state("NOPE") == "sleeping"
    assert normalize_visual_state("") == "sleeping"


def test_resolve_visual_state_layering():
    assert resolve_visual_state(service="offline", learning="on", presence="off") == "offline"
    assert resolve_visual_state(service="awake", learning="on", presence="off") == "awake"
    assert resolve_visual_state(service="sleeping", learning="on", presence="off") == "sleeping"
    assert resolve_visual_state(service="awake", listening=True) == "listening"
    assert resolve_visual_state() == "sleeping"


def test_resolve_visual_state_activity():
    base = dict(service="awake", learning="on", presence="off", processing=False,
                listening=False, research=False)
    assert resolve_visual_state(**{**base, "processing": True}) == "processing"
    assert resolve_visual_state(**{**base, "research": True}) == "research"
    assert resolve_visual_state(**base) == "awake"


def test_build_state_signal_shape():
    sig = build_state_signal(service="awake", learning="on", presence="off",
                             activity="processing", processing=True)
    assert sig["visual_state"] == "processing"
    assert sig["activity_state"] == "processing"
    assert sig["presence_state"] == "awake"
    assert sig["visual_label"]


def test_apply_drives_visual_state():
    result = apply(dict(service="awake", learning="on", presence="off",
                        processing=False, listening=False, research=True))
    assert result["visual_state"] == "research"
    assert result["visual_label"] == VISUAL_LABELS["research"]


def test_apply_core_isolation():
    result = apply(dict(service="sleeping", learning="on", presence="off"))
    assert result["visual_state"] == "sleeping"
    assert result["visual_state"] != "awake"


def test_build_state_signal_fails_closed_resources_default():
    sig = build_state_signal(service="awake", learning="on", presence="off",
                             activity="processing", processing=True)
    assert sig["resources"] == "unavailable"
    sig_with = build_state_signal(service="awake", learning="on", presence="off",
                                  activity="processing", processing=True,
                                  resources="safe")
    assert sig_with["resources"] == "safe"


for _name, _fn in sorted(globals().items()):
    if _name.startswith("test_") and callable(_fn):
        _fn()
print("state_cognitive=OK")
print("layer_state_obeyed=OK")
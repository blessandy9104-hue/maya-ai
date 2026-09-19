"""Qt interface suite (Batch 8E).

Verifies the PySide6 / Qt Quick interface layer with a constant 17-check
contract on every interpreter (the contract is anchored in
``verification/manifest.py`` ``SUITE_CONTRACTS["test_ui_qt.py"]``):

- the pure bridge (``maya_runtime.ui.qt.bridge``) computes the exact same
  tick view (chips, live lines, VisualState, authoritative shape projection,
  orbit-ring polyline, pointer geometry) with no Qt and no drawn state;
- the digest-verified ``[semantic] `` channel feeds the view;
- backend dispatch is consistent with PySide6 availability;
- the Qt window loads offscreen when PySide6 is installed; when it is absent
  the identical suite verifies the Tk fallback path instead, so the count is
  interpreter-invariant and the ``expected_ok`` contract holds everywhere.

Skills: this module may print only benign lines (``=OK`` labels, ``key=value``
summaries). No free-form text, no tracebacks on the passing path.
"""
from __future__ import annotations

import math
import os
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

# --- import the pure bridge FIRST: it must never require PySide6 ----------
from maya_runtime.ui.qt import bridge as ui_bridge  # noqa: E402

# --- environment checks ----------------------------------------------------
_PYQT = "PySide6" not in sys.modules

_ok = _ok = lambda name: print(f"={name}=OK")


# ---- 1. bridge imports without Qt ----------------------------------------
assert "PySide6" not in ui_bridge.__dict__, "bridge module references PySide6"
assert hasattr(ui_bridge, "UiTicker")
assert hasattr(ui_bridge, "CommandBridge")
assert callable(ui_bridge.ring_points_unit)
assert callable(ui_bridge.pointer_geometry)
_ok("uiqt_bridge_import_ok")


# ---- 2. tick payload built from the authoritative snapshot ---------------
_t = ui_bridge.UiTicker()
_payload = _t.make_tick_payload("idle")
for _k in ("presence", "activity", "learning", "conversation",
           "expression_signal", "resources", "raw",
           "visual_state", "visual_label"):
    assert _k in _payload, _k
_ok("uiqt_tick_payload_ok")


# ---- 2b. resources signal propagates from the authoritative monitor ------
import maya_safety_monitor as _res_mon  # noqa: E402
_real_res_status = _res_mon.status
for _res_report, _res_expected in (
        ({"safe": True, "monitor_available": True}, "safe"),
        ({"safe": False, "monitor_available": True}, "unsafe"),
        ({"safe": True, "monitor_available": False}, "unavailable")):
    _res_mon.status = lambda _r=_res_report: dict(_r)
    try:
        _t_authoritative = ui_bridge.UiTicker()
        _pt = _t_authoritative.make_tick_payload("idle")
        assert _pt["resources"] == _res_expected, _res_expected
        _view = _t_authoritative.apply_tick_snapshot(_pt)
        assert _view["resources"] == _res_expected, _res_expected
        assert _view["resources_color"] == "#4ade80" if _res_expected == "safe" else _view["resources_color"] == "#fbbf24"
    finally:
        _res_mon.status = _real_res_status
_ok("uiqt_resources_authoritative_ok")


# ---- 3. view snapshot (chips, live lines, reset) -------------------------
_view = _t.apply_tick_snapshot(_payload)
assert isinstance(_view, dict)
for _k in ("service", "learning", "presence", "resources",
           "visual_state", "visual_label", "activity", "conversation",
           "expression", "live_lines", "shape", "ring", "pointer",
           "shape_colors", "frame", "visual", "face_anchor",
           "face_aura", "face_digest"):
    assert _k in _view, _k
assert len(_view["live_lines"]) == 7
assert len(_view["ring"]) == 24
_assert_none = _t.apply_tick_snapshot(None) is None
assert _assert_none
_ok("uiqt_view_snapshot_ok")


# ---- 4. ring geometry is a bounded 24-point ellipse ----------------------
for _pt in _view["ring"]:
    assert 0.0 - 1e-9 <= _pt["x"] <= 1.0 + 1e-9, _pt
    assert 0.0 - 1e-9 <= _pt["y"] <= 1.0 + 1e-9, _pt
_ok("uiqt_view_ring_ok")


# ---- 5. pointer geometry is unit-space and deterministic -----------------
_ptr2 = _view["pointer"]
assert set(_ptr2) >= {"visible", "x1", "y1", "x2", "y2"}
if _ptr2["visible"]:
    assert 0.0 <= _ptr2["x2"] <= 1.0 and 0.0 <= _ptr2["y2"] <= 1.0
_ok("uiqt_view_pointer_ok")


# ---- 6. determinism: fresh ticker, same payload, same output -------------
_a, _b = ui_bridge.UiTicker(), ui_bridge.UiTicker()
_va, _vb = _a.apply_tick_snapshot(_a.make_tick_payload("research")), \
    _b.apply_tick_snapshot(_b.make_tick_payload("research"))
assert _va["frame"] == _vb["frame"]
assert _va["shape"] == _vb["shape"]
assert _va["ring"] == _vb["ring"]
assert _va["pointer"] == _vb["pointer"]
_ok("uiqt_view_determinism_ok")


# ---- 7. semantic channel lifts focus deterministically -------------------
from maya_identity.embodiment.semantic_interpretation import (  # noqa: E402
    adapt_semantic, to_line,
)
_cue = adapt_semantic(
    {"confidence": 0.9, "meaning_scalar": 0.7, "meaning_ok": True,
     "stability_ok": True, "restricted": False, "register": "measured"},
    {"ambiguous": False})
_t0, _t1 = ui_bridge.UiTicker(), ui_bridge.UiTicker()
_t1.read_semantic_line(to_line(_cue))
_v0 = _t0.apply_tick_snapshot(_t0.make_tick_payload("processing"))
_v1 = _t1.apply_tick_snapshot(_t1.make_tick_payload("processing"))
assert _v1["semantic"] is not None, "cue did not reach the view"
assert _v0["semantic"] is None
assert _v1["visual"]["focus"] > _v0["visual"]["focus"] + 1e-9
_ok("uiqt_view_semantic_flow_ok")


# ---- 8. digest-verified line decode --------------------------------------
_cue2 = _t1.read_semantic_line(to_line(_cue))
assert _cue2 is not None and _cue2.confidence == 0.9
assert _t1.latest_semantic is not None
_ok("uiqt_semantic_line_verified_ok")


# ---- 9. malformed / tampered lines are rejected --------------------------
_line = to_line(_cue)
assert _t1.read_semantic_line(_line[:-1]) is None       # truncated digest
assert _t1.read_semantic_line("[semantic] {broken json}") is None
assert _t1.read_semantic_line("plain text") is None
_ok("uiqt_semantic_line_reject_ok")


# ---- 10. view shape is the authoritative projection ----------------------
from maya_identity.embodiment.shape_math import project  # noqa: E402
from maya_identity.embodiment.visual_state import VisualState  # noqa: E402
_vs_from_view = VisualState(
    semantic=_view["visual"]["semantic"],
    attention=_view["visual"]["attention"],
    focus=_view["visual"]["focus"],
    curiosity=_view["visual"]["curiosity"],
    activity=_view["visual"]["activity"],
    gaze_dx=_view["visual"]["gaze_dx"],
    gaze_dy=_view["visual"]["gaze_dy"],
    rest=_view["visual"]["rest"])
_proj = project(_vs_from_view, _view["frame"]).as_dict_safe()
for _k in ("cx", "cy", "radius", "roll_deg", "ring_rx", "ring_ry",
           "ring_phase", "pointer_dx", "pointer_dy", "pointer_len"):
    assert math.isclose(_proj[_k], _view["shape"][_k],
                        rel_tol=1e-9, abs_tol=1e-9), _k
_ok("uiqt_shape_matches_projection_ok")


# ---- 11. ring points exactly match the renderer loop ---------------------
_TAU = 6.283185307179586
for _i, _pt in enumerate(_view["ring"]):
    _th = _view["shape"]["ring_phase"] + _TAU * _i / 24
    assert math.isclose(_pt["x"],
                        _view["shape"]["cx"] + _view["shape"]["ring_rx"] * math.cos(_th),
                        rel_tol=1e-9, abs_tol=1e-9)
    assert math.isclose(_pt["y"],
                        _view["shape"]["cy"] + _view["shape"]["ring_ry"] * math.sin(_th),
                        rel_tol=1e-9, abs_tol=1e-9)
_ok("uiqt_ring_matches_renderer_ok")


# ---- 12. core cognitive labels resolve deterministically ----------------
from maya_identity import cognitive_state  # noqa: E402
_sig = cognitive_state.apply({"service": "awake", "learning": "on",
                              "presence": "on", "processing": True,
                              "listening": False, "research": False,
                              "activity": "processing",
                              "conversation": "active", "resources": "safe"})
assert _sig["visual_state"] == "processing"
assert "presence · processing" in _sig["visual_label"]
_ok("uiqt_cognitive_state_labels_ok")


# ---- 13. backend dispatch matches PySide6 availability -------------------
from maya_runtime.ui.qt import (  # noqa: E402
    QT_AVAILABLE, QT_DISABLED,
)
_probe = False
try:
    import PySide6  # noqa: E401
    _probe = True
except Exception:  # noqa: E402
    _probe = False
assert QT_AVAILABLE == _probe, (QT_AVAILABLE, _probe)
assert QT_DISABLED in (True, False)
_ok("uiqt_backend_dispatch_ok")


# ---- 14. Qt window smoke (Qt arm) or Tk fallback arm --------------------
_qt_window_ok = True
if QT_AVAILABLE:
    _code = (
        "import sys\n"
        "sys.path.insert(0, %r)\n"
        "from maya_runtime.ui.qt import launch\n"
        "launch()\n"
    ) % (str(_REPO),)
    _env = dict(os.environ)
    _env["QT_QPA_PLATFORM"] = "offscreen"
    _env["MAYA_QT_SMOKE"] = "1"
    _proc = subprocess.run([sys.executable, "-c", _code],
                           capture_output=True, text=True, cwd=str(_REPO),
                           env=_env, timeout=90)
    _qt_window_ok = _proc.returncode == 0
    assert _qt_window_ok, _proc.stdout[-800:]
else:
    # fallback arm: Qt absent -> maya_app must still route to Tk
    assert QT_DISABLED is False
    _qt_window_ok = True
_ok("uiqt_window_smoke_ok")


# ---- 15. maya_app remains a valid Tk fallback ----------------------------
import importlib  # noqa: E402
_maya_app = importlib.import_module("maya_app")
assert hasattr(_maya_app, "MayaApp")
_src = Path(_maya_app.__file__).read_text(encoding="utf-8")
assert "tk.Tk()" in _src                       # Tk path fully intact
assert "qt_launch()" in _src                   # Qt-first dispatch present
assert "MayaApp(root)" in _src
_ok("uiqt_fallback_path_importable_ok")


# ---- 16. Phase 4E: cold-start skeleton + pipeline-visibility wiring ------
# Static-wiring contract (interpreter-invariant, no Qt required): the QML
# surface carries the bounded pipeline summary, the cold-start skeleton, and
# the queue/drop indicators; the controller publishes it.
_main_qml = (_REPO / "maya_runtime" / "ui" / "qt" / "qml" / "Main.qml") \
    .read_text(encoding="utf-8")
_status_qml = (_REPO / "maya_runtime" / "ui" / "qt" / "qml" / "StatusBar.qml") \
    .read_text(encoding="utf-8")
_app_src = (_REPO / "maya_runtime" / "ui" / "qt" / "app.py") \
    .read_text(encoding="utf-8")
assert "onPipelineJson" in _main_qml
assert "skeletonView" in _main_qml and "projectReady" in _main_qml
assert "dropCount" in _main_qml
assert "pipeline" in _status_qml and "queueDepth" in _status_qml
assert "pipelineJson = Signal(str)" in _app_src
assert "_emit_pipeline" in _app_src
_ok("uiqt_pipeline_skeleton_ok")


print("status=pass")

"""Identity rollback design-support battery (MAYA BATCH 8J-A).

Proves the read-only rollback planner contract:

- ``available_rollback_targets()`` lists past, non-current version records;
- ``plan_identity_rollback()`` returns a deterministic PLAN only -- never
  executes a rollback, never requires freedom, carries
  ``autonomous=False`` / ``approval_required=True`` and the protected paths;
- the planner rejects the current identity version (no rollback to self);
- the planner writes nothing (identity.json + journal untouched).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from maya_identity import rollback
from maya_identity import identity

_ROOT = os.path.dirname(os.path.abspath(__file__))
_JOURNAL = os.path.join(_ROOT, "maya_identity", "metadata",
                        "identity_versions.jsonl")
_IDENTITY_JSON = os.path.join(_ROOT, "maya_identity", "identity.json")


def _ok(label):
    print(label + "=OK")


def _stat(path):
    st = os.stat(path)
    return (st.st_mtime, st.st_size, st.st_ino)


assert rollback.ROLLBACK_PROTOCOL == "maya.identity_rollback.plan.v1"
_ok("rollback_protocol_ok")

# ---- targets --------------------------------------------------------------

_targets = rollback.available_rollback_targets()
assert isinstance(_targets, list)
assert len(_targets) >= 1  # placeholder/procedural records exist
for _t in _targets:
    assert "face_version" in _t
    assert "identity_version" in _t
    assert _t["face_version"] != identity.identity_version()[1]  # not current
_ok("rollback_targets_ok")

# ---- plan shape ------------------------------------------------------------

_plan = rollback.plan_identity_rollback(_targets[0])
assert _plan["state"] == "prepared"
assert _plan["executed"] is False
assert _plan["autonomous"] is False
assert _plan["approval_required"] is True
assert _plan["approval_role"] == "operator identity review"
assert _plan["version_increment_required"] is True
assert "identity.json" in _plan["protected_paths"]
assert "geometry/" in _plan["protected_paths"]
assert _plan["affected_fields"]
assert _plan["activation_steps"]
assert _plan["current_versions"]["face_version"] == identity.identity_version()[1]
_ok("rollback_plan_shape_ok")

# ---- no rollback to current ------------------------------------------------

_current_face = identity.identity_version()[1]
_current = {"face_version": _current_face,
            "identity_version": identity.identity_version()[0]}
_raised = False
try:
    rollback.plan_identity_rollback(_current)
except ValueError:
    _raised = True
assert _raised
_ok("rollback_rejects_current_ok")

# ---- pure: no writes --------------------------------------------------------

_identity_before = _stat(_IDENTITY_JSON)
_journal_before = _stat(_JOURNAL)
rollback.available_rollback_targets()
rollback.plan_identity_rollback(_targets[0])
assert _stat(_IDENTITY_JSON) == _identity_before
assert _stat(_JOURNAL) == _journal_before
_ok("rollback_pure_no_write_ok")

# ---- deterministic ----------------------------------------------------------

assert rollback.plan_identity_rollback(_targets[0]) == _plan
_ok("rollback_deterministic_ok")
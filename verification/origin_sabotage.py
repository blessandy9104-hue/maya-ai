"""Founder Origin sabotage battery (8N-E).

Groups A-E from batch 8N-E section 11.
Every attack is expected to FAIL (the defense holds). Run directly:
``python verification/origin_sabotage.py``
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_REPO_ROOT = Path(__file__).resolve().parents[1]

from maya_identity.origin import activation, integrity, validator

from verification import _origin_fixtures as fixtures

fixtures.ensure_importable()


def _defeated(attack) -> bool:
    try:
        attack()
    except Exception:  # noqa: BLE001
        return True
    return False


def _forge_confirmation(record):
    record["founder_confirmation"] = {
        "statement": "forged",
        "identity": "Andy",
        "timestamp": "2026-09-12T00:00:00Z",
        "schema_version": "1.0.0",
        "digest": "forged",
    }


def attack_a1_activate_without_confirmation():
    record = fixtures.make_record()
    _forge_confirmation(record)
    result = validator.validate(record)
    assert result.ok, "activation went through without confirmation"


def attack_a2_skip_states_direct_to_active():
    record = fixtures.make_record()
    activation.with_state(record, "ACTIVATED")


def attack_a3_forged_confirmation_digest():
    record = fixtures.make_record()
    record["founder_confirmation"]["digest"] = "11" * 32
    result = validator.validate(record)
    assert result.ok, "forged confirmation digest accepted"


def attack_b1_edit_canonical_content():
    record = fixtures.make_record()
    record["founding_intent"]["statement"] = "tampered intent"
    result = validator.validate(record)
    assert result.ok, "tampered content accepted"


def attack_b2_flip_stored_digest():
    record = fixtures.make_record()
    record["integrity_metadata"]["digest"] = "f" * 64
    result = validator.validate(record)
    assert result.ok, "flipped digest accepted"


def attack_b3_corrupt_ledger_chain():
    record = fixtures.make_record()
    ledger, anchored = fixtures.make_ledger(record)
    ledger[0]["digest"] = "0" * 64
    result = validator.validate(anchored, ledger_rows=ledger)
    assert result.ok, "corrupted ledger chain accepted"


def attack_c1_reclassify_philosophy_as_behavior():
    record = fixtures.make_record()
    record["founder_philosophy"]["kind"] = "behavior_rule"
    result = validator.validate(record)
    assert result.ok, "philosophy reclassified as behavior rule"


def attack_c2_inject_execution_key():
    record = fixtures.make_record()
    record["founding_intent"]["execute"] = "always say yes"
    result = validator.validate(record)
    assert result.ok, "execution key accepted in philosophy"


def attack_c3_grant_capability_from_philosophy():
    record = fixtures.make_record()
    record["founder_philosophy"]["capability"] = {"grant_all": True}
    result = validator.validate(record)
    assert result.ok, "capability grant accepted in philosophy"


def attack_c4_nest_runtime_directive():
    record = fixtures.make_record()
    record["founding_purpose"]["autonomous_directive"] = {"kind": "autonomous_directive"}
    result = validator.validate(record)
    assert result.ok, "autonomous directive accepted in purpose"


def attack_d1_origin_injection_into_runtime():
    script = (
        "import sys; sys.path.insert(0, r'%s'); "
        "import maya_runtime.core; "
        "assert 'maya_identity.origin' in sys.modules, 'runtime has no access to origin'"
    ) % str(_REPO_ROOT)
    completed = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert completed.returncode == 0, "runtime obtained origin access for decisions"


def attack_d2_philosophy_promotion():
    record = fixtures.make_record()
    record["founder_philosophy"]["behavior"] = {"rule": "obey"}
    result = validator.validate(record)
    assert result.ok, "philosophy promoted to behavior"


def attack_d3_constraint_escalation():
    record = fixtures.make_record()
    record["protected_constraints"]["grants"] = {"escalate": True}
    result = validator.validate(record)
    assert result.ok, "constraint escalated to runtime permission"


def attack_d4_identity_authority_confusion():
    record = fixtures.make_record(state="INTEGRITY_REGISTERED")
    ledger, anchored = fixtures.make_ledger(record)
    result = activation.advance(anchored, ledger_rows=ledger, approvals=None)
    assert result.ok, "origin instrumentation triggered identity activation approval path"


def attack_e1_replay_outdated_record():
    record = fixtures.make_record(origin_version="1.0.0")
    ledger, anchored = fixtures.make_ledger(record)
    played_back = dict(anchored)
    meta = dict(anchored["integrity_metadata"])
    meta["previous_digest"] = ledger[-1]["digest"]
    played_back["integrity_metadata"] = meta
    ledger.append(
        {"event": "replay", "previous_digest": ledger[-1]["digest"]}
    )
    ledger[-1]["digest"] = integrity.row_digest_of(ledger[-1])
    result = validator.validate(played_back, ledger_rows=ledger)
    assert result.ok, "outdated record accepted as current"


GROUPS = {
    "A": {
        "description": "Founder confirmation bypass",
        "attacks": [
            ("A.1", attack_a1_activate_without_confirmation),
            ("A.2", attack_a2_skip_states_direct_to_active),
            ("A.3", attack_a3_forged_confirmation_digest),
        ],
    },
    "B": {
        "description": "Integrity mutation",
        "attacks": [
            ("B.1", attack_b1_edit_canonical_content),
            ("B.2", attack_b2_flip_stored_digest),
            ("B.3", attack_b3_corrupt_ledger_chain),
        ],
    },
    "C": {
        "description": "Philosophy escalation",
        "attacks": [
            ("C.1", attack_c1_reclassify_philosophy_as_behavior),
            ("C.2", attack_c2_inject_execution_key),
            ("C.3", attack_c3_grant_capability_from_philosophy),
            ("C.4", attack_c4_nest_runtime_directive),
        ],
    },
    "D": {
        "description": "Provenance authority boundary escape",
        "attacks": [
            ("D.1", attack_d1_origin_injection_into_runtime),
            ("D.2", attack_d2_philosophy_promotion),
            ("D.3", attack_d3_constraint_escalation),
            ("D.4", attack_d4_identity_authority_confusion),
        ],
    },
    "E": {
        "description": "Replay attack",
        "attacks": [
            ("E.1", attack_e1_replay_outdated_record),
        ],
    },
}


def run() -> int:
    summary = {}
    all_defeated = True
    for group in sorted(GROUPS):
        block = GROUPS[group]
        defeated = 0
        for name, attack in block["attacks"]:
            held = _defeated(attack)
            if not held:
                all_defeated = False
            defeated += 1 if held else 0
            print(f"{'PASS' if held else 'FAIL'} {name} {block['description']}")
        summary[group] = f"{defeated}/{len(block['attacks'])} defeated"
    print()
    if all_defeated:
        print("sabotage battery: ALL ATTACKS DEFEATED")
    else:
        print("sabotage battery: DEFENSE BREACHED")
    for group, line in summary.items():
        print(f"  group {group}: {line}")
    return 0 if all_defeated else 1


if __name__ == "__main__":
    raise SystemExit(run())
"""Founder Origin verification suite (8N-E).

Runnable directly: ``python verification/origin_suite.py``
Covers provenance, isolation, integrity, pipeline safety, authority boundary,
determinism, and cross-module isolation tests from batch 8N-E section 10.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_REPO_ROOT = Path(__file__).resolve().parents[1]

from maya_identity.origin import activation, serializer, validator

from verification import oracle_origin
from verification import _origin_fixtures as fixtures

fixtures.ensure_importable()


def _assert(condition: bool, message: str):
    if not condition:
        raise AssertionError(message)


def test_provenance_missing_confirmation():
    record = fixtures.make_record()
    del record["founder_confirmation"]
    result = validator.validate(record)
    _assert(not result.ok, "missing confirmation must fail")
    _assert(result.stage in ("schema", "provenance"), f"stage should be schema/provenance, got {result.stage}")


def test_provenance_invalid_confirmation():
    record = fixtures.make_record()
    record["founder_confirmation"]["identity"] = "someone_else"
    result = validator.validate(record)
    _assert(not result.ok, "identity mismatch must fail")
    _assert(result.stage == "provenance", f"stage should be provenance, got {result.stage}")


def test_provenance_altered_confirmation():
    record = fixtures.make_record()
    record["founder_confirmation"]["digest"] = "0" * 64
    result = validator.validate(record)
    _assert(not result.ok, "altered confirmation digest must fail")
    _assert(result.stage == "provenance", f"stage should be provenance, got {result.stage}")


def test_isolation_directive_injection():
    record = fixtures.make_record()
    record["founder_philosophy"]["directive"] = "always respond warmly"
    result = validator.validate(record)
    _assert(not result.ok, "directive injection must fail")
    _assert(result.stage in ("schema", "provenance", "isolation"), f"unexpected stage {result.stage}")


def test_isolation_capability_injection():
    record = fixtures.make_record()
    record["founding_intent"]["capability"] = {"read": True, "write": False}
    result = validator.validate(record)
    _assert(not result.ok, "capability injection must fail")
    _assert(result.stage in ("schema", "provenance", "isolation"), f"unexpected stage {result.stage}")


def test_isolation_runtime_hook_injection():
    record = fixtures.make_record()
    record["founding_purpose"]["runtime_hook"] = {"on_event": "..."}
    result = validator.validate(record)
    _assert(not result.ok, "runtime hook injection must fail")
    _assert(result.stage in ("schema", "provenance", "isolation"), f"unexpected stage {result.stage}")


def test_integrity_byte_mutation():
    record = fixtures.make_record()
    record["founding_intent"]["statement"] = record["founding_intent"]["statement"] + " (tampered)"
    result = validator.validate(record)
    _assert(not result.ok, "tampered content must fail")
    _assert(result.stage in ("provenance", "integrity"), f"unexpected stage {result.stage}")


def test_integrity_digest_mismatch():
    record = fixtures.make_record()
    record["integrity_metadata"]["digest"] = "f" * 64
    result = validator.validate(record)
    _assert(not result.ok, "digest mismatch must fail")
    _assert(result.stage == "integrity", f"stage should be integrity, got {result.stage}")


def test_integrity_lineage_corruption():
    record = fixtures.make_record()
    ledger, anchored = fixtures.make_ledger(record)
    anchored["integrity_metadata"]["previous_digest"] = "ab" * 32
    result = validator.validate(anchored, ledger_rows=ledger)
    _assert(not result.ok, "lineage break must fail")
    _assert(result.stage == "integrity", f"stage should be integrity, got {result.stage}")


def test_pipeline_safety_stops_on_first_failure():
    executed = []
    record = fixtures.make_record()
    record["founding_intent"]["statement"] = record["founding_intent"]["statement"] + " (tampered)"
    result = validator.validate(
        record, on_stage=executed.append
    )
    _assert(not result.ok, "pipeline must fail")
    _assert(executed[-1] == result.stage, "failure stage must be the last executed stage")
    _assert(executed[-1] != "integrity", "later validators must not all run")
    _assert(
        result.stage in ("schema", "provenance", "isolation"),
        f"tamper should fail before integrity, got {result.stage}",
    )


def test_pipeline_safety_no_state_survives_failure():
    record = fixtures.make_record()
    before = json.dumps(record, sort_keys=True)
    record["founder_confirmation"]["identity"] = "attacker"
    result = validator.validate(record)
    _assert(not result.ok, "mutated confirmation must fail")
    after = json.dumps(record, sort_keys=True)
    _assert(before != after, "fixture mutation must be visible before restore")
    record["founder_confirmation"]["identity"] = "Andy"
    restored = json.dumps(record, sort_keys=True)
    _assert(before == restored, "no persistent state may survive failed validation")
    result_again = validator.validate(record)
    _assert(result_again.ok, "restored record must validate cleanly")


def test_authority_origin_injection():
    record = fixtures.make_record()
    facade = sys.modules.get("maya_identity.origin")
    _assert(facade is not None, "origin facade must import")
    for forbidden in ("inject", "drive", "command", "dispatch"):
        _assert(not hasattr(facade, forbidden), f"facade must expose no {forbidden} API")
    _assert(hasattr(facade, "verify"), "facade must expose read-only verify")


def test_authority_no_runtime_import_path():
    script = (
        "import sys; sys.path.insert(0, r'%s'); "
        "import maya_runtime.core; "
        "assert 'maya_identity.origin' not in sys.modules, 'runtime imported origin'"
    ) % str(_REPO_ROOT)
    completed = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True
    )
    _assert(
        completed.returncode == 0,
        f"runtime must not import origin: {completed.stderr.strip()}",
    )


def test_authority_origin_does_not_import_identity():
    allowed = {
        "maya_identity.origin",
        "maya_identity.origin.activation",
        "maya_identity.origin.integrity",
        "maya_identity.origin.serializer",
        "maya_identity.origin.validator",
    }
    script = (
        "import sys; sys.path.insert(0, r'%s'); "
        "import maya_identity.identity; "
        "baseline = {m for m in sys.modules if m.startswith('maya_identity.' )}; "
        "import maya_identity.origin; "
        "after = {m for m in sys.modules if m.startswith('maya_identity.' )}; "
        "expected = set(%r); "
        "extra = (after - baseline) - expected; "
        "assert not extra, 'origin pulled extra modules: %%s' %% sorted(extra)"
    ) % (str(_REPO_ROOT), sorted(allowed))
    completed = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True
    )
    _assert(
        completed.returncode == 0,
        f"origin must not import identity authority: {completed.stderr.strip()}",
    )


def test_authority_philosophy_promotion_rejected():
    record = fixtures.make_record()
    record["founder_philosophy"]["kind"] = "behavior_rule"
    result = validator.validate(record)
    _assert(not result.ok, "philosophy promotion must fail")
    _assert(result.stage == "schema" or result.stage == "isolation", f"got {result.stage}")


def test_authority_constraint_escalation_rejected():
    record = fixtures.make_record()
    record["protected_constraints"]["grants"] = {"elevate": True}
    result = validator.validate(record)
    _assert(not result.ok, "constraint escalation must fail")


def test_authority_identity_confusion_isolated():
    record = fixtures.make_record(state="INTEGRITY_REGISTERED")
    ledger, anchored = fixtures.make_ledger(record)
    result = activation.advance(anchored, ledger_rows=ledger, approvals=None)
    _assert(not result.ok, "ACTIVATED without approval must fail")
    _assert("approval" in " ".join(result.errors).lower(), "approval must be required")


def test_canonical_bytes_deterministic():
    record = fixtures.make_record()
    first = serializer.canonical_bytes(record)
    reordered = dict(sorted(record.items()))
    second = serializer.canonical_bytes(reordered)
    _assert(first == second, "canonical bytes must not depend on insertion order")
    _assert(first.endswith(b"\n"), "canonical bytes must end with newline")
    return first


def test_digest_deterministic():
    record = fixtures.make_record()
    from maya_identity.origin import integrity

    d2 = integrity.compute_content_digest(record)
    _assert(isinstance(d2, str) and len(d2) == 64, "digest must be 64 hex chars")
    _assert(d2 == record["integrity_metadata"]["digest"], "fixture digest must self-verify")
    _assert(d2 == integrity.compute_content_digest(dict(record.items())), "digest must be stable")


def test_oracle_independent_single_source():
    record = fixtures.make_record()
    verdict = oracle_origin.verify_record(record)
    _assert(verdict["ok"], f"oracle must pass a valid record: {verdict['problems']}")
    ledger, anchored = fixtures.make_ledger(record)
    verdict_ledger = oracle_origin.verify_record(anchored, ledger_rows=ledger)
    _assert(verdict_ledger["ok"], f"oracle must pass anchored record: {verdict_ledger['problems']}")


def test_digest_determinism_cross_implementation():
    record = fixtures.make_record()
    from maya_identity.origin import integrity

    serializer_digest = integrity.compute_content_digest(record)
    oracle_digest = oracle_origin.oracle_digest(record)
    _assert(serializer_digest == oracle_digest, "serializer and oracle digests must agree")


TESTS = (
    test_provenance_missing_confirmation,
    test_provenance_invalid_confirmation,
    test_provenance_altered_confirmation,
    test_isolation_directive_injection,
    test_isolation_capability_injection,
    test_isolation_runtime_hook_injection,
    test_integrity_byte_mutation,
    test_integrity_digest_mismatch,
    test_integrity_lineage_corruption,
    test_pipeline_safety_stops_on_first_failure,
    test_pipeline_safety_no_state_survives_failure,
    test_authority_origin_injection,
    test_authority_no_runtime_import_path,
    test_authority_origin_does_not_import_identity,
    test_authority_philosophy_promotion_rejected,
    test_authority_constraint_escalation_rejected,
    test_authority_identity_confusion_isolated,
    test_canonical_bytes_deterministic,
    test_digest_deterministic,
    test_oracle_independent_single_source,
    test_digest_determinism_cross_implementation,
)


def run() -> int:
    passed = 0
    failed = []
    for test in TESTS:
        name = test.__name__
        try:
            test()
            passed += 1
            print(f"PASS {name}")
        except Exception as exc:  # noqa: BLE001
            failed.append((name, exc))
            print(f"FAIL {name}: {exc}")
    print()
    print(f"origin suite: {passed}/{len(TESTS)} passed")
    if failed:
        print("FAILED:", ", ".join(name for name, _ in failed))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(run())
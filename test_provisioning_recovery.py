"""Provisioning-recovery verification suite.

Proves that Maya can recover a declared-but-missing dependency *without ever
weakening the trust gate*:

- provisioning is default-deny (no validated provider record -> refused) and
  owner-confirmed (an exact capability+dependency token is required; a wrong
  token runs nothing and writes nothing);
- ``execute`` defaults to ``False`` (a read-only plan), and "execution"
  without a runner is refused;
- with the trusted provider record present and an injected sandbox runner, the
  missing module is installed and re-probed, so the record transitions
  ``unavailable -> available``;
- a dependent provider whose availability probe was failing recovers to
  ``available`` after the dependency is provisioned, and only then does
  ``authorize`` allow its action;
- the same ``signal_integrity`` gate that the frequency layer adds refuses a
  noisy-evidence record and admits a coherent periodic one.

Everything runs against temporary registries and a sandbox directory; the
real registry and action log are byte-compared and never written.
"""
from __future__ import annotations

import math
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT))

import maya_provisioning as provisioning
import maya_trust as trust


def _ok(label: str) -> None:
    print(label + " =OK")


def _lcg(seed: int, n: int):
    x = seed
    out = []
    for _ in range(n):
        x = (1103515245 * x + 12345) % (2 ** 31)
        out.append(x / 2 ** 31)
    return out


SINE_P8 = [math.sin(2 * math.pi * k / 8) for k in range(16)]
NOISE = _lcg(7, 128)

_tmp = Path(tempfile.mkdtemp())
REGISTRY = _tmp / "trust.jsonl"
ACTIONS = _tmp / "actions.jsonl"
SANDBOX = _tmp / "sandbox"
SANDBOX.mkdir()
trust.set_clock(lambda: 1234.0)

DEP = "maya_demo_spectral_backend"
DEP2 = "maya_demo_frequency_index"
TOKEN = provisioning.confirmation_token(DEP)
TOKEN2 = provisioning.confirmation_token(DEP2)


def _read(path: Path):
    return path.read_bytes() if path.exists() else None


def _sizes():
    return (_read(REGISTRY), _read(ACTIONS))


def _runner(descriptor):
    module = descriptor["module"]
    (SANDBOX / (module + ".py")).write_text("VALUE = 1\n", encoding="utf-8")
    if str(SANDBOX) not in sys.path:
        sys.path.insert(0, str(SANDBOX))
    return {"installed": module}


# ---- 1. read-only plan and allowlist --------------------------------------

_before = _sizes()
plan = provisioning.plan(DEP)
assert plan["known"] is True and plan["missing"] is True
assert plan["manager"] in provisioning.MANAGERS
assert plan["confirmation_token"] == TOKEN
assert provisioning.plan("not_a_dependency")["known"] is False
assert provisioning.import_available("maya_demo_spectral_backend") is False
assert _sizes() == _before
_ok("provisioning_plan_read_only")

# ---- 2. default deny: no record, no execution -----------------------------

refused = provisioning.provision(
    DEP, confirmation=TOKEN, execute=True, runner=_runner,
    registry_path=REGISTRY, action_log=ACTIONS)
assert refused["status"] == provisioning.STATUS_REFUSED
assert refused["executed"] is False
assert refused["authorization"]["verdict"] == "refused"
assert not any(SANDBOX.iterdir())
_ok("provisioning_default_deny")

# ---- 3. owner confirmation is mandatory and side-effect free --------------

_pre_confirm = _sizes()
_wrong = provisioning.provision(DEP, confirmation="provision:wrong",
                                execute=True, runner=_runner,
                                registry_path=REGISTRY, action_log=ACTIONS)
assert _wrong["status"] == provisioning.STATUS_CONFIRMATION
assert _wrong["executed"] is False
_missing = provisioning.provision(DEP, execute=True, runner=_runner,
                                  registry_path=REGISTRY, action_log=ACTIONS)
assert _missing["status"] == provisioning.STATUS_CONFIRMATION
assert not any(SANDBOX.iterdir())
assert _sizes() == _pre_confirm
_ok("provisioning_confirmation_enforced")

# Unknown dependencies are refused before the confirmation gate.
_unknown = provisioning.provision("maya_evil", confirmation="provision:x:y",
                                  execute=True, runner=_runner,
                                  registry_path=REGISTRY, action_log=ACTIONS)
assert _unknown["status"] == provisioning.STATUS_UNKNOWN
assert not any(SANDBOX.iterdir())
_ok("provisioning_allowlist_enforced")

# ---- 4. register the provisioning provider (explicit trust) ---------------

stored = provisioning.register_provisioning_provider(
    registry_path=REGISTRY, action_log=ACTIONS)
assert stored["status"] == trust.AVAILABLE
assert stored["verification"]["supported"] is True
assert stored["capability"] == provisioning.CAPABILITY
_ok("provisioning_provider_registered")

# ---- 5. prepared (not executed), then runner required ---------------------

prepared = provisioning.provision(DEP, confirmation=TOKEN,
                                  registry_path=REGISTRY,
                                  action_log=ACTIONS)
assert prepared["status"] == provisioning.STATUS_PREPARED
assert prepared["executed"] is False
assert prepared["available_before"] is False
_no_runner = provisioning.provision(DEP, confirmation=TOKEN, execute=True,
                                    registry_path=REGISTRY,
                                    action_log=ACTIONS)
assert _no_runner["status"] == provisioning.STATUS_RUNNER
assert not any(SANDBOX.iterdir())
_ok("provisioning_prepared_then_runner_required")

# ---- 6. install the dependency through the sandbox runner -----------------

installed = provisioning.provision(DEP, confirmation=TOKEN, execute=True,
                                   runner=_runner, registry_path=REGISTRY,
                                   action_log=ACTIONS)
assert installed["status"] == provisioning.STATUS_INSTALLED
assert installed["executed"] is True
assert installed["available_before"] is False
assert installed["available_after"] is True
assert provisioning.import_available("maya_demo_spectral_backend") is True
assert (SANDBOX / "maya_demo_spectral_backend.py").exists()
assert installed["authorization"]["verdict"] == "allowed"
_ok("provisioning_installs_missing_dependency")

_repeat = provisioning.provision(DEP, confirmation=TOKEN, execute=True,
                                 runner=_runner, registry_path=REGISTRY,
                                 action_log=ACTIONS)
assert _repeat["status"] == provisioning.STATUS_ALREADY
assert _repeat["executed"] is False
_ok("provisioning_idempotent_when_present")

# ---- 7. dependent record recovers unavailable -> available ----------------

def _dependent_record(capability, provider):
    return {
        "capability": capability,
        "provider": provider,
        "context": "personal",
        "permissions": {"read_status": True},
        "actions": ("read_status",),
        "trust_basis": ["dependent on provisioned dependency"],
        "identity": {"provider": provider, "version": "1",
                     "source_digest": None},
        "auth": {"method": "local", "state": "valid"},
        "boundaries": {"input": "project", "output": "project",
                       "cross_context_denied": True},
        "result_confirmation": {"supported": True, "method": "digest"},
        "failure": {"fail_closed": True},
    }


dependent = _dependent_record("frequency_index", "frequency_index_provider")
blocked = provisioning.revalidate_dependent(dependent, available=False,
                                            registry_path=REGISTRY,
                                            action_log=ACTIONS)
assert blocked["status"] == trust.UNAVAILABLE
_denied = trust.authorize("frequency_index", "read_status", "personal",
                          path=REGISTRY, action_log=ACTIONS)
assert _denied["verdict"] == "refused"
_ok("dependent_unavailable_until_provisioned")

recovered = provisioning.provision(DEP2, confirmation=TOKEN2, execute=True,
                                   runner=_runner, registry_path=REGISTRY,
                                   action_log=ACTIONS,
                                   dependent_record=dependent)
assert recovered["status"] == provisioning.STATUS_INSTALLED
assert recovered["dependent"]["status"] == trust.AVAILABLE
assert recovered["dependent"]["supported"] is True
_allowed = trust.authorize("frequency_index", "read_status", "personal",
                           path=REGISTRY, action_log=ACTIONS)
assert _allowed["verdict"] == "allowed", _allowed
_ok("dependent_recovers_after_provisioning")

# ---- 8. the spectral gate composes with provisioning trust ----------------

def _signal_record(capability, signal):
    record = _dependent_record(capability, capability + "_provider")
    record["signal"] = signal
    return record


_clean = trust.refresh(_signal_record("spectral_backend", SINE_P8),
                       probe={"available": True}, path=REGISTRY)
assert _clean["status"] == trust.AVAILABLE
_clean_decision = trust.authorize("spectral_backend", "read_status",
                                  "personal", path=REGISTRY,
                                  action_log=ACTIONS)
assert _clean_decision["verdict"] == "allowed"
_noisy = trust.refresh(_signal_record("noisy_backend", NOISE),
                       probe={"available": True}, path=REGISTRY)
assert _noisy["status"] == trust.UNTRUSTED
_noisy_decision = trust.authorize("noisy_backend", "read_status", "personal",
                                  path=REGISTRY, action_log=ACTIONS)
assert _noisy_decision["verdict"] == "refused"
_ok("provisioning_composes_with_signal_gate")

# ---- 9. real registry and action log untouched ----------------------------

_real_registry = _read(trust.TRUST_FILE)
_real_actions = _read(trust.ACTION_LOG)
trust.authorize("frequency_index", "read_status", "personal",
                path=REGISTRY, action_log=ACTIONS)
assert _read(trust.TRUST_FILE) == _real_registry
assert _read(trust.ACTION_LOG) == _real_actions
_ok("provisioning_real_state_untouched")

# A refused provisioning attempt leaves the temporary registry untouched too.
_snapshot = _read(REGISTRY)
provisioning.provision(DEP, confirmation="bad", execute=True, runner=_runner,
                       registry_path=REGISTRY, action_log=ACTIONS)
assert _read(REGISTRY) == _snapshot
_ok("provisioning_refusal_no_write")

print("test_provisioning_recovery=PASS")

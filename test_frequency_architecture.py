"""Frequency architectural layer verification suite.

Proves that the architectural frequency layer (``maya_math.spectral`` ->
``maya_frequency`` -> ``MathAgent`` / ``PatternAlignment`` -> the trust
validation battery) is deterministic, bounded, fail-closed, and strictly
additive:

- the pure substrate provides a correct radix-2 FFT, a bounded [0, 1]
  autocorrelation periodicity, a finite SNR, a Haar energy profile, and a
  spectral alignment, with corrupt input raising at the boundary;
- the frequency layer converts a series into a structured report and a
  fail-closed quality gate (positive SNR *and* non-trivial periodicity *and*
  bounded noise);
- the math coordinator and its runtime facade expose the same vocabulary;
- a record's declared spectral evidence becomes a ``signal_integrity`` trust
  check that fails closed on noisy evidence and is *not applicable* — and
  therefore passing — when no signal is declared.
"""
from __future__ import annotations

import math
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT))

import maya_frequency as frequency
import maya_trust as trust
from maya_math import spectral
from maya_runtime.pattern_alignment import PATTERN_ALIGNMENT


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
SINE_P4 = [math.sin(2 * math.pi * k / 4) for k in range(16)]
ALTERNATING = [1.0 if k % 2 == 0 else -1.0 for k in range(16)]
NOISE = _lcg(7, 128)

# ---- 1. pure substrate primitives -----------------------------------------

assert spectral.is_power_of_two(1) and spectral.is_power_of_two(16)
assert not spectral.is_power_of_two(0) and not spectral.is_power_of_two(12)
assert not spectral.is_power_of_two(True)
assert spectral.next_power_of_two(1) == 1
assert spectral.next_power_of_two(13) == 16
assert spectral.next_power_of_two(16) == 16
_ok("spectral_power_of_two")

for bad in (None, [], "text", [1.0, float("nan")], [True, 1.0], [object()]):
    try:
        spectral.clean_samples(bad)
    except ValueError:
        pass
    else:
        raise AssertionError(f"clean_samples accepted {bad!r}")
assert spectral.clean_samples([1, 2.5, 3]) == [1.0, 2.5, 3.0]
_ok("spectral_clean_samples_fail_closed")

_ok("spectral_fft_known_tone"
    if spectral.dominant_frequency(SINE_P8)["frequency"] == 0.125
    else (_ for _ in ()).throw(AssertionError("wrong dominant frequency")))

# Parseval: sum of squared Haar bands equals the signal energy.
_energy = sum(v * v for v in SINE_P8)
_haar = spectral.haar_energy(SINE_P8)
assert abs((_haar["approximation"] + sum(_haar["details"])) - _energy) < 1e-9
assert _haar["levels"] == 4
_ok("spectral_haar_parseval")

# ---- 2. bounded, deterministic statistics ---------------------------------

assert abs(spectral.periodicity_score(SINE_P8) - 1.0) < 1e-9
assert spectral.periodicity_score([3.0] * 16) == 0.0
assert spectral.periodicity_score([0.5 * k for k in range(16)]) == 0.0
assert spectral.periodicity_score(NOISE) < 0.2
for series in (SINE_P8, ALTERNATING, NOISE, [0.5 * k for k in range(16)]):
    per = spectral.periodicity_score(series)
    snr = spectral.snr_db(series)
    ratio = spectral.noise_ratio(series)
    assert 0.0 <= per <= 1.0, per
    assert 0.0 <= ratio <= 1.0, ratio
    assert abs((per + ratio) - 1.0) < 1e-9
    assert math.isfinite(snr), snr
    assert spectral.spectral_invariants(series)["ok"] is True
_ok("spectral_scores_bounded")
_ok("spectral_invariants_hold")

if not spectral.snr_db(NOISE) < spectral.snr_db(SINE_P8):
    raise AssertionError("SNR did not separate noise from tone")
_ok("spectral_snr_separates_noise")

# Determinism: identical inputs yield identical output.
assert spectral.classify_spectrum(SINE_P8) == spectral.classify_spectrum(SINE_P8)
_ok("spectral_deterministic")

# ---- 3. classification ----------------------------------------------------

assert spectral.classify_spectrum([3.0] * 16)["class"] == "constant"
assert spectral.classify_spectrum([0.5 * k - 3 for k in range(16)])["class"] == "trend"
assert spectral.classify_spectrum(SINE_P4)["class"] == "periodic"
assert spectral.classify_spectrum(ALTERNATING)["class"] == "periodic"
assert spectral.classify_spectrum(NOISE)["class"] == "noise"
_twofreq = [math.sin(2 * math.pi * k / 8)
            + 0.6 * math.sin(2 * math.pi * 3 * k / 16) for k in range(16)]
assert spectral.classify_spectrum(_twofreq)["class"] == "mixed"
assert spectral.classify_spectrum("bad")["class"] == "invalid"
assert spectral.classify_spectrum("bad")["ok"] is False
_ok("spectral_classification")

# ---- 4. alignment ---------------------------------------------------------

assert abs(spectral.spectral_alignment(SINE_P8, SINE_P8) - 1.0) < 1e-9
assert spectral.spectral_alignment(SINE_P8, SINE_P4) < 1e-9
assert spectral.spectral_alignment([3.0] * 16, SINE_P8) == 0.0
_ok("spectral_alignment")

# ---- 5. architectural frequency layer -------------------------------------

report = frequency.analyze(SINE_P8, sample_rate=8.0)
assert report["ok"] is True and report["class"] == "periodic"
assert abs(report["dominant_frequency"] - 1.0) < 1e-9
assert report["samples"] == 16 and report["sample_rate"] == 8.0
_bad = frequency.analyze("nope")
assert _bad["ok"] is False and _bad["class"] == "invalid"
_ok("frequency_analyze")

_good = frequency.signal_quality(SINE_P8)
assert _good["ok"] is True and _good["reason"] is None
_noisy = frequency.signal_quality(NOISE)
assert _noisy["ok"] is False and _noisy["reason"] == frequency.REASON_LOW_SNR
_short = frequency.signal_quality([1.0, 2.0])
assert _short["ok"] is False and _short["reason"] == frequency.REASON_TOO_FEW
assert frequency.signal_quality("bad")["reason"] == frequency.REASON_INVALID
_ok("frequency_quality_gate")

_strict = frequency.signal_quality(_twofreq, max_noise=0.4)
assert _strict["ok"] is False and _strict["reason"] == frequency.REASON_NOISE
_refined = frequency.refine_snr(SINE_P8)
assert _refined["ok"] is True and _refined["margin_db"] > 0.0
assert frequency.refine_snr(NOISE)["ok"] is False
_ok("frequency_thresholds_and_refine")

assert abs(frequency.alignment(SINE_P8, SINE_P8) - 1.0) < 1e-9
assert frequency.alignment(SINE_P8, "bad") == 0.0
assert frequency.frequency_profile(SINE_P8)["haar"]["levels"] == 4
_ok("frequency_alignment_and_profile")

# ---- 6. coordinator / runtime facade --------------------------------------

_agent_report = PATTERN_ALIGNMENT.spectral(SINE_P8)
assert _agent_report["class"] == "periodic"
assert PATTERN_ALIGNMENT.periodicity(SINE_P8) == 1.0
assert PATTERN_ALIGNMENT.periodicity("bad") == 0.0
assert PATTERN_ALIGNMENT.signal_quality(NOISE)["ok"] is False
assert abs(PATTERN_ALIGNMENT.spectral_alignment(SINE_P8, SINE_P8) - 1.0) < 1e-9
_ok("pattern_alignment_spectral_facade")

from maya_identity.wireframe.math_coordinator import MATH_AGENT  # noqa: E402

assert MATH_AGENT.spectral_analysis(SINE_P8)["class"] == "periodic"
assert MATH_AGENT.signal_to_noise(SINE_P8)["ok"] is True
assert MATH_AGENT.spectral_alignment(SINE_P8, ALTERNATING) >= 0.0
_ok("math_agent_spectral_methods")

# ---- 7. trust signal_integrity (strictly additive) ------------------------

_tmp = Path(tempfile.mkdtemp())
_REGISTRY = _tmp / "trust.jsonl"
_ACTIONS = _tmp / "actions.jsonl"
trust.set_clock(lambda: 1234.0)


def _record(capability, signal_key=None, signal=None):
    record = {
        "capability": capability,
        "provider": capability + "_provider",
        "context": "personal",
        "permissions": {"read_status": True},
        "actions": ("read_status",),
        "trust_basis": ["frequency suite"],
        "identity": {"provider": capability + "_provider", "version": "1",
                     "source_digest": None},
        "auth": {"method": "local", "state": "valid"},
        "boundaries": {"input": "project", "output": "project",
                       "cross_context_denied": True},
        "result_confirmation": {"supported": True, "method": "digest"},
        "failure": {"fail_closed": True},
    }
    if signal_key is not None:
        record[signal_key] = signal
    return record


_plain = trust.refresh(_record("freq_plain"), probe={"available": True},
                       path=_REGISTRY)
assert _plain["status"] == trust.AVAILABLE
_names = [c["name"] for c in _plain["verification"]["checks"]]
assert "signal_integrity" in _names
_signal_check = [c for c in _plain["verification"]["checks"]
                 if c["name"] == "signal_integrity"][0]
assert _signal_check["ok"] is True and _signal_check["detail"] == ""
_ok("trust_signal_not_applicable_passes")

_clean = trust.refresh(_record("freq_clean", "signal", SINE_P8),
                       probe={"available": True}, path=_REGISTRY)
assert _clean["status"] == trust.AVAILABLE
assert _clean["verification"]["supported"] is True
_ok("trust_clean_signal_available")

_noisy_record = trust.refresh(_record("freq_noisy", "signal", NOISE),
                              probe={"available": True}, path=_REGISTRY)
assert _noisy_record["status"] == trust.UNTRUSTED
assert _noisy_record["verification"]["supported"] is False
_noisy_check = [c for c in _noisy_record["verification"]["checks"]
                if c["name"] == "signal_integrity"][0]
assert _noisy_check["ok"] is False
assert "spectral evidence insufficient" in _noisy_check["detail"]
_ok("trust_noisy_signal_untrusted")

_block = trust.refresh(
    _record("freq_block", "signal", SINE_P8) | {
        "frequency": {"signal": SINE_P8, "min_snr_db": 3.0,
                      "min_periodicity": 0.2, "max_noise": 0.4}},
    probe={"available": True}, path=_REGISTRY)
assert _block["status"] == trust.AVAILABLE
_malformed = trust.refresh(_record("freq_malformed", "signal", ["a", "b", 1, 2]),
                           probe={"available": True}, path=_REGISTRY)
assert _malformed["status"] == trust.UNTRUSTED
_ok("trust_signal_config_and_malformed")

# The action vocabulary now admits the provisioning action; unknown actions
# still fail closed.
assert "install_dependency" in trust.ACTION_VOCABULARY
_unknown = trust.refresh(_record("freq_unknown") | {
    "permissions": {"smuggle_billing": True}, "actions": ("smuggle_billing",)},
    probe={"available": True}, path=_REGISTRY)
assert _unknown["status"] == trust.UNTRUSTED
_ok("trust_action_vocabulary_extended")

print("test_frequency_architecture=PASS")

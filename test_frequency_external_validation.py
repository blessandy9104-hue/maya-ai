"""External verification of the frequency layer against a clean-room oracle.

``verification/frequency_dataset.json`` holds static signal cases and the
clean-room ``verification/oracle_frequency.py`` re-derives every salient
spectral quantity with an independent naive O(N^2) DFT (the substrate uses an
iterative radix-2 FFT). Because every dataset signal has a power-of-two
length, both transforms produce identical bins, so the two implementations
must agree to machine precision. Agreement is therefore real evidence, not a
self-consistent mirror.

Every case also pins its expected spectral class, which is checked against
*three* independent paths: the substrate classifier, the oracle classifier,
and the architectural frequency report.
"""
from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT))

from maya_math import spectral
import maya_frequency as frequency

_DATASET = _ROOT / "verification" / "frequency_dataset.json"
_ORACLE_PATH = _ROOT / "verification" / "oracle_frequency.py"
_TOL = 1e-9


def _ok(label: str) -> None:
    print(label + " =OK")


def _load_oracle():
    spec = importlib.util.spec_from_file_location("oracle_frequency",
                                                  _ORACLE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


oracle = _load_oracle()

# ---- 1. dataset shape -----------------------------------------------------

with _DATASET.open("r", encoding="utf-8") as handle:
    dataset = json.load(handle)
assert dataset["schema"] == "maya/verification/frequency-dataset/1.0.0"
cases = dataset["cases"]
assert len(cases) >= 10
_ids = [case["id"] for case in cases]
assert len(set(_ids)) == len(_ids)
for case in cases:
    assert spectral.is_power_of_two(len(case["signal"])), case["id"]
    assert case["expect_class"] in spectral.CLASSES
_ok("frequency_dataset_shape")

# ---- 2. oracle purity (clean room) ----------------------------------------

_source = _ORACLE_PATH.read_text(encoding="utf-8")
assert "import maya_math" not in _source
assert "import maya_frequency" not in _source
assert "from maya_math" not in _source
assert "from maya_frequency" not in _source
for bad in (None, [], [float("inf")], [True]):
    try:
        oracle.clean(bad)
    except ValueError:
        pass
    else:
        raise AssertionError(f"oracle accepted {bad!r}")
_ok("frequency_oracle_clean_room")

# ---- 3. per-case substrate vs oracle agreement ----------------------------

_checked = 0
for case in cases:
    signal = case["signal"]
    rate = case["sample_rate"]
    report = frequency.analyze(signal, rate)
    assert report["ok"] is True, case["id"]

    pairs = (
        ("dominant_frequency",
         report["dominant_frequency"],
         oracle.dominant_frequency(signal, rate)),
        ("periodicity",
         report["periodicity"],
         oracle.periodicity(signal)),
        ("snr_db", report["snr_db"], oracle.snr_db(signal)),
        ("noise_ratio",
         report["noise_ratio"],
         oracle.noise_ratio(signal)),
        ("spectral_centroid",
         report["spectral_centroid"],
         oracle.spectral_centroid(signal, rate)),
    )
    for name, substrate_value, oracle_value in pairs:
        if not math.isfinite(substrate_value):
            raise AssertionError(f"{case['id']}: {name} not finite")
        if abs(substrate_value - oracle_value) > _TOL:
            raise AssertionError(
                f"{case['id']}: {name} substrate={substrate_value!r} "
                f"oracle={oracle_value!r}")
    _checked += 1
assert _checked == len(cases)
_ok("frequency_oracle_agreement")

# ---- 4. class agreement across all three paths ----------------------------

for case in cases:
    signal = case["signal"]
    expected = case["expect_class"]
    substrate_class = spectral.classify_spectrum(signal)["class"]
    oracle_class = oracle.classify(signal)
    report_class = frequency.analyze(signal, case["sample_rate"])["class"]
    assert substrate_class == expected, (case["id"], substrate_class, expected)
    assert oracle_class == expected, (case["id"], oracle_class, expected)
    assert report_class == expected, (case["id"], report_class, expected)
_ok("frequency_class_agreement")

# ---- 5. quality gate agrees with the declared expectation -----------------

for case in cases:
    quality = frequency.signal_quality(
        case["signal"], min_snr_db=case["min_snr_db"],
        min_periodicity=case["min_periodicity"], max_noise=case["max_noise"],
        sample_rate=case["sample_rate"])
    assert bool(quality["ok"]) == bool(case["expect_quality"]), (
        case["id"], quality["reason"])
_ok("frequency_quality_expectations")

# ---- 6. determinism across the whole corpus -------------------------------

for case in cases:
    first = frequency.analyze(case["signal"], case["sample_rate"])
    second = frequency.analyze(case["signal"], case["sample_rate"])
    assert first == second, case["id"]
_ok("frequency_corpus_deterministic")

print("test_frequency_external_validation=PASS")

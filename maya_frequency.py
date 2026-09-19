"""Architectural frequency layer: spectral evidence for the trust gate.

Maya reasons about time-varying observations — provider availability,
resource pressure, latency traces, motion and world-feature sequences. This
module turns such a series into an explicit, structured spectral verdict the
rest of the architecture can quote:

- :func:`analyze` — a deterministic frequency report (class, dominant
  frequency, SNR, periodicity, noise ratio, noise floor, centroid);
- :func:`signal_quality` — the fail-closed gate: does this observation carry
  enough coherent periodic content to be trusted as a real signal, or is it
  broadband noise (or corrupt input) that must not be?
- :func:`refine_snr` — a focused SNR refinement with its margin;
- :func:`alignment` — spectral agreement between two observations.

The layer is a thin, pure adapter over :mod:`maya_math.spectral`; it holds no
state, reads no clock, and never touches the network. Everything it reports is
derived from the samples it was handed, so a caller can re-derive it.

Defaults are deliberately conservative: a signal must clear a positive SNR
*and* a non-trivial periodicity *and* keep its residual noise below the cap.
Failing any of the three is a refusal, never a pass.
"""
from __future__ import annotations

from maya_math import spectral as _spectral

SCHEMA = "maya/frequency/1.0.0"

DEFAULT_MIN_SNR_DB = 3.0
DEFAULT_MIN_PERIODICITY = 0.2
DEFAULT_MAX_NOISE = 0.5
DEFAULT_MIN_SAMPLES = 4

REASON_INVALID = "invalid_signal"
REASON_TOO_FEW = "too_few_samples"
REASON_LOW_SNR = "low_snr"
REASON_LOW_PERIODICITY = "low_periodicity"
REASON_NOISE = "noise_floor_exceeded"
REASONS = (REASON_INVALID, REASON_TOO_FEW, REASON_LOW_SNR,
           REASON_LOW_PERIODICITY, REASON_NOISE)


def _metrics(signal, sample_rate):
    """The raw spectral metrics, raising ``ValueError`` on corrupt input."""
    samples = _spectral.clean_samples(signal)
    dominant = _spectral.dominant_frequency(samples, sample_rate)
    classification = _spectral.classify_spectrum(samples)
    return {
        "samples": len(samples),
        "sample_rate": float(sample_rate),
        "class": classification["class"],
        "dominant_frequency": dominant["frequency"],
        "dominant_bin": dominant["bin"],
        "snr_db": classification["snr_db"],
        "periodicity": classification["periodicity"],
        "noise_ratio": classification["noise_ratio"],
        "noise_floor": classification["noise_floor"],
        "spectral_centroid": _spectral.spectral_centroid(samples, sample_rate),
    }


def analyze(signal, sample_rate=1.0):
    """Full frequency report for one observation (fail-closed).

    Corrupt input yields ``ok=False`` with the validation reason rather than
    raising, so an unreadable series can never be optimistically classified.
    """
    try:
        report = _metrics(signal, sample_rate)
    except ValueError as exc:
        return {
            "schema": SCHEMA,
            "ok": False,
            "reason": str(exc),
            "class": "invalid",
            "samples": 0,
            "sample_rate": float(sample_rate),
            "dominant_frequency": 0.0,
            "dominant_bin": 0,
            "snr_db": _spectral.SNR_FLOOR_DB,
            "periodicity": 0.0,
            "noise_ratio": 1.0,
            "noise_floor": 0.0,
            "spectral_centroid": 0.0,
        }
    report["schema"] = SCHEMA
    report["ok"] = True
    report["reason"] = None
    return report


def signal_quality(signal, min_snr_db=DEFAULT_MIN_SNR_DB,
                   min_periodicity=DEFAULT_MIN_PERIODICITY,
                   max_noise=DEFAULT_MAX_NOISE, sample_rate=1.0,
                   min_samples=DEFAULT_MIN_SAMPLES):
    """Fail-closed quality gate for one observation.

    Returns ``{"ok", "reason", "reasons", "metrics"}``. A signal passes only
    when it is readable, long enough, has ``snr_db >= min_snr_db``,
    ``periodicity >= min_periodicity``, and ``noise_ratio <= max_noise``;
    the first failed constraint is reported as ``reason``.
    """
    report = analyze(signal, sample_rate)
    if not report["ok"]:
        return {"ok": False, "reason": REASON_INVALID,
                "reasons": [REASON_INVALID], "detail": report["reason"],
                "metrics": report}
    reasons = []
    if report["samples"] < int(min_samples):
        reasons.append(REASON_TOO_FEW)
    if report["snr_db"] < float(min_snr_db):
        reasons.append(REASON_LOW_SNR)
    if report["periodicity"] < float(min_periodicity):
        reasons.append(REASON_LOW_PERIODICITY)
    if report["noise_ratio"] > float(max_noise):
        reasons.append(REASON_NOISE)
    return {
        "ok": not reasons,
        "reason": reasons[0] if reasons else None,
        "reasons": reasons,
        "detail": None,
        "metrics": report,
    }


def refine_snr(signal, min_snr_db=DEFAULT_MIN_SNR_DB, sample_rate=1.0):
    """SNR refinement with its margin over the required minimum.

    A negative ``margin_db`` means the observation did not clear the bar.
    """
    report = analyze(signal, sample_rate)
    if not report["ok"]:
        return {"ok": False, "reason": REASON_INVALID, "snr_db":
                _spectral.SNR_FLOOR_DB, "min_snr_db": float(min_snr_db),
                "margin_db": _spectral.SNR_FLOOR_DB - float(min_snr_db),
                "metrics": report}
    snr = report["snr_db"]
    return {
        "ok": snr >= float(min_snr_db),
        "reason": None if snr >= float(min_snr_db) else REASON_LOW_SNR,
        "snr_db": snr,
        "min_snr_db": float(min_snr_db),
        "margin_db": snr - float(min_snr_db),
        "metrics": report,
    }


def alignment(left, right):
    """Bounded [0, 1] spectral agreement between two observations."""
    try:
        return _spectral.spectral_alignment(left, right)
    except ValueError:
        return 0.0


def frequency_profile(signal, sample_rate=1.0):
    """Frequency report augmented with the Haar wavelet energy profile."""
    report = analyze(signal, sample_rate)
    if not report["ok"]:
        report["haar"] = {"approximation": 0.0, "details": [], "levels": 0}
        return report
    report["haar"] = _spectral.haar_energy(signal)
    return report

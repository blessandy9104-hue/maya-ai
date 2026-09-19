"""Spectral analysis domain for the Maya mathematical substrate.

A pure, deterministic frequency-domain layer over sampled signals. It gives
every Maya subsystem that reasons about an observed series (availability,
resource pressure, motion, world-feature evolution) the same canonical
vocabulary:

- ``fft`` / ``fft_magnitudes`` / ``power_spectrum`` — radix-2 Cooley-Tukey
  transform, zero-padded to the next power of two so every input length is
  analysable;
- ``dominant_frequency`` — the strongest non-DC component (cycles per sample);
- ``periodicity_score`` — a bounded [0, 1] repetition measure from the
  detrended normalised autocorrelation peak (a smooth trend never reads as
  repetition);
- ``snr_db`` — signal-to-noise ratio of the dominant periodic content against
  the residual power of the detrended signal, in decibels, floored and finite;
- ``noise_ratio`` — the complementary bounded [0, 1] residual fraction;
- ``noise_floor`` / ``spectral_centroid`` — robust band statistics;
- ``haar_energy`` — a one-dimensional Haar wavelet energy profile;
- ``spectral_alignment`` — cosine alignment of two magnitude spectra;
- ``classify_spectrum`` — a deterministic ``constant`` / ``trend`` /
  ``periodic`` / ``noise`` / ``mixed`` label.

Design principles (identical to the rest of the substrate):

- **Pure and deterministic**: standard library only; no wall clock, no
  randomness, no IO. Identical inputs produce identical output.
- **Fail closed**: corrupt input (non-numeric, non-finite, boolean, or empty)
  raises ``ValueError`` at the boundary; the architectural layer converts that
  into an explicit refuse verdict rather than reporting a false result.
- **Bounded**: every reported score is finite and clamped onto its documented
  domain.
"""
from __future__ import annotations

import math

SCHEMA = "maya/math/spectral/1.0.0"

# Below this level a signal has no recoverable periodic content.
SNR_FLOOR_DB = -120.0
# Default number of harmonics that count as "the periodic content" of a signal.
DEFAULT_HARMONICS = 4

CLASS_CONSTANT = "constant"
CLASS_TREND = "trend"
CLASS_PERIODIC = "periodic"
CLASS_NOISE = "noise"
CLASS_MIXED = "mixed"
CLASS_INVALID = "invalid"
CLASSES = (CLASS_CONSTANT, CLASS_TREND, CLASS_PERIODIC, CLASS_NOISE,
           CLASS_MIXED)


def is_power_of_two(value):
    """True only for a positive integer power of two."""
    if isinstance(value, bool):
        return False
    try:
        n = int(value)
    except (TypeError, ValueError):
        return False
    return n > 0 and (n & (n - 1)) == 0


def next_power_of_two(value):
    """Smallest power of two >= ``value`` (at least 1)."""
    n = int(value)
    if n <= 1:
        return 1
    return 1 << (n - 1).bit_length()


def clean_samples(values):
    """Validate and normalise a sampled signal into a list of finite floats.

    Raises ``ValueError`` for ``None``, an empty sequence, booleans,
    non-numeric samples, or any non-finite sample. This is the single
    fail-closed gate every spectral entry point passes through.
    """
    if values is None:
        raise ValueError("spectral analysis requires samples")
    if isinstance(values, (str, bytes)):
        raise ValueError("a signal must be a numeric sequence, not text")
    try:
        items = list(values)
    except TypeError:
        raise ValueError("a signal must be a numeric sequence") from None
    if not items:
        raise ValueError("spectral analysis requires at least one sample")
    out = []
    for value in items:
        if isinstance(value, bool):
            raise ValueError("booleans are not signal samples")
        try:
            f = float(value)
        except (TypeError, ValueError):
            raise ValueError("signal samples must be numeric") from None
        if not math.isfinite(f):
            raise ValueError("signal samples must be finite")
        out.append(f)
    return out


def _fft(values):
    """Iterative radix-2 Cooley-Tukey FFT of a power-of-two real sequence.

    Returns the full complex spectrum. Raises ``ValueError`` when the length
    is not a positive power of two (callers pad first).
    """
    n = len(values)
    if not is_power_of_two(n):
        raise ValueError("fft requires a power-of-two length")
    data = [complex(v) for v in values]
    j = 0
    for i in range(1, n):
        bit = n >> 1
        while j & bit:
            j ^= bit
            bit >>= 1
        j |= bit
        if i < j:
            data[i], data[j] = data[j], data[i]
    length = 2
    while length <= n:
        angle = -2.0 * math.pi / length
        wlen = complex(math.cos(angle), math.sin(angle))
        half = length >> 1
        for start in range(0, n, length):
            w = 1.0 + 0.0j
            for k in range(half):
                u = data[start + k]
                v = data[start + k + half] * w
                data[start + k] = u + v
                data[start + k + half] = u - v
                w *= wlen
        length <<= 1
    return data


def _half_powers(samples):
    """Half-spectrum power of an already-clean signal (internal)."""
    n = next_power_of_two(len(samples))
    spectrum = _fft(samples + [0.0] * (n - len(samples)))
    half = n // 2 + 1
    return [c.real * c.real + c.imag * c.imag for c in spectrum[:half]]


def _detrend(samples):
    """Remove the least-squares linear trend (and thus the mean)."""
    n = len(samples)
    if n < 2:
        return [0.0] * n
    xbar = (n - 1) / 2.0
    ybar = math.fsum(samples) / n
    num = math.fsum((i - xbar) * (samples[i] - ybar) for i in range(n))
    den = math.fsum((i - xbar) ** 2 for i in range(n))
    slope = num / den if den > 0.0 else 0.0
    intercept = ybar - slope * xbar
    return [samples[i] - (slope * i + intercept) for i in range(n)]


def _zero_crossings(sequence):
    """Sign changes of a sequence, ignoring exact-zero samples."""
    crossings = 0
    previous = 0
    for value in sequence:
        if value > 0.0:
            sign = 1
        elif value < 0.0:
            sign = -1
        else:
            continue
        if previous != 0 and sign != previous:
            crossings += 1
        previous = sign
    return crossings


def fft(values):
    """Complex spectrum of a signal, zero-padded to the next power of two."""
    samples = clean_samples(values)
    n = next_power_of_two(len(samples))
    return _fft(samples + [0.0] * (n - len(samples)))


def fft_magnitudes(values):
    """Half-spectrum magnitudes (bins ``0 .. n/2`` inclusive)."""
    return [math.sqrt(p) for p in _half_powers(clean_samples(values))]


def power_spectrum(values):
    """Half-spectrum power (magnitude squared)."""
    return _half_powers(clean_samples(values))


def _peak_bin(powers, harmonics):
    """Strongest non-DC bin and the summed power of its harmonics."""
    half = len(powers)
    if half <= 2:
        return 0, 0.0
    peak = 1
    for b in range(2, half):
        if powers[b] > powers[peak]:
            peak = b
    signal = 0.0
    for k in range(1, max(1, int(harmonics)) + 1):
        b = peak * k
        if b >= half:
            break
        signal += powers[b]
    return peak, signal


def _noise_threshold(magnitudes):
    """Bins below this are numerical noise, not content: 1e-9 of the peak."""
    if not magnitudes:
        return 0.0
    return max(magnitudes) * 1e-9


def dominant_frequency(values, sample_rate=1.0):
    """Strongest non-DC frequency (cycles per ``sample_rate`` unit).

    Returns ``{"frequency", "bin", "magnitude", "normalized"}``; a signal with
    no non-DC content reports frequency 0 and normalized 0. Bins below
    :func:`_noise_threshold` of the peak are treated as absent, so a constant
    signal has no dominant frequency rather than reporting a numerical-noise
    bin.
    """
    samples = clean_samples(values)
    n = next_power_of_two(len(samples))
    magnitudes = [math.sqrt(p) for p in _half_powers(samples)]
    half = len(magnitudes)
    if half <= 2:
        return {"frequency": 0.0, "bin": 0, "magnitude": 0.0,
                "normalized": 0.0}
    threshold = _noise_threshold(magnitudes)
    best_bin = 1
    for b in range(2, half):
        if magnitudes[b] > magnitudes[best_bin]:
            best_bin = b
    magnitude = magnitudes[best_bin]
    if magnitude <= threshold:
        return {"frequency": 0.0, "bin": 0, "magnitude": 0.0,
                "normalized": 0.0}
    total = math.fsum(magnitudes)
    normalized = magnitude / total if total > 0.0 else 0.0
    return {
        "frequency": best_bin * float(sample_rate) / n,
        "bin": best_bin,
        "magnitude": magnitude,
        "normalized": normalized,
    }


def periodicity_score(values):
    """Bounded [0, 1] repetition measure.

    The mean-removed signal is scored by the strongest normalised
    autocorrelation at a *non-trivial local maximum* lag (``2 .. n/2``). A
    signal without at least two mean-crossings is not an oscillation and
    scores 0, so a monotonic drift never reads as repetition; requiring a
    local maximum (rather than the raw best lag) rejects the smooth,
    monotonically-decaying autocorrelation of drift and coloured noise.
    """
    samples = clean_samples(values)
    n = len(samples)
    if n < 4:
        return 0.0
    mean = math.fsum(samples) / n
    centered = [v - mean for v in samples]
    energy = math.fsum(v * v for v in centered)
    if energy <= 1e-15:
        return 0.0
    if _zero_crossings(centered) < 2:
        return 0.0
    max_lag = n // 2
    correlations = [0.0] * (max_lag + 2)
    for lag in range(1, max_lag + 1):
        left = centered[:n - lag]
        right = centered[lag:]
        left_energy = math.fsum(v * v for v in left)
        right_energy = math.fsum(v * v for v in right)
        if left_energy <= 0.0 or right_energy <= 0.0:
            continue
        numerator = math.fsum(a * b for a, b in zip(left, right))
        correlations[lag] = numerator / math.sqrt(left_energy * right_energy)
    best = 0.0
    for lag in range(2, max_lag + 1):
        value = correlations[lag]
        if value <= 0.0:
            continue
        if value < correlations[lag - 1]:
            continue
        if lag + 1 <= max_lag and value < correlations[lag + 1]:
            continue
        if value > best:
            best = value
    return max(0.0, min(1.0, best))


def noise_ratio(values):
    """Bounded [0, 1] residual fraction: ``1 - periodicity_score``."""
    return max(0.0, min(1.0, 1.0 - periodicity_score(values)))


def snr_db(values, harmonics=DEFAULT_HARMONICS):
    """Signal-to-noise ratio (dB) of the periodic content vs. the residual.

    The mean-removed signal is transformed; the periodic content is the power
    at the dominant non-DC bin plus its first ``harmonics`` multiples, and the
    residual is everything else. The result is finite: zero periodic content
    reports :data:`SNR_FLOOR_DB` and a noiseless signal reports
    ``-SNR_FLOOR_DB``.
    """
    samples = clean_samples(values)
    mean = math.fsum(samples) / len(samples)
    powers = _half_powers([v - mean for v in samples])
    total = math.fsum(powers)
    if total <= 0.0:
        return SNR_FLOOR_DB
    _peak, signal = _peak_bin(powers, harmonics)
    if signal <= 0.0:
        return SNR_FLOOR_DB
    noise = total - signal
    if noise <= total * 1e-12:
        noise = total * 1e-12
    value = 10.0 * math.log10(signal / noise)
    if not math.isfinite(value):
        return SNR_FLOOR_DB if value < 0 else -SNR_FLOOR_DB
    return value


def _median(seq):
    ordered = sorted(seq)
    size = len(ordered)
    if size == 0:
        return 0.0
    mid = size // 2
    if size % 2:
        return ordered[mid]
    return 0.5 * (ordered[mid - 1] + ordered[mid])


def noise_floor(values):
    """Robust magnitude floor: median of the non-DC magnitude bins."""
    magnitudes = fft_magnitudes(values)
    band = magnitudes[1:] or [0.0]
    return _median(band)


def spectral_centroid(values, sample_rate=1.0):
    """Magnitude-weighted mean non-DC frequency (a brightness measure)."""
    samples = clean_samples(values)
    n = next_power_of_two(len(samples))
    magnitudes = [math.sqrt(p) for p in _half_powers(samples)]
    threshold = _noise_threshold(magnitudes)
    numerator = 0.0
    denominator = 0.0
    for b in range(1, len(magnitudes)):
        if magnitudes[b] <= threshold:
            continue
        numerator += b * magnitudes[b]
        denominator += magnitudes[b]
    if denominator <= 0.0:
        return 0.0
    return (numerator / denominator) * float(sample_rate) / n


def haar_energy(values):
    """Haar wavelet energy profile of a zero-padded signal.

    Returns ``{"approximation", "details", "levels"}`` where ``details`` lists
    the detail-band energy at each decomposition level (finest first) and
    ``approximation`` is the final scaling-coefficient energy. The total
    across all bands equals the signal energy (Parseval for the orthonormal
    Haar basis).
    """
    samples = clean_samples(values)
    n = next_power_of_two(len(samples))
    data = samples + [0.0] * (n - len(samples))
    details = []
    length = n
    while length >= 2:
        half = length // 2
        approximation = [0.0] * half
        detail = [0.0] * half
        for i in range(half):
            a = data[2 * i]
            b = data[2 * i + 1]
            approximation[i] = (a + b) / math.sqrt(2.0)
            detail[i] = (a - b) / math.sqrt(2.0)
        details.append(math.fsum(d * d for d in detail))
        data = approximation
        length = half
    return {
        "approximation": math.fsum(x * x for x in data),
        "details": details,
        "levels": len(details),
    }


def spectral_alignment(a, b):
    """Cosine alignment of two magnitude spectra, bounded onto [0, 1].

    Both signals are zero-padded to a shared power-of-two length so the
    comparison is dimensionally consistent. A signal with no non-DC content
    carries no direction and scores 0.
    """
    left = clean_samples(a)
    right = clean_samples(b)
    n = next_power_of_two(max(len(left), len(right)))
    ma = _fft(left + [0.0] * (n - len(left)))
    mb = _fft(right + [0.0] * (n - len(right)))
    half = n // 2 + 1
    xa = [abs(ma[i]) for i in range(1, half)]
    xb = [abs(mb[i]) for i in range(1, half)]
    na = math.sqrt(math.fsum(v * v for v in xa))
    nb = math.sqrt(math.fsum(v * v for v in xb))
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    dot = math.fsum(p * q for p, q in zip(xa, xb))
    cosine = dot / (na * nb)
    return max(0.0, min(1.0, cosine))


def spectrum_vector(values, bins=None):
    """Unit-normalised non-DC magnitude vector (DC dropped).

    When ``bins`` is supplied the vector is truncated or zero-padded to that
    exact length, so independently-sourced spectra are directly comparable.
    A zero spectrum returns the zero vector.
    """
    magnitudes = fft_magnitudes(values)
    vector = magnitudes[1:]
    if bins is not None:
        size = max(0, int(bins))
        if len(vector) < size:
            vector = vector + [0.0] * (size - len(vector))
        else:
            vector = vector[:size]
    norm = math.sqrt(math.fsum(v * v for v in vector))
    if norm <= 0.0:
        return tuple(0.0 for _ in vector)
    return tuple(v / norm for v in vector)


def _residual_fraction(samples):
    total = math.fsum((v - math.fsum(samples) / len(samples)) ** 2
                      for v in samples)
    if total <= 0.0:
        return 0.0
    residual = math.fsum(v * v for v in _detrend(samples))
    return max(0.0, min(1.0, residual / total))


def classify_spectrum(values, harmonics=DEFAULT_HARMONICS):
    """Deterministic spectral class with its supporting metrics.

    Fail-closed: corrupt input yields ``ok=False, class="invalid"`` rather
    than raising, so an unreadable signal can never be optimistically
    classified.
    """
    try:
        samples = clean_samples(values)
    except ValueError as exc:
        return {
            "ok": False,
            "class": CLASS_INVALID,
            "reason": str(exc),
            "samples": 0,
            "snr_db": SNR_FLOOR_DB,
            "periodicity": 0.0,
            "noise_ratio": 1.0,
            "noise_floor": 0.0,
            "centroid": 0.0,
        }
    span = max(samples) - min(samples)
    periodicity = periodicity_score(samples)
    snr = snr_db(samples, harmonics)
    if span <= 1e-12:
        label = CLASS_CONSTANT
    elif _residual_fraction(samples) <= 1e-9:
        label = CLASS_TREND
    elif periodicity >= 0.5 and snr >= 6.0:
        label = CLASS_PERIODIC
    elif periodicity < 0.2:
        label = CLASS_NOISE
    else:
        label = CLASS_MIXED
    return {
        "ok": True,
        "class": label,
        "reason": None,
        "samples": len(samples),
        "snr_db": snr,
        "periodicity": periodicity,
        "noise_ratio": max(0.0, min(1.0, 1.0 - periodicity)),
        "noise_floor": noise_floor(samples),
        "centroid": spectral_centroid(samples),
    }


def spectral_invariants(values):
    """Audit the documented invariants for one signal.

    Every score is finite and inside its domain, power is non-negative, and
    periodicity + noise_ratio equals one. Returns ``{"ok", "violations"}``;
    an empty violation list is a proof that the spectral algebra held.
    """
    violations = []
    try:
        samples = clean_samples(values)
    except ValueError as exc:
        return {"ok": False, "violations": [{"rule": "invalid_signal",
                                             "detail": str(exc)}]}
    powers = _half_powers(samples)
    if any(not math.isfinite(p) or p < 0.0 for p in powers):
        violations.append({"rule": "power_not_non_negative"})
    periodicity = periodicity_score(samples)
    noise = noise_ratio(samples)
    snr = snr_db(samples)
    if not 0.0 <= periodicity <= 1.0:
        violations.append({"rule": "periodicity_out_of_domain",
                           "value": periodicity})
    if not 0.0 <= noise <= 1.0:
        violations.append({"rule": "noise_ratio_out_of_domain",
                           "value": noise})
    if abs((periodicity + noise) - 1.0) > 1e-9:
        violations.append({"rule": "periodicity_noise_not_complementary"})
    if not math.isfinite(snr):
        violations.append({"rule": "snr_not_finite", "value": snr})
    return {"ok": not violations, "violations": violations}

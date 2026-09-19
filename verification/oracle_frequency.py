"""Clean-room oracle for the architectural frequency layer.

Independent re-derivation of the spectral quantities used by
:mod:`maya_math.spectral` and :mod:`maya_frequency`, using a *different*
computational method so agreement is real evidence and not a self-consistent
mirror:

- the transform is the naive O(N^2) DFT evaluated directly from the defining
  sums (substrate: an iterative radix-2 Cooley-Tukey FFT);
- dominant frequency, SNR and the noise floor are read off those DFT bins
  rather than an FFT half-spectrum;
- the periodicity measure is re-coded from the definition (mean-removed
  normalised cross-correlation at the strongest non-trivial local maximum)
  with explicit index loops and no shared helpers.

This module imports only the standard library and never imports ``maya_math``
or ``maya_frequency``. Every signal in ``frequency_dataset.json`` has a
power-of-two length, so the DFT bins and the substrate FFT bins coincide and
the two implementations are directly comparable.
"""
from __future__ import annotations

import math

SNR_FLOOR_DB = -120.0
DEFAULT_HARMONICS = 4


def clean(values):
    """Independent validation: finite floats only, non-empty, no booleans."""
    if values is None or isinstance(values, (str, bytes)):
        raise ValueError("oracle requires a numeric sequence")
    items = list(values)
    if not items:
        raise ValueError("oracle requires at least one sample")
    out = []
    for value in items:
        if isinstance(value, bool):
            raise ValueError("boolean sample")
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("non-finite sample")
        out.append(number)
    return out


def next_pow2(n):
    size = 1
    while size < n:
        size *= 2
    return size


def dft(values):
    """Naive O(N^2) DFT of a zero-padded real sequence (full spectrum)."""
    samples = clean(values)
    n = next_pow2(len(samples))
    data = samples + [0.0] * (n - len(samples))
    spectrum = []
    for k in range(n):
        real = 0.0
        imag = 0.0
        for i in range(n):
            angle = -2.0 * math.pi * k * i / n
            real += data[i] * math.cos(angle)
            imag += data[i] * math.sin(angle)
        spectrum.append(complex(real, imag))
    return spectrum


def half_powers(values):
    """Half-spectrum power from the naive DFT."""
    spectrum = dft(values)
    n = len(spectrum)
    half = n // 2 + 1
    return [abs(spectrum[i]) ** 2 for i in range(half)]


def padded_length(values):
    return next_pow2(len(clean(values)))


def _mean(values):
    total = 0.0
    for value in values:
        total += value
    return total / len(values)


def _zero_crossings(values):
    crossings = 0
    previous = 0
    for value in values:
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


def _peak_and_signal(powers, harmonics):
    half = len(powers)
    if half <= 2:
        return 0, 0.0
    peak = 1
    for b in range(2, half):
        if powers[b] > powers[peak]:
            peak = b
    signal = 0.0
    k = 1
    while k <= max(1, int(harmonics)):
        b = peak * k
        if b >= half:
            break
        signal += powers[b]
        k += 1
    return peak, signal


def _noise_threshold(magnitudes):
    if not magnitudes:
        return 0.0
    return max(magnitudes) * 1e-9


def dominant_frequency(values, sample_rate=1.0):
    magnitudes = [math.sqrt(p) for p in half_powers(values)]
    n = padded_length(values)
    half = len(magnitudes)
    if half <= 2:
        return 0.0
    threshold = _noise_threshold(magnitudes)
    best = 1
    for b in range(2, half):
        if magnitudes[b] > magnitudes[best]:
            best = b
    if magnitudes[best] <= threshold:
        return 0.0
    return best * float(sample_rate) / n


def periodicity(values):
    samples = clean(values)
    n = len(samples)
    if n < 4:
        return 0.0
    mean = _mean(samples)
    centered = [value - mean for value in samples]
    energy = 0.0
    for value in centered:
        energy += value * value
    if energy <= 1e-15:
        return 0.0
    if _zero_crossings(centered) < 2:
        return 0.0
    max_lag = n // 2
    correlations = {}
    for lag in range(1, max_lag + 1):
        left_energy = 0.0
        right_energy = 0.0
        cross = 0.0
        for i in range(n - lag):
            a = centered[i]
            b = centered[i + lag]
            cross += a * b
            left_energy += a * a
            right_energy += b * b
        if left_energy <= 0.0 or right_energy <= 0.0:
            correlations[lag] = 0.0
        else:
            correlations[lag] = cross / math.sqrt(left_energy * right_energy)
    best = 0.0
    for lag in range(2, max_lag + 1):
        value = correlations[lag]
        if value <= 0.0 or value < correlations[lag - 1]:
            continue
        if lag + 1 <= max_lag and value < correlations[lag + 1]:
            continue
        if value > best:
            best = value
    if best < 0.0:
        return 0.0
    if best > 1.0:
        return 1.0
    return best


def noise_ratio(values):
    value = 1.0 - periodicity(values)
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def snr_db(values, harmonics=DEFAULT_HARMONICS):
    samples = clean(values)
    mean = _mean(samples)
    powers = half_powers([value - mean for value in samples])
    total = 0.0
    for power in powers:
        total += power
    if total <= 0.0:
        return SNR_FLOOR_DB
    _peak, signal = _peak_and_signal(powers, harmonics)
    if signal <= 0.0:
        return SNR_FLOOR_DB
    noise = total - signal
    if noise <= total * 1e-12:
        noise = total * 1e-12
    value = 10.0 * math.log10(signal / noise)
    if not math.isfinite(value):
        return SNR_FLOOR_DB if value < 0 else -SNR_FLOOR_DB
    return value


def spectral_centroid(values, sample_rate=1.0):
    magnitudes = [math.sqrt(p) for p in half_powers(values)]
    n = padded_length(values)
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


def residual_fraction(values):
    samples = clean(values)
    mean = _mean(samples)
    total = 0.0
    for value in samples:
        total += (value - mean) ** 2
    if total <= 0.0:
        return 0.0
    n = len(samples)
    xbar = (n - 1) / 2.0
    numerator = 0.0
    denominator = 0.0
    for i in range(n):
        numerator += (i - xbar) * (samples[i] - mean)
        denominator += (i - xbar) ** 2
    slope = numerator / denominator if denominator > 0.0 else 0.0
    intercept = mean - slope * xbar
    residual = 0.0
    for i in range(n):
        diff = samples[i] - (slope * i + intercept)
        residual += diff * diff
    value = residual / total
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def classify(values):
    samples = clean(values)
    span = max(samples) - min(samples)
    per = periodicity(samples)
    snr = snr_db(samples)
    if span <= 1e-12:
        return "constant"
    if residual_fraction(samples) <= 1e-9:
        return "trend"
    if per >= 0.5 and snr >= 6.0:
        return "periodic"
    if per < 0.2:
        return "noise"
    return "mixed"

"""Maya Market Pattern Module (MPM): interpretation-only market structure.

Stateless, deterministic, math-only. This module never issues an action
directive and never predicts: every output describes historical/current price
structure only, output shaped to ``maya_identity/market/mpm.schema.json``
(``state="interpretation"``). Imports are intentionally limited to stdlib
math/typing/dataclasses so the engine stays device-independent.

Public surface:
    interpret, validate, detect_pattern, classify_trend, assess_volatility,
    risk_flags, indicator_summary, sentiment_of
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

MPM_VERSION = "1.0"
STATE = "interpretation"

# Schema-conformant vocabulary (mirrors maya_identity/market/mpm.schema.json).
INSTRUMENT_TYPES = ("equity_index", "equity", "commodity", "fx", "crypto", "treasury")
TIMEFRAMES = ("1m", "5m", "15m", "1h", "4h", "1d", "1w")
PATTERN_PRIMARY_ENUM = (
    "trend_continuation", "range_consolidation", "breakout",
    "pole_reversal", "volatility_cluster",
)
TREND_KINDS = ("uptrend", "downtrend", "sideways", "choppy")
VOLATILITY_LEVELS = ("low", "medium", "high")
RISK_FLAG_TYPES = ("overextension", "sharp_move", "gap", "high_volatility")
RISK_SEVERITIES = ("low", "medium", "high")
SENTIMENT_TONES = ("positive", "neutral", "negative", "mixed", "none")

# The safety layer caps any EXPRESSED confidence at this value. The engine
# itself reports structural confidence bounded to [0, 1] per the schema.
EXPRESSION_CONFIDENCE_CAP = 0.5
MAX_RISK_FLAGS = 5

MPM_DISCLAIMER = (
    "Interpretation of historical and current price structure only. "
    "Not a prediction, recommendation, or guarantee of any outcome."
)

_POSITIVE_TERMS = (
    "strong", "raised", "beat", "growth", "gain", "gains", "up", "higher",
    "bull", "bullish", "rally", "record", "rise", "rising", "improve",
)
_NEGATIVE_TERMS = (
    "slump", "cut", "loss", "losses", "miss", "down", "lower", "bear",
    "bearish", "crash", "fall", "falling", "weak", "weaken", "drop",
)


@dataclass(frozen=True)
class Instrument:
    type: str
    timeframe: str = "1d"


@dataclass
class _Candle:
    close: float
    high: float
    low: float


def _as_candles(price_series: Any) -> Tuple[_Candle, ...]:
    """Normalize the accepted price-series shapes into candles.

    Accepts either a flat sequence of numbers (close-only) or a sequence of
    dicts with ``close`` and optional ``high``/``low``. Raises ``ValueError``
    on malformed input; non-finite, out-of-order or reversed values are
    rejected at the boundary.
    """
    if isinstance(price_series, (str, bytes)) or not isinstance(price_series, Sequence):
        raise ValueError("price_series must be a sequence of prices or candles")
    candles: List[_Candle] = []
    for item in price_series:
        if isinstance(item, dict):
            raw_close = item.get("close")
            high = item.get("high", raw_close)
            low = item.get("low", raw_close)
            try:
                close = float(raw_close)
                high_f = float(high)
                low_f = float(low)
            except (TypeError, ValueError) as exc:
                raise ValueError("candle values must be numeric") from exc
        elif isinstance(item, (int, float)):
            try:
                close = float(item)
            except (TypeError, ValueError) as exc:
                raise ValueError("price values must be numeric") from exc
            high_f = close
            low_f = close
        elif hasattr(item, "close"):
            try:
                close = float(item.close)
                high_f = float(getattr(item, "high", close))
                low_f = float(getattr(item, "low", close))
            except (TypeError, ValueError) as exc:
                raise ValueError("candle values must be numeric") from exc
        else:
            raise ValueError("price_series items must be prices or candle dicts")
        if not (math.isfinite(close) and math.isfinite(high_f) and math.isfinite(low_f)):
            raise ValueError("candle values must be finite")
        if high_f < low_f:
            raise ValueError("candle high must be >= low")
        if not (low_f <= close <= high_f):
            raise ValueError("candle close must lie within the high/low range")
        candles.append(_Candle(close, high_f, low_f))
    if len(candles) < 2:
        raise ValueError("price_series must contain at least two observations")
    return tuple(candles)


def _ema_series(closes: Sequence[float], span: int) -> Tuple[float, ...]:
    alpha = 2.0 / (span + 1.0)
    series: List[float] = []
    seed = closes[0]
    for close in closes:
        seed = alpha * close + (1.0 - alpha) * seed
        series.append(seed)
    return tuple(series)


def _rsi14(closes: Sequence[float]) -> float:
    """Wilder RSI(14); 50.0 (neutral) when fewer than 15 prices exist."""
    if len(closes) < 15:
        return 50.0
    gains = []
    losses = []
    for i in range(1, len(closes)):
        delta = closes[i] - closes[i - 1]
        gains.append(delta if delta > 0 else 0.0)
        losses.append(-delta if delta < 0 else 0.0)
    avg_gain = math.fsum(gains) / len(gains)
    avg_loss = math.fsum(losses) / len(losses)
    if avg_loss == 0.0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _atr(candles: Sequence[_Candle]) -> float:
    """Mean of Wilder-style true ranges over consecutive candles."""
    if len(candles) < 2:
        return 0.0
    ranges = []
    prev = candles[0].close
    for c in candles[1:]:
        tr = max(c.high, prev) - min(c.low, prev)
        ranges.append(max(tr, 0.0))
        prev = c.close
    return math.fsum(ranges) / len(ranges)


def _mean(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return math.fsum(values) / len(values)


def _atr_pct(candles: Sequence[_Candle]) -> float:
    atr = _atr(candles)
    mid = _mean([c.close for c in candles])
    if mid == 0.0:
        return 0.0
    return 100.0 * atr / mid


def _channel_range(candles: Sequence[_Candle]) -> Tuple[float, float]:
    """(range_pct, drift_pct) over the full window."""
    high = max(c.high for c in candles)
    low = min(c.low for c in candles)
    mid = _mean([c.close for c in candles])
    first = candles[0].close
    last = candles[-1].close
    range_pct = 100.0 * (high - low) / mid if mid else 0.0
    drift_pct = 100.0 * (last - first) / first if first else 0.0
    return range_pct, drift_pct


def assess_volatility(price_series: Any) -> Dict[str, Any]:
    candles = _as_candles(price_series)
    atr = _atr_pct(candles)
    if atr < 2.0:
        level = "low"
        bucket = "atr_below_2"
    elif atr <= 6.0:
        level = "medium"
        bucket = "atr_pct_2_6"
    else:
        level = "high"
        bucket = "atr_pct_above_6"
    return {"level": level, "bucket": bucket, "atr_pct": round(atr, 4)}


def classify_trend(closes: Sequence[float]) -> Dict[str, Any]:
    """Deterministic trend classification with bounded signal strength.

    Sideways requires BOTH a narrow channel (range < 2%) and a negligible
    drift (|drift| < 0.8%); otherwise the drift dominates the label."""
    first = closes[0]
    last = closes[-1]
    mid = _mean(list(closes))
    drift_pct = 100.0 * (last - first) / first if first else 0.0
    range_pct = 100.0 * (max(closes) - min(closes)) / mid if mid else 0.0
    if range_pct < 2.0 and abs(drift_pct) < 0.8:
        kind = "sideways"
        signal_strength = abs(drift_pct) / 8.0
    elif drift_pct >= 0.8:
        kind = "uptrend"
        signal_strength = min(1.0, 0.2 + abs(drift_pct) / 10.0)
    elif drift_pct <= -0.8:
        kind = "downtrend"
        signal_strength = min(1.0, 0.2 + abs(drift_pct) / 10.0)
    else:
        kind = "choppy"
        signal_strength = 0.5
    return {
        "kind": kind,
        "signal_strength": round(signal_strength, 2),
        "drift_pct": round(drift_pct, 4),
    }


def detect_pattern(
    price_series: Any,
    trend: Dict[str, Any],
    volatility: Dict[str, Any],
) -> Dict[str, Any]:
    candles = _as_candles(price_series)
    range_pct, drift_pct = _channel_range(candles)
    closes = [c.close for c in candles]
    ema = _ema_series(closes, 9)[-1]
    dist_pct = (100.0 * (closes[-1] - ema) / ema) if ema else 0.0
    kind = trend["kind"]

    if kind == "sideways":
        confidence = 0.70
        primary = "range_consolidation"
        rationale = "Price structure is bound in a narrow range with negligible drift."
    elif kind == "choppy" and range_pct < 6.0 and abs(drift_pct) < 3.0:
        confidence = 0.60
        primary = "breakout"
        rationale = ("Compressed structure sits inside the breakout window "
                     "(range <6%, drift <3%): a directional break is not confirmed.")
    elif volatility["level"] == "high":
        confidence = 0.55
        primary = "volatility_cluster"
        rationale = "Expanded true ranges produce clustered volatility with no clean trend."
    elif kind in ("uptrend", "downtrend") and abs(dist_pct) >= 1.0:
        confidence = 0.65
        primary = "breakout"
        rationale = "Price extends beyond the fast EMA on persistent directional drift."
    elif kind in ("uptrend", "downtrend"):
        confidence = 0.55
        primary = "trend_continuation"
        rationale = "Directional drift dominates the window; structure continues its prevailing lean."
    else:
        confidence = 0.45
        primary = "pole_reversal"
        rationale = "Shallow or mixed structure: recent price pulled back from the window extremes."

    return {
        "primary": primary,
        "confidence": round(min(1.0, max(0.0, confidence)), 4),
        "rationale": rationale,
    }


def risk_flags(
    price_series: Any,
    trend: Dict[str, Any],
    volatility: Dict[str, Any],
) -> List[Dict[str, str]]:
    """Deterministic risk flags, capped at MAX_RISK_FLAGS."""
    candles = _as_candles(price_series)
    closes = [c.close for c in candles]
    atr = _atr(candles)
    mid = _mean(closes)
    atr_pct = (100.0 * atr / mid) if mid else 0.0
    ema = _ema_series(closes, 9)[-1]
    flags: List[Dict[str, str]] = []

    if atr_pct > 6.0:
        flags.append({"type": "high_volatility", "severity": "high",
                      "note": "ATR% exceeds the high-volatility threshold."})

    dist_pct = (100.0 * (closes[-1] - ema) / ema) if ema else 0.0
    if dist_pct > 6.0 or dist_pct < -6.0:
        flags.append({
            "type": "overextension", "severity": "high",
            "note": "Price is stretched more than 6% from the fast EMA(9).",
        })
    elif dist_pct > 3.0 or dist_pct < -3.0:
        flags.append({
            "type": "overextension", "severity": "medium",
            "note": "Price is stretched more than 3% from the fast EMA(9).",
        })

    for i in range(1, len(closes)):
        if closes[i - 1] == 0.0:
            continue
        move_pct = abs(closes[i] - closes[i - 1]) * 100.0 / closes[i - 1]
        if move_pct > 6.0:
            flags.append({
                "type": "sharp_move", "severity": "high",
                "note": "A single-bar move exceeded 6%.",
            })
            break
        if move_pct > 3.0:
            flags.append({
                "type": "sharp_move", "severity": "medium",
                "note": "A single-bar move exceeded 3%.",
            })
            break

    return flags[:MAX_RISK_FLAGS]


def indicator_summary(
    price_series: Any,
    trend: Dict[str, Any],
    volatility: Dict[str, Any],
) -> List[Dict[str, str]]:
    candles = _as_candles(price_series)
    closes = [c.close for c in candles]
    ema = _ema_series(closes, 9)[-1]
    last = closes[-1]
    ma_reading = "price_above_fast_ema" if last >= ema else "price_below_fast_ema"
    rsi = _rsi14(closes)
    if rsi >= 70.0:
        rsi_reading = "overbought"
    elif rsi <= 30.0:
        rsi_reading = "oversold"
    else:
        rsi_reading = "neutral_zone"
    return [
        {
            "indicator": "ma",
            "reading": ma_reading,
            "detail": (f"fast EMA(9) {ema:.4f} vs last close {last:.4f}"
                       f" ({ma_reading})"),
        },
        {
            "indicator": "rsi",
            "reading": rsi_reading,
            "detail": f"RSI(14) {rsi:.1f} ({rsi_reading})",
        },
    ]


def sentiment_of(user_context: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    """Deterministic lexicon tone from user-provided context (source always
    user_provided). None or an empty payload yields tone 'none'."""
    source = "user_provided"
    if not isinstance(user_context, dict):
        return {"source": source, "tone": "none"}
    news = user_context.get("news")
    if not isinstance(news, str) or not news.strip():
        return {"source": source, "tone": "none"}
    tokens = news.lower().split()
    pos = sum(1 for t in tokens if t in _POSITIVE_TERMS)
    neg = sum(1 for t in tokens if t in _NEGATIVE_TERMS)
    if pos and neg:
        tone = "mixed"
    elif pos:
        tone = "positive"
    elif neg:
        tone = "negative"
    else:
        tone = "neutral"
    return {"source": source, "tone": tone}


def validate(obj: Any) -> bool:
    """Structural schema conformance check for an MPM object."""
    if not isinstance(obj, dict):
        return False
    required = (
        "mpm_version", "state", "instrument", "pattern", "trend", "volatility",
        "risk_flags", "indicator_summary", "sentiment", "explanation",
        "disclaimer",
    )
    if not all(key in obj for key in required):
        return False
    if obj.get("mpm_version") != MPM_VERSION or obj.get("state") != STATE:
        return False
    instrument = obj.get("instrument")
    if not isinstance(instrument, dict):
        return False
    if instrument.get("type") not in INSTRUMENT_TYPES:
        return False
    if instrument.get("timeframe") not in TIMEFRAMES:
        return False
    pattern = obj.get("pattern")
    if not isinstance(pattern, dict):
        return False
    if pattern.get("primary") not in PATTERN_PRIMARY_ENUM:
        return False
    confidence = pattern.get("confidence")
    if not isinstance(confidence, (int, float)) or not (0.0 <= confidence <= 1.0):
        return False
    trend = obj.get("trend")
    if not isinstance(trend, dict) or trend.get("kind") not in TREND_KINDS:
        return False
    strength = trend.get("signal_strength")
    if not isinstance(strength, (int, float)) or not (0.0 <= strength <= 1.0):
        return False
    volatility = obj.get("volatility")
    if not isinstance(volatility, dict) or volatility.get("level") not in VOLATILITY_LEVELS:
        return False
    flags = obj.get("risk_flags")
    if not isinstance(flags, list) or len(flags) > MAX_RISK_FLAGS:
        return False
    if any(flag.get("type") not in RISK_FLAG_TYPES for flag in flags):
        return False
    if any(flag.get("severity") not in RISK_SEVERITIES for flag in flags):
        return False
    indicators = obj.get("indicator_summary")
    if not isinstance(indicators, list) or not indicators:
        return False
    sentiment = obj.get("sentiment")
    if not isinstance(sentiment, dict) or sentiment.get("source") != "user_provided":
        return False
    if sentiment.get("tone") not in SENTIMENT_TONES:
        return False
    if not obj.get("explanation") or not obj.get("disclaimer"):
        return False
    return True


def interpret(
    price_series: Any,
    instrument: Any,
    user_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Full deterministic interpretation for one price window.

    Returns a schema-conformant interpretation object. Raises ``ValueError``
    on malformed input. Pure: no state, no randomness, no IO, no clocks.
    """
    candles = _as_candles(price_series)
    if isinstance(instrument, Instrument):
        itype = instrument.type
        timeframe = instrument.timeframe
    elif isinstance(instrument, dict):
        itype = instrument.get("type")
        timeframe = instrument.get("timeframe", "1d")
    else:
        raise ValueError("instrument must be an Instrument or mapping")
    if itype not in INSTRUMENT_TYPES:
        raise ValueError(f"unknown instrument type: {itype!r}")
    if timeframe not in TIMEFRAMES:
        raise ValueError(f"unknown timeframe: {timeframe!r}")
    if user_context is not None and not isinstance(user_context, dict):
        raise ValueError("user_context must be a mapping or None")

    closes = [c.close for c in candles]
    trend = classify_trend(closes)
    volatility = assess_volatility(candles)
    pattern = detect_pattern(candles, trend, volatility)
    flags = risk_flags(candles, trend, volatility)
    indicators = indicator_summary(candles, trend, volatility)
    sentiment = sentiment_of(user_context)

    explanation = (
        f"{pattern['primary']} structure with {(', '.join(flag['type'] for flag in flags) or 'no')} "
        f"risk flag{'' if len(flags) == 1 else 's'}; {trend['kind']} lean at "
        f"confidence {pattern['confidence']:.2f} on {volatility['level']} volatility "
        f"(ATR {volatility['atr_pct']:.2f}%)."
    )

    return {
        "mpm_version": MPM_VERSION,
        "state": STATE,
        "instrument": {"type": itype, "timeframe": timeframe},
        "pattern": pattern,
        "trend": {"kind": trend["kind"], "signal_strength": trend["signal_strength"]},
        "volatility": {"level": volatility["level"], "bucket": volatility["bucket"]},
        "risk_flags": flags,
        "indicator_summary": indicators,
        "sentiment": sentiment,
        "explanation": explanation,
        "disclaimer": MPM_DISCLAIMER,
    }
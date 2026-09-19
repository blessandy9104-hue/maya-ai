from __future__ import annotations

import json
import math
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from maya_runtime.market import mpm  # noqa: E402

id_instrument = {"type": "equity_index", "timeframe": "1d"}
eq_instrument = {"type": "equity", "timeframe": "1h"}


def uptrend_fixture():
    closes = [round(100.0 + i * 10.0 / 9.0, 12) for i in range(10)]
    return [{"close": c, "high": c + 1.75, "low": c - 1.75} for c in closes]


def range_fixture():
    closes = [99.9, 100.2, 99.8, 100.4, 100.0, 99.7, 100.3, 99.9, 100.5, 100.1]
    return [{"close": c, "high": c + 0.3, "low": c - 0.3} for c in closes]


# --- schema-conformant vocabulary pin ---------------------------------------

_props = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "maya_identity", "market", "mpm.schema.json"),
                        encoding="utf-8"))

assert mpm.MPM_VERSION == "1.0"
assert mpm.STATE == "interpretation"
assert tuple(mpm.INSTRUMENT_TYPES) == tuple(_props["definitions"]["instrument_type"]["enum"])
assert tuple(mpm.TIMEFRAMES) == tuple(_props["definitions"]["timeframe"]["enum"])
assert tuple(mpm.PATTERN_PRIMARY_ENUM) == tuple(_props["definitions"]["pattern_primary"]["enum"])
assert tuple(mpm.TREND_KINDS) == tuple(_props["definitions"]["trend_kind"]["enum"])
assert tuple(mpm.RISK_FLAG_TYPES) == tuple(_props["definitions"]["risk_flag_type"]["enum"])
assert set(_props["properties"].keys()) >= {
    "mpm_version", "state", "instrument", "pattern", "trend", "volatility",
    "risk_flags", "indicator_summary", "sentiment", "explanation", "disclaimer",
}
print("mpm_schema_compiles=OK")

# --- determinism: identical input -> identical output ------------------------

up = uptrend_fixture()
o1 = mpm.interpret(up, id_instrument, {"news": "earnings strong, guidance raised"})
o2 = mpm.interpret(up, id_instrument, {"news": "earnings strong, guidance raised"})
assert o1 == o2
for _ in range(3):
    assert mpm.interpret(up, id_instrument, {"news": "earnings"}) == \
        mpm.interpret(up, id_instrument, {"news": "earnings"})
print("mpm_deterministic=OK")

# --- stateless: repeated calls never accumulate state ------------------------

before = mpm.interpret(up, id_instrument)
_ = mpm.interpret(range_fixture(), eq_instrument)
after = mpm.interpret(up, id_instrument)
assert before == after
assert mpm.validate(before) and mpm.validate(after)
print("mpm_stateless=OK")

# --- boundary validation: malformed input raises -----------------------------

def _raises(fn):
    try:
        fn()
    except (ValueError, TypeError):
        return True
    return False

series2 = [{"close": 10.0, "high": 10.5, "low": 9.5},
           {"close": 10.2, "high": 10.6, "low": 9.7}]
assert _raises(lambda: mpm.interpret([1.0], id_instrument))
assert _raises(lambda: mpm.interpret([], id_instrument))
assert _raises(lambda: mpm.interpret([float("nan"), 2.0], id_instrument))
assert _raises(lambda: mpm.interpret([1.0, float("inf")], id_instrument))
assert _raises(lambda: mpm.interpret("prices", id_instrument))
assert _raises(lambda: mpm.interpret([1.0, 2.0], {"type": "unknown", "timeframe": "1d"}))
assert _raises(lambda: mpm.interpret([1.0, 2.0], {"type": "equity", "timeframe": "9d"}))
assert _raises(lambda: mpm.interpret([1.0, 2.0], "equity"))
assert _raises(lambda: mpm.interpret(up, id_instrument, "news"))
assert mpm.validate(mpm.interpret(series2, id_instrument))
assert not _raises(lambda: mpm.interpret(up, id_instrument, {"news": "flat"}))
print("mpm_input_sensitive=OK")

# --- uptrend trace -----------------------------------------------------------

ut = mpm.interpret(up, id_instrument, {"news": "earnings strong, guidance raised"})
assert mpm.validate(ut)
assert ut["pattern"]["primary"] == "breakout"
assert ut["pattern"]["confidence"] == 0.65
assert ut["trend"]["kind"] == "uptrend"
assert ut["trend"]["signal_strength"] == 1.0
assert ut["volatility"]["level"] == "medium"
assert ut["volatility"]["bucket"] == "atr_pct_2_6"
assert len(ut["risk_flags"]) == 1
assert ut["risk_flags"][0]["type"] == "overextension"
assert ut["risk_flags"][0]["severity"] == "medium"
assert ut["sentiment"]["source"] == "user_provided"
assert ut["sentiment"]["tone"] == "positive"
ema9_val = float(ut["indicator_summary"][0]["detail"].split("vs")[0].split()[-1])
assert abs(ema9_val - 105.8) <= 0.6
assert ut["mpm_version"] == "1.0" and ut["state"] == "interpretation"
print("mpm_uptrend_trace=OK")

# --- range trace -------------------------------------------------------------

rg = mpm.interpret(range_fixture(), eq_instrument)
assert mpm.validate(rg)
assert rg["pattern"]["primary"] == "range_consolidation"
assert rg["pattern"]["confidence"] == 0.70
assert rg["trend"]["kind"] == "sideways"
assert rg["trend"]["signal_strength"] == 0.03
assert rg["volatility"]["level"] == "low"
assert rg["risk_flags"] == []
assert rg["sentiment"]["tone"] == "none"
print("mpm_range_trace=OK")

# --- full schema conformance -------------------------------------------------

assert set(ut.keys()) == {
    "mpm_version", "state", "instrument", "pattern", "trend", "volatility",
    "risk_flags", "indicator_summary", "sentiment", "explanation", "disclaimer",
}
assert ut["instrument"] == {"type": "equity_index", "timeframe": "1d"}
assert set(ut["pattern"].keys()) == {"primary", "confidence", "rationale"}
assert set(ut["trend"].keys()) == {"kind", "signal_strength"}
assert set(ut["volatility"].keys()) == {"level", "bucket"}
assert set(ut["risk_flags"][0].keys()) == {"type", "severity", "note"}
assert all(f["type"] in mpm.RISK_FLAG_TYPES for f in ut["risk_flags"])
assert all(f["severity"] in mpm.RISK_SEVERITIES for f in ut["risk_flags"])
assert len(ut["risk_flags"]) <= mpm.MAX_RISK_FLAGS
print("mpm_schema_conformance=OK")

# --- instrument enum across every type/timeframe -----------------------------

for itype in mpm.INSTRUMENT_TYPES:
    for tframe in mpm.TIMEFRAMES:
        obj = mpm.interpret(up, {"type": itype, "timeframe": tframe})
        assert obj["instrument"] == {"type": itype, "timeframe": tframe}
        assert mpm.validate(obj)
print("mpm_instrument_enum=OK")

# --- EMA math: independent reference -----------------------------------------

ema_ref = []
anchor = up[0]["close"]
for c in up:
    anchor = 0.2 * c["close"] + 0.8 * anchor
    ema_ref.append(anchor)
detail = ut["indicator_summary"][0]
assert detail["indicator"] == "ma"
assert "EMA(9)" in detail["detail"]
for token in detail["detail"].split():
    if token.startswith("EMA(9)"):
        continue
    try:
        ema_val = float(token.lstrip("fast").strip())
    except ValueError:
        continue
    assert math.isclose(ema_val, ema_ref[-1], rel_tol=1e-6, abs_tol=1e-3)
    break
assert ut["indicator_summary"][0]["reading"] == "price_above_fast_ema"
print("mpm_ema_math=OK")

# --- RSI bounds: neutral for short windows, in range otherwise ---------------

rsi_obj = ut["indicator_summary"][1]
assert rsi_obj["indicator"] == "rsi"
assert rsi_obj["reading"] == "neutral_zone"
long_series = [[{"close": 100.0 + i, "high": 101.5 + i, "low": 98.5 + i}
                for i in range(30)]]
rsi = mpm._rsi14([c["close"] for c in long_series[0]])
assert 0.0 <= rsi <= 100.0
assert mpm._rsi14([1.0, 2.0]) == 50.0
print("mpm_rsi_bounds=OK")

# --- volatility buckets ------------------------------------------------------

low_c = [{"close": c, "high": c + 0.1, "low": c - 0.1}
         for c in (99.95, 100.05, 99.9, 100.1, 99.95, 100.05, 99.9, 100.1, 99.95, 100.05)]
mid_c = [{"close": c, "high": c + 1.75, "low": c - 1.75} for c in range(100, 110)]
hi_c = [{"close": c, "high": c + 6.0, "low": c - 6.0} for c in range(100, 110)]
assert mpm.assess_volatility(low_c)["level"] == "low"
assert mpm.assess_volatility(mid_c)["level"] == "medium"
assert mpm.assess_volatility(hi_c)["level"] == "high"
assert mpm.assess_volatility(up)["bucket"] == "atr_pct_2_6"
print("mpm_volatility_buckets=OK")

# --- trend classification ----------------------------------------------------

for kind, closes in (("uptrend", [100.0 + i * 2.0 for i in range(10)]),
                     ("downtrend", [100.0 - i * 2.0 for i in range(10)]),
                     ("sideways", [100.0 + (i % 2) * 0.1 for i in range(10)])):
    tr = mpm.classify_trend(closes)
    assert tr["kind"] == kind, (kind, tr)
    assert 0.0 <= tr["signal_strength"] <= 1.0
print("mpm_trend_classification=OK")

# --- risk flags capped -------------------------------------------------------

flag_run = [{"close": 100.0 + i, "high": 101.5 + i, "low": 98.5 + i}
            for i in range(10)]
flags = mpm.risk_flags(flag_run, mpm.classify_trend([c["close"] for c in flag_run]),
                       mpm.assess_volatility(flag_run))
assert isinstance(flags, list)
assert len(flags) <= mpm.MAX_RISK_FLAGS
assert [f for f in flags if f["type"] == "overextension"][0]["severity"] == "medium"
spike = ([{"close": 100.0, "high": 101.0, "low": 99.0},
          {"close": 104.5, "high": 105.0, "low": 103.5}]
         + [{"close": 104.5, "high": 105.0, "low": 104.0} for _ in range(6)])
sf = mpm.risk_flags(spike, mpm.classify_trend([c["close"] for c in spike]),
                    mpm.assess_volatility(spike))
assert any(f["type"] == "sharp_move" and f["severity"] == "medium" for f in sf)
assert mpm.risk_flags(range_fixture(),
                      mpm.classify_trend([c["close"] for c in range_fixture()]),
                      mpm.assess_volatility(range_fixture())) == []
print("mpm_risk_flags_capped=OK")

# --- sentiment is always user_provided, deterministic tones ------------------

assert mpm.sentiment_of(None) == {"source": "user_provided", "tone": "none"}
assert mpm.sentiment_of({}) == {"source": "user_provided", "tone": "none"}
assert mpm.sentiment_of({"news": "raised guidance, strong earnings"})["tone"] == "positive"
assert mpm.sentiment_of({"news": "cut guidance, weak sales"})["tone"] == "negative"
assert mpm.sentiment_of({"news": "raised guidance but weak sales"})["tone"] == "mixed"
assert mpm.sentiment_of({"news": "the market opened"})["tone"] == "neutral"
assert all(mpm.sentiment_of({"news": "x"})["source"] == "user_provided" for x in range(1))
print("mpm_sentiment_user_only=OK")

# --- directive-free explanation ----------------------------------------------

for line in (ut["explanation"], rg["explanation"]):
    low = line.lower()
    for banned in ("buy", "sell", "hold", "long", "short", "should",
                   "guarantee", "predict", "must"):
        assert banned not in low, (banned, line)
assert ut["disclaimer"] and "not a prediction" in ut["disclaimer"].lower()
print("mpm_directive_free=OK")

# --- native/headless parity --------------------------------------------------

parity_code = (
    "import sys\n"
    "sys.path.insert(0, %r)\n"
    "from maya_runtime.market import mpm\n"
    "closes = [round(100.0 + i * 10.0 / 9.0, 12) for i in range(10)]\n"
    "c = [{'close': x, 'high': x + 1.75, 'low': x - 1.75} for x in closes]\n"
    "print(json.dumps(mpm.interpret(c, {'type': 'equity_index', 'timeframe': '1d'}, "
    "{'news': 'earnings strong'}), sort_keys=True))\n"
) % os.path.dirname(os.path.abspath(__file__))
parity_code = "import json\n" + parity_code
env = dict(os.environ)
env["MAYA_RUNTIME_HEADLESS"] = "1"
proc = subprocess.run([sys.executable, "-c", parity_code], capture_output=True,
                      text=True, cwd=os.path.dirname(os.path.abspath(__file__)), env=env)
assert proc.returncode == 0, proc.stderr
headless_obj = json.loads(proc.stdout.strip().splitlines()[-1])
assert headless_obj == ut
print("mpm_parity_native_headless=OK")
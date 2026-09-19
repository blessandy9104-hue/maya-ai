"""Local, approval-aware learning and Andy-interest inference for Maya.

All learning and prediction runs through the Math Coordination Agent; nothing
here computes arithmetic directly. Evidence signals are bounded onto [0, 1];
learning summarizes each topic's signal series with variance, stability, a
normalized (variance, stability, trend) learning vector, and an exp_smooth-
stabilized prediction of the next signal that must be re-validated before it
is stored.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from maya_identity.wireframe.math_coordinator import (
    LEARNING_DEFAULT_HORIZON, MATH_AGENT)

ROOT = Path(__file__).resolve().parent
LEARNING_STATUS = ROOT / "learning_status.json"
INTEREST_MAP = ROOT / "knowledge" / "andy_interest_map.json"
LEARNING_LOG = ROOT / "knowledge" / "learning_events.jsonl"

# Evidence signal domain: evidence is bounded onto [0, 1] by this ceiling,
# so the topic series and every prediction live on the pattern domain.
_EVIDENCE_CEILING = 8
_SIGNAL_CAP = 12


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _log(event: dict[str, Any]) -> None:
    LEARNING_LOG.parent.mkdir(parents=True, exist_ok=True)
    with LEARNING_LOG.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"timestamp": _now(), **event}, ensure_ascii=False) + "\n")


def learning_status() -> dict[str, Any]:
    default = {
        "mode": "sleeping",
        "observation": "disabled",
        "local_only": True,
        "network_research": "disabled",
        "permanent_memory": "approval_required",
        "updated_at": _now(),
    }
    status = _read_json(LEARNING_STATUS, default)
    if not isinstance(status, dict):
        return default
    return {**default, **status}


def set_learning_mode(mode: str) -> dict[str, Any]:
    if mode not in {"sleeping", "learning"}:
        raise ValueError("mode must be sleeping or learning")
    if mode == "learning":
        status = {
            "mode": "learning",
            "observation": "approved_local_signals_only",
            "local_only": True,
            "network_research": "read_only_allowlist_only",
            "permanent_memory": "approval_required",
            "started_at": _now(),
            "updated_at": _now(),
        }
        _log({"event": "learning_started", "source": "andy_explicit_wake"})
    else:
        status = {
            "mode": "sleeping",
            "observation": "disabled",
            "local_only": True,
            "network_research": "read_only_allowlist_only",
            "permanent_memory": "approval_required",
            "updated_at": _now(),
        }
        _log({"event": "learning_stopped", "source": "andy_explicit_stop"})
    _write_json(LEARNING_STATUS, status)
    return status


def _load_map() -> dict[str, Any]:
    default = {
        "owner": "Andy",
        "purpose": "Provisional model of Andy's interests and reasoning patterns.",
        "interests": {},
        "rules": [],
        "last_updated": None,
        "memory_policy": "Inferences remain provisional until Andy approves permanent memory.",
    }
    data = _read_json(INTEREST_MAP, default)
    return data if isinstance(data, dict) else default


def record_signal(topic: str, source: str, detail: str = "") -> dict[str, Any]:
    """Record a provisional interest signal only during an active learning session."""
    status = learning_status()
    if status.get("mode") != "learning":
        return {"recorded": False, "reason": "learning session is sleeping"}
    topic = " ".join(topic.strip().lower().split())
    if not topic:
        return {"recorded": False, "reason": "empty topic"}
    data = _load_map()
    item = data.setdefault("interests", {}).setdefault(topic, {
        "evidence": 0,
        "confidence": "low",
        "sources": [],
        "last_seen": None,
        "status": "inferred",
    })
    item["evidence"] = int(item.get("evidence", 0)) + 1
    signal = MATH_AGENT.map01(float(item["evidence"]) / float(_EVIDENCE_CEILING))
    series = item.setdefault("signal_series", [])
    series.append(signal)
    if len(series) > _SIGNAL_CAP:
        del series[: -_SIGNAL_CAP]
    learning = MATH_AGENT.learn_feature(series)
    stats = MATH_AGENT.learn_stats(series)
    prediction = MATH_AGENT.predict_signal(series, expected=1.0)
    validated = MATH_AGENT.predict_validate(series, prediction)
    item["learning_vector"] = {
        "variance": learning[0],
        "stability": learning[1],
        "trend": learning[2],
        "series_std": stats["std"],
    }
    item["prediction"] = {
        "signal": prediction["predicted"],
        "trend_alignment": prediction["trend"],
        "horizon": prediction["horizon"],
        "validated": validated["ok"],
    }
    level = prediction["predicted"]
    item["confidence"] = (
        "high" if level >= 0.75
        else "medium" if level >= 0.45
        else "low")
    item["last_seen"] = _now()
    if source not in item.setdefault("sources", []):
        item["sources"].append(source)
    data["last_updated"] = _now()
    _write_json(INTEREST_MAP, data)
    _log({"event": "interest_signal", "topic": topic, "source": source, "detail": detail[:500]})
    return {"recorded": True, "topic": topic, "confidence": item["confidence"], "evidence": item["evidence"]}


def interest_summary() -> str:
    data = _load_map()
    interests = data.get("interests", {})
    if not interests:
        return "I do not have enough approved learning-session evidence to infer your interests yet."
    ranked = sorted(interests.items(), key=lambda pair: (pair[1].get("evidence", 0), pair[0]), reverse=True)
    lines = ["These are provisional interest inferences, not permanent memories:"]
    for topic, item in ranked[:12]:
        lines.append(f"- {topic} (confidence: {item.get('confidence', 'low')}, evidence: {item.get('evidence', 0)})")
    lines.append("I will use them for suggestions only and will not treat them as confirmed facts without your approval.")
    return "\n".join(lines)

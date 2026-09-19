"""Neutral, provenance-first world-model evidence store for Maya.

This layer stores public or explicitly approved world evidence separately from
private user memory. It records provenance and uncertainty; it does not decide
truth, make forecasts, or trigger actions.
"""
from __future__ import annotations

import json
import math
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
EVIDENCE_FILE = ROOT / "maya_world_evidence.jsonl"
ALLOWED_EVIDENCE_TYPES = {"fact", "report", "observation", "historical_record", "user_approved_context"}
ALLOWED_CONFIDENCE = {"low", "medium", "high"}
FORBIDDEN_PRIVATE_FIELDS = {"password", "token", "secret", "private_key", "credit_card", "ssn"}
NEGATION_MARKERS = {"not", "never", "no", "without", "cannot", "can't", "fails", "unavailable"}
STOPWORDS = {"the", "a", "an", "is", "are", "was", "were", "to", "of", "and", "for", "in", "on", "this", "that", "with"}
STALE_AFTER_DAYS = 30


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read() -> list[dict[str, Any]]:
    if not EVIDENCE_FILE.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in EVIDENCE_FILE.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
            if isinstance(item, dict):
                rows.append(item)
        except json.JSONDecodeError:
            continue
    return rows


def _append(item: dict[str, Any]) -> None:
    with EVIDENCE_FILE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")


def _claim_tokens(claim: str) -> set[str]:
    words = {word.strip(".,!?;:()[]{}\"'").lower() for word in claim.split()}
    return {word for word in words if word and word not in STOPWORDS}


def _has_negation(claim: str) -> bool:
    return bool(_claim_tokens(claim) & NEGATION_MARKERS)


def _find_conflicts(claim: str, existing: list[dict[str, Any]]) -> list[str]:
    tokens = _claim_tokens(claim)
    negated = _has_negation(claim)
    conflicts = []
    for item in existing:
        other_claim = str(item.get("claim", ""))
        overlap = tokens & _claim_tokens(other_claim)
        if len(overlap) >= 3 and negated != _has_negation(other_claim):
            conflicts.append(str(item.get("evidence_id")))
    return conflicts


def evidence_freshness(item: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    """Classify evidence age without changing its confidence or truth status."""
    retrieved_at = str(item.get("retrieved_at", "")).strip()
    try:
        retrieved = datetime.fromisoformat(retrieved_at.replace("Z", "+00:00"))
        if retrieved.tzinfo is None:
            retrieved = retrieved.replace(tzinfo=timezone.utc)
    except ValueError:
        return {"status": "unknown", "reason": "retrieval timestamp is missing or invalid"}
    reference = now or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    age_days = max(0, (reference - retrieved).days)
    return {
        "status": "stale" if age_days >= STALE_AFTER_DAYS else "fresh",
        "age_days": age_days,
        "refresh_after_days": STALE_AFTER_DAYS,
        "reason": "review before relying on time-sensitive evidence" if age_days >= STALE_AFTER_DAYS else "within the local review window",
    }


def compare_sources(query: str = "", limit: int = 20) -> dict[str, Any]:
    """Return a transparent, read-only comparison of matching evidence."""
    query_tokens = _claim_tokens(query)
    rows = list_evidence(limit)
    if query_tokens:
        rows = [row for row in rows if query_tokens & _claim_tokens(str(row.get("claim", "")))]
    records = []
    for row in rows:
        freshness = evidence_freshness(row)
        records.append({
            "evidence_id": row.get("evidence_id"),
            "claim": row.get("claim"),
            "source": row.get("source"),
            "source_url": row.get("source_url"),
            "confidence": row.get("confidence"),
            "evidence_type": row.get("evidence_type"),
            "conflict_status": row.get("conflict_status"),
            "freshness": freshness,
            "uncertainty": row.get("uncertainty"),
        })
    sources = {str(record.get("source", "")).strip() for record in records if str(record.get("source", "")).strip()}
    return {
        "status": "source_comparison",
        "query": query.strip() or None,
        "matching_records": len(records),
        "distinct_sources": len(sources),
        "stale_records": sum(record["freshness"]["status"] == "stale" for record in records),
        "unknown_freshness_records": sum(record["freshness"]["status"] == "unknown" for record in records),
        "conflict_flagged_records": sum(record.get("conflict_status") == "conflict_flagged" for record in records),
        "records": records,
        "interpretation": "Comparison preserves source, uncertainty, conflict, and freshness signals; it does not determine truth or make a forecast.",
    }


def add_evidence(*, claim: str, source: str, source_url: str = "", confidence: str = "medium", evidence_type: str = "fact", published_at: str | None = None, perspective: str = "", uncertainty: str = "", approved_context: bool = False, initial_conflicts: list[str] | None = None) -> dict[str, Any]:
    claim = claim.strip()
    source = source.strip()
    source_url = source_url.strip()
    confidence = confidence.strip().lower()
    evidence_type = evidence_type.strip().lower()
    combined = f"{claim} {source}".lower()
    if not claim or not source:
        return {"status": "rejected", "reason": "claim and source are required"}
    if any(field in combined for field in FORBIDDEN_PRIVATE_FIELDS):
        return {"status": "rejected", "reason": "potentially sensitive private field detected; world model stores no secrets"}
    if confidence not in ALLOWED_CONFIDENCE:
        return {"status": "rejected", "reason": "confidence must be low, medium, or high"}
    if evidence_type not in ALLOWED_EVIDENCE_TYPES:
        return {"status": "rejected", "reason": f"evidence_type must be one of {sorted(ALLOWED_EVIDENCE_TYPES)}"}
    if evidence_type == "user_approved_context" and not approved_context:
        return {"status": "rejected", "reason": "user_approved_context requires explicit approval"}
    conflicts_with = _find_conflicts(claim, _read())
    if initial_conflicts:
        existing_ids = {str(item.get("evidence_id")) for item in _read()}
        extra = [str(evidence_id) for evidence_id in initial_conflicts
                 if str(evidence_id) in existing_ids and str(evidence_id) not in conflicts_with]
        conflicts_with = list(conflicts_with) + extra
    item = {
        "evidence_id": str(uuid.uuid4()),
        "claim": claim,
        "source": source,
        "source_url": source_url,
        "retrieved_at": _utc_now(),
        "published_at": published_at.strip() if published_at else None,
        "confidence": confidence,
        "evidence_type": evidence_type,
        "perspective": perspective.strip(),
        "uncertainty": uncertainty.strip() or "Not recorded; review before relying on this claim.",
        "visibility": "approved_world_context" if approved_context else "public_world_context",
        "conflict_status": "conflict_flagged" if conflicts_with else "no_conflict_detected",
        "conflicts_with": conflicts_with,
        "memory_update": "not_performed",
        "external_action": "not_performed",
    }
    _append(item)
    return {"status": "recorded", "evidence": item}


def _clause(text: str, limit: int = 120) -> str:
    """Short, single-line excerpt used to describe a research source."""
    cleaned = " ".join(str(text).split())
    return cleaned[:limit].rstrip(".") + "."


def add_research_conflict(*, topic: str, sentence_a: str, url_a: str = "", host_a: str = "", sentence_b: str = "", url_b: str = "", host_b: str = "", confidence: str = "low") -> dict[str, Any]:
    """Persist a neutral disagreement note from read-only research.

    Records that live research synthesis found two retrieved sources in
    disagreement for a topic. This is a structural, provenance-bearing
    observation in the world ledger — it is not approved memory, does not
    decide truth, and performs no external action.
    """
    label_a = host_a.strip() or url_a.strip() or "source A"
    label_b = host_b.strip() or url_b.strip() or "source B"
    claim = (
        "Research synthesis for %r found retrieved sources %s and %s disagree: "
        "%s %s"
        % (topic[:120], label_a, label_b,
           _clause(sentence_a), _clause(sentence_b))
    )
    return add_evidence(
        claim=claim[:600],
        source="research_synthesis",
        source_url=url_a.strip(),
        confidence=confidence,
        evidence_type="observation",
        perspective=url_b.strip(),
        uncertainty="Automated disagreement flag from read-only research; structural note, not a truth judgement.",
    )


def list_evidence(limit: int = 20) -> list[dict[str, Any]]:
    return _read()[-max(1, min(int(limit), 100)):]


def read_evidence() -> list[dict[str, Any]]:
    """Public read-only view of the full evidence store (every row).

    The one door external consumers (provenance drilldown) use; the file
    stays this module's private state.
    """
    return _read()


def evidence_summary() -> dict[str, Any]:
    rows = _read()
    freshness = [evidence_freshness(row).get("status") for row in rows]
    return {
        "status": "neutral_world_model",
        "record_count": len(rows),
        "confidence_counts": {level: sum(row.get("confidence") == level for row in rows) for level in sorted(ALLOWED_CONFIDENCE)},
        "public_world_context_records": sum(row.get("visibility") == "public_world_context" for row in rows),
        "approved_world_context_records": sum(row.get("visibility") == "approved_world_context" for row in rows),
        "conflict_flagged_records": sum(row.get("conflict_status") == "conflict_flagged" for row in rows),
        "fresh_records": freshness.count("fresh"),
        "stale_records": freshness.count("stale"),
        "unknown_freshness_records": freshness.count("unknown"),
        "freshness_review_window_days": STALE_AFTER_DAYS,
        "private_memory_access": False,
        "automatic_forecasting": False,
        "automatic_external_action": False,
    }


def numeric_uncertainty_series() -> list[float]:
    """Read-only numeric uncertainty series for the safety engine. Returns
    every recorded numeric uncertainty as float; non-numeric entries are
    omitted so drift detection never invents a value."""
    rows = _read()
    return [float(row["uncertainty"]) for row in rows
            if isinstance(row.get("uncertainty"), (int, float))
            and not isinstance(row.get("uncertainty"), bool)]


def render_evidence(limit: int = 10) -> str:
    rows = list_evidence(limit)
    if not rows:
        return "Neutral world model is empty. Add source-backed evidence for review."
    lines = [f"Neutral world evidence ({len(rows)} shown; provenance and confidence are mandatory):"]
    for row in rows:
        lines.append(f"- {row['evidence_id'][:12]} | {row['confidence']} | {row['evidence_type']} | {row['claim']} | source: {row['source']} | retrieved: {row['retrieved_at']}")
    return "\n".join(lines)


def stability_status() -> dict[str, Any]:
    """Read-only stability report for the world model, computed through the
    Math Coordination Agent. Reports domain/stability of numeric evidence
    features (uncertainty, freshness) and the coherence, drift, and
    classification of the normalized world-state pattern — without writing
    or forecasting. Every measurement is mathematically validated; there is
    no heuristic world reasoning."""
    from maya_identity.wireframe.math_coordinator import MATH_AGENT
    rows = _read()
    uncertainties = []
    for row in rows:
        value = row.get("uncertainty")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            uncertainties.append(float(value))
    world = MATH_AGENT.world_stability(uncertainties, max_std=0.10) if uncertainties else {"ok": True, "reason": None, "std": 0.0}
    state = {"evidence_count": len(rows), "uncertainty_std": world["std"], "fully_stable": bool(world["ok"])}
    report = MATH_AGENT.world_state_ok(state)

    stale = sum(evidence_freshness(row)["status"] == "stale" for row in rows)
    conflicts = sum(row.get("conflict_status") == "conflict_flagged" for row in rows)

    # Normalized world-state pattern on the canonical feature space
    # (stability, drift, currency, consensus) — each feature bounded onto
    # [0, 1] before any dot similarity or smoothing touches it.
    n = max(1, len(rows))
    drift_feature = MATH_AGENT.world_index(conflicts * 2, 8) if rows else 1.0
    currency_feature = MATH_AGENT.world_index(stale, max(1, n))
    consensus_feature = MATH_AGENT.world_index(conflicts, max(1, n)) if rows else 1.0
    stability_feature = 1.0 if not rows else (1.0 - float(world["std"])) * (1.0 - MATH_AGENT.world_index(conflicts, max(1, n)))
    pattern = (MATH_AGENT.map01(stability_feature),
               MATH_AGENT.map01(drift_feature),
               MATH_AGENT.map01(currency_feature),
               MATH_AGENT.map01(consensus_feature))

    # World-drift smoothing uses alpha=0.05 here vs the agent's default 0.03
    # INTENTIONALLY. Evidence-uncertainty series evolve at the evidence
    # ingestion cadence, not the sustained-trend cadence, so 0.05 keeps the
    # drift signal reactive to real regime changes. Do not unify these values
    # without an explicit justification.
    drift = MATH_AGENT.world_drift(uncertainties, alpha=0.05) if len(uncertainties) >= 2 else {"ok": True, "reason": None, "equilibrium": uncertainties[0] if uncertainties else None, "drift": 0.0}
    coherence = MATH_AGENT.world_coherence(pattern)
    classification = MATH_AGENT.world_classify(pattern)
    prediction = MATH_AGENT.world_predict(
        pattern, MATH_AGENT.world_normalize(pattern))

    stable = (world["ok"] and report["ok"] and drift["ok"]
              and coherence["ok"] and classification["ok"] and prediction["ok"])
    return {
        "status": "stable" if stable else "review",
        "evidence_count": len(rows),
        "uncertainty_domain_ok": bool(world["ok"]),
        "uncertainty_std": world["std"],
        "world_pattern": pattern,
        "stale_records": stale,
        "conflict_flagged_records": conflicts,
        "drift": drift,
        "coherence": coherence,
        "classification": classification,
        "prediction": prediction,
        "violations": report["violations"],
        "world_stability": world,
    }


def mathematical_analysis(limit: int = 200) -> dict:
    """Read-only mathematical analysis of stored evidence, computed through
    the 8F mathematical substrate.

    Builds a claim/source graph, detects genuine contradictions with the
    logic domain, aggregates belief into a deterministic distribution with
    entropy, measures the information gain of a source split, and summarises
    per-source uncertainty statistics. It never writes, never forecasts and
    never asserts truth: it is a structural description, plainly labelled.

    Rows are passed into the substrate; the substrate reads no files and no
    clocks, so the output is deterministic for a fixed evidence file.
    """
    from maya_math.evidence import analyze_evidence
    rows = list_evidence(limit)
    analysis = analyze_evidence(rows)
    analysis["status"] = "mathematical_analysis"
    analysis["additive_only"] = True
    analysis["existing_conflicts_preserved"] = True
    return analysis


def _rounded(value, digits: int = 6):
    """Bound a numeric digest value: finite floats are rounded, everything
    else degrades to None so no non-finite number can reach the loop frame."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return round(float(value), digits)
    return None


def world_structure_summary(world_series: list | None = None, limit: int = 200) -> dict[str, Any]:
    """Deterministic, read-only digest of the stored world ledger, plus a
    bounded fold of a runtime world-observation series.

    This is the runtime/evidence bridge entry point: the intelligence loop
    calls it when a live ``world_series`` is present, so each observation
    tick is weighed against what the ledger structurally holds. It never
    writes, never reads clocks and never asserts truth; the output is fixed
    for a fixed ledger file.
    """
    structure = mathematical_analysis(limit=limit)
    digest = {
        "status": "world_ledger_digest",
        "category": "runtime_observation_fold_over_review_only_evidence",
        "evidence_count": int(structure.get("evidence_count", 0)),
        "claim_count": int(structure.get("claim_count", 0)),
        "source_count": int(structure.get("source_count", 0)),
        "contradiction_pairs": len(structure.get("contradictions") or []),
        "belief_entropy_bits": _rounded(
            (structure.get("belief") or {}).get("entropy_bits", 0.0)),
        "belief_normalized_entropy": _rounded(
            (structure.get("belief") or {}).get("normalized_entropy", 0.0)),
        "information_gain_by_source": _rounded(
            structure.get("information_gain_by_source", 0.0)),
        "structure_fixpoint": bool(
            (structure.get("invariants") or {}).get("structural_fixpoint",
                                                    False)),
        "all_finite": bool((structure.get("invariants") or {})
                           .get("all_finite", False)),
        "notes": "structural comparison only; never writes, never forecasts, never asserts truth",
    }
    values = None
    if world_series is not None:
        values = [float(v) for v in world_series
                  if isinstance(v, (int, float)) and not isinstance(v, bool)
                  and math.isfinite(float(v))
                  and v is not None]
    if values and len(values) >= 2:
        from maya_identity.wireframe.math_coordinator import MATH_AGENT
        verdict = MATH_AGENT.world_stability(values)
        digest["runtime_series"] = {
            "n": len(values),
            "std": _rounded(verdict.get("std", 0.0)),
            "stable": bool(verdict.get("ok", False)),
        }
    else:
        digest["runtime_series"] = None
    return digest

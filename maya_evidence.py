"""Provenance drilldown for Maya's research and world-model answers.

Research answers are synthesized from transient public sources, so each
source row gets a stable, content-derived evidence ID (a short hash of
url + excerpt), and this module owns the answer registry — one JSONL file
(knowledge/evidence_registry.jsonl) with a single writer (register_answer,
idempotent and capped) and a single reader (load_answers).

World-model rows already carry stable UUID evidence IDs and are read
through the store's public ``read_evidence`` door — never duplicated.

``drilldown`` and ``show_sources`` are pure renderers over the registry
and world data: they read and format existing provenance; they never
write, never update confidence, and never decide truth. ``now`` injects
the freshness clock for deterministic checks.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REGISTRY_FILE = ROOT / "knowledge" / "evidence_registry.jsonl"
REGISTRY_MAX_ANSWERS = 50
PREFIX_MIN = 8
ID_PREFIX = "ev-"


def evidence_id_for_row(url="", snippet="") -> str:
    """Deterministic evidence ID from the row's identifying content.

    URL plus excerpt fully identify one source row, so the same row always
    yields the same ID across sessions, processes, and capture paths (cache
    replay or summary parsing); any content change yields a new ID, so an
    ID never silently covers different text.
    """
    material = "%s|%s" % (str(url or "").strip().lower(), " ".join(str(snippet or "").split()))
    return ID_PREFIX + hashlib.sha256(material.encode("utf-8")).hexdigest()[:10]


def register_answer(topic, rows, meta=None, session_id=None, registry_path=None) -> dict:
    """Record one research answer's source provenance in the registry.

    This module owns the registry file (knowledge/evidence_registry.jsonl)
    as its single state: one writer (this function — idempotent for an
    identical answer, capped to the most recent REGISTRY_MAX_ANSWERS) and
    hermetic tests via the injectable ``registry_path``. Analysis
    (conflicts, answer-level status and confidence) is delegated to the
    research module, whose helpers produced the answer itself. Best-effort:
    it never raises and never blocks the answer.
    """
    path = Path(registry_path) if registry_path else REGISTRY_FILE
    source_rows = [dict(row or {}) for row in (rows or []) if isinstance(row, dict)]
    if not source_rows:
        return {"status": "nothing_registered", "reason": "answer had no usable sources"}
    meta = dict(meta or {})
    try:
        from maya_web_research import _conflict_index_map, analyze_rows
        conflict_map = _conflict_index_map(source_rows)
        analysis = analyze_rows(source_rows, conflict_map=conflict_map)
    except Exception:
        conflict_map, analysis = {}, {"status": "unknown", "confidence": "unknown", "belief": 0.0}
    entries = []
    for index, row in enumerate(source_rows):
        entries.append({
            "evidence_id": evidence_id_for_row(row.get("url", ""), row.get("snippet", "")),
            "url": row.get("url", ""),
            "title": row.get("title", ""),
            "host": row.get("host", ""),
            "class": row.get("class", "general"),
            "tier": row.get("tier", "medium"),
            "belief": row.get("belief"),
            "snippet": row.get("snippet", ""),
            "retrieved_at": row.get("retrieved_at") or meta.get("retrieved_at", ""),
            "conflict_indexes": conflict_map.get(index, []),
        })
    answer = {
        "kind": "research_answer",
        "topic": str(topic or "").strip(),
        "recorded_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "session_id": session_id,
        "answer_status": analysis["status"],
        "answer_confidence": analysis["confidence"],
        "answer_belief": analysis["belief"],
        "sources": entries,
    }
    existing = load_answers(path)
    answer_ids = [e["evidence_id"] for e in entries]
    for old in existing:
        if (old.get("kind") == "research_answer"
                and old.get("topic") == answer["topic"]
                and [s.get("evidence_id") for s in old.get("sources", [])] == answer_ids):
            return {"status": "already_registered", "evidence_ids": answer_ids}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        kept = existing[-(REGISTRY_MAX_ANSWERS - 1):] + [answer]
        text = "".join(json.dumps(a, ensure_ascii=False) + "\n" for a in kept)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(str(tmp), str(path))
    except OSError:
        return {"status": "not_registered", "reason": "registry write failed"}
    return {"status": "registered", "evidence_ids": answer_ids}


def load_answers(registry_path=None) -> list[dict]:
    """Read persisted research answers (newest last) from the registry.

    The one reader for the registry file this module owns; renderers take
    the result as injected data so they stay pure.
    """
    path = Path(registry_path) if registry_path else REGISTRY_FILE
    if not path.exists():
        return []
    rows = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                rows.append(item)
    except OSError:
        return []
    return rows


def _freshness_text(retrieved_at, now=None) -> str:
    try:
        from maya_world_model import evidence_freshness
        fresh = evidence_freshness({"retrieved_at": str(retrieved_at or "")}, now=now)
    except Exception:
        return "unknown (freshness lookup unavailable)"
    if fresh.get("status") == "unknown":
        return "unknown (%s)" % fresh.get("reason", "timestamp missing or invalid")
    return "%s (%s days old; review window %s days)" % (
        fresh.get("status"), fresh.get("age_days"), fresh.get("refresh_after_days"))


def _world_match(query: str):
    from maya_world_model import read_evidence
    rows = read_evidence()
    exact = [row for row in rows if str(row.get("evidence_id", "")) == query]
    if exact:
        return exact[0], None
    candidates = [row for row in rows
                  if str(row.get("evidence_id", "")).startswith(query)
                  and len(query) >= PREFIX_MIN]
    if len(candidates) == 1:
        return candidates[0], None
    if len(candidates) > 1:
        return None, "ambiguous ID prefix '%s' matches %d records; use a longer ID." % (
            query, len(candidates))
    return None, None


def _research_match(query: str, answers: list[dict]):
    """Return (source_entry, parent_answer, error) for a persisted answer."""
    matches = []
    for answer in answers:
        for source in answer.get("sources", []):
            if str(source.get("evidence_id", "")) == query:
                matches.append((source, answer))
    if matches:
        return matches[-1][0], matches[-1][1], None
    if len(query) >= PREFIX_MIN:
        prefixed = []
        for answer in answers:
            for source in answer.get("sources", []):
                if str(source.get("evidence_id", "")).startswith(query):
                    prefixed.append((source, answer))
        if len(prefixed) == 1:
            return prefixed[0][0], prefixed[0][1], None
        if len(prefixed) > 1:
            return None, None, "ambiguous ID prefix '%s' matches %d records; use a longer ID." % (
                query, len(prefixed))
    return None, None, None


def _world_drilldown(row: dict, now=None) -> str:
    conflicts = str(row.get("conflict_status", "unknown"))
    with_ids = row.get("conflicts_with") or []
    conflict_line = conflicts + (" (flagged against: %s)" % ", ".join(with_ids) if with_ids else "")
    lines = [
        "Evidence %s (world model)" % str(row.get("evidence_id", "?")),
        "Claim: %s" % str(row.get("claim", "")),
        "Source: %s%s" % (row.get("source", ""), " (%s)" % row["source_url"] if row.get("source_url") else ""),
        "Type: %s | Confidence: %s" % (row.get("evidence_type", ""), row.get("confidence", "")),
        "Retrieved: %s | Published: %s" % (row.get("retrieved_at", "") or "unrecorded",
                                           row.get("published_at") or "unrecorded"),
        "Freshness: %s" % _freshness_text(row.get("retrieved_at"), now=now),
        "Conflicts: %s" % conflict_line,
        "Uncertainty: %s" % (row.get("uncertainty", "") or "Not recorded."),
        "Visibility: %s | Memory update: %s | External action: %s" % (
            row.get("visibility", ""), row.get("memory_update", ""), row.get("external_action", "")),
    ]
    return "\n".join(lines)


def _research_drilldown(source: dict, answer: dict, now=None) -> str:
    mates = source.get("conflict_indexes") or []
    all_sources = answer.get("sources", [])
    if mates:
        mate_ids = [all_sources[m].get("evidence_id", "?") for m in mates
                    if isinstance(m, int) and 0 <= m < len(all_sources)]
        conflict_line = "flagged as contradicting %s within the same answer" % ", ".join(mate_ids)
    else:
        conflict_line = "no contradiction detected among this answer's sources"
    lines = [
        "Evidence %s (research)" % source.get("evidence_id", "?"),
        "Topic: %s" % answer.get("topic", ""),
        "Supports: %s" % (" ".join(str(source.get("snippet", "")).split()) or "No readable excerpt."),
        "Source: %s%s" % (source.get("url", ""), " (%s)" % source["title"] if source.get("title") else ""),
        "Type: %s | Confidence: %s%s" % (
            source.get("class", "general"), source.get("tier", "medium"),
            " (belief %s)" % source.get("belief") if source.get("belief") is not None else ""),
        "Retrieved: %s" % (source.get("retrieved_at", "") or "unrecorded"),
        "Freshness: %s" % _freshness_text(source.get("retrieved_at"), now=now),
        "Conflicts: %s" % conflict_line,
        "Answer context: status %s, confidence %s (%s); answered %s%s" % (
            answer.get("answer_status", "unknown"), answer.get("answer_confidence", "unknown"),
            answer.get("answer_belief", "?"), answer.get("recorded_at", ""),
            ", session %s" % answer["session_id"] if answer.get("session_id") else ""),
    ]
    return "\n".join(lines)


def drilldown(evidence_id, answers=None, now=None) -> str:
    """Expand one evidence ID (persisted research answer or world model)
    into its full provenance: source, timestamps, confidence, conflicts,
    freshness.

    ``answers`` optionally supplies persisted research-answer records (as
    loaded by ``load_answers``); without them only world-model IDs resolve.
    ``now`` injects the freshness clock for deterministic checks.
    """
    query = str(evidence_id or "").strip()
    if not query or query.lower() == "help":
        return ("Evidence drilldown: use `:evidence <id>` with an ID from a research answer "
                "or `:world list`, or `show sources` to list recent answered questions. "
                "An unambiguous ID prefix (8+ characters) is accepted.")
    source, answer, error = _research_match(query, list(answers or []))
    if error:
        return error
    if source is not None:
        return _research_drilldown(source, answer, now=now)
    row, error = _world_match(query)
    if error:
        return error
    if row is not None:
        return _world_drilldown(row, now=now)
    return ("No evidence record matches '%s'. Use `show sources` for recent research answers "
            "or `:world list` for world-model IDs." % query)


def show_sources(answers=None) -> str:
    """List recent research answers with their stable evidence IDs.

    ``answers`` are the persisted research-answer records, newest last;
    pure presentation over caller-supplied data.
    """
    answers = list(answers or [])
    if not answers:
        return ("No research answers are registered yet. Ask Maya to research a topic; each "
                "answer's sources are then listed here with stable evidence IDs.")
    answers = answers[-20:][::-1]
    lines = ["Recent research answers (newest first; use :evidence <id> for full provenance):"]
    for position, answer in enumerate(answers, start=1):
        ids = ", ".join(str(s.get("evidence_id", "?")) for s in answer.get("sources", []))
        lines.append("%d. [%s] %s — %d source(s), status %s, confidence %s (%s), answered %s" % (
            position, "research", answer.get("topic", ""), len(answer.get("sources", [])),
            answer.get("answer_status", "unknown"), answer.get("answer_confidence", "unknown"),
            answer.get("answer_belief", "?"), answer.get("recorded_at", "")))
        lines.append("   Evidence IDs: %s" % (ids or "none"))
    lines.append("%d answer(s) retained in the conversation record" % len(answers))
    return "\n".join(lines)

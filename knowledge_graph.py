"""Knowledge network runtime (restoration increment).

First persisted claim->source graph over Maya's neutral stores. Edges are
derived deterministically from records that already carry provenance
(``maya_world_evidence.jsonl`` and the approved answer registry), written to
``knowledge/graph_edges.jsonl`` review-only and only while the core service
is live (the same gate the research cache uses), and rendered or traversed
by the chat commands. It never fabricates a relation the stores do not
contain: every edge is a labelled copy of fields already on disk.

Deterministic: no wall clock, no randomness beyond the stored retrieval
timestamps, and every listing is sorted. Read-only for the human: no
trusted-memory update is ever recorded.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EDGE_FILE = ROOT / "knowledge" / "graph_edges.jsonl"
WORLD_FILE = ROOT / "maya_world_evidence.jsonl"

_COPY_FIELDS = (
    "claim", "source", "source_url", "confidence", "evidence_type",
    "retrieved_at", "conflict_status", "memory_update", "visibility",
)


def _subject(claim):
    tokens = []
    for token in (claim or "").split():
        clean = "".join(ch.lower() for ch in token if ch.isalnum())
        if clean:
            tokens.append(clean)
        if len(tokens) >= 3:
            break
    return " ".join(tokens)


def _first_terms(text, limit=6):
    out = []
    for token in (text or "").split():
        clean = "".join(ch.lower() for ch in token if ch.isalnum())
        if clean and clean not in out:
            out.append(clean)
        if len(out) >= limit:
            break
    return out


def _world_rows():
    if not WORLD_FILE.exists():
        return []
    rows = []
    for line in WORLD_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows


def _answer_sources(answers):
    for answer in answers or []:
        topic = (answer or {}).get("topic") or ""
        if not topic:
            continue
        sources = answer.get("sources") or []
        if isinstance(sources, dict):
            sources = [sources]
        if not sources:
            sources = [answer]
        seen = set()
        for source in sources:
            if isinstance(source, str):
                url = source
            elif isinstance(source, dict):
                url = (source.get("url") or source.get("source_url")
                       or source.get("source") or "")
            else:
                url = ""
            if not url or url in seen:
                continue
            seen.add(url)
            yield topic, url, answer


def build_edges():
    """Deterministic, de-duplicated edge list over the neutral stores."""
    edges = []
    seen = set()

    def add(edge):
        key = (edge.get("kind"), edge.get("subject"),
               edge.get("claim"), edge.get("source_url") or edge.get("source"))
        if key in seen:
            return
        seen.add(key)
        edges.append(edge)

    for row in _world_rows():
        claim = row.get("claim") or ""
        if claim:
            edge = {"kind": "source_claim", "subject": _subject(claim),
                    "provenance": "world_evidence", "review_only": True}
            for field in _COPY_FIELDS:
                if field in row:
                    edge[field] = row[field]
            add(edge)
        for other in (row.get("conflicts_with") or []):
            if isinstance(other, dict):
                other_claim = other.get("claim")
            else:
                other_claim = other
            add({
                "kind": "contradiction",
                "subject": _subject(claim),
                "claim_a": claim,
                "claim_b": str(other_claim or ""),
                "source": row.get("source"),
                "source_url": row.get("source_url"),
                "provenance": "world_evidence",
                "conflict_status": row.get("conflict_status",
                                           "conflict_detected"),
                "review_only": True,
            })

    try:
        from maya_evidence import load_answers
        answers = load_answers()
    except Exception:
        answers = []
    for topic, url, answer in _answer_sources(answers):
        add({
            "kind": "answer_source",
            "subject": _subject(topic),
            "claim": topic,
            "source": url,
            "source_url": url,
            "confidence": answer.get("answer_confidence"),
            "answer_status": answer.get("answer_status"),
            "provenance": "answer_registry",
            "review_only": True,
        })

    edges.sort(key=lambda e: (e.get("kind"), e.get("subject"),
                              e.get("claim"),
                              e.get("source_url") or e.get("source") or ""))
    return edges


def count_edges(edges=None):
    edges = build_edges() if edges is None else edges
    counts = {}
    for edge in edges:
        kind = edge.get("kind")
        counts[kind] = counts.get(kind, 0) + 1
    return counts


def persist_edges(edges=None):
    """Write the derived edges only while the core service is live.

    Returns ``{"written": n, "reason": ...}``. Never writes during offline
    runs or tests (service pid is None there), mirroring the research cache
    gate. The rewrite is deterministic for a fixed set of stores.
    """
    try:
        import maya_service
        pid = maya_service.running_pid()
    except Exception:
        return {"written": 0, "reason": "no_service_module"}
    if not pid:
        return {"written": 0, "reason": "service_offline"}
    edges = build_edges() if edges is None else edges
    try:
        EDGE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with EDGE_FILE.open("w", encoding="utf-8") as handle:
            for edge in edges:
                handle.write(json.dumps(edge, ensure_ascii=False) + "\n")
    except OSError:
        return {"written": 0, "reason": "write_failed"}
    return {"written": len(edges), "reason": "service_live"}


def render_graph(term=None, edges=None):
    """Render the derived graph, optionally narrowing to connected edges
    whose claim or source references every token of ``term``. Read-only.
    """
    edges = build_edges() if edges is None else edges
    persisted = EDGE_FILE.exists()
    lines = [
        "Knowledge network (%s):" % (
            "persisted to %s" % EDGE_FILE if persisted
            else "derived from neutral stores, not yet persisted")
    ]
    counts = count_edges(edges)
    if counts:
        lines.append("  edges: " + ", ".join(
            "%s=%d" % (key, counts[key]) for key in sorted(counts)))
    else:
        lines.append("  edges: none")
    term_tokens = _first_terms(term, limit=4) if term else []
    if term_tokens:
        matched = []
        for edge in edges:
            hay = " ".join([
                str(edge.get("subject") or ""),
                str(edge.get("claim") or ""),
                str(edge.get("claim_a") or ""),
                str(edge.get("claim_b") or ""),
                str(edge.get("source") or ""),
                str(edge.get("source_url") or ""),
            ]).lower()
            if all(token in hay for token in term_tokens):
                matched.append(edge)
        lines.append("Connected edges for '%s':" % term)
        if not matched:
            lines.append("  none - nothing in the neutral stores references "
                         "that term yet.")
        for edge in matched[:12]:
            claim = (edge.get("claim") or edge.get("claim_a") or "")
            lines.append("  %s <- %s (%s)" % (
                claim, edge.get("source") or edge.get("source_url"),
                edge.get("kind")))
    else:
        lines.append("  total edges: %d" % len(edges))
    lines.append("Read-only view; derived records are review-only, carry "
                 "provenance, and record no trusted memory update.")
    return "\n".join(lines)
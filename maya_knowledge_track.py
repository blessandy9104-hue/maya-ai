"""Bounded, source-linked learning tracks for subjects Andy follows."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from maya_learning import learning_status, record_signal
from maya_research import research_url

ROOT = Path(__file__).resolve().parent
TRACKS = ROOT / "knowledge" / "subject_tracks.json"
TRACK_NOTES = ROOT / "knowledge" / "subject_learning_notes.jsonl"

SUBJECT_CATALOG = {
    "philosophy": {
        "description": "Structured study of philosophical traditions, arguments, concepts, and major thinkers.",
        "subtopics": [
            "ethics", "epistemology", "metaphysics", "logic", "philosophy of mind",
            "philosophy of language", "political philosophy", "philosophy of science",
            "ancient philosophy", "medieval philosophy", "modern philosophy",
            "continental philosophy", "analytic philosophy", "chinese philosophy",
            "indian philosophy", "islamic philosophy",
        ],
        "sources": [
            "https://plato.stanford.edu/",
            "https://iep.utm.edu/",
        ],
    }
}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _load():
    try:
        data = json.loads(TRACKS.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"tracks": {}}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {"tracks": {}}


def _save(data):
    TRACKS.parent.mkdir(parents=True, exist_ok=True)
    TRACKS.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def learn_subject(subject: str) -> str:
    subject = " ".join(subject.lower().split())
    if learning_status().get("mode") != "learning":
        return "Subject learning is paused. Wake Maya first with: python3 maya_control.py wake"
    catalog = SUBJECT_CATALOG.get(subject)
    if not catalog:
        available = ", ".join(sorted(SUBJECT_CATALOG))
        return f"I do not have a configured learning track for {subject!r}. Available tracks: {available}."

    data = _load()
    track = data.setdefault("tracks", {}).setdefault(subject, {
        "status": "active",
        "description": catalog["description"],
        "subtopics": {name: {"evidence": 0, "confidence": "low"} for name in catalog["subtopics"]},
        "sources": catalog["sources"],
        "cycles": 0,
        "last_cycle": None,
    })
    results = []
    for url in catalog["sources"]:
        result = research_url(url)
        results.append({"url": url, "result": result[:400]})
    for topic in catalog["subtopics"]:
        record_signal(topic, f"subject_track:{subject}")
    track["cycles"] = int(track.get("cycles", 0)) + 1
    track["last_cycle"] = _now()
    _save(data)
    with TRACK_NOTES.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({
            "timestamp": _now(), "subject": subject, "cycle": track["cycles"],
            "source_results": results, "status": "unreviewed_for_synthesis",
        }, ensure_ascii=False) + "\n")
    return (
        f"Completed learning cycle {track['cycles']} for {subject}. "
        f"Reviewed {len(catalog['sources'])} configured reference sources and recorded "
        f"{len(catalog['subtopics'])} provisional subtopic signals locally. "
        "The notes remain unreviewed and did not change permanent memory or code."
    )


def track_summary() -> str:
    data = _load().get("tracks", {})
    if not data:
        return "No subject-learning tracks have been started."
    lines = ["Subject-learning tracks:"]
    for subject, track in data.items():
        lines.append(f"- {subject}: {track.get('cycles', 0)} cycle(s), last run {track.get('last_cycle', 'never')}")
    lines.append("Source notes remain local and unreviewed until Maya synthesizes them with citations.")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    if len(sys.argv) == 2 and sys.argv[1] == "tracks":
        print(track_summary())
    elif len(sys.argv) == 3 and sys.argv[1] == "learn":
        print(learn_subject(sys.argv[2]))
    else:
        print("Usage: python3 maya_knowledge_track.py [tracks|learn SUBJECT]")
        raise SystemExit(2)

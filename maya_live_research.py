"""Explicit live topic lookup with a narrow, read-only source policy."""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
POLICY = ROOT / "evolution" / "network_policy.json"
LOG = ROOT / "knowledge" / "live_lookup_notes.jsonl"


def _now():
    return datetime.now(timezone.utc).isoformat()


def _policy():
    try:
        return json.loads(POLICY.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _title(topic: str) -> str:
    cleaned = re.sub(r"[^\w\s-]", " ", topic, flags=re.UNICODE)
    return " ".join(cleaned.split()).strip().title()


def live_lookup(topic: str, show_source: bool = False) -> str:
    topic = " ".join(topic.split()).strip()
    if not topic:
        return "Tell me the topic you want me to look up live."
    policy = _policy()
    if policy.get("enabled") is not True or policy.get("mode") != "read_only":
        return "Live lookup is disabled because the local network policy is not in read-only mode."
    host = "en.wikipedia.org"
    if host not in policy.get("allowed_hosts", []):
        return "Live lookup is disabled because its reference host is not allow-listed."
    page = urllib.parse.quote(_title(topic), safe="")
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{page}"
    request = urllib.request.Request(url, headers={"User-Agent": "Maya-Explicit-Live-Lookup/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=int(policy.get("timeout_seconds", 10))) as response:
            raw = response.read(int(policy.get("max_bytes", 200000)) + 1)
        if len(raw) > int(policy.get("max_bytes", 200000)):
            return "Live lookup was blocked because the response was too large."
        data = json.loads(raw.decode("utf-8", "replace"))
    except Exception as error:
        return f"Live lookup failed safely: {error}"
    extract = data.get("extract")
    if not extract:
        return f"I could not find a live reference summary for {topic!r}."
    source_url = data.get("content_urls", {}).get("desktop", {}).get("page", url)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({
            "timestamp": _now(), "topic": topic, "source_url": source_url,
            "source": "explicit_live_lookup", "memory_update": "not_performed",
        }, ensure_ascii=False) + "\n")
    answer = f"{extract}\n\n"
    if show_source:
        answer += f"Source: {source_url}\n"
    return answer.strip()


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python3 maya_live_research.py TOPIC [--source]")
        raise SystemExit(2)
    args = sys.argv[1:]
    show_source = "--source" in args
    args = [arg for arg in args if arg != "--source"]
    print(live_lookup(" ".join(args), show_source=show_source))

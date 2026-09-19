"""Read-only, allow-listed web research for an active Maya learning session."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

from maya_learning import learning_status, record_signal

ROOT = Path(__file__).resolve().parent
POLICY = ROOT / "evolution" / "network_policy.json"
NOTES = ROOT / "knowledge" / "research_notes.jsonl"


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() in {"script", "style", "noscript", "svg"}:
            self._skip += 1

    def handle_endtag(self, tag):
        if tag.lower() in {"script", "style", "noscript", "svg"} and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip and data.strip():
            self.parts.append(" ".join(data.split()))


def _now():
    return datetime.now(timezone.utc).isoformat()


def _allowed(url: str) -> bool:
    try:
        policy = json.loads(POLICY.read_text(encoding="utf-8"))
        parsed = urlparse(url)
        return (
            policy.get("enabled") is True
            and policy.get("mode") == "read_only"
            and parsed.scheme == "https"
            and parsed.hostname in policy.get("allowed_hosts", [])
        )
    except (OSError, json.JSONDecodeError):
        return False


def research_url(url: str) -> str:
    status = learning_status()
    if status.get("mode") != "learning":
        return "Research is paused. Wake Maya first with: python3 maya_control.py wake"
    if not _allowed(url):
        return "Blocked: the URL is not an enabled HTTPS host in evolution/network_policy.json."
    try:
        result = subprocess.run(
            [sys.executable, str(ROOT / "net_fetch.py"), url],
            cwd=str(ROOT), capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "Research failed safely: the local fetcher did not respond in time."
    if result.returncode != 0:
        return "Research blocked or failed safely: " + (result.stderr.strip() or "unknown fetch error")
    raw = result.stdout
    parser = TextExtractor()
    parser.feed(raw)
    text = " ".join(parser.parts)
    preview = text[:1600]
    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if NOTES.exists():
        try:
            for line in NOTES.read_text(encoding="utf-8").splitlines():
                old = json.loads(line)
                if old.get("url") == url and old.get("content_hash") == content_hash:
                    return f"Already recorded this unchanged note from {urlparse(url).hostname}; no duplicate was created."
        except (OSError, json.JSONDecodeError):
            pass
    NOTES.parent.mkdir(parents=True, exist_ok=True)
    note = {
        "timestamp": _now(),
        "url": url,
        "host": urlparse(url).hostname,
        "chars": len(text),
        "content_hash": content_hash,
        "preview": preview,
        "status": "unreviewed_local_note",
        "memory_update": "not_performed",
    }
    with NOTES.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(note, ensure_ascii=False) + "\n")
    host = urlparse(url).hostname or "unknown source"
    record_signal(host, "approved_web_source", url)
    return (
        f"Fetched a read-only note from {host}. It was saved locally for review; "
        "it did not change Maya’s permanent memory or code.\n\n"
        + preview
    )


def main():
    if len(sys.argv) != 2:
        print("Usage: python3 maya_research.py https://allowed-host/path")
        raise SystemExit(2)
    print(research_url(sys.argv[1]))


if __name__ == "__main__":
    main()

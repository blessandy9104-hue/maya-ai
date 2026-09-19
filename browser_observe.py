"""Explicitly gated, read-only browser-tab observation.

This script is intentionally blocked by default. It must satisfy all three
conditions before reading the local Chrome DevTools tab list:
1. observation_policy.json explicitly enables browser_tabs;
2. maya_activation_state.json says the user activated Presence Mode; and
3. the policy remains local-only with raw content disabled.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
POLICY_PATH = ROOT / "observation_policy.json"
ACTIVATION_PATH = ROOT / "maya_activation_state.json"
NETWORK_POLICY_PATH = ROOT / "evolution" / "network_policy.json"
OUTPUT_PATH = ROOT / "evolution" / "browser_observations.json"


def _read(path: Path, default: dict) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else default
    except (OSError, json.JSONDecodeError):
        return default


def main() -> int:
    observation_policy = _read(POLICY_PATH, {})
    enabled_sources = observation_policy.get("enabled_sources", {})
    activation = _read(ACTIVATION_PATH, {})

    if not observation_policy.get("local_only"):
        print("OBSERVATION_BLOCKED: local-only policy is not enabled")
        return 2
    if observation_policy.get("storage", {}).get("raw_content", True):
        print("OBSERVATION_BLOCKED: raw content storage is enabled")
        return 2
    if enabled_sources.get("browser_tabs") is not True:
        print("OBSERVATION_BLOCKED: browser_tabs is disabled in observation_policy.json")
        return 2
    if activation.get("active") is not True or activation.get("presence_mode") is not True:
        print("OBSERVATION_BLOCKED: Presence Mode must be explicitly active")
        return 2

    network_policy = _read(NETWORK_POLICY_PATH, {})
    allowed_hosts = set(network_policy.get("allowed_hosts", []))
    try:
        with urllib.request.urlopen("http://127.0.0.1:9222/json/list", timeout=5) as response:
            tabs = json.load(response)
    except Exception as exc:
        print(f"OBSERVATION_UNAVAILABLE: {type(exc).__name__}")
        return 3

    rows = []
    for tab in tabs if isinstance(tabs, list) else []:
        url = tab.get("url", "")
        host = urlparse(url).hostname
        if host in allowed_hosts:
            rows.append({
                "title": tab.get("title", ""),
                "url": url,
                "host": host,
                "type": tab.get("type"),
            })

    OUTPUT_PATH.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("Allowed browser observations:", len(rows))
    for row in rows:
        print(row["host"], row["title"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

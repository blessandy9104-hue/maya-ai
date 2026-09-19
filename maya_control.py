"""Explicit controls for Maya's availability and supervised learning session."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from maya_learning import interest_summary, learning_status, set_learning_mode
from maya_knowledge_track import learn_subject, track_summary


def main() -> int:
    command = sys.argv[1].lower() if len(sys.argv) > 1 else "status"
    if command in {"wake", "start"}:
        status = set_learning_mode("learning")
        print("Maya is awake and learning from approved local signals.")
        print(json.dumps(status, indent=2))
        return 0
    if command in {"sleep", "stop"}:
        status = set_learning_mode("sleeping")
        print("Maya learning is stopped. Background availability may remain enabled separately.")
        print(json.dumps(status, indent=2))
        return 0
    if command == "status":
        print(json.dumps(learning_status(), indent=2))
        return 0
    if command in {"interests", "interest"}:
        print(interest_summary())
        return 0
    if command in {"tracks", "knowledge-tracks"}:
        print(track_summary())
        return 0
    if command == "learn":
        subject = " ".join(sys.argv[2:]).strip()
        if not subject:
            print("Usage: python3 maya_control.py learn SUBJECT")
            return 2
        print(learn_subject(subject))
        return 0
    print("Usage: python3 maya_control.py [wake|sleep|status|interests|tracks|learn SUBJECT]")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

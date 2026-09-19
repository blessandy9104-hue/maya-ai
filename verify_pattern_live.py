import json
from pathlib import Path

from maya_rules import fast_answer
from maya_chat import maya_local_command
from maya_pattern_mapping import pattern_map

ROOT = Path(__file__).resolve().parent


def main():
    before = {
        name: (ROOT / name).read_bytes() if (ROOT / name).exists() else b""
        for name in ("andy_profile.json", "maya_interest_profile.json", "knowledge/andy_interest_map.json")
    }
    natural = fast_answer("What opportunities fit my current interests and skills?", [])
    assert natural is not None
    assert "review only" in natural.lower()
    assert "not a probability" in natural.lower()
    assert "no memory" in natural.lower()

    command = maya_local_command(":pattern map")
    assert "Pattern map" in command
    assert "decision" in command.lower() or "no memory" in command.lower()

    negated = pattern_map("I do not want trading, purchases, or external action")
    assert negated["negation_terms_detected"]
    assert any("No memory" in line for line in ["No memory, permission, purchase, message, trade, or external action was performed."])

    for name, value in before.items():
        assert (ROOT / name).read_bytes() == value

    print(json.dumps({"status": "ok", "natural_fast_path": True, "command_route": True, "no_writes": True}))


if __name__ == "__main__":
    main()

from __future__ import annotations

import json
from pathlib import Path

from maya_pattern_mapping import pattern_map, render_pattern_map

ROOT = Path(__file__).resolve().parent

CASES = [
    ("map my opportunities", "candidates"),
    ("which paths fit coding and creative interests?", "technology"),
    ("I want research and philosophy learning options", "services"),
    ("I do not want trading or financial action", "negation"),
    ("privacy and local only", "constraints"),
    ("show probable paths", "uncertainty"),
    ("what patterns point me toward education?", "education"),
    ("I am unsure and may change direction", "uncertainty"),
    ("map opportunities for a small reversible experiment", "uncertainty"),
    ("do not assume this is my permanent interest", "uncertainty"),
]


def main():
    before = {}
    for name in ("andy_profile.json", "maya_interest_profile.json", "knowledge/andy_interest_map.json"):
        path = ROOT / name
        before[name] = path.read_bytes() if path.exists() else b""

    results = []
    for query, expected in CASES:
        result = pattern_map(query)
        rendered = render_pattern_map(query)
        assert result["status"] == "review_only"
        assert "not a calibrated probability" in " ".join(result["uncertainty"])
        assert "No memory" in rendered
        if expected == "candidates":
            passed = bool(result["candidates"])
        elif expected == "negation":
            passed = bool(result["negation_terms_detected"])
        elif expected == "constraints":
            passed = bool(result["constraints_detected"])
        elif expected == "uncertainty":
            passed = "not a probability" in rendered.lower()
        else:
            passed = any(item["category"] == expected for item in result["candidates"])
        results.append({"query": query, "expected": expected, "passed": passed})

    for name in before:
        path = ROOT / name
        after = path.read_bytes() if path.exists() else b""
        assert after == before[name], f"pattern mapping changed {name}"

    passed = sum(1 for item in results if item["passed"])
    report = {
        "status": "ok" if passed == len(results) else "review_required",
        "cases": len(results),
        "passed": passed,
        "coverage": round(passed / len(results), 2),
        "results": results,
        "note": "This is a deterministic behavior benchmark, not a claim of real-world predictive accuracy.",
    }
    print(json.dumps(report, ensure_ascii=False))
    assert passed == len(results), json.dumps(report)


if __name__ == "__main__":
    main()

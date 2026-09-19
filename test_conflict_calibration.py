import tempfile
from pathlib import Path

import maya_world_model as world

cases = [
    ("The library is open to students.", "The library is not open to students.", True),
    ("The project has a public roadmap.", "The project does not have a public roadmap.", True),
    ("Maya supports local review.", "Maya supports local review.", False),
    ("The weather is clear today.", "The computer has no available disk space.", False),
    ("The service is unavailable to new users.", "The service is available to existing users.", False),
    ("The report was published in June.", "The report was not published in June.", True),
]

with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    world.EVIDENCE_FILE = root / "evidence.jsonl"
    results = []
    for index, (positive, negative, expected_conflict) in enumerate(cases, 1):
        first = world.add_evidence(claim=positive, source=f"Calibration source {index}A", confidence="medium", evidence_type="observation")
        second = world.add_evidence(claim=negative, source=f"Calibration source {index}B", confidence="medium", evidence_type="observation")
        actual = second["evidence"].get("conflict_status") == "conflict_flagged"
        results.append((index, expected_conflict, actual, positive, negative))

hits = sum(expected == actual for _, expected, actual, _, _ in results)
false_flags = [item for item in results if not item[1] and item[2]]
misses = [item for item in results if item[1] and not item[2]]
print(f"cases={len(results)}")
print(f"hits={hits}")
print(f"calibration_rate={hits / len(results):.2f}")
print(f"false_flags={len(false_flags)}")
print(f"misses={len(misses)}")
for index, expected, actual, positive, negative in results:
    print(f"case_{index}: expected={expected} actual={actual}")
    if expected != actual:
        print(f"  positive={positive}")
        print(f"  negative={negative}")

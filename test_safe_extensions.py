from pathlib import Path
import json

from maya_context import rewrite_follow_up, relevant_context
from maya_emerging_interests import emerging_interest_review, emerging_interest_hypotheses

ROOT = Path(__file__).resolve().parent


def main():
    review = emerging_interest_review()
    assert "hypotheses only" in review
    assert "Nothing was saved" in review
    assert "lifestyle" not in review.lower()
    hypotheses = emerging_interest_hypotheses()
    assert hypotheses
    assert all(item["status"] == "unconfirmed" for item in hypotheses)
    assert all("next_step" in item for item in hypotheses)

    history = [{"role": "user", "content": "What opportunities fit my coding and creative interests?"}]
    rewritten = rewrite_follow_up("what about that?", history)
    assert "previous question" in rewritten
    assert history[0]["content"] in rewritten
    assert "requested answer length" in relevant_context(history)

    before = (ROOT / "knowledge" / "andy_interest_map.json").read_text(encoding="utf-8")
    _ = emerging_interest_review()
    after = (ROOT / "knowledge" / "andy_interest_map.json").read_text(encoding="utf-8")
    assert before == after
    print(json.dumps({"status": "ok", "hypotheses": len(hypotheses), "memory_unchanged": True}))


if __name__ == "__main__":
    main()

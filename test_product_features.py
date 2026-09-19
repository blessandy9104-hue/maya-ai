from pathlib import Path
import json

import maya_chat
from maya_product_features import (
    onboarding_interview, onboarding_answer, pattern_report,
    bookmark_opportunity, opportunity_bookmarks, memory_audit,
    memory_delete, next_reflection_prompt, add_reflection, contradiction_review,
)


def main():
    assert "5–7" not in onboarding_interview()  # questions are listed explicitly
    assert onboarding_answer(1, "I want to build useful tools.").startswith("Saved answer")
    assert "not approved memory" in onboarding_interview()
    assert "Weekly pattern report" in pattern_report()

    assert "marked saved" in bookmark_opportunity("A reviewed service brief")
    assert "A reviewed service brief" in opportunity_bookmarks()
    assert "marked dismissed" in bookmark_opportunity("A reviewed service brief", "dismissed")

    audit = memory_audit()
    assert "Memory audit" in audit
    assert "approved" in audit.lower()
    assert "confirm" in memory_delete("interests.making_money", "no")
    assert "nothing was deleted" in memory_delete("interests.making_money", "no").lower()

    first_prompt = next_reflection_prompt()
    assert "reflection prompt" in first_prompt.lower()
    assert "nothing is saved" in first_prompt.lower()
    assert "saved locally" in add_reflection("I want to explore a new direction.")
    contradiction = contradiction_review().lower()
    assert "contradiction" in contradiction or "no clear" in contradiction

    assert "onboarding interview" in maya_chat.maya_local_command(":onboarding").lower()
    assert "weekly pattern report" in maya_chat.maya_local_command(":pattern report").lower()
    assert "memory audit" in maya_chat.maya_local_command(":memory audit").lower()
    assert "reflection prompt" in maya_chat.maya_local_command(":reflection").lower()

    print(json.dumps({"status": "ok", "memory_delete_requires_confirmation": True, "router": "ok"}))


if __name__ == "__main__":
    main()

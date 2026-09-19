"""Regression test for Maya's local-vs-research command routing.

`route_local` and `maya_live_research.live_lookup` were removed in a later
refactor; deterministic commands now go through `maya_chat.maya_local_command`,
and topic lookups ("look up X", "research X", ...) route to
`maya_chat.maya_topic_research`, which calls the live web-research module
(`maya_web_research.research_topic`). This test checks the routing without
requiring live network access, since `test_maya_learning.py` and
`test_web_synthesis.py` already cover the live SOURCE: output end to end.
"""
from unittest.mock import patch

import maya_chat


def main():
    # A deterministic command must never look like a sourced research answer.
    answer = maya_chat.maya_local_command("help maya")
    assert "SOURCE:" not in answer, answer

    # "look up <topic>" phrasing must route to the topic-research path.
    fake_result = "SOURCE: https://en.wikipedia.org/wiki/Philosophy\nPhilosophy studies fundamental questions."
    with patch("maya_chat.maya_topic_research", return_value=fake_result) as mocked:
        routed = maya_chat.maya_local_command("look up philosophy")
    mocked.assert_called_once_with("philosophy")
    assert "SOURCE:" in routed, routed
    print("Live lookup routing test passed")


if __name__ == "__main__":
    main()
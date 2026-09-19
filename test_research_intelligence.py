"""Offline tests for Maya's research intelligence layer.

These tests exercise the deterministic core of the research pipeline
without any network access: source-class selection, relevance scoring,
duplicate removal, contradiction detection, confidence composition, and
the structured synthesis renderer. Live retrieval (``research_topic``)
is covered end-to-end by ``test_web_synthesis.py`` / ``test_maya_learning.py``
against the local network policy.
"""
from __future__ import annotations

import maya_web_research as r


ROWS_AGREEING = [
    {
        "url": "https://en.wikipedia.org/wiki/Philosophy",
        "host": "en.wikipedia.org",
        "class": "encyclopedic",
        "relevance": 1.0,
        "tier": "medium",
        "belief": 0.60,
        "snippet": "Philosophy is the systematic study of general and fundamental "
                    "questions about existence, reason, knowledge, value, mind, "
                    "and language.",
    },
    {
        "url": "https://plato.stanford.edu/entries/philosophy/",
        "host": "plato.stanford.edu",
        "class": "scholarly",
        "relevance": 0.95,
        "tier": "high",
        "belief": 0.85,
        "snippet": "Philosophy as a discipline encompasses the rational "
                    "investigation of the truths and principles of being, "
                    "knowledge, and conduct.",
    },
    {
        "url": "https://iep.utm.edu/philosophy/",
        "host": "iep.utm.edu",
        "class": "scholarly",
        "relevance": 0.92,
        "tier": "high",
        "belief": 0.85,
        "snippet": "Philosophy is a reasoned pursuit of fundamental truths, "
                    "often treated as a foundation of the liberal arts.",
    },
]

ROWS_CONFLICTING = [
    {
        "url": "https://en.wikipedia.org/wiki/Red_panda",
        "host": "en.wikipedia.org",
        "class": "encyclopedic",
        "relevance": 0.9,
        "tier": "medium",
        "belief": 0.60,
        "snippet": "The red panda does not hibernate in winter and is not a "
                    "member of the bear family.",
    },
    {
        "url": "https://en.wikipedia.org/wiki/Bear",
        "host": "en.wikipedia.org",
        "class": "encyclopedic",
        "relevance": 0.9,
        "tier": "medium",
        "belief": 0.60,
        "snippet": "The red panda hibernates in winter and is a member of "
                    "the bear family.",
    },
]

META = {
    "kind": "definition_or_information",
    "kind_confidence": 0.82,
    "classes": ["encyclopedic", "scholarly"],
    "source_notes": ["Wikipedia API", "Bing RSS"],
    "allowed_hosts": {"en.wikipedia.org", "plato.stanford.edu", "iep.utm.edu"},
    "retrieved_at": "2026-09-14T00:00:00+00:00",
}


def test_single_source_no_fake_confidence():
    result = r.research_summary("philosophy", ROWS_AGREEING[:1], META)
    assert "Status: supported (limited)" in result, result
    assert "Confidence:" in result, result
    assert "Single-source evidence; independent corroboration unavailable" in result, result
    assert "No trusted memory update occurred." in result, result
    print("single_source_failure=OK")


def test_multi_source_retrieval_plan():
    candidates = [
        {"url": "https://en.wikipedia.org/wiki/Philosophy", "title": "Philosophy - Wikipedia", "host": "en.wikipedia.org", "class": "encyclopedic"},
        {"url": "https://en.wikipedia.org/wiki/Doctor_of_Philosophy", "title": "Doctor of Philosophy - Wikipedia", "host": "en.wikipedia.org", "class": "encyclopedic"},
        {"url": "https://en.wikipedia.org/wiki/Philosophy#History", "title": "Philosophy - Wikipedia", "host": "en.wikipedia.org", "class": "encyclopedic"},
        {"url": "https://plato.stanford.edu/entries/philosophy/", "title": "Philosophy (SEP)", "host": "plato.stanford.edu", "class": "scholarly"},
        {"url": "https://iep.utm.edu/philosophy/", "title": "Philosophy (IEP)", "host": "iep.utm.edu", "class": "scholarly"},
        {"url": "https://docs.python.org/3/reference/index.html", "title": "Python reference", "host": "docs.python.org", "class": "technical"},
        {"url": "https://random-blog.example.com/philosophy", "title": "Random blog", "host": "random-blog.example.com", "class": "general"},
    ]
    deduped = r.dedupe_candidates(candidates)
    assert len(deduped) == 6, deduped
    assert not any(c["url"] == "https://en.wikipedia.org/wiki/Philosophy#History" for c in deduped)
    plan = r.plan_candidates("philosophy", deduped, META, allowed=META["allowed_hosts"])
    classes = [c["class"] for c in plan]
    assert "general" not in classes, classes
    assert classes.count("encyclopedic") <= 2, classes
    assert classes.count("scholarly") <= 2, classes
    assert any(c["class"] == "scholarly" for c in plan), classes
    assert "random-blog.example.com" not in [c["host"] for c in plan]
    print("multi_source_retrieval=OK")


def test_synthesis_structure():
    result = r.research_summary("philosophy", ROWS_AGREEING, META)
    assert "Core understanding (synthesized from 3 source(s))" in result, result
    assert "Evidence:" in result, result
    assert "1. Source:" in result, result
    assert "Type: scholarly" in result, result
    assert "Confidence:" in result, result
    assert "Supports:" in result, result
    assert "Research limitation:" in result, result
    assert "Status: supported" in result, result
    assert "No trusted memory update occurred." in result, result
    print("synthesis=OK")


def test_contradiction_detection():
    result = r.research_summary("panda hibernation", ROWS_CONFLICTING, META)
    assert "Status: disputed" in result, result
    assert "Contradiction" in result, result
    print("contradiction=OK")


def test_confidence_reporting():
    high = r.research_summary("philosophy", ROWS_AGREEING, META)
    assert "Confidence: high" in high, high
    low = r.research_summary("panda hibernation", ROWS_CONFLICTING, META)
    assert "Confidence: medium" in low, low
    assert "conflicting evidence lowers confidence" in low, low
    single = r.research_summary("philosophy", ROWS_AGREEING[:1], META)
    assert "single source, no independent corroboration" in single, single
    print("confidence_reporting=OK")


def test_irrelevant_source_rejection():
    junk_score = r.score_relevance(
        "red panda",
        "Turning Red (film)",
        "Turning Red is a 2022 computer-animated fantasy comedy film.")
    good_score = r.score_relevance(
        "red panda",
        "Red panda",
        "The red panda (Ailurus fulgens) is a small mammal native to the "
        "eastern Himalayas and southwestern China.")
    assert junk_score < good_score, (junk_score, good_score)
    assert good_score == 1.0, good_score
    assert r.accept_relevance(good_score, 2, 2) is True
    assert r.accept_relevance(junk_score, 1, 2) is False
    assert r._accept_evidence("red panda", "Red panda",
                              "The red panda (Ailurus fulgens) is a small mammal "
                              "native to the eastern Himalayas.") is True
    assert r._accept_evidence("red panda", "Turning Red (film)",
                              "Turning Red is a 2022 computer-animated fantasy "
                              "comedy film.") is False
    candidates = [
        {"url": "https://en.wikipedia.org/wiki/Red_panda", "title": "Red panda", "host": "en.wikipedia.org", "class": "encyclopedic"},
        {"url": "https://en.wikipedia.org/wiki/Turning_Red", "title": "Turning Red (film)", "host": "en.wikipedia.org", "class": "encyclopedic"},
    ]
    plan = r.plan_candidates("red panda", candidates, META, allowed=META["allowed_hosts"])
    assert plan[0]["url"] == "https://en.wikipedia.org/wiki/Red_panda", plan
    print("irrelevant_source_rejection=OK")


def test_source_class_selection():
    assert r.host_class("en.wikipedia.org") == "encyclopedic"
    assert r.host_class("plato.stanford.edu") == "scholarly"
    assert r.host_class("iep.utm.edu") == "scholarly"
    assert r.host_class("docs.python.org") == "technical"
    assert r.host_class("api.github.com") == "technical"
    assert r.host_class("example.com") == "general"
    philosophy = r.classify_query("what is philosophy?")
    assert "encyclopedic" in philosophy["classes"], philosophy
    assert "scholarly" in philosophy["classes"], philosophy
    technical = r.classify_query("python requests library api")
    assert "technical" in technical["classes"], technical
    assert r.tier_for("encyclopedic", 0.6) == ("medium", 0.6)
    assert r.tier_for("scholarly", 0.9)[0] == "high"
    print("source_class_selection=OK")


if __name__ == "__main__":
    test_single_source_no_fake_confidence()
    test_multi_source_retrieval_plan()
    test_synthesis_structure()
    test_contradiction_detection()
    test_confidence_reporting()
    test_irrelevant_source_rejection()
    test_source_class_selection()
    print("research_intelligence_suite=PASS")
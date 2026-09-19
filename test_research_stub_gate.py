"""Evidence-quality gate tests for the research pipeline.

Offline: exercises evidence_gate_decision, research_summary, _render_cached,
and a simulated full research_topic pipeline. No network, no LLM, no writes.
"""
from __future__ import annotations

import maya_web_research as r


META = {
    "kind": "definition_or_information",
    "kind_confidence": 0.82,
    "classes": ["encyclopedic", "scholarly"],
    "source_notes": ["Wikipedia API"],
    "allowed_hosts": {"en.wikipedia.org", "plato.stanford.edu"},
    "retrieved_at": "2026-09-15T00:00:00+00:00",
}

GOOD_ROW = {
    "url": "https://en.wikipedia.org/wiki/Carl_Jung",
    "host": "en.wikipedia.org",
    "class": "encyclopedic",
    "relevance": 0.95,
    "tier": "high",
    "belief": 0.85,
    "snippet": ("Carl Gustav Jung was a Swiss psychiatrist and psychoanalyst "
                "who founded analytical psychology."),
}

STUB_ROW = {
    "url": "https://en.wikipedia.org/wiki/Carl_Jung_publications",
    "host": "en.wikipedia.org",
    "class": "encyclopedic",
    "relevance": 0.88,
    "tier": "medium",
    "belief": 0.60,
    "snippet": "This is a list of writings published by Carl Jung.",
}


def test_reject_list_lead():
    d, reason = r.evidence_gate_decision(
        "This is a list of writings published by Carl Jung.")
    assert d == "REJECT", d
    assert reason == r.STUB_LIST_LEAD, reason
    print("reject_list_lead=OK")


def test_reject_following_list():
    d, _ = r.evidence_gate_decision(
        "The following is a list of episodes of the series.")
    assert d == "REJECT", d
    print("reject_following_list=OK")


def test_reject_below_list():
    d, _ = r.evidence_gate_decision(
        "Below is a list of characters appearing in the film.")
    assert d == "REJECT", d
    print("reject_below_list=OK")


def test_reject_disambiguation():
    d, reason = r.evidence_gate_decision(
        "In everyday speech and in grammar, ellipsis may refer to:")
    assert d == "REJECT", d
    assert reason == r.DISAMBIGUATION_LEAD, reason
    d2, _ = r.evidence_gate_decision(
        "This disambiguation page lists articles associated with the title X.")
    assert d2 == "REJECT", d2
    print("reject_disambiguation=OK")


def test_reject_stub_boilerplate():
    d, reason = r.evidence_gate_decision(
        "This article is a stub. You can help by expanding it.")
    assert d == "REJECT", d
    assert reason == r.STUB_BOILERPLATE, reason
    d2, _ = r.evidence_gate_decision(
        "This article does not cite any sources. Please help improve it.")
    assert d2 == "REJECT", d2
    print("reject_stub_boilerplate=OK")


def test_reject_empty_and_whitespace():
    for sample in ("", "   ", "\n\n", "  \t  "):
        d, reason = r.evidence_gate_decision(sample)
        assert d == "REJECT", (repr(sample), d)
        assert reason == r.NON_INFORMATIVE_LEAD, (repr(sample), reason)
    print("reject_empty=OK")


def test_reject_boilerplate_leads():
    for snippet in ("This is a book.", "This is a website.",
                    "This is a poem.", "This is a show.",
                    "This article is a game.", "This page is a song."):
        d, reason = r.evidence_gate_decision(snippet)
        assert d == "REJECT", (snippet, d)
        assert reason == r.NON_INFORMATIVE_LEAD, (snippet, reason)
    print("reject_boilerplate_leads=OK")


def test_accept_short_informative():
    samples = [
        "Socrates was a Greek philosopher from Athens who is credited as the founder of Western philosophy.",
        "Philosophy is the systematic study of general and fundamental questions about existence, reason, knowledge, value, mind, and language.",
        "The red panda (Ailurus fulgens) is a small mammal native to the eastern Himalayas and southwestern China.",
        "Turning Red is a 2022 computer-animated fantasy comedy film produced by Pixar.",
        ("This is a book about ancient Egyptian architecture and monumental "
         "building techniques employed during the Old Kingdom."),
        "John Smith (born 1953) is an American politician who served as mayor of Springfield.",
    ]
    for sample in samples:
        d, reason = r.evidence_gate_decision(sample)
        assert d == "ACCEPT", (sample[:60], d, reason)
    print("accept_short_informative=OK")


def test_accept_existing_fixtures():
    for row in [
        {"snippet": ("Philosophy is the systematic study of general and fundamental "
                     "questions about existence, reason, knowledge, value, mind, and language.")},
        {"snippet": ("Philosophy as a discipline encompasses the rational "
                     "investigation of the truths and principles of being, "
                     "knowledge, and conduct.")},
        {"snippet": ("Philosophy is a reasoned pursuit of fundamental truths, "
                     "often treated as a foundation of the liberal arts.")},
    ]:
        d, _ = r.evidence_gate_decision(row["snippet"])
        assert d == "ACCEPT", (row["snippet"][:40], d)
    print("accept_existing_fixtures=OK")


def test_contract_returns():
    d1, r1 = r.evidence_gate_decision("This is a list of writings published by Carl Jung.")
    assert isinstance(d1, str) and isinstance(r1, str), type((d1, r1))
    d2, r2 = r.evidence_gate_decision("Socrates was a philosopher.")
    assert d2 == "ACCEPT" and r2 is None, (d2, r2)
    print("contract=OK")


def test_summary_excludes_stub_and_shows_note():
    rows = [GOOD_ROW, STUB_ROW]
    result = r.research_summary("carl jung", rows, META)
    lines = result.splitlines()
    source_lines = [line.strip() for line in lines
                    if line.strip().startswith("1. Source:")
                    or line.strip().startswith("2. Source:")]
    assert any("Carl_Jung" in line for line in source_lines), source_lines
    assert not any("Carl_Jung_publications" in line for line in source_lines), source_lines
    assert "Evidence filtering note:" in result, result
    assert "stub_list_lead" in result, result
    assert "synthesized from 1 source(s))" in result, result
    print("summary_excludes_stub=OK")


def test_summary_no_note_when_clean():
    result = r.research_summary("philosophy", [GOOD_ROW], META)
    assert "Evidence filtering note:" not in result, result
    assert "synthesized from 1 source(s)" in result, result
    print("summary_no_note_when_clean=OK")


def test_render_cached_filters_stub():
    entry = {
        "topic": "carl jung",
        "retrieved_at": META["retrieved_at"],
        "source_notes": ["Wikipedia API"],
        "meta": {},
        "sources": [GOOD_ROW, STUB_ROW],
    }
    result = r._render_cached(entry, "carl jung")
    # Stub absent from the Evidence block (numbered Source entries)
    evidence_block = result.split("Differences:")[0]
    assert "Carl_Jung_publications" not in evidence_block, evidence_block
    # Stub present only in the filtering note
    assert "Evidence filtering note:" in result, result
    assert "stub_list_lead" in result, result
    print("render_cached_filters_stub=OK")


def test_render_cached_no_note_when_clean():
    entry = {
        "topic": "philosophy",
        "retrieved_at": META["retrieved_at"],
        "source_notes": [],
        "meta": {},
        "sources": [GOOD_ROW],
    }
    result = r._render_cached(entry, "philosophy")
    assert "Evidence filtering note:" not in result, result
    print("render_cached_no_note=OK")


def test_summary_all_filtered_returns_honest():
    only_stub = [STUB_ROW]
    result = r.research_summary("carl jung", only_stub, META)
    assert "No evidence from any allowed source class" in result, result
    assert "Evidence filtering note:" in result, result
    print("summary_all_filtered_honest=OK")


def test_gate_constants_are_strings():
    assert isinstance(r.STUB_LIST_LEAD, str)
    assert isinstance(r.DISAMBIGUATION_LEAD, str)
    assert isinstance(r.STUB_BOILERPLATE, str)
    assert isinstance(r.NON_INFORMATIVE_LEAD, str)
    print("constants=OK")


def test_ranking_confidence_unchanged_with_informative_rows():
    agreeing = [
        {"url": "https://en.wikipedia.org/wiki/Philosophy", "host": "en.wikipedia.org",
         "class": "encyclopedic", "relevance": 1.0, "tier": "medium", "belief": 0.60,
         "snippet": "Philosophy is the systematic study of general and fundamental "
                    "questions about existence, reason, knowledge, value, mind, and language."},
        {"url": "https://plato.stanford.edu/entries/philosophy/",
         "host": "plato.stanford.edu", "class": "scholarly",
         "relevance": 0.95, "tier": "high", "belief": 0.85,
         "snippet": "Philosophy as a discipline encompasses the rational "
                    "investigation of the truths and principles of being, "
                    "knowledge, and conduct."},
    ]
    result = r.research_summary("philosophy", agreeing, META)
    assert "Confidence: high" in result, result
    assert "Evidence filtering note:" not in result, result
    assert "Core understanding (synthesized from 2 source(s))" in result, result
    print("ranking_confidence_unchanged=OK")


def test_contradiction_detection_unchanged():
    rows = [
        {"url": "https://en.wikipedia.org/wiki/Red_panda",
         "host": "en.wikipedia.org", "class": "encyclopedic",
         "relevance": 0.9, "tier": "medium", "belief": 0.60,
         "snippet": "The red panda does not hibernate in winter and is not a member of the bear family."},
        {"url": "https://en.wikipedia.org/wiki/Bear",
         "host": "en.wikipedia.org", "class": "encyclopedic",
         "relevance": 0.9, "tier": "medium", "belief": 0.60,
         "snippet": "The red panda hibernates in winter and is a member of the bear family."},
    ]
    result = r.research_summary("panda hibernation", rows, META)
    assert "Status: disputed" in result, result
    assert "Contradiction" in result, result
    assert "Evidence filtering note:" not in result, result
    print("contradiction_unchanged=OK")


def _disco(topic, allowed, query_meta):
    return ([{"url": "https://en.wikipedia.org/wiki/Carl_Jung",
              "title": "Carl Jung - Wikipedia", "host": "en.wikipedia.org",
              "class": "encyclopedic"},
             {"url": "https://en.wikipedia.org/wiki/Carl_Jung_publications",
              "title": "Carl Jung publications - Wikipedia",
              "host": "en.wikipedia.org", "class": "encyclopedic"}],
            ["Wikipedia API"])


def _fetch(url, timeout=12):
    if "publications" in url:
        return ("<html><body><p>This is a list of writings published by Carl Jung.</p></body></html>")
    return ("<html><body><p>Carl Gustav Jung was a Swiss psychiatrist and "
            "psychoanalyst who founded analytical psychology.</p></body></html>")


def test_simulated_pipeline_rejects_stub():
    orig_disco, orig_fetch = r._discover_candidates, r._public_fetch
    orig_cache, orig_write = r._cache_hit, r._write_cache
    orig_persist = r._persist_research_disagreements
    written = {}
    try:
        r._discover_candidates = _disco
        r._public_fetch = _fetch
        r._cache_hit = lambda topic: None
        r._persist_research_disagreements = lambda *a, **kw: 0
        def _rec_write(topic, ra, sn, rows, meta):
            written["rows"] = rows
            return False
        r._write_cache = _rec_write
        result = r.research_topic("carl jung")
        lines = result.splitlines()
        source_lines = [line.strip() for line in lines
                        if line.strip().startswith("1. Source:")
                        or line.strip().startswith("2. Source:")]
        assert any("Carl_Jung" in l for l in source_lines), source_lines
        assert not any("publications" in l for l in source_lines), source_lines
        assert "Evidence filtering note:" in result, result
        assert "stub_list_lead" in result, result
        assert "core understanding" in result.lower() or "Core understanding" in result
        cache_rows = written.get("rows", [])
        assert all("publications" not in row.get("url", "") for row in cache_rows), cache_rows
    finally:
        r._discover_candidates = orig_disco
        r._public_fetch = orig_fetch
        r._cache_hit = orig_cache
        r._write_cache = orig_write
        r._persist_research_disagreements = orig_persist
    print("simulated_pipeline_rejects_stub=OK")


def test_simulated_pipeline_all_filtered_no_evidence():
    orig_disco, orig_fetch = r._discover_candidates, r._public_fetch
    orig_cache = r._cache_hit
    orig_write, orig_persist = r._write_cache, r._persist_research_disagreements
    try:
        r._discover_candidates = lambda t, a, q: (
            [{"url": "https://en.wikipedia.org/wiki/List_X",
              "title": "List X", "host": "en.wikipedia.org", "class": "encyclopedic"}],
            ["Wikipedia API"])
        r._public_fetch = lambda url, timeout=12: (
            "<html><body><p>This is a list of articles about X.</p></body></html>")
        r._cache_hit = lambda topic: None
        r._persist_research_disagreements = lambda *a, **kw: 0
        r._write_cache = lambda *a, **kw: False
        result = r.research_topic("topic x")
        assert "No focused public result matched:" in result, result
    finally:
        r._discover_candidates = orig_disco
        r._public_fetch = orig_fetch
        r._write_cache = orig_write
        r._persist_research_disagreements = orig_persist
    print("all_filtered_honest=OK")


if __name__ == "__main__":
    test_reject_list_lead()
    test_reject_following_list()
    test_reject_below_list()
    test_reject_disambiguation()
    test_reject_stub_boilerplate()
    test_reject_empty_and_whitespace()
    test_reject_boilerplate_leads()
    test_accept_short_informative()
    test_accept_existing_fixtures()
    test_contract_returns()
    test_summary_excludes_stub_and_shows_note()
    test_summary_no_note_when_clean()
    test_render_cached_filters_stub()
    test_render_cached_no_note_when_clean()
    test_summary_all_filtered_returns_honest()
    test_gate_constants_are_strings()
    test_ranking_confidence_unchanged_with_informative_rows()
    test_contradiction_detection_unchanged()
    test_simulated_pipeline_rejects_stub()
    test_simulated_pipeline_all_filtered_no_evidence()
    print("research_stub_gate=PASS")

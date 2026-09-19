"""Deterministic multi-signal pattern mapping for Maya.

The engine produces relative evidence-fit bands, not guaranteed probabilities.
It uses local approved/provisional data only and never writes memory or acts.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
PROFILE = ROOT / "andy_profile.json"
INTEREST_MAP = ROOT / "knowledge" / "andy_interest_map.json"
INTEREST_PROFILE = ROOT / "maya_interest_profile.json"
BOOKMARKS = ROOT / "maya_opportunity_bookmarks.json"
REFLECTIONS = ROOT / "inverted_maya_reflections.jsonl"

CANDIDATES = {
    "supervised_ai_workflows": {
        "label": "supervised AI and workflow tooling",
        "signals": {"self_evolution", "local ai", "automation", "python", "coding", "tech", "assistant"},
        "category": "technology",
        "experiment": "Build one small local workflow and measure whether it saves time.",
    },
    "research_writing_services": {
        "label": "research, writing, and evidence briefs",
        "signals": {"research", "writing", "philosophy", "learning", "public knowledge", "analysis"},
        "category": "services",
        "experiment": "Prepare one source-labeled brief for a real feedback recipient.",
    },
    "creative_technical_products": {
        "label": "creative-technical products",
        "signals": {"graphic design", "photography", "creative", "design", "automation", "python", "software"},
        "category": "creative_technology",
        "experiment": "Create one small visual or automation prototype and request focused feedback.",
    },
    "decision_support_education": {
        "label": "decision-support and educational tools",
        "signals": {"self-evolution", "philosophy", "consciousness", "learning", "education", "career", "purpose"},
        "category": "education",
        "experiment": "Write a one-page decision map for one learning or career choice.",
    },
    "markets_and_tools": {
        "label": "markets research and analytical tools",
        "signals": {"trading", "markets", "crypto", "algorithmic", "chart", "python", "data"},
        "category": "markets_education",
        "experiment": "Backtest or document one educational hypothesis without trading or financial action.",
    },
}

NEGATION_TERMS = {"avoid", "not", "never", "hate", "no longer", "don't", "do not", "exclude"}


def _read(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def _text_blob() -> tuple[str, list[tuple[str, str, str]]]:
    sources: list[tuple[str, str, str]] = []
    profile = _read(PROFILE, {})
    for section in ("interests", "decision_patterns", "working_preferences", "approved_memories"):
        values = profile.get(section, {}) if isinstance(profile, dict) else {}
        if isinstance(values, dict):
            for key, item in values.items():
                if isinstance(item, dict) and item.get("status") == "approved":
                    value = item.get("value") or item.get("proposal") or item.get("label") or key
                    sources.append((f"approved_profile:{section}", str(key), str(value)))
        elif isinstance(values, list):
            for index, item in enumerate(values):
                if isinstance(item, dict) and item.get("status") == "approved":
                    sources.append((f"approved_profile:{section}", str(index), json.dumps(item, ensure_ascii=False)))

    interest_profile = _read(INTEREST_PROFILE, {})
    for category, items in interest_profile.get("interests", {}).items() if isinstance(interest_profile, dict) else []:
        if isinstance(items, list):
            for item in items:
                sources.append((f"reviewable_interest_profile:{category}", category, str(item)))

    interest_map = _read(INTEREST_MAP, {})
    for topic, item in interest_map.get("interests", {}).items() if isinstance(interest_map, dict) else []:
        if isinstance(item, dict) and item.get("status") != "rejected":
            evidence = int(item.get("evidence", 0) or 0)
            sources.append(("provisional_interest_map", topic, f"{topic} evidence {evidence}"))

    bookmarks = _read(BOOKMARKS, {})
    for item in bookmarks.get("items", []) if isinstance(bookmarks, dict) else []:
        if isinstance(item, dict) and item.get("status") in {"saved", "revisit"}:
            sources.append(("opportunity_history", item.get("status", "saved"), str(item.get("label", ""))))

    if REFLECTIONS.exists():
        for line in REFLECTIONS.read_text(encoding="utf-8").splitlines()[-12:]:
            try:
                item = json.loads(line)
                sources.append(("local_reflection", "reflection", str(item.get("text", ""))))
            except json.JSONDecodeError:
                continue

    blob = " ".join(value for _, _, value in sources).lower()
    return blob, sources


def _match_signal(blob: str, signal: str) -> bool:
    raw = signal.lower()
    variants = {raw, raw.replace("_", " "), raw.replace("_", "-")}
    for variant in variants:
        if re.search(r"(?<![a-z0-9])" + re.escape(variant), blob):
            return True
    return False


def _constraints(blob: str) -> list[str]:
    constraints = []
    for phrase in ("low cost", "cpu", "local only", "privacy", "approval", "reversible", "no trading", "no external action"):
        if phrase in blob:
            constraints.append(phrase)
    return constraints


def _candidate_evidence_to_change(matches: list[str], independent_sources: int) -> list[str]:
    lines = []
    if independent_sources < 2:
        lines.append("More independent source types matching these signals would raise confidence.")
    if len(matches) < 2:
        lines.append("At least one additional repeated signal is needed before this fit is treated as stable.")
    lines.append("A new approved interest, correction, or verified outcome in any matched signal area could change this ranking.")
    return lines


def pattern_map(user_text: str = "") -> dict[str, Any]:
    blob, sources = _text_blob()
    query = user_text.strip().lower()
    combined = f"{blob} {query}"
    constraints = _constraints(combined)
    negated = [term for term in NEGATION_TERMS if term in combined]
    candidates = []

    for key, candidate in CANDIDATES.items():
        matches = [signal for signal in candidate["signals"] if _match_signal(combined, signal)]
        supporting_source_types = {
            source_type.split(":", 1)[0] for source_type, _, value in sources
            if any(_match_signal(value.lower(), signal) for signal in matches)
        }
        evidence_count = len(matches)
        independent_sources = len(supporting_source_types)
        # Relative fit score is deliberately not called probability.
        fit_score = min(100, evidence_count * 10 + independent_sources * 12)
        if evidence_count == 0:
            continue
        if independent_sources < 2 or evidence_count < 2:
            confidence = "tentative"
        elif fit_score >= 70:
            confidence = "supported, not confirmed"
        else:
            confidence = "moderate, needs validation"
        caveats = []
        if negated:
            caveats.append("Negation or exclusion language is present; inspect the full sentence before relying on this fit.")
        if "privacy" in constraints or "local only" in constraints:
            caveats.append("Privacy/local-only constraints should shape the experiment.")
        candidates.append({
            "key": key,
            "label": candidate["label"],
            "category": candidate["category"],
            "relative_evidence_fit": fit_score,
            "confidence_band": confidence,
            "matched_signals": sorted(matches),
            "independent_source_types": sorted(supporting_source_types),
            "constraints_detected": constraints,
            "caveats": caveats,
            "small_reversible_experiment": candidate["experiment"],
            "what_would_change_ranking": _candidate_evidence_to_change(matches, independent_sources),
            "decision": "Andy decides; Maya does not take external action.",
        })

    candidates.sort(key=lambda item: (item["relative_evidence_fit"], len(item["independent_source_types"])), reverse=True)
    return {
        "purpose": "Map approved and provisional patterns to possible directions.",
        "status": "review_only",
        "source_count": len(sources),
        "source_types": sorted({source_type.split(":", 1)[0] for source_type, _, _ in sources}),
        "constraints_detected": constraints,
        "negation_terms_detected": sorted(negated),
        "candidates": candidates[:5],
        "uncertainty": [
            "This is relative evidence fit, not a calibrated probability or prediction.",
            "Patterns can be incomplete, stale, or misinterpreted.",
            "No memory, permission, purchase, message, trade, or external action was performed.",
        ],
    }


def pattern_map_events(events: list[str], objective: str = "") -> dict[str, Any]:
    """Map a bounded, user-supplied event stream without predicting an outcome.

    This is intentionally separate from the personal opportunity mapper. It is
    useful for simulations and structured reviews where sequence and state
    changes matter more than profile-signal overlap.
    """
    clean = [" ".join(str(event).split()) for event in events if str(event).strip()]
    text = " ".join(clean).lower()
    risk_terms = {
        "resource_depletion": ("deplet", "loss of", "running out", "pressure"),
        "system_failure": ("failure", "failed", "undervolt", "bang", "damaged", "abnormal"),
        "life_support_or_safety": ("oxygen", "water", "life-support", "life support", "dangerous"),
        "uncertainty": ("assess", "indication", "appeared", "possible", "unknown", "uncertain", "uncertainty", "sensor", "considered"),
    }
    detected = {name: [term for term in terms if term in text] for name, terms in risk_terms.items()}
    detected = {name: terms for name, terms in detected.items() if terms}
    patterns = []
    if any(word in text for word in ("previously", "earlier", "ground testing", "damaged")) and any(word in text for word in ("soon after", "later", "began to", "followed")):
        patterns.append({"name": "known-hazard-escalation", "evidence": "earlier anomaly or damage is followed by later abnormal behavior", "confidence": "moderate"})
    if (any(word in text for word in ("oxygen", "pressure", "deplet", "life-support", "life support")) and any(word in text for word in ("electrical", "fuel-cell", "undervolt", "power"))) or (any(word in text for word in ("collapse", "trapped", "buried")) and any(word in text for word in ("limited", "survivor", "survivors", "dangerous"))):
        patterns.append({"name": "cascading-system-failure", "evidence": "an initial failure creates secondary resource or safety degradation", "confidence": "moderate"})
    if any(word in text for word in ("crew", "controllers", "assessed", "reported", "instructions", "uncertain", "uncertainty", "considered", "search")):
        patterns.append({"name": "human-decision-under-uncertainty", "evidence": "people are assessing incomplete signals before choosing a response", "confidence": "tentative"})
    if objective and any(word in text for word in ("threatened", "loss", "failure", "problem", "trapped", "limited", "uncertain", "changes")):
        patterns.append({"name": "objective-at-risk", "evidence": objective, "confidence": "tentative"})
    if any(word in text for word in ("repeatedly", "over several weeks", "multiple conversations", "returns", "recurring", "several times")):
        patterns.append({"name": "repeated-interest-signals", "evidence": "the same theme or behavior recurs across observations", "confidence": "tentative"})
    if any(word in text for word in ("limited", "competing", "cannot", "but", "small budget", "narrow", "constraints")):
        patterns.append({"name": "conflict-and-constraint", "evidence": "goals or actions are bounded by competing priorities or limited resources", "confidence": "tentative"})
    if any(word in text for word in ("considering", "choose", "choosing", "decide", "specialize", "commit")):
        patterns.append({"name": "decision-point", "evidence": "the event stream contains an explicit choice or commitment point", "confidence": "tentative"})
    if any(word in text for word in ("small", "pilot", "test", "trial", "reversible", "three low-risk experiments")):
        patterns.append({"name": "small-experiment", "evidence": "a bounded experiment is available before a larger commitment", "confidence": "moderate"})
    if any(word in text for word in ("three", "multiple plans", "alternative", "compare", "options")):
        patterns.append({"name": "alternative-paths", "evidence": "more than one path or plan is being considered", "confidence": "tentative"})
    if any(word in text for word in ("do not", "don't", "never", "exclude", "avoid")):
        patterns.append({"name": "negation-or-exclusion", "evidence": "the event stream explicitly rules out an action or category", "confidence": "moderate"})
    if any(word in text for word in ("earlier attempts", "later attempts", "partial improvement", "repeated errors")):
        patterns.append({"name": "trend-with-noise", "evidence": "repeated observations show change without a clean monotonic trend", "confidence": "tentative"})
    if any(word in text for word in ("increased", "technology changes", "broadband", "market response", "environment")):
        patterns.append({"name": "environmental-shift", "evidence": "the surrounding technical or market environment is changing", "confidence": "tentative"})
    if any(word in text for word in ("while", "continued operating", "building the new", "existing model")):
        patterns.append({"name": "parallel-transition", "evidence": "an existing path continues while a new path is built", "confidence": "tentative"})
    if any(word in text for word in ("investment", "limited", "budget", "resource", "existing model")) and any(word in text for word in ("new", "building", "technology", "service")):
        patterns.append({"name": "resource-allocation-tradeoff", "evidence": "resources must be divided between current operations and a new direction", "confidence": "tentative"})
    if any(word in text for word in ("rescue plans", "multiple rescue", "backup", "fallback", "redundant", "alternative")):
        patterns.append({"name": "fallback-and-redundancy", "evidence": "multiple backup or recovery paths are present", "confidence": "tentative"})
    if any(word in text for word in ("limited food", "limited water", "limited space", "limited time", "small budget", "limited energy", "scarce", "conserve")):
        patterns.append({"name": "resource-preservation", "evidence": "a scarce resource must be protected while the situation unfolds", "confidence": "moderate"})
    response_options = []
    if "resource_depletion" in detected or "life_support_or_safety" in detected or any(word in text for word in ("limited food", "limited water", "limited evening time", "small budget", "limited energy", "narrow weekly time")):
        response_options.append("protect scarce resources and define a minimum safe state")
    if "system_failure" in detected:
        response_options.append("isolate failed components and validate a backup path in simulation before execution")
    if "uncertainty" in detected:
        response_options.append("separate observed facts from inferred causes and maintain multiple live hypotheses")
    return {
        "purpose": "Bounded sequence review of user-supplied events",
        "status": "review_only",
        "event_count": len(clean),
        "patterns": patterns,
        "risk_states": detected,
        "response_options": response_options,
        "uncertainty": [
            "This is a structured pattern review, not a calibrated probability or prediction.",
            "The mapper cannot know held-out events and should not claim an exact future outcome.",
            "Human review is required before any real-world response.",
        ],
        "memory_update": "not_performed",
        "external_action": "not_performed",
    }


def conditional_map_events(events: list[str], objective: str = "") -> dict[str, Any]:
    """Render bounded if-then possibilities from observed event patterns.

    Wording deliberately uses ``consider`` rather than ``should``: the output
    is a review aid and cannot authorize a real-world action.
    """
    mapped = pattern_map_events(events, objective)
    branches = []
    names = {item.get("name") for item in mapped.get("patterns", [])}
    if "known-hazard-escalation" in names or "cascading-system-failure" in names:
        branches.append({"if": "the observed escalation continues", "then": "secondary failures become more plausible", "consider": "isolating the failing component and validating a backup path"})
    if "resource-preservation" in names or "conflict-and-constraint" in names:
        branches.append({"if": "the scarce-resource constraint remains", "then": "the original plan may become less feasible", "consider": "defining a minimum safe state and comparing reversible alternatives"})
    if "human-decision-under-uncertainty" in names or "uncertainty" in mapped.get("risk_states", {}):
        branches.append({"if": "key evidence remains ambiguous", "then": "multiple explanations remain live", "consider": "separating observations from causes and gathering the next discriminating evidence"})
    if "objective-at-risk" in names:
        branches.append({"if": "the original objective continues to conflict with safety constraints", "then": "a revised objective may be more viable", "consider": "reframing the goal while keeping the decision with the responsible humans"})
    return {
        **mapped,
        "conditional_branches": branches,
        "language_policy": "if_then_review_only_consider_not_should",
        "decision_owner": "human",
        "memory_update": "not_performed",
        "external_action": "not_performed",
    }


def rank_character_options(options: list[str], events: list[str]) -> list[dict[str, Any]]:
    """Rank user-visible options from character-specific permitted events.

    This uses explicit lexical evidence and constraints only. It does not infer
    hidden traits, rank people, or produce a probability of what they will do.
    """
    text = " ".join(str(event).lower() for event in events)
    signal_groups = {
        "pilot": ("software", "product", "experiment", "flexible", "savings", "uncertain short-term"),
        "course": ("credential", "structured", "fixed", "predictable", "low-variance", "recognized"),
        "portfolio": ("photography", "design", "portfolio", "weekend", "visible"),
        "wait": ("uncertain", "gather", "evidence", "more information", "review"),
    }
    ranked = []
    for option in options:
        lowered = option.lower()
        if "portfolio" in lowered:
            group = "portfolio"
        elif "course" in lowered:
            group = "course"
        elif "pilot" in lowered:
            group = "pilot"
        else:
            group = "wait"
        score = sum(1 for signal in signal_groups[group] if signal in text)
        if group == "pilot" and "small budget" in text:
            score -= 2
        if group == "portfolio" and "limited time" in text:
            score += 1
        ranked.append({"option": option, "relative_fit": max(0, score), "evidence_group": group})
    return sorted(ranked, key=lambda item: (item["relative_fit"], item["option"]), reverse=True)


def render_pattern_map(user_text: str = "") -> str:
    result = pattern_map(user_text)
    conditional = conditional_map_events([user_text] if user_text.strip() else [], user_text)
    lines = [
        "Pattern map (review only):",
        "Relative evidence fit is not a probability or a guaranteed outcome.",
        f"Signals used: {result['source_count']} local items across {', '.join(result['source_types']) or 'no sources'}.",
    ]
    if not result["candidates"]:
        lines.append("There are not enough matched signals to produce a responsible candidate map.")
    if conditional["conditional_branches"]:
        lines.append("Conditional paths (review only; consider, not should):")
        for branch in conditional["conditional_branches"]:
            lines.append(f"If {branch['if']}, then {branch['then']}; consider {branch['consider']}.")
    for index, candidate in enumerate(result['candidates'], 1):
        lines.extend([
            f"{index}. {candidate['label']} — {candidate['confidence_band']} (relative fit {candidate['relative_evidence_fit']}/100)",
            f"   Signals: {', '.join(candidate['matched_signals'])}",
            f"   Experiment: {candidate['small_reversible_experiment']}",
        ])
        for caveat in candidate["caveats"]:
            lines.append(f"   Caveat: {caveat}")
        for evidence_trigger in candidate.get("what_would_change_ranking", []):
            lines.append(f"   Evidence that could change this ranking: {evidence_trigger}")
    if len(result["candidates"]) > 1:
        lines.append("Alternative kept: " + result["candidates"][1]["label"] + " remains a credible second route unless new evidence changes the comparison.")
    lines.append("No memory, permission, purchase, message, trade, or external action was performed.")
    return "\n".join(lines)

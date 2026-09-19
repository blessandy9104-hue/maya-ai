"""Semantic interpretation of one conversational turn (Batch 8G).

Adds to the existing live intent classifier (``maya_intent_cues``) exactly the
machinery that module cannot provide:

- multi-candidate interpretation preservation (never silently collapse),
- reference resolution against *ranked* antecedents,
- correction / clarification detection,
- epistemic-status labeling of user claims (the fact boundary, reused from
  :mod:`maya_runtime.intelligence.epistemic`),
- modality and turn-finality carriers for the text/voice parity contract.

The module is deterministic: no wall clock, no randomness, no file writes.
"""
from __future__ import annotations

import re

from .state import ConversationState, _clean, _normalized_utterance

# ---- epistemic vocabulary (reused from the intelligence core) ------------

try:  # pragmatic reuse: keep ``maya_conversation`` importable in a stripped
    # build, and let verification prove the vocabularies stay identical.
    from maya_runtime.intelligence.epistemic import (
        EPISTEMIC_STATUSES as _CORE_EPISTEMIC,
        EPISTEMIC_STATUSES_ORDERED as _CORE_EPISTEMIC_ORDERED,
    )
    EPISTEMIC_STATUSES = frozenset(_CORE_EPISTEMIC)
    EPISTEMIC_STATUSES_ORDERED = tuple(_CORE_EPISTEMIC_ORDERED)
    _EPISTEMIC_IMPORTED = True
except Exception:  # pragma: no cover - fallback, verified identical in tests
    EPISTEMIC_STATUSES = frozenset({
        "OBSERVED", "MEASURED", "CALCULATED", "INFERRED", "REPORTED",
        "DOCUMENTED", "BELIEVED", "BELIEF", "TRADITIONAL", "INTERPRETIVE",
        "INTERPRETATION", "HYPOTHETICAL", "HYPOTHESIS", "SUPPORTED",
        "EMPIRICALLY_TESTED", "DISPUTED", "CONTRADICTED", "UNVERIFIED",
        "UNKNOWN",
    })
    EPISTEMIC_STATUSES_ORDERED = (
        "OBSERVED", "MEASURED", "CALCULATED", "INFERRED", "REPORTED",
        "DOCUMENTED", "BELIEVED", "BELIEF", "TRADITIONAL", "INTERPRETIVE",
        "INTERPRETATION", "HYPOTHETICAL", "HYPOTHESIS", "SUPPORTED",
        "EMPIRICALLY_TESTED", "DISPUTED", "CONTRADICTED", "UNVERIFIED",
        "UNKNOWN",
    )
    _EPISTEMIC_IMPORTED = False

_NON_FACTUAL = {
    "BELIEVED", "BELIEF", "TRADITIONAL", "INTERPRETIVE", "INTERPRETATION",
    "HYPOTHETICAL", "HYPOTHESIS", "DISPUTED", "CONTRADICTED", "UNVERIFIED",
    "UNKNOWN",
}

# classifier reuse (wrap: fails open to a conservative fallback intent)
try:
    from maya_intent_cues import classify_opening as _classify_opening
except Exception:  # pragma: no cover - absent in stripped environments
    def _classify_opening(text):  # fallback, documented
        return {
            "intent": "statement_or_general_request", "first_word": "",
            "secondary_intents": [], "contrastive_markers": [],
            "confidence": 0.0, "ambiguous": True, "model": "fallback",
        }

# reference / deictic surface (kept deliberately close to maya_context)
_DEICTIC = {"this", "that", "it", "they", "them", "one", "other", "those",
            "these", "its", "their"}
_QUESTION_WORD_REF = {"why", "how", "what", "which", "who", "where", "when",
                      "and", "then", "so"}
_HOW_SO = {"why", "how so", "how come", "and", "then", "what now", "why not"}
_NEW_TOPIC_RE = re.compile(
    r"^\s*(?:(?:and|but|so|also|ok|okay|sure|hmm|hm)\s+)?"
    r"((what|how)[^?.]{0,12}\babout|[a-z]*\bswitch to|let.s talk about|"
    r"tell me about|regarding|now (regarding|about))\s+(?P<subject>.+?)\??\s*$",
    re.IGNORECASE)
_REF_SHORT_RE = re.compile(r"^\s*(why\??|how so\??|how come\??|and\??|"
                           r"then\??|what now\??|what about it\??|"
                           r"why not\??)\s*$", re.IGNORECASE)
_UNCERTAINTY_RE = re.compile(
    r"\b(maybe|possibly|perhaps|probably|guess|i think|not sure|could be|"
    r"might be|seems like|i feel like)\b", re.IGNORECASE)
_REPORT_RE = re.compile(
    r"\b(some say|they say|people say|according to|research shows|studies "
    r"show|studies suggest|reports say|i read that|i heard that|i saw)\b",
    re.IGNORECASE)
_QUOTED_RE = re.compile(r"[\"“]([^\"”]+)[\"”]")
_CONSTRAINT_RE = re.compile(
    r"\b(remember\s+this|keep\s+(this|that)\s+in\s+mind|from\s+now\s+on|"
    r"always|never assume|never\s+say|you\s+must|please\s+never|"
    r"don.t\s+forget|important:\s*)\b", re.IGNORECASE)
_CORRECTION_CORE_RE = re.compile(
    r"^\s*(no|wait|that.s\s+not|that.sn.t|actually|i\s+meant|i\s+mean|"
    r"correction|not\s+what\s+i|wrong)\b.?",
    re.IGNORECASE)

QUESTION_INTENTS = {
    "definition_or_information", "person_or_entity", "time_or_history",
    "reason_or_cause", "process_or_explanation", "choice_or_comparison",
    "fact_check_or_definition",
    "request_for_explanation", "location",
}


def _significant_tokens(text):
    """Deterministic content-word set for antecedent ranking."""
    return {token for token in re.findall(r"[a-z]{4,}", text.lower())
            if token not in {
                "what", "when", "where", "which", "who", "why", "how",
                "about", "with", "from", "that", "this", "there", "they",
                "them", "their", "have", "been", "were", "would", "could",
                "should", "does", "doing", "your", "yours", "wouldn"}}

def _rank_antecedents(text, history):
    """Rank candidate priority. Returns list of dicts most-recent-first with
    an overlap score; ties resolve to the more recent turn. Deterministic."""
    hoped = []
    utt = _normalized_utterance(text)
    sig = _significant_tokens(utt)
    blurred = _clean(text).lower()
    for index, entry in reversed(list(enumerate(history))):
        content = _clean(entry.get("content") if isinstance(entry, dict) else entry)
        if not content:
            continue
        if entry.get("role", "user") == "assistant":
            continue
        content_norm = _normalized_utterance(content)
        overlap = len(sig & _significant_tokens(content_norm))
        if sig and overlap:
            score = overlap
        elif sig:
            score = 0
        else:
            score = 1 if _REF_SHORT_RE.match(utt) else 0
        hoped.append({"turn": index, "score": score, "content": content})
    hoped.sort(key=lambda item: item["score"], reverse=True)
    return hoped


def interpret_input(text, state=None, history=None):
    """Deterministic interpretation of one turn.

    ``state``   : :class:`ConversationState` (may be ``None`` on first turn).
    ``history`` : iterable of ``{"role","content"}`` or plain strings.
    """
    cleaned = _clean(text)
    normalized = _normalized_utterance(cleaned)
    history = list(history or [])

    classifier = _classify_opening(cleaned)
    intent = str(classifier.get("intent") or "statement_or_general_request")
    ambiguous = bool(classifier.get("ambiguous"))
    confidence = float(classifier.get("confidence") or 0.0)

    # ---- modality carriers (text by default; voice via TranscribedTurn) --
    modality = "voice" if getattr(state, "modality", "text") == "voice" else "text"
    final = True
    stt_confidence = 1.0

    # ---- correction detection --------------------------------------------
    is_correction = False
    correction_note = ""
    match = _CORRECTION_CORE_RE.match(cleaned)
    if match:
        is_correction = True
        core = _CORRECTION_CORE_RE.sub("", cleaned).strip(" .?!")
        # keep the part of the utterance that *replaces* the prior content
        correction_note = (core or cleaned)[:120]

    # ---- reference resolution (ranked antecedents) -----------------------
    references = []
    ranked = _rank_antecedents(cleaned, history)
    if ranked and (ranked[0]["score"] > 0 or _REF_SHORT_RE.match(normalized) or
                   (not _significant_tokens(normalized))):
        best = ranked[0]
        if best["score"] > 0 or _REF_SHORT_RE.match(normalized):
            references.append({
                "antecedent": best["content"][:200],
                "kind": "deictic_or_anaphoric" if not _REF_SHORT_RE.match(normalized)
                        else "question_word",
                "turn": best["turn"],
                "score": best["score"],
            })
    # state-topic fallback: short follow-ups with no usable history still
    # resolve against the conversational topic (the ranked antecedent set
    # includes the state's current anchor at lowest rank).
    state_topic = _clean(state.topic if state else "")
    _deictic_here = any(token in normalized for token in (
        "it", "this", "that", "they", "them", "those", "these"))
    if not references and state_topic and (
            _REF_SHORT_RE.match(normalized)
            or (not _significant_tokens(normalized))
            or _deictic_here
            or any(token in normalized for token in (
                "what about", "how about", "and", "then", "why is that",
                "why not", "is that"))):
        references.append({
            "antecedent": state_topic[:200],
            "kind": "conversational_topic",
            "turn": -1,
            "score": 1,
        })

    # ---- candidate interpretations (preserved, ranked, with reason) ------
    candidates = []
    candidates.append({
        "interpretation": intent,
        "label": "primary",
        "confidence": confidence,
        "reason": "cue-classified primary intent",
    })
    if ambiguous or references or _REF_SHORT_RE.match(normalized):
        if _REF_SHORT_RE.match(normalized) and references:
            candidates.append({
                "interpretation":
                    "follow_up_on_previous_topic",
                "label": "alternative",
                "confidence": 0.62,
                "reason": "short reference form; antecedent ranked by overlap",
            })
        elif not _significant_tokens(normalized) and not references:
            candidates.append({
                "interpretation": "fragment_or_greeting",
                "label": "alternative",
                "confidence": 0.5,
                "reason": "no content words; greeting or fragment",
            })
    seen = set()
    candidates_dedup = []
    for candidate in candidates:
        key = candidate["interpretation"]
        if key not in seen:
            seen.add(key)
            candidates_dedup.append(candidate)
    candidates = candidates_dedup

    # ---- topic handling --------------------------------------------------
    topic = current_topic if (current_topic := state.topic if state else "") else ""
    new_topic = ""
    topic_match = _NEW_TOPIC_RE.match(cleaned)
    if topic_match:
        new_topic = topic_match.group("subject").strip(" .?!")[:80]
    if not new_topic and not topic:
        topic = cleaned[:80]

    # ---- claims with epistemic status (user content only) ----------------
    claims = []
    _classify_claims(cleaned, claims)

    # ---- unresolved question bookkeeping ---------------------------------
    unresolved_question = ""
    resolved_question_id = ""
    if intent in QUESTION_INTENTS:
        resolved = _find_resolvable_question(normalized, state)
        if resolved:
            resolved_question_id = _clean(resolved)
        elif normalized and len(normalized) <= 120:
            unresolved_question = normalized

    # ---- explicit constraints --------------------------------------------
    constraints = []
    for ctl in _CONSTRAINT_RE.finditer(cleaned):
        rest = cleaned[ctl.end():].strip(" .:?!,;")
        if rest:
            constraints.append(rest[:120])

    return {
        "utterance": cleaned,
        "normalized": normalized,
        "intent": intent,
        "primary_intent": intent,
        "candidates": candidates,
        "ambiguous": ambiguous,
        "is_correction": is_correction,
        "correction_note": correction_note,
        "references": references,
        "topic": topic,
        "new_topic": new_topic,
        "claims": claims,
        "unresolved_question": unresolved_question,
        "resolved_question_id": resolved_question_id,
        "constraints": constraints,
        "modality": modality,
        "final": final,
        "stt_confidence": stt_confidence,
        "classifier_used_as_hint_only": True,
    }


def _find_resolvable_question(normalized, state):
    if not state:
        return ""
    for entry in list(state.unresolved_questions):
        prior = entry.get("question", "")
        a = _normalized_utterance(prior)
        b = _normalized_utterance(normalized)
        if a and (a in b or b in a):
            return prior
    return ""


def _classify_claims(text, out):
    """Conservative, deterministic claim tagging: never upgrades the user's
    assertion above REPORTED, and downgrades hedging to HYPOTHESIS."""
    if not text:
        return
    for quote in _QUOTED_RE.findall(text):
        out.append({"text": quote.strip()[:200],
                    "epistemic_status": "REPORTED",
                    "marker": "quoted",
                    "factive": False})
    segments = [seg.strip() for seg in re.split(r"[.!?]+", text) if seg.strip()]
    for segment in segments:
        low = segment.lower()
        if _UNCERTAINTY_RE.search(low):
            out.append({"text": segment[:200],
                        "epistemic_status": "HYPOTHESIS",
                        "marker": "uncertainty",
                        "factive": False})
            continue
        if _REPORT_RE.search(low):
            out.append({"text": segment[:200],
                        "epistemic_status": "REPORTED",
                        "marker": "hearsay",
                        "factive": False})
            continue
        if re.search(r"\b(is|are|was|were|has|have|means)\b", low) and \
                re.search(r"\b(i|my|we|our)\b", low) and \
                not _UNCERTAINTY_RE.search(low):
            out.append({"text": segment[:200],
                        "epistemic_status": "BELIEVED",
                        "marker": "user_assertion",
                        "factive": False})
    # de-duplicate by (text, status), stable order
    seen = set()
    dedup = []
    for claim in out:
        key = (claim["text"], claim["epistemic_status"])
        if key not in seen:
            seen.add(key)
            dedup.append(claim)
    out[:] = dedup


# -- vocabulary parity (used by the verification suite) --------------------

def core_epistemic_imported():
    return _EPISTEMIC_IMPORTED
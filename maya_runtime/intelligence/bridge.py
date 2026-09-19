"""Deterministic bridge from free-form conversation to the intelligence core.

Maps raw conversation text to the verified feature primitives, runs the
seven-stage intelligence loop, and reduces the structured result to a small
deterministic *cognitive frame* plus an *expression directive* (register,
output budget, hold reasons, and constraint text) that is handed to the
natural-language expression layer.

Boundary, stated plainly:

- The mathematics owns the constraint envelope: register, output budget,
  hold reasons, and the numeric cognitive frame itself.
- The natural-language expression layer (the local LLM) owns the wording of
  the answer, inside that envelope.
- Nothing here replaces or bypasses the LLM, and nothing here generates the
  final natural-language sentence.

Every mapping heuristic is procedural and deterministic: token overlap,
question/exclamation flags, and a stable 64-bit FNV-1a hash of the text.
These are documented heuristics, not a claim of NLU. No host/time probes
are performed: the module imports only the standard library and the
intelligence package, and is scanned by the independent static arm for
forbidden nondeterminism imports.
"""
from __future__ import annotations

import json
import math
import re

from .loop import run as _run_loop
from .bus import bus_handoff_enabled, publish_turn
from .detector import detect as _detect_representation
from .world_mapping import map_to_world
from . import persona as _persona

_WORD_RE = re.compile(r"[a-z0-9']+")
_Q_WORDS = frozenset(("?", "what", "why", "how", "when", "where", "which",
                      "who", "do", "does", "could", "can", "should"))
_EXCLAIM_WORDS = frozenset(("please", "now", "urgent", "immediately", "asap",
                            "need", "must"))
_URGENT_WORDS = frozenset(("urgent", "asap", "emergency", "now",
                           "immediately", "critical", "danger", "deadline"))
_ACTION_WORDS = frozenset(("run", "start", "stop", "open", "close", "deploy",
                           "build", "create", "write", "fix", "install"))
_REFERENT_WORDS = frozenset(("you", "your", "yourself", "i", "me", "my", "we",
                             "us", "andy", "maya"))
_POSITIVE_WORDS = frozenset(("good", "great", "nice", "yes", "love", "like",
                             "happy", "thanks", "thank", "perfect",
                             "awesome", "cool", "works", "correct"))
_NEGATIVE_WORDS = frozenset(("not", "no", "bad", "wrong", "error", "fail",
                             "failed", "broken", "hate", "stop", "sorry",
                             "never", "can't", "unable"))

_DEFAULT_REGISTER = "compact"
_SAFE_METRICS = {"cpu_percent": 5.0, "memory_percent": 30.0,
                 "process_count": 1, "launches": 0}
_BUDGET_FULL = 48
_BUDGET_RESTRICTED = 24
_BUDGET_HOLD = 16


def _tokens(text):
    return tuple(_WORD_RE.findall(str(text or "").lower()))


def _hash01(text):
    """Stable 64-bit FNV-1a hash normalized to [0, 1). No imports needed."""
    value = 14695981039346656037
    for byte in str(text or "").encode("utf-8"):
        value ^= byte
        value = (value * 1099511628211) & ((1 << 64) - 1)
    return (value & ((1 << 64) - 1)) / float(1 << 64)


def _clamp01(value):
    return max(0.0, min(1.0, float(value)))


def _clamp(value, lo, hi):
    return max(lo, min(hi, float(value)))


def _round4(value):
    return round(float(value), 4)


def _has(tokens_set, text):
    return any(word in tokens_set for word in _tokens(text))


def _question_factor(text):
    t = str(text or "").strip()
    if "?" in t:
        return 1.0
    return 1.0 if _has(_Q_WORDS, t) else 0.0


def _exclaim_factor(text):
    t = str(text or "")
    if "!" in t or _has(_EXCLAIM_WORDS, t):
        return 1.0
    return 0.0


def _upper_frac(text):
    letters = [c for c in str(text or "") if c.isalpha()]
    if not letters:
        return 0.0
    return sum(1 for c in letters if c.isupper()) / float(len(letters))


def _overlap(a, b):
    ta = set(_tokens(a))
    tb = set(_tokens(b))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / float(len(ta | tb))


def _population_std(values):
    vals = [float(v) for v in values if v is not None]
    if not vals:
        return 0.0
    mean = sum(vals) / len(vals)
    return math.sqrt(sum((v - mean) ** 2 for v in vals) / len(vals))


def _clean_history(history=None):
    cleaned = []
    for item in (history or ()):
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "")
        content = str(item.get("content") or "").strip()
        if content and role in ("user", "assistant"):
            cleaned.append({"role": role, "content": content})
    return tuple(cleaned)


def _last_content(history, role):
    for item in reversed(history):
        if item["role"] == role:
            return item["content"]
    return ""


def _turn_force(content, role):
    text = str(content or "")
    base = _hash01(text if text.strip() else (role or "x"))
    length = min(1.0, len(text) / 200.0)
    return _round4(_clamp01(0.5 * base + 0.5 * length))


def _force_series(history, user_text):
    series = [_turn_force(item["content"], item["role"])
              for item in history[-6:]]
    series.append(_turn_force(user_text, "user"))
    return tuple(series)


def _question_count(history):
    return sum(1 for item in history
               if item["role"] == "user" and "?" in item["content"])


def _topic_reference(history, current):
    prior = " ".join(str(m["content"]) for m in history[-4:])
    whole = (prior + " " + str(current)).strip()
    words = _tokens(whole)
    referent = 1.0 if any(w in _REFERENT_WORDS for w in words) else 0.0
    return (round(_hash01(whole + ":topic"), 6),
            round(_question_factor(current), 6),
            round(referent, 6))


def map_conversation(user_text, history=None, sequence=0, environment="local"):
    """Map conversation text to the verified feature primitives.

    Returns a dict of kwargs valid for ``intelligence.run``. Every value is
    derived procedurally and deterministically from the text itself; no
    clock, random source, or host probe is consulted.
    """
    history = _clean_history(history)
    current = str(user_text or "").strip()
    prev_user = _last_content(history, "user")
    prev_assistant = _last_content(history, "assistant")
    words = _tokens(current)
    char_len = len(current)
    words_len = len(words) or 1
    q_factor = _question_factor(current)
    ex_factor = _exclaim_factor(current)
    upper = _upper_frac(current)
    overlap = _overlap(prev_user, current) if prev_user else 0.5
    pos = sum(1 for w in words if w in _POSITIVE_WORDS)
    neg = sum(1 for w in words if w in _NEGATIVE_WORDS)
    pos_frac = pos / float(pos + neg + 1)
    neg_frac = neg / float(pos + neg + 1)
    referent = 1.0 if _has(_REFERENT_WORDS, current) else 0.0
    intensity = _round4(_clamp01(0.3 + 0.4 * ex_factor + 0.3 * upper +
                                 0.1 * min(1.0, char_len / 40.0)))
    valence = _round4(_clamp01(0.5 + 0.5 * (pos - neg) /
                               float(pos + neg + 1)))
    arousal = _round4(_clamp01(0.4 * ex_factor + 0.4 * upper +
                               0.3 * q_factor))
    warmth = _round4(_clamp01(0.55 + 0.35 * pos_frac - 0.25 * neg_frac))
    urgency = 1.0 if _has(_URGENT_WORDS, current) else 0.2
    impact = 1.0 if _has(_ACTION_WORDS, current) else 0.3
    effort = _round4(_clamp01(char_len / 60.0))
    relevance = overlap if not prev_assistant else _overlap(prev_assistant,
                                                            current)
    series = _force_series(history, current)
    current_force = series[-1]
    force_std = _round4(_population_std(series))
    total = 1 + len(history)
    q_count = _question_count(history) + (1 if q_factor == 1.0 else 0)
    consensus = _round4(_clamp01(0.9 - 0.4 * (q_count / float(total))))
    currency = _round4(_clamp01(0.9 - 0.1 * min(6, len(history))))
    reference = _topic_reference(history, current)
    topic_vector = (round(_hash01(current + ":topic"), 6), q_factor,
                    referent)
    zprime = _round4(_clamp(0.8 * intensity - 0.4, -0.9, 0.8))

    return {
        "semantic": {
            "coherence": _round4(_clamp01(overlap)),
            "salience": _round4(_clamp01(0.5 + 0.5 * referent)),
            "novelty": _round4(_clamp01(1.0 - overlap)),
            "topic_vector": topic_vector,
            "evidence_sufficient": True,
        },
        "emotional": {
            "intensity": intensity,
            "valence": valence,
            "arousal": arousal,
            "warmth": warmth,
            "state_vector": (intensity, valence, arousal),
            "reactive": bool(ex_factor >= 1.0 or upper > 0.3),
        },
        "contextual": {
            "urgency": _round4(urgency),
            "impact": _round4(impact),
            "effort": effort,
            "relevance": _round4(_clamp01(relevance)),
            "time_critical": bool(urgency >= 0.9),
        },
        "historical": {
            "stability": series,
            "drift": series,
            "coherence": _round4(_clamp01(overlap)),
            "consensus": consensus,
            "currency": currency,
            "equilibrium_near": bool(force_std < 0.05),
        },
        "render": {
            "glow": intensity,
            "depth": _round4(_clamp01(char_len / 120.0)),
            "thickness": _round4(_clamp(1.0 + char_len / 40.0, 1.0, 5.0)),
            "zprime": zprime,
            "jaw": _round4(_clamp01(0.2 + char_len / 300.0)),
            "glow_present": bool(intensity > 0.5),
        },
        "reference": reference,
        "world_series": series,
        "metrics": dict(_SAFE_METRICS),
        "context_vector": reference,
        "evidence_ok": hasattr(_run_loop, "__call__"),
        "now": None,
        "sequence": int(sequence) if sequence else 0,
        "architect_instruction": None,
        "environment": environment,
    }


def _as_float(value, fallback=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _extract_cognitive(frame):
    """Reduce one intelligence result to a flat, serializable frame."""
    if frame is None:
        return None
    if not isinstance(frame, dict):
        return None
    meaning = frame.get("meaning") or {}
    language = frame.get("language") or {}
    state = frame.get("state") or {}
    safety = frame.get("safety") or {}
    confidence = frame.get("confidence") or {}
    fusion = frame.get("fusion") or {}
    meaning_vector = tuple(_round4(_as_float(v))
                           for v in (meaning.get("meaning_vector") or ()))
    return {
        "meaning_scalar": _round4(_as_float(meaning.get("meaning_scalar"))),
        "meaning_vector": meaning_vector,
        "meaning_ok": bool(meaning.get("ok", False)),
        "stability": _round4(_as_float(state.get("stability"))),
        "drift": _round4(_as_float(state.get("drift"))),
        "std": _round4(_as_float(state.get("std"))),
        "alignment": _round4(_as_float(state.get("alignment"))),
        "state_ok": bool(state.get("ok", False)),
        "stability_ok": bool(state.get("stability_ok", False)),
        "safety_ok": bool(safety.get("ok", False)),
        "safety_violations": list(safety.get("violations") or ()),
        "confidence": _round4(_as_float(confidence.get("confidence"))),
        "restricted": bool(confidence.get("restricted", False)),
        "output_budget": _round4(_as_float(confidence.get("output_budget"))),
        "register": str(language.get("register") or _DEFAULT_REGISTER),
        "tone": str(language.get("tone") or "measured"),
        "meaning_sha": str(language.get("meaning_sha") or ""),
        "persona": str(fusion.get("dominant") or "maya"),
    }


def _frame_json(cognitive):
    if cognitive is None:
        return "unavailable"
    fields = {
        "meaning": cognitive["meaning_scalar"],
        "meaning_vector": [float(v) for v in cognitive["meaning_vector"]],
        "stability": cognitive["stability"],
        "drift": cognitive["drift"],
        "std": cognitive["std"],
        "confidence": cognitive["confidence"],
        "alignment": cognitive["alignment"],
        "register": cognitive["register"],
        "safety_ok": cognitive["safety_ok"],
        "state_ok": cognitive["state_ok"],
    }
    return json.dumps(fields, sort_keys=True, ensure_ascii=False)


def expression_directive(cognitive):
    """Reduce a cognitive frame to the deterministic expression directive."""
    if cognitive is None:
        text = ("Structured cognitive state: unavailable. Constrain "
                "language: reply in one brief sentence, be clear that a "
                "stable reading is unavailable, and do not assert facts "
                "beyond what is provided.")
        return {"register": "reserved", "budget": _BUDGET_HOLD,
                "holds": ["intelligence_unavailable"], "text": text}
    holds = []
    if not cognitive["safety_ok"]:
        holds.append("safety_boundary")
    if not cognitive["stability_ok"]:
        holds.append("unstable_world_model")
    if not cognitive["meaning_ok"]:
        holds.append("meaning_not_ok")
    if not cognitive["state_ok"]:
        holds.append("state_not_ok")
    if cognitive["restricted"]:
        holds.append("low_confidence")
    if holds:
        register = "reserved"
        budget = _BUDGET_HOLD if ("safety_boundary" in holds or
                                  "unstable_world_model" in holds or
                                  "meaning_not_ok" in holds or
                                  "state_not_ok" in holds) else _BUDGET_RESTRICTED
        text = ("Structured cognitive state: " + _frame_json(cognitive) +
                " Constrain language: register=%s; output budget=%s; "
                "holds=%s. Reply in one brief sentence; do not present "
                "uncertain or unstable states as fact."
                % (register, budget, ",".join(holds)))
    else:
        register = cognitive["register"] or _DEFAULT_REGISTER
        budget = _BUDGET_FULL
        text = ("Structured cognitive state: " + _frame_json(cognitive) +
                " Constrain language: register=%s; output budget=%s. "
                "Reply directly and concisely in the deterministic "
                "register, without restating the frame." % (register, budget))
    return {"register": register, "budget": int(budget), "holds": holds,
            "text": text}


def detect_user_input(user_text):
    """Batch #4: deterministic representation detection on the raw input.

    Structured text lines are parsed as JSON when they clearly are containers;
    otherwise the raw text line is detected directly. Command routing in
    ``maya_chat`` is untouched — this runs only on the free-form intelligence
    path. Deterministic and exception-free on the bridge boundary.
    """
    text = "" if user_text is None else user_text
    stripped = str(text).strip()
    parsed = None
    if stripped and stripped[0] in ("{", "["):
        try:
            parsed = json.loads(str(text))
        except (ValueError, RecursionError):
            parsed = None
    if parsed is not None and not isinstance(parsed, (bool, type(None))):
        return _detect_representation(parsed)
    return _detect_representation(str(text))


def _bus_input_declared_from(detection):
    """Map a KNOWN non-text detection onto a bus typed input value.

    Free text stays on the bridge default (typed text), so existing chat
    behavior is unchanged; structured detections commit the more specific
    shared representation type into the record.
    """
    if detection is None:
        return None
    if detection.get("status") != "KNOWN":
        return None
    kind = detection.get("detected_type")
    if kind in (None, "text"):
        return None
    candidate = detection.get("canonical_candidate")
    if not isinstance(candidate, dict) or "type" not in candidate \
            or "value" not in candidate:
        return None
    return dict(candidate)


def _world_mapping_for(detection, user_text, created_at):
    """Batch #5: representation -> world-model mapping for the turn.

    Deterministic: the mapping is computed from the detector verdict and the
    caller-supplied temporal provenance only. When ``created_at`` is absent
    the mapping is still computed (structural claims carry the provenance
    timestamp only when the caller supplies one).
    """
    provenance = None
    if created_at is not None:
        provenance = {"source": "bridge.conversation",
                      "source_url": None, "retrieved_at": created_at,
                      "evidence_type": "observation", "confidence": "medium",
                      "claim": "Conversational turn mapped to the "
                               "world-model vocabulary."}
    try:
        return map_to_world(detection, original=str(user_text)
                            if user_text is not None else None,
                            provenance=provenance)
    except Exception:
        return None


def _persona_fusion_for(detection, world_mapping, persona_context=None):
    """Batch #6: persona activation + weighted fusion for the turn.

    Deterministic lens over the turn's shared state: relevance comes from the
    detector verdict and the world mapping only, plus any *explicit* caller
    context (task type / switches) — never invented intent. Absent evidence
    yields the explicit NO_ACTIVE_PERSONA state (or None on corrupt input),
    so the conversational path never fabricates a persona.
    """
    try:
        detected_type = detection.get("detected_type") \
            if isinstance(detection, dict) else None
        context = dict(persona_context or {})
        task_type = context.get("task_type")
        switches = context.get("switches")
        mapping = world_mapping if isinstance(world_mapping, dict) else None
        state_reference = "world_mapping"
        if isinstance(mapping, dict) and isinstance(
                mapping.get("provenance"), dict):
            retrieved = mapping["provenance"].get("retrieved_at")
            if isinstance(retrieved, str):
                state_reference = "world_mapping@%s" % (retrieved,)
        core_epistemic = mapping.get("epistemic") \
            if isinstance(mapping, dict) else None
        return _persona.compute(
            world_mapping=mapping,
            detected_type=detected_type,
            task_type=task_type,
            switches=switches,
            state_reference=state_reference,
            core_epistemic=core_epistemic,
        )
    except Exception:
        return None


def _handoff_to_bus(user_text, history, sequence, envelope, environment,
                    created_at, bus_enabled, detection=None,
                    persona_context=None):
    """Unify one turn into the shared state bus (Batch #3 handoff).

    Deterministic and exception-free on the bridge boundary: when the bus is
    disabled (``MAYA_BUS_DISABLED=1``), temporal context is missing, or the
    record fails validation, the envelope reports the reason and the
    conversational path still completes normally. The bus never invents a
    timestamp; ``created_at`` is caller-supplied.
    """
    try:
        enabled = bus_handoff_enabled() if bus_enabled is None else \
            bool(bus_enabled)
        world_mapping = _world_mapping_for(detection, user_text, created_at)
        return publish_turn(
            user_text=user_text,
            history=_clean_history(history),
            features={},
            cognitive=envelope.get("cognitive") or {},
            directive=envelope.get("directive") or {},
            sequence=sequence,
            environment=environment,
            source="bridge.conversation",
            created_at=created_at,
            bus_enabled=enabled,
            input_declared=_bus_input_declared_from(detection),
            world_mapping=world_mapping,
            persona_fusion=_persona_fusion_for(detection, world_mapping,
                                               persona_context),
        )
    except Exception as exc:
        return {"engaged": False, "minted": False,
                "reason": "handoff_error: %s: %s"
                          % (type(exc).__name__, exc),
                "state": None, "digest": None}


def run_conversation_for_expression(user_text, history=None, sequence=0,
                                    run_func=None, environment="local",
                                    created_at=None, bus_enabled=None,
                                    persona_context=None):
    """Run the intelligence core for one free-form conversational turn.

    Returns an envelope with the cognitive frame, the expression directive,
    the unified-state bus record for the turn, and the identity behavior
    block (Batch 8J-B). The immutable identity behavior context is derived
    AFTER semantic extraction and merged into the directive text, so
    identity constrains response behavior without biasing interpretation
    and without weakening the verification gates (register/budget/holds are
    never modified). Never raises: any intelligence failure degrades to a
    safe hold directive (deterministic, language-boundary preserved), and a
    failed handoff is reported without crashing the conversational path.
    """
    envelope = {"invoked": False, "ok": False, "failure": None,
                "cognitive": None, "directive": None, "detection": None,
                "identity": None}
    try:
        features = map_conversation(user_text, history, sequence,
                                    environment=environment)
        detection = detect_user_input(user_text)
        runner = run_func if run_func is not None else _run_loop
        frame = runner(**features)
        resolved = frame.get("result") if isinstance(frame, dict) else None
        cognitive = _extract_cognitive(resolved or frame)
        directive = expression_directive(cognitive)
        identity_block = None
        identity_extra = ""
        try:
            from maya_identity.behavior import build_identity_behavior
            identity_block = build_identity_behavior()
            identity_extra = (identity_block.text or "") \
                if identity_block is not None else ""
        except Exception:
            identity_block = None
            identity_extra = ""
        if directive is not None and identity_extra:
            directive = dict(directive)
            directive["text"] = (directive.get("text") or "") + (
                "\n\n" + identity_extra if directive.get("text")
                else identity_extra)
        envelope.update({
            "invoked": True,
            "ok": bool(cognitive is not None and directive is not None),
            "cognitive": cognitive,
            "directive": directive,
            "detection": detection,
            "identity": identity_block.to_plain()
            if identity_block is not None else None,
        })
    except Exception as exc:
        envelope["failure"] = "%s: %s" % (type(exc).__name__, str(exc))
        envelope["directive"] = expression_directive(None)
    envelope["bus"] = _handoff_to_bus(user_text, history, sequence, envelope,
                                      environment, created_at, bus_enabled,
                                      detection=envelope["detection"],
                                      persona_context=persona_context)
    return envelope
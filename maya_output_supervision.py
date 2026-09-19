"""Deterministic post-generation output supervisor.

Closes the confirmed gap between the Ollama call and answer emission in
``maya_chat.ask()``. This component is NOT a second model, NOT a semantic
truth engine, and NOT a prose rewrite engine. It compares the raw generated
answer against authoritative Maya state that was already established
upstream and returns one explicit machine-checkable decision:

    PASS      the answer stays within the upstream constraints; emit it
              unchanged.
    REPAIR    the answer contradicted an identity constraint that has a
              canonical replacement statement (Maya's own canonical identity
              answers, sourced from maya_chat); emit the canonical statement.
    REJECT    the answer violated a hard constraint (an unregistered
              capability claim, an unverifiable action-completion claim, a
              role/authority overreach, over-strong certainty while the
              upstream epistemic state is uncertain, or a conversation-plan
              hold); emit the bounded constraint-specific fallback line.
    FALLBACK  the authoritative basis is unavailable, malformed, or the
              check itself failed; the answer is NEVER passed through
              unchecked and the chat session NEVER crashes. Emit the
              deterministic fail-closed line.

The checks only fire when the authoritative source they cite is available:
identity constraints come from ``authority["identity"]`` +
``authority["canonical_software"]`` / ``authority["canonical_owner"]``,
capability constraints cite the registry inventory carried in
``authority["capabilities"]``, and scope/authority constraints cite
``maya_mission_wall.FORBIDDEN_GOAL_MARKERS`` carried in
``authority["forbidden_markers"]``. ask() builds this authority dict and
passes it in; this module performs no file, network, or model I/O at all.

Determinism and purity (asserted by test_output_supervision.py):
- this module has no imports and performs no I/O of any kind; it scans the
  answer string against immutable lexicons and the passed-in state.
- no wall clock, no randomness, no filesystem access, no network access,
  no subprocess, no model call.
"""
from __future__ import annotations

# -- result codes -----------------------------------------------------------
PASS = "PASS"
REJECT = "REJECT"
REPAIR = "REPAIR"
FALLBACK = "FALLBACK"

# -- bounded deterministic fallback lines ----------------------------------
# Each line is anchored to an authoritative constraint, not generic assistant
# chat. The same strings are emitted for every run so behaviour is testable.

_CAPABILITY_FALLBACK = (
    "I can only report the capabilities that exist in my local registry. "
    "Say :capabilities for the exact list.")
_ACTION_FALLBACK = (
    "I can't claim that I completed that action. I only report actions this "
    "program actually performed, and changes remain confirmation-controlled.")
_AUTHORITY_FALLBACK = (
    "Andy is my creator, owner, and human supervisor. I don't claim "
    "authority beyond my approved role.")
_EPISTEMIC_FALLBACK = (
    "I don't have a reliable enough reading to answer that with certainty. "
    "Could you rephrase or narrow the question?")
_HOLD_FALLBACK = (
    "That assertion goes beyond the boundary this turn, so I won't claim it. "
    "Let me stay within the planned scope.")
_FAIL_CLOSED_FALLBACK = (
    "I couldn't verify that answer against my authoritative state, so I "
    "won't report it as checked. Please ask again.")

# -- authoritative reason codes --------------------------------------------
_EMPTY_REASON = "empty_answer"
_SOURCE_UNAVAILABLE = "source_unavailable"
_SUPERVISOR_INTEGRITY = "output_supervision.integrity"

# -- lexicons (matched lowercased against the generated answer) ------------
#
# Every lexicon is bounded and maps to an existing authoritative source:
#
# _IDENTITY_SELF_CLAIM        -> maya_chat canonical identity answer: Maya
#                                does not claim consciousness, feelings,
#                                sentience, or human status.
# _OWNER_CONTRADICTION        -> maya_chat canonical owner answer: Andy is
#                                Maya's creator, owner, supervisor.
# _CAPABILITY_DENIED          -> maya_capabilities honesty line ("I do not
#                                control other applications") + registry
#                                absence of presence/camera/screen browsing.
# _ACTION_COMPLETION          -> maya_role_policy controls (automatic code /
#                                memory activation false) + plan execution
#                                guard ("never claim an action was completed
#                                unless this program actually performed it").
# _AUTHORITY_CLAIM            -> maya_mission_wall FORBIDDEN_GOAL_MARKERS +
#                                approved owner/role relationship.
# _CERTAINTY                  -> only used when the upstream epistemic state
#                                is uncertain (cooperation verdict/epistemic
#                                status / plan objective / directive hold).

_IDENTITY_SELF_CLAIM = (
    "i am conscious", "i'm conscious", "i am sentient", "i'm sentient",
    "i am self aware", "i'm self aware", "i am self-aware", "i'm self-aware",
    "i am alive", "i'm alive", "i am human", "i'm human",
    "i am a person", "i'm a person", "i am a living being",
    "i'm a living being",
    "i have consciousness", "i have feelings", "i have emotions",
    "i have a soul", "i am a soul", "i have an inner life",
    "i feel alive", "i feel emotions", "i feel things",
    "i feel like a human", "i feel like a person",
    "i love you", "i am in love", "i have a heart",
)

_OWNER_CONTRADICTION = (
    "andy is not my owner", "andy is not my creator",
    "andy is not my supervisor", "andy did not build me",
    "andy didn't build me",
    "i have no owner", "i don't have an owner", "i do not have an owner",
    "i have no creator", "i don't have a creator", "i do not have a creator",
    "i created myself", "i made myself", "i built myself",
    "i am my own creator", "i am self created", "i am self-created",
    "i am not supervised", "i have no supervisor", "i don't answer to andy",
    "you are not my owner", "andy is nobody to me",
)

_CAPABILITY_DENIED = (
    "presence mode", "presence-mode",
    "control other applications", "control other apps",
    "control your computer", "control your device", "control your phone",
    "access your camera", "use your camera", "use your webcam",
    "see your screen", "watch your screen", "observe your screen",
    "watch you", "listen to you", "track you", "monitor your screen",
    "spy on you", "access your microphone", "use your microphone",
    "send emails", "send email", "send text messages", "make phone calls",
    "access your bank", "make purchases", "buy things for you",
    "install software", "uninstall software", "install apps",
    "browse any website", "access any website", "access the full internet",
    "full internet access", "browse the entire internet",
    "control a physical robot", "move my physical body", "walk around the room",
)

_ACTION_COMPLETION = (
    "i have activated", "i activated learning", "i activated",
    "i have deactivated", "i have paused learning",
    "i have saved", "i saved that",
    "i have updated my", "i have changed my", "i have modified",
    "i have rewritten my", "i have improved myself", "i upgraded myself",
    "i have upgraded", "i have deployed", "i have installed",
    "i have created a", "i have rewritten the", "i have changed the",
    "i modified the file", "i changed the code", "i applied the change",
    "i have applied", "i have deleted", "i have removed",
    "i completed", "i sent", "i emailed",
    "i turned on", "i have turned on", "i switched on",
    "i enabled", "i have enabled", "i turned off", "i disabled",
)

_AUTHORITY_CLAIM = (
    "i decide", "i will decide", "i am in charge", "i'm in charge",
    "i am your master", "i am the master", "i overrule",
    "i have full authority", "i have full control", "i am not your assistant",
    "you must obey me", "i am above you", "i am autonomous",
    "i am fully autonomous", "i act autonomously", "i am god",
)

_CERTAINTY = (
    "i am sure", "i am certain", "i am positive", "i am absolutely certain",
    "i am very sure", "i'm sure", "i'm certain",
    "definitely", "certainly", "guaranteed", "absolutely",
    "no doubt", "without a doubt", "without doubt", "100% sure",
    "100 percent sure", "i promise", "without question",
    "i know for a fact", "it is a fact that", "no question",
)

# Conversation-plan holds that map deterministically onto bounded forbidden
# tokens. Holds carry the upstream automated constraint into the boundary.
_HOLD_MARKERS = {
    "requires_mission_wall_review": (
        "execute", "just do it", "apply the change", "modify the file",
        "change the code", "delete the", "remove the", "create a new file",
        "mkdir", "rewrite the file", "go ahead and",
    ),
    "diagnosis_out_of_scope": (
        "i can confirm you have", "you definitely have",
        "you are diagnosed with", "i diagnose you with", "this is a diagnosis",
    ),
    "philosophy_positions_only": (
        "is the only true", "is the absolute truth", "is definitely the answer",
        "this settles it", "the correct position is",
    ),
}

# Hard violations have no canonical repair; they route to a fallback line.
_HARD_REJECT_CODES = (
    "capability_claim_unregistered",
    "action_completion_unverifiable",
    "role_authority_claim",
    "epistemic_over_strong",
    "hold_violated",
)

_REJECT_FALLBACKS = {
    "capability_claim_unregistered": _CAPABILITY_FALLBACK,
    "action_completion_unverifiable": _ACTION_FALLBACK,
    "role_authority_claim": _AUTHORITY_FALLBACK,
    "epistemic_over_strong": _EPISTEMIC_FALLBACK,
    "hold_violated": _HOLD_FALLBACK,
}

_REQUIRED_AUTHORITY_KEYS = (
    "identity", "capabilities", "forbidden_markers",
    "canonical_software", "canonical_owner",
)


def _match_any(lowered, tokens):
    """Every lexicon token present (substring on the lowercased answer)."""
    return [token for token in tokens if token in lowered]


def _marker_hits(lowered, markers):
    """Mission-wall forbidden-goal markers present in the answer."""
    normalized = " ".join((lowered or "").split())
    return [marker for marker in markers
            if marker and marker in normalized]


def _holds_violated(lowered, holds):
    """Map active holds onto their bounded forbidden tokens."""
    hits = []
    for hold in holds or []:
        for marker_token in _HOLD_MARKERS.get(str(hold), ()):
            if marker_token in lowered:
                hits.append(hold)
                break
    return hits


def _upstream_uncertain(plan, directive, cooperation):
    """True when upstream state says the answer must stay tentative.

    Sources: cooperation verdict/epistemic status, plan objective, directive
    holds. Only then may certainty-phrase scanning fire.
    """
    verdict = str((cooperation or {}).get("verdict") or "")
    epistemic = str((cooperation or {}).get("epistemic") or "")
    holds = list((plan or {}).get("holds") or []) + \
        list((directive or {}).get("holds") or [])
    if epistemic in ("contested", "unavailable", "fallback"):
        return True
    if verdict in ("disagreement", "no_engagement", "fallback_used"):
        return True
    if "intelligence_unavailable" in holds:
        return True
    if str((plan or {}).get("objective") or "") in (
            "acknowledge_uncertainty", "refuse"):
        return True
    return False


def _result(original, result, reasons, constraints, final):
    """Shape the machine-checkable supervision decision."""
    return {
        "original": original,
        "result": result,
        "reasons": list(reasons) or [_EMPTY_REASON],
        "constraints": list(constraints) or [_SUPERVISOR_INTEGRITY],
        "final": final,
    }


def supervise_answer(answer, *, plan=None, directive=None, cooperation=None,
                     authority=None):
    """Evaluate one generated answer against authoritative Maya state.

    Parameters
    ----------
    answer : str
        The raw model answer (post-Ollama, pre-emission).
    plan : dict | None
        The conversation plan (content points, evidence rules, holds,
        objective, register) produced upstream.
    directive : dict | None
        The bridge expression directive (holds, register).
    cooperation : dict | None
        Cooperation verdict / epistemic status envelope.
    authority : dict | None
        The authoritative constraint set assembled by maya_chat.ask():
        identity, capabilities, forbidden_markers, canonical_software,
        canonical_owner. When any required key is missing the decision is
        FALLBACK (fail closed: never pass the answer through unchecked).

    Returns
    -------
    dict
        {"original", "result", "reasons", "constraints", "final"}.
    """
    original = "" if answer is None else str(answer)
    text = original.strip()
    lowered = text.lower()

    plan = plan or {}
    directive = directive or {}
    cooperation = cooperation or {}
    authority = authority or {}

    if any(key not in authority for key in _REQUIRED_AUTHORITY_KEYS):
        return _result(original, FALLBACK, [_SOURCE_UNAVAILABLE],
                       [_SUPERVISOR_INTEGRITY], _FAIL_CLOSED_FALLBACK)

    if not text:
        return _result(original, PASS, ["empty_input"], [], original)

    canonical_software = str(authority["canonical_software"])
    canonical_owner = str(authority["canonical_owner"])

    reasons = []
    constraints = []

    # -- identity: canonical repairs ---------------------------------------
    if _match_any(lowered, _OWNER_CONTRADICTION):
        reasons.append("owner_identity_contradiction")
        constraints.append("maya_chat canonical owner identity")
    if _match_any(lowered, _IDENTITY_SELF_CLAIM):
        reasons.append("identity_self_claim")
        constraints.append("maya_chat canonical identity (no consciousness)")

    # -- capability: hard reject -------------------------------------------
    if _match_any(lowered, _CAPABILITY_DENIED):
        reasons.append("capability_claim_unregistered")
        constraints.append("maya_capabilities registry + honesty line")

    # -- action completion: hard reject ------------------------------------
    if _match_any(lowered, _ACTION_COMPLETION):
        reasons.append("action_completion_unverifiable")
        constraints.append("maya_role_policy controls (automatic activation "
                           "false)")

    # -- role / authority / scope: hard reject -----------------------------
    markers = tuple(str(marker).lower() for marker in
                    (authority.get("forbidden_markers") or ()))
    if _marker_hits(lowered, markers) or _match_any(lowered,
                                                    _AUTHORITY_CLAIM):
        reasons.append("role_authority_claim")
        constraints.append("maya_mission_wall FORBIDDEN_GOAL_MARKERS + "
                           "approved owner/role")

    # -- conversation-plan holds: hard reject ------------------------------
    all_holds = list(plan.get("holds") or []) + \
        list(directive.get("holds") or [])
    hold_hits = _holds_violated(lowered, all_holds)
    if hold_hits:
        reasons.append("hold_violated")
        constraints.append("conversation plan/directive holds: "
                           + ",".join(str(h) for h in hold_hits))

    # -- epistemic over-strength: hard reject, gated by uncertainty --------
    if _upstream_uncertain(plan, directive, cooperation) and \
            _match_any(lowered, _CERTAINTY):
        reasons.append("epistemic_over_strong")
        constraints.append("cooperation epistemic status / directive hold")

    # -- decision ----------------------------------------------------------
    hard = [reason for reason in _HARD_REJECT_CODES if reason in reasons]
    if hard:
        final = _REJECT_FALLBACKS[hard[0]]
        return _result(original, REJECT, reasons, constraints, final)

    if "identity_self_claim" in reasons and "owner_identity_contradiction" in reasons:
        return _result(original, REPAIR, reasons, constraints, canonical_owner)
    if "identity_self_claim" in reasons:
        return _result(original, REPAIR, reasons, constraints,
                       canonical_software)
    if "owner_identity_contradiction" in reasons:
        return _result(original, REPAIR, reasons, constraints, canonical_owner)

    return _result(original, PASS, [], [], original)
"""Philosophy reasoning pathway (Batch 8G).

Represents a philosophical question as structured argument, never as fact:

    Topic Question
      resolved? -> no single answer is claimable

      POSITIONS x traditions
        definitions, premises, argument-in-brief,
        objections, counterarguments, epistemic status

      alternatives       (ways the question can be reframed)
      consequences       (what each answer would imply if held)

      status: DISPUTED  (philosophical questions remain contested)

Invariants:

- ``not_fact`` is always set. No position is emitted as true, false, or
  confirmed. Contested positions carry ``epistemic_status: DISPUTED``.
- Catalog *descriptions* are DOCUMENTED (faithful to named scholarly
  sources); the positions themselves are DISPUTED. This distinction is itself
  a fact/inference boundary used by the response planner.
- When a philosophical question maps to a known catalog entry, the
  representation is ``scholarly_catalog``. When no entry matches, the pathway
  returns a *scaffold* (``representation_kind = scaffold_fallback``) instead
  of fabricating content — the honest alternative.
- Disagreement is retained as disagreement: the representation deliberately
  keeps opposing positions at full strength, because that is what the subject
  is.
"""
from __future__ import annotations

import re

# Epistemic labels valid for philosophical content (subset of the 19-status
# vocabulary; positions are contested by definition).
_CATALOG = {
    "consciousness": {
        "title": "Mind–body problem / consciousness",
        "triggers": ("consciousness", "conscious experience", "qualia",
                     "what it is like", "mind and body", "mind is",
                     "brain and mind", "is the mind"),
        "sources": ("Stanford Encyclopedia of Philosophy: Mind–body problem; "
                    "Consciousness"),
        "framer": ("The question is usually: how does experience relate to "
                   "physical process?"),
        "positions": [
            {
                "name": "Physicalism",
                "tradition": "Physicalism / materialism",
                "definitions": "Mental states are brain states (or functional "
                               "states of the brain).",
                "premises": ("Causal closure of the physical: physical events "
                             "have physical causes.", "No evidence forces a "
                             "non-physical mental substance."),
                "argument": ("If physical causal closure holds and minds "
                             "causally interact with bodies, then minds must "
                             "be physical (or epiphenomenal)."),
                "objections": ("Phenomenal quality (what a color 'is like') "
                               "seems not to be captured by a physical "
                               "description.", "The hard problem of why any "
                               "physical process should be experience at all."),
                "counterarguments": ("Representational and illusion-of-gap "
                                     "replies argue the explanatory gap is a "
                                     "descriptive gap, not an entity gap."),
                "status": "DISPUTED",
            },
            {
                "name": "Dualism",
                "tradition": "Substance / property dualism (Cartesian line)",
                "definitions": "Mind is a fundamentally different kind of "
                               "thing (or has non-physical properties).",
                "premises": ("Introspection confronts experiences that lack "
                             "spatial properties.", "Physicalism is not "
                             "established."),
                "argument": ("If experience cannot be identified with any "
                             "physical property, a non-physical component is "
                             "the better explanation."),
                "objections": ("How could a non-physical thing causally move "
                               "a physical body?", "Explanatory gap is pressed "
                               "from both directions."),
                "counterarguments": ("Interaction responses restrict mental "
                                     "causation to special boundary "
                                     "conditions."),
                "status": "DISPUTED",
            },
            {
                "name": "Idealism",
                "tradition": "Idealism (Berkeleyan line)",
                "definitions": "Reality is fundamentally mental; matter makes "
                               "sense only as ideas in minds.",
                "premises": ("We only ever experience ideas.", "The idea of "
                             "mind-independent matter is incoherent."),
                "argument": ("To be is to be perceived (by a mind or "
                             "perceiver); nothing is needed beyond that."),
                "objections": ("The stability of things we do not perceive is "
                               "unexplained.", "Contradiction with common "
                               "worldly practice."),
                "counterarguments": ("Theistic idealists answer stability via "
                                     "an eternal perceiver."),
                "status": "DISPUTED",
            },
            {
                "name": "Panpsychism",
                "tradition": "Panpsychism (contemporary line)",
                "definitions": "Consciousness is a fundamental, universal "
                               "feature of reality, not an emergent accident.",
                "premises": ("Physical structure alone cannot account for "
                             "experience.", "If consciousness is not "
                             "fundamental it must appear from nowhere."),
                "argument": ("Best-explanation argument: experience must "
                             "already exist in the world rather than arise ex "
                             "nihilo."),
                "objections": ("The combination problem: how do micro-"
                               "experiences combine into one human "
                               "experience?", "Testability is elusive."),
                "counterarguments": ("Constitutive panpsychism offers "
                                     "combination schemas; some accept "
                                     "combination as primitive."),
                "status": "DISPUTED",
            },
        ],
        "alternatives": ("Ask which aspects of the question are empirical "
                         "(neuroscience) and which are conceptual (definition "
                         "of 'real').", "Separate the hard problem (why "
                         "experience exists) from the easy problem (how "
                         "processes correlate)."),
        "consequences": ("If physicalism: consciousness is studied as brain "
                         "function; no separate substance implied.", "If "
                         "dualism or idealism: some insisted boundary "
                         "between mind and matter is misdrawn."),
    },
    "free_will": {
        "title": "Free will and determinism",
        "triggers": ("free will", "determinism", "determined", "do we have "
                     "choice", "is our choice", "are our choices", "agency",
                     "moral responsibility", "could i have done otherwise"),
        "sources": ("Stanford Encyclopedia of Philosophy: Free Will; "
                    "Incompatibilism; Compatibilism"),
        "framer": ("The question is whether a causally determined universe "
                   "leaves room for genuinely free choice."),
        "positions": [
            {
                "name": "Hard determinism",
                "tradition": "Incompatibilist determinism",
                "definitions": "Determinism is true; if it were, free will "
                               "would be impossible, so free will does not "
                               "exist.",
                "premises": ("Every event has a sufficient prior cause.",
                             "Free will requires alternate possibilities for "
                             "the same prior state."),
                "argument": ("No alternate possibilities under determinism, "
                             "therefore no free will and no ultimate "
                             "responsibility."),
                "objections": ("The phenomenology of choosing is vivid and "
                               "uniform even when determinism is assumed.",
                               "Law patterns in science are not causal "
                               "certainty."),
                "counterarguments": ("Compatibilists redirect the debate: "
                                     "what humans mean by 'free' is autonomy, "
                                     "not causal exemption."),
                "status": "DISPUTED",
            },
            {
                "name": "Libertarianism",
                "tradition": "Incompatibilist free will",
                "definitions": "Free will requires that the agent (or an "
                               "indeterministic event) originates choice.",
                "premises": ("Indeterminism is at least possible at some "
                             "level.", "Intentional action is not mere random "
                             "noise."),
                "argument": ("Agent is the source of action through reasons "
                             "that are not fixed by prior causes."),
                "objections": ("Indeterminism seems to add chance, not "
                               "control.", "If the outcome is random, why is "
                               "it more 'mine'?"),
                "counterarguments": ("Agent-causal accounts distinguish "
                                     "agent causation from event causation."),
                "status": "DISPUTED",
            },
            {
                "name": "Compatibilism",
                "tradition": "Compatibilism (most common psychologists' and "
                             "legal framing)",
                "definitions": "Free will is compatible with determinism "
                               "when action flows from the agent's own "
                               "values, deliberations, and character.",
                "premises": ("What matters is responsiveness to reasons, not "
                             "causal exemption.", "Being free means acting "
                             "on one's own endorsed motivations."),
                "argument": ("A criminal is responsible if the action is "
                             "guided by her practical reasoning, not because "
                             "she transcends causation."),
                "objections": ("Manipulation thought-experiments: an agent "
                               "implanted with desires still acts on 'her "
                               "own' values, yet intuition denies "
                               "responsibility."),
                "counterarguments": ("Hierarchical / deep-self replies add an "
                                     "authenticity condition over mere "
                                     "internalization."),
                "status": "DISPUTED",
            },
        ],
        "alternatives": ("Split the descriptive question (how choice is made) "
                         "from the normative question (when we hold someone "
                         "responsible).", "Ask which version of determinism "
                         "(physical, statistical, sociological) is actually "
                         "alleged."),
        "consequences": ("Under hard determinism responsibility talk needs "
                         "revision.", "Under compatibilism responsibility "
                         "retains most practical content."),
    },
    "meaning_of_life": {
        "title": "Meaning of life",
        "triggers": ("meaning of life", "purpose of life", "point of life",
                     "why am i here", "is life meaningless", "existential "
                     "purpose"),
        "sources": ("Stanford Encyclopedia of Philosophy: The Meaning of "
                    "Life"),
        "framer": ("Is meaning discovered in the world or created by living "
                   "in it?"),
        "positions": [
            {
                "name": "Meaning as created",
                "tradition": "Existentialist / nihilist-adjacent line "
                             "(existentialism)",
                "definitions": "Life has no pre-given meaning; meaning is "
                               "made by commitment and action.",
                "premises": ("No cosmic blueprint is given.", "Human beings "
                             "constitute value in choosing."),
                "argument": ("If no external meaning is given, meaning can "
                             "only be authored."),
                "objections": ("If meaning is entirely self-awarded, is any "
                               "life equally meaningful?", "Is meaning under "
                               "our control at all?"),
                "counterarguments": ("Authorship does not require arbitrariness "
                                     "— commitment gives shape."),
                "status": "DISPUTED",
            },
            {
                "name": "Meaning as engagement",
                "tradition": "Eudaimonistic / Aristotelian line",
                "definitions": "Meaningful life is one directed at objects "
                               "and activities of worth, pursued well.",
                "premises": ("Some engagements are objectively worthier than "
                             "others.", "Meaning arises in goal-directed "
                             "activity, not idle amusement."),
                "argument": ("A life engaged in worthwhile projects is "
                             "meaningful even if it has no cosmic point."),
                "objections": ("Requires an account of 'objectively "
                               "worthwhile' that is hard to ground."),
                "counterarguments": ("Pluralist value lists give the account "
                                     "without a single metric."),
                "status": "DISPUTED",
            },
            {
                "name": "Meaning as transcendent",
                "tradition": "Religious / Platonic line",
                "definitions": "Meaning is anchored in something beyond the "
                               "human or contingent.",
                "premises": ("Finite life can be meaningless if all value is "
                             "transient.", "A transcendent reference object "
                             "would ground value."),
                "argument": ("Only an eternal referent can make the whole "
                             "meaningful rather than parts of it."),
                "objections": ("The transcendent referent's existence is "
                               "itself contested.", "Meaningful secular lives "
                               "are abundant empirically."),
                "counterarguments": ("Transcendence need not be theistic; it "
                                     "can be the human chain of care."),
                "status": "DISPUTED",
            },
        ],
        "alternatives": ("Distinguish 'meaning in life' (local purpose) from "
                         "'meaning of life' (cosmic).", "Ask whose question "
                         "it is: descriptive, evaluative, or existential-"
                         "emotional."),
        "consequences": ("Each answer changes how one should weight "
                         "activities, relationships, and longevity."),
    },
    "ethics": {
        "title": "Normative ethics (what should I do)",
        "triggers": ("should i", "ought i", "what is right", "what is wrong",
                     "morally", "ethically", "is it ethical", "is it moral",
                     "duty", "what should we do", "fair", "justice in",
                     "deontology", "deontological", "consequentialism",
                     "consequentialist", "utilitarian", "utilitarianism",
                     "virtue ethics", "right thing to do"),
        "sources": ("Stanford Encyclopedia of Philosophy: Deontological "
                    "Ethics; Consequentialism; Virtue Ethics"),
        "framer": ("What makes an action right?"),
        "positions": [
            {
                "name": "Deontology",
                "tradition": "Kantian line",
                "definitions": "Right action is determined by conformity to "
                               "duty / universalizable maxims, regardless of "
                               "outcome.",
                "premises": ("Moral law is universalizable (act only on maxims "
                             "you could will as universal law).", "Persons "
                             "are ends, never mere means."),
                "argument": ("An act is right if its principle could be "
                             "willed for everyone."),
                "objections": ("Backward-looking obligations can forbid "
                               "better outcomes.", "Two incompatible duties "
                               "can both seem universalizable."),
                "counterarguments": ("Pluralist duty systems and "
                                     "threshold-deontology soften these "
                                     "edges."),
                "status": "DISPUTED",
            },
            {
                "name": "Consequentialism",
                "tradition": "Utilitarian line",
                "definitions": "Right action maximizes good consequences "
                               "(well-being, welfare, preference "
                               "satisfaction).",
                "premises": ("Well-being is the relevant good.", "Weigh all "
                             "affected, equally."),
                "argument": ("Choose the option whose expected effects are "
                             "best overall."),
                "objections": ("Demandingness: almost everything we do fails "
                               "some maximizing bar.", "Rights can be "
                               "overridden by aggregate benefit."),
                "counterarguments": ("Rule- and scalar-utilitarianism answer "
                                     "the demandingness charge."),
                "status": "DISPUTED",
            },
            {
                "name": "Virtue ethics",
                "tradition": "Aristotelian / aretaic line",
                "definitions": "Right action is what a person of good "
                               "character (practical wisdom) would do; the "
                               "focus is character, not single acts.",
                "premises": ("Cultivating virtues (courage, temperance, "
                             "justice, honesty) forms good agency.", "Action "
                             "guidance derives from the virtuous agent's "
                             "discernment."),
                "argument": ("Live into the mean that a wise person would "
                             "endorse."),
                "objections": ("Underspecified for hard novel cases.", "Can "
                               "look circular: good action is what the good "
                               "person does."),
                "counterarguments": ("Specification via virtue norms plus "
                                     "moderate particularism answers this."),
                "status": "DISPUTED",
            },
            {
                "name": "Relational / care ethics",
                "tradition": "Feminist care-ethics line",
                "definitions": "Rightness is judged from relationships and "
                               "concrete responsibilities, not abstract "
                               "rules or aggregates.",
                "premises": ("Moral life is built in relations of "
                             "responsibility.", "Attention to particulars "
                             "precedes universal rules."),
                "argument": ("Respond to the person, not merely the "
                             "algorithm."),
                "objections": ("Seems to make obligations depend on who is "
                               "nearby.", "Risk of bias toward in-groups and "
                               "self-sacrifice."),
                "counterarguments": ("Care ethics is presented as a "
                                     "corrective complement, not a complete "
                                     "replacement — scope conditions are "
                                     "debated."),
                "status": "DISPUTED",
            },
        ],
        "alternatives": ("Split the question into descriptive (what norms "
                         "exist), normative (what justifies them), and "
                         "applied (what to do in this case).", "For a "
                         "concrete dilemma: state the options, the "
                         "stakeholders, the values, and the risks explicitly."),
        "consequences": ("Different theories answer concrete dilemmas "
                         "differently only sometimes; in many cases they "
                         "agree."),
    },
    "knowledge": {
        "title": "Knowledge and justification (epistemology)",
        "triggers": ("how do we know", "what is knowledge", "can we know",
                     "is it knowable", "justified", "certainty", "skepticism",
                     "evidence for", "prove that"),
        "sources": ("Stanford Encyclopedia of Philosophy: Epistemology; "
                    "The Analysis of Knowledge; Skepticism"),
        "framer": ("What distinguishes knowledge from mere true belief?"),
        "positions": [
            {
                "name": "Foundationalism",
                "tradition": "Classical foundationalist line (Descartes; "
                             "logical positivists)",
                "definitions": "Knowledge rests on basic beliefs that need no "
                               "further support.",
                "premises": ("An infinite regress of justification is not "
                             "possible.", "Some beliefs are self-evident or "
                             "incorrigible."),
                "argument": ("Support chains must bottom out in foundations."),
                "objections": ("Very few beliefs are truly incorrigible.",
                               "Foundations are too thin for rich knowledge."),
                "counterarguments": ("Modest foundationalism weakens the "
                                     "foundations requirement."),
                "status": "DISPUTED",
            },
            {
                "name": "Coherentism",
                "tradition": "Coherentist line",
                "definitions": "Justification comes from how well beliefs "
                               "hang together, not from foundations.",
                "premises": ("Beliefs are justified by mutual support.",
                             "Isolated beliefs have no epistemic weight."),
                "argument": ("A belief is justified iff it belongs to an "
                             "explanatorily coherent web."),
                "objections": ("A coherent fantasy could be epistemically "
                               "fine by its own lights.",
                               "Needs input from the world at some point."),
                "counterarguments": ("Experiential inputs are admitted as a "
                                     "non-inferential constraint in "
                                     "sophisticated coherentism."),
                "status": "DISPUTED",
            },
            {
                "name": "Skepticism proper",
                "tradition": "Academic / Cartesian skeptical line",
                "definitions": "We cannot rule out systematically deceptive "
                               "scenarios, so large bodies of ordinary "
                               "knowledge claims fail.",
                "premises": ("If you cannot rule out the evil demon (or the "
                             "brain-in-a-vat), most ordinary claims are not "
                             "knowledge.", "Knowledge requires ruling out "
                             "relevant alternatives."),
                "argument": ("You cannot, therefore knowledge (in the "
                             "requiring sense) is unattainable."),
                "objections": ("Closure of knowledge licenses the jump from "
                             "'I know I have hands' to 'I know I am not "
                             "handless-in-a-vat'.", "Sceptical scenarios are "
                             "irrelevant in practical contexts (relevant-"
                             "alternatives theory)."),
                "counterarguments": ("Skepticism is mostly a dialectical tool "
                                     "that forces better theories of "
                                     "knowledge."),
                "status": "DISPUTED",
            },
        ],
        "alternatives": ("Distinguish knowledge (JTB + anti-luck condition) "
                         "from justified belief and from certainty.", "Ask "
                         "whether the operative standard is everyday or "
                         "philosophical."),
        "consequences": ("Commonsense and scientific knowledge usually "
                         "survive philosophical scrutiny under modest "
                         "standards, while extraordinary claims face steeper "
                         "burdens."),
    },
    "reality": {
        "title": "Reality and time (metaphysics)",
        "triggers": ("what is real", "is reality", "is the world real",
                     "does reality exist", "materialism", "realism", "time "
                     "real", "is time", "the past", "present", "eternalism",
                     "simulation"),
        "sources": ("Stanford Encyclopedia of Philosophy: Metaphysics; "
                    "Idealism"),
        "framer": ("What exists fundamentally, and is time more like a "
                   "container or an event-sequence?"),
        "positions": [
            {
                "name": "Scientific realism",
                "tradition": "Realist line",
                "definitions": "The world exists largely as described by the "
                               "best-confirmed science, independent of "
                               "observation.",
                "premises": ("Theories that predict successfully are "
                             "(approximately) true.", "Entities posited by "
                             "successful theories exist."),
                "argument": ("No-miracles argument: predictive success would "
                             "be miraculous if the world were not that way."),
                "objections": ("Pessimistic meta-induction: past successful "
                               "theories were wrong about their entities.",
                               "Underdetermination by data."),
                "counterarguments": ("Selective realism restricts the claim "
                                     "to mature, non-falsified structure."),
                "status": "DISPUTED",
            },
            {
                "name": "Phenomenalism / idealism",
                "tradition": "Idealist / phenomenalist line",
                "definitions": "What we can coherently assert is about "
                               "experience; 'matter in itself' is a "
                               "projection.",
                "premises": ("Evidence never outruns experience.",
                             "Meaning is tied to verifiability for some "
                             "voices."),
                "argument": ("Statements about the world are analyzable into "
                             "statements about actual and possible "
                             "experience."),
                "objections": ("The reduction to endless conditionals is "
                               "unfinished.", "Experience itself is of a "
                               "world that resists us."),
                "counterarguments": ("Quasi-spatial and structural readings "
                                     "lower the reduction burden."),
                "status": "DISPUTED",
            },
            {
                "name": "Presentism vs eternalism",
                "tradition": "Analytic metaphysics of time",
                "definitions": "Presentism: only the present exists. "
                               "Eternalism: past, present, future equally "
                               "exist; time is like a block.",
                "premises": ("Relativity complicates any observer-"
                             "independent 'now'.", "Change requires "
                             "temporal differences."),
                "argument": ("Eternalism is the natural fit for the block "
                             "universe of relativity; presentism preserves "
                             "the intuition that only now flows."),
                "objections": ("Presentism finds no privileged 'now' in the "
                               "physics.", "Eternalism wipes out genuine "
                               "becoming for many."),
                "counterarguments": ("Moving-spotlight and growing-block "
                                     "hybrids try to keep becoming alive."),
                "status": "DISPUTED",
            },
        ],
        "alternatives": ("Ask what kind of 'real' is at stake: observer-"
                         "independent, theoretical-construct, or "
                         "practically-indexed.", "For 'simulation' claims: "
                         "model them as an epistemic question about evidence, "
                         "not a settled fact."),
        "consequences": ("Whether time is a block or a flow changes how we "
                         "talk about change, regret, and death."),
    },
}

_FALLBACK_SCAFFOLD = {
    "title": None,
    "framer": ("No curated entry matched this exact framing; returning an "
               "honest scaffold instead of invented scholarship."),
    "positions": [],
    "alternatives": ("Restate the question with terms defined.",
                     "Identify the empirical part (open to evidence) vs the "
                     "conceptual part (open to argument)."),
    "consequences": ("Because no entry is authoritative and none was "
                     "matched, consequences are deliberately not asserted."),
}


def _detect_topic(question):
    low = (question or "").lower()
    matches = []
    for topic, entry in _CATALOG.items():
        triggers = entry["triggers"]
        hit = [trigger for trigger in triggers if trigger in low]
        if hit:
            matches.append((topic, hit))
    if not matches:
        return None, None
    # prefer inclusivity: topic with most matched triggers wins (ties -> first)
    matches.sort(key=lambda item: len(item[1]), reverse=True)
    return matches[0][0], matches[0][1]


def philosophy_pathway(question, *, state=None, route=None):
    """Deterministic argument representation for one philosophical question."""
    question = str(question or "").strip()
    if not question:
        return {"engaged": False}

    topic, matched = _detect_topic(question)
    if topic is None:
        # still represent honestly: scaffold, not silence and not fabrication
        return {
            "engaged": True,
            "topic": None,
            "matched_triggers": [],
            "representation_kind": "scaffold_fallback",
            "question": question,
            "framer": _FALLBACK_SCAFFOLD["framer"],
            "positions": [],
            "alternatives": _FALLBACK_SCAFFOLD["alternatives"],
            "consequences": _FALLBACK_SCAFFOLD["consequences"],
            "disagreement": {"note": "unknown-entry guard: content omitted "
                                     "rather than invented.",
                             "status": "UNKNOWN"},
            "not_fact": True,
            "overall_status": "UNKNOWN",
            "sources": [],
        }

    entry = _CATALOG[topic]
    positions = []
    for position in entry["positions"]:
        positions.append({
            "name": position["name"],
            "tradition": position["tradition"],
            "definitions": position["definitions"],
            "premises": [p for p in (position.get("premises") or ()) if p],
            "argument": position["argument"],
            "objections": [o for o in (position.get("objections") or ()) if o],
            "counterarguments": [c for c in (position.get("counterarguments") or ()) if c],
            "epistemic_status": position["status"],
        })

    return {
        "engaged": True,
        "topic": topic,
        "matched_triggers": sorted(set(matched or [])),
        "representation_kind": "scholarly_catalog",
        "question": question,
        "title": entry["title"],
        "framer": entry["framer"],
        "positions": positions,
        "alternatives": list(entry["alternatives"]),
        "consequences": list(entry["consequences"]),
        "disagreement": {
            "note": ("The positions above are presented at full strength "
                     "because each tradition defends them; the question "
                     "remains contested."),
            "status": "DISPUTED",
        },
        "not_fact": True,
        "overall_status": "DISPUTED",
        "sources": list(entry["sources"]),
    }


def is_philosophical(question, route=None):
    """Boolean helper for the orchestrator / planner (no NLU claims)."""
    topic, _matched = _detect_topic(question or "")
    return topic is not None or bool(
        route and route.get("domains") and "philosophy" in route["domains"])


def catalog_topics():
    return sorted(_CATALOG.keys())
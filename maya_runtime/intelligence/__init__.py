"""Maya Runtime intelligence subsystem.

Deterministic, architect-ruled layer on top of the verified math surface:
feature encoding, state engine, persona fusion, world confidence,
relevance validation, safety enforcement, meaning, language, reports,
identity anchors, architect-gated evolution, and versioned deployment
profiles — orchestrated by the strict 7-stage loop.
"""
from __future__ import annotations

from .encoder import FeatureEncoder, ENCODER, encode
from .state import StateEngine, STATE_ENGINE, compute
from .anchors import IdentityAnchors, IDENTITY_ANCHORS, ANCHOR_VECTORS
from .fusion import PersonaFusion, PERSONA_FUSION
from .confidence import ConfidenceScorer, CONFIDENCE
from .relevance import Relevance, RELEVANCE
from .safety import SafetyEnforcer, SAFETY, MAX_PERSONA_WEIGHT
from .meaning import MeaningComputer, MEANING
from .language import LanguageEngine, LANGUAGE
from .reports import (
    build_decision_report,
    build_evidence_report,
    build_stability_report,
)
from .locks import SafetyLocks, SAFETY_LOCKS, LOCKED_SURFACES
from .evolution import EvolutionLog, EVOLUTION
from .profiles import (
    DeploymentProfiles,
    DEPLOYMENT,
    DEPLOYMENT_PROFILES,
)
from .loop import (
    IntelligenceLoop,
    INTELLIGENCE,
    STAGES,
    run,
    step,
)

VERSION = "1.0.0"

__all__ = (
    "FeatureEncoder", "ENCODER", "encode",
    "StateEngine", "STATE_ENGINE", "compute",
    "IdentityAnchors", "IDENTITY_ANCHORS", "ANCHOR_VECTORS",
    "PersonaFusion", "PERSONA_FUSION",
    "ConfidenceScorer", "CONFIDENCE",
    "Relevance", "RELEVANCE",
    "SafetyEnforcer", "SAFETY", "MAX_PERSONA_WEIGHT",
    "MeaningComputer", "MEANING",
    "LanguageEngine", "LANGUAGE",
    "build_decision_report", "build_evidence_report",
    "build_stability_report",
    "SafetyLocks", "SAFETY_LOCKS", "LOCKED_SURFACES",
    "EvolutionLog", "EVOLUTION",
    "DeploymentProfiles", "DEPLOYMENT", "DEPLOYMENT_PROFILES",
    "IntelligenceLoop", "INTELLIGENCE", "STAGES", "run", "step",
    "VERSION",
)
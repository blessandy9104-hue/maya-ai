"""Maya mathematical substrate (Batch 8F).

A coherent, cross-cutting mathematical layer available to every Maya subsystem
(interpretation, evidence, world model, learning, planning, behaviour,
verification, visual projection) so that each problem can use the mathematical
representation — or combination of representations — that fits its structure.

Design principles (implemented below):

- **Pure and deterministic**: standard library only; no Qt, no tkinter, no
  wall clock, no randomness. Identical inputs produce identical outputs, and
  discrete structure (graph shape, indices, components) is compared by exact
  equality on every interpreter. Numeric results are compared with tolerance
  across interpreters.
- **Domain separation**: one module per mathematical domain — primitives
  (analytic), probability, statistics, information theory, graph theory,
  formal logic / set theory. ``evidence.py`` composes domains over real
  evidence rows (the demonstrated, audit-justified consumer).
- **Conservative**: nothing here rewrites existing authoritative primitives
  (``rig_math``, ``math_coordinator``, ``visual_state``, ``shape_math``).
  Mirrored semantics are documented where a shared convention already exists
  (e.g. confidence composition matches the bus ``min-if-conflict / max-if-
  agree`` rule).
- **Belief is not truth**: numeric scores and distributions represent
  uncertainty; they never fabricate facts or convert confidence into truth.
- **No IO**: every function is import- and compute-only. Callers pass rows in;
  nothing reads files or clocks inside the package.

The package is validated by ``test_math_substrate.py`` against an independent
clean-room oracle (``verification/oracle_math_substrate.py``) and by
cross-interpreter and sabotage runs described in
``MAYA_BATCH_8F_MATHEMATICAL_SUBSTRATE_REPORT.md``.
"""
from __future__ import annotations

from .core import (  # noqa: F401
    DEG2RAD,
    RAD2DEG,
    clamp,
    clamp01,
    cosine_similarity,
    exp_smooth,
    finite_ok,
    lerp,
    magnitude,
    normalize_weights,
    population_std,
    population_variance,
    quantize,
    smoothstep,
    stable_lerp,
    weighted_mean,
)
from .probability import (  # noqa: F401
    TIER_BELIEF,
    belief_distribution,
    combine_confidences,
    tier_belief,
)
from .statistics import (  # noqa: F401
    OnlineStats,
    coeff_variation,
    data_range,
    mean,
    median,
    population_variance as stats_population_variance,  # noqa: F401
    quantile_nearest_rank,
    sample_variance,
    std_deviation,
    turn_points,
)
from .information import (  # noqa: F401
    entropy,
    entropy_bits,
    information_gain,
    kl_divergence,
    normalized_entropy,
    outcome_information,
    validate_pmf,
)
from .graph import Graph, ClaimGraph  # noqa: F401
from .logic import (  # noqa: F401
    NEGATION_MARKERS,
    STOPWORDS,
    consistent_set,
    contradictory_claims,
    intersect,
    is_disjoint,
    is_subset,
    negation_marked,
    set_union,
    set_exclude,
    tokens,
)
from .checks import substrate_invariants  # noqa: F401
from . import spectral as spectral  # noqa: F401
from .spectral import (  # noqa: F401
    classify_spectrum,
    dominant_frequency,
    fft_magnitudes,
    haar_energy,
    noise_ratio,
    periodicity_score,
    spectral_alignment,
    spectral_centroid,
    spectral_invariants,
    snr_db,
)
from . import evidence as evidence  # noqa: F401
from . import cooperation as cooperation  # noqa: F401
from .cooperation import (  # noqa: F401
    agreement_weighted_combine,
    concordance,
    label_similarity,
    pooled_agreement,
)

__all__ = (
    "DEG2RAD",
    "RAD2DEG",
    "clamp",
    "clamp01",
    "cosine_similarity",
    "exp_smooth",
    "finite_ok",
    "lerp",
    "magnitude",
    "normalize_weights",
    "population_std",
    "population_variance",
    "quantize",
    "smoothstep",
    "stable_lerp",
    "weighted_mean",
    "TIER_BELIEF",
    "belief_distribution",
    "combine_confidences",
    "tier_belief",
    "OnlineStats",
    "coeff_variation",
    "data_range",
    "mean",
    "median",
    "quantile_nearest_rank",
    "sample_variance",
    "std_deviation",
    "turn_points",
    "entropy",
    "entropy_bits",
    "information_gain",
    "kl_divergence",
    "normalized_entropy",
    "outcome_information",
    "validate_pmf",
    "Graph",
    "ClaimGraph",
    "NEGATION_MARKERS",
    "STOPWORDS",
    "consistent_set",
    "contradictory_claims",
    "intersect",
    "is_disjoint",
    "is_subset",
    "negation_marked",
    "set_union",
    "set_exclude",
    "tokens",
    "substrate_invariants",
    "spectral",
    "classify_spectrum",
    "dominant_frequency",
    "fft_magnitudes",
    "haar_energy",
    "noise_ratio",
    "periodicity_score",
    "spectral_alignment",
    "spectral_centroid",
    "spectral_invariants",
    "snr_db",
    "evidence",
    "cooperation",
    "agreement_weighted_combine",
    "concordance",
    "label_similarity",
    "pooled_agreement",
)
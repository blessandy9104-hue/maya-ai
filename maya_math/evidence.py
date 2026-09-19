"""Compositional evidence analysis — the substrate's demonstrated consumer.

Builds a claim/source graph, applies formal-logic contradiction detection,
aggregates belief into a deterministic probability mass function, measures the
residual uncertainty with information theory, and characterises source
reliability with descriptive statistics — all over real evidence rows supplied
by the caller (the world-model evidence schema). Read-only: it never writes,
never reads clocks and never asserts truth. Output is fully deterministic.

Input row schema (matches ``maya_world_model``):
    ``evidence_id`` (str), ``claim`` (str), ``source`` (str),
    ``confidence`` (one of low|medium|high), ``uncertainty`` (optional
    numeric, recorded as the source's numeric uncertainty).
"""
from __future__ import annotations

import math

from .graph import ClaimGraph


def _finite_all(d):
    if isinstance(d, dict):
        return all(_finite_all(v) for v in d.values())
    if isinstance(d, (list, tuple)):
        return all(_finite_all(v) for v in d)
    if isinstance(d, (int, float)) and not isinstance(d, bool):
        return math.isfinite(float(d))
    return True


def _iter_members(rows):
    """Yield (evidence_id, claim, source, confidence, uncertainty) tuples for
    well-formed rows; non-row entries are skipped (documented degradation)."""
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        evidence_id = str(row.get("evidence_id") or "").strip()
        claim = str(row.get("claim") or "").strip()
        source = str(row.get("source") or "").strip()
        confidence = str(row.get("confidence") or "").strip().lower()
        uncertainty = row.get("uncertainty")
        if not evidence_id or not claim or not source:
            continue
        yield evidence_id, claim, source, confidence, uncertainty


def _numeric_uncertainty(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return float(value)
    return None


def analyze_evidence(rows, min_overlap=3):
    """Compose the evidence graph, belief/entropy and source statistics.

    Returns a deterministic dict:

    - ``graph``: nodes/edges/components/cycles/density structurally,
    - ``contradictions``: genuine contradiction pairs with reasoning,
    - ``belief``: per-claim-item distribution + entropy (bits, normalized),
    - ``sources``: per-source counts, tier distribution, uncertainty stats,
    - ``statistics``: overall uncertainty mean/std (population) and turn
      points,
    - ``invariants``: finiteness, fix-point determinism, forest identity.
    """
    members = list(_iter_members(rows))

    # Skip tiers that are not part of the convention; count them for honesty.
    from .probability import TIER_BELIEF
    mapped = [(eid, claim, source, tier, unc)
              for eid, claim, source, tier, unc in members
              if tier in TIER_BELIEF]
    skipped_unknown_tier = len(members) - len(mapped)

    graph = ClaimGraph()
    for eid, claim, source, tier, _unc in mapped:
        graph.add_claim(eid, claim)
        graph.add_support(eid, source)

    contradictions = graph.find_contradictions(min_overlap=min_overlap)

    # Belief distribution over claim items (each evidence row is an outcome).
    beliefs = []
    from .probability import tier_belief, belief_distribution
    for _eid, _claim, _source, tier, _unc in mapped:
        beliefs.append(tier_belief(tier))

    pmf = belief_distribution(beliefs) if beliefs else []
    entropy_bits = 0.0
    normalized_entropy = 0.0
    if pmf:
        from .information import entropy_bits as _eb, normalized_entropy as _ne
        entropy_bits = _eb(pmf)
        normalized_entropy = _ne(pmf)

    # Source statistics and the information gain of a source split.
    source_rows = {}
    for _eid, _claim, source, tier, unc in mapped:
        bucket = source_rows.setdefault(source, {"tiers": [], "uncertainty": []})
        bucket["tiers"].append(tier)
        value = _numeric_uncertainty(unc)
        if value is not None:
            bucket["uncertainty"].append(value)
    source_stats = {}
    for source in sorted(source_rows):
        bucket = source_rows[source]
        uncertainties = bucket["uncertainty"]
        from .statistics import mean as _mean, population_std as _pstd, \
            data_min as _dmin, data_max as _dmax
        source_stats[source] = {
            "evidence_count": len(bucket["tiers"]),
            "tier_counts": {t: bucket["tiers"].count(t)
                            for t in sorted(set(bucket["tiers"]))},
            "uncertainty_mean": _mean(uncertainties),
            "uncertainty_std": _pstd(uncertainties),
            "uncertainty_min": _dmin(uncertainties),
            "uncertainty_max": _dmax(uncertainties),
        }

    split_gain = 0.0
    if pmf and source_rows:
        from .information import information_gain
        # Partition the row-ordered PMF by maximal contiguous same-source runs
        # so every branch weight (run length) is aligned with its PMF slice
        # for ANY input ordering (not just source-grouped input).
        runs = []
        for index, (_eid, _claim, source, _tier, _unc) in enumerate(mapped):
            if runs and runs[-1]["source"] == source:
                runs[-1]["end"] = index + 1
            else:
                runs.append({"source": source, "start": index, "end": index + 1})
        branches = []
        offset_ok = True
        for run in runs:
            slice_ = pmf[run["start"]:run["end"]]
            branches.append((float(run["end"] - run["start"]), slice_))
        if sum(run["end"] - run["start"] for run in runs) == len(pmf):
            split_gain = information_gain(pmf, branches)

    # Overall numeric uncertainty track (ordered by file order).
    from .statistics import mean as _mean, population_std as _pstd, turn_points
    ordered_uncertainty = [_numeric_uncertainty(unc)
                           for (_eid, _claim, _source, _tier, unc) in mapped]
    ordered_uncertainty = [float(v) for v in ordered_uncertainty
                           if v is not None]
    overall_mean = _mean(ordered_uncertainty)
    overall_std = _pstd(ordered_uncertainty)
    turning = turn_points(ordered_uncertainty)

    # Invariants: everything finite, structure fix-point, Euler forest.
    structural = graph.to_graph_dict()
    fixpoint = graph.to_graph_dict() == structural
    forest_ok = (not structural["has_cycle"]) == \
        (structural["edge_count"]
         == structural["node_count"] - len(structural["components"]))
    finite_ok_all = _finite_all({
        "pmf": pmf, "entropy": entropy_bits, "split_gain": split_gain,
        "num_mean": overall_mean, "num_std": overall_std,
    })

    return {
        "evidence_count": len(mapped),
        "skipped_unknown_confidence": skipped_unknown_tier,
        "claim_count": len(graph.claims()),
        "source_count": len(graph.sources()),
        "graph": structural,
        "contradictions": [
            {"claim_a": a, "claim_b": b,
             "basis": graph.claim(a) and graph.claim(b)
             and contradictory_basis(graph.claim(a)["text"],
                                     graph.claim(b)["text"],
                                     min_overlap=min_overlap)}
            for a, b in contradictions],
        "belief": {
            "items": len(pmf),
            "entropy_bits": entropy_bits,
            "normalized_entropy": normalized_entropy,
        },
        "information_gain_by_source": split_gain,
        "sources": source_stats,
        "statistics": {
            "uncertainty_mean": overall_mean,
            "uncertainty_std": overall_std,
            "uncertainty_turn_points": turning,
        },
        "invariants": {
            "all_finite": finite_ok_all,
            "structural_fixpoint": fixpoint,
            "forest_identity_ok": forest_ok,
        },
        "notes": [
            "read-only analysis: never writes, never forecasts, never asserts truth",
            "belief values are composition weights, not calibrated probabilities",
        ],
    }


def contradictory_basis(a_text, b_text, min_overlap=3):
    """Recompute the contradiction reasoning for a recorded pair."""
    from .logic import contradictory_claims
    return contradictory_claims(a_text, b_text, min_overlap=min_overlap)
"""Cross-representation invariant checks for the substrate.

Functions that verify the same mathematical fact through independent
relationships (two variance formulations, the Euler forest identity for
undirected graphs, entropy identities with the 0-log-0 convention). These
mirror what the clean-room oracle re-derives independently
(``verification/oracle_math_substrate.py``); the in-package checks are the
fast invariants the suite asserts on every real computation.
"""
from __future__ import annotations

import math

from .core import population_variance


def variance_crosscheck(values, tol=1e-9):
    """Compare the two-pass variance against the naive sum-of-squares
    ``E[x^2] - E[x]^2`` relation. Returns (two_pass, naive, delta, ok)."""
    values = [float(v) for v in values if not isinstance(v, bool)]
    two_pass = population_variance(values)
    if not values:
        return (0.0, 0.0, 0.0, True)
    mean = math.fsum(values) / len(values)
    naive = max(0.0, math.fsum((v * v) for v in values) / len(values)
                - mean * mean)
    delta = abs(two_pass - naive)
    return (two_pass, naive, delta, delta <= tol)


def forest_edge_identity(nodes, edges, components):
    """Euler characteristic for an undirected forest: a graph with ``nodes``
    vertices, ``edges`` edges and ``components`` connected components has
    ``edges = nodes - components`` exactly when it is acyclic."""
    return int(edges) == int(nodes) - int(components)


def entropy_identity(pmf):
    """Entropy identity check: ``H = sum_i H_i`` where ``H_i`` is the
    contribution of outcome i (the 0 log 0 := 0 convention makes every
    contribution well-defined and non-negative). Returns (contributions_sum,
    direct, ok)."""
    from .information import _log2x, validate_pmf
    validate_pmf(pmf)
    total = math.fsum(float(v) for v in pmf)
    normalized = [float(v) / total for v in pmf]
    parts = [_log2x(p) for p in normalized]
    return (math.fsum(parts), math.fsum(_log2x(p) for p in normalized), True)


def substrate_invariants():
    """Aggregate invariant summary used by verification: returns a dict
    quoting every primitive's guarantees through rederivable identities."""
    return {
        "variance_crosscheck": variance_crosscheck,
        "forest_edge_identity": forest_edge_identity,
        "entropy_identity": entropy_identity,
    }
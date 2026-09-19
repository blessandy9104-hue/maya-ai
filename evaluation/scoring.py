"""Shared deterministic scoring for Maya evaluation and benchmark scripts.

Coverage here always means structural pattern coverage on a fixed fixture:
expected names minus found names. It is never a future-prediction accuracy.
"""
from __future__ import annotations

from typing import Iterable, Sequence


def score_patterns(expected: Iterable[str], found: Iterable[str]) -> dict:
    """Hit/miss/coverage triple over pattern-name sets.

    Returns keys in stable order ``hits, misses, coverage`` so callers can
    extend the dict without disturbing JSON field order.
    """
    expected_set = set(expected)
    found_set = set(found)
    hits = sorted(expected_set & found_set)
    misses = sorted(expected_set - found_set)
    coverage = round(len(hits) / len(expected_set), 2) if expected_set else 1.0
    return {"hits": hits, "misses": misses, "coverage": coverage}


def ratio(hits: int, total: int, ndigits: int = 2) -> float:
    return round(hits / total, ndigits) if total else 1.0


def mean_round(values: Sequence[float], ndigits: int = 2) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), ndigits)

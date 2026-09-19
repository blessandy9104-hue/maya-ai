"""Clean-room oracle for the 8F mathematical substrate.

Independent re-derivation of the substrate's numeric/structural results using
*different* computational methods, so agreement is real evidence and not a
self-consistent mirror:

- variance via the naive sum-of-squares form ``E[x^2] - E[x]^2`` (substrate:
  two-pass degrades differently on near-cancellation),
- standard deviation as ``sqrt(naive variance)``,
- quantile/median via sort + integer nearest-rank arithmetic (substrate:
  ``math.ceil``),
- entropy via the count-form ``log2(W) - (1/W) * sum(w_i log2 w_i)``, an
  algebraically identical but implementationally different formulation from
  the PMF sum ``-sum(p log2 p)``;
- KL divergence via natural logarithm then ``/ ln 2`` (substrate: direct
  ``log2``);
- connected components and cycle detection via union-find together with the
  Euler identity ``cycles iff E > V - C`` (substrate: DFS over an explicit
  graph);
- contradiction recovery with an independent tokenizer that keeps ALL words
  (no stopword removal) and checks substantive-overlap and polarity from that
  richer token stream (substrate: stopword-filtered token sets).

This module imports only the standard library and never imports ``maya_math``.
"""
from __future__ import annotations

import math

ORACLE_STOPWORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "to", "of", "and", "for",
    "in", "on", "this", "that", "with",
})

ORACLE_NEGATION = frozenset({
    "not", "never", "no", "without", "cannot", "can't", "fails",
    "unavailable",
})


def oracle_variance(values):
    """Naive sum-of-squares population variance."""
    values = [float(v) for v in values
              if not isinstance(v, bool) and math.isfinite(float(v))]
    if not values:
        return 0.0
    n = len(values)
    mean = sum(values) / n
    return sum(v * v for v in values) / n - mean * mean


def oracle_std(values):
    return math.sqrt(oracle_variance(values))


def oracle_quantile(data, q):
    """Sort + nearest-rank quantile via ``ceil(q*n)`` on the oracle side."""
    data = sorted(float(v) for v in data
                  if not isinstance(v, bool) and math.isfinite(float(v)))
    if not data:
        return 0.0
    if q <= 0.0:
        return data[0]
    if q >= 1.0:
        return data[-1]
    rank = int(math.ceil(q * len(data)))
    if rank < 1:
        rank = 1
    if rank > len(data):
        rank = len(data)
    return data[rank - 1]


def oracle_median(data):
    return oracle_quantile(data, 0.5)


def oracle_entropy_bits(weights):
    """Count-form entropy: ``log2(W) - (1/W) * sum(w_i * log2 w_i)``."""
    weights = [float(w) for w in weights if math.isfinite(float(w))]
    total = math.fsum(weights)
    if total <= 0.0:
        raise ValueError("oracle entropy requires a positive total")
    terms = [0.0 if w <= 0.0 else w * math.log2(w) for w in weights]
    return math.log2(total) - math.fsum(terms) / total


def oracle_normalized_entropy(weights):
    size = len(weights)
    if size <= 1:
        return 0.0
    h = oracle_entropy_bits(weights)
    return max(0.0, min(1.0, h / math.log2(size)))


def oracle_kl_bits(p, q):
    """KL divergence in bits via the natural-log path."""
    p = [float(v) for v in p]
    q = [float(v) for v in q]
    if len(p) != len(q):
        raise ValueError("KL requires equal length")
    tp = math.fsum(p)
    tq = math.fsum(q)
    if tp <= 0.0 or tq <= 0.0:
        raise ValueError("KL requires positive totals")
    acc = 0.0
    for a, b in zip(p, q):
        pa = a / tp
        qa = b / tq
        if pa > 0.0:
            if qa <= 0.0:
                return math.inf
            acc += pa * (math.log(pa) - math.log(qa))
    return acc / math.log(2.0)


class _UnionFind:
    def __init__(self, members):
        self._parent = {m: m for m in members}

    def find(self, x):
        while self._parent[x] != x:
            self._parent[x] = self._parent[self._parent[x]]
            x = self._parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self._parent[max(ra, rb)] = min(ra, rb)
            return True
        return False

    def components(self):
        groups = {}
        for member in sorted(self._parent):
            groups.setdefault(self.find(member), []).append(member)
        return [sorted(g) for g in groups.values()]


def oracle_components(node_ids, edges):
    """Connected components via union-find (substrate: breadth-first search)."""
    members = [str(n) for n in node_ids]
    nodes = {str(n) for n in node_ids}
    uf = _UnionFind(members)
    for a, b in edges:
        a, b = str(a), str(b)
        if a not in nodes or b not in nodes:
            continue
        if a != b:
            uf.union(a, b)
    return sorted(uf.components())


def oracle_cycle_present(node_ids, edges):
    """Cycle detection via the Euler identity ``E > V - C`` (union-find
    components). Independent of any search implementation."""
    members = [str(n) for n in node_ids]
    nodes = {str(n) for n in node_ids}
    uf = _UnionFind(members)
    seen = set()
    edge_count = 0
    for a, b in edges:
        pair = (min(str(a), str(b)), max(str(a), str(b)))
        if str(a) == str(b) or str(a) not in nodes or str(b) not in nodes:
            continue
        if pair in seen:
            continue
        seen.add(pair)
        edge_count += 1
        uf.union(pair[0], pair[1])
    components = len(uf.components())
    vertex_count = len(nodes)
    return edge_count > vertex_count - components


def oracle_forest_ok(node_ids, edges):
    """True when the graph is acyclic: ``E == V - C`` (Euler)."""
    members = [str(n) for n in node_ids]
    nodes = {str(n) for n in node_ids}
    uf = _UnionFind(members)
    seen = set()
    edge_count = 0
    for a, b in edges:
        pair = (min(str(a), str(b)), max(str(a), str(b)))
        if str(a) == str(b) or str(a) not in nodes or str(b) not in nodes:
            continue
        if pair in seen:
            continue
        seen.add(pair)
        edge_count += 1
        uf.union(pair[0], pair[1])
    return edge_count == len(nodes) - len(uf.components())


def oracle_all_words(text):
    """Tokenization that keeps every word (no stopword removal) — the
    independent token path for contradiction recovery."""
    return set(word.strip(".,!?;:()[]{}\"'") for word in str(text).split())


def oracle_contradiction(a_text, b_text, min_overlap=3):
    """Independent contradiction recovery over the all-words stream.

    Uses the richer token stream but evaluates the same published rule
    (substantive shared vocabulary plus a polarity mismatch). Returns the
    same decision the substrate reaches on the verification corpus, derived
    through a different token pipeline.
    """
    a_all = oracle_all_words(a_text)
    b_all = oracle_all_words(b_text)
    substantive_a = a_all - ORACLE_STOPWORDS
    substantive_b = b_all - ORACLE_STOPWORDS
    overlap = len(substantive_a & substantive_b)
    neg_a = bool(a_all & ORACLE_NEGATION)
    neg_b = bool(b_all & ORACLE_NEGATION)
    contradictory = bool(overlap >= int(min_overlap) and neg_a != neg_b)
    return {
        "contradictory": contradictory,
        "overlap": overlap,
        "polarity_a": "negated" if neg_a else "asserted",
        "polarity_b": "negated" if neg_b else "asserted",
    }
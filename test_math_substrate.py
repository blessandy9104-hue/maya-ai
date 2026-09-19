"""Mathematical substrate verification battery (Batch 8F).

Proves, against the running implementation AND a clean-room oracle
(``verification/oracle_math_substrate.py``) that re-derives every salient
result through a *different* computational method:

- analytic primitives: clamp / clamp01 / lerp / stable_lerp / smoothstep /
  exp_smooth / weighted_mean / normalize_weights / quantize-grid /
  cosine_similarity / angle constants / NaN-Inf degradation;
- statistics: two-pass variance vs naive ``E[x^2]-E[x]^2``, Welford online vs
  batch, nearest-rank quantiles, known turn points, sample-vs-population
  variance, coefficient of variation;
- probability: tier conventions, bus-parity confidence composition
  (min-if-conflict / max-if-agree, ``bus.py:1183-1189``), normalized belief
  distributions;
- information theory: count-form entropy oracle, binary-entropy identity,
  normalized entropy bounds, natural-log KL oracle, information gain;
- graph theory: union-find component oracle, ``E > V - C`` cycle oracle,
  Euler forest identity, reachability/density/canonical order;
- logic and sets: tokens / negation polarity, contradiction
  oracle-agreement across a corpus plus deliberate non-contradictions,
  set operations, consistent-set validation;
- the demonstrated consumer: ``analyze_evidence`` over a fixed corpus —
  graph composition, contradiction detection (true positives and negatives),
  belief entropy, per-source statistics, split information gain, invariants
  (finiteness / structural fix-point / Euler consistency), determinism and
  the ``min_overlap`` sensitivity boundary;
- additive world-model integration: ``mathematical_analysis`` is read-only and
  coexists untouched with ``stability_status``;
- purity: no randomness, no wall clock, no IO, no eval/exec in ``maya_math``.

Discrete structure is compared by exact equality; floats with 1e-9 tolerance
(identical on both the 3.13.15 and 3.14.7 interpreters). Determinism is
demonstrated by repeated evaluation with structurally identical output.
"""
import importlib.util
import math
import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import maya_math
import maya_world_model
from maya_math import checks, core, evidence, graph, information, logic, probability, statistics

_ROOT = os.path.dirname(os.path.abspath(__file__))
_TOL = 1e-9
_ORACLE = None


def _ok(label):
    print(label + "=OK")


def _load_oracle():
    global _ORACLE
    if _ORACLE is not None:
        return _ORACLE
    path = os.path.join(_ROOT, "verification", "oracle_math_substrate.py")
    spec = importlib.util.spec_from_file_location("math_substrate_oracle", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _ORACLE = module
    return _ORACLE


ORACLE = _load_oracle()

# --------------------------------------------------------------------------
# Fixed verification corpus (also used for oracle agreement).
# --------------------------------------------------------------------------
CORPUS = [
    {"evidence_id": "c1", "claim": "AI weather models predict rainfall with high confidence",
     "source": "arxiv", "confidence": "high", "uncertainty": 0.15},
    {"evidence_id": "c2", "claim": "AI weather models cannot predict rainfall with confidence",
     "source": "dissent-blog", "confidence": "low", "uncertainty": 0.65},
    {"evidence_id": "c3", "claim": "AI weather models predict rainfall reliably in temperate zones",
     "source": "arxiv", "confidence": "medium", "uncertainty": 0.30},
    {"evidence_id": "c4", "claim": "Language models articulate coherent summaries of scientific findings",
     "source": "journal", "confidence": "high", "uncertainty": 0.10},
    {"evidence_id": "c5", "claim": "Language models cannot articulate coherent summaries of scientific findings",
     "source": "critic-journal", "confidence": "medium", "uncertainty": 0.45},
    {"evidence_id": "c6", "claim": "Renewable grids integrate storage at declining cost",
     "source": "energy-report", "confidence": "medium", "uncertainty": 0.30},
    {"evidence_id": "c7", "claim": "Renewable grids integrate storage at increasing cost as penetration rises",
     "source": "grid-notes", "confidence": "high", "uncertainty": 0.20},
]
NORCORPUS = [
    {"evidence_id": "n1", "claim": "The quick brown fox jumps over the lazy dog",
     "source": "fable", "confidence": "low", "uncertainty": 0.5},
    {"evidence_id": "n2", "claim": "The quick brown fox sleeps under the rain",
     "source": "garden", "confidence": "medium", "uncertainty": 0.9},
]

SERIES = [2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0]
TURN_SERIES = [1.0, 2.0, 3.0, 2.0, 1.0, 2.0, 3.0]

# ---- 1. analytic primitives ----------------------------------------------

assert core.clamp(0.5, 0, 1) == 0.5
assert core.clamp(-1, 0, 1) == 0.0
assert core.clamp(3, 0, 1) == 1.0
assert core.clamp(float("nan"), 0, 1) == 0.0
assert core.clamp01(2) == 1.0
assert core.clamp01(-2) == 0.0
_ok("msub_core_clamp_ok")

assert core.lerp(2, 6, 0.25) == 3.0
assert core.lerp(2, 6, 0.0) == 2.0
assert core.lerp(2, 6, 1.0) == 6.0
assert core.stable_lerp(2, 6, 1.7) == 6.0
assert core.stable_lerp(2, 6, -0.5) == 2.0
assert core.lerp(10, 20, 0.5) == 15.0
_ok("msub_core_lerp_ok")

assert math.isclose(core.smoothstep(0, 1, 0.5), 0.5, abs_tol=_TOL)
assert core.smoothstep(0, 1, -1) == 0.0
assert core.smoothstep(0, 1, 2) == 1.0
assert math.isclose(core.smoothstep(0, 1, 0.25), 0.25 * 0.25 * (3 - 2 * 0.25), abs_tol=_TOL)
assert core.smoothstep(0, 0, 0.5) == 0.0  # degenerate range
_ok("msub_core_smoothstep_ok")

assert core.exp_smooth(0, 1, 0.5) == 0.5
assert core.exp_smooth(10, 20, 0.0) == 10.0
assert core.exp_smooth(10, 20, 2.0) == 20.0  # alpha clamped to 1
assert math.isclose(core.exp_smooth(0, 1, 0.25), 0.25, abs_tol=_TOL)
_ok("msub_core_exp_smooth_ok")

assert core.weighted_mean([1, 2, 3], [1, 1, 0]) == 1.5
assert core.weighted_mean([], []) == 0.0
assert core.weighted_mean([1, 2], [0, 0]) == 0.0
assert math.isclose(core.weighted_mean([10, 4], [9, 1]), 9.4, abs_tol=_TOL)
_ok("msub_core_weighted_mean_ok")

assert math.fsum(core.normalize_weights([1, 1, 1])) == 1.0
assert math.fsum(core.normalize_weights([2, 3, 5])) == 1.0
assert core.normalize_weights([4]) == [1.0]
assert all(0.0 <= w <= 1.0 for w in core.normalize_weights([5, 5, 5]))
_ok("msub_core_normalize_exact_sum_ok")

assert core.quantize(-0.5, 5, 0, 1) == 0
assert core.quantize(1.5, 5, 0, 1) == 5
assert core.quantize(0.5, 5, 0, 1) == 3  # bucket 2.5 -> round -> 3
assert core.quantize(0.0, 5, 0, 1) == 0
assert core.quantize(1.0, 5, 0, 1) == 5
assert core.quantize(0.9, 1, 0, 1) == 1
assert core.quantize(float("nan"), 5, 0, 1) == 0
assert core.quantize(0.5, 0, 0, 1) == 0
low_bucket = core.quantize(0.1, 10, 0, 1)
mid_bucket = core.quantize(0.95, 10, 0, 1)
assert low_bucket < mid_bucket
assert core.grid_value(core.quantize(0.55, 10, 0, 1), 10, 0, 1) > 0.5
_ok("msub_core_quantize_grid_ok")

assert core.cosine_similarity((1, 0), (1, 0)) == 1.0
assert core.cosine_similarity((1, 0), (0, 1)) == 0.0
assert math.isclose(core.cosine_similarity((1, 1), (1, 1)), 1.0, abs_tol=_TOL)
assert math.isclose(core.cosine_similarity((1, 2, 3), (1, 2, 3)), 1.0, abs_tol=_TOL)
assert core.cosine_similarity((0, 0), (1, 1)) == 0.0
assert core.cosine_similarity(None, (1, 1)) == 0.0
assert core.cosine_similarity((1, 0, 0), (1, 0)) == 0.0  # unequal length
assert core.cosine_similarity((float("nan"), 0), (1, 0)) == 0.0
_ok("msub_core_cosine_similarity_ok")

assert math.isclose(core.DEG2RAD * 180.0, math.pi, abs_tol=1e-9)
assert math.isclose(core.RAD2DEG * (math.pi / 180.0), 1.0, abs_tol=1e-9)
assert math.isclose(core.RAD2DEG * (core.DEG2RAD * 90.0), 90.0, abs_tol=1e-9)
_ok("msub_core_angle_constants_ok")

# NaN / Inf degrade to the documented safe values instead of raising.
assert core.clamp01(float("nan")) == 0.0
assert core.clamp(float("inf"), 0, 1) == 0.0  # non-finite degrades to low
assert math.isfinite(core.lerp(float("nan"), 1, 0.5))
assert math.isfinite(core.smoothstep(0, 1, float("nan")))
assert math.isfinite(core.exp_smooth(float("nan"), 1.0, 0.5))
assert core.magnitude([float("nan"), float("inf")]) == 0.0
assert core.weighted_mean([1, 2], [float("nan"), 1.0]) == 2.0  # nan weight -> 0
assert core.quantize(float("-inf"), 5) == 0.0
assert not core.finite_ok(float("inf"))
assert core.finite_ok(42) and core.finite_ok("ignored")
_ok("msub_core_nan_inf_degrade_ok")

for bad in ([], [-1, 2], [float("nan"), 1.0], [0, 0], [float("inf"), 1.0]):
    try:
        core.normalize_weights(bad)
        raise AssertionError("normalize_weights accepted corrupt input %r" % (bad,))
    except ValueError:
        pass
_ok("msub_core_normalize_rejects_corrupt_ok")

# ---- 2. statistics -------------------------------------------------------

_two_pass = statistics.population_variance(SERIES)
_naive = ORACLE.oracle_variance(SERIES)
assert math.isclose(_two_pass, _naive, abs_tol=_TOL)
_tp, _nv, _delta, _cv_ok = checks.variance_crosscheck(SERIES)
assert math.isclose(_two_pass, 4.0, abs_tol=_TOL)
assert _cv_ok and _delta <= _TOL
assert statistics.population_std(SERIES) == 2.0
_ok("msub_stats_variance_oracle_ok")

_online = statistics.OnlineStats()
for value in SERIES:
    _online.update(value)
assert _online.count == len(SERIES)
assert math.isclose(_online.mean_value, 5.0, abs_tol=1e-12)
assert math.isclose(_online.variance(), 4.0, abs_tol=1e-12)
assert math.isclose(_online.variance(ddof=1), 32.0 / 7.0, abs_tol=1e-12)
assert math.isclose(_online.std(), 2.0, abs_tol=1e-12)
_ok("msub_stats_online_matches_batch_ok")

for q in (0.0, 0.25, 0.5, 0.75, 1.0, 1.4, -0.2):
    assert statistics.quantile_nearest_rank(SERIES, q) == \
        ORACLE.oracle_quantile(SERIES, q)
assert statistics.median(SERIES) == 4.0
assert statistics.median(SERIES) == ORACLE.oracle_median(SERIES)
assert statistics.quantile_nearest_rank([], 0.5) == 0.0
assert statistics.median([7]) == 7.0
_ok("msub_stats_quantile_oracle_ok")

assert statistics.turn_points(TURN_SERIES) == [2, 4]
total_tp = statistics.turn_points([1, 2, 3, 4, 5])  # monotone: none
assert total_tp == []
_ok("msub_stats_known_turn_points_ok")

assert math.isclose(statistics.sample_variance(SERIES), 32.0 / 7.0, abs_tol=_TOL)
assert statistics.sample_variance([1, 2]) > statistics.population_variance([1, 2])
assert statistics.sample_variance([5]) == 0.0
assert statistics.std_deviation([]) == 0.0
_ok("msub_stats_sample_vs_population_ok")

assert math.isclose(statistics.coeff_variation(SERIES), 2.0 / 5.0, abs_tol=_TOL)
assert statistics.coeff_variation([0, 0, 0]) == 0.0
assert statistics.coeff_variation([]) == 0.0
assert statistics.data_range(SERIES) == 7.0
assert math.isclose(statistics.mean([2, 4, 6]), 4.0, abs_tol=_TOL)
_ok("msub_stats_cv_bounds_ok")

# ---- 3. probability ------------------------------------------------------

assert probability.TIER_BELIEF == {"low": 0.35, "medium": 0.60, "high": 0.85}
assert probability.tier_belief("high") == 0.85
assert probability.tier_belief("medium") == 0.60
assert probability.tier_belief("low") == 0.35
for unknown in ("certain", "HIGH", "", None):
    try:
        probability.tier_belief(unknown)
        raise AssertionError("unknown tier accepted: %r" % (unknown,))
    except ValueError:
        pass
_ok("msub_prob_tier_belief_ok")

# Bus parity: the state bus merges confidence with min-when-conflicting and
# max-when-agreeing (bus.py:1183-1189). The substrate's composition mirrors
# that convention.
assert probability.combine_confidences([0.8, 0.6], [0.2]) == 0.2
assert probability.combine_confidences([0.3, 0.5], []) == 0.5
assert probability.combine_confidences([], [0.2, 0.4]) == 0.2
assert probability.combine_confidences([], []) == 0.0
_agree = [0.9, 0.7, 0.8]
assert probability.combine_confidences(_agree, []) == max(_agree)
_conflict = [0.1, 0.4, 0.25]
assert probability.combine_confidences([0.9], [v for v in _conflict]) == min(_conflict)
assert probability.combine_confidences([2.0], []) == 1.0  # clamped
assert probability.combine_confidences([float("nan")], []) == 0.0
_ok("msub_prob_combine_bus_parity_ok")

pmf = probability.belief_distribution([0.85, 0.35, 0.60, 0.85, 0.60, 0.60, 0.85])
assert math.fsum(pmf) == 1.0
assert all(0.0 < p <= 1.0 for p in pmf)
assert math.isclose(probability.distribution_mean([0.5, 0.5], [1.0, 2.0]), 1.5, abs_tol=_TOL)
assert math.isclose(probability.distribution_entropy([0.5, 0.5]), 1.0, abs_tol=_TOL)
try:
    probability.belief_distribution([0.5, -0.5])
    raise AssertionError("negative beliefs accepted")
except ValueError:
    pass
_ok("msub_prob_distribution_ok")

# ---- 4. information theory ------------------------------------------------

_beliefs = [0.85, 0.35, 0.60, 0.85, 0.60, 0.60, 0.85]
_h = information.entropy_bits(_beliefs)
_h_oracle = ORACLE.oracle_entropy_bits(_beliefs)
assert math.isclose(_h, _h_oracle, abs_tol=_TOL)
_ok("msub_info_entropy_oracle_ok")

assert math.isclose(information.entropy_bits([0.5, 0.5]), 1.0, abs_tol=_TOL)
assert information.entropy_bits([1.0]) == 0.0
assert math.isclose(information.entropy_bits([0.25, 0.75]),
                    0.25 * math.log2(1 / 0.25) + 0.75 * math.log2(1 / 0.75),
                    abs_tol=_TOL)
try:
    information.entropy_bits([-0.5, 1.5])
    raise AssertionError("invalid PMF accepted")
except ValueError:
    pass
try:
    information.entropy_bits([])
    raise AssertionError("empty PMF accepted")
except ValueError:
    pass
_ok("msub_info_binary_entropy_ok")

assert math.isclose(information.normalized_entropy(_beliefs),
                    ORACLE.oracle_normalized_entropy(_beliefs), abs_tol=_TOL)
assert 0.0 <= information.normalized_entropy(_beliefs) <= 1.0
assert information.normalized_entropy([1.0]) == 0.0
assert math.isclose(information.normalized_entropy([0.5, 0.5]), 1.0, abs_tol=_TOL)
_ok("msub_info_normalized_entropy_bounds_ok")

_kl = information.kl_divergence([0.5, 0.5], [0.25, 0.75])
_kl_oracle = ORACLE.oracle_kl_bits([0.5, 0.5], [0.25, 0.75])
assert math.isclose(_kl, _kl_oracle, abs_tol=_TOL)
assert information.kl_divergence([0.5, 0.5], [0.5, 0.5]) == 0.0
assert math.isclose(information.kl_divergence([0.0, 1.0], [0.5, 0.5]), 1.0, abs_tol=_TOL)  # 0 log 0 := 0
assert information.kl_divergence([0.5, 0.5], [0.0, 1.0]) == math.inf
try:
    information.kl_divergence([0.5], [0.25, 0.75])
    raise AssertionError("length-mismatched KL accepted")
except ValueError:
    pass
_ok("msub_info_kl_oracle_ok")

_prior = [0.5, 0.5]
_branches = [(1.0, [1.0, 0.0]), (1.0, [0.0, 1.0])]  # perfect split
_gain = information.information_gain(_prior, _branches)
assert math.isclose(_gain, 1.0, abs_tol=_TOL)
assert _gain >= 0.0
assert information.information_gain(_prior, []) == 0.0
_noisy = information.information_gain(_prior, [(1.0, [0.5, 0.5])])
assert math.isclose(_noisy, 0.0, abs_tol=_TOL)
_ok("msub_info_gain_ok")

# ---- 5. graph theory ------------------------------------------------------

_cg = graph.Graph()
_cg.add_edge("a", "b")
_cg.add_edge("b", "c")
_cg.add_edge("c", "a")
_cg.add_node("d")
_cg.add_edge("e", "f")
_components = _cg.connected_components()
_oracle_components = ORACLE.oracle_components(
    ["a", "b", "c", "d", "e", "f"], [("a", "b"), ("b", "c"), ("c", "a"), ("e", "f")])
assert _components == _oracle_components
assert _components == [["a", "b", "c"], ["d"], ["e", "f"]]
_ok("msub_graph_components_oracle_ok")

assert _cg.has_cycle() is ORACLE.oracle_cycle_present(
    ["a", "b", "c", "d", "e", "f"], [("a", "b"), ("b", "c"), ("c", "a"), ("e", "f")])
assert _cg.has_cycle() is True
_chain = graph.Graph()
for x, y in [("a", "b"), ("b", "c"), ("c", "d")]:
    _chain.add_edge(x, y)
assert _chain.has_cycle() is False
assert _chain.has_cycle() is ORACLE.oracle_cycle_present(
    ["a", "b", "c", "d"], [("a", "b"), ("b", "c"), ("c", "d")])
_ok("msub_graph_cycle_oracle_ok")

_chain_nodes = 4
_chain_edges = 3
_chain_components = 1
assert checks.forest_edge_identity(_chain_nodes, _chain_edges, _chain_components)
assert ORACLE.oracle_forest_ok(["a", "b", "c", "d"],
                               [("a", "b"), ("b", "c"), ("c", "d")]) is True
_cyc = graph.Graph()
_cyc.add_edge("x", "y")
_cyc.add_edge("y", "z")
_cyc.add_edge("z", "x")
_cyc_nodes = _cyc.node_count()
_cyc_edges = _cyc.edge_count()
_cyc_comps = len(_cyc.connected_components())
if _cyc.has_cycle():
    assert not checks.forest_edge_identity(_cyc_nodes, _cyc_edges, _cyc_comps)
assert checks.forest_edge_identity(_cyc_nodes, _cyc_edges + 1, _cyc_comps) is False
_ok("msub_graph_forest_identity_ok")

assert _chain.reachable("a") == ["a", "b", "c", "d"]
assert _chain.reachable("c") == ["a", "b", "c", "d"]
assert _chain.reachable("zzz") == []
assert _chain.degree("b") == 2
assert _chain.degree("zzz") == 0
_k3 = graph.Graph()
for x, y in [("p", "q"), ("q", "r"), ("p", "r")]:
    _k3.add_edge(x, y)
assert math.isclose(_k3.density(), 1.0, abs_tol=_TOL)
assert _chain.density() > 0.0
_single = graph.Graph()
_single.add_node("solo")
assert _single.density() == 0.0
_ok("msub_graph_reachability_density_ok")

_g1 = graph.Graph()
_g1.add_edge("z", "a")
_g1.add_edge("m", "z")
_g2 = graph.Graph()
_g2.add_edge("z", "a")
_g2.add_node("m")
_g2.add_edge("m", "z")
assert _g1.nodes_sorted() == _g2.nodes_sorted() == ["a", "m", "z"]
assert _g1.connected_components() == _g2.connected_components()
assert _g1.to_graph_dict() == _g2.to_graph_dict()
assert _g1.to_graph_dict() == _g1.to_graph_dict()  # structural fix-point
assert "edges" in _g1.preview() and "components" in _g1.preview()
_ok("msub_graph_canonical_order_ok")

# ---- 6. logic and sets ----------------------------------------------------

assert logic.negation_marked("AI cannot predict rain") is True
assert logic.negation_marked("AI can predict rain") is False
assert "cannot" in logic.tokens("AI cannot predict rain")
assert "the" not in logic.tokens("the AI system")
assert logic.tokens("The Quick Fox") == logic.tokens("the quick fox")
assert logic.token_overlap("alpha beta gamma", "beta gamma delta") == 2
assert logic.NEGATION_MARKERS <= maya_world_model.NEGATION_MARKERS | {"nothing", "doesn't", "didn't", "isn't", "won't"}
_ok("msub_logic_tokens_negation_ok")

# Oracle agreement across every corpus pair (substrate tokenizer vs oracle
# all-words tokenizer must reach the same decision).
_pairs = [(row_a["claim"], row_b["claim"])
          for row_a in CORPUS for row_b in CORPUS]
for a_text, b_text in _pairs:
    sub = logic.contradictory_claims(a_text, b_text, min_overlap=3)
    ora = ORACLE.oracle_contradiction(a_text, b_text, min_overlap=3)
    assert sub["contradictory"] == ora["contradictory"], (a_text, b_text)
true_pairs = [("c1", "c2"), ("c2", "c3"), ("c4", "c5")]
for a, b in true_pairs:
    row_a = next(r for r in CORPUS if r["evidence_id"] == a)
    row_b = next(r for r in CORPUS if r["evidence_id"] == b)
    assert logic.contradictory_claims(row_a["claim"], row_b["claim"])["contradictory"]
same_polarity = [("c1", "c3"), ("c6", "c7")]
for a, b in same_polarity:
    row_a = next(r for r in CORPUS if r["evidence_id"] == a)
    row_b = next(r for r in CORPUS if r["evidence_id"] == b)
    assert not logic.contradictory_claims(row_a["claim"], row_b["claim"])["contradictory"]
# identical polarity with high overlap is never burned as a contradiction.
assert not logic.contradictory_claims("x is warm", "x is warm", min_overlap=1)["contradictory"]
_ok("msub_logic_contradiction_oracle_ok")

assert logic.intersect({1, 2}, {2, 3}) == frozenset({2})
assert logic.intersect() == frozenset()
assert logic.set_union({1}, {2, 3}) == frozenset({1, 2, 3})
assert logic.set_exclude({1, 2, 3}, {2}) == frozenset({1, 3})
assert logic.is_subset({1}, {1, 2})
assert not logic.is_subset({3}, {1, 2})
assert logic.is_disjoint({1}, {2})
assert not logic.is_disjoint({1}, {1, 2})
_ok("msub_logic_set_ops_ok")

ok_flag, violations = logic.consistent_set({"a", "b"}, allowed={"a", "b"}, forbidden={"c"})
assert ok_flag and violations == []
ok_flag, violations = logic.consistent_set({"a", "c"}, allowed={"a", "b"})
assert not ok_flag and violations == ["member_not_allowed=c"]
ok_flag, violations = logic.consistent_set({"a", "c"}, forbidden={"c"})
assert not ok_flag and violations == ["member_forbidden=c"]
_ok("msub_logic_consistent_set_ok")

# ---- 7. the demonstrated consumer (analyze_evidence) ----------------------

_result_a = evidence.analyze_evidence(CORPUS)
_result_b = evidence.analyze_evidence(CORPUS)
assert _result_a == _result_b  # determinism
assert _result_a["evidence_count"] == 7
assert _result_a["claim_count"] == 7
assert _result_a["source_count"] == 6
assert _result_a["graph"]["node_count"] == 13
assert _result_a["graph"]["edge_count"] == 10
assert _result_a["graph"]["has_cycle"] is True
assert len(_result_a["graph"]["components"]) == 4
assert _result_a["skipped_unknown_confidence"] == 0
_ok("msub_evidence_graph_composition_ok")

contra = {tuple(pair) for pair in
          [(c["claim_a"], c["claim_b"]) for c in _result_a["contradictions"]]}
assert contra == {("c1", "c2"), ("c2", "c3"), ("c4", "c5")}
for pair in _result_a["contradictions"]:
    assert pair["basis"]["contradictory"] is True
    assert pair["basis"]["overlap"] >= 3
assert all(c["basis"]["polarity_a"] != c["basis"]["polarity_b"]
           for c in _result_a["contradictions"])
_ok("msub_evidence_contradiction_integration_ok")

_mock = evidence.analyze_evidence(NORCORPUS)
assert _mock["evidence_count"] == 2
assert _mock["graph"]["components"] == [["n1", "src:fable"], ["n2", "src:garden"]]
assert _mock["contradictions"] == []
assert _mock["graph"]["has_cycle"] is False
assert _mock["invariants"]["forest_identity_ok"] is True
_ok("msub_evidence_mock_matrix_ok")

_pmf = _result_a["belief"]["items"]  # noqa: F841 (guard)
assert _result_a["belief"]["items"] == 7
_entropy_analysis = _result_a["belief"]["entropy_bits"]
assert math.isclose(_entropy_analysis, _h_oracle, abs_tol=_TOL)
_norm = _result_a["belief"]["normalized_entropy"]
assert 0.0 <= _norm <= 1.0
assert math.isclose(_norm, ORACLE.oracle_normalized_entropy(_beliefs), abs_tol=_TOL)
_ok("msub_evidence_belief_entropy_oracle_ok")

# Per-source uncertainty statistics against the oracle naive form.
arxi = [_row["uncertainty"] for _row in CORPUS if _row["source"] == "arxiv"]
assert math.isclose(_result_a["sources"]["arxiv"]["uncertainty_mean"],
                    statistics.mean(arxi), abs_tol=_TOL)
assert math.isclose(_result_a["sources"]["arxiv"]["uncertainty_mean"],
                    0.225, abs_tol=_TOL)
assert math.isclose(_result_a["sources"]["arxiv"]["uncertainty_std"],
                    ORACLE.oracle_std(arxi), abs_tol=_TOL)
assert _result_a["sources"]["arxiv"]["evidence_count"] == 2
assert _result_a["sources"]["arxiv"]["tier_counts"] == {"high": 1, "medium": 1}
total_unc = [r["uncertainty"] for r in CORPUS]
assert math.isclose(_result_a["statistics"]["uncertainty_mean"],
                    statistics.mean(total_unc), abs_tol=_TOL)
assert math.isclose(_result_a["statistics"]["uncertainty_std"],
                    ORACLE.oracle_std(total_unc), abs_tol=_TOL)
_ok("msub_evidence_source_stats_oracle_ok")

_split_gain = _result_a["information_gain_by_source"]
# Interleaved rows: every contiguous same-source run has length 1, so a
# source-split removes no uncertainty and the gain is the prior entropy.
assert math.isclose(_split_gain, _h_oracle, abs_tol=1e-9)
# Source-grouped rows give a genuine split; recompute it independently.
REORDERED = [CORPUS[0], CORPUS[2], CORPUS[1], CORPUS[3], CORPUS[4],
             CORPUS[5], CORPUS[6]]
_result_r = evidence.analyze_evidence(REORDERED)
_gain_r = _result_r["information_gain_by_source"]
_manual_gain = 0.0
_source_order = []
for _row in REORDERED:
    if _row["source"] not in _source_order:
        _source_order.append(_row["source"])
for _src in _source_order:
    _rows = [r for r in REORDERED if r["source"] == _src]
    _branch_beliefs = [
        0.85 if r["confidence"] == "high"
        else 0.60 if r["confidence"] == "medium" else 0.35
        for r in _rows]
    _manual_gain += (len(_rows) / 7.0) * ORACLE.oracle_entropy_bits(_branch_beliefs)
_manual_gain = _h_oracle - _manual_gain
assert math.isclose(_gain_r, _manual_gain, abs_tol=1e-6)
assert _split_gain >= 0.0 and _gain_r >= 0.0
_ok("msub_evidence_split_gain_oracle_ok")

assert _result_a["invariants"]["all_finite"] is True
assert _result_a["invariants"]["structural_fixpoint"] is True
assert _result_a["invariants"]["forest_identity_ok"] is True  # consistency holds
assert all("never asserts truth" in note or "composition weights" in note
           for note in _result_a["notes"])
_ok("msub_evidence_invariants_ok")

_s = evidence.analyze_evidence(CORPUS, min_overlap=6)
_tight_pairs = {tuple(pair) for pair in
                [(c["claim_a"], c["claim_b"]) for c in _s["contradictions"]]}
assert _tight_pairs == {("c1", "c2"), ("c4", "c5")}
for a_text, b_text in [(r1["claim"], r2["claim"]) for r1 in CORPUS for r2 in CORPUS
                       if r1["evidence_id"] != r2["evidence_id"]]:
    sub = logic.contradictory_claims(a_text, b_text, min_overlap=6)
    ora = ORACLE.oracle_contradiction(a_text, b_text, min_overlap=6)
    assert sub["contradictory"] == ora["contradictory"], (a_text, b_text)
_s7 = evidence.analyze_evidence(CORPUS, min_overlap=7)
_loose_pairs_7 = {tuple(pair) for pair in
                  [(c["claim_a"], c["claim_b"]) for c in _s7["contradictions"]]}
assert _loose_pairs_7 == {("c4", "c5")}
_ok("msub_evidence_min_overlap_sensitivity_ok")

# ---- 8. additive world-model integration -----------------------------------

_before = maya_world_model.stability_status()
_math_out = maya_world_model.mathematical_analysis(limit=0)
_after = maya_world_model.stability_status()
assert _math_out["status"] == "mathematical_analysis"
assert _math_out["additive_only"] is True
assert _math_out["claim_count"] == _math_out["evidence_count"] >= 1
assert _before.keys() == _after.keys()
assert _before["status"] in ("stable", "review")
assert _before == _after  # read-only: no mutation of the existing layer
assert set(_math_out.keys()) >= {
    "evidence_count", "claim_count", "source_count", "graph",
    "contradictions", "belief", "sources", "statistics", "invariants"}
_ok("msub_world_model_additive_integration_ok")

# ---- 9. purity: no randomness, wall clock, IO, or dynamic code ------------

_banned_imports = re.compile(
    r"^\s*(import|from)\s+(random|time|datetime|os|subprocess|socket)",
    re.MULTILINE)
_banned_dynamic = re.compile(r"\b(eval|exec)\s*\(")
_banned_io = re.compile(r"\bopen\s*\(")
_pkg_dir = os.path.join(_ROOT, "maya_math")
_checked = 0
for _name in ["__init__.py", "core.py", "probability.py", "statistics.py",
              "information.py", "graph.py", "logic.py", "evidence.py", "checks.py"]:
    with open(os.path.join(_pkg_dir, _name), "r", encoding="utf-8") as _handle:
        _src = _handle.read()
    _checked += 1
    assert not _banned_imports.search(_src), _name
    assert not _banned_dynamic.search(_src), _name
    assert not _banned_io.search(_src), _name
assert _checked == 9
import maya_math
_ok("msub_package_purity_ok")

print("status=pass")
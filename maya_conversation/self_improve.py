"""Batch 8I phase 12: controlled self-improvement.

A new method may be promoted ONLY when:
  (a) it demonstrates ≥1 successful transfer,
  (b) its most similar old hypothesis has already failed or been rejected,
      AND
  (c) the old hypothesis would NOT have covered the new task's conditions
      (transfer-boundary mismatch).

No old rule is mutated. No learning rules are replaced in-flight. No 8H/8F/8G
core is touched: this entire subsystem runs outside the production pipeline.

Purity:
- No clock, no randomness, no file writes, no network.
- Rank ordering is deterministic; winner selection is deterministic.
Fail-open:
- Missing hypotheses / bad inputs degrade safely to None / empty lists.
"""
from __future__ import annotations

from .generalize import transfer_boundary_check, _set
from .hypothesis import hypothesis_from_experience


def _finite(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if number != number or number in (float("inf"), float("-inf")):
        return 0.0
    return number


class ControlledImprovement:
    """Candidate proposals ranked by old-hypothesis similarity + evidence."""

    def __init__(self, similarity_threshold=0.5):
        self.similarity_threshold = _finite(similarity_threshold)
        self._candidates = []
        self._old_map = {}    # candidate_index -> old hypothesis

    def propose(self, old_hypothesis, new_method,
                source_experience, conditions=None,
                exclusions=None):
        """Create one candidate hypothesis explicitly tied to its predecessor."""
        hp = hypothesis_from_experience(
            new_method, source_experience,
            conditions=conditions, exclusions=exclusions)
        index = len(self._candidates)
        self._candidates.append({
            "hypothesis": hp,
            "old": old_hypothesis,
            "ok_transfers": 0,
            "attempts": 0,
        })
        self._old_map[index] = old_hypothesis
        return hp

    def evidence(self, index, fingerprint, outcome):
        """Record one real outcome for a specific candidate index."""
        if not (0 <= index < len(self._candidates)):
            return None
        c = self._candidates[index]
        ok = bool(outcome)
        c["hypothesis"].record_case(
            case_key="improve_%d" % c["attempts"],
            outcome="controlled improvement",
            ok=ok)
        c["hypothesis"].update_uncertainty()
        c["attempts"] += 1
        if ok:
            c["ok_transfers"] += 1
        return dict(ok=ok, attempts=c["attempts"],
                    ok_transfers=c["ok_transfers"])

    def _similarity(self, a, b):
        """Simple feature-overlap similarity for dicts / hypotheses."""
        a_conds = getattr(a, "conditions", None)
        if a_conds is None and isinstance(a, dict):
            a_conds = a.get("conditions", {})
        b_conds = getattr(b, "conditions", None)
        if b_conds is None and isinstance(b, dict):
            b_conds = b.get("conditions", {})
        if not isinstance(a_conds, dict):
            a_conds = {}
        if not isinstance(b_conds, dict):
            b_conds = {}
        all_keys = set(a_conds) | set(b_conds)
        if not all_keys:
            return 0.0
        matches = sum(
            1 for k in all_keys
            if a_conds.get(k) == b_conds.get(k))
        return matches / len(all_keys)

    def rank(self):
        """Deterministic ordering of candidates by similarity+evidence."""
        ranked = []
        for i, c in enumerate(self._candidates):
            old = c["old"]
            sim = self._similarity(c["hypothesis"], old) if old else 0.0
            success_ratio = (c["ok_transfers"] / c["attempts"]
                             if c["attempts"] else 0.0)
            ranked.append({
                "index": i,
                "method": c["hypothesis"].method,
                "similarity_to_old": sim,
                "success_ratio": success_ratio,
                "attempts": c["attempts"],
                "old_status": getattr(old, "status", None) if old else None,
            })
        ranked.sort(key=lambda item: (
            -item["similarity_to_old"],
            -item["success_ratio"],
            -item["attempts"],
            item["method"]))
        return ranked

    def winner(self):
        """Select the best controlled-improvement candidate, if any.

        A candidate wins when:
          (a) ok_transfers >= 1
          (b) similarity to the old hypothesis >= threshold
          (c) old hypothesis status is NOT promoted / tested (it failed)
          (d) old hypothesis would have failed under the new conditions
              (boundary check says new fp is outside old scope)
        """
        ranked = self.rank()
        for entry in ranked:
            i = entry["index"]
            c = self._candidates[i]
            old = c["old"]
            if old is None:
                continue
            if c["ok_transfers"] < 1:
                continue
            if entry["similarity_to_old"] < self.similarity_threshold:
                continue
            old_status = getattr(old, "status", None)
            if old_status in ("promoted", "tested", None):
                continue
            new_hp = c["hypothesis"]
            new_conds = getattr(new_hp, "conditions", None)
            if new_conds is None and isinstance(new_hp, dict):
                new_conds = new_hp.get("conditions", {})
            mock_new_fp = {}
            if isinstance(new_conds, dict):
                mock_new_fp.update(new_conds)
            check = transfer_boundary_check(old, mock_new_fp)
            if check["within_scope"]:
                continue
            return {"method": c["hypothesis"].method,
                    "index": i,
                    "old_method": getattr(old, "method", str(old)),
                    "similarity": entry["similarity_to_old"],
                    "ok_transfers": c["ok_transfers"]}
        return None

    def count(self):
        return len(self._candidates)

    def snapshot(self):
        return {
            "candidates": [
                {"index": i, "method": c["hypothesis"].method,
                 "status": c["hypothesis"].status,
                 "ok_transfers": c["ok_transfers"],
                 "attempts": c["attempts"]}
                for i, c in enumerate(self._candidates)
            ],
            "threshold": self.similarity_threshold,
        }
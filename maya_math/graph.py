"""Graph-theory domain of the substrate.

A deterministic undirected graph with canonical iteration order (sorted node
ids), exact-equality structure (components, cycles, degrees, reachability)
and invariants usable by verification (``forest_edge_identity``).
``ClaimGraph`` specialises the representation for evidence: claim nodes,
``src:<source>`` support nodes, and claim–claim contradiction edges produced
by the logic domain.

Everything here is import/compute-only; iteration order never depends on hash
randomization (sorted keys everywhere).
"""
from __future__ import annotations

from .logic import contradictory_claims, negation_marked


class Graph:
    """Simple undirected graph keyed by string node ids."""

    def __init__(self):
        self._nodes = {}

    # -- structure ---------------------------------------------------------
    def add_node(self, node_id):
        """Add a node id; returns True when newly created."""
        node_id = str(node_id)
        if node_id in self._nodes:
            return False
        self._nodes[node_id] = set()
        return True

    def node_count(self):
        return len(self._nodes)

    def edge_count(self):
        return sum(len(adj) for adj in self._nodes.values()) // 2

    def has_node(self, node_id):
        return str(node_id) in self._nodes

    def degree(self, node_id):
        return len(self._nodes.get(str(node_id), set()))

    def nodes_sorted(self):
        """Canonical (sorted) node id list."""
        return sorted(self._nodes)

    def adjacents(self, node_id):
        """Sorted neighbours of a node (empty list for unknown nodes)."""
        return sorted(self._nodes.get(str(node_id), set()))

    def add_edge(self, a, b):
        """Add an undirected edge. Self-loops are ignored (a claim is never
        its own contradiction). Ids without nodes are created implicitly."""
        a, b = str(a), str(b)
        if a == b:
            return False
        self.add_node(a)
        self.add_node(b)
        if b in self._nodes[a]:
            return False
        self._nodes[a].add(b)
        self._nodes[b].add(a)
        return True

    # -- queries -----------------------------------------------------------
    def connected_components(self):
        """Connected components as sorted lists, discovered in canonical
        (sorted-start) order via breadth-first search."""
        seen = set()
        components = []
        for start in self.nodes_sorted():
            if start in seen:
                continue
            queue = [start]
            seen.add(start)
            membership = []
            while queue:
                node = queue.pop(0)
                membership.append(node)
                for nxt in sorted(self._nodes[node]):
                    if nxt not in seen:
                        seen.add(nxt)
                        queue.append(nxt)
            components.append(sorted(membership))
        return components

    def has_cycle(self):
        """True when the undirected graph contains a cycle (depth-first search
        tracking the parent edge)."""
        seen = set()
        for start in self.nodes_sorted():
            if start in seen:
                continue
            stack = [(start, None)]
            seen.add(start)
            while stack:
                node, parent = stack.pop()
                for nxt in self._nodes[node]:
                    if nxt == parent:
                        continue
                    if nxt in seen:
                        return True
                    seen.add(nxt)
                    stack.append((nxt, node))
        return False

    def reachable(self, root):
        """All nodes reachable from ``root`` (sorted), breadth-first."""
        if str(root) not in self._nodes:
            return []
        seen = {str(root)}
        queue = [str(root)]
        while queue:
            node = queue.pop(0)
            for nxt in sorted(self._nodes[node]):
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)
        return sorted(seen)

    def density(self):
        """``2E / (V(V-1))`` for this undirected graph; 0.0 for degenerate
        sizes."""
        n = len(self._nodes)
        edges = self.edge_count()
        if n < 2:
            return 0.0
        return (2.0 * edges) / (n * (n - 1))

    def to_graph_dict(self):
        """Deterministic structural dict (sorted everywhere) for tests,
        digests and cross-representation checks."""
        return {
            "nodes": self.nodes_sorted(),
            "edges": sorted(
                (a, b) for a in self._nodes for b in self._nodes[a]
                if a < b),
            "node_count": len(self._nodes),
            "edge_count": self.edge_count(),
            "components": self.connected_components(),
            "has_cycle": self.has_cycle(),
            "density": self.density(),
        }

    def preview(self):
        return self.to_graph_dict()

    def __repr__(self):
        return "Graph(nodes=%d, edges=%d)" % (self.node_count(), self.edge_count())


class ClaimGraph(Graph):
    """Evidence representation: claim nodes, ``src:<source>`` support nodes,
    and claim–claim contradiction edges.

    Supports a claim via ``add_claim`` (computes polarity deterministically
    from the text using the logic domain) and ``add_support(claim_id, source)``.
    """

    def __init__(self):
        super().__init__()
        self._claims = {}
        self._contradictions = []

    def add_claim(self, claim_id, text):
        newly = self.add_node(claim_id)
        self._claims[str(claim_id)] = {
            "id": str(claim_id),
            "text": str(text),
            "polarity": "negated" if negation_marked(str(text)) else "asserted",
        }
        return newly

    def add_support(self, claim_id, source):
        return self.add_edge(claim_id, "src:" + str(source))

    def add_contradiction(self, claim_a, claim_b):
        """Record a contradiction edge between two claim nodes."""
        if self.add_edge(claim_a, claim_b):
            pair = tuple(sorted((str(claim_a), str(claim_b))))
            if pair not in self._contradictions:
                self._contradictions.append(pair)
        return self.add_edge(claim_a, claim_b)

    def claims(self):
        return sorted(self._claims)

    def claim(self, claim_id):
        return self._claims.get(str(claim_id))

    def contradictory_pairs(self):
        """Sorted claim–claim contradiction pairs."""
        return sorted(set(self._contradictions))

    def sources(self):
        return sorted(node for node in self._nodes
                      if node.startswith("src:"))

    def find_contradictions(self, min_overlap=3):
        """Scan all claim pairs with the logic domain and record genuine
        contradictions as edges. Returns the sorted pair list. Deterministic."""
        ids = self.claims()
        for index, a in enumerate(ids):
            for b in ids[index + 1:]:
                result = contradictory_claims(
                    self._claims[a]["text"], self._claims[b]["text"],
                    min_overlap=min_overlap)
                if result["contradictory"]:
                    self.add_contradiction(a, b)
        return self.contradictory_pairs()

    def source_degrees(self):
        return {src: self.degree(src) for src in self.sources()}
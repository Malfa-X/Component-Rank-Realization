"""tests/test_graph.py"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pytest
from parsing.use_relation import Component
from graph.component_graph import build_cluster_graph
from graph.matrix_builder import build_distribution_matrix


def _make_comp(qname: str, uses: set[str], cluster_id: int) -> Component:
    c = Component(
        qualified_name=qname,
        simple_name=qname.split(".")[-1],
        file_path=f"/fake/{qname}.java",
        source_lines=[],
        uses=uses,
    )
    c.cluster_id = cluster_id
    return c


# ── build_cluster_graph ──────────────────────────────────────────────────────

class TestBuildClusterGraph:
    def test_basic_inter_cluster_edge(self):
        # Cluster 0: A, uses B (cluster 1)
        comps = [
            _make_comp("A", {"B"}, 0),
            _make_comp("B", set(), 1),
        ]
        name_to_idx = {"A": 0, "B": 1}
        adj = build_cluster_graph(comps, name_to_idx)
        assert 1 in adj[0]
        assert len(adj[1]) == 0

    def test_intra_cluster_self_loop_excluded(self):
        # A and B are in the same cluster (0); A uses B → self-loop must be removed
        comps = [
            _make_comp("A", {"B"}, 0),
            _make_comp("B", set(), 0),
        ]
        name_to_idx = {"A": 0, "B": 1}
        adj = build_cluster_graph(comps, name_to_idx)
        assert 0 not in adj[0]  # no self-loop on cluster 0

    def test_all_clusters_present_as_keys(self):
        comps = [
            _make_comp("A", set(), 0),
            _make_comp("B", set(), 1),
            _make_comp("C", set(), 2),
        ]
        name_to_idx = {"A": 0, "B": 1, "C": 2}
        adj = build_cluster_graph(comps, name_to_idx)
        assert set(adj.keys()) == {0, 1, 2}

    def test_multiple_components_same_cluster_deduplicate_edges(self):
        # A1 and A2 are both in cluster 0 and both use B (cluster 1)
        comps = [
            _make_comp("A1", {"B"}, 0),
            _make_comp("A2", {"B"}, 0),
            _make_comp("B", set(), 1),
        ]
        name_to_idx = {"A1": 0, "A2": 1, "B": 2}
        adj = build_cluster_graph(comps, name_to_idx)
        # Should have exactly one edge 0→1 (set, not multiset)
        assert adj[0] == {1}


# ── build_distribution_matrix ─────────────────────────────────────────────────

class TestBuildDistributionMatrix:
    def test_row_sums_non_sink(self):
        adj = {0: {1, 2}, 1: {0}, 2: {0, 1}}
        D = build_distribution_matrix(adj, N=3, p=0.85)
        np.testing.assert_allclose(D.sum(axis=1), np.ones(3), atol=1e-12)

    def test_row_sums_with_sink(self):
        adj = {0: {1}, 1: set(), 2: {0}}  # node 1 is a sink
        D = build_distribution_matrix(adj, N=3, p=0.85)
        np.testing.assert_allclose(D.sum(axis=1), np.ones(3), atol=1e-12)

    def test_sink_row_is_uniform(self):
        adj = {0: {1}, 1: set()}
        D = build_distribution_matrix(adj, N=2, p=0.85)
        # Row 1 (sink) should be uniform [0.5, 0.5]
        np.testing.assert_allclose(D[1], [0.5, 0.5], atol=1e-12)

    def test_non_sink_teleport_term(self):
        # With p=0.85, N=3, non-neighbour gets exactly (1-0.85)/3
        adj = {0: {1}, 1: {0}, 2: {0}}
        D = build_distribution_matrix(adj, N=3, p=0.85)
        teleport = 0.15 / 3
        # D[0, 2] should be the teleport only (0 is not a neighbour of... wait)
        # Node 0 has only one neighbour: 1.  So D[0,2] = teleport.
        np.testing.assert_allclose(D[0, 2], teleport, atol=1e-12)

    def test_all_entries_positive(self):
        adj = {0: {1}, 1: {2}, 2: set()}
        D = build_distribution_matrix(adj, N=3, p=0.85)
        assert np.all(D > 0)

    def test_single_node_trivial(self):
        adj = {0: set()}
        D = build_distribution_matrix(adj, N=1, p=0.85)
        assert D.shape == (1, 1)
        np.testing.assert_allclose(D[0, 0], 1.0, atol=1e-12)

    def test_equal_distribution_among_neighbours(self):
        # Node 0 → nodes 1, 2, 3  (3 outgoing edges)
        adj = {0: {1, 2, 3}, 1: set(), 2: set(), 3: set()}
        D = build_distribution_matrix(adj, N=4, p=0.85)
        # Each neighbour gets p/3 + (1-p)/4
        expected_neighbour = 0.85 / 3 + 0.15 / 4
        for j in [1, 2, 3]:
            np.testing.assert_allclose(D[0, j], expected_neighbour, atol=1e-12)
        # Non-neighbour (self) gets only teleport
        np.testing.assert_allclose(D[0, 0], 0.15 / 4, atol=1e-12)

"""tests/test_ranking.py"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pytest
from graph.matrix_builder import build_distribution_matrix
from ranking.power_iteration import power_iteration
from ranking.eigenvector import eigenvector_solver


# ── Shared helpers ────────────────────────────────────────────────────────────

def _chain_graph(N: int) -> dict[int, set[int]]:
    """0→1→2→…→N-1, where N-1 is a sink."""
    return {i: ({i + 1} if i < N - 1 else set()) for i in range(N)}


def _cycle_graph(N: int) -> dict[int, set[int]]:
    """0→1→…→N-1→0"""
    return {i: {(i + 1) % N} for i in range(N)}


# ── power_iteration ───────────────────────────────────────────────────────────

class TestPowerIteration:
    def test_weights_sum_to_one(self):
        adj = _chain_graph(4)
        D = build_distribution_matrix(adj, N=4)
        W = power_iteration(D)
        np.testing.assert_allclose(W.sum(), 1.0, atol=1e-10)

    def test_all_weights_non_negative(self):
        adj = _cycle_graph(5)
        D = build_distribution_matrix(adj, N=5)
        W = power_iteration(D)
        assert np.all(W >= 0)

    def test_chain_most_used_node_highest_rank(self):
        # In a chain 0→1→2, node 2 is the sink and receives the most flow.
        adj = {0: {1}, 1: {2}, 2: set()}
        D = build_distribution_matrix(adj, N=3, p=0.85)
        W = power_iteration(D)
        assert W[2] > W[1] > W[0]

    def test_symmetric_graph_equal_weights(self):
        # Cycle 0→1→2→0: by symmetry all weights should be equal ~1/3
        adj = _cycle_graph(3)
        D = build_distribution_matrix(adj, N=3)
        W = power_iteration(D)
        np.testing.assert_allclose(W, [1/3, 1/3, 1/3], atol=1e-6)

    def test_single_node(self):
        D = build_distribution_matrix({0: set()}, N=1)
        W = power_iteration(D)
        np.testing.assert_allclose(W, [1.0], atol=1e-12)

    def test_two_nodes_mutual(self):
        # 0↔1, equal mutual use → equal weights
        adj = {0: {1}, 1: {0}}
        D = build_distribution_matrix(adj, N=2)
        W = power_iteration(D)
        np.testing.assert_allclose(W[0], W[1], atol=1e-8)

    def test_stationary_property(self):
        # W should satisfy W = D'^T @ W after convergence
        adj = {0: {1, 2}, 1: {0}, 2: {1}}
        D = build_distribution_matrix(adj, N=3)
        W = power_iteration(D, epsilon=1e-12)
        np.testing.assert_allclose(D.T @ W, W, atol=1e-8)

    def test_does_not_converge_raises(self):
        # Use an asymmetric graph (chain with sink) so the first step does NOT
        # converge: initial W=[0.5,0.5] → after 1 step W=[0.2875,0.7125],
        # delta ≈ 0.425 >> epsilon=1e-100.
        adj = {0: {1}, 1: set()}  # 0→1, 1 is a sink
        D = build_distribution_matrix(adj, N=2, p=0.85)
        with pytest.raises(RuntimeError, match="did not converge"):
            power_iteration(D, epsilon=1e-100, max_iter=1)


# ── eigenvector_solver ────────────────────────────────────────────────────────

class TestEigenvectorSolver:
    def test_weights_sum_to_one(self):
        adj = _chain_graph(4)
        D = build_distribution_matrix(adj, N=4)
        W = eigenvector_solver(D)
        np.testing.assert_allclose(W.sum(), 1.0, atol=1e-10)

    def test_all_weights_non_negative(self):
        adj = _cycle_graph(5)
        D = build_distribution_matrix(adj, N=5)
        W = eigenvector_solver(D)
        assert np.all(W >= 0)

    def test_agrees_with_power_iteration(self):
        adj = {0: {1, 2}, 1: {0}, 2: {1, 0}}
        D = build_distribution_matrix(adj, N=3, p=0.85)
        W_power = power_iteration(D, epsilon=1e-12)
        W_eigen = eigenvector_solver(D)
        np.testing.assert_allclose(W_power, W_eigen, atol=1e-6)

    def test_stationary_property(self):
        adj = {0: {1}, 1: {2}, 2: {0}}
        D = build_distribution_matrix(adj, N=3)
        W = eigenvector_solver(D)
        np.testing.assert_allclose(D.T @ W, W, atol=1e-8)

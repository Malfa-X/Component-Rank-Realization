"""
graph/matrix_builder.py
Constructs the N×N amended distribution ratio matrix D' from the
cluster adjacency dict.

Mathematical background (Definition 4 from the paper):

    d'_ij = p * d_ij + (1-p)/N    if node i has at least one outgoing edge
    d'_ij = 1/N                   if node i has no outgoing edges (sink)

where:
    d_ij = 1/out_degree(i)  if there is an edge i→j, else 0
    p    = damping factor (default 0.85)
    N    = total number of cluster nodes

Convention: D'[i, j] is the fraction of cluster i's weight flowing to
cluster j (row-stochastic: rows sum to 1).

Power iteration uses W_new = (D')^T @ W, so the transpose of D' is taken
once before iteration starts — see ranking/power_iteration.py.

Row-sum proof:
  Non-sink row i with out-degree k:
    sum_j d'_ij = k * (p/k + (1-p)/N) + (N-k) * (1-p)/N
                = p + k*(1-p)/N + (N-k)*(1-p)/N
                = p + N*(1-p)/N = p + (1-p) = 1  ✓
  Sink row i:
    sum_j d'_ij = N * (1/N) = 1  ✓
"""

from __future__ import annotations
import numpy as np

from config import DEFAULT_DAMPING


def build_distribution_matrix(
    adjacency: dict[int, set[int]],
    N: int,
    p: float = DEFAULT_DAMPING,
) -> np.ndarray:
    """
    Build the N×N amended distribution ratio matrix D'.

    Parameters
    ----------
    adjacency:
        {source_cluster_id: set of target_cluster_ids}
        Must contain every cluster ID 0..N-1 as a key.
    N:
        Number of cluster nodes.
    p:
        Damping factor (real-use-relation weight).  Default 0.85.

    Returns
    -------
    D_prime: np.ndarray, shape (N, N), float64
        Row-stochastic matrix.  Rows sum to 1.0 within float tolerance.
    """
    if N == 1:
        # Trivial case: single cluster, full self-loop via pseudo relations.
        return np.ones((1, 1), dtype=np.float64)

    D_prime = np.zeros((N, N), dtype=np.float64)
    teleport = (1.0 - p) / N  # contribution from pseudo use relations

    for i in range(N):
        out_neighbors = adjacency[i]
        deg = len(out_neighbors)

        if deg == 0:
            # Sink node: distribute uniformly to all nodes
            D_prime[i, :] = 1.0 / N
        else:
            # Pseudo relations flow to every node
            D_prime[i, :] = teleport
            # Real relations add extra weight to actual neighbours
            real_weight = p / deg
            for j in out_neighbors:
                D_prime[i, j] += real_weight

    # Validate: every row must sum to 1.0
    row_sums = D_prime.sum(axis=1)
    if not np.allclose(row_sums, 1.0, atol=1e-10):
        bad = np.where(~np.isclose(row_sums, 1.0, atol=1e-10))[0]
        raise ValueError(
            f"D' row sums are not all 1.0 for rows: {bad.tolist()}. "
            f"Sums: {row_sums[bad]}"
        )

    return D_prime

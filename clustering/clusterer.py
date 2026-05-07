"""
clustering/clusterer.py
Builds equivalence classes from the pairwise similarity matrix.

Algorithm:
  For every pair (i, j) with S[i,j] >= threshold, merge them via Union-Find.
  Union-Find's transitivity naturally handles the case where
  S(A,B) >= t and S(B,C) >= t but S(A,C) < t — all three still end up
  in the same cluster, consistent with the paper's "equivalence relation"
  framing.

After clustering, each Component receives a contiguous cluster_id in
0 .. N-1, where N = number of distinct clusters.
"""

from __future__ import annotations
import numpy as np

from parsing.use_relation import Component
from clustering.union_find import UnionFind
from config import DEFAULT_THRESHOLD


def cluster_components(
    components: list[Component],
    similarity_matrix: np.ndarray,
    threshold: float = DEFAULT_THRESHOLD,
) -> tuple[list[Component], dict[int, list[int]]]:
    """
    Assign cluster IDs to each component and return the cluster map.

    Parameters
    ----------
    components:
        List of M Component objects (modified in-place: cluster_id is set).
    similarity_matrix:
        (M, M) symmetric float matrix; S[i,i] == 1.0.
    threshold:
        Pairs with S[i,j] >= threshold are merged into the same cluster.

    Returns
    -------
    components:
        The same list, with each component's cluster_id now assigned.
    cluster_map:
        Dict mapping contiguous cluster_id (0..N-1) to the list of
        component indices belonging to that cluster.
    """
    M = len(components)
    uf = UnionFind(M)

    # Merge all pairs that exceed the similarity threshold
    for i in range(M):
        for j in range(i + 1, M):
            if similarity_matrix[i, j] >= threshold:
                uf.union(i, j)

    # raw_clusters: {root_index: [member indices]}
    raw_clusters = uf.get_clusters()

    # Remap root indices to contiguous 0..N-1
    # Sort roots for deterministic ordering
    sorted_roots = sorted(raw_clusters.keys())
    root_to_cid: dict[int, int] = {
        root: cid for cid, root in enumerate(sorted_roots)
    }

    # Assign cluster_id on each Component
    for comp_idx, comp in enumerate(components):
        root = uf.find(comp_idx)
        comp.cluster_id = root_to_cid[root]

    # Build cluster_map with remapped IDs
    cluster_map: dict[int, list[int]] = {
        root_to_cid[root]: members
        for root, members in raw_clusters.items()
    }

    return components, cluster_map

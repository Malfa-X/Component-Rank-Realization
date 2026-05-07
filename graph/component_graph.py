"""
graph/component_graph.py
Builds the directed adjacency structure between clusters.

An edge (cluster_i → cluster_j) exists when at least one component in
cluster_i has a use relation targeting at least one component in cluster_j,
and i ≠ j (intra-cluster self-loops are excluded).

The paper uses binary (present/absent) edges with equal distribution
ratios, so multiple use relations between the same pair of clusters count
as a single edge.
"""

from __future__ import annotations
from parsing.use_relation import Component


def build_cluster_graph(
    components: list[Component],
    name_to_idx: dict[str, int],
) -> dict[int, set[int]]:
    """
    Build a cluster-level adjacency from component-level use relations.

    Parameters
    ----------
    components:
        List of Component objects with cluster_id already assigned.
    name_to_idx:
        Maps qualified_name → index in components list.

    Returns
    -------
    adjacency:
        Dict {source_cluster_id: set of target_cluster_ids}.
        Every cluster ID from 0 to N-1 has a key (possibly with empty set).
    """
    N = max(c.cluster_id for c in components) + 1  # type: ignore[arg-type]
    adjacency: dict[int, set[int]] = {i: set() for i in range(N)}

    for comp in components:
        src_cid = comp.cluster_id
        for used_name in comp.uses:
            target_idx = name_to_idx.get(used_name)
            if target_idx is None:
                continue  # defensive: should already be filtered by parser
            tgt_cid = components[target_idx].cluster_id
            if tgt_cid != src_cid:  # exclude intra-cluster self-loops
                adjacency[src_cid].add(tgt_cid)  # type: ignore[index]

    return adjacency

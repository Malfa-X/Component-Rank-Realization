"""tests/test_clustering.py"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pytest
from parsing.use_relation import Component
from clustering.union_find import UnionFind
from clustering.clusterer import cluster_components


def _make_components(n: int) -> list[Component]:
    return [
        Component(
            qualified_name=f"com.example.C{i}",
            simple_name=f"C{i}",
            file_path=f"/fake/C{i}.java",
            source_lines=[],
        )
        for i in range(n)
    ]


# ── UnionFind ────────────────────────────────────────────────────────────────

class TestUnionFind:
    def test_initial_all_separate(self):
        uf = UnionFind(5)
        assert uf.num_clusters() == 5

    def test_union_merges(self):
        uf = UnionFind(4)
        uf.union(0, 1)
        assert uf.same(0, 1)
        assert not uf.same(0, 2)

    def test_transitivity(self):
        uf = UnionFind(3)
        uf.union(0, 1)
        uf.union(1, 2)
        assert uf.same(0, 2)  # transitive

    def test_union_returns_false_when_already_same(self):
        uf = UnionFind(3)
        uf.union(0, 1)
        assert uf.union(0, 1) is False

    def test_get_clusters_contiguous_after_remap(self):
        uf = UnionFind(4)
        uf.union(0, 2)
        uf.union(1, 3)
        clusters = uf.get_clusters()
        # Should have exactly 2 clusters
        assert len(clusters) == 2
        # All 4 indices should appear
        all_members = [idx for members in clusters.values() for idx in members]
        assert sorted(all_members) == [0, 1, 2, 3]

    def test_path_compression_correctness(self):
        uf = UnionFind(6)
        for i in range(5):
            uf.union(i, i + 1)
        for i in range(6):
            assert uf.same(0, i)


# ── Clusterer ────────────────────────────────────────────────────────────────

class TestClusterer:
    def test_all_different_n_equals_m(self):
        M = 4
        comps = _make_components(M)
        S = np.eye(M)
        comps, cmap = cluster_components(comps, S, threshold=0.80)
        assert len(cmap) == M
        for c in comps:
            assert c.cluster_id is not None

    def test_all_identical_single_cluster(self):
        M = 3
        comps = _make_components(M)
        S = np.ones((M, M))
        comps, cmap = cluster_components(comps, S, threshold=0.80)
        assert len(cmap) == 1
        assert all(c.cluster_id == 0 for c in comps)

    def test_transitivity_merges_all(self):
        # S(A,B)=0.9, S(B,C)=0.9, S(A,C)=0.5 — all should merge
        S = np.array([
            [1.0, 0.9, 0.5],
            [0.9, 1.0, 0.9],
            [0.5, 0.9, 1.0],
        ])
        comps = _make_components(3)
        comps, cmap = cluster_components(comps, S, threshold=0.80)
        assert len(cmap) == 1

    def test_cluster_ids_contiguous(self):
        M = 5
        comps = _make_components(M)
        S = np.eye(M)
        comps, cmap = cluster_components(comps, S, threshold=0.80)
        ids = {c.cluster_id for c in comps}
        assert ids == set(range(len(cmap)))

    def test_cluster_map_covers_all_components(self):
        M = 4
        comps = _make_components(M)
        S = np.array([
            [1.0, 0.9, 0.0, 0.0],
            [0.9, 1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.85],
            [0.0, 0.0, 0.85, 1.0],
        ])
        comps, cmap = cluster_components(comps, S, threshold=0.80)
        assert len(cmap) == 2
        all_in_map = [idx for members in cmap.values() for idx in members]
        assert sorted(all_in_map) == list(range(M))

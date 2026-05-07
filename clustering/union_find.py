"""
clustering/union_find.py
Path-compressed, union-by-rank Union-Find (Disjoint Set Union).
"""

from __future__ import annotations
from collections import defaultdict


class UnionFind:
    """
    Union-Find with path compression and union by rank.

    All operations are effectively O(α(n)) amortised where α is the
    inverse Ackermann function — practically constant for any realistic n.
    """

    def __init__(self, n: int) -> None:
        self.parent: list[int] = list(range(n))
        self.rank: list[int] = [0] * n

    def find(self, x: int) -> int:
        """Return the root representative of x's set (with path compression)."""
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])  # recursive path halving
        return self.parent[x]

    def union(self, x: int, y: int) -> bool:
        """
        Merge the sets containing x and y.
        Returns True if they were in different sets (a merge happened),
        False if they were already in the same set.
        """
        rx, ry = self.find(x), self.find(y)
        if rx == ry:
            return False
        # Attach smaller-rank tree under larger-rank tree
        if self.rank[rx] < self.rank[ry]:
            rx, ry = ry, rx
        self.parent[ry] = rx
        if self.rank[rx] == self.rank[ry]:
            self.rank[rx] += 1
        return True

    def same(self, x: int, y: int) -> bool:
        """Return True if x and y are in the same set."""
        return self.find(x) == self.find(y)

    def get_clusters(self) -> dict[int, list[int]]:
        """
        Return a mapping from root index to the list of all member indices
        in that cluster.

        Note: root indices are NOT contiguous 0..k-1; they are the indices
        of whichever element happens to be the root after all unions.
        The caller is responsible for remapping to 0..k-1 if needed.
        """
        clusters: dict[int, list[int]] = defaultdict(list)
        for i in range(len(self.parent)):
            clusters[self.find(i)].append(i)
        return dict(clusters)

    def num_clusters(self) -> int:
        """Return the number of disjoint sets."""
        return len({self.find(i) for i in range(len(self.parent))})

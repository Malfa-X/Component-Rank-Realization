"""
similarity/base.py
Abstract base class for all similarity methods.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from parsing.use_relation import Component


class SimilarityMethod(ABC):
    """
    Interface for pairwise source-code similarity computation.

    Implementations must return a value in [0.0, 1.0]:
      - 1.0 means the two components are identical
      - 0.0 means they share no common content
    The computation must be symmetric: compute(a, b) == compute(b, a).
    """

    @abstractmethod
    def compute(self, a: Component, b: Component) -> float:
        """Return similarity score between components a and b."""
        ...

    # ------------------------------------------------------------------
    # Shared helper
    # ------------------------------------------------------------------

    @staticmethod
    def _size_ratio_exceeds_cutoff(len_a: int, len_b: int, cutoff: float) -> bool:
        """
        Quick short-circuit: if the larger sequence is more than `cutoff`
        times the smaller, the Jaccard similarity cannot exceed 1/(cutoff+1)
        — far below any practical clustering threshold — so we return 0.0.
        """
        if len_a == 0 or len_b == 0:
            return len_a != len_b  # both zero → same; one zero → different
        lo, hi = min(len_a, len_b), max(len_a, len_b)
        return (hi / lo) > cutoff

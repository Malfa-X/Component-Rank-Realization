"""
similarity/diff_based.py
Diff-based similarity mirroring the CCFinder + diff approach from the paper.

Formula (Jaccard variant):
    S(a, b) = shared_lines / (len_a + len_b - shared_lines)

where shared_lines is the number of lines that appear in both files,
counted as the sum of matching-block sizes from a SequenceMatcher diff.

This is equivalent to: |A ∩ B| / |A ∪ B| on the multiset of lines.
"""

from __future__ import annotations
import difflib

from parsing.use_relation import Component
from similarity.base import SimilarityMethod
from config import SIZE_RATIO_CUTOFF


class DiffBasedSimilarity(SimilarityMethod):
    """
    Line-level Jaccard similarity via difflib.SequenceMatcher.

    Why autojunk=False:
        SequenceMatcher's junk heuristic treats lines that appear in
        more than 1% of the sequence as "junk" (e.g. closing braces `}`).
        For source-code comparison this artificially lowers similarity, so
        we disable it.
    """

    def compute(self, a: Component, b: Component) -> float:
        lines_a = a.source_lines
        lines_b = b.source_lines
        len_a, len_b = len(lines_a), len(lines_b)

        # Identical-length zero-line files
        if len_a == 0 and len_b == 0:
            return 1.0

        # One empty → no shared content
        if len_a == 0 or len_b == 0:
            return 0.0

        # Size-ratio short-circuit
        if self._size_ratio_exceeds_cutoff(len_a, len_b, SIZE_RATIO_CUTOFF):
            return 0.0

        matcher = difflib.SequenceMatcher(
            None, lines_a, lines_b, autojunk=False
        )
        # get_matching_blocks() returns (i, j, n) triples where
        # lines_a[i:i+n] == lines_b[j:j+n]. Sum the n's.
        shared = sum(n for _, _, n in matcher.get_matching_blocks())

        # Jaccard: intersection / union
        union = len_a + len_b - shared
        return shared / union if union > 0 else 0.0

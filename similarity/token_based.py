"""
similarity/token_based.py
Token-based similarity using an LCS of source-language tokens.

Formula (Jaccard variant):
    S(a, b) = lcs_length(tokens_a, tokens_b)
              / (len_tokens_a + len_tokens_b - lcs_length(...))

The tokenizer is language-specific and is injected via the constructor.
The default tokenizer (java_tokenize) preserves backwards compatibility
with existing Java-only usage.

For long token sequences (> TOKEN_LCS_FALLBACK_LIMIT) the pure-Python
O(m·n) DP table is replaced by difflib.SequenceMatcher on the token
lists, which uses a faster heuristic algorithm.
"""

from __future__ import annotations

import difflib
from typing import Callable

from parsing.use_relation import Component
from similarity.base import SimilarityMethod
from config import SIZE_RATIO_CUTOFF, TOKEN_LCS_FALLBACK_LIMIT


def _lcs_length_dp(a: list[str], b: list[str]) -> int:
    """
    Exact LCS length via two-row dynamic programming.
    Time: O(m·n). Space: O(min(m,n)).
    Always called with len(a) >= len(b) (caller ensures this).
    """
    n = len(b)
    prev = [0] * (n + 1)
    for ai in a:
        curr = [0] * (n + 1)
        for j in range(1, n + 1):
            if ai == b[j - 1]:
                curr[j] = prev[j - 1] + 1
            else:
                curr[j] = prev[j] if prev[j] > curr[j - 1] else curr[j - 1]
        prev = curr
    return prev[n]


def _lcs_length_fast(a: list[str], b: list[str]) -> int:
    """
    Approximate LCS via difflib.SequenceMatcher (Ratcliff/Obershelp).
    Faster than the O(m·n) DP for long sequences; trades exactness for speed.
    """
    matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
    return sum(n for _, _, n in matcher.get_matching_blocks())


class TokenBasedSimilarity(SimilarityMethod):
    """
    Similarity based on the longest common subsequence of source tokens.

    Parameters
    ----------
    tokenizer_fn:
        A callable (source_lines: list[str]) -> list[str] that converts
        source code into a flat list of token value strings.  When None,
        the Java tokenizer (javalang) is used as the default, preserving
        backwards compatibility.

    Tokens are cached per component qualified_name to avoid re-tokenizing
    on each pair comparison.
    """

    def __init__(
        self, tokenizer_fn: Callable[[list[str]], list[str]] | None = None
    ) -> None:
        if tokenizer_fn is None:
            from similarity.tokenizers import java_tokenize
            tokenizer_fn = java_tokenize
        self._tokenizer_fn = tokenizer_fn
        # Cache: qualified_name → token list
        self._cache: dict[str, list[str]] = {}

    def _get_tokens(self, comp: Component) -> list[str]:
        if comp.qualified_name not in self._cache:
            self._cache[comp.qualified_name] = self._tokenizer_fn(comp.source_lines)
        return self._cache[comp.qualified_name]

    def compute(self, a: Component, b: Component) -> float:
        tok_a = self._get_tokens(a)
        tok_b = self._get_tokens(b)
        len_a, len_b = len(tok_a), len(tok_b)

        if len_a == 0 and len_b == 0:
            return 1.0
        if len_a == 0 or len_b == 0:
            return 0.0

        if self._size_ratio_exceeds_cutoff(len_a, len_b, SIZE_RATIO_CUTOFF):
            return 0.0

        # Choose algorithm based on sequence length
        if min(len_a, len_b) > TOKEN_LCS_FALLBACK_LIMIT:
            shared = _lcs_length_fast(tok_a, tok_b)
        else:
            # Ensure len(a) >= len(b) for the DP (minor optimisation)
            if len_a >= len_b:
                shared = _lcs_length_dp(tok_a, tok_b)
            else:
                shared = _lcs_length_dp(tok_b, tok_a)

        union = len_a + len_b - shared
        return shared / union if union > 0 else 0.0

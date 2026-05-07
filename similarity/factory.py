"""
similarity/factory.py
Returns the requested SimilarityMethod instance by name.
"""

from __future__ import annotations
from similarity.base import SimilarityMethod
from similarity.diff_based import DiffBasedSimilarity
from similarity.token_based import TokenBasedSimilarity

_METHODS: dict[str, type[SimilarityMethod]] = {
    "diff": DiffBasedSimilarity,
    "token": TokenBasedSimilarity,
}


def get_similarity_method(name: str, language: str = "java") -> SimilarityMethod:
    """
    Instantiate and return a SimilarityMethod by its short name.

    Parameters
    ----------
    name:
        "diff" or "token".
    language:
        Source language ("java", "python", …).  Used only when name="token"
        to select the correct language-specific tokenizer; ignored for "diff".

    Raises ValueError for unknown names.
    """
    if name not in _METHODS:
        choices = ", ".join(f"'{k}'" for k in _METHODS)
        raise ValueError(
            f"Unknown similarity method '{name}'. Choose one of: {choices}"
        )
    if name == "token":
        from similarity.tokenizers import get_tokenizer
        return TokenBasedSimilarity(tokenizer_fn=get_tokenizer(language))
    return _METHODS[name]()


def available_methods() -> list[str]:
    return list(_METHODS.keys())

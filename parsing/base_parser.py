"""parsing/base_parser.py — Abstract base class for all language parsers."""

from __future__ import annotations
from abc import ABC, abstractmethod

from parsing.use_relation import Component


class LanguageParser(ABC):
    """
    Abstract parser that converts a source corpus directory into Component objects.

    Every language-specific parser must inherit from this class and implement
    parse_corpus().  The rest of the pipeline (similarity, clustering, ranking)
    is language-agnostic and only consumes Component objects.
    """

    @abstractmethod
    def parse_corpus(
        self, corpus_dir: str, verbose: bool = False
    ) -> list[Component]:
        """
        Parse all source files under corpus_dir and return a list of Components.

        Parameters
        ----------
        corpus_dir:
            Root directory to search recursively for source files.
        verbose:
            Emit INFO-level log messages for each pipeline sub-step.

        Returns
        -------
        List of Component objects with qualified_name, simple_name, file_path,
        source_lines, and uses populated.  cluster_id is always None at this
        stage (assigned later by the clusterer).
        """
        ...

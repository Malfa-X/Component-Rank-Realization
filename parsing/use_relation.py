"""
parsing/use_relation.py
Core data structure representing a single Java component (one .java file).
"""

from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class Component:
    # Fully-qualified class name, e.g. "org.apache.commons.lang3.StringUtils"
    qualified_name: str

    # Simple (unqualified) class name, e.g. "StringUtils"
    simple_name: str

    # Absolute path to the source file on disk
    file_path: str

    # Raw source lines retained for diff-based similarity computation.
    # Produced by source.splitlines(keepends=True).
    source_lines: list[str]

    # Fully-qualified names of classes this component uses.
    # Contains only names that resolve to other corpus members.
    # Populated by java_parser.py; empty set until then.
    uses: set[str] = field(default_factory=set)

    # Index into the cluster list, assigned by clusterer.py.
    # None until clustering has run.
    cluster_id: int | None = None

    def __repr__(self) -> str:
        return (
            f"Component({self.qualified_name!r}, "
            f"uses={len(self.uses)}, cluster={self.cluster_id})"
        )

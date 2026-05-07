"""
parsing/treesitter_java_parser.py
Java parser backed by tree-sitter-java.  Supports Java 8–21 syntax
(records, sealed classes, text blocks, module-info, etc.).

This parser mirrors the two-phase design of java_parser.py:
  Phase 1 — Fast line-scan to build the corpus name map (same code path).
  Phase 2 — tree-sitter AST walk to extract use relations.

Use-relation extraction strategy
----------------------------------
Rather than using S-expression queries (whose grammar node names can shift
between tree-sitter-java grammar versions), this parser walks the tree
iteratively and collects every node whose type is "type_identifier" or
"scoped_type_identifier", skipping import_declaration and
package_declaration subtrees.  These are the only node types in the
tree-sitter-java grammar that represent type references.  Variable names,
method names, and other identifiers use the "identifier" type, not
"type_identifier", so false positives are rare.  Any name that does not
resolve to a corpus member is silently dropped by _resolve().

Requires
--------
    pip install tree-sitter>=0.22.0 tree-sitter-java
"""

from __future__ import annotations

import logging
import os
from collections import defaultdict
from pathlib import Path
from typing import Iterator

from parsing.base_parser import LanguageParser
from parsing.use_relation import Component

log = logging.getLogger(__name__)

# ─── Tree-sitter bootstrap (lazy import) ────────────────────────────────────

def _bootstrap():
    """Import tree-sitter-java and return (Language, Parser class)."""
    try:
        import tree_sitter_java as tsjava          # type: ignore[import]
        from tree_sitter import Language, Parser   # type: ignore[import]
        return Language(tsjava.language()), Parser
    except ImportError as exc:
        raise ImportError(
            "tree-sitter-java is not installed.\n"
            "Run: pip install 'tree-sitter>=0.22.0' tree-sitter-java\n"
            f"(original error: {exc})"
        ) from exc


# ─── Phase-1 helpers (identical to java_parser.py) ──────────────────────────

def _iter_java_files(corpus_dir: str) -> Iterator[str]:
    for root, _, files in os.walk(corpus_dir):
        for name in files:
            if name.endswith(".java") and name != "module-info.java":
                yield os.path.join(root, name)


def _quick_extract_package_and_class(file_path: str) -> tuple[str, str] | None:
    class_name = Path(file_path).stem
    package = ""
    try:
        with open(file_path, encoding="utf-8", errors="replace") as fh:
            for _lineno, line in enumerate(fh):
                if _lineno >= 50:
                    break
                stripped = line.strip()
                if not stripped.startswith("package "):
                    continue
                semicolon = stripped.find(";")
                if semicolon < 0:
                    continue
                package = stripped[len("package "):semicolon].strip()
                break
    except OSError:
        return None
    return package, class_name


def _build_name_map(
    java_files: list[str],
) -> tuple[dict[str, list[str]], set[str], dict[str, str]]:
    simple_name_map: dict[str, list[str]] = defaultdict(list)
    qualified_name_set: set[str] = set()
    file_to_qname: dict[str, str] = {}

    for fp in java_files:
        result = _quick_extract_package_and_class(fp)
        if result is None:
            continue
        package, class_name = result
        qname = f"{package}.{class_name}" if package else class_name
        simple_name_map[class_name].append(qname)
        qualified_name_set.add(qname)
        file_to_qname[fp] = qname

    return dict(simple_name_map), qualified_name_set, file_to_qname


# ─── Phase-2 helpers ─────────────────────────────────────────────────────────

def _node_text(node, source_bytes: bytes) -> str:
    return source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _extract_imports(
    root_node, source_bytes: bytes
) -> tuple[dict[str, str], list[str]]:
    """
    Parse import declarations by reading their raw text — avoids dependence
    on the exact grammar sub-node structure.

    Returns
    -------
    single_imports : simple_name → qualified_name (for non-wildcard imports)
    star_packages  : list of package prefixes for wildcard imports
    """
    single_imports: dict[str, str] = {}
    star_packages: list[str] = []

    for child in root_node.children:
        if child.type != "import_declaration":
            continue
        text = _node_text(child, source_bytes).strip()
        # "import com.example.Foo;" or "import static com.example.Foo;"
        # "import com.example.*;"
        if not text.startswith("import ") or not text.endswith(";"):
            continue
        path = text[7:-1].strip()           # strip "import " and ";"
        path = path.lstrip("static").strip()  # strip optional "static" keyword
        if path.endswith(".*"):
            star_packages.append(path[:-2])
        else:
            simple = path.rsplit(".", 1)[-1]
            single_imports[simple] = path

    return single_imports, star_packages


def _collect_type_names(root_node, source_bytes: bytes) -> list[str]:
    """
    Iteratively walk the tree and collect all type_identifier /
    scoped_type_identifier text values, skipping import and package
    declaration subtrees.
    """
    result: list[str] = []
    stack = [root_node]
    while stack:
        node = stack.pop()
        # Skip import/package subtrees entirely
        if node.type in ("import_declaration", "package_declaration"):
            continue
        if node.type in ("type_identifier", "scoped_type_identifier"):
            result.append(_node_text(node, source_bytes))
        # Push children (reversed so left-to-right order in stack)
        for child in reversed(node.children):
            stack.append(child)
    return result


def _resolve(
    raw_name: str,
    single_imports: dict[str, str],
    star_packages: list[str],
    package: str,
    simple_name_map: dict[str, list[str]],
    qualified_name_set: set[str],
) -> str | None:
    """Mirror the resolution strategy from java_parser._resolve()."""
    base = raw_name.split("<")[0].split("[")[0].strip()
    if not base:
        return None
    if base in qualified_name_set:
        return base
    if base in single_imports and single_imports[base] in qualified_name_set:
        return single_imports[base]
    same_pkg = f"{package}.{base}" if package else base
    if same_pkg in qualified_name_set:
        return same_pkg
    star_candidates = [
        f"{pkg}.{base}" for pkg in star_packages
        if f"{pkg}.{base}" in qualified_name_set
    ]
    if len(star_candidates) == 1:
        return star_candidates[0]
    candidates = simple_name_map.get(base, [])
    if len(candidates) == 1:
        return candidates[0]
    return None


# ─── Parser class ─────────────────────────────────────────────────────────────

class TreeSitterJavaParser(LanguageParser):
    """
    Java parser backed by tree-sitter-java.

    Handles Java 8–21 syntax.  Import resolution uses the same three-tier
    strategy (single-type imports → same package → corpus-wide fallback)
    as the javalang-based parser, but use-relation extraction is done by
    walking the tree for type_identifier nodes rather than javalang AST
    traversal.  This makes the parser robust to new Java syntax that
    javalang does not understand.
    """

    def __init__(self) -> None:
        language, Parser = _bootstrap()
        self._language = language
        self._parser = Parser(language)

    def parse_corpus(
        self, corpus_dir: str, verbose: bool = False
    ) -> list[Component]:
        java_files = list(_iter_java_files(corpus_dir))
        if verbose:
            log.info("Found %d .java files", len(java_files))

        # Phase 1
        simple_name_map, qualified_name_set, file_to_qname = _build_name_map(
            java_files
        )
        if verbose:
            log.info(
                "Corpus contains %d distinct qualified names",
                len(qualified_name_set),
            )

        # Phase 2
        components: list[Component] = []
        skipped = 0

        for fp in java_files:
            self_qname = file_to_qname.get(fp)
            if self_qname is None:
                skipped += 1
                continue

            try:
                with open(fp, encoding="utf-8", errors="replace") as fh:
                    source = fh.read()
            except OSError as exc:
                log.warning("Cannot read %s: %s", fp, exc)
                skipped += 1
                continue

            source_bytes = source.encode("utf-8", errors="replace")
            try:
                tree = self._parser.parse(source_bytes)
            except Exception as exc:
                log.debug("Skipping %s (parse error: %s)", fp, exc)
                skipped += 1
                continue

            package = self_qname.rsplit(".", 1)[0] if "." in self_qname else ""
            single_imports, star_packages = _extract_imports(
                tree.root_node, source_bytes
            )

            type_names = _collect_type_names(tree.root_node, source_bytes)

            uses: set[str] = set()
            for raw_name in type_names:
                resolved = _resolve(
                    raw_name, single_imports, star_packages,
                    package, simple_name_map, qualified_name_set,
                )
                if resolved and resolved != self_qname:
                    uses.add(resolved)

            source_lines = source.splitlines(keepends=True)
            components.append(Component(
                qualified_name=self_qname,
                simple_name=Path(fp).stem,
                file_path=fp,
                source_lines=source_lines,
                uses=uses,
            ))

        if verbose:
            log.info(
                "Parsed %d components; skipped %d files", len(components), skipped
            )
        return components

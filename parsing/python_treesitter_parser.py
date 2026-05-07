"""
parsing/python_treesitter_parser.py
Python parser backed by tree-sitter-python.

Key differences from PythonAstParser (ast-based)
-------------------------------------------------
1. Fault-tolerant: tree-sitter returns a partial tree even for files with
   syntax errors, rather than raising SyntaxError and skipping the file.
2. Version-agnostic: works on Python 2 and Python 3 syntax regardless of
   the Python version running this tool.
3. Slightly slower than the ast module for large files due to the C
   extension call overhead and tree traversal.

Use-relation extraction
-----------------------
Node types targeted (tree-sitter-python grammar):
  import_statement        → import X, import X.Y.Z
  import_from_statement   → from X import Y
  class_definition        → argument_list contains base class identifiers
  function_definition /
  async_function_def      → typed_parameter, return type annotations
  assignment              → annotated variable: x: Type = ...
  type (annotation node)  → identifier / attribute / subscript recursed

Requires
--------
    pip install tree-sitter>=0.22.0 tree-sitter-python
"""

from __future__ import annotations

import logging
import os
from typing import Iterator

from parsing.base_parser import LanguageParser
from parsing.python_parser import (
    _iter_python_files, _build_name_map, _resolve,
)
from parsing.use_relation import Component

log = logging.getLogger(__name__)


# ─── Tree-sitter bootstrap ────────────────────────────────────────────────────

def _bootstrap():
    try:
        import tree_sitter_python as tspython       # type: ignore[import]
        from tree_sitter import Language, Parser     # type: ignore[import]
        return Language(tspython.language()), Parser
    except ImportError as exc:
        raise ImportError(
            "tree-sitter-python is not installed.\n"
            "Run: pip install 'tree-sitter>=0.22.0' tree-sitter-python\n"
            f"(original error: {exc})"
        ) from exc


# ─── Node-text helper ─────────────────────────────────────────────────────────

def _node_text(node, source_bytes: bytes) -> str:
    return source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


# ─── Type name extraction from tree-sitter nodes ─────────────────────────────

def _extract_type_names_from_node(node, source_bytes: bytes) -> list[str]:
    """
    Recursively extract dotted type names from a tree-sitter type node.

    Handles:
      identifier           → simple name
      attribute            → dotted name (e.g. module.Class)
      subscript            → generic; recurse into object and subscript
      binary_operator (|)  → PEP 604 union; recurse both sides
    """
    if node is None:
        return []

    t = node.type

    if t == "identifier":
        return [_node_text(node, source_bytes)]

    if t == "attribute":
        # Reconstruct dotted name: value "." attribute
        parts: list[str] = []
        curr = node
        while curr.type == "attribute":
            attr_child = next(
                (c for c in curr.children if c.type == "identifier"), None
            )
            if attr_child is None:
                break
            parts.append(_node_text(attr_child, source_bytes))
            # The value is the first non-dot, non-identifier child
            curr = curr.children[0]
        if curr.type == "identifier":
            parts.append(_node_text(curr, source_bytes))
        return [".".join(reversed(parts))] if parts else []

    if t == "subscript":
        # Generic[T] → recurse into value and subscript
        results: list[str] = []
        if node.children:
            results.extend(_extract_type_names_from_node(node.children[0], source_bytes))
        for child in node.children[1:]:
            if child.type not in ("[", "]", ","):
                results.extend(_extract_type_names_from_node(child, source_bytes))
        return results

    if t == "binary_operator":
        # X | Y  (PEP 604)
        results = []
        for child in node.children:
            if child.type != "|":
                results.extend(_extract_type_names_from_node(child, source_bytes))
        return results

    if t == "type":
        # Wrapper node — recurse into its single child
        for child in node.children:
            names = _extract_type_names_from_node(child, source_bytes)
            if names:
                return names
        return []

    return []


# ─── Use-relation collection via tree walk ────────────────────────────────────

def _collect_uses_treesitter(
    root_node,
    source_bytes: bytes,
    self_qname: str,
    current_pkg: str,
    qualified_name_set: set[str],
    simple_name_map: dict[str, list[str]],
) -> set[str]:
    uses: set[str] = set()

    def add(name: str) -> None:
        resolved = _resolve(name, current_pkg, qualified_name_set, simple_name_map)
        if resolved and resolved != self_qname:
            uses.add(resolved)

    def add_names(node) -> None:
        for n in _extract_type_names_from_node(node, source_bytes):
            add(n)

    # Iterative BFS to avoid deep-recursion issues on large files
    queue = [root_node]
    while queue:
        node = queue.pop(0)
        t = node.type

        if t == "import_statement":
            # import X, import X.Y, import X as Y
            for child in node.children:
                if child.type in ("dotted_name", "aliased_import"):
                    name_node = child if child.type == "dotted_name" else child.children[0]
                    add(_node_text(name_node, source_bytes))

        elif t == "import_from_statement":
            # from X.Y import Z, *
            module_node = next(
                (c for c in node.children if c.type == "dotted_name"), None
            )
            if module_node:
                mod = _node_text(module_node, source_bytes)
                add(mod)
                for child in node.children:
                    if child.type == "import_list":
                        for item in child.children:
                            if item.type in ("identifier", "aliased_import"):
                                name_node = (
                                    item if item.type == "identifier"
                                    else item.children[0]
                                )
                                add(f"{mod}.{_node_text(name_node, source_bytes)}")

        elif t == "class_definition":
            # class A(B, C):  → B and C are bases
            arg_list = next(
                (c for c in node.children if c.type == "argument_list"), None
            )
            if arg_list:
                for child in arg_list.children:
                    if child.type not in (",", "(", ")"):
                        add_names(child)

        elif t in ("function_definition", "async_function_def"):
            # Return type annotation
            return_type = next(
                (c for c in node.children if c.type == "type"), None
            )
            if return_type:
                add_names(return_type)
            # Parameter annotations
            params = next(
                (c for c in node.children if c.type == "parameters"), None
            )
            if params:
                for child in params.children:
                    if child.type in (
                        "typed_parameter", "typed_default_parameter"
                    ):
                        type_node = next(
                            (c for c in child.children if c.type == "type"), None
                        )
                        if type_node:
                            add_names(type_node)

        elif t == "expression_statement":
            # Annotated assignment: x: Type = ...
            for child in node.children:
                if child.type == "assignment":
                    type_node = next(
                        (c for c in child.children if c.type == "type"), None
                    )
                    if type_node:
                        add_names(type_node)

        queue.extend(node.children)

    return uses


# ─── Public parser class ──────────────────────────────────────────────────────

class PythonTreeSitterParser(LanguageParser):
    """
    Python parser backed by tree-sitter-python.

    Fault-tolerant: partially parses files with syntax errors rather than
    skipping them entirely.  Useful for mixed-version corpora or projects
    with generated code that does not fully conform to the current Python
    grammar.
    """

    def __init__(self) -> None:
        language, Parser = _bootstrap()
        self._language = language
        self._parser = Parser(language)

    def parse_corpus(
        self, corpus_dir: str, verbose: bool = False
    ) -> list[Component]:
        py_files = list(_iter_python_files(corpus_dir))
        if verbose:
            log.info("Found %d .py files", len(py_files))

        simple_name_map, qualified_name_set, file_to_qname = _build_name_map(
            py_files, corpus_dir
        )
        if verbose:
            log.info(
                "Corpus contains %d distinct module names", len(qualified_name_set)
            )

        components: list[Component] = []
        skipped = 0

        for fp in py_files:
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
            tree = self._parser.parse(source_bytes)
            # tree-sitter always returns a tree, even for invalid files

            current_pkg = self_qname.rsplit(".", 1)[0] if "." in self_qname else ""

            uses = _collect_uses_treesitter(
                tree.root_node, source_bytes,
                self_qname, current_pkg,
                qualified_name_set, simple_name_map,
            )

            source_lines = source.splitlines(keepends=True)
            simple_name = self_qname.rsplit(".", 1)[-1]

            components.append(Component(
                qualified_name=self_qname,
                simple_name=simple_name,
                file_path=fp,
                source_lines=source_lines,
                uses=uses,
            ))

        if verbose:
            log.info(
                "Parsed %d components; skipped %d files", len(components), skipped
            )
        return components

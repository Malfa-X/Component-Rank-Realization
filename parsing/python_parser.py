"""
parsing/python_parser.py
Parses a directory tree of .py files into Component objects using
Python's built-in ast module.

Component model
---------------
  Component = one .py file (Python module).

  Qualified name = relative path from corpus_dir, with path separators
  replaced by "." and the ".py" extension stripped.

    corpus_dir = /project/src
    file       = /project/src/utils/helper.py
    qname      = utils.helper

  __init__.py files are mapped to their parent package name:
    /project/src/utils/__init__.py  →  utils

  simple_name = the final dotted segment (e.g. "helper", "utils").

Use relations extracted
-----------------------
  1. import X.Y        → uses X.Y (if in corpus)
  2. from X.Y import Z → uses X.Y; also checks X.Y.Z
  3. class A(B, C):    → uses B, uses C (resolved against corpus)
  4. Type annotations  → variable annotations, function parameter types,
                         return types (ast.AnnAssign, ast.arg, FunctionDef.returns)
  Generic annotations (e.g. Optional[Foo]) are expanded recursively so
  that the type argument Foo is also captured.

Limitations
-----------
- Only imports that resolve to corpus modules are captured; stdlib and
  third-party imports are silently dropped.
- Dynamic imports (importlib, __import__) are not captured.
- String annotations ("MyClass") are not evaluated.
- ast.parse() raises SyntaxError on invalid Python; such files are
  skipped and logged (like the Java parser skips invalid .java files).
"""

from __future__ import annotations

import ast
import logging
import os
from collections import defaultdict
from pathlib import Path
from typing import Iterator

from parsing.base_parser import LanguageParser
from parsing.use_relation import Component

log = logging.getLogger(__name__)


# ─── File discovery ───────────────────────────────────────────────────────────

def _iter_python_files(corpus_dir: str) -> Iterator[str]:
    """Yield absolute paths to all .py files, skipping __pycache__."""
    for root, dirs, files in os.walk(corpus_dir):
        # Prune __pycache__ subtrees for speed
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in files:
            if name.endswith(".py"):
                yield os.path.join(root, name)


# ─── Qualified-name derivation ────────────────────────────────────────────────

def _file_to_qname(file_path: str, corpus_dir: str) -> str:
    """
    Derive a dotted module name from a file path relative to corpus_dir.

    __init__.py → parent package name (e.g. utils/__init__.py → utils).
    All others  → dotted relative path without extension.
    """
    rel = os.path.relpath(file_path, corpus_dir)
    # Normalise Windows back-slashes
    rel = rel.replace("\\", "/")
    if rel.endswith(".py"):
        rel = rel[:-3]
    # utils/__init__ → utils
    if rel.endswith("/__init__") or rel == "__init__":
        rel = rel[: -len("/__init__")] if "/" in rel else ""
    return rel.replace("/", ".")


# ─── Phase-1: corpus name map ─────────────────────────────────────────────────

def _build_name_map(
    py_files: list[str], corpus_dir: str
) -> tuple[dict[str, list[str]], set[str], dict[str, str]]:
    """
    Returns
    -------
    simple_name_map  : last segment → [qualified_names]
    qualified_name_set : all qualified names in corpus
    file_to_qname    : absolute file path → qualified name
    """
    simple_name_map: dict[str, list[str]] = defaultdict(list)
    qualified_name_set: set[str] = set()
    file_to_qname: dict[str, str] = {}

    for fp in py_files:
        qname = _file_to_qname(fp, corpus_dir)
        if not qname:
            # Degenerate case: the corpus_dir itself is an __init__.py
            continue
        simple = qname.rsplit(".", 1)[-1]
        simple_name_map[simple].append(qname)
        qualified_name_set.add(qname)
        file_to_qname[fp] = qname

    return dict(simple_name_map), qualified_name_set, file_to_qname


# ─── Name extraction from AST annotation nodes ───────────────────────────────

def _extract_annotation_names(node: ast.expr | None) -> list[str]:
    """
    Recursively collect all type names from an annotation expression.

    Handles:
      Name           → "Foo"
      Attribute      → "module.Foo"
      Subscript      → generic type; recurse into value and slice
      BinOp (X | Y)  → PEP 604 union; recurse into both sides
      Constant (str) → string annotations are skipped
    """
    if node is None:
        return []
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, ast.Attribute):
        parts: list[str] = []
        curr: ast.expr = node
        while isinstance(curr, ast.Attribute):
            parts.append(curr.attr)
            curr = curr.value
        if isinstance(curr, ast.Name):
            parts.append(curr.id)
            return [".".join(reversed(parts))]
        return []
    if isinstance(node, ast.Subscript):
        outer = _extract_annotation_names(node.value)
        slice_node = node.slice
        if isinstance(slice_node, ast.Tuple):
            inner: list[str] = []
            for elt in slice_node.elts:
                inner.extend(_extract_annotation_names(elt))
        else:
            inner = _extract_annotation_names(slice_node)
        return outer + inner
    if isinstance(node, ast.BinOp):
        # PEP 604: X | Y
        return (
            _extract_annotation_names(node.left)
            + _extract_annotation_names(node.right)
        )
    return []


# ─── Phase-2: import + use-relation extraction ───────────────────────────────

def _resolve(
    name: str,
    current_pkg: str,
    qualified_name_set: set[str],
    simple_name_map: dict[str, list[str]],
) -> str | None:
    """
    Attempt to resolve a name to a corpus module.

    Resolution order:
    1. Exact match in qualified_name_set
    2. current_pkg.name  (same-package sibling)
    3. simple_name_map[name] if unambiguous (corpus-wide fallback)
    """
    if not name:
        return None
    if name in qualified_name_set:
        return name
    if current_pkg:
        candidate = f"{current_pkg}.{name}"
        if candidate in qualified_name_set:
            return candidate
    siblings = simple_name_map.get(name, [])
    if len(siblings) == 1:
        return siblings[0]
    return None


def _collect_uses(
    tree: ast.Module,
    self_qname: str,
    current_pkg: str,
    qualified_name_set: set[str],
    simple_name_map: dict[str, list[str]],
) -> set[str]:
    """Walk the AST and collect all resolvable use relations."""
    uses: set[str] = set()

    def add(name: str | None) -> None:
        if not name:
            return
        resolved = _resolve(name, current_pkg, qualified_name_set, simple_name_map)
        if resolved and resolved != self_qname:
            uses.add(resolved)

    for node in ast.walk(tree):
        # 1 & 2. Import statements
        if isinstance(node, ast.Import):
            for alias in node.names:
                add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod:
                add(mod)
                for alias in node.names:
                    if alias.name != "*":
                        add(f"{mod}.{alias.name}")

        # 3. Class base classes
        elif isinstance(node, ast.ClassDef):
            for base in node.bases:
                for n in _extract_annotation_names(base):
                    add(n)

        # 4. Function parameter type annotations
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            # Return annotation
            for n in _extract_annotation_names(node.returns):
                add(n)
            # Parameter annotations
            for arg in (
                node.args.args
                + node.args.posonlyargs
                + node.args.kwonlyargs
                + ([node.args.vararg] if node.args.vararg else [])
                + ([node.args.kwarg] if node.args.kwarg else [])
            ):
                for n in _extract_annotation_names(arg.annotation):
                    add(n)

        # 5. Variable annotations (x: MyClass = ...)
        elif isinstance(node, ast.AnnAssign):
            for n in _extract_annotation_names(node.annotation):
                add(n)

    return uses


# ─── Public parser class ──────────────────────────────────────────────────────

class PythonAstParser(LanguageParser):
    """
    Python parser using the built-in ast module.

    Fast and accurate for syntactically valid Python 3 code.  Files that
    fail ast.parse() (SyntaxError) are skipped and logged — matching the
    behaviour of the Java parser for unparseable .java files.
    """

    def parse_corpus(
        self, corpus_dir: str, verbose: bool = False
    ) -> list[Component]:
        py_files = list(_iter_python_files(corpus_dir))
        if verbose:
            log.info("Found %d .py files", len(py_files))

        # Phase 1
        simple_name_map, qualified_name_set, file_to_qname = _build_name_map(
            py_files, corpus_dir
        )
        if verbose:
            log.info(
                "Corpus contains %d distinct module names", len(qualified_name_set)
            )

        # Phase 2
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

            try:
                tree = ast.parse(source, filename=fp)
            except SyntaxError as exc:
                log.debug("Skipping %s (SyntaxError: %s)", fp, exc)
                skipped += 1
                continue
            except Exception as exc:
                log.debug("Skipping %s (parse error: %s)", fp, exc)
                skipped += 1
                continue

            # The "package" of utils.helper is utils
            current_pkg = self_qname.rsplit(".", 1)[0] if "." in self_qname else ""

            uses = _collect_uses(
                tree, self_qname, current_pkg,
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

"""
parsing/js_parser.py
Parses a directory tree of JavaScript / TypeScript files into Component objects
using regular expressions (no external dependencies required).

Supported file extensions
-------------------------
  .js   .mjs   .cjs   .jsx   .ts   .tsx
  TypeScript declaration files (.d.ts) are skipped (type stubs only).

Component model
---------------
  Component = one JS/TS source file.

  Qualified name = relative path from corpus_dir with path separators
  replaced by "." and the extension stripped.

    corpus_dir = /project/src
    file       = /project/src/utils/helper.ts
    qname      = utils.helper

  index.{js,ts,...} files are mapped to their parent directory name,
  analogous to Python's __init__.py:
    /project/src/utils/index.ts  →  utils

Use relations extracted (5 types)
----------------------------------
  1. ES6 imports / re-exports with 'from':  import X from './foo'
                                            export { X } from './foo'
                                            export * from './foo'
  2. Bare side-effect imports:              import './styles.css'
  3. CommonJS require():                    require('./foo')
  4. Dynamic import():                      import('./foo')
  5. Class / interface inheritance:         class A extends B
     TypeScript implements:                 class A implements B, C

Only relative paths (starting with '.') are resolved to corpus components;
bare npm package names ('react', 'lodash') are silently dropped.

Limitations
-----------
- Regex parsing is not as precise as an AST parser; strings or regex
  literals that contain import-like text may occasionally produce false
  positives.
- TypeScript generic type annotations in function signatures are not
  captured (only class-level extends/implements).
- Template-literal import paths (import('./'+name)) are not captured.
- node_modules/, dist/, build/, .next/, coverage/, .git/ directories are
  automatically excluded; .d.ts declaration files are skipped.
"""

from __future__ import annotations

import logging
import os
import re
from collections import defaultdict
from typing import Iterator

from parsing.base_parser import LanguageParser
from parsing.use_relation import Component

log = logging.getLogger(__name__)

# ─── File extensions ───────────────────────────────────────────────────────────

_JS_EXTENSIONS: frozenset[str] = frozenset({
    ".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx",
})

# Directories to skip entirely (external deps, build artefacts, vcs metadata)
_SKIP_DIRS: frozenset[str] = frozenset({
    "node_modules", ".git", "dist", "build", ".next",
    "coverage", ".nyc_output", "__pycache__",
})

# ─── Regex patterns ───────────────────────────────────────────────────────────

# Strip JS comments before applying import regexes to reduce false positives.
_COMMENT_MULTI_RE  = re.compile(r"/\*[\s\S]*?\*/", re.DOTALL)
_COMMENT_SINGLE_RE = re.compile(r"//[^\n]*")

# 1. ES6 import / re-export with 'from':
#    import X from './foo'      import { A } from './foo'
#    export { X } from './bar'  export * from './bar'
_FROM_RE = re.compile(r'\bfrom\s+[\'"]([^\'"]+)[\'"]')

# 2. Bare side-effect import (no binding, no 'from'):
#    import './styles.css'
#    Guard: the character right after the quote opener must NOT be
#    a word char or whitespace — rules out 'import type' etc. already
#    handled by _FROM_RE.
_IMPORT_BARE_RE = re.compile(r'\bimport\s+[\'"]([^\'"]+)[\'"]')

# 3. CommonJS require():  require('./foo')  / const x = require('../bar')
_REQUIRE_RE = re.compile(r'\brequire\s*\(\s*[\'"]([^\'"]+)[\'"]\s*\)')

# 4. Dynamic import():  import('./foo')
_DYN_IMPORT_RE = re.compile(r'\bimport\s*\(\s*[\'"]([^\'"]+)[\'"]\s*\)')

# 5a. class / interface A extends B  (also generic constraints are caught but
#     won't resolve to corpus members, so they are harmlessly dropped)
_EXTENDS_RE = re.compile(r'\bextends\s+([\w$][\w$]*)')

# 5b. TypeScript: class A implements B, C
_IMPLEMENTS_RE = re.compile(
    r'\bimplements\s+([\w$][\w$]*(?:\s*,\s*[\w$][\w$]*)*)'
)


# ─── File discovery ───────────────────────────────────────────────────────────

def _iter_js_files(corpus_dir: str) -> Iterator[str]:
    """
    Yield absolute paths to all JS/TS source files under corpus_dir,
    skipping node_modules, build output directories, and .d.ts files.
    """
    for root, dirs, files in os.walk(corpus_dir):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        for name in files:
            if name.endswith(".d.ts"):
                continue
            ext = os.path.splitext(name)[1].lower()
            if ext in _JS_EXTENSIONS:
                yield os.path.join(root, name)


# ─── Qualified-name derivation ────────────────────────────────────────────────

def _file_to_qname(file_path: str, corpus_dir: str) -> str | None:
    """
    Derive a dotted module name from a file path relative to corpus_dir.

    index.{js,ts,jsx,tsx,mjs,cjs} → parent directory name.
    Returns None for a root-level index file (no useful qualified name).
    """
    rel = os.path.relpath(file_path, corpus_dir).replace("\\", "/")

    # Strip extension — check longest suffixes first (.tsx before .ts, etc.)
    for ext in (".tsx", ".ts", ".jsx", ".mjs", ".cjs", ".js"):
        if rel.lower().endswith(ext):
            rel = rel[: -len(ext)]
            break

    # Map index.* to its parent directory (like Python __init__.py).
    # Root-level index files keep the name "index" — unlike Python where a
    # corpus-root __init__.py has no meaningful qualified name.
    if rel.rsplit("/", 1)[-1] == "index":
        if "/" in rel:
            rel = rel.rsplit("/", 1)[0]
        # else: rel stays as "index" — a valid corpus component name

    return rel.replace("/", ".") if rel else None


# ─── Phase-1: corpus name map ─────────────────────────────────────────────────

def _build_name_map(
    js_files: list[str], corpus_dir: str
) -> tuple[dict[str, list[str]], set[str], dict[str, str]]:
    """
    Returns
    -------
    simple_name_map    : last dotted segment → [qualified_names]
    qualified_name_set : all corpus qualified names
    file_to_qname      : absolute file path → qualified name
    """
    simple_name_map: dict[str, list[str]] = defaultdict(list)
    qualified_name_set: set[str] = set()
    file_to_qname: dict[str, str] = {}

    for fp in js_files:
        qname = _file_to_qname(fp, corpus_dir)
        if not qname:
            continue
        simple = qname.rsplit(".", 1)[-1]
        simple_name_map[simple].append(qname)
        qualified_name_set.add(qname)
        file_to_qname[fp] = qname

    return dict(simple_name_map), qualified_name_set, file_to_qname


# ─── Path and name resolution ─────────────────────────────────────────────────

def _strip_comments(source: str) -> str:
    """Remove JS single-line (//) and multi-line (/* */) comments."""
    source = _COMMENT_MULTI_RE.sub(" ", source)
    source = _COMMENT_SINGLE_RE.sub(" ", source)
    return source


def _resolve_specifier(
    specifier: str,
    current_file: str,
    corpus_dir: str,
    qualified_name_set: set[str],
) -> str | None:
    """
    Resolve a JS module specifier to a corpus qualified name.

    Only relative paths (starting with '.') are followed; bare npm package
    names, Node built-ins, and URLs are silently dropped.
    """
    if not specifier.startswith("."):
        return None

    current_dir = os.path.dirname(current_file)
    target_base = os.path.normpath(os.path.join(current_dir, specifier))

    # Candidate files: the specifier itself plus all extension variants,
    # and index.* inside a directory of that name.
    candidates: list[str] = [target_base]
    for ext in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"):
        candidates.append(target_base + ext)
    for idx_ext in (".ts", ".tsx", ".js", ".jsx"):
        candidates.append(os.path.join(target_base, "index" + idx_ext))

    for candidate in candidates:
        try:
            rel = os.path.relpath(candidate, corpus_dir).replace("\\", "/")
        except ValueError:
            continue  # different Windows drive

        # Strip extension
        for ext in (".tsx", ".ts", ".jsx", ".mjs", ".cjs", ".js"):
            if rel.lower().endswith(ext):
                rel = rel[: -len(ext)]
                break

        # Map index.* to parent directory; root-level index stays as "index"
        if rel.rsplit("/", 1)[-1] == "index":
            rel = rel.rsplit("/", 1)[0] if "/" in rel else "index"

        qname = rel.replace("/", ".") if rel else ""
        if qname and qname in qualified_name_set:
            return qname

    return None


def _resolve_simple_name(
    name: str,
    current_pkg: str,
    qualified_name_set: set[str],
    simple_name_map: dict[str, list[str]],
) -> str | None:
    """Resolve a bare class/interface name to a corpus qualified name."""
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


# ─── Phase-2: use-relation extraction ────────────────────────────────────────

def _collect_uses(
    source: str,
    self_qname: str,
    current_file: str,
    current_pkg: str,
    corpus_dir: str,
    qualified_name_set: set[str],
    simple_name_map: dict[str, list[str]],
) -> set[str]:
    """Extract all corpus-internal use relations from a JS/TS source string."""
    uses: set[str] = set()
    clean = _strip_comments(source)

    def add_spec(spec: str) -> None:
        qname = _resolve_specifier(spec, current_file, corpus_dir, qualified_name_set)
        if qname and qname != self_qname:
            uses.add(qname)

    def add_name(name: str) -> None:
        qname = _resolve_simple_name(
            name.strip(), current_pkg, qualified_name_set, simple_name_map
        )
        if qname and qname != self_qname:
            uses.add(qname)

    # 1. import/export ... from 'specifier'
    for m in _FROM_RE.finditer(clean):
        add_spec(m.group(1))

    # 2. import 'specifier'  (side-effect)
    for m in _IMPORT_BARE_RE.finditer(clean):
        add_spec(m.group(1))

    # 3. require('specifier')
    for m in _REQUIRE_RE.finditer(clean):
        add_spec(m.group(1))

    # 4. import('specifier')
    for m in _DYN_IMPORT_RE.finditer(clean):
        add_spec(m.group(1))

    # 5a. extends ClassName
    for m in _EXTENDS_RE.finditer(clean):
        add_name(m.group(1))

    # 5b. implements A, B, C
    for m in _IMPLEMENTS_RE.finditer(clean):
        for part in m.group(1).split(","):
            add_name(part.strip())

    return uses


# ─── Public parser class ──────────────────────────────────────────────────────

class JavaScriptParser(LanguageParser):
    """
    JavaScript / TypeScript parser using regular expressions.

    No external dependencies required.  Handles .js, .mjs, .cjs, .jsx,
    .ts, and .tsx files.  .d.ts declaration files and the node_modules/,
    dist/, build/, .next/, and coverage/ directories are excluded.
    """

    def parse_corpus(
        self, corpus_dir: str, verbose: bool = False
    ) -> list[Component]:
        js_files = list(_iter_js_files(corpus_dir))
        if verbose:
            log.info("Found %d JS/TS files", len(js_files))

        # Phase 1
        simple_name_map, qualified_name_set, file_to_qname = _build_name_map(
            js_files, corpus_dir
        )
        if verbose:
            log.info(
                "Corpus contains %d distinct module names", len(qualified_name_set)
            )

        # Phase 2
        components: list[Component] = []
        skipped = 0

        for fp in js_files:
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

            current_pkg = self_qname.rsplit(".", 1)[0] if "." in self_qname else ""

            uses = _collect_uses(
                source, self_qname, fp, current_pkg,
                corpus_dir, qualified_name_set, simple_name_map,
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

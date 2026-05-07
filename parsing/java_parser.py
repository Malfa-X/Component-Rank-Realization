"""
parsing/java_parser.py
Parses a directory tree of .java files into Component objects.

Two-phase design
----------------
Phase 1 — Name map: walk all files, extract package + class name to
          build a corpus-wide lookup table (simple_name → qualified_name).

Phase 2 — Full parse: for each file, resolve import statements, then
          walk the AST to extract use relations (extends, implements,
          field types, method signatures, object creation, method invocation
          qualifiers).  Only names that resolve to other corpus members
          are kept in Component.uses.

Limitations (acknowledged in the paper)
----------------------------------------
- Only statically detectable use relations are extracted.
- MethodInvocation.qualifier is a raw string; if it names a local
  variable rather than a class, resolution fails silently.
- javalang supports Java 8 syntax only; Java 9+ constructs (module-info,
  records, sealed classes) will cause a parse error that is caught and
  logged; the file is skipped.
- Internal/nested classes are excluded (paper specification).
"""

from __future__ import annotations

import logging
import os
from collections import defaultdict
from pathlib import Path
from typing import Iterator

import javalang
import javalang.tree as jt

from parsing.use_relation import Component

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Phase 1: build corpus name map
# ---------------------------------------------------------------------------

def _iter_java_files(corpus_dir: str) -> Iterator[str]:
    """Yield absolute paths to all .java files under corpus_dir."""
    for root, _, files in os.walk(corpus_dir):
        for name in files:
            if name.endswith(".java") and name != "module-info.java":
                yield os.path.join(root, name)


def _quick_extract_package_and_class(
    file_path: str,
) -> tuple[str, str] | None:
    """
    Fast extraction of package name and top-level class name without a full
    AST parse.  Returns (package, class_name) or None on failure.

    Handles:
    - Package on its own line:  "package com.example;"
    - Package and class on same line: "package p; public class Foo {}"
    - Leading blank lines (e.g. from triple-quoted string literals in tests)
    """
    class_name = Path(file_path).stem  # filename without .java
    package = ""
    try:
        with open(file_path, encoding="utf-8", errors="replace") as fh:
            # Read at most the first 50 lines; avoid fh.tell() which is
            # incompatible with the line-iteration protocol on Python 3.
            for _lineno, line in enumerate(fh):
                if _lineno >= 50:
                    break
                stripped = line.strip()
                if not stripped.startswith("package "):
                    continue
                # Extract the package name up to the first semicolon.
                # This handles both "package p;" alone and
                # "package p; public class Foo {}" on one line.
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
    """
    Build:
      simple_name_map: simple_name → list[qualified_name]
                       (list because two files can share a simple name)
      qualified_name_set: all qualified names in the corpus
      file_to_qname: file_path → qualified_name
    """
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


# ---------------------------------------------------------------------------
# Phase 2: import map + use-relation extraction
# ---------------------------------------------------------------------------

def _build_import_map(
    imports: list,
    package: str,
    simple_name_map: dict[str, list[str]],
    qualified_name_set: set[str],
) -> dict[str, str]:
    """
    Map simple name → qualified name for this file's imports.

    Single-type imports (import org.foo.Bar) are unambiguous.
    Star imports (import org.foo.*) are resolved lazily at lookup time
    via the returned map: we store the package prefix so that the
    resolver can check whether a name comes from that package.

    Returns a flat dict: simple_name → qualified_name (only for
    single-type imports that resolve to corpus members).
    Star imports are handled at resolution time.
    """
    local_map: dict[str, str] = {}
    for imp in imports or []:
        if imp.wildcard:
            continue  # handled in resolver
        qname = imp.path  # e.g. "org.foo.Bar"
        simple = qname.rsplit(".", 1)[-1]
        if qname in qualified_name_set:
            local_map[simple] = qname
    return local_map


def _resolve(
    raw_name: str,
    local_import_map: dict[str, str],
    star_import_packages: list[str],
    package: str,
    simple_name_map: dict[str, list[str]],
    qualified_name_set: set[str],
) -> str | None:
    """
    Attempt to resolve a raw (possibly simple) type name to its
    fully-qualified corpus name.  Returns None if unresolvable.

    Resolution order (per plan):
    1. local_import_map  (single-type imports)
    2. Same package      (files in the same package as the current file)
    3. Star imports      (only if exactly one corpus match)
    4. simple_name_map   (corpus-wide fallback, only if unambiguous)
    """
    # Strip generic suffix: "List<String>" → "List"
    base = raw_name.split("<")[0].split("[")[0].strip()
    if not base:
        return None

    # Already fully qualified and in corpus?
    if base in qualified_name_set:
        return base

    # 1. Single-type import map
    if base in local_import_map:
        return local_import_map[base]

    # 2. Same package
    same_pkg = f"{package}.{base}" if package else base
    if same_pkg in qualified_name_set:
        return same_pkg

    # 3. Star imports: check if exactly one corpus name matches
    star_candidates = [
        f"{pkg}.{base}" for pkg in star_import_packages
        if f"{pkg}.{base}" in qualified_name_set
    ]
    if len(star_candidates) == 1:
        return star_candidates[0]

    # 4. Corpus-wide fallback (unambiguous only)
    candidates = simple_name_map.get(base, [])
    if len(candidates) == 1:
        return candidates[0]

    return None  # unresolvable or ambiguous


def _extract_type_name(type_node) -> str | None:
    """Safely pull .name from a type node (handles None and missing attr)."""
    if type_node is None:
        return None
    return getattr(type_node, "name", None)


def _collect_uses(
    tree: jt.CompilationUnit,
    top_class: jt.ClassDeclaration,
    local_import_map: dict[str, str],
    star_import_packages: list[str],
    package: str,
    simple_name_map: dict[str, list[str]],
    qualified_name_set: set[str],
    self_qname: str,
) -> set[str]:
    """Walk the top-level class and collect all resolvable use relations."""
    uses: set[str] = set()

    def add(raw: str | None) -> None:
        if not raw:
            return
        resolved = _resolve(
            raw, local_import_map, star_import_packages,
            package, simple_name_map, qualified_name_set,
        )
        if resolved and resolved != self_qname:
            uses.add(resolved)

    # 1. extends
    if top_class.extends:
        add(top_class.extends.name)
        # Generic arguments of the supertype
        for arg in (getattr(top_class.extends, "arguments", None) or []):
            add(_extract_type_name(getattr(arg, "type", None)))

    # 2. implements
    for iface in (top_class.implements or []):
        add(iface.name)
        for arg in (getattr(iface, "arguments", None) or []):
            add(_extract_type_name(getattr(arg, "type", None)))

    # 3. Field declarations
    for _, field in tree.filter(jt.FieldDeclaration):
        add(_extract_type_name(field.type))
        for arg in (getattr(field.type, "arguments", None) or []):
            add(_extract_type_name(getattr(arg, "type", None)))

    # 4. Method return types and parameter types
    for _, method in tree.filter(jt.MethodDeclaration):
        add(_extract_type_name(method.return_type))
        for param in (method.parameters or []):
            add(_extract_type_name(param.type))
            for arg in (getattr(param.type, "arguments", None) or []):
                add(_extract_type_name(getattr(arg, "type", None)))

    # 5. Constructor parameter types
    for _, ctor in tree.filter(jt.ConstructorDeclaration):
        for param in (ctor.parameters or []):
            add(_extract_type_name(param.type))

    # 6. Object creation (new Foo(...))
    for _, creator in tree.filter(jt.ClassCreator):
        add(_extract_type_name(creator.type))

    # 7. Method invocation qualifiers (best-effort; many will be variable
    #    names and fail resolution silently)
    for _, inv in tree.filter(jt.MethodInvocation):
        if inv.qualifier:
            add(inv.qualifier)

    # 8. Local variable declarations
    for _, var_decl in tree.filter(jt.LocalVariableDeclaration):
        add(_extract_type_name(var_decl.type))
        for arg in (getattr(var_decl.type, "arguments", None) or []):
            add(_extract_type_name(getattr(arg, "type", None)))

    return uses - {None}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_corpus(corpus_dir: str, verbose: bool = False) -> list[Component]:
    """
    Parse all .java files under corpus_dir and return a list of Component
    objects with their use relations fully resolved.

    Files that fail to parse (javalang.parser.JavaSyntaxError or any
    unexpected exception) are logged and skipped.
    """
    java_files = list(_iter_java_files(corpus_dir))
    if verbose:
        log.info("Found %d .java files", len(java_files))

    # Phase 1: corpus name map
    simple_name_map, qualified_name_set, file_to_qname = _build_name_map(java_files)
    if verbose:
        log.info("Corpus contains %d distinct qualified names", len(qualified_name_set))

    # Phase 2: full parse
    components: list[Component] = []
    skipped = 0

    for fp in java_files:
        self_qname = file_to_qname.get(fp)
        if self_qname is None:
            skipped += 1
            continue  # Phase 1 extraction failed for this file

        try:
            with open(fp, encoding="utf-8", errors="replace") as fh:
                source = fh.read()
        except OSError as exc:
            log.warning("Cannot read %s: %s", fp, exc)
            skipped += 1
            continue

        try:
            tree = javalang.parse.parse(source)
        except Exception as exc:
            log.debug("Skipping %s (parse error: %s)", fp, exc)
            skipped += 1
            continue

        # We only consider the first top-level type declaration.
        # Files with no class declaration (interface-only, enum-only, etc.)
        # are still included — they count as components.
        if not tree.types:
            skipped += 1
            continue

        top_type = tree.types[0]
        # Exclude annotation type declarations (rare in application code)
        if isinstance(top_type, jt.AnnotationDeclaration):
            skipped += 1
            continue

        package = tree.package.name if tree.package else ""
        source_lines = source.splitlines(keepends=True)

        # Build per-file import resolution data
        local_import_map = _build_import_map(
            tree.imports, package, simple_name_map, qualified_name_set
        )
        star_import_packages = [
            imp.path.rstrip(".*")
            for imp in (tree.imports or [])
            if imp.wildcard
        ]

        # Collect use relations
        if isinstance(top_type, jt.ClassDeclaration):
            uses = _collect_uses(
                tree, top_type, local_import_map, star_import_packages,
                package, simple_name_map, qualified_name_set, self_qname,
            )
        else:
            # Interface / enum declarations: only extract extends/implements
            uses: set[str] = set()
            for base in (getattr(top_type, "extends", None) or []):
                name = getattr(base, "name", None)
                if name:
                    resolved = _resolve(
                        name, local_import_map, star_import_packages,
                        package, simple_name_map, qualified_name_set,
                    )
                    if resolved and resolved != self_qname:
                        uses.add(resolved)

        components.append(Component(
            qualified_name=self_qname,
            simple_name=top_type.name,
            file_path=fp,
            source_lines=source_lines,
            uses=uses,
        ))

    if verbose:
        log.info(
            "Parsed %d components; skipped %d files", len(components), skipped
        )
    return components

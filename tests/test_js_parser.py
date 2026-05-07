"""tests/test_js_parser.py
Unit tests for JavaScriptParser, mirroring the structure of test_python_parser.py.
"""

import os
import sys
import tempfile
import textwrap

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from parsing.js_parser import JavaScriptParser


def _write(directory: str, filename: str, source: str) -> str:
    path = os.path.join(directory, filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(textwrap.dedent(source))
    return path


def _parser():
    return JavaScriptParser()


# ── Qualified-name derivation ──────────────────────────────────────────────────

class TestQualifiedNames:
    def test_ts_file_qname(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "helper.ts", "export const x = 1;\n")
            comps = _parser().parse_corpus(d)
        assert len(comps) == 1
        assert comps[0].qualified_name == "helper"
        assert comps[0].simple_name == "helper"

    def test_nested_ts_file_qname(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, os.path.join("utils", "helper.ts"), "export const x = 1;\n")
            comps = _parser().parse_corpus(d)
        assert comps[0].qualified_name == "utils.helper"

    def test_js_file_qname(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "app.js", "const x = 1;\n")
            comps = _parser().parse_corpus(d)
        assert comps[0].qualified_name == "app"

    def test_tsx_file_qname(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, os.path.join("components", "Button.tsx"), "export default () => null;\n")
            comps = _parser().parse_corpus(d)
        assert comps[0].qualified_name == "components.Button"

    def test_index_ts_maps_to_directory(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, os.path.join("utils", "index.ts"), "export const x = 1;\n")
            comps = _parser().parse_corpus(d)
        assert comps[0].qualified_name == "utils"

    def test_index_js_maps_to_directory(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, os.path.join("lib", "index.js"), "module.exports = {};\n")
            comps = _parser().parse_corpus(d)
        assert comps[0].qualified_name == "lib"

    def test_source_lines_populated(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "x.ts", "const a = 1;\nconst b = 2;\n")
            comps = _parser().parse_corpus(d)
        assert len(comps[0].source_lines) > 0

    def test_root_index_js_gets_qname_index(self):
        """Root-level index.js is kept as "index", not skipped."""
        with tempfile.TemporaryDirectory() as d:
            _write(d, "index.js", "export const x = 1;\n")
            comps = _parser().parse_corpus(d)
        assert len(comps) == 1
        assert comps[0].qualified_name == "index"

    def test_root_index_import_relation_captured(self):
        """index.js at corpus root imports utilities.js — edge must be captured."""
        with tempfile.TemporaryDirectory() as d:
            _write(d, "utilities.js", "export const x = 1;\n")
            _write(d, "index.js", "import { x } from './utilities.js';\n")
            comps = _parser().parse_corpus(d)
        idx = next(c for c in comps if c.simple_name == "index")
        assert "utilities" in idx.uses


# ── File filtering ─────────────────────────────────────────────────────────────

class TestFileFiltering:
    def test_dts_file_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "types.d.ts", "export type Foo = string;\n")
            _write(d, "real.ts", "const x = 1;\n")
            comps = _parser().parse_corpus(d)
        names = [c.simple_name for c in comps]
        assert "real" in names
        assert "types" not in names

    def test_node_modules_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            nm = os.path.join(d, "node_modules", "react")
            os.makedirs(nm)
            _write(d, os.path.join("node_modules", "react", "index.js"), "module.exports = {};\n")
            _write(d, "app.ts", "const x = 1;\n")
            comps = _parser().parse_corpus(d)
        names = [c.simple_name for c in comps]
        assert "app" in names
        assert "react" not in names

    def test_dist_dir_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, os.path.join("dist", "bundle.js"), "var x = 1;\n")
            _write(d, "src.ts", "const x = 1;\n")
            comps = _parser().parse_corpus(d)
        names = [c.simple_name for c in comps]
        assert "src" in names
        assert "bundle" not in names


# ── Use-relation extraction: module specifiers ────────────────────────────────

class TestImportRelations:
    def test_es6_default_import(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "helper.ts", "export const x = 1;\n")
            _write(d, "main.ts", "import helper from './helper';\n")
            comps = _parser().parse_corpus(d)
        main = next(c for c in comps if c.simple_name == "main")
        assert "helper" in main.uses

    def test_es6_named_import(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "utils.ts", "export const x = 1;\n")
            _write(d, "app.ts", "import { x } from './utils';\n")
            comps = _parser().parse_corpus(d)
        app = next(c for c in comps if c.simple_name == "app")
        assert "utils" in app.uses

    def test_es6_namespace_import(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "math.ts", "export const PI = 3.14;\n")
            _write(d, "calc.ts", "import * as M from './math';\n")
            comps = _parser().parse_corpus(d)
        calc = next(c for c in comps if c.simple_name == "calc")
        assert "math" in calc.uses

    def test_export_from(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "base.ts", "export class Base {}\n")
            _write(d, "re_export.ts", "export { Base } from './base';\n")
            comps = _parser().parse_corpus(d)
        re_exp = next(c for c in comps if c.simple_name == "re_export")
        assert "base" in re_exp.uses

    def test_export_star_from(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "types.ts", "export type Foo = string;\n")
            _write(d, "barrel.ts", "export * from './types';\n")
            comps = _parser().parse_corpus(d)
        barrel = next(c for c in comps if c.simple_name == "barrel")
        assert "types" in barrel.uses

    def test_require_relation(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "config.js", "module.exports = {};\n")
            _write(d, "server.js", "const cfg = require('./config');\n")
            comps = _parser().parse_corpus(d)
        srv = next(c for c in comps if c.simple_name == "server")
        assert "config" in srv.uses

    def test_dynamic_import_relation(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "heavy.ts", "export const x = 1;\n")
            _write(d, "loader.ts", "const m = await import('./heavy');\n")
            comps = _parser().parse_corpus(d)
        loader = next(c for c in comps if c.simple_name == "loader")
        assert "heavy" in loader.uses

    def test_import_resolves_index_directory(self):
        """import './utils' should resolve to utils/index.ts"""
        with tempfile.TemporaryDirectory() as d:
            _write(d, os.path.join("utils", "index.ts"), "export const x = 1;\n")
            _write(d, "app.ts", "import './utils';\n")
            comps = _parser().parse_corpus(d)
        app = next(c for c in comps if c.simple_name == "app")
        assert "utils" in app.uses

    def test_external_npm_package_dropped(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "app.ts", "import React from 'react';\nimport { useState } from 'react';\n")
            comps = _parser().parse_corpus(d)
        assert len(comps[0].uses) == 0

    def test_node_builtin_dropped(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "app.js", "const fs = require('fs');\nconst path = require('path');\n")
            comps = _parser().parse_corpus(d)
        assert len(comps[0].uses) == 0


# ── Use-relation extraction: class inheritance ────────────────────────────────

class TestInheritanceRelations:
    def test_extends_relation(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "base.ts", "export class Base {}\n")
            _write(d, "child.ts", textwrap.dedent("""\
                import { Base } from './base';
                class Child extends Base {}
            """))
            comps = _parser().parse_corpus(d)
        child = next(c for c in comps if c.simple_name == "child")
        assert "base" in child.uses

    def test_implements_relation(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "iface.ts", "export interface IFoo { bar(): void; }\n")
            _write(d, "impl.ts", textwrap.dedent("""\
                import { IFoo } from './iface';
                class Impl implements IFoo { bar() {} }
            """))
            comps = _parser().parse_corpus(d)
        impl = next(c for c in comps if c.simple_name == "impl")
        assert "iface" in impl.uses

    def test_implements_multiple(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "ia.ts", "export interface IA {}\n")
            _write(d, "ib.ts", "export interface IB {}\n")
            _write(d, "cls.ts", textwrap.dedent("""\
                import { IA } from './ia';
                import { IB } from './ib';
                class Cls implements IA, IB {}
            """))
            comps = _parser().parse_corpus(d)
        cls = next(c for c in comps if c.simple_name == "cls")
        assert "ia" in cls.uses
        assert "ib" in cls.uses


# ── Self-reference / mutual reference ────────────────────────────────────────

class TestSelfAndMutual:
    def test_self_reference_excluded(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "a.ts", "import './a';\n")
            comps = _parser().parse_corpus(d)
        assert "a" not in comps[0].uses

    def test_mutual_reference(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "a.ts", "import './b';\n")
            _write(d, "b.ts", "import './a';\n")
            comps = _parser().parse_corpus(d)
        a = next(c for c in comps if c.simple_name == "a")
        b = next(c for c in comps if c.simple_name == "b")
        assert "b" in a.uses
        assert "a" in b.uses

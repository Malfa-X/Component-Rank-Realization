"""tests/test_python_parser.py
Unit tests for PythonAstParser, mirroring the structure of test_parser.py.
"""

import sys, os, tempfile, textwrap
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from parsing.python_parser import PythonAstParser


def _write_py(directory: str, filename: str, source: str) -> str:
    path = os.path.join(directory, filename)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(textwrap.dedent(source))
    return path


def _parser():
    return PythonAstParser()


# ── Basic parsing ─────────────────────────────────────────────────────────────

class TestPythonParser:
    def test_simple_module_parsed(self):
        with tempfile.TemporaryDirectory() as d:
            _write_py(d, "foo.py", "x = 1\n")
            comps = _parser().parse_corpus(d)
        assert len(comps) == 1
        assert comps[0].qualified_name == "foo"
        assert comps[0].simple_name == "foo"

    def test_nested_module_qualified_name(self):
        with tempfile.TemporaryDirectory() as d:
            pkg = os.path.join(d, "utils")
            os.makedirs(pkg)
            _write_py(pkg, "helper.py", "x = 1\n")
            comps = _parser().parse_corpus(d)
        assert len(comps) == 1
        assert comps[0].qualified_name == "utils.helper"

    def test_init_maps_to_package_name(self):
        with tempfile.TemporaryDirectory() as d:
            pkg = os.path.join(d, "utils")
            os.makedirs(pkg)
            _write_py(pkg, "__init__.py", "x = 1\n")
            comps = _parser().parse_corpus(d)
        assert len(comps) == 1
        assert comps[0].qualified_name == "utils"

    # ── Use-relation extraction ───────────────────────────────────────────────

    def test_import_relation(self):
        with tempfile.TemporaryDirectory() as d:
            _write_py(d, "helper.py", "x = 1\n")
            _write_py(d, "main.py", "import helper\n")
            comps = _parser().parse_corpus(d)
        main = next(c for c in comps if c.simple_name == "main")
        assert "helper" in main.uses

    def test_from_import_relation(self):
        with tempfile.TemporaryDirectory() as d:
            pkg = os.path.join(d, "utils")
            os.makedirs(pkg)
            _write_py(pkg, "helper.py", "x = 1\n")
            _write_py(d, "main.py", "from utils import helper\n")
            comps = _parser().parse_corpus(d)
        main = next(c for c in comps if c.simple_name == "main")
        assert "utils.helper" in main.uses

    def test_class_inheritance_relation(self):
        with tempfile.TemporaryDirectory() as d:
            _write_py(d, "base.py", "class Base: pass\n")
            _write_py(d, "child.py", textwrap.dedent("""\
                import base
                class Child(base.Base): pass
            """))
            comps = _parser().parse_corpus(d)
        child = next(c for c in comps if c.simple_name == "child")
        assert "base" in child.uses

    def test_type_annotation_relation(self):
        with tempfile.TemporaryDirectory() as d:
            _write_py(d, "models.py", "class User: pass\n")
            _write_py(d, "service.py", textwrap.dedent("""\
                from models import User
                def get_user() -> User: ...
            """))
            comps = _parser().parse_corpus(d)
        svc = next(c for c in comps if c.simple_name == "service")
        assert "models" in svc.uses

    def test_external_references_dropped(self):
        # os, sys, etc. are not in the corpus → should not appear in uses
        with tempfile.TemporaryDirectory() as d:
            _write_py(d, "foo.py", "import os\nimport sys\n")
            comps = _parser().parse_corpus(d)
        assert len(comps[0].uses) == 0

    def test_self_reference_excluded(self):
        with tempfile.TemporaryDirectory() as d:
            _write_py(d, "a.py", textwrap.dedent("""\
                import a   # self-import
            """))
            comps = _parser().parse_corpus(d)
        assert "a" not in comps[0].uses

    def test_unparseable_file_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            _write_py(d, "good.py", "x = 1\n")
            _write_py(d, "bad.py", "def ((((\n")   # SyntaxError
            comps = _parser().parse_corpus(d)
        assert len(comps) == 1
        assert comps[0].simple_name == "good"

    def test_source_lines_populated(self):
        with tempfile.TemporaryDirectory() as d:
            _write_py(d, "x.py", "a = 1\nb = 2\n")
            comps = _parser().parse_corpus(d)
        assert len(comps[0].source_lines) > 0

    def test_two_modules_use_each_other(self):
        with tempfile.TemporaryDirectory() as d:
            _write_py(d, "a.py", "import b\n")
            _write_py(d, "b.py", "import a\n")
            comps = _parser().parse_corpus(d)
        a = next(c for c in comps if c.simple_name == "a")
        b = next(c for c in comps if c.simple_name == "b")
        assert "b" in a.uses
        assert "a" in b.uses

    def test_pycache_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            cache = os.path.join(d, "__pycache__")
            os.makedirs(cache)
            _write_py(cache, "cached.py", "x = 1\n")
            _write_py(d, "real.py", "x = 1\n")
            comps = _parser().parse_corpus(d)
        names = [c.simple_name for c in comps]
        assert "real" in names
        assert "cached" not in names

    def test_generic_annotation_inner_type_captured(self):
        # Optional[models] → models should be captured as a use
        with tempfile.TemporaryDirectory() as d:
            _write_py(d, "models.py", "class User: pass\n")
            _write_py(d, "service.py", textwrap.dedent("""\
                from typing import Optional
                from models import User
                def get() -> Optional[User]: ...
            """))
            comps = _parser().parse_corpus(d)
        svc = next(c for c in comps if c.simple_name == "service")
        assert "models" in svc.uses

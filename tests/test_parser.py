"""tests/test_parser.py"""

import sys, os, tempfile, textwrap
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from parsing.java_parser import parse_corpus


def _write_java(directory: str, filename: str, source: str) -> str:
    path = os.path.join(directory, filename)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(textwrap.dedent(source))
    return path


# ── Basic parsing ─────────────────────────────────────────────────────────────

class TestParser:
    def test_simple_class_parsed(self):
        with tempfile.TemporaryDirectory() as d:
            _write_java(d, "Foo.java", """
                package com.example;
                public class Foo {}
            """)
            comps = parse_corpus(d)
        assert len(comps) == 1
        assert comps[0].qualified_name == "com.example.Foo"
        assert comps[0].simple_name == "Foo"

    def test_extends_relation(self):
        with tempfile.TemporaryDirectory() as d:
            _write_java(d, "Base.java", "package p; public class Base {}")
            _write_java(d, "Child.java", "package p; public class Child extends Base {}")
            comps = parse_corpus(d)
        child = next(c for c in comps if c.simple_name == "Child")
        assert "p.Base" in child.uses

    def test_implements_relation(self):
        with tempfile.TemporaryDirectory() as d:
            _write_java(d, "IFoo.java", "package p; public interface IFoo {}")
            _write_java(d, "Bar.java",  "package p; public class Bar implements IFoo {}")
            comps = parse_corpus(d)
        bar = next(c for c in comps if c.simple_name == "Bar")
        assert "p.IFoo" in bar.uses

    def test_external_references_dropped(self):
        # java.util.List is not in corpus → should not appear in uses
        with tempfile.TemporaryDirectory() as d:
            _write_java(d, "MyClass.java", """
                package p;
                import java.util.List;
                public class MyClass {
                    private List<String> items;
                }
            """)
            comps = parse_corpus(d)
        assert len(comps[0].uses) == 0

    def test_module_info_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            _write_java(d, "module-info.java", "module com.example {}")
            _write_java(d, "Foo.java", "package p; public class Foo {}")
            comps = parse_corpus(d)
        assert len(comps) == 1
        assert comps[0].simple_name == "Foo"

    def test_unparseable_file_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            _write_java(d, "Good.java", "package p; public class Good {}")
            _write_java(d, "Bad.java",  "this is not java @@@@")
            comps = parse_corpus(d)
        assert len(comps) == 1
        assert comps[0].simple_name == "Good"

    def test_self_reference_excluded(self):
        with tempfile.TemporaryDirectory() as d:
            _write_java(d, "A.java", """
                package p;
                public class A {
                    private A other;   // self-reference
                }
            """)
            comps = parse_corpus(d)
        assert "p.A" not in comps[0].uses

    def test_source_lines_populated(self):
        with tempfile.TemporaryDirectory() as d:
            _write_java(d, "X.java", "package p;\npublic class X {}\n")
            comps = parse_corpus(d)
        assert len(comps[0].source_lines) > 0

    def test_two_corpus_members_use_each_other(self):
        with tempfile.TemporaryDirectory() as d:
            _write_java(d, "A.java", """
                package p;
                public class A extends B {}
            """)
            _write_java(d, "B.java", """
                package p;
                public class B {
                    private A ref;
                }
            """)
            comps = parse_corpus(d)
        a = next(c for c in comps if c.simple_name == "A")
        b = next(c for c in comps if c.simple_name == "B")
        assert "p.B" in a.uses
        assert "p.A" in b.uses

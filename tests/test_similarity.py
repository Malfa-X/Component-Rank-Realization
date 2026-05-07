"""tests/test_similarity.py"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from parsing.use_relation import Component
from similarity.diff_based import DiffBasedSimilarity
from similarity.token_based import TokenBasedSimilarity
from similarity.factory import get_similarity_method


def _make_comp(lines: list[str], name: str = "com.example.A") -> Component:
    return Component(
        qualified_name=name,
        simple_name=name.split(".")[-1],
        file_path=f"/fake/{name}.java",
        source_lines=lines,
    )


# ── DiffBasedSimilarity ──────────────────────────────────────────────────────

class TestDiffBasedSimilarity:
    def setup_method(self):
        self.method = DiffBasedSimilarity()

    def test_identical_files_score_one(self):
        lines = ["public class A {}\n", "  int x;\n"]
        a = _make_comp(lines, "A")
        b = _make_comp(lines, "B")
        assert self.method.compute(a, b) == pytest.approx(1.0)

    def test_empty_both_score_one(self):
        a = _make_comp([], "A")
        b = _make_comp([], "B")
        assert self.method.compute(a, b) == pytest.approx(1.0)

    def test_one_empty_score_zero(self):
        a = _make_comp(["line\n"], "A")
        b = _make_comp([], "B")
        assert self.method.compute(a, b) == pytest.approx(0.0)

    def test_completely_different_low_score(self):
        a = _make_comp(["aaa\n", "bbb\n", "ccc\n"], "A")
        b = _make_comp(["xxx\n", "yyy\n", "zzz\n"], "B")
        assert self.method.compute(a, b) == pytest.approx(0.0)

    def test_size_ratio_shortcircuit(self):
        a = _make_comp(["line\n"] * 100, "A")
        b = _make_comp(["line\n"] * 5, "B")
        # ratio = 100/5 = 20 > SIZE_RATIO_CUTOFF (10)
        assert self.method.compute(a, b) == pytest.approx(0.0)

    def test_symmetry(self):
        a = _make_comp(["x\n", "y\n"], "A")
        b = _make_comp(["y\n", "z\n"], "B")
        assert self.method.compute(a, b) == pytest.approx(self.method.compute(b, a))

    def test_partial_overlap(self):
        # 2 lines shared out of union 4 → Jaccard = 2/4 = 0.5
        a = _make_comp(["line1\n", "line2\n"], "A")
        b = _make_comp(["line2\n", "line3\n"], "B")
        score = self.method.compute(a, b)
        assert 0.0 < score < 1.0


# ── TokenBasedSimilarity ─────────────────────────────────────────────────────

class TestTokenBasedSimilarity:
    def setup_method(self):
        self.method = TokenBasedSimilarity()

    def test_identical_source_score_one(self):
        src = ["public class Foo { int x = 1; }\n"]
        a = _make_comp(src, "A")
        b = _make_comp(src, "B")
        assert self.method.compute(a, b) == pytest.approx(1.0)

    def test_empty_both_score_one(self):
        a = _make_comp([], "A")
        b = _make_comp([], "B")
        assert self.method.compute(a, b) == pytest.approx(1.0)

    def test_one_empty_score_zero(self):
        a = _make_comp(["public class Foo {}\n"], "A")
        b = _make_comp([], "B")
        assert self.method.compute(a, b) == pytest.approx(0.0)

    def test_symmetry(self):
        a = _make_comp(["class A { int x; }\n"], "A")
        b = _make_comp(["class B { int y; }\n"], "B")
        assert self.method.compute(a, b) == pytest.approx(self.method.compute(b, a))

    def test_formatting_insensitive(self):
        # Same tokens, different whitespace → should score near 1.0
        a = _make_comp(["class A{int x;}\n"], "A")
        b = _make_comp(["class A {\n", "    int x;\n", "}\n"], "B")
        score = self.method.compute(a, b)
        assert score > 0.8

    def test_size_ratio_shortcircuit(self):
        a = _make_comp(["class A { int x; }\n"] * 100, "A")
        b = _make_comp(["class A { int x; }\n"] * 4, "B")
        # len_a >> len_b → short-circuit
        assert self.method.compute(a, b) == pytest.approx(0.0)


# ── Factory ──────────────────────────────────────────────────────────────────

class TestFactory:
    def test_returns_diff(self):
        m = get_similarity_method("diff")
        assert isinstance(m, DiffBasedSimilarity)

    def test_returns_token(self):
        m = get_similarity_method("token")
        assert isinstance(m, TokenBasedSimilarity)

    def test_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown similarity method"):
            get_similarity_method("bogus")

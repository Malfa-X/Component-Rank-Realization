"""
parsing/parser_factory.py
Selects the correct LanguageParser implementation given a language name
and optional parser-engine name.

Supported combinations
----------------------
  language="java",   parser_name="javalang"   (default for Java)
      → parsing.java_parser          — javalang 0.13.0, Java 8 syntax
  language="java",   parser_name="treesitter"
      → parsing.treesitter_java_parser — tree-sitter-java, Java 8–21
  language="python", parser_name="ast"        (default for Python)
      → parsing.python_parser        — built-in ast module
  language="python", parser_name="treesitter"
      → parsing.python_treesitter_parser — tree-sitter-python
  language="javascript", parser_name="regex" (default)
      → parsing.js_parser — regex-based, no extra deps, JS 8–21 / TS

Adding a new language
---------------------
1. Create a parsing/<lang>_parser.py that subclasses LanguageParser.
2. Register it in _REGISTRY below.
3. Add a default entry in _DEFAULTS.
"""

from __future__ import annotations

from parsing.base_parser import LanguageParser

# ─── Supported languages and their default parser engines ───────────────────

SUPPORTED_LANGUAGES: list[str] = ["java", "python", "javascript"]

_DEFAULTS: dict[str, str] = {
    "java":       "javalang",
    "python":     "ast",
    "javascript": "regex",
}

# ─── Lazy-loader callables (avoid importing heavy deps at import time) ───────

def _load_javalang_java() -> LanguageParser:
    from parsing.java_parser import parse_corpus

    class _JavalangJavaParser(LanguageParser):
        def parse_corpus(self, corpus_dir: str, verbose: bool = False):
            return parse_corpus(corpus_dir, verbose=verbose)

    return _JavalangJavaParser()


def _load_treesitter_java() -> LanguageParser:
    from parsing.treesitter_java_parser import TreeSitterJavaParser
    return TreeSitterJavaParser()


def _load_python_ast() -> LanguageParser:
    from parsing.python_parser import PythonAstParser
    return PythonAstParser()


def _load_python_treesitter() -> LanguageParser:
    from parsing.python_treesitter_parser import PythonTreeSitterParser
    return PythonTreeSitterParser()


def _load_javascript_regex() -> LanguageParser:
    from parsing.js_parser import JavaScriptParser
    return JavaScriptParser()


_REGISTRY: dict[tuple[str, str], object] = {
    ("java",       "javalang"):   _load_javalang_java,
    ("java",       "treesitter"): _load_treesitter_java,
    ("python",     "ast"):        _load_python_ast,
    ("python",     "treesitter"): _load_python_treesitter,
    ("javascript", "regex"):      _load_javascript_regex,
}

# ─── Public API ─────────────────────────────────────────────────────────────

def get_parser(
    language: str, parser_name: str | None = None
) -> LanguageParser:
    """
    Instantiate and return the appropriate LanguageParser.

    Parameters
    ----------
    language:
        Target language.  Supported values: "java", "python".
    parser_name:
        Parser engine.  When None the default for the language is used.
        Valid values per language:
          java   → "javalang" (default), "treesitter"
          python → "ast" (default), "treesitter"

    Raises
    ------
    ValueError
        If the language or (language, parser_name) combination is unknown.
    """
    language = language.lower()
    if language not in SUPPORTED_LANGUAGES:
        raise ValueError(
            f"Unknown language '{language}'. "
            f"Supported: {', '.join(SUPPORTED_LANGUAGES)}"
        )

    name = (parser_name or _DEFAULTS[language]).lower()
    key = (language, name)

    if key not in _REGISTRY:
        valid = [k[1] for k in _REGISTRY if k[0] == language]
        raise ValueError(
            f"Unknown parser '{name}' for language '{language}'. "
            f"Valid choices: {', '.join(valid)}"
        )

    loader = _REGISTRY[key]
    return loader()  # type: ignore[operator]


def list_parsers() -> dict[str, list[str]]:
    """Return a dict mapping each language to its available parser names."""
    result: dict[str, list[str]] = {lang: [] for lang in SUPPORTED_LANGUAGES}
    for lang, name in _REGISTRY:
        result[lang].append(name)
    return result

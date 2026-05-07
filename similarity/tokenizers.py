"""
similarity/tokenizers.py
Language-specific source tokenizers for token-based similarity.

Each tokenizer takes a list[str] of source lines and returns a list[str]
of meaningful token values, with whitespace, comments, and structural
noise stripped.  The resulting token sequence is used by
TokenBasedSimilarity to compute the LCS-based Jaccard similarity.

Tokenizers
----------
java_tokenize   — uses javalang.tokenizer (Java 8 lexer).  This is the
                  original tokenizer from token_based.py, moved here so it
                  can be shared.

python_tokenize — uses the built-in tokenize module.  Keeps NAME, OP,
                  NUMBER, STRING, and OP tokens; discards COMMENT, NL,
                  NEWLINE, INDENT, DEDENT, ENCODING, and ENDMARKER.

get_tokenizer   — factory function: returns the tokenizer for a given
                  language string.  Falls back to java_tokenize for
                  unknown languages to preserve backwards compatibility.
"""

from __future__ import annotations

import io
import tokenize as _py_tokenize
from typing import Callable


# ─── Java tokenizer ───────────────────────────────────────────────────────────

def java_tokenize(source_lines: list[str]) -> list[str]:
    """
    Tokenize Java source using javalang's lexer.

    Whitespace, comments, and the EndOfInput sentinel are excluded.
    Returns an empty list on any LexerError (partial tokenization is
    not attempted — the LCS will treat such a file as empty).
    """
    import javalang.tokenizer as jt   # local import: javalang is optional

    source = "".join(source_lines)
    tokens: list[str] = []
    try:
        for tok in jt.tokenize(source):
            if isinstance(
                tok,
                (
                    jt.Separator, jt.Operator,
                    jt.BasicType, jt.Modifier,
                    jt.Keyword, jt.Identifier,
                    jt.Integer, jt.DecimalInteger,
                    jt.OctalInteger, jt.BinaryInteger,
                    jt.HexInteger, jt.FloatingPoint,
                    jt.DecimalFloatingPoint, jt.HexFloatingPoint,
                    jt.Boolean, jt.Character,
                    jt.String, jt.Null,
                ),
            ):
                tokens.append(tok.value)
    except jt.LexerError:
        pass
    return tokens


# ─── Python tokenizer ─────────────────────────────────────────────────────────

# Token types to discard (noise / formatting)
_PY_SKIP = frozenset({
    _py_tokenize.COMMENT,
    _py_tokenize.NL,
    _py_tokenize.NEWLINE,
    _py_tokenize.INDENT,
    _py_tokenize.DEDENT,
    _py_tokenize.ENCODING,
    _py_tokenize.ENDMARKER,
    _py_tokenize.ERRORTOKEN,
})


def python_tokenize(source_lines: list[str]) -> list[str]:
    """
    Tokenize Python source using the built-in tokenize module.

    Keeps NAME, NUMBER, STRING, and OP tokens; discards comments,
    whitespace, indentation markers, and encoding/EOF sentinels.
    Returns whatever was collected before a TokenError (e.g. from an
    incomplete file).
    """
    source = "".join(source_lines)
    tokens: list[str] = []
    try:
        reader = io.StringIO(source).readline
        for tok in _py_tokenize.generate_tokens(reader):
            if tok.type not in _PY_SKIP:
                tokens.append(tok.string)
    except _py_tokenize.TokenError:
        pass  # return partial result
    return tokens


# ─── JavaScript / TypeScript tokenizer ───────────────────────────────────────

import re as _re

_JS_TOKEN_RE = _re.compile(
    r"`(?:[^`\\]|\\.)*`"               # template literal
    r"|'(?:[^'\\]|\\.)*'"              # single-quoted string
    r'|"(?:[^"\\]|\\.)*"'              # double-quoted string
    r"|//[^\n]*"                        # single-line comment (will be skipped)
    r"|/\*[\s\S]*?\*/"                 # multi-line comment (will be skipped)
    r"|[a-zA-Z_$][a-zA-Z0-9_$]*"      # identifier / keyword
    r"|[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?n?"  # number
    r"|[^\s\w'\"` ]",                  # operators / punctuation
    _re.DOTALL,
)


def js_tokenize(source_lines: list[str]) -> list[str]:
    """
    Tokenize JavaScript / TypeScript source using regular expressions.

    Keeps identifiers, keywords, numbers, strings / template literals, and
    operators; discards single-line (//) and multi-line (/* */) comments.
    Returns whatever tokens were collected even if the source has syntax errors.
    """
    source = "".join(source_lines)
    tokens: list[str] = []
    for m in _JS_TOKEN_RE.finditer(source):
        v = m.group()
        if v.startswith("//") or v.startswith("/*"):
            continue
        tokens.append(v)
    return tokens


# ─── Factory ──────────────────────────────────────────────────────────────────

_TOKENIZERS: dict[str, Callable[[list[str]], list[str]]] = {
    "java":       java_tokenize,
    "python":     python_tokenize,
    "javascript": js_tokenize,
}


def get_tokenizer(language: str) -> Callable[[list[str]], list[str]]:
    """
    Return the tokenizer function for the given language.

    Falls back to java_tokenize for unrecognised language strings to
    preserve backwards compatibility with callers that don't pass a
    language argument.
    """
    return _TOKENIZERS.get(language.lower(), java_tokenize)

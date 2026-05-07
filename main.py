"""
main.py — Component Rank CLI entry point.

Usage
-----
python main.py <corpus_dir> [options]

Example
-------
python main.py /path/to/commons-lang/src/main/java \\
    --similarity diff --top 20 --output-format table
"""

from __future__ import annotations
import argparse
import sys
import os

# Ensure the package root is on sys.path when run as a script
sys.path.insert(0, os.path.dirname(__file__))

from config import (
    DEFAULT_DAMPING, DEFAULT_EPSILON, DEFAULT_MAX_ITER, DEFAULT_THRESHOLD,
)
from pipeline.runner import run_pipeline
from output.formatter import format_output
from similarity.factory import available_methods
from parsing.parser_factory import SUPPORTED_LANGUAGES


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="component-rank",
        description=(
            "Rank software components by reuse significance "
            "(Inoue et al., 2003 — Component Rank). "
            "Supports Java and Python source trees."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "corpus_dir",
        help="Directory containing source files (searched recursively).",
    )
    parser.add_argument(
        "--language", "-l",
        choices=SUPPORTED_LANGUAGES,
        default="java",
        metavar="LANG",
        help=(
            "Source language to analyse. "
            f"Supported: {', '.join(SUPPORTED_LANGUAGES)}. "
            "Default: java."
        ),
    )
    parser.add_argument(
        "--parser",
        default=None,
        metavar="ENGINE",
        help=(
            "Parser engine override (optional). "
            "java: 'javalang' (default, Java 8) or 'treesitter' (Java 8-21). "
            "python: 'ast' (default) or 'treesitter' (fault-tolerant). "
            "Omit to use the language default."
        ),
    )
    parser.add_argument(
        "--similarity", "-s",
        choices=available_methods(),
        default="diff",
        metavar="METHOD",
        help=(
            "Similarity method for clustering. "
            f"Choices: {', '.join(available_methods())}."
        ),
    )
    parser.add_argument(
        "--threshold", "-t",
        type=float,
        default=DEFAULT_THRESHOLD,
        metavar="T",
        help="Clustering threshold: pairs with similarity >= T are merged.",
    )
    parser.add_argument(
        "--damping", "-p",
        type=float,
        default=DEFAULT_DAMPING,
        metavar="P",
        help="Damping factor for pseudo use relations.",
    )
    parser.add_argument(
        "--epsilon", "-e",
        type=float,
        default=DEFAULT_EPSILON,
        metavar="EPS",
        help="Convergence criterion for power iteration (L1 norm delta).",
    )
    parser.add_argument(
        "--max-iter",
        type=int,
        default=DEFAULT_MAX_ITER,
        metavar="N",
        help="Maximum number of power-iteration steps.",
    )
    parser.add_argument(
        "--solver",
        choices=["power", "eigen"],
        default="power",
        help=(
            "'power' = iterative power method (recommended for large corpora); "
            "'eigen' = scipy direct eigenvector solver (exact, for N < 500)."
        ),
    )
    parser.add_argument(
        "--output-format", "-f",
        choices=["table", "csv", "json"],
        default="table",
        dest="output_format",
        help="Output format.",
    )
    parser.add_argument(
        "--top", "-n",
        type=int,
        default=None,
        metavar="N",
        help="Show only the top N results (default: all).",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print pipeline progress to stdout.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    # Validate corpus directory
    if not os.path.isdir(args.corpus_dir):
        parser.error(f"corpus_dir '{args.corpus_dir}' is not a directory.")

    try:
        ranked = run_pipeline(
            corpus_dir=args.corpus_dir,
            similarity_method=args.similarity,
            threshold=args.threshold,
            damping=args.damping,
            epsilon=args.epsilon,
            max_iter=args.max_iter,
            solver=args.solver,
            verbose=args.verbose,
            language=args.language,
            parser_name=args.parser,
        )
    except (RuntimeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    output = format_output(ranked, fmt=args.output_format, top=args.top)
    print(output)


if __name__ == "__main__":
    main()

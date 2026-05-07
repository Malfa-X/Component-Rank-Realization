"""
pipeline/runner.py
Orchestrates all eight steps of the Component Rank pipeline.
"""

from __future__ import annotations
import logging
import sys

import numpy as np
from tqdm import tqdm

from config import (
    DEFAULT_DAMPING, DEFAULT_EPSILON, DEFAULT_MAX_ITER,
    DEFAULT_THRESHOLD, SIZE_RATIO_CUTOFF,
)
from parsing.parser_factory import get_parser
from similarity.factory import get_similarity_method
from clustering.clusterer import cluster_components
from graph.component_graph import build_cluster_graph
from graph.matrix_builder import build_distribution_matrix
from ranking.power_iteration import power_iteration
from ranking.eigenvector import eigenvector_solver
from output.formatter import format_output, RankedEntry

log = logging.getLogger(__name__)


def _compute_similarity_matrix(components, method, threshold):
    """
    Compute the M×M symmetric similarity matrix.
    Only the upper triangle is computed; the lower is mirrored.
    """
    M = len(components)
    S = np.zeros((M, M), dtype=np.float64)
    np.fill_diagonal(S, 1.0)

    total_pairs = M * (M - 1) // 2
    with tqdm(total=total_pairs, desc="Similarity", unit="pair",
              file=sys.stdout, leave=False) as pbar:
        for i in range(M):
            for j in range(i + 1, M):
                s = method.compute(components[i], components[j])
                S[i, j] = s
                S[j, i] = s
                pbar.update(1)
    return S


def _assign_ranks(component_weights: list[tuple[str, float]]) -> list[RankedEntry]:
    """
    Given a list of (qualified_name, weight) sorted descending by weight,
    assign dense ranks: tied weights share the same rank.
    """
    ranked: list[RankedEntry] = []
    current_rank = 1
    for i, (name, weight) in enumerate(component_weights):
        if i > 0 and component_weights[i - 1][1] != weight:
            current_rank = i + 1
        ranked.append((current_rank, name, weight))
    return ranked


def run_pipeline(
    corpus_dir: str,
    similarity_method: str = "diff",
    threshold: float = DEFAULT_THRESHOLD,
    damping: float = DEFAULT_DAMPING,
    epsilon: float = DEFAULT_EPSILON,
    max_iter: int = DEFAULT_MAX_ITER,
    solver: str = "power",
    verbose: bool = False,
    language: str = "java",
    parser_name: str | None = None,
) -> list[RankedEntry]:
    """
    Run the full Component Rank pipeline and return the ranked list.

    Parameters
    ----------
    corpus_dir:
        Directory tree containing source files.
    similarity_method:
        "diff" or "token".
    threshold:
        Clustering similarity threshold t (default 0.80).
    damping:
        Damping factor p for pseudo use relations (default 0.85).
    epsilon:
        Power-iteration convergence threshold (default 1e-10).
    max_iter:
        Maximum power-iteration steps (default 1000).
    solver:
        "power" (power iteration) or "eigen" (scipy eigenvector).
    verbose:
        Emit progress log messages.
    language:
        Source language to analyse: "java" (default) or "python".
    parser_name:
        Parser engine override.  None selects the language default.
        java  → "javalang" (Java 8) or "treesitter" (Java 8–21).
        python → "ast" or "treesitter".

    Returns
    -------
    List of (rank, qualified_name, weight) tuples, sorted by weight
    descending, with dense ranking for ties.
    """
    if verbose:
        logging.basicConfig(level=logging.INFO, format="%(message)s")

    # ------------------------------------------------------------------
    # Step 1: Parse source files
    # ------------------------------------------------------------------
    log.info("Step 1/7  Parsing %s files in '%s'…", language, corpus_dir)
    parser = get_parser(language, parser_name)
    components = parser.parse_corpus(corpus_dir, verbose=verbose)
    M = len(components)
    if M == 0:
        raise RuntimeError(
            f"No parseable {language} source files found in '{corpus_dir}'."
        )
    log.info("          %d components parsed", M)

    # Build qualified-name → index lookup (used by graph builder)
    name_to_idx: dict[str, int] = {
        c.qualified_name: i for i, c in enumerate(components)
    }

    # ------------------------------------------------------------------
    # Step 2: Pairwise similarity
    # ------------------------------------------------------------------
    log.info("Step 2/7  Computing %d pairwise similarities (%s)…",
             M * (M - 1) // 2, similarity_method)
    method = get_similarity_method(similarity_method, language=language)
    S = _compute_similarity_matrix(components, method, threshold)

    # ------------------------------------------------------------------
    # Step 3: Cluster similar components
    # ------------------------------------------------------------------
    log.info("Step 3/7  Clustering (threshold=%.2f)…", threshold)
    components, cluster_map = cluster_components(components, S, threshold)
    N = len(cluster_map)
    log.info("          %d components → %d clusters", M, N)

    # ------------------------------------------------------------------
    # Step 4: Build cluster-level graph
    # ------------------------------------------------------------------
    log.info("Step 4/7  Building cluster graph…")
    adjacency = build_cluster_graph(components, name_to_idx)
    total_edges = sum(len(v) for v in adjacency.values())
    log.info("          %d directed edges between %d clusters", total_edges, N)

    # ------------------------------------------------------------------
    # Step 5: Build amended distribution matrix D'
    # ------------------------------------------------------------------
    log.info("Step 5/7  Building %dx%d distribution matrix (p=%.2f)…",
             N, N, damping)
    D_prime = build_distribution_matrix(adjacency, N, p=damping)

    # ------------------------------------------------------------------
    # Step 6: Compute weights
    # ------------------------------------------------------------------
    log.info("Step 6/7  Computing weights (%s)…", solver)
    if solver == "eigen":
        W = eigenvector_solver(D_prime)
    else:
        W = power_iteration(D_prime, epsilon=epsilon, max_iter=max_iter)
    log.info("          Weight vector sum: %.10f", W.sum())

    # ------------------------------------------------------------------
    # Step 7: De-cluster and rank
    # ------------------------------------------------------------------
    log.info("Step 7/7  De-clustering and ranking…")
    component_weights = [
        (c.qualified_name, float(W[c.cluster_id]))  # type: ignore[index]
        for c in components
    ]
    component_weights.sort(key=lambda x: x[1], reverse=True)
    ranked = _assign_ranks(component_weights)
    log.info("          Done.  Top result: %s (weight=%.8f)",
             ranked[0][1], ranked[0][2])

    return ranked

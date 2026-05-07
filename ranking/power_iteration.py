"""
ranking/power_iteration.py
Computes the stationary distribution W of the Markov chain defined by D'
via repeated matrix-vector multiplication (the Power Method).

Algorithm:
    1. Initialise W = [1/N, ..., 1/N]
    2. Each step: W_new = (D')^T @ W
    3. Re-normalise W_new (guards against floating-point drift)
    4. If  ||W_new - W||_1  <  epsilon, declare convergence

The transpose (D')^T is taken once before the loop so that each iteration
is a single matrix-vector product — no redundant transposes.

The mathematical guarantee of convergence follows from the Perron-Frobenius
theorem: D' is a positive, row-stochastic matrix (every entry > 0 because
of the pseudo-use-relation term), so it has a unique stationary distribution
and the power iteration converges to it from any initial distribution.
"""

from __future__ import annotations
import numpy as np

from config import DEFAULT_EPSILON, DEFAULT_MAX_ITER


def power_iteration(
    D_prime: np.ndarray,
    epsilon: float = DEFAULT_EPSILON,
    max_iter: int = DEFAULT_MAX_ITER,
) -> np.ndarray:
    """
    Compute the stationary weight vector W by power iteration.

    Parameters
    ----------
    D_prime:
        (N, N) row-stochastic amended distribution matrix.
    epsilon:
        Convergence threshold on the L1 norm of the weight change.
    max_iter:
        Maximum number of iterations before raising RuntimeError.

    Returns
    -------
    W: np.ndarray, shape (N,), dtype float64
        Non-negative weight vector summing to 1.0.

    Raises
    ------
    RuntimeError if convergence is not reached within max_iter steps.
    """
    N = D_prime.shape[0]
    W = np.full(N, 1.0 / N, dtype=np.float64)
    D_T = D_prime.T.copy()  # transpose once; reuse across all iterations

    delta = float("inf")
    for iteration in range(max_iter):
        W_new = D_T @ W
        # Re-normalise to counteract floating-point drift
        total = W_new.sum()
        if total > 0:
            W_new /= total
        delta = float(np.abs(W_new - W).sum())
        W = W_new
        if delta < epsilon:
            break
    else:
        raise RuntimeError(
            f"Power iteration did not converge after {max_iter} iterations. "
            f"Final L1 delta: {delta:.3e}  (epsilon={epsilon:.3e})"
        )

    # Safety: clip tiny negative values produced by float arithmetic
    assert np.all(W >= -1e-12), f"Unexpected negative weights: {W[W < 0]}"
    W = np.maximum(W, 0.0)

    return W

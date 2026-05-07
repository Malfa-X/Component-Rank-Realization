"""
ranking/eigenvector.py
Alternative stationary-distribution solver using scipy's full eigendecomposition.

The stationary distribution W satisfies  (D')^T W = W,
i.e. W is the right eigenvector of (D')^T with eigenvalue 1.

This solver is numerically exact but O(N^3) in time and O(N^2) in memory,
making it suitable for small corpora (N < 500).  For large corpora, prefer
power_iteration.py.
"""

from __future__ import annotations
import numpy as np


def eigenvector_solver(D_prime: np.ndarray) -> np.ndarray:
    """
    Compute the stationary weight vector W via full eigendecomposition.

    Parameters
    ----------
    D_prime:
        (N, N) row-stochastic amended distribution matrix.

    Returns
    -------
    W: np.ndarray, shape (N,), dtype float64
        Non-negative weight vector summing to 1.0.

    Raises
    ------
    RuntimeError if no eigenvalue close to 1.0 is found.
    """
    try:
        from scipy.linalg import eig
    except ImportError as exc:
        raise ImportError(
            "scipy is required for the eigenvector solver. "
            "Install it with: pip install scipy"
        ) from exc

    N = D_prime.shape[0]

    # We want the right eigenvector of (D')^T with eigenvalue 1.
    eigenvalues, eigenvectors = eig(D_prime.T)

    # Find the index of the eigenvalue closest to 1.0
    distances = np.abs(eigenvalues - 1.0)
    idx = int(np.argmin(distances))

    if distances[idx] > 1e-6:
        raise RuntimeError(
            f"No eigenvalue close to 1.0 found.  "
            f"Closest: {eigenvalues[idx]:.6f}  (distance {distances[idx]:.3e})"
        )

    W = eigenvectors[:, idx].real
    W = np.abs(W)   # eigenvector direction is arbitrary; ensure non-negative

    total = W.sum()
    if total <= 0:
        raise RuntimeError("Eigenvector for eigenvalue 1 sums to zero.")
    W /= total

    # Clip tiny float negatives
    assert np.all(W >= -1e-12), f"Unexpected negative weights: {W[W < 0]}"
    return np.maximum(W, 0.0)

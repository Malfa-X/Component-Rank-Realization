# config.py — all pipeline defaults live here

DEFAULT_DAMPING: float = 0.85       # p: weight given to real use relations
DEFAULT_THRESHOLD: float = 0.80     # t: similarity threshold for clustering
DEFAULT_EPSILON: float = 1e-10      # convergence criterion (L1 norm delta)
DEFAULT_MAX_ITER: int = 1000        # safety cap on power iteration steps
SIZE_RATIO_CUTOFF: float = 10.0     # skip pair if max_len/min_len > this
TOKEN_LCS_FALLBACK_LIMIT: int = 2000  # fall back to SequenceMatcher above this

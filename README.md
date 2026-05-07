# Component Rank

> [English](README.md) | [中文](README_ZH.md)

A Python implementation of the **Component Rank** algorithm from:

> Inoue, K., Yokomori, R., Fujiwara, H., Yamamoto, T., Matsushita, M., & Kusumoto, S. (2003).
> *Component Rank: Relative Significance Rank for Software Component Search.*

Component Rank is a PageRank-style algorithm that ranks software components by their **reuse significance** — how much the rest of the codebase depends on them. Components that are widely depended upon (directly or transitively) receive a higher rank.

This implementation supports **Java**, **Python**, and **JavaScript / TypeScript** source trees.

---

## How It Works (Brief)

1. **Parse** all source files (`.java`, `.py`, `.js` / `.ts`) to extract use relations (inheritance, imports, field/method types, object creation).
2. **Compute pairwise similarity** between every pair of files to detect near-duplicates.
3. **Cluster** similar files into equivalence classes so copied components are not double-counted.
4. **Build a weighted directed graph** where each cluster is a node and edges represent use relations.
5. **Solve for the stationary distribution** of the resulting Markov chain (power iteration or eigenvector solver). This is the Component Rank weight vector.
6. **Output** a ranked list: highest-weight classes are the most reused and foundational.

---

## Requirements

- Python 3.10 or later
- Git (to clone the target repository)

---

## Installation

```bash
# Clone this repository
git clone <this-repo-url>
cd component_rank

# Install dependencies
pip install -r requirements.txt
```

`requirements.txt` installs:

| Package | Purpose |
|---|---|
| `javalang==0.13.0` | Java AST parser and tokenizer (Java 8 syntax) |
| `numpy` | Matrix operations and power iteration |
| `scipy` | Optional eigenvector solver |
| `tabulate` | Table-formatted output |
| `tqdm` | Progress bar during similarity computation |
| `pytest` | Test suite |

---

## Quickstart: Analysing a GitHub Package

### Step 1 — Clone the target repository

```bash
git clone --depth 1 https://github.com/<owner>/<repo>.git
```

Using `--depth 1` skips the full git history and is much faster. Examples:

```bash
# Apache Commons Lang  (~200 Java files, good first test)
git clone --depth 1 --branch rel/commons-lang-3.12.0 \
  https://github.com/apache/commons-lang.git

# Google Guava  (~1 500 Java files)
git clone --depth 1 \
  https://github.com/google/guava.git

# JUnit 5  (~800 Java files)
git clone --depth 1 \
  https://github.com/junit-team/junit5.git
```

### Step 2 — Point Component Rank at the source directory

Find the directory that contains the `.java` source files. For Maven/Gradle projects this is almost always `src/main/java`:

```bash
python main.py commons-lang/src/main/java
```

For projects with a flat layout (all `.java` files at the root):

```bash
python main.py <repo-root>
```

Component Rank searches **recursively**, so you only need to provide the top-level source directory.

### Step 3 — Read the output

```
+--------+-------------------------------------------------------+------------+
|   Rank | Component                                             |     Weight |
+========+=======================================================+============+
|      1 | org.apache.commons.lang3.StringUtils                  | 0.04812301 |
|      2 | org.apache.commons.lang3.Validate                     | 0.03991244 |
|      3 | org.apache.commons.lang3.ArrayUtils                   | 0.03217809 |
|      4 | org.apache.commons.lang3.ObjectUtils                  | 0.02984512 |
...
```

- **Rank** — dense rank; tied weights share the same rank number.
- **Component** — fully-qualified Java class name.
- **Weight** — the Component Rank value; all weights sum to 1.0.

High-ranked classes are the most depended-upon. Low-ranked classes are narrow,
application-specific, or not used by anyone else in the corpus.

---

## Full CLI Reference

```
python main.py <corpus_dir> [OPTIONS]
```

| Option | Default | Description |
|---|---|---|
| `--language java\|python\|javascript` | `java` | Source language to analyse |
| `--parser ENGINE` | *(language default)* | Parser engine override. Java: `javalang` (Java 8, default) or `treesitter` (Java 8–21). Python: `ast` (default) or `treesitter` (fault-tolerant). |
| `--similarity diff\|token` | `diff` | Similarity method for clustering (see below) |
| `--threshold T` | `0.80` | Two files with similarity ≥ T are merged into one cluster |
| `--damping P` | `0.85` | Weight given to real use relations vs. pseudo use relations |
| `--epsilon EPS` | `1e-10` | Convergence criterion (L1 norm of weight change per step) |
| `--max-iter N` | `1000` | Safety cap on power-iteration steps |
| `--solver power\|eigen` | `power` | Ranking solver (see below) |
| `--output-format table\|csv\|json` | `table` | Output format |
| `--top N` | *(all)* | Show only the top N results |
| `--verbose` | off | Print step-by-step pipeline progress |

---

## Worked Examples

### Example 1 — Top 20 classes in Apache Commons Lang

```bash
git clone --depth 1 --branch rel/commons-lang-3.12.0 \
  https://github.com/apache/commons-lang.git

python main.py commons-lang/src/main/java \
  --top 20 \
  --verbose
```

### Example 2 — Export full ranking to CSV

```bash
python main.py commons-lang/src/main/java \
  --output-format csv > commons_lang_rank.csv
```

### Example 3 — Export to JSON for downstream processing

```bash
python main.py guava/guava/src \
  --output-format json \
  --top 50 > guava_top50.json
```

JSON format:
```json
[
  {"rank": 1, "qualified_name": "com.google.common.base.Preconditions", "weight": 0.0523},
  {"rank": 2, "qualified_name": "com.google.common.collect.ImmutableList", "weight": 0.0481},
  ...
]
```

### Example 4 — Compare two similarity methods

```bash
# Method 1: diff-based (line-level, mirrors CCFinder + diff from the paper)
python main.py commons-lang/src/main/java \
  --similarity diff --top 10 --output-format csv > diff_rank.csv

# Method 2: token-based LCS (whitespace/formatting insensitive)
python main.py commons-lang/src/main/java \
  --similarity token --top 10 --output-format csv > token_rank.csv
```

### Example 5 — Use the exact eigenvector solver (for small corpora)

```bash
python main.py my-small-project/src \
  --solver eigen \
  --top 10
```

The eigenvector solver (`scipy.linalg.eig`) is exact but O(N³). Prefer it
when the corpus has fewer than ~500 classes. Use the default `power` solver
for larger corpora.

### Example 6 — Adjust the clustering threshold

```bash
# Stricter: only near-identical files are merged (less clustering)
python main.py commons-lang/src/main/java --threshold 0.95

# Looser: files with ~50% shared lines are merged (more clustering)
python main.py commons-lang/src/main/java --threshold 0.50
```

### Example 7 — Rank a Python project

```bash
git clone --depth 1 https://github.com/psf/requests.git

python main.py requests/src/requests \
  --language python \
  --top 20 \
  --verbose
```

### Example 8 — Rank a JavaScript / TypeScript project

```bash
git clone --depth 1 https://github.com/chalk/chalk.git

python main.py chalk/source \
  --language javascript \
  --top 20 \
  --verbose
```

### Example 9 — Use the tree-sitter engine for Java 9+ projects

```bash
# Switch from the default javalang engine (Java 8 only) to tree-sitter (Java 8–21)
python main.py my-java21-project/src \
  --language java \
  --parser treesitter \
  --top 20
```

---

## Similarity Methods Explained

### `--similarity diff` (default)

Mirrors the CCFinder + diff approach described in the paper.

```
S(A, B) = shared_lines / (lines_A + lines_B - shared_lines)
```

`shared_lines` is the count of lines that appear in the same order in both
files (longest common subsequence of lines, via `difflib.SequenceMatcher`).
This is the **Jaccard similarity** of the line multisets.

**Use when:** you want to stay close to the paper's methodology, or for
fast analysis of large corpora.

### `--similarity token`

Tokenizes both files using the Java lexer (`javalang.tokenizer`), then
computes the LCS of the resulting token sequences. Whitespace, comments, and
formatting differences are ignored.

```
S(A, B) = lcs_tokens(A, B) / (tokens_A + tokens_B - lcs_tokens(A, B))
```

**Use when:** you suspect the corpus contains reformatted copies (e.g.
auto-formatted by different IDEs) that the diff method would incorrectly
treat as different.

---

## Algorithm Parameters

| Parameter | Symbol | Default | Effect |
|---|---|---|---|
| Damping factor | *p* | 0.85 | Weight given to real use relations. Pseudo use relations (random jumps) get weight 1−p = 0.15. Identical to Google PageRank's damping factor. |
| Similarity threshold | *t* | 0.80 | Files with S ≥ t are merged before ranking. Higher values = less merging. |
| Convergence epsilon | *ε* | 1e-10 | Power iteration stops when the L1 norm of the weight change falls below ε. |

The paper reports that Component Rank is **insensitive to p** (stable from 0.75 to 0.95)
and **insensitive to t** (stable from 0.10 to 0.90), so the defaults are safe for most corpora.

---

## Interpreting Results

| Rank range | Typical characteristics |
|---|---|
| **Top 1–10%** | Core utility classes, base types, widely-shared data structures. These are the backbone of the codebase. |
| **Top 10–30%** | Framework classes, shared helpers, common interfaces. Frequently used but more specific. |
| **Bottom 30%** | Application-specific classes, leaf nodes, entry points, test helpers. Not used by others. |

**Classes with tied weights (same rank)** were merged into the same cluster during
step 3, meaning they were found to be ≥ t similar to each other. They share one
Component Rank value.

---

## Known Limitations

| Limitation | Detail |
|---|---|
| **Java 8 only (default engine)** | The default `javalang` engine does not support Java 9+ syntax (module-info, records, sealed classes, text blocks). Files using these features are skipped with a debug log message. Switch to `--parser treesitter` for Java 8–21 support (`pip install tree-sitter tree-sitter-java` required). |
| **Static analysis only** | Use relations are extracted from source code structure (field types, method signatures, inheritance). Dynamic dispatch and reflection are not captured. |
| **Intra-corpus only** | References to classes outside the corpus (e.g. `java.util.List`) are silently dropped. To include JDK classes, add the JDK source to the corpus directory. |
| **O(M²) similarity** | Pairwise similarity computation is quadratic in the number of files. For M = 2 000 files this means ~2 million pairs. On a modern laptop this takes 5–15 minutes. A progress bar is shown. |
| **Inner classes excluded** | Only the top-level class in each `.java` file is counted as a component, matching the paper's specification. |

---

## Running the Tests

```bash
cd component_rank
python -m pytest tests/ -v
```

All 59 tests should pass. Test coverage includes:

- Union-Find correctness and transitivity
- Both similarity methods (identical, empty, partial overlap, size-ratio short-circuit)
- Clustering (all-different, all-identical, transitive merging)
- Graph builder (intra-cluster self-loop exclusion, edge deduplication)
- Matrix builder (row sums = 1.0, sink nodes, teleport term)
- Power iteration (convergence, stationary property, chain ordering)
- Eigenvector solver (agrees with power iteration to 1e-6)
- Java parser (extends, implements, external-reference filtering, module-info skip)

---

## Project Layout

```
component_rank/
├── main.py                          CLI entry point
├── config.py                        All defaults (p, t, ε, …)
├── requirements.txt
├── pipeline/
│   └── runner.py                    Orchestrates all 7 steps
├── parsing/
│   ├── use_relation.py              Component dataclass
│   ├── base_parser.py               Abstract LanguageParser interface
│   ├── parser_factory.py            Selects parser by --language / --parser
│   ├── java_parser.py               Java parser (javalang, Java 8)
│   ├── treesitter_java_parser.py    Java parser (tree-sitter, Java 8–21)
│   ├── python_parser.py             Python parser (built-in ast)
│   ├── python_treesitter_parser.py  Python parser (tree-sitter, fault-tolerant)
│   └── js_parser.py                 JavaScript / TypeScript parser (regex)
├── similarity/
│   ├── base.py                      Abstract SimilarityMethod
│   ├── diff_based.py                Line-level Jaccard (difflib)
│   ├── token_based.py               Token LCS Jaccard
│   ├── tokenizers.py                Language-specific tokenizers (Java / Python / JS)
│   └── factory.py                   Selects method by name
├── clustering/
│   ├── union_find.py                Path-compressed Union-Find
│   └── clusterer.py                 Equivalence class builder
├── graph/
│   ├── component_graph.py           Cluster-level adjacency
│   └── matrix_builder.py           Builds amended D′ matrix
├── ranking/
│   ├── power_iteration.py           W = (D′)ᵀW until convergence
│   └── eigenvector.py               scipy direct solver
├── output/
│   └── formatter.py                 table / CSV / JSON output
└── tests/
    ├── test_parser.py
    ├── test_python_parser.py
    ├── test_js_parser.py
    ├── test_similarity.py
    ├── test_clustering.py
    ├── test_graph.py
    └── test_ranking.py
```

---

## Reference

> Inoue, K., Yokomori, R., Fujiwara, H., Yamamoto, T., Matsushita, M., & Kusumoto, S. (2003).
> **Component Rank: Relative Significance Rank for Software Component Search.**
> *Proceedings of the 25th International Conference on Software Engineering (ICSE 2003)*, pp. 390–400.

The algorithm is mathematically equivalent to **PageRank** (Page et al., 1998) applied to
software component use-relation graphs, with the addition of a **pre-clustering step** that
prevents duplicated or near-identical components from inflating their own rank.

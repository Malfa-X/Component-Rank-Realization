# Component Rank（组件排名）

本项目是以下论文中 **Component Rank** 算法的 Python 实现：

> Inoue, K., Yokomori, R., Fujiwara, H., Yamamoto, T., Matsushita, M., & Kusumoto, S. (2003).
> *Component Rank: Relative Significance Rank for Software Component Search.*

Component Rank 是一种类 PageRank 算法，通过分析代码库中各组件之间的实际依赖关系，对每个组件的**复用重要性**进行量化排名。被其他代码广泛依赖（直接或间接）的组件将获得更高的排名。

本实现支持 **Java**、**Python** 以及 **JavaScript / TypeScript** 源代码树。

---

## 算法原理（简述）

1. **解析**所有源文件（`.java`、`.py`、`.js` / `.ts`），提取使用关系（继承、import、字段/方法类型引用、对象创建）。
2. **计算两两相似度**，检测近似重复的文件。
3. **聚类**：将相似文件归入同一等价类，避免复制组件被重复计算。
4. **构建加权有向图**：每个聚类作为一个节点，边表示使用关系。
5. **求解马尔可夫链的稳态分布**（幂迭代法或特征向量法），得到 Component Rank 权重向量。
6. **输出**排名列表：权重越高的类，复用价值和基础性越强。

---

## 环境要求

- Python 3.10 及以上版本
- Git（用于克隆目标仓库）

---

## 安装

```bash
# 克隆本仓库
git clone <本仓库地址>
cd component_rank

# 安装依赖
pip install -r requirements.txt
```

`requirements.txt` 包含以下依赖：

| 包名 | 用途 |
|---|---|
| `javalang==0.13.0` | Java AST 解析器与词法分析器（支持 Java 8 语法） |
| `numpy` | 矩阵运算与幂迭代 |
| `scipy` | 可选的特征向量求解器 |
| `tabulate` | 表格格式化输出 |
| `tqdm` | 相似度计算进度条 |
| `pytest` | 测试套件 |

---

## 快速入门：分析 GitHub 上的某个包

### 第一步 — 克隆目标仓库

```bash
git clone --depth 1 https://github.com/<用户名>/<仓库名>.git
```

使用 `--depth 1` 可跳过完整的 git 历史记录，显著提升克隆速度。示例：

```bash
# Apache Commons Lang（约 200 个 Java 文件，适合初次体验）
git clone --depth 1 --branch rel/commons-lang-3.12.0 \
  https://github.com/apache/commons-lang.git

# Google Guava（约 1500 个 Java 文件）
git clone --depth 1 \
  https://github.com/google/guava.git

# JUnit 5（约 800 个 Java 文件）
git clone --depth 1 \
  https://github.com/junit-team/junit5.git
```

### 第二步 — 指定源代码目录

找到存放 `.java` 文件的目录。Maven/Gradle 项目几乎都使用 `src/main/java`：

```bash
python main.py commons-lang/src/main/java
```

若项目采用扁平布局（所有 `.java` 文件位于根目录）：

```bash
python main.py <仓库根目录>
```

Component Rank 会**递归搜索**子目录，只需提供最顶层的源代码目录即可。

### 第三步 — 阅读输出结果

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

- **Rank（排名）** — 密集排名；权重相同的类共享同一排名编号。
- **Component（组件）** — Java 类的完全限定名。
- **Weight（权重）** — Component Rank 值；所有权重之和为 1.0。

排名靠前的类是被依赖最多的基础类；排名靠后的类功能单一，通常是特定业务逻辑或入口类。

---

## 完整命令行参考

```
python main.py <语料库目录> [选项]
```

| 选项 | 默认值 | 说明 |
|---|---|---|
| `--language java\|python\|javascript` | `java` | 待分析的源代码语言 |
| `--parser ENGINE` | *(语言默认值)* | 解析器引擎覆盖（可选）。Java：`javalang`（Java 8，默认）或 `treesitter`（Java 8–21）；Python：`ast`（默认）或 `treesitter`（容错模式）。 |
| `--similarity diff\|token` | `diff` | 聚类所用的相似度计算方法（详见下文） |
| `--threshold T` | `0.80` | 相似度 ≥ T 的两个文件将合并为同一聚类 |
| `--damping P` | `0.85` | 真实使用关系的权重占比（其余 1−P 分配给伪使用关系） |
| `--epsilon EPS` | `1e-10` | 收敛判据（权重变化量的 L1 范数低于此值时停止迭代） |
| `--max-iter N` | `1000` | 幂迭代的最大步数上限 |
| `--solver power\|eigen` | `power` | 排名求解器（详见下文） |
| `--output-format table\|csv\|json` | `table` | 输出格式 |
| `--top N` | *(全部)* | 仅显示排名前 N 的结果 |
| `--verbose` | 关闭 | 打印逐步的流程进度信息 |

---

## 使用示例

### 示例一 — 查看 Apache Commons Lang 排名前 20 的类

```bash
git clone --depth 1 --branch rel/commons-lang-3.12.0 \
  https://github.com/apache/commons-lang.git

python main.py commons-lang/src/main/java \
  --top 20 \
  --verbose
```

### 示例二 — 将完整排名导出为 CSV

```bash
python main.py commons-lang/src/main/java \
  --output-format csv > commons_lang_rank.csv
```

### 示例三 — 导出为 JSON 供后续处理

```bash
python main.py guava/guava/src \
  --output-format json \
  --top 50 > guava_top50.json
```

JSON 格式示例：
```json
[
  {"rank": 1, "qualified_name": "com.google.common.base.Preconditions", "weight": 0.0523},
  {"rank": 2, "qualified_name": "com.google.common.collect.ImmutableList", "weight": 0.0481},
  ...
]
```

### 示例四 — 对比两种相似度计算方法

```bash
# 方法一：基于 diff 的行级相似度（与论文方法一致）
python main.py commons-lang/src/main/java \
  --similarity diff --top 10 --output-format csv > diff_rank.csv

# 方法二：基于词法单元 LCS 的相似度（对格式差异不敏感）
python main.py commons-lang/src/main/java \
  --similarity token --top 10 --output-format csv > token_rank.csv
```

### 示例五 — 对小型语料库使用精确特征向量求解器

```bash
python main.py my-small-project/src \
  --solver eigen \
  --top 10
```

特征向量求解器（`scipy.linalg.eig`）结果精确，但时间复杂度为 O(N³)。建议在类数量少于约 500 时使用，更大的语料库请使用默认的 `power`（幂迭代）求解器。

### 示例六 — 调整聚类阈值

```bash
# 更严格：只有几乎完全相同的文件才会合并（聚类更少）
python main.py commons-lang/src/main/java --threshold 0.95

# 更宽松：共享约 50% 行内容的文件即会合并（聚类更多）
python main.py commons-lang/src/main/java --threshold 0.50
```

### 示例七 — 分析 Python 项目

```bash
git clone --depth 1 https://github.com/psf/requests.git

python main.py requests/src/requests \
  --language python \
  --top 20 \
  --verbose
```

### 示例八 — 分析 JavaScript / TypeScript 项目

```bash
git clone --depth 1 https://github.com/chalk/chalk.git

python main.py chalk/source \
  --language javascript \
  --top 20 \
  --verbose
```

### 示例九 — 对 Java 9+ 项目使用 tree-sitter 引擎

```bash
# 将默认的 javalang 引擎（仅支持 Java 8）切换为 tree-sitter（支持 Java 8–21）
python main.py my-java21-project/src \
  --language java \
  --parser treesitter \
  --top 20
```

---

## 相似度计算方法详解

### `--similarity diff`（默认）

对应论文中的 CCFinder + diff 方案。

```
S(A, B) = 共同行数 / (A 的行数 + B 的行数 - 共同行数)
```

"共同行数"指两个文件中以相同顺序出现的行的数量（即行序列的最长公共子序列长度，通过 `difflib.SequenceMatcher` 计算）。这等价于行多重集合上的 **Jaccard 相似度**。

**适用场景：** 希望与论文方法保持一致，或需要快速分析大型语料库时。

### `--similarity token`

使用 Java 词法分析器（`javalang.tokenizer`）对两个文件进行词法单元化，然后计算词法单元序列的最长公共子序列（LCS）。该方法对空白字符、注释和代码格式差异不敏感。

```
S(A, B) = lcs_tokens(A, B) / (A 的词元数 + B 的词元数 - lcs_tokens(A, B))
```

**适用场景：** 怀疑语料库中存在被不同 IDE 自动格式化过的副本，而 diff 方法可能将其错误地视为不同文件时。

---

## 算法参数说明

| 参数 | 符号 | 默认值 | 作用 |
|---|---|---|---|
| 阻尼因子 | *p* | 0.85 | 真实使用关系的权重占比。伪使用关系（随机跳转）占 1−p = 0.15，与 Google PageRank 的阻尼因子含义相同。 |
| 相似度阈值 | *t* | 0.80 | 相似度 ≥ t 的文件在排名前合并。值越高，合并越少。 |
| 收敛精度 | *ε* | 1e-10 | 幂迭代中权重变化量的 L1 范数低于 ε 时停止迭代。 |

论文指出，Component Rank 对 *p*（0.75～0.95 范围内稳定）和 *t*（0.10～0.90 范围内稳定）均**不敏感**，因此默认值对大多数语料库都是安全可靠的。

---

## 结果解读

| 排名区间 | 典型特征 |
|---|---|
| **前 1%～10%** | 核心工具类、基础类型、广泛共享的数据结构——代码库的骨架。 |
| **前 10%～30%** | 框架类、共享辅助类、通用接口——使用频繁但更具针对性。 |
| **后 30%** | 特定业务逻辑类、叶节点类、程序入口类、测试辅助类——不被其他类依赖。 |

**权重相同（排名相同）的类**在第三步中被合并为同一聚类，说明它们彼此之间的相似度 ≥ t，共享同一个 Component Rank 值。

---

## 已知局限

| 局限 | 详细说明 |
|---|---|
| **默认引擎仅支持 Java 8** | 默认的 `javalang` 引擎不支持 Java 9+ 语法（模块声明 module-info、记录类 record、密封类 sealed、文本块 text block 等）。使用这些特性的文件将被跳过并记录调试日志。切换至 `--parser treesitter` 可支持 Java 8–21（需额外安装 `pip install tree-sitter tree-sitter-java`）。 |
| **仅静态分析** | 使用关系从源代码结构中提取（字段类型、方法签名、继承关系）。动态分发和反射无法被捕获。 |
| **仅限语料库内部** | 对语料库外部类（如 `java.util.List`）的引用会被静默丢弃。如需纳入 JDK 类，请将 JDK 源代码加入语料库目录。 |
| **O(M²) 相似度计算** | 两两相似度计算的时间复杂度与文件数量的平方成正比。M = 2000 个文件约产生 200 万对比较，在现代笔记本上耗时约 5～15 分钟，运行期间会显示进度条。 |
| **不含内部类** | 每个 `.java` 文件中只有最顶层的类被视为一个组件，与论文规范一致。 |

---

## 运行测试

```bash
cd component_rank
python -m pytest tests/ -v
```

59 个测试用例应全部通过。测试覆盖范围包括：

- Union-Find 正确性与传递性
- 两种相似度方法（完全相同、为空、部分重叠、尺寸比值短路）
- 聚类（全不同、全相同、传递性合并）
- 图构建（类内自环排除、边去重）
- 矩阵构建（行和 = 1.0、汇点节点、传送项）
- 幂迭代（收敛性、稳态性质、链式顺序）
- 特征向量求解器（与幂迭代结果误差 ≤ 1e-6）
- Java 解析器（extends、implements、外部引用过滤、module-info 跳过）

---

## 项目结构

```
component_rank/
├── main.py                          命令行入口
├── config.py                        所有默认参数（p、t、ε 等）
├── requirements.txt
├── pipeline/
│   └── runner.py                    协调全部 7 个步骤
├── parsing/
│   ├── use_relation.py              Component 数据类
│   ├── base_parser.py               抽象接口 LanguageParser
│   ├── parser_factory.py            根据 --language / --parser 选择解析器
│   ├── java_parser.py               Java 解析器（javalang，Java 8）
│   ├── treesitter_java_parser.py    Java 解析器（tree-sitter，Java 8–21）
│   ├── python_parser.py             Python 解析器（内置 ast）
│   ├── python_treesitter_parser.py  Python 解析器（tree-sitter，容错模式）
│   └── js_parser.py                 JavaScript / TypeScript 解析器（正则）
├── similarity/
│   ├── base.py                      抽象基类 SimilarityMethod
│   ├── diff_based.py                行级 Jaccard 相似度（difflib）
│   ├── token_based.py               词元 LCS Jaccard 相似度
│   ├── tokenizers.py                各语言词法分析器（Java / Python / JS）
│   └── factory.py                   按名称选择相似度方法
├── clustering/
│   ├── union_find.py                路径压缩 Union-Find
│   └── clusterer.py                 等价类构建器
├── graph/
│   ├── component_graph.py           聚类级有向邻接表
│   └── matrix_builder.py           构建修正后的 D′ 矩阵
├── ranking/
│   ├── power_iteration.py           W = (D′)ᵀW 直至收敛
│   └── eigenvector.py               scipy 精确求解器
├── output/
│   └── formatter.py                 table / CSV / JSON 输出
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

## 参考文献

> Inoue, K., Yokomori, R., Fujiwara, H., Yamamoto, T., Matsushita, M., & Kusumoto, S. (2003).
> **Component Rank: Relative Significance Rank for Software Component Search.**
> *第 25 届国际软件工程大会论文集（ICSE 2003）*，第 390–400 页。

本算法在数学上等价于将 **PageRank**（Page 等，1998）应用于软件组件使用关系图，其核心创新在于增加了一个**预聚类步骤**，防止重复或近似重复的组件通过彼此引用人为地抬高自身排名。

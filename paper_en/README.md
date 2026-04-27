# English TIFS manuscript (`paper_en/`)

## Source of truth for translation

- **Authoritative modular Chinese draft**: `docs/论文初稿/` (`01-摘要.md` … `12-附录.md`, `claim_traceability.md`).  
- **Legacy merged Chinese file** `paper_cn/论文初稿.md` may contain older narrative; **do not** use it as the sole evidence baseline—translate from `docs/论文初稿/` first.

## Alignment with Chinese policy (platform scope)

English text must mirror the same **narrative–evidence** rules as the Chinese chapters:

1. **Quantitative main-text closure in this repository version** is primarily **Eth-Docker** (`results/statistics/ED-MAIN-*`, graph optimizer `stats_summary_graph_optimizer.*`, claims **C007**, **C003**, **C006**, **C009** where applicable).  
2. **Eth-Cloud** and **BTC-Docker** rows in `protocol/03_experiment_matrix.md` are **pre-registered**; statistics will be produced **after** the corresponding stacks are **downloaded and run locally**. Until `results/statistics/` contains EC/BTC summaries, **do not** state EC/BTC main-table conclusions as completed.  
3. **Ablation**: gradient-mode evidence lives under `results/ablation_snapshots/` (**C009**); do not mix with default `results/statistics/` paths in the main results section.

**Copy-ready English paragraphs** (abstract / intro / limitations) live in:

- **`MANUSCRIPT_SCOPE_en.md`**

Update that file whenever `docs/论文初稿/` changes platform scope wording.

## File layout (recommended)

When you add a full IEEE draft, mirror `docs/论文初稿/` section numbering (e.g. `sections/01-abstract.md`) and keep figure/table IDs consistent with the Chinese draft.

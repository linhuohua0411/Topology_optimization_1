# Manuscript scope & platform wording (English, aligned with `docs/论文初稿/`)

> Use these paragraphs **verbatim or lightly edited** in the IEEE/TIFS draft so English and Chinese policies stay aligned. Update this file when `docs/论文初稿/` changes.

---

## Abstract — platform scope (add after traceability / evidence-chain sentence)

**Eth-Cloud** and **BTC-Docker** experiments are **pre-registered** in `protocol/03_experiment_matrix.md` and Section 6 of the manuscript; we **plan to download and deploy the corresponding platform stacks locally** and then collect runs and fill `results/statistics/` for the main tables (Claims **C001**, **C002**). Until those artifacts exist, **we do not state cross-platform superiority as a settled quantitative conclusion**.

---

## Introduction — contributions bullet (replace any “EC/BTC are primary closed evidence” wording)

We establish a **unified evaluation protocol** (fields, `comparison_id`, and **fair-budget** as the primary reporting variant). **In this manuscript version, the closed quantitative evidence chain for main-text numbers is primarily from Eth-Docker.** Eth-Cloud and BTC-Docker follow the **same** protocol and matrix entries; their statistics will be produced **after local deployment** of the respective stacks, and the main-text tables (`Table 7-1`, `Table 7-2`) and `claim_traceability` rows **C001/C002** will be updated accordingly.

---

## Experimental setup — one-sentence scope guard (Section 6, after platform table)

**Version note:** Rows that already appear in `results/statistics/` and support `status=done` claims in `claim_traceability.md` are **currently dominated by Eth-Docker**. Eth-Cloud and BTC-Docker matrix entries are **on the same protocol**; their `stats_summary*` outputs are **planned after local stack deployment**. **No `done` claim** for C001/C002—and **no definitive cross-platform sentence in the Abstract/Conclusions**—until those files exist.

---

## Main results — reserved subsections (Sections 7.2–7.3 headings / opening lines)

**Section 7.2 — Eth-Cloud (reserved).** Eth-Cloud main experiments (`EC-MAIN`, …) are **planned** after **downloading and locally deploying** the Eth-Cloud stack; we will then populate `results/statistics/` and **Table 7-1** and mark **C001**. This version contains **no** definitive Eth-Cloud quantitative claims.

**Section 7.3 — BTC-Docker (reserved).** BTC-Docker runs (`BTC-MAIN`, …) are **planned** after **downloading and locally deploying** the BTC-Docker stack; we will then populate **Table 7-2** and mark **C002**. This version contains **no** definitive BTC quantitative claims.

---

## Attack analysis chapter — scope disclaimer (opening of Section 8)

**Scope (this version):** The closed statistical loop is **Eth-Docker-first** (see Section 7 and `results/statistics/ED-MAIN-*`). Rows involving **Eth-Cloud** or **BTC-Docker** in the attack matrix are **pre-registered targets** in `protocol/03`; they become first-class main-text tables with `comparison_id` **only after** local deployment produces `stats_summary` rows consistent with `experiments/tifs_stats.py`. Until then, they are **placeholders**, not completed experiments.

---

## Limitations / future work (one paragraph)

We will **download and deploy the Eth-Cloud and BTC-Docker stacks locally**, then rerun under the **`unified_full_protocol`** and **`tifs_stats.py`** rules, write outputs under `results/statistics/`, and update `claim_traceability` (**C001**, **C002**, and **C008** when both EC and ED are `done`). Only then may Eth-Cloud/BTC-Docker be described as **peer** main-text quantitative sources alongside the current Eth-Docker closure.

---

## Glossary (keep consistent in English)

| Term | Note |
|------|------|
| `unified_full_protocol` | Only this variant supports **main-text** quantitative claims (G1). |
| `fair-budget` / `raw-budget` | Primary ranking vs sensitivity; report separately (G5). |
| `ablation_gradient` | Gradient-mode ablation; evidence under `results/ablation_snapshots/` (**C009**), not default `results/statistics/`. |

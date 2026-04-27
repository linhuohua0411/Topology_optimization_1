# 实验配置与产出

本目录存放实验配置与指标产出，与 TIFS 计划 5.1（以太坊/波卡分工）及 4.4（攻击与性能数据）对应。

## 子目录

- **`metrics/`**：结构指标与性能指标时间序列、单轮汇总表（按 run_id 存放 structure_*.csv、perf_timeseries_*.csv 等）
- **配置来源说明**：当前版本未单独维护 `configs/` 目录，主要实验参数直接在脚本中固定：
  - `run_all_experiments.py`
  - `run_eth_real_experiments.py`
  - `run_real_dual_network_experiments.py`
  如需统一配置化管理，可后续新增 `configs/` 并把参数外置。

## run_id 与拓扑形态

- `topology_type`：baseline / optimized  
- 攻击实验：attack_type（random_node、targeted_node、jitter 等）、attack_intensity（如 0.05、0.10）  
- 性能实验：无攻击时记录延迟、P2P 消息量、CPU/带宽等，用于基线 vs 优化后对比

详见计划文档中「数据需求分析」与「实验设计与数据采集计划」。

# 源码说明

本目录包含「基于网络演化动力学的区块链网络拓扑结构全局优化」的核心实现，与 TIFS 计划 6.1 对应。

## 模块

- **`models/`**  
  - `robustness.py`：鲁棒性函数 R、R_s、R_c、R_r 及梯度近似。  
  - `global_optimizer.py`：演化动力学 + 自组织动力学串联、RK4 积分、约束处理，提供 `evolve_step`、`run_optimization`。
- **`data/`**  
  - `io_utils.py`：邻接矩阵与边列表互转、CSV 读写，与 `data/` 目录下拓扑与指标文件格式一致。

## 后续实现顺序

1. 实现 `robustness.py` 中 R 及各子项与梯度。  
2. 实现 `global_optimizer.py` 中单步与整轮优化。  
3. 实现 `io_utils.py` 与 `data/` 下数据格式对接。

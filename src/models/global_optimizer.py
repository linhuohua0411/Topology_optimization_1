"""
演化+自组织串联的全局拓扑优化器，RK4 离散与约束处理，与 TIFS 计划 6.1 一致。
"""


def evolve_step(A, params):
    """单步：演化动力学 RK4 -> 自组织动力学 RK4 -> 约束。返回 A_next。"""
    raise NotImplementedError


def run_optimization(A0, params):
    """从 A0 运行优化，返回 (A_star, history)。"""
    raise NotImplementedError

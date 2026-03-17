"""
鲁棒性评估与梯度近似模块。
实现 R = w1*R_s + w2*R_c + w3*R_r，以及数值差分梯度，与 TIFS 计划 6.1 一致。
"""


def compute_R(A):
    """总鲁棒性 R(A)。返回 float，范围 [0,1]。"""
    raise NotImplementedError


def compute_R_components(A):
    """返回 dict：R_s, R_c, R_r 及可选子项。"""
    raise NotImplementedError


def compute_gradient_R(A, epsilon=1e-5, sample_ratio=0.1):
    """鲁棒性梯度近似，用于演化与自组织驱动。"""
    raise NotImplementedError

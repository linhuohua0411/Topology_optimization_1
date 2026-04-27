#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
数据处理工具函数
提供通用的数据转换和验证功能
"""

from typing import Any, List


def hex_to_int(value: Any, default: int = 0) -> int:
    """
    将十六进制字符串转换为整数
    
    Args:
        value: 可以是十六进制字符串（如 "0x1a"）或整数
        default: 转换失败时的默认值
    
    Returns:
        转换后的整数值
    """
    if isinstance(value, str) and value.startswith("0x"):
        try:
            return int(value, 16)
        except ValueError:
            return default
    try:
        return int(value) if value else default
    except (ValueError, TypeError):
        return default


def status_to_int(status: Any) -> int:
    """
    将状态值转换为整数
    
    Args:
        status: 可以是字符串（"success"/"failure"）或整数
    
    Returns:
        1 表示成功，0 表示失败
    """
    if isinstance(status, str):
        return 1 if status.lower() == "success" else 0
    try:
        return int(status) if status else 0
    except (ValueError, TypeError):
        return 0


def validate_node_id(node_id: Any) -> bool:
    """
    验证节点ID是否有效
    
    Args:
        node_id: 节点ID
    
    Returns:
        True 如果节点ID有效，False 否则
    """
    return bool(node_id and isinstance(node_id, str) and node_id.strip() != "")


def extract_ip_from_p2p_addresses(p2p_addresses: List[str]) -> str:
    """
    从p2p地址列表中提取IP地址
    
    解析格式如: /ip4/10.151.0.72/tcp/9000/p2p/16Uiu2HAm...
    
    Args:
        p2p_addresses: p2p地址列表
    
    Returns:
        提取的IP地址，如果未找到则返回空字符串
    """
    for addr in p2p_addresses:
        if addr.startswith('/ip4/'):
            parts = addr.split('/')
            if len(parts) >= 3:
                return parts[2]  # IP地址在第3个位置
    return ""


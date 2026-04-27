#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
以太坊网络仿真配置模块
从环境变量加载所有配置，支持 2as_6nodes / 12as_100nodes 两种拓扑。
"""

import os
from dataclasses import dataclass, field
from typing import List


def _split_csv(value: str) -> List[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass
class SimulationConfig:
    # ── 以太坊 RPC ────────────────────────────────────────────
    eth_rpc_url: str = "http://10.101.0.72:8545"  # 12as_100nodes BootNode in AS101
    eth_chain_id: int = 1337
    eth_network_id: str = "1337"

    # ── 已解锁账户（从各节点 start.sh 提取，密码为空字符串）──────
    # BootNode(NODE_2): 用于查询，不发送交易（避免影响链路由）
    # POS-3~6: 矿工兼验证者，账户已解锁，可直接通过 eth_sendTransaction 发送
    unlocked_accounts: List[str] = field(default_factory=lambda: [
        # 12as_100nodes: 运行时从 geth eth_accounts 自动获取，或通过 UNLOCKED_ACCOUNTS 环境变量设置
    ])

    # ── 中央收集器 ────────────────────────────────────────────
    central_collector_url: str = "http://eth_node_cleaner:8888"

    # ── PostgreSQL（直接写入，用于补充数据） ──────────────────
    postgresql_dsn: str = "postgresql://postgres:password@eth_postgresql:5432/ethereum_monitor"

    # ── 交易生成器配置 ────────────────────────────────────────
    tx_min_interval: int = 15    # 最小发送间隔（秒）
    tx_max_interval: int = 45    # 最大发送间隔（秒）
    tx_value_min_wei: int = 1_000_000_000_000_000     # 0.001 ETH
    tx_value_max_wei: int = 10_000_000_000_000_000    # 0.01 ETH
    tx_gas_price_gwei: int = 1   # Gas Price (Gwei)
    tx_gas_limit: int = 21000    # 普通转账 Gas

    # ── 混沌代理配置 ──────────────────────────────────────────
    # 目标容器名称包含以下前缀之一（正则 OR）
    chaos_target_patterns: List[str] = field(default_factory=lambda: [
        f"as10{i}h-Ethereum-POS-" for i in range(1, 10)
    ] + [
        f"as11{i}h-Ethereum-POS-" for i in range(0, 3)
    ])
    # 排除节点（BeaconSetup/BootNode 是基础设施，不能下线）
    chaos_exclude_keywords: List[str] = field(default_factory=lambda: [
        "BeaconSetup", "BootNode",
    ])
    chaos_down_min: int = 60     # 节点下线最短时间（秒）
    chaos_down_max: int = 120    # 节点下线最长时间（秒）
    chaos_up_min: int = 180      # 节点上线最短等待时间（秒）
    chaos_up_max: int = 480      # 节点上线最长等待时间（秒）
    chaos_max_concurrent_down: int = 30  # 12as_100nodes: 107个验证者，最多30个同时下线
    # 目标网络接口名称（interface_setup脚本重命名后的名字）
    chaos_interface: str = ""
    chaos_restore_retry_seconds: int = 30

    # ── 合约代理配置 ──────────────────────────────────────────
    contract_call_min_interval: int = 30
    contract_call_max_interval: int = 60
    contract_deploy_min_interval: int = 180
    contract_deploy_max_interval: int = 420
    contract_max_instances_per_type: int = 12
    deployer_account: str = ""  # 12as_100nodes: 运行时从 geth 自动获取第一个账户

    # ── WAN 混沌代理配置 ──────────────────────────────────────
    wan_target_patterns: List[str] = field(default_factory=lambda: ["brd-router"])
    wan_interface_prefixes: List[str] = field(default_factory=lambda: ["ix"])
    wan_event_min_interval: int = 90
    wan_event_max_interval: int = 240
    wan_duration_min: int = 120
    wan_duration_max: int = 300
    wan_max_concurrent_links: int = 6
    wan_min_bandwidth_mbit: int = 5
    wan_max_bandwidth_mbit: int = 300
    wan_min_delay_ms: int = 15
    wan_max_delay_ms: int = 220
    wan_max_jitter_ms: int = 35
    wan_max_loss_pct: float = 2.5

    # ── 控制接口配置 ──────────────────────────────────────────
    control_host: str = "0.0.0.0"
    control_port: int = 8890

    # ── NodeDataCollector 配置 ───────────────────────────────
    # 采集间隔（秒），每隔这么久轮询一次所有节点的 Geth/Lighthouse API
    node_collect_interval: int = 60  # 12as_100nodes节点多，加大采集间隔
    # 节点列表（通过环境变量 ETH_NODES 自定义，分号分隔）
    # 格式: "name:ip[:geth_port[:lh_port[:has_validator]]]"
    # 示例: "POS-3:10.151.0.73:8545:8000:true;POS-4:10.152.0.71"
    eth_nodes_env: str = ""

    # ── 容器标识 ──────────────────────────────────────────────
    container_id: str = "eth_simulation"
    node_id: str = "eth_simulation_agent"


def load_config() -> SimulationConfig:
    """从环境变量加载配置（支持覆盖默认值）"""
    cfg = SimulationConfig()

    cfg.eth_rpc_url = os.getenv("ETH_RPC_URL", cfg.eth_rpc_url)
    cfg.eth_chain_id = int(os.getenv("ETH_CHAIN_ID", str(cfg.eth_chain_id)))
    cfg.central_collector_url = os.getenv("CENTRAL_COLLECTOR_URL", cfg.central_collector_url)
    cfg.postgresql_dsn = os.getenv("POSTGRESQL_DSN", os.getenv("POSTGRES_DSN", cfg.postgresql_dsn))

    # 交易配置
    cfg.tx_min_interval = int(os.getenv("TX_MIN_INTERVAL", str(cfg.tx_min_interval)))
    cfg.tx_max_interval = int(os.getenv("TX_MAX_INTERVAL", str(cfg.tx_max_interval)))

    # 混沌配置
    cfg.chaos_down_min = int(os.getenv("CHAOS_DOWN_MIN", str(cfg.chaos_down_min)))
    cfg.chaos_down_max = int(os.getenv("CHAOS_DOWN_MAX", str(cfg.chaos_down_max)))
    cfg.chaos_up_min = int(os.getenv("CHAOS_UP_MIN", str(cfg.chaos_up_min)))
    cfg.chaos_up_max = int(os.getenv("CHAOS_UP_MAX", str(cfg.chaos_up_max)))
    cfg.chaos_interface = os.getenv("CHAOS_INTERFACE", cfg.chaos_interface)
    cfg.chaos_restore_retry_seconds = int(
        os.getenv("CHAOS_RESTORE_RETRY_SECONDS", str(cfg.chaos_restore_retry_seconds))
    )

    # 合约部署账户
    cfg.deployer_account = os.getenv("CONTRACT_DEPLOYER", cfg.deployer_account)
    cfg.contract_call_min_interval = int(
        os.getenv("CONTRACT_CALL_MIN_INTERVAL", str(cfg.contract_call_min_interval))
    )
    cfg.contract_call_max_interval = int(
        os.getenv("CONTRACT_CALL_MAX_INTERVAL", str(cfg.contract_call_max_interval))
    )
    cfg.contract_deploy_min_interval = int(
        os.getenv("CONTRACT_DEPLOY_MIN_INTERVAL", str(cfg.contract_deploy_min_interval))
    )
    cfg.contract_deploy_max_interval = int(
        os.getenv("CONTRACT_DEPLOY_MAX_INTERVAL", str(cfg.contract_deploy_max_interval))
    )
    cfg.contract_max_instances_per_type = int(
        os.getenv("CONTRACT_MAX_INSTANCES_PER_TYPE", str(cfg.contract_max_instances_per_type))
    )

    # 自定义目标模式（逗号分隔）
    custom_patterns = os.getenv("CHAOS_TARGET_PATTERNS")
    if custom_patterns:
        cfg.chaos_target_patterns = _split_csv(custom_patterns)

    # 自定义账户列表（逗号分隔）
    custom_accounts = os.getenv("UNLOCKED_ACCOUNTS")
    if custom_accounts:
        cfg.unlocked_accounts = _split_csv(custom_accounts)

    # WAN 配置
    wan_patterns = os.getenv("WAN_TARGET_PATTERNS")
    if wan_patterns:
        cfg.wan_target_patterns = _split_csv(wan_patterns)
    wan_prefixes = os.getenv("WAN_INTERFACE_PREFIXES")
    if wan_prefixes:
        cfg.wan_interface_prefixes = _split_csv(wan_prefixes)
    cfg.wan_event_min_interval = int(
        os.getenv("WAN_EVENT_MIN_INTERVAL", str(cfg.wan_event_min_interval))
    )
    cfg.wan_event_max_interval = int(
        os.getenv("WAN_EVENT_MAX_INTERVAL", str(cfg.wan_event_max_interval))
    )
    cfg.wan_duration_min = int(os.getenv("WAN_DURATION_MIN", str(cfg.wan_duration_min)))
    cfg.wan_duration_max = int(os.getenv("WAN_DURATION_MAX", str(cfg.wan_duration_max)))
    cfg.wan_max_concurrent_links = int(
        os.getenv("WAN_MAX_CONCURRENT_LINKS", str(cfg.wan_max_concurrent_links))
    )
    cfg.wan_min_bandwidth_mbit = int(
        os.getenv("WAN_MIN_BANDWIDTH_MBIT", str(cfg.wan_min_bandwidth_mbit))
    )
    cfg.wan_max_bandwidth_mbit = int(
        os.getenv("WAN_MAX_BANDWIDTH_MBIT", str(cfg.wan_max_bandwidth_mbit))
    )
    cfg.wan_min_delay_ms = int(os.getenv("WAN_MIN_DELAY_MS", str(cfg.wan_min_delay_ms)))
    cfg.wan_max_delay_ms = int(os.getenv("WAN_MAX_DELAY_MS", str(cfg.wan_max_delay_ms)))
    cfg.wan_max_jitter_ms = int(
        os.getenv("WAN_MAX_JITTER_MS", str(cfg.wan_max_jitter_ms))
    )
    cfg.wan_max_loss_pct = float(os.getenv("WAN_MAX_LOSS_PCT", str(cfg.wan_max_loss_pct)))

    # 控制接口
    cfg.control_host = os.getenv("CONTROL_HOST", cfg.control_host)
    cfg.control_port = int(os.getenv("CONTROL_PORT", str(cfg.control_port)))

    # 节点采集间隔
    cfg.node_collect_interval = int(os.getenv("NODE_COLLECT_INTERVAL", str(cfg.node_collect_interval)))

    # 自定义节点列表
    cfg.eth_nodes_env = os.getenv("ETH_NODES", "")

    return cfg

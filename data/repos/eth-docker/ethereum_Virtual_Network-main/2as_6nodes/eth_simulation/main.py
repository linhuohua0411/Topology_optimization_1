#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
以太坊网络仿真主程序
并行运行五个模块：
  1. TxGenerator   — 随机发送 ETH 交易
  2. ChaosAgent    — 节点随机上/下线（ip link set net0 up/down）
  3. ContractAgent — 智能合约部署与自动调用
  4. WanChaosAgent — BIRD 广域网链路随机整形
  5. ControlApi    — 研究员手动控制节点/链路的 HTTP 接口

所有数据实时上报到 central_collector + PostgreSQL。
"""

import asyncio
import logging
import os
import signal
import sys

from config import load_config
from reporter import Reporter
from tx_generator import TxGenerator
from chaos_agent import ChaosAgent
from contract_agent import ContractAgent
from wan_chaos_agent import WanChaosAgent
from control_api import ControlApi
# NodeDataCollector 已被节点内置 Agent (eth_node_monitoring_agent) 替代
# 内置 Agent 在每个以太坊节点容器内运行，直接访问 localhost:8545 和本机 Lighthouse
# 保留此模块作为备用（通过 ENABLE_NODE_COLLECTOR=true 环境变量开启）
import os as _os
_ENABLE_NODE_COLLECTOR = _os.getenv("ENABLE_NODE_COLLECTOR", "false").lower() == "true"
if _ENABLE_NODE_COLLECTOR:
    from node_data_collector import NodeDataCollector

# ── 日志配置 ──────────────────────────────────────────────────
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("main")


async def periodic_heartbeat(reporter: Reporter, interval: int = 30):
    """定期向 central_collector 发送心跳"""
    while True:
        await asyncio.sleep(interval)
        await reporter.send_heartbeat()


async def periodic_stats_log(tx_gen: TxGenerator, chaos: ChaosAgent,
                             contract: ContractAgent, wan: WanChaosAgent,
                             interval: int = 60):
    """定期打印统计信息"""
    while True:
        await asyncio.sleep(interval)
        tx_s = tx_gen.get_stats()
        chaos_s = chaos.get_stats()
        contract_s = contract.get_stats()
        wan_s = wan.get_stats()
        logger.info(
            f"\n{'='*60}\n"
            f"📊 仿真统计摘要\n"
            f"  [交易] 发送:{tx_s['sent']} 确认:{tx_s['confirmed']} "
            f"失败:{tx_s['failed']} 成功率:{tx_s['success_rate']:.1f}%\n"
            f"  [混沌] 下线:{chaos_s['total_down']} 上线:{chaos_s['total_up']} "
            f"当前下线:{chaos_s['down_count']}个 恢复失败:{chaos_s['restore_failures']}\n"
            f"  [合约] 部署成功:{contract_s['deploy_success']} "
            f"Counter调用:{contract_s['counter_calls']} "
            f"Token转账:{contract_s['token_transfers']} "
            f"Mint:{contract_s['token_mints']}\n"
            f"  [WAN] 生效:{wan_s['profiles_applied']} 恢复:{wan_s['profiles_restored']} "
            f"当前活跃:{wan_s['active_links']} 失败:{wan_s['apply_failures']}\n"
            f"  Counter值={contract_s['current_counter_value']} "
            f"Counter地址={contract_s.get('counter_address', 'N/A')}\n"
            f"{'='*60}"
        )


async def run_agent(name: str, coro):
    """运行单个代理（捕获异常，不影响其他代理）"""
    try:
        logger.info(f"▶ {name} 启动")
        await coro
    except asyncio.CancelledError:
        logger.info(f"⏹ {name} 已停止")
    except Exception as e:
        logger.error(f"❌ {name} 崩溃: {e}", exc_info=True)


async def main():
    logger.info("=" * 60)
    logger.info("🚀 以太坊网络仿真程序启动")
    logger.info("   功能0: 节点P2P拓扑主动采集（NodeDataCollector）← 实时拓扑的数据源")
    logger.info("   功能1: 随机交易发送器")
    logger.info("   功能2: 节点随机上/下线混沌代理")
    logger.info("   功能3: 智能合约部署与自动交互")
    logger.info("   功能4: BIRD 广域网链路随机整形")
    logger.info("   功能5: 手工控制 API")
    logger.info("=" * 60)

    # 加载配置
    config = load_config()
    logger.info(f"  RPC: {config.eth_rpc_url}")
    logger.info(f"  收集器: {config.central_collector_url}")
    logger.info(f"  混沌目标: {config.chaos_target_patterns}")
    logger.info(f"  交易间隔: {config.tx_min_interval}~{config.tx_max_interval}s")
    logger.info(f"  混沌下线: {config.chaos_down_min}~{config.chaos_down_max}s")
    logger.info(f"  混沌上线等待: {config.chaos_up_min}~{config.chaos_up_max}s")

    # 初始化上报器
    reporter = Reporter(
        config.central_collector_url,
        config.postgresql_dsn,
        config.container_id,
        config.node_id
    )
    await reporter.start()

    # 初始化各代理
    tx_gen = TxGenerator(config, reporter)
    chaos = ChaosAgent(config, reporter)
    contract = ContractAgent(config, reporter)
    wan = WanChaosAgent(config, reporter)
    node_collector = NodeDataCollector(config, reporter) if _ENABLE_NODE_COLLECTOR else None
    control_api = ControlApi(config, chaos, wan, tx_gen, contract)

    # 并行初始化（都会等待链就绪）
    logger.info("⏳ 初始化各代理（等待以太坊链就绪）...")
    tx_ok = await tx_gen.initialize()
    chaos_ok = await chaos.initialize()
    contract_ok = await contract.initialize()
    wan_ok = await wan.initialize()
    # NodeDataCollector 无需等待链（它自身会重试），直接标记可用
    collector_ok = True

    if not tx_ok:
        logger.warning("⚠️ TxGenerator 初始化失败（可能账户余额不足）")
    if not chaos_ok:
        logger.warning("⚠️ ChaosAgent 初始化失败（Docker 可能不可用）")
    if not contract_ok:
        logger.warning("⚠️ ContractAgent 初始化失败（可能无法编译合约）")
    if not wan_ok:
        logger.warning("⚠️ WanChaosAgent 初始化失败（未找到可用 BIRD/WAN 链路）")

    # 构建任务列表
    tasks = []
    if tx_ok:
        tasks.append(asyncio.create_task(
            run_agent("TxGenerator", tx_gen.run())
        ))
    if chaos_ok:
        tasks.append(asyncio.create_task(
            run_agent("ChaosAgent", chaos.run())
        ))
    if contract_ok:
        tasks.append(asyncio.create_task(
            run_agent("ContractAgent", contract.run())
        ))
    if wan_ok:
        tasks.append(asyncio.create_task(
            run_agent("WanChaosAgent", wan.run())
        ))

    # NodeDataCollector：默认禁用，内置 Agent 已接管采集（通过 ENABLE_NODE_COLLECTOR=true 开启）
    if node_collector and _ENABLE_NODE_COLLECTOR:
        tasks.append(asyncio.create_task(
            run_agent("NodeDataCollector", node_collector.run())
        ))
        logger.info("✅ NodeDataCollector 已启动（备用采集模式）")
    else:
        logger.info("ℹ️  NodeDataCollector 已禁用（节点内置 Agent 负责采集）")

    # 后台任务
    await control_api.start()
    logger.info(f"✅ Control API 已启动: http://{config.control_host}:{config.control_port}")
    tasks.append(asyncio.create_task(periodic_heartbeat(reporter)))
    tasks.append(asyncio.create_task(
        periodic_stats_log(tx_gen, chaos, contract, wan)
    ))

    if not any([tx_ok, chaos_ok, contract_ok, wan_ok, collector_ok]):
        logger.error("❌ 所有代理初始化失败，程序退出")
        await control_api.stop()
        await reporter.stop()
        return

    logger.info(f"✅ {sum([tx_ok, chaos_ok, contract_ok, wan_ok])} 个代理已启动，开始仿真")

    # 等待信号
    loop = asyncio.get_event_loop()
    stop_event = asyncio.Event()

    def _signal_handler():
        logger.info("收到停止信号，正在关闭...")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _signal_handler)

    await stop_event.wait()

    # 优雅停止
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    await control_api.stop()
    await wan.shutdown()
    await chaos.shutdown()
    await reporter.stop()
    logger.info("✅ 仿真程序已停止")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("程序被用户中断")
    except Exception as e:
        logger.error(f"程序异常退出: {e}", exc_info=True)
        sys.exit(1)

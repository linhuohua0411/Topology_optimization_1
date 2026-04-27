#!/usr/bin/env python3
"""
以太坊监控容器主启动脚本
同时运行：
1. 网络拓扑管理器 (eth_node_cleaner.py)
2. 中央数据收集器 (central_collector)
"""

import asyncio
import logging
import signal
import sys
from concurrent.futures import ProcessPoolExecutor
import subprocess
import os

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('main')


def run_topology_manager():
    """运行网络拓扑管理器"""
    try:
        logger.info("启动网络拓扑管理器...")
        subprocess.run([sys.executable, "eth_node_cleaner.py"], check=True)
    except KeyboardInterrupt:
        logger.info("网络拓扑管理器收到停止信号")
    except Exception as e:
        logger.error(f"网络拓扑管理器异常: {e}")


async def run_central_collector():
    """运行中央数据收集器"""
    try:
        logger.info("启动中央数据收集器...")
        from central_collector import CentralDataCollector
        
        collector = CentralDataCollector()
        await collector.start()
        
        # 保持运行
        while True:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("中央数据收集器收到停止信号")
    except Exception as e:
        logger.error(f"中央数据收集器异常: {e}")


def signal_handler(signum, frame):
    """处理退出信号"""
    logger.info("收到退出信号，正在关闭所有服务...")
    sys.exit(0)


async def main():
    """主函数"""
    logger.info("=" * 60)
    logger.info("以太坊监控容器启动")
    logger.info("包含功能：")
    logger.info("1. 网络拓扑管理器 - 监控节点连通性")
    logger.info("2. 中央数据收集器 - 接收代理数据(8888端口)")
    logger.info("=" * 60)
    
    # 设置信号处理
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # 创建进程池
    with ProcessPoolExecutor(max_workers=2) as executor:
        # 在独立进程中运行拓扑管理器
        topology_future = executor.submit(run_topology_manager)
        
        # 在主进程中运行中央数据收集器（异步）
        try:
            await run_central_collector()
        except Exception as e:
            logger.error(f"主进程异常: {e}")
        
        # 等待拓扑管理器完成
        topology_future.result()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("程序被用户中断")
    except Exception as e:
        logger.error(f"程序异常退出: {e}")
        sys.exit(1) 
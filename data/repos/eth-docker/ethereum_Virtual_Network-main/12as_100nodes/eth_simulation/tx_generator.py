#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
随机交易发送器（功能1）

逻辑：
1. 等待 Geth RPC 就绪（有区块生成且 block_number > 0）
2. 检查各账户余额，筛选有效发送账户
3. 每隔随机间隔随机选取 from/to 账户，发送 ETH 转账
4. 等待交易收据，将结果上报到 central_collector 和 PostgreSQL
5. 统计交易成功率、Gas 使用量、交易网络图

交易网络：每笔交易在 Neo4j 中形成 Address -> TRANSACTED_WITH -> Address 图
"""

import asyncio
import logging
import random
import time
from typing import Dict, List, Optional, Set

from web3 import Web3
try:
    from web3.middleware import ExtraDataToPOAMiddleware
except ImportError:
    from web3.middleware import geth_poa_middleware as ExtraDataToPOAMiddleware

from config import SimulationConfig
from reporter import Reporter

logger = logging.getLogger("tx_generator")


class TxGenerator:
    def __init__(self, config: SimulationConfig, reporter: Reporter):
        self.config = config
        self.reporter = reporter
        self.w3: Optional[Web3] = None

        # 运行时状态
        self.funded_accounts: List[str] = []
        self.running = False

        # 统计
        self.stats = {
            "sent": 0,
            "confirmed": 0,
            "failed": 0,
            "total_eth_moved": 0,
            "total_gas_used": 0,
            "start_time": time.time(),
        }

    # ── 初始化 ────────────────────────────────────────────────

    async def initialize(self) -> bool:
        """连接 Geth 并等待链就绪"""
        logger.info(f"连接 Geth RPC: {self.config.eth_rpc_url}")
        for attempt in range(60):
            try:
                self.w3 = Web3(Web3.HTTPProvider(
                    self.config.eth_rpc_url,
                    request_kwargs={"timeout": 5}
                ))
                # PoA 兼容（早期挖矿阶段）
                try:
                    self.w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
                except Exception:
                    self.w3.middleware_onion.inject(ExtraDataToPOAMiddleware, 'geth_poa')

                if not self.w3.is_connected():
                    raise ConnectionError("RPC 未响应")

                block = self.w3.eth.block_number
                logger.info(f"✅ Geth 已连接，当前区块: {block}")

                if block >= 1:
                    break
                logger.info(f"等待区块生成（当前: {block}）...")
            except Exception as e:
                logger.info(f"等待 Geth 就绪（{attempt+1}/60）: {e}")
            await asyncio.sleep(5)
        else:
            logger.error("❌ Geth 连接超时")
            return False

        await self._refresh_funded_accounts()
        return len(self.funded_accounts) >= 1

    async def _refresh_funded_accounts(self):
        """刷新有余额的账户列表"""
        funded = []
        # 优先使用配置中的已解锁账户
        candidates = list(self.config.unlocked_accounts)

        # 也尝试从 geth 获取额外账户
        try:
            geth_accounts = self.w3.eth.accounts
            for acc in geth_accounts:
                if acc not in candidates:
                    candidates.append(acc)
        except Exception:
            pass

        for addr in candidates:
            try:
                balance = self.w3.eth.get_balance(addr)
                min_balance = self.config.tx_value_max_wei + 21000 * 10**9  # 加上 Gas 费用
                if balance >= min_balance:
                    funded.append(addr)
                    logger.debug(f"  {addr[:12]}... 余额: {balance / 10**18:.4f} ETH ✅")
                else:
                    logger.debug(f"  {addr[:12]}... 余额不足: {balance / 10**18:.6f} ETH")
            except Exception as e:
                logger.debug(f"  查询余额失败 {addr[:12]}: {e}")

        self.funded_accounts = funded
        logger.info(f"有余额账户数: {len(funded)}/{len(candidates)}")

    # ── 主循环 ────────────────────────────────────────────────

    async def run(self):
        """主循环：定时发送随机交易"""
        self.running = True
        logger.info("🚀 随机交易发送器启动")

        while self.running:
            try:
                await self._send_random_transaction()
            except Exception as e:
                logger.error(f"交易发送异常: {e}")

            # 随机等待间隔
            interval = random.randint(
                self.config.tx_min_interval,
                self.config.tx_max_interval
            )
            logger.debug(f"下次交易将在 {interval} 秒后发送")
            await asyncio.sleep(interval)

            # 每 10 笔交易刷新一次账户余额
            if self.stats["sent"] % 10 == 0:
                await self._refresh_funded_accounts()

    async def _send_random_transaction(self):
        """发送一笔随机 ETH 转账交易"""
        if len(self.funded_accounts) < 1:
            logger.warning("⚠️ 有余额账户为空，跳过交易")
            await self._refresh_funded_accounts()
            return

        # 随机选择 from 和 to（不重复）
        from_addr = random.choice(self.funded_accounts)
        to_candidates = [a for a in self.funded_accounts if a != from_addr]
        if not to_candidates:
            # 使用所有已知验证者地址（接收方不需要在本节点解锁）
            all_known = [
                '0x1081c645CC8c21EfbB0114eAc5fcDBE01a1a4b19',
                '0xD4CC43e3f2830f9082495Dba904B57fc2Ca95CBd',
                '0x72943017A1fa5f255fC0f06625Aec22319FCd5b3',
                '0xC5247277519ca71C488e7D093350aa659aCaDF7e',
            ]
            to_candidates = [a for a in all_known if a != from_addr] or all_known
        to_addr = random.choice(to_candidates)

        # 随机金额
        value_wei = random.randint(
            self.config.tx_value_min_wei,
            self.config.tx_value_max_wei
        )

        try:
            # 使用 pending 状态的 nonce，避免 "replacement transaction underpriced" 错误
            nonce = self.w3.eth.get_transaction_count(from_addr, 'pending')
            gas_price = self.w3.eth.gas_price or (self.config.tx_gas_price_gwei * 10**9)
            # 稍微提高 gas price，避免 nonce 冲突时的替换失败
            gas_price = int(gas_price * 1.1)

            tx_hash = self.w3.eth.send_transaction({
                "from": from_addr,
                "to": to_addr,
                "value": value_wei,
                "gas": self.config.tx_gas_limit,
                "gasPrice": gas_price,
                "nonce": nonce,
                "chainId": self.config.eth_chain_id,
            })

            self.stats["sent"] += 1
            logger.info(
                f"📤 交易发送 [{self.stats['sent']}] "
                f"{from_addr[:10]}→{to_addr[:10]} "
                f"{value_wei/10**18:.4f}ETH tx={tx_hash.hex()[:16]}..."
            )

            # 异步等待收据（最多 60 秒）
            asyncio.create_task(self._wait_for_receipt(tx_hash, {
                "hash": tx_hash.hex(),
                "from": from_addr,
                "to": to_addr,
                "value": value_wei,
                "gas": self.config.tx_gas_limit,
                "gas_price": gas_price,
                "nonce": nonce,
                "input": "0x",
            }))

        except Exception as e:
            self.stats["failed"] += 1
            logger.error(f"❌ 交易发送失败: {e}")

    async def _wait_for_receipt(self, tx_hash, tx_info: Dict, timeout: int = 60):
        """等待交易收据并上报"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                receipt = self.w3.eth.get_transaction_receipt(tx_hash)
                if receipt:
                    self.stats["confirmed"] += 1
                    self.stats["total_gas_used"] += receipt.gasUsed
                    self.stats["total_eth_moved"] += tx_info["value"]

                    tx_data = {
                        **tx_info,
                        "hash": tx_hash.hex(),
                        "block_number": receipt.blockNumber,
                        "status": receipt.status,
                        "gas_used": receipt.gasUsed,
                        "transaction_index": receipt.transactionIndex,
                        "timestamp": time.time(),
                    }

                    await self.reporter.report_transaction(tx_data)
                    logger.info(
                        f"✅ 交易确认: {tx_hash.hex()[:16]}... "
                        f"区块#{receipt.blockNumber} "
                        f"Gas={receipt.gasUsed} "
                        f"状态={'成功' if receipt.status == 1 else '失败'}"
                    )
                    return
            except Exception:
                pass
            await asyncio.sleep(3)

        self.stats["failed"] += 1
        logger.warning(f"⚠️ 交易超时未确认: {tx_hash.hex()[:16]}...")

    def get_stats(self) -> Dict:
        elapsed = time.time() - self.stats["start_time"]
        return {
            **self.stats,
            "elapsed_seconds": int(elapsed),
            "success_rate": (
                self.stats["confirmed"] / self.stats["sent"] * 100
                if self.stats["sent"] > 0 else 0
            ),
            "avg_eth_per_tx": (
                self.stats["total_eth_moved"] / 10**18 / self.stats["confirmed"]
                if self.stats["confirmed"] > 0 else 0
            ),
            "funded_accounts": len(self.funded_accounts),
        }

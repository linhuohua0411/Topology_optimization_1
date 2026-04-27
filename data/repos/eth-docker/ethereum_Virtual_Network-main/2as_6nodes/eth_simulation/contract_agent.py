#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能合约部署与自动交互代理（功能3）

持续随机部署简单合约，并自动触发交互：
1. 启动时部署基线合约，保证系统初始化后立即产生链上合约活动
2. 运行期间按较长时间窗口持续随机部署新实例
3. 每个新实例部署成功后会立刻执行一次合约调用
4. 运行期间持续随机选择已部署实例进行调用，上报到 central_collector + PostgreSQL
"""

import asyncio
import logging
import random
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from web3 import Web3
try:
    from web3.middleware import ExtraDataToPOAMiddleware
except ImportError:
    from web3.middleware import geth_poa_middleware as ExtraDataToPOAMiddleware

from config import SimulationConfig
from reporter import Reporter

logger = logging.getLogger("contract_agent")

COUNTER_SOURCE = """
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract SimpleCounter {
    uint256 public count;
    address public owner;
    uint256 public totalIncrements;
    uint256 public totalDecrements;

    event CountChanged(address indexed by, uint256 newCount, string action, uint256 timestamp);
    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);

    constructor() {
        owner = msg.sender;
        count = 0;
    }

    modifier onlyOwner() {
        require(msg.sender == owner, "Only owner can call this");
        _;
    }

    function increment() public {
        count += 1;
        totalIncrements += 1;
        emit CountChanged(msg.sender, count, "increment", block.timestamp);
    }

    function incrementBy(uint256 amount) public {
        require(amount > 0 && amount <= 100, "Amount must be 1-100");
        count += amount;
        totalIncrements += amount;
        emit CountChanged(msg.sender, count, "incrementBy", block.timestamp);
    }

    function decrement() public {
        require(count > 0, "Count cannot go below zero");
        count -= 1;
        totalDecrements += 1;
        emit CountChanged(msg.sender, count, "decrement", block.timestamp);
    }

    function reset() public onlyOwner {
        count = 0;
        emit CountChanged(msg.sender, count, "reset", block.timestamp);
    }
}
"""

TOKEN_SOURCE = """
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract SimpleToken {
    string public name = "SimTestToken";
    string public symbol = "STT";
    uint8 public decimals = 18;
    uint256 public totalSupply;
    address public owner;
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);
    event Minted(address indexed to, uint256 amount, uint256 timestamp);

    constructor(uint256 initialSupply) {
        owner = msg.sender;
        totalSupply = initialSupply * (10 ** uint256(decimals));
        balanceOf[msg.sender] = totalSupply;
        emit Transfer(address(0), msg.sender, totalSupply);
    }

    modifier onlyOwner() {
        require(msg.sender == owner, "Only owner");
        _;
    }

    function transfer(address to, uint256 amount) public returns (bool) {
        require(to != address(0), "Zero address");
        require(balanceOf[msg.sender] >= amount, "Insufficient balance");
        balanceOf[msg.sender] -= amount;
        balanceOf[to] += amount;
        emit Transfer(msg.sender, to, amount);
        return true;
    }

    function mint(address to, uint256 amount) public onlyOwner {
        totalSupply += amount;
        balanceOf[to] += amount;
        emit Minted(to, amount, block.timestamp);
        emit Transfer(address(0), to, amount);
    }

    function burn(uint256 amount) public {
        require(balanceOf[msg.sender] >= amount, "Insufficient balance");
        balanceOf[msg.sender] -= amount;
        totalSupply -= amount;
        emit Transfer(msg.sender, address(0), amount);
    }
}
"""

FALLBACK_RECIPIENTS = [
    "0x1081c645CC8c21EfbB0114eAc5fcDBE01a1a4b19",
    "0xD4CC43e3f2830f9082495Dba904B57fc2Ca95CBd",
    "0x72943017A1fa5f255fC0f06625Aec22319FCd5b3",
    "0xC5247277519ca71C488e7D093350aa659aCaDF7e",
]


def _compile_contract(source: str, contract_name: str) -> Optional[Tuple[list, str]]:
    try:
        from solcx import compile_source, get_installed_solc_versions

        installed = get_installed_solc_versions()
        if not installed:
            raise RuntimeError("未找到已安装的 solc")
        version = str(installed[0])
        logger.info(f"  使用 solc {version} 编译 {contract_name}")
        compiled = compile_source(
            source,
            output_values=["abi", "bin"],
            solc_version=version,
            optimize=True,
            optimize_runs=200,
            evm_version="paris",
        )
        for key, data in compiled.items():
            if contract_name in key:
                return data["abi"], data["bin"]
        first = list(compiled.values())[0]
        return first["abi"], first["bin"]
    except Exception as e:
        logger.error(f"  ❌ 编译 {contract_name} 失败: {e}")
        return None


@dataclass
class ContractInstance:
    contract_name: str
    address: str
    contract: any
    deployed_at: float


class ContractAgent:
    def __init__(self, config: SimulationConfig, reporter: Reporter):
        self.config = config
        self.reporter = reporter
        self.w3: Optional[Web3] = None
        self.running = False
        self.counter = None
        self.counter_address: Optional[str] = None
        self.token = None
        self.token_address: Optional[str] = None
        self.accounts: List[str] = list(dict.fromkeys(config.unlocked_accounts))
        self.deployer = config.deployer_account
        self.compiled_contracts: Dict[str, Tuple[list, str]] = {}
        self.counter_instances: List[ContractInstance] = []
        self.token_instances: List[ContractInstance] = []
        self._next_deploy_at = 0.0
        self.stats = {
            "counter_calls": 0,
            "token_transfers": 0,
            "token_mints": 0,
            "token_burns": 0,
            "deploy_success": 0,
            "deploy_failures": 0,
            "call_failures": 0,
        }

    async def initialize(self) -> bool:
        for _ in range(60):
            try:
                self.w3 = Web3(Web3.HTTPProvider(
                    self.config.eth_rpc_url,
                    request_kwargs={"timeout": 5},
                ))
                try:
                    self.w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
                except Exception:
                    self.w3.middleware_onion.inject(ExtraDataToPOAMiddleware, "geth_poa")
                if self.w3.is_connected() and self.w3.eth.block_number >= 1:
                    break
            except Exception:
                pass
            await asyncio.sleep(5)
        else:
            logger.error("❌ Geth 连接超时")
            return False

        logger.info(f"✅ Geth 已连接 (block #{self.w3.eth.block_number})")
        self.accounts = self._discover_accounts()
        if not self.deployer:
            self.deployer = self.accounts[0] if self.accounts else ""
        if self.deployer and self.deployer not in self.accounts:
            self.accounts.insert(0, self.deployer)
        if not self.deployer:
            logger.error("❌ 未发现可用部署账户")
            return False

        balance = self.w3.eth.get_balance(self.deployer)
        logger.info(f"  部署者 {self.deployer[:12]}... 余额: {balance/10**18:.4f} ETH")
        if balance < 10**15:
            logger.error("❌ 部署者余额不足，无法部署合约")
            return False

        if not self._compile_all_contracts():
            return False

        success = await self._deploy_bootstrap_contracts()
        self._schedule_next_deploy()
        return success

    def _discover_accounts(self) -> List[str]:
        accounts = list(dict.fromkeys(self.accounts))
        try:
            for account in self.w3.eth.accounts:
                if account not in accounts:
                    accounts.append(account)
        except Exception:
            pass
        if self.deployer and self.deployer not in accounts:
            accounts.append(self.deployer)
        logger.info(f"  可用合约账户数: {len(accounts)}")
        return accounts

    def _compile_all_contracts(self) -> bool:
        logger.info("📦 编译合约源码...")
        for name, source in {
            "SimpleCounter": COUNTER_SOURCE,
            "SimpleToken": TOKEN_SOURCE,
        }.items():
            compiled = _compile_contract(source, name)
            if compiled:
                self.compiled_contracts[name] = compiled
        return bool(self.compiled_contracts)

    async def _deploy_bootstrap_contracts(self) -> bool:
        success = False
        for name in ("SimpleCounter", "SimpleToken"):
            success = await self._deploy_contract_by_name(name, prime_after=True) or success
        return success

    async def _deploy_contract_by_name(self, contract_name: str, prime_after: bool = False) -> bool:
        compiled = self.compiled_contracts.get(contract_name)
        if not compiled:
            return False

        abi, bytecode = compiled
        constructor_args = [1_000_000] if contract_name == "SimpleToken" else None
        address = await self._deploy_contract(contract_name, abi, bytecode, constructor_args)
        if not address:
            self.stats["deploy_failures"] += 1
            return False

        instance = ContractInstance(
            contract_name=contract_name,
            address=address,
            contract=self.w3.eth.contract(address=address, abi=abi),
            deployed_at=time.time(),
        )
        self._register_instance(instance)
        self.stats["deploy_success"] += 1

        if contract_name == "SimpleToken":
            await self._distribute_tokens(instance.contract)

        if prime_after:
            await self._prime_contract(instance)
        return True

    def _register_instance(self, instance: ContractInstance):
        if instance.contract_name == "SimpleCounter":
            self.counter_instances.append(instance)
            self.counter_instances = self.counter_instances[-self.config.contract_max_instances_per_type:]
            latest = self.counter_instances[-1]
            self.counter = latest.contract
            self.counter_address = latest.address
            logger.info(f"✅ SimpleCounter 部署成功: {latest.address}")
        elif instance.contract_name == "SimpleToken":
            self.token_instances.append(instance)
            self.token_instances = self.token_instances[-self.config.contract_max_instances_per_type:]
            latest = self.token_instances[-1]
            self.token = latest.contract
            self.token_address = latest.address
            logger.info(f"✅ SimpleToken 部署成功: {latest.address}")

    async def _deploy_contract(self, name: str, abi: list, bytecode: str,
                               constructor_args: Optional[list] = None) -> Optional[str]:
        try:
            contract = self.w3.eth.contract(abi=abi, bytecode=bytecode)
            if constructor_args:
                tx = contract.constructor(*constructor_args).transact({"from": self.deployer})
            else:
                tx = contract.constructor().transact({"from": self.deployer})
            receipt = await asyncio.get_event_loop().run_in_executor(
                None, lambda: self.w3.eth.wait_for_transaction_receipt(tx, timeout=90)
            )
            await self.reporter.report_contract_deployed(
                name,
                receipt.contractAddress,
                self.deployer,
                receipt.blockNumber,
                tx.hex(),
            )
            logger.info(f"  {name} 部署 tx={tx.hex()[:16]}... 区块#{receipt.blockNumber}")
            return receipt.contractAddress
        except Exception as e:
            logger.error(f"  ❌ {name} 部署失败: {e}")
            return None

    async def _distribute_tokens(self, token_contract):
        amount = 10_000 * 10**18
        for addr in self.accounts:
            if addr == self.deployer:
                continue
            try:
                tx = token_contract.functions.transfer(addr, amount).transact({"from": self.deployer})
                await asyncio.get_event_loop().run_in_executor(
                    None, lambda: self.w3.eth.wait_for_transaction_receipt(tx, timeout=30)
                )
            except Exception as e:
                logger.warning(f"  ⚠️ 分发代币失败 {addr[:12]}: {e}")

    async def _prime_contract(self, instance: ContractInstance):
        try:
            if instance.contract_name == "SimpleCounter":
                tx = instance.contract.functions.incrementBy(random.randint(1, 5)).transact(
                    {"from": self._choose_caller()}
                )
                receipt = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: self.w3.eth.wait_for_transaction_receipt(tx, timeout=60)
                )
                await self.reporter.report_contract_call(
                    instance.address,
                    "incrementBy",
                    self.deployer,
                    tx.hex(),
                    receipt.blockNumber,
                    {"prime": True, "new_count": instance.contract.functions.count().call()},
                )
            elif instance.contract_name == "SimpleToken":
                recipient = self._choose_recipient(exclude=self.deployer)
                if recipient:
                    tx = instance.contract.functions.transfer(recipient, 50 * 10**18).transact(
                        {"from": self.deployer}
                    )
                    receipt = await asyncio.get_event_loop().run_in_executor(
                        None, lambda: self.w3.eth.wait_for_transaction_receipt(tx, timeout=60)
                    )
                    await self.reporter.report_contract_call(
                        instance.address,
                        "transfer",
                        self.deployer,
                        tx.hex(),
                        receipt.blockNumber,
                        {"prime": True, "from": self.deployer, "to": recipient, "amount": 50, "unit": "STT"},
                    )
        except Exception as e:
            self.stats["call_failures"] += 1
            logger.warning(f"  ⚠️ 合约部署后自动触发失败 {instance.contract_name}: {e}")

    def _schedule_next_deploy(self):
        self._next_deploy_at = time.time() + random.randint(
            self.config.contract_deploy_min_interval,
            self.config.contract_deploy_max_interval,
        )

    def _choose_caller(self) -> str:
        return random.choice(self.accounts) if self.accounts else self.deployer

    def _choose_recipient(self, exclude: Optional[str] = None) -> Optional[str]:
        candidates: List[str] = []
        for address in list(self.accounts) + FALLBACK_RECIPIENTS:
            if address and address != exclude and address not in candidates:
                candidates.append(address)
        return random.choice(candidates) if candidates else None

    async def run(self):
        self.running = True
        logger.info("📝 合约部署/交互代理启动")
        if not self.counter_instances and not self.token_instances:
            logger.error("❌ 没有可用合约，退出")
            return

        while self.running:
            try:
                if time.time() >= self._next_deploy_at:
                    await self._deploy_random_contract()
                    self._schedule_next_deploy()
                await self._random_contract_interaction()
            except Exception as e:
                logger.error(f"合约交互异常: {e}", exc_info=True)

            await asyncio.sleep(random.randint(
                self.config.contract_call_min_interval,
                self.config.contract_call_max_interval,
            ))

    async def _deploy_random_contract(self):
        contract_name = random.choice(list(self.compiled_contracts.keys()))
        logger.info(f"📦 运行期随机部署合约: {contract_name}")
        await self._deploy_contract_by_name(contract_name, prime_after=True)

    async def _random_contract_interaction(self):
        operations = []
        if self.counter_instances:
            operations.extend([
                self._call_counter_increment,
                self._call_counter_increment_by,
                self._call_counter_decrement,
            ])
        if self.token_instances:
            operations.extend([
                self._call_token_transfer,
                self._call_token_mint,
                self._call_token_burn,
            ])
        if not operations:
            return
        await random.choice(operations)()

    async def _call_counter_increment(self):
        instance = random.choice(self.counter_instances)
        caller = self._choose_caller()
        try:
            tx = instance.contract.functions.increment().transact({"from": caller})
            receipt = await asyncio.get_event_loop().run_in_executor(
                None, lambda: self.w3.eth.wait_for_transaction_receipt(tx, timeout=30)
            )
            self.stats["counter_calls"] += 1
            await self.reporter.report_contract_call(
                instance.address,
                "increment",
                caller,
                tx.hex(),
                receipt.blockNumber,
                {"caller": caller, "new_count": instance.contract.functions.count().call()},
            )
        except Exception as e:
            self.stats["call_failures"] += 1
            logger.error(f"  ❌ increment 失败: {e}")

    async def _call_counter_increment_by(self):
        instance = random.choice(self.counter_instances)
        caller = self._choose_caller()
        amount = random.randint(1, 10)
        try:
            tx = instance.contract.functions.incrementBy(amount).transact({"from": caller})
            receipt = await asyncio.get_event_loop().run_in_executor(
                None, lambda: self.w3.eth.wait_for_transaction_receipt(tx, timeout=30)
            )
            self.stats["counter_calls"] += 1
            await self.reporter.report_contract_call(
                instance.address,
                "incrementBy",
                caller,
                tx.hex(),
                receipt.blockNumber,
                {"caller": caller, "amount": amount, "new_count": instance.contract.functions.count().call()},
            )
        except Exception as e:
            self.stats["call_failures"] += 1
            logger.error(f"  ❌ incrementBy 失败: {e}")

    async def _call_counter_decrement(self):
        instance = random.choice(self.counter_instances)
        current = instance.contract.functions.count().call()
        if current == 0:
            return
        caller = self._choose_caller()
        try:
            tx = instance.contract.functions.decrement().transact({"from": caller})
            receipt = await asyncio.get_event_loop().run_in_executor(
                None, lambda: self.w3.eth.wait_for_transaction_receipt(tx, timeout=30)
            )
            self.stats["counter_calls"] += 1
            await self.reporter.report_contract_call(
                instance.address,
                "decrement",
                caller,
                tx.hex(),
                receipt.blockNumber,
                {"caller": caller, "new_count": instance.contract.functions.count().call()},
            )
        except Exception as e:
            self.stats["call_failures"] += 1
            logger.error(f"  ❌ decrement 失败: {e}")

    async def _call_token_transfer(self):
        instance = random.choice(self.token_instances)
        from_acc = self._choose_caller()
        to_acc = self._choose_recipient(exclude=from_acc)
        if not to_acc:
            return
        balance = instance.contract.functions.balanceOf(from_acc).call()
        if balance < 10**18:
            return
        amount = random.randint(1, min(100, balance // 10**18)) * 10**18
        try:
            tx = instance.contract.functions.transfer(to_acc, amount).transact({"from": from_acc})
            receipt = await asyncio.get_event_loop().run_in_executor(
                None, lambda: self.w3.eth.wait_for_transaction_receipt(tx, timeout=30)
            )
            self.stats["token_transfers"] += 1
            await self.reporter.report_contract_call(
                instance.address,
                "transfer",
                from_acc,
                tx.hex(),
                receipt.blockNumber,
                {"from": from_acc, "to": to_acc, "amount": amount // 10**18, "unit": "STT"},
            )
        except Exception as e:
            self.stats["call_failures"] += 1
            logger.error(f"  ❌ token transfer 失败: {e}")

    async def _call_token_mint(self):
        instance = random.choice(self.token_instances)
        to_acc = self._choose_recipient()
        if not to_acc:
            return
        amount = random.randint(100, 1000) * 10**18
        try:
            tx = instance.contract.functions.mint(to_acc, amount).transact({"from": self.deployer})
            receipt = await asyncio.get_event_loop().run_in_executor(
                None, lambda: self.w3.eth.wait_for_transaction_receipt(tx, timeout=30)
            )
            self.stats["token_mints"] += 1
            await self.reporter.report_contract_call(
                instance.address,
                "mint",
                self.deployer,
                tx.hex(),
                receipt.blockNumber,
                {"to": to_acc, "amount": amount // 10**18, "unit": "STT"},
            )
        except Exception as e:
            self.stats["call_failures"] += 1
            logger.error(f"  ❌ token mint 失败: {e}")

    async def _call_token_burn(self):
        instance = random.choice(self.token_instances)
        caller = self._choose_caller()
        balance = instance.contract.functions.balanceOf(caller).call()
        if balance < 10**18:
            return
        amount = random.randint(1, min(10, balance // 10**18)) * 10**18
        try:
            tx = instance.contract.functions.burn(amount).transact({"from": caller})
            receipt = await asyncio.get_event_loop().run_in_executor(
                None, lambda: self.w3.eth.wait_for_transaction_receipt(tx, timeout=30)
            )
            self.stats["token_burns"] += 1
            await self.reporter.report_contract_call(
                instance.address,
                "burn",
                caller,
                tx.hex(),
                receipt.blockNumber,
                {"caller": caller, "amount": amount // 10**18, "unit": "STT"},
            )
        except Exception as e:
            self.stats["call_failures"] += 1
            logger.error(f"  ❌ token burn 失败: {e}")

    def get_stats(self) -> Dict:
        counter_val = 0
        if self.counter:
            try:
                counter_val = self.counter.functions.count().call()
            except Exception:
                pass
        return {
            **self.stats,
            "counter_address": self.counter_address,
            "token_address": self.token_address,
            "current_counter_value": counter_val,
            "active_counter_contracts": len(self.counter_instances),
            "active_token_contracts": len(self.token_instances),
            "next_deploy_at": int(self._next_deploy_at) if self._next_deploy_at else None,
        }

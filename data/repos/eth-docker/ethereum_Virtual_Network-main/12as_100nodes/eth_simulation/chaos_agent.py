#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
节点随机上下线代理（功能2）

关键能力：
1. 自动发现目标节点的真实主接口，而不是盲目假设固定接口名
2. 下线前保存 IP/前缀/网关/邻居表
3. 上线时通过 ip link set <iface> up + 路由/邻居恢复，尽量还原到下线前状态
4. 支持随机混沌和人工指定节点上下线
"""

import asyncio
import json
import logging
import random
import re
import shlex
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import aiohttp
import docker
from docker.errors import DockerException, NotFound

from config import SimulationConfig
from reporter import Reporter

logger = logging.getLogger("chaos_agent")


@dataclass
class NeighborEntry:
    ip_address: str
    lladdr: str = ""
    state: str = "UNKNOWN"

    def to_dict(self) -> Dict[str, str]:
        return {
            "ip_address": self.ip_address,
            "lladdr": self.lladdr,
            "state": self.state,
        }


@dataclass
class NodeNetworkConfig:
    container_name: str
    interface: str
    ip_with_prefix: str
    ip_address: str
    prefix_len: str
    broadcast: str
    gateway: str
    gateway_dev: str
    neighbors: List[NeighborEntry] = field(default_factory=list)
    saved_at: float = field(default_factory=time.time)

    def is_valid(self) -> bool:
        return bool(self.ip_address and self.gateway and self.interface)


class ChaosAgent:
    def __init__(self, config: SimulationConfig, reporter: Reporter):
        self.config = config
        self.reporter = reporter
        self.running = False
        self._docker: Optional[docker.DockerClient] = None
        self._lock = asyncio.Lock()
        self._down_nodes: Dict[str, NodeNetworkConfig] = {}
        self._pending_nodes: set[str] = set()
        self._recovery_tasks: Dict[str, asyncio.Task] = {}
        self.stats = {
            "total_down": 0,
            "total_up": 0,
            "restore_failures": 0,
            "skipped_no_targets": 0,
            "manual_down_requests": 0,
            "manual_up_requests": 0,
        }

    async def initialize(self) -> bool:
        try:
            self._docker = docker.from_env()
            self._docker.ping()
            targets = self._get_target_containers()
            logger.info("✅ Docker 客户端初始化成功")
            logger.info(f"  可用混沌目标: {[c.name for c in targets]}")
            return len(targets) > 0
        except DockerException as e:
            logger.error(f"❌ Docker 不可用: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ 混沌代理初始化失败: {e}", exc_info=True)
            return False

    async def run(self):
        self.running = True
        initial_wait = 60
        logger.info(f"🔀 节点混沌代理启动，初始等待 {initial_wait}s")
        await asyncio.sleep(initial_wait)

        while self.running:
            try:
                await self.trigger_node_down(trigger="random")
            except Exception as e:
                logger.error(f"混沌周期异常: {e}", exc_info=True)

            wait = random.randint(self.config.chaos_up_min, self.config.chaos_up_max)
            logger.info(f"⏳ 下次随机下线事件将在 {wait}s 后触发")
            await asyncio.sleep(wait)

    async def shutdown(self):
        self.running = False
        logger.info("♻️  混沌代理准备恢复所有已下线节点")

        current = asyncio.current_task()
        async with self._lock:
            tasks = list(self._recovery_tasks.items())
            down_nodes = list(self._down_nodes.keys())

        for name, task in tasks:
            if task is not current:
                task.cancel()
        if tasks:
            await asyncio.gather(
                *[task for _, task in tasks if task is not current],
                return_exceptions=True
            )

        for name in down_nodes:
            try:
                await self.trigger_node_up(name, trigger="shutdown")
            except Exception as e:
                logger.error(f"恢复节点 {name} 失败: {e}", exc_info=True)

    async def list_nodes(self) -> List[Dict]:
        targets = self._get_target_containers()
        results = []
        for container in targets:
            name = container.name
            async with self._lock:
                cfg = self._down_nodes.get(name)
                pending = name in self._pending_nodes
            iface = cfg.interface if cfg else await self._discover_interface(container)
            results.append({
                "container_name": name,
                "status": "down" if cfg else ("pending" if pending else "up"),
                "interface": iface,
                "ip_address": cfg.ip_address if cfg else None,
            })
        return results

    async def trigger_node_down(self, container_name: Optional[str] = None,
                                duration_seconds: Optional[int] = None,
                                trigger: str = "manual") -> Dict:
        container = self._resolve_target_container(container_name)
        if not container:
            self.stats["skipped_no_targets"] += 1
            return {"ok": False, "error": "no_target"}

        name = container.name
        async with self._lock:
            if name in self._down_nodes:
                return {"ok": False, "error": "already_down", "container_name": name}
            if name in self._pending_nodes:
                return {"ok": False, "error": "operation_in_progress", "container_name": name}
            if len(self._down_nodes) >= self.config.chaos_max_concurrent_down:
                return {"ok": False, "error": "max_concurrent_down_reached"}
            self._pending_nodes.add(name)
            if trigger == "manual":
                self.stats["manual_down_requests"] += 1

        try:
            iface = await self._discover_interface(container)
            if not iface:
                return {"ok": False, "error": "interface_not_found", "container_name": name}

            cfg = await self._save_network_config(container, iface)
            if not cfg or not cfg.is_valid():
                return {"ok": False, "error": "save_network_config_failed", "container_name": name}

            logger.info(f"⬇️  下线节点 {name}，接口 {iface}")
            code, output = await self._exec(container, f"ip link set {shlex.quote(iface)} down")
            if code != 0:
                logger.error(f"  ❌ ip link down 失败: {output}")
                return {"ok": False, "error": "ip_link_down_failed", "container_name": name}

            await asyncio.sleep(1)
            state = await self._get_interface_state(container, iface)
            if state == "UP":
                return {"ok": False, "error": "link_still_up", "container_name": name}

            if duration_seconds is None:
                duration_seconds = random.randint(
                    self.config.chaos_down_min, self.config.chaos_down_max
                )

            async with self._lock:
                self._down_nodes[name] = cfg
                self.stats["total_down"] += 1
                recovery_task = asyncio.create_task(
                    self._recover_after(name, duration_seconds)
                )
                self._recovery_tasks[name] = recovery_task

            await self.reporter.report_chaos_event(
                "node_link_down", name, cfg.ip_address,
                {
                    "layer": "execution",
                    "interface": iface,
                    "trigger": trigger,
                    "saved_config": {
                        "ip": cfg.ip_with_prefix,
                        "prefix_len": cfg.prefix_len,
                        "broadcast": cfg.broadcast,
                        "gateway": cfg.gateway,
                        "gateway_dev": cfg.gateway_dev,
                        "neighbors": [n.to_dict() for n in cfg.neighbors],
                    },
                    "down_duration_seconds": duration_seconds,
                    "timestamp": time.time(),
                }
            )
            logger.info(f"  ✅ {name} 已下线，将在 {duration_seconds}s 后自动尝试恢复")
            return {
                "ok": True,
                "container_name": name,
                "interface": iface,
                "ip_address": cfg.ip_address,
                "duration_seconds": duration_seconds,
            }
        finally:
            async with self._lock:
                self._pending_nodes.discard(name)

    async def trigger_node_up(self, container_name: str, trigger: str = "manual") -> Dict:
        if trigger == "manual":
            self.stats["manual_up_requests"] += 1

        async with self._lock:
            cfg = self._down_nodes.get(container_name)
            task = self._recovery_tasks.pop(container_name, None)

        if not cfg:
            return {"ok": False, "error": "node_not_down", "container_name": container_name}

        current = asyncio.current_task()
        if task and task is not current:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

        try:
            container = self._docker.containers.get(container_name)
        except NotFound:
            return {"ok": False, "error": "container_not_found", "container_name": container_name}

        success, details = await self._restore_node(container, cfg)
        if not success:
            self.stats["restore_failures"] += 1
            if trigger != "shutdown" and self.running:
                retry_task = asyncio.create_task(self._retry_restore(container_name))
                async with self._lock:
                    self._recovery_tasks[container_name] = retry_task
            return {"ok": False, "error": "restore_failed", "details": details}

        async with self._lock:
            self._down_nodes.pop(container_name, None)
            self.stats["total_up"] += 1

        await self.reporter.report_chaos_event(
            "node_link_up", container_name, cfg.ip_address,
            {
                "layer": "execution",
                "interface": cfg.interface,
                "trigger": trigger,
                "restored_config": details,
                "down_duration_seconds": int(time.time() - cfg.saved_at),
                "timestamp": time.time(),
            }
        )
        logger.info(f"⬆️  {container_name} 已恢复上线")
        return {"ok": True, "container_name": container_name, "details": details}

    async def _recover_after(self, container_name: str, duration_seconds: int):
        try:
            await asyncio.sleep(duration_seconds)
            await self.trigger_node_up(container_name, trigger="auto_recovery")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"自动恢复 {container_name} 失败: {e}", exc_info=True)

    async def _retry_restore(self, container_name: str):
        await asyncio.sleep(self.config.chaos_restore_retry_seconds)
        await self.trigger_node_up(container_name, trigger="auto_retry")

    async def _restore_node(self, container, cfg: NodeNetworkConfig) -> Tuple[bool, Dict]:
        iface = cfg.interface
        logger.info(f"⬆️  恢复节点 {cfg.container_name}，接口 {iface}")

        code, output = await self._exec(container, f"ip link set {shlex.quote(iface)} up")
        if code != 0:
            logger.error(f"  ❌ ip link up 失败: {output}")
            return False, {"step": "ip_link_up", "output": output}

        await asyncio.sleep(1)

        current_ip = await self._get_current_ip(container, iface)
        if cfg.ip_address not in current_ip:
            address_cmd = (
                f"ip addr add {shlex.quote(cfg.ip_with_prefix)} "
                f"{('brd ' + shlex.quote(cfg.broadcast)) if cfg.broadcast else ''} "
                f"dev {shlex.quote(iface)}"
            ).strip()
            code, output = await self._exec(container, address_cmd)
            if code != 0 and "File exists" not in output:
                logger.error(f"  ❌ 恢复 IP 失败: {output}")
                return False, {"step": "ip_addr_add", "output": output}

        await self._exec(container, "ip route del default")
        code, output = await self._exec(
            container,
            f"ip route replace default via {shlex.quote(cfg.gateway)} dev {shlex.quote(cfg.gateway_dev or iface)}"
        )
        if code != 0:
            logger.error(f"  ❌ 恢复默认路由失败: {output}")
            return False, {"step": "route_restore", "output": output}

        restored_neighbors = 0
        for neighbor in cfg.neighbors:
            if not neighbor.lladdr:
                continue
            code, _ = await self._exec(
                container,
                "ip neigh replace "
                f"{shlex.quote(neighbor.ip_address)} "
                f"lladdr {shlex.quote(neighbor.lladdr)} "
                f"nud reachable dev {shlex.quote(iface)}"
            )
            if code == 0:
                restored_neighbors += 1

        await asyncio.sleep(1)
        state = await self._get_interface_state(container, iface)
        route_code, route_output = await self._exec(container, "ip route show default")
        ping_code, ping_output = await self._exec(
            container,
            f"ping -c 1 -W 2 {shlex.quote(cfg.gateway)}"
        )

        details = {
            "ip": await self._get_current_ip(container, iface),
            "gateway": cfg.gateway,
            "gateway_dev": cfg.gateway_dev,
            "interface_state": state,
            "default_route": route_output.strip(),
            "gateway_ping_ok": ping_code == 0,
            "restored_neighbors": restored_neighbors,
        }

        if state != "UP":
            return False, {"step": "link_state_verify", **details}
        if cfg.gateway not in route_output:
            return False, {"step": "route_verify", **details}

        if ping_code != 0:
            logger.warning(f"  ⚠️ 网关 ping 失败，可能需要等待 BIRD 收敛: {ping_output.strip()}")

        geth_ok = await self._verify_geth_recovery(container, cfg)
        details["geth_rpc_ok"] = geth_ok

        return True, details

    async def _verify_geth_recovery(self, container, cfg: NodeNetworkConfig) -> bool:
        """恢复后验证 Geth RPC 可用性，并尝试重新连接已知 Peer"""
        geth_url = f"http://{cfg.ip_address}:8545"
        rpc_ok = False

        for attempt in range(6):
            try:
                async with aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=3)
                ) as session:
                    payload = {"jsonrpc": "2.0", "method": "admin_peers", "params": [], "id": 1}
                    async with session.post(geth_url, json=payload) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            peers = data.get("result", []) or []
                            logger.info(
                                f"  ✅ Geth RPC 可达 ({cfg.container_name})，"
                                f"当前 peer 数: {len(peers)}"
                            )
                            rpc_ok = True
                            if len(peers) > 0:
                                return True
                            await self._try_add_bootnodes(session, geth_url, cfg)
                            return True
            except Exception:
                pass
            await asyncio.sleep(5)

        if not rpc_ok:
            logger.warning(f"  ⚠️ Geth RPC 在 30s 内未恢复 ({cfg.container_name})")
        return rpc_ok

    async def _try_add_bootnodes(self, session: aiohttp.ClientSession,
                                  geth_url: str, cfg: NodeNetworkConfig):
        """尝试将 bootnode 的 enode 信息添加为 peer，加速区块链网络重连"""
        for neighbor in cfg.neighbors:
            if not neighbor.ip_address:
                continue
            neighbor_geth = f"http://{neighbor.ip_address}:8545"
            try:
                payload = {"jsonrpc": "2.0", "method": "admin_nodeInfo", "params": [], "id": 1}
                async with session.post(neighbor_geth, json=payload) as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.json()
                    enode = (data.get("result") or {}).get("enode", "")
                    if not enode:
                        continue
                add_payload = {
                    "jsonrpc": "2.0",
                    "method": "admin_addPeer",
                    "params": [enode],
                    "id": 2,
                }
                async with session.post(geth_url, json=add_payload) as resp:
                    if resp.status == 200:
                        logger.info(f"  ➕ 已添加 peer {neighbor.ip_address} 的 enode")
                        return
            except Exception:
                continue

    async def _save_network_config(self, container, iface: str) -> Optional[NodeNetworkConfig]:
        code, addr_output = await self._exec(container, f"ip -o -4 addr show dev {shlex.quote(iface)}")
        if code != 0:
            logger.error(f"  ❌ 读取 {iface} IP 失败: {addr_output}")
            return None

        ip_match = re.search(
            r"inet\s+(\d+\.\d+\.\d+\.\d+)/(\d+)(?:\s+brd\s+(\d+\.\d+\.\d+\.\d+))?",
            addr_output
        )
        if not ip_match:
            logger.error(f"  ❌ 无法解析 {iface} 的 IP: {addr_output}")
            return None

        ip_addr = ip_match.group(1)
        prefix_len = ip_match.group(2)
        broadcast = ip_match.group(3) or ""
        ip_with_prefix = f"{ip_addr}/{prefix_len}"

        code, route_output = await self._exec(
            container,
            f"ip route show default dev {shlex.quote(iface)} || ip route show default"
        )
        if code != 0:
            logger.error(f"  ❌ 读取默认路由失败: {route_output}")
            return None

        route_match = re.search(
            r"default via\s+(\d+\.\d+\.\d+\.\d+)(?:\s+dev\s+(\S+))?",
            route_output
        )
        if not route_match:
            logger.error(f"  ❌ 无法解析默认路由: {route_output}")
            return None
        gateway = route_match.group(1)
        gateway_dev = route_match.group(2) or iface

        _, neigh_output = await self._exec(container, f"ip neigh show dev {shlex.quote(iface)}")
        neighbors = self._parse_neighbors(neigh_output)

        return NodeNetworkConfig(
            container_name=container.name,
            interface=iface,
            ip_with_prefix=ip_with_prefix,
            ip_address=ip_addr,
            prefix_len=prefix_len,
            broadcast=broadcast,
            gateway=gateway,
            gateway_dev=gateway_dev,
            neighbors=neighbors,
        )

    async def _discover_interface(self, container) -> str:
        preferred = (self.config.chaos_interface or "").strip()
        if preferred and await self._interface_exists(container, preferred):
            return preferred

        _, route_output = await self._exec(container, "ip route show default")
        route_match = re.search(r"default via\s+\S+\s+dev\s+(\S+)", route_output)
        if route_match:
            route_iface = route_match.group(1)
            if await self._interface_exists(container, route_iface):
                return route_iface

        for iface in self._get_labeled_interfaces(container):
            if iface.startswith("ix"):
                continue
            if await self._interface_exists(container, iface):
                return iface

        _, link_output = await self._exec(container, "ip -o link show")
        for line in link_output.splitlines():
            match = re.search(r":\s+([^:@]+)", line)
            if not match:
                continue
            iface = match.group(1)
            if iface == "lo" or iface.startswith("docker"):
                continue
            if iface.startswith(("net", "inet", "eth")):
                return iface
        return ""

    async def _interface_exists(self, container, iface: str) -> bool:
        code, _ = await self._exec(container, f"ip link show {shlex.quote(iface)}")
        return code == 0

    async def _get_interface_state(self, container, iface: str) -> str:
        code, output = await self._exec(container, f"ip link show {shlex.quote(iface)}")
        if code != 0:
            return "UNKNOWN"
        if "state UP" in output:
            return "UP"
        if "state DOWN" in output:
            return "DOWN"
        return "UNKNOWN"

    async def _get_current_ip(self, container, iface: str) -> str:
        code, output = await self._exec(container, f"ip -o -4 addr show dev {shlex.quote(iface)}")
        if code != 0:
            return "N/A"
        match = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+/\d+)", output)
        return match.group(1) if match else "N/A"

    async def _exec(self, container, command: str) -> Tuple[int, str]:
        try:
            result = container.exec_run(["sh", "-lc", command], privileged=True)
            output = result.output.decode("utf-8", errors="replace") if result.output else ""
            return result.exit_code, output
        except Exception as e:
            return 1, str(e)

    def _parse_neighbors(self, output: str) -> List[NeighborEntry]:
        neighbors: List[NeighborEntry] = []
        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue
            tokens = line.split()
            ip_addr = tokens[0]
            lladdr = ""
            state = tokens[-1]
            if "lladdr" in tokens:
                idx = tokens.index("lladdr")
                if idx + 1 < len(tokens):
                    lladdr = tokens[idx + 1]
            neighbors.append(NeighborEntry(ip_address=ip_addr, lladdr=lladdr, state=state))
        return neighbors[:8]

    def _get_labeled_interfaces(self, container) -> List[str]:
        labels = getattr(container, "labels", None) or container.attrs.get("Config", {}).get("Labels", {}) or {}
        prefix = "org.seedsecuritylabs.seedemu.meta.net."
        entries: List[Tuple[int, str]] = []
        for key, value in labels.items():
            if key.startswith(prefix) and key.endswith(".name"):
                suffix = key[len(prefix):]
                try:
                    index = int(suffix.split(".")[0])
                except ValueError:
                    continue
                entries.append((index, value))
        return [value for _, value in sorted(entries)]

    def _resolve_target_container(self, container_name: Optional[str]):
        targets = self._get_target_containers()
        if not targets:
            return None
        if container_name:
            for container in targets:
                if container.name == container_name:
                    return container
            return None

        async_down_count = len(self._down_nodes)
        if async_down_count >= self.config.chaos_max_concurrent_down:
            logger.info(f"ℹ️ 已达到最大下线数 {self.config.chaos_max_concurrent_down}")
            return None

        available = [c for c in targets if c.name not in self._down_nodes and c.name not in self._pending_nodes]
        if not available:
            logger.info("ℹ️ 当前没有可下线的候选节点")
            return None
        return random.choice(available)

    def _get_target_containers(self) -> List:
        if not self._docker:
            return []
        try:
            containers = self._docker.containers.list()
            targets = []
            for container in containers:
                name = container.name
                if any(keyword in name for keyword in self.config.chaos_exclude_keywords):
                    continue
                if any(pattern in name for pattern in self.config.chaos_target_patterns):
                    targets.append(container)
            return sorted(targets, key=lambda item: item.name)
        except Exception as e:
            logger.error(f"获取容器列表失败: {e}", exc_info=True)
            return []

    def get_stats(self) -> Dict:
        return {
            **self.stats,
            "currently_down": sorted(self._down_nodes.keys()),
            "down_count": len(self._down_nodes),
            "pending_count": len(self._pending_nodes),
        }

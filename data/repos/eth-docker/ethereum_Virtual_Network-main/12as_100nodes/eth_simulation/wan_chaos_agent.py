#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WAN 链路混沌代理（功能4）

针对 BIRD 路由器/IX 接口持续随机调整 tc profile，
并在指定持续时间后自动恢复到原先的 qdisc 状态。
"""

import asyncio
import logging
import random
import re
import shlex
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import docker
from docker.errors import DockerException, NotFound

from config import SimulationConfig
from reporter import Reporter

logger = logging.getLogger("wan_chaos_agent")


@dataclass
class WanProfile:
    bandwidth_mbit: int
    delay_ms: int
    jitter_ms: int
    loss_pct: float
    latency_ms: int = 60
    burst_kbit: int = 0

    def __post_init__(self):
        if not self.burst_kbit:
            self.burst_kbit = max(128, min(4096, self.bandwidth_mbit * 32))

    def to_dict(self) -> Dict:
        return {
            "bandwidth_mbit": self.bandwidth_mbit,
            "delay_ms": self.delay_ms,
            "jitter_ms": self.jitter_ms,
            "loss_pct": round(self.loss_pct, 3),
            "latency_ms": self.latency_ms,
            "burst_kbit": self.burst_kbit,
        }


@dataclass
class WanLinkState:
    container_name: str
    interface: str
    active_profile: WanProfile
    baseline_profile: Optional[WanProfile]
    baseline_raw: str
    applied_at: float = field(default_factory=time.time)


class WanChaosAgent:
    def __init__(self, config: SimulationConfig, reporter: Reporter):
        self.config = config
        self.reporter = reporter
        self.running = False
        self._docker: Optional[docker.DockerClient] = None
        self._lock = asyncio.Lock()
        self._active_links: Dict[str, WanLinkState] = {}
        self._restore_tasks: Dict[str, asyncio.Task] = {}
        self.stats = {
            "profiles_applied": 0,
            "profiles_restored": 0,
            "apply_failures": 0,
            "manual_apply_requests": 0,
            "manual_reset_requests": 0,
        }

    async def initialize(self) -> bool:
        try:
            self._docker = docker.from_env()
            self._docker.ping()
            targets = self._list_target_links()
            logger.info(f"✅ WAN 混沌代理初始化成功，可用链路数: {len(targets)}")
            return len(targets) > 0
        except DockerException as e:
            logger.error(f"❌ WAN 混沌代理无法连接 Docker: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ WAN 混沌代理初始化失败: {e}", exc_info=True)
            return False

    async def run(self):
        self.running = True
        initial_wait = 90
        logger.info(f"🌐 WAN 混沌代理启动，初始等待 {initial_wait}s")
        await asyncio.sleep(initial_wait)

        while self.running:
            try:
                await self.apply_profile(trigger="random")
            except Exception as e:
                logger.error(f"WAN 混沌周期异常: {e}", exc_info=True)

            wait = random.randint(self.config.wan_event_min_interval, self.config.wan_event_max_interval)
            logger.info(f"⏳ 下次 WAN 扰动将在 {wait}s 后触发")
            await asyncio.sleep(wait)

    async def shutdown(self):
        self.running = False
        current = asyncio.current_task()
        async with self._lock:
            tasks = list(self._restore_tasks.items())
            active_keys = list(self._active_links.keys())

        for _, task in tasks:
            if task is not current:
                task.cancel()
        if tasks:
            await asyncio.gather(
                *[task for _, task in tasks if task is not current],
                return_exceptions=True
            )

        for key in active_keys:
            container_name, interface = key.split("::", 1)
            try:
                await self.reset_profile(container_name, interface, trigger="shutdown")
            except Exception as e:
                logger.error(f"恢复 WAN 链路 {key} 失败: {e}", exc_info=True)

    async def list_targets(self) -> List[Dict]:
        results = []
        for container, iface in self._list_target_links():
            results.append({
                "container_name": container.name,
                "interface": iface,
                "active": self._link_key(container.name, iface) in self._active_links,
            })
        return results

    async def list_active_profiles(self) -> List[Dict]:
        async with self._lock:
            states = list(self._active_links.values())
        return [{
            "container_name": state.container_name,
            "interface": state.interface,
            "profile": state.active_profile.to_dict(),
            "baseline": state.baseline_profile.to_dict() if state.baseline_profile else None,
            "applied_at": state.applied_at,
        } for state in states]

    async def apply_profile(self, container_name: Optional[str] = None,
                            interface: Optional[str] = None,
                            duration_seconds: Optional[int] = None,
                            profile: Optional[WanProfile] = None,
                            trigger: str = "manual") -> Dict:
        target = self._resolve_target_link(container_name, interface)
        if not target:
            return {"ok": False, "error": "no_target_link"}
        container, interface_name = target
        key = self._link_key(container.name, interface_name)

        async with self._lock:
            if trigger == "manual":
                self.stats["manual_apply_requests"] += 1
            if key in self._active_links:
                return {"ok": False, "error": "link_already_active", "link": key}
            if len(self._active_links) >= self.config.wan_max_concurrent_links:
                return {"ok": False, "error": "max_concurrent_links_reached"}

        if profile is None:
            profile = self._generate_profile()
        if duration_seconds is None:
            duration_seconds = random.randint(self.config.wan_duration_min, self.config.wan_duration_max)

        baseline_raw = await self._show_qdisc(container, interface_name)
        baseline_profile = self._parse_qdisc_profile(baseline_raw)
        success, output = await self._apply_qdisc_profile(container, interface_name, profile)
        if not success:
            self.stats["apply_failures"] += 1
            return {"ok": False, "error": "apply_failed", "output": output}

        link_state = WanLinkState(
            container_name=container.name,
            interface=interface_name,
            active_profile=profile,
            baseline_profile=baseline_profile,
            baseline_raw=baseline_raw,
        )
        restore_task = asyncio.create_task(self._restore_after(container.name, interface_name, duration_seconds))

        async with self._lock:
            self._active_links[key] = link_state
            self._restore_tasks[key] = restore_task
            self.stats["profiles_applied"] += 1

        await self.reporter.report_wan_event(
            "wan_profile_changed",
            container.name,
            interface_name,
            {
                "trigger": trigger,
                "profile": profile.to_dict(),
                "baseline": baseline_profile.to_dict() if baseline_profile else {"mode": "clear_root_qdisc"},
                "duration_seconds": duration_seconds,
                "reason": "bird_wan_randomization",
                "old_value": baseline_profile.to_dict() if baseline_profile else {"mode": "default"},
                "new_value": profile.to_dict(),
                "timestamp": time.time(),
            }
        )
        logger.info(
            f"🌐 已对 {container.name}:{interface_name} 应用 WAN profile "
            f"{profile.to_dict()}，持续 {duration_seconds}s"
        )
        return {
            "ok": True,
            "container_name": container.name,
            "interface": interface_name,
            "profile": profile.to_dict(),
            "duration_seconds": duration_seconds,
        }

    async def reset_profile(self, container_name: str, interface: str,
                            trigger: str = "manual") -> Dict:
        key = self._link_key(container_name, interface)
        async with self._lock:
            state = self._active_links.get(key)
            task = self._restore_tasks.pop(key, None)
            if trigger == "manual":
                self.stats["manual_reset_requests"] += 1

        if not state:
            return {"ok": False, "error": "link_not_active", "link": key}

        current = asyncio.current_task()
        if task and task is not current:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

        try:
            container = self._docker.containers.get(container_name)
        except NotFound:
            return {"ok": False, "error": "container_not_found", "link": key}

        if state.baseline_profile:
            success, output = await self._apply_qdisc_profile(container, interface, state.baseline_profile)
        else:
            success, output = await self._clear_qdisc(container, interface)

        if not success:
            self.stats["apply_failures"] += 1
            return {"ok": False, "error": "restore_failed", "output": output}

        async with self._lock:
            self._active_links.pop(key, None)
            self.stats["profiles_restored"] += 1

        await self.reporter.report_wan_event(
            "wan_profile_restored",
            container_name,
            interface,
            {
                "trigger": trigger,
                "profile": state.active_profile.to_dict(),
                "baseline": state.baseline_profile.to_dict() if state.baseline_profile else {"mode": "clear_root_qdisc"},
                "reason": "bird_wan_randomization",
                "old_value": state.active_profile.to_dict(),
                "new_value": state.baseline_profile.to_dict() if state.baseline_profile else {"mode": "default"},
                "timestamp": time.time(),
            }
        )
        logger.info(f"✅ 已恢复 WAN 链路 {container_name}:{interface}")
        return {"ok": True, "container_name": container_name, "interface": interface}

    async def _restore_after(self, container_name: str, interface: str, duration_seconds: int):
        try:
            await asyncio.sleep(duration_seconds)
            await self.reset_profile(container_name, interface, trigger="auto_restore")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"自动恢复 WAN 链路失败 {container_name}:{interface}: {e}", exc_info=True)

    async def _apply_qdisc_profile(self, container, interface: str,
                                   profile: WanProfile) -> Tuple[bool, str]:
        command_root = (
            f"tc qdisc replace dev {shlex.quote(interface)} root handle 1: "
            f"tbf rate {profile.bandwidth_mbit}mbit burst {profile.burst_kbit}kbit "
            f"latency {profile.latency_ms}ms"
        )
        command_child = (
            f"tc qdisc replace dev {shlex.quote(interface)} parent 1:1 handle 10: "
            f"netem delay {profile.delay_ms}ms {profile.jitter_ms}ms distribution normal "
            f"loss {profile.loss_pct:.3f}%"
        )
        code_root, output_root = await self._exec(container, command_root)
        if code_root != 0:
            return False, output_root
        code_child, output_child = await self._exec(container, command_child)
        if code_child != 0:
            return False, output_child
        return True, output_child

    async def _clear_qdisc(self, container, interface: str) -> Tuple[bool, str]:
        code, output = await self._exec(
            container,
            f"tc qdisc del dev {shlex.quote(interface)} root"
        )
        if code != 0 and "No such file or directory" not in output and "Cannot delete qdisc with handle of zero" not in output:
            return False, output
        return True, output

    async def _show_qdisc(self, container, interface: str) -> str:
        _, output = await self._exec(container, f"tc qdisc show dev {shlex.quote(interface)}")
        return output

    async def _exec(self, container, command: str) -> Tuple[int, str]:
        try:
            result = container.exec_run(["sh", "-lc", command], privileged=True)
            output = result.output.decode("utf-8", errors="replace") if result.output else ""
            return result.exit_code, output
        except Exception as e:
            return 1, str(e)

    def _generate_profile(self) -> WanProfile:
        return WanProfile(
            bandwidth_mbit=random.randint(
                self.config.wan_min_bandwidth_mbit,
                self.config.wan_max_bandwidth_mbit,
            ),
            delay_ms=random.randint(self.config.wan_min_delay_ms, self.config.wan_max_delay_ms),
            jitter_ms=random.randint(3, self.config.wan_max_jitter_ms),
            loss_pct=round(random.uniform(0.0, self.config.wan_max_loss_pct), 3),
        )

    def _parse_qdisc_profile(self, qdisc_output: str) -> Optional[WanProfile]:
        if "tbf" not in qdisc_output and "netem" not in qdisc_output:
            return None

        rate_match = re.search(r"rate\s+([\d.]+)([KMGTP]?bit)", qdisc_output)
        delay_match = re.search(r"delay\s+([\d.]+)ms(?:\s+([\d.]+)ms)?", qdisc_output)
        loss_match = re.search(r"loss\s+([\d.]+)%", qdisc_output)
        latency_match = re.search(r"lat(?:ency)?\s+([\d.]+)ms", qdisc_output)
        burst_match = re.search(r"burst\s+([\d.]+)([KMG]?b)", qdisc_output)

        bandwidth_mbit = 1000
        if rate_match:
            bandwidth_mbit = max(1, int(self._convert_rate_to_mbit(rate_match.group(1), rate_match.group(2))))

        delay_ms = int(float(delay_match.group(1))) if delay_match else 0
        jitter_ms = int(float(delay_match.group(2))) if delay_match and delay_match.group(2) else 0
        loss_pct = float(loss_match.group(1)) if loss_match else 0.0
        latency_ms = int(float(latency_match.group(1))) if latency_match else 60
        burst_kbit = 0
        if burst_match:
            burst_kbit = max(1, int(self._convert_size_to_kbit(burst_match.group(1), burst_match.group(2))))

        return WanProfile(
            bandwidth_mbit=bandwidth_mbit,
            delay_ms=delay_ms,
            jitter_ms=jitter_ms,
            loss_pct=loss_pct,
            latency_ms=latency_ms,
            burst_kbit=burst_kbit,
        )

    def _convert_rate_to_mbit(self, value: str, unit: str) -> float:
        unit = unit.lower()
        numeric = float(value)
        if unit == "bit":
            return numeric / 1_000_000
        if unit == "kbit":
            return numeric / 1_000
        if unit == "mbit":
            return numeric
        if unit == "gbit":
            return numeric * 1_000
        if unit == "tbit":
            return numeric * 1_000_000
        return numeric

    def _convert_size_to_kbit(self, value: str, unit: str) -> float:
        unit = unit.lower()
        numeric = float(value)
        if unit == "b":
            return numeric * 8 / 1000
        if unit == "kb":
            return numeric * 8
        if unit == "mb":
            return numeric * 8 * 1000
        if unit == "gb":
            return numeric * 8 * 1_000_000
        return numeric

    def _resolve_target_link(self, container_name: Optional[str],
                             interface: Optional[str]) -> Optional[Tuple]:
        links = self._list_target_links()
        if not links:
            return None

        if container_name:
            for container, iface in links:
                if container.name == container_name and (not interface or iface == interface):
                    return container, iface
            return None

        available = [
            (container, iface)
            for container, iface in links
            if self._link_key(container.name, iface) not in self._active_links
        ]
        if not available:
            return None
        return random.choice(available)

    def _list_target_links(self) -> List[Tuple]:
        if not self._docker:
            return []
        links = []
        try:
            for container in self._docker.containers.list():
                if self.config.wan_target_patterns and not any(
                    pattern in container.name for pattern in self.config.wan_target_patterns
                ):
                    continue
                for interface in self._get_ix_interfaces(container):
                    links.append((container, interface))
            links.sort(key=lambda item: (item[0].name, item[1]))
            return links
        except Exception as e:
            logger.error(f"枚举 WAN 链路失败: {e}", exc_info=True)
            return []

    def _get_ix_interfaces(self, container) -> List[str]:
        labels = getattr(container, "labels", None) or container.attrs.get("Config", {}).get("Labels", {}) or {}
        prefix = "org.seedsecuritylabs.seedemu.meta.net."
        interfaces = []
        for key, value in labels.items():
            if key.startswith(prefix) and key.endswith(".name"):
                if any(value.startswith(prefix_name) for prefix_name in self.config.wan_interface_prefixes):
                    interfaces.append(value)
        return sorted(set(interfaces))

    def _link_key(self, container_name: str, interface: str) -> str:
        return f"{container_name}::{interface}"

    def get_stats(self) -> Dict:
        return {
            **self.stats,
            "active_links": len(self._active_links),
            "active_link_keys": sorted(self._active_links.keys()),
        }

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
轻量控制接口：
- 指定节点上下线
- 指定 WAN 链路应用/恢复 profile
- 查询当前状态
"""

from typing import Any, Dict, Optional

from aiohttp import web

from config import SimulationConfig
from wan_chaos_agent import WanProfile


class ControlApi:
    def __init__(self, config: SimulationConfig, chaos_agent, wan_agent,
                 tx_generator=None, contract_agent=None):
        self.config = config
        self.chaos_agent = chaos_agent
        self.wan_agent = wan_agent
        self.tx_generator = tx_generator
        self.contract_agent = contract_agent
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None

    async def start(self):
        app = web.Application()
        app.add_routes([
            web.get("/healthz", self._healthz),
            web.get("/api/v1/status", self._status),
            web.get("/api/v1/chaos/nodes", self._list_nodes),
            web.post("/api/v1/chaos/nodes/down", self._node_down),
            web.post("/api/v1/chaos/nodes/up", self._node_up),
            web.get("/api/v1/wan/targets", self._wan_targets),
            web.get("/api/v1/wan/active", self._wan_active),
            web.post("/api/v1/wan/apply", self._wan_apply),
            web.post("/api/v1/wan/reset", self._wan_reset),
        ])
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self.config.control_host, self.config.control_port)
        await self._site.start()

    async def stop(self):
        if self._runner:
            await self._runner.cleanup()
            self._runner = None
            self._site = None

    async def _healthz(self, request):
        return web.json_response({"status": "ok"})

    async def _status(self, request):
        return web.json_response({
            "chaos": self.chaos_agent.get_stats(),
            "wan": self.wan_agent.get_stats(),
            "tx": self.tx_generator.get_stats() if self.tx_generator else None,
            "contracts": self.contract_agent.get_stats() if self.contract_agent else None,
        })

    async def _list_nodes(self, request):
        return web.json_response({"nodes": await self.chaos_agent.list_nodes()})

    async def _node_down(self, request):
        payload = await self._read_json(request)
        result = await self.chaos_agent.trigger_node_down(
            container_name=payload.get("container_name"),
            duration_seconds=payload.get("duration_seconds"),
            trigger="manual",
        )
        return web.json_response(result, status=200 if result.get("ok") else 400)

    async def _node_up(self, request):
        payload = await self._read_json(request)
        container_name = payload.get("container_name")
        if not container_name:
            return web.json_response({"ok": False, "error": "container_name_required"}, status=400)
        result = await self.chaos_agent.trigger_node_up(container_name, trigger="manual")
        return web.json_response(result, status=200 if result.get("ok") else 400)

    async def _wan_targets(self, request):
        return web.json_response({"targets": await self.wan_agent.list_targets()})

    async def _wan_active(self, request):
        return web.json_response({"active_profiles": await self.wan_agent.list_active_profiles()})

    async def _wan_apply(self, request):
        payload = await self._read_json(request)
        profile = None
        if any(key in payload for key in ("bandwidth_mbit", "delay_ms", "jitter_ms", "loss_pct")):
            missing = [key for key in ("bandwidth_mbit", "delay_ms", "jitter_ms", "loss_pct") if key not in payload]
            if missing:
                return web.json_response(
                    {"ok": False, "error": f"missing_profile_fields:{','.join(missing)}"},
                    status=400
                )
            profile = WanProfile(
                bandwidth_mbit=int(payload["bandwidth_mbit"]),
                delay_ms=int(payload["delay_ms"]),
                jitter_ms=int(payload["jitter_ms"]),
                loss_pct=float(payload["loss_pct"]),
            )
        result = await self.wan_agent.apply_profile(
            container_name=payload.get("container_name"),
            interface=payload.get("interface"),
            duration_seconds=payload.get("duration_seconds"),
            profile=profile,
            trigger="manual",
        )
        return web.json_response(result, status=200 if result.get("ok") else 400)

    async def _wan_reset(self, request):
        payload = await self._read_json(request)
        if not payload.get("container_name") or not payload.get("interface"):
            return web.json_response(
                {"ok": False, "error": "container_name_and_interface_required"},
                status=400
            )
        result = await self.wan_agent.reset_profile(
            payload["container_name"],
            payload["interface"],
            trigger="manual",
        )
        return web.json_response(result, status=200 if result.get("ok") else 400)

    async def _read_json(self, request) -> Dict[str, Any]:
        if request.can_read_body:
            try:
                return await request.json()
            except Exception:
                return {}
        return {}

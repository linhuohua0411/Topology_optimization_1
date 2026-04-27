#!/bin/bash
# =============================================================================
# start.sh — 2as_6nodes 一键启动脚本
# 用法:
#   ./start.sh            启动完整网络（首次或重新启动）
#   ./start.sh stop       停止所有服务
#   ./start.sh restart    重启所有服务
#   ./start.sh status     查看服务状态
#   ./start.sh logs       实时查看关键日志
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── 颜色 ──────────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✅ $*${NC}"; }
warn() { echo -e "${YELLOW}⚠️  $*${NC}"; }
err()  { echo -e "${RED}❌ $*${NC}"; }
info() { echo -e "${CYAN}ℹ️  $*${NC}"; }
step() { echo -e "\n${BOLD}${CYAN}▶ $*${NC}"; }

# ── 子命令处理 ─────────────────────────────────────────────────────────────────
case "${1:-start}" in
  stop)
    step "停止所有服务..."
    ./deploy_monitoring.sh --stop 2>/dev/null || true
    docker compose down
    ok "所有服务已停止"
    exit 0 ;;
  restart)
    step "重启服务..."
    ./deploy_monitoring.sh --stop 2>/dev/null || true
    docker compose down
    exec "$0" start ;;
  status)
    echo -e "${BOLD}=== 容器运行状态 ===${NC}"
    docker compose ps
    echo ""
    echo -e "${BOLD}=== 监控 Agent 状态 ===${NC}"
    ./deploy_monitoring.sh --status 2>/dev/null || warn "Agent 未部署"
    echo ""
    echo -e "${BOLD}=== 以太坊链状态 ===${NC}"
    BLOCK=$(curl -sf -X POST http://localhost:8545 \
      -H "Content-Type: application/json" \
      -d '{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}' 2>/dev/null \
      | python3 -c "import sys,json; print(int(json.load(sys.stdin)['result'],16))" 2>/dev/null || echo "未就绪")
    echo "  区块高度: #${BLOCK}"
    echo ""
    echo -e "${BOLD}=== 监控服务 ===${NC}"
    curl -sf http://localhost:8888/health 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'  eth_node_cleaner: {d[\"status\"]}')" 2>/dev/null || warn "  eth_node_cleaner 未就绪"
    curl -sf http://localhost:9999/health 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); s=d.get('connections',{}); print(f'  eth_node_monitoring: {d[\"status\"]} (redis={s.get(\"redis\",\"?\")}, neo4j={s.get(\"neo4j\",\"?\")}, pg={s.get(\"postgresql\",\"?\")})')" 2>/dev/null || warn "  eth_node_monitoring 未就绪"
    exit 0 ;;
  logs)
    echo "实时查看日志（Ctrl+C 退出）..."
    docker compose logs -f eth_node_cleaner eth_simulation eth_node_monitoring 2>/dev/null
    exit 0 ;;
  start|"") : ;;
  *)
    echo "用法: $0 [start|stop|restart|status|logs]"
    exit 1 ;;
esac

# ══════════════════════════════════════════════════════════════════════════════
echo -e "${BOLD}"
echo "╔══════════════════════════════════════════════════════════╗"
echo "║     以太坊虚拟网络仿真平台 — 2as_6nodes 一键启动        ║"
echo "║     拓扑: 2个AS, 6个节点, 1个IXP, 4个PoS验证者          ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# ── 检查 Docker ───────────────────────────────────────────────────────────────
step "Step 1/5: 环境检查"
if ! docker info > /dev/null 2>&1; then
  err "Docker 未运行，请先启动 Docker"
  exit 1
fi
ok "Docker 已运行（$(docker --version | awk '{print $3}' | tr -d ',')）"

if ! docker compose version > /dev/null 2>&1; then
  err "请安装 Docker Compose v2"
  exit 1
fi
ok "Docker Compose 已就绪"

# ── 构建镜像 ──────────────────────────────────────────────────────────────────
step "Step 2/5: 构建 Docker 镜像"
info "构建基础镜像（路由器 + 以太坊节点）..."
docker compose build \
  39e016aa9e819f203ebc1809245a5818 \
  f1d53a66de3c35d8a921558f3b4bdbbd \
  2>&1 | grep -E "Built|Error|error" | tail -5

info "构建监控和仿真镜像..."
docker compose build \
  eth_node_cleaner eth_node_monitoring eth_simulation \
  2>&1 | grep -E "Built|Error|error" | tail -5

ok "所有镜像构建完成"

# ── 启动数据库 ────────────────────────────────────────────────────────────────
step "Step 3/5: 启动数据库服务"
docker compose up -d postgresql redis neo4j

info "等待数据库健康检查..."
TIMEOUT=60
for i in $(seq 1 $TIMEOUT); do
  PG_OK=$(docker exec eth_postgresql pg_isready -U postgres 2>/dev/null && echo ok || echo no)
  RD_OK=$(docker exec eth_redis redis-cli ping 2>/dev/null | grep -c PONG || echo 0)
  if [ "$PG_OK" = "ok" ] && [ "$RD_OK" = "1" ]; then
    break
  fi
  [ $((i % 10)) -eq 0 ] && info "等待中... (${i}s)"
  sleep 1
done

# 修复 PostgreSQL md5 认证（兼容 asyncpg 旧版本）
docker exec eth_postgresql bash -c "
  grep -q 'scram-sha-256' /var/lib/postgresql/data/pg_hba.conf 2>/dev/null && {
    sed -i 's/host all all all scram-sha-256/host all all all md5/' /var/lib/postgresql/data/pg_hba.conf
    psql -U postgres -c \"SELECT pg_reload_conf()\" > /dev/null 2>&1
    psql -U postgres -c \"ALTER USER postgres WITH PASSWORD 'password'\" > /dev/null 2>&1
  }
" 2>/dev/null || true

ok "PostgreSQL ✅  Redis ✅  Neo4j 启动中（后台继续初始化）"

# ── 启动网络 ──────────────────────────────────────────────────────────────────
step "Step 4/5: 启动完整以太坊网络"
docker compose up -d

ok "所有容器已启动（$(docker compose ps --status running -q | wc -l | tr -d ' ')个）"
echo ""
info "等待以太坊链初始化（约5分钟）..."
info "进度：BeaconSetup 生成创世块 → Lighthouse 建立共识 → 出块"

BLOCK=0
WAIT=0
MAX_WAIT=360  # 6分钟超时
while [ $BLOCK -lt 5 ] && [ $WAIT -lt $MAX_WAIT ]; do
  sleep 10
  WAIT=$((WAIT + 10))
  BLOCK=$(curl -sf -X POST http://localhost:8545 \
    -H "Content-Type: application/json" \
    -d '{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}' 2>/dev/null \
    | python3 -c "import sys,json; print(int(json.load(sys.stdin)['result'],16))" 2>/dev/null || echo 0)
  printf "\r  ⏳ 已等待 %ds | 区块高度: #%s " "$WAIT" "$BLOCK"
done
echo ""

if [ "$BLOCK" -lt 5 ]; then
  warn "链未能在 ${MAX_WAIT}s 内达到区块 #5，可能需要更多时间"
  warn "可以稍后运行: ./start.sh status 查看状态"
else
  ok "以太坊链正常运行！区块高度: #${BLOCK}"
fi

# ── 部署监控 Agent ────────────────────────────────────────────────────────────
step "Step 5/5: 热部署节点监控 Agent"
chmod +x deploy_monitoring.sh
./deploy_monitoring.sh 2>&1 | grep -E "✅|❌|成功|失败|汇总"

# ── 启动完成 ──────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}"
echo "╔══════════════════════════════════════════════════════════╗"
echo "║                  ✅ 启动完成！                           ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo -e "${NC}"

BLOCK=$(curl -sf -X POST http://localhost:8545 \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}' 2>/dev/null \
  | python3 -c "import sys,json; print(int(json.load(sys.stdin)['result'],16))" 2>/dev/null || echo "初始化中")

echo "  区块高度:          #${BLOCK}"
echo "  eth_node_cleaner:  http://localhost:8888"
echo "  eth_node_monitoring: http://localhost:9999"
echo "  Neo4j 浏览器:     http://localhost:7475  (neo4j/1qaz@WSX)"
echo "  网络可视化:        http://localhost:8080"
echo "  以太坊查看器:      http://localhost:5000"
echo ""
echo "  常用命令:"
echo "    ./start.sh status   — 查看运行状态"
echo "    ./start.sh logs     — 查看实时日志"
echo "    ./start.sh stop     — 停止所有服务"
echo "    ./deploy_monitoring.sh --status  — 查看 Agent 状态"
echo ""
echo "  监控 API 示例:"
echo "    curl http://localhost:9999/api/v1/monitoring/statistics"
echo "    curl http://localhost:9999/api/v1/monitoring/topology"

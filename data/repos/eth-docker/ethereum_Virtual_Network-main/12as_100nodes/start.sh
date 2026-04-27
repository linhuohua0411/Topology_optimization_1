#!/bin/bash
# =============================================================================
# start.sh — 12as_100nodes 一键启动脚本
# 用法:
#   ./start.sh            启动完整网络（首次或重新启动）
#   ./start.sh stop       停止所有服务
#   ./start.sh restart    重启所有服务
#   ./start.sh status     查看服务状态
#   ./start.sh logs       查看关键日志
#   ./start.sh build-only 仅构建镜像（不启动）
# 注意: 需要服务器内存 ≥ 32GB，推荐 62GB
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

# ── 配置 ──────────────────────────────────────────────────────────────────────
AS_LIST="101 102 103 104 105 106 107 108 109 110 111 112"
HOSTS_PER_AS="0 1 2 3 4 5 6 7 8"
CHAIN_WAIT_SECS=360     # 等待出块超时（秒）
AGENT_SAMPLE=5          # Agent 验证抽样节点数

# ── 子命令 ────────────────────────────────────────────────────────────────────
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
    RUNNING=$(docker ps --format '{{.Names}}' | grep -E 'as[0-9]+|eth_' | wc -l | tr -d ' ')
    ETH_NODES=$(docker ps --format '{{.Names}}' | grep -c 'Ethereum-POS' || echo 0)
    ROUTERS=$(docker ps --format '{{.Names}}' | grep -c 'brd\|rs_ix' || echo 0)
    MONITOR=$(docker ps --format '{{.Names}}' | grep -c 'eth_node\|eth_sim\|eth_pos\|eth_red\|eth_neo' || echo 0)
    echo -e "${BOLD}=== 容器运行状态（共 ${RUNNING} 个）===${NC}"
    echo "  以太坊节点: ${ETH_NODES}/108"
    echo "  BGP路由器:  ${ROUTERS}/24"
    echo "  监控服务:   $(docker ps --format '{{.Names}}' | grep -c 'eth_node_cleaner\|eth_node_monitoring\|eth_simulation\|eth_postgresql\|eth_redis\|eth_neo4j' || echo 0)/6"
    echo "  （运行 'docker compose ps' 查看全部容器）"
    echo ""
    BLOCK=$(docker exec as101h-Ethereum-POS-3-10.101.0.73 \
      curl -sf -X POST http://localhost:8545 \
      -H "Content-Type: application/json" \
      -d '{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}' 2>/dev/null \
      | python3 -c "import sys,json; print(int(json.load(sys.stdin)['result'],16))" 2>/dev/null || echo "未就绪")
    echo -e "${BOLD}=== 以太坊链状态 ===${NC}"
    echo "  区块高度: #${BLOCK}"
    echo ""
    echo -e "${BOLD}=== 监控 API ===${NC}"
    curl -sf http://localhost:9999/api/v1/monitoring/statistics 2>/dev/null | \
      python3 -c "import sys,json; d=json.load(sys.stdin); s=d['summary']; n=d['node_statistics']; print(f'  事件总数={s[\"total_events_received\"]} | exec节点={n[\"exec_node_count\"]} | cons节点={n[\"cons_node_count\"]} | cons连接={n[\"cons_link_count\"]}')" 2>/dev/null || warn "  eth_node_monitoring 未就绪"
    exit 0 ;;
  logs)
    docker compose logs -f eth_node_cleaner eth_simulation eth_node_monitoring
    exit 0 ;;
  build-only)
    step "仅构建镜像..."
    docker compose build eth_node_cleaner eth_node_monitoring eth_simulation
    ok "镜像构建完成"
    exit 0 ;;
  start|"") : ;;
  *)
    echo "用法: $0 [start|stop|restart|status|logs|build-only]"
    exit 1 ;;
esac

# ══════════════════════════════════════════════════════════════════════════════
echo -e "${BOLD}"
echo "╔══════════════════════════════════════════════════════════╗"
echo "║   以太坊虚拟网络仿真平台 — 12as_100nodes 一键启动        ║"
echo "║   拓扑: 12个AS, 108个节点, 4个IXP, 107个PoS验证者        ║"
echo "║   预计启动时间: 约10分钟  内存需求: ≥32GB                ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# ── 检查 Docker ───────────────────────────────────────────────────────────────
step "Step 1/6: 环境检查"
if ! docker info > /dev/null 2>&1; then err "Docker 未运行"; exit 1; fi
ok "Docker 已运行"

MEM_GB=$(free -g 2>/dev/null | awk '/^Mem:/{print $2}' || echo 0)
if [ "$MEM_GB" -lt 30 ]; then
  warn "可用内存 ${MEM_GB}GB 可能不足（推荐 ≥32GB）"
else
  ok "内存充足: ${MEM_GB}GB"
fi

# ── 构建监控镜像 ───────────────────────────────────────────────────────────────
step "Step 2/6: 构建监控和仿真镜像"
info "（跳过节点镜像构建，使用已有镜像）"
docker compose build eth_node_cleaner eth_node_monitoring eth_simulation \
  2>&1 | grep -E "Built|Error|error" | tail -5
ok "监控镜像构建完成"

# ── 启动数据库 ────────────────────────────────────────────────────────────────
step "Step 3/6: 启动数据库服务"
docker compose up -d postgresql redis neo4j

info "等待数据库就绪..."
for i in $(seq 1 60); do
  PG_OK=$(docker exec eth_postgresql pg_isready -U postgres 2>/dev/null && echo ok || echo no)
  RD_OK=$(docker exec eth_redis redis-cli ping 2>/dev/null | grep -c PONG || echo 0)
  [ "$PG_OK" = "ok" ] && [ "$RD_OK" = "1" ] && break
  sleep 1
done

# 修复 PostgreSQL md5 认证
docker exec eth_postgresql bash -c "
  grep -q 'scram-sha-256' /var/lib/postgresql/data/pg_hba.conf 2>/dev/null && {
    sed -i 's/host all all all scram-sha-256/host all all all md5/' /var/lib/postgresql/data/pg_hba.conf
    psql -U postgres -c \"SELECT pg_reload_conf()\" > /dev/null 2>&1
    psql -U postgres -c \"ALTER USER postgres WITH PASSWORD 'password'\" > /dev/null 2>&1
  }
" 2>/dev/null || true

ok "数据库已就绪"

# ── 启动监控服务和基础镜像 ─────────────────────────────────────────────────────
step "Step 4/6: 启动监控服务和路由基础设施"
docker compose up -d \
  39e016aa9e819f203ebc1809245a5818 \
  f1d53a66de3c35d8a921558f3b4bdbbd \
  eth_node_cleaner eth_node_monitoring eth_simulation

# 启动所有路由器和IXP（24个容器）
info "启动 BGP/OSPF 路由器..."
ROUTERS=""
for as in $AS_LIST; do
  ROUTERS="$ROUTERS brdnode_${as}_router0"
done
ROUTERS="$ROUTERS brdnode_2_r51 brdnode_2_r52 brdnode_2_r53 brdnode_2_r54"
ROUTERS="$ROUTERS brdnode_21_r51 brdnode_22_r52 brdnode_23_r53 brdnode_24_r54"
ROUTERS="$ROUTERS rs_ix_ix51 rs_ix_ix52 rs_ix_ix53 rs_ix_ix54"
docker compose up -d $ROUTERS 2>&1 | tail -3
ok "路由器和IXP已启动"

# ── 分批启动以太坊节点 ─────────────────────────────────────────────────────────
step "Step 5/6: 分批启动以太坊节点（共108个）"
info "先启动 AS101（含 BeaconSetup + BootNode）..."

# AS101 优先启动（BeaconSetup需要其他节点的Geth先运行）
AS101_NODES=""
for h in $HOSTS_PER_AS; do AS101_NODES="$AS101_NODES hnode_101_host${h}"; done
docker compose up -d $AS101_NODES 2>&1 | tail -2
ok "AS101（9个节点）已启动"

# 等待 AS101 的 Geth 初始化（BeaconSetup 需要 POS-3 出块）
info "等待 AS101 Geth 初始化（约30秒）..."
sleep 30

# 其余11个AS（每批启动一个AS，避免内存峰值）
info "启动 AS102-AS112 节点..."
TOTAL=9
for as in 102 103 104 105 106 107 108 109 110 111 112; do
  NODES=""
  for h in $HOSTS_PER_AS; do NODES="$NODES hnode_${as}_host${h}"; done
  docker compose up -d $NODES 2>&1 | tail -1
  TOTAL=$((TOTAL + 9))
  printf "\r  已启动 %d/108 个节点..." "$TOTAL"
done
echo ""
ok "全部 108 个以太坊节点已启动"

# ── 等待链初始化 ───────────────────────────────────────────────────────────────
info "等待以太坊链初始化（BeaconSetup 完成创世 + Lighthouse 共识）..."
BLOCK=0
WAIT=0
while [ $BLOCK -lt 5 ] && [ $WAIT -lt $CHAIN_WAIT_SECS ]; do
  sleep 15
  WAIT=$((WAIT + 15))
  BLOCK=$(docker exec as101h-Ethereum-POS-3-10.101.0.73 \
    curl -sf -X POST http://localhost:8545 \
    -H "Content-Type: application/json" \
    -d '{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}' 2>/dev/null \
    | python3 -c "import sys,json; print(int(json.load(sys.stdin)['result'],16))" 2>/dev/null || echo 0)
  LH_LOG=$(docker logs as101h-Ethereum-BootNode-10.101.0.72 2>&1 \
    | grep -oE 'slot: [0-9]+' | tail -1 | awk '{print $2}' || echo "0")
  printf "\r  ⏳ %ds | 区块:#%s | Lighthouse slot:%s " "$WAIT" "$BLOCK" "$LH_LOG"
done
echo ""

if [ "$BLOCK" -ge 5 ]; then
  ok "以太坊链正常运行！区块高度: #${BLOCK}"
else
  warn "链初始化可能需要更多时间（当前区块 #${BLOCK}）"
  warn "可运行 ./start.sh status 持续检查"
fi

# ── 部署监控 Agent ────────────────────────────────────────────────────────────
step "Step 6/6: 热部署节点监控 Agent（107个节点）"
chmod +x deploy_monitoring.sh
./deploy_monitoring.sh 2>&1 | grep -E "✅|❌|成功:|失败:|跳过:"

# ── 完成 ──────────────────────────────────────────────────────────────────────
CONTAINERS=$(docker ps -q | wc -l | tr -d ' ')
BLOCK=$(docker exec as101h-Ethereum-POS-3-10.101.0.73 \
  curl -sf -X POST http://localhost:8545 \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}' 2>/dev/null \
  | python3 -c "import sys,json; print(int(json.load(sys.stdin)['result'],16))" 2>/dev/null || echo "初始化中")

echo ""
echo -e "${BOLD}${GREEN}"
echo "╔══════════════════════════════════════════════════════════╗"
echo "║                  ✅ 启动完成！                           ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo -e "${NC}"
echo "  运行容器数:        ${CONTAINERS}"
echo "  以太坊区块:        #${BLOCK}"
echo "  eth_node_cleaner:  http://localhost:8888"
echo "  eth_node_monitoring: http://localhost:9999"
echo "  Neo4j 浏览器:     http://localhost:7475  (neo4j/1qaz@WSX)"
echo ""
echo "  常用命令:"
echo "    ./start.sh status   — 查看运行状态"
echo "    ./start.sh logs     — 查看实时日志"
echo "    ./start.sh stop     — 停止所有服务"
echo ""
echo "  监控 API:"
echo "    curl http://localhost:9999/api/v1/monitoring/statistics"

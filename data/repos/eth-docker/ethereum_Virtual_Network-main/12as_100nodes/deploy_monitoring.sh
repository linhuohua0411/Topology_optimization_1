#!/bin/bash
# =============================================================================
# deploy_monitoring.sh — 将 eth_node_monitoring_agent 热部署到运行中的节点容器
#
# 使用方法:
#   ./deploy_monitoring.sh              # 部署到所有以太坊节点
#   ./deploy_monitoring.sh --stop       # 停止所有节点的监控 Agent
#   ./deploy_monitoring.sh --status     # 查看各节点 Agent 运行状态
#   ./deploy_monitoring.sh --logs       # 实时查看所有节点 Agent 日志
#
# 设计说明:
#   1. 先正常启动以太坊网络 (docker compose up -d)
#   2. 等待链稳定后执行此脚本（建议等待至少 5 分钟）
#   3. 脚本通过 docker cp 将 Agent 复制进容器，再用 docker exec 启动
#   4. Agent 与 Geth/Lighthouse 共存于同一容器，以后台进程方式运行
#   5. 可随时重新执行此脚本（自动热更新 Agent 代码，不影响以太坊进程）
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_FILE="$SCRIPT_DIR/eth_node_monitoring/eth_node_monitoring_agent.py"

# ── 配置 ────────────────────────────────────────────────────────────────────
CENTRAL_COLLECTOR_URL="${CENTRAL_COLLECTOR_URL:-http://eth_node_cleaner:8888}"
COLLECT_INTERVAL="${NODE_COLLECT_INTERVAL:-30}"
HEARTBEAT_INTERVAL="${HEARTBEAT_INTERVAL:-30}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"
AGENT_DEST="/usr/local/bin/eth_node_monitoring_agent.py"
AGENT_LOG="/var/log/eth_monitoring_agent.log"

# ── 目标节点（容器名 → 节点IP:是否有验证者） ────────────────────────────────
declare -A NODES
NODES["as101h-Ethereum-BootNode-10.101.0.72"]="10.101.0.72:false"
NODES["as101h-Ethereum-POS-3-10.101.0.71"]="10.101.0.71:true"
NODES["as101h-Ethereum-POS-4-10.101.0.72"]="10.101.0.72:true"
NODES["as101h-Ethereum-POS-5-10.101.0.73"]="10.101.0.73:true"
NODES["as101h-Ethereum-POS-6-10.101.1.71"]="10.101.1.71:true"
NODES["as101h-Ethereum-POS-7-10.101.1.72"]="10.101.1.72:true"
NODES["as101h-Ethereum-POS-8-10.101.1.73"]="10.101.1.73:true"
NODES["as101h-Ethereum-POS-9-10.101.2.71"]="10.101.2.71:true"
NODES["as102h-Ethereum-POS-10-10.102.0.71"]="10.102.0.71:true"
NODES["as102h-Ethereum-POS-11-10.102.0.72"]="10.102.0.72:true"
NODES["as102h-Ethereum-POS-12-10.102.0.73"]="10.102.0.73:true"
NODES["as102h-Ethereum-POS-13-10.102.1.71"]="10.102.1.71:true"
NODES["as102h-Ethereum-POS-14-10.102.1.72"]="10.102.1.72:true"
NODES["as102h-Ethereum-POS-15-10.102.1.73"]="10.102.1.73:true"
NODES["as102h-Ethereum-POS-16-10.102.2.71"]="10.102.2.71:true"
NODES["as102h-Ethereum-POS-17-10.102.2.72"]="10.102.2.72:true"
NODES["as102h-Ethereum-POS-18-10.102.2.73"]="10.102.2.73:true"
NODES["as103h-Ethereum-POS-19-10.103.0.71"]="10.103.0.71:true"
NODES["as103h-Ethereum-POS-20-10.103.0.72"]="10.103.0.72:true"
NODES["as103h-Ethereum-POS-21-10.103.0.73"]="10.103.0.73:true"
NODES["as103h-Ethereum-POS-22-10.103.1.71"]="10.103.1.71:true"
NODES["as103h-Ethereum-POS-23-10.103.1.72"]="10.103.1.72:true"
NODES["as103h-Ethereum-POS-24-10.103.1.73"]="10.103.1.73:true"
NODES["as103h-Ethereum-POS-25-10.103.2.71"]="10.103.2.71:true"
NODES["as103h-Ethereum-POS-26-10.103.2.72"]="10.103.2.72:true"
NODES["as103h-Ethereum-POS-27-10.103.2.73"]="10.103.2.73:true"
NODES["as104h-Ethereum-POS-28-10.104.0.71"]="10.104.0.71:true"
NODES["as104h-Ethereum-POS-29-10.104.0.72"]="10.104.0.72:true"
NODES["as104h-Ethereum-POS-30-10.104.0.73"]="10.104.0.73:true"
NODES["as104h-Ethereum-POS-31-10.104.1.71"]="10.104.1.71:true"
NODES["as104h-Ethereum-POS-32-10.104.1.72"]="10.104.1.72:true"
NODES["as104h-Ethereum-POS-33-10.104.1.73"]="10.104.1.73:true"
NODES["as104h-Ethereum-POS-34-10.104.2.71"]="10.104.2.71:true"
NODES["as104h-Ethereum-POS-35-10.104.2.72"]="10.104.2.72:true"
NODES["as104h-Ethereum-POS-36-10.104.2.73"]="10.104.2.73:true"
NODES["as105h-Ethereum-POS-37-10.105.0.71"]="10.105.0.71:true"
NODES["as105h-Ethereum-POS-38-10.105.0.72"]="10.105.0.72:true"
NODES["as105h-Ethereum-POS-39-10.105.0.73"]="10.105.0.73:true"
NODES["as105h-Ethereum-POS-40-10.105.1.71"]="10.105.1.71:true"
NODES["as105h-Ethereum-POS-41-10.105.1.72"]="10.105.1.72:true"
NODES["as105h-Ethereum-POS-42-10.105.1.73"]="10.105.1.73:true"
NODES["as105h-Ethereum-POS-43-10.105.2.71"]="10.105.2.71:true"
NODES["as105h-Ethereum-POS-44-10.105.2.72"]="10.105.2.72:true"
NODES["as105h-Ethereum-POS-45-10.105.2.73"]="10.105.2.73:true"
NODES["as106h-Ethereum-POS-46-10.106.0.71"]="10.106.0.71:true"
NODES["as106h-Ethereum-POS-47-10.106.0.72"]="10.106.0.72:true"
NODES["as106h-Ethereum-POS-48-10.106.0.73"]="10.106.0.73:true"
NODES["as106h-Ethereum-POS-49-10.106.1.71"]="10.106.1.71:true"
NODES["as106h-Ethereum-POS-50-10.106.1.72"]="10.106.1.72:true"
NODES["as106h-Ethereum-POS-51-10.106.1.73"]="10.106.1.73:true"
NODES["as106h-Ethereum-POS-52-10.106.2.71"]="10.106.2.71:true"
NODES["as106h-Ethereum-POS-53-10.106.2.72"]="10.106.2.72:true"
NODES["as106h-Ethereum-POS-54-10.106.2.73"]="10.106.2.73:true"
NODES["as107h-Ethereum-POS-55-10.107.0.71"]="10.107.0.71:true"
NODES["as107h-Ethereum-POS-56-10.107.0.72"]="10.107.0.72:true"
NODES["as107h-Ethereum-POS-57-10.107.0.73"]="10.107.0.73:true"
NODES["as107h-Ethereum-POS-58-10.107.1.71"]="10.107.1.71:true"
NODES["as107h-Ethereum-POS-59-10.107.1.72"]="10.107.1.72:true"
NODES["as107h-Ethereum-POS-60-10.107.1.73"]="10.107.1.73:true"
NODES["as107h-Ethereum-POS-61-10.107.2.71"]="10.107.2.71:true"
NODES["as107h-Ethereum-POS-62-10.107.2.72"]="10.107.2.72:true"
NODES["as107h-Ethereum-POS-63-10.107.2.73"]="10.107.2.73:true"
NODES["as108h-Ethereum-POS-64-10.108.0.71"]="10.108.0.71:true"
NODES["as108h-Ethereum-POS-65-10.108.0.72"]="10.108.0.72:true"
NODES["as108h-Ethereum-POS-66-10.108.0.73"]="10.108.0.73:true"
NODES["as108h-Ethereum-POS-67-10.108.1.71"]="10.108.1.71:true"
NODES["as108h-Ethereum-POS-68-10.108.1.72"]="10.108.1.72:true"
NODES["as108h-Ethereum-POS-69-10.108.1.73"]="10.108.1.73:true"
NODES["as108h-Ethereum-POS-70-10.108.2.71"]="10.108.2.71:true"
NODES["as108h-Ethereum-POS-71-10.108.2.72"]="10.108.2.72:true"
NODES["as108h-Ethereum-POS-72-10.108.2.73"]="10.108.2.73:true"
NODES["as109h-Ethereum-POS-73-10.109.0.71"]="10.109.0.71:true"
NODES["as109h-Ethereum-POS-74-10.109.0.72"]="10.109.0.72:true"
NODES["as109h-Ethereum-POS-75-10.109.0.73"]="10.109.0.73:true"
NODES["as109h-Ethereum-POS-76-10.109.1.71"]="10.109.1.71:true"
NODES["as109h-Ethereum-POS-77-10.109.1.72"]="10.109.1.72:true"
NODES["as109h-Ethereum-POS-78-10.109.1.73"]="10.109.1.73:true"
NODES["as109h-Ethereum-POS-79-10.109.2.71"]="10.109.2.71:true"
NODES["as109h-Ethereum-POS-80-10.109.2.72"]="10.109.2.72:true"
NODES["as109h-Ethereum-POS-81-10.109.2.73"]="10.109.2.73:true"
NODES["as110h-Ethereum-POS-82-10.110.0.71"]="10.110.0.71:true"
NODES["as110h-Ethereum-POS-83-10.110.0.72"]="10.110.0.72:true"
NODES["as110h-Ethereum-POS-84-10.110.0.73"]="10.110.0.73:true"
NODES["as110h-Ethereum-POS-85-10.110.1.71"]="10.110.1.71:true"
NODES["as110h-Ethereum-POS-86-10.110.1.72"]="10.110.1.72:true"
NODES["as110h-Ethereum-POS-87-10.110.1.73"]="10.110.1.73:true"
NODES["as110h-Ethereum-POS-88-10.110.2.71"]="10.110.2.71:true"
NODES["as110h-Ethereum-POS-89-10.110.2.72"]="10.110.2.72:true"
NODES["as110h-Ethereum-POS-90-10.110.2.73"]="10.110.2.73:true"
NODES["as111h-Ethereum-POS-91-10.111.0.71"]="10.111.0.71:true"
NODES["as111h-Ethereum-POS-92-10.111.0.72"]="10.111.0.72:true"
NODES["as111h-Ethereum-POS-93-10.111.0.73"]="10.111.0.73:true"
NODES["as111h-Ethereum-POS-94-10.111.1.71"]="10.111.1.71:true"
NODES["as111h-Ethereum-POS-95-10.111.1.72"]="10.111.1.72:true"
NODES["as111h-Ethereum-POS-96-10.111.1.73"]="10.111.1.73:true"
NODES["as111h-Ethereum-POS-97-10.111.2.71"]="10.111.2.71:true"
NODES["as111h-Ethereum-POS-98-10.111.2.72"]="10.111.2.72:true"
NODES["as111h-Ethereum-POS-99-10.111.2.73"]="10.111.2.73:true"
NODES["as112h-Ethereum-POS-100-10.112.0.71"]="10.112.0.71:true"
NODES["as112h-Ethereum-POS-101-10.112.0.72"]="10.112.0.72:true"
NODES["as112h-Ethereum-POS-102-10.112.0.73"]="10.112.0.73:true"
NODES["as112h-Ethereum-POS-103-10.112.1.71"]="10.112.1.71:true"
NODES["as112h-Ethereum-POS-104-10.112.1.72"]="10.112.1.72:true"
NODES["as112h-Ethereum-POS-105-10.112.1.73"]="10.112.1.73:true"
NODES["as112h-Ethereum-POS-106-10.112.2.71"]="10.112.2.71:true"
NODES["as112h-Ethereum-POS-107-10.112.2.72"]="10.112.2.72:true"
NODES["as112h-Ethereum-POS-108-10.112.2.73"]="10.112.2.73:true"

# ── 颜色输出 ─────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info()    { echo -e "${GREEN}[INFO]${NC}  $*"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $*"; }
log_section() { echo -e "\n${CYAN}══════════════════════════════════════════${NC}"; echo -e "${CYAN}  $*${NC}"; echo -e "${CYAN}══════════════════════════════════════════${NC}"; }

# ── 子命令：查看状态 ─────────────────────────────────────────────────────────
cmd_status() {
    log_section "各节点 Agent 运行状态"
    for container in "${!NODES[@]}"; do
        INFO="${NODES[$container]}"
        NODE_IP="${INFO%%:*}"
        if ! docker ps --format "{{.Names}}" | grep -q "^${container}$" 2>/dev/null; then
            echo -e "  ${RED}●${NC} $container — 容器未运行"
            continue
        fi
        # 检查 agent 进程是否存在
        if docker exec "$container" pgrep -f eth_node_monitoring_agent.py > /dev/null 2>&1; then
            PID=$(docker exec "$container" pgrep -f eth_node_monitoring_agent.py | head -1)
            echo -e "  ${GREEN}●${NC} $container (${NODE_IP}) — Agent 运行中 PID=${PID}"
        else
            echo -e "  ${RED}●${NC} $container (${NODE_IP}) — Agent 未运行"
        fi
    done
    echo ""
}

# ── 子命令：停止所有 Agent ──────────────────────────────────────────────────
cmd_stop() {
    log_section "停止所有节点的监控 Agent"
    for container in "${!NODES[@]}"; do
        if ! docker ps --format "{{.Names}}" | grep -q "^${container}$" 2>/dev/null; then
            continue
        fi
        if docker exec "$container" pgrep -f eth_node_monitoring_agent.py > /dev/null 2>&1; then
            docker exec "$container" pkill -f eth_node_monitoring_agent.py 2>/dev/null || true
            log_info "已停止 $container 的 Agent"
        else
            log_warn "$container: Agent 未在运行"
        fi
    done
    echo ""
}

# ── 子命令：实时查看日志 ─────────────────────────────────────────────────────
cmd_logs() {
    log_section "实时日志（Ctrl+C 退出）"
    # 用 tmux 或 multitail 最理想，这里用简单方式
    CONTAINERS=()
    for container in "${!NODES[@]}"; do
        if docker ps --format "{{.Names}}" | grep -q "^${container}$" 2>/dev/null; then
            CONTAINERS+=("$container")
        fi
    done

    if [ ${#CONTAINERS[@]} -eq 0 ]; then
        log_error "没有运行中的容器"
        exit 1
    fi

    echo "按 Ctrl+C 退出日志查看..."
    echo ""
    # 轮询日志（简单实现，生产环境建议使用 multitail 或 promtail）
    while true; do
        for container in "${CONTAINERS[@]}"; do
            INFO="${NODES[$container]}"
            NODE_IP="${INFO%%:*}"
            LINES=$(docker exec "$container" tail -3 "$AGENT_LOG" 2>/dev/null | \
                    sed "s/^/  [${NODE_IP}] /")
            if [ -n "$LINES" ]; then
                echo "$LINES"
            fi
        done
        sleep 5
    done
}

# ── 主部署逻辑 ───────────────────────────────────────────────────────────────
cmd_deploy() {
    log_section "以太坊节点监控 Agent 热部署"
    echo "  Agent 文件: $AGENT_FILE"
    echo "  中央收集器: $CENTRAL_COLLECTOR_URL"
    echo "  采集间隔:   ${COLLECT_INTERVAL}s"
    echo "  心跳间隔:   ${HEARTBEAT_INTERVAL}s"
    echo ""

    # 检查 Agent 文件存在
    if [ ! -f "$AGENT_FILE" ]; then
        log_error "Agent 文件不存在: $AGENT_FILE"
        exit 1
    fi

    SUCCESS=0
    SKIPPED=0
    FAILED=0

    for container in "${!NODES[@]}"; do
        INFO="${NODES[$container]}"
        NODE_IP="${INFO%%:*}"
        HAS_VAL="${INFO##*:}"

        echo -e "\n${CYAN}── $container (${NODE_IP}) ──${NC}"

        # 检查容器是否运行
        if ! docker ps --format "{{.Names}}" | grep -q "^${container}$" 2>/dev/null; then
            log_warn "容器未运行，跳过"
            ((SKIPPED++)) || true
            continue
        fi

        # 检查容器内是否有 Python3
        if ! docker exec "$container" which python3 > /dev/null 2>&1; then
            log_error "容器内无 python3，跳过"
            ((FAILED++)) || true
            continue
        fi

        # 步骤1：停止已有的 Agent（热更新场景）
        if docker exec "$container" pgrep -f eth_node_monitoring_agent.py > /dev/null 2>&1; then
            docker exec "$container" pkill -f eth_node_monitoring_agent.py 2>/dev/null || true
            log_info "已停止旧版 Agent"
            sleep 1
        fi

        # 步骤2：复制 Agent 脚本到容器
        if docker cp "$AGENT_FILE" "${container}:${AGENT_DEST}" 2>/dev/null; then
            log_info "已复制 Agent → ${AGENT_DEST}"
        else
            log_error "复制失败"
            ((FAILED++)) || true
            continue
        fi

        # 步骤3：确保日志目录存在
        docker exec "$container" bash -c "mkdir -p $(dirname $AGENT_LOG)" 2>/dev/null || true

        # 步骤4：后台启动 Agent（nohup + 重定向日志）
        docker exec -d "$container" bash -c "
            CONTAINER_NAME='${container}' \
            NODE_IP='${NODE_IP}' \
            HAS_VALIDATOR='${HAS_VAL}' \
            CENTRAL_COLLECTOR_URL='${CENTRAL_COLLECTOR_URL}' \
            NODE_COLLECT_INTERVAL='${COLLECT_INTERVAL}' \
            HEARTBEAT_INTERVAL='${HEARTBEAT_INTERVAL}' \
            LOG_LEVEL='${LOG_LEVEL}' \
            nohup python3 '${AGENT_DEST}' >> '${AGENT_LOG}' 2>&1
        "

        # 步骤5：等待2秒验证 Agent 是否成功启动
        sleep 2
        if docker exec "$container" pgrep -f eth_node_monitoring_agent.py > /dev/null 2>&1; then
            PID=$(docker exec "$container" pgrep -f eth_node_monitoring_agent.py | head -1)
            log_info "✅ Agent 启动成功 PID=${PID} 日志→ ${AGENT_LOG}"
            ((SUCCESS++)) || true
        else
            # 打印最后几行日志帮助定位问题
            log_error "Agent 启动失败！最近日志："
            docker exec "$container" tail -10 "$AGENT_LOG" 2>/dev/null | sed 's/^/    /' || true
            ((FAILED++)) || true
        fi
    done

    echo ""
    log_section "部署结果汇总"
    echo -e "  ${GREEN}成功: ${SUCCESS}${NC}  ${YELLOW}跳过: ${SKIPPED}${NC}  ${RED}失败: ${FAILED}${NC}"

    if [ "$SUCCESS" -gt 0 ]; then
        echo ""
        echo "  查看 Agent 状态: ./deploy_monitoring.sh --status"
        echo "  查看实时日志:   ./deploy_monitoring.sh --logs"
        echo "  停止所有 Agent: ./deploy_monitoring.sh --stop"
        echo ""
        echo "  各节点 Agent 日志位于容器内: ${AGENT_LOG}"
        echo "  快速查看某节点日志:"
        echo "    docker exec as151h-Ethereum-POS-3-10.151.0.73 tail -f ${AGENT_LOG}"
    fi
}

# ── 入口 ─────────────────────────────────────────────────────────────────────
case "${1:-deploy}" in
    --stop)    cmd_stop ;;
    --status)  cmd_status ;;
    --logs)    cmd_logs ;;
    --help|-h)
        echo "用法: $0 [--stop|--status|--logs|--help]"
        echo "  (无参数)   部署或热更新 Agent 到所有运行中的以太坊节点"
        echo "  --stop     停止所有节点的 Agent"
        echo "  --status   查看各节点 Agent 运行状态"
        echo "  --logs     实时查看所有节点 Agent 日志（Ctrl+C 退出）"
        ;;
    *)         cmd_deploy ;;
esac

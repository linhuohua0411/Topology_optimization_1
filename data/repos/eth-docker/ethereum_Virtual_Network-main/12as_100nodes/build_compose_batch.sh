#!/bin/bash
# build_compose_batch.sh
#
# 用于按特定顺序（Dummy, 路由, 主机, 可视化）分批构建 docker-compose.yml 中的服务，
# 然后在所有构建完成后，使用 'docker compose down' 停止并移除它们。
# 生成日期: $(date)

# --- 脚本行为设置 ---
set -e  # 如果任何命令以非零状态退出，则立即退出脚本。

# --- 可配置参数 ---
DEFAULT_BATCH_SIZE=20 # 默认批次大小
BATCH_SIZE=${BATCH_SIZE:-$DEFAULT_BATCH_SIZE} # 允许通过环境变量覆盖

# === 重要: 请将 docker-compose.txt 的内容保存为 docker-compose.yml ===
# === 或者修改下面的 COMPOSE_FILE 变量为你实际的文件名         ===
COMPOSE_FILE="docker-compose.yml" # 明确指定操作的Compose文件

# --- 日志和项目名称 ---
LOG_PREFIX="[BUILD_ORDERED_BATCH]"
COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-$(basename "$(pwd)")}"

# --- 辅助函数定义 ---
log_info() {
    echo "${LOG_PREFIX} INFO: $1"
}

log_warn() {
    echo "${LOG_PREFIX} WARN: $1" >&2
}

log_error() {
    echo "${LOG_PREFIX} ERROR: $1" >&2
}

# --- 主逻辑开始 ---

log_info "开始按顺序分批构建来自 '${COMPOSE_FILE}' 中的服务，完成后将全部停止。"

if [ ! -f "${COMPOSE_FILE}" ]; then
    log_error "错误: Docker Compose 文件 '${COMPOSE_FILE}' 在当前目录未找到！"
    log_error "请确保将提供的 docker-compose.txt 内容保存为 '${COMPOSE_FILE}' 或更新脚本中的 COMPOSE_FILE 变量。"
    exit 1
fi

log_info "正在从 '${COMPOSE_FILE}' 读取并分类服务列表..."
ALL_SERVICES_FROM_FILE=()
# 使用 'docker compose' (V2命令)
while IFS= read -r line; do
    if [[ -n "$line" ]]; then
        ALL_SERVICES_FROM_FILE+=("$line")
    fi
done < <(docker compose -f "${COMPOSE_FILE}" config --services)

DUMMY_SERVICES=()
ROUTER_SERVICES=()
HOST_SERVICES=()
VIZ_SERVICES=()
OTHER_SERVICES=()

for service in "${ALL_SERVICES_FROM_FILE[@]}"; do
    if [[ "$service" =~ ^[0-9a-f]{32}$ ]]; then
        DUMMY_SERVICES+=("$service")
    elif [[ "$service" =~ ^brdnode_ ]] || [[ "$service" =~ ^rs_ix_ ]]; then
        ROUTER_SERVICES+=("$service")
    elif [[ "$service" =~ ^hnode_ ]]; then
        HOST_SERVICES+=("$service")
    elif [[ "$service" == "seedemu-internet-client" || "$service" == "seedemu-ether-client" ]]; then
        VIZ_SERVICES+=("$service")
    else
        log_warn "发现未明确分类的服务: '$service'。将添加到 '其他服务' 类别并在最后构建。"
        OTHER_SERVICES+=("$service")
    fi
done

# 对每个类别的服务进行排序
save_ifs=$IFS IFS=$'\n' # 保存并设置IFS以正确处理sort的输出
DUMMY_SERVICES_SORTED=($(sort <<<"${DUMMY_SERVICES[*]}"))
ROUTER_SERVICES_SORTED=($(sort <<<"${ROUTER_SERVICES[*]}"))
HOST_SERVICES_SORTED=($(sort <<<"${HOST_SERVICES[*]}"))
VIZ_SERVICES_SORTED=($(sort <<<"${VIZ_SERVICES[*]}"))
OTHER_SERVICES_SORTED=($(sort <<<"${OTHER_SERVICES[*]}"))
IFS=$save_ifs # 恢复IFS

# 组合最终的构建顺序
SERVICES_TO_BUILD=(
    "${DUMMY_SERVICES_SORTED[@]}"
    "${ROUTER_SERVICES_SORTED[@]}"
    "${HOST_SERVICES_SORTED[@]}"
    "${VIZ_SERVICES_SORTED[@]}"
    "${OTHER_SERVICES_SORTED[@]}"
)
SERVICES_TO_BUILD=(${SERVICES_TO_BUILD[@]}) # 移除因空数组产生的空元素

TOTAL_SERVICES_TO_BUILD=${#SERVICES_TO_BUILD[@]}
CURRENT_INDEX=0

log_info "从 '${COMPOSE_FILE}' 中解析并按预定顺序排列后，总共需要构建的服务数量: $TOTAL_SERVICES_TO_BUILD"
log_info "实际使用的批次大小: $BATCH_SIZE"
if [ "$COMPOSE_PROJECT_NAME" != "$(basename "$(pwd)")" ]; then
    log_info "将使用 Docker Compose 项目名: $COMPOSE_PROJECT_NAME"
fi

if [ $TOTAL_SERVICES_TO_BUILD -eq 0 ]; then
    log_warn "在 '${COMPOSE_FILE}' 中没有找到可构建的服务。脚本退出。"
    exit 0
fi

echo ""
log_info "以下服务将按类别和批次进行构建:"
idx_print=0
if [ ${#DUMMY_SERVICES_SORTED[@]} -gt 0 ]; then
  echo "--- DUMMY 服务 ---"
  for s in "${DUMMY_SERVICES_SORTED[@]}"; do printf "  %3d. %s\n" $((++idx_print)) "$s"; done
fi
if [ ${#ROUTER_SERVICES_SORTED[@]} -gt 0 ]; then
  echo "--- 路由 服务 ---"
  for s in "${ROUTER_SERVICES_SORTED[@]}"; do printf "  %3d. %s\n" $((++idx_print)) "$s"; done
fi
if [ ${#HOST_SERVICES_SORTED[@]} -gt 0 ]; then
  echo "--- 主机 服务 ---"
  for s in "${HOST_SERVICES_SORTED[@]}"; do printf "  %3d. %s\n" $((++idx_print)) "$s"; done
fi
if [ ${#VIZ_SERVICES_SORTED[@]} -gt 0 ]; then
  echo "--- 可视化 服务 ---"
  for s in "${VIZ_SERVICES_SORTED[@]}"; do printf "  %3d. %s\n" $((++idx_print)) "$s"; done
fi
if [ ${#OTHER_SERVICES_SORTED[@]} -gt 0 ]; then
  echo "--- 其他 服务 ---"
  for s in "${OTHER_SERVICES_SORTED[@]}"; do printf "  %3d. %s\n" $((++idx_print)) "$s"; done
fi
echo ""
read -p "按 Enter键 继续执行构建，或按 Ctrl+C 中止脚本..."

BUILT_SUCCESSFULLY_COUNT=0
BUILD_FAILED_BATCHES_INFO=() # 存储失败批次的信息

while [ $CURRENT_INDEX -lt $TOTAL_SERVICES_TO_BUILD ]; do
    BATCH_END_INDEX=$((CURRENT_INDEX + BATCH_SIZE))
    if [ $BATCH_END_INDEX -gt $TOTAL_SERVICES_TO_BUILD ]; then
        BATCH_END_INDEX=$TOTAL_SERVICES_TO_BUILD
    fi

    CURRENT_BATCH_SERVICES_ARRAY=()
    for ((idx=$CURRENT_INDEX; idx<$BATCH_END_INDEX; idx++)); do
        CURRENT_BATCH_SERVICES_ARRAY+=("${SERVICES_TO_BUILD[idx]}")
    done

    if [ ${#CURRENT_BATCH_SERVICES_ARRAY[@]} -eq 0 ]; then
        break # 没有服务了
    fi

    CURRENT_BATCH_SERVICES_STRING="${CURRENT_BATCH_SERVICES_ARRAY[*]}"

    log_info ""
    log_info "======================================================================"
    log_info "正在构建批次: ${CURRENT_BATCH_SERVICES_STRING}"
    log_info "服务范围: 从 $((CURRENT_INDEX + 1)) 到 $BATCH_END_INDEX (总共 $TOTAL_SERVICES_TO_BUILD 个)"
    log_info "======================================================================"

    log_info "执行命令: docker compose -f \"${COMPOSE_FILE}\" build ${CURRENT_BATCH_SERVICES_STRING}"
    if ! docker compose -f "${COMPOSE_FILE}" build ${CURRENT_BATCH_SERVICES_STRING}; then
        log_error "构建批次时发生错误: ${CURRENT_BATCH_SERVICES_STRING}"
        log_error "请检查上面的 Docker Compose 输出日志以获取详细错误信息。"
        BUILD_FAILED_BATCHES_INFO+=("批次 (${CURRENT_INDEX}-${BATCH_END_INDEX}): ${CURRENT_BATCH_SERVICES_STRING}")
        # 即使批次构建失败，也继续尝试下一个批次
    else
        log_info "批次构建成功: ${CURRENT_BATCH_SERVICES_STRING}"
        BUILT_SUCCESSFULLY_COUNT=$((BUILT_SUCCESSFULLY_COUNT + ${#CURRENT_BATCH_SERVICES_ARRAY[@]}))
    fi

    CURRENT_INDEX=$BATCH_END_INDEX

    if [ $CURRENT_INDEX -lt $TOTAL_SERVICES_TO_BUILD ]; then
        PAUSE_BETWEEN_BATCHES=1
        log_info "在开始下一批次构建前暂停 ${PAUSE_BETWEEN_BATCHES} 秒..."
        sleep $PAUSE_BETWEEN_BATCHES
    fi
done

log_info ""
log_info "======================================================================"
log_info "所有构建批次已处理完毕。"
log_info "尝试构建的服务数量: $TOTAL_SERVICES_TO_BUILD"
log_info "成功构建的服务数量 (基于批次成功): $BUILT_SUCCESSFULLY_COUNT"
if [ ${#BUILD_FAILED_BATCHES_INFO[@]} -gt 0 ]; then
    log_warn "以下批次的构建过程中报告了错误:"
    for failed_batch_info in "${BUILD_FAILED_BATCHES_INFO[@]}"; do
        log_warn "  - ${failed_batch_info}"
    done
    log_warn "请仔细检查上述日志以确定具体失败的服务。"
fi
log_info "======================================================================"
echo ""

# --- 停止并移除所有容器 ---
log_info "所有构建尝试已完成。现在将停止并移除 '${COMPOSE_FILE}' 中定义的所有容器、网络等。"
log_info "执行命令: docker compose -f \"${COMPOSE_FILE}\" down --remove-orphans"

if ! docker compose -f "${COMPOSE_FILE}" down --remove-orphans; then
    log_error "执行 'docker compose down --remove-orphans' 时发生错误。"
    log_error "请检查上面的 Docker Compose 输出日志。"
else
    log_info "'docker compose down --remove-orphans' 命令成功执行。"
fi

log_info ""
log_info "======================================================================"
log_info "脚本执行完毕。"
log_info "所有服务已按指定顺序尝试构建，并且已尝试停止和移除所有相关资源。"
log_info "======================================================================"

exit 0
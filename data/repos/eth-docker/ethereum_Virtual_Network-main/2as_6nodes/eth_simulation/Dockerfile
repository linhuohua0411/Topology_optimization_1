FROM python:3.11-slim
ARG DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# 系统依赖（iputils-ping 用于混沌代理验证；curl 用于健康检查）
RUN apt-get update && apt-get install -y --no-install-recommends \
    iputils-ping curl iproute2 \
    && rm -rf /var/lib/apt/lists/*

# Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 安装 solc 0.8.20（在构建时下载，避免运行时联网）
RUN python3 -c "\
from solcx import install_solc; \
print('正在下载 solc 0.8.20...'); \
install_solc('0.8.20'); \
print('✅ solc 安装完成')"

# 应用代码
COPY config.py reporter.py tx_generator.py chaos_agent.py contract_agent.py wan_chaos_agent.py control_api.py node_data_collector.py main.py ./

ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO

# 健康检查（检测 Geth RPC 可达性）
HEALTHCHECK --interval=30s --timeout=10s --retries=5 \
    CMD curl -sf -X POST -H "Content-Type: application/json" \
        -d '{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}' \
        ${ETH_RPC_URL:-http://10.151.0.72:8545} > /dev/null || exit 1

CMD ["python3", "main.py"]

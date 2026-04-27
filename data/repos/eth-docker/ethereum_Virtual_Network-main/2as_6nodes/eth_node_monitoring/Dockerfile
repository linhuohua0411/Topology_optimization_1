FROM python:3.10-slim
ARG DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl iputils-ping && \
    rm -rf /var/lib/apt/lists/*

# 安装Python依赖
RUN pip install --no-cache-dir \
    aiohttp==3.9.5 \
    asyncpg==0.29.0 \
    neo4j==5.14.1 \
    redis==5.0.4

COPY eth_node_monitoring.py .

ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO
ENV MONITORING_PORT=9999

EXPOSE 9999

CMD ["python3", "eth_node_monitoring.py"]

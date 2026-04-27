FROM f1d53a66de3c35d8a921558f3b4bdbbd
ARG DEBIAN_FRONTEND=noninteractive

# 设置工作目录
WORKDIR /app

# 复制所有本地依赖包
COPY wheels/*.whl ./

# 安装所有本地Python依赖包
# --no-index: 禁止从PyPI下载
# --find-links .: 在当前目录查找依赖
RUN pip install --no-index --find-links . \
    aiohttp asyncpg neo4j redis psutil web3

# 复制应用代码
COPY eth_node_cleaner.py .
COPY main.py .
COPY central_collector/ ./central_collector/

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO

# 暴露中央数据收集器端口
EXPOSE 8888

# 启动主程序
CMD ["python3", "main.py"]
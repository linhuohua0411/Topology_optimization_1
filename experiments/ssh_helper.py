"""SSH 辅助模块：连接远程服务器并执行命令。

凭证通过环境变量传入:
  ETH_SERVER_HOST, ETH_SERVER_PORT, ETH_SERVER_USER, ETH_SERVER_PASS
"""

import os
import paramiko
import time


SERVER_HOST = os.environ.get('ETH_SERVER_HOST', '111.230.44.107')
SERVER_PORT = int(os.environ.get('ETH_SERVER_PORT', '22'))
SERVER_USER = os.environ.get('ETH_SERVER_USER', 'ubuntu')
SERVER_PASS = os.environ.get('ETH_SERVER_PASS', '')


def get_ssh_client(retries=5, backoff=10):
    """创建并返回 SSH 客户端连接，带重试。"""
    for attempt in range(retries):
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(SERVER_HOST, port=SERVER_PORT, username=SERVER_USER,
                        password=SERVER_PASS, timeout=30)
            return ssh
        except Exception as e:
            if attempt < retries - 1:
                wait = backoff * (attempt + 1)
                time.sleep(wait)
            else:
                raise


def run_remote(cmd, timeout=60):
    """在远程服务器上执行命令并返回输出。"""
    ssh = get_ssh_client()
    try:
        stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
        out = stdout.read().decode('utf-8', errors='replace')
        err = stderr.read().decode('utf-8', errors='replace')
        return out, err
    finally:
        ssh.close()


def run_remote_long(cmd, timeout=300):
    """执行长时间命令。"""
    return run_remote(cmd, timeout=timeout)


if __name__ == '__main__':
    out, err = run_remote('echo "Test connection OK" && whoami && pwd')
    print("STDOUT:", out)
    if err:
        print("STDERR:", err)

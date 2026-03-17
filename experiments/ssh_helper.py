"""SSH 辅助模块：连接远程服务器并执行命令。"""

import paramiko
import time


SERVER_HOST = '161.97.133.14'
SERVER_PORT = 22
SERVER_USER = 'ht1220'
SERVER_PASS = '592087469hW'


def get_ssh_client():
    """创建并返回 SSH 客户端连接。"""
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(SERVER_HOST, port=SERVER_PORT, username=SERVER_USER,
                password=SERVER_PASS, timeout=30)
    return ssh


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

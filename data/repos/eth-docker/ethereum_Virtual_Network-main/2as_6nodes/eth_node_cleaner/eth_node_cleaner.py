#!/usr/bin/env python3

"""
以太坊网络拓扑真实性管理器 - Enhanced Version
功能：确保Neo4j数据库反映真实可通信的网络拓扑，支持攻击场景
"""

import os
import time
import subprocess
import requests
import json
from neo4j import GraphDatabase
import logging
from typing import List, Tuple, Dict
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

class EthNetworkTopologyManager:
    """以太坊网络拓扑真实性管理器"""
    
    def __init__(self):
        # Neo4j配置
        self.neo4j_uri = os.getenv('NEO4J_URI', 'bolt://eth_neo4j:7687')
        self.neo4j_username = os.getenv('NEO4J_USERNAME', os.getenv('NEO4J_USER', 'neo4j'))  # 使用标准键名，向后兼容
        self.neo4j_password = os.getenv('NEO4J_PASSWORD', '1qaz@WSX')
        
        # 中央收集器配置
        self.central_collector_url = os.getenv('CENTRAL_COLLECTOR_URL', 'http://localhost:8888')
        
        # 设置日志
        self.logger = logging.getLogger('EthNetworkTopologyManager')
        
        # 初始化Neo4j连接
        self.driver = self._get_neo4j_driver_with_retry()
        
        # 统计信息
        self.total_checks = 0
        self.total_removals = 0
        self.last_cleanup_time = None
        
        self.logger.info("以太坊网络拓扑管理器初始化完成")
        self.logger.info("功能：维护Neo4j中的可通信节点拓扑（支持网络攻击场景）")
        self.logger.info(f"集成变化检测系统: {self.central_collector_url}")
    
    def _get_neo4j_driver_with_retry(self, max_retry: int = 30, interval: int = 2) -> GraphDatabase:
        """获取Neo4j驱动（带重试机制）"""
        for i in range(max_retry):
            try:
                driver = GraphDatabase.driver(
                    self.neo4j_uri, 
                    auth=(self.neo4j_username, self.neo4j_password)
                )
                # 测试连接
                with driver.session() as session:
                    session.run("RETURN 1")
                self.logger.info("成功连接到Neo4j数据库")
                return driver
            except Exception as e:
                self.logger.warning(f"第{i+1}次连接Neo4j失败: {e}，{interval}秒后重试...")
                time.sleep(interval)
        
        raise Exception("多次重试后仍无法连接到Neo4j数据库")
    
    def ping_check(self, ip: str) -> bool:
        """网络连通性检查 - 核心功能，支持攻击场景检测"""
        try:
            # 使用快速ping检查，适合攻击场景的快速响应
            result = subprocess.call(
                ['ping', '-c', '2', '-W', '3', ip], 
                stdout=subprocess.DEVNULL, 
                stderr=subprocess.DEVNULL
            )
            is_reachable = result == 0
            
            if not is_reachable:
                self.logger.debug(f"网络不可达: {ip} (可能是网络攻击或容器下线)")
            
            return is_reachable
        except Exception as e:
            self.logger.debug(f"ping检查异常 {ip}: {e}")
            return False
    
    def get_all_recorded_nodes(self) -> List[Tuple[str, str, str]]:
        """获取Neo4j中所有已记录的节点"""
        nodes = []
        try:
            with self.driver.session() as session:
                # 获取执行层节点 - 修复字段名称为node_id
                result = session.run("MATCH (n:ExecNode) RETURN n.node_id, n.ip, 'ExecNode' as type")
                nodes.extend([
                    (record['n.node_id'], record['n.ip'], record['type']) 
                    for record in result if record['n.ip']
                ])
                
                # 获取共识层节点 - 修复字段名称为node_id
                result = session.run("MATCH (n:ConsNode) RETURN n.node_id, n.ip, 'ConsNode' as type")
                nodes.extend([
                    (record['n.node_id'], record['n.ip'], record['type']) 
                    for record in result if record['n.ip']
                ])
        except Exception as e:
            self.logger.error(f"获取节点记录失败: {e}")
            return []
        
        return nodes
    
    def _send_node_deletion_event(self, node_id: str, node_type: str, node_ip: str):
        """向中央收集器发送节点删除事件"""
        try:
            # 构造变化事件
            event_data = {
                'data_type': 'network_topology_change',
                'data': {
                    'change_type': 'node_unreachable',
                    'layer': 'execution' if node_type == 'ExecNode' else 'consensus',
                    'node_id': node_id,
                    'node_type': node_type,
                    'node_ip': node_ip,
                    'change_data': {
                        'reason': 'network_unreachable',
                        'detection_method': 'ping_check',
                        'old_value': {'status': 'active', 'ip': node_ip},
                        'new_value': {'status': 'unreachable', 'ip': node_ip}
                    },
                    'timestamp': datetime.now().isoformat(),
                    'source': 'EthNetworkTopologyManager',
                    'impact_score': 0.8  # 高影响，因为是网络不可达
                },
                'container_id': 'topology_manager',
                'timestamp': datetime.now().isoformat()
            }
            
            # 发送到中央收集器
            response = requests.post(
                f"{self.central_collector_url}/api/v1/monitoring/data",
                json=event_data,
                timeout=5
            )
            
            if response.status_code == 200:
                self.logger.debug(f"节点删除事件已发送到变化检测系统: {node_id}")
            else:
                self.logger.warning(f"发送节点删除事件失败: {response.status_code}")
                
        except Exception as e:
            self.logger.warning(f"发送节点删除事件异常: {e}")

    def _delete_node_from_neo4j(self, node_id: str, node_type: str, node_ip: str = None):
        """从Neo4j删除指定类型的节点及其所有关系"""
        try:
            with self.driver.session() as session:
                # 优先使用IP地址删除（因为节点id可能为NULL）
                if node_ip:
                    result = session.run(
                        f"MATCH (n:{node_type} {{ip: $node_ip}}) DETACH DELETE n RETURN count(n) as deleted",
                        node_ip=node_ip
                    )
                    deleted_count = result.single()['deleted']
                    if deleted_count > 0:
                        self.logger.info(f"已从Neo4j删除{node_type}节点: {node_id or 'NULL'} (IP: {node_ip})")
                        self.total_removals += 1
                        
                        # 发送变化事件到中央收集器
                        self._send_node_deletion_event(node_id, node_type, node_ip)
                        return
                
                # 如果没有IP地址，则使用节点ID删除 - 修复字段名称为node_id
                result = session.run(
                    f"MATCH (n:{node_type} {{node_id: $node_id}}) DETACH DELETE n RETURN count(n) as deleted",
                    node_id=node_id
                )
                
                deleted_count = result.single()['deleted']
                if deleted_count > 0:
                    self.logger.info(f"已从Neo4j删除{node_type}节点: {node_id}")
                    self.total_removals += 1
                    
                    # 发送变化事件到中央收集器
                    if node_ip:
                        self._send_node_deletion_event(node_id, node_type, node_ip)
                else:
                    self.logger.warning(f"{node_type}节点 {node_id} (IP: {node_ip}) 不存在或已被删除")
        except Exception as e:
            self.logger.error(f"删除{node_type}节点 {node_id} (IP: {node_ip}) 失败: {e}")
    
    def cleanup_unreachable_nodes(self):
        """清理网络不可达的节点 - 支持攻击场景"""
        start_time = time.time()
        nodes = self.get_all_recorded_nodes()
        
        if not nodes:
            self.logger.info("Neo4j中没有节点记录，等待节点上报...")
            return
        
        self.logger.debug(f"开始检查 {len(nodes)} 个节点的网络连通性...")
        
        removed_count = 0
        for node_id, node_ip, node_type in nodes:
            self.total_checks += 1
            
            if not self.ping_check(node_ip):
                self.logger.info(
                    f"网络不可达，删除{node_type}节点: {node_id} ({node_ip}) "
                    f"[原因：容器停止或网络攻击]"
                )
                self._delete_node_from_neo4j(node_id, node_type, node_ip)
                removed_count += 1
            else:
                self.logger.debug(f"{node_type}节点网络正常: {node_id} ({node_ip})")
        
        # 更新统计信息
        self.last_cleanup_time = datetime.now()
        cleanup_duration = time.time() - start_time
        
        if removed_count > 0:
            self.logger.info(
                f"🌐 网络层拓扑清理完成: 删除 {removed_count} 个IP不可达节点 "
                f"(耗时 {cleanup_duration:.2f}秒)"
            )
            
            # 重新查询节点数量，确保统计信息准确
            updated_nodes = self.get_all_recorded_nodes()
            exec_nodes = len([n for n in updated_nodes if n[2] == 'ExecNode'])
            cons_nodes = len([n for n in updated_nodes if n[2] == 'ConsNode'])
            
            self.logger.info(
                f"📊 网络层统计: 当前{len(updated_nodes)}个IP可达节点 "
                f"(执行层:{exec_nodes}, 共识层:{cons_nodes}) "
                f"| 总删除:{self.total_removals}"
            )
        else:
            self.logger.info(
                f"🌐 网络层检查完成: 所有 {len(nodes)} 个节点IP网络连通正常 "
                f"(耗时 {cleanup_duration:.2f}秒)"
            )
            self.logger.info(
                f"💡 说明: 网络层检测IP可达性，应用层P2P连接状态由中央收集器监控"
            )
    
    def run_topology_management(self):
        """运行网络拓扑管理循环"""
        self.logger.info("启动以太坊网络拓扑管理器...")
        self.logger.info("⚠️  攻击场景支持：检测 'ip link set eth0 down/up' 网络攻击")
        self.logger.info("🎯 目标：确保Neo4j图数据库反映真实可通信的网络拓扑")
        
        while True:
            try:
                self.cleanup_unreachable_nodes()
                
                # 每分钟打印一次统计信息
                if self.total_checks % 10 == 0:
                    nodes = self.get_all_recorded_nodes()
                    exec_nodes = len([n for n in nodes if n[2] == 'ExecNode'])
                    cons_nodes = len([n for n in nodes if n[2] == 'ConsNode'])
                    
                    self.logger.info(
                        f"📊 统计: 当前{len(nodes)}个节点 "
                        f"(执行层:{exec_nodes}, 共识层:{cons_nodes}) "
                        f"| 总检查:{self.total_checks} | 总删除:{self.total_removals}"
                    )
                
                # 等待6秒再进行下次检查（快速响应攻击场景）
                time.sleep(6)
                
            except Exception as e:
                self.logger.error(f"拓扑管理失败: {e}")
                time.sleep(10)  # 出错时等待更长时间
    
    def __del__(self):
        """清理资源"""
        try:
            if hasattr(self, 'driver') and self.driver:
                self.driver.close()
                self.logger.info("Neo4j连接已关闭")
        except Exception:
            pass


def main():
    """主函数"""
    manager = EthNetworkTopologyManager()
    
    try:
        manager.run_topology_management()
    except KeyboardInterrupt:
        print("\n⏹️  收到停止信号，正在关闭网络拓扑管理器...")
        manager.logger.info("网络拓扑管理器已停止")
    except Exception as e:
        manager.logger.error(f"管理器运行异常: {e}")
        raise


if __name__ == '__main__':
    main()

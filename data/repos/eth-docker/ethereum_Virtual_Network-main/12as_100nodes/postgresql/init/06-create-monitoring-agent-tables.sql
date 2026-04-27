-- ==========================================
-- 监控代理相关表（agent_heartbeats, node_failures, active_agents视图）
-- ==========================================

-- 代理心跳记录表
CREATE TABLE IF NOT EXISTS agent_heartbeats (
    id SERIAL PRIMARY KEY,
    container_id VARCHAR(255) NOT NULL,
    node_id VARCHAR(255),
    heartbeat_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) DEFAULT 'active',
    agent_type VARCHAR(50) DEFAULT 'monitoring',
    agent_version VARCHAR(50) DEFAULT 'unknown',
    monitoring_capabilities JSONB DEFAULT '{}',
    local_ip INET,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_agent_heartbeats_container ON agent_heartbeats(container_id);
CREATE INDEX IF NOT EXISTS idx_agent_heartbeats_time ON agent_heartbeats(heartbeat_time);
CREATE INDEX IF NOT EXISTS idx_agent_heartbeats_status ON agent_heartbeats(status);
CREATE INDEX IF NOT EXISTS idx_agent_heartbeats_node ON agent_heartbeats(node_id);

-- 活跃代理视图（最近5分钟内有心跳的代理）
CREATE OR REPLACE VIEW active_agents AS
SELECT DISTINCT ON (container_id)
    container_id,
    node_id,
    heartbeat_time AS last_heartbeat,
    status,
    agent_type,
    agent_version,
    monitoring_capabilities,
    local_ip
FROM agent_heartbeats
WHERE heartbeat_time >= NOW() - INTERVAL '5 minutes'
ORDER BY container_id, heartbeat_time DESC;

-- 节点故障记录表
CREATE TABLE IF NOT EXISTS node_failures (
    id SERIAL PRIMARY KEY,
    container_id VARCHAR(255) NOT NULL,
    node_id VARCHAR(255) NOT NULL,
    failure_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    failure_type VARCHAR(50) DEFAULT 'unknown',
    status VARCHAR(20) DEFAULT 'inactive',
    details JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_node_failure UNIQUE (container_id, node_id)
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_node_failures_container ON node_failures(container_id);
CREATE INDEX IF NOT EXISTS idx_node_failures_node ON node_failures(node_id);
CREATE INDEX IF NOT EXISTS idx_node_failures_time ON node_failures(failure_time);
CREATE INDEX IF NOT EXISTS idx_node_failures_status ON node_failures(status);

-- 完成提示
DO $$
BEGIN
    RAISE NOTICE '==============================================';
    RAISE NOTICE '监控代理表创建完成';
    RAISE NOTICE '- agent_heartbeats: 代理心跳记录表';
    RAISE NOTICE '- active_agents: 活跃代理视图（5分钟内）';
    RAISE NOTICE '- node_failures: 节点故障记录表';
    RAISE NOTICE '==============================================';
END $$;

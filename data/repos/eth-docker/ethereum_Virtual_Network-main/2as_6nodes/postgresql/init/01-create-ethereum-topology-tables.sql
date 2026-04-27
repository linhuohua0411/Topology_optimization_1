-- ==========================================
-- 以太坊拓扑变化追踪系统数据库初始化脚本
-- ==========================================

-- 创建以太坊拓扑变化追踪相关表
-- 支持执行层(execution)和共识层(consensus)的独立追踪

-- ==========================================
-- 执行层拓扑历史表
-- ==========================================

-- 执行层拓扑快照表
CREATE TABLE IF NOT EXISTS eth_execution_topology_snapshots (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    snapshot_hash VARCHAR(64) UNIQUE NOT NULL,
    node_count INTEGER NOT NULL,
    link_count INTEGER NOT NULL,
    topology_data JSONB NOT NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_eth_execution_snapshots_timestamp 
    ON eth_execution_topology_snapshots(timestamp);
CREATE INDEX IF NOT EXISTS idx_eth_execution_snapshots_hash 
    ON eth_execution_topology_snapshots(snapshot_hash);

-- 执行层拓扑变化事件表
CREATE TABLE IF NOT EXISTS eth_execution_topology_changes (
    id SERIAL PRIMARY KEY,
    event_id VARCHAR(64) UNIQUE NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    change_type VARCHAR(50) NOT NULL,
    before_snapshot_id INTEGER REFERENCES eth_execution_topology_snapshots(id),
    after_snapshot_id INTEGER NOT NULL REFERENCES eth_execution_topology_snapshots(id),
    diff_data JSONB NOT NULL,
    metadata JSONB DEFAULT '{}',
    source VARCHAR(50) DEFAULT 'ethereum_topology_tracker',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_eth_execution_changes_timestamp 
    ON eth_execution_topology_changes(timestamp);
CREATE INDEX IF NOT EXISTS idx_eth_execution_changes_type 
    ON eth_execution_topology_changes(change_type);
CREATE INDEX IF NOT EXISTS idx_eth_execution_changes_event_id 
    ON eth_execution_topology_changes(event_id);

-- 执行层节点变化详情表
CREATE TABLE IF NOT EXISTS eth_execution_node_changes (
    id SERIAL PRIMARY KEY,
    change_event_id INTEGER NOT NULL REFERENCES eth_execution_topology_changes(id),
    node_id VARCHAR(255) NOT NULL,
    change_type VARCHAR(20) NOT NULL, -- 'added', 'removed', 'modified'
    old_data JSONB,
    new_data JSONB,
    timestamp TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_eth_execution_node_changes_node_id 
    ON eth_execution_node_changes(node_id);
CREATE INDEX IF NOT EXISTS idx_eth_execution_node_changes_timestamp 
    ON eth_execution_node_changes(timestamp);
CREATE INDEX IF NOT EXISTS idx_eth_execution_node_changes_event_id 
    ON eth_execution_node_changes(change_event_id);

-- 执行层连接变化详情表
CREATE TABLE IF NOT EXISTS eth_execution_link_changes (
    id SERIAL PRIMARY KEY,
    change_event_id INTEGER NOT NULL REFERENCES eth_execution_topology_changes(id),
    source_node_id VARCHAR(255) NOT NULL,
    target_node_id VARCHAR(255) NOT NULL,
    link_type VARCHAR(50),
    change_type VARCHAR(20) NOT NULL, -- 'added', 'removed', 'modified'
    old_data JSONB,
    new_data JSONB,
    timestamp TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_eth_execution_link_changes_source_target 
    ON eth_execution_link_changes(source_node_id, target_node_id);
CREATE INDEX IF NOT EXISTS idx_eth_execution_link_changes_timestamp 
    ON eth_execution_link_changes(timestamp);
CREATE INDEX IF NOT EXISTS idx_eth_execution_link_changes_event_id 
    ON eth_execution_link_changes(change_event_id);

-- ==========================================
-- 共识层拓扑历史表
-- ==========================================

-- 共识层拓扑快照表
CREATE TABLE IF NOT EXISTS eth_consensus_topology_snapshots (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    snapshot_hash VARCHAR(64) UNIQUE NOT NULL,
    node_count INTEGER NOT NULL,
    link_count INTEGER NOT NULL,
    topology_data JSONB NOT NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_eth_consensus_snapshots_timestamp 
    ON eth_consensus_topology_snapshots(timestamp);
CREATE INDEX IF NOT EXISTS idx_eth_consensus_snapshots_hash 
    ON eth_consensus_topology_snapshots(snapshot_hash);

-- 共识层拓扑变化事件表
CREATE TABLE IF NOT EXISTS eth_consensus_topology_changes (
    id SERIAL PRIMARY KEY,
    event_id VARCHAR(64) UNIQUE NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    change_type VARCHAR(50) NOT NULL,
    before_snapshot_id INTEGER REFERENCES eth_consensus_topology_snapshots(id),
    after_snapshot_id INTEGER NOT NULL REFERENCES eth_consensus_topology_snapshots(id),
    diff_data JSONB NOT NULL,
    metadata JSONB DEFAULT '{}',
    source VARCHAR(50) DEFAULT 'ethereum_topology_tracker',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_eth_consensus_changes_timestamp 
    ON eth_consensus_topology_changes(timestamp);
CREATE INDEX IF NOT EXISTS idx_eth_consensus_changes_type 
    ON eth_consensus_topology_changes(change_type);
CREATE INDEX IF NOT EXISTS idx_eth_consensus_changes_event_id 
    ON eth_consensus_topology_changes(event_id);

-- 共识层节点变化详情表
CREATE TABLE IF NOT EXISTS eth_consensus_node_changes (
    id SERIAL PRIMARY KEY,
    change_event_id INTEGER NOT NULL REFERENCES eth_consensus_topology_changes(id),
    node_id VARCHAR(255) NOT NULL,
    change_type VARCHAR(20) NOT NULL, -- 'added', 'removed', 'modified'
    old_data JSONB,
    new_data JSONB,
    timestamp TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_eth_consensus_node_changes_node_id 
    ON eth_consensus_node_changes(node_id);
CREATE INDEX IF NOT EXISTS idx_eth_consensus_node_changes_timestamp 
    ON eth_consensus_node_changes(timestamp);
CREATE INDEX IF NOT EXISTS idx_eth_consensus_node_changes_event_id 
    ON eth_consensus_node_changes(change_event_id);

-- 共识层连接变化详情表
CREATE TABLE IF NOT EXISTS eth_consensus_link_changes (
    id SERIAL PRIMARY KEY,
    change_event_id INTEGER NOT NULL REFERENCES eth_consensus_topology_changes(id),
    source_node_id VARCHAR(255) NOT NULL,
    target_node_id VARCHAR(255) NOT NULL,
    link_type VARCHAR(50),
    change_type VARCHAR(20) NOT NULL, -- 'added', 'removed', 'modified'
    old_data JSONB,
    new_data JSONB,
    timestamp TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_eth_consensus_link_changes_source_target 
    ON eth_consensus_link_changes(source_node_id, target_node_id);
CREATE INDEX IF NOT EXISTS idx_eth_consensus_link_changes_timestamp 
    ON eth_consensus_link_changes(timestamp);
CREATE INDEX IF NOT EXISTS idx_eth_consensus_link_changes_event_id 
    ON eth_consensus_link_changes(change_event_id);

-- ==========================================
-- 创建表注释
-- ==========================================

COMMENT ON TABLE eth_execution_topology_snapshots IS '以太坊执行层拓扑快照表';
COMMENT ON TABLE eth_execution_topology_changes IS '以太坊执行层拓扑变化事件表';
COMMENT ON TABLE eth_execution_node_changes IS '以太坊执行层节点变化详情表';
COMMENT ON TABLE eth_execution_link_changes IS '以太坊执行层连接变化详情表';

COMMENT ON TABLE eth_consensus_topology_snapshots IS '以太坊共识层拓扑快照表';
COMMENT ON TABLE eth_consensus_topology_changes IS '以太坊共识层拓扑变化事件表';
COMMENT ON TABLE eth_consensus_node_changes IS '以太坊共识层节点变化详情表';
COMMENT ON TABLE eth_consensus_link_changes IS '以太坊共识层连接变化详情表';

-- ==========================================
-- 创建视图 - 便于查询
-- ==========================================

-- 执行层变化统计视图
CREATE OR REPLACE VIEW eth_execution_change_stats AS
SELECT 
    DATE_TRUNC('hour', timestamp) as hour,
    change_type,
    COUNT(*) as change_count,
    MAX(timestamp) as latest_change
FROM eth_execution_topology_changes
GROUP BY DATE_TRUNC('hour', timestamp), change_type
ORDER BY hour DESC;

-- 共识层变化统计视图
CREATE OR REPLACE VIEW eth_consensus_change_stats AS
SELECT 
    DATE_TRUNC('hour', timestamp) as hour,
    change_type,
    COUNT(*) as change_count,
    MAX(timestamp) as latest_change
FROM eth_consensus_topology_changes
GROUP BY DATE_TRUNC('hour', timestamp), change_type
ORDER BY hour DESC;

-- ==========================================
-- 初始化完成
-- ==========================================

-- 插入初始化标记
INSERT INTO eth_execution_topology_snapshots (timestamp, snapshot_hash, node_count, link_count, topology_data, metadata) 
VALUES (NOW(), 'init_marker', 0, 0, '{}', '{"type": "init_marker", "description": "Database initialization marker"}')
ON CONFLICT (snapshot_hash) DO NOTHING;

INSERT INTO eth_consensus_topology_snapshots (timestamp, snapshot_hash, node_count, link_count, topology_data, metadata) 
VALUES (NOW(), 'init_marker', 0, 0, '{}', '{"type": "init_marker", "description": "Database initialization marker"}')
ON CONFLICT (snapshot_hash) DO NOTHING;

COMMIT; 
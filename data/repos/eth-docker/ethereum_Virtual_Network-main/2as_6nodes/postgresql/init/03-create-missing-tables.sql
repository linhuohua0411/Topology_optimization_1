-- ==========================================
-- 补充缺失的监控表结构
-- ==========================================

-- 分叉事件表
CREATE TABLE IF NOT EXISTS fork_events (
    id SERIAL PRIMARY KEY,
    fork_id VARCHAR(100) NOT NULL,
    detection_time TIMESTAMP NOT NULL,
    slot INTEGER,
    fork_type VARCHAR(50),
    resolution_status VARCHAR(20) DEFAULT 'active',
    details JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 节点快照表
CREATE TABLE IF NOT EXISTS node_snapshots (
    id SERIAL PRIMARY KEY,
    node_id VARCHAR(64),
    timestamp TIMESTAMP,
    data JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 拓扑变化表
CREATE TABLE IF NOT EXISTS topology_changes (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP,
    layer VARCHAR(20),
    source_node VARCHAR(64),
    target_node VARCHAR(64),
    action VARCHAR(20),
    metadata JSONB
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_fork_events_detection_time ON fork_events(detection_time);
CREATE INDEX IF NOT EXISTS idx_fork_events_status ON fork_events(resolution_status);
CREATE INDEX IF NOT EXISTS idx_fork_events_fork_id ON fork_events(fork_id);

CREATE INDEX IF NOT EXISTS idx_node_snapshots_node_time ON node_snapshots(node_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_node_snapshots_timestamp ON node_snapshots(timestamp);

CREATE INDEX IF NOT EXISTS idx_topology_changes_timestamp ON topology_changes(timestamp);
CREATE INDEX IF NOT EXISTS idx_topology_changes_layer ON topology_changes(layer);

-- 完成提示
DO $$
BEGIN
    RAISE NOTICE '==============================================';
    RAISE NOTICE '补充监控表结构创建完成';
    RAISE NOTICE '- fork_events: 分叉事件表';
    RAISE NOTICE '- node_snapshots: 节点快照表';
    RAISE NOTICE '- topology_changes: 拓扑变化表';
    RAISE NOTICE '==============================================';
END $$; 
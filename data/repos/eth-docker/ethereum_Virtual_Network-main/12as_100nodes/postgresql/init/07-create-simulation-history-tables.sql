-- ==========================================
-- 仿真历史记录与拓扑分析表
-- 用于时序追踪节点上下线事件、WAN扰动历史、
-- 交易网络拓扑和合约交互拓扑
-- ==========================================

-- ============================================
-- 1. 节点混沌事件历史表 (每次上/下线都是一条独立记录)
-- ============================================
CREATE TABLE IF NOT EXISTS node_chaos_events (
    id SERIAL PRIMARY KEY,
    event_type VARCHAR(30) NOT NULL,  -- 'node_link_down' / 'node_link_up'
    container_name VARCHAR(255) NOT NULL,
    node_ip VARCHAR(45),
    interface VARCHAR(30),
    trigger VARCHAR(30) DEFAULT 'random',  -- 'random' / 'manual' / 'auto_recovery' / 'shutdown'
    ip_with_prefix VARCHAR(50),
    gateway VARCHAR(45),
    gateway_dev VARCHAR(30),
    down_duration_seconds INTEGER,
    gateway_ping_ok BOOLEAN,
    restored_neighbors INTEGER DEFAULT 0,
    details JSONB DEFAULT '{}',
    event_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_node_chaos_events_time ON node_chaos_events(event_time);
CREATE INDEX IF NOT EXISTS idx_node_chaos_events_container ON node_chaos_events(container_name);
CREATE INDEX IF NOT EXISTS idx_node_chaos_events_type ON node_chaos_events(event_type);
CREATE INDEX IF NOT EXISTS idx_node_chaos_events_trigger ON node_chaos_events(trigger);

COMMENT ON TABLE node_chaos_events IS '节点混沌事件完整历史（每次 ip link up/down 独立记录，不覆盖）';

-- ============================================
-- 2. WAN 链路混沌事件历史表
-- ============================================
CREATE TABLE IF NOT EXISTS wan_chaos_events (
    id SERIAL PRIMARY KEY,
    event_type VARCHAR(30) NOT NULL,  -- 'wan_profile_changed' / 'wan_profile_restored'
    container_name VARCHAR(255) NOT NULL,
    interface VARCHAR(30) NOT NULL,
    trigger VARCHAR(30) DEFAULT 'random',
    bandwidth_mbit INTEGER,
    delay_ms INTEGER,
    jitter_ms INTEGER,
    loss_pct DECIMAL(6,3),
    baseline_bandwidth_mbit INTEGER,
    baseline_delay_ms INTEGER,
    baseline_jitter_ms INTEGER,
    baseline_loss_pct DECIMAL(6,3),
    duration_seconds INTEGER,
    details JSONB DEFAULT '{}',
    event_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_wan_chaos_events_time ON wan_chaos_events(event_time);
CREATE INDEX IF NOT EXISTS idx_wan_chaos_events_container ON wan_chaos_events(container_name);
CREATE INDEX IF NOT EXISTS idx_wan_chaos_events_type ON wan_chaos_events(event_type);
CREATE INDEX IF NOT EXISTS idx_wan_chaos_events_interface ON wan_chaos_events(interface);

COMMENT ON TABLE wan_chaos_events IS 'WAN链路混沌事件完整历史（每次 tc qdisc 操作独立记录）';

-- ============================================
-- 3. 交易网络拓扑视图 (地址 -> 地址 转账图)
-- ============================================

CREATE OR REPLACE VIEW transaction_network_topology AS
SELECT
    from_address,
    to_address,
    COUNT(*) AS tx_count,
    SUM(value) AS total_value_wei,
    SUM(gas_used) AS total_gas_used,
    MIN(timestamp) AS first_tx_time,
    MAX(timestamp) AS last_tx_time,
    COUNT(CASE WHEN status = 1 THEN 1 END) AS success_count,
    COUNT(CASE WHEN status = 0 THEN 1 END) AS fail_count
FROM transactions
WHERE to_address IS NOT NULL
GROUP BY from_address, to_address
ORDER BY tx_count DESC;

COMMENT ON VIEW transaction_network_topology IS '交易网络拓扑视图：地址之间的转账关系图';

-- 按小时聚合的交易拓扑快照（用于时序分析拓扑变化）
CREATE OR REPLACE VIEW transaction_topology_hourly AS
SELECT
    DATE_TRUNC('hour', timestamp) AS hour,
    from_address,
    to_address,
    COUNT(*) AS tx_count,
    SUM(value) AS total_value_wei
FROM transactions
WHERE to_address IS NOT NULL
GROUP BY DATE_TRUNC('hour', timestamp), from_address, to_address
ORDER BY hour DESC, tx_count DESC;

COMMENT ON VIEW transaction_topology_hourly IS '按小时聚合的交易拓扑快照（用于时序分析拓扑演变）';

-- ============================================
-- 4. 合约交互拓扑视图
-- ============================================

CREATE OR REPLACE VIEW contract_interaction_topology AS
SELECT
    ce.contract_address,
    c.contract_name,
    c.contract_type,
    ce.event_name AS method_name,
    COUNT(*) AS call_count,
    MIN(ce.timestamp) AS first_call_time,
    MAX(ce.timestamp) AS last_call_time,
    COUNT(DISTINCT ce.event_name) AS unique_methods_called
FROM contract_events ce
LEFT JOIN contracts c ON ce.contract_address = c.contract_address
GROUP BY ce.contract_address, c.contract_name, c.contract_type, ce.event_name
ORDER BY call_count DESC;

COMMENT ON VIEW contract_interaction_topology IS '合约交互拓扑视图：合约方法调用关系图';

-- 按小时聚合的合约交互快照
CREATE OR REPLACE VIEW contract_interaction_hourly AS
SELECT
    DATE_TRUNC('hour', ce.timestamp) AS hour,
    ce.contract_address,
    c.contract_name,
    ce.event_name AS method_name,
    COUNT(*) AS call_count
FROM contract_events ce
LEFT JOIN contracts c ON ce.contract_address = c.contract_address
GROUP BY DATE_TRUNC('hour', ce.timestamp), ce.contract_address, c.contract_name, ce.event_name
ORDER BY hour DESC, call_count DESC;

COMMENT ON VIEW contract_interaction_hourly IS '按小时聚合的合约交互快照（用于时序分析合约活动演变）';

-- ============================================
-- 5. 节点在线/离线状态时间线视图
-- ============================================

CREATE OR REPLACE VIEW node_updown_timeline AS
SELECT
    container_name,
    event_type,
    trigger,
    interface,
    ip_with_prefix,
    gateway,
    down_duration_seconds,
    gateway_ping_ok,
    event_time,
    LAG(event_time) OVER (PARTITION BY container_name ORDER BY event_time) AS prev_event_time,
    EXTRACT(EPOCH FROM (event_time - LAG(event_time) OVER (PARTITION BY container_name ORDER BY event_time))) AS seconds_since_prev_event
FROM node_chaos_events
ORDER BY event_time DESC;

COMMENT ON VIEW node_updown_timeline IS '节点上下线时间线（含相邻事件间隔，便于时序分析）';

-- ============================================
-- 6. WAN 链路带宽变化时间线视图
-- ============================================

CREATE OR REPLACE VIEW wan_bandwidth_timeline AS
SELECT
    container_name,
    interface,
    event_type,
    trigger,
    bandwidth_mbit,
    delay_ms,
    jitter_ms,
    loss_pct,
    baseline_bandwidth_mbit,
    baseline_delay_ms,
    duration_seconds,
    event_time,
    LAG(event_time) OVER (PARTITION BY container_name, interface ORDER BY event_time) AS prev_event_time,
    EXTRACT(EPOCH FROM (event_time - LAG(event_time) OVER (PARTITION BY container_name, interface ORDER BY event_time))) AS seconds_since_prev
FROM wan_chaos_events
ORDER BY event_time DESC;

COMMENT ON VIEW wan_bandwidth_timeline IS 'WAN带宽变化时间线（含相邻事件间隔，便于时序分析）';

-- ============================================
-- 7. 综合仿真事件时间线（合并所有事件源）
-- ============================================

CREATE OR REPLACE VIEW simulation_events_timeline AS
SELECT
    event_time AS timestamp,
    'chaos' AS event_source,
    event_type,
    container_name AS target,
    interface,
    trigger,
    details
FROM node_chaos_events
UNION ALL
SELECT
    event_time AS timestamp,
    'wan' AS event_source,
    event_type,
    container_name AS target,
    interface,
    trigger,
    details
FROM wan_chaos_events
UNION ALL
SELECT
    timestamp,
    'topology' AS event_source,
    action AS event_type,
    source_node AS target,
    target_node AS interface,
    layer AS trigger,
    metadata AS details
FROM topology_changes
ORDER BY timestamp DESC;

COMMENT ON VIEW simulation_events_timeline IS '所有仿真事件的统一时间线视图';

-- ============================================
-- 完成提示
-- ============================================
DO $$
BEGIN
    RAISE NOTICE '==============================================';
    RAISE NOTICE '仿真历史记录与拓扑分析表创建完成 ✅';
    RAISE NOTICE '- node_chaos_events: 节点混沌事件完整历史';
    RAISE NOTICE '- wan_chaos_events: WAN链路混沌事件完整历史';
    RAISE NOTICE '- transaction_network_topology: 交易网络拓扑视图';
    RAISE NOTICE '- transaction_topology_hourly: 按小时交易拓扑';
    RAISE NOTICE '- contract_interaction_topology: 合约交互拓扑视图';
    RAISE NOTICE '- contract_interaction_hourly: 按小时合约交互';
    RAISE NOTICE '- node_updown_timeline: 节点上下线时间线';
    RAISE NOTICE '- wan_bandwidth_timeline: WAN带宽变化时间线';
    RAISE NOTICE '- simulation_events_timeline: 综合仿真事件时间线';
    RAISE NOTICE '==============================================';
END $$;

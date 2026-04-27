-- ==========================================
-- 以太坊交易和合约数据库表
-- ==========================================

-- 交易历史表
CREATE TABLE IF NOT EXISTS transaction_history (
    id SERIAL PRIMARY KEY,
    tx_hash VARCHAR(66) UNIQUE NOT NULL,
    block_number BIGINT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    from_address VARCHAR(42) NOT NULL,
    to_address VARCHAR(42),
    value BIGINT NOT NULL DEFAULT 0,
    gas_used BIGINT,
    status INTEGER,
    contract_address VARCHAR(42),
    method_id VARCHAR(10),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 合约事件表
CREATE TABLE IF NOT EXISTS contract_events (
    id SERIAL PRIMARY KEY,
    block_number BIGINT NOT NULL,
    event_name VARCHAR(255) NOT NULL,
    contract_address VARCHAR(42) NOT NULL,
    args JSONB,
    timestamp TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_transaction_history_hash ON transaction_history(tx_hash);
CREATE INDEX IF NOT EXISTS idx_transaction_history_block ON transaction_history(block_number);
CREATE INDEX IF NOT EXISTS idx_transaction_history_from ON transaction_history(from_address);
CREATE INDEX IF NOT EXISTS idx_transaction_history_to ON transaction_history(to_address);
CREATE INDEX IF NOT EXISTS idx_transaction_history_timestamp ON transaction_history(timestamp);

CREATE INDEX IF NOT EXISTS idx_contract_events_block ON contract_events(block_number);
CREATE INDEX IF NOT EXISTS idx_contract_events_address ON contract_events(contract_address);
CREATE INDEX IF NOT EXISTS idx_contract_events_timestamp ON contract_events(timestamp);

-- 视图：交易统计
CREATE OR REPLACE VIEW transaction_stats AS
SELECT 
    DATE_TRUNC('hour', timestamp) as hour,
    COUNT(*) as tx_count,
    SUM(value) as total_value,
    COUNT(DISTINCT from_address) as unique_senders,
    COUNT(DISTINCT to_address) as unique_receivers
FROM transaction_history
GROUP BY DATE_TRUNC('hour', timestamp)
ORDER BY hour DESC;

-- 视图：合约活动统计
CREATE OR REPLACE VIEW contract_activity_stats AS
SELECT 
    contract_address,
    COUNT(*) as event_count,
    COUNT(DISTINCT event_name) as unique_events,
    DATE_TRUNC('hour', timestamp) as hour
FROM contract_events
GROUP BY contract_address, DATE_TRUNC('hour', timestamp)
ORDER BY hour DESC, event_count DESC; 
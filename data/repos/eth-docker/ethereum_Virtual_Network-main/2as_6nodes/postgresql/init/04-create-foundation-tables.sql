-- Foundation层统一数据访问所需的表结构
-- 创建日期: 2024-12-22
-- 用途: 支持Foundation层统一数据接口

-- ============================================
-- 1. 信标链区块表 (beacon_blocks)
-- ============================================
CREATE TABLE IF NOT EXISTS beacon_blocks (
    id SERIAL PRIMARY KEY,
    slot BIGINT NOT NULL,
    hash VARCHAR(66) UNIQUE NOT NULL,
    parent_hash VARCHAR(66),
    proposer_index INTEGER,
    timestamp FLOAT NOT NULL,
    state_root VARCHAR(66),
    attestations TEXT,
    attestation_count INTEGER DEFAULT 0,
    discovery_time FLOAT,
    source_node_ip INET,
    potential_fork BOOLEAN DEFAULT FALSE,
    fork_confidence FLOAT DEFAULT 0.0,
    competing_blocks JSONB DEFAULT '[]',
    block_number BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_beacon_blocks_slot ON beacon_blocks(slot);
CREATE INDEX IF NOT EXISTS idx_beacon_blocks_hash ON beacon_blocks(hash);
CREATE INDEX IF NOT EXISTS idx_beacon_blocks_timestamp ON beacon_blocks(timestamp);
CREATE INDEX IF NOT EXISTS idx_beacon_blocks_proposer ON beacon_blocks(proposer_index);

-- ============================================
-- 2. 验证者表 (validators)
-- ============================================
CREATE TABLE IF NOT EXISTS validators (
    id SERIAL PRIMARY KEY,
    validator_index INTEGER UNIQUE NOT NULL,
    pubkey VARCHAR(98) NOT NULL,
    status VARCHAR(20) DEFAULT 'active',
    effective_balance BIGINT,
    slashed BOOLEAN DEFAULT FALSE,
    activation_epoch BIGINT,   -- 使用 BIGINT 存储 Ethereum epoch（uint64，FAR_FUTURE=2^64-1）
    exit_epoch BIGINT,         -- 使用 BIGINT，FAR_FUTURE_EPOCH 在代码层转为 NULL
    withdrawal_credentials VARCHAR(66),
    current_duties JSONB DEFAULT '{}',
    balance BIGINT,
    managed_by_node VARCHAR(130),
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_validators_index ON validators(validator_index);
CREATE INDEX IF NOT EXISTS idx_validators_pubkey ON validators(pubkey);
CREATE INDEX IF NOT EXISTS idx_validators_status ON validators(status);
CREATE INDEX IF NOT EXISTS idx_validators_node ON validators(managed_by_node);

-- ============================================
-- 3. 证明表 (attestations)
-- ============================================
CREATE TABLE IF NOT EXISTS attestations (
    id SERIAL PRIMARY KEY,
    attestation_id VARCHAR(100) UNIQUE NOT NULL,
    slot BIGINT NOT NULL,
    committee_index INTEGER,
    beacon_block_root VARCHAR(66),
    source_epoch INTEGER,
    target_epoch INTEGER,
    validator_indices INTEGER[],
    aggregation_bits TEXT,
    signature VARCHAR(192),
    inclusion_slot BIGINT,
    inclusion_delay INTEGER,
    is_included BOOLEAN DEFAULT FALSE,
    validation_status VARCHAR(20) DEFAULT 'pending',
    processing_time FLOAT DEFAULT 0.0,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_attestations_slot ON attestations(slot);
CREATE INDEX IF NOT EXISTS idx_attestations_committee ON attestations(committee_index);
CREATE INDEX IF NOT EXISTS idx_attestations_inclusion ON attestations(inclusion_slot);
CREATE INDEX IF NOT EXISTS idx_attestations_status ON attestations(validation_status);

-- ============================================
-- 4. 统一交易表 (transactions)
-- ============================================
CREATE TABLE IF NOT EXISTS transactions (
    id SERIAL PRIMARY KEY,
    tx_hash VARCHAR(66) UNIQUE NOT NULL,
    block_number BIGINT NOT NULL,
    from_address VARCHAR(42) NOT NULL,
    to_address VARCHAR(42),
    value BIGINT DEFAULT 0,
    gas_limit BIGINT,
    gas_price BIGINT,
    gas_used BIGINT,
    status INTEGER DEFAULT 0, -- 0=failed, 1=success
    input_data TEXT,
    method_id VARCHAR(10),
    contract_address VARCHAR(42),
    timestamp TIMESTAMP NOT NULL,
    transaction_index INTEGER,
    nonce INTEGER,
    logs JSONB DEFAULT '[]',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_transactions_hash ON transactions(tx_hash);
CREATE INDEX IF NOT EXISTS idx_transactions_block ON transactions(block_number);
CREATE INDEX IF NOT EXISTS idx_transactions_from ON transactions(from_address);
CREATE INDEX IF NOT EXISTS idx_transactions_to ON transactions(to_address);
CREATE INDEX IF NOT EXISTS idx_transactions_timestamp ON transactions(timestamp);
CREATE INDEX IF NOT EXISTS idx_transactions_contract ON transactions(contract_address);

-- ============================================
-- 5. 统一合约表 (contracts)
-- ============================================
CREATE TABLE IF NOT EXISTS contracts (
    id SERIAL PRIMARY KEY,
    contract_address VARCHAR(42) UNIQUE NOT NULL,
    deployer_address VARCHAR(42) NOT NULL,
    block_number BIGINT NOT NULL,
    tx_hash VARCHAR(66) NOT NULL,
    bytecode TEXT,
    abi JSONB,
    contract_name VARCHAR(100),
    contract_type VARCHAR(50) DEFAULT 'Unknown',
    is_verified BOOLEAN DEFAULT FALSE,
    source_code TEXT,
    compiler_version VARCHAR(50),
    optimization_enabled BOOLEAN,
    constructor_args TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_contracts_address ON contracts(contract_address);
CREATE INDEX IF NOT EXISTS idx_contracts_deployer ON contracts(deployer_address);
CREATE INDEX IF NOT EXISTS idx_contracts_block ON contracts(block_number);
CREATE INDEX IF NOT EXISTS idx_contracts_type ON contracts(contract_type);
CREATE INDEX IF NOT EXISTS idx_contracts_verified ON contracts(is_verified);

-- ============================================
-- 6. 创建数据兼容性视图
-- ============================================

-- 为现有transaction_history表创建别名视图
CREATE OR REPLACE VIEW transaction_history_view AS
SELECT 
    tx_hash,
    block_number,
    from_address,
    to_address,
    value,
    gas_used as gas_limit,
    status,
    method_id,
    timestamp,
    contract_address
FROM transactions;

-- 为现有contract_events表创建扩展视图
CREATE OR REPLACE VIEW contract_events_view AS
SELECT 
    c.contract_address,
    c.deployer_address,
    c.block_number,
    c.tx_hash,
    c.contract_type,
    c.is_verified,
    c.created_at
FROM contracts c;

-- ============================================
-- 7. 数据迁移存储过程
-- ============================================

-- 从transaction_history迁移数据到transactions表
CREATE OR REPLACE FUNCTION migrate_transaction_history()
RETURNS INTEGER AS $$
DECLARE
    migrated_count INTEGER := 0;
BEGIN
    -- 检查transaction_history表是否存在
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'transaction_history') THEN
        INSERT INTO transactions (
            tx_hash, block_number, from_address, to_address, 
            value, gas_used, status, method_id, timestamp, contract_address
        )
        SELECT DISTINCT
            tx_hash, block_number, from_address, to_address,
            value, gas_used, status, method_id, timestamp, contract_address
        FROM transaction_history
        ON CONFLICT (tx_hash) DO NOTHING;
        
        GET DIAGNOSTICS migrated_count = ROW_COUNT;
    END IF;
    
    RETURN migrated_count;
END;
$$ LANGUAGE plpgsql;

-- 从contract_events迁移数据到contracts表  
CREATE OR REPLACE FUNCTION migrate_contract_events()
RETURNS INTEGER AS $$
DECLARE
    migrated_count INTEGER := 0;
BEGIN
    -- 检查contract_events表是否存在
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'contract_events') THEN
        INSERT INTO contracts (
            contract_address, deployer_address, block_number, 
            tx_hash, contract_type, created_at
        )
        SELECT DISTINCT
            contract_address, 
            'unknown' as deployer_address,
            block_number,
            'unknown' as tx_hash,
            'Unknown' as contract_type,
            timestamp as created_at
        FROM contract_events
        WHERE contract_address IS NOT NULL
        ON CONFLICT (contract_address) DO NOTHING;
        
        GET DIAGNOSTICS migrated_count = ROW_COUNT;
    END IF;
    
    RETURN migrated_count;
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- 8. 自动执行迁移
-- ============================================

-- 执行数据迁移
DO $$
DECLARE
    tx_migrated INTEGER;
    contract_migrated INTEGER;
BEGIN
    tx_migrated := migrate_transaction_history();
    contract_migrated := migrate_contract_events();
    
    RAISE NOTICE '数据迁移完成: 交易记录 % 条, 合约记录 % 条', tx_migrated, contract_migrated;
END;
$$; 
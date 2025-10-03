-- Real-time Payments & Cross-border System Database Schema
-- Optimized for sub-second processing and high throughput

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "btree_gist";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Create custom types
CREATE TYPE payment_status AS ENUM ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED', 'CANCELLED', 'RETURNED');
CREATE TYPE payment_type AS ENUM ('INSTANT', 'CROSSBORDER', 'BULK', 'RECURRING');
CREATE TYPE currency_code AS ENUM ('USD', 'EUR', 'GBP', 'JPY', 'CHF', 'CAD', 'AUD', 'CNY', 'HKD', 'SGD', 'BRL', 'MXN', 'INR', 'KRW', 'ZAR');
CREATE TYPE network_type AS ENUM ('FEDWIRE', 'RTP', 'SEPA_INSTANT', 'SWIFT_GPI', 'FASTER_PAYMENTS', 'PIX', 'UPI');
CREATE TYPE participant_type AS ENUM ('BANK', 'FINTECH', 'CORPORATE', 'GOVERNMENT', 'INDIVIDUAL');
CREATE TYPE settlement_status AS ENUM ('PENDING', 'SETTLED', 'FAILED', 'RECONCILED');

-- Participants (Banks, FinTechs, etc.)
CREATE TABLE participants (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    participant_id VARCHAR(50) UNIQUE NOT NULL,
    participant_name VARCHAR(255) NOT NULL,
    participant_type participant_type NOT NULL,
    
    -- Network identifiers
    bic_code VARCHAR(11), -- SWIFT BIC
    routing_number VARCHAR(20),
    sort_code VARCHAR(10),
    country_code VARCHAR(2) NOT NULL,
    
    -- Supported networks
    supported_networks network_type[] NOT NULL DEFAULT '{}',
    
    -- Operational details
    is_active BOOLEAN DEFAULT true,
    operating_hours JSONB, -- 24/7 or specific hours
    timezone VARCHAR(50) DEFAULT 'UTC',
    
    -- Limits and configuration
    daily_limit DECIMAL(20,2),
    transaction_limit DECIMAL(20,2),
    supported_currencies currency_code[] NOT NULL DEFAULT '{}',
    
    -- API configuration
    api_endpoint TEXT,
    webhook_url TEXT,
    public_key TEXT, -- For message verification
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT valid_country CHECK (country_code ~ '^[A-Z]{2}$'),
    CONSTRAINT valid_bic CHECK (bic_code IS NULL OR bic_code ~ '^[A-Z]{6}[A-Z0-9]{2}([A-Z0-9]{3})?$')
);

-- Accounts for participants
CREATE TABLE accounts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    participant_id UUID NOT NULL REFERENCES participants(id),
    account_number VARCHAR(50) NOT NULL,
    account_name VARCHAR(255) NOT NULL,
    currency currency_code NOT NULL,
    
    -- Account details
    account_type VARCHAR(20) DEFAULT 'CURRENT', -- CURRENT, SAVINGS, NOSTRO, VOSTRO
    balance DECIMAL(20,2) NOT NULL DEFAULT 0,
    available_balance DECIMAL(20,2) NOT NULL DEFAULT 0,
    
    -- Limits
    daily_debit_limit DECIMAL(20,2),
    daily_credit_limit DECIMAL(20,2),
    
    -- Status
    is_active BOOLEAN DEFAULT true,
    is_blocked BOOLEAN DEFAULT false,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT positive_balance CHECK (balance >= 0),
    CONSTRAINT available_balance_check CHECK (available_balance <= balance),
    CONSTRAINT unique_account_per_participant UNIQUE (participant_id, account_number, currency)
);

-- Payment messages (ISO 20022 based)
CREATE TABLE payment_messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    message_id VARCHAR(100) UNIQUE NOT NULL,
    
    -- Message metadata
    message_type VARCHAR(20) NOT NULL, -- pacs.008, pacs.002, camt.056, etc.
    creation_datetime TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    settlement_date DATE,
    
    -- Payment details
    payment_type payment_type NOT NULL,
    amount DECIMAL(20,2) NOT NULL,
    currency currency_code NOT NULL,
    
    -- Cross-border specific
    source_currency currency_code,
    target_currency currency_code,
    fx_rate DECIMAL(12,6),
    fx_contract_id VARCHAR(50),
    
    -- Parties
    debtor_name VARCHAR(255) NOT NULL,
    debtor_account VARCHAR(50) NOT NULL,
    debtor_agent VARCHAR(50) NOT NULL, -- BIC or routing number
    debtor_participant_id UUID REFERENCES participants(id),
    
    creditor_name VARCHAR(255) NOT NULL,
    creditor_account VARCHAR(50) NOT NULL,
    creditor_agent VARCHAR(50) NOT NULL,
    creditor_participant_id UUID REFERENCES participants(id),
    
    -- Routing information
    network_type network_type,
    correspondent_bank VARCHAR(50),
    clearing_system VARCHAR(20),
    
    -- Payment purpose and details
    purpose_code VARCHAR(10), -- TRADE, SALA, PENS, etc.
    remittance_info TEXT,
    end_to_end_id VARCHAR(100),
    transaction_id VARCHAR(100),
    
    -- Processing status
    status payment_status DEFAULT 'PENDING',
    processing_started_at TIMESTAMP WITH TIME ZONE,
    processing_completed_at TIMESTAMP WITH TIME ZONE,
    
    -- Error handling
    error_code VARCHAR(20),
    error_description TEXT,
    retry_count INTEGER DEFAULT 0,
    
    -- Compliance
    sanctions_checked BOOLEAN DEFAULT false,
    sanctions_result VARCHAR(20), -- CLEAR, BLOCK, REVIEW
    aml_score DECIMAL(3,2), -- 0.00 to 1.00
    
    -- Performance metrics
    processing_time_ms INTEGER,
    network_latency_ms INTEGER,
    
    -- Raw message data
    original_message JSONB,
    iso20022_message XML,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT positive_amount CHECK (amount > 0),
    CONSTRAINT valid_fx_rate CHECK (fx_rate IS NULL OR fx_rate > 0),
    CONSTRAINT valid_message_id CHECK (message_id ~ '^[A-Za-z0-9]{1,35}$'),
    CONSTRAINT valid_aml_score CHECK (aml_score IS NULL OR (aml_score >= 0 AND aml_score <= 1))
);

-- Payment events (for audit trail and event sourcing)
CREATE TABLE payment_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    payment_id UUID NOT NULL REFERENCES payment_messages(id),
    event_type VARCHAR(50) NOT NULL,
    event_status VARCHAR(50) NOT NULL,
    
    -- Event details
    event_data JSONB,
    processing_node VARCHAR(100),
    
    -- Timing
    event_timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    processing_time_ms INTEGER,
    
    -- External references
    external_reference VARCHAR(100),
    network_response JSONB,
    
    -- Constraints
    CONSTRAINT valid_event_type CHECK (event_type IN ('RECEIVED', 'VALIDATED', 'ROUTED', 'SENT', 'ACKNOWLEDGED', 'SETTLED', 'FAILED', 'RETURNED'))
);

-- FX rates for cross-border payments
CREATE TABLE fx_rates (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    base_currency currency_code NOT NULL,
    target_currency currency_code NOT NULL,
    rate DECIMAL(12,6) NOT NULL,
    
    -- Rate metadata
    rate_type VARCHAR(20) DEFAULT 'SPOT', -- SPOT, FORWARD, SWAP
    source VARCHAR(50) NOT NULL, -- REUTERS, BLOOMBERG, ECB, etc.
    
    -- Validity
    valid_from TIMESTAMP WITH TIME ZONE NOT NULL,
    valid_until TIMESTAMP WITH TIME ZONE NOT NULL,
    
    -- Spread and fees
    bid_rate DECIMAL(12,6),
    ask_rate DECIMAL(12,6),
    spread_bps INTEGER, -- Basis points
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT positive_rate CHECK (rate > 0),
    CONSTRAINT different_currencies CHECK (base_currency != target_currency),
    CONSTRAINT valid_timeframe CHECK (valid_until > valid_from)
);

-- Settlement instructions
CREATE TABLE settlement_instructions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    payment_id UUID NOT NULL REFERENCES payment_messages(id),
    
    -- Settlement details
    settlement_method VARCHAR(20) NOT NULL, -- RTGS, PREFUNDED, NOSTRO
    settlement_account VARCHAR(50),
    settlement_amount DECIMAL(20,2) NOT NULL,
    settlement_currency currency_code NOT NULL,
    
    -- Timing
    settlement_date DATE NOT NULL,
    settlement_time TIME,
    value_date DATE,
    
    -- Status
    status settlement_status DEFAULT 'PENDING',
    
    -- External references
    settlement_reference VARCHAR(100),
    clearing_reference VARCHAR(100),
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    settled_at TIMESTAMP WITH TIME ZONE,
    
    -- Constraints
    CONSTRAINT positive_settlement_amount CHECK (settlement_amount > 0)
);

-- Liquidity pools for instant settlement
CREATE TABLE liquidity_pools (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    participant_id UUID NOT NULL REFERENCES participants(id),
    currency currency_code NOT NULL,
    
    -- Pool details
    pool_name VARCHAR(100) NOT NULL,
    total_capacity DECIMAL(20,2) NOT NULL,
    available_liquidity DECIMAL(20,2) NOT NULL,
    reserved_liquidity DECIMAL(20,2) NOT NULL DEFAULT 0,
    
    -- Thresholds
    minimum_threshold DECIMAL(20,2) NOT NULL,
    warning_threshold DECIMAL(20,2) NOT NULL,
    
    -- Status
    is_active BOOLEAN DEFAULT true,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT positive_capacity CHECK (total_capacity > 0),
    CONSTRAINT liquidity_balance CHECK (available_liquidity + reserved_liquidity <= total_capacity),
    CONSTRAINT valid_thresholds CHECK (minimum_threshold <= warning_threshold),
    CONSTRAINT unique_pool_per_currency UNIQUE (participant_id, currency)
);

-- Network routing rules
CREATE TABLE routing_rules (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    rule_name VARCHAR(100) NOT NULL,
    
    -- Routing criteria
    source_country VARCHAR(2),
    target_country VARCHAR(2),
    currency currency_code,
    amount_min DECIMAL(20,2),
    amount_max DECIMAL(20,2),
    
    -- Network preference
    preferred_network network_type NOT NULL,
    fallback_networks network_type[] DEFAULT '{}',
    
    -- Timing
    operating_hours JSONB,
    
    -- Status
    is_active BOOLEAN DEFAULT true,
    priority INTEGER DEFAULT 100,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Sanctions and watchlist screening
CREATE TABLE sanctions_lists (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    list_name VARCHAR(100) NOT NULL,
    list_type VARCHAR(50) NOT NULL, -- OFAC, EU, UN, etc.
    
    -- Entity details
    entity_name VARCHAR(255) NOT NULL,
    entity_type VARCHAR(50), -- INDIVIDUAL, ENTITY, VESSEL, etc.
    aliases TEXT[], -- Alternative names
    
    -- Identifiers
    identifiers JSONB, -- Passport, national ID, etc.
    addresses JSONB,
    
    -- List metadata
    list_date DATE NOT NULL,
    effective_date DATE,
    
    -- Status
    is_active BOOLEAN DEFAULT true,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Performance metrics
CREATE TABLE performance_metrics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    metric_name VARCHAR(100) NOT NULL,
    metric_value DECIMAL(12,4) NOT NULL,
    metric_unit VARCHAR(20) NOT NULL, -- ms, tps, percent, etc.
    
    -- Dimensions
    service_name VARCHAR(100),
    network_type network_type,
    currency currency_code,
    
    -- Timing
    measurement_time TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Metadata
    tags JSONB
);

-- Create indexes for performance
CREATE INDEX idx_payment_messages_message_id ON payment_messages(message_id);
CREATE INDEX idx_payment_messages_status ON payment_messages(status);
CREATE INDEX idx_payment_messages_created_at ON payment_messages(created_at);
CREATE INDEX idx_payment_messages_debtor_participant ON payment_messages(debtor_participant_id);
CREATE INDEX idx_payment_messages_creditor_participant ON payment_messages(creditor_participant_id);
CREATE INDEX idx_payment_messages_network_type ON payment_messages(network_type);
CREATE INDEX idx_payment_messages_currency ON payment_messages(currency);

CREATE INDEX idx_payment_events_payment_id ON payment_events(payment_id);
CREATE INDEX idx_payment_events_event_timestamp ON payment_events(event_timestamp);
CREATE INDEX idx_payment_events_event_type ON payment_events(event_type);

CREATE INDEX idx_accounts_participant_id ON accounts(participant_id);
CREATE INDEX idx_accounts_account_number ON accounts(account_number);
CREATE INDEX idx_accounts_currency ON accounts(currency);

CREATE INDEX idx_fx_rates_currencies ON fx_rates(base_currency, target_currency);
CREATE INDEX idx_fx_rates_valid_from ON fx_rates(valid_from);
CREATE INDEX idx_fx_rates_valid_until ON fx_rates(valid_until);

CREATE INDEX idx_settlement_instructions_payment_id ON settlement_instructions(payment_id);
CREATE INDEX idx_settlement_instructions_settlement_date ON settlement_instructions(settlement_date);
CREATE INDEX idx_settlement_instructions_status ON settlement_instructions(status);

CREATE INDEX idx_liquidity_pools_participant_currency ON liquidity_pools(participant_id, currency);

CREATE INDEX idx_sanctions_lists_entity_name ON sanctions_lists USING gin(entity_name gin_trgm_ops);
CREATE INDEX idx_sanctions_lists_aliases ON sanctions_lists USING gin(aliases);

CREATE INDEX idx_performance_metrics_time ON performance_metrics(measurement_time);
CREATE INDEX idx_performance_metrics_service ON performance_metrics(service_name);

-- Create triggers for updated_at timestamps
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_participants_updated_at BEFORE UPDATE ON participants FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_accounts_updated_at BEFORE UPDATE ON accounts FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_payment_messages_updated_at BEFORE UPDATE ON payment_messages FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_liquidity_pools_updated_at BEFORE UPDATE ON liquidity_pools FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_routing_rules_updated_at BEFORE UPDATE ON routing_rules FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_sanctions_lists_updated_at BEFORE UPDATE ON sanctions_lists FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Create function for balance updates
CREATE OR REPLACE FUNCTION update_account_balance()
RETURNS TRIGGER AS $$
BEGIN
    -- Update available balance when balance changes
    IF TG_OP = 'UPDATE' AND OLD.balance != NEW.balance THEN
        -- Ensure available balance doesn't exceed actual balance
        IF NEW.available_balance > NEW.balance THEN
            NEW.available_balance = NEW.balance;
        END IF;
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_account_balance_trigger 
    BEFORE UPDATE ON accounts 
    FOR EACH ROW EXECUTE FUNCTION update_account_balance();

-- Create function for liquidity pool validation
CREATE OR REPLACE FUNCTION validate_liquidity_pool()
RETURNS TRIGGER AS $$
BEGIN
    -- Ensure liquidity constraints are maintained
    IF NEW.available_liquidity + NEW.reserved_liquidity > NEW.total_capacity THEN
        RAISE EXCEPTION 'Liquidity pool capacity exceeded: available (%) + reserved (%) > capacity (%)', 
            NEW.available_liquidity, NEW.reserved_liquidity, NEW.total_capacity;
    END IF;
    
    -- Check minimum threshold
    IF NEW.available_liquidity < NEW.minimum_threshold THEN
        -- Log warning or trigger alert
        INSERT INTO payment_events (payment_id, event_type, event_status, event_data)
        VALUES (uuid_generate_v4(), 'LIQUIDITY_WARNING', 'LOW_LIQUIDITY', 
                jsonb_build_object('pool_id', NEW.id, 'available', NEW.available_liquidity, 'threshold', NEW.minimum_threshold));
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER validate_liquidity_pool_trigger 
    BEFORE INSERT OR UPDATE ON liquidity_pools 
    FOR EACH ROW EXECUTE FUNCTION validate_liquidity_pool();

-- Grant permissions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO realtime_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO realtime_user;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO realtime_user;

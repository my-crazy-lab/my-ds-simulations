-- Clearing & Settlement Engine Database Schema
-- Optimized for interbank settlement, netting, and risk management

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "btree_gist";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Create custom types
CREATE TYPE participant_type AS ENUM ('BANK', 'CLEARING_HOUSE', 'CENTRAL_BANK', 'BROKER_DEALER', 'CUSTODIAN');
CREATE TYPE transaction_status AS ENUM ('PENDING', 'VALIDATED', 'NETTED', 'SETTLED', 'FAILED', 'CANCELLED');
CREATE TYPE settlement_method AS ENUM ('RTGS', 'DNS', 'CLS', 'CBDC', 'PREFUNDED');
CREATE TYPE netting_type AS ENUM ('BILATERAL', 'MULTILATERAL', 'CLOSE_OUT', 'PAYMENT');
CREATE TYPE risk_status AS ENUM ('NORMAL', 'WARNING', 'BREACH', 'CRITICAL');
CREATE TYPE collateral_type AS ENUM ('CASH', 'GOVERNMENT_BONDS', 'CORPORATE_BONDS', 'EQUITIES', 'GOLD');
CREATE TYPE settlement_cycle AS ENUM ('T0', 'T1', 'T2', 'T3', 'INTRADAY');

-- Clearing participants (banks, institutions)
CREATE TABLE participants (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    participant_code VARCHAR(20) UNIQUE NOT NULL,
    participant_name VARCHAR(255) NOT NULL,
    participant_type participant_type NOT NULL,
    
    -- Regulatory identifiers
    bic_code VARCHAR(11),
    lei_code VARCHAR(20), -- Legal Entity Identifier
    regulatory_id VARCHAR(50),
    country_code VARCHAR(2) NOT NULL,
    
    -- Settlement configuration
    settlement_methods settlement_method[] NOT NULL DEFAULT '{}',
    supported_currencies VARCHAR(3)[] NOT NULL DEFAULT '{}',
    default_settlement_cycle settlement_cycle DEFAULT 'T1',
    
    -- Risk limits
    credit_limit DECIMAL(20,2) DEFAULT 0,
    debit_limit DECIMAL(20,2) DEFAULT 0,
    intraday_limit DECIMAL(20,2) DEFAULT 0,
    
    -- Operational details
    is_active BOOLEAN DEFAULT true,
    is_suspended BOOLEAN DEFAULT false,
    suspension_reason TEXT,
    
    -- Contact information
    primary_contact JSONB,
    settlement_contact JSONB,
    risk_contact JSONB,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT valid_country CHECK (country_code ~ '^[A-Z]{2}$'),
    CONSTRAINT valid_bic CHECK (bic_code IS NULL OR bic_code ~ '^[A-Z]{6}[A-Z0-9]{2}([A-Z0-9]{3})?$')
);

-- Settlement accounts for participants
CREATE TABLE settlement_accounts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    participant_id UUID NOT NULL REFERENCES participants(id),
    account_number VARCHAR(50) NOT NULL,
    account_name VARCHAR(255) NOT NULL,
    currency VARCHAR(3) NOT NULL,
    
    -- Account details
    account_type VARCHAR(20) DEFAULT 'SETTLEMENT', -- SETTLEMENT, COLLATERAL, RESERVE
    balance DECIMAL(20,2) NOT NULL DEFAULT 0,
    available_balance DECIMAL(20,2) NOT NULL DEFAULT 0,
    reserved_balance DECIMAL(20,2) NOT NULL DEFAULT 0,
    
    -- Central bank account details
    central_bank_account VARCHAR(50),
    rtgs_account VARCHAR(50),
    
    -- Status
    is_active BOOLEAN DEFAULT true,
    is_blocked BOOLEAN DEFAULT false,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT positive_balance CHECK (balance >= 0),
    CONSTRAINT balance_consistency CHECK (available_balance + reserved_balance <= balance),
    CONSTRAINT unique_account_per_participant UNIQUE (participant_id, account_number, currency)
);

-- Clearing transactions
CREATE TABLE clearing_transactions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    transaction_id VARCHAR(100) UNIQUE NOT NULL,
    
    -- Transaction details
    payer_participant_id UUID NOT NULL REFERENCES participants(id),
    payee_participant_id UUID NOT NULL REFERENCES participants(id),
    amount DECIMAL(20,2) NOT NULL,
    currency VARCHAR(3) NOT NULL,
    
    -- Transaction metadata
    transaction_type VARCHAR(50) NOT NULL, -- CREDIT_TRANSFER, DEBIT_TRANSFER, FX_SETTLEMENT, etc.
    priority VARCHAR(20) DEFAULT 'NORMAL', -- HIGH, NORMAL, LOW
    value_date DATE NOT NULL,
    settlement_date DATE,
    
    -- Processing status
    status transaction_status DEFAULT 'PENDING',
    processing_stage VARCHAR(50),
    
    -- Netting information
    netting_batch_id UUID,
    net_amount DECIMAL(20,2),
    netting_type netting_type,
    
    -- Settlement information
    settlement_batch_id UUID,
    settlement_method settlement_method,
    settlement_reference VARCHAR(100),
    
    -- Risk and compliance
    risk_score DECIMAL(5,2),
    requires_approval BOOLEAN DEFAULT false,
    approved_by VARCHAR(100),
    approved_at TIMESTAMP WITH TIME ZONE,
    
    -- External references
    original_message_id VARCHAR(100),
    external_reference VARCHAR(100),
    
    -- Error handling
    error_code VARCHAR(20),
    error_description TEXT,
    retry_count INTEGER DEFAULT 0,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    processed_at TIMESTAMP WITH TIME ZONE,
    settled_at TIMESTAMP WITH TIME ZONE,
    
    -- Constraints
    CONSTRAINT positive_amount CHECK (amount > 0),
    CONSTRAINT different_participants CHECK (payer_participant_id != payee_participant_id),
    CONSTRAINT valid_transaction_id CHECK (transaction_id ~ '^[A-Za-z0-9_-]{1,100}$')
);

-- Netting batches
CREATE TABLE netting_batches (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    batch_id VARCHAR(100) UNIQUE NOT NULL,
    
    -- Batch details
    netting_type netting_type NOT NULL,
    currency VARCHAR(3) NOT NULL,
    value_date DATE NOT NULL,
    
    -- Participants involved
    participant_ids UUID[] NOT NULL,
    transaction_count INTEGER NOT NULL DEFAULT 0,
    
    -- Netting results
    gross_amount DECIMAL(20,2) NOT NULL DEFAULT 0,
    net_amount DECIMAL(20,2) NOT NULL DEFAULT 0,
    netting_efficiency DECIMAL(5,2), -- Percentage reduction
    
    -- Processing status
    status VARCHAR(20) DEFAULT 'PENDING', -- PENDING, PROCESSING, COMPLETED, FAILED
    
    -- Timing
    cutoff_time TIMESTAMP WITH TIME ZONE,
    processing_started_at TIMESTAMP WITH TIME ZONE,
    processing_completed_at TIMESTAMP WITH TIME ZONE,
    processing_duration_ms INTEGER,
    
    -- Algorithm details
    netting_algorithm VARCHAR(50) DEFAULT 'STANDARD',
    optimization_level VARCHAR(20) DEFAULT 'NORMAL',
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT positive_amounts CHECK (gross_amount >= 0 AND net_amount >= 0),
    CONSTRAINT valid_efficiency CHECK (netting_efficiency IS NULL OR (netting_efficiency >= 0 AND netting_efficiency <= 100))
);

-- Netting positions (results of netting)
CREATE TABLE netting_positions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    netting_batch_id UUID NOT NULL REFERENCES netting_batches(id),
    participant_id UUID NOT NULL REFERENCES participants(id),
    
    -- Position details
    gross_debit DECIMAL(20,2) NOT NULL DEFAULT 0,
    gross_credit DECIMAL(20,2) NOT NULL DEFAULT 0,
    net_position DECIMAL(20,2) NOT NULL DEFAULT 0, -- Positive = net creditor, Negative = net debtor
    
    -- Transaction counts
    debit_transaction_count INTEGER DEFAULT 0,
    credit_transaction_count INTEGER DEFAULT 0,
    
    -- Settlement requirements
    settlement_amount DECIMAL(20,2),
    settlement_direction VARCHAR(10), -- RECEIVE, PAY
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT valid_net_position CHECK (net_position = gross_credit - gross_debit),
    CONSTRAINT unique_position_per_batch UNIQUE (netting_batch_id, participant_id)
);

-- Settlement batches
CREATE TABLE settlement_batches (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    batch_id VARCHAR(100) UNIQUE NOT NULL,
    
    -- Batch details
    settlement_method settlement_method NOT NULL,
    currency VARCHAR(3) NOT NULL,
    settlement_date DATE NOT NULL,
    settlement_cycle settlement_cycle NOT NULL,
    
    -- Participants and amounts
    participant_ids UUID[] NOT NULL,
    total_amount DECIMAL(20,2) NOT NULL,
    transaction_count INTEGER NOT NULL DEFAULT 0,
    
    -- Processing status
    status VARCHAR(20) DEFAULT 'PENDING', -- PENDING, PROCESSING, SETTLED, FAILED, CANCELLED
    
    -- Settlement details
    central_bank_reference VARCHAR(100),
    rtgs_reference VARCHAR(100),
    settlement_time TIMESTAMP WITH TIME ZONE,
    
    -- Risk and collateral
    required_collateral DECIMAL(20,2) DEFAULT 0,
    available_collateral DECIMAL(20,2) DEFAULT 0,
    collateral_shortfall DECIMAL(20,2) DEFAULT 0,
    
    -- Processing timing
    processing_started_at TIMESTAMP WITH TIME ZONE,
    processing_completed_at TIMESTAMP WITH TIME ZONE,
    processing_duration_ms INTEGER,
    
    -- Error handling
    error_code VARCHAR(20),
    error_description TEXT,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT positive_total_amount CHECK (total_amount >= 0)
);

-- Settlement instructions
CREATE TABLE settlement_instructions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    settlement_batch_id UUID NOT NULL REFERENCES settlement_batches(id),
    participant_id UUID NOT NULL REFERENCES participants(id),
    
    -- Instruction details
    instruction_type VARCHAR(20) NOT NULL, -- DEBIT, CREDIT
    amount DECIMAL(20,2) NOT NULL,
    currency VARCHAR(3) NOT NULL,
    
    -- Account details
    settlement_account_id UUID REFERENCES settlement_accounts(id),
    central_bank_account VARCHAR(50),
    
    -- Processing status
    status VARCHAR(20) DEFAULT 'PENDING', -- PENDING, SENT, ACKNOWLEDGED, SETTLED, FAILED
    
    -- External references
    instruction_reference VARCHAR(100),
    central_bank_reference VARCHAR(100),
    
    -- Timing
    sent_at TIMESTAMP WITH TIME ZONE,
    acknowledged_at TIMESTAMP WITH TIME ZONE,
    settled_at TIMESTAMP WITH TIME ZONE,
    
    -- Error handling
    error_code VARCHAR(20),
    error_description TEXT,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT positive_amount CHECK (amount > 0),
    CONSTRAINT valid_instruction_type CHECK (instruction_type IN ('DEBIT', 'CREDIT'))
);

-- Risk exposures
CREATE TABLE risk_exposures (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    participant_id UUID NOT NULL REFERENCES participants(id),
    counterparty_id UUID REFERENCES participants(id),
    
    -- Exposure details
    currency VARCHAR(3) NOT NULL,
    gross_exposure DECIMAL(20,2) NOT NULL DEFAULT 0,
    net_exposure DECIMAL(20,2) NOT NULL DEFAULT 0,
    potential_future_exposure DECIMAL(20,2) DEFAULT 0,
    
    -- Limits
    credit_limit DECIMAL(20,2),
    exposure_limit DECIMAL(20,2),
    
    -- Risk metrics
    risk_status risk_status DEFAULT 'NORMAL',
    utilization_percentage DECIMAL(5,2),
    
    -- Timing
    calculation_time TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    next_calculation_time TIMESTAMP WITH TIME ZONE,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT positive_exposures CHECK (gross_exposure >= 0 AND net_exposure >= 0),
    CONSTRAINT valid_utilization CHECK (utilization_percentage IS NULL OR (utilization_percentage >= 0 AND utilization_percentage <= 100))
);

-- Collateral pools
CREATE TABLE collateral_pools (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    participant_id UUID NOT NULL REFERENCES participants(id),
    pool_name VARCHAR(100) NOT NULL,
    
    -- Pool details
    currency VARCHAR(3) NOT NULL,
    total_value DECIMAL(20,2) NOT NULL DEFAULT 0,
    available_value DECIMAL(20,2) NOT NULL DEFAULT 0,
    allocated_value DECIMAL(20,2) NOT NULL DEFAULT 0,
    
    -- Pool configuration
    minimum_value DECIMAL(20,2) NOT NULL DEFAULT 0,
    target_value DECIMAL(20,2),
    
    -- Status
    is_active BOOLEAN DEFAULT true,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT positive_values CHECK (total_value >= 0 AND available_value >= 0 AND allocated_value >= 0),
    CONSTRAINT value_consistency CHECK (available_value + allocated_value <= total_value),
    CONSTRAINT unique_pool_per_participant UNIQUE (participant_id, pool_name, currency)
);

-- Collateral assets
CREATE TABLE collateral_assets (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    collateral_pool_id UUID NOT NULL REFERENCES collateral_pools(id),
    
    -- Asset details
    asset_type collateral_type NOT NULL,
    asset_identifier VARCHAR(100) NOT NULL, -- ISIN, CUSIP, etc.
    asset_name VARCHAR(255),
    
    -- Valuation
    nominal_value DECIMAL(20,2) NOT NULL,
    market_value DECIMAL(20,2) NOT NULL,
    haircut_percentage DECIMAL(5,2) NOT NULL DEFAULT 0,
    eligible_value DECIMAL(20,2) NOT NULL,
    
    -- Asset details
    maturity_date DATE,
    credit_rating VARCHAR(10),
    issuer VARCHAR(255),
    
    -- Status
    is_eligible BOOLEAN DEFAULT true,
    is_allocated BOOLEAN DEFAULT false,
    allocation_reference VARCHAR(100),
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_valued_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT positive_values CHECK (nominal_value > 0 AND market_value >= 0 AND eligible_value >= 0),
    CONSTRAINT valid_haircut CHECK (haircut_percentage >= 0 AND haircut_percentage <= 100),
    CONSTRAINT eligible_value_calc CHECK (eligible_value <= market_value * (1 - haircut_percentage / 100))
);

-- Settlement events (audit trail)
CREATE TABLE settlement_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_type VARCHAR(50) NOT NULL,
    entity_type VARCHAR(50) NOT NULL, -- TRANSACTION, BATCH, PARTICIPANT, etc.
    entity_id UUID NOT NULL,
    
    -- Event details
    event_data JSONB,
    previous_state VARCHAR(50),
    new_state VARCHAR(50),
    
    -- Processing info
    processing_node VARCHAR(100),
    user_id VARCHAR(100),
    
    -- Timestamp
    event_timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT valid_event_type CHECK (event_type IN ('CREATED', 'UPDATED', 'PROCESSED', 'SETTLED', 'FAILED', 'CANCELLED', 'APPROVED', 'REJECTED'))
);

-- Create indexes for performance
CREATE INDEX idx_clearing_transactions_payer ON clearing_transactions(payer_participant_id);
CREATE INDEX idx_clearing_transactions_payee ON clearing_transactions(payee_participant_id);
CREATE INDEX idx_clearing_transactions_status ON clearing_transactions(status);
CREATE INDEX idx_clearing_transactions_value_date ON clearing_transactions(value_date);
CREATE INDEX idx_clearing_transactions_currency ON clearing_transactions(currency);
CREATE INDEX idx_clearing_transactions_netting_batch ON clearing_transactions(netting_batch_id);
CREATE INDEX idx_clearing_transactions_settlement_batch ON clearing_transactions(settlement_batch_id);

CREATE INDEX idx_netting_batches_status ON netting_batches(status);
CREATE INDEX idx_netting_batches_value_date ON netting_batches(value_date);
CREATE INDEX idx_netting_batches_currency ON netting_batches(currency);
CREATE INDEX idx_netting_batches_type ON netting_batches(netting_type);

CREATE INDEX idx_netting_positions_batch ON netting_positions(netting_batch_id);
CREATE INDEX idx_netting_positions_participant ON netting_positions(participant_id);

CREATE INDEX idx_settlement_batches_status ON settlement_batches(status);
CREATE INDEX idx_settlement_batches_settlement_date ON settlement_batches(settlement_date);
CREATE INDEX idx_settlement_batches_currency ON settlement_batches(currency);
CREATE INDEX idx_settlement_batches_method ON settlement_batches(settlement_method);

CREATE INDEX idx_settlement_instructions_batch ON settlement_instructions(settlement_batch_id);
CREATE INDEX idx_settlement_instructions_participant ON settlement_instructions(participant_id);
CREATE INDEX idx_settlement_instructions_status ON settlement_instructions(status);

CREATE INDEX idx_risk_exposures_participant ON risk_exposures(participant_id);
CREATE INDEX idx_risk_exposures_counterparty ON risk_exposures(counterparty_id);
CREATE INDEX idx_risk_exposures_currency ON risk_exposures(currency);
CREATE INDEX idx_risk_exposures_status ON risk_exposures(risk_status);

CREATE INDEX idx_collateral_pools_participant ON collateral_pools(participant_id);
CREATE INDEX idx_collateral_pools_currency ON collateral_pools(currency);

CREATE INDEX idx_collateral_assets_pool ON collateral_assets(collateral_pool_id);
CREATE INDEX idx_collateral_assets_type ON collateral_assets(asset_type);
CREATE INDEX idx_collateral_assets_eligible ON collateral_assets(is_eligible);

CREATE INDEX idx_settlement_events_entity ON settlement_events(entity_type, entity_id);
CREATE INDEX idx_settlement_events_timestamp ON settlement_events(event_timestamp);
CREATE INDEX idx_settlement_events_type ON settlement_events(event_type);

-- Create triggers for updated_at timestamps
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_participants_updated_at BEFORE UPDATE ON participants FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_settlement_accounts_updated_at BEFORE UPDATE ON settlement_accounts FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_clearing_transactions_updated_at BEFORE UPDATE ON clearing_transactions FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_netting_batches_updated_at BEFORE UPDATE ON netting_batches FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_settlement_batches_updated_at BEFORE UPDATE ON settlement_batches FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_settlement_instructions_updated_at BEFORE UPDATE ON settlement_instructions FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_risk_exposures_updated_at BEFORE UPDATE ON risk_exposures FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_collateral_pools_updated_at BEFORE UPDATE ON collateral_pools FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_collateral_assets_updated_at BEFORE UPDATE ON collateral_assets FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Create function for balance validation
CREATE OR REPLACE FUNCTION validate_settlement_account_balance()
RETURNS TRIGGER AS $$
BEGIN
    -- Ensure balance consistency
    IF NEW.available_balance + NEW.reserved_balance > NEW.balance THEN
        RAISE EXCEPTION 'Balance consistency violation: available (%) + reserved (%) > balance (%)', 
            NEW.available_balance, NEW.reserved_balance, NEW.balance;
    END IF;
    
    -- Check for negative balances
    IF NEW.balance < 0 OR NEW.available_balance < 0 OR NEW.reserved_balance < 0 THEN
        RAISE EXCEPTION 'Negative balance not allowed: balance=%, available=%, reserved=%', 
            NEW.balance, NEW.available_balance, NEW.reserved_balance;
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER validate_settlement_account_balance_trigger 
    BEFORE INSERT OR UPDATE ON settlement_accounts 
    FOR EACH ROW EXECUTE FUNCTION validate_settlement_account_balance();

-- Create function for netting efficiency calculation
CREATE OR REPLACE FUNCTION calculate_netting_efficiency()
RETURNS TRIGGER AS $$
BEGIN
    -- Calculate netting efficiency as percentage reduction
    IF NEW.gross_amount > 0 THEN
        NEW.netting_efficiency = ((NEW.gross_amount - NEW.net_amount) / NEW.gross_amount) * 100;
    ELSE
        NEW.netting_efficiency = 0;
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER calculate_netting_efficiency_trigger 
    BEFORE INSERT OR UPDATE ON netting_batches 
    FOR EACH ROW EXECUTE FUNCTION calculate_netting_efficiency();

-- Grant permissions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO settlement_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO settlement_user;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO settlement_user;

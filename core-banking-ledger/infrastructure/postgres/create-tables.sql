-- Core Banking Ledger Database Schema
-- This schema implements double-entry bookkeeping with ACID guarantees

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "btree_gist";

-- Create custom types
CREATE TYPE account_type AS ENUM ('ASSET', 'LIABILITY', 'EQUITY', 'REVENUE', 'EXPENSE');
CREATE TYPE transaction_status AS ENUM ('PENDING', 'COMMITTED', 'FAILED', 'REVERSED');
CREATE TYPE entry_type AS ENUM ('DEBIT', 'CREDIT');
CREATE TYPE reconciliation_status AS ENUM ('PENDING', 'MATCHED', 'UNMATCHED', 'DISCREPANCY');

-- Chart of Accounts
CREATE TABLE chart_of_accounts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    account_code VARCHAR(20) UNIQUE NOT NULL,
    account_name VARCHAR(255) NOT NULL,
    account_type account_type NOT NULL,
    parent_account_code VARCHAR(20) REFERENCES chart_of_accounts(account_code),
    is_active BOOLEAN DEFAULT true,
    currency VARCHAR(3) DEFAULT 'USD',
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_by VARCHAR(100),
    
    -- Constraints
    CONSTRAINT valid_account_code CHECK (account_code ~ '^[0-9A-Z-]+$'),
    CONSTRAINT valid_currency CHECK (currency ~ '^[A-Z]{3}$')
);

-- Create indexes for chart_of_accounts
CREATE INDEX idx_chart_accounts_code ON chart_of_accounts(account_code);
CREATE INDEX idx_chart_accounts_type ON chart_of_accounts(account_type);
CREATE INDEX idx_chart_accounts_parent ON chart_of_accounts(parent_account_code);
CREATE INDEX idx_chart_accounts_active ON chart_of_accounts(is_active) WHERE is_active = true;

-- Account Balances (materialized view for performance)
CREATE TABLE account_balances (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    account_code VARCHAR(20) NOT NULL REFERENCES chart_of_accounts(account_code),
    currency VARCHAR(3) NOT NULL DEFAULT 'USD',
    balance_amount DECIMAL(20,4) NOT NULL DEFAULT 0.00,
    pending_amount DECIMAL(20,4) NOT NULL DEFAULT 0.00,
    available_amount DECIMAL(20,4) GENERATED ALWAYS AS (balance_amount - pending_amount) STORED,
    last_transaction_id UUID,
    last_updated TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    version_number BIGINT DEFAULT 1,
    
    -- Constraints
    UNIQUE(account_code, currency),
    CONSTRAINT valid_balance_currency CHECK (currency ~ '^[A-Z]{3}$')
);

-- Create indexes for account_balances
CREATE INDEX idx_account_balances_code ON account_balances(account_code);
CREATE INDEX idx_account_balances_currency ON account_balances(currency);
CREATE INDEX idx_account_balances_updated ON account_balances(last_updated);

-- Transactions (header table)
CREATE TABLE transactions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    transaction_id VARCHAR(100) UNIQUE NOT NULL,
    description TEXT NOT NULL,
    reference_number VARCHAR(100),
    transaction_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    value_date DATE DEFAULT CURRENT_DATE,
    status transaction_status DEFAULT 'PENDING',
    total_amount DECIMAL(20,4) NOT NULL,
    currency VARCHAR(3) NOT NULL DEFAULT 'USD',
    source_system VARCHAR(50),
    batch_id VARCHAR(100),
    idempotency_key VARCHAR(255) UNIQUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_by VARCHAR(100),
    approved_by VARCHAR(100),
    approved_at TIMESTAMP WITH TIME ZONE,
    
    -- Audit fields
    correlation_id UUID DEFAULT uuid_generate_v4(),
    trace_id VARCHAR(100),
    
    -- Constraints
    CONSTRAINT valid_transaction_id CHECK (transaction_id ~ '^[A-Za-z0-9-_]+$'),
    CONSTRAINT valid_currency CHECK (currency ~ '^[A-Z]{3}$'),
    CONSTRAINT positive_amount CHECK (total_amount > 0)
);

-- Create indexes for transactions
CREATE INDEX idx_transactions_id ON transactions(transaction_id);
CREATE INDEX idx_transactions_date ON transactions(transaction_date);
CREATE INDEX idx_transactions_status ON transactions(status);
CREATE INDEX idx_transactions_batch ON transactions(batch_id);
CREATE INDEX idx_transactions_correlation ON transactions(correlation_id);
CREATE INDEX idx_transactions_idempotency ON transactions(idempotency_key);

-- Transaction Entries (double-entry details)
CREATE TABLE transaction_entries (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    transaction_id UUID NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
    entry_sequence INTEGER NOT NULL,
    account_code VARCHAR(20) NOT NULL REFERENCES chart_of_accounts(account_code),
    entry_type entry_type NOT NULL,
    amount DECIMAL(20,4) NOT NULL,
    currency VARCHAR(3) NOT NULL DEFAULT 'USD',
    description TEXT,
    reference_data JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Constraints
    UNIQUE(transaction_id, entry_sequence),
    CONSTRAINT positive_entry_amount CHECK (amount > 0),
    CONSTRAINT valid_entry_currency CHECK (currency ~ '^[A-Z]{3}$')
);

-- Create indexes for transaction_entries
CREATE INDEX idx_entries_transaction ON transaction_entries(transaction_id);
CREATE INDEX idx_entries_account ON transaction_entries(account_code);
CREATE INDEX idx_entries_type ON transaction_entries(entry_type);
CREATE INDEX idx_entries_amount ON transaction_entries(amount);
CREATE INDEX idx_entries_created ON transaction_entries(created_at);

-- Audit Trail (immutable log)
CREATE TABLE audit_trail (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_id VARCHAR(100) UNIQUE NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    entity_type VARCHAR(50) NOT NULL,
    entity_id VARCHAR(100) NOT NULL,
    old_values JSONB,
    new_values JSONB,
    changed_fields TEXT[],
    event_timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    user_id VARCHAR(100),
    session_id VARCHAR(100),
    ip_address INET,
    user_agent TEXT,
    correlation_id UUID,
    trace_id VARCHAR(100),
    
    -- Cryptographic integrity
    hash_value VARCHAR(64) NOT NULL,
    previous_hash VARCHAR(64),
    merkle_root VARCHAR(64),
    
    -- Constraints
    CONSTRAINT valid_event_id CHECK (event_id ~ '^[A-Za-z0-9-_]+$')
);

-- Create indexes for audit_trail
CREATE INDEX idx_audit_event_id ON audit_trail(event_id);
CREATE INDEX idx_audit_entity ON audit_trail(entity_type, entity_id);
CREATE INDEX idx_audit_timestamp ON audit_trail(event_timestamp);
CREATE INDEX idx_audit_user ON audit_trail(user_id);
CREATE INDEX idx_audit_correlation ON audit_trail(correlation_id);
CREATE INDEX idx_audit_hash ON audit_trail(hash_value);

-- Reconciliation Records
CREATE TABLE reconciliation_batches (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    batch_id VARCHAR(100) UNIQUE NOT NULL,
    reconciliation_date DATE NOT NULL,
    start_time TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    end_time TIMESTAMP WITH TIME ZONE,
    status reconciliation_status DEFAULT 'PENDING',
    total_transactions BIGINT DEFAULT 0,
    matched_transactions BIGINT DEFAULT 0,
    unmatched_transactions BIGINT DEFAULT 0,
    discrepancy_amount DECIMAL(20,4) DEFAULT 0.00,
    currency VARCHAR(3) DEFAULT 'USD',
    created_by VARCHAR(100),
    
    -- Constraints
    CONSTRAINT valid_recon_batch_id CHECK (batch_id ~ '^[A-Za-z0-9-_]+$'),
    CONSTRAINT valid_recon_currency CHECK (currency ~ '^[A-Z]{3}$')
);

-- Create indexes for reconciliation_batches
CREATE INDEX idx_recon_batch_id ON reconciliation_batches(batch_id);
CREATE INDEX idx_recon_date ON reconciliation_batches(reconciliation_date);
CREATE INDEX idx_recon_status ON reconciliation_batches(status);

-- Reconciliation Details
CREATE TABLE reconciliation_details (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    batch_id UUID NOT NULL REFERENCES reconciliation_batches(id) ON DELETE CASCADE,
    transaction_id UUID REFERENCES transactions(id),
    external_reference VARCHAR(100),
    account_code VARCHAR(20) REFERENCES chart_of_accounts(account_code),
    expected_amount DECIMAL(20,4),
    actual_amount DECIMAL(20,4),
    difference_amount DECIMAL(20,4) GENERATED ALWAYS AS (expected_amount - actual_amount) STORED,
    status reconciliation_status DEFAULT 'PENDING',
    notes TEXT,
    resolved_at TIMESTAMP WITH TIME ZONE,
    resolved_by VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for reconciliation_details
CREATE INDEX idx_recon_details_batch ON reconciliation_details(batch_id);
CREATE INDEX idx_recon_details_transaction ON reconciliation_details(transaction_id);
CREATE INDEX idx_recon_details_account ON reconciliation_details(account_code);
CREATE INDEX idx_recon_details_status ON reconciliation_details(status);

-- Idempotency Keys (for duplicate prevention)
CREATE TABLE idempotency_keys (
    key_value VARCHAR(255) PRIMARY KEY,
    entity_type VARCHAR(50) NOT NULL,
    entity_id VARCHAR(100) NOT NULL,
    response_data JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE DEFAULT (NOW() + INTERVAL '24 hours')
);

-- Create indexes for idempotency_keys
CREATE INDEX idx_idempotency_entity ON idempotency_keys(entity_type, entity_id);
CREATE INDEX idx_idempotency_expires ON idempotency_keys(expires_at);

-- Distributed Locks (for concurrency control)
CREATE TABLE distributed_locks (
    lock_name VARCHAR(255) PRIMARY KEY,
    lock_owner VARCHAR(255) NOT NULL,
    acquired_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    metadata JSONB
);

-- Create indexes for distributed_locks
CREATE INDEX idx_locks_owner ON distributed_locks(lock_owner);
CREATE INDEX idx_locks_expires ON distributed_locks(expires_at);

-- Create triggers for updated_at timestamps
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_chart_of_accounts_updated_at BEFORE UPDATE ON chart_of_accounts FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_transactions_updated_at BEFORE UPDATE ON transactions FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Create function to validate double-entry balance
CREATE OR REPLACE FUNCTION validate_double_entry_balance()
RETURNS TRIGGER AS $$
DECLARE
    debit_total DECIMAL(20,4);
    credit_total DECIMAL(20,4);
BEGIN
    -- Calculate total debits and credits for the transaction
    SELECT 
        COALESCE(SUM(CASE WHEN entry_type = 'DEBIT' THEN amount ELSE 0 END), 0),
        COALESCE(SUM(CASE WHEN entry_type = 'CREDIT' THEN amount ELSE 0 END), 0)
    INTO debit_total, credit_total
    FROM transaction_entries 
    WHERE transaction_id = NEW.transaction_id;
    
    -- Ensure debits equal credits
    IF debit_total != credit_total THEN
        RAISE EXCEPTION 'Double-entry validation failed: Debits (%) must equal Credits (%) for transaction %', 
            debit_total, credit_total, NEW.transaction_id;
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger for double-entry validation
CREATE TRIGGER validate_double_entry_trigger 
    AFTER INSERT OR UPDATE ON transaction_entries 
    FOR EACH ROW EXECUTE FUNCTION validate_double_entry_balance();

-- Create function to update account balances
CREATE OR REPLACE FUNCTION update_account_balance()
RETURNS TRIGGER AS $$
BEGIN
    -- Update account balance based on entry type and account type
    INSERT INTO account_balances (account_code, currency, balance_amount, last_transaction_id, last_updated, version_number)
    VALUES (NEW.account_code, NEW.currency, 
            CASE 
                WHEN NEW.entry_type = 'DEBIT' THEN NEW.amount
                ELSE -NEW.amount
            END,
            (SELECT id FROM transactions WHERE id = NEW.transaction_id),
            NOW(), 1)
    ON CONFLICT (account_code, currency) 
    DO UPDATE SET
        balance_amount = account_balances.balance_amount + 
            CASE 
                WHEN NEW.entry_type = 'DEBIT' THEN NEW.amount
                ELSE -NEW.amount
            END,
        last_transaction_id = (SELECT id FROM transactions WHERE id = NEW.transaction_id),
        last_updated = NOW(),
        version_number = account_balances.version_number + 1;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger for balance updates
CREATE TRIGGER update_balance_trigger 
    AFTER INSERT ON transaction_entries 
    FOR EACH ROW EXECUTE FUNCTION update_account_balance();

-- Create function for audit trail
CREATE OR REPLACE FUNCTION create_audit_record()
RETURNS TRIGGER AS $$
DECLARE
    event_type_val VARCHAR(50);
    old_vals JSONB;
    new_vals JSONB;
    changed_fields_arr TEXT[];
    hash_input TEXT;
    computed_hash VARCHAR(64);
    prev_hash VARCHAR(64);
BEGIN
    -- Determine event type
    IF TG_OP = 'INSERT' THEN
        event_type_val := 'CREATE';
        old_vals := NULL;
        new_vals := to_jsonb(NEW);
    ELSIF TG_OP = 'UPDATE' THEN
        event_type_val := 'UPDATE';
        old_vals := to_jsonb(OLD);
        new_vals := to_jsonb(NEW);
        -- Find changed fields
        SELECT array_agg(key) INTO changed_fields_arr
        FROM jsonb_each(old_vals) o
        JOIN jsonb_each(new_vals) n ON o.key = n.key
        WHERE o.value != n.value;
    ELSIF TG_OP = 'DELETE' THEN
        event_type_val := 'DELETE';
        old_vals := to_jsonb(OLD);
        new_vals := NULL;
    END IF;
    
    -- Get previous hash for chaining
    SELECT hash_value INTO prev_hash 
    FROM audit_trail 
    ORDER BY event_timestamp DESC 
    LIMIT 1;
    
    -- Compute hash for integrity
    hash_input := COALESCE(prev_hash, '') || event_type_val || TG_TABLE_NAME || 
                  COALESCE(new_vals::text, '') || COALESCE(old_vals::text, '');
    computed_hash := encode(digest(hash_input, 'sha256'), 'hex');
    
    -- Insert audit record
    INSERT INTO audit_trail (
        event_id, event_type, entity_type, entity_id,
        old_values, new_values, changed_fields,
        hash_value, previous_hash,
        correlation_id
    ) VALUES (
        uuid_generate_v4()::text,
        event_type_val,
        TG_TABLE_NAME,
        COALESCE(NEW.id::text, OLD.id::text),
        old_vals,
        new_vals,
        changed_fields_arr,
        computed_hash,
        prev_hash,
        COALESCE(NEW.correlation_id, OLD.correlation_id, uuid_generate_v4())
    );
    
    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

-- Create audit triggers for key tables
CREATE TRIGGER audit_chart_of_accounts AFTER INSERT OR UPDATE OR DELETE ON chart_of_accounts FOR EACH ROW EXECUTE FUNCTION create_audit_record();
CREATE TRIGGER audit_transactions AFTER INSERT OR UPDATE OR DELETE ON transactions FOR EACH ROW EXECUTE FUNCTION create_audit_record();
CREATE TRIGGER audit_transaction_entries AFTER INSERT OR UPDATE OR DELETE ON transaction_entries FOR EACH ROW EXECUTE FUNCTION create_audit_record();
CREATE TRIGGER audit_account_balances AFTER INSERT OR UPDATE OR DELETE ON account_balances FOR EACH ROW EXECUTE FUNCTION create_audit_record();

-- Create cleanup function for expired records
CREATE OR REPLACE FUNCTION cleanup_expired_records()
RETURNS void AS $$
BEGIN
    -- Clean up expired idempotency keys
    DELETE FROM idempotency_keys WHERE expires_at < NOW();
    
    -- Clean up expired distributed locks
    DELETE FROM distributed_locks WHERE expires_at < NOW();
    
    -- Log cleanup activity
    RAISE NOTICE 'Cleanup completed at %', NOW();
END;
$$ LANGUAGE plpgsql;

-- Grant permissions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO banking_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO banking_user;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO banking_user;

-- Payments Acquiring Gateway Database Schema
-- PCI DSS compliant schema with field-level encryption

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "btree_gist";

-- Create custom types
CREATE TYPE payment_status AS ENUM ('PENDING', 'AUTHORIZED', 'CAPTURED', 'SETTLED', 'FAILED', 'CANCELLED', 'REFUNDED');
CREATE TYPE card_brand AS ENUM ('VISA', 'MASTERCARD', 'AMEX', 'DISCOVER', 'JCB', 'DINERS', 'UNIONPAY');
CREATE TYPE transaction_type AS ENUM ('AUTHORIZATION', 'CAPTURE', 'REFUND', 'VOID');
CREATE TYPE fraud_status AS ENUM ('CLEAN', 'REVIEW', 'BLOCK');
CREATE TYPE three_ds_status AS ENUM ('NOT_ENROLLED', 'ENROLLED', 'AUTHENTICATED', 'FAILED', 'BYPASSED');
CREATE TYPE settlement_status AS ENUM ('PENDING', 'PROCESSING', 'SETTLED', 'FAILED');

-- Merchants table
CREATE TABLE merchants (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    merchant_id VARCHAR(50) UNIQUE NOT NULL,
    merchant_name VARCHAR(255) NOT NULL,
    business_type VARCHAR(100),
    mcc VARCHAR(4), -- Merchant Category Code
    country_code VARCHAR(2) NOT NULL,
    currency VARCHAR(3) NOT NULL DEFAULT 'USD',
    is_active BOOLEAN DEFAULT true,
    risk_level VARCHAR(20) DEFAULT 'LOW',
    
    -- PCI compliance fields
    pci_compliance_level VARCHAR(10) DEFAULT 'SAQ-A',
    last_pci_scan DATE,
    
    -- API credentials (encrypted)
    api_key_hash VARCHAR(255),
    webhook_url TEXT,
    webhook_secret_hash VARCHAR(255),
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT valid_mcc CHECK (mcc ~ '^[0-9]{4}$'),
    CONSTRAINT valid_country CHECK (country_code ~ '^[A-Z]{2}$'),
    CONSTRAINT valid_currency CHECK (currency ~ '^[A-Z]{3}$')
);

-- Card tokens (PCI scope - encrypted storage)
CREATE TABLE card_tokens (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    token VARCHAR(255) UNIQUE NOT NULL,
    
    -- Encrypted card data (using application-level encryption)
    encrypted_pan TEXT NOT NULL, -- Encrypted PAN
    pan_hash VARCHAR(64) NOT NULL, -- SHA-256 hash for lookups
    encrypted_expiry TEXT NOT NULL,
    card_brand card_brand NOT NULL,
    last_four VARCHAR(4) NOT NULL,
    
    -- Tokenization metadata
    tokenization_method VARCHAR(50) DEFAULT 'AES-256-GCM',
    key_version INTEGER DEFAULT 1,
    
    -- Card metadata
    issuer_country VARCHAR(2),
    issuer_bank VARCHAR(100),
    card_type VARCHAR(20), -- DEBIT, CREDIT, PREPAID
    
    -- Security
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE,
    last_used_at TIMESTAMP WITH TIME ZONE,
    
    -- Constraints
    CONSTRAINT valid_last_four CHECK (last_four ~ '^[0-9]{4}$'),
    CONSTRAINT valid_token CHECK (token ~ '^tok_[A-Za-z0-9]{24}$')
);

-- Payments table
CREATE TABLE payments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    payment_id VARCHAR(100) UNIQUE NOT NULL,
    merchant_id UUID NOT NULL REFERENCES merchants(id),
    
    -- Payment details
    amount DECIMAL(12,2) NOT NULL,
    currency VARCHAR(3) NOT NULL,
    description TEXT,
    reference_id VARCHAR(100),
    
    -- Card information (tokenized)
    card_token_id UUID REFERENCES card_tokens(id),
    card_last_four VARCHAR(4),
    card_brand card_brand,
    
    -- Status and processing
    status payment_status DEFAULT 'PENDING',
    transaction_type transaction_type DEFAULT 'AUTHORIZATION',
    
    -- External references
    psp_transaction_id VARCHAR(100),
    psp_reference VARCHAR(100),
    acquirer_reference VARCHAR(100),
    
    -- Fraud detection
    fraud_score DECIMAL(3,2), -- 0.00 to 1.00
    fraud_status fraud_status DEFAULT 'CLEAN',
    fraud_reason TEXT,
    
    -- 3D Secure
    three_ds_status three_ds_status DEFAULT 'NOT_ENROLLED',
    three_ds_transaction_id VARCHAR(100),
    three_ds_eci VARCHAR(2),
    three_ds_cavv TEXT,
    three_ds_xid TEXT,
    
    -- Billing address
    billing_street TEXT,
    billing_city VARCHAR(100),
    billing_state VARCHAR(100),
    billing_zip VARCHAR(20),
    billing_country VARCHAR(2),
    
    -- Processing metadata
    processing_time_ms INTEGER,
    retry_count INTEGER DEFAULT 0,
    last_retry_at TIMESTAMP WITH TIME ZONE,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    authorized_at TIMESTAMP WITH TIME ZONE,
    captured_at TIMESTAMP WITH TIME ZONE,
    settled_at TIMESTAMP WITH TIME ZONE,
    
    -- Constraints
    CONSTRAINT positive_amount CHECK (amount > 0),
    CONSTRAINT valid_currency CHECK (currency ~ '^[A-Z]{3}$'),
    CONSTRAINT valid_fraud_score CHECK (fraud_score >= 0 AND fraud_score <= 1),
    CONSTRAINT valid_payment_id CHECK (payment_id ~ '^pay_[A-Za-z0-9]{24}$')
);

-- Payment events (audit trail)
CREATE TABLE payment_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    payment_id UUID NOT NULL REFERENCES payments(id),
    event_type VARCHAR(50) NOT NULL,
    event_status VARCHAR(50) NOT NULL,
    
    -- Event details
    amount DECIMAL(12,2),
    currency VARCHAR(3),
    description TEXT,
    
    -- External references
    psp_response JSONB,
    gateway_response JSONB,
    
    -- Processing info
    processing_time_ms INTEGER,
    error_code VARCHAR(50),
    error_message TEXT,
    
    -- Metadata
    user_agent TEXT,
    ip_address INET,
    correlation_id UUID DEFAULT uuid_generate_v4(),
    
    -- Timestamp
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT valid_event_type CHECK (event_type IN ('AUTHORIZATION', 'CAPTURE', 'REFUND', 'VOID', 'FRAUD_CHECK', '3DS_AUTH'))
);

-- Refunds table
CREATE TABLE refunds (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    refund_id VARCHAR(100) UNIQUE NOT NULL,
    payment_id UUID NOT NULL REFERENCES payments(id),
    
    -- Refund details
    amount DECIMAL(12,2) NOT NULL,
    currency VARCHAR(3) NOT NULL,
    reason TEXT,
    
    -- Status
    status payment_status DEFAULT 'PENDING',
    
    -- External references
    psp_refund_id VARCHAR(100),
    psp_reference VARCHAR(100),
    
    -- Processing
    processing_time_ms INTEGER,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    processed_at TIMESTAMP WITH TIME ZONE,
    
    -- Constraints
    CONSTRAINT positive_refund_amount CHECK (amount > 0),
    CONSTRAINT valid_refund_currency CHECK (currency ~ '^[A-Z]{3}$'),
    CONSTRAINT valid_refund_id CHECK (refund_id ~ '^ref_[A-Za-z0-9]{24}$')
);

-- Settlement batches
CREATE TABLE settlement_batches (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    batch_id VARCHAR(100) UNIQUE NOT NULL,
    merchant_id UUID NOT NULL REFERENCES merchants(id),
    
    -- Batch details
    settlement_date DATE NOT NULL,
    currency VARCHAR(3) NOT NULL,
    total_amount DECIMAL(12,2) NOT NULL,
    transaction_count INTEGER NOT NULL,
    
    -- Status
    status settlement_status DEFAULT 'PENDING',
    
    -- External references
    bank_reference VARCHAR(100),
    acquirer_batch_id VARCHAR(100),
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    processed_at TIMESTAMP WITH TIME ZONE,
    
    -- Constraints
    CONSTRAINT valid_batch_id CHECK (batch_id ~ '^bat_[A-Za-z0-9]{24}$')
);

-- Settlement transactions
CREATE TABLE settlement_transactions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    batch_id UUID NOT NULL REFERENCES settlement_batches(id),
    payment_id UUID NOT NULL REFERENCES payments(id),
    
    -- Settlement details
    gross_amount DECIMAL(12,2) NOT NULL,
    fee_amount DECIMAL(12,2) NOT NULL DEFAULT 0,
    net_amount DECIMAL(12,2) NOT NULL,
    currency VARCHAR(3) NOT NULL,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Fraud rules
CREATE TABLE fraud_rules (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    rule_name VARCHAR(100) UNIQUE NOT NULL,
    rule_type VARCHAR(50) NOT NULL, -- VELOCITY, GEOLOCATION, AMOUNT, etc.
    
    -- Rule configuration
    rule_config JSONB NOT NULL,
    threshold_value DECIMAL(10,4),
    action VARCHAR(20) NOT NULL, -- BLOCK, REVIEW, ALLOW
    
    -- Status
    is_active BOOLEAN DEFAULT true,
    priority INTEGER DEFAULT 100,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT valid_action CHECK (action IN ('BLOCK', 'REVIEW', 'ALLOW'))
);

-- Fraud alerts
CREATE TABLE fraud_alerts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    payment_id UUID NOT NULL REFERENCES payments(id),
    rule_id UUID REFERENCES fraud_rules(id),
    
    -- Alert details
    alert_type VARCHAR(50) NOT NULL,
    risk_score DECIMAL(3,2) NOT NULL,
    reason TEXT NOT NULL,
    
    -- Status
    status VARCHAR(20) DEFAULT 'OPEN', -- OPEN, REVIEWED, CLOSED
    reviewed_by VARCHAR(100),
    reviewed_at TIMESTAMP WITH TIME ZONE,
    resolution TEXT,
    
    -- Timestamp
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT valid_risk_score CHECK (risk_score >= 0 AND risk_score <= 1)
);

-- PSP configurations
CREATE TABLE psp_configs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    psp_name VARCHAR(100) NOT NULL,
    psp_type VARCHAR(50) NOT NULL, -- STRIPE, ADYEN, BRAINTREE, etc.
    
    -- Configuration
    config JSONB NOT NULL,
    is_active BOOLEAN DEFAULT true,
    priority INTEGER DEFAULT 100,
    
    -- Routing rules
    routing_rules JSONB,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- API keys (for merchant authentication)
CREATE TABLE api_keys (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    merchant_id UUID NOT NULL REFERENCES merchants(id),
    
    -- Key details
    key_id VARCHAR(50) UNIQUE NOT NULL,
    key_hash VARCHAR(255) NOT NULL, -- Hashed API key
    key_prefix VARCHAR(10) NOT NULL, -- First few characters for identification
    
    -- Permissions
    permissions JSONB NOT NULL DEFAULT '[]',
    
    -- Status
    is_active BOOLEAN DEFAULT true,
    last_used_at TIMESTAMP WITH TIME ZONE,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE,
    
    -- Constraints
    CONSTRAINT valid_key_id CHECK (key_id ~ '^pk_(test|live)_[A-Za-z0-9]{24}$')
);

-- Create indexes for performance
CREATE INDEX idx_payments_merchant_id ON payments(merchant_id);
CREATE INDEX idx_payments_status ON payments(status);
CREATE INDEX idx_payments_created_at ON payments(created_at);
CREATE INDEX idx_payments_card_token ON payments(card_token_id);
CREATE INDEX idx_payments_psp_transaction ON payments(psp_transaction_id);

CREATE INDEX idx_card_tokens_pan_hash ON card_tokens(pan_hash);
CREATE INDEX idx_card_tokens_token ON card_tokens(token);
CREATE INDEX idx_card_tokens_last_four ON card_tokens(last_four);

CREATE INDEX idx_payment_events_payment_id ON payment_events(payment_id);
CREATE INDEX idx_payment_events_created_at ON payment_events(created_at);
CREATE INDEX idx_payment_events_event_type ON payment_events(event_type);

CREATE INDEX idx_refunds_payment_id ON refunds(payment_id);
CREATE INDEX idx_refunds_status ON refunds(status);

CREATE INDEX idx_settlement_batches_merchant_id ON settlement_batches(merchant_id);
CREATE INDEX idx_settlement_batches_settlement_date ON settlement_batches(settlement_date);

CREATE INDEX idx_fraud_alerts_payment_id ON fraud_alerts(payment_id);
CREATE INDEX idx_fraud_alerts_status ON fraud_alerts(status);
CREATE INDEX idx_fraud_alerts_created_at ON fraud_alerts(created_at);

CREATE INDEX idx_api_keys_merchant_id ON api_keys(merchant_id);
CREATE INDEX idx_api_keys_key_id ON api_keys(key_id);

-- Create triggers for updated_at timestamps
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_merchants_updated_at BEFORE UPDATE ON merchants FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_payments_updated_at BEFORE UPDATE ON payments FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_refunds_updated_at BEFORE UPDATE ON refunds FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_settlement_batches_updated_at BEFORE UPDATE ON settlement_batches FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_fraud_rules_updated_at BEFORE UPDATE ON fraud_rules FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_psp_configs_updated_at BEFORE UPDATE ON psp_configs FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Create function to validate payment amounts
CREATE OR REPLACE FUNCTION validate_payment_amount()
RETURNS TRIGGER AS $$
BEGIN
    -- Ensure refund amount doesn't exceed original payment
    IF TG_TABLE_NAME = 'refunds' THEN
        DECLARE
            payment_amount DECIMAL(12,2);
            total_refunded DECIMAL(12,2);
        BEGIN
            SELECT amount INTO payment_amount FROM payments WHERE id = NEW.payment_id;
            SELECT COALESCE(SUM(amount), 0) INTO total_refunded 
            FROM refunds 
            WHERE payment_id = NEW.payment_id AND status IN ('AUTHORIZED', 'CAPTURED', 'SETTLED');
            
            IF (total_refunded + NEW.amount) > payment_amount THEN
                RAISE EXCEPTION 'Refund amount exceeds original payment amount';
            END IF;
        END;
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger for refund validation
CREATE TRIGGER validate_refund_amount_trigger 
    BEFORE INSERT ON refunds 
    FOR EACH ROW EXECUTE FUNCTION validate_payment_amount();

-- Grant permissions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO payments_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO payments_user;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO payments_user;

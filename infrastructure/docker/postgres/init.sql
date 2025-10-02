-- Initialize microservices database
CREATE DATABASE IF NOT EXISTS microservices;

-- Connect to microservices database
\c microservices;

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Saga orchestrator tables
CREATE TABLE IF NOT EXISTS saga_instances (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    saga_type VARCHAR(100) NOT NULL,
    saga_data JSONB NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'STARTED',
    current_step INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    correlation_id VARCHAR(255),
    idempotency_key VARCHAR(255) UNIQUE
);

CREATE INDEX idx_saga_instances_status ON saga_instances(status);
CREATE INDEX idx_saga_instances_correlation_id ON saga_instances(correlation_id);
CREATE INDEX idx_saga_instances_idempotency_key ON saga_instances(idempotency_key);

CREATE TABLE IF NOT EXISTS saga_steps (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    saga_id UUID NOT NULL REFERENCES saga_instances(id) ON DELETE CASCADE,
    step_name VARCHAR(100) NOT NULL,
    step_order INTEGER NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
    input_data JSONB,
    output_data JSONB,
    error_message TEXT,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    retry_count INTEGER DEFAULT 0,
    compensation_data JSONB
);

CREATE INDEX idx_saga_steps_saga_id ON saga_steps(saga_id);
CREATE INDEX idx_saga_steps_status ON saga_steps(status);

-- Outbox pattern table
CREATE TABLE IF NOT EXISTS outbox_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    aggregate_id VARCHAR(255) NOT NULL,
    aggregate_type VARCHAR(100) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    event_data JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    processed_at TIMESTAMP WITH TIME ZONE,
    status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
    retry_count INTEGER DEFAULT 0,
    correlation_id VARCHAR(255),
    causation_id VARCHAR(255),
    version INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX idx_outbox_events_status ON outbox_events(status);
CREATE INDEX idx_outbox_events_aggregate_id ON outbox_events(aggregate_id);
CREATE INDEX idx_outbox_events_created_at ON outbox_events(created_at);

-- Inventory service tables
CREATE TABLE IF NOT EXISTS inventory_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    sku VARCHAR(100) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    quantity INTEGER NOT NULL DEFAULT 0,
    reserved_quantity INTEGER NOT NULL DEFAULT 0,
    price DECIMAL(10,2) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    version INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX idx_inventory_items_sku ON inventory_items(sku);

CREATE TABLE IF NOT EXISTS inventory_reservations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    item_id UUID NOT NULL REFERENCES inventory_items(id),
    order_id UUID NOT NULL,
    quantity INTEGER NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'RESERVED',
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    released_at TIMESTAMP WITH TIME ZONE,
    correlation_id VARCHAR(255)
);

CREATE INDEX idx_inventory_reservations_order_id ON inventory_reservations(order_id);
CREATE INDEX idx_inventory_reservations_status ON inventory_reservations(status);
CREATE INDEX idx_inventory_reservations_expires_at ON inventory_reservations(expires_at);

-- Payment service tables
CREATE TABLE IF NOT EXISTS payment_accounts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL,
    account_number VARCHAR(100) NOT NULL UNIQUE,
    balance DECIMAL(15,2) NOT NULL DEFAULT 0.00,
    currency VARCHAR(3) NOT NULL DEFAULT 'USD',
    status VARCHAR(50) NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    version INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX idx_payment_accounts_user_id ON payment_accounts(user_id);
CREATE INDEX idx_payment_accounts_account_number ON payment_accounts(account_number);

CREATE TABLE IF NOT EXISTS payment_transactions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    account_id UUID NOT NULL REFERENCES payment_accounts(id),
    order_id UUID NOT NULL,
    amount DECIMAL(15,2) NOT NULL,
    currency VARCHAR(3) NOT NULL DEFAULT 'USD',
    transaction_type VARCHAR(50) NOT NULL, -- CHARGE, REFUND, HOLD, RELEASE
    status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
    external_transaction_id VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    error_message TEXT,
    idempotency_key VARCHAR(255) UNIQUE,
    correlation_id VARCHAR(255)
);

CREATE INDEX idx_payment_transactions_order_id ON payment_transactions(order_id);
CREATE INDEX idx_payment_transactions_status ON payment_transactions(status);
CREATE INDEX idx_payment_transactions_idempotency_key ON payment_transactions(idempotency_key);

-- Notification service tables
CREATE TABLE IF NOT EXISTS notification_templates (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(100) NOT NULL UNIQUE,
    type VARCHAR(50) NOT NULL, -- EMAIL, SMS, PUSH
    subject VARCHAR(255),
    body TEXT NOT NULL,
    variables JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS notifications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    template_id UUID REFERENCES notification_templates(id),
    recipient VARCHAR(255) NOT NULL,
    type VARCHAR(50) NOT NULL,
    subject VARCHAR(255),
    body TEXT NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
    sent_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    retry_count INTEGER DEFAULT 0,
    error_message TEXT,
    correlation_id VARCHAR(255),
    order_id UUID
);

CREATE INDEX idx_notifications_status ON notifications(status);
CREATE INDEX idx_notifications_order_id ON notifications(order_id);
CREATE INDEX idx_notifications_correlation_id ON notifications(correlation_id);

-- Idempotency tracking table
CREATE TABLE IF NOT EXISTS idempotency_keys (
    key VARCHAR(255) PRIMARY KEY,
    response_data JSONB,
    status_code INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE INDEX idx_idempotency_keys_expires_at ON idempotency_keys(expires_at);

-- Insert sample data
INSERT INTO inventory_items (sku, name, description, quantity, price) VALUES
('LAPTOP-001', 'Gaming Laptop', 'High-performance gaming laptop', 10, 1299.99),
('MOUSE-001', 'Wireless Mouse', 'Ergonomic wireless mouse', 50, 29.99),
('KEYBOARD-001', 'Mechanical Keyboard', 'RGB mechanical keyboard', 25, 89.99);

INSERT INTO payment_accounts (user_id, account_number, balance) VALUES
('550e8400-e29b-41d4-a716-446655440001', 'ACC-001', 5000.00),
('550e8400-e29b-41d4-a716-446655440002', 'ACC-002', 3000.00),
('550e8400-e29b-41d4-a716-446655440003', 'ACC-003', 1500.00);

INSERT INTO notification_templates (name, type, subject, body, variables) VALUES
('order_confirmation', 'EMAIL', 'Order Confirmation - {{order_id}}', 
 'Thank you for your order {{order_id}}. Total amount: ${{amount}}', 
 '{"order_id": "string", "amount": "number"}'),
('payment_failed', 'EMAIL', 'Payment Failed - {{order_id}}', 
 'Your payment for order {{order_id}} has failed. Please try again.', 
 '{"order_id": "string"}'),
('inventory_reserved', 'EMAIL', 'Items Reserved - {{order_id}}', 
 'Items for order {{order_id}} have been reserved.', 
 '{"order_id": "string"}');

-- Create functions for updated_at triggers
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create triggers for updated_at
CREATE TRIGGER update_saga_instances_updated_at BEFORE UPDATE ON saga_instances FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_inventory_items_updated_at BEFORE UPDATE ON inventory_items FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_payment_accounts_updated_at BEFORE UPDATE ON payment_accounts FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_notification_templates_updated_at BEFORE UPDATE ON notification_templates FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ===== NEW SERVICES TABLES =====

-- Account Service Tables (for CQRS/Event Sourcing with Axon)
CREATE TABLE IF NOT EXISTS domain_event_entry (
    global_index BIGSERIAL PRIMARY KEY,
    aggregate_identifier VARCHAR(255) NOT NULL,
    sequence_number BIGINT NOT NULL,
    type VARCHAR(255) NOT NULL,
    event_identifier VARCHAR(255) NOT NULL UNIQUE,
    payload_type VARCHAR(255) NOT NULL,
    payload TEXT NOT NULL,
    meta_data TEXT,
    time_stamp VARCHAR(255) NOT NULL,
    UNIQUE (aggregate_identifier, sequence_number)
);

CREATE TABLE IF NOT EXISTS snapshot_event_entry (
    aggregate_identifier VARCHAR(255) PRIMARY KEY,
    sequence_number BIGINT NOT NULL,
    type VARCHAR(255) NOT NULL,
    event_identifier VARCHAR(255) NOT NULL UNIQUE,
    payload_type VARCHAR(255) NOT NULL,
    payload TEXT NOT NULL,
    meta_data TEXT,
    time_stamp VARCHAR(255) NOT NULL
);

CREATE TABLE IF NOT EXISTS saga_entry (
    saga_id VARCHAR(255) PRIMARY KEY,
    saga_type VARCHAR(255) NOT NULL,
    serialized_saga TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS association_value_entry (
    id BIGSERIAL PRIMARY KEY,
    association_key VARCHAR(255) NOT NULL,
    association_value VARCHAR(255) NOT NULL,
    saga_type VARCHAR(255) NOT NULL,
    saga_id VARCHAR(255) NOT NULL
);

-- Account projections
CREATE TABLE IF NOT EXISTS account_projection (
    account_id UUID PRIMARY KEY,
    account_number VARCHAR(50) UNIQUE NOT NULL,
    customer_id VARCHAR(255) NOT NULL,
    account_type VARCHAR(50) NOT NULL,
    status VARCHAR(50) NOT NULL,
    balance DECIMAL(19,2) NOT NULL DEFAULT 0,
    available_balance DECIMAL(19,2) NOT NULL DEFAULT 0,
    reserved_amount DECIMAL(19,2) NOT NULL DEFAULT 0,
    currency VARCHAR(3) NOT NULL DEFAULT 'USD',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    version BIGINT NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_account_customer_id ON account_projection(customer_id);
CREATE INDEX IF NOT EXISTS idx_account_number ON account_projection(account_number);
CREATE INDEX IF NOT EXISTS idx_account_status ON account_projection(status);

-- Outbox Events Table (for reliable event publishing)
CREATE TABLE IF NOT EXISTS outbox_events (
    id UUID PRIMARY KEY,
    aggregate_id VARCHAR(255) NOT NULL,
    aggregate_type VARCHAR(100) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    event_data JSONB NOT NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    processed_at TIMESTAMP WITH TIME ZONE,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    retry_count INTEGER NOT NULL DEFAULT 0,
    max_retries INTEGER NOT NULL DEFAULT 5,
    next_retry_at TIMESTAMP WITH TIME ZONE,
    error_message TEXT,
    topic VARCHAR(100) NOT NULL,
    partition_key VARCHAR(255),
    headers JSONB DEFAULT '{}',
    source VARCHAR(100) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_outbox_status ON outbox_events(status);
CREATE INDEX IF NOT EXISTS idx_outbox_created_at ON outbox_events(created_at);
CREATE INDEX IF NOT EXISTS idx_outbox_aggregate ON outbox_events(aggregate_id, aggregate_type);
CREATE INDEX IF NOT EXISTS idx_outbox_retry ON outbox_events(status, next_retry_at) WHERE status = 'failed';
CREATE INDEX IF NOT EXISTS idx_outbox_source ON outbox_events(source);

-- Fraud Detection Tables
CREATE TABLE IF NOT EXISTS fraud_assessments (
    id UUID PRIMARY KEY,
    transaction_id VARCHAR(255) NOT NULL,
    user_id VARCHAR(255) NOT NULL,
    fraud_score DECIMAL(5,4) NOT NULL,
    ml_score DECIMAL(5,4) NOT NULL,
    risk_level VARCHAR(20) NOT NULL,
    decision VARCHAR(20) NOT NULL,
    triggered_rules JSONB DEFAULT '[]',
    features_used JSONB DEFAULT '[]',
    processing_time_ms INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_fraud_transaction_id ON fraud_assessments(transaction_id);
CREATE INDEX IF NOT EXISTS idx_fraud_user_id ON fraud_assessments(user_id);
CREATE INDEX IF NOT EXISTS idx_fraud_created_at ON fraud_assessments(created_at);
CREATE INDEX IF NOT EXISTS idx_fraud_decision ON fraud_assessments(decision);
CREATE INDEX IF NOT EXISTS idx_fraud_risk_level ON fraud_assessments(risk_level);

-- User transaction history for fraud detection
CREATE TABLE IF NOT EXISTS user_transactions (
    id UUID PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    transaction_id VARCHAR(255) NOT NULL,
    amount DECIMAL(19,2) NOT NULL,
    currency VARCHAR(3) NOT NULL,
    merchant_id VARCHAR(255),
    merchant_category VARCHAR(100),
    country VARCHAR(2),
    device_fingerprint VARCHAR(255),
    ip_address INET,
    transaction_type VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_transactions_user_id ON user_transactions(user_id);
CREATE INDEX IF NOT EXISTS idx_user_transactions_created_at ON user_transactions(created_at);
CREATE INDEX IF NOT EXISTS idx_user_transactions_merchant ON user_transactions(merchant_id);

-- Device intelligence
CREATE TABLE IF NOT EXISTS device_intelligence (
    device_fingerprint VARCHAR(255) PRIMARY KEY,
    ip_address INET NOT NULL,
    is_vpn BOOLEAN DEFAULT FALSE,
    is_proxy BOOLEAN DEFAULT FALSE,
    is_tor BOOLEAN DEFAULT FALSE,
    risk_score DECIMAL(3,2) DEFAULT 0.5,
    ip_reputation DECIMAL(3,2) DEFAULT 0.5,
    first_seen TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    last_seen TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    transaction_count INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_device_ip ON device_intelligence(ip_address);
CREATE INDEX IF NOT EXISTS idx_device_risk ON device_intelligence(risk_score);

-- Fraud rules
CREATE TABLE IF NOT EXISTS fraud_rules (
    rule_id VARCHAR(100) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    rule_type VARCHAR(50) NOT NULL,
    threshold DECIMAL(19,2),
    weight DECIMAL(3,2) NOT NULL DEFAULT 0.5,
    severity VARCHAR(20) NOT NULL DEFAULT 'MEDIUM',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    trigger_count BIGINT DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

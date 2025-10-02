-- PostgreSQL Primary Database Initialization

-- Create replication user
CREATE USER replicator WITH REPLICATION ENCRYPTED PASSWORD 'replicator_pass';

-- Create extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";
CREATE EXTENSION IF NOT EXISTS "btree_gin";
CREATE EXTENSION IF NOT EXISTS "btree_gist";

-- Create schemas
CREATE SCHEMA IF NOT EXISTS saga;
CREATE SCHEMA IF NOT EXISTS inventory;
CREATE SCHEMA IF NOT EXISTS payment;
CREATE SCHEMA IF NOT EXISTS notification;
CREATE SCHEMA IF NOT EXISTS analytics;
CREATE SCHEMA IF NOT EXISTS sync;

-- Saga tables
CREATE TABLE IF NOT EXISTS saga.saga_instances (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    saga_type VARCHAR(100) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'STARTED',
    saga_data JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    timeout_at TIMESTAMP WITH TIME ZONE,
    correlation_id VARCHAR(255),
    idempotency_key VARCHAR(255) UNIQUE,
    version INTEGER DEFAULT 1,
    retry_count INTEGER DEFAULT 0,
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS saga.saga_steps (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    saga_id UUID NOT NULL REFERENCES saga.saga_instances(id) ON DELETE CASCADE,
    step_name VARCHAR(100) NOT NULL,
    step_order INTEGER NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
    step_data JSONB,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    compensation_data JSONB,
    version INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS saga.outbox_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    aggregate_id VARCHAR(255) NOT NULL,
    aggregate_type VARCHAR(100) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    event_data JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    processed_at TIMESTAMP WITH TIME ZONE,
    status VARCHAR(50) DEFAULT 'PENDING',
    retry_count INTEGER DEFAULT 0,
    correlation_id VARCHAR(255),
    causation_id VARCHAR(255),
    version INTEGER DEFAULT 1
);

-- Inventory tables
CREATE TABLE IF NOT EXISTS inventory.items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    sku VARCHAR(100) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    quantity INTEGER NOT NULL DEFAULT 0,
    reserved_quantity INTEGER NOT NULL DEFAULT 0,
    price DECIMAL(10,2) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    version INTEGER DEFAULT 1,
    shard_key VARCHAR(100) -- For sharding
);

CREATE TABLE IF NOT EXISTS inventory.reservations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    item_id UUID NOT NULL REFERENCES inventory.items(id),
    order_id UUID NOT NULL,
    quantity INTEGER NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'RESERVED',
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    released_at TIMESTAMP WITH TIME ZONE,
    correlation_id VARCHAR(255),
    version INTEGER DEFAULT 1
);

-- Payment tables
CREATE TABLE IF NOT EXISTS payment.payments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    order_id UUID NOT NULL,
    user_id UUID NOT NULL,
    amount DECIMAL(10,2) NOT NULL,
    currency VARCHAR(3) NOT NULL DEFAULT 'USD',
    payment_method VARCHAR(50) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
    external_payment_id VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    processed_at TIMESTAMP WITH TIME ZONE,
    correlation_id VARCHAR(255),
    version INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS payment.refunds (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    payment_id UUID NOT NULL REFERENCES payment.payments(id),
    amount DECIMAL(10,2) NOT NULL,
    reason TEXT,
    status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
    external_refund_id VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    processed_at TIMESTAMP WITH TIME ZONE,
    correlation_id VARCHAR(255),
    version INTEGER DEFAULT 1
);

-- Notification tables
CREATE TABLE IF NOT EXISTS notification.notifications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL,
    type VARCHAR(50) NOT NULL,
    channel VARCHAR(50) NOT NULL,
    recipient VARCHAR(255) NOT NULL,
    subject VARCHAR(255),
    content TEXT NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
    sent_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    correlation_id VARCHAR(255),
    version INTEGER DEFAULT 1
);

-- Sync tables for offline-online sync
CREATE TABLE IF NOT EXISTS sync.sync_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    device_id VARCHAR(255) NOT NULL,
    user_id UUID NOT NULL,
    entity_type VARCHAR(100) NOT NULL,
    entity_id VARCHAR(255) NOT NULL,
    operation VARCHAR(50) NOT NULL, -- INSERT, UPDATE, DELETE
    data JSONB NOT NULL,
    vector_clock JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    synced_at TIMESTAMP WITH TIME ZONE,
    conflict_resolved BOOLEAN DEFAULT FALSE,
    resolution_strategy VARCHAR(100)
);

CREATE TABLE IF NOT EXISTS sync.conflict_resolutions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    sync_log_id UUID NOT NULL REFERENCES sync.sync_logs(id),
    conflict_type VARCHAR(100) NOT NULL,
    local_data JSONB NOT NULL,
    remote_data JSONB NOT NULL,
    resolved_data JSONB NOT NULL,
    resolution_strategy VARCHAR(100) NOT NULL,
    resolved_by VARCHAR(255),
    resolved_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_saga_instances_status ON saga.saga_instances(status);
CREATE INDEX IF NOT EXISTS idx_saga_instances_type ON saga.saga_instances(saga_type);
CREATE INDEX IF NOT EXISTS idx_saga_instances_correlation ON saga.saga_instances(correlation_id);
CREATE INDEX IF NOT EXISTS idx_saga_instances_created_at ON saga.saga_instances(created_at);
CREATE INDEX IF NOT EXISTS idx_saga_instances_timeout ON saga.saga_instances(timeout_at) WHERE timeout_at IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_saga_steps_saga_id ON saga.saga_steps(saga_id);
CREATE INDEX IF NOT EXISTS idx_saga_steps_status ON saga.saga_steps(status);
CREATE INDEX IF NOT EXISTS idx_saga_steps_order ON saga.saga_steps(saga_id, step_order);

CREATE INDEX IF NOT EXISTS idx_outbox_events_status ON saga.outbox_events(status);
CREATE INDEX IF NOT EXISTS idx_outbox_events_created_at ON saga.outbox_events(created_at);
CREATE INDEX IF NOT EXISTS idx_outbox_events_aggregate ON saga.outbox_events(aggregate_type, aggregate_id);

CREATE INDEX IF NOT EXISTS idx_inventory_items_sku ON inventory.items(sku);
CREATE INDEX IF NOT EXISTS idx_inventory_items_shard_key ON inventory.items(shard_key);
CREATE INDEX IF NOT EXISTS idx_inventory_reservations_item_id ON inventory.reservations(item_id);
CREATE INDEX IF NOT EXISTS idx_inventory_reservations_order_id ON inventory.reservations(order_id);
CREATE INDEX IF NOT EXISTS idx_inventory_reservations_expires_at ON inventory.reservations(expires_at);

CREATE INDEX IF NOT EXISTS idx_payments_order_id ON payment.payments(order_id);
CREATE INDEX IF NOT EXISTS idx_payments_user_id ON payment.payments(user_id);
CREATE INDEX IF NOT EXISTS idx_payments_status ON payment.payments(status);

CREATE INDEX IF NOT EXISTS idx_notifications_user_id ON notification.notifications(user_id);
CREATE INDEX IF NOT EXISTS idx_notifications_status ON notification.notifications(status);

CREATE INDEX IF NOT EXISTS idx_sync_logs_device_user ON sync.sync_logs(device_id, user_id);
CREATE INDEX IF NOT EXISTS idx_sync_logs_entity ON sync.sync_logs(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_sync_logs_created_at ON sync.sync_logs(created_at);

-- Create partitioned tables for high-volume data
CREATE TABLE IF NOT EXISTS analytics.events (
    id UUID DEFAULT uuid_generate_v4(),
    event_type VARCHAR(100) NOT NULL,
    entity_id VARCHAR(255) NOT NULL,
    entity_type VARCHAR(100) NOT NULL,
    event_data JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    user_id UUID,
    session_id VARCHAR(255),
    correlation_id VARCHAR(255)
) PARTITION BY RANGE (created_at);

-- Create monthly partitions for events
CREATE TABLE IF NOT EXISTS analytics.events_2024_01 PARTITION OF analytics.events
    FOR VALUES FROM ('2024-01-01') TO ('2024-02-01');
CREATE TABLE IF NOT EXISTS analytics.events_2024_02 PARTITION OF analytics.events
    FOR VALUES FROM ('2024-02-01') TO ('2024-03-01');
CREATE TABLE IF NOT EXISTS analytics.events_2024_03 PARTITION OF analytics.events
    FOR VALUES FROM ('2024-03-01') TO ('2024-04-01');

-- Insert sample data
INSERT INTO inventory.items (sku, name, description, quantity, price, shard_key) VALUES
('LAPTOP-001', 'Gaming Laptop', 'High-performance gaming laptop', 50, 1299.99, 'electronics'),
('PHONE-001', 'Smartphone', 'Latest smartphone model', 100, 899.99, 'electronics'),
('BOOK-001', 'Programming Book', 'Learn advanced programming', 200, 49.99, 'books'),
('HEADPHONES-001', 'Wireless Headphones', 'Noise-cancelling headphones', 75, 299.99, 'electronics');

-- Create functions for triggers
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create triggers
CREATE TRIGGER update_saga_instances_updated_at BEFORE UPDATE ON saga.saga_instances FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_inventory_items_updated_at BEFORE UPDATE ON inventory.items FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- PostgreSQL Shard Database Initialization

-- Create extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";
CREATE EXTENSION IF NOT EXISTS "btree_gin";
CREATE EXTENSION IF NOT EXISTS "btree_gist";

-- Create schemas
CREATE SCHEMA IF NOT EXISTS inventory;
CREATE SCHEMA IF NOT EXISTS payment;
CREATE SCHEMA IF NOT EXISTS analytics;

-- Inventory tables (sharded)
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
    shard_key VARCHAR(100) NOT NULL -- Sharding key
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

-- Payment tables (sharded by user_id)
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
    version INTEGER DEFAULT 1,
    shard_key VARCHAR(100) NOT NULL -- Sharding key based on user_id
);

-- Analytics tables for shard-specific metrics
CREATE TABLE IF NOT EXISTS analytics.shard_metrics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    shard_id VARCHAR(50) NOT NULL,
    metric_name VARCHAR(100) NOT NULL,
    metric_value DECIMAL(15,4) NOT NULL,
    dimensions JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_inventory_items_shard_key ON inventory.items(shard_key);
CREATE INDEX IF NOT EXISTS idx_inventory_items_sku ON inventory.items(sku);
CREATE INDEX IF NOT EXISTS idx_inventory_reservations_item_id ON inventory.reservations(item_id);
CREATE INDEX IF NOT EXISTS idx_inventory_reservations_order_id ON inventory.reservations(order_id);

CREATE INDEX IF NOT EXISTS idx_payments_shard_key ON payment.payments(shard_key);
CREATE INDEX IF NOT EXISTS idx_payments_user_id ON payment.payments(user_id);
CREATE INDEX IF NOT EXISTS idx_payments_order_id ON payment.payments(order_id);
CREATE INDEX IF NOT EXISTS idx_payments_status ON payment.payments(status);

CREATE INDEX IF NOT EXISTS idx_shard_metrics_shard_id ON analytics.shard_metrics(shard_id);
CREATE INDEX IF NOT EXISTS idx_shard_metrics_name ON analytics.shard_metrics(metric_name);
CREATE INDEX IF NOT EXISTS idx_shard_metrics_created_at ON analytics.shard_metrics(created_at);

-- Create functions for triggers
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create triggers
CREATE TRIGGER update_inventory_items_updated_at BEFORE UPDATE ON inventory.items FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Function to determine shard key for items
CREATE OR REPLACE FUNCTION get_item_shard_key(sku VARCHAR)
RETURNS VARCHAR AS $$
BEGIN
    -- Simple hash-based sharding
    CASE 
        WHEN sku LIKE 'LAPTOP%' OR sku LIKE 'PHONE%' OR sku LIKE 'HEADPHONES%' THEN
            RETURN 'electronics';
        WHEN sku LIKE 'BOOK%' THEN
            RETURN 'books';
        WHEN sku LIKE 'CLOTHING%' THEN
            RETURN 'clothing';
        ELSE
            RETURN 'general';
    END CASE;
END;
$$ LANGUAGE plpgsql;

-- Function to determine shard key for payments based on user_id
CREATE OR REPLACE FUNCTION get_payment_shard_key(user_uuid UUID)
RETURNS VARCHAR AS $$
BEGIN
    -- Hash user_id to determine shard
    RETURN 'user_' || (hashtext(user_uuid::text) % 2)::text;
END;
$$ LANGUAGE plpgsql;

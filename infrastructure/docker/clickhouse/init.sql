-- ClickHouse Analytics Database Initialization

-- Create analytics database
CREATE DATABASE IF NOT EXISTS analytics;

-- Use analytics database
USE analytics;

-- Create events table for real-time analytics
CREATE TABLE IF NOT EXISTS events (
    id UUID DEFAULT generateUUIDv4(),
    event_type String,
    entity_id String,
    entity_type String,
    user_id Nullable(String),
    session_id Nullable(String),
    correlation_id Nullable(String),
    event_data String, -- JSON string
    timestamp DateTime64(3) DEFAULT now64(),
    date Date DEFAULT toDate(timestamp),
    hour UInt8 DEFAULT toHour(timestamp)
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(date)
ORDER BY (event_type, entity_type, timestamp)
TTL date + INTERVAL 1 YEAR
SETTINGS index_granularity = 8192;

-- Create saga events table
CREATE TABLE IF NOT EXISTS saga_events (
    id UUID DEFAULT generateUUIDv4(),
    saga_id String,
    saga_type String,
    event_type String,
    step_name Nullable(String),
    event_data String, -- JSON string
    timestamp DateTime64(3) DEFAULT now64(),
    date Date DEFAULT toDate(timestamp),
    correlation_id Nullable(String),
    causation_id Nullable(String)
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(date)
ORDER BY (saga_type, saga_id, timestamp)
TTL date + INTERVAL 2 YEARS
SETTINGS index_granularity = 8192;

-- Create inventory events table
CREATE TABLE IF NOT EXISTS inventory_events (
    id UUID DEFAULT generateUUIDv4(),
    item_id String,
    sku String,
    event_type String,
    quantity_before Int32,
    quantity_after Int32,
    reserved_before Int32,
    reserved_after Int32,
    order_id Nullable(String),
    timestamp DateTime64(3) DEFAULT now64(),
    date Date DEFAULT toDate(timestamp),
    correlation_id Nullable(String)
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(date)
ORDER BY (sku, timestamp)
TTL date + INTERVAL 1 YEAR
SETTINGS index_granularity = 8192;

-- Create payment events table
CREATE TABLE IF NOT EXISTS payment_events (
    id UUID DEFAULT generateUUIDv4(),
    payment_id String,
    order_id String,
    user_id String,
    event_type String,
    amount Decimal(10, 2),
    currency String,
    payment_method String,
    status String,
    timestamp DateTime64(3) DEFAULT now64(),
    date Date DEFAULT toDate(timestamp),
    correlation_id Nullable(String)
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(date)
ORDER BY (user_id, timestamp)
TTL date + INTERVAL 3 YEARS
SETTINGS index_granularity = 8192;

-- Create notification events table
CREATE TABLE IF NOT EXISTS notification_events (
    id UUID DEFAULT generateUUIDv4(),
    notification_id String,
    user_id String,
    event_type String,
    channel String,
    status String,
    timestamp DateTime64(3) DEFAULT now64(),
    date Date DEFAULT toDate(timestamp),
    correlation_id Nullable(String)
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(date)
ORDER BY (user_id, timestamp)
TTL date + INTERVAL 1 YEAR
SETTINGS index_granularity = 8192;

-- Create Kafka engine tables for real-time ingestion
CREATE TABLE IF NOT EXISTS kafka_events (
    id String,
    event_type String,
    entity_id String,
    entity_type String,
    user_id Nullable(String),
    session_id Nullable(String),
    correlation_id Nullable(String),
    event_data String,
    timestamp DateTime64(3)
) ENGINE = Kafka()
SETTINGS 
    kafka_broker_list = 'kafka:29092',
    kafka_topic_list = 'analytics-events',
    kafka_group_name = 'clickhouse-analytics',
    kafka_format = 'JSONEachRow',
    kafka_num_consumers = 3;

-- Create materialized view to move data from Kafka to events table
CREATE MATERIALIZED VIEW IF NOT EXISTS kafka_events_mv TO events AS
SELECT 
    toUUID(id) as id,
    event_type,
    entity_id,
    entity_type,
    user_id,
    session_id,
    correlation_id,
    event_data,
    timestamp,
    toDate(timestamp) as date,
    toHour(timestamp) as hour
FROM kafka_events;

-- Create aggregated tables for fast queries
CREATE TABLE IF NOT EXISTS daily_saga_metrics (
    date Date,
    saga_type String,
    total_sagas UInt64,
    completed_sagas UInt64,
    failed_sagas UInt64,
    compensated_sagas UInt64,
    avg_duration_seconds Float64,
    p95_duration_seconds Float64,
    p99_duration_seconds Float64
) ENGINE = SummingMergeTree()
PARTITION BY toYYYYMM(date)
ORDER BY (date, saga_type)
SETTINGS index_granularity = 8192;

CREATE TABLE IF NOT EXISTS hourly_inventory_metrics (
    date Date,
    hour UInt8,
    sku String,
    total_reservations UInt64,
    successful_reservations UInt64,
    failed_reservations UInt64,
    total_releases UInt64,
    avg_quantity_reserved Float64
) ENGINE = SummingMergeTree()
PARTITION BY toYYYYMM(date)
ORDER BY (date, hour, sku)
SETTINGS index_granularity = 8192;

CREATE TABLE IF NOT EXISTS daily_payment_metrics (
    date Date,
    currency String,
    payment_method String,
    total_payments UInt64,
    successful_payments UInt64,
    failed_payments UInt64,
    total_amount Decimal(15, 2),
    avg_amount Float64,
    total_refunds UInt64,
    total_refund_amount Decimal(15, 2)
) ENGINE = SummingMergeTree()
PARTITION BY toYYYYMM(date)
ORDER BY (date, currency, payment_method)
SETTINGS index_granularity = 8192;

-- Create time-travel tables for point-in-time analytics
CREATE TABLE IF NOT EXISTS inventory_snapshots (
    snapshot_date Date,
    snapshot_time DateTime,
    item_id String,
    sku String,
    quantity Int32,
    reserved_quantity Int32,
    price Decimal(10, 2),
    version UInt32
) ENGINE = ReplacingMergeTree(version)
PARTITION BY toYYYYMM(snapshot_date)
ORDER BY (snapshot_date, sku, snapshot_time)
SETTINGS index_granularity = 8192;

-- Create distributed tables for multi-node setup
CREATE TABLE IF NOT EXISTS events_distributed AS events
ENGINE = Distributed(analytics_cluster, analytics, events, rand());

CREATE TABLE IF NOT EXISTS saga_events_distributed AS saga_events
ENGINE = Distributed(analytics_cluster, analytics, saga_events, cityHash64(saga_id));

-- Create views for common queries
CREATE VIEW IF NOT EXISTS saga_success_rate AS
SELECT 
    saga_type,
    date,
    countIf(event_type = 'SAGA_COMPLETED') as completed,
    countIf(event_type = 'SAGA_FAILED') as failed,
    countIf(event_type = 'SAGA_COMPENSATED') as compensated,
    count() as total,
    completed / total * 100 as success_rate
FROM saga_events
WHERE event_type IN ('SAGA_COMPLETED', 'SAGA_FAILED', 'SAGA_COMPENSATED')
GROUP BY saga_type, date
ORDER BY date DESC, saga_type;

CREATE VIEW IF NOT EXISTS inventory_availability AS
SELECT 
    sku,
    argMax(quantity_after, timestamp) as current_quantity,
    argMax(reserved_after, timestamp) as current_reserved,
    current_quantity - current_reserved as available_quantity,
    max(timestamp) as last_updated
FROM inventory_events
GROUP BY sku
ORDER BY sku;

CREATE VIEW IF NOT EXISTS payment_volume_by_hour AS
SELECT 
    toStartOfHour(timestamp) as hour,
    currency,
    count() as transaction_count,
    sum(amount) as total_volume,
    avg(amount) as avg_amount,
    countIf(status = 'COMPLETED') as successful_count,
    countIf(status = 'FAILED') as failed_count
FROM payment_events
WHERE date >= today() - 7
GROUP BY hour, currency
ORDER BY hour DESC, currency;

-- Create functions for analytics
CREATE FUNCTION IF NOT EXISTS calculateSagaDuration AS (started_at, completed_at) -> 
    dateDiff('second', started_at, completed_at);

CREATE FUNCTION IF NOT EXISTS getBusinessHour AS (timestamp) -> 
    multiIf(
        toDayOfWeek(timestamp) IN (6, 7), 'weekend',
        toHour(timestamp) BETWEEN 9 AND 17, 'business_hours',
        'after_hours'
    );

-- Insert sample data for testing
INSERT INTO events VALUES
    (generateUUIDv4(), 'order_created', 'order-001', 'order', 'user-001', 'session-001', 'corr-001', '{"amount": 1299.99, "items": 1}', now(), today(), toHour(now())),
    (generateUUIDv4(), 'payment_processed', 'payment-001', 'payment', 'user-001', 'session-001', 'corr-001', '{"amount": 1299.99, "method": "credit_card"}', now(), today(), toHour(now())),
    (generateUUIDv4(), 'inventory_reserved', 'item-001', 'inventory', 'user-001', 'session-001', 'corr-001', '{"sku": "LAPTOP-001", "quantity": 1}', now(), today(), toHour(now()));

INSERT INTO saga_events VALUES
    (generateUUIDv4(), 'saga-001', 'order-processing', 'SAGA_STARTED', NULL, '{"order_id": "order-001"}', now(), today(), 'corr-001', NULL),
    (generateUUIDv4(), 'saga-001', 'order-processing', 'STEP_COMPLETED', 'reserve-inventory', '{"item_id": "item-001", "quantity": 1}', now(), today(), 'corr-001', 'step-001'),
    (generateUUIDv4(), 'saga-001', 'order-processing', 'STEP_COMPLETED', 'process-payment', '{"payment_id": "payment-001", "amount": 1299.99}', now(), today(), 'corr-001', 'step-002'),
    (generateUUIDv4(), 'saga-001', 'order-processing', 'SAGA_COMPLETED', NULL, '{"order_id": "order-001", "total_amount": 1299.99}', now(), today(), 'corr-001', NULL);

-- Create indexes for better query performance
ALTER TABLE events ADD INDEX idx_event_type event_type TYPE bloom_filter GRANULARITY 1;
ALTER TABLE events ADD INDEX idx_entity_type entity_type TYPE bloom_filter GRANULARITY 1;
ALTER TABLE events ADD INDEX idx_user_id user_id TYPE bloom_filter GRANULARITY 1;

ALTER TABLE saga_events ADD INDEX idx_saga_type saga_type TYPE bloom_filter GRANULARITY 1;
ALTER TABLE saga_events ADD INDEX idx_event_type event_type TYPE bloom_filter GRANULARITY 1;

-- Create dictionaries for dimension lookups
CREATE DICTIONARY IF NOT EXISTS event_type_dict (
    event_type String,
    category String,
    description String
) PRIMARY KEY event_type
SOURCE(CLICKHOUSE(HOST 'localhost' PORT 9000 USER 'default' TABLE 'event_types' DB 'analytics'))
LIFETIME(MIN 300 MAX 600)
LAYOUT(HASHED());

-- Optimize tables
OPTIMIZE TABLE events FINAL;
OPTIMIZE TABLE saga_events FINAL;
OPTIMIZE TABLE inventory_events FINAL;
OPTIMIZE TABLE payment_events FINAL;

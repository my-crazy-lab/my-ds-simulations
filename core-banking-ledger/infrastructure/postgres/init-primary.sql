-- Initialize PostgreSQL Primary Database for Core Banking Ledger
-- This script sets up replication and security for the primary database

-- Create replication user
CREATE USER replicator WITH REPLICATION ENCRYPTED PASSWORD 'repl_pass';

-- Create application user with limited privileges
CREATE USER banking_user WITH ENCRYPTED PASSWORD 'secure_banking_pass';

-- Create database
CREATE DATABASE core_banking OWNER banking_user;

-- Connect to the core_banking database
\c core_banking;

-- Grant necessary privileges to banking_user
GRANT ALL PRIVILEGES ON DATABASE core_banking TO banking_user;
GRANT ALL PRIVILEGES ON SCHEMA public TO banking_user;

-- Create replication slot for streaming replication
SELECT pg_create_physical_replication_slot('replica_slot');

-- Configure WAL level for replication (this should be in postgresql.conf)
-- wal_level = replica
-- max_wal_senders = 3
-- max_replication_slots = 3
-- hot_standby = on

-- Create monitoring user for health checks
CREATE USER monitor WITH ENCRYPTED PASSWORD 'monitor_pass';
GRANT CONNECT ON DATABASE core_banking TO monitor;
GRANT USAGE ON SCHEMA public TO monitor;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO monitor;

-- Log initialization
INSERT INTO pg_stat_statements_info (query) VALUES ('Primary database initialized');

-- Show replication status
SELECT * FROM pg_replication_slots;

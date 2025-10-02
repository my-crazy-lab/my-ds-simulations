#!/bin/bash
set -e

# Wait for primary to be ready
echo "Waiting for primary database to be ready..."
until pg_isready -h $POSTGRES_PRIMARY_HOST -p $POSTGRES_PRIMARY_PORT -U postgres; do
  echo "Primary database is not ready yet. Waiting..."
  sleep 2
done

echo "Primary database is ready. Setting up replica..."

# Stop PostgreSQL if running
pg_ctl -D "$PGDATA" -m fast -w stop || true

# Remove existing data directory
rm -rf "$PGDATA"/*

# Create base backup from primary
echo "Creating base backup from primary..."
PGPASSWORD=$POSTGRES_REPLICATION_PASSWORD pg_basebackup \
    -h $POSTGRES_PRIMARY_HOST \
    -p $POSTGRES_PRIMARY_PORT \
    -U $POSTGRES_REPLICATION_USER \
    -D "$PGDATA" \
    -Fp -Xs -P -R

# Set proper permissions
chmod 700 "$PGDATA"

# Create recovery configuration
cat > "$PGDATA/postgresql.conf" << EOF
# PostgreSQL Replica Configuration

# Connection Settings
listen_addresses = '*'
port = 5432
max_connections = 100

# Memory Settings
shared_buffers = 128MB
effective_cache_size = 512MB
work_mem = 2MB
maintenance_work_mem = 32MB

# Standby Settings
hot_standby = on
max_standby_streaming_delay = 30s
max_standby_archive_delay = 30s
hot_standby_feedback = on

# WAL Settings
wal_level = replica
max_wal_senders = 5
wal_keep_size = 512MB

# Logging
log_destination = 'stderr'
logging_collector = on
log_directory = 'log'
log_filename = 'postgresql-%Y-%m-%d_%H%M%S.log'
log_min_duration_statement = 1000
log_line_prefix = '%t [%p]: [%l-1] user=%u,db=%d,app=%a,client=%h '

# Statistics
track_activities = on
track_counts = on
track_io_timing = on

# Locale and Formatting
datestyle = 'iso, mdy'
timezone = 'UTC'
lc_messages = 'en_US.utf8'
lc_monetary = 'en_US.utf8'
lc_numeric = 'en_US.utf8'
lc_time = 'en_US.utf8'
default_text_search_config = 'pg_catalog.english'
EOF

# Create standby.signal file to indicate this is a standby server
touch "$PGDATA/standby.signal"

echo "Replica setup completed. Starting PostgreSQL..."

# Start PostgreSQL
exec postgres

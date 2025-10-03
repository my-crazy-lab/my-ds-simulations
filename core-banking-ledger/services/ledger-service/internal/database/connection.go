package database

import (
	"context"
	"database/sql"
	"fmt"
	"time"

	"github.com/jmoiron/sqlx"
	_ "github.com/lib/pq" // PostgreSQL driver
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/trace"
)

// DB wraps sqlx.DB with additional functionality
type DB struct {
	*sqlx.DB
	tracer trace.Tracer
}

// NewConnection creates a new database connection
func NewConnection(databaseURL string) (*DB, error) {
	db, err := sqlx.Connect("postgres", databaseURL)
	if err != nil {
		return nil, fmt.Errorf("failed to connect to database: %w", err)
	}

	// Configure connection pool
	db.SetMaxOpenConns(25)
	db.SetMaxIdleConns(5)
	db.SetConnMaxLifetime(5 * time.Minute)

	// Test the connection
	if err := db.Ping(); err != nil {
		return nil, fmt.Errorf("failed to ping database: %w", err)
	}

	return &DB{
		DB:     db,
		tracer: otel.Tracer("database"),
	}, nil
}

// Transaction represents a database transaction with tracing
type Transaction struct {
	*sqlx.Tx
	tracer trace.Tracer
}

// BeginTx starts a new transaction with context and tracing
func (db *DB) BeginTx(ctx context.Context) (*Transaction, error) {
	ctx, span := db.tracer.Start(ctx, "database.begin_transaction")
	defer span.End()

	tx, err := db.DB.BeginTxx(ctx, nil)
	if err != nil {
		span.RecordError(err)
		return nil, fmt.Errorf("failed to begin transaction: %w", err)
	}

	return &Transaction{
		Tx:     tx,
		tracer: db.tracer,
	}, nil
}

// Commit commits the transaction with tracing
func (tx *Transaction) Commit(ctx context.Context) error {
	ctx, span := tx.tracer.Start(ctx, "database.commit_transaction")
	defer span.End()

	if err := tx.Tx.Commit(); err != nil {
		span.RecordError(err)
		return fmt.Errorf("failed to commit transaction: %w", err)
	}

	return nil
}

// Rollback rolls back the transaction with tracing
func (tx *Transaction) Rollback(ctx context.Context) error {
	ctx, span := tx.tracer.Start(ctx, "database.rollback_transaction")
	defer span.End()

	if err := tx.Tx.Rollback(); err != nil {
		span.RecordError(err)
		return fmt.Errorf("failed to rollback transaction: %w", err)
	}

	return nil
}

// QueryRowContext executes a query with tracing
func (db *DB) QueryRowContext(ctx context.Context, query string, args ...interface{}) *sql.Row {
	ctx, span := db.tracer.Start(ctx, "database.query_row")
	defer span.End()

	span.SetAttributes(
		attribute.String("db.statement", query),
		attribute.Int("db.args_count", len(args)),
	)

	return db.DB.QueryRowContext(ctx, query, args...)
}

// QueryContext executes a query with tracing
func (db *DB) QueryContext(ctx context.Context, query string, args ...interface{}) (*sql.Rows, error) {
	ctx, span := db.tracer.Start(ctx, "database.query")
	defer span.End()

	span.SetAttributes(
		attribute.String("db.statement", query),
		attribute.Int("db.args_count", len(args)),
	)

	rows, err := db.DB.QueryContext(ctx, query, args...)
	if err != nil {
		span.RecordError(err)
		return nil, err
	}

	return rows, nil
}

// ExecContext executes a statement with tracing
func (db *DB) ExecContext(ctx context.Context, query string, args ...interface{}) (sql.Result, error) {
	ctx, span := db.tracer.Start(ctx, "database.exec")
	defer span.End()

	span.SetAttributes(
		attribute.String("db.statement", query),
		attribute.Int("db.args_count", len(args)),
	)

	result, err := db.DB.ExecContext(ctx, query, args...)
	if err != nil {
		span.RecordError(err)
		return nil, err
	}

	return result, nil
}

// SelectContext executes a select query with tracing
func (db *DB) SelectContext(ctx context.Context, dest interface{}, query string, args ...interface{}) error {
	ctx, span := db.tracer.Start(ctx, "database.select")
	defer span.End()

	span.SetAttributes(
		attribute.String("db.statement", query),
		attribute.Int("db.args_count", len(args)),
	)

	err := db.DB.SelectContext(ctx, dest, query, args...)
	if err != nil {
		span.RecordError(err)
		return err
	}

	return nil
}

// GetContext executes a get query with tracing
func (db *DB) GetContext(ctx context.Context, dest interface{}, query string, args ...interface{}) error {
	ctx, span := db.tracer.Start(ctx, "database.get")
	defer span.End()

	span.SetAttributes(
		attribute.String("db.statement", query),
		attribute.Int("db.args_count", len(args)),
	)

	err := db.DB.GetContext(ctx, dest, query, args...)
	if err != nil {
		span.RecordError(err)
		return err
	}

	return nil
}

// NamedExecContext executes a named statement with tracing
func (db *DB) NamedExecContext(ctx context.Context, query string, arg interface{}) (sql.Result, error) {
	ctx, span := db.tracer.Start(ctx, "database.named_exec")
	defer span.End()

	span.SetAttributes(
		attribute.String("db.statement", query),
	)

	result, err := db.DB.NamedExecContext(ctx, query, arg)
	if err != nil {
		span.RecordError(err)
		return nil, err
	}

	return result, nil
}

// HealthCheck performs a health check on the database
func (db *DB) HealthCheck(ctx context.Context) error {
	ctx, span := db.tracer.Start(ctx, "database.health_check")
	defer span.End()

	var result int
	err := db.DB.QueryRowContext(ctx, "SELECT 1").Scan(&result)
	if err != nil {
		span.RecordError(err)
		return fmt.Errorf("database health check failed: %w", err)
	}

	if result != 1 {
		err := fmt.Errorf("unexpected health check result: %d", result)
		span.RecordError(err)
		return err
	}

	return nil
}

// GetStats returns database connection statistics
func (db *DB) GetStats() sql.DBStats {
	return db.DB.Stats()
}

// Close closes the database connection
func (db *DB) Close() error {
	return db.DB.Close()
}

// WithTransaction executes a function within a database transaction
func (db *DB) WithTransaction(ctx context.Context, fn func(*Transaction) error) error {
	ctx, span := db.tracer.Start(ctx, "database.with_transaction")
	defer span.End()

	tx, err := db.BeginTx(ctx)
	if err != nil {
		span.RecordError(err)
		return err
	}

	defer func() {
		if p := recover(); p != nil {
			tx.Rollback(ctx)
			panic(p)
		} else if err != nil {
			tx.Rollback(ctx)
		} else {
			err = tx.Commit(ctx)
		}
	}()

	err = fn(tx)
	return err
}

// Repository provides common database operations
type Repository struct {
	db      *DB
	replica *DB
	tracer  trace.Tracer
}

// NewRepository creates a new repository instance
func NewRepository(db, replica *DB) *Repository {
	return &Repository{
		db:      db,
		replica: replica,
		tracer:  otel.Tracer("repository"),
	}
}

// GetDB returns the primary database connection
func (r *Repository) GetDB() *DB {
	return r.db
}

// GetReplica returns the replica database connection
func (r *Repository) GetReplica() *DB {
	return r.replica
}

// ExecuteInTransaction executes a function within a transaction
func (r *Repository) ExecuteInTransaction(ctx context.Context, fn func(*Transaction) error) error {
	return r.db.WithTransaction(ctx, fn)
}

// QueryWithFallback tries the primary database first, then falls back to replica
func (r *Repository) QueryWithFallback(ctx context.Context, dest interface{}, query string, args ...interface{}) error {
	ctx, span := r.tracer.Start(ctx, "repository.query_with_fallback")
	defer span.End()

	// Try primary database first
	err := r.db.SelectContext(ctx, dest, query, args...)
	if err == nil {
		span.SetAttributes(attribute.String("db.source", "primary"))
		return nil
	}

	// Fall back to replica
	span.SetAttributes(attribute.String("db.source", "replica"))
	return r.replica.SelectContext(ctx, dest, query, args...)
}

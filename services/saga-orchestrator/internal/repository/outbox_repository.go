package repository

import (
	"context"
	"database/sql"
	"fmt"
	"time"

	"github.com/google/uuid"
	"github.com/microservices-saga/services/saga-orchestrator/internal/models"
)

// PostgresOutboxRepository implements OutboxRepository using PostgreSQL
type PostgresOutboxRepository struct {
	db *sql.DB
}

// NewOutboxRepository creates a new PostgreSQL outbox repository
func NewOutboxRepository(db *sql.DB) OutboxRepository {
	return &PostgresOutboxRepository{db: db}
}

// CreateEvent creates a new outbox event
func (r *PostgresOutboxRepository) CreateEvent(ctx context.Context, event *models.OutboxEvent) error {
	query := `
		INSERT INTO outbox_events (
			id, aggregate_id, aggregate_type, event_type, event_data, created_at,
			status, retry_count, correlation_id, causation_id, version
		) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)`

	_, err := r.db.ExecContext(ctx, query,
		event.ID, event.AggregateID, event.AggregateType, event.EventType,
		event.EventData, event.CreatedAt, event.Status, event.RetryCount,
		event.CorrelationID, event.CausationID, event.Version)

	if err != nil {
		return fmt.Errorf("failed to create outbox event: %w", err)
	}

	return nil
}

// GetEvent retrieves an outbox event by ID
func (r *PostgresOutboxRepository) GetEvent(ctx context.Context, id uuid.UUID) (*models.OutboxEvent, error) {
	query := `
		SELECT id, aggregate_id, aggregate_type, event_type, event_data, created_at,
			   processed_at, status, retry_count, correlation_id, causation_id, version
		FROM outbox_events WHERE id = $1`

	event := &models.OutboxEvent{}
	err := r.db.QueryRowContext(ctx, query, id).Scan(
		&event.ID, &event.AggregateID, &event.AggregateType, &event.EventType,
		&event.EventData, &event.CreatedAt, &event.ProcessedAt, &event.Status,
		&event.RetryCount, &event.CorrelationID, &event.CausationID, &event.Version)

	if err != nil {
		if err == sql.ErrNoRows {
			return nil, fmt.Errorf("outbox event not found: %s", id)
		}
		return nil, fmt.Errorf("failed to get outbox event: %w", err)
	}

	return event, nil
}

// UpdateEvent updates an outbox event
func (r *PostgresOutboxRepository) UpdateEvent(ctx context.Context, event *models.OutboxEvent) error {
	query := `
		UPDATE outbox_events SET
			processed_at = $2, status = $3, retry_count = $4
		WHERE id = $1`

	result, err := r.db.ExecContext(ctx, query,
		event.ID, event.ProcessedAt, event.Status, event.RetryCount)

	if err != nil {
		return fmt.Errorf("failed to update outbox event: %w", err)
	}

	rowsAffected, err := result.RowsAffected()
	if err != nil {
		return fmt.Errorf("failed to get rows affected: %w", err)
	}

	if rowsAffected == 0 {
		return fmt.Errorf("outbox event not found: %s", event.ID)
	}

	return nil
}

// DeleteEvent deletes an outbox event
func (r *PostgresOutboxRepository) DeleteEvent(ctx context.Context, id uuid.UUID) error {
	query := `DELETE FROM outbox_events WHERE id = $1`

	result, err := r.db.ExecContext(ctx, query, id)
	if err != nil {
		return fmt.Errorf("failed to delete outbox event: %w", err)
	}

	rowsAffected, err := result.RowsAffected()
	if err != nil {
		return fmt.Errorf("failed to get rows affected: %w", err)
	}

	if rowsAffected == 0 {
		return fmt.Errorf("outbox event not found: %s", id)
	}

	return nil
}

// GetPendingEvents retrieves pending outbox events
func (r *PostgresOutboxRepository) GetPendingEvents(ctx context.Context, limit int) ([]*models.OutboxEvent, error) {
	query := `
		SELECT id, aggregate_id, aggregate_type, event_type, event_data, created_at,
			   processed_at, status, retry_count, correlation_id, causation_id, version
		FROM outbox_events 
		WHERE status = 'PENDING'
		ORDER BY created_at ASC
		LIMIT $1`

	rows, err := r.db.QueryContext(ctx, query, limit)
	if err != nil {
		return nil, fmt.Errorf("failed to get pending outbox events: %w", err)
	}
	defer rows.Close()

	var events []*models.OutboxEvent
	for rows.Next() {
		event := &models.OutboxEvent{}
		err := rows.Scan(
			&event.ID, &event.AggregateID, &event.AggregateType, &event.EventType,
			&event.EventData, &event.CreatedAt, &event.ProcessedAt, &event.Status,
			&event.RetryCount, &event.CorrelationID, &event.CausationID, &event.Version)
		if err != nil {
			return nil, fmt.Errorf("failed to scan outbox event: %w", err)
		}
		events = append(events, event)
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("error iterating outbox event rows: %w", err)
	}

	return events, nil
}

// GetEventsByStatus retrieves outbox events by status with pagination
func (r *PostgresOutboxRepository) GetEventsByStatus(ctx context.Context, status string, limit, offset int) ([]*models.OutboxEvent, error) {
	query := `
		SELECT id, aggregate_id, aggregate_type, event_type, event_data, created_at,
			   processed_at, status, retry_count, correlation_id, causation_id, version
		FROM outbox_events 
		WHERE status = $1
		ORDER BY created_at DESC
		LIMIT $2 OFFSET $3`

	rows, err := r.db.QueryContext(ctx, query, status, limit, offset)
	if err != nil {
		return nil, fmt.Errorf("failed to get outbox events by status: %w", err)
	}
	defer rows.Close()

	var events []*models.OutboxEvent
	for rows.Next() {
		event := &models.OutboxEvent{}
		err := rows.Scan(
			&event.ID, &event.AggregateID, &event.AggregateType, &event.EventType,
			&event.EventData, &event.CreatedAt, &event.ProcessedAt, &event.Status,
			&event.RetryCount, &event.CorrelationID, &event.CausationID, &event.Version)
		if err != nil {
			return nil, fmt.Errorf("failed to scan outbox event: %w", err)
		}
		events = append(events, event)
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("error iterating outbox event rows: %w", err)
	}

	return events, nil
}

// GetEventsByAggregateID retrieves outbox events by aggregate ID
func (r *PostgresOutboxRepository) GetEventsByAggregateID(ctx context.Context, aggregateID string) ([]*models.OutboxEvent, error) {
	query := `
		SELECT id, aggregate_id, aggregate_type, event_type, event_data, created_at,
			   processed_at, status, retry_count, correlation_id, causation_id, version
		FROM outbox_events 
		WHERE aggregate_id = $1
		ORDER BY created_at ASC`

	rows, err := r.db.QueryContext(ctx, query, aggregateID)
	if err != nil {
		return nil, fmt.Errorf("failed to get outbox events by aggregate ID: %w", err)
	}
	defer rows.Close()

	var events []*models.OutboxEvent
	for rows.Next() {
		event := &models.OutboxEvent{}
		err := rows.Scan(
			&event.ID, &event.AggregateID, &event.AggregateType, &event.EventType,
			&event.EventData, &event.CreatedAt, &event.ProcessedAt, &event.Status,
			&event.RetryCount, &event.CorrelationID, &event.CausationID, &event.Version)
		if err != nil {
			return nil, fmt.Errorf("failed to scan outbox event: %w", err)
		}
		events = append(events, event)
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("error iterating outbox event rows: %w", err)
	}

	return events, nil
}

// CountEventsByStatus counts outbox events by status
func (r *PostgresOutboxRepository) CountEventsByStatus(ctx context.Context, status string) (int64, error) {
	var count int64
	err := r.db.QueryRowContext(ctx, "SELECT COUNT(*) FROM outbox_events WHERE status = $1", status).Scan(&count)
	if err != nil {
		return 0, fmt.Errorf("failed to count outbox events by status: %w", err)
	}
	return count, nil
}

// CountEventsByType counts outbox events by type
func (r *PostgresOutboxRepository) CountEventsByType(ctx context.Context, eventType string) (int64, error) {
	var count int64
	err := r.db.QueryRowContext(ctx, "SELECT COUNT(*) FROM outbox_events WHERE event_type = $1", eventType).Scan(&count)
	if err != nil {
		return 0, fmt.Errorf("failed to count outbox events by type: %w", err)
	}
	return count, nil
}

// GetOldestPendingEvent retrieves the oldest pending outbox event
func (r *PostgresOutboxRepository) GetOldestPendingEvent(ctx context.Context) (*models.OutboxEvent, error) {
	query := `
		SELECT id, aggregate_id, aggregate_type, event_type, event_data, created_at,
			   processed_at, status, retry_count, correlation_id, causation_id, version
		FROM outbox_events 
		WHERE status = 'PENDING'
		ORDER BY created_at ASC
		LIMIT 1`

	event := &models.OutboxEvent{}
	err := r.db.QueryRowContext(ctx, query).Scan(
		&event.ID, &event.AggregateID, &event.AggregateType, &event.EventType,
		&event.EventData, &event.CreatedAt, &event.ProcessedAt, &event.Status,
		&event.RetryCount, &event.CorrelationID, &event.CausationID, &event.Version)

	if err != nil {
		if err == sql.ErrNoRows {
			return nil, nil // No pending events
		}
		return nil, fmt.Errorf("failed to get oldest pending outbox event: %w", err)
	}

	return event, nil
}

// DeleteProcessedEventsBefore deletes processed events before a certain time
func (r *PostgresOutboxRepository) DeleteProcessedEventsBefore(ctx context.Context, before time.Time) (int64, error) {
	result, err := r.db.ExecContext(ctx,
		"DELETE FROM outbox_events WHERE status = 'PROCESSED' AND processed_at < $1",
		before)
	if err != nil {
		return 0, fmt.Errorf("failed to delete processed outbox events: %w", err)
	}
	
	rowsAffected, err := result.RowsAffected()
	if err != nil {
		return 0, fmt.Errorf("failed to get rows affected: %w", err)
	}
	
	return rowsAffected, nil
}

// DeleteFailedEventsBefore deletes failed events before a certain time
func (r *PostgresOutboxRepository) DeleteFailedEventsBefore(ctx context.Context, before time.Time) (int64, error) {
	result, err := r.db.ExecContext(ctx,
		"DELETE FROM outbox_events WHERE status = 'FAILED' AND created_at < $1",
		before)
	if err != nil {
		return 0, fmt.Errorf("failed to delete failed outbox events: %w", err)
	}
	
	rowsAffected, err := result.RowsAffected()
	if err != nil {
		return 0, fmt.Errorf("failed to get rows affected: %w", err)
	}
	
	return rowsAffected, nil
}

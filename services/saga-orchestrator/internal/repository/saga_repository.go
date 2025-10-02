package repository

import (
	"context"
	"database/sql"
	"fmt"
	"time"

	"github.com/google/uuid"
	"github.com/lib/pq"
	"github.com/microservices-saga/services/saga-orchestrator/internal/models"
)

// PostgresSagaRepository implements SagaRepository using PostgreSQL
type PostgresSagaRepository struct {
	db *sql.DB
}

// NewSagaRepository creates a new PostgreSQL saga repository
func NewSagaRepository(db *sql.DB) SagaRepository {
	return &PostgresSagaRepository{db: db}
}

// Create creates a new saga instance
func (r *PostgresSagaRepository) Create(ctx context.Context, saga *models.SagaInstance) error {
	query := `
		INSERT INTO saga_instances (
			id, saga_type, saga_data, status, current_step, created_at, updated_at,
			retry_count, max_retries, correlation_id, idempotency_key
		) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)`

	_, err := r.db.ExecContext(ctx, query,
		saga.ID, saga.SagaType, saga.SagaData, saga.Status, saga.CurrentStep,
		saga.CreatedAt, saga.UpdatedAt, saga.RetryCount, saga.MaxRetries,
		saga.CorrelationID, saga.IdempotencyKey)

	if err != nil {
		if pqErr, ok := err.(*pq.Error); ok && pqErr.Code == "23505" {
			return fmt.Errorf("saga with idempotency key already exists: %w", err)
		}
		return fmt.Errorf("failed to create saga: %w", err)
	}

	return nil
}

// GetByID retrieves a saga by ID
func (r *PostgresSagaRepository) GetByID(ctx context.Context, id uuid.UUID) (*models.SagaInstance, error) {
	query := `
		SELECT id, saga_type, saga_data, status, current_step, created_at, updated_at,
			   completed_at, error_message, retry_count, max_retries, correlation_id, idempotency_key
		FROM saga_instances WHERE id = $1`

	saga := &models.SagaInstance{}
	err := r.db.QueryRowContext(ctx, query, id).Scan(
		&saga.ID, &saga.SagaType, &saga.SagaData, &saga.Status, &saga.CurrentStep,
		&saga.CreatedAt, &saga.UpdatedAt, &saga.CompletedAt, &saga.ErrorMessage,
		&saga.RetryCount, &saga.MaxRetries, &saga.CorrelationID, &saga.IdempotencyKey)

	if err != nil {
		if err == sql.ErrNoRows {
			return nil, fmt.Errorf("saga not found: %s", id)
		}
		return nil, fmt.Errorf("failed to get saga: %w", err)
	}

	return saga, nil
}

// GetByIdempotencyKey retrieves a saga by idempotency key
func (r *PostgresSagaRepository) GetByIdempotencyKey(ctx context.Context, key string) (*models.SagaInstance, error) {
	query := `
		SELECT id, saga_type, saga_data, status, current_step, created_at, updated_at,
			   completed_at, error_message, retry_count, max_retries, correlation_id, idempotency_key
		FROM saga_instances WHERE idempotency_key = $1`

	saga := &models.SagaInstance{}
	err := r.db.QueryRowContext(ctx, query, key).Scan(
		&saga.ID, &saga.SagaType, &saga.SagaData, &saga.Status, &saga.CurrentStep,
		&saga.CreatedAt, &saga.UpdatedAt, &saga.CompletedAt, &saga.ErrorMessage,
		&saga.RetryCount, &saga.MaxRetries, &saga.CorrelationID, &saga.IdempotencyKey)

	if err != nil {
		if err == sql.ErrNoRows {
			return nil, fmt.Errorf("saga not found with idempotency key: %s", key)
		}
		return nil, fmt.Errorf("failed to get saga by idempotency key: %w", err)
	}

	return saga, nil
}

// Update updates a saga instance
func (r *PostgresSagaRepository) Update(ctx context.Context, saga *models.SagaInstance) error {
	query := `
		UPDATE saga_instances SET
			saga_data = $2, status = $3, current_step = $4, updated_at = $5,
			completed_at = $6, error_message = $7, retry_count = $8
		WHERE id = $1`

	result, err := r.db.ExecContext(ctx, query,
		saga.ID, saga.SagaData, saga.Status, saga.CurrentStep, saga.UpdatedAt,
		saga.CompletedAt, saga.ErrorMessage, saga.RetryCount)

	if err != nil {
		return fmt.Errorf("failed to update saga: %w", err)
	}

	rowsAffected, err := result.RowsAffected()
	if err != nil {
		return fmt.Errorf("failed to get rows affected: %w", err)
	}

	if rowsAffected == 0 {
		return fmt.Errorf("saga not found: %s", saga.ID)
	}

	return nil
}

// Delete deletes a saga instance
func (r *PostgresSagaRepository) Delete(ctx context.Context, id uuid.UUID) error {
	query := `DELETE FROM saga_instances WHERE id = $1`

	result, err := r.db.ExecContext(ctx, query, id)
	if err != nil {
		return fmt.Errorf("failed to delete saga: %w", err)
	}

	rowsAffected, err := result.RowsAffected()
	if err != nil {
		return fmt.Errorf("failed to get rows affected: %w", err)
	}

	if rowsAffected == 0 {
		return fmt.Errorf("saga not found: %s", id)
	}

	return nil
}

// List retrieves sagas with pagination and optional status filter
func (r *PostgresSagaRepository) List(ctx context.Context, limit, offset int, status *models.SagaStatus) ([]*models.SagaInstance, int, error) {
	var args []interface{}
	var whereClause string
	argIndex := 1

	if status != nil {
		whereClause = "WHERE status = $" + fmt.Sprintf("%d", argIndex)
		args = append(args, *status)
		argIndex++
	}

	// Count query
	countQuery := fmt.Sprintf("SELECT COUNT(*) FROM saga_instances %s", whereClause)
	var total int
	err := r.db.QueryRowContext(ctx, countQuery, args...).Scan(&total)
	if err != nil {
		return nil, 0, fmt.Errorf("failed to count sagas: %w", err)
	}

	// Data query
	query := fmt.Sprintf(`
		SELECT id, saga_type, saga_data, status, current_step, created_at, updated_at,
			   completed_at, error_message, retry_count, max_retries, correlation_id, idempotency_key
		FROM saga_instances %s
		ORDER BY created_at DESC
		LIMIT $%d OFFSET $%d`, whereClause, argIndex, argIndex+1)

	args = append(args, limit, offset)

	rows, err := r.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, 0, fmt.Errorf("failed to list sagas: %w", err)
	}
	defer rows.Close()

	var sagas []*models.SagaInstance
	for rows.Next() {
		saga := &models.SagaInstance{}
		err := rows.Scan(
			&saga.ID, &saga.SagaType, &saga.SagaData, &saga.Status, &saga.CurrentStep,
			&saga.CreatedAt, &saga.UpdatedAt, &saga.CompletedAt, &saga.ErrorMessage,
			&saga.RetryCount, &saga.MaxRetries, &saga.CorrelationID, &saga.IdempotencyKey)
		if err != nil {
			return nil, 0, fmt.Errorf("failed to scan saga: %w", err)
		}
		sagas = append(sagas, saga)
	}

	if err := rows.Err(); err != nil {
		return nil, 0, fmt.Errorf("error iterating saga rows: %w", err)
	}

	return sagas, total, nil
}

// ListByCorrelationID retrieves sagas by correlation ID
func (r *PostgresSagaRepository) ListByCorrelationID(ctx context.Context, correlationID string) ([]*models.SagaInstance, error) {
	query := `
		SELECT id, saga_type, saga_data, status, current_step, created_at, updated_at,
			   completed_at, error_message, retry_count, max_retries, correlation_id, idempotency_key
		FROM saga_instances 
		WHERE correlation_id = $1
		ORDER BY created_at DESC`

	rows, err := r.db.QueryContext(ctx, query, correlationID)
	if err != nil {
		return nil, fmt.Errorf("failed to list sagas by correlation ID: %w", err)
	}
	defer rows.Close()

	var sagas []*models.SagaInstance
	for rows.Next() {
		saga := &models.SagaInstance{}
		err := rows.Scan(
			&saga.ID, &saga.SagaType, &saga.SagaData, &saga.Status, &saga.CurrentStep,
			&saga.CreatedAt, &saga.UpdatedAt, &saga.CompletedAt, &saga.ErrorMessage,
			&saga.RetryCount, &saga.MaxRetries, &saga.CorrelationID, &saga.IdempotencyKey)
		if err != nil {
			return nil, fmt.Errorf("failed to scan saga: %w", err)
		}
		sagas = append(sagas, saga)
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("error iterating saga rows: %w", err)
	}

	return sagas, nil
}

// CreateStep creates a new saga step
func (r *PostgresSagaRepository) CreateStep(ctx context.Context, step *models.SagaStep) error {
	query := `
		INSERT INTO saga_steps (
			id, saga_id, step_name, step_order, status, input_data, retry_count
		) VALUES ($1, $2, $3, $4, $5, $6, $7)`

	_, err := r.db.ExecContext(ctx, query,
		step.ID, step.SagaID, step.StepName, step.StepOrder, step.Status,
		step.InputData, step.RetryCount)

	if err != nil {
		return fmt.Errorf("failed to create saga step: %w", err)
	}

	return nil
}

// GetStep retrieves a saga step by ID
func (r *PostgresSagaRepository) GetStep(ctx context.Context, id uuid.UUID) (*models.SagaStep, error) {
	query := `
		SELECT id, saga_id, step_name, step_order, status, input_data, output_data,
			   error_message, started_at, completed_at, retry_count, compensation_data
		FROM saga_steps WHERE id = $1`

	step := &models.SagaStep{}
	err := r.db.QueryRowContext(ctx, query, id).Scan(
		&step.ID, &step.SagaID, &step.StepName, &step.StepOrder, &step.Status,
		&step.InputData, &step.OutputData, &step.ErrorMessage, &step.StartedAt,
		&step.CompletedAt, &step.RetryCount, &step.CompensationData)

	if err != nil {
		if err == sql.ErrNoRows {
			return nil, fmt.Errorf("saga step not found: %s", id)
		}
		return nil, fmt.Errorf("failed to get saga step: %w", err)
	}

	return step, nil
}

// GetSteps retrieves all steps for a saga
func (r *PostgresSagaRepository) GetSteps(ctx context.Context, sagaID uuid.UUID) ([]*models.SagaStep, error) {
	query := `
		SELECT id, saga_id, step_name, step_order, status, input_data, output_data,
			   error_message, started_at, completed_at, retry_count, compensation_data
		FROM saga_steps 
		WHERE saga_id = $1
		ORDER BY step_order`

	rows, err := r.db.QueryContext(ctx, query, sagaID)
	if err != nil {
		return nil, fmt.Errorf("failed to get saga steps: %w", err)
	}
	defer rows.Close()

	var steps []*models.SagaStep
	for rows.Next() {
		step := &models.SagaStep{}
		err := rows.Scan(
			&step.ID, &step.SagaID, &step.StepName, &step.StepOrder, &step.Status,
			&step.InputData, &step.OutputData, &step.ErrorMessage, &step.StartedAt,
			&step.CompletedAt, &step.RetryCount, &step.CompensationData)
		if err != nil {
			return nil, fmt.Errorf("failed to scan saga step: %w", err)
		}
		steps = append(steps, step)
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("error iterating saga step rows: %w", err)
	}

	return steps, nil
}

// UpdateStep updates a saga step
func (r *PostgresSagaRepository) UpdateStep(ctx context.Context, step *models.SagaStep) error {
	query := `
		UPDATE saga_steps SET
			status = $2, input_data = $3, output_data = $4, error_message = $5,
			started_at = $6, completed_at = $7, retry_count = $8, compensation_data = $9
		WHERE id = $1`

	result, err := r.db.ExecContext(ctx, query,
		step.ID, step.Status, step.InputData, step.OutputData, step.ErrorMessage,
		step.StartedAt, step.CompletedAt, step.RetryCount, step.CompensationData)

	if err != nil {
		return fmt.Errorf("failed to update saga step: %w", err)
	}

	rowsAffected, err := result.RowsAffected()
	if err != nil {
		return fmt.Errorf("failed to get rows affected: %w", err)
	}

	if rowsAffected == 0 {
		return fmt.Errorf("saga step not found: %s", step.ID)
	}

	return nil
}

// DeleteStep deletes a saga step
func (r *PostgresSagaRepository) DeleteStep(ctx context.Context, id uuid.UUID) error {
	query := `DELETE FROM saga_steps WHERE id = $1`

	result, err := r.db.ExecContext(ctx, query, id)
	if err != nil {
		return fmt.Errorf("failed to delete saga step: %w", err)
	}

	rowsAffected, err := result.RowsAffected()
	if err != nil {
		return fmt.Errorf("failed to get rows affected: %w", err)
	}

	if rowsAffected == 0 {
		return fmt.Errorf("saga step not found: %s", id)
	}

	return nil
}

// GetSagaMetrics retrieves saga metrics for a time period
func (r *PostgresSagaRepository) GetSagaMetrics(ctx context.Context, from, to time.Time) (*models.SagaMetrics, error) {
	metrics := &models.SagaMetrics{
		SagasByType:   make(map[string]int64),
		SagasByStatus: make(map[string]int64),
	}

	// Total sagas
	err := r.db.QueryRowContext(ctx,
		"SELECT COUNT(*) FROM saga_instances WHERE created_at BETWEEN $1 AND $2",
		from, to).Scan(&metrics.TotalSagas)
	if err != nil {
		return nil, fmt.Errorf("failed to get total sagas: %w", err)
	}

	// Completed sagas
	err = r.db.QueryRowContext(ctx,
		"SELECT COUNT(*) FROM saga_instances WHERE status = 'COMPLETED' AND created_at BETWEEN $1 AND $2",
		from, to).Scan(&metrics.CompletedSagas)
	if err != nil {
		return nil, fmt.Errorf("failed to get completed sagas: %w", err)
	}

	// Failed sagas
	err = r.db.QueryRowContext(ctx,
		"SELECT COUNT(*) FROM saga_instances WHERE status = 'FAILED' AND created_at BETWEEN $1 AND $2",
		from, to).Scan(&metrics.FailedSagas)
	if err != nil {
		return nil, fmt.Errorf("failed to get failed sagas: %w", err)
	}

	// Compensated sagas
	err = r.db.QueryRowContext(ctx,
		"SELECT COUNT(*) FROM saga_instances WHERE status = 'COMPENSATED' AND created_at BETWEEN $1 AND $2",
		from, to).Scan(&metrics.CompensatedSagas)
	if err != nil {
		return nil, fmt.Errorf("failed to get compensated sagas: %w", err)
	}

	// Average duration
	var avgSeconds sql.NullFloat64
	err = r.db.QueryRowContext(ctx,
		`SELECT AVG(EXTRACT(EPOCH FROM (completed_at - created_at)))
		 FROM saga_instances
		 WHERE completed_at IS NOT NULL AND created_at BETWEEN $1 AND $2`,
		from, to).Scan(&avgSeconds)
	if err != nil {
		return nil, fmt.Errorf("failed to get average duration: %w", err)
	}
	if avgSeconds.Valid {
		metrics.AverageDuration = time.Duration(avgSeconds.Float64) * time.Second
	}

	return metrics, nil
}

// CountSagasByStatus counts sagas by status
func (r *PostgresSagaRepository) CountSagasByStatus(ctx context.Context, status models.SagaStatus) (int64, error) {
	var count int64
	err := r.db.QueryRowContext(ctx, "SELECT COUNT(*) FROM saga_instances WHERE status = $1", status).Scan(&count)
	if err != nil {
		return 0, fmt.Errorf("failed to count sagas by status: %w", err)
	}
	return count, nil
}

// CountSagasByType counts sagas by type
func (r *PostgresSagaRepository) CountSagasByType(ctx context.Context, sagaType string) (int64, error) {
	var count int64
	err := r.db.QueryRowContext(ctx, "SELECT COUNT(*) FROM saga_instances WHERE saga_type = $1", sagaType).Scan(&count)
	if err != nil {
		return 0, fmt.Errorf("failed to count sagas by type: %w", err)
	}
	return count, nil
}

// GetAverageSagaDuration gets average saga duration for a type and time period
func (r *PostgresSagaRepository) GetAverageSagaDuration(ctx context.Context, sagaType string, from, to time.Time) (time.Duration, error) {
	var avgSeconds sql.NullFloat64
	err := r.db.QueryRowContext(ctx,
		`SELECT AVG(EXTRACT(EPOCH FROM (completed_at - created_at)))
		 FROM saga_instances
		 WHERE saga_type = $1 AND completed_at IS NOT NULL AND created_at BETWEEN $2 AND $3`,
		sagaType, from, to).Scan(&avgSeconds)
	if err != nil {
		return 0, fmt.Errorf("failed to get average saga duration: %w", err)
	}
	if avgSeconds.Valid {
		return time.Duration(avgSeconds.Float64) * time.Second, nil
	}
	return 0, nil
}

// DeleteCompletedSagasBefore deletes completed sagas before a certain time
func (r *PostgresSagaRepository) DeleteCompletedSagasBefore(ctx context.Context, before time.Time) (int64, error) {
	result, err := r.db.ExecContext(ctx,
		"DELETE FROM saga_instances WHERE status = 'COMPLETED' AND completed_at < $1",
		before)
	if err != nil {
		return 0, fmt.Errorf("failed to delete completed sagas: %w", err)
	}

	rowsAffected, err := result.RowsAffected()
	if err != nil {
		return 0, fmt.Errorf("failed to get rows affected: %w", err)
	}

	return rowsAffected, nil
}

// DeleteFailedSagasBefore deletes failed sagas before a certain time
func (r *PostgresSagaRepository) DeleteFailedSagasBefore(ctx context.Context, before time.Time) (int64, error) {
	result, err := r.db.ExecContext(ctx,
		"DELETE FROM saga_instances WHERE status = 'FAILED' AND updated_at < $1",
		before)
	if err != nil {
		return 0, fmt.Errorf("failed to delete failed sagas: %w", err)
	}

	rowsAffected, err := result.RowsAffected()
	if err != nil {
		return 0, fmt.Errorf("failed to get rows affected: %w", err)
	}

	return rowsAffected, nil
}

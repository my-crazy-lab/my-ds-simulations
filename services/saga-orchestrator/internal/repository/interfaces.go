package repository

import (
	"context"
	"time"

	"github.com/google/uuid"
	"github.com/microservices-saga/services/saga-orchestrator/internal/models"
)

// SagaRepository defines the interface for saga persistence
type SagaRepository interface {
	// Saga operations
	Create(ctx context.Context, saga *models.SagaInstance) error
	GetByID(ctx context.Context, id uuid.UUID) (*models.SagaInstance, error)
	GetByIdempotencyKey(ctx context.Context, key string) (*models.SagaInstance, error)
	Update(ctx context.Context, saga *models.SagaInstance) error
	Delete(ctx context.Context, id uuid.UUID) error
	List(ctx context.Context, limit, offset int, status *models.SagaStatus) ([]*models.SagaInstance, int, error)
	ListByCorrelationID(ctx context.Context, correlationID string) ([]*models.SagaInstance, error)
	
	// Step operations
	CreateStep(ctx context.Context, step *models.SagaStep) error
	GetStep(ctx context.Context, id uuid.UUID) (*models.SagaStep, error)
	GetSteps(ctx context.Context, sagaID uuid.UUID) ([]*models.SagaStep, error)
	UpdateStep(ctx context.Context, step *models.SagaStep) error
	DeleteStep(ctx context.Context, id uuid.UUID) error
	
	// Metrics and monitoring
	GetSagaMetrics(ctx context.Context, from, to time.Time) (*models.SagaMetrics, error)
	CountSagasByStatus(ctx context.Context, status models.SagaStatus) (int64, error)
	CountSagasByType(ctx context.Context, sagaType string) (int64, error)
	GetAverageSagaDuration(ctx context.Context, sagaType string, from, to time.Time) (time.Duration, error)
	
	// Cleanup operations
	DeleteCompletedSagasBefore(ctx context.Context, before time.Time) (int64, error)
	DeleteFailedSagasBefore(ctx context.Context, before time.Time) (int64, error)
}

// OutboxRepository defines the interface for outbox event persistence
type OutboxRepository interface {
	// Event operations
	CreateEvent(ctx context.Context, event *models.OutboxEvent) error
	GetEvent(ctx context.Context, id uuid.UUID) (*models.OutboxEvent, error)
	UpdateEvent(ctx context.Context, event *models.OutboxEvent) error
	DeleteEvent(ctx context.Context, id uuid.UUID) error
	
	// Batch operations
	GetPendingEvents(ctx context.Context, limit int) ([]*models.OutboxEvent, error)
	GetEventsByStatus(ctx context.Context, status string, limit, offset int) ([]*models.OutboxEvent, error)
	GetEventsByAggregateID(ctx context.Context, aggregateID string) ([]*models.OutboxEvent, error)
	
	// Metrics and monitoring
	CountEventsByStatus(ctx context.Context, status string) (int64, error)
	CountEventsByType(ctx context.Context, eventType string) (int64, error)
	GetOldestPendingEvent(ctx context.Context) (*models.OutboxEvent, error)
	
	// Cleanup operations
	DeleteProcessedEventsBefore(ctx context.Context, before time.Time) (int64, error)
	DeleteFailedEventsBefore(ctx context.Context, before time.Time) (int64, error)
}

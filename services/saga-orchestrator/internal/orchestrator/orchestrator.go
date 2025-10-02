package orchestrator

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"github.com/google/uuid"
	"github.com/microservices-saga/services/saga-orchestrator/internal/infrastructure"
	"github.com/microservices-saga/services/saga-orchestrator/internal/models"
	"github.com/microservices-saga/services/saga-orchestrator/internal/repository"
	"github.com/microservices-saga/services/saga-orchestrator/internal/services"
	"github.com/sirupsen/logrus"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
)

var tracer = otel.Tracer("saga-orchestrator")

// SagaOrchestrator manages saga execution and coordination
type SagaOrchestrator struct {
	sagaRepo            repository.SagaRepository
	outboxRepo          repository.OutboxRepository
	eventService        services.EventService
	idempotencyService  services.IdempotencyService
	compensationService services.CompensationService
	metrics             *infrastructure.Metrics
	logger              *logrus.Logger
	sagaDefinitions     map[string]*models.SagaDefinition
}

// NewSagaOrchestrator creates a new saga orchestrator
func NewSagaOrchestrator(
	sagaRepo repository.SagaRepository,
	outboxRepo repository.OutboxRepository,
	eventService services.EventService,
	idempotencyService services.IdempotencyService,
	compensationService services.CompensationService,
	metrics *infrastructure.Metrics,
	logger *logrus.Logger,
) *SagaOrchestrator {
	orchestrator := &SagaOrchestrator{
		sagaRepo:            sagaRepo,
		outboxRepo:          outboxRepo,
		eventService:        eventService,
		idempotencyService:  idempotencyService,
		compensationService: compensationService,
		metrics:             metrics,
		logger:              logger,
		sagaDefinitions:     make(map[string]*models.SagaDefinition),
	}

	// Register saga definitions
	orchestrator.registerSagaDefinitions()

	return orchestrator
}

// CreateSaga creates a new saga instance
func (o *SagaOrchestrator) CreateSaga(ctx context.Context, req *models.CreateSagaRequest) (*models.SagaInstance, error) {
	ctx, span := tracer.Start(ctx, "orchestrator.CreateSaga")
	defer span.End()

	span.SetAttributes(
		attribute.String("saga.type", req.SagaType),
		attribute.String("correlation.id", stringValue(req.CorrelationID)),
	)

	// Check idempotency
	if req.IdempotencyKey != nil {
		if existing, err := o.idempotencyService.GetResult(ctx, *req.IdempotencyKey); err == nil {
			o.logger.WithField("idempotency_key", *req.IdempotencyKey).Info("Returning cached saga result")
			var saga models.SagaInstance
			if err := json.Unmarshal(existing, &saga); err == nil {
				return &saga, nil
			}
		}
	}

	// Validate saga type
	definition, exists := o.sagaDefinitions[req.SagaType]
	if !exists {
		return nil, fmt.Errorf("unknown saga type: %s", req.SagaType)
	}

	// Create saga instance
	saga := &models.SagaInstance{
		ID:             uuid.New(),
		SagaType:       req.SagaType,
		SagaData:       req.SagaData,
		Status:         models.SagaStatusStarted,
		CurrentStep:    0,
		CreatedAt:      time.Now(),
		UpdatedAt:      time.Now(),
		RetryCount:     0,
		MaxRetries:     definition.MaxRetries,
		CorrelationID:  req.CorrelationID,
		IdempotencyKey: req.IdempotencyKey,
	}

	// Save saga instance
	if err := o.sagaRepo.Create(ctx, saga); err != nil {
		span.RecordError(err)
		return nil, fmt.Errorf("failed to create saga: %w", err)
	}

	// Create saga steps
	if err := o.createSagaSteps(ctx, saga, definition); err != nil {
		span.RecordError(err)
		return nil, fmt.Errorf("failed to create saga steps: %w", err)
	}

	// Cache result for idempotency
	if req.IdempotencyKey != nil {
		if data, err := json.Marshal(saga); err == nil {
			o.idempotencyService.StoreResult(ctx, *req.IdempotencyKey, data, 24*time.Hour)
		}
	}

	// Publish saga started event
	event := &models.SagaEvent{
		ID:            uuid.New(),
		SagaID:        saga.ID,
		EventType:     "saga.started",
		EventData:     req.SagaData,
		Timestamp:     time.Now(),
		CorrelationID: stringValue(req.CorrelationID),
		CausationID:   saga.ID.String(),
	}

	if err := o.publishEvent(ctx, event); err != nil {
		o.logger.WithError(err).Error("Failed to publish saga started event")
	}

	// Update metrics
	o.metrics.SagasCreated.WithLabelValues(req.SagaType).Inc()

	o.logger.WithFields(logrus.Fields{
		"saga_id":   saga.ID,
		"saga_type": saga.SagaType,
	}).Info("Saga created successfully")

	return saga, nil
}

// GetSaga retrieves a saga by ID
func (o *SagaOrchestrator) GetSaga(ctx context.Context, sagaID uuid.UUID) (*models.SagaInstance, error) {
	ctx, span := tracer.Start(ctx, "orchestrator.GetSaga")
	defer span.End()

	span.SetAttributes(attribute.String("saga.id", sagaID.String()))

	saga, err := o.sagaRepo.GetByID(ctx, sagaID)
	if err != nil {
		span.RecordError(err)
		return nil, fmt.Errorf("failed to get saga: %w", err)
	}

	return saga, nil
}

// ListSagas retrieves sagas with pagination
func (o *SagaOrchestrator) ListSagas(ctx context.Context, limit, offset int, status *models.SagaStatus) ([]*models.SagaInstance, int, error) {
	ctx, span := tracer.Start(ctx, "orchestrator.ListSagas")
	defer span.End()

	span.SetAttributes(
		attribute.Int("limit", limit),
		attribute.Int("offset", offset),
	)

	if status != nil {
		span.SetAttributes(attribute.String("status", string(*status)))
	}

	sagas, total, err := o.sagaRepo.List(ctx, limit, offset, status)
	if err != nil {
		span.RecordError(err)
		return nil, 0, fmt.Errorf("failed to list sagas: %w", err)
	}

	return sagas, total, nil
}

// CompensateSaga initiates compensation for a saga
func (o *SagaOrchestrator) CompensateSaga(ctx context.Context, sagaID uuid.UUID, reason string) error {
	ctx, span := tracer.Start(ctx, "orchestrator.CompensateSaga")
	defer span.End()

	span.SetAttributes(
		attribute.String("saga.id", sagaID.String()),
		attribute.String("reason", reason),
	)

	saga, err := o.sagaRepo.GetByID(ctx, sagaID)
	if err != nil {
		span.RecordError(err)
		return fmt.Errorf("failed to get saga: %w", err)
	}

	if saga.Status.IsTerminal() {
		return fmt.Errorf("cannot compensate saga in status: %s", saga.Status)
	}

	// Update saga status
	saga.Status = models.SagaStatusFailed
	saga.UpdatedAt = time.Now()
	saga.ErrorMessage = &reason

	if err := o.sagaRepo.Update(ctx, saga); err != nil {
		span.RecordError(err)
		return fmt.Errorf("failed to update saga: %w", err)
	}

	// Start compensation
	if err := o.compensationService.StartCompensation(ctx, saga); err != nil {
		span.RecordError(err)
		return fmt.Errorf("failed to start compensation: %w", err)
	}

	// Update metrics
	o.metrics.SagasCompensated.WithLabelValues(saga.SagaType).Inc()

	o.logger.WithFields(logrus.Fields{
		"saga_id": sagaID,
		"reason":  reason,
	}).Info("Saga compensation initiated")

	return nil
}

// RetrySaga retries a failed saga from a specific step
func (o *SagaOrchestrator) RetrySaga(ctx context.Context, sagaID uuid.UUID, fromStep int) error {
	ctx, span := tracer.Start(ctx, "orchestrator.RetrySaga")
	defer span.End()

	span.SetAttributes(
		attribute.String("saga.id", sagaID.String()),
		attribute.Int("from_step", fromStep),
	)

	saga, err := o.sagaRepo.GetByID(ctx, sagaID)
	if err != nil {
		span.RecordError(err)
		return fmt.Errorf("failed to get saga: %w", err)
	}

	if saga.Status != models.SagaStatusFailed {
		return fmt.Errorf("can only retry failed sagas, current status: %s", saga.Status)
	}

	if saga.RetryCount >= saga.MaxRetries {
		return fmt.Errorf("saga has exceeded maximum retry count: %d", saga.MaxRetries)
	}

	// Reset saga state
	saga.Status = models.SagaStatusInProgress
	saga.CurrentStep = fromStep
	saga.RetryCount++
	saga.UpdatedAt = time.Now()
	saga.ErrorMessage = nil

	if err := o.sagaRepo.Update(ctx, saga); err != nil {
		span.RecordError(err)
		return fmt.Errorf("failed to update saga: %w", err)
	}

	// Reset steps from the retry point
	if err := o.resetSagaSteps(ctx, sagaID, fromStep); err != nil {
		span.RecordError(err)
		return fmt.Errorf("failed to reset saga steps: %w", err)
	}

	// Update metrics
	o.metrics.SagasRetried.WithLabelValues(saga.SagaType).Inc()

	o.logger.WithFields(logrus.Fields{
		"saga_id":     sagaID,
		"from_step":   fromStep,
		"retry_count": saga.RetryCount,
	}).Info("Saga retry initiated")

	return nil
}

// Helper functions
func stringValue(s *string) string {
	if s == nil {
		return ""
	}
	return *s
}

func (o *SagaOrchestrator) createSagaSteps(ctx context.Context, saga *models.SagaInstance, definition *models.SagaDefinition) error {
	for _, stepDef := range definition.Steps {
		step := &models.SagaStep{
			ID:        uuid.New(),
			SagaID:    saga.ID,
			StepName:  stepDef.Name,
			StepOrder: stepDef.Order,
			Status:    models.StepStatusPending,
		}

		if err := o.sagaRepo.CreateStep(ctx, step); err != nil {
			return fmt.Errorf("failed to create step %s: %w", stepDef.Name, err)
		}
	}

	return nil
}

func (o *SagaOrchestrator) resetSagaSteps(ctx context.Context, sagaID uuid.UUID, fromStep int) error {
	steps, err := o.sagaRepo.GetSteps(ctx, sagaID)
	if err != nil {
		return fmt.Errorf("failed to get saga steps: %w", err)
	}

	for _, step := range steps {
		if step.StepOrder >= fromStep {
			step.Status = models.StepStatusPending
			step.StartedAt = nil
			step.CompletedAt = nil
			step.ErrorMessage = nil
			step.RetryCount = 0

			if err := o.sagaRepo.UpdateStep(ctx, step); err != nil {
				return fmt.Errorf("failed to reset step %s: %w", step.StepName, err)
			}
		}
	}

	return nil
}

func (o *SagaOrchestrator) publishEvent(ctx context.Context, event *models.SagaEvent) error {
	eventData, err := json.Marshal(event)
	if err != nil {
		return fmt.Errorf("failed to marshal event: %w", err)
	}

	return o.eventService.PublishEvent(ctx, "saga-events", event.SagaID.String(), eventData)
}

// registerSagaDefinitions registers all saga definitions
func (o *SagaOrchestrator) registerSagaDefinitions() {
	// Order Processing Saga
	o.sagaDefinitions["order-processing"] = &models.SagaDefinition{
		Type:       "order-processing",
		Timeout:    5 * time.Minute,
		MaxRetries: 3,
		Steps: []models.StepDefinition{
			{
				Name:               "reserve-inventory",
				Order:              1,
				Action:             "inventory.reserve",
				CompensationAction: "inventory.release",
				Timeout:            30 * time.Second,
				MaxRetries:         3,
				RetryDelay:         5 * time.Second,
			},
			{
				Name:               "process-payment",
				Order:              2,
				Action:             "payment.charge",
				CompensationAction: "payment.refund",
				Timeout:            30 * time.Second,
				MaxRetries:         3,
				RetryDelay:         5 * time.Second,
			},
			{
				Name:               "send-confirmation",
				Order:              3,
				Action:             "notification.send",
				CompensationAction: "notification.cancel",
				Timeout:            15 * time.Second,
				MaxRetries:         2,
				RetryDelay:         3 * time.Second,
				ContinueOnFailure:  true,
			},
		},
	}

	// Payment Refund Saga
	o.sagaDefinitions["payment-refund"] = &models.SagaDefinition{
		Type:       "payment-refund",
		Timeout:    3 * time.Minute,
		MaxRetries: 3,
		Steps: []models.StepDefinition{
			{
				Name:               "process-refund",
				Order:              1,
				Action:             "payment.refund",
				CompensationAction: "payment.reverse-refund",
				Timeout:            30 * time.Second,
				MaxRetries:         3,
				RetryDelay:         5 * time.Second,
			},
			{
				Name:               "restore-inventory",
				Order:              2,
				Action:             "inventory.restore",
				CompensationAction: "inventory.reserve",
				Timeout:            15 * time.Second,
				MaxRetries:         2,
				RetryDelay:         3 * time.Second,
			},
			{
				Name:               "send-refund-notification",
				Order:              3,
				Action:             "notification.send-refund",
				CompensationAction: "notification.cancel",
				Timeout:            15 * time.Second,
				MaxRetries:         2,
				RetryDelay:         3 * time.Second,
				ContinueOnFailure:  true,
			},
		},
	}
}

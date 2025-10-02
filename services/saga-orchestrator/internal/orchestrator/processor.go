package orchestrator

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"github.com/microservices-saga/services/saga-orchestrator/internal/infrastructure"
	"github.com/microservices-saga/services/saga-orchestrator/internal/models"
	"go.opentelemetry.io/otel/attribute"
)

// StartSagaProcessor starts the saga processing loop
func (o *SagaOrchestrator) StartSagaProcessor(ctx context.Context) {
	ticker := time.NewTicker(5 * time.Second)
	defer ticker.Stop()

	o.logger.Info("Starting saga processor")

	for {
		select {
		case <-ctx.Done():
			o.logger.Info("Saga processor stopped")
			return
		case <-ticker.C:
			if err := o.processPendingSagas(ctx); err != nil {
				o.logger.WithError(err).Error("Error processing pending sagas")
			}
		}
	}
}

// processPendingSagas processes all pending sagas
func (o *SagaOrchestrator) processPendingSagas(ctx context.Context) error {
	ctx, span := tracer.Start(ctx, "orchestrator.processPendingSagas")
	defer span.End()

	// Get sagas that need processing
	statuses := []models.SagaStatus{models.SagaStatusStarted, models.SagaStatusInProgress}
	
	for _, status := range statuses {
		sagas, _, err := o.sagaRepo.List(ctx, 100, 0, &status)
		if err != nil {
			span.RecordError(err)
			return fmt.Errorf("failed to get pending sagas: %w", err)
		}

		for _, saga := range sagas {
			if err := o.processSaga(ctx, saga); err != nil {
				o.logger.WithError(err).WithField("saga_id", saga.ID).Error("Failed to process saga")
				continue
			}
		}
	}

	return nil
}

// processSaga processes a single saga
func (o *SagaOrchestrator) processSaga(ctx context.Context, saga *models.SagaInstance) error {
	ctx, span := tracer.Start(ctx, "orchestrator.processSaga")
	defer span.End()

	span.SetAttributes(
		attribute.String("saga.id", saga.ID.String()),
		attribute.String("saga.type", saga.SagaType),
		attribute.String("saga.status", string(saga.Status)),
		attribute.Int("saga.current_step", saga.CurrentStep),
	)

	definition, exists := o.sagaDefinitions[saga.SagaType]
	if !exists {
		return fmt.Errorf("unknown saga type: %s", saga.SagaType)
	}

	// Check for timeout
	if time.Since(saga.CreatedAt) > definition.Timeout {
		return o.timeoutSaga(ctx, saga)
	}

	// Get current step
	steps, err := o.sagaRepo.GetSteps(ctx, saga.ID)
	if err != nil {
		return fmt.Errorf("failed to get saga steps: %w", err)
	}

	// Find next step to execute
	var currentStep *models.SagaStep
	for _, step := range steps {
		if step.StepOrder == saga.CurrentStep+1 && step.Status == models.StepStatusPending {
			currentStep = step
			break
		}
	}

	if currentStep == nil {
		// Check if all steps are completed
		allCompleted := true
		for _, step := range steps {
			if step.Status != models.StepStatusCompleted && step.Status != models.StepStatusSkipped {
				allCompleted = false
				break
			}
		}

		if allCompleted {
			return o.completeSaga(ctx, saga)
		}

		// No more steps to process
		return nil
	}

	// Execute the step
	return o.executeStep(ctx, saga, currentStep, definition)
}

// executeStep executes a saga step
func (o *SagaOrchestrator) executeStep(ctx context.Context, saga *models.SagaInstance, step *models.SagaStep, definition *models.SagaDefinition) error {
	ctx, span := tracer.Start(ctx, "orchestrator.executeStep")
	defer span.End()

	span.SetAttributes(
		attribute.String("saga.id", saga.ID.String()),
		attribute.String("step.name", step.StepName),
		attribute.Int("step.order", step.StepOrder),
	)

	// Find step definition
	var stepDef *models.StepDefinition
	for _, def := range definition.Steps {
		if def.Name == step.StepName {
			stepDef = &def
			break
		}
	}

	if stepDef == nil {
		return fmt.Errorf("step definition not found: %s", step.StepName)
	}

	// Update step status to in progress
	step.Status = models.StepStatusInProgress
	step.StartedAt = timePtr(time.Now())

	if err := o.sagaRepo.UpdateStep(ctx, step); err != nil {
		return fmt.Errorf("failed to update step status: %w", err)
	}

	// Create step execution event
	stepEvent := &models.SagaEvent{
		ID:            step.ID,
		SagaID:        saga.ID,
		EventType:     fmt.Sprintf("step.%s.execute", stepDef.Action),
		EventData:     saga.SagaData,
		Timestamp:     time.Now(),
		CorrelationID: stringValue(saga.CorrelationID),
		CausationID:   saga.ID.String(),
	}

	// Publish step execution event
	if err := o.publishEvent(ctx, stepEvent); err != nil {
		o.logger.WithError(err).Error("Failed to publish step execution event")
		return o.failStep(ctx, saga, step, err.Error())
	}

	// Update saga current step
	saga.CurrentStep = step.StepOrder
	saga.Status = models.SagaStatusInProgress
	saga.UpdatedAt = time.Now()

	if err := o.sagaRepo.Update(ctx, saga); err != nil {
		return fmt.Errorf("failed to update saga: %w", err)
	}

	// Update metrics
	o.metrics.SagaStepsExecuted.WithLabelValues(saga.SagaType, step.StepName).Inc()

	o.logger.WithFields(map[string]interface{}{
		"saga_id":   saga.ID,
		"step_name": step.StepName,
		"action":    stepDef.Action,
	}).Info("Step execution initiated")

	return nil
}

// completeSaga marks a saga as completed
func (o *SagaOrchestrator) completeSaga(ctx context.Context, saga *models.SagaInstance) error {
	ctx, span := tracer.Start(ctx, "orchestrator.completeSaga")
	defer span.End()

	span.SetAttributes(attribute.String("saga.id", saga.ID.String()))

	saga.Status = models.SagaStatusCompleted
	saga.CompletedAt = timePtr(time.Now())
	saga.UpdatedAt = time.Now()

	if err := o.sagaRepo.Update(ctx, saga); err != nil {
		return fmt.Errorf("failed to complete saga: %w", err)
	}

	// Publish saga completed event
	event := &models.SagaEvent{
		ID:            saga.ID,
		SagaID:        saga.ID,
		EventType:     "saga.completed",
		EventData:     saga.SagaData,
		Timestamp:     time.Now(),
		CorrelationID: stringValue(saga.CorrelationID),
		CausationID:   saga.ID.String(),
	}

	if err := o.publishEvent(ctx, event); err != nil {
		o.logger.WithError(err).Error("Failed to publish saga completed event")
	}

	// Update metrics
	o.metrics.SagasCompleted.WithLabelValues(saga.SagaType).Inc()
	
	duration := time.Since(saga.CreatedAt)
	o.metrics.SagaDuration.WithLabelValues(saga.SagaType).Observe(duration.Seconds())

	o.logger.WithFields(map[string]interface{}{
		"saga_id":   saga.ID,
		"saga_type": saga.SagaType,
		"duration":  duration,
	}).Info("Saga completed successfully")

	return nil
}

// failStep marks a step as failed
func (o *SagaOrchestrator) failStep(ctx context.Context, saga *models.SagaInstance, step *models.SagaStep, errorMsg string) error {
	step.Status = models.StepStatusFailed
	step.CompletedAt = timePtr(time.Now())
	step.ErrorMessage = &errorMsg

	if err := o.sagaRepo.UpdateStep(ctx, step); err != nil {
		return fmt.Errorf("failed to update failed step: %w", err)
	}

	// Check if step should be retried
	stepDef := o.getStepDefinition(saga.SagaType, step.StepName)
	if stepDef != nil && step.RetryCount < stepDef.MaxRetries {
		step.RetryCount++
		step.Status = models.StepStatusPending
		step.StartedAt = nil
		step.CompletedAt = nil
		step.ErrorMessage = nil

		if err := o.sagaRepo.UpdateStep(ctx, step); err != nil {
			return fmt.Errorf("failed to retry step: %w", err)
		}

		o.logger.WithFields(map[string]interface{}{
			"saga_id":     saga.ID,
			"step_name":   step.StepName,
			"retry_count": step.RetryCount,
		}).Info("Step scheduled for retry")

		return nil
	}

	// Check if step can continue on failure
	if stepDef != nil && stepDef.ContinueOnFailure {
		step.Status = models.StepStatusSkipped
		if err := o.sagaRepo.UpdateStep(ctx, step); err != nil {
			return fmt.Errorf("failed to skip step: %w", err)
		}

		o.logger.WithFields(map[string]interface{}{
			"saga_id":   saga.ID,
			"step_name": step.StepName,
		}).Info("Step skipped due to continue on failure")

		return nil
	}

	// Fail the entire saga
	return o.failSaga(ctx, saga, errorMsg)
}

// failSaga marks a saga as failed and initiates compensation
func (o *SagaOrchestrator) failSaga(ctx context.Context, saga *models.SagaInstance, errorMsg string) error {
	saga.Status = models.SagaStatusFailed
	saga.UpdatedAt = time.Now()
	saga.ErrorMessage = &errorMsg

	if err := o.sagaRepo.Update(ctx, saga); err != nil {
		return fmt.Errorf("failed to fail saga: %w", err)
	}

	// Start compensation
	if err := o.compensationService.StartCompensation(ctx, saga); err != nil {
		o.logger.WithError(err).Error("Failed to start compensation")
	}

	// Update metrics
	o.metrics.SagasFailed.WithLabelValues(saga.SagaType).Inc()

	o.logger.WithFields(map[string]interface{}{
		"saga_id": saga.ID,
		"error":   errorMsg,
	}).Error("Saga failed")

	return nil
}

// timeoutSaga handles saga timeout
func (o *SagaOrchestrator) timeoutSaga(ctx context.Context, saga *models.SagaInstance) error {
	return o.failSaga(ctx, saga, "saga timeout exceeded")
}

// getStepDefinition gets step definition by name
func (o *SagaOrchestrator) getStepDefinition(sagaType, stepName string) *models.StepDefinition {
	definition, exists := o.sagaDefinitions[sagaType]
	if !exists {
		return nil
	}

	for _, step := range definition.Steps {
		if step.Name == stepName {
			return &step
		}
	}

	return nil
}

// Helper functions
func timePtr(t time.Time) *time.Time {
	return &t
}

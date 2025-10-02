package orchestrator

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"github.com/google/uuid"
	"github.com/microservices-saga/services/saga-orchestrator/internal/infrastructure"
	"github.com/microservices-saga/services/saga-orchestrator/internal/models"
	"go.opentelemetry.io/otel/attribute"
)

// StartEventConsumer starts consuming events from Kafka
func (o *SagaOrchestrator) StartEventConsumer(ctx context.Context, consumer *infrastructure.KafkaConsumer) error {
	o.logger.Info("Starting event consumer")

	topics := []string{
		"inventory-events",
		"payment-events",
		"notification-events",
		"saga-events",
	}

	return consumer.Subscribe(ctx, topics, o.handleEvent)
}

// handleEvent handles incoming events
func (o *SagaOrchestrator) handleEvent(ctx context.Context, topic, key string, value []byte) error {
	ctx, span := tracer.Start(ctx, "orchestrator.handleEvent")
	defer span.End()

	span.SetAttributes(
		attribute.String("kafka.topic", topic),
		attribute.String("kafka.key", key),
	)

	o.logger.WithFields(map[string]interface{}{
		"topic": topic,
		"key":   key,
	}).Debug("Received event")

	switch topic {
	case "inventory-events":
		return o.handleInventoryEvent(ctx, key, value)
	case "payment-events":
		return o.handlePaymentEvent(ctx, key, value)
	case "notification-events":
		return o.handleNotificationEvent(ctx, key, value)
	case "saga-events":
		return o.handleSagaEvent(ctx, key, value)
	default:
		o.logger.WithField("topic", topic).Warn("Unknown topic")
		return nil
	}
}

// handleInventoryEvent handles inventory service events
func (o *SagaOrchestrator) handleInventoryEvent(ctx context.Context, key string, value []byte) error {
	ctx, span := tracer.Start(ctx, "orchestrator.handleInventoryEvent")
	defer span.End()

	var event map[string]interface{}
	if err := json.Unmarshal(value, &event); err != nil {
		span.RecordError(err)
		return fmt.Errorf("failed to unmarshal inventory event: %w", err)
	}

	eventType, ok := event["event_type"].(string)
	if !ok {
		return fmt.Errorf("missing event_type in inventory event")
	}

	span.SetAttributes(attribute.String("event.type", eventType))

	switch eventType {
	case "inventory.reserved":
		return o.handleInventoryReserved(ctx, event)
	case "inventory.reservation_failed":
		return o.handleInventoryReservationFailed(ctx, event)
	case "inventory.released":
		return o.handleInventoryReleased(ctx, event)
	default:
		o.logger.WithField("event_type", eventType).Debug("Unhandled inventory event")
		return nil
	}
}

// handlePaymentEvent handles payment service events
func (o *SagaOrchestrator) handlePaymentEvent(ctx context.Context, key string, value []byte) error {
	ctx, span := tracer.Start(ctx, "orchestrator.handlePaymentEvent")
	defer span.End()

	var event map[string]interface{}
	if err := json.Unmarshal(value, &event); err != nil {
		span.RecordError(err)
		return fmt.Errorf("failed to unmarshal payment event: %w", err)
	}

	eventType, ok := event["event_type"].(string)
	if !ok {
		return fmt.Errorf("missing event_type in payment event")
	}

	span.SetAttributes(attribute.String("event.type", eventType))

	switch eventType {
	case "payment.charged":
		return o.handlePaymentCharged(ctx, event)
	case "payment.charge_failed":
		return o.handlePaymentChargeFailed(ctx, event)
	case "payment.refunded":
		return o.handlePaymentRefunded(ctx, event)
	default:
		o.logger.WithField("event_type", eventType).Debug("Unhandled payment event")
		return nil
	}
}

// handleNotificationEvent handles notification service events
func (o *SagaOrchestrator) handleNotificationEvent(ctx context.Context, key string, value []byte) error {
	ctx, span := tracer.Start(ctx, "orchestrator.handleNotificationEvent")
	defer span.End()

	var event map[string]interface{}
	if err := json.Unmarshal(value, &event); err != nil {
		span.RecordError(err)
		return fmt.Errorf("failed to unmarshal notification event: %w", err)
	}

	eventType, ok := event["event_type"].(string)
	if !ok {
		return fmt.Errorf("missing event_type in notification event")
	}

	span.SetAttributes(attribute.String("event.type", eventType))

	switch eventType {
	case "notification.sent":
		return o.handleNotificationSent(ctx, event)
	case "notification.send_failed":
		return o.handleNotificationSendFailed(ctx, event)
	default:
		o.logger.WithField("event_type", eventType).Debug("Unhandled notification event")
		return nil
	}
}

// handleSagaEvent handles saga orchestrator events
func (o *SagaOrchestrator) handleSagaEvent(ctx context.Context, key string, value []byte) error {
	// Handle internal saga events if needed
	return nil
}

// Event handlers for specific events
func (o *SagaOrchestrator) handleInventoryReserved(ctx context.Context, event map[string]interface{}) error {
	return o.completeStep(ctx, event, "reserve-inventory")
}

func (o *SagaOrchestrator) handleInventoryReservationFailed(ctx context.Context, event map[string]interface{}) error {
	return o.failStepFromEvent(ctx, event, "reserve-inventory")
}

func (o *SagaOrchestrator) handleInventoryReleased(ctx context.Context, event map[string]interface{}) error {
	return o.completeStep(ctx, event, "restore-inventory")
}

func (o *SagaOrchestrator) handlePaymentCharged(ctx context.Context, event map[string]interface{}) error {
	return o.completeStep(ctx, event, "process-payment")
}

func (o *SagaOrchestrator) handlePaymentChargeFailed(ctx context.Context, event map[string]interface{}) error {
	return o.failStepFromEvent(ctx, event, "process-payment")
}

func (o *SagaOrchestrator) handlePaymentRefunded(ctx context.Context, event map[string]interface{}) error {
	return o.completeStep(ctx, event, "process-refund")
}

func (o *SagaOrchestrator) handleNotificationSent(ctx context.Context, event map[string]interface{}) error {
	return o.completeStep(ctx, event, "send-confirmation")
}

func (o *SagaOrchestrator) handleNotificationSendFailed(ctx context.Context, event map[string]interface{}) error {
	return o.failStepFromEvent(ctx, event, "send-confirmation")
}

// completeStep marks a step as completed based on an event
func (o *SagaOrchestrator) completeStep(ctx context.Context, event map[string]interface{}, stepName string) error {
	ctx, span := tracer.Start(ctx, "orchestrator.completeStep")
	defer span.End()

	span.SetAttributes(attribute.String("step.name", stepName))

	sagaID, err := o.extractSagaID(event)
	if err != nil {
		span.RecordError(err)
		return err
	}

	span.SetAttributes(attribute.String("saga.id", sagaID))

	// Get saga
	saga, err := o.sagaRepo.GetByID(ctx, sagaID)
	if err != nil {
		span.RecordError(err)
		return fmt.Errorf("failed to get saga: %w", err)
	}

	// Get step
	steps, err := o.sagaRepo.GetSteps(ctx, sagaID)
	if err != nil {
		span.RecordError(err)
		return fmt.Errorf("failed to get saga steps: %w", err)
	}

	var step *models.SagaStep
	for _, s := range steps {
		if s.StepName == stepName && s.Status == models.StepStatusInProgress {
			step = s
			break
		}
	}

	if step == nil {
		o.logger.WithFields(map[string]interface{}{
			"saga_id":   sagaID,
			"step_name": stepName,
		}).Warn("Step not found or not in progress")
		return nil
	}

	// Update step
	step.Status = models.StepStatusCompleted
	step.CompletedAt = timePtr(time.Now())

	if outputData, err := json.Marshal(event); err == nil {
		step.OutputData = outputData
	}

	if err := o.sagaRepo.UpdateStep(ctx, step); err != nil {
		span.RecordError(err)
		return fmt.Errorf("failed to update step: %w", err)
	}

	// Update metrics
	o.metrics.SagaStepsCompleted.WithLabelValues(saga.SagaType, stepName).Inc()

	o.logger.WithFields(map[string]interface{}{
		"saga_id":   sagaID,
		"step_name": stepName,
	}).Info("Step completed successfully")

	return nil
}

// failStepFromEvent marks a step as failed based on an event
func (o *SagaOrchestrator) failStepFromEvent(ctx context.Context, event map[string]interface{}, stepName string) error {
	ctx, span := tracer.Start(ctx, "orchestrator.failStepFromEvent")
	defer span.End()

	span.SetAttributes(attribute.String("step.name", stepName))

	sagaID, err := o.extractSagaID(event)
	if err != nil {
		span.RecordError(err)
		return err
	}

	span.SetAttributes(attribute.String("saga.id", sagaID.String()))

	// Get saga
	saga, err := o.sagaRepo.GetByID(ctx, sagaID)
	if err != nil {
		span.RecordError(err)
		return fmt.Errorf("failed to get saga: %w", err)
	}

	// Get step
	steps, err := o.sagaRepo.GetSteps(ctx, sagaID)
	if err != nil {
		span.RecordError(err)
		return fmt.Errorf("failed to get saga steps: %w", err)
	}

	var step *models.SagaStep
	for _, s := range steps {
		if s.StepName == stepName && s.Status == models.StepStatusInProgress {
			step = s
			break
		}
	}

	if step == nil {
		o.logger.WithFields(map[string]interface{}{
			"saga_id":   sagaID,
			"step_name": stepName,
		}).Warn("Step not found or not in progress")
		return nil
	}

	// Extract error message
	errorMsg := "step execution failed"
	if errMsg, ok := event["error_message"].(string); ok {
		errorMsg = errMsg
	}

	// Update metrics
	o.metrics.SagaStepsFailed.WithLabelValues(saga.SagaType, stepName).Inc()

	// Use the existing failStep method from processor.go
	return o.failStep(ctx, saga, step, errorMsg)
}

// extractSagaID extracts saga ID from event
func (o *SagaOrchestrator) extractSagaID(event map[string]interface{}) (uuid.UUID, error) {
	// Try different possible field names for saga ID
	fields := []string{"saga_id", "correlation_id", "order_id"}

	for _, field := range fields {
		if idStr, ok := event[field].(string); ok {
			if id, err := uuid.Parse(idStr); err == nil {
				return id, nil
			}
		}
	}

	return uuid.Nil, fmt.Errorf("saga ID not found in event")
}

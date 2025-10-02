package services

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"github.com/google/uuid"
	"github.com/microservices-saga/services/saga-orchestrator/internal/models"
	"github.com/sirupsen/logrus"
	"go.opentelemetry.io/otel/attribute"
)

// CompensationService handles saga compensation logic
type CompensationService interface {
	StartCompensation(ctx context.Context, saga *models.SagaInstance) error
	CompensateStep(ctx context.Context, saga *models.SagaInstance, step *models.SagaStep) error
	IsCompensationRequired(step *models.SagaStep) bool
}

// DefaultCompensationService implements CompensationService
type DefaultCompensationService struct {
	eventService EventService
	logger       *logrus.Logger
}

// NewCompensationService creates a new compensation service
func NewCompensationService(eventService EventService, logger *logrus.Logger) CompensationService {
	return &DefaultCompensationService{
		eventService: eventService,
		logger:       logger,
	}
}

// StartCompensation initiates compensation for a failed saga
func (s *DefaultCompensationService) StartCompensation(ctx context.Context, saga *models.SagaInstance) error {
	ctx, span := tracer.Start(ctx, "compensation_service.StartCompensation")
	defer span.End()

	span.SetAttributes(
		attribute.String("saga.id", saga.ID.String()),
		attribute.String("saga.type", saga.SagaType),
		attribute.Int("saga.current_step", saga.CurrentStep),
	)

	s.logger.WithFields(logrus.Fields{
		"saga_id":      saga.ID,
		"saga_type":    saga.SagaType,
		"current_step": saga.CurrentStep,
	}).Info("Starting saga compensation")

	// Create compensation started event
	compensationEvent := &models.SagaEvent{
		ID:            uuid.New(),
		SagaID:        saga.ID,
		EventType:     "saga.compensation.started",
		EventData:     saga.SagaData,
		Timestamp:     time.Now(),
		CorrelationID: stringValue(saga.CorrelationID),
		CausationID:   saga.ID.String(),
	}

	// Publish compensation started event
	if err := s.publishCompensationEvent(ctx, compensationEvent); err != nil {
		s.logger.WithError(err).Error("Failed to publish compensation started event")
	}

	// Get completed steps that need compensation (in reverse order)
	completedSteps, err := s.getCompletedStepsForCompensation(saga)
	if err != nil {
		span.RecordError(err)
		return fmt.Errorf("failed to get completed steps for compensation: %w", err)
	}

	if len(completedSteps) == 0 {
		s.logger.WithField("saga_id", saga.ID).Info("No steps require compensation")
		return s.markCompensationCompleted(ctx, saga)
	}

	// Start compensating steps in reverse order
	for i := len(completedSteps) - 1; i >= 0; i-- {
		step := completedSteps[i]
		if s.IsCompensationRequired(step) {
			if err := s.CompensateStep(ctx, saga, step); err != nil {
				span.RecordError(err)
				s.logger.WithError(err).WithFields(logrus.Fields{
					"saga_id":   saga.ID,
					"step_name": step.StepName,
				}).Error("Failed to compensate step")
				continue // Continue with other steps
			}
		}
	}

	return s.markCompensationCompleted(ctx, saga)
}

// CompensateStep compensates a specific saga step
func (s *DefaultCompensationService) CompensateStep(ctx context.Context, saga *models.SagaInstance, step *models.SagaStep) error {
	ctx, span := tracer.Start(ctx, "compensation_service.CompensateStep")
	defer span.End()

	span.SetAttributes(
		attribute.String("saga.id", saga.ID.String()),
		attribute.String("step.name", step.StepName),
		attribute.Int("step.order", step.StepOrder),
	)

	s.logger.WithFields(logrus.Fields{
		"saga_id":   saga.ID,
		"step_name": step.StepName,
		"step_id":   step.ID,
	}).Info("Compensating saga step")

	// Determine compensation action based on step
	compensationAction := s.getCompensationAction(saga.SagaType, step.StepName)
	if compensationAction == "" {
		s.logger.WithFields(logrus.Fields{
			"saga_id":   saga.ID,
			"step_name": step.StepName,
		}).Warn("No compensation action defined for step")
		return nil
	}

	// Create compensation data
	compensationData := map[string]interface{}{
		"saga_id":           saga.ID,
		"step_id":           step.ID,
		"step_name":         step.StepName,
		"compensation_action": compensationAction,
		"original_data":     step.OutputData,
		"timestamp":         time.Now(),
	}

	// Add saga-specific compensation data
	if err := s.addSagaSpecificCompensationData(saga, step, compensationData); err != nil {
		s.logger.WithError(err).Warn("Failed to add saga-specific compensation data")
	}

	// Create compensation event
	compensationEvent := &models.SagaEvent{
		ID:            uuid.New(),
		SagaID:        saga.ID,
		EventType:     fmt.Sprintf("step.%s.compensate", compensationAction),
		EventData:     mustMarshal(compensationData),
		Timestamp:     time.Now(),
		CorrelationID: stringValue(saga.CorrelationID),
		CausationID:   step.ID.String(),
	}

	// Publish compensation event
	if err := s.publishCompensationEvent(ctx, compensationEvent); err != nil {
		span.RecordError(err)
		return fmt.Errorf("failed to publish compensation event: %w", err)
	}

	// Store compensation data in step
	step.CompensationData = mustMarshal(compensationData)

	s.logger.WithFields(logrus.Fields{
		"saga_id":             saga.ID,
		"step_name":           step.StepName,
		"compensation_action": compensationAction,
	}).Info("Step compensation initiated")

	return nil
}

// IsCompensationRequired checks if a step requires compensation
func (s *DefaultCompensationService) IsCompensationRequired(step *models.SagaStep) bool {
	// Only compensate completed steps
	if step.Status != models.StepStatusCompleted {
		return false
	}

	// Check if step has compensation data or if it's a compensatable action
	compensatableActions := map[string]bool{
		"inventory.reserve": true,
		"payment.charge":    true,
		"payment.hold":      true,
		// notification steps typically don't need compensation
		"notification.send": false,
	}

	// Extract action from step name or use step name directly
	action := s.extractActionFromStepName(step.StepName)
	
	if required, exists := compensatableActions[action]; exists {
		return required
	}

	// Default: require compensation for most actions
	return true
}

// Helper methods

func (s *DefaultCompensationService) getCompletedStepsForCompensation(saga *models.SagaInstance) ([]*models.SagaStep, error) {
	// This would typically query the repository, but for now we'll return empty
	// In a real implementation, this would get steps from the saga repository
	return []*models.SagaStep{}, nil
}

func (s *DefaultCompensationService) getCompensationAction(sagaType, stepName string) string {
	compensationMap := map[string]map[string]string{
		"order-processing": {
			"reserve-inventory": "inventory.release",
			"process-payment":   "payment.refund",
			"send-confirmation": "notification.cancel",
		},
		"payment-refund": {
			"process-refund":            "payment.reverse-refund",
			"restore-inventory":         "inventory.reserve",
			"send-refund-notification": "notification.cancel",
		},
	}

	if sagaMap, exists := compensationMap[sagaType]; exists {
		if action, exists := sagaMap[stepName]; exists {
			return action
		}
	}

	return ""
}

func (s *DefaultCompensationService) addSagaSpecificCompensationData(saga *models.SagaInstance, step *models.SagaStep, data map[string]interface{}) error {
	switch saga.SagaType {
	case "order-processing":
		return s.addOrderProcessingCompensationData(saga, step, data)
	case "payment-refund":
		return s.addPaymentRefundCompensationData(saga, step, data)
	default:
		return nil
	}
}

func (s *DefaultCompensationService) addOrderProcessingCompensationData(saga *models.SagaInstance, step *models.SagaStep, data map[string]interface{}) error {
	// Parse saga data to extract order information
	var orderData models.OrderSagaData
	if err := json.Unmarshal(saga.SagaData, &orderData); err != nil {
		return fmt.Errorf("failed to unmarshal order saga data: %w", err)
	}

	data["order_id"] = orderData.OrderID
	data["user_id"] = orderData.UserID

	switch step.StepName {
	case "reserve-inventory":
		data["items"] = orderData.Items
	case "process-payment":
		data["amount"] = orderData.TotalAmount
		data["currency"] = orderData.Currency
		data["payment_method"] = orderData.PaymentMethod
	case "send-confirmation":
		data["recipient"] = orderData.UserID // Assuming user ID is used for notifications
	}

	return nil
}

func (s *DefaultCompensationService) addPaymentRefundCompensationData(saga *models.SagaInstance, step *models.SagaStep, data map[string]interface{}) error {
	// Add refund-specific compensation data
	// This would extract refund information from saga data
	return nil
}

func (s *DefaultCompensationService) extractActionFromStepName(stepName string) string {
	actionMap := map[string]string{
		"reserve-inventory":         "inventory.reserve",
		"process-payment":           "payment.charge",
		"send-confirmation":         "notification.send",
		"process-refund":            "payment.refund",
		"restore-inventory":         "inventory.restore",
		"send-refund-notification": "notification.send-refund",
	}

	if action, exists := actionMap[stepName]; exists {
		return action
	}

	return stepName
}

func (s *DefaultCompensationService) publishCompensationEvent(ctx context.Context, event *models.SagaEvent) error {
	eventData, err := json.Marshal(event)
	if err != nil {
		return fmt.Errorf("failed to marshal compensation event: %w", err)
	}

	return s.eventService.PublishEvent(ctx, "saga-events", event.SagaID.String(), eventData)
}

func (s *DefaultCompensationService) markCompensationCompleted(ctx context.Context, saga *models.SagaInstance) error {
	// Create compensation completed event
	compensationEvent := &models.SagaEvent{
		ID:            uuid.New(),
		SagaID:        saga.ID,
		EventType:     "saga.compensation.completed",
		EventData:     saga.SagaData,
		Timestamp:     time.Now(),
		CorrelationID: stringValue(saga.CorrelationID),
		CausationID:   saga.ID.String(),
	}

	// Publish compensation completed event
	if err := s.publishCompensationEvent(ctx, compensationEvent); err != nil {
		s.logger.WithError(err).Error("Failed to publish compensation completed event")
	}

	s.logger.WithField("saga_id", saga.ID).Info("Saga compensation completed")

	return nil
}

// Helper functions
func stringValue(s *string) string {
	if s == nil {
		return ""
	}
	return *s
}

func mustMarshal(v interface{}) json.RawMessage {
	data, err := json.Marshal(v)
	if err != nil {
		panic(fmt.Sprintf("failed to marshal: %v", err))
	}
	return data
}

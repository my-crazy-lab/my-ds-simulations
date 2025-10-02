package orchestrator

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"github.com/google/uuid"
	"github.com/microservices-saga/services/saga-orchestrator/internal/models"
	"go.opentelemetry.io/otel/attribute"
)

// StartOutboxProcessor starts the outbox event processing loop
func (o *SagaOrchestrator) StartOutboxProcessor(ctx context.Context) {
	ticker := time.NewTicker(2 * time.Second)
	defer ticker.Stop()

	o.logger.Info("Starting outbox processor")

	for {
		select {
		case <-ctx.Done():
			o.logger.Info("Outbox processor stopped")
			return
		case <-ticker.C:
			if err := o.processOutboxEvents(ctx); err != nil {
				o.logger.WithError(err).Error("Error processing outbox events")
			}
		}
	}
}

// processOutboxEvents processes pending outbox events
func (o *SagaOrchestrator) processOutboxEvents(ctx context.Context) error {
	ctx, span := tracer.Start(ctx, "orchestrator.processOutboxEvents")
	defer span.End()

	// Get pending outbox events
	events, err := o.outboxRepo.GetPendingEvents(ctx, 100)
	if err != nil {
		span.RecordError(err)
		return fmt.Errorf("failed to get pending outbox events: %w", err)
	}

	if len(events) == 0 {
		return nil
	}

	span.SetAttributes(attribute.Int("events.count", len(events)))

	for _, event := range events {
		if err := o.processOutboxEvent(ctx, event); err != nil {
			o.logger.WithError(err).WithField("event_id", event.ID).Error("Failed to process outbox event")
			continue
		}
	}

	return nil
}

// processOutboxEvent processes a single outbox event
func (o *SagaOrchestrator) processOutboxEvent(ctx context.Context, event *models.OutboxEvent) error {
	ctx, span := tracer.Start(ctx, "orchestrator.processOutboxEvent")
	defer span.End()

	span.SetAttributes(
		attribute.String("event.id", event.ID.String()),
		attribute.String("event.type", event.EventType),
		attribute.String("aggregate.id", event.AggregateID),
		attribute.String("aggregate.type", event.AggregateType),
	)

	// Check if event has exceeded max retries
	if event.RetryCount >= 5 {
		return o.markEventAsFailed(ctx, event, "max retries exceeded")
	}

	// Determine topic based on event type
	topic := o.getTopicForEvent(event)
	if topic == "" {
		return o.markEventAsFailed(ctx, event, "unknown event type")
	}

	// Publish event to Kafka
	key := event.AggregateID
	if event.CorrelationID != nil {
		key = *event.CorrelationID
	}

	if err := o.eventService.PublishEvent(ctx, topic, key, event.EventData); err != nil {
		// Increment retry count and schedule for retry
		event.RetryCount++
		if err := o.outboxRepo.UpdateEvent(ctx, event); err != nil {
			o.logger.WithError(err).Error("Failed to update outbox event retry count")
		}
		
		span.RecordError(err)
		return fmt.Errorf("failed to publish event: %w", err)
	}

	// Mark event as processed
	event.Status = "PROCESSED"
	event.ProcessedAt = timePtr(time.Now())

	if err := o.outboxRepo.UpdateEvent(ctx, event); err != nil {
		span.RecordError(err)
		return fmt.Errorf("failed to mark event as processed: %w", err)
	}

	// Update metrics
	o.metrics.OutboxEventsProcessed.WithLabelValues(event.EventType).Inc()

	o.logger.WithFields(map[string]interface{}{
		"event_id":       event.ID,
		"event_type":     event.EventType,
		"aggregate_id":   event.AggregateID,
		"aggregate_type": event.AggregateType,
	}).Debug("Outbox event processed successfully")

	return nil
}

// markEventAsFailed marks an outbox event as failed
func (o *SagaOrchestrator) markEventAsFailed(ctx context.Context, event *models.OutboxEvent, reason string) error {
	event.Status = "FAILED"
	event.ProcessedAt = timePtr(time.Now())

	if err := o.outboxRepo.UpdateEvent(ctx, event); err != nil {
		return fmt.Errorf("failed to mark event as failed: %w", err)
	}

	// Update metrics
	o.metrics.OutboxEventsFailed.WithLabelValues(event.EventType).Inc()

	o.logger.WithFields(map[string]interface{}{
		"event_id":   event.ID,
		"event_type": event.EventType,
		"reason":     reason,
	}).Error("Outbox event marked as failed")

	return nil
}

// getTopicForEvent determines the Kafka topic for an outbox event
func (o *SagaOrchestrator) getTopicForEvent(event *models.OutboxEvent) string {
	switch event.AggregateType {
	case "saga":
		return "saga-events"
	case "inventory":
		return "inventory-events"
	case "payment":
		return "payment-events"
	case "notification":
		return "notification-events"
	default:
		// Try to infer from event type
		switch {
		case contains(event.EventType, "inventory"):
			return "inventory-events"
		case contains(event.EventType, "payment"):
			return "payment-events"
		case contains(event.EventType, "notification"):
			return "notification-events"
		case contains(event.EventType, "saga"):
			return "saga-events"
		default:
			return ""
		}
	}
}

// CreateOutboxEvent creates a new outbox event
func (o *SagaOrchestrator) CreateOutboxEvent(ctx context.Context, aggregateID, aggregateType, eventType string, eventData interface{}, correlationID, causationID *string) error {
	ctx, span := tracer.Start(ctx, "orchestrator.CreateOutboxEvent")
	defer span.End()

	span.SetAttributes(
		attribute.String("aggregate.id", aggregateID),
		attribute.String("aggregate.type", aggregateType),
		attribute.String("event.type", eventType),
	)

	data, err := json.Marshal(eventData)
	if err != nil {
		span.RecordError(err)
		return fmt.Errorf("failed to marshal event data: %w", err)
	}

	event := &models.OutboxEvent{
		ID:            uuid.New(),
		AggregateID:   aggregateID,
		AggregateType: aggregateType,
		EventType:     eventType,
		EventData:     data,
		CreatedAt:     time.Now(),
		Status:        "PENDING",
		RetryCount:    0,
		CorrelationID: correlationID,
		CausationID:   causationID,
		Version:       1,
	}

	if err := o.outboxRepo.CreateEvent(ctx, event); err != nil {
		span.RecordError(err)
		return fmt.Errorf("failed to create outbox event: %w", err)
	}

	// Update metrics
	o.metrics.OutboxEventsCreated.WithLabelValues(eventType).Inc()

	o.logger.WithFields(map[string]interface{}{
		"event_id":       event.ID,
		"event_type":     eventType,
		"aggregate_id":   aggregateID,
		"aggregate_type": aggregateType,
	}).Debug("Outbox event created")

	return nil
}

// CleanupProcessedEvents removes old processed events from the outbox
func (o *SagaOrchestrator) CleanupProcessedEvents(ctx context.Context) error {
	ctx, span := tracer.Start(ctx, "orchestrator.CleanupProcessedEvents")
	defer span.End()

	// Delete events older than 7 days
	cutoff := time.Now().AddDate(0, 0, -7)
	
	count, err := o.outboxRepo.DeleteProcessedEventsBefore(ctx, cutoff)
	if err != nil {
		span.RecordError(err)
		return fmt.Errorf("failed to cleanup processed events: %w", err)
	}

	if count > 0 {
		span.SetAttributes(attribute.Int("deleted.count", int(count)))
		o.logger.WithField("deleted_count", count).Info("Cleaned up processed outbox events")
	}

	return nil
}

// StartCleanupWorker starts a background worker to cleanup old outbox events
func (o *SagaOrchestrator) StartCleanupWorker(ctx context.Context) {
	ticker := time.NewTicker(1 * time.Hour)
	defer ticker.Stop()

	o.logger.Info("Starting outbox cleanup worker")

	for {
		select {
		case <-ctx.Done():
			o.logger.Info("Outbox cleanup worker stopped")
			return
		case <-ticker.C:
			if err := o.CleanupProcessedEvents(ctx); err != nil {
				o.logger.WithError(err).Error("Error cleaning up processed events")
			}
		}
	}
}

// GetOutboxMetrics returns outbox processing metrics
func (o *SagaOrchestrator) GetOutboxMetrics(ctx context.Context) (map[string]interface{}, error) {
	ctx, span := tracer.Start(ctx, "orchestrator.GetOutboxMetrics")
	defer span.End()

	pending, err := o.outboxRepo.CountEventsByStatus(ctx, "PENDING")
	if err != nil {
		span.RecordError(err)
		return nil, fmt.Errorf("failed to count pending events: %w", err)
	}

	processed, err := o.outboxRepo.CountEventsByStatus(ctx, "PROCESSED")
	if err != nil {
		span.RecordError(err)
		return nil, fmt.Errorf("failed to count processed events: %w", err)
	}

	failed, err := o.outboxRepo.CountEventsByStatus(ctx, "FAILED")
	if err != nil {
		span.RecordError(err)
		return nil, fmt.Errorf("failed to count failed events: %w", err)
	}

	metrics := map[string]interface{}{
		"pending_events":   pending,
		"processed_events": processed,
		"failed_events":    failed,
		"total_events":     pending + processed + failed,
	}

	return metrics, nil
}

// Helper function
func contains(s, substr string) bool {
	return len(s) >= len(substr) && (s == substr || 
		(len(s) > len(substr) && (s[:len(substr)] == substr || s[len(s)-len(substr):] == substr)))
}

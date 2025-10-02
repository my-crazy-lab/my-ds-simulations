package services

import (
	"context"
	"fmt"

	"github.com/microservices-saga/services/saga-orchestrator/internal/infrastructure"
	"github.com/sirupsen/logrus"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
)

var tracer = otel.Tracer("saga-orchestrator-services")

// EventService handles event publishing and consumption
type EventService interface {
	PublishEvent(ctx context.Context, topic, key string, data []byte) error
	PublishEventWithHeaders(ctx context.Context, topic, key string, data []byte, headers map[string]string) error
}

// KafkaEventService implements EventService using Kafka
type KafkaEventService struct {
	producer *infrastructure.KafkaProducer
	logger   *logrus.Logger
}

// NewEventService creates a new Kafka event service
func NewEventService(producer *infrastructure.KafkaProducer, logger *logrus.Logger) EventService {
	return &KafkaEventService{
		producer: producer,
		logger:   logger,
	}
}

// PublishEvent publishes an event to a Kafka topic
func (s *KafkaEventService) PublishEvent(ctx context.Context, topic, key string, data []byte) error {
	return s.PublishEventWithHeaders(ctx, topic, key, data, nil)
}

// PublishEventWithHeaders publishes an event to a Kafka topic with headers
func (s *KafkaEventService) PublishEventWithHeaders(ctx context.Context, topic, key string, data []byte, headers map[string]string) error {
	ctx, span := tracer.Start(ctx, "event_service.PublishEvent")
	defer span.End()

	span.SetAttributes(
		attribute.String("kafka.topic", topic),
		attribute.String("kafka.key", key),
		attribute.Int("data.size", len(data)),
	)

	if headers != nil {
		for k, v := range headers {
			span.SetAttributes(attribute.String(fmt.Sprintf("kafka.header.%s", k), v))
		}
	}

	err := s.producer.Produce(ctx, topic, key, data, headers)
	if err != nil {
		span.RecordError(err)
		s.logger.WithError(err).WithFields(logrus.Fields{
			"topic": topic,
			"key":   key,
		}).Error("Failed to publish event")
		return fmt.Errorf("failed to publish event to topic %s: %w", topic, err)
	}

	s.logger.WithFields(logrus.Fields{
		"topic":     topic,
		"key":       key,
		"data_size": len(data),
	}).Debug("Event published successfully")

	return nil
}

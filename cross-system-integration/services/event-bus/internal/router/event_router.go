package router

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
	"time"

	"github.com/go-redis/redis/v8"
	"github.com/segmentio/kafka-go"
	"github.com/sirupsen/logrus"
	"github.com/cross-system-integration/shared/events"
)

// RoutingRule defines how events should be routed
type RoutingRule struct {
	ID          string              `json:"id"`
	Name        string              `json:"name"`
	Description string              `json:"description"`
	Filter      events.EventFilter  `json:"filter"`
	Destinations []Destination      `json:"destinations"`
	Transform   *TransformRule      `json:"transform,omitempty"`
	Enabled     bool                `json:"enabled"`
	CreatedAt   time.Time           `json:"created_at"`
	UpdatedAt   time.Time           `json:"updated_at"`
}

// Destination represents an event destination
type Destination struct {
	Type       DestinationType       `json:"type"`
	Config     map[string]interface{} `json:"config"`
	Enabled    bool                   `json:"enabled"`
	RetryPolicy *RetryPolicy          `json:"retry_policy,omitempty"`
}

// DestinationType represents the type of destination
type DestinationType string

const (
	DestinationKafka     DestinationType = "kafka"
	DestinationHTTP      DestinationType = "http"
	DestinationWebhook   DestinationType = "webhook"
	DestinationDatabase  DestinationType = "database"
	DestinationRedis     DestinationType = "redis"
)

// TransformRule defines event transformation rules
type TransformRule struct {
	AddFields    map[string]interface{} `json:"add_fields,omitempty"`
	RemoveFields []string               `json:"remove_fields,omitempty"`
	RenameFields map[string]string      `json:"rename_fields,omitempty"`
	Script       string                 `json:"script,omitempty"` // JavaScript transformation script
}

// RetryPolicy defines retry behavior for failed deliveries
type RetryPolicy struct {
	MaxRetries    int           `json:"max_retries"`
	InitialDelay  time.Duration `json:"initial_delay"`
	MaxDelay      time.Duration `json:"max_delay"`
	BackoffFactor float64       `json:"backoff_factor"`
}

// EventRouter handles event routing logic
type EventRouter struct {
	kafkaWriter *kafka.Writer
	redisClient *redis.Client
	logger      *logrus.Logger
	rules       map[string]*RoutingRule
}

// NewEventRouter creates a new event router
func NewEventRouter(kafkaWriter *kafka.Writer, redisClient *redis.Client, logger *logrus.Logger) *EventRouter {
	return &EventRouter{
		kafkaWriter: kafkaWriter,
		redisClient: redisClient,
		logger:      logger,
		rules:       make(map[string]*RoutingRule),
	}
}

// RouteEvent routes an event based on configured rules
func (er *EventRouter) RouteEvent(ctx context.Context, event *events.UnifiedEvent) error {
	er.logger.WithFields(logrus.Fields{
		"event_id":   event.ID,
		"event_type": event.Type,
		"source":     event.Source,
	}).Debug("Routing event")

	// Load routing rules if not cached
	if len(er.rules) == 0 {
		if err := er.loadRoutingRules(ctx); err != nil {
			return fmt.Errorf("failed to load routing rules: %w", err)
		}
	}

	// Find matching rules
	matchingRules := er.findMatchingRules(event)
	if len(matchingRules) == 0 {
		er.logger.WithFields(logrus.Fields{
			"event_id":   event.ID,
			"event_type": event.Type,
		}).Warn("No routing rules matched event")
		return nil
	}

	// Route to all matching destinations
	for _, rule := range matchingRules {
		if err := er.routeToRule(ctx, event, rule); err != nil {
			er.logger.WithFields(logrus.Fields{
				"event_id": event.ID,
				"rule_id":  rule.ID,
				"error":    err,
			}).Error("Failed to route event to rule")
			// Continue with other rules even if one fails
		}
	}

	return nil
}

// findMatchingRules finds all rules that match the given event
func (er *EventRouter) findMatchingRules(event *events.UnifiedEvent) []*RoutingRule {
	var matchingRules []*RoutingRule

	for _, rule := range er.rules {
		if rule.Enabled && rule.Filter.Matches(event) {
			matchingRules = append(matchingRules, rule)
		}
	}

	return matchingRules
}

// routeToRule routes an event to all destinations in a rule
func (er *EventRouter) routeToRule(ctx context.Context, event *events.UnifiedEvent, rule *RoutingRule) error {
	// Apply transformation if specified
	transformedEvent := event
	if rule.Transform != nil {
		var err error
		transformedEvent, err = er.applyTransformation(event, rule.Transform)
		if err != nil {
			return fmt.Errorf("failed to apply transformation: %w", err)
		}
	}

	// Route to all destinations
	for _, destination := range rule.Destinations {
		if destination.Enabled {
			if err := er.routeToDestination(ctx, transformedEvent, &destination); err != nil {
				er.logger.WithFields(logrus.Fields{
					"event_id":        event.ID,
					"rule_id":         rule.ID,
					"destination_type": destination.Type,
					"error":           err,
				}).Error("Failed to route to destination")
				// Continue with other destinations
			}
		}
	}

	return nil
}

// routeToDestination routes an event to a specific destination
func (er *EventRouter) routeToDestination(ctx context.Context, event *events.UnifiedEvent, destination *Destination) error {
	switch destination.Type {
	case DestinationKafka:
		return er.routeToKafka(ctx, event, destination)
	case DestinationHTTP:
		return er.routeToHTTP(ctx, event, destination)
	case DestinationWebhook:
		return er.routeToWebhook(ctx, event, destination)
	case DestinationDatabase:
		return er.routeToDatabase(ctx, event, destination)
	case DestinationRedis:
		return er.routeToRedis(ctx, event, destination)
	default:
		return fmt.Errorf("unsupported destination type: %s", destination.Type)
	}
}

// routeToKafka routes an event to a Kafka topic
func (er *EventRouter) routeToKafka(ctx context.Context, event *events.UnifiedEvent, destination *Destination) error {
	topic, ok := destination.Config["topic"].(string)
	if !ok {
		return fmt.Errorf("kafka destination missing topic configuration")
	}

	// Serialize event
	eventData, err := event.ToJSON()
	if err != nil {
		return fmt.Errorf("failed to serialize event: %w", err)
	}

	// Create Kafka message
	message := kafka.Message{
		Topic:     topic,
		Key:       []byte(event.ID),
		Value:     eventData,
		Time:      event.Timestamp,
		Headers: []kafka.Header{
			{Key: "event-type", Value: []byte(event.Type)},
			{Key: "event-source", Value: []byte(event.Source)},
			{Key: "correlation-id", Value: []byte(event.CorrelationID)},
		},
	}

	// Add partition key if specified
	if partitionKey, ok := destination.Config["partition_key"].(string); ok {
		if value, exists := event.GetDataField(partitionKey); exists {
			if strValue, ok := value.(string); ok {
				message.Key = []byte(strValue)
			}
		}
	}

	// Write to Kafka
	return er.kafkaWriter.WriteMessages(ctx, message)
}

// routeToHTTP routes an event to an HTTP endpoint
func (er *EventRouter) routeToHTTP(ctx context.Context, event *events.UnifiedEvent, destination *Destination) error {
	// Implementation for HTTP routing
	// This would use an HTTP client to POST the event to the specified endpoint
	return fmt.Errorf("HTTP routing not implemented yet")
}

// routeToWebhook routes an event to a webhook
func (er *EventRouter) routeToWebhook(ctx context.Context, event *events.UnifiedEvent, destination *Destination) error {
	// Implementation for webhook routing
	// Similar to HTTP but with webhook-specific headers and retry logic
	return fmt.Errorf("webhook routing not implemented yet")
}

// routeToDatabase routes an event to a database
func (er *EventRouter) routeToDatabase(ctx context.Context, event *events.UnifiedEvent, destination *Destination) error {
	// Implementation for database routing
	// This would insert the event into a specified database table
	return fmt.Errorf("database routing not implemented yet")
}

// routeToRedis routes an event to Redis
func (er *EventRouter) routeToRedis(ctx context.Context, event *events.UnifiedEvent, destination *Destination) error {
	key, ok := destination.Config["key"].(string)
	if !ok {
		return fmt.Errorf("redis destination missing key configuration")
	}

	// Replace placeholders in key
	key = er.replacePlaceholders(key, event)

	// Serialize event
	eventData, err := event.ToJSON()
	if err != nil {
		return fmt.Errorf("failed to serialize event: %w", err)
	}

	// Determine Redis operation
	operation, ok := destination.Config["operation"].(string)
	if !ok {
		operation = "set" // default operation
	}

	switch operation {
	case "set":
		ttl := time.Duration(0)
		if ttlSeconds, ok := destination.Config["ttl"].(float64); ok {
			ttl = time.Duration(ttlSeconds) * time.Second
		}
		return er.redisClient.Set(ctx, key, eventData, ttl).Err()
	case "lpush":
		return er.redisClient.LPush(ctx, key, eventData).Err()
	case "rpush":
		return er.redisClient.RPush(ctx, key, eventData).Err()
	case "publish":
		return er.redisClient.Publish(ctx, key, eventData).Err()
	default:
		return fmt.Errorf("unsupported Redis operation: %s", operation)
	}
}

// applyTransformation applies transformation rules to an event
func (er *EventRouter) applyTransformation(event *events.UnifiedEvent, transform *TransformRule) (*events.UnifiedEvent, error) {
	// Clone the event to avoid modifying the original
	transformedEvent := event.Clone()

	// Add fields
	for key, value := range transform.AddFields {
		transformedEvent.Data[key] = value
	}

	// Remove fields
	for _, key := range transform.RemoveFields {
		delete(transformedEvent.Data, key)
	}

	// Rename fields
	for oldKey, newKey := range transform.RenameFields {
		if value, exists := transformedEvent.Data[oldKey]; exists {
			transformedEvent.Data[newKey] = value
			delete(transformedEvent.Data, oldKey)
		}
	}

	// Apply script transformation (if specified)
	if transform.Script != "" {
		// This would execute a JavaScript transformation script
		// For now, we'll skip this implementation
		er.logger.Warn("Script transformation not implemented yet")
	}

	return transformedEvent, nil
}

// replacePlaceholders replaces placeholders in a string with event data
func (er *EventRouter) replacePlaceholders(template string, event *events.UnifiedEvent) string {
	result := template

	// Replace common placeholders
	result = strings.ReplaceAll(result, "{event.id}", event.ID)
	result = strings.ReplaceAll(result, "{event.type}", string(event.Type))
	result = strings.ReplaceAll(result, "{event.source}", string(event.Source))
	result = strings.ReplaceAll(result, "{event.correlation_id}", event.CorrelationID)

	// Replace data field placeholders
	for key, value := range event.Data {
		placeholder := fmt.Sprintf("{event.data.%s}", key)
		if strValue, ok := value.(string); ok {
			result = strings.ReplaceAll(result, placeholder, strValue)
		}
	}

	return result
}

// loadRoutingRules loads routing rules from Redis
func (er *EventRouter) loadRoutingRules(ctx context.Context) error {
	// Get all routing rule keys
	keys, err := er.redisClient.Keys(ctx, "routing:rule:*").Result()
	if err != nil {
		return fmt.Errorf("failed to get routing rule keys: %w", err)
	}

	// Load each rule
	for _, key := range keys {
		ruleData, err := er.redisClient.Get(ctx, key).Result()
		if err != nil {
			er.logger.WithFields(logrus.Fields{
				"key":   key,
				"error": err,
			}).Warn("Failed to load routing rule")
			continue
		}

		var rule RoutingRule
		if err := json.Unmarshal([]byte(ruleData), &rule); err != nil {
			er.logger.WithFields(logrus.Fields{
				"key":   key,
				"error": err,
			}).Warn("Failed to unmarshal routing rule")
			continue
		}

		er.rules[rule.ID] = &rule
	}

	er.logger.WithField("count", len(er.rules)).Info("Loaded routing rules")
	return nil
}

// AddRoutingRule adds a new routing rule
func (er *EventRouter) AddRoutingRule(ctx context.Context, rule *RoutingRule) error {
	rule.CreatedAt = time.Now()
	rule.UpdatedAt = time.Now()

	// Serialize rule
	ruleData, err := json.Marshal(rule)
	if err != nil {
		return fmt.Errorf("failed to serialize routing rule: %w", err)
	}

	// Store in Redis
	key := fmt.Sprintf("routing:rule:%s", rule.ID)
	if err := er.redisClient.Set(ctx, key, ruleData, 0).Err(); err != nil {
		return fmt.Errorf("failed to store routing rule: %w", err)
	}

	// Update local cache
	er.rules[rule.ID] = rule

	return nil
}

// UpdateRoutingRule updates an existing routing rule
func (er *EventRouter) UpdateRoutingRule(ctx context.Context, rule *RoutingRule) error {
	rule.UpdatedAt = time.Now()

	// Serialize rule
	ruleData, err := json.Marshal(rule)
	if err != nil {
		return fmt.Errorf("failed to serialize routing rule: %w", err)
	}

	// Store in Redis
	key := fmt.Sprintf("routing:rule:%s", rule.ID)
	if err := er.redisClient.Set(ctx, key, ruleData, 0).Err(); err != nil {
		return fmt.Errorf("failed to store routing rule: %w", err)
	}

	// Update local cache
	er.rules[rule.ID] = rule

	return nil
}

// DeleteRoutingRule deletes a routing rule
func (er *EventRouter) DeleteRoutingRule(ctx context.Context, ruleID string) error {
	// Delete from Redis
	key := fmt.Sprintf("routing:rule:%s", ruleID)
	if err := er.redisClient.Del(ctx, key).Err(); err != nil {
		return fmt.Errorf("failed to delete routing rule: %w", err)
	}

	// Remove from local cache
	delete(er.rules, ruleID)

	return nil
}

// GetRoutingRules returns all routing rules
func (er *EventRouter) GetRoutingRules() map[string]*RoutingRule {
	return er.rules
}

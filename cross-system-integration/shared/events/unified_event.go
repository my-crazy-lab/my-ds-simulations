package events

import (
	"encoding/json"
	"fmt"
	"time"

	"github.com/google/uuid"
)

// EventType represents the type of event
type EventType string

const (
	// Microservices events
	EventTypeSagaStarted    EventType = "saga.started"
	EventTypeSagaCompleted  EventType = "saga.completed"
	EventTypeSagaFailed     EventType = "saga.failed"
	EventTypeInventoryReserved EventType = "inventory.reserved"
	EventTypePaymentProcessed  EventType = "payment.processed"
	
	// Analytics events
	EventTypeDataIngested   EventType = "data.ingested"
	EventTypeMetricComputed EventType = "metric.computed"
	EventTypeAnomalyDetected EventType = "anomaly.detected"
	
	// AI/ML events
	EventTypeModelTrained   EventType = "model.trained"
	EventTypeDriftDetected  EventType = "drift.detected"
	EventTypeRAGIndexed     EventType = "rag.indexed"
	EventTypePredictionMade EventType = "prediction.made"
	
	// Cross-system events
	EventTypeSystemHealthChanged EventType = "system.health_changed"
	EventTypeOptimizationApplied EventType = "optimization.applied"
	EventTypeChatOpsCommand      EventType = "chatops.command"
)

// EventSource represents the source system
type EventSource string

const (
	SourceMicroservices EventSource = "microservices"
	SourceAnalytics     EventSource = "analytics"
	SourceAIML          EventSource = "ai-ml"
	SourceCrossSystem   EventSource = "cross-system"
)

// EventPriority represents event processing priority
type EventPriority string

const (
	PriorityLow      EventPriority = "low"
	PriorityNormal   EventPriority = "normal"
	PriorityHigh     EventPriority = "high"
	PriorityCritical EventPriority = "critical"
)

// MLContext contains ML-specific context for events
type MLContext struct {
	ModelVersion    string                 `json:"model_version,omitempty"`
	FeatureVector   []float64              `json:"feature_vector,omitempty"`
	PredictionScore float64                `json:"prediction_score,omitempty"`
	Confidence      float64                `json:"confidence,omitempty"`
	Metadata        map[string]interface{} `json:"metadata,omitempty"`
}

// EventMetadata contains additional event metadata
type EventMetadata struct {
	Version     string                 `json:"version"`
	Priority    EventPriority          `json:"priority"`
	Tags        []string               `json:"tags,omitempty"`
	TTL         *time.Duration         `json:"ttl,omitempty"`
	RetryCount  int                    `json:"retry_count,omitempty"`
	MaxRetries  int                    `json:"max_retries,omitempty"`
	Properties  map[string]interface{} `json:"properties,omitempty"`
}

// UnifiedEvent represents a standardized event across all systems
type UnifiedEvent struct {
	ID            string                 `json:"id"`
	Type          EventType              `json:"type"`
	Source        EventSource            `json:"source"`
	Timestamp     time.Time              `json:"timestamp"`
	CorrelationID string                 `json:"correlation_id"`
	CausationID   string                 `json:"causation_id,omitempty"`
	Data          map[string]interface{} `json:"data"`
	Metadata      EventMetadata          `json:"metadata"`
	MLContext     *MLContext             `json:"ml_context,omitempty"`
}

// NewUnifiedEvent creates a new unified event
func NewUnifiedEvent(eventType EventType, source EventSource, data map[string]interface{}) *UnifiedEvent {
	return &UnifiedEvent{
		ID:            uuid.New().String(),
		Type:          eventType,
		Source:        source,
		Timestamp:     time.Now(),
		CorrelationID: uuid.New().String(),
		Data:          data,
		Metadata: EventMetadata{
			Version:  "1.0",
			Priority: PriorityNormal,
		},
	}
}

// WithCorrelationID sets the correlation ID
func (e *UnifiedEvent) WithCorrelationID(correlationID string) *UnifiedEvent {
	e.CorrelationID = correlationID
	return e
}

// WithCausationID sets the causation ID
func (e *UnifiedEvent) WithCausationID(causationID string) *UnifiedEvent {
	e.CausationID = causationID
	return e
}

// WithPriority sets the event priority
func (e *UnifiedEvent) WithPriority(priority EventPriority) *UnifiedEvent {
	e.Metadata.Priority = priority
	return e
}

// WithTags adds tags to the event
func (e *UnifiedEvent) WithTags(tags ...string) *UnifiedEvent {
	e.Metadata.Tags = append(e.Metadata.Tags, tags...)
	return e
}

// WithTTL sets the time-to-live for the event
func (e *UnifiedEvent) WithTTL(ttl time.Duration) *UnifiedEvent {
	e.Metadata.TTL = &ttl
	return e
}

// WithMLContext adds ML context to the event
func (e *UnifiedEvent) WithMLContext(mlContext *MLContext) *UnifiedEvent {
	e.MLContext = mlContext
	return e
}

// WithProperty adds a custom property
func (e *UnifiedEvent) WithProperty(key string, value interface{}) *UnifiedEvent {
	if e.Metadata.Properties == nil {
		e.Metadata.Properties = make(map[string]interface{})
	}
	e.Metadata.Properties[key] = value
	return e
}

// IsExpired checks if the event has expired based on TTL
func (e *UnifiedEvent) IsExpired() bool {
	if e.Metadata.TTL == nil {
		return false
	}
	return time.Since(e.Timestamp) > *e.Metadata.TTL
}

// ShouldRetry checks if the event should be retried
func (e *UnifiedEvent) ShouldRetry() bool {
	return e.Metadata.RetryCount < e.Metadata.MaxRetries
}

// IncrementRetry increments the retry count
func (e *UnifiedEvent) IncrementRetry() {
	e.Metadata.RetryCount++
}

// ToJSON converts the event to JSON
func (e *UnifiedEvent) ToJSON() ([]byte, error) {
	return json.Marshal(e)
}

// FromJSON creates an event from JSON
func FromJSON(data []byte) (*UnifiedEvent, error) {
	var event UnifiedEvent
	if err := json.Unmarshal(data, &event); err != nil {
		return nil, fmt.Errorf("failed to unmarshal event: %w", err)
	}
	return &event, nil
}

// Validate validates the event structure
func (e *UnifiedEvent) Validate() error {
	if e.ID == "" {
		return fmt.Errorf("event ID is required")
	}
	if e.Type == "" {
		return fmt.Errorf("event type is required")
	}
	if e.Source == "" {
		return fmt.Errorf("event source is required")
	}
	if e.Timestamp.IsZero() {
		return fmt.Errorf("event timestamp is required")
	}
	if e.CorrelationID == "" {
		return fmt.Errorf("correlation ID is required")
	}
	if e.Data == nil {
		return fmt.Errorf("event data is required")
	}
	return nil
}

// Clone creates a deep copy of the event
func (e *UnifiedEvent) Clone() *UnifiedEvent {
	// Marshal and unmarshal for deep copy
	data, _ := json.Marshal(e)
	var clone UnifiedEvent
	json.Unmarshal(data, &clone)
	return &clone
}

// GetDataField safely gets a field from event data
func (e *UnifiedEvent) GetDataField(key string) (interface{}, bool) {
	value, exists := e.Data[key]
	return value, exists
}

// GetDataString gets a string field from event data
func (e *UnifiedEvent) GetDataString(key string) (string, bool) {
	if value, exists := e.Data[key]; exists {
		if str, ok := value.(string); ok {
			return str, true
		}
	}
	return "", false
}

// GetDataInt gets an int field from event data
func (e *UnifiedEvent) GetDataInt(key string) (int, bool) {
	if value, exists := e.Data[key]; exists {
		switch v := value.(type) {
		case int:
			return v, true
		case float64:
			return int(v), true
		}
	}
	return 0, false
}

// GetDataFloat gets a float field from event data
func (e *UnifiedEvent) GetDataFloat(key string) (float64, bool) {
	if value, exists := e.Data[key]; exists {
		switch v := value.(type) {
		case float64:
			return v, true
		case int:
			return float64(v), true
		}
	}
	return 0, false
}

// GetDataBool gets a boolean field from event data
func (e *UnifiedEvent) GetDataBool(key string) (bool, bool) {
	if value, exists := e.Data[key]; exists {
		if b, ok := value.(bool); ok {
			return b, true
		}
	}
	return false, false
}

// EventFilter represents a filter for events
type EventFilter struct {
	Types         []EventType   `json:"types,omitempty"`
	Sources       []EventSource `json:"sources,omitempty"`
	Tags          []string      `json:"tags,omitempty"`
	MinPriority   EventPriority `json:"min_priority,omitempty"`
	CorrelationID string        `json:"correlation_id,omitempty"`
	TimeRange     *TimeRange    `json:"time_range,omitempty"`
}

// TimeRange represents a time range filter
type TimeRange struct {
	Start time.Time `json:"start"`
	End   time.Time `json:"end"`
}

// Matches checks if an event matches the filter
func (f *EventFilter) Matches(event *UnifiedEvent) bool {
	// Check event types
	if len(f.Types) > 0 {
		found := false
		for _, t := range f.Types {
			if event.Type == t {
				found = true
				break
			}
		}
		if !found {
			return false
		}
	}

	// Check sources
	if len(f.Sources) > 0 {
		found := false
		for _, s := range f.Sources {
			if event.Source == s {
				found = true
				break
			}
		}
		if !found {
			return false
		}
	}

	// Check tags
	if len(f.Tags) > 0 {
		for _, filterTag := range f.Tags {
			found := false
			for _, eventTag := range event.Metadata.Tags {
				if eventTag == filterTag {
					found = true
					break
				}
			}
			if !found {
				return false
			}
		}
	}

	// Check priority
	if f.MinPriority != "" {
		if !isPriorityHigherOrEqual(event.Metadata.Priority, f.MinPriority) {
			return false
		}
	}

	// Check correlation ID
	if f.CorrelationID != "" && event.CorrelationID != f.CorrelationID {
		return false
	}

	// Check time range
	if f.TimeRange != nil {
		if event.Timestamp.Before(f.TimeRange.Start) || event.Timestamp.After(f.TimeRange.End) {
			return false
		}
	}

	return true
}

// isPriorityHigherOrEqual checks if priority1 is higher or equal to priority2
func isPriorityHigherOrEqual(priority1, priority2 EventPriority) bool {
	priorities := map[EventPriority]int{
		PriorityLow:      1,
		PriorityNormal:   2,
		PriorityHigh:     3,
		PriorityCritical: 4,
	}
	return priorities[priority1] >= priorities[priority2]
}

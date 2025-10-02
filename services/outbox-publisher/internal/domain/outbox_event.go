package domain

import (
	"encoding/json"
	"time"

	"github.com/google/uuid"
)

// OutboxEventStatus represents the status of an outbox event
type OutboxEventStatus string

const (
	OutboxEventStatusPending    OutboxEventStatus = "pending"
	OutboxEventStatusProcessing OutboxEventStatus = "processing"
	OutboxEventStatusProcessed  OutboxEventStatus = "processed"
	OutboxEventStatusFailed     OutboxEventStatus = "failed"
	OutboxEventStatusDeadLetter OutboxEventStatus = "dead_letter"
)

// OutboxEvent represents an event in the outbox pattern
type OutboxEvent struct {
	ID            string                 `json:"id" bson:"_id"`
	AggregateID   string                 `json:"aggregate_id" bson:"aggregate_id"`
	AggregateType string                 `json:"aggregate_type" bson:"aggregate_type"`
	EventType     string                 `json:"event_type" bson:"event_type"`
	EventData     json.RawMessage        `json:"event_data" bson:"event_data"`
	Metadata      map[string]interface{} `json:"metadata" bson:"metadata"`
	CreatedAt     time.Time              `json:"created_at" bson:"created_at"`
	ProcessedAt   *time.Time             `json:"processed_at,omitempty" bson:"processed_at,omitempty"`
	Status        OutboxEventStatus      `json:"status" bson:"status"`
	RetryCount    int                    `json:"retry_count" bson:"retry_count"`
	MaxRetries    int                    `json:"max_retries" bson:"max_retries"`
	NextRetryAt   *time.Time             `json:"next_retry_at,omitempty" bson:"next_retry_at,omitempty"`
	ErrorMessage  string                 `json:"error_message,omitempty" bson:"error_message,omitempty"`
	Topic         string                 `json:"topic" bson:"topic"`
	PartitionKey  string                 `json:"partition_key,omitempty" bson:"partition_key,omitempty"`
	Headers       map[string]string      `json:"headers,omitempty" bson:"headers,omitempty"`
	Source        string                 `json:"source" bson:"source"` // Which service/database this event came from
}

// NewOutboxEvent creates a new outbox event
func NewOutboxEvent(
	aggregateID, aggregateType, eventType string,
	eventData interface{},
	topic string,
	source string,
) (*OutboxEvent, error) {
	eventDataBytes, err := json.Marshal(eventData)
	if err != nil {
		return nil, err
	}

	return &OutboxEvent{
		ID:            uuid.New().String(),
		AggregateID:   aggregateID,
		AggregateType: aggregateType,
		EventType:     eventType,
		EventData:     eventDataBytes,
		Metadata:      make(map[string]interface{}),
		CreatedAt:     time.Now().UTC(),
		Status:        OutboxEventStatusPending,
		RetryCount:    0,
		MaxRetries:    5,
		Topic:         topic,
		Source:        source,
		Headers:       make(map[string]string),
	}, nil
}

// WithMetadata adds metadata to the event
func (e *OutboxEvent) WithMetadata(key string, value interface{}) *OutboxEvent {
	if e.Metadata == nil {
		e.Metadata = make(map[string]interface{})
	}
	e.Metadata[key] = value
	return e
}

// WithPartitionKey sets the partition key for Kafka
func (e *OutboxEvent) WithPartitionKey(key string) *OutboxEvent {
	e.PartitionKey = key
	return e
}

// WithHeader adds a header to the event
func (e *OutboxEvent) WithHeader(key, value string) *OutboxEvent {
	if e.Headers == nil {
		e.Headers = make(map[string]string)
	}
	e.Headers[key] = value
	return e
}

// WithMaxRetries sets the maximum number of retries
func (e *OutboxEvent) WithMaxRetries(maxRetries int) *OutboxEvent {
	e.MaxRetries = maxRetries
	return e
}

// MarkProcessing marks the event as being processed
func (e *OutboxEvent) MarkProcessing() {
	e.Status = OutboxEventStatusProcessing
}

// MarkProcessed marks the event as successfully processed
func (e *OutboxEvent) MarkProcessed() {
	e.Status = OutboxEventStatusProcessed
	now := time.Now().UTC()
	e.ProcessedAt = &now
	e.ErrorMessage = ""
}

// MarkFailed marks the event as failed and increments retry count
func (e *OutboxEvent) MarkFailed(errorMessage string) {
	e.RetryCount++
	e.ErrorMessage = errorMessage

	if e.RetryCount >= e.MaxRetries {
		e.Status = OutboxEventStatusDeadLetter
	} else {
		e.Status = OutboxEventStatusFailed
		// Exponential backoff: 2^retry_count minutes
		backoffMinutes := 1 << e.RetryCount
		nextRetry := time.Now().UTC().Add(time.Duration(backoffMinutes) * time.Minute)
		e.NextRetryAt = &nextRetry
	}
}

// CanRetry returns true if the event can be retried
func (e *OutboxEvent) CanRetry() bool {
	if e.Status != OutboxEventStatusFailed {
		return false
	}
	if e.NextRetryAt == nil {
		return true
	}
	return time.Now().UTC().After(*e.NextRetryAt)
}

// ResetForRetry resets the event for retry
func (e *OutboxEvent) ResetForRetry() {
	e.Status = OutboxEventStatusPending
	e.NextRetryAt = nil
}

// IsProcessed returns true if the event has been successfully processed
func (e *OutboxEvent) IsProcessed() bool {
	return e.Status == OutboxEventStatusProcessed
}

// IsFailed returns true if the event has failed
func (e *OutboxEvent) IsFailed() bool {
	return e.Status == OutboxEventStatusFailed
}

// IsDeadLetter returns true if the event is in dead letter status
func (e *OutboxEvent) IsDeadLetter() bool {
	return e.Status == OutboxEventStatusDeadLetter
}

// GetEventDataAs unmarshals the event data into the provided interface
func (e *OutboxEvent) GetEventDataAs(v interface{}) error {
	return json.Unmarshal(e.EventData, v)
}

// OutboxEventFilter represents filters for querying outbox events
type OutboxEventFilter struct {
	AggregateType *string
	EventType     *string
	Status        *OutboxEventStatus
	Source        *string
	CreatedAfter  *time.Time
	CreatedBefore *time.Time
	Limit         int
	Offset        int
}

// OutboxEventRepository defines the interface for outbox event persistence
type OutboxEventRepository interface {
	// Save saves an outbox event
	Save(event *OutboxEvent) error
	
	// Update updates an outbox event
	Update(event *OutboxEvent) error
	
	// GetByID retrieves an outbox event by ID
	GetByID(id string) (*OutboxEvent, error)
	
	// GetPendingEvents retrieves pending events for processing
	GetPendingEvents(limit int) ([]*OutboxEvent, error)
	
	// GetFailedEvents retrieves failed events that can be retried
	GetFailedEvents(limit int) ([]*OutboxEvent, error)
	
	// GetEventsByFilter retrieves events based on filter criteria
	GetEventsByFilter(filter OutboxEventFilter) ([]*OutboxEvent, error)
	
	// CountPendingEvents returns the count of pending events
	CountPendingEvents() (int64, error)
	
	// CountFailedEvents returns the count of failed events
	CountFailedEvents() (int64, error)
	
	// DeleteProcessedEvents deletes processed events older than the specified duration
	DeleteProcessedEvents(olderThan time.Duration) (int64, error)
	
	// GetEventsByAggregateID retrieves all events for a specific aggregate
	GetEventsByAggregateID(aggregateID string) ([]*OutboxEvent, error)
}

// OutboxEventPublisher defines the interface for publishing events
type OutboxEventPublisher interface {
	// Publish publishes an event to the message broker
	Publish(event *OutboxEvent) error
	
	// Close closes the publisher
	Close() error
}

// OutboxStats represents statistics about outbox events
type OutboxStats struct {
	TotalEvents     int64 `json:"total_events"`
	PendingEvents   int64 `json:"pending_events"`
	ProcessedEvents int64 `json:"processed_events"`
	FailedEvents    int64 `json:"failed_events"`
	DeadLetterEvents int64 `json:"dead_letter_events"`
	LastProcessedAt *time.Time `json:"last_processed_at,omitempty"`
}

// EventMetrics represents metrics for monitoring
type EventMetrics struct {
	EventsPublished   int64
	EventsFailed      int64
	EventsRetried     int64
	PublishLatency    time.Duration
	LastPublishedAt   time.Time
	LastFailedAt      time.Time
}

// Common event types
const (
	// Transaction events
	EventTypeTransactionCreated   = "TransactionCreated"
	EventTypeTransactionCommitted = "TransactionCommitted"
	EventTypeTransactionAborted   = "TransactionAborted"
	
	// Saga events
	EventTypeSagaCreated     = "SagaCreated"
	EventTypeSagaCompleted   = "SagaCompleted"
	EventTypeSagaCompensated = "SagaCompensated"
	EventTypeSagaStepCompleted = "SagaStepCompleted"
	EventTypeSagaStepFailed    = "SagaStepFailed"
	
	// Account events
	EventTypeAccountCreated      = "AccountCreated"
	EventTypeMoneyDeposited      = "MoneyDeposited"
	EventTypeMoneyWithdrawn      = "MoneyWithdrawn"
	EventTypeMoneyReserved       = "MoneyReserved"
	EventTypeReservationReleased = "ReservationReleased"
	EventTypeReservationConfirmed = "ReservationConfirmed"
	
	// Order events
	EventTypeOrderCreated   = "OrderCreated"
	EventTypeOrderCompleted = "OrderCompleted"
	EventTypeOrderCancelled = "OrderCancelled"
	
	// Payment events
	EventTypePaymentProcessed = "PaymentProcessed"
	EventTypePaymentFailed    = "PaymentFailed"
	EventTypePaymentRefunded  = "PaymentRefunded"
	
	// Billing events
	EventTypeBillingCreated     = "BillingCreated"
	EventTypeInvoiceGenerated   = "InvoiceGenerated"
	EventTypePaymentReceived    = "PaymentReceived"
)

// Common topics
const (
	TopicTransactionEvents = "transaction-events"
	TopicSagaEvents       = "saga-events"
	TopicAccountEvents    = "account-events"
	TopicOrderEvents      = "order-events"
	TopicPaymentEvents    = "payment-events"
	TopicBillingEvents    = "billing-events"
)

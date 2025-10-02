package models

import (
	"encoding/json"
	"time"

	"github.com/google/uuid"
)

// SagaStatus represents the status of a saga
type SagaStatus string

const (
	SagaStatusStarted     SagaStatus = "STARTED"
	SagaStatusInProgress  SagaStatus = "IN_PROGRESS"
	SagaStatusCompleted   SagaStatus = "COMPLETED"
	SagaStatusFailed      SagaStatus = "FAILED"
	SagaStatusCompensated SagaStatus = "COMPENSATED"
	SagaStatusCancelled   SagaStatus = "CANCELLED"
)

// StepStatus represents the status of a saga step
type StepStatus string

const (
	StepStatusPending     StepStatus = "PENDING"
	StepStatusInProgress  StepStatus = "IN_PROGRESS"
	StepStatusCompleted   StepStatus = "COMPLETED"
	StepStatusFailed      StepStatus = "FAILED"
	StepStatusCompensated StepStatus = "COMPENSATED"
	StepStatusSkipped     StepStatus = "SKIPPED"
)

// SagaInstance represents a saga instance in the database
type SagaInstance struct {
	ID             uuid.UUID       `json:"id" db:"id"`
	SagaType       string          `json:"saga_type" db:"saga_type"`
	SagaData       json.RawMessage `json:"saga_data" db:"saga_data"`
	Status         SagaStatus      `json:"status" db:"status"`
	CurrentStep    int             `json:"current_step" db:"current_step"`
	CreatedAt      time.Time       `json:"created_at" db:"created_at"`
	UpdatedAt      time.Time       `json:"updated_at" db:"updated_at"`
	CompletedAt    *time.Time      `json:"completed_at,omitempty" db:"completed_at"`
	ErrorMessage   *string         `json:"error_message,omitempty" db:"error_message"`
	RetryCount     int             `json:"retry_count" db:"retry_count"`
	MaxRetries     int             `json:"max_retries" db:"max_retries"`
	CorrelationID  *string         `json:"correlation_id,omitempty" db:"correlation_id"`
	IdempotencyKey *string         `json:"idempotency_key,omitempty" db:"idempotency_key"`
}

// SagaStep represents a step in a saga
type SagaStep struct {
	ID               uuid.UUID       `json:"id" db:"id"`
	SagaID           uuid.UUID       `json:"saga_id" db:"saga_id"`
	StepName         string          `json:"step_name" db:"step_name"`
	StepOrder        int             `json:"step_order" db:"step_order"`
	Status           StepStatus      `json:"status" db:"status"`
	InputData        json.RawMessage `json:"input_data,omitempty" db:"input_data"`
	OutputData       json.RawMessage `json:"output_data,omitempty" db:"output_data"`
	ErrorMessage     *string         `json:"error_message,omitempty" db:"error_message"`
	StartedAt        *time.Time      `json:"started_at,omitempty" db:"started_at"`
	CompletedAt      *time.Time      `json:"completed_at,omitempty" db:"completed_at"`
	RetryCount       int             `json:"retry_count" db:"retry_count"`
	CompensationData json.RawMessage `json:"compensation_data,omitempty" db:"compensation_data"`
}

// SagaDefinition defines the structure of a saga
type SagaDefinition struct {
	Type       string            `json:"type"`
	Steps      []StepDefinition  `json:"steps"`
	Timeout    time.Duration     `json:"timeout"`
	MaxRetries int               `json:"max_retries"`
	Metadata   map[string]string `json:"metadata,omitempty"`
}

// StepDefinition defines a step in a saga
type StepDefinition struct {
	Name               string            `json:"name"`
	Order              int               `json:"order"`
	Action             string            `json:"action"`
	CompensationAction string            `json:"compensation_action"`
	Timeout            time.Duration     `json:"timeout"`
	MaxRetries         int               `json:"max_retries"`
	RetryDelay         time.Duration     `json:"retry_delay"`
	ContinueOnFailure  bool              `json:"continue_on_failure"`
	Metadata           map[string]string `json:"metadata,omitempty"`
}

// OrderSagaData represents the data for an order saga
type OrderSagaData struct {
	OrderID         uuid.UUID   `json:"order_id"`
	UserID          uuid.UUID   `json:"user_id"`
	Items           []OrderItem `json:"items"`
	TotalAmount     float64     `json:"total_amount"`
	Currency        string      `json:"currency"`
	PaymentMethod   string      `json:"payment_method"`
	ShippingAddress Address     `json:"shipping_address"`
}

// OrderItem represents an item in an order
type OrderItem struct {
	SKU      string  `json:"sku"`
	Quantity int     `json:"quantity"`
	Price    float64 `json:"price"`
}

// Address represents a shipping address
type Address struct {
	Street     string `json:"street"`
	City       string `json:"city"`
	State      string `json:"state"`
	PostalCode string `json:"postal_code"`
	Country    string `json:"country"`
}

// SagaEvent represents an event in the saga
type SagaEvent struct {
	ID            uuid.UUID       `json:"id"`
	SagaID        uuid.UUID       `json:"saga_id"`
	EventType     string          `json:"event_type"`
	EventData     json.RawMessage `json:"event_data"`
	Timestamp     time.Time       `json:"timestamp"`
	CorrelationID string          `json:"correlation_id"`
	CausationID   string          `json:"causation_id"`
}

// OutboxEvent represents an event in the outbox
type OutboxEvent struct {
	ID            uuid.UUID       `json:"id" db:"id"`
	AggregateID   string          `json:"aggregate_id" db:"aggregate_id"`
	AggregateType string          `json:"aggregate_type" db:"aggregate_type"`
	EventType     string          `json:"event_type" db:"event_type"`
	EventData     json.RawMessage `json:"event_data" db:"event_data"`
	CreatedAt     time.Time       `json:"created_at" db:"created_at"`
	ProcessedAt   *time.Time      `json:"processed_at,omitempty" db:"processed_at"`
	Status        string          `json:"status" db:"status"`
	RetryCount    int             `json:"retry_count" db:"retry_count"`
	CorrelationID *string         `json:"correlation_id,omitempty" db:"correlation_id"`
	CausationID   *string         `json:"causation_id,omitempty" db:"causation_id"`
	Version       int             `json:"version" db:"version"`
}

// CreateSagaRequest represents a request to create a new saga
type CreateSagaRequest struct {
	SagaType       string          `json:"saga_type" binding:"required"`
	SagaData       json.RawMessage `json:"saga_data" binding:"required"`
	CorrelationID  *string         `json:"correlation_id,omitempty"`
	IdempotencyKey *string         `json:"idempotency_key,omitempty"`
}

// SagaResponse represents a saga response
type SagaResponse struct {
	ID             uuid.UUID  `json:"id"`
	SagaType       string     `json:"saga_type"`
	Status         SagaStatus `json:"status"`
	CurrentStep    int        `json:"current_step"`
	CreatedAt      time.Time  `json:"created_at"`
	UpdatedAt      time.Time  `json:"updated_at"`
	CompletedAt    *time.Time `json:"completed_at,omitempty"`
	ErrorMessage   *string    `json:"error_message,omitempty"`
	RetryCount     int        `json:"retry_count"`
	CorrelationID  *string    `json:"correlation_id,omitempty"`
	IdempotencyKey *string    `json:"idempotency_key,omitempty"`
}

// SagaListResponse represents a list of sagas
type SagaListResponse struct {
	Sagas      []SagaResponse `json:"sagas"`
	TotalCount int            `json:"total_count"`
	Page       int            `json:"page"`
	PageSize   int            `json:"page_size"`
}

// CompensateSagaRequest represents a request to compensate a saga
type CompensateSagaRequest struct {
	Reason string `json:"reason,omitempty"`
}

// RetrySagaRequest represents a request to retry a saga
type RetrySagaRequest struct {
	FromStep int `json:"from_step,omitempty"`
}

// SagaMetrics represents saga metrics
type SagaMetrics struct {
	TotalSagas       int64            `json:"total_sagas"`
	CompletedSagas   int64            `json:"completed_sagas"`
	FailedSagas      int64            `json:"failed_sagas"`
	CompensatedSagas int64            `json:"compensated_sagas"`
	AverageDuration  time.Duration    `json:"average_duration"`
	SagasByType      map[string]int64 `json:"sagas_by_type"`
	SagasByStatus    map[string]int64 `json:"sagas_by_status"`
}

// IsTerminal returns true if the saga status is terminal
func (s SagaStatus) IsTerminal() bool {
	return s == SagaStatusCompleted || s == SagaStatusFailed || s == SagaStatusCompensated || s == SagaStatusCancelled
}

// IsTerminal returns true if the step status is terminal
func (s StepStatus) IsTerminal() bool {
	return s == StepStatusCompleted || s == StepStatusFailed || s == StepStatusCompensated || s == StepStatusSkipped
}

// ToResponse converts a SagaInstance to SagaResponse
func (s *SagaInstance) ToResponse() *SagaResponse {
	return &SagaResponse{
		ID:             s.ID,
		SagaType:       s.SagaType,
		Status:         s.Status,
		CurrentStep:    s.CurrentStep,
		CreatedAt:      s.CreatedAt,
		UpdatedAt:      s.UpdatedAt,
		CompletedAt:    s.CompletedAt,
		ErrorMessage:   s.ErrorMessage,
		RetryCount:     s.RetryCount,
		CorrelationID:  s.CorrelationID,
		IdempotencyKey: s.IdempotencyKey,
	}
}

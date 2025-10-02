package models

import (
	"encoding/json"
	"time"

	"github.com/google/uuid"
)

// InventoryItem represents an inventory item
type InventoryItem struct {
	ID                uuid.UUID `json:"id" db:"id"`
	SKU               string    `json:"sku" db:"sku"`
	Name              string    `json:"name" db:"name"`
	Description       string    `json:"description" db:"description"`
	Quantity          int       `json:"quantity" db:"quantity"`
	ReservedQuantity  int       `json:"reserved_quantity" db:"reserved_quantity"`
	Price             float64   `json:"price" db:"price"`
	CreatedAt         time.Time `json:"created_at" db:"created_at"`
	UpdatedAt         time.Time `json:"updated_at" db:"updated_at"`
	Version           int       `json:"version" db:"version"`
}

// AvailableQuantity returns the available quantity (total - reserved)
func (i *InventoryItem) AvailableQuantity() int {
	return i.Quantity - i.ReservedQuantity
}

// InventoryReservation represents a reservation of inventory items
type InventoryReservation struct {
	ID            uuid.UUID           `json:"id" db:"id"`
	ItemID        uuid.UUID           `json:"item_id" db:"item_id"`
	OrderID       uuid.UUID           `json:"order_id" db:"order_id"`
	Quantity      int                 `json:"quantity" db:"quantity"`
	Status        ReservationStatus   `json:"status" db:"status"`
	ExpiresAt     time.Time           `json:"expires_at" db:"expires_at"`
	CreatedAt     time.Time           `json:"created_at" db:"created_at"`
	ReleasedAt    *time.Time          `json:"released_at,omitempty" db:"released_at"`
	CorrelationID *string             `json:"correlation_id,omitempty" db:"correlation_id"`
}

// ReservationStatus represents the status of a reservation
type ReservationStatus string

const (
	ReservationStatusReserved ReservationStatus = "RESERVED"
	ReservationStatusReleased ReservationStatus = "RELEASED"
	ReservationStatusExpired  ReservationStatus = "EXPIRED"
)

// IsActive returns true if the reservation is active
func (r *InventoryReservation) IsActive() bool {
	return r.Status == ReservationStatusReserved && time.Now().Before(r.ExpiresAt)
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

// Request/Response models

// CreateItemRequest represents a request to create an inventory item
type CreateItemRequest struct {
	SKU         string  `json:"sku" binding:"required"`
	Name        string  `json:"name" binding:"required"`
	Description string  `json:"description"`
	Quantity    int     `json:"quantity" binding:"min=0"`
	Price       float64 `json:"price" binding:"min=0"`
}

// UpdateItemRequest represents a request to update an inventory item
type UpdateItemRequest struct {
	Name        *string  `json:"name,omitempty"`
	Description *string  `json:"description,omitempty"`
	Quantity    *int     `json:"quantity,omitempty" binding:"omitempty,min=0"`
	Price       *float64 `json:"price,omitempty" binding:"omitempty,min=0"`
}

// ReserveItemRequest represents a request to reserve inventory
type ReserveItemRequest struct {
	OrderID       uuid.UUID `json:"order_id" binding:"required"`
	Quantity      int       `json:"quantity" binding:"required,min=1"`
	TTLMinutes    *int      `json:"ttl_minutes,omitempty" binding:"omitempty,min=1"`
	CorrelationID *string   `json:"correlation_id,omitempty"`
}

// ReleaseReservationRequest represents a request to release a reservation
type ReleaseReservationRequest struct {
	OrderID       uuid.UUID `json:"order_id" binding:"required"`
	CorrelationID *string   `json:"correlation_id,omitempty"`
}

// ItemResponse represents an inventory item response
type ItemResponse struct {
	ID                uuid.UUID `json:"id"`
	SKU               string    `json:"sku"`
	Name              string    `json:"name"`
	Description       string    `json:"description"`
	Quantity          int       `json:"quantity"`
	ReservedQuantity  int       `json:"reserved_quantity"`
	AvailableQuantity int       `json:"available_quantity"`
	Price             float64   `json:"price"`
	CreatedAt         time.Time `json:"created_at"`
	UpdatedAt         time.Time `json:"updated_at"`
	Version           int       `json:"version"`
}

// ToResponse converts an InventoryItem to ItemResponse
func (i *InventoryItem) ToResponse() *ItemResponse {
	return &ItemResponse{
		ID:                i.ID,
		SKU:               i.SKU,
		Name:              i.Name,
		Description:       i.Description,
		Quantity:          i.Quantity,
		ReservedQuantity:  i.ReservedQuantity,
		AvailableQuantity: i.AvailableQuantity(),
		Price:             i.Price,
		CreatedAt:         i.CreatedAt,
		UpdatedAt:         i.UpdatedAt,
		Version:           i.Version,
	}
}

// ReservationResponse represents a reservation response
type ReservationResponse struct {
	ID            uuid.UUID         `json:"id"`
	ItemID        uuid.UUID         `json:"item_id"`
	OrderID       uuid.UUID         `json:"order_id"`
	Quantity      int               `json:"quantity"`
	Status        ReservationStatus `json:"status"`
	ExpiresAt     time.Time         `json:"expires_at"`
	CreatedAt     time.Time         `json:"created_at"`
	ReleasedAt    *time.Time        `json:"released_at,omitempty"`
	CorrelationID *string           `json:"correlation_id,omitempty"`
}

// ToResponse converts an InventoryReservation to ReservationResponse
func (r *InventoryReservation) ToResponse() *ReservationResponse {
	return &ReservationResponse{
		ID:            r.ID,
		ItemID:        r.ItemID,
		OrderID:       r.OrderID,
		Quantity:      r.Quantity,
		Status:        r.Status,
		ExpiresAt:     r.ExpiresAt,
		CreatedAt:     r.CreatedAt,
		ReleasedAt:    r.ReleasedAt,
		CorrelationID: r.CorrelationID,
	}
}

// ItemListResponse represents a list of inventory items
type ItemListResponse struct {
	Items      []ItemResponse `json:"items"`
	TotalCount int            `json:"total_count"`
	Page       int            `json:"page"`
	PageSize   int            `json:"page_size"`
}

// ReservationListResponse represents a list of reservations
type ReservationListResponse struct {
	Reservations []ReservationResponse `json:"reservations"`
	TotalCount   int                   `json:"total_count"`
	Page         int                   `json:"page"`
	PageSize     int                   `json:"page_size"`
}

// Event models

// InventoryReservedEvent represents an inventory reserved event
type InventoryReservedEvent struct {
	ItemID        uuid.UUID `json:"item_id"`
	SKU           string    `json:"sku"`
	OrderID       uuid.UUID `json:"order_id"`
	Quantity      int       `json:"quantity"`
	ReservationID uuid.UUID `json:"reservation_id"`
	ExpiresAt     time.Time `json:"expires_at"`
	Timestamp     time.Time `json:"timestamp"`
	CorrelationID *string   `json:"correlation_id,omitempty"`
}

// InventoryReservationFailedEvent represents a failed inventory reservation event
type InventoryReservationFailedEvent struct {
	ItemID        uuid.UUID `json:"item_id"`
	SKU           string    `json:"sku"`
	OrderID       uuid.UUID `json:"order_id"`
	Quantity      int       `json:"quantity"`
	Reason        string    `json:"reason"`
	Timestamp     time.Time `json:"timestamp"`
	CorrelationID *string   `json:"correlation_id,omitempty"`
}

// InventoryReleasedEvent represents an inventory released event
type InventoryReleasedEvent struct {
	ItemID        uuid.UUID `json:"item_id"`
	SKU           string    `json:"sku"`
	OrderID       uuid.UUID `json:"order_id"`
	Quantity      int       `json:"quantity"`
	ReservationID uuid.UUID `json:"reservation_id"`
	Timestamp     time.Time `json:"timestamp"`
	CorrelationID *string   `json:"correlation_id,omitempty"`
}

// InventoryUpdatedEvent represents an inventory updated event
type InventoryUpdatedEvent struct {
	ItemID              uuid.UUID `json:"item_id"`
	SKU                 string    `json:"sku"`
	PreviousQuantity    int       `json:"previous_quantity"`
	NewQuantity         int       `json:"new_quantity"`
	PreviousReserved    int       `json:"previous_reserved"`
	NewReserved         int       `json:"new_reserved"`
	Timestamp           time.Time `json:"timestamp"`
	CorrelationID       *string   `json:"correlation_id,omitempty"`
}

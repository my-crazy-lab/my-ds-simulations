package main

import (
	"context"
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"github.com/lib/pq"
	_ "github.com/lib/pq"
	"github.com/redis/go-redis/v9"
	"github.com/segmentio/kafka-go"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/trace"
)

// RegulatoryEvent represents a regulatory event
type RegulatoryEvent struct {
	ID            string                 `json:"id" db:"id"`
	EventType     string                 `json:"event_type" db:"event_type"`
	Timestamp     time.Time              `json:"timestamp" db:"timestamp"`
	Source        string                 `json:"source" db:"source"`
	EntityID      string                 `json:"entity_id" db:"entity_id"`
	Jurisdiction  string                 `json:"jurisdiction" db:"jurisdiction"`
	EventData     map[string]interface{} `json:"event_data" db:"event_data"`
	SchemaVersion string                 `json:"schema_version" db:"schema_version"`
	Hash          string                 `json:"hash" db:"hash"`
	PreviousHash  string                 `json:"previous_hash" db:"previous_hash"`
	CreatedAt     time.Time              `json:"created_at" db:"created_at"`
}

// EventSubmissionRequest represents event submission request
type EventSubmissionRequest struct {
	EventType    string                 `json:"event_type" binding:"required"`
	Source       string                 `json:"source" binding:"required"`
	EntityID     string                 `json:"entity_id" binding:"required"`
	Jurisdiction string                 `json:"jurisdiction" binding:"required"`
	EventData    map[string]interface{} `json:"event_data" binding:"required"`
	Timestamp    *time.Time             `json:"timestamp"`
}

// EventIngestionService handles regulatory event ingestion
type EventIngestionService struct {
	db          *sql.DB
	redisClient *redis.Client
	kafkaWriter *kafka.Writer
	tracer      trace.Tracer
}

// NewEventIngestionService creates a new event ingestion service
func NewEventIngestionService(db *sql.DB, redisClient *redis.Client, kafkaWriter *kafka.Writer) *EventIngestionService {
	tracer := otel.Tracer("event-ingestion")
	return &EventIngestionService{
		db:          db,
		redisClient: redisClient,
		kafkaWriter: kafkaWriter,
		tracer:      tracer,
	}
}

// SubmitEvent submits a regulatory event
func (eis *EventIngestionService) SubmitEvent(ctx context.Context, req EventSubmissionRequest, userID string) (*RegulatoryEvent, error) {
	ctx, span := eis.tracer.Start(ctx, "submit_event")
	defer span.End()

	// Generate event ID
	eventID := uuid.New().String()

	// Set timestamp if not provided
	timestamp := time.Now()
	if req.Timestamp != nil {
		timestamp = *req.Timestamp
	}

	// Validate event data against schema
	if err := eis.validateEventData(req.EventType, req.EventData); err != nil {
		span.RecordError(err)
		return nil, fmt.Errorf("event validation failed: %w", err)
	}

	// Get previous hash for chain integrity
	previousHash, err := eis.getLastEventHash(ctx, req.EntityID)
	if err != nil {
		span.RecordError(err)
		return nil, fmt.Errorf("failed to get previous hash: %w", err)
	}

	// Create regulatory event
	event := &RegulatoryEvent{
		ID:            eventID,
		EventType:     req.EventType,
		Timestamp:     timestamp,
		Source:        req.Source,
		EntityID:      req.EntityID,
		Jurisdiction:  req.Jurisdiction,
		EventData:     req.EventData,
		SchemaVersion: "1.0", // Would be determined by schema registry
		PreviousHash:  previousHash,
		CreatedAt:     time.Now(),
	}

	// Calculate event hash for tamper evidence
	event.Hash = eis.calculateEventHash(event)

	// Store event in database
	if err := eis.storeEvent(ctx, event); err != nil {
		span.RecordError(err)
		return nil, fmt.Errorf("failed to store event: %w", err)
	}

	// Publish event to Kafka for downstream processing
	if err := eis.publishEvent(ctx, event); err != nil {
		span.RecordError(err)
		// Log error but don't fail the request - event is already stored
		log.Printf("Failed to publish event to Kafka: %v", err)
	}

	// Cache event for quick retrieval
	eventJSON, _ := json.Marshal(event)
	eis.redisClient.Set(ctx, fmt.Sprintf("event:%s", eventID), eventJSON, time.Hour)

	// Log audit event
	eis.logAuditEvent(ctx, "EVENT_SUBMITTED", eventID, userID, map[string]interface{}{
		"event_type":   req.EventType,
		"entity_id":    req.EntityID,
		"jurisdiction": req.Jurisdiction,
	})

	span.SetAttributes(
		attribute.String("event.id", eventID),
		attribute.String("event.type", req.EventType),
		attribute.String("event.entity_id", req.EntityID),
		attribute.String("event.jurisdiction", req.Jurisdiction),
	)

	return event, nil
}

// GetEvent retrieves an event by ID
func (eis *EventIngestionService) GetEvent(ctx context.Context, eventID string) (*RegulatoryEvent, error) {
	ctx, span := eis.tracer.Start(ctx, "get_event")
	defer span.End()

	// Try cache first
	cached, err := eis.redisClient.Get(ctx, fmt.Sprintf("event:%s", eventID)).Result()
	if err == nil {
		var event RegulatoryEvent
		if json.Unmarshal([]byte(cached), &event) == nil {
			return &event, nil
		}
	}

	// Query database
	var event RegulatoryEvent
	var eventDataJSON []byte
	query := `
		SELECT id, event_type, timestamp, source, entity_id, jurisdiction, 
		       event_data, schema_version, hash, previous_hash, created_at
		FROM regulatory_events WHERE id = $1
	`
	err = eis.db.QueryRowContext(ctx, query, eventID).Scan(
		&event.ID, &event.EventType, &event.Timestamp, &event.Source, &event.EntityID,
		&event.Jurisdiction, &eventDataJSON, &event.SchemaVersion, &event.Hash,
		&event.PreviousHash, &event.CreatedAt,
	)
	if err != nil {
		if err == sql.ErrNoRows {
			return nil, fmt.Errorf("event not found")
		}
		span.RecordError(err)
		return nil, fmt.Errorf("failed to get event: %w", err)
	}

	// Parse event data JSON
	if err := json.Unmarshal(eventDataJSON, &event.EventData); err != nil {
		span.RecordError(err)
		return nil, fmt.Errorf("failed to parse event data: %w", err)
	}

	// Cache result
	eventJSON, _ := json.Marshal(event)
	eis.redisClient.Set(ctx, fmt.Sprintf("event:%s", eventID), eventJSON, time.Hour)

	return &event, nil
}

// GetEventsByEntity retrieves events for a specific entity
func (eis *EventIngestionService) GetEventsByEntity(ctx context.Context, entityID string, limit int, offset int) ([]RegulatoryEvent, error) {
	ctx, span := eis.tracer.Start(ctx, "get_events_by_entity")
	defer span.End()

	query := `
		SELECT id, event_type, timestamp, source, entity_id, jurisdiction, 
		       event_data, schema_version, hash, previous_hash, created_at
		FROM regulatory_events 
		WHERE entity_id = $1 
		ORDER BY timestamp DESC 
		LIMIT $2 OFFSET $3
	`
	rows, err := eis.db.QueryContext(ctx, query, entityID, limit, offset)
	if err != nil {
		span.RecordError(err)
		return nil, fmt.Errorf("failed to get events: %w", err)
	}
	defer rows.Close()

	var events []RegulatoryEvent
	for rows.Next() {
		var event RegulatoryEvent
		var eventDataJSON []byte
		
		err := rows.Scan(
			&event.ID, &event.EventType, &event.Timestamp, &event.Source, &event.EntityID,
			&event.Jurisdiction, &eventDataJSON, &event.SchemaVersion, &event.Hash,
			&event.PreviousHash, &event.CreatedAt,
		)
		if err != nil {
			span.RecordError(err)
			continue
		}

		// Parse event data JSON
		if err := json.Unmarshal(eventDataJSON, &event.EventData); err != nil {
			span.RecordError(err)
			continue
		}

		events = append(events, event)
	}

	return events, nil
}

// VerifyEventChain verifies the integrity of the event chain
func (eis *EventIngestionService) VerifyEventChain(ctx context.Context, entityID string) (bool, error) {
	ctx, span := eis.tracer.Start(ctx, "verify_event_chain")
	defer span.End()

	// Get all events for entity in chronological order
	query := `
		SELECT id, event_type, timestamp, source, entity_id, jurisdiction, 
		       event_data, schema_version, hash, previous_hash, created_at
		FROM regulatory_events 
		WHERE entity_id = $1 
		ORDER BY timestamp ASC
	`
	rows, err := eis.db.QueryContext(ctx, query, entityID)
	if err != nil {
		span.RecordError(err)
		return false, fmt.Errorf("failed to get events for verification: %w", err)
	}
	defer rows.Close()

	var previousHash string
	eventCount := 0

	for rows.Next() {
		var event RegulatoryEvent
		var eventDataJSON []byte
		
		err := rows.Scan(
			&event.ID, &event.EventType, &event.Timestamp, &event.Source, &event.EntityID,
			&event.Jurisdiction, &eventDataJSON, &event.SchemaVersion, &event.Hash,
			&event.PreviousHash, &event.CreatedAt,
		)
		if err != nil {
			span.RecordError(err)
			return false, fmt.Errorf("failed to scan event: %w", err)
		}

		// Parse event data JSON
		if err := json.Unmarshal(eventDataJSON, &event.EventData); err != nil {
			span.RecordError(err)
			return false, fmt.Errorf("failed to parse event data: %w", err)
		}

		// Verify hash chain
		if event.PreviousHash != previousHash {
			return false, fmt.Errorf("hash chain broken at event %s", event.ID)
		}

		// Verify event hash
		calculatedHash := eis.calculateEventHash(&event)
		if calculatedHash != event.Hash {
			return false, fmt.Errorf("event hash mismatch for event %s", event.ID)
		}

		previousHash = event.Hash
		eventCount++
	}

	span.SetAttributes(
		attribute.String("entity.id", entityID),
		attribute.Int("events.verified", eventCount),
	)

	return true, nil
}

// Helper functions

func (eis *EventIngestionService) validateEventData(eventType string, eventData map[string]interface{}) error {
	// This would integrate with schema registry for validation
	// For now, perform basic validation
	
	requiredFields := map[string][]string{
		"TRADE_EXECUTION": {"trade_id", "instrument", "quantity", "price"},
		"ORDER_PLACEMENT": {"order_id", "instrument", "quantity", "order_type"},
		"SETTLEMENT":      {"settlement_id", "trade_id", "amount", "currency"},
		"COMPLIANCE_BREACH": {"breach_type", "severity", "description"},
	}

	if fields, exists := requiredFields[eventType]; exists {
		for _, field := range fields {
			if _, ok := eventData[field]; !ok {
				return fmt.Errorf("required field '%s' missing for event type '%s'", field, eventType)
			}
		}
	}

	return nil
}

func (eis *EventIngestionService) getLastEventHash(ctx context.Context, entityID string) (string, error) {
	var lastHash string
	query := `
		SELECT hash FROM regulatory_events 
		WHERE entity_id = $1 
		ORDER BY timestamp DESC 
		LIMIT 1
	`
	err := eis.db.QueryRowContext(ctx, query, entityID).Scan(&lastHash)
	if err != nil {
		if err == sql.ErrNoRows {
			return "", nil // First event for this entity
		}
		return "", err
	}
	return lastHash, nil
}

func (eis *EventIngestionService) calculateEventHash(event *RegulatoryEvent) string {
	// Create hash input from event data
	hashInput := fmt.Sprintf("%s|%s|%s|%s|%s|%s|%s|%s",
		event.ID,
		event.EventType,
		event.Timestamp.Format(time.RFC3339Nano),
		event.Source,
		event.EntityID,
		event.Jurisdiction,
		event.PreviousHash,
		eis.serializeEventData(event.EventData),
	)

	hash := sha256.Sum256([]byte(hashInput))
	return hex.EncodeToString(hash[:])
}

func (eis *EventIngestionService) serializeEventData(eventData map[string]interface{}) string {
	// Serialize event data in a deterministic way
	jsonData, _ := json.Marshal(eventData)
	return string(jsonData)
}

func (eis *EventIngestionService) storeEvent(ctx context.Context, event *RegulatoryEvent) error {
	eventDataJSON, err := json.Marshal(event.EventData)
	if err != nil {
		return fmt.Errorf("failed to marshal event data: %w", err)
	}

	query := `
		INSERT INTO regulatory_events (
			id, event_type, timestamp, source, entity_id, jurisdiction,
			event_data, schema_version, hash, previous_hash, created_at
		) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
	`
	_, err = eis.db.ExecContext(ctx, query,
		event.ID, event.EventType, event.Timestamp, event.Source, event.EntityID,
		event.Jurisdiction, eventDataJSON, event.SchemaVersion, event.Hash,
		event.PreviousHash, event.CreatedAt,
	)
	if err != nil {
		return fmt.Errorf("failed to insert event: %w", err)
	}

	return nil
}

func (eis *EventIngestionService) publishEvent(ctx context.Context, event *RegulatoryEvent) error {
	eventJSON, err := json.Marshal(event)
	if err != nil {
		return fmt.Errorf("failed to marshal event for Kafka: %w", err)
	}

	message := kafka.Message{
		Key:   []byte(event.EntityID),
		Value: eventJSON,
		Headers: []kafka.Header{
			{Key: "event_type", Value: []byte(event.EventType)},
			{Key: "jurisdiction", Value: []byte(event.Jurisdiction)},
			{Key: "schema_version", Value: []byte(event.SchemaVersion)},
		},
	}

	return eis.kafkaWriter.WriteMessages(ctx, message)
}

func (eis *EventIngestionService) logAuditEvent(ctx context.Context, eventType, eventID, userID string, details map[string]interface{}) {
	auditEvent := map[string]interface{}{
		"event_type": eventType,
		"event_id":   eventID,
		"user_id":    userID,
		"timestamp":  time.Now().Unix(),
		"details":    details,
	}

	// Send to audit log service (Redis for now)
	eventJSON, _ := json.Marshal(auditEvent)
	eis.redisClient.LPush(ctx, "audit_events", eventJSON)
}

// HTTP handlers

func (eis *EventIngestionService) submitEventHandler(c *gin.Context) {
	var req EventSubmissionRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	userID := c.GetHeader("X-User-ID")
	if userID == "" {
		userID = "system"
	}

	event, err := eis.SubmitEvent(c.Request.Context(), req, userID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusCreated, event)
}

func (eis *EventIngestionService) getEventHandler(c *gin.Context) {
	eventID := c.Param("eventId")
	
	event, err := eis.GetEvent(c.Request.Context(), eventID)
	if err != nil {
		if err.Error() == "event not found" {
			c.JSON(http.StatusNotFound, gin.H{"error": "Event not found"})
		} else {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		}
		return
	}

	c.JSON(http.StatusOK, event)
}

func (eis *EventIngestionService) getEventsByEntityHandler(c *gin.Context) {
	entityID := c.Param("entityId")
	limit := 100
	offset := 0

	if l := c.Query("limit"); l != "" {
		if parsed, err := fmt.Sscanf(l, "%d", &limit); err != nil || parsed != 1 {
			limit = 100
		}
	}

	if o := c.Query("offset"); o != "" {
		if parsed, err := fmt.Sscanf(o, "%d", &offset); err != nil || parsed != 1 {
			offset = 0
		}
	}

	events, err := eis.GetEventsByEntity(c.Request.Context(), entityID, limit, offset)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"events": events})
}

func (eis *EventIngestionService) verifyEventChainHandler(c *gin.Context) {
	entityID := c.Param("entityId")
	
	valid, err := eis.VerifyEventChain(c.Request.Context(), entityID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"entity_id": entityID,
		"chain_valid": valid,
		"verified_at": time.Now(),
	})
}

func (eis *EventIngestionService) healthCheckHandler(c *gin.Context) {
	c.JSON(http.StatusOK, gin.H{
		"status":    "healthy",
		"service":   "event-ingestion",
		"timestamp": time.Now().Unix(),
	})
}

func main() {
	// Database connection
	dbURL := os.Getenv("DATABASE_URL")
	if dbURL == "" {
		dbURL = "postgres://regtech_user:secure_regtech_pass@localhost:5441/regtech_system?sslmode=disable"
	}

	db, err := sql.Open("postgres", dbURL)
	if err != nil {
		log.Fatal("Failed to connect to database:", err)
	}
	defer db.Close()

	// Redis connection
	redisURL := os.Getenv("REDIS_URL")
	if redisURL == "" {
		redisURL = "redis://localhost:6387"
	}

	opt, err := redis.ParseURL(redisURL)
	if err != nil {
		log.Fatal("Failed to parse Redis URL:", err)
	}
	redisClient := redis.NewClient(opt)

	// Kafka writer
	kafkaBrokers := os.Getenv("KAFKA_BROKERS")
	if kafkaBrokers == "" {
		kafkaBrokers = "localhost:9099"
	}

	kafkaWriter := &kafka.Writer{
		Addr:     kafka.TCP(kafkaBrokers),
		Topic:    "regulatory-events",
		Balancer: &kafka.LeastBytes{},
	}
	defer kafkaWriter.Close()

	// Initialize event ingestion service
	eventService := NewEventIngestionService(db, redisClient, kafkaWriter)

	// Setup Gin router
	r := gin.Default()

	// Health check
	r.GET("/health", eventService.healthCheckHandler)

	// API routes
	api := r.Group("/api/v1")
	{
		api.POST("/events", eventService.submitEventHandler)
		api.GET("/events/:eventId", eventService.getEventHandler)
		api.GET("/entities/:entityId/events", eventService.getEventsByEntityHandler)
		api.GET("/entities/:entityId/verify-chain", eventService.verifyEventChainHandler)
	}

	// Start server
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	log.Printf("Event Ingestion service starting on port %s", port)
	log.Fatal(http.ListenAndServe(":"+port, r))
}

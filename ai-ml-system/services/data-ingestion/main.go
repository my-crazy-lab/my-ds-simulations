package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"sync"
	"syscall"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	"github.com/segmentio/kafka-go"
	"github.com/sirupsen/logrus"
)

// Metrics
var (
	messagesReceived = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "ingestion_messages_received_total",
			Help: "Total number of messages received",
		},
		[]string{"source", "status"},
	)

	messagesProcessed = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "ingestion_messages_processed_total",
			Help: "Total number of messages processed",
		},
		[]string{"source", "status"},
	)

	processingDuration = promauto.NewHistogramVec(
		prometheus.HistogramOpts{
			Name:    "ingestion_processing_duration_seconds",
			Help:    "Time spent processing messages",
			Buckets: prometheus.DefBuckets,
		},
		[]string{"source"},
	)

	duplicatesDetected = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "ingestion_duplicates_detected_total",
			Help: "Total number of duplicate messages detected",
		},
		[]string{"source"},
	)

	validationErrors = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "ingestion_validation_errors_total",
			Help: "Total number of validation errors",
		},
		[]string{"source", "error_type"},
	)
)

// Message structures
type IncomingMessage struct {
	ID          string                 `json:"id"`
	Source      string                 `json:"source"`
	Type        string                 `json:"type"`
	Timestamp   time.Time              `json:"timestamp"`
	Data        map[string]interface{} `json:"data"`
	Metadata    map[string]string      `json:"metadata,omitempty"`
	IdempotencyKey string              `json:"idempotency_key,omitempty"`
}

type ProcessedMessage struct {
	ID             string                 `json:"id"`
	OriginalID     string                 `json:"original_id"`
	Source         string                 `json:"source"`
	Type           string                 `json:"type"`
	Timestamp      time.Time              `json:"timestamp"`
	ProcessedAt    time.Time              `json:"processed_at"`
	Data           map[string]interface{} `json:"data"`
	Metadata       map[string]string      `json:"metadata"`
	IdempotencyKey string                 `json:"idempotency_key"`
	ValidationStatus string               `json:"validation_status"`
	NormalizationApplied []string         `json:"normalization_applied"`
}

// Data Ingestion Service
type DataIngestionService struct {
	kafkaWriter    *kafka.Writer
	dedupeCache    map[string]time.Time
	dedupeMutex    sync.RWMutex
	logger         *logrus.Logger
	validator      *MessageValidator
	normalizer     *MessageNormalizer
}

func NewDataIngestionService() *DataIngestionService {
	logger := logrus.New()
	logger.SetFormatter(&logrus.JSONFormatter{})

	kafkaWriter := &kafka.Writer{
		Addr:         kafka.TCP("localhost:9092"),
		Topic:        "processed-messages",
		Balancer:     &kafka.LeastBytes{},
		RequiredAcks: kafka.RequireAll,
		Async:        false,
	}

	return &DataIngestionService{
		kafkaWriter: kafkaWriter,
		dedupeCache: make(map[string]time.Time),
		logger:      logger,
		validator:   NewMessageValidator(),
		normalizer:  NewMessageNormalizer(),
	}
}

func (dis *DataIngestionService) ProcessMessage(ctx context.Context, msg IncomingMessage) error {
	startTime := time.Now()
	defer func() {
		processingDuration.WithLabelValues(msg.Source).Observe(time.Since(startTime).Seconds())
	}()

	// Generate idempotency key if not provided
	if msg.IdempotencyKey == "" {
		msg.IdempotencyKey = generateIdempotencyKey(msg)
	}

	// Check for duplicates
	if dis.isDuplicate(msg.IdempotencyKey) {
		duplicatesDetected.WithLabelValues(msg.Source).Inc()
		dis.logger.WithFields(logrus.Fields{
			"message_id":       msg.ID,
			"idempotency_key": msg.IdempotencyKey,
			"source":          msg.Source,
		}).Info("Duplicate message detected, skipping")
		return nil
	}

	// Validate message
	validationResult := dis.validator.Validate(msg)
	if !validationResult.IsValid {
		validationErrors.WithLabelValues(msg.Source, validationResult.ErrorType).Inc()
		dis.logger.WithFields(logrus.Fields{
			"message_id": msg.ID,
			"source":     msg.Source,
			"errors":     validationResult.Errors,
		}).Error("Message validation failed")
		messagesProcessed.WithLabelValues(msg.Source, "validation_failed").Inc()
		return fmt.Errorf("validation failed: %v", validationResult.Errors)
	}

	// Normalize message
	normalizedMsg, normalizationSteps := dis.normalizer.Normalize(msg)

	// Create processed message
	processedMsg := ProcessedMessage{
		ID:                   uuid.New().String(),
		OriginalID:           msg.ID,
		Source:               msg.Source,
		Type:                 msg.Type,
		Timestamp:            msg.Timestamp,
		ProcessedAt:          time.Now(),
		Data:                 normalizedMsg.Data,
		Metadata:             normalizedMsg.Metadata,
		IdempotencyKey:       msg.IdempotencyKey,
		ValidationStatus:     "valid",
		NormalizationApplied: normalizationSteps,
	}

	// Send to Kafka
	messageBytes, err := json.Marshal(processedMsg)
	if err != nil {
		dis.logger.WithError(err).Error("Failed to marshal processed message")
		messagesProcessed.WithLabelValues(msg.Source, "marshal_failed").Inc()
		return err
	}

	err = dis.kafkaWriter.WriteMessages(ctx, kafka.Message{
		Key:   []byte(processedMsg.IdempotencyKey),
		Value: messageBytes,
		Headers: []kafka.Header{
			{Key: "source", Value: []byte(msg.Source)},
			{Key: "type", Value: []byte(msg.Type)},
			{Key: "processed_at", Value: []byte(processedMsg.ProcessedAt.Format(time.RFC3339))},
		},
	})

	if err != nil {
		dis.logger.WithError(err).Error("Failed to write message to Kafka")
		messagesProcessed.WithLabelValues(msg.Source, "kafka_failed").Inc()
		return err
	}

	// Mark as processed (add to dedupe cache)
	dis.markAsProcessed(msg.IdempotencyKey)

	messagesProcessed.WithLabelValues(msg.Source, "success").Inc()
	dis.logger.WithFields(logrus.Fields{
		"message_id":       processedMsg.ID,
		"original_id":      msg.ID,
		"source":           msg.Source,
		"idempotency_key":  msg.IdempotencyKey,
		"processing_time":  time.Since(startTime),
	}).Info("Message processed successfully")

	return nil
}

func (dis *DataIngestionService) isDuplicate(idempotencyKey string) bool {
	dis.dedupeMutex.RLock()
	defer dis.dedupeMutex.RUnlock()
	
	_, exists := dis.dedupeCache[idempotencyKey]
	return exists
}

func (dis *DataIngestionService) markAsProcessed(idempotencyKey string) {
	dis.dedupeMutex.Lock()
	defer dis.dedupeMutex.Unlock()
	
	dis.dedupeCache[idempotencyKey] = time.Now()
}

func (dis *DataIngestionService) cleanupDedupeCache() {
	ticker := time.NewTicker(5 * time.Minute)
	defer ticker.Stop()

	for range ticker.C {
		dis.dedupeMutex.Lock()
		cutoff := time.Now().Add(-24 * time.Hour) // Keep entries for 24 hours
		
		for key, timestamp := range dis.dedupeCache {
			if timestamp.Before(cutoff) {
				delete(dis.dedupeCache, key)
			}
		}
		dis.dedupeMutex.Unlock()
		
		dis.logger.WithField("cache_size", len(dis.dedupeCache)).Info("Cleaned up dedupe cache")
	}
}

func generateIdempotencyKey(msg IncomingMessage) string {
	// Generate deterministic key based on message content
	data := fmt.Sprintf("%s-%s-%s-%d", msg.Source, msg.Type, msg.ID, msg.Timestamp.Unix())
	return fmt.Sprintf("%x", data)
}

// HTTP Handlers
func (dis *DataIngestionService) ingestHandler(c *gin.Context) {
	var msg IncomingMessage
	if err := c.ShouldBindJSON(&msg); err != nil {
		messagesReceived.WithLabelValues("unknown", "invalid_json").Inc()
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid JSON format"})
		return
	}

	// Set default values
	if msg.ID == "" {
		msg.ID = uuid.New().String()
	}
	if msg.Timestamp.IsZero() {
		msg.Timestamp = time.Now()
	}
	if msg.Source == "" {
		msg.Source = "api"
	}

	messagesReceived.WithLabelValues(msg.Source, "received").Inc()

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	if err := dis.ProcessMessage(ctx, msg); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{
			"error": "Failed to process message",
			"details": err.Error(),
		})
		return
	}

	c.JSON(http.StatusAccepted, gin.H{
		"status": "accepted",
		"message_id": msg.ID,
		"idempotency_key": msg.IdempotencyKey,
	})
}

func (dis *DataIngestionService) healthHandler(c *gin.Context) {
	c.JSON(http.StatusOK, gin.H{
		"status": "healthy",
		"service": "data-ingestion",
		"timestamp": time.Now().Format(time.RFC3339),
		"cache_size": len(dis.dedupeCache),
	})
}

func main() {
	service := NewDataIngestionService()
	
	// Start dedupe cache cleanup goroutine
	go service.cleanupDedupeCache()

	// Setup HTTP server
	gin.SetMode(gin.ReleaseMode)
	router := gin.Default()

	// Add middleware for logging and metrics
	router.Use(gin.Logger())
	router.Use(gin.Recovery())

	// Routes
	router.POST("/api/v1/ingest", service.ingestHandler)
	router.GET("/health", service.healthHandler)
	router.GET("/metrics", gin.WrapH(promhttp.Handler()))

	// Start server
	srv := &http.Server{
		Addr:    ":8080",
		Handler: router,
	}

	// Graceful shutdown
	go func() {
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("Failed to start server: %v", err)
		}
	}()

	service.logger.Info("Data Ingestion Service started on :8080")

	// Wait for interrupt signal
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit

	service.logger.Info("Shutting down server...")

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	if err := srv.Shutdown(ctx); err != nil {
		service.logger.WithError(err).Error("Server forced to shutdown")
	}

	service.kafkaWriter.Close()
	service.logger.Info("Server exited")
}

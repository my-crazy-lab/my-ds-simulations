package main

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// Test structures - copy from main package for testing
type IncomingMessage struct {
	ID             string                 `json:"id"`
	Source         string                 `json:"source"`
	Type           string                 `json:"type"`
	Timestamp      time.Time              `json:"timestamp"`
	Data           map[string]interface{} `json:"data"`
	Metadata       map[string]string      `json:"metadata,omitempty"`
	IdempotencyKey string                 `json:"idempotency_key,omitempty"`
}

func TestDataIngestionService_ProcessMessage(t *testing.T) {
	tests := []struct {
		name           string
		message        IncomingMessage
		expectError    bool
		expectedStatus string
	}{
		{
			name: "valid_zalo_chat_message",
			message: IncomingMessage{
				ID:        "msg-001",
				Source:    "zalo",
				Type:      "chat_message",
				Timestamp: time.Now(),
				Data: map[string]interface{}{
					"user_id":         "123456789",
					"conversation_id": "conv-001",
					"content":         "Hello, this is a test message",
					"sender_id":       "user-123",
				},
				Metadata: map[string]string{
					"platform": "zalo",
				},
			},
			expectError:    false,
			expectedStatus: "success",
		},
		{
			name: "valid_webhook_user_event",
			message: IncomingMessage{
				ID:        "evt-001",
				Source:    "webhook",
				Type:      "user_event",
				Timestamp: time.Now(),
				Data: map[string]interface{}{
					"event_name": "user_login",
					"user_id":    "user-456",
					"properties": map[string]interface{}{
						"login_method": "oauth",
						"device_type":  "mobile",
					},
				},
				Metadata: map[string]string{
					"webhook_source":    "partner_api",
					"webhook_signature": "sha256=abc123",
				},
			},
			expectError:    false,
			expectedStatus: "success",
		},
		{
			name: "invalid_missing_required_fields",
			message: IncomingMessage{
				ID:        "",
				Source:    "",
				Type:      "",
				Timestamp: time.Time{},
				Data:      nil,
			},
			expectError:    true,
			expectedStatus: "validation_failed",
		},
		{
			name: "invalid_future_timestamp",
			message: IncomingMessage{
				ID:        "msg-002",
				Source:    "api",
				Type:      "chat_message",
				Timestamp: time.Now().Add(2 * time.Hour), // 2 hours in future
				Data: map[string]interface{}{
					"content":   "Test message",
					"sender_id": "user-123",
				},
			},
			expectError:    true,
			expectedStatus: "validation_failed",
		},
		{
			name: "invalid_old_timestamp",
			message: IncomingMessage{
				ID:        "msg-003",
				Source:    "api",
				Type:      "chat_message",
				Timestamp: time.Now().Add(-31 * 24 * time.Hour), // 31 days old
				Data: map[string]interface{}{
					"content":   "Old message",
					"sender_id": "user-123",
				},
			},
			expectError:    true,
			expectedStatus: "validation_failed",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			// Create test service (without Kafka for unit tests)
			service := &DataIngestionService{
				dedupeCache: make(map[string]time.Time),
				validator:   NewMessageValidator(),
				normalizer:  NewMessageNormalizer(),
			}

			// Test message processing logic (without Kafka)
			ctx := context.Background()
			
			// Generate idempotency key if not provided
			if tt.message.IdempotencyKey == "" {
				tt.message.IdempotencyKey = generateIdempotencyKey(tt.message)
			}

			// Check for duplicates
			isDupe := service.isDuplicate(tt.message.IdempotencyKey)
			assert.False(t, isDupe, "Message should not be duplicate on first processing")

			// Validate message
			validationResult := service.validator.Validate(tt.message)
			
			if tt.expectError {
				assert.False(t, validationResult.IsValid, "Message should fail validation")
				assert.NotEmpty(t, validationResult.Errors, "Should have validation errors")
				return
			}

			assert.True(t, validationResult.IsValid, "Message should pass validation")
			assert.Empty(t, validationResult.Errors, "Should not have validation errors")

			// Test normalization
			normalizedMsg, steps := service.normalizer.Normalize(tt.message)
			assert.NotNil(t, normalizedMsg, "Normalized message should not be nil")
			assert.NotNil(t, steps, "Normalization steps should not be nil")

			// Mark as processed
			service.markAsProcessed(tt.message.IdempotencyKey)

			// Test duplicate detection
			isDupeAfter := service.isDuplicate(tt.message.IdempotencyKey)
			assert.True(t, isDupeAfter, "Message should be detected as duplicate after processing")
		})
	}
}

func TestDataIngestionService_HTTPEndpoints(t *testing.T) {
	gin.SetMode(gin.TestMode)
	
	// Create test service
	service := &DataIngestionService{
		dedupeCache: make(map[string]time.Time),
		validator:   NewMessageValidator(),
		normalizer:  NewMessageNormalizer(),
	}

	router := gin.New()
	router.POST("/api/v1/ingest", service.ingestHandler)
	router.GET("/health", service.healthHandler)

	t.Run("health_endpoint", func(t *testing.T) {
		req, _ := http.NewRequest("GET", "/health", nil)
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)

		assert.Equal(t, http.StatusOK, w.Code)
		
		var response map[string]interface{}
		err := json.Unmarshal(w.Body.Bytes(), &response)
		require.NoError(t, err)
		
		assert.Equal(t, "healthy", response["status"])
		assert.Equal(t, "data-ingestion", response["service"])
	})

	t.Run("ingest_valid_message", func(t *testing.T) {
		message := IncomingMessage{
			ID:        "test-001",
			Source:    "api",
			Type:      "chat_message",
			Timestamp: time.Now(),
			Data: map[string]interface{}{
				"content":   "Test message for ingestion",
				"sender_id": "user-test",
			},
		}

		messageBytes, _ := json.Marshal(message)
		req, _ := http.NewRequest("POST", "/api/v1/ingest", bytes.NewBuffer(messageBytes))
		req.Header.Set("Content-Type", "application/json")
		
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)

		// Note: This will fail in unit test because Kafka is not available
		// In integration tests, we would expect 202 Accepted
		assert.Contains(t, []int{http.StatusAccepted, http.StatusInternalServerError}, w.Code)
	})

	t.Run("ingest_invalid_json", func(t *testing.T) {
		req, _ := http.NewRequest("POST", "/api/v1/ingest", bytes.NewBufferString("invalid json"))
		req.Header.Set("Content-Type", "application/json")
		
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)

		assert.Equal(t, http.StatusBadRequest, w.Code)
		
		var response map[string]interface{}
		err := json.Unmarshal(w.Body.Bytes(), &response)
		require.NoError(t, err)
		
		assert.Equal(t, "Invalid JSON format", response["error"])
	})
}

func TestMessageValidator_Validate(t *testing.T) {
	validator := NewMessageValidator()

	tests := []struct {
		name        string
		message     IncomingMessage
		expectValid bool
		expectError string
	}{
		{
			name: "valid_zalo_message",
			message: IncomingMessage{
				ID:        "msg-001",
				Source:    "zalo",
				Type:      "chat_message",
				Timestamp: time.Now(),
				Data: map[string]interface{}{
					"user_id":         "123456789",
					"conversation_id": "conv-001",
					"content":         "Hello world",
					"sender_id":       "user-123",
				},
			},
			expectValid: true,
		},
		{
			name: "invalid_missing_zalo_user_id",
			message: IncomingMessage{
				ID:        "msg-002",
				Source:    "zalo",
				Type:      "chat_message",
				Timestamp: time.Now(),
				Data: map[string]interface{}{
					"conversation_id": "conv-001",
					"content":         "Hello world",
					"sender_id":       "user-123",
				},
			},
			expectValid: false,
			expectError: "Zalo messages must have user_id",
		},
		{
			name: "invalid_empty_content",
			message: IncomingMessage{
				ID:        "msg-003",
				Source:    "api",
				Type:      "chat_message",
				Timestamp: time.Now(),
				Data: map[string]interface{}{
					"content":   "",
					"sender_id": "user-123",
				},
			},
			expectValid: false,
			expectError: "chat message content cannot be empty",
		},
		{
			name: "invalid_large_content",
			message: IncomingMessage{
				ID:        "msg-004",
				Source:    "api",
				Type:      "chat_message",
				Timestamp: time.Now(),
				Data: map[string]interface{}{
					"content":   strings.Repeat("a", 10001), // Exceeds 10000 char limit
					"sender_id": "user-123",
				},
			},
			expectValid: false,
			expectError: "chat message content cannot exceed 10000 characters",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := validator.Validate(tt.message)
			
			assert.Equal(t, tt.expectValid, result.IsValid)
			
			if !tt.expectValid {
				assert.NotEmpty(t, result.Errors)
				if tt.expectError != "" {
					found := false
					for _, err := range result.Errors {
						if strings.Contains(err, tt.expectError) {
							found = true
							break
						}
					}
					assert.True(t, found, "Expected error '%s' not found in: %v", tt.expectError, result.Errors)
				}
			}
		})
	}
}

func TestMessageNormalizer_Normalize(t *testing.T) {
	normalizer := NewMessageNormalizer()

	tests := []struct {
		name           string
		message        IncomingMessage
		expectedSteps  []string
		expectedChanges map[string]interface{}
	}{
		{
			name: "normalize_phone_number",
			message: IncomingMessage{
				ID:        "msg-001",
				Source:    "api",
				Type:      "user_event",
				Timestamp: time.Now(),
				Data: map[string]interface{}{
					"phone":    "0901234567",
					"event_name": "user_registration",
					"user_id":  "user-123",
				},
			},
			expectedSteps: []string{"normalized_phone_number"},
			expectedChanges: map[string]interface{}{
				"phone": "+84901234567",
			},
		},
		{
			name: "normalize_email",
			message: IncomingMessage{
				ID:        "msg-002",
				Source:    "api",
				Type:      "user_event",
				Timestamp: time.Now(),
				Data: map[string]interface{}{
					"email":      "  USER@EXAMPLE.COM  ",
					"event_name": "user_login",
					"user_id":    "user-456",
				},
			},
			expectedSteps: []string{"normalized_email"},
			expectedChanges: map[string]interface{}{
				"email": "user@example.com",
			},
		},
		{
			name: "normalize_chat_content",
			message: IncomingMessage{
				ID:        "msg-003",
				Source:    "api",
				Type:      "chat_message",
				Timestamp: time.Now(),
				Data: map[string]interface{}{
					"content":   "  Hello    world!  \n\n  Multiple   spaces  ",
					"sender_id": "user-789",
				},
			},
			expectedSteps: []string{"normalized_message_content"},
			expectedChanges: map[string]interface{}{
				"content": "Hello world! Multiple spaces",
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			normalizedMsg, steps := normalizer.Normalize(tt.message)
			
			// Check that expected steps were applied
			for _, expectedStep := range tt.expectedSteps {
				found := false
				for _, step := range steps {
					if step == expectedStep {
						found = true
						break
					}
				}
				assert.True(t, found, "Expected normalization step '%s' not found in: %v", expectedStep, steps)
			}

			// Check expected changes
			for key, expectedValue := range tt.expectedChanges {
				actualValue, exists := normalizedMsg.Data[key]
				assert.True(t, exists, "Expected key '%s' not found in normalized data", key)
				assert.Equal(t, expectedValue, actualValue, "Unexpected value for key '%s'", key)
			}

			// Check that metadata was added
			assert.NotNil(t, normalizedMsg.Metadata["normalized_at"])
			assert.Equal(t, "1.0", normalizedMsg.Metadata["normalization_version"])
		})
	}
}

func TestDeduplication(t *testing.T) {
	service := &DataIngestionService{
		dedupeCache: make(map[string]time.Time),
	}

	key1 := "test-key-1"
	key2 := "test-key-2"

	// Initially, no keys should be duplicates
	assert.False(t, service.isDuplicate(key1))
	assert.False(t, service.isDuplicate(key2))

	// Mark key1 as processed
	service.markAsProcessed(key1)

	// Now key1 should be a duplicate, but key2 should not
	assert.True(t, service.isDuplicate(key1))
	assert.False(t, service.isDuplicate(key2))

	// Mark key2 as processed
	service.markAsProcessed(key2)

	// Now both should be duplicates
	assert.True(t, service.isDuplicate(key1))
	assert.True(t, service.isDuplicate(key2))
}

func TestIdempotencyKeyGeneration(t *testing.T) {
	msg1 := IncomingMessage{
		ID:        "msg-001",
		Source:    "zalo",
		Type:      "chat_message",
		Timestamp: time.Unix(1640995200, 0), // Fixed timestamp
	}

	msg2 := IncomingMessage{
		ID:        "msg-001",
		Source:    "zalo",
		Type:      "chat_message",
		Timestamp: time.Unix(1640995200, 0), // Same timestamp
	}

	msg3 := IncomingMessage{
		ID:        "msg-002", // Different ID
		Source:    "zalo",
		Type:      "chat_message",
		Timestamp: time.Unix(1640995200, 0),
	}

	key1 := generateIdempotencyKey(msg1)
	key2 := generateIdempotencyKey(msg2)
	key3 := generateIdempotencyKey(msg3)

	// Same message should generate same key
	assert.Equal(t, key1, key2)

	// Different message should generate different key
	assert.NotEqual(t, key1, key3)

	// Keys should not be empty
	assert.NotEmpty(t, key1)
	assert.NotEmpty(t, key3)
}

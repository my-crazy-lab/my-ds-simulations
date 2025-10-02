package main

import (
	"encoding/json"
	"fmt"
	"regexp"
	"strings"
	"time"
)

// ValidationResult represents the result of message validation
type ValidationResult struct {
	IsValid   bool     `json:"is_valid"`
	Errors    []string `json:"errors"`
	ErrorType string   `json:"error_type"`
}

// MessageValidator handles message validation logic
type MessageValidator struct {
	phoneRegex *regexp.Regexp
	emailRegex *regexp.Regexp
}

// NewMessageValidator creates a new message validator
func NewMessageValidator() *MessageValidator {
	return &MessageValidator{
		phoneRegex: regexp.MustCompile(`^(\+84|84|0)[3|5|7|8|9][0-9]{8}$`), // Vietnamese phone numbers
		emailRegex: regexp.MustCompile(`^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$`),
	}
}

// Validate performs comprehensive validation on incoming messages
func (mv *MessageValidator) Validate(msg IncomingMessage) ValidationResult {
	var errors []string
	var errorType string

	// Required field validation
	if msg.ID == "" {
		errors = append(errors, "message ID is required")
		errorType = "missing_required_field"
	}

	if msg.Source == "" {
		errors = append(errors, "message source is required")
		errorType = "missing_required_field"
	}

	if msg.Type == "" {
		errors = append(errors, "message type is required")
		errorType = "missing_required_field"
	}

	if msg.Data == nil || len(msg.Data) == 0 {
		errors = append(errors, "message data is required")
		errorType = "missing_required_field"
	}

	// Timestamp validation
	if msg.Timestamp.IsZero() {
		errors = append(errors, "timestamp is required")
		errorType = "missing_required_field"
	} else {
		// Check if timestamp is not too far in the future (max 1 hour)
		if msg.Timestamp.After(time.Now().Add(time.Hour)) {
			errors = append(errors, "timestamp cannot be more than 1 hour in the future")
			errorType = "invalid_timestamp"
		}
		
		// Check if timestamp is not too old (max 30 days)
		if msg.Timestamp.Before(time.Now().Add(-30 * 24 * time.Hour)) {
			errors = append(errors, "timestamp cannot be older than 30 days")
			errorType = "invalid_timestamp"
		}
	}

	// Source-specific validation
	switch msg.Source {
	case "zalo":
		errors = append(errors, mv.validateZaloMessage(msg)...)
	case "webhook":
		errors = append(errors, mv.validateWebhookMessage(msg)...)
	case "csv":
		errors = append(errors, mv.validateCSVMessage(msg)...)
	case "api":
		errors = append(errors, mv.validateAPIMessage(msg)...)
	default:
		errors = append(errors, fmt.Sprintf("unsupported source: %s", msg.Source))
		errorType = "unsupported_source"
	}

	// Type-specific validation
	switch msg.Type {
	case "chat_message":
		errors = append(errors, mv.validateChatMessage(msg)...)
	case "user_event":
		errors = append(errors, mv.validateUserEvent(msg)...)
	case "system_event":
		errors = append(errors, mv.validateSystemEvent(msg)...)
	default:
		errors = append(errors, fmt.Sprintf("unsupported message type: %s", msg.Type))
		if errorType == "" {
			errorType = "unsupported_type"
		}
	}

	// Data structure validation
	if len(errors) == 0 {
		errors = append(errors, mv.validateDataStructure(msg)...)
		if len(errors) > 0 && errorType == "" {
			errorType = "invalid_data_structure"
		}
	}

	// Set default error type if not set
	if len(errors) > 0 && errorType == "" {
		errorType = "validation_error"
	}

	return ValidationResult{
		IsValid:   len(errors) == 0,
		Errors:    errors,
		ErrorType: errorType,
	}
}

// validateZaloMessage validates Zalo-specific message format
func (mv *MessageValidator) validateZaloMessage(msg IncomingMessage) []string {
	var errors []string

	// Check for required Zalo fields
	if msg.Data["user_id"] == nil {
		errors = append(errors, "Zalo messages must have user_id")
	}

	if msg.Data["conversation_id"] == nil {
		errors = append(errors, "Zalo messages must have conversation_id")
	}

	// Validate Zalo user ID format
	if userID, ok := msg.Data["user_id"].(string); ok {
		if len(userID) == 0 {
			errors = append(errors, "Zalo user_id cannot be empty")
		}
	}

	return errors
}

// validateWebhookMessage validates webhook-specific message format
func (mv *MessageValidator) validateWebhookMessage(msg IncomingMessage) []string {
	var errors []string

	// Check for webhook signature if present
	if signature, exists := msg.Metadata["webhook_signature"]; exists {
		if signature == "" {
			errors = append(errors, "webhook signature cannot be empty")
		}
	}

	// Check for webhook source
	if _, exists := msg.Metadata["webhook_source"]; !exists {
		errors = append(errors, "webhook messages must have webhook_source in metadata")
	}

	return errors
}

// validateCSVMessage validates CSV import message format
func (mv *MessageValidator) validateCSVMessage(msg IncomingMessage) []string {
	var errors []string

	// Check for CSV metadata
	if _, exists := msg.Metadata["csv_file"]; !exists {
		errors = append(errors, "CSV messages must have csv_file in metadata")
	}

	if _, exists := msg.Metadata["row_number"]; !exists {
		errors = append(errors, "CSV messages must have row_number in metadata")
	}

	return errors
}

// validateAPIMessage validates API-specific message format
func (mv *MessageValidator) validateAPIMessage(msg IncomingMessage) []string {
	var errors []string

	// API messages should have client identification
	if _, exists := msg.Metadata["client_id"]; !exists {
		errors = append(errors, "API messages should have client_id in metadata")
	}

	return errors
}

// validateChatMessage validates chat message content
func (mv *MessageValidator) validateChatMessage(msg IncomingMessage) []string {
	var errors []string

	// Check for message content
	if msg.Data["content"] == nil {
		errors = append(errors, "chat messages must have content")
		return errors
	}

	content, ok := msg.Data["content"].(string)
	if !ok {
		errors = append(errors, "chat message content must be a string")
		return errors
	}

	// Validate content length
	if len(content) == 0 {
		errors = append(errors, "chat message content cannot be empty")
	}

	if len(content) > 10000 {
		errors = append(errors, "chat message content cannot exceed 10000 characters")
	}

	// Check for sender information
	if msg.Data["sender_id"] == nil {
		errors = append(errors, "chat messages must have sender_id")
	}

	return errors
}

// validateUserEvent validates user event data
func (mv *MessageValidator) validateUserEvent(msg IncomingMessage) []string {
	var errors []string

	// Check for event name
	if msg.Data["event_name"] == nil {
		errors = append(errors, "user events must have event_name")
	}

	// Check for user ID
	if msg.Data["user_id"] == nil {
		errors = append(errors, "user events must have user_id")
	}

	return errors
}

// validateSystemEvent validates system event data
func (mv *MessageValidator) validateSystemEvent(msg IncomingMessage) []string {
	var errors []string

	// Check for event type
	if msg.Data["event_type"] == nil {
		errors = append(errors, "system events must have event_type")
	}

	// Check for severity level
	if msg.Data["severity"] == nil {
		errors = append(errors, "system events must have severity level")
	}

	return errors
}

// validateDataStructure performs deep validation of data structure
func (mv *MessageValidator) validateDataStructure(msg IncomingMessage) []string {
	var errors []string

	// Check for circular references in JSON
	if _, err := json.Marshal(msg.Data); err != nil {
		errors = append(errors, fmt.Sprintf("invalid JSON structure in data: %v", err))
	}

	// Validate nested data depth (prevent deeply nested objects)
	if depth := mv.getJSONDepth(msg.Data); depth > 10 {
		errors = append(errors, fmt.Sprintf("data structure too deep (max 10 levels, got %d)", depth))
	}

	// Validate data size (prevent extremely large payloads)
	if dataBytes, err := json.Marshal(msg.Data); err == nil {
		if len(dataBytes) > 1024*1024 { // 1MB limit
			errors = append(errors, fmt.Sprintf("data payload too large (max 1MB, got %d bytes)", len(dataBytes)))
		}
	}

	// Validate specific data fields
	errors = append(errors, mv.validateDataFields(msg.Data)...)

	return errors
}

// getJSONDepth calculates the maximum depth of nested JSON objects
func (mv *MessageValidator) getJSONDepth(data interface{}) int {
	switch v := data.(type) {
	case map[string]interface{}:
		maxDepth := 0
		for _, value := range v {
			depth := mv.getJSONDepth(value)
			if depth > maxDepth {
				maxDepth = depth
			}
		}
		return maxDepth + 1
	case []interface{}:
		maxDepth := 0
		for _, value := range v {
			depth := mv.getJSONDepth(value)
			if depth > maxDepth {
				maxDepth = depth
			}
		}
		return maxDepth + 1
	default:
		return 1
	}
}

// validateDataFields validates specific data field formats
func (mv *MessageValidator) validateDataFields(data map[string]interface{}) []string {
	var errors []string

	// Validate phone numbers
	if phone, exists := data["phone"]; exists {
		if phoneStr, ok := phone.(string); ok {
			if !mv.phoneRegex.MatchString(phoneStr) {
				errors = append(errors, "invalid phone number format")
			}
		}
	}

	// Validate email addresses
	if email, exists := data["email"]; exists {
		if emailStr, ok := email.(string); ok {
			if !mv.emailRegex.MatchString(emailStr) {
				errors = append(errors, "invalid email address format")
			}
		}
	}

	// Validate URLs
	if url, exists := data["url"]; exists {
		if urlStr, ok := url.(string); ok {
			if !strings.HasPrefix(urlStr, "http://") && !strings.HasPrefix(urlStr, "https://") {
				errors = append(errors, "URL must start with http:// or https://")
			}
		}
	}

	return errors
}

package main

import (
	"encoding/json"
	"fmt"
	"regexp"
	"strings"
	"time"
	"unicode"
)

// MessageNormalizer handles message normalization logic
type MessageNormalizer struct {
	phoneRegex     *regexp.Regexp
	whitespaceRegex *regexp.Regexp
	urlRegex       *regexp.Regexp
}

// NewMessageNormalizer creates a new message normalizer
func NewMessageNormalizer() *MessageNormalizer {
	return &MessageNormalizer{
		phoneRegex:      regexp.MustCompile(`(\+84|84|0)([3|5|7|8|9][0-9]{8})`),
		whitespaceRegex: regexp.MustCompile(`\s+`),
		urlRegex:        regexp.MustCompile(`https?://[^\s]+`),
	}
}

// Normalize applies normalization rules to incoming messages
func (mn *MessageNormalizer) Normalize(msg IncomingMessage) (IncomingMessage, []string) {
	var appliedSteps []string
	normalizedMsg := msg

	// Deep copy the data to avoid modifying the original
	if dataBytes, err := json.Marshal(msg.Data); err == nil {
		var newData map[string]interface{}
		if err := json.Unmarshal(dataBytes, &newData); err == nil {
			normalizedMsg.Data = newData
		}
	}

	// Initialize metadata if nil
	if normalizedMsg.Metadata == nil {
		normalizedMsg.Metadata = make(map[string]string)
	}

	// Source-specific normalization
	switch msg.Source {
	case "zalo":
		steps := mn.normalizeZaloMessage(&normalizedMsg)
		appliedSteps = append(appliedSteps, steps...)
	case "webhook":
		steps := mn.normalizeWebhookMessage(&normalizedMsg)
		appliedSteps = append(appliedSteps, steps...)
	case "csv":
		steps := mn.normalizeCSVMessage(&normalizedMsg)
		appliedSteps = append(appliedSteps, steps...)
	}

	// Type-specific normalization
	switch msg.Type {
	case "chat_message":
		steps := mn.normalizeChatMessage(&normalizedMsg)
		appliedSteps = append(appliedSteps, steps...)
	case "user_event":
		steps := mn.normalizeUserEvent(&normalizedMsg)
		appliedSteps = append(appliedSteps, steps...)
	}

	// General data normalization
	steps := mn.normalizeDataFields(&normalizedMsg)
	appliedSteps = append(appliedSteps, steps...)

	// Add normalization metadata
	normalizedMsg.Metadata["normalized_at"] = time.Now().Format(time.RFC3339)
	normalizedMsg.Metadata["normalization_version"] = "1.0"

	return normalizedMsg, appliedSteps
}

// normalizeZaloMessage applies Zalo-specific normalization
func (mn *MessageNormalizer) normalizeZaloMessage(msg *IncomingMessage) []string {
	var steps []string

	// Normalize Zalo user ID format
	if userID, exists := msg.Data["user_id"]; exists {
		if userIDStr, ok := userID.(string); ok {
			// Remove any non-numeric characters from Zalo user ID
			normalizedUserID := regexp.MustCompile(`[^0-9]`).ReplaceAllString(userIDStr, "")
			if normalizedUserID != userIDStr {
				msg.Data["user_id"] = normalizedUserID
				steps = append(steps, "normalized_zalo_user_id")
			}
		}
	}

	// Normalize conversation ID
	if convID, exists := msg.Data["conversation_id"]; exists {
		if convIDStr, ok := convID.(string); ok {
			// Ensure conversation ID is lowercase
			normalizedConvID := strings.ToLower(convIDStr)
			if normalizedConvID != convIDStr {
				msg.Data["conversation_id"] = normalizedConvID
				steps = append(steps, "normalized_conversation_id")
			}
		}
	}

	// Add Zalo-specific metadata
	msg.Metadata["platform"] = "zalo"
	steps = append(steps, "added_platform_metadata")

	return steps
}

// normalizeWebhookMessage applies webhook-specific normalization
func (mn *MessageNormalizer) normalizeWebhookMessage(msg *IncomingMessage) []string {
	var steps []string

	// Normalize webhook headers to lowercase
	for key, value := range msg.Metadata {
		if strings.HasPrefix(key, "webhook_header_") {
			normalizedKey := strings.ToLower(key)
			if normalizedKey != key {
				msg.Metadata[normalizedKey] = value
				delete(msg.Metadata, key)
				steps = append(steps, "normalized_webhook_headers")
			}
		}
	}

	// Add webhook processing timestamp
	msg.Metadata["webhook_processed_at"] = time.Now().Format(time.RFC3339)
	steps = append(steps, "added_webhook_timestamp")

	return steps
}

// normalizeCSVMessage applies CSV-specific normalization
func (mn *MessageNormalizer) normalizeCSVMessage(msg *IncomingMessage) []string {
	var steps []string

	// Normalize CSV row data
	for key, value := range msg.Data {
		if valueStr, ok := value.(string); ok {
			// Trim whitespace from CSV fields
			trimmed := strings.TrimSpace(valueStr)
			if trimmed != valueStr {
				msg.Data[key] = trimmed
				steps = append(steps, "trimmed_csv_fields")
			}

			// Convert empty strings to nil for CSV data
			if trimmed == "" {
				msg.Data[key] = nil
				steps = append(steps, "converted_empty_strings_to_nil")
			}
		}
	}

	return steps
}

// normalizeChatMessage applies chat message-specific normalization
func (mn *MessageNormalizer) normalizeChatMessage(msg *IncomingMessage) []string {
	var steps []string

	// Normalize message content
	if content, exists := msg.Data["content"]; exists {
		if contentStr, ok := content.(string); ok {
			originalContent := contentStr

			// Trim whitespace
			contentStr = strings.TrimSpace(contentStr)

			// Normalize whitespace (replace multiple spaces with single space)
			contentStr = mn.whitespaceRegex.ReplaceAllString(contentStr, " ")

			// Remove control characters except newlines and tabs
			contentStr = mn.removeControlCharacters(contentStr)

			// Normalize Unicode (NFC normalization would be ideal here)
			contentStr = mn.normalizeUnicode(contentStr)

			if contentStr != originalContent {
				msg.Data["content"] = contentStr
				msg.Data["original_content"] = originalContent
				steps = append(steps, "normalized_message_content")
			}
		}
	}

	// Normalize sender ID
	if senderID, exists := msg.Data["sender_id"]; exists {
		if senderIDStr, ok := senderID.(string); ok {
			normalizedSenderID := strings.ToLower(strings.TrimSpace(senderIDStr))
			if normalizedSenderID != senderIDStr {
				msg.Data["sender_id"] = normalizedSenderID
				steps = append(steps, "normalized_sender_id")
			}
		}
	}

	// Extract and normalize mentions
	if content, exists := msg.Data["content"]; exists {
		if contentStr, ok := content.(string); ok {
			mentions := mn.extractMentions(contentStr)
			if len(mentions) > 0 {
				msg.Data["mentions"] = mentions
				steps = append(steps, "extracted_mentions")
			}
		}
	}

	// Extract and normalize URLs
	if content, exists := msg.Data["content"]; exists {
		if contentStr, ok := content.(string); ok {
			urls := mn.extractURLs(contentStr)
			if len(urls) > 0 {
				msg.Data["urls"] = urls
				steps = append(steps, "extracted_urls")
			}
		}
	}

	return steps
}

// normalizeUserEvent applies user event-specific normalization
func (mn *MessageNormalizer) normalizeUserEvent(msg *IncomingMessage) []string {
	var steps []string

	// Normalize event name to lowercase with underscores
	if eventName, exists := msg.Data["event_name"]; exists {
		if eventNameStr, ok := eventName.(string); ok {
			normalizedEventName := mn.normalizeEventName(eventNameStr)
			if normalizedEventName != eventNameStr {
				msg.Data["event_name"] = normalizedEventName
				msg.Data["original_event_name"] = eventNameStr
				steps = append(steps, "normalized_event_name")
			}
		}
	}

	// Normalize user ID
	if userID, exists := msg.Data["user_id"]; exists {
		if userIDStr, ok := userID.(string); ok {
			normalizedUserID := strings.ToLower(strings.TrimSpace(userIDStr))
			if normalizedUserID != userIDStr {
				msg.Data["user_id"] = normalizedUserID
				steps = append(steps, "normalized_user_id")
			}
		}
	}

	return steps
}

// normalizeDataFields applies general data field normalization
func (mn *MessageNormalizer) normalizeDataFields(msg *IncomingMessage) []string {
	var steps []string

	// Normalize phone numbers
	if phone, exists := msg.Data["phone"]; exists {
		if phoneStr, ok := phone.(string); ok {
			normalizedPhone := mn.normalizePhoneNumber(phoneStr)
			if normalizedPhone != phoneStr {
				msg.Data["phone"] = normalizedPhone
				msg.Data["original_phone"] = phoneStr
				steps = append(steps, "normalized_phone_number")
			}
		}
	}

	// Normalize email addresses
	if email, exists := msg.Data["email"]; exists {
		if emailStr, ok := email.(string); ok {
			normalizedEmail := strings.ToLower(strings.TrimSpace(emailStr))
			if normalizedEmail != emailStr {
				msg.Data["email"] = normalizedEmail
				steps = append(steps, "normalized_email")
			}
		}
	}

	// Normalize timestamps
	for key, value := range msg.Data {
		if strings.Contains(key, "timestamp") || strings.Contains(key, "_at") {
			if timestampStr, ok := value.(string); ok {
				if normalizedTimestamp := mn.normalizeTimestamp(timestampStr); normalizedTimestamp != timestampStr {
					msg.Data[key] = normalizedTimestamp
					steps = append(steps, fmt.Sprintf("normalized_timestamp_%s", key))
				}
			}
		}
	}

	return steps
}

// Helper functions

func (mn *MessageNormalizer) removeControlCharacters(s string) string {
	return strings.Map(func(r rune) rune {
		if unicode.IsControl(r) && r != '\n' && r != '\t' && r != '\r' {
			return -1
		}
		return r
	}, s)
}

func (mn *MessageNormalizer) normalizeUnicode(s string) string {
	// Basic Unicode normalization - in production, use golang.org/x/text/unicode/norm
	return strings.TrimSpace(s)
}

func (mn *MessageNormalizer) extractMentions(content string) []string {
	mentionRegex := regexp.MustCompile(`@([a-zA-Z0-9_]+)`)
	matches := mentionRegex.FindAllStringSubmatch(content, -1)
	
	var mentions []string
	for _, match := range matches {
		if len(match) > 1 {
			mentions = append(mentions, match[1])
		}
	}
	
	return mentions
}

func (mn *MessageNormalizer) extractURLs(content string) []string {
	matches := mn.urlRegex.FindAllString(content, -1)
	return matches
}

func (mn *MessageNormalizer) normalizeEventName(eventName string) string {
	// Convert to lowercase and replace spaces with underscores
	normalized := strings.ToLower(eventName)
	normalized = strings.ReplaceAll(normalized, " ", "_")
	normalized = strings.ReplaceAll(normalized, "-", "_")
	
	// Remove special characters except underscores
	normalized = regexp.MustCompile(`[^a-z0-9_]`).ReplaceAllString(normalized, "")
	
	return normalized
}

func (mn *MessageNormalizer) normalizePhoneNumber(phone string) string {
	// Remove all non-digit characters
	digits := regexp.MustCompile(`[^0-9]`).ReplaceAllString(phone, "")
	
	// Convert Vietnamese phone number formats to standard format
	if strings.HasPrefix(digits, "84") && len(digits) == 11 {
		return "+84" + digits[2:]
	} else if strings.HasPrefix(digits, "0") && len(digits) == 10 {
		return "+84" + digits[1:]
	} else if len(digits) == 9 {
		return "+84" + digits
	}
	
	return phone // Return original if no normalization applied
}

func (mn *MessageNormalizer) normalizeTimestamp(timestamp string) string {
	// Try to parse and reformat timestamp to RFC3339
	formats := []string{
		time.RFC3339,
		time.RFC3339Nano,
		"2006-01-02 15:04:05",
		"2006-01-02T15:04:05",
		"2006/01/02 15:04:05",
	}
	
	for _, format := range formats {
		if t, err := time.Parse(format, timestamp); err == nil {
			return t.Format(time.RFC3339)
		}
	}
	
	return timestamp // Return original if parsing fails
}

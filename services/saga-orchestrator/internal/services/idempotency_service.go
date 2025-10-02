package services

import (
	"context"
	"fmt"
	"time"

	"github.com/go-redis/redis/v8"
	"github.com/sirupsen/logrus"
	"go.opentelemetry.io/otel/attribute"
)

// IdempotencyService handles idempotency key management
type IdempotencyService interface {
	StoreResult(ctx context.Context, key string, result []byte, ttl time.Duration) error
	GetResult(ctx context.Context, key string) ([]byte, error)
	DeleteResult(ctx context.Context, key string) error
	IsProcessed(ctx context.Context, key string) (bool, error)
	MarkAsProcessing(ctx context.Context, key string, ttl time.Duration) error
}

// RedisIdempotencyService implements IdempotencyService using Redis
type RedisIdempotencyService struct {
	client *redis.Client
	logger *logrus.Logger
	prefix string
}

// NewIdempotencyService creates a new Redis idempotency service
func NewIdempotencyService(client *redis.Client, logger *logrus.Logger) IdempotencyService {
	return &RedisIdempotencyService{
		client: client,
		logger: logger,
		prefix: "idempotency:",
	}
}

// StoreResult stores the result for an idempotency key
func (s *RedisIdempotencyService) StoreResult(ctx context.Context, key string, result []byte, ttl time.Duration) error {
	ctx, span := tracer.Start(ctx, "idempotency_service.StoreResult")
	defer span.End()

	span.SetAttributes(
		attribute.String("idempotency.key", key),
		attribute.Int("result.size", len(result)),
		attribute.String("ttl", ttl.String()),
	)

	redisKey := s.prefix + key
	err := s.client.Set(ctx, redisKey, result, ttl).Err()
	if err != nil {
		span.RecordError(err)
		s.logger.WithError(err).WithField("key", key).Error("Failed to store idempotency result")
		return fmt.Errorf("failed to store idempotency result: %w", err)
	}

	s.logger.WithFields(logrus.Fields{
		"key":         key,
		"result_size": len(result),
		"ttl":         ttl,
	}).Debug("Idempotency result stored")

	return nil
}

// GetResult retrieves the result for an idempotency key
func (s *RedisIdempotencyService) GetResult(ctx context.Context, key string) ([]byte, error) {
	ctx, span := tracer.Start(ctx, "idempotency_service.GetResult")
	defer span.End()

	span.SetAttributes(attribute.String("idempotency.key", key))

	redisKey := s.prefix + key
	result, err := s.client.Get(ctx, redisKey).Bytes()
	if err != nil {
		if err == redis.Nil {
			span.SetAttributes(attribute.Bool("found", false))
			return nil, fmt.Errorf("idempotency key not found: %s", key)
		}
		span.RecordError(err)
		s.logger.WithError(err).WithField("key", key).Error("Failed to get idempotency result")
		return nil, fmt.Errorf("failed to get idempotency result: %w", err)
	}

	span.SetAttributes(
		attribute.Bool("found", true),
		attribute.Int("result.size", len(result)),
	)

	s.logger.WithFields(logrus.Fields{
		"key":         key,
		"result_size": len(result),
	}).Debug("Idempotency result retrieved")

	return result, nil
}

// DeleteResult deletes the result for an idempotency key
func (s *RedisIdempotencyService) DeleteResult(ctx context.Context, key string) error {
	ctx, span := tracer.Start(ctx, "idempotency_service.DeleteResult")
	defer span.End()

	span.SetAttributes(attribute.String("idempotency.key", key))

	redisKey := s.prefix + key
	err := s.client.Del(ctx, redisKey).Err()
	if err != nil {
		span.RecordError(err)
		s.logger.WithError(err).WithField("key", key).Error("Failed to delete idempotency result")
		return fmt.Errorf("failed to delete idempotency result: %w", err)
	}

	s.logger.WithField("key", key).Debug("Idempotency result deleted")

	return nil
}

// IsProcessed checks if an idempotency key has been processed
func (s *RedisIdempotencyService) IsProcessed(ctx context.Context, key string) (bool, error) {
	ctx, span := tracer.Start(ctx, "idempotency_service.IsProcessed")
	defer span.End()

	span.SetAttributes(attribute.String("idempotency.key", key))

	redisKey := s.prefix + key
	exists, err := s.client.Exists(ctx, redisKey).Result()
	if err != nil {
		span.RecordError(err)
		s.logger.WithError(err).WithField("key", key).Error("Failed to check idempotency key")
		return false, fmt.Errorf("failed to check idempotency key: %w", err)
	}

	processed := exists > 0
	span.SetAttributes(attribute.Bool("processed", processed))

	return processed, nil
}

// MarkAsProcessing marks an idempotency key as being processed
func (s *RedisIdempotencyService) MarkAsProcessing(ctx context.Context, key string, ttl time.Duration) error {
	ctx, span := tracer.Start(ctx, "idempotency_service.MarkAsProcessing")
	defer span.End()

	span.SetAttributes(
		attribute.String("idempotency.key", key),
		attribute.String("ttl", ttl.String()),
	)

	redisKey := s.prefix + "processing:" + key
	
	// Use SET with NX (only if not exists) to ensure atomicity
	success, err := s.client.SetNX(ctx, redisKey, "processing", ttl).Result()
	if err != nil {
		span.RecordError(err)
		s.logger.WithError(err).WithField("key", key).Error("Failed to mark as processing")
		return fmt.Errorf("failed to mark as processing: %w", err)
	}

	if !success {
		span.SetAttributes(attribute.Bool("already_processing", true))
		return fmt.Errorf("idempotency key already being processed: %s", key)
	}

	s.logger.WithFields(logrus.Fields{
		"key": key,
		"ttl": ttl,
	}).Debug("Idempotency key marked as processing")

	return nil
}

// CleanupExpiredKeys removes expired idempotency keys (for maintenance)
func (s *RedisIdempotencyService) CleanupExpiredKeys(ctx context.Context) error {
	ctx, span := tracer.Start(ctx, "idempotency_service.CleanupExpiredKeys")
	defer span.End()

	// Redis automatically handles TTL expiration, but we can scan for any orphaned keys
	pattern := s.prefix + "*"
	
	var cursor uint64
	var deletedCount int64

	for {
		keys, nextCursor, err := s.client.Scan(ctx, cursor, pattern, 100).Result()
		if err != nil {
			span.RecordError(err)
			return fmt.Errorf("failed to scan idempotency keys: %w", err)
		}

		if len(keys) > 0 {
			// Check TTL for each key and delete if expired
			for _, key := range keys {
				ttl, err := s.client.TTL(ctx, key).Result()
				if err != nil {
					continue
				}
				
				// If TTL is -1 (no expiration) or -2 (key doesn't exist), skip
				if ttl == -1 || ttl == -2 {
					continue
				}
				
				// If TTL is very small (< 1 second), delete it
				if ttl < time.Second {
					if err := s.client.Del(ctx, key).Err(); err == nil {
						deletedCount++
					}
				}
			}
		}

		cursor = nextCursor
		if cursor == 0 {
			break
		}
	}

	if deletedCount > 0 {
		span.SetAttributes(attribute.Int64("deleted.count", deletedCount))
		s.logger.WithField("deleted_count", deletedCount).Info("Cleaned up expired idempotency keys")
	}

	return nil
}

// GetStats returns statistics about idempotency keys
func (s *RedisIdempotencyService) GetStats(ctx context.Context) (map[string]interface{}, error) {
	ctx, span := tracer.Start(ctx, "idempotency_service.GetStats")
	defer span.End()

	pattern := s.prefix + "*"
	
	var cursor uint64
	var totalKeys int64
	var processingKeys int64

	for {
		keys, nextCursor, err := s.client.Scan(ctx, cursor, pattern, 100).Result()
		if err != nil {
			span.RecordError(err)
			return nil, fmt.Errorf("failed to scan idempotency keys: %w", err)
		}

		totalKeys += int64(len(keys))
		
		for _, key := range keys {
			if contains(key, "processing:") {
				processingKeys++
			}
		}

		cursor = nextCursor
		if cursor == 0 {
			break
		}
	}

	stats := map[string]interface{}{
		"total_keys":      totalKeys,
		"processing_keys": processingKeys,
		"completed_keys":  totalKeys - processingKeys,
	}

	span.SetAttributes(
		attribute.Int64("total.keys", totalKeys),
		attribute.Int64("processing.keys", processingKeys),
	)

	return stats, nil
}

// Helper function
func contains(s, substr string) bool {
	return len(s) >= len(substr) && (s == substr || 
		(len(s) > len(substr) && (s[:len(substr)] == substr || s[len(s)-len(substr):] == substr)))
}

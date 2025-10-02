package infrastructure

import (
	"context"
	"fmt"
	"net/url"
	"strconv"
	"time"

	"github.com/go-redis/redis/v8"
)

// NewRedisClient creates a new Redis client
func NewRedisClient(redisURL string) (*redis.Client, error) {
	parsedURL, err := url.Parse(redisURL)
	if err != nil {
		return nil, fmt.Errorf("failed to parse Redis URL: %w", err)
	}

	// Extract connection parameters
	addr := parsedURL.Host
	if parsedURL.Port() == "" {
		addr = parsedURL.Hostname() + ":6379"
	}

	var password string
	if parsedURL.User != nil {
		password, _ = parsedURL.User.Password()
	}

	// Extract database number from path
	db := 0
	if parsedURL.Path != "" && parsedURL.Path != "/" {
		if dbNum, err := strconv.Atoi(parsedURL.Path[1:]); err == nil {
			db = dbNum
		}
	}

	// Create Redis client
	client := redis.NewClient(&redis.Options{
		Addr:         addr,
		Password:     password,
		DB:           db,
		DialTimeout:  5 * time.Second,
		ReadTimeout:  3 * time.Second,
		WriteTimeout: 3 * time.Second,
		PoolSize:     10,
		MinIdleConns: 2,
		MaxRetries:   3,
	})

	// Test the connection
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	if err := client.Ping(ctx).Err(); err != nil {
		client.Close()
		return nil, fmt.Errorf("failed to ping Redis: %w", err)
	}

	return client, nil
}

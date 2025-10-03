package config

import (
	"fmt"
	"os"
	"strconv"
	"strings"
)

// Config holds all configuration for the ledger service
type Config struct {
	// Service configuration
	ServiceName string
	Environment string
	Port        int
	MetricsPort int
	LogLevel    string

	// Database configuration
	DatabaseURL        string
	ReplicaDatabaseURL string
	MaxOpenConns       int
	MaxIdleConns       int
	ConnMaxLifetime    int

	// Redis configuration
	RedisURL      string
	RedisPassword string
	RedisDB       int

	// Kafka configuration
	KafkaBrokers        []string
	SchemaRegistryURL   string
	ConsumerGroup       string
	ProducerRetries     int
	ProducerBatchSize   int
	ProducerLingerMS    int

	// Observability
	JaegerEndpoint string
	MetricsEnabled bool

	// Security
	JWTSecret           string
	EncryptionKey       string
	TLSEnabled          bool
	TLSCertFile         string
	TLSKeyFile          string

	// Rate limiting
	RateLimit int

	// Business logic
	DefaultCurrency          string
	MaxTransactionAmount     float64
	ReconciliationSchedule   string
	AuditRetentionDays       int
	IdempotencyKeyTTL        int
	DistributedLockTTL       int

	// Feature flags
	EnableAuditTrail       bool
	EnableReconciliation   bool
	EnableDistributedLocks bool
	EnableMetrics          bool
	EnableTracing          bool
}

// Load loads configuration from environment variables with defaults
func Load() (*Config, error) {
	config := &Config{
		// Service defaults
		ServiceName: getEnv("SERVICE_NAME", "ledger-service"),
		Environment: getEnv("ENVIRONMENT", "development"),
		Port:        getEnvAsInt("PORT", 8080),
		MetricsPort: getEnvAsInt("METRICS_PORT", 9090),
		LogLevel:    getEnv("LOG_LEVEL", "info"),

		// Database defaults
		DatabaseURL:        getEnv("DATABASE_URL", "postgres://banking_user:secure_banking_pass@localhost:5433/core_banking?sslmode=disable"),
		ReplicaDatabaseURL: getEnv("REPLICA_DATABASE_URL", "postgres://banking_user:secure_banking_pass@localhost:5434/core_banking?sslmode=disable"),
		MaxOpenConns:       getEnvAsInt("DB_MAX_OPEN_CONNS", 25),
		MaxIdleConns:       getEnvAsInt("DB_MAX_IDLE_CONNS", 5),
		ConnMaxLifetime:    getEnvAsInt("DB_CONN_MAX_LIFETIME", 300),

		// Redis defaults
		RedisURL:      getEnv("REDIS_URL", "redis://localhost:6380"),
		RedisPassword: getEnv("REDIS_PASSWORD", ""),
		RedisDB:       getEnvAsInt("REDIS_DB", 0),

		// Kafka defaults
		KafkaBrokers:        getEnvAsSlice("KAFKA_BROKERS", []string{"localhost:9093"}),
		SchemaRegistryURL:   getEnv("SCHEMA_REGISTRY_URL", "http://localhost:8082"),
		ConsumerGroup:       getEnv("KAFKA_CONSUMER_GROUP", "ledger-service-group"),
		ProducerRetries:     getEnvAsInt("KAFKA_PRODUCER_RETRIES", 3),
		ProducerBatchSize:   getEnvAsInt("KAFKA_PRODUCER_BATCH_SIZE", 100),
		ProducerLingerMS:    getEnvAsInt("KAFKA_PRODUCER_LINGER_MS", 10),

		// Observability defaults
		JaegerEndpoint: getEnv("JAEGER_ENDPOINT", "http://localhost:14269/api/traces"),
		MetricsEnabled: getEnvAsBool("METRICS_ENABLED", true),

		// Security defaults
		JWTSecret:     getEnv("JWT_SECRET", "your-secret-key-change-in-production"),
		EncryptionKey: getEnv("ENCRYPTION_KEY", "32-byte-key-for-aes-256-encryption"),
		TLSEnabled:    getEnvAsBool("TLS_ENABLED", false),
		TLSCertFile:   getEnv("TLS_CERT_FILE", ""),
		TLSKeyFile:    getEnv("TLS_KEY_FILE", ""),

		// Rate limiting
		RateLimit: getEnvAsInt("RATE_LIMIT", 1000),

		// Business logic defaults
		DefaultCurrency:          getEnv("DEFAULT_CURRENCY", "USD"),
		MaxTransactionAmount:     getEnvAsFloat("MAX_TRANSACTION_AMOUNT", 1000000.00),
		ReconciliationSchedule:   getEnv("RECONCILIATION_SCHEDULE", "0 2 * * *"), // Daily at 2 AM
		AuditRetentionDays:       getEnvAsInt("AUDIT_RETENTION_DAYS", 2555),       // 7 years
		IdempotencyKeyTTL:        getEnvAsInt("IDEMPOTENCY_KEY_TTL", 86400),       // 24 hours
		DistributedLockTTL:       getEnvAsInt("DISTRIBUTED_LOCK_TTL", 300),        // 5 minutes

		// Feature flags
		EnableAuditTrail:       getEnvAsBool("ENABLE_AUDIT_TRAIL", true),
		EnableReconciliation:   getEnvAsBool("ENABLE_RECONCILIATION", true),
		EnableDistributedLocks: getEnvAsBool("ENABLE_DISTRIBUTED_LOCKS", true),
		EnableMetrics:          getEnvAsBool("ENABLE_METRICS", true),
		EnableTracing:          getEnvAsBool("ENABLE_TRACING", true),
	}

	// Validate required configuration
	if err := config.validate(); err != nil {
		return nil, fmt.Errorf("configuration validation failed: %w", err)
	}

	return config, nil
}

// validate checks that required configuration is present and valid
func (c *Config) validate() error {
	if c.DatabaseURL == "" {
		return fmt.Errorf("DATABASE_URL is required")
	}

	if c.RedisURL == "" {
		return fmt.Errorf("REDIS_URL is required")
	}

	if len(c.KafkaBrokers) == 0 {
		return fmt.Errorf("KAFKA_BROKERS is required")
	}

	if c.Port <= 0 || c.Port > 65535 {
		return fmt.Errorf("PORT must be between 1 and 65535")
	}

	if c.MetricsPort <= 0 || c.MetricsPort > 65535 {
		return fmt.Errorf("METRICS_PORT must be between 1 and 65535")
	}

	if c.MaxTransactionAmount <= 0 {
		return fmt.Errorf("MAX_TRANSACTION_AMOUNT must be positive")
	}

	if c.AuditRetentionDays <= 0 {
		return fmt.Errorf("AUDIT_RETENTION_DAYS must be positive")
	}

	// Validate currency code
	if len(c.DefaultCurrency) != 3 {
		return fmt.Errorf("DEFAULT_CURRENCY must be a 3-letter ISO currency code")
	}

	// Validate TLS configuration
	if c.TLSEnabled {
		if c.TLSCertFile == "" || c.TLSKeyFile == "" {
			return fmt.Errorf("TLS_CERT_FILE and TLS_KEY_FILE are required when TLS is enabled")
		}
	}

	return nil
}

// IsDevelopment returns true if running in development mode
func (c *Config) IsDevelopment() bool {
	return c.Environment == "development"
}

// IsProduction returns true if running in production mode
func (c *Config) IsProduction() bool {
	return c.Environment == "production"
}

// GetDatabaseConfig returns database configuration as a map
func (c *Config) GetDatabaseConfig() map[string]interface{} {
	return map[string]interface{}{
		"primary_url":       c.DatabaseURL,
		"replica_url":       c.ReplicaDatabaseURL,
		"max_open_conns":    c.MaxOpenConns,
		"max_idle_conns":    c.MaxIdleConns,
		"conn_max_lifetime": c.ConnMaxLifetime,
	}
}

// GetRedisConfig returns Redis configuration as a map
func (c *Config) GetRedisConfig() map[string]interface{} {
	return map[string]interface{}{
		"url":      c.RedisURL,
		"password": c.RedisPassword,
		"db":       c.RedisDB,
	}
}

// GetKafkaConfig returns Kafka configuration as a map
func (c *Config) GetKafkaConfig() map[string]interface{} {
	return map[string]interface{}{
		"brokers":             c.KafkaBrokers,
		"schema_registry_url": c.SchemaRegistryURL,
		"consumer_group":      c.ConsumerGroup,
		"producer_retries":    c.ProducerRetries,
		"producer_batch_size": c.ProducerBatchSize,
		"producer_linger_ms":  c.ProducerLingerMS,
	}
}

// Helper functions for environment variable parsing

func getEnv(key, defaultValue string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return defaultValue
}

func getEnvAsInt(key string, defaultValue int) int {
	if value := os.Getenv(key); value != "" {
		if intValue, err := strconv.Atoi(value); err == nil {
			return intValue
		}
	}
	return defaultValue
}

func getEnvAsFloat(key string, defaultValue float64) float64 {
	if value := os.Getenv(key); value != "" {
		if floatValue, err := strconv.ParseFloat(value, 64); err == nil {
			return floatValue
		}
	}
	return defaultValue
}

func getEnvAsBool(key string, defaultValue bool) bool {
	if value := os.Getenv(key); value != "" {
		if boolValue, err := strconv.ParseBool(value); err == nil {
			return boolValue
		}
	}
	return defaultValue
}

func getEnvAsSlice(key string, defaultValue []string) []string {
	if value := os.Getenv(key); value != "" {
		return strings.Split(value, ",")
	}
	return defaultValue
}

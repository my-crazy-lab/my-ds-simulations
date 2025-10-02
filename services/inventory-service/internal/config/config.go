package config

import (
	"os"
	"strconv"
	"strings"
)

type Config struct {
	ServiceName     string
	Port            int
	MetricsPort     int
	DatabaseURL     string
	KafkaBrokers    []string
	JaegerEndpoint  string
	LogLevel        string
	ReservationTTL  int // minutes
}

func Load() (*Config, error) {
	cfg := &Config{
		ServiceName:     getEnv("SERVICE_NAME", "inventory-service"),
		Port:            getEnvAsInt("PORT", 8080),
		MetricsPort:     getEnvAsInt("METRICS_PORT", 9090),
		DatabaseURL:     getEnv("DATABASE_URL", "postgres://postgres:postgres@localhost:5432/microservices?sslmode=disable"),
		KafkaBrokers:    getEnvAsSlice("KAFKA_BROKERS", []string{"localhost:9092"}),
		JaegerEndpoint:  getEnv("JAEGER_ENDPOINT", "http://localhost:14268/api/traces"),
		LogLevel:        getEnv("LOG_LEVEL", "info"),
		ReservationTTL:  getEnvAsInt("RESERVATION_TTL", 30),
	}

	return cfg, nil
}

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

func getEnvAsSlice(key string, defaultValue []string) []string {
	if value := os.Getenv(key); value != "" {
		return strings.Split(value, ",")
	}
	return defaultValue
}

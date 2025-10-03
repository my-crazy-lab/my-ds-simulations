package config

import (
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"
)

// Config holds the configuration for a Raft node
type Config struct {
	// Node configuration
	NodeID      string
	NodeAddress string
	HTTPPort    int
	GRPCPort    int
	MetricsPort int

	// Cluster configuration
	ClusterNodes map[string]string // nodeID -> address mapping

	// Raft configuration
	ElectionTimeout        time.Duration
	HeartbeatInterval      time.Duration
	SnapshotInterval       int
	LogCompactionThreshold int

	// Storage configuration
	DataDir string
	WALDir  string

	// Observability
	PrometheusEnabled bool
	JaegerEndpoint    string
	LogLevel          string
}

// Load loads configuration from environment variables
func Load() (*Config, error) {
	cfg := &Config{
		NodeID:      getEnv("NODE_ID", "node1"),
		NodeAddress: getEnv("NODE_ADDRESS", "localhost:9090"),
		HTTPPort:    getEnvInt("HTTP_PORT", 8080),
		GRPCPort:    getEnvInt("GRPC_PORT", 9090),
		MetricsPort: getEnvInt("METRICS_PORT", 7070),

		ElectionTimeout:        getEnvDuration("ELECTION_TIMEOUT", 150*time.Millisecond),
		HeartbeatInterval:      getEnvDuration("HEARTBEAT_INTERVAL", 50*time.Millisecond),
		SnapshotInterval:       getEnvInt("SNAPSHOT_INTERVAL", 1000),
		LogCompactionThreshold: getEnvInt("LOG_COMPACTION_THRESHOLD", 10000),

		DataDir: getEnv("DATA_DIR", "./data"),
		WALDir:  getEnv("WAL_DIR", "./wal"),

		PrometheusEnabled: getEnvBool("PROMETHEUS_ENABLED", true),
		JaegerEndpoint:    getEnv("JAEGER_ENDPOINT", ""),
		LogLevel:          getEnv("LOG_LEVEL", "info"),
	}

	// Parse cluster nodes
	clusterNodes := getEnv("CLUSTER_NODES", "")
	if clusterNodes == "" {
		return nil, fmt.Errorf("CLUSTER_NODES environment variable is required")
	}

	cfg.ClusterNodes = make(map[string]string)
	for _, node := range strings.Split(clusterNodes, ",") {
		parts := strings.Split(node, ":")
		if len(parts) != 3 {
			return nil, fmt.Errorf("invalid cluster node format: %s (expected nodeID:host:port)", node)
		}
		nodeID := parts[0]
		address := parts[1] + ":" + parts[2]
		cfg.ClusterNodes[nodeID] = address
	}

	// Validate configuration
	if err := cfg.validate(); err != nil {
		return nil, fmt.Errorf("configuration validation failed: %w", err)
	}

	return cfg, nil
}

func (c *Config) validate() error {
	if c.NodeID == "" {
		return fmt.Errorf("node ID cannot be empty")
	}

	if c.NodeAddress == "" {
		return fmt.Errorf("node address cannot be empty")
	}

	if len(c.ClusterNodes) == 0 {
		return fmt.Errorf("cluster nodes cannot be empty")
	}

	if _, exists := c.ClusterNodes[c.NodeID]; !exists {
		return fmt.Errorf("current node ID %s not found in cluster nodes", c.NodeID)
	}

	if c.ElectionTimeout <= c.HeartbeatInterval {
		return fmt.Errorf("election timeout must be greater than heartbeat interval")
	}

	return nil
}

// GetPeers returns the addresses of all peer nodes (excluding current node)
func (c *Config) GetPeers() map[string]string {
	peers := make(map[string]string)
	for nodeID, address := range c.ClusterNodes {
		if nodeID != c.NodeID {
			peers[nodeID] = address
		}
	}
	return peers
}

// Helper functions for environment variable parsing

func getEnv(key, defaultValue string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return defaultValue
}

func getEnvInt(key string, defaultValue int) int {
	if value := os.Getenv(key); value != "" {
		if intValue, err := strconv.Atoi(value); err == nil {
			return intValue
		}
	}
	return defaultValue
}

func getEnvBool(key string, defaultValue bool) bool {
	if value := os.Getenv(key); value != "" {
		if boolValue, err := strconv.ParseBool(value); err == nil {
			return boolValue
		}
	}
	return defaultValue
}

func getEnvDuration(key string, defaultValue time.Duration) time.Duration {
	if value := os.Getenv(key); value != "" {
		if duration, err := time.ParseDuration(value); err == nil {
			return duration
		}
	}
	return defaultValue
}

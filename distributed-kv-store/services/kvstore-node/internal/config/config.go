package config

import (
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"
)

// ConsistencyMode represents the consistency mode of the KV store
type ConsistencyMode string

const (
	StrongConsistency    ConsistencyMode = "strong"
	EventualConsistency  ConsistencyMode = "eventual"
	HybridConsistency    ConsistencyMode = "hybrid"
)

// Config holds the configuration for a KV store node
type Config struct {
	// Node configuration
	NodeID      string
	NodeAddress string
	HTTPPort    int
	GRPCPort    int
	MetricsPort int

	// Cluster configuration
	ClusterNodes map[string]string // nodeID -> address mapping

	// Consistency configuration
	ConsistencyMode   ConsistencyMode
	ReplicationFactor int
	ReadQuorum        int
	WriteQuorum       int

	// Feature flags
	EnableRaft           bool
	EnableQuorum         bool
	HintedHandoffEnabled bool
	ReadRepairEnabled    bool
	AntiEntropyEnabled   bool

	// Timing configuration
	RequestTimeout        time.Duration
	HintedHandoffTimeout  time.Duration
	ReadRepairInterval    time.Duration
	AntiEntropyInterval   time.Duration

	// Storage configuration
	DataDir string

	// Observability
	PrometheusEnabled bool
	JaegerEndpoint    string
	LogLevel          string
}

// Load loads configuration from environment variables
func Load() (*Config, error) {
	cfg := &Config{
		NodeID:      getEnv("NODE_ID", "kvstore-node1"),
		NodeAddress: getEnv("NODE_ADDRESS", "localhost:9090"),
		HTTPPort:    getEnvInt("HTTP_PORT", 8080),
		GRPCPort:    getEnvInt("GRPC_PORT", 9090),
		MetricsPort: getEnvInt("METRICS_PORT", 7070),

		ConsistencyMode:   ConsistencyMode(getEnv("CONSISTENCY_MODE", "hybrid")),
		ReplicationFactor: getEnvInt("REPLICATION_FACTOR", 3),
		ReadQuorum:        getEnvInt("READ_QUORUM", 2),
		WriteQuorum:       getEnvInt("WRITE_QUORUM", 2),

		EnableRaft:           getEnvBool("ENABLE_RAFT", true),
		EnableQuorum:         getEnvBool("ENABLE_QUORUM", true),
		HintedHandoffEnabled: getEnvBool("HINTED_HANDOFF_ENABLED", true),
		ReadRepairEnabled:    getEnvBool("READ_REPAIR_ENABLED", true),
		AntiEntropyEnabled:   getEnvBool("ANTI_ENTROPY_ENABLED", true),

		RequestTimeout:       getEnvDuration("REQUEST_TIMEOUT", 5*time.Second),
		HintedHandoffTimeout: getEnvDuration("HINTED_HANDOFF_TIMEOUT", 10*time.Second),
		ReadRepairInterval:   getEnvDuration("READ_REPAIR_INTERVAL", 60*time.Second),
		AntiEntropyInterval:  getEnvDuration("ANTI_ENTROPY_INTERVAL", 300*time.Second),

		DataDir: getEnv("DATA_DIR", "./data"),

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

	// Validate consistency mode
	switch c.ConsistencyMode {
	case StrongConsistency, EventualConsistency, HybridConsistency:
		// Valid modes
	default:
		return fmt.Errorf("invalid consistency mode: %s", c.ConsistencyMode)
	}

	// Validate quorum settings
	if c.ReadQuorum < 1 || c.ReadQuorum > c.ReplicationFactor {
		return fmt.Errorf("read quorum must be between 1 and replication factor")
	}

	if c.WriteQuorum < 1 || c.WriteQuorum > c.ReplicationFactor {
		return fmt.Errorf("write quorum must be between 1 and replication factor")
	}

	// For strong consistency, we need R + W > N to ensure consistency
	if c.ConsistencyMode == StrongConsistency || c.ConsistencyMode == HybridConsistency {
		if c.ReadQuorum+c.WriteQuorum <= c.ReplicationFactor {
			return fmt.Errorf("for strong consistency, read quorum + write quorum must be > replication factor")
		}
	}

	// Validate feature flags
	if c.ConsistencyMode == StrongConsistency && !c.EnableRaft {
		return fmt.Errorf("strong consistency mode requires Raft to be enabled")
	}

	if c.ConsistencyMode == EventualConsistency && !c.EnableQuorum {
		return fmt.Errorf("eventual consistency mode requires quorum to be enabled")
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

// IsStrongConsistencyEnabled returns true if strong consistency is enabled
func (c *Config) IsStrongConsistencyEnabled() bool {
	return c.ConsistencyMode == StrongConsistency || c.ConsistencyMode == HybridConsistency
}

// IsEventualConsistencyEnabled returns true if eventual consistency is enabled
func (c *Config) IsEventualConsistencyEnabled() bool {
	return c.ConsistencyMode == EventualConsistency || c.ConsistencyMode == HybridConsistency
}

// GetConsistencyLevel returns the appropriate consistency level for an operation
func (c *Config) GetConsistencyLevel(requestedLevel string) string {
	// If hybrid mode, honor the requested level
	if c.ConsistencyMode == HybridConsistency {
		switch requestedLevel {
		case "strong", "eventual", "local":
			return requestedLevel
		default:
			return "eventual" // Default to eventual consistency
		}
	}

	// For fixed modes, return the configured mode
	switch c.ConsistencyMode {
	case StrongConsistency:
		return "strong"
	case EventualConsistency:
		return "eventual"
	default:
		return "eventual"
	}
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

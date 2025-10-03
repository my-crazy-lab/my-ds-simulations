package config

import (
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"
)

// Config holds all configuration for the commit log broker
type Config struct {
	// Broker identification
	BrokerID     int      `json:"broker_id"`
	ClusterNodes []string `json:"cluster_nodes"`

	// Network configuration
	HTTPPort int `json:"http_port"`
	GRPCPort int `json:"grpc_port"`

	// Storage configuration
	DataDir        string `json:"data_dir"`
	LogSegmentSize int64  `json:"log_segment_size"`
	IndexInterval  int64  `json:"index_interval"`

	// Retention configuration
	LogRetentionHours int64 `json:"log_retention_hours"`
	LogRetentionBytes int64 `json:"log_retention_bytes"`

	// Replication configuration
	ReplicationFactor   int           `json:"replication_factor"`
	MinInSyncReplicas   int           `json:"min_insync_replicas"`
	ReplicaFetchMaxWait time.Duration `json:"replica_fetch_max_wait"`
	ReplicaFetchMinBytes int32        `json:"replica_fetch_min_bytes"`

	// Producer configuration
	ProducerBatchSize     int           `json:"producer_batch_size"`
	ProducerLingerMs      time.Duration `json:"producer_linger_ms"`
	ProducerMaxRequestSize int32        `json:"producer_max_request_size"`
	ProducerAcks          string        `json:"producer_acks"` // "0", "1", "all"

	// Consumer configuration
	ConsumerSessionTimeoutMs  time.Duration `json:"consumer_session_timeout_ms"`
	ConsumerHeartbeatInterval time.Duration `json:"consumer_heartbeat_interval"`
	ConsumerMaxPollRecords    int           `json:"consumer_max_poll_records"`
	ConsumerFetchMinBytes     int32         `json:"consumer_fetch_min_bytes"`
	ConsumerFetchMaxWait      time.Duration `json:"consumer_fetch_max_wait"`

	// Log compaction configuration
	EnableLogCompaction      bool          `json:"enable_log_compaction"`
	LogCompactionInterval    time.Duration `json:"log_compaction_interval"`
	LogCompactionMinLag      time.Duration `json:"log_compaction_min_lag"`
	LogCompactionDeleteRetention time.Duration `json:"log_compaction_delete_retention"`

	// Performance tuning
	NumNetworkThreads   int `json:"num_network_threads"`
	NumIOThreads        int `json:"num_io_threads"`
	SocketSendBufferBytes int `json:"socket_send_buffer_bytes"`
	SocketReceiveBufferBytes int `json:"socket_receive_buffer_bytes"`

	// Monitoring configuration
	PrometheusPort int    `json:"prometheus_port"`
	JaegerEndpoint string `json:"jaeger_endpoint"`

	// Security configuration
	EnableSSL        bool   `json:"enable_ssl"`
	SSLKeystore      string `json:"ssl_keystore"`
	SSLKeystorePassword string `json:"ssl_keystore_password"`
	EnableSASL       bool   `json:"enable_sasl"`
	SASLMechanism    string `json:"sasl_mechanism"`

	// Advanced configuration
	EnableTransactions bool `json:"enable_transactions"`
	TransactionTimeoutMs time.Duration `json:"transaction_timeout_ms"`
	TransactionAbortTimeoutMs time.Duration `json:"transaction_abort_timeout_ms"`
}

// LoadConfig loads configuration from environment variables with sensible defaults
func LoadConfig() (*Config, error) {
	config := &Config{
		// Default values
		BrokerID:     1,
		ClusterNodes: []string{"localhost:9090"},
		HTTPPort:     8080,
		GRPCPort:     9090,
		DataDir:      "/data",
		LogSegmentSize: 1024 * 1024 * 1024, // 1GB
		IndexInterval:  4096,
		LogRetentionHours: 168, // 7 days
		LogRetentionBytes: -1,  // No size limit
		ReplicationFactor: 1,
		MinInSyncReplicas: 1,
		ReplicaFetchMaxWait: 500 * time.Millisecond,
		ReplicaFetchMinBytes: 1,
		ProducerBatchSize: 16384,
		ProducerLingerMs: 0,
		ProducerMaxRequestSize: 1024 * 1024, // 1MB
		ProducerAcks: "1",
		ConsumerSessionTimeoutMs: 30 * time.Second,
		ConsumerHeartbeatInterval: 3 * time.Second,
		ConsumerMaxPollRecords: 500,
		ConsumerFetchMinBytes: 1,
		ConsumerFetchMaxWait: 500 * time.Millisecond,
		EnableLogCompaction: false,
		LogCompactionInterval: 5 * time.Minute,
		LogCompactionMinLag: 1 * time.Minute,
		LogCompactionDeleteRetention: 24 * time.Hour,
		NumNetworkThreads: 3,
		NumIOThreads: 8,
		SocketSendBufferBytes: 102400,
		SocketReceiveBufferBytes: 102400,
		PrometheusPort: 8080,
		JaegerEndpoint: "http://jaeger:14268/api/traces",
		EnableSSL: false,
		EnableSASL: false,
		SASLMechanism: "PLAIN",
		EnableTransactions: false,
		TransactionTimeoutMs: 60 * time.Second,
		TransactionAbortTimeoutMs: 60 * time.Second,
	}

	// Override with environment variables
	if brokerID := os.Getenv("BROKER_ID"); brokerID != "" {
		if id, err := strconv.Atoi(brokerID); err == nil {
			config.BrokerID = id
		}
	}

	if clusterNodes := os.Getenv("CLUSTER_NODES"); clusterNodes != "" {
		config.ClusterNodes = strings.Split(clusterNodes, ",")
	}

	if httpPort := os.Getenv("HTTP_PORT"); httpPort != "" {
		if port, err := strconv.Atoi(httpPort); err == nil {
			config.HTTPPort = port
		}
	}

	if grpcPort := os.Getenv("GRPC_PORT"); grpcPort != "" {
		if port, err := strconv.Atoi(grpcPort); err == nil {
			config.GRPCPort = port
		}
	}

	if dataDir := os.Getenv("DATA_DIR"); dataDir != "" {
		config.DataDir = dataDir
	}

	if segmentSize := os.Getenv("LOG_SEGMENT_SIZE"); segmentSize != "" {
		if size, err := strconv.ParseInt(segmentSize, 10, 64); err == nil {
			config.LogSegmentSize = size
		}
	}

	if retentionHours := os.Getenv("LOG_RETENTION_HOURS"); retentionHours != "" {
		if hours, err := strconv.ParseInt(retentionHours, 10, 64); err == nil {
			config.LogRetentionHours = hours
		}
	}

	if retentionBytes := os.Getenv("LOG_RETENTION_BYTES"); retentionBytes != "" {
		if bytes, err := strconv.ParseInt(retentionBytes, 10, 64); err == nil {
			config.LogRetentionBytes = bytes
		}
	}

	if replicationFactor := os.Getenv("REPLICATION_FACTOR"); replicationFactor != "" {
		if factor, err := strconv.Atoi(replicationFactor); err == nil {
			config.ReplicationFactor = factor
		}
	}

	if minISR := os.Getenv("MIN_INSYNC_REPLICAS"); minISR != "" {
		if isr, err := strconv.Atoi(minISR); err == nil {
			config.MinInSyncReplicas = isr
		}
	}

	if acks := os.Getenv("PRODUCER_ACKS"); acks != "" {
		config.ProducerAcks = acks
	}

	if enableCompaction := os.Getenv("ENABLE_LOG_COMPACTION"); enableCompaction != "" {
		if enable, err := strconv.ParseBool(enableCompaction); err == nil {
			config.EnableLogCompaction = enable
		}
	}

	if compactionInterval := os.Getenv("LOG_COMPACTION_INTERVAL_MS"); compactionInterval != "" {
		if interval, err := strconv.ParseInt(compactionInterval, 10, 64); err == nil {
			config.LogCompactionInterval = time.Duration(interval) * time.Millisecond
		}
	}

	if prometheusPort := os.Getenv("PROMETHEUS_PORT"); prometheusPort != "" {
		if port, err := strconv.Atoi(prometheusPort); err == nil {
			config.PrometheusPort = port
		}
	}

	if jaegerEndpoint := os.Getenv("JAEGER_ENDPOINT"); jaegerEndpoint != "" {
		config.JaegerEndpoint = jaegerEndpoint
	}

	if enableSSL := os.Getenv("ENABLE_SSL"); enableSSL != "" {
		if enable, err := strconv.ParseBool(enableSSL); err == nil {
			config.EnableSSL = enable
		}
	}

	if enableSASL := os.Getenv("ENABLE_SASL"); enableSASL != "" {
		if enable, err := strconv.ParseBool(enableSASL); err == nil {
			config.EnableSASL = enable
		}
	}

	if enableTransactions := os.Getenv("ENABLE_TRANSACTIONS"); enableTransactions != "" {
		if enable, err := strconv.ParseBool(enableTransactions); err == nil {
			config.EnableTransactions = enable
		}
	}

	// Validate configuration
	if err := config.Validate(); err != nil {
		return nil, fmt.Errorf("invalid configuration: %w", err)
	}

	return config, nil
}

// Validate validates the configuration
func (c *Config) Validate() error {
	if c.BrokerID <= 0 {
		return fmt.Errorf("broker_id must be positive")
	}

	if len(c.ClusterNodes) == 0 {
		return fmt.Errorf("cluster_nodes cannot be empty")
	}

	if c.HTTPPort <= 0 || c.HTTPPort > 65535 {
		return fmt.Errorf("http_port must be between 1 and 65535")
	}

	if c.GRPCPort <= 0 || c.GRPCPort > 65535 {
		return fmt.Errorf("grpc_port must be between 1 and 65535")
	}

	if c.DataDir == "" {
		return fmt.Errorf("data_dir cannot be empty")
	}

	if c.LogSegmentSize <= 0 {
		return fmt.Errorf("log_segment_size must be positive")
	}

	if c.ReplicationFactor <= 0 {
		return fmt.Errorf("replication_factor must be positive")
	}

	if c.MinInSyncReplicas <= 0 || c.MinInSyncReplicas > c.ReplicationFactor {
		return fmt.Errorf("min_insync_replicas must be positive and <= replication_factor")
	}

	if c.ProducerAcks != "0" && c.ProducerAcks != "1" && c.ProducerAcks != "all" {
		return fmt.Errorf("producer_acks must be '0', '1', or 'all'")
	}

	if c.ConsumerSessionTimeoutMs <= 0 {
		return fmt.Errorf("consumer_session_timeout_ms must be positive")
	}

	if c.ConsumerHeartbeatInterval <= 0 {
		return fmt.Errorf("consumer_heartbeat_interval must be positive")
	}

	if c.ConsumerHeartbeatInterval >= c.ConsumerSessionTimeoutMs {
		return fmt.Errorf("consumer_heartbeat_interval must be less than session_timeout")
	}

	return nil
}

// GetRetentionDuration returns the retention duration
func (c *Config) GetRetentionDuration() time.Duration {
	return time.Duration(c.LogRetentionHours) * time.Hour
}

// IsLeader checks if this broker should be the leader for a given partition
func (c *Config) IsLeader(topic string, partition int) bool {
	// Simple hash-based leader selection
	// In a real implementation, this would use a more sophisticated algorithm
	hash := 0
	for _, b := range topic {
		hash = hash*31 + int(b)
	}
	hash += partition
	leaderIndex := hash % len(c.ClusterNodes)
	
	// Find our position in the cluster
	ourIndex := -1
	for i, node := range c.ClusterNodes {
		if strings.Contains(node, fmt.Sprintf(":%d", c.GRPCPort)) {
			ourIndex = i
			break
		}
	}
	
	return ourIndex == leaderIndex
}

// GetClusterSize returns the number of nodes in the cluster
func (c *Config) GetClusterSize() int {
	return len(c.ClusterNodes)
}

// GetOtherNodes returns the list of other nodes in the cluster
func (c *Config) GetOtherNodes() []string {
	var others []string
	myNode := fmt.Sprintf(":%d", c.GRPCPort)
	
	for _, node := range c.ClusterNodes {
		if !strings.Contains(node, myNode) {
			others = append(others, node)
		}
	}
	
	return others
}

// String returns a string representation of the config
func (c *Config) String() string {
	return fmt.Sprintf("Broker{ID:%d, HTTP:%d, gRPC:%d, DataDir:%s, Cluster:%v}",
		c.BrokerID, c.HTTPPort, c.GRPCPort, c.DataDir, c.ClusterNodes)
}

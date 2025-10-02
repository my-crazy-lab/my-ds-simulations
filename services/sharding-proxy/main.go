package main

import (
	"context"
	"crypto/md5"
	"database/sql"
	"encoding/hex"
	"fmt"
	"log"
	"net"
	"os"
	"strconv"
	"strings"
	"sync"
	"time"

	_ "github.com/lib/pq"
	"github.com/sirupsen/logrus"
)

// ShardingProxy handles database sharding and routing
type ShardingProxy struct {
	primaryDB   *sql.DB
	replicaDB   *sql.DB
	shards      map[string]*sql.DB
	shardRing   *ConsistentHashRing
	logger      *logrus.Logger
	mu          sync.RWMutex
	rebalancer  *ShardRebalancer
}

// ConsistentHashRing implements consistent hashing for shard selection
type ConsistentHashRing struct {
	nodes    []string
	replicas int
	ring     map[uint32]string
	sortedKeys []uint32
	mu       sync.RWMutex
}

// ShardRebalancer handles online shard rebalancing
type ShardRebalancer struct {
	proxy           *ShardingProxy
	migrationStatus map[string]*MigrationStatus
	mu              sync.RWMutex
}

// MigrationStatus tracks the status of data migration
type MigrationStatus struct {
	FromShard    string
	ToShard      string
	KeyRange     KeyRange
	Status       string // PENDING, IN_PROGRESS, COMPLETED, FAILED
	Progress     float64
	StartedAt    time.Time
	CompletedAt  *time.Time
	ErrorMessage string
}

// KeyRange represents a range of keys being migrated
type KeyRange struct {
	Start string
	End   string
}

func main() {
	logger := logrus.New()
	logger.SetLevel(logrus.InfoLevel)
	logger.SetFormatter(&logrus.JSONFormatter{})

	// Initialize sharding proxy
	proxy, err := NewShardingProxy(logger)
	if err != nil {
		logger.Fatalf("Failed to initialize sharding proxy: %v", err)
	}
	defer proxy.Close()

	// Start rebalancer
	go proxy.rebalancer.Start(context.Background())

	// Start proxy server
	listener, err := net.Listen("tcp", ":5432")
	if err != nil {
		logger.Fatalf("Failed to start listener: %v", err)
	}
	defer listener.Close()

	logger.Info("Sharding proxy started on port 5432")

	for {
		conn, err := listener.Accept()
		if err != nil {
			logger.Errorf("Failed to accept connection: %v", err)
			continue
		}

		go proxy.handleConnection(conn)
	}
}

// NewShardingProxy creates a new sharding proxy
func NewShardingProxy(logger *logrus.Logger) (*ShardingProxy, error) {
	primaryURL := os.Getenv("PRIMARY_URL")
	replicaURL := os.Getenv("REPLICA_URL")
	shard1URL := os.Getenv("SHARD1_URL")
	shard2URL := os.Getenv("SHARD2_URL")

	// Connect to primary database
	primaryDB, err := sql.Open("postgres", primaryURL)
	if err != nil {
		return nil, fmt.Errorf("failed to connect to primary: %w", err)
	}

	// Connect to replica database
	replicaDB, err := sql.Open("postgres", replicaURL)
	if err != nil {
		return nil, fmt.Errorf("failed to connect to replica: %w", err)
	}

	// Connect to shards
	shards := make(map[string]*sql.DB)
	
	shard1DB, err := sql.Open("postgres", shard1URL)
	if err != nil {
		return nil, fmt.Errorf("failed to connect to shard1: %w", err)
	}
	shards["shard1"] = shard1DB

	shard2DB, err := sql.Open("postgres", shard2URL)
	if err != nil {
		return nil, fmt.Errorf("failed to connect to shard2: %w", err)
	}
	shards["shard2"] = shard2DB

	// Initialize consistent hash ring
	ring := NewConsistentHashRing(3)
	ring.AddNode("shard1")
	ring.AddNode("shard2")

	proxy := &ShardingProxy{
		primaryDB: primaryDB,
		replicaDB: replicaDB,
		shards:    shards,
		shardRing: ring,
		logger:    logger,
	}

	// Initialize rebalancer
	proxy.rebalancer = &ShardRebalancer{
		proxy:           proxy,
		migrationStatus: make(map[string]*MigrationStatus),
	}

	return proxy, nil
}

// NewConsistentHashRing creates a new consistent hash ring
func NewConsistentHashRing(replicas int) *ConsistentHashRing {
	return &ConsistentHashRing{
		replicas: replicas,
		ring:     make(map[uint32]string),
	}
}

// AddNode adds a node to the hash ring
func (c *ConsistentHashRing) AddNode(node string) {
	c.mu.Lock()
	defer c.mu.Unlock()

	for i := 0; i < c.replicas; i++ {
		key := c.hash(fmt.Sprintf("%s:%d", node, i))
		c.ring[key] = node
		c.sortedKeys = append(c.sortedKeys, key)
	}
	c.sortKeys()
	c.nodes = append(c.nodes, node)
}

// RemoveNode removes a node from the hash ring
func (c *ConsistentHashRing) RemoveNode(node string) {
	c.mu.Lock()
	defer c.mu.Unlock()

	for i := 0; i < c.replicas; i++ {
		key := c.hash(fmt.Sprintf("%s:%d", node, i))
		delete(c.ring, key)
	}

	// Remove from sorted keys
	newKeys := make([]uint32, 0)
	for _, key := range c.sortedKeys {
		if c.ring[key] != node {
			newKeys = append(newKeys, key)
		}
	}
	c.sortedKeys = newKeys

	// Remove from nodes
	newNodes := make([]string, 0)
	for _, n := range c.nodes {
		if n != node {
			newNodes = append(newNodes, n)
		}
	}
	c.nodes = newNodes
}

// GetNode returns the node for a given key
func (c *ConsistentHashRing) GetNode(key string) string {
	c.mu.RLock()
	defer c.mu.RUnlock()

	if len(c.ring) == 0 {
		return ""
	}

	hash := c.hash(key)
	
	// Find the first node with hash >= key hash
	for _, k := range c.sortedKeys {
		if k >= hash {
			return c.ring[k]
		}
	}

	// Wrap around to the first node
	return c.ring[c.sortedKeys[0]]
}

// hash generates a hash for the given key
func (c *ConsistentHashRing) hash(key string) uint32 {
	h := md5.Sum([]byte(key))
	return uint32(h[0])<<24 | uint32(h[1])<<16 | uint32(h[2])<<8 | uint32(h[3])
}

// sortKeys sorts the keys in the ring
func (c *ConsistentHashRing) sortKeys() {
	// Simple bubble sort for small arrays
	n := len(c.sortedKeys)
	for i := 0; i < n-1; i++ {
		for j := 0; j < n-i-1; j++ {
			if c.sortedKeys[j] > c.sortedKeys[j+1] {
				c.sortedKeys[j], c.sortedKeys[j+1] = c.sortedKeys[j+1], c.sortedKeys[j]
			}
		}
	}
}

// handleConnection handles incoming database connections
func (p *ShardingProxy) handleConnection(conn net.Conn) {
	defer conn.Close()

	p.logger.Info("New connection established")

	// Simple protocol handler - in production, implement full PostgreSQL protocol
	buffer := make([]byte, 4096)
	for {
		n, err := conn.Read(buffer)
		if err != nil {
			p.logger.Errorf("Connection read error: %v", err)
			return
		}

		query := string(buffer[:n])
		p.logger.Infof("Received query: %s", query)

		// Route query based on type and sharding key
		result, err := p.routeQuery(query)
		if err != nil {
			p.logger.Errorf("Query routing error: %v", err)
			conn.Write([]byte(fmt.Sprintf("ERROR: %v\n", err)))
			continue
		}

		conn.Write([]byte(result))
	}
}

// routeQuery routes queries to appropriate database based on sharding logic
func (p *ShardingProxy) routeQuery(query string) (string, error) {
	query = strings.TrimSpace(strings.ToUpper(query))

	// Determine query type
	if strings.HasPrefix(query, "SELECT") {
		return p.routeSelectQuery(query)
	} else if strings.HasPrefix(query, "INSERT") {
		return p.routeInsertQuery(query)
	} else if strings.HasPrefix(query, "UPDATE") {
		return p.routeUpdateQuery(query)
	} else if strings.HasPrefix(query, "DELETE") {
		return p.routeDeleteQuery(query)
	}

	// Default to primary for DDL and other operations
	return p.executeOnPrimary(query)
}

// routeSelectQuery routes SELECT queries
func (p *ShardingProxy) routeSelectQuery(query string) (string, error) {
	// Extract sharding key from WHERE clause
	shardingKey := p.extractShardingKey(query)
	
	if shardingKey != "" {
		// Route to specific shard
		shard := p.shardRing.GetNode(shardingKey)
		return p.executeOnShard(query, shard)
	}

	// If no sharding key, check if it's an analytical query
	if p.isAnalyticalQuery(query) {
		// Route to replica for read-only analytical queries
		return p.executeOnReplica(query)
	}

	// Default to primary
	return p.executeOnPrimary(query)
}

// routeInsertQuery routes INSERT queries
func (p *ShardingProxy) routeInsertQuery(query string) (string, error) {
	shardingKey := p.extractShardingKeyFromInsert(query)
	
	if shardingKey != "" {
		shard := p.shardRing.GetNode(shardingKey)
		return p.executeOnShard(query, shard)
	}

	return p.executeOnPrimary(query)
}

// routeUpdateQuery routes UPDATE queries
func (p *ShardingProxy) routeUpdateQuery(query string) (string, error) {
	shardingKey := p.extractShardingKey(query)
	
	if shardingKey != "" {
		shard := p.shardRing.GetNode(shardingKey)
		return p.executeOnShard(query, shard)
	}

	// If no sharding key, might need to execute on all shards
	return p.executeOnAllShards(query)
}

// routeDeleteQuery routes DELETE queries
func (p *ShardingProxy) routeDeleteQuery(query string) (string, error) {
	shardingKey := p.extractShardingKey(query)
	
	if shardingKey != "" {
		shard := p.shardRing.GetNode(shardingKey)
		return p.executeOnShard(query, shard)
	}

	// If no sharding key, might need to execute on all shards
	return p.executeOnAllShards(query)
}

// extractShardingKey extracts sharding key from query
func (p *ShardingProxy) extractShardingKey(query string) string {
	// Simple extraction - in production, use proper SQL parser
	if strings.Contains(query, "user_id") {
		// Extract user_id value
		parts := strings.Split(query, "user_id")
		if len(parts) > 1 {
			// Simple regex-like extraction
			value := strings.TrimSpace(parts[1])
			if strings.HasPrefix(value, "=") {
				value = strings.TrimSpace(value[1:])
				value = strings.Trim(value, "'\"")
				return value
			}
		}
	}
	
	if strings.Contains(query, "sku") {
		// Extract SKU value for inventory sharding
		parts := strings.Split(query, "sku")
		if len(parts) > 1 {
			value := strings.TrimSpace(parts[1])
			if strings.HasPrefix(value, "=") {
				value = strings.TrimSpace(value[1:])
				value = strings.Trim(value, "'\"")
				return value
			}
		}
	}

	return ""
}

// extractShardingKeyFromInsert extracts sharding key from INSERT query
func (p *ShardingProxy) extractShardingKeyFromInsert(query string) string {
	// Simple extraction for INSERT queries
	// In production, use proper SQL parser
	return ""
}

// isAnalyticalQuery determines if query is analytical
func (p *ShardingProxy) isAnalyticalQuery(query string) bool {
	analyticalKeywords := []string{"COUNT", "SUM", "AVG", "GROUP BY", "ORDER BY", "HAVING"}
	
	for _, keyword := range analyticalKeywords {
		if strings.Contains(query, keyword) {
			return true
		}
	}
	
	return false
}

// executeOnPrimary executes query on primary database
func (p *ShardingProxy) executeOnPrimary(query string) (string, error) {
	rows, err := p.primaryDB.Query(query)
	if err != nil {
		return "", err
	}
	defer rows.Close()

	return "Query executed on primary\n", nil
}

// executeOnReplica executes query on replica database
func (p *ShardingProxy) executeOnReplica(query string) (string, error) {
	rows, err := p.replicaDB.Query(query)
	if err != nil {
		return "", err
	}
	defer rows.Close()

	return "Query executed on replica\n", nil
}

// executeOnShard executes query on specific shard
func (p *ShardingProxy) executeOnShard(query string, shardName string) (string, error) {
	p.mu.RLock()
	shard, exists := p.shards[shardName]
	p.mu.RUnlock()

	if !exists {
		return "", fmt.Errorf("shard %s not found", shardName)
	}

	rows, err := shard.Query(query)
	if err != nil {
		return "", err
	}
	defer rows.Close()

	return fmt.Sprintf("Query executed on %s\n", shardName), nil
}

// executeOnAllShards executes query on all shards
func (p *ShardingProxy) executeOnAllShards(query string) (string, error) {
	results := make([]string, 0)
	
	p.mu.RLock()
	defer p.mu.RUnlock()

	for shardName, shard := range p.shards {
		rows, err := shard.Query(query)
		if err != nil {
			p.logger.Errorf("Error executing on shard %s: %v", shardName, err)
			continue
		}
		rows.Close()
		results = append(results, fmt.Sprintf("Executed on %s", shardName))
	}

	return strings.Join(results, "\n") + "\n", nil
}

// Start starts the shard rebalancer
func (r *ShardRebalancer) Start(ctx context.Context) {
	ticker := time.NewTicker(30 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			r.checkAndRebalance()
		}
	}
}

// checkAndRebalance checks for hot shards and triggers rebalancing
func (r *ShardRebalancer) checkAndRebalance() {
	// Monitor shard metrics and detect hot spots
	hotShards := r.detectHotShards()
	
	for _, hotShard := range hotShards {
		r.proxy.logger.Infof("Detected hot shard: %s", hotShard)
		
		// Trigger rebalancing
		err := r.rebalanceShard(hotShard)
		if err != nil {
			r.proxy.logger.Errorf("Failed to rebalance shard %s: %v", hotShard, err)
		}
	}
}

// detectHotShards detects shards with high load
func (r *ShardRebalancer) detectHotShards() []string {
	// In production, implement proper metrics collection and analysis
	// For now, return empty slice
	return []string{}
}

// rebalanceShard performs online shard rebalancing
func (r *ShardRebalancer) rebalanceShard(shardName string) error {
	r.mu.Lock()
	defer r.mu.Unlock()

	// Check if migration is already in progress
	if status, exists := r.migrationStatus[shardName]; exists && status.Status == "IN_PROGRESS" {
		return fmt.Errorf("migration already in progress for shard %s", shardName)
	}

	// Create migration status
	migration := &MigrationStatus{
		FromShard: shardName,
		ToShard:   r.selectTargetShard(shardName),
		Status:    "PENDING",
		StartedAt: time.Now(),
	}

	r.migrationStatus[shardName] = migration

	// Start migration in background
	go r.performMigration(migration)

	return nil
}

// selectTargetShard selects the target shard for migration
func (r *ShardRebalancer) selectTargetShard(fromShard string) string {
	// Simple selection - choose the other shard
	if fromShard == "shard1" {
		return "shard2"
	}
	return "shard1"
}

// performMigration performs the actual data migration
func (r *ShardRebalancer) performMigration(migration *MigrationStatus) {
	r.proxy.logger.Infof("Starting migration from %s to %s", migration.FromShard, migration.ToShard)

	migration.Status = "IN_PROGRESS"

	// In production, implement:
	// 1. Identify keys to migrate
	// 2. Set up double-write to both shards
	// 3. Migrate existing data in batches
	// 4. Update routing rules
	// 5. Remove old data

	// Simulate migration
	time.Sleep(10 * time.Second)

	migration.Status = "COMPLETED"
	now := time.Now()
	migration.CompletedAt = &now
	migration.Progress = 100.0

	r.proxy.logger.Infof("Migration completed from %s to %s", migration.FromShard, migration.ToShard)
}

// Close closes all database connections
func (p *ShardingProxy) Close() {
	if p.primaryDB != nil {
		p.primaryDB.Close()
	}
	if p.replicaDB != nil {
		p.replicaDB.Close()
	}
	for _, shard := range p.shards {
		shard.Close()
	}
}

package kvstore

import (
	"context"
	"fmt"
	"log"
	"sync"
	"time"

	"../config"
	"../storage"
	"../raft"
	"../quorum"
)

// Store represents the distributed KV store
type Store struct {
	mu sync.RWMutex

	// Configuration
	config *config.Config

	// Storage layer
	storage storage.Storage

	// Consistency engines
	raftEngine   *raft.Engine   // For strong consistency (CP)
	quorumEngine *quorum.Engine // For eventual consistency (AP)

	// Background processes
	readRepairTicker   *time.Ticker
	antiEntropyTicker  *time.Ticker
	stopCh             chan struct{}

	// Metrics and monitoring
	operationCount map[string]int64
	lastOperation  time.Time
}

// NewStore creates a new distributed KV store
func NewStore(cfg *config.Config, storage storage.Storage) (*Store, error) {
	store := &Store{
		config:         cfg,
		storage:        storage,
		operationCount: make(map[string]int64),
		stopCh:         make(chan struct{}),
	}

	// Initialize Raft engine for strong consistency
	if cfg.IsStrongConsistencyEnabled() {
		raftEngine, err := raft.NewEngine(cfg, storage)
		if err != nil {
			return nil, fmt.Errorf("failed to initialize Raft engine: %w", err)
		}
		store.raftEngine = raftEngine
	}

	// Initialize Quorum engine for eventual consistency
	if cfg.IsEventualConsistencyEnabled() {
		quorumEngine, err := quorum.NewEngine(cfg, storage)
		if err != nil {
			return nil, fmt.Errorf("failed to initialize Quorum engine: %w", err)
		}
		store.quorumEngine = quorumEngine
	}

	return store, nil
}

// Start starts the KV store and background processes
func (s *Store) Start() error {
	log.Printf("Starting KV store node %s", s.config.NodeID)

	// Start Raft engine
	if s.raftEngine != nil {
		if err := s.raftEngine.Start(); err != nil {
			return fmt.Errorf("failed to start Raft engine: %w", err)
		}
	}

	// Start Quorum engine
	if s.quorumEngine != nil {
		if err := s.quorumEngine.Start(); err != nil {
			return fmt.Errorf("failed to start Quorum engine: %w", err)
		}
	}

	// Start background processes
	s.startBackgroundProcesses()

	log.Printf("KV store node %s started successfully", s.config.NodeID)
	return nil
}

// Stop stops the KV store and background processes
func (s *Store) Stop() {
	log.Printf("Stopping KV store node %s", s.config.NodeID)

	// Stop background processes
	close(s.stopCh)
	if s.readRepairTicker != nil {
		s.readRepairTicker.Stop()
	}
	if s.antiEntropyTicker != nil {
		s.antiEntropyTicker.Stop()
	}

	// Stop engines
	if s.raftEngine != nil {
		s.raftEngine.Stop()
	}
	if s.quorumEngine != nil {
		s.quorumEngine.Stop()
	}

	log.Printf("KV store node %s stopped", s.config.NodeID)
}

// Get retrieves a value with the specified consistency level
func (s *Store) Get(key, consistencyLevel string) (string, int64, error) {
	s.mu.Lock()
	s.operationCount["get"]++
	s.lastOperation = time.Now()
	s.mu.Unlock()

	// Determine actual consistency level
	actualLevel := s.config.GetConsistencyLevel(consistencyLevel)

	switch actualLevel {
	case "strong":
		return s.getStrong(key)
	case "eventual":
		return s.getEventual(key)
	case "local":
		return s.getLocal(key)
	default:
		return s.getEventual(key)
	}
}

// Put stores a value with the specified consistency level
func (s *Store) Put(key, value, consistencyLevel string) (int64, error) {
	s.mu.Lock()
	s.operationCount["put"]++
	s.lastOperation = time.Now()
	s.mu.Unlock()

	// Determine actual consistency level
	actualLevel := s.config.GetConsistencyLevel(consistencyLevel)

	switch actualLevel {
	case "strong":
		return s.putStrong(key, value)
	case "eventual":
		return s.putEventual(key, value)
	default:
		return s.putEventual(key, value)
	}
}

// PutIfVersion performs a conditional put based on version
func (s *Store) PutIfVersion(key, value string, expectedVersion int64, consistencyLevel string) (int64, error) {
	s.mu.Lock()
	s.operationCount["put_if_version"]++
	s.lastOperation = time.Now()
	s.mu.Unlock()

	// Determine actual consistency level
	actualLevel := s.config.GetConsistencyLevel(consistencyLevel)

	switch actualLevel {
	case "strong":
		return s.putIfVersionStrong(key, value, expectedVersion)
	case "eventual":
		return s.putIfVersionEventual(key, value, expectedVersion)
	default:
		return s.putIfVersionEventual(key, value, expectedVersion)
	}
}

// Delete removes a key with the specified consistency level
func (s *Store) Delete(key, consistencyLevel string) error {
	s.mu.Lock()
	s.operationCount["delete"]++
	s.lastOperation = time.Now()
	s.mu.Unlock()

	// Determine actual consistency level
	actualLevel := s.config.GetConsistencyLevel(consistencyLevel)

	switch actualLevel {
	case "strong":
		return s.deleteStrong(key)
	case "eventual":
		return s.deleteEventual(key)
	default:
		return s.deleteEventual(key)
	}
}

// Batch performs multiple operations atomically
func (s *Store) Batch(operations []interface{}, consistencyLevel string) ([]interface{}, error) {
	s.mu.Lock()
	s.operationCount["batch"]++
	s.lastOperation = time.Now()
	s.mu.Unlock()

	// Determine actual consistency level
	actualLevel := s.config.GetConsistencyLevel(consistencyLevel)

	switch actualLevel {
	case "strong":
		return s.batchStrong(operations)
	case "eventual":
		return s.batchEventual(operations)
	default:
		return s.batchEventual(operations)
	}
}

// Strong consistency operations (via Raft)

func (s *Store) getStrong(key string) (string, int64, error) {
	if s.raftEngine == nil {
		return "", 0, fmt.Errorf("strong consistency not enabled")
	}
	return s.raftEngine.Get(key)
}

func (s *Store) putStrong(key, value string) (int64, error) {
	if s.raftEngine == nil {
		return 0, fmt.Errorf("strong consistency not enabled")
	}
	return s.raftEngine.Put(key, value)
}

func (s *Store) putIfVersionStrong(key, value string, expectedVersion int64) (int64, error) {
	if s.raftEngine == nil {
		return 0, fmt.Errorf("strong consistency not enabled")
	}
	return s.raftEngine.PutIfVersion(key, value, expectedVersion)
}

func (s *Store) deleteStrong(key string) error {
	if s.raftEngine == nil {
		return fmt.Errorf("strong consistency not enabled")
	}
	return s.raftEngine.Delete(key)
}

func (s *Store) batchStrong(operations []interface{}) ([]interface{}, error) {
	if s.raftEngine == nil {
		return nil, fmt.Errorf("strong consistency not enabled")
	}
	return s.raftEngine.Batch(operations)
}

// Eventual consistency operations (via Quorum)

func (s *Store) getEventual(key string) (string, int64, error) {
	if s.quorumEngine == nil {
		return "", 0, fmt.Errorf("eventual consistency not enabled")
	}
	return s.quorumEngine.Get(key, s.config.ReadQuorum)
}

func (s *Store) putEventual(key, value string) (int64, error) {
	if s.quorumEngine == nil {
		return 0, fmt.Errorf("eventual consistency not enabled")
	}
	return s.quorumEngine.Put(key, value, s.config.WriteQuorum)
}

func (s *Store) putIfVersionEventual(key, value string, expectedVersion int64) (int64, error) {
	if s.quorumEngine == nil {
		return 0, fmt.Errorf("eventual consistency not enabled")
	}
	return s.quorumEngine.PutIfVersion(key, value, expectedVersion, s.config.WriteQuorum)
}

func (s *Store) deleteEventual(key string) error {
	if s.quorumEngine == nil {
		return fmt.Errorf("eventual consistency not enabled")
	}
	return s.quorumEngine.Delete(key, s.config.WriteQuorum)
}

func (s *Store) batchEventual(operations []interface{}) ([]interface{}, error) {
	if s.quorumEngine == nil {
		return nil, fmt.Errorf("eventual consistency not enabled")
	}
	return s.quorumEngine.Batch(operations, s.config.WriteQuorum)
}

// Local operations (no consistency guarantees)

func (s *Store) getLocal(key string) (string, int64, error) {
	return s.storage.Get(key)
}

// Background processes

func (s *Store) startBackgroundProcesses() {
	// Start read repair process
	if s.config.ReadRepairEnabled {
		s.readRepairTicker = time.NewTicker(s.config.ReadRepairInterval)
		go s.readRepairLoop()
	}

	// Start anti-entropy process
	if s.config.AntiEntropyEnabled {
		s.antiEntropyTicker = time.NewTicker(s.config.AntiEntropyInterval)
		go s.antiEntropyLoop()
	}
}

func (s *Store) readRepairLoop() {
	for {
		select {
		case <-s.readRepairTicker.C:
			s.performReadRepair()
		case <-s.stopCh:
			return
		}
	}
}

func (s *Store) antiEntropyLoop() {
	for {
		select {
		case <-s.antiEntropyTicker.C:
			s.performAntiEntropy()
		case <-s.stopCh:
			return
		}
	}
}

func (s *Store) performReadRepair() {
	if s.quorumEngine != nil {
		s.quorumEngine.PerformReadRepair()
	}
}

func (s *Store) performAntiEntropy() {
	if s.quorumEngine != nil {
		s.quorumEngine.PerformAntiEntropy()
	}
}

// Admin operations

func (s *Store) TriggerReadRepair() error {
	if s.quorumEngine == nil {
		return fmt.Errorf("quorum engine not available")
	}
	go s.performReadRepair()
	return nil
}

func (s *Store) TriggerAntiEntropy() error {
	if s.quorumEngine == nil {
		return fmt.Errorf("quorum engine not available")
	}
	go s.performAntiEntropy()
	return nil
}

func (s *Store) GetStatus() map[string]interface{} {
	s.mu.RLock()
	defer s.mu.RUnlock()

	status := map[string]interface{}{
		"node_id":          s.config.NodeID,
		"consistency_mode": s.config.ConsistencyMode,
		"operation_count":  s.operationCount,
		"last_operation":   s.lastOperation,
	}

	if s.raftEngine != nil {
		status["raft_status"] = s.raftEngine.GetStatus()
	}

	if s.quorumEngine != nil {
		status["quorum_status"] = s.quorumEngine.GetStatus()
	}

	return status
}

func (s *Store) GetNodes() map[string]interface{} {
	nodes := make(map[string]interface{})

	// Add information from both engines
	if s.raftEngine != nil {
		raftNodes := s.raftEngine.GetNodes()
		for nodeID, info := range raftNodes {
			nodes[nodeID] = info
		}
	}

	if s.quorumEngine != nil {
		quorumNodes := s.quorumEngine.GetNodes()
		for nodeID, info := range quorumNodes {
			if existing, exists := nodes[nodeID]; exists {
				// Merge information
				if existingMap, ok := existing.(map[string]interface{}); ok {
					if infoMap, ok := info.(map[string]interface{}); ok {
						existingMap["quorum_status"] = infoMap
					}
				}
			} else {
				nodes[nodeID] = info
			}
		}
	}

	return nodes
}

func (s *Store) GetConsistencyStatus() map[string]interface{} {
	status := map[string]interface{}{
		"consistency_mode":     s.config.ConsistencyMode,
		"strong_enabled":       s.config.IsStrongConsistencyEnabled(),
		"eventual_enabled":     s.config.IsEventualConsistencyEnabled(),
		"read_quorum":          s.config.ReadQuorum,
		"write_quorum":         s.config.WriteQuorum,
		"replication_factor":   s.config.ReplicationFactor,
		"read_repair_enabled":  s.config.ReadRepairEnabled,
		"anti_entropy_enabled": s.config.AntiEntropyEnabled,
	}

	if s.raftEngine != nil {
		status["raft_consistency"] = s.raftEngine.GetConsistencyStatus()
	}

	if s.quorumEngine != nil {
		status["quorum_consistency"] = s.quorumEngine.GetConsistencyStatus()
	}

	return status
}

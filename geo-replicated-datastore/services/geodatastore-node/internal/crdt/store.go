package crdt

import (
	"encoding/json"
	"fmt"
	"sync"
	"time"

	"../config"
	"../storage"
)

// CRDTType represents the type of CRDT
type CRDTType string

const (
	GCounterType   CRDTType = "g_counter"
	PNCounterType  CRDTType = "pn_counter"
	GSetType       CRDTType = "g_set"
	TwoPSetType    CRDTType = "2p_set"
	ORSetType      CRDTType = "or_set"
	LWWRegisterType CRDTType = "lww_register"
	MVRegisterType  CRDTType = "mv_register"
	ORMapType      CRDTType = "or_map"
)

// VectorClock represents a vector clock for causal ordering
type VectorClock map[string]int64

// CRDT represents a conflict-free replicated data type
type CRDT interface {
	Type() CRDTType
	Merge(other CRDT) error
	Clone() CRDT
	GetVectorClock() VectorClock
	SetVectorClock(VectorClock)
	Serialize() ([]byte, error)
	Deserialize([]byte) error
}

// Metadata contains CRDT metadata
type Metadata struct {
	Type        CRDTType     `json:"type"`
	Key         string       `json:"key"`
	NodeID      string       `json:"node_id"`
	Region      string       `json:"region"`
	CreatedAt   time.Time    `json:"created_at"`
	UpdatedAt   time.Time    `json:"updated_at"`
	VectorClock VectorClock  `json:"vector_clock"`
	Version     int64        `json:"version"`
}

// Conflict represents a detected conflict
type Conflict struct {
	ID          string      `json:"id"`
	Key         string      `json:"key"`
	Type        CRDTType    `json:"type"`
	Values      []CRDT      `json:"values"`
	DetectedAt  time.Time   `json:"detected_at"`
	Resolved    bool        `json:"resolved"`
	Resolution  string      `json:"resolution,omitempty"`
}

// Store manages CRDT operations and storage
type Store struct {
	mu          sync.RWMutex
	config      *config.Config
	storage     storage.Storage
	crdts       map[string]CRDT
	metadata    map[string]*Metadata
	conflicts   map[string]*Conflict
	vectorClock VectorClock
	startTime   time.Time
}

// NewStore creates a new CRDT store
func NewStore(cfg *config.Config, storage storage.Storage) (*Store, error) {
	store := &Store{
		config:      cfg,
		storage:     storage,
		crdts:       make(map[string]CRDT),
		metadata:    make(map[string]*Metadata),
		conflicts:   make(map[string]*Conflict),
		vectorClock: make(VectorClock),
		startTime:   time.Now(),
	}

	// Initialize vector clock
	store.vectorClock[cfg.NodeID] = 0

	// Load existing CRDTs from storage
	if err := store.loadFromStorage(); err != nil {
		return nil, fmt.Errorf("failed to load CRDTs from storage: %w", err)
	}

	return store, nil
}

// CreateCounter creates a new counter CRDT
func (s *Store) CreateCounter(key string, counterType string, initialValue int64) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	if _, exists := s.crdts[key]; exists {
		return fmt.Errorf("CRDT with key %s already exists", key)
	}

	var counter CRDT
	var err error

	switch CRDTType(counterType) {
	case GCounterType:
		counter = NewGCounter(s.config.NodeID, initialValue)
	case PNCounterType:
		counter = NewPNCounter(s.config.NodeID, initialValue)
	default:
		return fmt.Errorf("unsupported counter type: %s", counterType)
	}

	// Update vector clock
	s.vectorClock[s.config.NodeID]++
	counter.SetVectorClock(s.copyVectorClock())

	// Store CRDT
	s.crdts[key] = counter
	s.metadata[key] = &Metadata{
		Type:        CRDTType(counterType),
		Key:         key,
		NodeID:      s.config.NodeID,
		Region:      s.config.Region,
		CreatedAt:   time.Now(),
		UpdatedAt:   time.Now(),
		VectorClock: s.copyVectorClock(),
		Version:     1,
	}

	// Persist to storage
	return s.persistCRDT(key, counter)
}

// GetCounter retrieves a counter value
func (s *Store) GetCounter(key string, consistency string) (int64, *Metadata, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	crdt, exists := s.crdts[key]
	if !exists {
		return 0, nil, fmt.Errorf("counter with key %s not found", key)
	}

	metadata := s.metadata[key]
	if metadata == nil {
		return 0, nil, fmt.Errorf("metadata for key %s not found", key)
	}

	var value int64
	switch counter := crdt.(type) {
	case *GCounter:
		value = counter.Value()
	case *PNCounter:
		value = counter.Value()
	default:
		return 0, nil, fmt.Errorf("key %s is not a counter", key)
	}

	// Handle read repair for eventual consistency
	if consistency == "eventual" {
		go s.triggerReadRepair(key)
	}

	return value, metadata, nil
}

// IncrementCounter increments a counter
func (s *Store) IncrementCounter(key string, value int64) (int64, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	crdt, exists := s.crdts[key]
	if !exists {
		return 0, fmt.Errorf("counter with key %s not found", key)
	}

	// Update vector clock
	s.vectorClock[s.config.NodeID]++

	var newValue int64
	switch counter := crdt.(type) {
	case *GCounter:
		if value < 0 {
			return 0, fmt.Errorf("cannot decrement G-Counter")
		}
		counter.Increment(s.config.NodeID, value)
		newValue = counter.Value()
	case *PNCounter:
		if value >= 0 {
			counter.Increment(s.config.NodeID, value)
		} else {
			counter.Decrement(s.config.NodeID, -value)
		}
		newValue = counter.Value()
	default:
		return 0, fmt.Errorf("key %s is not a counter", key)
	}

	// Update metadata
	metadata := s.metadata[key]
	metadata.UpdatedAt = time.Now()
	metadata.VectorClock = s.copyVectorClock()
	metadata.Version++

	// Update CRDT vector clock
	crdt.SetVectorClock(s.copyVectorClock())

	// Persist to storage
	if err := s.persistCRDT(key, crdt); err != nil {
		return 0, err
	}

	return newValue, nil
}

// CreateSet creates a new set CRDT
func (s *Store) CreateSet(key string, setType string) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	if _, exists := s.crdts[key]; exists {
		return fmt.Errorf("CRDT with key %s already exists", key)
	}

	var set CRDT
	switch CRDTType(setType) {
	case GSetType:
		set = NewGSet()
	case TwoPSetType:
		set = NewTwoPSet()
	case ORSetType:
		set = NewORSet(s.config.NodeID)
	default:
		return fmt.Errorf("unsupported set type: %s", setType)
	}

	// Update vector clock
	s.vectorClock[s.config.NodeID]++
	set.SetVectorClock(s.copyVectorClock())

	// Store CRDT
	s.crdts[key] = set
	s.metadata[key] = &Metadata{
		Type:        CRDTType(setType),
		Key:         key,
		NodeID:      s.config.NodeID,
		Region:      s.config.Region,
		CreatedAt:   time.Now(),
		UpdatedAt:   time.Now(),
		VectorClock: s.copyVectorClock(),
		Version:     1,
	}

	// Persist to storage
	return s.persistCRDT(key, set)
}

// CreateRegister creates a new register CRDT
func (s *Store) CreateRegister(key string, registerType string, initialValue interface{}) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	if _, exists := s.crdts[key]; exists {
		return fmt.Errorf("CRDT with key %s already exists", key)
	}

	var register CRDT
	switch CRDTType(registerType) {
	case LWWRegisterType:
		register = NewLWWRegister(s.config.NodeID, initialValue)
	case MVRegisterType:
		register = NewMVRegister(s.config.NodeID, initialValue)
	default:
		return fmt.Errorf("unsupported register type: %s", registerType)
	}

	// Update vector clock
	s.vectorClock[s.config.NodeID]++
	register.SetVectorClock(s.copyVectorClock())

	// Store CRDT
	s.crdts[key] = register
	s.metadata[key] = &Metadata{
		Type:        CRDTType(registerType),
		Key:         key,
		NodeID:      s.config.NodeID,
		Region:      s.config.Region,
		CreatedAt:   time.Now(),
		UpdatedAt:   time.Now(),
		VectorClock: s.copyVectorClock(),
		Version:     1,
	}

	// Persist to storage
	return s.persistCRDT(key, register)
}

// MergeCRDT merges a remote CRDT with the local one
func (s *Store) MergeCRDT(key string, remoteCRDT CRDT, remoteMetadata *Metadata) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	localCRDT, exists := s.crdts[key]
	if !exists {
		// No local CRDT, adopt the remote one
		s.crdts[key] = remoteCRDT.Clone()
		s.metadata[key] = remoteMetadata
		return s.persistCRDT(key, remoteCRDT)
	}

	localMetadata := s.metadata[key]

	// Check for conflicts
	if s.hasConflict(localMetadata.VectorClock, remoteMetadata.VectorClock) {
		conflictID := fmt.Sprintf("%s_%d", key, time.Now().UnixNano())
		s.conflicts[conflictID] = &Conflict{
			ID:         conflictID,
			Key:        key,
			Type:       localCRDT.Type(),
			Values:     []CRDT{localCRDT.Clone(), remoteCRDT.Clone()},
			DetectedAt: time.Now(),
			Resolved:   false,
		}
	}

	// Merge CRDTs
	if err := localCRDT.Merge(remoteCRDT); err != nil {
		return fmt.Errorf("failed to merge CRDT: %w", err)
	}

	// Merge vector clocks
	s.mergeVectorClock(remoteMetadata.VectorClock)
	localCRDT.SetVectorClock(s.copyVectorClock())

	// Update metadata
	localMetadata.UpdatedAt = time.Now()
	localMetadata.VectorClock = s.copyVectorClock()
	localMetadata.Version++

	// Persist to storage
	return s.persistCRDT(key, localCRDT)
}

// GetConflicts returns all detected conflicts
func (s *Store) GetConflicts() map[string]*Conflict {
	s.mu.RLock()
	defer s.mu.RUnlock()

	conflicts := make(map[string]*Conflict)
	for id, conflict := range s.conflicts {
		conflicts[id] = conflict
	}
	return conflicts
}

// ResolveConflict resolves a conflict using the specified strategy
func (s *Store) ResolveConflict(conflictID string, strategy string) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	conflict, exists := s.conflicts[conflictID]
	if !exists {
		return fmt.Errorf("conflict %s not found", conflictID)
	}

	if conflict.Resolved {
		return fmt.Errorf("conflict %s already resolved", conflictID)
	}

	// Apply resolution strategy
	var resolvedCRDT CRDT
	switch strategy {
	case "lww":
		resolvedCRDT = s.resolveLWW(conflict.Values)
	case "mv":
		resolvedCRDT = s.resolveMV(conflict.Values)
	case "merge":
		resolvedCRDT = s.resolveMerge(conflict.Values)
	default:
		return fmt.Errorf("unsupported resolution strategy: %s", strategy)
	}

	// Update the CRDT
	s.crdts[conflict.Key] = resolvedCRDT
	
	// Mark conflict as resolved
	conflict.Resolved = true
	conflict.Resolution = strategy

	// Persist to storage
	return s.persistCRDT(conflict.Key, resolvedCRDT)
}

// GetStats returns store statistics
func (s *Store) GetStats() map[string]interface{} {
	s.mu.RLock()
	defer s.mu.RUnlock()

	stats := map[string]interface{}{
		"total_crdts":     len(s.crdts),
		"total_conflicts": len(s.conflicts),
		"vector_clock_size": len(s.vectorClock),
		"uptime":         time.Since(s.startTime).String(),
	}

	// Count by type
	typeCounts := make(map[CRDTType]int)
	for _, metadata := range s.metadata {
		typeCounts[metadata.Type]++
	}
	stats["crdt_types"] = typeCounts

	return stats
}

// GetVectorClocks returns all vector clocks
func (s *Store) GetVectorClocks() map[string]VectorClock {
	s.mu.RLock()
	defer s.mu.RUnlock()

	clocks := make(map[string]VectorClock)
	for key, metadata := range s.metadata {
		clocks[key] = metadata.VectorClock
	}
	return clocks
}

// GetVectorClockSizes returns the size of vector clocks
func (s *Store) GetVectorClockSizes() map[string]int {
	s.mu.RLock()
	defer s.mu.RUnlock()

	sizes := make(map[string]int)
	for key, metadata := range s.metadata {
		sizes[key] = len(metadata.VectorClock)
	}
	return sizes
}

// GetStartTime returns the store start time
func (s *Store) GetStartTime() time.Time {
	return s.startTime
}

// Helper methods

func (s *Store) copyVectorClock() VectorClock {
	copy := make(VectorClock)
	for node, clock := range s.vectorClock {
		copy[node] = clock
	}
	return copy
}

func (s *Store) mergeVectorClock(remote VectorClock) {
	for node, remoteClock := range remote {
		if localClock, exists := s.vectorClock[node]; !exists || remoteClock > localClock {
			s.vectorClock[node] = remoteClock
		}
	}
}

func (s *Store) hasConflict(local, remote VectorClock) bool {
	localDominates := false
	remoteDominates := false

	// Check all nodes in both clocks
	allNodes := make(map[string]bool)
	for node := range local {
		allNodes[node] = true
	}
	for node := range remote {
		allNodes[node] = true
	}

	for node := range allNodes {
		localClock := local[node]
		remoteClock := remote[node]

		if localClock > remoteClock {
			localDominates = true
		} else if remoteClock > localClock {
			remoteDominates = true
		}
	}

	// Conflict exists if neither dominates the other
	return localDominates && remoteDominates
}

func (s *Store) resolveLWW(values []CRDT) CRDT {
	// Last-writer-wins: choose the CRDT with the highest timestamp
	var latest CRDT
	var latestTime int64

	for _, crdt := range values {
		clock := crdt.GetVectorClock()
		var maxTime int64
		for _, t := range clock {
			if t > maxTime {
				maxTime = t
			}
		}
		if maxTime > latestTime {
			latestTime = maxTime
			latest = crdt
		}
	}

	return latest.Clone()
}

func (s *Store) resolveMV(values []CRDT) CRDT {
	// Multi-value: keep all concurrent values
	// This is a simplified implementation
	if len(values) > 0 {
		return values[0].Clone()
	}
	return nil
}

func (s *Store) resolveMerge(values []CRDT) CRDT {
	// Merge all values
	if len(values) == 0 {
		return nil
	}

	result := values[0].Clone()
	for i := 1; i < len(values); i++ {
		result.Merge(values[i])
	}

	return result
}

func (s *Store) persistCRDT(key string, crdt CRDT) error {
	data, err := crdt.Serialize()
	if err != nil {
		return fmt.Errorf("failed to serialize CRDT: %w", err)
	}

	metadata := s.metadata[key]
	metadataData, err := json.Marshal(metadata)
	if err != nil {
		return fmt.Errorf("failed to serialize metadata: %w", err)
	}

	// Store both CRDT data and metadata
	if err := s.storage.Put([]byte("crdt:"+key), data); err != nil {
		return fmt.Errorf("failed to store CRDT: %w", err)
	}

	if err := s.storage.Put([]byte("metadata:"+key), metadataData); err != nil {
		return fmt.Errorf("failed to store metadata: %w", err)
	}

	return nil
}

func (s *Store) loadFromStorage() error {
	// This is a simplified implementation
	// In a real implementation, you would iterate through all keys
	// and deserialize CRDTs and metadata
	return nil
}

func (s *Store) triggerReadRepair(key string) {
	// Trigger read repair in the background
	// This would involve checking with other replicas
	// and merging any differences found
}

// Additional CRDT operations would be implemented here
// (sets, registers, maps, etc.)

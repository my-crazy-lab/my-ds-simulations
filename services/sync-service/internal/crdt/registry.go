package crdt

import (
	"fmt"
	"sync"
)

// CRDT represents a Conflict-free Replicated Data Type
type CRDT interface {
	// Merge merges another CRDT state into this one
	Merge(other CRDT) error
	
	// State returns the current state of the CRDT
	State() interface{}
	
	// Clone creates a deep copy of the CRDT
	Clone() CRDT
	
	// Type returns the CRDT type name
	Type() string
	
	// Validate validates the CRDT state
	Validate() error
}

// CRDTFactory is a function that creates a new CRDT instance
type CRDTFactory func() CRDT

// Registry manages CRDT types and their factories
type Registry struct {
	factories map[string]CRDTFactory
	mu        sync.RWMutex
}

// NewRegistry creates a new CRDT registry
func NewRegistry() *Registry {
	return &Registry{
		factories: make(map[string]CRDTFactory),
	}
}

// RegisterCRDT registers a CRDT type with its factory
func (r *Registry) RegisterCRDT(typeName string, factory CRDTFactory) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.factories[typeName] = factory
}

// CreateCRDT creates a new CRDT instance of the specified type
func (r *Registry) CreateCRDT(typeName string) (CRDT, error) {
	r.mu.RLock()
	factory, exists := r.factories[typeName]
	r.mu.RUnlock()
	
	if !exists {
		return nil, fmt.Errorf("unknown CRDT type: %s", typeName)
	}
	
	return factory(), nil
}

// GetRegisteredTypes returns all registered CRDT types
func (r *Registry) GetRegisteredTypes() []string {
	r.mu.RLock()
	defer r.mu.RUnlock()
	
	types := make([]string, 0, len(r.factories))
	for typeName := range r.factories {
		types = append(types, typeName)
	}
	
	return types
}

// VectorClock represents a vector clock for ordering events
type VectorClock map[string]uint64

// NewVectorClock creates a new vector clock
func NewVectorClock() VectorClock {
	return make(VectorClock)
}

// Increment increments the clock for the given node
func (vc VectorClock) Increment(nodeID string) {
	vc[nodeID]++
}

// Update updates the vector clock with another vector clock
func (vc VectorClock) Update(other VectorClock) {
	for nodeID, timestamp := range other {
		if vc[nodeID] < timestamp {
			vc[nodeID] = timestamp
		}
	}
}

// Compare compares this vector clock with another
func (vc VectorClock) Compare(other VectorClock) Ordering {
	lessOrEqual := true
	greaterOrEqual := true
	
	// Check all nodes in this clock
	for nodeID, timestamp := range vc {
		otherTimestamp, exists := other[nodeID]
		if !exists {
			otherTimestamp = 0
		}
		
		if timestamp > otherTimestamp {
			lessOrEqual = false
		}
		if timestamp < otherTimestamp {
			greaterOrEqual = false
		}
	}
	
	// Check nodes that exist only in other clock
	for nodeID, otherTimestamp := range other {
		if _, exists := vc[nodeID]; !exists && otherTimestamp > 0 {
			lessOrEqual = false
		}
	}
	
	if lessOrEqual && greaterOrEqual {
		return Equal
	} else if lessOrEqual {
		return Before
	} else if greaterOrEqual {
		return After
	} else {
		return Concurrent
	}
}

// Clone creates a copy of the vector clock
func (vc VectorClock) Clone() VectorClock {
	clone := make(VectorClock)
	for nodeID, timestamp := range vc {
		clone[nodeID] = timestamp
	}
	return clone
}

// Ordering represents the relationship between two vector clocks
type Ordering int

const (
	Before Ordering = iota
	After
	Equal
	Concurrent
)

// String returns string representation of ordering
func (o Ordering) String() string {
	switch o {
	case Before:
		return "before"
	case After:
		return "after"
	case Equal:
		return "equal"
	case Concurrent:
		return "concurrent"
	default:
		return "unknown"
	}
}

// Operation represents a CRDT operation
type Operation struct {
	Type        string                 `json:"type"`
	NodeID      string                 `json:"node_id"`
	Timestamp   uint64                 `json:"timestamp"`
	VectorClock VectorClock            `json:"vector_clock"`
	Data        map[string]interface{} `json:"data"`
}

// OperationLog maintains a log of operations for debugging and replay
type OperationLog struct {
	operations []Operation
	mu         sync.RWMutex
}

// NewOperationLog creates a new operation log
func NewOperationLog() *OperationLog {
	return &OperationLog{
		operations: make([]Operation, 0),
	}
}

// AddOperation adds an operation to the log
func (ol *OperationLog) AddOperation(op Operation) {
	ol.mu.Lock()
	defer ol.mu.Unlock()
	ol.operations = append(ol.operations, op)
}

// GetOperations returns all operations
func (ol *OperationLog) GetOperations() []Operation {
	ol.mu.RLock()
	defer ol.mu.RUnlock()
	
	// Return a copy to prevent external modification
	ops := make([]Operation, len(ol.operations))
	copy(ops, ol.operations)
	return ops
}

// GetOperationsSince returns operations since the given vector clock
func (ol *OperationLog) GetOperationsSince(since VectorClock) []Operation {
	ol.mu.RLock()
	defer ol.mu.RUnlock()
	
	var result []Operation
	for _, op := range ol.operations {
		if op.VectorClock.Compare(since) == After {
			result = append(result, op)
		}
	}
	
	return result
}

// Prune removes operations older than the given vector clock
func (ol *OperationLog) Prune(before VectorClock) {
	ol.mu.Lock()
	defer ol.mu.Unlock()
	
	var remaining []Operation
	for _, op := range ol.operations {
		if op.VectorClock.Compare(before) != Before {
			remaining = append(remaining, op)
		}
	}
	
	ol.operations = remaining
}

// ConflictResolutionStrategy defines how conflicts should be resolved
type ConflictResolutionStrategy int

const (
	LastWriteWins ConflictResolutionStrategy = iota
	FirstWriteWins
	Manual
	CRDT
	Merge
)

// String returns string representation of conflict resolution strategy
func (crs ConflictResolutionStrategy) String() string {
	switch crs {
	case LastWriteWins:
		return "last_write_wins"
	case FirstWriteWins:
		return "first_write_wins"
	case Manual:
		return "manual"
	case CRDT:
		return "crdt"
	case Merge:
		return "merge"
	default:
		return "unknown"
	}
}

// ConflictResolver defines the interface for conflict resolution
type ConflictResolver interface {
	ResolveConflict(local, remote CRDT, strategy ConflictResolutionStrategy) (CRDT, error)
}

// DefaultConflictResolver provides default conflict resolution strategies
type DefaultConflictResolver struct{}

// NewDefaultConflictResolver creates a new default conflict resolver
func NewDefaultConflictResolver() *DefaultConflictResolver {
	return &DefaultConflictResolver{}
}

// ResolveConflict resolves conflicts between two CRDT states
func (dcr *DefaultConflictResolver) ResolveConflict(local, remote CRDT, strategy ConflictResolutionStrategy) (CRDT, error) {
	switch strategy {
	case CRDT:
		// For CRDTs, merge is the default resolution
		result := local.Clone()
		err := result.Merge(remote)
		return result, err
		
	case LastWriteWins:
		// Return the remote version (assuming it's newer)
		return remote.Clone(), nil
		
	case FirstWriteWins:
		// Return the local version (assuming it's older)
		return local.Clone(), nil
		
	case Merge:
		// Attempt to merge both versions
		result := local.Clone()
		err := result.Merge(remote)
		return result, err
		
	default:
		return nil, fmt.Errorf("unsupported conflict resolution strategy: %v", strategy)
	}
}

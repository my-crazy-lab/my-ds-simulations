package crdt

import (
	"encoding/json"
	"fmt"
	"time"
)

// LWWRegister implements a Last-Write-Wins Register CRDT
type LWWRegister struct {
	value     interface{}
	timestamp time.Time
	nodeID    string
}

// LWWRegisterState represents the serializable state of LWWRegister
type LWWRegisterState struct {
	Value     interface{} `json:"value"`
	Timestamp time.Time   `json:"timestamp"`
	NodeID    string      `json:"node_id"`
}

// NewLWWRegister creates a new LWW Register
func NewLWWRegister() CRDT {
	return &LWWRegister{
		timestamp: time.Now(),
	}
}

// NewLWWRegisterWithValue creates a new LWW Register with initial value
func NewLWWRegisterWithValue(value interface{}, nodeID string) *LWWRegister {
	return &LWWRegister{
		value:     value,
		timestamp: time.Now(),
		nodeID:    nodeID,
	}
}

// Set sets a new value in the register
func (r *LWWRegister) Set(value interface{}, nodeID string) {
	r.value = value
	r.timestamp = time.Now()
	r.nodeID = nodeID
}

// Get returns the current value
func (r *LWWRegister) Get() interface{} {
	return r.value
}

// GetTimestamp returns the timestamp of the last write
func (r *LWWRegister) GetTimestamp() time.Time {
	return r.timestamp
}

// GetNodeID returns the node ID of the last writer
func (r *LWWRegister) GetNodeID() string {
	return r.nodeID
}

// Merge merges another LWWRegister into this one
func (r *LWWRegister) Merge(other CRDT) error {
	otherReg, ok := other.(*LWWRegister)
	if !ok {
		return fmt.Errorf("cannot merge different CRDT types")
	}

	// Last write wins - compare timestamps
	if otherReg.timestamp.After(r.timestamp) {
		r.value = otherReg.value
		r.timestamp = otherReg.timestamp
		r.nodeID = otherReg.nodeID
	} else if otherReg.timestamp.Equal(r.timestamp) {
		// If timestamps are equal, use node ID for deterministic ordering
		if otherReg.nodeID > r.nodeID {
			r.value = otherReg.value
			r.timestamp = otherReg.timestamp
			r.nodeID = otherReg.nodeID
		}
	}

	return nil
}

// State returns the current state of the CRDT
func (r *LWWRegister) State() interface{} {
	return LWWRegisterState{
		Value:     r.value,
		Timestamp: r.timestamp,
		NodeID:    r.nodeID,
	}
}

// Clone creates a deep copy of the CRDT
func (r *LWWRegister) Clone() CRDT {
	return &LWWRegister{
		value:     r.value,
		timestamp: r.timestamp,
		nodeID:    r.nodeID,
	}
}

// Type returns the CRDT type name
func (r *LWWRegister) Type() string {
	return "LWWRegister"
}

// Validate validates the CRDT state
func (r *LWWRegister) Validate() error {
	if r.timestamp.IsZero() {
		return fmt.Errorf("timestamp cannot be zero")
	}
	return nil
}

// MarshalJSON implements json.Marshaler
func (r *LWWRegister) MarshalJSON() ([]byte, error) {
	return json.Marshal(r.State())
}

// UnmarshalJSON implements json.Unmarshaler
func (r *LWWRegister) UnmarshalJSON(data []byte) error {
	var state LWWRegisterState
	if err := json.Unmarshal(data, &state); err != nil {
		return err
	}

	r.value = state.Value
	r.timestamp = state.Timestamp
	r.nodeID = state.NodeID

	return nil
}

// GCounter implements a Grow-only Counter CRDT
type GCounter struct {
	counters map[string]uint64
}

// NewGCounter creates a new G-Counter
func NewGCounter() CRDT {
	return &GCounter{
		counters: make(map[string]uint64),
	}
}

// Increment increments the counter for the given node
func (c *GCounter) Increment(nodeID string, delta uint64) {
	c.counters[nodeID] += delta
}

// Value returns the total value of the counter
func (c *GCounter) Value() uint64 {
	var total uint64
	for _, count := range c.counters {
		total += count
	}
	return total
}

// Merge merges another GCounter into this one
func (c *GCounter) Merge(other CRDT) error {
	otherCounter, ok := other.(*GCounter)
	if !ok {
		return fmt.Errorf("cannot merge different CRDT types")
	}

	for nodeID, count := range otherCounter.counters {
		if c.counters[nodeID] < count {
			c.counters[nodeID] = count
		}
	}

	return nil
}

// State returns the current state of the CRDT
func (c *GCounter) State() interface{} {
	// Return a copy to prevent external modification
	state := make(map[string]uint64)
	for nodeID, count := range c.counters {
		state[nodeID] = count
	}
	return state
}

// Clone creates a deep copy of the CRDT
func (c *GCounter) Clone() CRDT {
	clone := &GCounter{
		counters: make(map[string]uint64),
	}
	for nodeID, count := range c.counters {
		clone.counters[nodeID] = count
	}
	return clone
}

// Type returns the CRDT type name
func (c *GCounter) Type() string {
	return "GCounter"
}

// Validate validates the CRDT state
func (c *GCounter) Validate() error {
	for nodeID, count := range c.counters {
		if nodeID == "" {
			return fmt.Errorf("node ID cannot be empty")
		}
		if count < 0 {
			return fmt.Errorf("counter value cannot be negative")
		}
	}
	return nil
}

// PNCounter implements a Increment/Decrement Counter CRDT
type PNCounter struct {
	positive *GCounter
	negative *GCounter
}

// NewPNCounter creates a new PN-Counter
func NewPNCounter() CRDT {
	return &PNCounter{
		positive: NewGCounter().(*GCounter),
		negative: NewGCounter().(*GCounter),
	}
}

// Increment increments the counter for the given node
func (c *PNCounter) Increment(nodeID string, delta uint64) {
	c.positive.Increment(nodeID, delta)
}

// Decrement decrements the counter for the given node
func (c *PNCounter) Decrement(nodeID string, delta uint64) {
	c.negative.Increment(nodeID, delta)
}

// Value returns the total value of the counter
func (c *PNCounter) Value() int64 {
	return int64(c.positive.Value()) - int64(c.negative.Value())
}

// Merge merges another PNCounter into this one
func (c *PNCounter) Merge(other CRDT) error {
	otherCounter, ok := other.(*PNCounter)
	if !ok {
		return fmt.Errorf("cannot merge different CRDT types")
	}

	if err := c.positive.Merge(otherCounter.positive); err != nil {
		return err
	}

	if err := c.negative.Merge(otherCounter.negative); err != nil {
		return err
	}

	return nil
}

// State returns the current state of the CRDT
func (c *PNCounter) State() interface{} {
	return map[string]interface{}{
		"positive": c.positive.State(),
		"negative": c.negative.State(),
		"value":    c.Value(),
	}
}

// Clone creates a deep copy of the CRDT
func (c *PNCounter) Clone() CRDT {
	return &PNCounter{
		positive: c.positive.Clone().(*GCounter),
		negative: c.negative.Clone().(*GCounter),
	}
}

// Type returns the CRDT type name
func (c *PNCounter) Type() string {
	return "PNCounter"
}

// Validate validates the CRDT state
func (c *PNCounter) Validate() error {
	if err := c.positive.Validate(); err != nil {
		return fmt.Errorf("positive counter validation failed: %w", err)
	}
	if err := c.negative.Validate(); err != nil {
		return fmt.Errorf("negative counter validation failed: %w", err)
	}
	return nil
}

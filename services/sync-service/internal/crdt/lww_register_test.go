package crdt

import (
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
)

func TestLWWRegister_Set(t *testing.T) {
	// Setup
	register := NewLWWRegister("node1")

	// Test data
	value := "hello world"
	timestamp := time.Now()

	// Execute
	err := register.Set(value, timestamp)

	// Assert
	assert.NoError(t, err)
	assert.Equal(t, value, register.value)
	assert.Equal(t, timestamp, register.timestamp)
	assert.Equal(t, "node1", register.nodeID)
}

func TestLWWRegister_Get(t *testing.T) {
	// Setup
	register := NewLWWRegister("node1")
	value := "test value"
	timestamp := time.Now()
	register.Set(value, timestamp)

	// Execute
	result := register.Get()

	// Assert
	assert.Equal(t, value, result)
}

func TestLWWRegister_Merge_LaterTimestamp(t *testing.T) {
	// Setup
	register1 := NewLWWRegister("node1")
	register2 := NewLWWRegister("node2")

	// Set initial values
	timestamp1 := time.Now()
	timestamp2 := timestamp1.Add(time.Second) // Later timestamp

	register1.Set("value1", timestamp1)
	register2.Set("value2", timestamp2)

	// Execute merge
	err := register1.Merge(register2)

	// Assert
	assert.NoError(t, err)
	assert.Equal(t, "value2", register1.Get()) // Later timestamp wins
	assert.Equal(t, timestamp2, register1.timestamp)
	assert.Equal(t, "node2", register1.nodeID)
}

func TestLWWRegister_Merge_EarlierTimestamp(t *testing.T) {
	// Setup
	register1 := NewLWWRegister("node1")
	register2 := NewLWWRegister("node2")

	// Set initial values
	timestamp1 := time.Now()
	timestamp2 := timestamp1.Add(-time.Second) // Earlier timestamp

	register1.Set("value1", timestamp1)
	register2.Set("value2", timestamp2)

	// Execute merge
	err := register1.Merge(register2)

	// Assert
	assert.NoError(t, err)
	assert.Equal(t, "value1", register1.Get()) // Keep current value (later timestamp)
	assert.Equal(t, timestamp1, register1.timestamp)
	assert.Equal(t, "node1", register1.nodeID)
}

func TestLWWRegister_Merge_SameTimestamp_HigherNodeID(t *testing.T) {
	// Setup
	register1 := NewLWWRegister("node1")
	register2 := NewLWWRegister("node2") // Higher node ID

	// Set values with same timestamp
	timestamp := time.Now()
	register1.Set("value1", timestamp)
	register2.Set("value2", timestamp)

	// Execute merge
	err := register1.Merge(register2)

	// Assert
	assert.NoError(t, err)
	assert.Equal(t, "value2", register1.Get()) // Higher node ID wins
	assert.Equal(t, timestamp, register1.timestamp)
	assert.Equal(t, "node2", register1.nodeID)
}

func TestLWWRegister_Merge_SameTimestamp_LowerNodeID(t *testing.T) {
	// Setup
	register1 := NewLWWRegister("node2")
	register2 := NewLWWRegister("node1") // Lower node ID

	// Set values with same timestamp
	timestamp := time.Now()
	register1.Set("value1", timestamp)
	register2.Set("value2", timestamp)

	// Execute merge
	err := register1.Merge(register2)

	// Assert
	assert.NoError(t, err)
	assert.Equal(t, "value1", register1.Get()) // Keep current value (higher node ID)
	assert.Equal(t, timestamp, register1.timestamp)
	assert.Equal(t, "node2", register1.nodeID)
}

func TestLWWRegister_Clone(t *testing.T) {
	// Setup
	original := NewLWWRegister("node1")
	timestamp := time.Now()
	original.Set("test value", timestamp)

	// Execute
	cloned := original.Clone()

	// Assert
	assert.Equal(t, original.Get(), cloned.Get())
	assert.Equal(t, original.timestamp, cloned.(*LWWRegister).timestamp)
	assert.Equal(t, original.nodeID, cloned.(*LWWRegister).nodeID)

	// Verify they are separate instances
	original.Set("new value", timestamp.Add(time.Second))
	assert.NotEqual(t, original.Get(), cloned.Get())
}

func TestLWWRegister_State(t *testing.T) {
	// Setup
	register := NewLWWRegister("node1")
	value := "test value"
	timestamp := time.Now()
	register.Set(value, timestamp)

	// Execute
	state := register.State()

	// Assert
	expectedState := map[string]interface{}{
		"value":     value,
		"timestamp": timestamp,
		"node_id":   "node1",
	}
	assert.Equal(t, expectedState, state)
}

func TestLWWRegister_Merge_InvalidType(t *testing.T) {
	// Setup
	register := NewLWWRegister("node1")
	invalidCRDT := NewGCounter("node1")

	// Execute
	err := register.Merge(invalidCRDT)

	// Assert
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "cannot merge")
}

func TestLWWRegister_ConcurrentUpdates(t *testing.T) {
	// Setup - simulate concurrent updates from different nodes
	register1 := NewLWWRegister("node1")
	register2 := NewLWWRegister("node2")
	register3 := NewLWWRegister("node3")

	// Simulate concurrent updates at different times
	baseTime := time.Now()
	
	register1.Set("value1", baseTime.Add(1*time.Millisecond))
	register2.Set("value2", baseTime.Add(2*time.Millisecond))
	register3.Set("value3", baseTime.Add(3*time.Millisecond)) // Latest

	// Merge in different orders to test commutativity
	// First merge order: 1 <- 2 <- 3
	temp1 := register1.Clone().(*LWWRegister)
	temp1.Merge(register2)
	temp1.Merge(register3)

	// Second merge order: 1 <- 3 <- 2
	temp2 := register1.Clone().(*LWWRegister)
	temp2.Merge(register3)
	temp2.Merge(register2)

	// Third merge order: 2 <- 1 <- 3
	temp3 := register2.Clone().(*LWWRegister)
	temp3.Merge(register1)
	temp3.Merge(register3)

	// Assert all merge orders result in the same final state
	assert.Equal(t, "value3", temp1.Get()) // Latest timestamp wins
	assert.Equal(t, "value3", temp2.Get())
	assert.Equal(t, "value3", temp3.Get())
}

func TestLWWRegister_EmptyValue(t *testing.T) {
	// Setup
	register := NewLWWRegister("node1")

	// Test empty string
	err := register.Set("", time.Now())
	assert.NoError(t, err)
	assert.Equal(t, "", register.Get())

	// Test nil value
	err = register.Set(nil, time.Now())
	assert.NoError(t, err)
	assert.Nil(t, register.Get())
}

func TestLWWRegister_TypeSafety(t *testing.T) {
	// Setup
	register := NewLWWRegister("node1")
	timestamp := time.Now()

	// Test different value types
	testCases := []interface{}{
		"string value",
		42,
		3.14,
		true,
		[]string{"array", "value"},
		map[string]string{"key": "value"},
	}

	for _, testValue := range testCases {
		err := register.Set(testValue, timestamp)
		assert.NoError(t, err)
		assert.Equal(t, testValue, register.Get())
		timestamp = timestamp.Add(time.Millisecond) // Increment for next test
	}
}

func TestLWWRegister_ZeroTimestamp(t *testing.T) {
	// Setup
	register := NewLWWRegister("node1")
	zeroTime := time.Time{}

	// Execute
	err := register.Set("value", zeroTime)

	// Assert
	assert.NoError(t, err)
	assert.Equal(t, "value", register.Get())
	assert.Equal(t, zeroTime, register.timestamp)
}

func TestLWWRegister_MergeWithSelf(t *testing.T) {
	// Setup
	register := NewLWWRegister("node1")
	register.Set("value", time.Now())

	// Execute - merge with self
	err := register.Merge(register)

	// Assert - should be no-op
	assert.NoError(t, err)
	assert.Equal(t, "value", register.Get())
}

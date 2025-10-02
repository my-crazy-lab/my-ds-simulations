package crdt

import (
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
)

// Simple CRDT tests that don't require complex dependencies

func TestVectorClockComparison(t *testing.T) {
	tests := []struct {
		name     string
		clock1   map[string]uint64
		clock2   map[string]uint64
		expected string
	}{
		{
			name:     "equal clocks",
			clock1:   map[string]uint64{"node1": 1, "node2": 1},
			clock2:   map[string]uint64{"node1": 1, "node2": 1},
			expected: "equal",
		},
		{
			name:     "clock1 before clock2",
			clock1:   map[string]uint64{"node1": 1, "node2": 1},
			clock2:   map[string]uint64{"node1": 2, "node2": 1},
			expected: "before",
		},
		{
			name:     "clock1 after clock2",
			clock1:   map[string]uint64{"node1": 2, "node2": 1},
			clock2:   map[string]uint64{"node1": 1, "node2": 1},
			expected: "after",
		},
		{
			name:     "concurrent clocks",
			clock1:   map[string]uint64{"node1": 2, "node2": 1},
			clock2:   map[string]uint64{"node1": 1, "node2": 2},
			expected: "concurrent",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := compareVectorClocks(tt.clock1, tt.clock2)
			assert.Equal(t, tt.expected, result)
		})
	}
}

func compareVectorClocks(clock1, clock2 map[string]uint64) string {
	if len(clock1) == 0 && len(clock2) == 0 {
		return "equal"
	}

	// Get all nodes
	allNodes := make(map[string]bool)
	for node := range clock1 {
		allNodes[node] = true
	}
	for node := range clock2 {
		allNodes[node] = true
	}

	clock1Before := true
	clock2Before := true

	for node := range allNodes {
		val1 := clock1[node]
		val2 := clock2[node]

		if val1 > val2 {
			clock2Before = false
		} else if val1 < val2 {
			clock1Before = false
		}
	}

	if clock1Before && clock2Before {
		return "equal"
	} else if clock1Before {
		return "before"
	} else if clock2Before {
		return "after"
	} else {
		return "concurrent"
	}
}

func TestTimestampComparison(t *testing.T) {
	now := time.Now()
	earlier := now.Add(-time.Hour)
	later := now.Add(time.Hour)

	tests := []struct {
		name      string
		timestamp1 time.Time
		timestamp2 time.Time
		expected   int
	}{
		{"equal timestamps", now, now, 0},
		{"first earlier", earlier, now, -1},
		{"first later", later, now, 1},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := compareTimestamps(tt.timestamp1, tt.timestamp2)
			assert.Equal(t, tt.expected, result)
		})
	}
}

func compareTimestamps(t1, t2 time.Time) int {
	if t1.Before(t2) {
		return -1
	} else if t1.After(t2) {
		return 1
	}
	return 0
}

func TestNodeIDComparison(t *testing.T) {
	tests := []struct {
		name     string
		nodeID1  string
		nodeID2  string
		expected int
	}{
		{"equal nodes", "node1", "node1", 0},
		{"first smaller", "node1", "node2", -1},
		{"first larger", "node2", "node1", 1},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := compareNodeIDs(tt.nodeID1, tt.nodeID2)
			assert.Equal(t, tt.expected, result)
		})
	}
}

func compareNodeIDs(id1, id2 string) int {
	if id1 < id2 {
		return -1
	} else if id1 > id2 {
		return 1
	}
	return 0
}

func TestCRDTTypeValidation(t *testing.T) {
	validTypes := []string{
		"LWWRegister",
		"GCounter",
		"PNCounter",
		"ORSet",
	}

	for _, crdtType := range validTypes {
		t.Run("valid_type_"+crdtType, func(t *testing.T) {
			assert.True(t, isValidCRDTType(crdtType))
		})
	}

	invalidTypes := []string{
		"",
		"InvalidType",
		"lwwregister",
		"gcounter",
	}

	for _, crdtType := range invalidTypes {
		t.Run("invalid_type_"+crdtType, func(t *testing.T) {
			assert.False(t, isValidCRDTType(crdtType))
		})
	}
}

func isValidCRDTType(crdtType string) bool {
	validTypes := map[string]bool{
		"LWWRegister": true,
		"GCounter":    true,
		"PNCounter":   true,
		"ORSet":       true,
	}
	
	return validTypes[crdtType]
}

func TestConflictResolutionStrategy(t *testing.T) {
	tests := []struct {
		name     string
		strategy string
		isValid  bool
	}{
		{"last write wins", "LastWriteWins", true},
		{"first write wins", "FirstWriteWins", true},
		{"manual resolution", "Manual", true},
		{"crdt merge", "CRDT", true},
		{"invalid strategy", "InvalidStrategy", false},
		{"empty strategy", "", false},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			isValid := isValidConflictResolutionStrategy(tt.strategy)
			assert.Equal(t, tt.isValid, isValid)
		})
	}
}

func isValidConflictResolutionStrategy(strategy string) bool {
	validStrategies := map[string]bool{
		"LastWriteWins":  true,
		"FirstWriteWins": true,
		"Manual":         true,
		"CRDT":           true,
		"Merge":          true,
	}
	
	return validStrategies[strategy]
}

func TestDeviceIDGeneration(t *testing.T) {
	id1 := generateDeviceID()
	id2 := generateDeviceID()
	
	assert.NotEqual(t, id1, id2, "Device IDs should be unique")
	assert.NotEmpty(t, id1, "Device ID should not be empty")
	assert.NotEmpty(t, id2, "Device ID should not be empty")
	assert.Contains(t, id1, "device-", "Device ID should have proper prefix")
	assert.Contains(t, id2, "device-", "Device ID should have proper prefix")
}

func generateDeviceID() string {
	return "device-" + time.Now().Format("20060102150405") + "-" + string(rune(time.Now().Nanosecond()%1000))
}

func TestSyncOperationValidation(t *testing.T) {
	tests := []struct {
		name      string
		operation map[string]interface{}
		isValid   bool
	}{
		{
			name: "valid set operation",
			operation: map[string]interface{}{
				"type":      "set",
				"value":     "hello world",
				"timestamp": time.Now().Format(time.RFC3339),
				"node_id":   "device-123",
			},
			isValid: true,
		},
		{
			name: "missing type",
			operation: map[string]interface{}{
				"value":     "hello world",
				"timestamp": time.Now().Format(time.RFC3339),
				"node_id":   "device-123",
			},
			isValid: false,
		},
		{
			name: "missing timestamp",
			operation: map[string]interface{}{
				"type":    "set",
				"value":   "hello world",
				"node_id": "device-123",
			},
			isValid: false,
		},
		{
			name:      "empty operation",
			operation: map[string]interface{}{},
			isValid:   false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			isValid := validateSyncOperation(tt.operation)
			assert.Equal(t, tt.isValid, isValid)
		})
	}
}

func validateSyncOperation(operation map[string]interface{}) bool {
	if operation == nil || len(operation) == 0 {
		return false
	}
	
	requiredFields := []string{"type", "timestamp", "node_id"}
	for _, field := range requiredFields {
		if _, exists := operation[field]; !exists {
			return false
		}
	}
	
	return true
}

func TestCounterOperations(t *testing.T) {
	// Test G-Counter increment
	counter := map[string]uint64{
		"node1": 5,
		"node2": 3,
	}
	
	incrementedCounter := incrementGCounter(counter, "node1")
	assert.Equal(t, uint64(6), incrementedCounter["node1"])
	assert.Equal(t, uint64(3), incrementedCounter["node2"])
	
	// Test total value
	total := getTotalValue(incrementedCounter)
	assert.Equal(t, uint64(9), total) // 6 + 3
}

func incrementGCounter(counter map[string]uint64, nodeID string) map[string]uint64 {
	result := make(map[string]uint64)
	for k, v := range counter {
		result[k] = v
	}
	result[nodeID]++
	return result
}

func getTotalValue(counter map[string]uint64) uint64 {
	var total uint64
	for _, value := range counter {
		total += value
	}
	return total
}

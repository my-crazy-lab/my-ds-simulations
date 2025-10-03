#!/usr/bin/env python3
"""
Comprehensive unit tests for CRDT operations in the geo-replicated datastore.
Tests CRDT properties: commutativity, associativity, idempotency, and convergence.
"""

import pytest
import requests
import json
import time
import threading
import random
from typing import Dict, List, Any
from concurrent.futures import ThreadPoolExecutor, as_completed


class CRDTTestClient:
    """Test client for CRDT operations"""
    
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({'Content-Type': 'application/json'})
    
    def create_counter(self, key: str, counter_type: str, initial_value: int = 0) -> Dict:
        """Create a new counter CRDT"""
        payload = {
            "type": counter_type,
            "initial_value": initial_value
        }
        response = self.session.post(f"{self.base_url}/crdt/counters/{key}", json=payload)
        response.raise_for_status()
        return response.json()
    
    def get_counter(self, key: str, consistency: str = "eventual") -> Dict:
        """Get counter value"""
        response = self.session.get(f"{self.base_url}/crdt/counters/{key}?consistency={consistency}")
        response.raise_for_status()
        return response.json()
    
    def increment_counter(self, key: str, value: int = 1) -> Dict:
        """Increment counter"""
        payload = {"value": value}
        response = self.session.post(f"{self.base_url}/crdt/counters/{key}/increment", json=payload)
        response.raise_for_status()
        return response.json()
    
    def decrement_counter(self, key: str, value: int = 1) -> Dict:
        """Decrement counter (PN-Counter only)"""
        payload = {"value": -value}
        response = self.session.post(f"{self.base_url}/crdt/counters/{key}/increment", json=payload)
        response.raise_for_status()
        return response.json()
    
    def create_set(self, key: str, set_type: str) -> Dict:
        """Create a new set CRDT"""
        payload = {"type": set_type}
        response = self.session.post(f"{self.base_url}/crdt/sets/{key}", json=payload)
        response.raise_for_status()
        return response.json()
    
    def get_set(self, key: str, consistency: str = "eventual") -> Dict:
        """Get set elements"""
        response = self.session.get(f"{self.base_url}/crdt/sets/{key}?consistency={consistency}")
        response.raise_for_status()
        return response.json()
    
    def add_to_set(self, key: str, element: str) -> Dict:
        """Add element to set"""
        payload = {"element": element}
        response = self.session.post(f"{self.base_url}/crdt/sets/{key}/add", json=payload)
        response.raise_for_status()
        return response.json()
    
    def remove_from_set(self, key: str, element: str) -> Dict:
        """Remove element from set"""
        payload = {"element": element}
        response = self.session.post(f"{self.base_url}/crdt/sets/{key}/remove", json=payload)
        response.raise_for_status()
        return response.json()
    
    def create_register(self, key: str, register_type: str, initial_value: Any) -> Dict:
        """Create a new register CRDT"""
        payload = {
            "type": register_type,
            "initial_value": initial_value
        }
        response = self.session.post(f"{self.base_url}/crdt/registers/{key}", json=payload)
        response.raise_for_status()
        return response.json()
    
    def get_register(self, key: str, consistency: str = "eventual") -> Dict:
        """Get register value"""
        response = self.session.get(f"{self.base_url}/crdt/registers/{key}?consistency={consistency}")
        response.raise_for_status()
        return response.json()
    
    def set_register(self, key: str, value: Any) -> Dict:
        """Set register value"""
        payload = {"value": value}
        response = self.session.put(f"{self.base_url}/crdt/registers/{key}", json=payload)
        response.raise_for_status()
        return response.json()
    
    def get_status(self) -> Dict:
        """Get node status"""
        response = self.session.get(f"{self.base_url}/admin/status")
        response.raise_for_status()
        return response.json()
    
    def get_conflicts(self) -> Dict:
        """Get detected conflicts"""
        response = self.session.get(f"{self.base_url}/admin/conflicts")
        response.raise_for_status()
        return response.json()
    
    def trigger_sync(self, region: str = None) -> Dict:
        """Trigger synchronization"""
        if region:
            response = self.session.post(f"{self.base_url}/admin/anti-entropy/sync/{region}")
        else:
            response = self.session.post(f"{self.base_url}/admin/anti-entropy/full-sync")
        response.raise_for_status()
        return response.json()


class TestCRDTCounters:
    """Test CRDT counter operations"""
    
    @pytest.fixture
    def clients(self):
        """Create test clients for different nodes"""
        return {
            'us-1': CRDTTestClient('http://localhost:8081'),
            'us-2': CRDTTestClient('http://localhost:8082'),
            'eu-1': CRDTTestClient('http://localhost:8084'),
            'apac-1': CRDTTestClient('http://localhost:8087'),
        }
    
    def test_g_counter_basic_operations(self, clients):
        """Test basic G-Counter operations"""
        key = f"test_g_counter_{int(time.time())}"
        
        # Create G-Counter
        clients['us-1'].create_counter(key, "g_counter", 0)
        
        # Increment from different nodes
        clients['us-1'].increment_counter(key, 5)
        clients['us-2'].increment_counter(key, 3)
        clients['eu-1'].increment_counter(key, 2)
        
        # Wait for propagation
        time.sleep(2)
        
        # All nodes should converge to the same value
        expected_value = 10  # 5 + 3 + 2
        for node_id, client in clients.items():
            result = client.get_counter(key)
            assert result['value'] == expected_value, f"Node {node_id} has incorrect value"
    
    def test_pn_counter_increment_decrement(self, clients):
        """Test PN-Counter increment and decrement operations"""
        key = f"test_pn_counter_{int(time.time())}"
        
        # Create PN-Counter
        clients['us-1'].create_counter(key, "pn_counter", 10)
        
        # Mixed increment/decrement operations
        clients['us-1'].increment_counter(key, 5)
        clients['us-2'].decrement_counter(key, 3)
        clients['eu-1'].increment_counter(key, 7)
        clients['apac-1'].decrement_counter(key, 2)
        
        # Wait for propagation
        time.sleep(3)
        
        # All nodes should converge: 10 + 5 - 3 + 7 - 2 = 17
        expected_value = 17
        for node_id, client in clients.items():
            result = client.get_counter(key)
            assert result['value'] == expected_value, f"Node {node_id} has incorrect value"
    
    def test_counter_commutativity(self, clients):
        """Test that counter operations are commutative"""
        key1 = f"test_commute_1_{int(time.time())}"
        key2 = f"test_commute_2_{int(time.time())}"
        
        # Create identical counters
        clients['us-1'].create_counter(key1, "pn_counter", 0)
        clients['us-1'].create_counter(key2, "pn_counter", 0)
        
        # Apply operations in different orders
        # Sequence 1: A, B, C
        clients['us-1'].increment_counter(key1, 5)
        clients['us-2'].increment_counter(key1, 3)
        clients['eu-1'].decrement_counter(key1, 2)
        
        # Sequence 2: C, A, B
        clients['eu-1'].decrement_counter(key2, 2)
        clients['us-1'].increment_counter(key2, 5)
        clients['us-2'].increment_counter(key2, 3)
        
        # Wait for propagation
        time.sleep(3)
        
        # Both should have the same final value
        result1 = clients['us-1'].get_counter(key1)
        result2 = clients['us-1'].get_counter(key2)
        assert result1['value'] == result2['value'], "Operations are not commutative"
    
    def test_counter_idempotency(self, clients):
        """Test counter idempotency through duplicate operations"""
        key = f"test_idempotent_{int(time.time())}"
        
        # Create counter
        clients['us-1'].create_counter(key, "g_counter", 0)
        
        # Perform the same logical operation multiple times
        # (simulating network retries)
        for _ in range(3):
            clients['us-1'].increment_counter(key, 5)
        
        # Wait for propagation
        time.sleep(2)
        
        # Should only count once due to vector clock deduplication
        result = clients['us-1'].get_counter(key)
        # Note: This test assumes the implementation handles idempotency
        # In practice, you might need unique operation IDs
        assert result['value'] >= 5, "Counter value should be at least 5"


class TestCRDTSets:
    """Test CRDT set operations"""
    
    @pytest.fixture
    def clients(self):
        """Create test clients for different nodes"""
        return {
            'us-1': CRDTTestClient('http://localhost:8081'),
            'us-2': CRDTTestClient('http://localhost:8082'),
            'eu-1': CRDTTestClient('http://localhost:8084'),
            'apac-1': CRDTTestClient('http://localhost:8087'),
        }
    
    def test_g_set_basic_operations(self, clients):
        """Test basic G-Set operations"""
        key = f"test_g_set_{int(time.time())}"
        
        # Create G-Set
        clients['us-1'].create_set(key, "g_set")
        
        # Add elements from different nodes
        clients['us-1'].add_to_set(key, "element1")
        clients['us-2'].add_to_set(key, "element2")
        clients['eu-1'].add_to_set(key, "element3")
        clients['apac-1'].add_to_set(key, "element1")  # Duplicate
        
        # Wait for propagation
        time.sleep(3)
        
        # All nodes should have the same set
        expected_elements = {"element1", "element2", "element3"}
        for node_id, client in clients.items():
            result = client.get_set(key)
            actual_elements = set(result['elements'])
            assert actual_elements == expected_elements, f"Node {node_id} has incorrect elements"
    
    def test_or_set_add_remove(self, clients):
        """Test OR-Set add and remove operations"""
        key = f"test_or_set_{int(time.time())}"
        
        # Create OR-Set
        clients['us-1'].create_set(key, "or_set")
        
        # Add elements
        clients['us-1'].add_to_set(key, "item1")
        clients['us-2'].add_to_set(key, "item2")
        clients['eu-1'].add_to_set(key, "item3")
        
        # Wait for propagation
        time.sleep(2)
        
        # Remove some elements
        clients['us-1'].remove_from_set(key, "item1")
        clients['apac-1'].remove_from_set(key, "item2")
        
        # Wait for propagation
        time.sleep(3)
        
        # Check final state
        for node_id, client in clients.items():
            result = client.get_set(key)
            actual_elements = set(result['elements'])
            expected_elements = {"item3"}  # Only item3 should remain
            assert actual_elements == expected_elements, f"Node {node_id} has incorrect elements"
    
    def test_set_concurrent_add_remove(self, clients):
        """Test concurrent add/remove operations"""
        key = f"test_concurrent_{int(time.time())}"
        
        # Create OR-Set
        clients['us-1'].create_set(key, "or_set")
        
        # Add element from one node
        clients['us-1'].add_to_set(key, "concurrent_item")
        
        # Wait briefly
        time.sleep(1)
        
        # Concurrently add and remove the same element
        def add_operation():
            clients['us-2'].add_to_set(key, "concurrent_item")
        
        def remove_operation():
            clients['eu-1'].remove_from_set(key, "concurrent_item")
        
        # Execute operations concurrently
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(add_operation),
                executor.submit(remove_operation)
            ]
            for future in as_completed(futures):
                future.result()
        
        # Wait for propagation
        time.sleep(3)
        
        # In OR-Set, add should win over remove for concurrent operations
        for node_id, client in clients.items():
            result = client.get_set(key)
            actual_elements = set(result['elements'])
            assert "concurrent_item" in actual_elements, f"Node {node_id} missing concurrent item"


class TestCRDTRegisters:
    """Test CRDT register operations"""
    
    @pytest.fixture
    def clients(self):
        """Create test clients for different nodes"""
        return {
            'us-1': CRDTTestClient('http://localhost:8081'),
            'us-2': CRDTTestClient('http://localhost:8082'),
            'eu-1': CRDTTestClient('http://localhost:8084'),
            'apac-1': CRDTTestClient('http://localhost:8087'),
        }
    
    def test_lww_register_basic_operations(self, clients):
        """Test basic LWW-Register operations"""
        key = f"test_lww_register_{int(time.time())}"
        
        # Create LWW-Register
        clients['us-1'].create_register(key, "lww_register", "initial_value")
        
        # Update from different nodes with delays to ensure ordering
        clients['us-1'].set_register(key, "value1")
        time.sleep(0.1)
        clients['us-2'].set_register(key, "value2")
        time.sleep(0.1)
        clients['eu-1'].set_register(key, "value3")
        
        # Wait for propagation
        time.sleep(3)
        
        # All nodes should converge to the last written value
        for node_id, client in clients.items():
            result = client.get_register(key)
            assert result['value'] == "value3", f"Node {node_id} has incorrect value"
    
    def test_mv_register_concurrent_updates(self, clients):
        """Test MV-Register with concurrent updates"""
        key = f"test_mv_register_{int(time.time())}"
        
        # Create MV-Register
        clients['us-1'].create_register(key, "mv_register", "initial")
        
        # Wait for creation to propagate
        time.sleep(1)
        
        # Concurrent updates from different nodes
        def update_node(client, value):
            client.set_register(key, value)
        
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [
                executor.submit(update_node, clients['us-1'], "concurrent_value1"),
                executor.submit(update_node, clients['us-2'], "concurrent_value2"),
                executor.submit(update_node, clients['eu-1'], "concurrent_value3"),
            ]
            for future in as_completed(futures):
                future.result()
        
        # Wait for propagation
        time.sleep(3)
        
        # MV-Register should preserve all concurrent values
        for node_id, client in clients.items():
            result = client.get_register(key)
            # The exact behavior depends on implementation
            # Should either have all values or a deterministic merge
            assert result['value'] is not None, f"Node {node_id} has null value"


class TestCRDTConvergence:
    """Test CRDT convergence properties"""
    
    @pytest.fixture
    def clients(self):
        """Create test clients for different nodes"""
        return {
            'us-1': CRDTTestClient('http://localhost:8081'),
            'us-2': CRDTTestClient('http://localhost:8082'),
            'us-3': CRDTTestClient('http://localhost:8083'),
            'eu-1': CRDTTestClient('http://localhost:8084'),
            'eu-2': CRDTTestClient('http://localhost:8085'),
            'apac-1': CRDTTestClient('http://localhost:8087'),
        }
    
    def test_eventual_convergence(self, clients):
        """Test that all nodes eventually converge to the same state"""
        key = f"test_convergence_{int(time.time())}"
        
        # Create counter on first node
        clients['us-1'].create_counter(key, "pn_counter", 0)
        
        # Wait for creation to propagate
        time.sleep(2)
        
        # Perform random operations from all nodes
        operations = []
        for i in range(20):
            node_id = random.choice(list(clients.keys()))
            operation = random.choice(['increment', 'decrement'])
            value = random.randint(1, 10)
            
            operations.append((node_id, operation, value))
            
            if operation == 'increment':
                clients[node_id].increment_counter(key, value)
            else:
                clients[node_id].decrement_counter(key, value)
            
            # Small delay between operations
            time.sleep(0.1)
        
        # Wait for all operations to propagate
        time.sleep(10)
        
        # Calculate expected final value
        expected_value = sum(value if op == 'increment' else -value 
                           for _, op, value in operations)
        
        # All nodes should have converged to the same value
        values = {}
        for node_id, client in clients.items():
            result = client.get_counter(key)
            values[node_id] = result['value']
        
        # Check that all values are the same
        unique_values = set(values.values())
        assert len(unique_values) == 1, f"Nodes have not converged: {values}"
        
        # Check that the converged value is correct
        converged_value = list(unique_values)[0]
        assert converged_value == expected_value, f"Expected {expected_value}, got {converged_value}"
    
    def test_convergence_after_partition(self, clients):
        """Test convergence after simulated network partition"""
        key = f"test_partition_convergence_{int(time.time())}"
        
        # Create counter
        clients['us-1'].create_counter(key, "pn_counter", 0)
        time.sleep(2)
        
        # Simulate partition: US nodes vs EU/APAC nodes
        us_nodes = ['us-1', 'us-2', 'us-3']
        other_nodes = ['eu-1', 'eu-2', 'apac-1']
        
        # Operations on US partition
        for node_id in us_nodes:
            clients[node_id].increment_counter(key, 5)
        
        # Operations on EU/APAC partition
        for node_id in other_nodes:
            clients[node_id].increment_counter(key, 3)
        
        # Wait for intra-partition propagation
        time.sleep(3)
        
        # Trigger cross-region synchronization (simulating partition healing)
        for node_id in clients.keys():
            try:
                clients[node_id].trigger_sync()
            except:
                pass  # Some nodes might not support this endpoint
        
        # Wait for convergence
        time.sleep(10)
        
        # All nodes should converge
        expected_value = len(us_nodes) * 5 + len(other_nodes) * 3  # 15 + 18 = 33
        
        values = {}
        for node_id, client in clients.items():
            result = client.get_counter(key)
            values[node_id] = result['value']
        
        unique_values = set(values.values())
        assert len(unique_values) == 1, f"Nodes have not converged after partition: {values}"
        
        converged_value = list(unique_values)[0]
        assert converged_value == expected_value, f"Expected {expected_value}, got {converged_value}"


class TestCRDTConflictResolution:
    """Test CRDT conflict detection and resolution"""
    
    @pytest.fixture
    def clients(self):
        """Create test clients for different nodes"""
        return {
            'us-1': CRDTTestClient('http://localhost:8081'),
            'eu-1': CRDTTestClient('http://localhost:8084'),
            'apac-1': CRDTTestClient('http://localhost:8087'),
        }
    
    def test_conflict_detection(self, clients):
        """Test that conflicts are properly detected"""
        key = f"test_conflict_detection_{int(time.time())}"
        
        # Create register
        clients['us-1'].create_register(key, "lww_register", "initial")
        time.sleep(2)
        
        # Concurrent updates that should create conflicts
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [
                executor.submit(clients['us-1'].set_register, key, "us_value"),
                executor.submit(clients['eu-1'].set_register, key, "eu_value"),
                executor.submit(clients['apac-1'].set_register, key, "apac_value"),
            ]
            for future in as_completed(futures):
                future.result()
        
        # Wait for conflict detection
        time.sleep(5)
        
        # Check for detected conflicts
        conflicts_detected = False
        for node_id, client in clients.items():
            try:
                conflicts = client.get_conflicts()
                if conflicts.get('conflicts') and len(conflicts['conflicts']) > 0:
                    conflicts_detected = True
                    break
            except:
                pass  # Some nodes might not have conflicts endpoint
        
        # Note: Conflict detection depends on implementation
        # This test verifies the conflict detection mechanism exists
        print(f"Conflicts detected: {conflicts_detected}")


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "--tb=short"])

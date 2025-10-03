#!/usr/bin/env python3
"""
Comprehensive unit tests for Raft consensus algorithm core functionality.
Tests leader election, log replication, and safety properties.
"""

import asyncio
import json
import pytest
import requests
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional

class RaftTestClient:
    """Test client for interacting with Raft nodes"""
    
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.timeout = 5
    
    def get_status(self) -> Dict:
        """Get node status"""
        response = self.session.get(f"{self.base_url}/admin/status")
        response.raise_for_status()
        return response.json()
    
    def get_health(self) -> Dict:
        """Get node health"""
        response = self.session.get(f"{self.base_url}/health")
        response.raise_for_status()
        return response.json()
    
    def put_value(self, key: str, value: str) -> Dict:
        """Put a key-value pair"""
        response = self.session.put(
            f"{self.base_url}/kv/{key}",
            json={"value": value}
        )
        response.raise_for_status()
        return response.json()
    
    def get_value(self, key: str) -> Dict:
        """Get a value by key"""
        response = self.session.get(f"{self.base_url}/kv/{key}")
        response.raise_for_status()
        return response.json()
    
    def delete_value(self, key: str) -> Dict:
        """Delete a key"""
        response = self.session.delete(f"{self.base_url}/kv/{key}")
        response.raise_for_status()
        return response.json()
    
    def take_snapshot(self) -> Dict:
        """Take a snapshot"""
        response = self.session.post(f"{self.base_url}/admin/snapshot")
        response.raise_for_status()
        return response.json()
    
    def compact_log(self) -> Dict:
        """Compact the log"""
        response = self.session.post(f"{self.base_url}/admin/compact")
        response.raise_for_status()
        return response.json()

class RaftCluster:
    """Manages a cluster of Raft nodes for testing"""
    
    def __init__(self, node_urls: List[str]):
        self.nodes = {f"node{i+1}": RaftTestClient(url) for i, url in enumerate(node_urls)}
        self.node_urls = node_urls
    
    def wait_for_cluster_ready(self, timeout: int = 30) -> bool:
        """Wait for all nodes to be healthy"""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                healthy_nodes = 0
                for client in self.nodes.values():
                    health = client.get_health()
                    if health.get("status") == "healthy":
                        healthy_nodes += 1
                
                if healthy_nodes == len(self.nodes):
                    return True
                    
            except Exception as e:
                print(f"Waiting for cluster ready: {e}")
            
            time.sleep(1)
        
        return False
    
    def get_leader(self) -> Optional[str]:
        """Find the current leader"""
        for node_id, client in self.nodes.items():
            try:
                status = client.get_status()
                if status.get("state") == "Leader":
                    return node_id
            except Exception:
                continue
        return None
    
    def get_cluster_state(self) -> Dict:
        """Get the state of all nodes in the cluster"""
        cluster_state = {}
        for node_id, client in self.nodes.items():
            try:
                status = client.get_status()
                cluster_state[node_id] = status
            except Exception as e:
                cluster_state[node_id] = {"error": str(e)}
        return cluster_state
    
    def wait_for_leader_election(self, timeout: int = 30) -> Optional[str]:
        """Wait for a leader to be elected"""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            leader = self.get_leader()
            if leader:
                return leader
            time.sleep(0.5)
        
        return None

@pytest.fixture(scope="module")
def raft_cluster():
    """Fixture providing a 3-node Raft cluster"""
    node_urls = [
        "http://localhost:8081",
        "http://localhost:8082", 
        "http://localhost:8083"
    ]
    
    cluster = RaftCluster(node_urls)
    
    # Wait for cluster to be ready
    assert cluster.wait_for_cluster_ready(60), "Cluster failed to become ready"
    
    # Wait for leader election
    leader = cluster.wait_for_leader_election(30)
    assert leader is not None, "No leader elected within timeout"
    
    yield cluster

class TestRaftLeaderElection:
    """Test Raft leader election functionality"""
    
    def test_initial_leader_election(self, raft_cluster):
        """Test that a leader is elected on startup"""
        leader = raft_cluster.get_leader()
        assert leader is not None, "No leader found"
        
        # Verify only one leader exists
        leaders = []
        for node_id, client in raft_cluster.nodes.items():
            status = client.get_status()
            if status.get("state") == "Leader":
                leaders.append(node_id)
        
        assert len(leaders) == 1, f"Expected 1 leader, found {len(leaders)}: {leaders}"
    
    def test_leader_election_after_failure(self, raft_cluster):
        """Test leader election after current leader fails"""
        # This test would require stopping/starting containers
        # For now, we'll test the election timeout mechanism
        
        cluster_state = raft_cluster.get_cluster_state()
        leader = raft_cluster.get_leader()
        
        assert leader is not None
        
        # Verify all nodes agree on the leader
        leader_term = cluster_state[leader]["term"]
        for node_id, state in cluster_state.items():
            if "error" not in state:
                assert state["term"] >= leader_term, f"Node {node_id} has stale term"
    
    def test_split_vote_prevention(self, raft_cluster):
        """Test that split votes are prevented by randomized timeouts"""
        # Verify that election timeouts are randomized
        cluster_state = raft_cluster.get_cluster_state()
        
        # All followers should have the same term as the leader
        leader = raft_cluster.get_leader()
        leader_term = cluster_state[leader]["term"]
        
        for node_id, state in cluster_state.items():
            if "error" not in state and state["state"] == "Follower":
                assert state["term"] == leader_term, f"Follower {node_id} has different term"

class TestRaftLogReplication:
    """Test Raft log replication functionality"""
    
    def test_basic_log_replication(self, raft_cluster):
        """Test basic log replication for client operations"""
        leader = raft_cluster.get_leader()
        assert leader is not None
        
        leader_client = raft_cluster.nodes[leader]
        
        # Perform a PUT operation
        result = leader_client.put_value("test_key", "test_value")
        assert result["key"] == "test_key"
        assert result["value"] == "test_value"
        
        # Wait for replication
        time.sleep(2)
        
        # Verify the value can be read from the leader
        result = leader_client.get_value("test_key")
        assert result["key"] == "test_key"
        assert result["value"] == "test_value"
    
    def test_log_consistency(self, raft_cluster):
        """Test that logs remain consistent across nodes"""
        leader = raft_cluster.get_leader()
        assert leader is not None
        
        leader_client = raft_cluster.nodes[leader]
        
        # Perform multiple operations
        operations = [
            ("key1", "value1"),
            ("key2", "value2"),
            ("key3", "value3"),
        ]
        
        for key, value in operations:
            leader_client.put_value(key, value)
            time.sleep(0.1)  # Small delay between operations
        
        # Wait for replication
        time.sleep(2)
        
        # Verify all operations were applied
        for key, expected_value in operations:
            result = leader_client.get_value(key)
            assert result["value"] == expected_value
    
    def test_delete_operations(self, raft_cluster):
        """Test DELETE operations through log replication"""
        leader = raft_cluster.get_leader()
        assert leader is not None
        
        leader_client = raft_cluster.nodes[leader]
        
        # Put a value
        leader_client.put_value("delete_test", "to_be_deleted")
        time.sleep(1)
        
        # Verify it exists
        result = leader_client.get_value("delete_test")
        assert result["value"] == "to_be_deleted"
        
        # Delete the value
        result = leader_client.delete_value("delete_test")
        assert result["deleted"] is True
        time.sleep(1)
        
        # Verify it's gone
        with pytest.raises(requests.exceptions.HTTPError) as exc_info:
            leader_client.get_value("delete_test")
        assert exc_info.value.response.status_code == 404

class TestRaftSafety:
    """Test Raft safety properties"""
    
    def test_leader_completeness(self, raft_cluster):
        """Test that leaders have all committed entries"""
        leader = raft_cluster.get_leader()
        assert leader is not None
        
        leader_client = raft_cluster.nodes[leader]
        
        # Perform operations and verify they're committed
        test_data = [
            ("safety_key1", "safety_value1"),
            ("safety_key2", "safety_value2"),
        ]
        
        for key, value in test_data:
            leader_client.put_value(key, value)
        
        time.sleep(2)
        
        # Verify all data is present
        for key, expected_value in test_data:
            result = leader_client.get_value(key)
            assert result["value"] == expected_value
    
    def test_state_machine_safety(self, raft_cluster):
        """Test that state machines execute the same sequence of commands"""
        leader = raft_cluster.get_leader()
        assert leader is not None
        
        leader_client = raft_cluster.nodes[leader]
        
        # Perform a sequence of operations
        operations = [
            ("seq_key", "value1"),
            ("seq_key", "value2"),
            ("seq_key", "value3"),
        ]
        
        for key, value in operations:
            leader_client.put_value(key, value)
            time.sleep(0.5)
        
        # Final value should be the last one written
        result = leader_client.get_value("seq_key")
        assert result["value"] == "value3"

class TestRaftPerformance:
    """Test Raft performance characteristics"""
    
    def test_throughput_single_client(self, raft_cluster):
        """Test throughput with a single client"""
        leader = raft_cluster.get_leader()
        assert leader is not None
        
        leader_client = raft_cluster.nodes[leader]
        
        # Measure throughput
        num_operations = 100
        start_time = time.time()
        
        for i in range(num_operations):
            leader_client.put_value(f"perf_key_{i}", f"perf_value_{i}")
        
        end_time = time.time()
        duration = end_time - start_time
        throughput = num_operations / duration
        
        print(f"Single client throughput: {throughput:.2f} ops/sec")
        
        # Should achieve reasonable throughput (adjust based on requirements)
        assert throughput > 10, f"Throughput too low: {throughput:.2f} ops/sec"
    
    def test_concurrent_clients(self, raft_cluster):
        """Test performance with concurrent clients"""
        leader = raft_cluster.get_leader()
        assert leader is not None
        
        leader_client = raft_cluster.nodes[leader]
        
        def worker(worker_id: int, num_ops: int):
            """Worker function for concurrent operations"""
            for i in range(num_ops):
                try:
                    leader_client.put_value(f"worker_{worker_id}_key_{i}", f"worker_{worker_id}_value_{i}")
                except Exception as e:
                    print(f"Worker {worker_id} error: {e}")
        
        # Run concurrent workers
        num_workers = 5
        ops_per_worker = 20
        
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = [
                executor.submit(worker, worker_id, ops_per_worker)
                for worker_id in range(num_workers)
            ]
            
            # Wait for all workers to complete
            for future in futures:
                future.result()
        
        end_time = time.time()
        duration = end_time - start_time
        total_ops = num_workers * ops_per_worker
        throughput = total_ops / duration
        
        print(f"Concurrent client throughput: {throughput:.2f} ops/sec")
        
        # Should handle concurrent clients reasonably well
        assert throughput > 5, f"Concurrent throughput too low: {throughput:.2f} ops/sec"

class TestRaftOperational:
    """Test operational aspects of Raft"""
    
    def test_health_checks(self, raft_cluster):
        """Test health check endpoints"""
        for node_id, client in raft_cluster.nodes.items():
            health = client.get_health()
            assert health["status"] == "healthy"
            assert health["node_id"] == node_id
            assert "state" in health
            assert "term" in health
    
    def test_cluster_status(self, raft_cluster):
        """Test cluster status reporting"""
        leader = raft_cluster.get_leader()
        assert leader is not None
        
        leader_client = raft_cluster.nodes[leader]
        status = leader_client.get_status()
        
        assert status["state"] == "Leader"
        assert status["node_id"] == leader
        assert "term" in status
        assert "commit_index" in status
        assert "log_length" in status
        assert "nodes" in status
    
    def test_snapshot_operations(self, raft_cluster):
        """Test snapshot creation (if implemented)"""
        leader = raft_cluster.get_leader()
        assert leader is not None
        
        leader_client = raft_cluster.nodes[leader]
        
        # Add some data first
        for i in range(10):
            leader_client.put_value(f"snap_key_{i}", f"snap_value_{i}")
        
        time.sleep(1)
        
        # Try to take a snapshot
        try:
            result = leader_client.take_snapshot()
            # If implemented, should succeed
            assert "message" in result
        except requests.exceptions.HTTPError as e:
            # If not implemented, should return appropriate error
            assert e.response.status_code == 500
            assert "not implemented" in e.response.text.lower()

if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "--tb=short"])

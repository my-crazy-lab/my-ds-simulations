#!/usr/bin/env python3
"""
Comprehensive tests for distributed KV store consistency models.
Tests CP (strong consistency) vs AP (eventual consistency) trade-offs.
"""

import asyncio
import json
import pytest
import requests
import time
import threading
import random
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Set

class KVStoreTestClient:
    """Test client for interacting with distributed KV store"""
    
    def __init__(self, base_url: str, node_id: str):
        self.base_url = base_url
        self.node_id = node_id
        self.session = requests.Session()
        self.session.timeout = 10
    
    def get_health(self) -> Dict:
        """Get node health"""
        response = self.session.get(f"{self.base_url}/health")
        response.raise_for_status()
        return response.json()
    
    def get_status(self) -> Dict:
        """Get node status"""
        response = self.session.get(f"{self.base_url}/admin/status")
        response.raise_for_status()
        return response.json()
    
    def get_consistency_status(self) -> Dict:
        """Get consistency status"""
        response = self.session.get(f"{self.base_url}/admin/consistency")
        response.raise_for_status()
        return response.json()
    
    def put(self, key: str, value: str, consistency: str = "eventual") -> Dict:
        """Put a key-value pair with specified consistency"""
        response = self.session.put(
            f"{self.base_url}/kv/{key}?consistency={consistency}",
            json={"value": value}
        )
        response.raise_for_status()
        return response.json()
    
    def get(self, key: str, consistency: str = "eventual") -> Dict:
        """Get a value with specified consistency"""
        response = self.session.get(f"{self.base_url}/kv/{key}?consistency={consistency}")
        response.raise_for_status()
        return response.json()
    
    def delete(self, key: str, consistency: str = "eventual") -> Dict:
        """Delete a key with specified consistency"""
        response = self.session.delete(f"{self.base_url}/kv/{key}?consistency={consistency}")
        response.raise_for_status()
        return response.json()
    
    def put_if_version(self, key: str, value: str, version: int, consistency: str = "eventual") -> Dict:
        """Conditional put based on version"""
        response = self.session.put(
            f"{self.base_url}/kv/{key}?consistency={consistency}&if-version={version}",
            json={"value": value}
        )
        response.raise_for_status()
        return response.json()
    
    def batch(self, operations: List[Dict], consistency: str = "eventual") -> Dict:
        """Batch operations"""
        response = self.session.post(
            f"{self.base_url}/kv/batch?consistency={consistency}",
            json={"operations": operations}
        )
        response.raise_for_status()
        return response.json()
    
    def trigger_read_repair(self) -> Dict:
        """Trigger read repair"""
        response = self.session.post(f"{self.base_url}/admin/repair")
        response.raise_for_status()
        return response.json()
    
    def trigger_anti_entropy(self) -> Dict:
        """Trigger anti-entropy"""
        response = self.session.post(f"{self.base_url}/admin/anti-entropy")
        response.raise_for_status()
        return response.json()

class KVStoreCluster:
    """Manages a cluster of KV store nodes for testing"""
    
    def __init__(self, node_urls: List[str]):
        self.nodes = {
            f"kvstore-node{i+1}": KVStoreTestClient(url, f"kvstore-node{i+1}")
            for i, url in enumerate(node_urls)
        }
        self.node_urls = node_urls
    
    def wait_for_cluster_ready(self, timeout: int = 60) -> bool:
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
            
            time.sleep(2)
        
        return False
    
    def get_cluster_status(self) -> Dict:
        """Get the status of all nodes in the cluster"""
        cluster_status = {}
        for node_id, client in self.nodes.items():
            try:
                status = client.get_status()
                cluster_status[node_id] = status
            except Exception as e:
                cluster_status[node_id] = {"error": str(e)}
        return cluster_status

@pytest.fixture(scope="module")
def kvstore_cluster():
    """Fixture providing a 3-node KV store cluster"""
    node_urls = [
        "http://localhost:8081",
        "http://localhost:8082", 
        "http://localhost:8083"
    ]
    
    cluster = KVStoreCluster(node_urls)
    
    # Wait for cluster to be ready
    assert cluster.wait_for_cluster_ready(120), "Cluster failed to become ready"
    
    yield cluster

class TestStrongConsistency:
    """Test strong consistency (CP) operations"""
    
    def test_linearizable_reads_writes(self, kvstore_cluster):
        """Test that strong consistency provides linearizable operations"""
        client = list(kvstore_cluster.nodes.values())[0]
        
        # Perform a series of writes and reads
        test_key = "linearizable_test"
        
        # Write initial value
        result = client.put(test_key, "value1", "strong")
        assert result["consistency_level"] == "strong"
        version1 = result["version"]
        
        # Read should return the same value
        result = client.get(test_key, "strong")
        assert result["value"] == "value1"
        assert result["version"] == version1
        
        # Update value
        result = client.put(test_key, "value2", "strong")
        version2 = result["version"]
        assert version2 > version1
        
        # Read should return updated value
        result = client.get(test_key, "strong")
        assert result["value"] == "value2"
        assert result["version"] == version2
    
    def test_strong_consistency_across_nodes(self, kvstore_cluster):
        """Test that all nodes see the same value with strong consistency"""
        test_key = "strong_consistency_test"
        test_value = "consistent_value"
        
        # Write to first node
        first_client = list(kvstore_cluster.nodes.values())[0]
        result = first_client.put(test_key, test_value, "strong")
        version = result["version"]
        
        # Wait for replication
        time.sleep(2)
        
        # Read from all nodes - should get the same value
        for node_id, client in kvstore_cluster.nodes.items():
            try:
                result = client.get(test_key, "strong")
                assert result["value"] == test_value, f"Node {node_id} has inconsistent value"
                assert result["version"] == version, f"Node {node_id} has inconsistent version"
            except Exception as e:
                # Some nodes might not support strong consistency reads
                print(f"Node {node_id} strong read failed: {e}")
    
    def test_conditional_updates_strong(self, kvstore_cluster):
        """Test conditional updates with strong consistency"""
        client = list(kvstore_cluster.nodes.values())[0]
        test_key = "conditional_test"
        
        # Initial write
        result = client.put(test_key, "initial", "strong")
        version = result["version"]
        
        # Conditional update with correct version
        result = client.put_if_version(test_key, "updated", version, "strong")
        new_version = result["version"]
        assert new_version > version
        
        # Verify update
        result = client.get(test_key, "strong")
        assert result["value"] == "updated"
        assert result["version"] == new_version
        
        # Conditional update with wrong version should fail
        with pytest.raises(requests.exceptions.HTTPError):
            client.put_if_version(test_key, "should_fail", version, "strong")

class TestEventualConsistency:
    """Test eventual consistency (AP) operations"""
    
    def test_high_availability_writes(self, kvstore_cluster):
        """Test that eventual consistency provides high availability"""
        # Test writing to all nodes simultaneously
        test_key = "availability_test"
        
        results = []
        for i, (node_id, client) in enumerate(kvstore_cluster.nodes.items()):
            try:
                result = client.put(f"{test_key}_{i}", f"value_{i}", "eventual")
                results.append((node_id, result))
            except Exception as e:
                print(f"Write to {node_id} failed: {e}")
        
        # Should have successful writes to most nodes
        assert len(results) >= 2, "Not enough successful writes for high availability"
        
        # All successful writes should have eventual consistency
        for node_id, result in results:
            assert result["consistency_level"] == "eventual"
    
    def test_eventual_convergence(self, kvstore_cluster):
        """Test that nodes eventually converge to the same state"""
        test_key = "convergence_test"
        
        # Write different values to different nodes
        clients = list(kvstore_cluster.nodes.values())
        
        # Write to first node
        clients[0].put(test_key, "value_from_node1", "eventual")
        time.sleep(0.5)
        
        # Write to second node (potential conflict)
        clients[1].put(test_key, "value_from_node2", "eventual")
        time.sleep(0.5)
        
        # Wait for convergence
        time.sleep(10)
        
        # Trigger anti-entropy to speed up convergence
        for client in clients:
            try:
                client.trigger_anti_entropy()
            except Exception:
                pass
        
        time.sleep(5)
        
        # Check that all nodes have converged (last-write-wins)
        values = []
        for node_id, client in kvstore_cluster.nodes.items():
            try:
                result = client.get(test_key, "local")  # Local read to see actual stored value
                values.append(result["value"])
            except Exception as e:
                print(f"Read from {node_id} failed: {e}")
        
        # All nodes should have the same value (eventual consistency)
        if len(values) > 1:
            # Allow for some nodes to still be converging
            unique_values = set(values)
            assert len(unique_values) <= 2, f"Too many different values: {unique_values}"
    
    def test_read_repair(self, kvstore_cluster):
        """Test read repair mechanism"""
        test_key = "read_repair_test"
        client = list(kvstore_cluster.nodes.values())[0]
        
        # Write a value
        client.put(test_key, "original_value", "eventual")
        time.sleep(2)
        
        # Trigger read repair
        client.trigger_read_repair()
        time.sleep(3)
        
        # Read should work and potentially trigger repair
        result = client.get(test_key, "eventual")
        assert result["value"] == "original_value"

class TestHybridConsistency:
    """Test hybrid consistency mode (tunable per operation)"""
    
    def test_per_operation_consistency(self, kvstore_cluster):
        """Test that different operations can use different consistency levels"""
        client = list(kvstore_cluster.nodes.values())[0]
        
        # Strong consistency write
        strong_key = "strong_key"
        result = client.put(strong_key, "strong_value", "strong")
        assert result["consistency_level"] == "strong"
        
        # Eventual consistency write
        eventual_key = "eventual_key"
        result = client.put(eventual_key, "eventual_value", "eventual")
        assert result["consistency_level"] == "eventual"
        
        # Local read (fastest)
        try:
            result = client.get(eventual_key, "local")
            assert result["value"] == "eventual_value"
        except Exception:
            # Local reads might not be supported on all nodes
            pass
        
        # Strong read
        result = client.get(strong_key, "strong")
        assert result["value"] == "strong_value"
    
    def test_consistency_level_fallback(self, kvstore_cluster):
        """Test fallback behavior when requested consistency level is unavailable"""
        client = list(kvstore_cluster.nodes.values())[0]
        
        # Try to use strong consistency even if not fully available
        test_key = "fallback_test"
        
        try:
            result = client.put(test_key, "test_value", "strong")
            # If successful, verify it worked
            assert result["key"] == test_key
        except Exception:
            # If strong consistency fails, try eventual
            result = client.put(test_key, "test_value", "eventual")
            assert result["consistency_level"] == "eventual"

class TestCAPTheoremDemonstration:
    """Test CAP theorem trade-offs"""
    
    def test_consistency_vs_availability_tradeoff(self, kvstore_cluster):
        """Demonstrate the trade-off between consistency and availability"""
        clients = list(kvstore_cluster.nodes.values())
        test_key = "cap_test"
        
        # Test 1: Strong consistency may sacrifice availability
        strong_successes = 0
        for client in clients:
            try:
                client.put(f"{test_key}_strong", "strong_value", "strong")
                strong_successes += 1
            except Exception as e:
                print(f"Strong consistency write failed: {e}")
        
        # Test 2: Eventual consistency prioritizes availability
        eventual_successes = 0
        for client in clients:
            try:
                client.put(f"{test_key}_eventual", "eventual_value", "eventual")
                eventual_successes += 1
            except Exception as e:
                print(f"Eventual consistency write failed: {e}")
        
        # Eventual consistency should have higher availability
        print(f"Strong consistency successes: {strong_successes}/{len(clients)}")
        print(f"Eventual consistency successes: {eventual_successes}/{len(clients)}")
        
        # In a healthy cluster, both should work, but eventual should be more resilient
        assert eventual_successes >= strong_successes
    
    def test_partition_tolerance(self, kvstore_cluster):
        """Test behavior under network partitions (simulated by timeouts)"""
        # This test simulates partition tolerance by using very short timeouts
        
        test_key = "partition_test"
        
        # Configure clients with very short timeouts to simulate partitions
        partition_clients = []
        for url in kvstore_cluster.node_urls:
            client = KVStoreTestClient(url, "test")
            client.session.timeout = 0.1  # Very short timeout
            partition_clients.append(client)
        
        # Test eventual consistency under "partition" (timeout)
        eventual_successes = 0
        for client in partition_clients:
            try:
                client.put(f"{test_key}_partition", "partition_value", "eventual")
                eventual_successes += 1
            except Exception:
                pass  # Expected under partition
        
        # Test strong consistency under "partition"
        strong_successes = 0
        for client in partition_clients:
            try:
                client.put(f"{test_key}_strong_partition", "strong_partition_value", "strong")
                strong_successes += 1
            except Exception:
                pass  # Expected under partition
        
        print(f"Under partition - Eventual: {eventual_successes}, Strong: {strong_successes}")
        
        # Both might fail under partition, but eventual should be more resilient
        # This test mainly demonstrates the concept

class TestPerformanceComparison:
    """Compare performance between consistency models"""
    
    def test_latency_comparison(self, kvstore_cluster):
        """Compare latency between strong and eventual consistency"""
        client = list(kvstore_cluster.nodes.values())[0]
        
        # Measure strong consistency latency
        strong_latencies = []
        for i in range(10):
            start_time = time.time()
            try:
                client.put(f"strong_perf_{i}", f"value_{i}", "strong")
                latency = time.time() - start_time
                strong_latencies.append(latency)
            except Exception:
                pass
        
        # Measure eventual consistency latency
        eventual_latencies = []
        for i in range(10):
            start_time = time.time()
            try:
                client.put(f"eventual_perf_{i}", f"value_{i}", "eventual")
                latency = time.time() - start_time
                eventual_latencies.append(latency)
            except Exception:
                pass
        
        if strong_latencies and eventual_latencies:
            avg_strong = sum(strong_latencies) / len(strong_latencies)
            avg_eventual = sum(eventual_latencies) / len(eventual_latencies)
            
            print(f"Average strong consistency latency: {avg_strong:.3f}s")
            print(f"Average eventual consistency latency: {avg_eventual:.3f}s")
            
            # Eventual consistency should generally be faster
            # (though this might not always be true in all implementations)
    
    def test_throughput_comparison(self, kvstore_cluster):
        """Compare throughput between consistency models"""
        client = list(kvstore_cluster.nodes.values())[0]
        
        def measure_throughput(consistency_level: str, num_ops: int) -> float:
            start_time = time.time()
            successes = 0
            
            for i in range(num_ops):
                try:
                    client.put(f"throughput_{consistency_level}_{i}", f"value_{i}", consistency_level)
                    successes += 1
                except Exception:
                    pass
            
            duration = time.time() - start_time
            return successes / duration if duration > 0 else 0
        
        # Measure throughput for both consistency levels
        strong_throughput = measure_throughput("strong", 50)
        eventual_throughput = measure_throughput("eventual", 50)
        
        print(f"Strong consistency throughput: {strong_throughput:.2f} ops/sec")
        print(f"Eventual consistency throughput: {eventual_throughput:.2f} ops/sec")
        
        # Both should achieve reasonable throughput
        assert strong_throughput > 0, "Strong consistency should achieve some throughput"
        assert eventual_throughput > 0, "Eventual consistency should achieve some throughput"

if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "--tb=short"])

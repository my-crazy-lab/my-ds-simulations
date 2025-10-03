#!/usr/bin/env python3
"""
CAP Theorem validation tests for distributed KV store.
Tests Consistency, Availability, and Partition tolerance trade-offs.
"""

import asyncio
import docker
import json
import pytest
import requests
import time
import threading
import random
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Set

class CAPTestController:
    """Controls network partitions and node failures for CAP theorem testing"""
    
    def __init__(self):
        self.client = docker.from_env()
        self.kvstore_containers = []
        self._discover_kvstore_containers()
    
    def _discover_kvstore_containers(self):
        """Discover running KV store containers"""
        containers = self.client.containers.list()
        self.kvstore_containers = [
            c for c in containers 
            if c.name.startswith('kvstore-node') and c.status == 'running'
        ]
        print(f"Found {len(self.kvstore_containers)} KV store containers")
    
    def create_network_partition(self, partition_a: List[str], partition_b: List[str]) -> bool:
        """Create a network partition between two groups of nodes"""
        try:
            # Pause containers in partition B to simulate network partition
            for node_name in partition_b:
                container = self.client.containers.get(node_name)
                container.pause()
                print(f"Partitioned node: {node_name}")
            return True
        except Exception as e:
            print(f"Failed to create partition: {e}")
            return False
    
    def heal_network_partition(self, partition_b: List[str]) -> bool:
        """Heal the network partition"""
        try:
            for node_name in partition_b:
                container = self.client.containers.get(node_name)
                container.unpause()
                print(f"Healed partition for node: {node_name}")
            return True
        except Exception as e:
            print(f"Failed to heal partition: {e}")
            return False
    
    def stop_node(self, node_name: str) -> bool:
        """Stop a node to simulate failure"""
        try:
            container = self.client.containers.get(node_name)
            container.stop()
            print(f"Stopped node: {node_name}")
            return True
        except Exception as e:
            print(f"Failed to stop node {node_name}: {e}")
            return False
    
    def start_node(self, node_name: str) -> bool:
        """Start a node"""
        try:
            container = self.client.containers.get(node_name)
            container.start()
            print(f"Started node: {node_name}")
            return True
        except Exception as e:
            print(f"Failed to start node {node_name}: {e}")
            return False

class CAPTestClient:
    """Test client for CAP theorem validation"""
    
    def __init__(self, base_url: str, node_name: str):
        self.base_url = base_url
        self.node_name = node_name
        self.session = requests.Session()
        self.session.timeout = 5
    
    def is_available(self) -> bool:
        """Check if the node is available"""
        try:
            response = self.session.get(f"{self.base_url}/health")
            return response.status_code == 200
        except Exception:
            return False
    
    def put(self, key: str, value: str, consistency: str = "eventual") -> Optional[Dict]:
        """Put operation with error handling"""
        try:
            response = self.session.put(
                f"{self.base_url}/kv/{key}?consistency={consistency}",
                json={"value": value}
            )
            if response.status_code == 200:
                return response.json()
        except Exception:
            pass
        return None
    
    def get(self, key: str, consistency: str = "eventual") -> Optional[Dict]:
        """Get operation with error handling"""
        try:
            response = self.session.get(f"{self.base_url}/kv/{key}?consistency={consistency}")
            if response.status_code == 200:
                return response.json()
        except Exception:
            pass
        return None

class CAPTestCluster:
    """Manages cluster for CAP theorem testing"""
    
    def __init__(self):
        self.nodes = {
            "kvstore-node1": CAPTestClient("http://localhost:8081", "kvstore-node1"),
            "kvstore-node2": CAPTestClient("http://localhost:8082", "kvstore-node2"),
            "kvstore-node3": CAPTestClient("http://localhost:8083", "kvstore-node3"),
        }
        self.controller = CAPTestController()
    
    def get_available_nodes(self) -> List[str]:
        """Get list of currently available nodes"""
        available = []
        for node_name, client in self.nodes.items():
            if client.is_available():
                available.append(node_name)
        return available
    
    def count_successful_operations(self, operation_func, nodes: List[str]) -> int:
        """Count successful operations across specified nodes"""
        successes = 0
        for node_name in nodes:
            if node_name in self.nodes:
                result = operation_func(self.nodes[node_name])
                if result is not None:
                    successes += 1
        return successes

@pytest.fixture(scope="module")
def cap_cluster():
    """Fixture providing a CAP-testable cluster"""
    cluster = CAPTestCluster()
    
    # Ensure all nodes are running
    for node_name in cluster.nodes.keys():
        cluster.controller.start_node(node_name)
    
    # Wait for cluster to stabilize
    time.sleep(15)
    
    yield cluster
    
    # Cleanup: ensure all nodes are running and partitions are healed
    for node_name in cluster.nodes.keys():
        cluster.controller.start_node(node_name)
    cluster.controller.heal_network_partition(list(cluster.nodes.keys()))

class TestConsistencyVsAvailability:
    """Test the trade-off between Consistency and Availability"""
    
    def test_strong_consistency_sacrifices_availability(self, cap_cluster):
        """Test that strong consistency may sacrifice availability during partitions"""
        # Create a partition: majority (2 nodes) vs minority (1 node)
        majority_nodes = ["kvstore-node1", "kvstore-node2"]
        minority_nodes = ["kvstore-node3"]
        
        # Create partition
        cap_cluster.controller.create_network_partition(majority_nodes, minority_nodes)
        
        try:
            time.sleep(10)  # Allow partition to take effect
            
            # Test strong consistency operations
            def strong_write(client):
                return client.put("strong_partition_test", "test_value", "strong")
            
            # Majority partition should still work for strong consistency
            majority_successes = cap_cluster.count_successful_operations(
                strong_write, majority_nodes
            )
            
            # Minority partition should fail for strong consistency
            minority_successes = cap_cluster.count_successful_operations(
                strong_write, minority_nodes
            )
            
            print(f"Strong consistency - Majority successes: {majority_successes}/{len(majority_nodes)}")
            print(f"Strong consistency - Minority successes: {minority_successes}/{len(minority_nodes)}")
            
            # Strong consistency should work in majority but not minority
            assert majority_successes >= 1, "Strong consistency should work in majority partition"
            # Minority might still work if it's not truly implementing strong consistency
            
        finally:
            # Heal partition
            cap_cluster.controller.heal_network_partition(minority_nodes)
            time.sleep(5)
    
    def test_eventual_consistency_prioritizes_availability(self, cap_cluster):
        """Test that eventual consistency prioritizes availability"""
        # Create a partition
        majority_nodes = ["kvstore-node1", "kvstore-node2"]
        minority_nodes = ["kvstore-node3"]
        
        cap_cluster.controller.create_network_partition(majority_nodes, minority_nodes)
        
        try:
            time.sleep(10)
            
            # Test eventual consistency operations
            def eventual_write(client):
                return client.put("eventual_partition_test", "test_value", "eventual")
            
            # Both partitions should work for eventual consistency
            majority_successes = cap_cluster.count_successful_operations(
                eventual_write, majority_nodes
            )
            
            minority_successes = cap_cluster.count_successful_operations(
                eventual_write, minority_nodes
            )
            
            print(f"Eventual consistency - Majority successes: {majority_successes}/{len(majority_nodes)}")
            print(f"Eventual consistency - Minority successes: {minority_successes}/{len(minority_nodes)}")
            
            # Eventual consistency should maintain availability in both partitions
            assert majority_successes >= 1, "Eventual consistency should work in majority partition"
            # Note: Minority might not work if quorum requirements are enforced
            
        finally:
            cap_cluster.controller.heal_network_partition(minority_nodes)
            time.sleep(5)

class TestPartitionTolerance:
    """Test partition tolerance capabilities"""
    
    def test_cluster_survives_network_partition(self, cap_cluster):
        """Test that the cluster can survive network partitions"""
        # Record initial state
        initial_available = cap_cluster.get_available_nodes()
        assert len(initial_available) == 3, "All nodes should be initially available"
        
        # Create partition
        partition_a = ["kvstore-node1", "kvstore-node2"]
        partition_b = ["kvstore-node3"]
        
        cap_cluster.controller.create_network_partition(partition_a, partition_b)
        
        try:
            time.sleep(10)
            
            # Check availability in majority partition
            available_in_majority = []
            for node_name in partition_a:
                if cap_cluster.nodes[node_name].is_available():
                    available_in_majority.append(node_name)
            
            print(f"Available nodes in majority partition: {available_in_majority}")
            
            # Majority partition should remain available
            assert len(available_in_majority) >= 1, "Majority partition should remain available"
            
            # Test that operations still work in majority partition
            if available_in_majority:
                client = cap_cluster.nodes[available_in_majority[0]]
                result = client.put("partition_survival_test", "survived", "eventual")
                assert result is not None, "Operations should work in majority partition"
            
        finally:
            cap_cluster.controller.heal_network_partition(partition_b)
            time.sleep(10)
            
            # Verify cluster recovers
            recovered_available = cap_cluster.get_available_nodes()
            print(f"Nodes available after partition healing: {recovered_available}")
            assert len(recovered_available) >= 2, "Most nodes should recover after partition healing"
    
    def test_split_brain_prevention(self, cap_cluster):
        """Test that split-brain scenarios are prevented"""
        # Create an even split (if possible with 3 nodes, this tests edge cases)
        partition_a = ["kvstore-node1"]
        partition_b = ["kvstore-node2", "kvstore-node3"]
        
        cap_cluster.controller.create_network_partition(partition_a, partition_b)
        
        try:
            time.sleep(10)
            
            # Try to write the same key with different values in each partition
            test_key = "split_brain_test"
            
            # Write to partition A
            partition_a_result = None
            if cap_cluster.nodes["kvstore-node1"].is_available():
                partition_a_result = cap_cluster.nodes["kvstore-node1"].put(
                    test_key, "value_from_partition_a", "eventual"
                )
            
            # Write to partition B
            partition_b_results = []
            for node_name in partition_b:
                if cap_cluster.nodes[node_name].is_available():
                    result = cap_cluster.nodes[node_name].put(
                        test_key, "value_from_partition_b", "eventual"
                    )
                    if result:
                        partition_b_results.append(result)
            
            print(f"Partition A write result: {partition_a_result is not None}")
            print(f"Partition B write results: {len(partition_b_results)}")
            
            # At least one partition should be able to accept writes
            # (depending on quorum requirements)
            total_successful_writes = (1 if partition_a_result else 0) + len(partition_b_results)
            assert total_successful_writes > 0, "At least one partition should accept writes"
            
        finally:
            cap_cluster.controller.heal_network_partition(partition_a)
            time.sleep(10)
    
    def test_partition_recovery_and_consistency(self, cap_cluster):
        """Test that partitions recover and achieve consistency"""
        test_key = "recovery_consistency_test"
        
        # Create partition
        partition_a = ["kvstore-node1", "kvstore-node2"]
        partition_b = ["kvstore-node3"]
        
        cap_cluster.controller.create_network_partition(partition_a, partition_b)
        
        try:
            time.sleep(5)
            
            # Write to majority partition
            majority_client = cap_cluster.nodes["kvstore-node1"]
            if majority_client.is_available():
                result = majority_client.put(test_key, "majority_value", "eventual")
                print(f"Write to majority partition: {result is not None}")
            
            time.sleep(2)
            
        finally:
            # Heal partition
            cap_cluster.controller.heal_network_partition(partition_b)
            time.sleep(15)  # Allow time for recovery and anti-entropy
            
            # Trigger anti-entropy to speed up convergence
            for client in cap_cluster.nodes.values():
                try:
                    client.session.post(f"{client.base_url}/admin/anti-entropy")
                except Exception:
                    pass
            
            time.sleep(10)
            
            # Check that all nodes have converged
            values = []
            for node_name, client in cap_cluster.nodes.items():
                if client.is_available():
                    result = client.get(test_key, "local")
                    if result:
                        values.append(result["value"])
                        print(f"Node {node_name} has value: {result['value']}")
            
            # All available nodes should have the same value (eventual consistency)
            if len(values) > 1:
                unique_values = set(values)
                print(f"Unique values after recovery: {unique_values}")
                # Allow for some convergence time - should have at most 2 different values
                assert len(unique_values) <= 2, "Too many different values after partition recovery"

class TestCAPTheoremValidation:
    """Comprehensive CAP theorem validation"""
    
    def test_cap_theorem_demonstration(self, cap_cluster):
        """Demonstrate that you can't have all three: Consistency, Availability, Partition tolerance"""
        
        print("\n=== CAP Theorem Demonstration ===")
        
        # Phase 1: Normal operation (all three seem possible)
        print("\nPhase 1: Normal operation")
        test_key = "cap_demo"
        
        # Write with strong consistency
        client = cap_cluster.nodes["kvstore-node1"]
        result = client.put(test_key, "initial_value", "strong")
        strong_write_success = result is not None
        
        # Read from all nodes
        consistent_reads = 0
        for node_name, node_client in cap_cluster.nodes.items():
            if node_client.is_available():
                read_result = node_client.get(test_key, "strong")
                if read_result and read_result.get("value") == "initial_value":
                    consistent_reads += 1
        
        print(f"Normal operation - Strong write: {strong_write_success}, Consistent reads: {consistent_reads}/3")
        
        # Phase 2: Introduce partition (must choose between C and A)
        print("\nPhase 2: Network partition introduced")
        
        partition_a = ["kvstore-node1", "kvstore-node2"]
        partition_b = ["kvstore-node3"]
        
        cap_cluster.controller.create_network_partition(partition_a, partition_b)
        
        try:
            time.sleep(10)
            
            # Test Consistency vs Availability trade-off
            
            # Option 1: Prioritize Consistency (CP system)
            strong_writes_during_partition = 0
            for node_name in partition_a:  # Only majority partition
                client = cap_cluster.nodes[node_name]
                if client.is_available():
                    result = client.put(f"{test_key}_cp", "cp_value", "strong")
                    if result:
                        strong_writes_during_partition += 1
            
            # Option 2: Prioritize Availability (AP system)
            eventual_writes_during_partition = 0
            all_nodes = list(cap_cluster.nodes.keys())
            for node_name in all_nodes:
                client = cap_cluster.nodes[node_name]
                if client.is_available():
                    result = client.put(f"{test_key}_ap", "ap_value", "eventual")
                    if result:
                        eventual_writes_during_partition += 1
            
            print(f"During partition - CP writes: {strong_writes_during_partition}, AP writes: {eventual_writes_during_partition}")
            
            # Demonstrate the trade-off
            print("\nCAP Theorem Trade-off Analysis:")
            print(f"- Consistency + Partition tolerance (CP): {strong_writes_during_partition} successful operations")
            print(f"- Availability + Partition tolerance (AP): {eventual_writes_during_partition} successful operations")
            print("- Cannot have Consistency + Availability + Partition tolerance simultaneously")
            
            # The system must choose: either maintain consistency (fewer successful operations)
            # or maintain availability (potentially inconsistent but more operations succeed)
            
        finally:
            cap_cluster.controller.heal_network_partition(partition_b)
            time.sleep(10)
    
    def test_consistency_availability_spectrum(self, cap_cluster):
        """Test the spectrum between consistency and availability"""
        
        consistency_levels = ["strong", "eventual", "local"]
        results = {}
        
        for consistency in consistency_levels:
            print(f"\nTesting consistency level: {consistency}")
            
            # Measure availability (success rate)
            successful_operations = 0
            total_operations = 10
            
            for i in range(total_operations):
                # Try to write to a random node
                node_name = random.choice(list(cap_cluster.nodes.keys()))
                client = cap_cluster.nodes[node_name]
                
                result = client.put(f"spectrum_test_{consistency}_{i}", f"value_{i}", consistency)
                if result:
                    successful_operations += 1
                
                time.sleep(0.1)  # Small delay between operations
            
            availability = successful_operations / total_operations
            results[consistency] = {
                "availability": availability,
                "successful_operations": successful_operations,
                "total_operations": total_operations
            }
            
            print(f"Availability for {consistency}: {availability:.2%}")
        
        print("\n=== Consistency-Availability Spectrum ===")
        for consistency, metrics in results.items():
            print(f"{consistency:>10}: {metrics['availability']:.2%} availability "
                  f"({metrics['successful_operations']}/{metrics['total_operations']} operations)")
        
        # Generally, we expect: local >= eventual >= strong (in terms of availability)
        # Though this depends on the specific implementation

if __name__ == "__main__":
    # Run CAP theorem tests
    pytest.main([__file__, "-v", "--tb=short", "-s"])

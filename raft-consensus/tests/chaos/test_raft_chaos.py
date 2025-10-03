#!/usr/bin/env python3
"""
Chaos engineering tests for Raft consensus algorithm.
Tests network partitions, node failures, and other failure scenarios.
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

class DockerChaosController:
    """Controls Docker containers for chaos testing"""
    
    def __init__(self):
        self.client = docker.from_env()
        self.raft_containers = []
        self._discover_raft_containers()
    
    def _discover_raft_containers(self):
        """Discover running Raft containers"""
        containers = self.client.containers.list()
        self.raft_containers = [
            c for c in containers 
            if c.name.startswith('raft-node') and c.status == 'running'
        ]
        print(f"Found {len(self.raft_containers)} Raft containers")
    
    def stop_container(self, container_name: str) -> bool:
        """Stop a container"""
        try:
            container = self.client.containers.get(container_name)
            container.stop()
            print(f"Stopped container: {container_name}")
            return True
        except Exception as e:
            print(f"Failed to stop container {container_name}: {e}")
            return False
    
    def start_container(self, container_name: str) -> bool:
        """Start a container"""
        try:
            container = self.client.containers.get(container_name)
            container.start()
            print(f"Started container: {container_name}")
            return True
        except Exception as e:
            print(f"Failed to start container {container_name}: {e}")
            return False
    
    def restart_container(self, container_name: str) -> bool:
        """Restart a container"""
        try:
            container = self.client.containers.get(container_name)
            container.restart()
            print(f"Restarted container: {container_name}")
            return True
        except Exception as e:
            print(f"Failed to restart container {container_name}: {e}")
            return False
    
    def pause_container(self, container_name: str) -> bool:
        """Pause a container (simulates network partition)"""
        try:
            container = self.client.containers.get(container_name)
            container.pause()
            print(f"Paused container: {container_name}")
            return True
        except Exception as e:
            print(f"Failed to pause container {container_name}: {e}")
            return False
    
    def unpause_container(self, container_name: str) -> bool:
        """Unpause a container"""
        try:
            container = self.client.containers.get(container_name)
            container.unpause()
            print(f"Unpaused container: {container_name}")
            return True
        except Exception as e:
            print(f"Failed to unpause container {container_name}: {e}")
            return False
    
    def get_container_status(self, container_name: str) -> str:
        """Get container status"""
        try:
            container = self.client.containers.get(container_name)
            return container.status
        except Exception:
            return "not_found"

class RaftChaosTestClient:
    """Test client with chaos testing capabilities"""
    
    def __init__(self, base_url: str, node_name: str):
        self.base_url = base_url
        self.node_name = node_name
        self.session = requests.Session()
        self.session.timeout = 3  # Shorter timeout for chaos tests
    
    def is_reachable(self) -> bool:
        """Check if the node is reachable"""
        try:
            response = self.session.get(f"{self.base_url}/health")
            return response.status_code == 200
        except Exception:
            return False
    
    def get_status(self) -> Optional[Dict]:
        """Get node status (returns None if unreachable)"""
        try:
            response = self.session.get(f"{self.base_url}/admin/status")
            response.raise_for_status()
            return response.json()
        except Exception:
            return None
    
    def put_value(self, key: str, value: str) -> bool:
        """Put a key-value pair (returns success status)"""
        try:
            response = self.session.put(
                f"{self.base_url}/kv/{key}",
                json={"value": value}
            )
            return response.status_code == 200
        except Exception:
            return False
    
    def get_value(self, key: str) -> Optional[str]:
        """Get a value by key (returns None if not found or unreachable)"""
        try:
            response = self.session.get(f"{self.base_url}/kv/{key}")
            if response.status_code == 200:
                return response.json()["value"]
        except Exception:
            pass
        return None

class RaftChaosCluster:
    """Manages a Raft cluster for chaos testing"""
    
    def __init__(self):
        self.nodes = {
            "raft-node1": RaftChaosTestClient("http://localhost:8081", "raft-node1"),
            "raft-node2": RaftChaosTestClient("http://localhost:8082", "raft-node2"),
            "raft-node3": RaftChaosTestClient("http://localhost:8083", "raft-node3"),
        }
        self.chaos_controller = DockerChaosController()
    
    def get_reachable_nodes(self) -> List[str]:
        """Get list of currently reachable nodes"""
        reachable = []
        for node_name, client in self.nodes.items():
            if client.is_reachable():
                reachable.append(node_name)
        return reachable
    
    def get_leader(self) -> Optional[str]:
        """Find the current leader among reachable nodes"""
        for node_name, client in self.nodes.items():
            status = client.get_status()
            if status and status.get("state") == "Leader":
                return node_name
        return None
    
    def wait_for_leader_election(self, timeout: int = 30) -> Optional[str]:
        """Wait for a leader to be elected"""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            leader = self.get_leader()
            if leader:
                return leader
            time.sleep(1)
        
        return None
    
    def count_nodes_by_state(self) -> Dict[str, int]:
        """Count nodes by their Raft state"""
        states = {"Leader": 0, "Follower": 0, "Candidate": 0, "Unreachable": 0}
        
        for node_name, client in self.nodes.items():
            status = client.get_status()
            if status:
                state = status.get("state", "Unknown")
                states[state] = states.get(state, 0) + 1
            else:
                states["Unreachable"] += 1
        
        return states

@pytest.fixture(scope="module")
def chaos_cluster():
    """Fixture providing a chaos-testable Raft cluster"""
    cluster = RaftChaosCluster()
    
    # Ensure all nodes are running
    for node_name in cluster.nodes.keys():
        cluster.chaos_controller.start_container(node_name)
    
    # Wait for cluster to stabilize
    time.sleep(10)
    
    # Verify we have a leader
    leader = cluster.wait_for_leader_election(30)
    assert leader is not None, "No leader elected before chaos testing"
    
    yield cluster
    
    # Cleanup: ensure all nodes are running
    for node_name in cluster.nodes.keys():
        cluster.chaos_controller.start_container(node_name)
        cluster.chaos_controller.unpause_container(node_name)

class TestRaftNetworkPartitions:
    """Test Raft behavior under network partitions"""
    
    def test_minority_partition_isolation(self, chaos_cluster):
        """Test that minority partition cannot make progress"""
        # Get initial leader
        initial_leader = chaos_cluster.get_leader()
        assert initial_leader is not None
        
        # Create minority partition by isolating one node
        isolated_node = "raft-node3"
        chaos_cluster.chaos_controller.pause_container(isolated_node)
        
        try:
            # Wait for cluster to stabilize
            time.sleep(10)
            
            # Majority should still have a leader
            leader = chaos_cluster.get_leader()
            assert leader is not None, "Majority partition should have a leader"
            assert leader != isolated_node, "Isolated node should not be leader"
            
            # Majority should be able to make progress
            leader_client = chaos_cluster.nodes[leader]
            success = leader_client.put_value("partition_test", "majority_value")
            assert success, "Majority partition should accept writes"
            
            # Verify the write
            value = leader_client.get_value("partition_test")
            assert value == "majority_value"
            
        finally:
            # Restore the isolated node
            chaos_cluster.chaos_controller.unpause_container(isolated_node)
            time.sleep(5)
    
    def test_majority_partition_recovery(self, chaos_cluster):
        """Test that majority partition can recover minority nodes"""
        # Isolate one node
        isolated_node = "raft-node2"
        chaos_cluster.chaos_controller.pause_container(isolated_node)
        
        try:
            # Wait for stabilization
            time.sleep(10)
            
            # Perform operations on majority
            leader = chaos_cluster.get_leader()
            assert leader is not None
            
            leader_client = chaos_cluster.nodes[leader]
            test_data = [
                ("recovery_key1", "recovery_value1"),
                ("recovery_key2", "recovery_value2"),
            ]
            
            for key, value in test_data:
                success = leader_client.put_value(key, value)
                assert success, f"Failed to write {key}={value}"
                time.sleep(1)
            
            # Restore the isolated node
            chaos_cluster.chaos_controller.unpause_container(isolated_node)
            time.sleep(10)  # Allow time for catch-up
            
            # Verify the recovered node has the data
            recovered_client = chaos_cluster.nodes[isolated_node]
            for key, expected_value in test_data:
                # Try multiple times as the node might still be catching up
                for attempt in range(5):
                    value = recovered_client.get_value(key)
                    if value == expected_value:
                        break
                    time.sleep(2)
                else:
                    pytest.fail(f"Recovered node missing data: {key}={expected_value}")
        
        finally:
            chaos_cluster.chaos_controller.unpause_container(isolated_node)
    
    def test_split_brain_prevention(self, chaos_cluster):
        """Test that split-brain scenarios are prevented"""
        # This test simulates a network partition that splits the cluster
        # Since we have 3 nodes, we'll isolate one and verify only one side can make progress
        
        isolated_node = "raft-node1"
        chaos_cluster.chaos_controller.pause_container(isolated_node)
        
        try:
            time.sleep(10)
            
            # Count leaders - should be at most 1
            states = chaos_cluster.count_nodes_by_state()
            assert states["Leader"] <= 1, f"Split brain detected: {states['Leader']} leaders"
            
            # The majority (2 nodes) should have a leader
            assert states["Leader"] == 1, "Majority partition should have exactly one leader"
            
        finally:
            chaos_cluster.chaos_controller.unpause_container(isolated_node)

class TestRaftNodeFailures:
    """Test Raft behavior under node failures"""
    
    def test_leader_failure_recovery(self, chaos_cluster):
        """Test recovery from leader failure"""
        # Get current leader
        initial_leader = chaos_cluster.get_leader()
        assert initial_leader is not None
        
        # Stop the leader
        chaos_cluster.chaos_controller.stop_container(initial_leader)
        
        try:
            # Wait for new leader election
            new_leader = chaos_cluster.wait_for_leader_election(30)
            assert new_leader is not None, "No new leader elected after leader failure"
            assert new_leader != initial_leader, "Same leader re-elected"
            
            # Verify new leader can accept writes
            new_leader_client = chaos_cluster.nodes[new_leader]
            success = new_leader_client.put_value("leader_failure_test", "new_leader_value")
            assert success, "New leader should accept writes"
            
            # Verify the write
            value = new_leader_client.get_value("leader_failure_test")
            assert value == "new_leader_value"
            
        finally:
            # Restart the failed leader
            chaos_cluster.chaos_controller.start_container(initial_leader)
            time.sleep(10)
    
    def test_follower_failure_tolerance(self, chaos_cluster):
        """Test that follower failures don't affect cluster operation"""
        # Get current leader
        leader = chaos_cluster.get_leader()
        assert leader is not None
        
        # Find a follower to fail
        follower = None
        for node_name, client in chaos_cluster.nodes.items():
            if node_name != leader:
                status = client.get_status()
                if status and status.get("state") == "Follower":
                    follower = node_name
                    break
        
        assert follower is not None, "No follower found"
        
        # Stop the follower
        chaos_cluster.chaos_controller.stop_container(follower)
        
        try:
            time.sleep(5)
            
            # Leader should still be operational
            current_leader = chaos_cluster.get_leader()
            assert current_leader == leader, "Leader should remain the same"
            
            # Cluster should still accept writes
            leader_client = chaos_cluster.nodes[leader]
            success = leader_client.put_value("follower_failure_test", "still_working")
            assert success, "Cluster should still accept writes with one follower down"
            
        finally:
            # Restart the failed follower
            chaos_cluster.chaos_controller.start_container(follower)
            time.sleep(5)
    
    def test_cascading_failures(self, chaos_cluster):
        """Test behavior under cascading node failures"""
        # Stop two nodes sequentially to test minority scenarios
        nodes_to_fail = ["raft-node2", "raft-node3"]
        
        try:
            # Stop first node
            chaos_cluster.chaos_controller.stop_container(nodes_to_fail[0])
            time.sleep(5)
            
            # Cluster should still work with 2/3 nodes
            leader = chaos_cluster.get_leader()
            assert leader is not None, "Cluster should still have leader with 2/3 nodes"
            
            # Stop second node - now we have minority
            chaos_cluster.chaos_controller.stop_container(nodes_to_fail[1])
            time.sleep(10)
            
            # Now cluster should not be able to make progress
            remaining_node = "raft-node1"
            remaining_client = chaos_cluster.nodes[remaining_node]
            
            # The remaining node should not be able to accept writes
            success = remaining_client.put_value("minority_test", "should_fail")
            assert not success, "Minority node should not accept writes"
            
        finally:
            # Restart all failed nodes
            for node in nodes_to_fail:
                chaos_cluster.chaos_controller.start_container(node)
            time.sleep(15)

class TestRaftChaosScenarios:
    """Test complex chaos scenarios"""
    
    def test_random_chaos_monkey(self, chaos_cluster):
        """Test cluster resilience under random failures"""
        # Run chaos for a period while performing operations
        chaos_duration = 60  # seconds
        start_time = time.time()
        
        operation_count = 0
        successful_operations = 0
        
        def chaos_worker():
            """Worker that randomly causes chaos"""
            while time.time() - start_time < chaos_duration:
                # Random chaos action
                action = random.choice(["pause", "unpause", "restart"])
                node = random.choice(list(chaos_cluster.nodes.keys()))
                
                if action == "pause":
                    chaos_cluster.chaos_controller.pause_container(node)
                    time.sleep(random.uniform(5, 15))
                    chaos_cluster.chaos_controller.unpause_container(node)
                elif action == "restart":
                    chaos_cluster.chaos_controller.restart_container(node)
                
                time.sleep(random.uniform(10, 20))
        
        def operation_worker():
            """Worker that performs operations"""
            nonlocal operation_count, successful_operations
            
            while time.time() - start_time < chaos_duration:
                operation_count += 1
                
                # Try to find a leader and perform operation
                leader = chaos_cluster.get_leader()
                if leader:
                    leader_client = chaos_cluster.nodes[leader]
                    key = f"chaos_key_{operation_count}"
                    value = f"chaos_value_{operation_count}"
                    
                    if leader_client.put_value(key, value):
                        successful_operations += 1
                
                time.sleep(random.uniform(1, 3))
        
        # Run chaos and operations concurrently
        with ThreadPoolExecutor(max_workers=2) as executor:
            chaos_future = executor.submit(chaos_worker)
            operation_future = executor.submit(operation_worker)
            
            # Wait for both to complete
            chaos_future.result()
            operation_future.result()
        
        # Calculate success rate
        success_rate = successful_operations / operation_count if operation_count > 0 else 0
        
        print(f"Chaos test results:")
        print(f"  Total operations: {operation_count}")
        print(f"  Successful operations: {successful_operations}")
        print(f"  Success rate: {success_rate:.2%}")
        
        # Should maintain reasonable availability under chaos
        assert success_rate > 0.5, f"Success rate too low under chaos: {success_rate:.2%}"
        
        # Ensure cluster is still functional after chaos
        time.sleep(10)
        final_leader = chaos_cluster.wait_for_leader_election(30)
        assert final_leader is not None, "Cluster should recover after chaos"
    
    def test_data_consistency_under_chaos(self, chaos_cluster):
        """Test that data remains consistent under chaos conditions"""
        # Write initial data
        leader = chaos_cluster.get_leader()
        assert leader is not None
        
        leader_client = chaos_cluster.nodes[leader]
        initial_data = {
            "consistency_key1": "initial_value1",
            "consistency_key2": "initial_value2",
        }
        
        for key, value in initial_data.items():
            success = leader_client.put_value(key, value)
            assert success, f"Failed to write initial data: {key}={value}"
        
        # Cause some chaos
        chaos_node = random.choice(list(chaos_cluster.nodes.keys()))
        chaos_cluster.chaos_controller.restart_container(chaos_node)
        time.sleep(10)
        
        # Verify data consistency across all reachable nodes
        reachable_nodes = chaos_cluster.get_reachable_nodes()
        assert len(reachable_nodes) >= 2, "Need at least 2 reachable nodes for consistency check"
        
        for key, expected_value in initial_data.items():
            values_seen = set()
            
            for node_name in reachable_nodes:
                client = chaos_cluster.nodes[node_name]
                value = client.get_value(key)
                if value is not None:
                    values_seen.add(value)
            
            # All nodes should have the same value
            assert len(values_seen) <= 1, f"Inconsistent values for {key}: {values_seen}"
            if values_seen:
                assert expected_value in values_seen, f"Expected value {expected_value} not found for {key}"

if __name__ == "__main__":
    # Run chaos tests
    pytest.main([__file__, "-v", "--tb=short", "-s"])

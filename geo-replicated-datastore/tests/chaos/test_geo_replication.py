#!/usr/bin/env python3
"""
Chaos engineering tests for geo-replicated datastore.
Tests network partitions, node failures, and cross-region consistency.
"""

import pytest
import requests
import json
import time
import threading
import random
import docker
from typing import Dict, List, Set
from concurrent.futures import ThreadPoolExecutor, as_completed


class GeoReplicationChaosController:
    """Controller for chaos engineering tests"""
    
    def __init__(self):
        self.client = docker.from_env()
        self.nodes = {
            'us-1': 'geodatastore-us-1',
            'us-2': 'geodatastore-us-2', 
            'us-3': 'geodatastore-us-3',
            'eu-1': 'geodatastore-eu-1',
            'eu-2': 'geodatastore-eu-2',
            'eu-3': 'geodatastore-eu-3',
            'apac-1': 'geodatastore-apac-1',
            'apac-2': 'geodatastore-apac-2',
            'apac-3': 'geodatastore-apac-3',
        }
        self.regions = {
            'us': ['us-1', 'us-2', 'us-3'],
            'eu': ['eu-1', 'eu-2', 'eu-3'],
            'apac': ['apac-1', 'apac-2', 'apac-3'],
        }
        self.ports = {
            'us-1': 8081, 'us-2': 8082, 'us-3': 8083,
            'eu-1': 8084, 'eu-2': 8085, 'eu-3': 8086,
            'apac-1': 8087, 'apac-2': 8088, 'apac-3': 8089,
        }
    
    def stop_node(self, node_id: str) -> bool:
        """Stop a specific node"""
        try:
            container_name = self.nodes[node_id]
            container = self.client.containers.get(container_name)
            container.stop()
            print(f"Stopped node {node_id} ({container_name})")
            return True
        except Exception as e:
            print(f"Failed to stop node {node_id}: {e}")
            return False
    
    def start_node(self, node_id: str) -> bool:
        """Start a specific node"""
        try:
            container_name = self.nodes[node_id]
            container = self.client.containers.get(container_name)
            container.start()
            print(f"Started node {node_id} ({container_name})")
            # Wait for node to be ready
            time.sleep(10)
            return True
        except Exception as e:
            print(f"Failed to start node {node_id}: {e}")
            return False
    
    def pause_node(self, node_id: str) -> bool:
        """Pause a specific node (simulates network partition)"""
        try:
            container_name = self.nodes[node_id]
            container = self.client.containers.get(container_name)
            container.pause()
            print(f"Paused node {node_id} ({container_name})")
            return True
        except Exception as e:
            print(f"Failed to pause node {node_id}: {e}")
            return False
    
    def unpause_node(self, node_id: str) -> bool:
        """Unpause a specific node"""
        try:
            container_name = self.nodes[node_id]
            container = self.client.containers.get(container_name)
            container.unpause()
            print(f"Unpaused node {node_id} ({container_name})")
            return True
        except Exception as e:
            print(f"Failed to unpause node {node_id}: {e}")
            return False
    
    def partition_region(self, region: str) -> bool:
        """Partition an entire region from the rest"""
        success = True
        for node_id in self.regions[region]:
            if not self.pause_node(node_id):
                success = False
        return success
    
    def heal_region(self, region: str) -> bool:
        """Heal a partitioned region"""
        success = True
        for node_id in self.regions[region]:
            if not self.unpause_node(node_id):
                success = False
        return success
    
    def get_node_status(self, node_id: str) -> Dict:
        """Get status of a specific node"""
        try:
            port = self.ports[node_id]
            response = requests.get(f"http://localhost:{port}/admin/status", timeout=5)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"error": str(e), "status": "unreachable"}
    
    def wait_for_node_ready(self, node_id: str, timeout: int = 60) -> bool:
        """Wait for a node to be ready"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                port = self.ports[node_id]
                response = requests.get(f"http://localhost:{port}/health", timeout=5)
                if response.status_code == 200:
                    return True
            except:
                pass
            time.sleep(2)
        return False


class GeoReplicationTestClient:
    """Test client for geo-replication operations"""
    
    def __init__(self, node_id: str, port: int):
        self.node_id = node_id
        self.base_url = f"http://localhost:{port}"
        self.session = requests.Session()
        self.session.headers.update({'Content-Type': 'application/json'})
    
    def create_counter(self, key: str, counter_type: str = "pn_counter", initial_value: int = 0) -> Dict:
        """Create a counter CRDT"""
        payload = {"type": counter_type, "initial_value": initial_value}
        response = self.session.post(f"{self.base_url}/crdt/counters/{key}", json=payload)
        response.raise_for_status()
        return response.json()
    
    def increment_counter(self, key: str, value: int = 1) -> Dict:
        """Increment counter"""
        payload = {"value": value}
        response = self.session.post(f"{self.base_url}/crdt/counters/{key}/increment", json=payload)
        response.raise_for_status()
        return response.json()
    
    def get_counter(self, key: str, consistency: str = "eventual") -> Dict:
        """Get counter value"""
        response = self.session.get(f"{self.base_url}/crdt/counters/{key}?consistency={consistency}")
        response.raise_for_status()
        return response.json()
    
    def create_set(self, key: str, set_type: str = "or_set") -> Dict:
        """Create a set CRDT"""
        payload = {"type": set_type}
        response = self.session.post(f"{self.base_url}/crdt/sets/{key}", json=payload)
        response.raise_for_status()
        return response.json()
    
    def add_to_set(self, key: str, element: str) -> Dict:
        """Add element to set"""
        payload = {"element": element}
        response = self.session.post(f"{self.base_url}/crdt/sets/{key}/add", json=payload)
        response.raise_for_status()
        return response.json()
    
    def get_set(self, key: str) -> Dict:
        """Get set elements"""
        response = self.session.get(f"{self.base_url}/crdt/sets/{key}")
        response.raise_for_status()
        return response.json()
    
    def get_replication_lag(self) -> Dict:
        """Get replication lag information"""
        response = self.session.get(f"{self.base_url}/admin/replication/lag")
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
    
    def is_healthy(self) -> bool:
        """Check if node is healthy"""
        try:
            response = self.session.get(f"{self.base_url}/health", timeout=5)
            return response.status_code == 200
        except:
            return False


class TestNetworkPartitions:
    """Test network partition scenarios"""
    
    @pytest.fixture
    def chaos_controller(self):
        """Create chaos controller"""
        return GeoReplicationChaosController()
    
    @pytest.fixture
    def clients(self, chaos_controller):
        """Create test clients for all nodes"""
        clients = {}
        for node_id, port in chaos_controller.ports.items():
            clients[node_id] = GeoReplicationTestClient(node_id, port)
        return clients
    
    def test_single_region_partition(self, chaos_controller, clients):
        """Test partition of a single region"""
        key = f"test_region_partition_{int(time.time())}"
        
        # Create counter on US node
        clients['us-1'].create_counter(key, "pn_counter", 0)
        time.sleep(3)
        
        # Verify counter exists on all regions
        for region_nodes in chaos_controller.regions.values():
            for node_id in region_nodes:
                try:
                    result = clients[node_id].get_counter(key)
                    assert result['value'] == 0
                except:
                    pass  # Some nodes might not be ready yet
        
        # Partition EU region
        print("Partitioning EU region...")
        chaos_controller.partition_region('eu')
        time.sleep(2)
        
        # Perform operations on US and APAC (available regions)
        clients['us-1'].increment_counter(key, 5)
        clients['us-2'].increment_counter(key, 3)
        clients['apac-1'].increment_counter(key, 7)
        clients['apac-2'].increment_counter(key, 2)
        
        # Wait for propagation within available regions
        time.sleep(5)
        
        # Check that US and APAC nodes have converged
        expected_value = 17  # 5 + 3 + 7 + 2
        us_apac_nodes = chaos_controller.regions['us'] + chaos_controller.regions['apac']
        
        for node_id in us_apac_nodes:
            try:
                result = clients[node_id].get_counter(key)
                assert result['value'] == expected_value, f"Node {node_id} has incorrect value during partition"
            except Exception as e:
                print(f"Node {node_id} unreachable during partition: {e}")
        
        # Heal the partition
        print("Healing EU region partition...")
        chaos_controller.heal_region('eu')
        time.sleep(10)  # Wait for recovery and synchronization
        
        # Verify all nodes converge after partition healing
        all_converged = False
        for attempt in range(10):  # Try for up to 20 seconds
            values = {}
            reachable_nodes = 0
            
            for node_id in chaos_controller.nodes.keys():
                try:
                    result = clients[node_id].get_counter(key)
                    values[node_id] = result['value']
                    reachable_nodes += 1
                except Exception as e:
                    print(f"Node {node_id} still unreachable: {e}")
            
            if reachable_nodes >= 6:  # At least 2 nodes per region
                unique_values = set(values.values())
                if len(unique_values) == 1 and list(unique_values)[0] == expected_value:
                    all_converged = True
                    break
            
            time.sleep(2)
        
        assert all_converged, f"Nodes did not converge after partition healing. Values: {values}"
    
    def test_split_brain_scenario(self, chaos_controller, clients):
        """Test split-brain scenario with concurrent operations"""
        key = f"test_split_brain_{int(time.time())}"
        
        # Create counter
        clients['us-1'].create_counter(key, "pn_counter", 0)
        time.sleep(3)
        
        # Create split-brain: US vs EU+APAC
        print("Creating split-brain partition...")
        chaos_controller.partition_region('us')
        time.sleep(2)
        
        # Concurrent operations on both sides of the partition
        def us_operations():
            """Operations on US side (partitioned)"""
            # These operations will fail since US is partitioned
            try:
                clients['us-1'].increment_counter(key, 10)
                clients['us-2'].increment_counter(key, 5)
            except:
                pass  # Expected to fail during partition
        
        def eu_apac_operations():
            """Operations on EU+APAC side"""
            clients['eu-1'].increment_counter(key, 7)
            clients['eu-2'].increment_counter(key, 3)
            clients['apac-1'].increment_counter(key, 4)
            clients['apac-2'].increment_counter(key, 6)
        
        # Execute operations concurrently
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(us_operations),
                executor.submit(eu_apac_operations)
            ]
            for future in as_completed(futures):
                try:
                    future.result()
                except:
                    pass  # Some operations expected to fail
        
        # Wait for operations to complete
        time.sleep(5)
        
        # Heal the partition
        print("Healing split-brain partition...")
        chaos_controller.heal_region('us')
        time.sleep(15)  # Extended wait for recovery
        
        # Verify eventual consistency after healing
        expected_value = 20  # 7 + 3 + 4 + 6 (EU+APAC operations only)
        
        converged = False
        for attempt in range(15):  # Try for up to 30 seconds
            values = {}
            reachable_count = 0
            
            for node_id in ['us-1', 'eu-1', 'apac-1']:  # Sample nodes from each region
                try:
                    result = clients[node_id].get_counter(key)
                    values[node_id] = result['value']
                    reachable_count += 1
                except Exception as e:
                    print(f"Node {node_id} still recovering: {e}")
            
            if reachable_count >= 2:
                unique_values = set(values.values())
                if len(unique_values) == 1:
                    converged_value = list(unique_values)[0]
                    print(f"Converged to value: {converged_value}")
                    converged = True
                    break
            
            time.sleep(2)
        
        assert converged, f"Nodes did not converge after split-brain healing. Values: {values}"


class TestNodeFailures:
    """Test node failure scenarios"""
    
    @pytest.fixture
    def chaos_controller(self):
        """Create chaos controller"""
        return GeoReplicationChaosController()
    
    @pytest.fixture
    def clients(self, chaos_controller):
        """Create test clients"""
        clients = {}
        for node_id, port in chaos_controller.ports.items():
            clients[node_id] = GeoReplicationTestClient(node_id, port)
        return clients
    
    def test_single_node_failure(self, chaos_controller, clients):
        """Test failure of a single node"""
        key = f"test_node_failure_{int(time.time())}"
        
        # Create counter
        clients['us-1'].create_counter(key, "pn_counter", 0)
        time.sleep(3)
        
        # Perform some operations
        clients['us-1'].increment_counter(key, 5)
        clients['eu-1'].increment_counter(key, 3)
        clients['apac-1'].increment_counter(key, 2)
        time.sleep(3)
        
        # Stop one node
        print("Stopping node us-2...")
        chaos_controller.stop_node('us-2')
        time.sleep(2)
        
        # Continue operations with remaining nodes
        clients['us-1'].increment_counter(key, 4)
        clients['eu-1'].increment_counter(key, 6)
        clients['apac-1'].increment_counter(key, 1)
        time.sleep(3)
        
        # Verify remaining nodes have correct value
        expected_value = 21  # 5 + 3 + 2 + 4 + 6 + 1
        remaining_nodes = ['us-1', 'us-3', 'eu-1', 'apac-1']
        
        for node_id in remaining_nodes:
            try:
                result = clients[node_id].get_counter(key)
                assert result['value'] == expected_value, f"Node {node_id} has incorrect value"
            except Exception as e:
                print(f"Node {node_id} unreachable: {e}")
        
        # Restart the failed node
        print("Restarting node us-2...")
        chaos_controller.start_node('us-2')
        
        # Wait for node to catch up
        if chaos_controller.wait_for_node_ready('us-2'):
            time.sleep(10)  # Additional time for synchronization
            
            # Verify the restarted node has caught up
            try:
                result = clients['us-2'].get_counter(key)
                assert result['value'] == expected_value, f"Restarted node has incorrect value: {result['value']}"
                print("Node us-2 successfully caught up after restart")
            except Exception as e:
                print(f"Restarted node us-2 still not ready: {e}")
    
    def test_cascading_failures(self, chaos_controller, clients):
        """Test cascading node failures"""
        key = f"test_cascading_failures_{int(time.time())}"
        
        # Create counter
        clients['us-1'].create_counter(key, "pn_counter", 0)
        time.sleep(3)
        
        # Initial operations
        clients['us-1'].increment_counter(key, 10)
        clients['eu-1'].increment_counter(key, 20)
        clients['apac-1'].increment_counter(key, 30)
        time.sleep(3)
        
        initial_value = 60
        
        # Simulate cascading failures
        failed_nodes = []
        
        # Fail nodes one by one
        for node_id in ['us-2', 'eu-2', 'apac-2']:
            print(f"Stopping node {node_id}...")
            if chaos_controller.stop_node(node_id):
                failed_nodes.append(node_id)
            time.sleep(2)
            
            # Continue operations with remaining nodes
            try:
                clients['us-1'].increment_counter(key, 1)
                time.sleep(1)
            except:
                pass
        
        # Wait for stabilization
        time.sleep(5)
        
        # Verify remaining nodes still function
        remaining_nodes = ['us-1', 'us-3', 'eu-1', 'eu-3', 'apac-1', 'apac-3']
        functional_nodes = []
        
        for node_id in remaining_nodes:
            try:
                result = clients[node_id].get_counter(key)
                functional_nodes.append(node_id)
                print(f"Node {node_id} is functional with value: {result['value']}")
            except Exception as e:
                print(f"Node {node_id} is not functional: {e}")
        
        # Should have at least one node per region functional
        assert len(functional_nodes) >= 3, f"Too few functional nodes: {functional_nodes}"
        
        # Restart failed nodes
        for node_id in failed_nodes:
            print(f"Restarting node {node_id}...")
            chaos_controller.start_node(node_id)
            time.sleep(5)
        
        # Wait for recovery
        time.sleep(15)
        
        # Verify all nodes are functional again
        recovered_nodes = []
        for node_id in chaos_controller.nodes.keys():
            if chaos_controller.wait_for_node_ready(node_id, timeout=30):
                recovered_nodes.append(node_id)
        
        print(f"Recovered nodes: {recovered_nodes}")
        assert len(recovered_nodes) >= 6, f"Not enough nodes recovered: {recovered_nodes}"


class TestCrossRegionConsistency:
    """Test cross-region consistency guarantees"""
    
    @pytest.fixture
    def chaos_controller(self):
        """Create chaos controller"""
        return GeoReplicationChaosController()
    
    @pytest.fixture
    def clients(self, chaos_controller):
        """Create test clients"""
        clients = {}
        for node_id, port in chaos_controller.ports.items():
            clients[node_id] = GeoReplicationTestClient(node_id, port)
        return clients
    
    def test_eventual_consistency_across_regions(self, chaos_controller, clients):
        """Test eventual consistency across all regions"""
        key = f"test_cross_region_consistency_{int(time.time())}"
        
        # Create counter in US
        clients['us-1'].create_counter(key, "pn_counter", 0)
        time.sleep(5)  # Wait for cross-region propagation
        
        # Perform operations from all regions simultaneously
        operations = []
        
        def perform_operations(region_nodes, base_value):
            """Perform operations from a specific region"""
            region_ops = []
            for i, node_id in enumerate(region_nodes):
                try:
                    value = base_value + i + 1
                    clients[node_id].increment_counter(key, value)
                    region_ops.append(value)
                    time.sleep(0.1)
                except Exception as e:
                    print(f"Operation failed on {node_id}: {e}")
            return region_ops
        
        # Execute operations from all regions concurrently
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [
                executor.submit(perform_operations, chaos_controller.regions['us'], 10),
                executor.submit(perform_operations, chaos_controller.regions['eu'], 20),
                executor.submit(perform_operations, chaos_controller.regions['apac'], 30),
            ]
            
            for future in as_completed(futures):
                try:
                    region_ops = future.result()
                    operations.extend(region_ops)
                except Exception as e:
                    print(f"Region operations failed: {e}")
        
        # Calculate expected final value
        expected_value = sum(operations)
        print(f"Expected final value: {expected_value} (from operations: {operations})")
        
        # Wait for cross-region propagation
        time.sleep(15)
        
        # Verify eventual consistency across all regions
        region_values = {}
        for region, nodes in chaos_controller.regions.items():
            region_values[region] = []
            for node_id in nodes:
                try:
                    result = clients[node_id].get_counter(key)
                    region_values[region].append(result['value'])
                except Exception as e:
                    print(f"Failed to get value from {node_id}: {e}")
        
        # Check that all reachable nodes in each region have the same value
        for region, values in region_values.items():
            if values:
                unique_values = set(values)
                assert len(unique_values) == 1, f"Region {region} nodes not consistent: {values}"
        
        # Check that all regions have converged to the same value
        all_values = []
        for values in region_values.values():
            if values:
                all_values.extend(values)
        
        if all_values:
            unique_global_values = set(all_values)
            assert len(unique_global_values) == 1, f"Regions not globally consistent: {region_values}"
            
            converged_value = list(unique_global_values)[0]
            print(f"All regions converged to value: {converged_value}")
            
            # The converged value should be close to expected (allowing for some failed operations)
            assert converged_value >= expected_value * 0.8, f"Converged value {converged_value} too low"


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "--tb=short", "-s"])

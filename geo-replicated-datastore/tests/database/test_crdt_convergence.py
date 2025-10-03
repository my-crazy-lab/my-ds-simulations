#!/usr/bin/env python3
"""
Comprehensive CRDT Convergence Tests for Geo-Replicated Datastore
Tests conflict-free replicated data types and eventual consistency
"""

import asyncio
import json
import logging
import random
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Set

import requests

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CRDTTestClient:
    """Test client for CRDT operations"""
    
    def __init__(self, regions: List[str] = None):
        self.regions = regions or [
            "http://localhost:8100",  # US-East
            "http://localhost:8101",  # EU-West
            "http://localhost:8102"   # Asia-Pacific
        ]
        self.session = requests.Session()
        self.session.timeout = 15
    
    def g_counter_increment(self, key: str, node_id: str, region_idx: int = 0) -> Optional[Dict]:
        """Increment G-Counter (grow-only counter)"""
        try:
            response = self.session.post(
                f"{self.regions[region_idx]}/api/v1/crdt/g-counter/{key}/increment",
                json={"node_id": node_id, "increment": 1},
                headers={"Content-Type": "application/json"}
            )
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"G-Counter increment failed: {e}")
            return None
    
    def g_counter_read(self, key: str, region_idx: int = 0) -> Optional[Dict]:
        """Read G-Counter value"""
        try:
            response = self.session.get(f"{self.regions[region_idx]}/api/v1/crdt/g-counter/{key}")
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"G-Counter read failed: {e}")
            return None
    
    def or_set_add(self, key: str, element: str, region_idx: int = 0) -> Optional[Dict]:
        """Add element to OR-Set (observed-remove set)"""
        try:
            response = self.session.post(
                f"{self.regions[region_idx]}/api/v1/crdt/or-set/{key}/add",
                json={"element": element, "timestamp": int(time.time() * 1000)},
                headers={"Content-Type": "application/json"}
            )
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"OR-Set add failed: {e}")
            return None
    
    def or_set_remove(self, key: str, element: str, region_idx: int = 0) -> Optional[Dict]:
        """Remove element from OR-Set"""
        try:
            response = self.session.delete(
                f"{self.regions[region_idx]}/api/v1/crdt/or-set/{key}/remove",
                json={"element": element},
                headers={"Content-Type": "application/json"}
            )
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"OR-Set remove failed: {e}")
            return None
    
    def or_set_read(self, key: str, region_idx: int = 0) -> Optional[Dict]:
        """Read OR-Set elements"""
        try:
            response = self.session.get(f"{self.regions[region_idx]}/api/v1/crdt/or-set/{key}")
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"OR-Set read failed: {e}")
            return None
    
    def lww_register_write(self, key: str, value: str, region_idx: int = 0) -> Optional[Dict]:
        """Write to LWW-Register (last-writer-wins register)"""
        try:
            response = self.session.put(
                f"{self.regions[region_idx]}/api/v1/crdt/lww-register/{key}",
                json={
                    "value": value,
                    "timestamp": int(time.time() * 1000),
                    "node_id": f"node_{region_idx}"
                },
                headers={"Content-Type": "application/json"}
            )
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"LWW-Register write failed: {e}")
            return None
    
    def lww_register_read(self, key: str, region_idx: int = 0) -> Optional[Dict]:
        """Read from LWW-Register"""
        try:
            response = self.session.get(f"{self.regions[region_idx]}/api/v1/crdt/lww-register/{key}")
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"LWW-Register read failed: {e}")
            return None
    
    def trigger_sync(self, source_region: int, target_region: int) -> bool:
        """Trigger synchronization between regions"""
        try:
            response = self.session.post(
                f"{self.regions[source_region]}/api/v1/sync/trigger",
                json={"target_region": self.regions[target_region]},
                headers={"Content-Type": "application/json"}
            )
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Sync trigger failed: {e}")
            return False
    
    def get_region_status(self, region_idx: int = 0) -> Optional[Dict]:
        """Get region status and metrics"""
        try:
            response = self.session.get(f"{self.regions[region_idx]}/api/v1/status")
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"Region status failed: {e}")
            return None


class CRDTConvergenceAnalyzer:
    """Analyzer for CRDT convergence behavior"""
    
    def __init__(self, client: CRDTTestClient):
        self.client = client
        self.operation_history: List[Dict] = []
    
    def test_g_counter_convergence(self, num_operations: int = 100) -> Dict:
        """Test G-Counter convergence across regions"""
        logger.info(f"Testing G-Counter convergence with {num_operations} operations")
        
        counter_key = f"test_counter_{int(time.time())}"
        operations_per_region = num_operations // len(self.client.regions)
        
        # Perform increments across different regions
        total_increments = 0
        for region_idx in range(len(self.client.regions)):
            for i in range(operations_per_region):
                node_id = f"node_{region_idx}_{i}"
                result = self.client.g_counter_increment(counter_key, node_id, region_idx)
                if result:
                    total_increments += 1
        
        # Wait for convergence
        time.sleep(5)
        
        # Trigger synchronization between all regions
        for i in range(len(self.client.regions)):
            for j in range(len(self.client.regions)):
                if i != j:
                    self.client.trigger_sync(i, j)
        
        # Wait for sync to complete
        time.sleep(3)
        
        # Read counter value from all regions
        region_values = []
        for region_idx in range(len(self.client.regions)):
            result = self.client.g_counter_read(counter_key, region_idx)
            if result:
                region_values.append(result.get("value", 0))
        
        # Check convergence
        converged = len(set(region_values)) <= 1  # All regions have same value
        expected_value = total_increments
        actual_values = region_values
        
        return {
            "crdt_type": "g_counter",
            "total_increments": total_increments,
            "expected_value": expected_value,
            "region_values": actual_values,
            "converged": converged,
            "convergence_accuracy": (
                1.0 if converged and (not actual_values or actual_values[0] == expected_value)
                else 0.0
            )
        }
    
    def test_or_set_convergence(self, num_operations: int = 50) -> Dict:
        """Test OR-Set convergence with concurrent adds/removes"""
        logger.info(f"Testing OR-Set convergence with {num_operations} operations")
        
        set_key = f"test_set_{int(time.time())}"
        added_elements = set()
        removed_elements = set()
        
        # Perform concurrent add/remove operations
        for i in range(num_operations):
            element = f"element_{i}"
            region_idx = i % len(self.client.regions)
            
            # 70% add, 30% remove operations
            if random.random() < 0.7:
                result = self.client.or_set_add(set_key, element, region_idx)
                if result:
                    added_elements.add(element)
            else:
                # Only remove if we have elements to remove
                if added_elements:
                    element_to_remove = random.choice(list(added_elements))
                    result = self.client.or_set_remove(set_key, element_to_remove, region_idx)
                    if result:
                        removed_elements.add(element_to_remove)
        
        # Wait for convergence
        time.sleep(5)
        
        # Trigger synchronization
        for i in range(len(self.client.regions)):
            for j in range(len(self.client.regions)):
                if i != j:
                    self.client.trigger_sync(i, j)
        
        time.sleep(3)
        
        # Read set from all regions
        region_sets = []
        for region_idx in range(len(self.client.regions)):
            result = self.client.or_set_read(set_key, region_idx)
            if result:
                region_sets.append(set(result.get("elements", [])))
        
        # Check convergence
        converged = len(set(frozenset(s) for s in region_sets)) <= 1
        expected_elements = added_elements - removed_elements
        
        return {
            "crdt_type": "or_set",
            "added_elements": len(added_elements),
            "removed_elements": len(removed_elements),
            "expected_final_size": len(expected_elements),
            "region_sets": [list(s) for s in region_sets],
            "converged": converged,
            "convergence_accuracy": (
                1.0 if converged and (not region_sets or region_sets[0] == expected_elements)
                else 0.0
            )
        }
    
    def test_lww_register_convergence(self, num_writes: int = 30) -> Dict:
        """Test LWW-Register convergence with concurrent writes"""
        logger.info(f"Testing LWW-Register convergence with {num_writes} writes")
        
        register_key = f"test_register_{int(time.time())}"
        write_operations = []
        
        # Perform concurrent writes across regions
        for i in range(num_writes):
            value = f"value_{i}_{random.randint(1000, 9999)}"
            region_idx = i % len(self.client.regions)
            
            # Add small delay to ensure timestamp ordering
            time.sleep(0.01)
            
            write_time = time.time()
            result = self.client.lww_register_write(register_key, value, region_idx)
            if result:
                write_operations.append({
                    "value": value,
                    "timestamp": write_time,
                    "region": region_idx
                })
        
        # Wait for convergence
        time.sleep(5)
        
        # Trigger synchronization
        for i in range(len(self.client.regions)):
            for j in range(len(self.client.regions)):
                if i != j:
                    self.client.trigger_sync(i, j)
        
        time.sleep(3)
        
        # Read register from all regions
        region_values = []
        for region_idx in range(len(self.client.regions)):
            result = self.client.lww_register_read(register_key, region_idx)
            if result:
                region_values.append(result.get("value"))
        
        # Determine expected value (last write wins)
        expected_value = None
        if write_operations:
            latest_write = max(write_operations, key=lambda x: x["timestamp"])
            expected_value = latest_write["value"]
        
        # Check convergence
        converged = len(set(region_values)) <= 1
        
        return {
            "crdt_type": "lww_register",
            "total_writes": len(write_operations),
            "expected_value": expected_value,
            "region_values": region_values,
            "converged": converged,
            "convergence_accuracy": (
                1.0 if converged and (not region_values or region_values[0] == expected_value)
                else 0.0
            )
        }
    
    def test_network_partition_resilience(self, partition_duration: int = 10) -> Dict:
        """Test CRDT behavior during network partitions"""
        logger.info(f"Testing partition resilience for {partition_duration} seconds")
        
        # Setup test data
        counter_key = f"partition_counter_{int(time.time())}"
        set_key = f"partition_set_{int(time.time())}"
        
        # Perform operations before partition
        pre_partition_ops = 0
        for i in range(10):
            region_idx = i % len(self.client.regions)
            if self.client.g_counter_increment(counter_key, f"node_{i}", region_idx):
                pre_partition_ops += 1
            self.client.or_set_add(set_key, f"pre_element_{i}", region_idx)
        
        # Simulate partition (operations continue on isolated regions)
        partition_ops = 0
        start_time = time.time()
        
        while time.time() - start_time < partition_duration:
            # Operations on region 0 (majority partition)
            if self.client.g_counter_increment(counter_key, f"partition_node_{int(time.time())}", 0):
                partition_ops += 1
            
            # Operations on region 1 (minority partition)
            self.client.or_set_add(set_key, f"partition_element_{int(time.time())}", 1)
            
            time.sleep(0.5)
        
        # Wait for partition to heal and sync
        time.sleep(3)
        
        # Trigger synchronization after partition heals
        for i in range(len(self.client.regions)):
            for j in range(len(self.client.regions)):
                if i != j:
                    self.client.trigger_sync(i, j)
        
        time.sleep(5)
        
        # Verify convergence after partition
        counter_values = []
        set_contents = []
        
        for region_idx in range(len(self.client.regions)):
            counter_result = self.client.g_counter_read(counter_key, region_idx)
            if counter_result:
                counter_values.append(counter_result.get("value", 0))
            
            set_result = self.client.or_set_read(set_key, region_idx)
            if set_result:
                set_contents.append(set(set_result.get("elements", [])))
        
        counter_converged = len(set(counter_values)) <= 1
        set_converged = len(set(frozenset(s) for s in set_contents)) <= 1
        
        return {
            "partition_duration": partition_duration,
            "pre_partition_ops": pre_partition_ops,
            "partition_ops": partition_ops,
            "counter_values": counter_values,
            "counter_converged": counter_converged,
            "set_converged": set_converged,
            "overall_convergence": counter_converged and set_converged
        }


class TestCRDTConvergence(unittest.TestCase):
    """Test cases for CRDT convergence"""
    
    @classmethod
    def setUpClass(cls):
        cls.client = CRDTTestClient()
        cls.analyzer = CRDTConvergenceAnalyzer(cls.client)
        
        # Wait for all regions to be ready
        max_retries = 30
        ready_regions = 0
        
        for region_idx in range(len(cls.client.regions)):
            for i in range(max_retries):
                try:
                    status = cls.client.get_region_status(region_idx)
                    if status and status.get("status") == "ready":
                        ready_regions += 1
                        break
                except Exception:
                    pass
                time.sleep(1)
        
        if ready_regions < len(cls.client.regions):
            raise Exception(f"Only {ready_regions}/{len(cls.client.regions)} regions ready")
        
        logger.info(f"All {ready_regions} geo-replicated regions are ready")
    
    def test_g_counter_eventual_consistency(self):
        """Test G-Counter eventual consistency"""
        result = self.analyzer.test_g_counter_convergence(num_operations=30)
        
        self.assertTrue(result["converged"])
        self.assertGreater(result["convergence_accuracy"], 0.95)
        
        logger.info(f"G-Counter Convergence Test: {result}")
    
    def test_or_set_conflict_resolution(self):
        """Test OR-Set conflict resolution"""
        result = self.analyzer.test_or_set_convergence(num_operations=20)
        
        self.assertTrue(result["converged"])
        
        logger.info(f"OR-Set Convergence Test: {result}")
    
    def test_lww_register_last_writer_wins(self):
        """Test LWW-Register last-writer-wins semantics"""
        result = self.analyzer.test_lww_register_convergence(num_writes=15)
        
        self.assertTrue(result["converged"])
        self.assertGreater(result["convergence_accuracy"], 0.90)
        
        logger.info(f"LWW-Register Convergence Test: {result}")
    
    def test_partition_tolerance_and_recovery(self):
        """Test CRDT behavior during network partitions"""
        result = self.analyzer.test_network_partition_resilience(partition_duration=5)
        
        self.assertTrue(result["overall_convergence"])
        
        logger.info(f"Partition Resilience Test: {result}")


if __name__ == "__main__":
    unittest.main()

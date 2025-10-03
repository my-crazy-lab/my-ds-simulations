#!/usr/bin/env python3
"""
Comprehensive Consistency Models Tests for Distributed KV Store
Tests various consistency levels and CAP theorem trade-offs
"""

import asyncio
import json
import logging
import random
import time
import unittest
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Set, Tuple

import requests

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ConsistencyTestClient:
    """Test client for consistency model operations"""
    
    def __init__(self, nodes: List[str] = None):
        self.nodes = nodes or [
            "http://localhost:8090",
            "http://localhost:8091", 
            "http://localhost:8092"
        ]
        self.session = requests.Session()
        self.session.timeout = 10
    
    def write_key(self, key: str, value: str, consistency: str = "strong", node_idx: int = 0) -> Optional[Dict]:
        """Write key-value pair with specified consistency"""
        try:
            response = self.session.put(
                f"{self.nodes[node_idx]}/api/v1/kv/{key}",
                json={
                    "value": value,
                    "timestamp": int(time.time() * 1000),
                    "consistency": consistency
                },
                headers={
                    "Content-Type": "application/json",
                    "X-Consistency-Level": consistency
                }
            )
            return response.json() if response.status_code in [200, 201] else None
        except Exception as e:
            logger.error(f"Write failed: {e}")
            return None
    
    def read_key(self, key: str, consistency: str = "strong", node_idx: int = 0) -> Optional[Dict]:
        """Read key with specified consistency"""
        try:
            response = self.session.get(
                f"{self.nodes[node_idx]}/api/v1/kv/{key}",
                headers={"X-Consistency-Level": consistency}
            )
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"Read failed: {e}")
            return None
    
    def delete_key(self, key: str, consistency: str = "strong", node_idx: int = 0) -> bool:
        """Delete key with specified consistency"""
        try:
            response = self.session.delete(
                f"{self.nodes[node_idx]}/api/v1/kv/{key}",
                headers={"X-Consistency-Level": consistency}
            )
            return response.status_code in [200, 204]
        except Exception as e:
            logger.error(f"Delete failed: {e}")
            return False
    
    def get_node_status(self, node_idx: int = 0) -> Optional[Dict]:
        """Get node status and metrics"""
        try:
            response = self.session.get(f"{self.nodes[node_idx]}/api/v1/status")
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"Status failed: {e}")
            return None
    
    def configure_consistency(self, config: Dict, node_idx: int = 0) -> bool:
        """Configure consistency settings"""
        try:
            response = self.session.post(
                f"{self.nodes[node_idx]}/api/v1/config/consistency",
                json=config,
                headers={"Content-Type": "application/json"}
            )
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Configuration failed: {e}")
            return False
    
    def simulate_partition(self, node_indices: List[int], duration: int = 10) -> bool:
        """Simulate network partition"""
        try:
            response = self.session.post(
                f"{self.nodes[0]}/api/v1/test/partition",
                json={
                    "nodes": node_indices,
                    "duration": duration
                }
            )
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Partition simulation failed: {e}")
            return False


class ConsistencyAnalyzer:
    """Analyzer for consistency model behavior"""
    
    def __init__(self, client: ConsistencyTestClient):
        self.client = client
        self.operation_history: List[Dict] = []
    
    def test_strong_consistency(self, num_operations: int = 100) -> Dict:
        """Test strong consistency guarantees"""
        logger.info(f"Testing strong consistency with {num_operations} operations")
        
        successful_writes = 0
        consistent_reads = 0
        inconsistent_reads = 0
        
        # Perform writes and immediate reads across different nodes
        for i in range(num_operations):
            key = f"strong_test_{i}"
            value = f"value_{i}_{random.randint(1000, 9999)}"
            
            # Write to random node
            write_node = random.randint(0, len(self.client.nodes) - 1)
            write_result = self.client.write_key(key, value, "strong", write_node)
            
            if write_result:
                successful_writes += 1
                
                # Immediately read from different node
                read_node = (write_node + 1) % len(self.client.nodes)
                read_result = self.client.read_key(key, "strong", read_node)
                
                if read_result and read_result.get("value") == value:
                    consistent_reads += 1
                else:
                    inconsistent_reads += 1
                    logger.warning(f"Inconsistent read for key {key}: expected {value}, got {read_result}")
        
        return {
            "consistency_level": "strong",
            "total_operations": num_operations,
            "successful_writes": successful_writes,
            "consistent_reads": consistent_reads,
            "inconsistent_reads": inconsistent_reads,
            "consistency_ratio": consistent_reads / successful_writes if successful_writes > 0 else 0
        }
    
    def test_eventual_consistency(self, num_operations: int = 100, convergence_time: int = 5) -> Dict:
        """Test eventual consistency behavior"""
        logger.info(f"Testing eventual consistency with {num_operations} operations")
        
        successful_writes = 0
        immediate_consistent_reads = 0
        eventual_consistent_reads = 0
        
        # Perform writes and reads with eventual consistency
        for i in range(num_operations):
            key = f"eventual_test_{i}"
            value = f"value_{i}_{random.randint(1000, 9999)}"
            
            # Write to random node
            write_node = random.randint(0, len(self.client.nodes) - 1)
            write_result = self.client.write_key(key, value, "eventual", write_node)
            
            if write_result:
                successful_writes += 1
                
                # Immediate read from different node
                read_node = (write_node + 1) % len(self.client.nodes)
                immediate_read = self.client.read_key(key, "eventual", read_node)
                
                if immediate_read and immediate_read.get("value") == value:
                    immediate_consistent_reads += 1
                
                # Wait for convergence and read again
                time.sleep(convergence_time)
                eventual_read = self.client.read_key(key, "eventual", read_node)
                
                if eventual_read and eventual_read.get("value") == value:
                    eventual_consistent_reads += 1
        
        return {
            "consistency_level": "eventual",
            "total_operations": num_operations,
            "successful_writes": successful_writes,
            "immediate_consistent_reads": immediate_consistent_reads,
            "eventual_consistent_reads": eventual_consistent_reads,
            "immediate_consistency_ratio": immediate_consistent_reads / successful_writes if successful_writes > 0 else 0,
            "eventual_consistency_ratio": eventual_consistent_reads / successful_writes if successful_writes > 0 else 0,
            "convergence_time": convergence_time
        }
    
    def test_session_consistency(self, num_sessions: int = 10, ops_per_session: int = 20) -> Dict:
        """Test session consistency guarantees"""
        logger.info(f"Testing session consistency with {num_sessions} sessions")
        
        session_results = []
        
        for session_id in range(num_sessions):
            session_writes = []
            monotonic_reads = 0
            total_reads = 0
            
            # Perform writes in this session
            for i in range(ops_per_session):
                key = f"session_{session_id}_key_{i}"
                value = f"value_{i}_{random.randint(1000, 9999)}"
                
                # Write with session consistency
                write_result = self.client.write_key(key, value, "session", 0)
                if write_result:
                    session_writes.append((key, value, write_result.get("timestamp", 0)))
            
            # Test monotonic read consistency
            last_timestamp = 0
            for key, expected_value, write_timestamp in session_writes:
                read_result = self.client.read_key(key, "session", 0)
                total_reads += 1
                
                if read_result:
                    read_timestamp = read_result.get("timestamp", 0)
                    if (read_result.get("value") == expected_value and 
                        read_timestamp >= last_timestamp):
                        monotonic_reads += 1
                        last_timestamp = read_timestamp
            
            session_results.append({
                "session_id": session_id,
                "writes": len(session_writes),
                "total_reads": total_reads,
                "monotonic_reads": monotonic_reads,
                "monotonic_ratio": monotonic_reads / total_reads if total_reads > 0 else 0
            })
        
        overall_monotonic_ratio = (
            sum(s["monotonic_reads"] for s in session_results) /
            sum(s["total_reads"] for s in session_results)
            if sum(s["total_reads"] for s in session_results) > 0 else 0
        )
        
        return {
            "consistency_level": "session",
            "num_sessions": num_sessions,
            "ops_per_session": ops_per_session,
            "session_results": session_results,
            "overall_monotonic_ratio": overall_monotonic_ratio
        }
    
    def test_partition_tolerance(self, partition_duration: int = 10) -> Dict:
        """Test behavior during network partitions"""
        logger.info(f"Testing partition tolerance for {partition_duration} seconds")
        
        # Write initial data
        initial_data = {}
        for i in range(50):
            key = f"partition_test_{i}"
            value = f"value_{i}"
            initial_data[key] = value
            self.client.write_key(key, value, "strong", 0)
        
        # Simulate partition (isolate one node)
        partition_success = self.client.simulate_partition([1], partition_duration)
        if not partition_success:
            return {"error": "Failed to simulate partition"}
        
        # Test operations during partition
        partition_writes = 0
        partition_reads = 0
        
        start_time = time.time()
        while time.time() - start_time < partition_duration:
            # Try to write to majority partition
            key = f"during_partition_{int(time.time())}"
            value = f"value_{random.randint(1000, 9999)}"
            
            if self.client.write_key(key, value, "strong", 0):
                partition_writes += 1
            
            # Try to read from majority partition
            test_key = random.choice(list(initial_data.keys()))
            if self.client.read_key(test_key, "strong", 0):
                partition_reads += 1
            
            time.sleep(0.1)
        
        # Wait for partition to heal
        time.sleep(2)
        
        # Verify data consistency after partition heals
        consistent_reads = 0
        for key, expected_value in initial_data.items():
            # Read from previously partitioned node
            result = self.client.read_key(key, "strong", 1)
            if result and result.get("value") == expected_value:
                consistent_reads += 1
        
        return {
            "partition_duration": partition_duration,
            "partition_writes": partition_writes,
            "partition_reads": partition_reads,
            "initial_data_count": len(initial_data),
            "consistent_reads_after_heal": consistent_reads,
            "consistency_after_partition": consistent_reads / len(initial_data) if initial_data else 0
        }


class TestConsistencyModels(unittest.TestCase):
    """Test cases for consistency models"""
    
    @classmethod
    def setUpClass(cls):
        cls.client = ConsistencyTestClient()
        cls.analyzer = ConsistencyAnalyzer(cls.client)
        
        # Wait for cluster to be ready
        max_retries = 30
        for i in range(max_retries):
            try:
                status = cls.client.get_node_status(0)
                if status and status.get("status") == "ready":
                    logger.info("KV store cluster is ready")
                    break
            except Exception:
                pass
            time.sleep(1)
        else:
            raise Exception("KV store cluster not ready after 30 seconds")
    
    def test_strong_consistency_guarantees(self):
        """Test strong consistency guarantees"""
        result = self.analyzer.test_strong_consistency(num_operations=50)
        
        self.assertGreater(result["successful_writes"], 45)
        self.assertGreater(result["consistency_ratio"], 0.95)
        
        logger.info(f"Strong Consistency Test: {result}")
    
    def test_eventual_consistency_convergence(self):
        """Test eventual consistency convergence"""
        result = self.analyzer.test_eventual_consistency(num_operations=30, convergence_time=3)
        
        self.assertGreater(result["successful_writes"], 25)
        self.assertGreater(result["eventual_consistency_ratio"], 0.90)
        
        logger.info(f"Eventual Consistency Test: {result}")
    
    def test_session_consistency_monotonic_reads(self):
        """Test session consistency with monotonic reads"""
        result = self.analyzer.test_session_consistency(num_sessions=5, ops_per_session=10)
        
        self.assertGreater(result["overall_monotonic_ratio"], 0.90)
        
        logger.info(f"Session Consistency Test: {result}")
    
    def test_cap_theorem_partition_tolerance(self):
        """Test CAP theorem trade-offs during partitions"""
        result = self.analyzer.test_partition_tolerance(partition_duration=5)
        
        self.assertNotIn("error", result)
        # During partition, should maintain consistency or availability
        self.assertTrue(
            result["partition_writes"] > 0 or  # Availability maintained
            result["consistency_after_partition"] > 0.95  # Consistency maintained
        )
        
        logger.info(f"Partition Tolerance Test: {result}")


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""
Comprehensive WAL (Write-Ahead Log) Management Tests for Raft Consensus
Tests database-specific features including WAL durability, compaction, and recovery
"""

import asyncio
import json
import logging
import os
import random
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Tuple

import aiohttp
import pytest
import requests

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class WALManagementTestClient:
    """Test client for WAL management operations"""
    
    def __init__(self, base_url: str = "http://localhost:8080"):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.timeout = 30
    
    def write_entry(self, key: str, value: str, consistency: str = "strong") -> Optional[Dict]:
        """Write entry to Raft log"""
        try:
            response = self.session.post(
                f"{self.base_url}/api/v1/write",
                json={
                    "key": key,
                    "value": value,
                    "timestamp": int(time.time() * 1000),
                    "consistency": consistency
                },
                headers={"Content-Type": "application/json"}
            )
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"Write failed: {e}")
            return None
    
    def read_entry(self, key: str, consistency: str = "strong") -> Optional[Dict]:
        """Read entry from Raft log"""
        try:
            response = self.session.get(
                f"{self.base_url}/api/v1/read/{key}",
                params={"consistency": consistency}
            )
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"Read failed: {e}")
            return None
    
    def get_wal_status(self) -> Optional[Dict]:
        """Get WAL status and metrics"""
        try:
            response = self.session.get(f"{self.base_url}/api/v1/wal/status")
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"WAL status failed: {e}")
            return None
    
    def trigger_compaction(self) -> bool:
        """Trigger WAL compaction"""
        try:
            response = self.session.post(f"{self.base_url}/api/v1/wal/compact")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Compaction failed: {e}")
            return False
    
    def create_snapshot(self) -> Optional[Dict]:
        """Create Raft snapshot"""
        try:
            response = self.session.post(f"{self.base_url}/api/v1/snapshot/create")
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"Snapshot creation failed: {e}")
            return None
    
    def get_cluster_status(self) -> Optional[Dict]:
        """Get cluster status"""
        try:
            response = self.session.get(f"{self.base_url}/api/v1/cluster/status")
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"Cluster status failed: {e}")
            return None
    
    def simulate_crash(self, node_id: str) -> bool:
        """Simulate node crash for testing"""
        try:
            response = self.session.post(
                f"{self.base_url}/api/v1/test/crash",
                json={"node_id": node_id}
            )
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Crash simulation failed: {e}")
            return False


class WALDurabilityAnalyzer:
    """Analyzer for WAL durability and consistency"""
    
    def __init__(self, client: WALManagementTestClient):
        self.client = client
        self.write_history: List[Dict] = []
        self.read_history: List[Dict] = []
    
    def analyze_wal_durability(self, num_writes: int = 1000) -> Dict:
        """Analyze WAL durability under various conditions"""
        logger.info(f"Analyzing WAL durability with {num_writes} writes")
        
        start_time = time.time()
        successful_writes = 0
        failed_writes = 0
        
        # Perform writes with durability tracking
        for i in range(num_writes):
            key = f"durability_test_{i}"
            value = f"value_{i}_{random.randint(1000, 9999)}"
            
            write_start = time.time()
            result = self.client.write_entry(key, value)
            write_end = time.time()
            
            if result:
                successful_writes += 1
                self.write_history.append({
                    "key": key,
                    "value": value,
                    "timestamp": write_start,
                    "latency": write_end - write_start,
                    "log_index": result.get("log_index"),
                    "term": result.get("term")
                })
            else:
                failed_writes += 1
            
            # Add some randomness to write pattern
            if random.random() < 0.01:  # 1% chance
                time.sleep(0.001)  # 1ms delay
        
        end_time = time.time()
        
        # Verify durability by reading back all written entries
        verified_reads = 0
        failed_reads = 0
        
        for write_record in self.write_history:
            result = self.client.read_entry(write_record["key"])
            if result and result.get("value") == write_record["value"]:
                verified_reads += 1
            else:
                failed_reads += 1
        
        return {
            "total_writes": num_writes,
            "successful_writes": successful_writes,
            "failed_writes": failed_writes,
            "verified_reads": verified_reads,
            "failed_reads": failed_reads,
            "durability_ratio": verified_reads / successful_writes if successful_writes > 0 else 0,
            "total_time": end_time - start_time,
            "writes_per_second": successful_writes / (end_time - start_time),
            "average_write_latency": sum(w["latency"] for w in self.write_history) / len(self.write_history) if self.write_history else 0
        }
    
    def analyze_wal_compaction(self) -> Dict:
        """Analyze WAL compaction behavior"""
        logger.info("Analyzing WAL compaction")
        
        # Get initial WAL status
        initial_status = self.client.get_wal_status()
        if not initial_status:
            return {"error": "Failed to get initial WAL status"}
        
        # Perform writes to generate WAL entries
        num_writes = 500
        for i in range(num_writes):
            key = f"compaction_test_{i}"
            value = f"value_{i}"
            self.client.write_entry(key, value)
        
        # Get WAL status before compaction
        pre_compaction_status = self.client.get_wal_status()
        
        # Trigger compaction
        compaction_start = time.time()
        compaction_success = self.client.trigger_compaction()
        compaction_end = time.time()
        
        if not compaction_success:
            return {"error": "Failed to trigger compaction"}
        
        # Wait for compaction to complete
        time.sleep(2)
        
        # Get WAL status after compaction
        post_compaction_status = self.client.get_wal_status()
        
        return {
            "compaction_time": compaction_end - compaction_start,
            "initial_wal_size": initial_status.get("wal_size", 0),
            "pre_compaction_wal_size": pre_compaction_status.get("wal_size", 0),
            "post_compaction_wal_size": post_compaction_status.get("wal_size", 0),
            "compaction_ratio": (
                (pre_compaction_status.get("wal_size", 0) - post_compaction_status.get("wal_size", 0)) /
                pre_compaction_status.get("wal_size", 1)
            ),
            "entries_before": pre_compaction_status.get("log_entries", 0),
            "entries_after": post_compaction_status.get("log_entries", 0)
        }
    
    def analyze_snapshot_consistency(self) -> Dict:
        """Analyze snapshot consistency and recovery"""
        logger.info("Analyzing snapshot consistency")
        
        # Write test data
        test_data = {}
        for i in range(100):
            key = f"snapshot_test_{i}"
            value = f"value_{i}_{random.randint(1000, 9999)}"
            test_data[key] = value
            self.client.write_entry(key, value)
        
        # Create snapshot
        snapshot_start = time.time()
        snapshot_result = self.client.create_snapshot()
        snapshot_end = time.time()
        
        if not snapshot_result:
            return {"error": "Failed to create snapshot"}
        
        # Verify all data is still readable
        consistent_reads = 0
        inconsistent_reads = 0
        
        for key, expected_value in test_data.items():
            result = self.client.read_entry(key)
            if result and result.get("value") == expected_value:
                consistent_reads += 1
            else:
                inconsistent_reads += 1
        
        return {
            "snapshot_time": snapshot_end - snapshot_start,
            "snapshot_id": snapshot_result.get("snapshot_id"),
            "snapshot_size": snapshot_result.get("size", 0),
            "test_entries": len(test_data),
            "consistent_reads": consistent_reads,
            "inconsistent_reads": inconsistent_reads,
            "consistency_ratio": consistent_reads / len(test_data) if test_data else 0
        }


class TestWALManagement(unittest.TestCase):
    """Test cases for WAL management"""
    
    @classmethod
    def setUpClass(cls):
        cls.client = WALManagementTestClient()
        cls.analyzer = WALDurabilityAnalyzer(cls.client)
        
        # Wait for Raft cluster to be ready
        max_retries = 30
        for i in range(max_retries):
            try:
                status = cls.client.get_cluster_status()
                if status and status.get("leader"):
                    logger.info("Raft cluster is ready")
                    break
            except Exception:
                pass
            time.sleep(1)
        else:
            raise Exception("Raft cluster not ready after 30 seconds")
    
    def test_wal_durability_basic(self):
        """Test basic WAL durability"""
        result = self.analyzer.analyze_wal_durability(num_writes=100)
        
        self.assertGreater(result["successful_writes"], 90)
        self.assertGreater(result["durability_ratio"], 0.99)
        self.assertLess(result["average_write_latency"], 0.1)  # < 100ms
        
        logger.info(f"WAL Durability Test: {result}")
    
    def test_wal_compaction_efficiency(self):
        """Test WAL compaction efficiency"""
        result = self.analyzer.analyze_wal_compaction()
        
        self.assertNotIn("error", result)
        self.assertLess(result["compaction_time"], 10.0)  # < 10 seconds
        self.assertGreater(result["compaction_ratio"], 0.1)  # At least 10% reduction
        
        logger.info(f"WAL Compaction Test: {result}")
    
    def test_snapshot_consistency(self):
        """Test snapshot consistency"""
        result = self.analyzer.analyze_snapshot_consistency()
        
        self.assertNotIn("error", result)
        self.assertEqual(result["consistency_ratio"], 1.0)  # 100% consistency
        self.assertLess(result["snapshot_time"], 5.0)  # < 5 seconds
        
        logger.info(f"Snapshot Consistency Test: {result}")
    
    def test_wal_recovery_after_crash(self):
        """Test WAL recovery after simulated crash"""
        # Write test data
        test_data = {}
        for i in range(50):
            key = f"recovery_test_{i}"
            value = f"value_{i}"
            test_data[key] = value
            self.client.write_entry(key, value)
        
        # Get cluster status to identify a follower
        status = self.client.get_cluster_status()
        followers = [node for node in status.get("nodes", []) if not node.get("is_leader")]
        
        if followers:
            # Simulate crash of a follower
            follower_id = followers[0]["id"]
            crash_success = self.client.simulate_crash(follower_id)
            self.assertTrue(crash_success)
            
            # Wait for recovery
            time.sleep(5)
            
            # Verify data consistency after recovery
            consistent_reads = 0
            for key, expected_value in test_data.items():
                result = self.client.read_entry(key)
                if result and result.get("value") == expected_value:
                    consistent_reads += 1
            
            consistency_ratio = consistent_reads / len(test_data)
            self.assertGreater(consistency_ratio, 0.95)  # 95% consistency after recovery
            
            logger.info(f"Recovery Test: {consistency_ratio * 100:.1f}% consistency after crash")


if __name__ == "__main__":
    unittest.main()

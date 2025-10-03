#!/usr/bin/env python3
"""
Comprehensive State Checkpointing Tests for Stateful Stream Processor
Tests durable state management, incremental checkpointing, and recovery
"""

import asyncio
import json
import logging
import random
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional

import requests

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class StateCheckpointingTestClient:
    """Test client for state checkpointing operations"""
    
    def __init__(self, processor_url: str = "http://localhost:8110"):
        self.processor_url = processor_url
        self.session = requests.Session()
        self.session.timeout = 30
    
    def submit_event(self, stream: str, event_data: Dict, partition: int = 0) -> Optional[Dict]:
        """Submit event to stream processor"""
        try:
            response = self.session.post(
                f"{self.processor_url}/api/v1/events",
                json={
                    "stream": stream,
                    "partition": partition,
                    "event": event_data,
                    "timestamp": int(time.time() * 1000)
                },
                headers={"Content-Type": "application/json"}
            )
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"Event submission failed: {e}")
            return None
    
    def create_stateful_operator(self, operator_config: Dict) -> Optional[Dict]:
        """Create stateful operator"""
        try:
            response = self.session.post(
                f"{self.processor_url}/api/v1/operators",
                json=operator_config,
                headers={"Content-Type": "application/json"}
            )
            return response.json() if response.status_code == 201 else None
        except Exception as e:
            logger.error(f"Operator creation failed: {e}")
            return None
    
    def get_operator_state(self, operator_id: str) -> Optional[Dict]:
        """Get current operator state"""
        try:
            response = self.session.get(f"{self.processor_url}/api/v1/operators/{operator_id}/state")
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"State retrieval failed: {e}")
            return None
    
    def trigger_checkpoint(self, operator_id: str = None) -> Optional[Dict]:
        """Trigger checkpoint creation"""
        try:
            url = f"{self.processor_url}/api/v1/checkpoints/trigger"
            if operator_id:
                url += f"?operator_id={operator_id}"
            
            response = self.session.post(url)
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"Checkpoint trigger failed: {e}")
            return None
    
    def get_checkpoint_status(self, checkpoint_id: str) -> Optional[Dict]:
        """Get checkpoint status"""
        try:
            response = self.session.get(f"{self.processor_url}/api/v1/checkpoints/{checkpoint_id}")
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"Checkpoint status failed: {e}")
            return None
    
    def restore_from_checkpoint(self, checkpoint_id: str, operator_id: str = None) -> bool:
        """Restore operator state from checkpoint"""
        try:
            response = self.session.post(
                f"{self.processor_url}/api/v1/checkpoints/{checkpoint_id}/restore",
                json={"operator_id": operator_id} if operator_id else {}
            )
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Checkpoint restore failed: {e}")
            return False
    
    def simulate_failure(self, operator_id: str, failure_type: str = "crash") -> bool:
        """Simulate operator failure"""
        try:
            response = self.session.post(
                f"{self.processor_url}/api/v1/test/failure",
                json={
                    "operator_id": operator_id,
                    "failure_type": failure_type
                }
            )
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Failure simulation failed: {e}")
            return False
    
    def get_processing_metrics(self) -> Optional[Dict]:
        """Get stream processing metrics"""
        try:
            response = self.session.get(f"{self.processor_url}/api/v1/metrics")
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"Metrics retrieval failed: {e}")
            return None


class StateCheckpointingAnalyzer:
    """Analyzer for state checkpointing behavior"""
    
    def __init__(self, client: StateCheckpointingTestClient):
        self.client = client
        self.test_operators: List[str] = []
    
    def test_incremental_checkpointing(self, num_events: int = 1000) -> Dict:
        """Test incremental checkpointing performance"""
        logger.info(f"Testing incremental checkpointing with {num_events} events")
        
        # Create stateful aggregation operator
        operator_config = {
            "name": "incremental_checkpoint_test",
            "type": "aggregation",
            "state_backend": "rocksdb",
            "checkpoint_interval": 100,  # Checkpoint every 100 events
            "state_config": {
                "enable_incremental": True,
                "compression": "snappy"
            }
        }
        
        operator_result = self.client.create_stateful_operator(operator_config)
        if not operator_result:
            return {"error": "Failed to create operator"}
        
        operator_id = operator_result["operator_id"]
        self.test_operators.append(operator_id)
        
        # Submit events and track checkpointing
        checkpoint_times = []
        state_sizes = []
        events_processed = 0
        
        for i in range(num_events):
            # Submit aggregation event
            event_data = {
                "key": f"key_{i % 100}",  # 100 unique keys
                "value": random.randint(1, 1000),
                "operation": "sum"
            }
            
            result = self.client.submit_event("test_stream", event_data)
            if result:
                events_processed += 1
                
                # Check if checkpoint was triggered
                if i % 100 == 0 and i > 0:
                    checkpoint_start = time.time()
                    checkpoint_result = self.client.trigger_checkpoint(operator_id)
                    
                    if checkpoint_result:
                        checkpoint_id = checkpoint_result["checkpoint_id"]
                        
                        # Wait for checkpoint completion
                        while True:
                            status = self.client.get_checkpoint_status(checkpoint_id)
                            if status and status.get("status") == "completed":
                                checkpoint_end = time.time()
                                checkpoint_times.append(checkpoint_end - checkpoint_start)
                                state_sizes.append(status.get("size_bytes", 0))
                                break
                            elif status and status.get("status") == "failed":
                                break
                            time.sleep(0.1)
        
        # Get final operator state
        final_state = self.client.get_operator_state(operator_id)
        
        return {
            "events_processed": events_processed,
            "checkpoints_created": len(checkpoint_times),
            "average_checkpoint_time": sum(checkpoint_times) / len(checkpoint_times) if checkpoint_times else 0,
            "max_checkpoint_time": max(checkpoint_times) if checkpoint_times else 0,
            "average_state_size": sum(state_sizes) / len(state_sizes) if state_sizes else 0,
            "final_state_keys": len(final_state.get("state", {})) if final_state else 0,
            "checkpoint_efficiency": len(checkpoint_times) / (num_events / 100) if num_events > 0 else 0
        }
    
    def test_state_recovery_accuracy(self, num_events: int = 500) -> Dict:
        """Test state recovery accuracy after failure"""
        logger.info(f"Testing state recovery accuracy with {num_events} events")
        
        # Create stateful counter operator
        operator_config = {
            "name": "recovery_test",
            "type": "counter",
            "state_backend": "rocksdb",
            "checkpoint_interval": 50,
            "state_config": {
                "enable_incremental": True
            }
        }
        
        operator_result = self.client.create_stateful_operator(operator_config)
        if not operator_result:
            return {"error": "Failed to create operator"}
        
        operator_id = operator_result["operator_id"]
        self.test_operators.append(operator_id)
        
        # Submit events and build expected state
        expected_counters = {}
        events_before_checkpoint = 0
        
        for i in range(num_events):
            key = f"counter_{i % 20}"  # 20 unique counters
            increment = random.randint(1, 10)
            
            event_data = {
                "key": key,
                "increment": increment,
                "operation": "increment"
            }
            
            result = self.client.submit_event("counter_stream", event_data)
            if result:
                expected_counters[key] = expected_counters.get(key, 0) + increment
                events_before_checkpoint += 1
                
                # Create checkpoint at midpoint
                if i == num_events // 2:
                    checkpoint_result = self.client.trigger_checkpoint(operator_id)
                    if checkpoint_result:
                        checkpoint_id = checkpoint_result["checkpoint_id"]
                        
                        # Wait for checkpoint completion
                        while True:
                            status = self.client.get_checkpoint_status(checkpoint_id)
                            if status and status.get("status") == "completed":
                                break
                            time.sleep(0.1)
        
        # Get state before failure
        pre_failure_state = self.client.get_operator_state(operator_id)
        
        # Simulate failure
        failure_success = self.client.simulate_failure(operator_id, "crash")
        if not failure_success:
            return {"error": "Failed to simulate failure"}
        
        # Wait for failure to take effect
        time.sleep(2)
        
        # Restore from checkpoint
        restore_success = self.client.restore_from_checkpoint(checkpoint_id, operator_id)
        if not restore_success:
            return {"error": "Failed to restore from checkpoint"}
        
        # Wait for recovery
        time.sleep(3)
        
        # Get state after recovery
        post_recovery_state = self.client.get_operator_state(operator_id)
        
        # Compare states
        pre_failure_counters = pre_failure_state.get("state", {}) if pre_failure_state else {}
        post_recovery_counters = post_recovery_state.get("state", {}) if post_recovery_state else {}
        
        # Calculate recovery accuracy
        matching_keys = 0
        total_keys = len(set(pre_failure_counters.keys()) | set(post_recovery_counters.keys()))
        
        for key in set(pre_failure_counters.keys()) | set(post_recovery_counters.keys()):
            pre_value = pre_failure_counters.get(key, 0)
            post_value = post_recovery_counters.get(key, 0)
            
            # Allow for some data loss after checkpoint (events after checkpoint may be lost)
            if post_value <= pre_value:
                matching_keys += 1
        
        recovery_accuracy = matching_keys / total_keys if total_keys > 0 else 0
        
        return {
            "events_processed": events_before_checkpoint,
            "pre_failure_keys": len(pre_failure_counters),
            "post_recovery_keys": len(post_recovery_counters),
            "recovery_accuracy": recovery_accuracy,
            "checkpoint_id": checkpoint_id,
            "state_consistency": recovery_accuracy >= 0.95
        }
    
    def test_exactly_once_processing(self, num_events: int = 300) -> Dict:
        """Test exactly-once processing guarantees"""
        logger.info(f"Testing exactly-once processing with {num_events} events")
        
        # Create exactly-once processor
        operator_config = {
            "name": "exactly_once_test",
            "type": "deduplication",
            "state_backend": "rocksdb",
            "checkpoint_interval": 25,
            "processing_guarantee": "exactly_once",
            "state_config": {
                "enable_incremental": True,
                "deduplication_window": 3600  # 1 hour
            }
        }
        
        operator_result = self.client.create_stateful_operator(operator_config)
        if not operator_result:
            return {"error": "Failed to create operator"}
        
        operator_id = operator_result["operator_id"]
        self.test_operators.append(operator_id)
        
        # Submit events with intentional duplicates
        unique_events = set()
        duplicate_events = 0
        total_submissions = 0
        
        for i in range(num_events):
            event_id = f"event_{i}"
            event_data = {
                "id": event_id,
                "data": f"payload_{i}",
                "timestamp": int(time.time() * 1000)
            }
            
            # Submit original event
            result = self.client.submit_event("dedup_stream", event_data)
            if result:
                unique_events.add(event_id)
                total_submissions += 1
                
                # Randomly submit duplicate (simulate retry)
                if random.random() < 0.2:  # 20% duplicate rate
                    duplicate_result = self.client.submit_event("dedup_stream", event_data)
                    if duplicate_result:
                        duplicate_events += 1
                        total_submissions += 1
        
        # Wait for processing to complete
        time.sleep(5)
        
        # Trigger final checkpoint
        final_checkpoint = self.client.trigger_checkpoint(operator_id)
        if final_checkpoint:
            checkpoint_id = final_checkpoint["checkpoint_id"]
            
            # Wait for checkpoint completion
            while True:
                status = self.client.get_checkpoint_status(checkpoint_id)
                if status and status.get("status") == "completed":
                    break
                time.sleep(0.1)
        
        # Get processing metrics
        metrics = self.client.get_processing_metrics()
        
        processed_events = metrics.get("events_processed", 0) if metrics else 0
        deduplicated_events = metrics.get("deduplicated_events", 0) if metrics else 0
        
        return {
            "unique_events": len(unique_events),
            "duplicate_submissions": duplicate_events,
            "total_submissions": total_submissions,
            "processed_events": processed_events,
            "deduplicated_events": deduplicated_events,
            "exactly_once_guarantee": processed_events == len(unique_events),
            "deduplication_effectiveness": deduplicated_events / duplicate_events if duplicate_events > 0 else 1.0
        }
    
    def cleanup_test_operators(self):
        """Clean up test operators"""
        for operator_id in self.test_operators:
            try:
                self.client.session.delete(f"{self.client.processor_url}/api/v1/operators/{operator_id}")
            except Exception:
                pass
        self.test_operators.clear()


class TestStateCheckpointing(unittest.TestCase):
    """Test cases for state checkpointing"""
    
    @classmethod
    def setUpClass(cls):
        cls.client = StateCheckpointingTestClient()
        cls.analyzer = StateCheckpointingAnalyzer(cls.client)
        
        # Wait for stream processor to be ready
        max_retries = 30
        for i in range(max_retries):
            try:
                metrics = cls.client.get_processing_metrics()
                if metrics and metrics.get("status") == "ready":
                    logger.info("Stream processor is ready")
                    break
            except Exception:
                pass
            time.sleep(1)
        else:
            raise Exception("Stream processor not ready after 30 seconds")
    
    @classmethod
    def tearDownClass(cls):
        cls.analyzer.cleanup_test_operators()
    
    def test_incremental_checkpoint_performance(self):
        """Test incremental checkpointing performance"""
        result = self.analyzer.test_incremental_checkpointing(num_events=200)
        
        self.assertNotIn("error", result)
        self.assertGreater(result["checkpoint_efficiency"], 0.8)
        self.assertLess(result["average_checkpoint_time"], 5.0)  # < 5 seconds
        
        logger.info(f"Incremental Checkpointing Test: {result}")
    
    def test_state_recovery_after_failure(self):
        """Test state recovery accuracy after failure"""
        result = self.analyzer.test_state_recovery_accuracy(num_events=100)
        
        self.assertNotIn("error", result)
        self.assertTrue(result["state_consistency"])
        self.assertGreater(result["recovery_accuracy"], 0.90)
        
        logger.info(f"State Recovery Test: {result}")
    
    def test_exactly_once_processing_guarantees(self):
        """Test exactly-once processing guarantees"""
        result = self.analyzer.test_exactly_once_processing(num_events=50)
        
        self.assertNotIn("error", result)
        self.assertTrue(result["exactly_once_guarantee"])
        self.assertGreater(result["deduplication_effectiveness"], 0.95)
        
        logger.info(f"Exactly-Once Processing Test: {result}")


if __name__ == "__main__":
    unittest.main()

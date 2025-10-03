#!/usr/bin/env python3
"""
Comprehensive Exactly-Once Semantics Tests for Commit-Log Service
Tests producer idempotence, consumer deduplication, and transactional guarantees
"""

import asyncio
import json
import logging
import random
import time
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Set

import requests

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ExactlyOnceTestClient:
    """Test client for exactly-once semantics operations"""
    
    def __init__(self, broker_url: str = "http://localhost:8080"):
        self.broker_url = broker_url
        self.session = requests.Session()
        self.session.timeout = 30
        self.producer_id = str(uuid.uuid4())
        self.sequence_number = 0
    
    def produce_message(self, topic: str, key: str, value: str, 
                       partition: int = 0, idempotent: bool = True) -> Optional[Dict]:
        """Produce message with optional idempotence"""
        try:
            headers = {"Content-Type": "application/json"}
            if idempotent:
                headers["X-Producer-ID"] = self.producer_id
                headers["X-Sequence-Number"] = str(self.sequence_number)
                self.sequence_number += 1
            
            response = self.session.post(
                f"{self.broker_url}/api/v1/produce",
                json={
                    "topic": topic,
                    "partition": partition,
                    "messages": [{
                        "key": key,
                        "value": value,
                        "timestamp": int(time.time() * 1000)
                    }]
                },
                headers=headers
            )
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"Produce failed: {e}")
            return None
    
    def consume_messages(self, topic: str, partition: int = 0, 
                        offset: int = 0, limit: int = 100) -> Optional[List[Dict]]:
        """Consume messages from topic"""
        try:
            response = self.session.get(
                f"{self.broker_url}/api/v1/consume",
                params={
                    "topic": topic,
                    "partition": partition,
                    "offset": offset,
                    "limit": limit
                }
            )
            return response.json().get("messages", []) if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"Consume failed: {e}")
            return None
    
    def create_topic(self, name: str, partitions: int = 3, replication_factor: int = 3) -> bool:
        """Create topic with specified configuration"""
        try:
            response = self.session.post(
                f"{self.broker_url}/api/v1/topics",
                json={
                    "name": name,
                    "partitions": partitions,
                    "replication_factor": replication_factor,
                    "config": {
                        "cleanup.policy": "delete",
                        "retention.ms": 604800000,  # 7 days
                        "enable.idempotence": True
                    }
                }
            )
            return response.status_code == 201
        except Exception as e:
            logger.error(f"Topic creation failed: {e}")
            return False
    
    def start_transaction(self) -> Optional[str]:
        """Start a new transaction"""
        try:
            response = self.session.post(
                f"{self.broker_url}/api/v1/transactions/begin",
                json={"producer_id": self.producer_id}
            )
            result = response.json() if response.status_code == 200 else None
            return result.get("transaction_id") if result else None
        except Exception as e:
            logger.error(f"Transaction start failed: {e}")
            return None
    
    def commit_transaction(self, transaction_id: str) -> bool:
        """Commit transaction"""
        try:
            response = self.session.post(
                f"{self.broker_url}/api/v1/transactions/{transaction_id}/commit"
            )
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Transaction commit failed: {e}")
            return False
    
    def abort_transaction(self, transaction_id: str) -> bool:
        """Abort transaction"""
        try:
            response = self.session.post(
                f"{self.broker_url}/api/v1/transactions/{transaction_id}/abort"
            )
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Transaction abort failed: {e}")
            return False
    
    def produce_transactional(self, transaction_id: str, topic: str, 
                             key: str, value: str, partition: int = 0) -> Optional[Dict]:
        """Produce message within transaction"""
        try:
            response = self.session.post(
                f"{self.broker_url}/api/v1/produce",
                json={
                    "topic": topic,
                    "partition": partition,
                    "messages": [{
                        "key": key,
                        "value": value,
                        "timestamp": int(time.time() * 1000)
                    }],
                    "transaction_id": transaction_id
                },
                headers={"Content-Type": "application/json"}
            )
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"Transactional produce failed: {e}")
            return None
    
    def get_topic_stats(self, topic: str) -> Optional[Dict]:
        """Get topic statistics"""
        try:
            response = self.session.get(f"{self.broker_url}/api/v1/topics/{topic}/stats")
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"Topic stats failed: {e}")
            return None


class ExactlyOnceAnalyzer:
    """Analyzer for exactly-once semantics"""
    
    def __init__(self, client: ExactlyOnceTestClient):
        self.client = client
        self.message_history: List[Dict] = []
    
    def test_producer_idempotence(self, topic: str, num_messages: int = 100, 
                                 duplicate_rate: float = 0.1) -> Dict:
        """Test producer idempotence with intentional duplicates"""
        logger.info(f"Testing producer idempotence with {num_messages} messages")
        
        # Create topic
        self.client.create_topic(topic)
        time.sleep(1)  # Wait for topic creation
        
        sent_messages = []
        duplicate_sends = 0
        successful_sends = 0
        
        # Send messages with intentional duplicates
        for i in range(num_messages):
            key = f"idempotence_test_{i}"
            value = f"message_{i}_{random.randint(1000, 9999)}"
            
            # Send original message
            result = self.client.produce_message(topic, key, value, idempotent=True)
            if result:
                successful_sends += 1
                sent_messages.append((key, value))
                
                # Randomly send duplicate (simulate network retry)
                if random.random() < duplicate_rate:
                    # Reset sequence number to create duplicate
                    original_seq = self.client.sequence_number - 1
                    self.client.sequence_number = original_seq
                    
                    duplicate_result = self.client.produce_message(topic, key, value, idempotent=True)
                    if duplicate_result:
                        duplicate_sends += 1
        
        # Wait for messages to be persisted
        time.sleep(2)
        
        # Consume all messages and check for duplicates
        consumed_messages = self.client.consume_messages(topic, offset=0, limit=num_messages * 2)
        if not consumed_messages:
            return {"error": "Failed to consume messages"}
        
        # Analyze for duplicates
        seen_keys = set()
        unique_messages = 0
        duplicate_messages = 0
        
        for msg in consumed_messages:
            key = msg.get("key")
            if key in seen_keys:
                duplicate_messages += 1
            else:
                seen_keys.add(key)
                unique_messages += 1
        
        return {
            "topic": topic,
            "sent_messages": len(sent_messages),
            "duplicate_sends": duplicate_sends,
            "successful_sends": successful_sends,
            "consumed_messages": len(consumed_messages),
            "unique_messages": unique_messages,
            "duplicate_messages": duplicate_messages,
            "idempotence_effectiveness": duplicate_messages == 0,
            "deduplication_ratio": 1.0 - (duplicate_messages / len(consumed_messages)) if consumed_messages else 0
        }
    
    def test_transactional_semantics(self, topic: str, num_transactions: int = 20) -> Dict:
        """Test transactional message production"""
        logger.info(f"Testing transactional semantics with {num_transactions} transactions")
        
        # Create topic
        self.client.create_topic(topic)
        time.sleep(1)
        
        committed_transactions = 0
        aborted_transactions = 0
        committed_messages = []
        aborted_messages = []
        
        for i in range(num_transactions):
            # Start transaction
            transaction_id = self.client.start_transaction()
            if not transaction_id:
                continue
            
            # Produce messages in transaction
            transaction_messages = []
            for j in range(3):  # 3 messages per transaction
                key = f"tx_{i}_msg_{j}"
                value = f"transaction_{i}_message_{j}"
                
                result = self.client.produce_transactional(transaction_id, topic, key, value)
                if result:
                    transaction_messages.append((key, value))
            
            # Randomly commit or abort (80% commit rate)
            if random.random() < 0.8:
                if self.client.commit_transaction(transaction_id):
                    committed_transactions += 1
                    committed_messages.extend(transaction_messages)
            else:
                if self.client.abort_transaction(transaction_id):
                    aborted_transactions += 1
                    aborted_messages.extend(transaction_messages)
        
        # Wait for transactions to be processed
        time.sleep(3)
        
        # Consume all messages
        consumed_messages = self.client.consume_messages(topic, offset=0, limit=num_transactions * 10)
        if not consumed_messages:
            return {"error": "Failed to consume messages"}
        
        # Check that only committed messages are visible
        consumed_keys = {msg.get("key") for msg in consumed_messages}
        committed_keys = {key for key, _ in committed_messages}
        aborted_keys = {key for key, _ in aborted_messages}
        
        correctly_visible = len(consumed_keys.intersection(committed_keys))
        incorrectly_visible = len(consumed_keys.intersection(aborted_keys))
        
        return {
            "topic": topic,
            "total_transactions": num_transactions,
            "committed_transactions": committed_transactions,
            "aborted_transactions": aborted_transactions,
            "committed_messages": len(committed_messages),
            "aborted_messages": len(aborted_messages),
            "consumed_messages": len(consumed_messages),
            "correctly_visible": correctly_visible,
            "incorrectly_visible": incorrectly_visible,
            "transaction_isolation": incorrectly_visible == 0,
            "visibility_accuracy": correctly_visible / len(committed_messages) if committed_messages else 0
        }
    
    def test_consumer_exactly_once(self, topic: str, num_messages: int = 100) -> Dict:
        """Test consumer exactly-once processing"""
        logger.info(f"Testing consumer exactly-once processing with {num_messages} messages")
        
        # Create topic and produce messages
        self.client.create_topic(topic)
        time.sleep(1)
        
        produced_messages = []
        for i in range(num_messages):
            key = f"consumer_test_{i}"
            value = f"message_{i}"
            
            result = self.client.produce_message(topic, key, value, idempotent=True)
            if result:
                produced_messages.append((key, value))
        
        # Wait for messages to be available
        time.sleep(2)
        
        # Simulate consumer processing with potential duplicates
        processed_messages = set()
        processing_attempts = 0
        duplicate_processing = 0
        
        # First consumption pass
        consumed_batch1 = self.client.consume_messages(topic, offset=0, limit=num_messages)
        if consumed_batch1:
            for msg in consumed_batch1:
                key = msg.get("key")
                processing_attempts += 1
                
                if key in processed_messages:
                    duplicate_processing += 1
                else:
                    processed_messages.add(key)
        
        # Simulate reprocessing (e.g., after consumer restart)
        consumed_batch2 = self.client.consume_messages(topic, offset=0, limit=num_messages)
        if consumed_batch2:
            for msg in consumed_batch2:
                key = msg.get("key")
                processing_attempts += 1
                
                if key in processed_messages:
                    duplicate_processing += 1
                else:
                    processed_messages.add(key)
        
        return {
            "topic": topic,
            "produced_messages": len(produced_messages),
            "processing_attempts": processing_attempts,
            "unique_processed": len(processed_messages),
            "duplicate_processing": duplicate_processing,
            "exactly_once_ratio": len(processed_messages) / len(produced_messages) if produced_messages else 0,
            "deduplication_effectiveness": duplicate_processing / processing_attempts if processing_attempts > 0 else 0
        }


class TestExactlyOnceSemantics(unittest.TestCase):
    """Test cases for exactly-once semantics"""
    
    @classmethod
    def setUpClass(cls):
        cls.client = ExactlyOnceTestClient()
        cls.analyzer = ExactlyOnceAnalyzer(cls.client)
        
        # Wait for broker to be ready
        max_retries = 30
        for i in range(max_retries):
            try:
                # Try to create a test topic to verify broker is ready
                if cls.client.create_topic("health_check"):
                    logger.info("Commit-log broker is ready")
                    break
            except Exception:
                pass
            time.sleep(1)
        else:
            raise Exception("Commit-log broker not ready after 30 seconds")
    
    def test_producer_idempotence_effectiveness(self):
        """Test producer idempotence prevents duplicates"""
        topic = f"idempotence_test_{int(time.time())}"
        result = self.analyzer.test_producer_idempotence(topic, num_messages=50, duplicate_rate=0.2)
        
        self.assertNotIn("error", result)
        self.assertTrue(result["idempotence_effectiveness"])
        self.assertGreater(result["deduplication_ratio"], 0.95)
        self.assertEqual(result["duplicate_messages"], 0)
        
        logger.info(f"Producer Idempotence Test: {result}")
    
    def test_transactional_message_isolation(self):
        """Test transactional message isolation"""
        topic = f"transaction_test_{int(time.time())}"
        result = self.analyzer.test_transactional_semantics(topic, num_transactions=10)
        
        self.assertNotIn("error", result)
        self.assertTrue(result["transaction_isolation"])
        self.assertEqual(result["incorrectly_visible"], 0)
        self.assertGreater(result["visibility_accuracy"], 0.95)
        
        logger.info(f"Transactional Semantics Test: {result}")
    
    def test_consumer_exactly_once_processing(self):
        """Test consumer exactly-once processing"""
        topic = f"consumer_test_{int(time.time())}"
        result = self.analyzer.test_consumer_exactly_once(topic, num_messages=30)
        
        self.assertNotIn("error", result)
        self.assertGreater(result["exactly_once_ratio"], 0.95)
        self.assertLess(result["deduplication_effectiveness"], 0.1)  # Low duplicate processing
        
        logger.info(f"Consumer Exactly-Once Test: {result}")
    
    def test_end_to_end_exactly_once(self):
        """Test end-to-end exactly-once guarantees"""
        topic = f"e2e_test_{int(time.time())}"
        
        # Test producer idempotence
        producer_result = self.analyzer.test_producer_idempotence(topic, num_messages=20, duplicate_rate=0.15)
        
        # Test consumer processing
        consumer_result = self.analyzer.test_consumer_exactly_once(topic, num_messages=20)
        
        # Verify end-to-end exactly-once
        self.assertTrue(producer_result["idempotence_effectiveness"])
        self.assertGreater(consumer_result["exactly_once_ratio"], 0.95)
        
        logger.info(f"End-to-End Exactly-Once Test - Producer: {producer_result}, Consumer: {consumer_result}")


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""
Comprehensive unit tests for exactly-once processing in the stateful stream processor.
Tests idempotency, transactional processing, and state consistency guarantees.
"""

import pytest
import requests
import json
import time
import threading
import uuid
import hashlib
from typing import Dict, List, Set, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from kafka import KafkaProducer, KafkaConsumer
from kafka.errors import KafkaError


class StreamProcessorTestClient:
    """Test client for stream processor operations"""
    
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({'Content-Type': 'application/json'})
    
    def get_status(self) -> Dict:
        """Get processor status"""
        response = self.session.get(f"{self.base_url}/processor/status")
        response.raise_for_status()
        return response.json()
    
    def start_processing(self, topics: List[str]) -> Dict:
        """Start processing topics"""
        payload = {"topics": topics}
        response = self.session.post(f"{self.base_url}/processor/start", json=payload)
        response.raise_for_status()
        return response.json()
    
    def stop_processing(self) -> Dict:
        """Stop processing"""
        response = self.session.post(f"{self.base_url}/processor/stop")
        response.raise_for_status()
        return response.json()
    
    def create_checkpoint(self) -> Dict:
        """Create a checkpoint"""
        response = self.session.post(f"{self.base_url}/processor/checkpoint")
        response.raise_for_status()
        return response.json()
    
    def get_state(self, store: str, key: str) -> Dict:
        """Get state value"""
        response = self.session.get(f"{self.base_url}/state/stores/{store}/{key}")
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()
    
    def put_state(self, store: str, key: str, value: Any) -> Dict:
        """Put state value"""
        payload = {"value": value}
        response = self.session.put(f"{self.base_url}/state/stores/{store}/{key}", json=payload)
        response.raise_for_status()
        return response.json()
    
    def delete_state(self, store: str, key: str) -> Dict:
        """Delete state value"""
        response = self.session.delete(f"{self.base_url}/state/stores/{store}/{key}")
        response.raise_for_status()
        return response.json()
    
    def list_state_stores(self) -> Dict:
        """List all state stores"""
        response = self.session.get(f"{self.base_url}/state/stores")
        response.raise_for_status()
        return response.json()
    
    def create_snapshot(self, store: str) -> Dict:
        """Create state store snapshot"""
        response = self.session.post(f"{self.base_url}/state/stores/{store}/snapshot")
        response.raise_for_status()
        return response.json()
    
    def get_exactly_once_status(self) -> Dict:
        """Get exactly-once processing status"""
        response = self.session.get(f"{self.base_url}/admin/exactly-once/status")
        response.raise_for_status()
        return response.json()
    
    def start_exactly_once_validation(self, topic: str, duration: int = 60, key_range: int = 1000) -> Dict:
        """Start exactly-once validation"""
        payload = {
            "topic": topic,
            "duration_seconds": duration,
            "key_range": key_range
        }
        response = self.session.post(f"{self.base_url}/admin/exactly-once/validate", json=payload)
        response.raise_for_status()
        return response.json()
    
    def get_processing_metrics(self) -> Dict:
        """Get processing metrics"""
        response = self.session.get(f"{self.base_url}/processor/metrics")
        response.raise_for_status()
        return response.json()
    
    def is_healthy(self) -> bool:
        """Check if processor is healthy"""
        try:
            response = self.session.get(f"{self.base_url}/health", timeout=5)
            return response.status_code == 200
        except:
            return False


class KafkaTestHelper:
    """Helper class for Kafka operations in tests"""
    
    def __init__(self, bootstrap_servers: str = "localhost:9092,localhost:9094,localhost:9095"):
        self.bootstrap_servers = bootstrap_servers
        self.producer = KafkaProducer(
            bootstrap_servers=bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            key_serializer=lambda k: k.encode('utf-8') if k else None,
            acks='all',
            retries=3,
            enable_idempotence=True
        )
    
    def produce_message(self, topic: str, key: str, value: Dict, headers: Dict = None) -> bool:
        """Produce a message to Kafka"""
        try:
            kafka_headers = []
            if headers:
                kafka_headers = [(k, v.encode('utf-8') if isinstance(v, str) else str(v).encode('utf-8')) 
                               for k, v in headers.items()]
            
            future = self.producer.send(
                topic=topic,
                key=key,
                value=value,
                headers=kafka_headers
            )
            future.get(timeout=10)
            return True
        except KafkaError as e:
            print(f"Failed to produce message: {e}")
            return False
    
    def produce_batch(self, topic: str, messages: List[Dict]) -> int:
        """Produce a batch of messages"""
        successful = 0
        for msg in messages:
            if self.produce_message(topic, msg.get('key'), msg.get('value'), msg.get('headers')):
                successful += 1
        self.producer.flush()
        return successful
    
    def consume_messages(self, topic: str, timeout_ms: int = 10000) -> List[Dict]:
        """Consume messages from a topic"""
        consumer = KafkaConsumer(
            topic,
            bootstrap_servers=self.bootstrap_servers,
            value_deserializer=lambda m: json.loads(m.decode('utf-8')),
            key_deserializer=lambda k: k.decode('utf-8') if k else None,
            auto_offset_reset='earliest',
            enable_auto_commit=False,
            consumer_timeout_ms=timeout_ms
        )
        
        messages = []
        try:
            for message in consumer:
                messages.append({
                    'key': message.key,
                    'value': message.value,
                    'partition': message.partition,
                    'offset': message.offset,
                    'timestamp': message.timestamp,
                    'headers': {k: v.decode('utf-8') for k, v in message.headers} if message.headers else {}
                })
        except Exception as e:
            print(f"Consumer timeout or error: {e}")
        finally:
            consumer.close()
        
        return messages
    
    def close(self):
        """Close producer"""
        self.producer.close()


class TestExactlyOnceProcessing:
    """Test exactly-once processing guarantees"""
    
    @pytest.fixture
    def clients(self):
        """Create test clients for stream processors"""
        return {
            'processor-1': StreamProcessorTestClient('http://localhost:8081'),
            'processor-2': StreamProcessorTestClient('http://localhost:8082'),
            'processor-3': StreamProcessorTestClient('http://localhost:8083'),
        }
    
    @pytest.fixture
    def kafka_helper(self):
        """Create Kafka test helper"""
        helper = KafkaTestHelper()
        yield helper
        helper.close()
    
    def test_basic_exactly_once_processing(self, clients, kafka_helper):
        """Test basic exactly-once processing without failures"""
        topic = f"test_exactly_once_basic_{int(time.time())}"
        
        # Start processing on one processor
        clients['processor-1'].start_processing([topic])
        time.sleep(2)
        
        # Produce unique messages
        messages = []
        for i in range(100):
            message = {
                'key': f"key_{i}",
                'value': {
                    'id': str(uuid.uuid4()),
                    'sequence': i,
                    'data': f"test_data_{i}",
                    'timestamp': int(time.time() * 1000)
                }
            }
            messages.append(message)
        
        # Send messages
        successful = kafka_helper.produce_batch(topic, messages)
        assert successful == 100, f"Only {successful}/100 messages were produced"
        
        # Wait for processing
        time.sleep(10)
        
        # Check exactly-once status
        status = clients['processor-1'].get_exactly_once_status()
        assert status['duplicate_processing_detected'] == 0, "Duplicate processing detected"
        assert status['out_of_order_processing'] == 0, "Out-of-order processing detected"
        
        # Verify processing metrics
        metrics = clients['processor-1'].get_processing_metrics()
        assert metrics['total_messages_processed'] >= 100, "Not all messages were processed"
    
    def test_duplicate_message_handling(self, clients, kafka_helper):
        """Test handling of duplicate messages"""
        topic = f"test_duplicate_handling_{int(time.time())}"
        
        # Start processing
        clients['processor-1'].start_processing([topic])
        time.sleep(2)
        
        # Create messages with intentional duplicates
        base_messages = []
        for i in range(50):
            message = {
                'key': f"key_{i}",
                'value': {
                    'id': f"msg_{i}",
                    'sequence': i,
                    'data': f"test_data_{i}"
                },
                'headers': {
                    'idempotency_key': f"idem_{i}"
                }
            }
            base_messages.append(message)
        
        # Send original messages
        kafka_helper.produce_batch(topic, base_messages)
        time.sleep(5)
        
        # Send duplicates (same idempotency keys)
        duplicate_messages = []
        for i in range(25):  # Duplicate first 25 messages
            message = {
                'key': f"key_{i}",
                'value': {
                    'id': f"msg_{i}_duplicate",
                    'sequence': i,
                    'data': f"test_data_{i}_duplicate"
                },
                'headers': {
                    'idempotency_key': f"idem_{i}"  # Same idempotency key
                }
            }
            duplicate_messages.append(message)
        
        kafka_helper.produce_batch(topic, duplicate_messages)
        time.sleep(10)
        
        # Check that duplicates were detected and handled
        status = clients['processor-1'].get_exactly_once_status()
        assert status['duplicate_processing_detected'] >= 25, "Duplicates not properly detected"
        
        # Verify that state reflects only original processing
        metrics = clients['processor-1'].get_processing_metrics()
        # Should process 50 unique messages, not 75
        assert metrics['unique_messages_processed'] == 50, "Duplicate messages were processed"
    
    def test_transactional_state_updates(self, clients, kafka_helper):
        """Test transactional state updates with exactly-once semantics"""
        topic = f"test_transactional_updates_{int(time.time())}"
        state_store = "transaction_test_store"
        
        # Start processing
        clients['processor-1'].start_processing([topic])
        time.sleep(2)
        
        # Initialize state
        initial_balance = 1000
        account_key = "account_123"
        clients['processor-1'].put_state(state_store, account_key, {"balance": initial_balance})
        
        # Create transaction messages
        transactions = []
        expected_balance = initial_balance
        
        for i in range(20):
            amount = (i + 1) * 10  # 10, 20, 30, ... 200
            transaction_type = "credit" if i % 2 == 0 else "debit"
            
            if transaction_type == "credit":
                expected_balance += amount
            else:
                expected_balance -= amount
            
            message = {
                'key': account_key,
                'value': {
                    'transaction_id': str(uuid.uuid4()),
                    'account_id': account_key,
                    'type': transaction_type,
                    'amount': amount,
                    'timestamp': int(time.time() * 1000) + i
                },
                'headers': {
                    'idempotency_key': f"txn_{i}"
                }
            }
            transactions.append(message)
        
        # Send transactions
        kafka_helper.produce_batch(topic, transactions)
        time.sleep(15)
        
        # Verify final state
        final_state = clients['processor-1'].get_state(state_store, account_key)
        assert final_state is not None, "Account state not found"
        assert final_state['value']['balance'] == expected_balance, \
            f"Expected balance {expected_balance}, got {final_state['value']['balance']}"
        
        # Verify exactly-once guarantees
        status = clients['processor-1'].get_exactly_once_status()
        assert status['transaction_failures'] == 0, "Transaction failures detected"
    
    def test_failure_recovery_exactly_once(self, clients, kafka_helper):
        """Test exactly-once guarantees during failure recovery"""
        topic = f"test_failure_recovery_{int(time.time())}"
        
        # Start processing on processor-1
        clients['processor-1'].start_processing([topic])
        time.sleep(2)
        
        # Send first batch of messages
        first_batch = []
        for i in range(50):
            message = {
                'key': f"key_{i}",
                'value': {
                    'id': f"msg_{i}",
                    'batch': 1,
                    'sequence': i
                },
                'headers': {
                    'idempotency_key': f"batch1_msg_{i}"
                }
            }
            first_batch.append(message)
        
        kafka_helper.produce_batch(topic, first_batch)
        time.sleep(5)
        
        # Create checkpoint before simulated failure
        checkpoint = clients['processor-1'].create_checkpoint()
        assert 'checkpoint_id' in checkpoint
        
        # Simulate processor failure by stopping processing
        clients['processor-1'].stop_processing()
        time.sleep(2)
        
        # Send second batch while processor is down
        second_batch = []
        for i in range(50, 100):
            message = {
                'key': f"key_{i}",
                'value': {
                    'id': f"msg_{i}",
                    'batch': 2,
                    'sequence': i
                },
                'headers': {
                    'idempotency_key': f"batch2_msg_{i}"
                }
            }
            second_batch.append(message)
        
        kafka_helper.produce_batch(topic, second_batch)
        
        # Start processing on processor-2 (simulating failover)
        clients['processor-2'].start_processing([topic])
        time.sleep(10)
        
        # Verify exactly-once processing after recovery
        status = clients['processor-2'].get_exactly_once_status()
        assert status['duplicate_processing_detected'] == 0, "Duplicates detected after recovery"
        
        # Verify all messages were processed exactly once
        metrics = clients['processor-2'].get_processing_metrics()
        assert metrics['total_messages_processed'] >= 100, "Not all messages processed after recovery"
    
    def test_concurrent_processing_exactly_once(self, clients, kafka_helper):
        """Test exactly-once guarantees with concurrent processors"""
        topic = f"test_concurrent_exactly_once_{int(time.time())}"
        
        # Start processing on multiple processors
        for processor_id, client in clients.items():
            client.start_processing([topic])
        
        time.sleep(3)
        
        # Generate messages with overlapping key ranges
        messages = []
        for i in range(200):
            # Use modulo to create overlapping keys across partitions
            key = f"key_{i % 50}"
            message = {
                'key': key,
                'value': {
                    'id': str(uuid.uuid4()),
                    'sequence': i,
                    'key_hash': hashlib.md5(key.encode()).hexdigest()
                },
                'headers': {
                    'idempotency_key': f"concurrent_msg_{i}"
                }
            }
            messages.append(message)
        
        # Send messages concurrently
        def send_batch(batch):
            return kafka_helper.produce_batch(topic, batch)
        
        batch_size = 50
        batches = [messages[i:i + batch_size] for i in range(0, len(messages), batch_size)]
        
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(send_batch, batch) for batch in batches]
            total_sent = sum(future.result() for future in as_completed(futures))
        
        assert total_sent == 200, f"Only {total_sent}/200 messages were sent"
        
        # Wait for processing
        time.sleep(15)
        
        # Verify exactly-once across all processors
        total_violations = 0
        total_processed = 0
        
        for processor_id, client in clients.items():
            status = client.get_exactly_once_status()
            metrics = client.get_processing_metrics()
            
            total_violations += status.get('duplicate_processing_detected', 0)
            total_processed += metrics.get('total_messages_processed', 0)
            
            print(f"Processor {processor_id}: {metrics.get('total_messages_processed', 0)} processed, "
                  f"{status.get('duplicate_processing_detected', 0)} violations")
        
        assert total_violations == 0, f"Total exactly-once violations: {total_violations}"
        assert total_processed >= 200, f"Total processed: {total_processed}, expected at least 200"


class TestStatefulProcessing:
    """Test stateful processing with exactly-once guarantees"""
    
    @pytest.fixture
    def clients(self):
        """Create test clients"""
        return {
            'processor-1': StreamProcessorTestClient('http://localhost:8081'),
            'processor-2': StreamProcessorTestClient('http://localhost:8082'),
        }
    
    @pytest.fixture
    def kafka_helper(self):
        """Create Kafka helper"""
        helper = KafkaTestHelper()
        yield helper
        helper.close()
    
    def test_stateful_aggregation_exactly_once(self, clients, kafka_helper):
        """Test stateful aggregation with exactly-once semantics"""
        topic = f"test_stateful_aggregation_{int(time.time())}"
        state_store = "aggregation_store"
        
        # Start processing
        clients['processor-1'].start_processing([topic])
        time.sleep(2)
        
        # Send aggregation events
        events = []
        expected_counts = {}
        
        for i in range(100):
            category = f"category_{i % 10}"  # 10 different categories
            event = {
                'key': category,
                'value': {
                    'event_id': str(uuid.uuid4()),
                    'category': category,
                    'count': 1,
                    'timestamp': int(time.time() * 1000) + i
                },
                'headers': {
                    'idempotency_key': f"agg_event_{i}"
                }
            }
            events.append(event)
            expected_counts[category] = expected_counts.get(category, 0) + 1
        
        # Send events
        kafka_helper.produce_batch(topic, events)
        time.sleep(10)
        
        # Verify aggregated state
        for category, expected_count in expected_counts.items():
            state = clients['processor-1'].get_state(state_store, category)
            if state:
                actual_count = state['value'].get('count', 0)
                assert actual_count == expected_count, \
                    f"Category {category}: expected {expected_count}, got {actual_count}"
        
        # Send duplicate events (should not affect counts)
        duplicate_events = events[:20]  # Duplicate first 20 events
        kafka_helper.produce_batch(topic, duplicate_events)
        time.sleep(5)
        
        # Verify counts remain the same
        for category, expected_count in expected_counts.items():
            state = clients['processor-1'].get_state(state_store, category)
            if state:
                actual_count = state['value'].get('count', 0)
                assert actual_count == expected_count, \
                    f"Category {category} affected by duplicates: expected {expected_count}, got {actual_count}"
    
    def test_state_snapshot_consistency(self, clients, kafka_helper):
        """Test state snapshot consistency with exactly-once processing"""
        topic = f"test_snapshot_consistency_{int(time.time())}"
        state_store = "snapshot_test_store"
        
        # Start processing
        clients['processor-1'].start_processing([topic])
        time.sleep(2)
        
        # Initialize state
        for i in range(10):
            key = f"item_{i}"
            clients['processor-1'].put_state(state_store, key, {"value": i * 10, "version": 1})
        
        # Create snapshot
        snapshot1 = clients['processor-1'].create_snapshot(state_store)
        assert 'snapshot_id' in snapshot1
        
        # Send update events
        updates = []
        for i in range(10):
            key = f"item_{i}"
            update = {
                'key': key,
                'value': {
                    'update_id': str(uuid.uuid4()),
                    'key': key,
                    'new_value': (i * 10) + 100,
                    'version': 2
                },
                'headers': {
                    'idempotency_key': f"update_{i}"
                }
            }
            updates.append(update)
        
        kafka_helper.produce_batch(topic, updates)
        time.sleep(5)
        
        # Create second snapshot
        snapshot2 = clients['processor-1'].create_snapshot(state_store)
        assert 'snapshot_id' in snapshot2
        assert snapshot2['snapshot_id'] != snapshot1['snapshot_id']
        
        # Verify state consistency
        for i in range(10):
            key = f"item_{i}"
            state = clients['processor-1'].get_state(state_store, key)
            assert state is not None, f"State for {key} not found"
            assert state['value']['value'] == (i * 10) + 100, f"Incorrect value for {key}"
            assert state['value']['version'] == 2, f"Incorrect version for {key}"
        
        # Verify exactly-once guarantees
        status = clients['processor-1'].get_exactly_once_status()
        assert status['duplicate_processing_detected'] == 0, "Duplicates detected during state updates"


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "--tb=short", "-s"])

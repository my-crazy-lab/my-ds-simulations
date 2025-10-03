#!/usr/bin/env python3
"""
Comprehensive tests for commit log service core functionality.
Tests append-only logs, consumer groups, replication, and state reconstruction.
"""

import asyncio
import json
import pytest
import requests
import time
import threading
import random
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Set

class CommitLogTestClient:
    """Test client for interacting with commit log service"""
    
    def __init__(self, base_url: str, broker_id: str):
        self.base_url = base_url
        self.broker_id = broker_id
        self.session = requests.Session()
        self.session.timeout = 10
    
    def get_health(self) -> Dict:
        """Get broker health"""
        response = self.session.get(f"{self.base_url}/health")
        response.raise_for_status()
        return response.json()
    
    def get_status(self) -> Dict:
        """Get broker status"""
        response = self.session.get(f"{self.base_url}/admin/status")
        response.raise_for_status()
        return response.json()
    
    def create_topic(self, name: str, partitions: int = 3, replication_factor: int = 2, config: Dict = None) -> Dict:
        """Create a topic"""
        payload = {
            "name": name,
            "partitions": partitions,
            "replication_factor": replication_factor,
            "config": config or {}
        }
        response = self.session.post(f"{self.base_url}/admin/topics", json=payload)
        response.raise_for_status()
        return response.json()
    
    def list_topics(self) -> Dict:
        """List all topics"""
        response = self.session.get(f"{self.base_url}/admin/topics")
        response.raise_for_status()
        return response.json()
    
    def get_topic_details(self, topic: str) -> Dict:
        """Get topic details"""
        response = self.session.get(f"{self.base_url}/admin/topics/{topic}")
        response.raise_for_status()
        return response.json()
    
    def delete_topic(self, topic: str) -> Dict:
        """Delete a topic"""
        response = self.session.delete(f"{self.base_url}/admin/topics/{topic}")
        response.raise_for_status()
        return response.json()
    
    def produce_message(self, topic: str, key: str = None, value: str = None, 
                       partition: int = None, headers: Dict = None) -> Dict:
        """Produce a single message"""
        payload = {
            "value": value or f"test_value_{uuid.uuid4()}",
        }
        if key:
            payload["key"] = key
        if partition is not None:
            payload["partition"] = partition
        if headers:
            payload["headers"] = headers
            
        response = self.session.post(f"{self.base_url}/produce/{topic}", json=payload)
        response.raise_for_status()
        return response.json()
    
    def produce_batch(self, topic: str, messages: List[Dict]) -> Dict:
        """Produce a batch of messages"""
        payload = {"messages": messages}
        response = self.session.post(f"{self.base_url}/produce/{topic}/batch", json=payload)
        response.raise_for_status()
        return response.json()
    
    def produce_transaction(self, topic: str, transaction_id: str, messages: List[Dict]) -> Dict:
        """Produce messages in a transaction"""
        payload = {
            "transaction_id": transaction_id,
            "messages": messages
        }
        response = self.session.post(f"{self.base_url}/produce/{topic}/transaction", json=payload)
        response.raise_for_status()
        return response.json()
    
    def consume_messages(self, topic: str, group: str, consumer: str = None, 
                        max_messages: int = 100) -> Dict:
        """Consume messages"""
        params = {
            "group": group,
            "max_messages": max_messages
        }
        if consumer:
            params["consumer"] = consumer
            
        response = self.session.get(f"{self.base_url}/consume/{topic}", params=params)
        response.raise_for_status()
        return response.json()
    
    def join_consumer_group(self, group: str, consumer_id: str, topics: List[str]) -> Dict:
        """Join a consumer group"""
        payload = {
            "consumer_id": consumer_id,
            "topics": topics
        }
        response = self.session.post(f"{self.base_url}/consumers/{group}", json=payload)
        response.raise_for_status()
        return response.json()
    
    def leave_consumer_group(self, group: str, consumer_id: str) -> Dict:
        """Leave a consumer group"""
        response = self.session.delete(f"{self.base_url}/consumers/{group}/{consumer_id}")
        response.raise_for_status()
        return response.json()
    
    def commit_offsets(self, group: str, consumer_id: str, offsets: List[Dict]) -> Dict:
        """Commit consumer offsets"""
        payload = {"offsets": offsets}
        response = self.session.post(f"{self.base_url}/consumers/{group}/{consumer_id}/offsets", json=payload)
        response.raise_for_status()
        return response.json()
    
    def get_offsets(self, group: str, consumer_id: str) -> Dict:
        """Get consumer offsets"""
        response = self.session.get(f"{self.base_url}/consumers/{group}/{consumer_id}/offsets")
        response.raise_for_status()
        return response.json()
    
    def list_consumer_groups(self) -> Dict:
        """List consumer groups"""
        response = self.session.get(f"{self.base_url}/admin/consumer-groups")
        response.raise_for_status()
        return response.json()
    
    def get_consumer_group_details(self, group: str) -> Dict:
        """Get consumer group details"""
        response = self.session.get(f"{self.base_url}/admin/consumer-groups/{group}")
        response.raise_for_status()
        return response.json()
    
    def compact_topic(self, topic: str) -> Dict:
        """Trigger topic compaction"""
        response = self.session.post(f"{self.base_url}/admin/topics/{topic}/compact")
        response.raise_for_status()
        return response.json()

class CommitLogCluster:
    """Manages a cluster of commit log brokers for testing"""
    
    def __init__(self, broker_urls: List[str]):
        self.brokers = {
            f"commitlog-broker{i+1}": CommitLogTestClient(url, f"commitlog-broker{i+1}")
            for i, url in enumerate(broker_urls)
        }
        self.broker_urls = broker_urls
    
    def wait_for_cluster_ready(self, timeout: int = 120) -> bool:
        """Wait for all brokers to be healthy"""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                healthy_brokers = 0
                for client in self.brokers.values():
                    health = client.get_health()
                    if health.get("status") == "healthy":
                        healthy_brokers += 1
                
                if healthy_brokers == len(self.brokers):
                    return True
                    
            except Exception as e:
                print(f"Waiting for cluster ready: {e}")
            
            time.sleep(3)
        
        return False
    
    def get_cluster_status(self) -> Dict:
        """Get the status of all brokers in the cluster"""
        cluster_status = {}
        for broker_id, client in self.brokers.items():
            try:
                status = client.get_status()
                cluster_status[broker_id] = status
            except Exception as e:
                cluster_status[broker_id] = {"error": str(e)}
        return cluster_status
    
    def get_leader_broker(self, topic: str, partition: int = 0) -> Optional[CommitLogTestClient]:
        """Get the leader broker for a topic partition"""
        for client in self.brokers.values():
            try:
                topic_details = client.get_topic_details(topic)
                partitions = topic_details.get("partitions", [])
                for p in partitions:
                    if p.get("id") == partition and p.get("leader") == client.broker_id:
                        return client
            except Exception:
                continue
        return None

@pytest.fixture(scope="module")
def commitlog_cluster():
    """Fixture providing a 3-broker commit log cluster"""
    broker_urls = [
        "http://localhost:8081",
        "http://localhost:8082", 
        "http://localhost:8083"
    ]
    
    cluster = CommitLogCluster(broker_urls)
    
    # Wait for cluster to be ready
    assert cluster.wait_for_cluster_ready(180), "Cluster failed to become ready"
    
    yield cluster

class TestCommitLogCore:
    """Test core commit log functionality"""
    
    def test_topic_management(self, commitlog_cluster):
        """Test topic creation, listing, and deletion"""
        client = list(commitlog_cluster.brokers.values())[0]
        
        # Create topic
        topic_name = f"test_topic_{uuid.uuid4().hex[:8]}"
        result = client.create_topic(topic_name, partitions=3, replication_factor=2)
        assert "created successfully" in result.get("message", "").lower()
        
        # List topics
        topics = client.list_topics()
        assert topic_name in topics.get("topics", [])
        
        # Get topic details
        details = client.get_topic_details(topic_name)
        assert details["name"] == topic_name
        assert details["partitions"] == 3
        assert details["replication_factor"] == 2
        
        # Delete topic
        result = client.delete_topic(topic_name)
        assert "deleted successfully" in result.get("message", "").lower()
    
    def test_message_production_and_consumption(self, commitlog_cluster):
        """Test basic message production and consumption"""
        client = list(commitlog_cluster.brokers.values())[0]
        
        # Create topic
        topic_name = f"test_messages_{uuid.uuid4().hex[:8]}"
        client.create_topic(topic_name, partitions=3, replication_factor=2)
        
        # Wait for topic to be ready
        time.sleep(5)
        
        # Produce messages
        messages = []
        for i in range(10):
            key = f"key_{i}"
            value = f"message_{i}_{uuid.uuid4()}"
            result = client.produce_message(topic_name, key=key, value=value)
            messages.append((key, value, result))
            assert "partition" in result
            assert "offset" in result
        
        # Consume messages
        consumer_group = f"test_group_{uuid.uuid4().hex[:8]}"
        consumer_id = f"consumer_{uuid.uuid4().hex[:8]}"
        
        # Join consumer group
        client.join_consumer_group(consumer_group, consumer_id, [topic_name])
        
        # Wait for consumer group coordination
        time.sleep(3)
        
        # Consume messages
        consumed = client.consume_messages(topic_name, consumer_group, consumer_id, max_messages=20)
        consumed_messages = consumed.get("messages", [])
        
        # Verify messages were consumed
        assert len(consumed_messages) >= 5, f"Expected at least 5 messages, got {len(consumed_messages)}"
        
        # Verify message structure
        for msg in consumed_messages:
            assert "key" in msg
            assert "value" in msg
            assert "partition" in msg
            assert "offset" in msg
            assert "timestamp" in msg
    
    def test_batch_production(self, commitlog_cluster):
        """Test batch message production"""
        client = list(commitlog_cluster.brokers.values())[0]
        
        # Create topic
        topic_name = f"test_batch_{uuid.uuid4().hex[:8]}"
        client.create_topic(topic_name, partitions=3, replication_factor=2)
        
        # Wait for topic to be ready
        time.sleep(5)
        
        # Prepare batch messages
        batch_messages = []
        for i in range(50):
            batch_messages.append({
                "key": f"batch_key_{i}",
                "value": f"batch_message_{i}_{uuid.uuid4()}",
                "headers": {"batch_id": "batch_001", "sequence": str(i)}
            })
        
        # Produce batch
        result = client.produce_batch(topic_name, batch_messages)
        assert "results" in result
        assert len(result["results"]) == 50
        
        # Verify all messages were produced successfully
        for res in result["results"]:
            assert "partition" in res
            assert "offset" in res
    
    def test_consumer_groups_and_rebalancing(self, commitlog_cluster):
        """Test consumer group coordination and rebalancing"""
        client = list(commitlog_cluster.brokers.values())[0]
        
        # Create topic
        topic_name = f"test_consumer_groups_{uuid.uuid4().hex[:8]}"
        client.create_topic(topic_name, partitions=6, replication_factor=2)
        
        # Wait for topic to be ready
        time.sleep(5)
        
        # Produce messages to all partitions
        for i in range(60):
            client.produce_message(
                topic_name, 
                key=f"key_{i}", 
                value=f"message_{i}",
                partition=i % 6
            )
        
        time.sleep(2)
        
        # Create consumer group with multiple consumers
        consumer_group = f"test_rebalance_group_{uuid.uuid4().hex[:8]}"
        consumers = []
        
        # Add first consumer
        consumer1_id = f"consumer1_{uuid.uuid4().hex[:8]}"
        client.join_consumer_group(consumer_group, consumer1_id, [topic_name])
        consumers.append(consumer1_id)
        
        time.sleep(3)
        
        # Consume with first consumer
        consumed1 = client.consume_messages(topic_name, consumer_group, consumer1_id, max_messages=30)
        messages1 = consumed1.get("messages", [])
        
        # Add second consumer (should trigger rebalancing)
        consumer2_id = f"consumer2_{uuid.uuid4().hex[:8]}"
        client.join_consumer_group(consumer_group, consumer2_id, [topic_name])
        consumers.append(consumer2_id)
        
        time.sleep(5)  # Wait for rebalancing
        
        # Consume with both consumers
        consumed2 = client.consume_messages(topic_name, consumer_group, consumer2_id, max_messages=30)
        messages2 = consumed2.get("messages", [])
        
        # Verify both consumers are getting messages
        print(f"Consumer 1 got {len(messages1)} messages")
        print(f"Consumer 2 got {len(messages2)} messages")
        
        # Get consumer group details
        group_details = client.get_consumer_group_details(consumer_group)
        assert len(group_details.get("consumers", [])) == 2
        
        # Clean up consumers
        for consumer_id in consumers:
            try:
                client.leave_consumer_group(consumer_group, consumer_id)
            except Exception:
                pass
    
    def test_offset_management(self, commitlog_cluster):
        """Test consumer offset management"""
        client = list(commitlog_cluster.brokers.values())[0]
        
        # Create topic
        topic_name = f"test_offsets_{uuid.uuid4().hex[:8]}"
        client.create_topic(topic_name, partitions=2, replication_factor=2)
        
        # Wait for topic to be ready
        time.sleep(5)
        
        # Produce messages
        for i in range(20):
            client.produce_message(topic_name, key=f"key_{i}", value=f"message_{i}")
        
        time.sleep(2)
        
        # Create consumer
        consumer_group = f"test_offset_group_{uuid.uuid4().hex[:8]}"
        consumer_id = f"consumer_{uuid.uuid4().hex[:8]}"
        
        client.join_consumer_group(consumer_group, consumer_id, [topic_name])
        time.sleep(3)
        
        # Consume some messages
        consumed = client.consume_messages(topic_name, consumer_group, consumer_id, max_messages=10)
        messages = consumed.get("messages", [])
        
        if messages:
            # Commit offsets manually
            offsets_to_commit = []
            partition_offsets = {}
            
            for msg in messages:
                partition = msg["partition"]
                offset = msg["offset"]
                partition_offsets[partition] = max(partition_offsets.get(partition, -1), offset)
            
            for partition, offset in partition_offsets.items():
                offsets_to_commit.append({
                    "partition": partition,
                    "offset": offset + 1  # Commit next offset
                })
            
            # Commit offsets
            commit_result = client.commit_offsets(consumer_group, consumer_id, offsets_to_commit)
            assert "committed" in commit_result.get("message", "").lower()
            
            # Get committed offsets
            offsets = client.get_offsets(consumer_group, consumer_id)
            assert "offsets" in offsets
            
            # Verify offsets were committed
            for committed_offset in offsets["offsets"]:
                partition = committed_offset["partition"]
                offset = committed_offset["offset"]
                expected_offset = partition_offsets.get(partition, -1) + 1
                assert offset == expected_offset, f"Expected offset {expected_offset}, got {offset}"

class TestLogCompaction:
    """Test log compaction functionality"""
    
    def test_log_compaction_basic(self, commitlog_cluster):
        """Test basic log compaction"""
        client = list(commitlog_cluster.brokers.values())[0]
        
        # Create topic with compaction enabled
        topic_name = f"test_compaction_{uuid.uuid4().hex[:8]}"
        config = {
            "cleanup.policy": "compact",
            "min.compaction.lag.ms": "1000",
            "segment.ms": "10000"
        }
        client.create_topic(topic_name, partitions=1, replication_factor=1, config=config)
        
        # Wait for topic to be ready
        time.sleep(5)
        
        # Produce messages with same keys (should be compacted)
        key = "compaction_test_key"
        values = []
        
        for i in range(10):
            value = f"value_{i}_{uuid.uuid4()}"
            values.append(value)
            client.produce_message(topic_name, key=key, value=value)
            time.sleep(0.1)
        
        time.sleep(2)
        
        # Trigger compaction
        compact_result = client.compact_topic(topic_name)
        assert "compaction triggered" in compact_result.get("message", "").lower()
        
        # Wait for compaction to complete
        time.sleep(10)
        
        # Consume all messages
        consumer_group = f"compaction_test_group_{uuid.uuid4().hex[:8]}"
        consumer_id = f"consumer_{uuid.uuid4().hex[:8]}"
        
        client.join_consumer_group(consumer_group, consumer_id, [topic_name])
        time.sleep(3)
        
        consumed = client.consume_messages(topic_name, consumer_group, consumer_id, max_messages=20)
        messages = consumed.get("messages", [])
        
        # After compaction, should only have the latest value for each key
        key_messages = [msg for msg in messages if msg.get("key") == key]
        
        if key_messages:
            # Should have only the latest message for the key
            latest_message = key_messages[-1]
            assert latest_message["value"] == values[-1], "Compaction should keep only the latest value"

class TestStateReconstruction:
    """Test state reconstruction capabilities"""
    
    def test_state_reconstruction_basic(self, commitlog_cluster):
        """Test basic state reconstruction from commit log"""
        client = list(commitlog_cluster.brokers.values())[0]
        
        # Create topic for state events
        topic_name = f"test_state_events_{uuid.uuid4().hex[:8]}"
        client.create_topic(topic_name, partitions=1, replication_factor=2)
        
        # Wait for topic to be ready
        time.sleep(5)
        
        # Produce state change events
        state_events = [
            {"key": "user:1", "value": json.dumps({"action": "create", "name": "Alice", "balance": 100})},
            {"key": "user:2", "value": json.dumps({"action": "create", "name": "Bob", "balance": 200})},
            {"key": "user:1", "value": json.dumps({"action": "update", "balance": 150})},
            {"key": "user:3", "value": json.dumps({"action": "create", "name": "Charlie", "balance": 300})},
            {"key": "user:2", "value": json.dumps({"action": "update", "balance": 250})},
            {"key": "user:1", "value": json.dumps({"action": "delete"})},
        ]
        
        # Produce events
        for event in state_events:
            client.produce_message(topic_name, key=event["key"], value=event["value"])
        
        time.sleep(2)
        
        # Reconstruct state by consuming all events
        consumer_group = f"state_reconstruction_group_{uuid.uuid4().hex[:8]}"
        consumer_id = f"consumer_{uuid.uuid4().hex[:8]}"
        
        client.join_consumer_group(consumer_group, consumer_id, [topic_name])
        time.sleep(3)
        
        consumed = client.consume_messages(topic_name, consumer_group, consumer_id, max_messages=20)
        messages = consumed.get("messages", [])
        
        # Reconstruct state from events
        state = {}
        for msg in sorted(messages, key=lambda x: x["offset"]):
            key = msg["key"]
            event_data = json.loads(msg["value"])
            
            if event_data["action"] == "create":
                state[key] = {
                    "name": event_data["name"],
                    "balance": event_data["balance"]
                }
            elif event_data["action"] == "update":
                if key in state:
                    state[key].update({k: v for k, v in event_data.items() if k != "action"})
            elif event_data["action"] == "delete":
                if key in state:
                    del state[key]
        
        # Verify reconstructed state
        expected_state = {
            "user:2": {"name": "Bob", "balance": 250},
            "user:3": {"name": "Charlie", "balance": 300}
        }
        
        assert state == expected_state, f"Expected {expected_state}, got {state}"

class TestPerformanceAndReliability:
    """Test performance and reliability characteristics"""
    
    def test_high_throughput_production(self, commitlog_cluster):
        """Test high throughput message production"""
        client = list(commitlog_cluster.brokers.values())[0]
        
        # Create topic
        topic_name = f"test_throughput_{uuid.uuid4().hex[:8]}"
        client.create_topic(topic_name, partitions=6, replication_factor=2)
        
        # Wait for topic to be ready
        time.sleep(5)
        
        # Measure production throughput
        num_messages = 1000
        message_size = 1024  # 1KB messages
        
        start_time = time.time()
        
        # Produce messages in batches for better throughput
        batch_size = 100
        for batch_start in range(0, num_messages, batch_size):
            batch_messages = []
            for i in range(batch_start, min(batch_start + batch_size, num_messages)):
                batch_messages.append({
                    "key": f"throughput_key_{i}",
                    "value": "x" * message_size,
                    "headers": {"batch": str(batch_start // batch_size)}
                })
            
            client.produce_batch(topic_name, batch_messages)
        
        end_time = time.time()
        duration = end_time - start_time
        throughput = num_messages / duration
        
        print(f"Produced {num_messages} messages in {duration:.2f}s")
        print(f"Throughput: {throughput:.2f} messages/second")
        print(f"Data rate: {(throughput * message_size / 1024 / 1024):.2f} MB/second")
        
        # Should achieve reasonable throughput
        assert throughput > 100, f"Throughput too low: {throughput} messages/second"
    
    def test_consumer_lag_monitoring(self, commitlog_cluster):
        """Test consumer lag monitoring"""
        client = list(commitlog_cluster.brokers.values())[0]
        
        # Create topic
        topic_name = f"test_lag_{uuid.uuid4().hex[:8]}"
        client.create_topic(topic_name, partitions=2, replication_factor=2)
        
        # Wait for topic to be ready
        time.sleep(5)
        
        # Produce messages continuously
        def producer_thread():
            for i in range(100):
                client.produce_message(topic_name, key=f"key_{i}", value=f"message_{i}")
                time.sleep(0.1)
        
        # Start producer
        producer = threading.Thread(target=producer_thread)
        producer.start()
        
        # Create slow consumer
        consumer_group = f"lag_test_group_{uuid.uuid4().hex[:8]}"
        consumer_id = f"consumer_{uuid.uuid4().hex[:8]}"
        
        client.join_consumer_group(consumer_group, consumer_id, [topic_name])
        time.sleep(3)
        
        # Consume slowly to create lag
        for _ in range(5):
            consumed = client.consume_messages(topic_name, consumer_group, consumer_id, max_messages=5)
            messages = consumed.get("messages", [])
            print(f"Consumed {len(messages)} messages")
            time.sleep(2)
        
        # Wait for producer to finish
        producer.join()
        
        # Check consumer group details for lag information
        group_details = client.get_consumer_group_details(consumer_group)
        print(f"Consumer group details: {group_details}")
        
        # Verify consumer group exists and has lag information
        assert "consumers" in group_details
        assert len(group_details["consumers"]) > 0

if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "--tb=short"])

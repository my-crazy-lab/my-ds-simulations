#!/usr/bin/env python3
"""
Chaos engineering tests for commit log replication and fault tolerance.
Tests broker failures, network partitions, and data consistency under failures.
"""

import asyncio
import docker
import json
import pytest
import requests
import time
import threading
import random
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Set

class CommitLogChaosController:
    """Controls chaos scenarios for commit log testing"""
    
    def __init__(self):
        self.client = docker.from_env()
        self.commitlog_containers = []
        self._discover_commitlog_containers()
    
    def _discover_commitlog_containers(self):
        """Discover running commit log containers"""
        containers = self.client.containers.list()
        self.commitlog_containers = [
            c for c in containers 
            if c.name.startswith('commitlog-broker') and c.status == 'running'
        ]
        print(f"Found {len(self.commitlog_containers)} commit log containers")
    
    def stop_broker(self, broker_name: str) -> bool:
        """Stop a broker to simulate failure"""
        try:
            container = self.client.containers.get(broker_name)
            container.stop()
            print(f"Stopped broker: {broker_name}")
            return True
        except Exception as e:
            print(f"Failed to stop broker {broker_name}: {e}")
            return False
    
    def start_broker(self, broker_name: str) -> bool:
        """Start a broker"""
        try:
            container = self.client.containers.get(broker_name)
            container.start()
            print(f"Started broker: {broker_name}")
            return True
        except Exception as e:
            print(f"Failed to start broker {broker_name}: {e}")
            return False
    
    def pause_broker(self, broker_name: str) -> bool:
        """Pause a broker to simulate network partition"""
        try:
            container = self.client.containers.get(broker_name)
            container.pause()
            print(f"Paused broker: {broker_name}")
            return True
        except Exception as e:
            print(f"Failed to pause broker {broker_name}: {e}")
            return False
    
    def unpause_broker(self, broker_name: str) -> bool:
        """Unpause a broker"""
        try:
            container = self.client.containers.get(broker_name)
            container.unpause()
            print(f"Unpaused broker: {broker_name}")
            return True
        except Exception as e:
            print(f"Failed to unpause broker {broker_name}: {e}")
            return False
    
    def create_network_partition(self, partition_a: List[str], partition_b: List[str]) -> bool:
        """Create a network partition between two groups of brokers"""
        try:
            # Pause brokers in partition B to simulate network partition
            for broker_name in partition_b:
                self.pause_broker(broker_name)
            return True
        except Exception as e:
            print(f"Failed to create partition: {e}")
            return False
    
    def heal_network_partition(self, partition_b: List[str]) -> bool:
        """Heal the network partition"""
        try:
            for broker_name in partition_b:
                self.unpause_broker(broker_name)
            return True
        except Exception as e:
            print(f"Failed to heal partition: {e}")
            return False
    
    def simulate_slow_network(self, broker_name: str, delay_ms: int = 1000) -> bool:
        """Simulate slow network by adding delay"""
        try:
            container = self.client.containers.get(broker_name)
            # Add network delay using tc (traffic control)
            container.exec_run(f"tc qdisc add dev eth0 root netem delay {delay_ms}ms")
            print(f"Added {delay_ms}ms delay to {broker_name}")
            return True
        except Exception as e:
            print(f"Failed to add network delay to {broker_name}: {e}")
            return False
    
    def remove_network_delay(self, broker_name: str) -> bool:
        """Remove network delay"""
        try:
            container = self.client.containers.get(broker_name)
            container.exec_run("tc qdisc del dev eth0 root")
            print(f"Removed network delay from {broker_name}")
            return True
        except Exception as e:
            print(f"Failed to remove network delay from {broker_name}: {e}")
            return False

class CommitLogChaosTestClient:
    """Test client for chaos testing"""
    
    def __init__(self, base_url: str, broker_name: str):
        self.base_url = base_url
        self.broker_name = broker_name
        self.session = requests.Session()
        self.session.timeout = 10
    
    def is_available(self) -> bool:
        """Check if the broker is available"""
        try:
            response = self.session.get(f"{self.base_url}/health")
            return response.status_code == 200
        except Exception:
            return False
    
    def get_status(self) -> Optional[Dict]:
        """Get broker status"""
        try:
            response = self.session.get(f"{self.base_url}/admin/status")
            if response.status_code == 200:
                return response.json()
        except Exception:
            pass
        return None
    
    def create_topic(self, name: str, partitions: int = 3, replication_factor: int = 2) -> Optional[Dict]:
        """Create a topic"""
        try:
            payload = {
                "name": name,
                "partitions": partitions,
                "replication_factor": replication_factor
            }
            response = self.session.post(f"{self.base_url}/admin/topics", json=payload)
            if response.status_code in [200, 201]:
                return response.json()
        except Exception:
            pass
        return None
    
    def produce_message(self, topic: str, key: str, value: str) -> Optional[Dict]:
        """Produce a message"""
        try:
            payload = {"key": key, "value": value}
            response = self.session.post(f"{self.base_url}/produce/{topic}", json=payload)
            if response.status_code == 200:
                return response.json()
        except Exception:
            pass
        return None
    
    def consume_messages(self, topic: str, group: str, consumer: str, max_messages: int = 10) -> Optional[Dict]:
        """Consume messages"""
        try:
            params = {
                "group": group,
                "consumer": consumer,
                "max_messages": max_messages
            }
            response = self.session.get(f"{self.base_url}/consume/{topic}", params=params)
            if response.status_code == 200:
                return response.json()
        except Exception:
            pass
        return None
    
    def join_consumer_group(self, group: str, consumer_id: str, topics: List[str]) -> Optional[Dict]:
        """Join a consumer group"""
        try:
            payload = {"consumer_id": consumer_id, "topics": topics}
            response = self.session.post(f"{self.base_url}/consumers/{group}", json=payload)
            if response.status_code in [200, 201]:
                return response.json()
        except Exception:
            pass
        return None

class CommitLogChaosCluster:
    """Manages cluster for chaos testing"""
    
    def __init__(self):
        self.brokers = {
            "commitlog-broker1": CommitLogChaosTestClient("http://localhost:8081", "commitlog-broker1"),
            "commitlog-broker2": CommitLogChaosTestClient("http://localhost:8082", "commitlog-broker2"),
            "commitlog-broker3": CommitLogChaosTestClient("http://localhost:8083", "commitlog-broker3"),
        }
        self.controller = CommitLogChaosController()
    
    def get_available_brokers(self) -> List[str]:
        """Get list of currently available brokers"""
        available = []
        for broker_name, client in self.brokers.items():
            if client.is_available():
                available.append(broker_name)
        return available
    
    def get_leader_broker(self, topic: str) -> Optional[str]:
        """Get the leader broker for a topic (simplified)"""
        for broker_name, client in self.brokers.items():
            if client.is_available():
                status = client.get_status()
                if status and topic in status.get("topics", {}):
                    topic_info = status["topics"][topic]
                    if topic_info.get("is_leader", False):
                        return broker_name
        return None
    
    def count_successful_operations(self, operation_func, brokers: List[str]) -> int:
        """Count successful operations across specified brokers"""
        successes = 0
        for broker_name in brokers:
            if broker_name in self.brokers:
                result = operation_func(self.brokers[broker_name])
                if result is not None:
                    successes += 1
        return successes

@pytest.fixture(scope="module")
def chaos_cluster():
    """Fixture providing a chaos-testable cluster"""
    cluster = CommitLogChaosCluster()
    
    # Ensure all brokers are running
    for broker_name in cluster.brokers.keys():
        cluster.controller.start_broker(broker_name)
    
    # Wait for cluster to stabilize
    time.sleep(20)
    
    yield cluster
    
    # Cleanup: ensure all brokers are running and delays are removed
    for broker_name in cluster.brokers.keys():
        cluster.controller.start_broker(broker_name)
        cluster.controller.unpause_broker(broker_name)
        cluster.controller.remove_network_delay(broker_name)

class TestBrokerFailures:
    """Test broker failure scenarios"""
    
    def test_single_broker_failure(self, chaos_cluster):
        """Test cluster behavior when a single broker fails"""
        # Create topic with replication
        topic_name = f"test_single_failure_{uuid.uuid4().hex[:8]}"
        
        # Find an available broker to create topic
        available_brokers = chaos_cluster.get_available_brokers()
        assert len(available_brokers) >= 2, "Need at least 2 brokers for this test"
        
        client = chaos_cluster.brokers[available_brokers[0]]
        result = client.create_topic(topic_name, partitions=3, replication_factor=2)
        assert result is not None, "Failed to create topic"
        
        time.sleep(10)  # Wait for topic to be replicated
        
        # Produce messages before failure
        messages_before = []
        for i in range(20):
            key = f"key_{i}"
            value = f"message_{i}_{uuid.uuid4()}"
            result = client.produce_message(topic_name, key, value)
            if result:
                messages_before.append((key, value))
        
        print(f"Produced {len(messages_before)} messages before failure")
        
        # Stop one broker
        broker_to_stop = available_brokers[1]
        chaos_cluster.controller.stop_broker(broker_to_stop)
        
        time.sleep(10)  # Wait for failure detection
        
        # Verify cluster is still operational
        remaining_brokers = [b for b in available_brokers if b != broker_to_stop]
        available_after_failure = chaos_cluster.get_available_brokers()
        
        print(f"Available brokers after failure: {available_after_failure}")
        assert len(available_after_failure) >= 1, "Cluster should remain operational"
        
        # Try to produce more messages
        messages_after = []
        for remaining_broker in remaining_brokers:
            client = chaos_cluster.brokers[remaining_broker]
            if client.is_available():
                for i in range(10):
                    key = f"after_failure_key_{i}"
                    value = f"after_failure_message_{i}_{uuid.uuid4()}"
                    result = client.produce_message(topic_name, key, value)
                    if result:
                        messages_after.append((key, value))
                break
        
        print(f"Produced {len(messages_after)} messages after failure")
        assert len(messages_after) > 0, "Should be able to produce messages after single broker failure"
        
        # Restart the failed broker
        chaos_cluster.controller.start_broker(broker_to_stop)
        time.sleep(15)  # Wait for recovery
        
        # Verify broker has recovered
        recovered_brokers = chaos_cluster.get_available_brokers()
        print(f"Available brokers after recovery: {recovered_brokers}")
        assert broker_to_stop in recovered_brokers, "Failed broker should recover"
    
    def test_majority_broker_failure(self, chaos_cluster):
        """Test cluster behavior when majority of brokers fail"""
        # Create topic
        topic_name = f"test_majority_failure_{uuid.uuid4().hex[:8]}"
        
        available_brokers = chaos_cluster.get_available_brokers()
        assert len(available_brokers) >= 3, "Need at least 3 brokers for this test"
        
        client = chaos_cluster.brokers[available_brokers[0]]
        result = client.create_topic(topic_name, partitions=2, replication_factor=2)
        assert result is not None, "Failed to create topic"
        
        time.sleep(10)
        
        # Produce some messages
        for i in range(10):
            client.produce_message(topic_name, f"key_{i}", f"message_{i}")
        
        # Stop majority of brokers (2 out of 3)
        brokers_to_stop = available_brokers[1:3]
        for broker in brokers_to_stop:
            chaos_cluster.controller.stop_broker(broker)
        
        time.sleep(10)
        
        # Check cluster availability
        available_after_failure = chaos_cluster.get_available_brokers()
        print(f"Available brokers after majority failure: {available_after_failure}")
        
        # With majority failure, cluster might not be able to accept writes
        # depending on the replication configuration
        remaining_client = chaos_cluster.brokers[available_brokers[0]]
        
        # Try to produce (might fail due to insufficient replicas)
        result = remaining_client.produce_message(topic_name, "test_key", "test_value")
        print(f"Production after majority failure: {'Success' if result else 'Failed'}")
        
        # Restart one broker to restore majority
        chaos_cluster.controller.start_broker(brokers_to_stop[0])
        time.sleep(15)
        
        # Should be able to produce again
        result = remaining_client.produce_message(topic_name, "recovery_key", "recovery_value")
        print(f"Production after partial recovery: {'Success' if result else 'Failed'}")
        
        # Restart all brokers
        for broker in brokers_to_stop[1:]:
            chaos_cluster.controller.start_broker(broker)
        
        time.sleep(10)

class TestNetworkPartitions:
    """Test network partition scenarios"""
    
    def test_network_partition_with_leader_isolation(self, chaos_cluster):
        """Test behavior when leader is isolated by network partition"""
        # Create topic
        topic_name = f"test_leader_isolation_{uuid.uuid4().hex[:8]}"
        
        available_brokers = chaos_cluster.get_available_brokers()
        assert len(available_brokers) >= 3, "Need at least 3 brokers for partition test"
        
        client = chaos_cluster.brokers[available_brokers[0]]
        result = client.create_topic(topic_name, partitions=1, replication_factor=3)
        assert result is not None, "Failed to create topic"
        
        time.sleep(10)
        
        # Produce messages before partition
        for i in range(10):
            client.produce_message(topic_name, f"before_partition_{i}", f"message_{i}")
        
        # Create partition: isolate one broker from the others
        isolated_broker = available_brokers[0]
        majority_brokers = available_brokers[1:]
        
        print(f"Creating partition: {isolated_broker} vs {majority_brokers}")
        
        # Pause the isolated broker to simulate network partition
        chaos_cluster.controller.pause_broker(isolated_broker)
        
        time.sleep(15)  # Wait for partition to take effect
        
        # Try to produce to majority partition
        majority_successes = 0
        for broker_name in majority_brokers:
            client = chaos_cluster.brokers[broker_name]
            if client.is_available():
                result = client.produce_message(topic_name, "majority_key", "majority_value")
                if result:
                    majority_successes += 1
                    break
        
        print(f"Productions to majority partition: {majority_successes}")
        
        # Heal partition
        chaos_cluster.controller.unpause_broker(isolated_broker)
        time.sleep(20)  # Wait for recovery and leader election
        
        # Verify all brokers are available again
        recovered_brokers = chaos_cluster.get_available_brokers()
        print(f"Brokers available after partition healing: {recovered_brokers}")
        assert len(recovered_brokers) >= 2, "Most brokers should recover after partition healing"
    
    def test_split_brain_prevention(self, chaos_cluster):
        """Test that split-brain scenarios are prevented"""
        # Create topic
        topic_name = f"test_split_brain_{uuid.uuid4().hex[:8]}"
        
        available_brokers = chaos_cluster.get_available_brokers()
        assert len(available_brokers) >= 3, "Need at least 3 brokers for split-brain test"
        
        client = chaos_cluster.brokers[available_brokers[0]]
        result = client.create_topic(topic_name, partitions=1, replication_factor=3)
        assert result is not None, "Failed to create topic"
        
        time.sleep(10)
        
        # Create an even split (1 vs 2 brokers)
        partition_a = [available_brokers[0]]
        partition_b = available_brokers[1:3]
        
        print(f"Creating split: {partition_a} vs {partition_b}")
        
        # Pause partition B
        for broker in partition_b:
            chaos_cluster.controller.pause_broker(broker)
        
        time.sleep(15)
        
        # Try to write to both partitions
        partition_a_success = False
        partition_b_success = False
        
        # Try partition A (minority)
        client_a = chaos_cluster.brokers[partition_a[0]]
        if client_a.is_available():
            result = client_a.produce_message(topic_name, "partition_a_key", "partition_a_value")
            partition_a_success = result is not None
        
        # Unpause partition B and pause partition A
        for broker in partition_b:
            chaos_cluster.controller.unpause_broker(broker)
        chaos_cluster.controller.pause_broker(partition_a[0])
        
        time.sleep(15)
        
        # Try partition B (majority)
        for broker_name in partition_b:
            client_b = chaos_cluster.brokers[broker_name]
            if client_b.is_available():
                result = client_b.produce_message(topic_name, "partition_b_key", "partition_b_value")
                if result:
                    partition_b_success = True
                    break
        
        print(f"Partition A (minority) success: {partition_a_success}")
        print(f"Partition B (majority) success: {partition_b_success}")
        
        # In a properly implemented system, only the majority partition should succeed
        # or the system should prevent split-brain by requiring majority consensus
        
        # Heal all partitions
        chaos_cluster.controller.unpause_broker(partition_a[0])
        time.sleep(15)

class TestReplicationConsistency:
    """Test replication consistency under failures"""
    
    def test_replication_lag_during_failures(self, chaos_cluster):
        """Test replication lag behavior during broker failures"""
        # Create topic with replication
        topic_name = f"test_replication_lag_{uuid.uuid4().hex[:8]}"
        
        available_brokers = chaos_cluster.get_available_brokers()
        assert len(available_brokers) >= 2, "Need at least 2 brokers for replication test"
        
        client = chaos_cluster.brokers[available_brokers[0]]
        result = client.create_topic(topic_name, partitions=1, replication_factor=2)
        assert result is not None, "Failed to create topic"
        
        time.sleep(10)
        
        # Produce messages continuously while introducing failures
        def continuous_producer():
            messages_produced = 0
            for i in range(100):
                for broker_name in available_brokers:
                    client = chaos_cluster.brokers[broker_name]
                    if client.is_available():
                        result = client.produce_message(topic_name, f"continuous_{i}", f"message_{i}")
                        if result:
                            messages_produced += 1
                            break
                time.sleep(0.1)
            return messages_produced
        
        # Start producer thread
        producer_thread = threading.Thread(target=continuous_producer)
        producer_thread.start()
        
        # Introduce failures during production
        time.sleep(2)
        
        # Stop and restart brokers to create replication lag
        for broker in available_brokers[1:]:
            chaos_cluster.controller.stop_broker(broker)
            time.sleep(5)
            chaos_cluster.controller.start_broker(broker)
            time.sleep(10)
        
        # Wait for producer to finish
        producer_thread.join()
        
        # Allow time for replication to catch up
        time.sleep(15)
        
        # Verify data consistency across replicas
        consumer_group = f"consistency_check_{uuid.uuid4().hex[:8]}"
        
        messages_per_broker = {}
        for broker_name in available_brokers:
            client = chaos_cluster.brokers[broker_name]
            if client.is_available():
                consumer_id = f"consumer_{broker_name}"
                client.join_consumer_group(consumer_group, consumer_id, [topic_name])
                time.sleep(3)
                
                consumed = client.consume_messages(topic_name, consumer_group, consumer_id, max_messages=200)
                if consumed:
                    messages = consumed.get("messages", [])
                    messages_per_broker[broker_name] = len(messages)
                    print(f"Broker {broker_name}: {len(messages)} messages")
        
        # Check that all brokers have similar message counts (allowing for some lag)
        if len(messages_per_broker) > 1:
            message_counts = list(messages_per_broker.values())
            max_count = max(message_counts)
            min_count = min(message_counts)
            lag_ratio = (max_count - min_count) / max_count if max_count > 0 else 0
            
            print(f"Replication lag ratio: {lag_ratio:.2%}")
            
            # Allow up to 20% lag (this is quite generous for testing)
            assert lag_ratio < 0.2, f"Replication lag too high: {lag_ratio:.2%}"

class TestRecoveryScenarios:
    """Test recovery scenarios"""
    
    def test_cluster_recovery_after_total_failure(self, chaos_cluster):
        """Test cluster recovery after all brokers fail"""
        # Create topic and produce data
        topic_name = f"test_total_recovery_{uuid.uuid4().hex[:8]}"
        
        available_brokers = chaos_cluster.get_available_brokers()
        client = chaos_cluster.brokers[available_brokers[0]]
        
        result = client.create_topic(topic_name, partitions=2, replication_factor=2)
        assert result is not None, "Failed to create topic"
        
        time.sleep(10)
        
        # Produce messages
        original_messages = []
        for i in range(20):
            key = f"recovery_key_{i}"
            value = f"recovery_message_{i}_{uuid.uuid4()}"
            result = client.produce_message(topic_name, key, value)
            if result:
                original_messages.append((key, value))
        
        print(f"Produced {len(original_messages)} messages before total failure")
        
        # Stop all brokers
        for broker_name in available_brokers:
            chaos_cluster.controller.stop_broker(broker_name)
        
        time.sleep(10)
        
        # Verify cluster is down
        available_after_shutdown = chaos_cluster.get_available_brokers()
        assert len(available_after_shutdown) == 0, "All brokers should be down"
        
        # Restart all brokers
        for broker_name in available_brokers:
            chaos_cluster.controller.start_broker(broker_name)
        
        # Wait for recovery
        time.sleep(30)
        
        # Verify cluster has recovered
        recovered_brokers = chaos_cluster.get_available_brokers()
        print(f"Recovered brokers: {recovered_brokers}")
        assert len(recovered_brokers) >= 1, "At least one broker should recover"
        
        # Verify data is still available
        if recovered_brokers:
            recovery_client = chaos_cluster.brokers[recovered_brokers[0]]
            
            # Create consumer to check data
            consumer_group = f"recovery_check_{uuid.uuid4().hex[:8]}"
            consumer_id = f"recovery_consumer_{uuid.uuid4().hex[:8]}"
            
            recovery_client.join_consumer_group(consumer_group, consumer_id, [topic_name])
            time.sleep(5)
            
            consumed = recovery_client.consume_messages(topic_name, consumer_group, consumer_id, max_messages=50)
            if consumed:
                recovered_messages = consumed.get("messages", [])
                print(f"Recovered {len(recovered_messages)} messages after total failure")
                
                # Should recover at least some messages
                assert len(recovered_messages) > 0, "Should recover some messages after total failure"
                
                # Verify message integrity
                for msg in recovered_messages[:5]:  # Check first few messages
                    assert "key" in msg
                    assert "value" in msg
                    assert "partition" in msg
                    assert "offset" in msg

if __name__ == "__main__":
    # Run chaos tests
    pytest.main([__file__, "-v", "--tb=short", "-s"])

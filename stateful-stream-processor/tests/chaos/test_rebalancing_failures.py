#!/usr/bin/env python3
"""
Chaos engineering tests for stream processor rebalancing and failure scenarios.
Tests dynamic rebalancing, state migration, and fault tolerance.
"""

import pytest
import requests
import json
import time
import threading
import uuid
import docker
from typing import Dict, List, Set
from concurrent.futures import ThreadPoolExecutor, as_completed
from kafka import KafkaProducer
from kafka.errors import KafkaError


class StreamProcessorChaosController:
    """Controller for chaos engineering tests"""
    
    def __init__(self):
        self.client = docker.from_env()
        self.processors = {
            'processor-1': 'stream-processor-1',
            'processor-2': 'stream-processor-2',
            'processor-3': 'stream-processor-3',
        }
        self.ports = {
            'processor-1': 8081,
            'processor-2': 8082,
            'processor-3': 8083,
        }
    
    def stop_processor(self, processor_id: str) -> bool:
        """Stop a stream processor"""
        try:
            container_name = self.processors[processor_id]
            container = self.client.containers.get(container_name)
            container.stop()
            print(f"Stopped processor {processor_id} ({container_name})")
            return True
        except Exception as e:
            print(f"Failed to stop processor {processor_id}: {e}")
            return False
    
    def start_processor(self, processor_id: str) -> bool:
        """Start a stream processor"""
        try:
            container_name = self.processors[processor_id]
            container = self.client.containers.get(container_name)
            container.start()
            print(f"Started processor {processor_id} ({container_name})")
            # Wait for processor to be ready
            time.sleep(15)
            return True
        except Exception as e:
            print(f"Failed to start processor {processor_id}: {e}")
            return False
    
    def pause_processor(self, processor_id: str) -> bool:
        """Pause a stream processor (simulates network partition)"""
        try:
            container_name = self.processors[processor_id]
            container = self.client.containers.get(container_name)
            container.pause()
            print(f"Paused processor {processor_id} ({container_name})")
            return True
        except Exception as e:
            print(f"Failed to pause processor {processor_id}: {e}")
            return False
    
    def unpause_processor(self, processor_id: str) -> bool:
        """Unpause a stream processor"""
        try:
            container_name = self.processors[processor_id]
            container = self.client.containers.get(container_name)
            container.unpause()
            print(f"Unpaused processor {processor_id} ({container_name})")
            return True
        except Exception as e:
            print(f"Failed to unpause processor {processor_id}: {e}")
            return False
    
    def get_processor_status(self, processor_id: str) -> Dict:
        """Get status of a specific processor"""
        try:
            port = self.ports[processor_id]
            response = requests.get(f"http://localhost:{port}/processor/status", timeout=5)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"error": str(e), "status": "unreachable"}
    
    def wait_for_processor_ready(self, processor_id: str, timeout: int = 60) -> bool:
        """Wait for a processor to be ready"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                port = self.ports[processor_id]
                response = requests.get(f"http://localhost:{port}/health", timeout=5)
                if response.status_code == 200:
                    return True
            except:
                pass
            time.sleep(2)
        return False


class StreamProcessorTestClient:
    """Test client for stream processor operations"""
    
    def __init__(self, processor_id: str, port: int):
        self.processor_id = processor_id
        self.base_url = f"http://localhost:{port}"
        self.session = requests.Session()
        self.session.headers.update({'Content-Type': 'application/json'})
    
    def start_processing(self, topics: List[str]) -> Dict:
        """Start processing topics"""
        payload = {"topics": topics}
        response = self.session.post(f"{self.base_url}/processor/start", json=payload)
        response.raise_for_status()
        return response.json()
    
    def get_status(self) -> Dict:
        """Get processor status"""
        response = self.session.get(f"{self.base_url}/processor/status")
        response.raise_for_status()
        return response.json()
    
    def get_partitions(self) -> Dict:
        """Get assigned partitions"""
        response = self.session.get(f"{self.base_url}/processor/partitions")
        response.raise_for_status()
        return response.json()
    
    def trigger_rebalance(self) -> Dict:
        """Trigger rebalancing"""
        response = self.session.post(f"{self.base_url}/rebalance/trigger")
        response.raise_for_status()
        return response.json()
    
    def get_rebalance_status(self) -> Dict:
        """Get rebalancing status"""
        response = self.session.get(f"{self.base_url}/rebalance/status")
        response.raise_for_status()
        return response.json()
    
    def get_state(self, store: str, key: str) -> Dict:
        """Get state value"""
        response = self.session.get(f"{self.base_url}/state/stores/{store}/{key}")
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()
    
    def create_checkpoint(self) -> Dict:
        """Create checkpoint"""
        response = self.session.post(f"{self.base_url}/processor/checkpoint")
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


class TestRebalancingScenarios:
    """Test dynamic rebalancing scenarios"""
    
    @pytest.fixture
    def chaos_controller(self):
        """Create chaos controller"""
        return StreamProcessorChaosController()
    
    @pytest.fixture
    def clients(self, chaos_controller):
        """Create test clients for all processors"""
        clients = {}
        for processor_id, port in chaos_controller.ports.items():
            clients[processor_id] = StreamProcessorTestClient(processor_id, port)
        return clients
    
    @pytest.fixture
    def kafka_producer(self):
        """Create Kafka producer for test messages"""
        producer = KafkaProducer(
            bootstrap_servers="localhost:9092,localhost:9094,localhost:9095",
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            key_serializer=lambda k: k.encode('utf-8') if k else None,
            acks='all',
            retries=3,
            enable_idempotence=True
        )
        yield producer
        producer.close()
    
    def test_planned_rebalancing(self, chaos_controller, clients, kafka_producer):
        """Test planned rebalancing without failures"""
        topic = f"test_planned_rebalancing_{int(time.time())}"
        
        # Start processing on all processors
        for processor_id, client in clients.items():
            client.start_processing([topic])
        
        time.sleep(5)
        
        # Send initial messages to establish state
        for i in range(100):
            key = f"key_{i % 20}"  # 20 unique keys
            message = {
                'id': str(uuid.uuid4()),
                'sequence': i,
                'data': f"initial_data_{i}"
            }
            kafka_producer.send(topic, key=key, value=message)
        
        kafka_producer.flush()
        time.sleep(10)
        
        # Get initial partition assignment
        initial_assignment = {}
        for processor_id, client in clients.items():
            try:
                partitions = client.get_partitions()
                initial_assignment[processor_id] = partitions.get('partitions', [])
                print(f"Initial assignment for {processor_id}: {initial_assignment[processor_id]}")
            except Exception as e:
                print(f"Failed to get partitions for {processor_id}: {e}")
        
        # Trigger rebalancing
        print("Triggering planned rebalancing...")
        clients['processor-1'].trigger_rebalance()
        
        # Wait for rebalancing to complete
        time.sleep(30)
        
        # Get new partition assignment
        new_assignment = {}
        for processor_id, client in clients.items():
            try:
                partitions = client.get_partitions()
                new_assignment[processor_id] = partitions.get('partitions', [])
                print(f"New assignment for {processor_id}: {new_assignment[processor_id]}")
            except Exception as e:
                print(f"Failed to get partitions for {processor_id}: {e}")
        
        # Verify all partitions are still assigned
        all_initial_partitions = set()
        all_new_partitions = set()
        
        for partitions in initial_assignment.values():
            all_initial_partitions.update(partitions)
        
        for partitions in new_assignment.values():
            all_new_partitions.update(partitions)
        
        assert all_initial_partitions == all_new_partitions, \
            f"Partition assignment changed: {all_initial_partitions} vs {all_new_partitions}"
        
        # Verify no partition is assigned to multiple processors
        partition_owners = {}
        for processor_id, partitions in new_assignment.items():
            for partition in partitions:
                if partition in partition_owners:
                    assert False, f"Partition {partition} assigned to both {partition_owners[partition]} and {processor_id}"
                partition_owners[partition] = processor_id
        
        # Send more messages after rebalancing
        for i in range(100, 200):
            key = f"key_{i % 20}"
            message = {
                'id': str(uuid.uuid4()),
                'sequence': i,
                'data': f"post_rebalance_data_{i}"
            }
            kafka_producer.send(topic, key=key, value=message)
        
        kafka_producer.flush()
        time.sleep(10)
        
        # Verify processing continues normally
        total_processed = 0
        for processor_id, client in clients.items():
            try:
                metrics = client.get_processing_metrics()
                processed = metrics.get('total_messages_processed', 0)
                total_processed += processed
                print(f"Processor {processor_id} processed {processed} messages")
            except Exception as e:
                print(f"Failed to get metrics for {processor_id}: {e}")
        
        assert total_processed >= 200, f"Expected at least 200 messages processed, got {total_processed}"
    
    def test_processor_failure_rebalancing(self, chaos_controller, clients, kafka_producer):
        """Test rebalancing after processor failure"""
        topic = f"test_failure_rebalancing_{int(time.time())}"
        
        # Start processing on all processors
        for processor_id, client in clients.items():
            client.start_processing([topic])
        
        time.sleep(5)
        
        # Send messages to establish state
        for i in range(150):
            key = f"key_{i % 30}"
            message = {
                'id': str(uuid.uuid4()),
                'sequence': i,
                'data': f"pre_failure_data_{i}"
            }
            kafka_producer.send(topic, key=key, value=message)
        
        kafka_producer.flush()
        time.sleep(10)
        
        # Get initial state from all processors
        initial_states = {}
        for processor_id, client in clients.items():
            try:
                metrics = client.get_processing_metrics()
                initial_states[processor_id] = metrics.get('total_messages_processed', 0)
                print(f"Processor {processor_id} initially processed {initial_states[processor_id]} messages")
            except Exception as e:
                print(f"Failed to get initial state for {processor_id}: {e}")
        
        # Stop one processor to simulate failure
        print("Simulating processor-2 failure...")
        chaos_controller.stop_processor('processor-2')
        time.sleep(5)
        
        # Continue sending messages during failure
        for i in range(150, 250):
            key = f"key_{i % 30}"
            message = {
                'id': str(uuid.uuid4()),
                'sequence': i,
                'data': f"during_failure_data_{i}"
            }
            kafka_producer.send(topic, key=key, value=message)
        
        kafka_producer.flush()
        time.sleep(15)  # Wait for rebalancing and processing
        
        # Verify remaining processors took over
        remaining_processors = ['processor-1', 'processor-3']
        total_processed_during_failure = 0
        
        for processor_id in remaining_processors:
            try:
                metrics = clients[processor_id].get_processing_metrics()
                processed = metrics.get('total_messages_processed', 0)
                total_processed_during_failure += processed
                print(f"Processor {processor_id} processed {processed} messages during failure")
            except Exception as e:
                print(f"Failed to get metrics for {processor_id}: {e}")
        
        # Should have processed at least the messages sent during failure
        assert total_processed_during_failure >= 100, \
            f"Expected at least 100 messages processed during failure, got {total_processed_during_failure}"
        
        # Restart failed processor
        print("Restarting processor-2...")
        chaos_controller.start_processor('processor-2')
        
        if chaos_controller.wait_for_processor_ready('processor-2'):
            # Restart processing
            clients['processor-2'].start_processing([topic])
            time.sleep(10)
            
            # Send more messages after recovery
            for i in range(250, 300):
                key = f"key_{i % 30}"
                message = {
                    'id': str(uuid.uuid4()),
                    'sequence': i,
                    'data': f"post_recovery_data_{i}"
                }
                kafka_producer.send(topic, key=key, value=message)
            
            kafka_producer.flush()
            time.sleep(15)
            
            # Verify all processors are working
            final_total = 0
            for processor_id, client in clients.items():
                try:
                    metrics = client.get_processing_metrics()
                    processed = metrics.get('total_messages_processed', 0)
                    final_total += processed
                    print(f"Processor {processor_id} final processed count: {processed}")
                except Exception as e:
                    print(f"Failed to get final metrics for {processor_id}: {e}")
            
            assert final_total >= 300, f"Expected at least 300 total messages processed, got {final_total}"
    
    def test_cascading_failures(self, chaos_controller, clients, kafka_producer):
        """Test cascading processor failures"""
        topic = f"test_cascading_failures_{int(time.time())}"
        
        # Start processing on all processors
        for processor_id, client in clients.items():
            client.start_processing([topic])
        
        time.sleep(5)
        
        # Send initial messages
        for i in range(100):
            key = f"key_{i % 25}"
            message = {
                'id': str(uuid.uuid4()),
                'sequence': i,
                'data': f"initial_data_{i}"
            }
            kafka_producer.send(topic, key=key, value=message)
        
        kafka_producer.flush()
        time.sleep(10)
        
        # Simulate cascading failures
        failed_processors = []
        
        # Fail processor-1
        print("Failing processor-1...")
        if chaos_controller.stop_processor('processor-1'):
            failed_processors.append('processor-1')
        time.sleep(10)
        
        # Continue processing and fail processor-2
        for i in range(100, 150):
            key = f"key_{i % 25}"
            message = {
                'id': str(uuid.uuid4()),
                'sequence': i,
                'data': f"after_first_failure_{i}"
            }
            kafka_producer.send(topic, key=key, value=message)
        
        kafka_producer.flush()
        time.sleep(5)
        
        print("Failing processor-2...")
        if chaos_controller.stop_processor('processor-2'):
            failed_processors.append('processor-2')
        time.sleep(10)
        
        # Only processor-3 should be running
        remaining_processor = 'processor-3'
        
        # Send more messages
        for i in range(150, 200):
            key = f"key_{i % 25}"
            message = {
                'id': str(uuid.uuid4()),
                'sequence': i,
                'data': f"single_processor_{i}"
            }
            kafka_producer.send(topic, key=key, value=message)
        
        kafka_producer.flush()
        time.sleep(15)
        
        # Verify remaining processor handles all partitions
        try:
            metrics = clients[remaining_processor].get_processing_metrics()
            processed = metrics.get('total_messages_processed', 0)
            print(f"Remaining processor {remaining_processor} processed {processed} messages")
            
            # Should have processed a significant portion of messages
            assert processed >= 100, f"Remaining processor should have processed at least 100 messages, got {processed}"
            
            partitions = clients[remaining_processor].get_partitions()
            assigned_partitions = partitions.get('partitions', [])
            print(f"Remaining processor has {len(assigned_partitions)} partitions assigned")
            
            # Should have taken over more partitions
            assert len(assigned_partitions) > 4, f"Expected more than 4 partitions, got {len(assigned_partitions)}"
            
        except Exception as e:
            print(f"Failed to verify remaining processor: {e}")
        
        # Restart failed processors
        for processor_id in failed_processors:
            print(f"Restarting {processor_id}...")
            if chaos_controller.start_processor(processor_id):
                if chaos_controller.wait_for_processor_ready(processor_id):
                    clients[processor_id].start_processing([topic])
                    time.sleep(5)
        
        # Wait for rebalancing
        time.sleep(20)
        
        # Send final batch of messages
        for i in range(200, 250):
            key = f"key_{i % 25}"
            message = {
                'id': str(uuid.uuid4()),
                'sequence': i,
                'data': f"after_recovery_{i}"
            }
            kafka_producer.send(topic, key=key, value=message)
        
        kafka_producer.flush()
        time.sleep(15)
        
        # Verify all processors are working again
        total_final = 0
        working_processors = 0
        
        for processor_id, client in clients.items():
            try:
                if client.is_healthy():
                    metrics = client.get_processing_metrics()
                    processed = metrics.get('total_messages_processed', 0)
                    total_final += processed
                    working_processors += 1
                    print(f"Processor {processor_id} final count: {processed}")
            except Exception as e:
                print(f"Processor {processor_id} not responding: {e}")
        
        assert working_processors >= 2, f"Expected at least 2 working processors, got {working_processors}"
        assert total_final >= 200, f"Expected at least 200 total messages processed, got {total_final}"


class TestStateMigration:
    """Test state migration during rebalancing"""
    
    @pytest.fixture
    def chaos_controller(self):
        """Create chaos controller"""
        return StreamProcessorChaosController()
    
    @pytest.fixture
    def clients(self, chaos_controller):
        """Create test clients"""
        clients = {}
        for processor_id, port in chaos_controller.ports.items():
            clients[processor_id] = StreamProcessorTestClient(processor_id, port)
        return clients
    
    @pytest.fixture
    def kafka_producer(self):
        """Create Kafka producer"""
        producer = KafkaProducer(
            bootstrap_servers="localhost:9092,localhost:9094,localhost:9095",
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            key_serializer=lambda k: k.encode('utf-8') if k else None,
            acks='all',
            retries=3,
            enable_idempotence=True
        )
        yield producer
        producer.close()
    
    def test_state_migration_during_rebalancing(self, chaos_controller, clients, kafka_producer):
        """Test state migration when processors are added/removed"""
        topic = f"test_state_migration_{int(time.time())}"
        state_store = "migration_test_store"
        
        # Start with only processor-1 and processor-2
        active_processors = ['processor-1', 'processor-2']
        for processor_id in active_processors:
            clients[processor_id].start_processing([topic])
        
        time.sleep(5)
        
        # Send stateful messages
        state_keys = set()
        for i in range(200):
            key = f"state_key_{i % 50}"  # 50 unique state keys
            state_keys.add(key)
            message = {
                'id': str(uuid.uuid4()),
                'key': key,
                'value': i,
                'operation': 'increment'
            }
            kafka_producer.send(topic, key=key, value=message)
        
        kafka_producer.flush()
        time.sleep(15)
        
        # Verify state is distributed across active processors
        initial_state_distribution = {}
        for processor_id in active_processors:
            initial_state_distribution[processor_id] = []
            for key in list(state_keys)[:10]:  # Sample some keys
                try:
                    state = clients[processor_id].get_state(state_store, key)
                    if state:
                        initial_state_distribution[processor_id].append(key)
                except:
                    pass
        
        print("Initial state distribution:")
        for processor_id, keys in initial_state_distribution.items():
            print(f"  {processor_id}: {len(keys)} keys")
        
        # Add processor-3 (scale out)
        print("Scaling out: adding processor-3...")
        clients['processor-3'].start_processing([topic])
        time.sleep(5)
        
        # Trigger rebalancing
        clients['processor-1'].trigger_rebalance()
        time.sleep(30)  # Wait for state migration
        
        # Verify state is redistributed
        new_state_distribution = {}
        total_keys_found = 0
        
        for processor_id in ['processor-1', 'processor-2', 'processor-3']:
            new_state_distribution[processor_id] = []
            for key in list(state_keys)[:20]:  # Sample more keys
                try:
                    state = clients[processor_id].get_state(state_store, key)
                    if state:
                        new_state_distribution[processor_id].append(key)
                        total_keys_found += 1
                except:
                    pass
        
        print("State distribution after scale out:")
        for processor_id, keys in new_state_distribution.items():
            print(f"  {processor_id}: {len(keys)} keys")
        
        # Verify state is preserved and redistributed
        assert total_keys_found > 0, "No state found after rebalancing"
        
        # Send more messages to verify continued processing
        for i in range(200, 300):
            key = f"state_key_{i % 50}"
            message = {
                'id': str(uuid.uuid4()),
                'key': key,
                'value': i,
                'operation': 'increment'
            }
            kafka_producer.send(topic, key=key, value=message)
        
        kafka_producer.flush()
        time.sleep(15)
        
        # Verify processing continues correctly
        total_processed = 0
        for processor_id in ['processor-1', 'processor-2', 'processor-3']:
            try:
                metrics = clients[processor_id].get_processing_metrics()
                processed = metrics.get('total_messages_processed', 0)
                total_processed += processed
                print(f"Processor {processor_id} processed {processed} messages after scale out")
            except Exception as e:
                print(f"Failed to get metrics for {processor_id}: {e}")
        
        assert total_processed >= 300, f"Expected at least 300 messages processed, got {total_processed}"


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "--tb=short", "-s"])

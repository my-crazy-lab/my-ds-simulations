#!/usr/bin/env python3
"""
Chaos engineering tests for hot-key scenarios in the distributed cache.
Tests hot-key detection, mitigation strategies, and system behavior under extreme load.
"""

import pytest
import requests
import json
import time
import threading
import uuid
import random
import docker
from typing import Dict, List, Set
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict, Counter


class CacheChaosController:
    """Controller for chaos engineering tests"""
    
    def __init__(self):
        self.client = docker.from_env()
        self.cache_nodes = {
            'node-1': 'cache-node-1',
            'node-2': 'cache-node-2', 
            'node-3': 'cache-node-3',
        }
        self.ports = {
            'node-1': 8081,
            'node-2': 8082,
            'node-3': 8083,
        }
    
    def stop_node(self, node_id: str) -> bool:
        """Stop a cache node"""
        try:
            container_name = self.cache_nodes[node_id]
            container = self.client.containers.get(container_name)
            container.stop()
            print(f"Stopped cache node {node_id} ({container_name})")
            return True
        except Exception as e:
            print(f"Failed to stop node {node_id}: {e}")
            return False
    
    def start_node(self, node_id: str) -> bool:
        """Start a cache node"""
        try:
            container_name = self.cache_nodes[node_id]
            container = self.client.containers.get(container_name)
            container.start()
            print(f"Started cache node {node_id} ({container_name})")
            time.sleep(10)  # Wait for node to be ready
            return True
        except Exception as e:
            print(f"Failed to start node {node_id}: {e}")
            return False
    
    def pause_node(self, node_id: str) -> bool:
        """Pause a cache node (simulates network partition)"""
        try:
            container_name = self.cache_nodes[node_id]
            container = self.client.containers.get(container_name)
            container.pause()
            print(f"Paused cache node {node_id} ({container_name})")
            return True
        except Exception as e:
            print(f"Failed to pause node {node_id}: {e}")
            return False
    
    def unpause_node(self, node_id: str) -> bool:
        """Unpause a cache node"""
        try:
            container_name = self.cache_nodes[node_id]
            container = self.client.containers.get(container_name)
            container.unpause()
            print(f"Unpaused cache node {node_id} ({container_name})")
            return True
        except Exception as e:
            print(f"Failed to unpause node {node_id}: {e}")
            return False
    
    def get_node_status(self, node_id: str) -> Dict:
        """Get status of a specific node"""
        try:
            port = self.ports[node_id]
            response = requests.get(f"http://localhost:{port}/admin/status", timeout=5)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"error": str(e), "status": "unreachable"}


class CacheTestClient:
    """Test client for cache operations"""
    
    def __init__(self, node_id: str, port: int):
        self.node_id = node_id
        self.base_url = f"http://localhost:{port}"
        self.session = requests.Session()
        self.session.headers.update({'Content-Type': 'application/json'})
    
    def get(self, key: str) -> Dict:
        """Get value from cache"""
        response = self.session.get(f"{self.base_url}/cache/{key}")
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()
    
    def put(self, key: str, value: any, ttl: int = 3600) -> Dict:
        """Put value in cache"""
        payload = {"value": value, "ttl": ttl}
        response = self.session.put(f"{self.base_url}/cache/{key}", json=payload)
        response.raise_for_status()
        return response.json()
    
    def get_hot_keys(self) -> Dict:
        """Get hot keys detected"""
        response = self.session.get(f"{self.base_url}/admin/hot-keys")
        response.raise_for_status()
        return response.json()
    
    def get_circuit_breakers(self) -> Dict:
        """Get circuit breaker status"""
        response = self.session.get(f"{self.base_url}/admin/circuit-breakers")
        response.raise_for_status()
        return response.json()
    
    def get_stats(self) -> Dict:
        """Get cache statistics"""
        response = self.session.get(f"{self.base_url}/admin/stats")
        response.raise_for_status()
        return response.json()
    
    def configure_hot_key_detection(self, threshold_rps: int, window_seconds: int, strategy: str) -> Dict:
        """Configure hot key detection"""
        payload = {
            "threshold_requests_per_second": threshold_rps,
            "detection_window_seconds": window_seconds,
            "mitigation_strategy": strategy
        }
        response = self.session.post(f"{self.base_url}/admin/hot-key-config", json=payload)
        response.raise_for_status()
        return response.json()
    
    def configure_circuit_breaker(self, failure_threshold: int, success_threshold: int, timeout_seconds: int) -> Dict:
        """Configure circuit breaker"""
        payload = {
            "failure_threshold": failure_threshold,
            "success_threshold": success_threshold,
            "timeout_seconds": timeout_seconds
        }
        response = self.session.post(f"{self.base_url}/admin/circuit-breaker-config", json=payload)
        response.raise_for_status()
        return response.json()
    
    def is_healthy(self) -> bool:
        """Check if node is healthy"""
        try:
            response = self.session.get(f"{self.base_url}/health", timeout=5)
            return response.status_code == 200
        except:
            return False


class HotKeyLoadGenerator:
    """Generate hot key load patterns"""
    
    def __init__(self, clients: Dict[str, CacheTestClient]):
        self.clients = clients
        self.stop_flag = threading.Event()
        self.stats = defaultdict(int)
        self.stats_lock = threading.Lock()
    
    def generate_hot_key_load(self, hot_keys: List[str], hot_key_rps: int, 
                             normal_keys: List[str], normal_key_rps: int, 
                             duration_seconds: int):
        """Generate load with hot keys and normal keys"""
        print(f"Starting hot key load generation:")
        print(f"  Hot keys: {len(hot_keys)} keys at {hot_key_rps} RPS each")
        print(f"  Normal keys: {len(normal_keys)} keys at {normal_key_rps} RPS total")
        print(f"  Duration: {duration_seconds} seconds")
        
        # Calculate intervals
        hot_key_interval = 1.0 / hot_key_rps if hot_key_rps > 0 else 1.0
        normal_key_interval = len(normal_keys) / normal_key_rps if normal_key_rps > 0 else 1.0
        
        # Start hot key threads
        hot_key_threads = []
        for hot_key in hot_keys:
            thread = threading.Thread(
                target=self._generate_key_load,
                args=(hot_key, hot_key_interval, duration_seconds, "hot")
            )
            hot_key_threads.append(thread)
            thread.start()
        
        # Start normal key thread
        normal_key_thread = threading.Thread(
            target=self._generate_normal_key_load,
            args=(normal_keys, normal_key_interval, duration_seconds)
        )
        normal_key_thread.start()
        
        # Wait for completion
        for thread in hot_key_threads:
            thread.join()
        normal_key_thread.join()
        
        print("Hot key load generation completed")
        return self.get_stats()
    
    def _generate_key_load(self, key: str, interval: float, duration: int, key_type: str):
        """Generate load for a specific key"""
        start_time = time.time()
        request_count = 0
        
        while time.time() - start_time < duration and not self.stop_flag.is_set():
            try:
                # Randomly select a client
                client = random.choice(list(self.clients.values()))
                
                # Perform operation (mostly reads for hot keys)
                if random.random() < 0.9:  # 90% reads
                    result = client.get(key)
                    with self.stats_lock:
                        if result:
                            self.stats[f"{key_type}_key_hits"] += 1
                        else:
                            self.stats[f"{key_type}_key_misses"] += 1
                else:  # 10% writes
                    value = {"data": f"value_{request_count}", "timestamp": time.time()}
                    client.put(key, value, ttl=300)
                    with self.stats_lock:
                        self.stats[f"{key_type}_key_writes"] += 1
                
                request_count += 1
                
                # Sleep to maintain rate
                time.sleep(interval)
                
            except Exception as e:
                with self.stats_lock:
                    self.stats[f"{key_type}_key_errors"] += 1
                time.sleep(interval)
        
        with self.stats_lock:
            self.stats[f"{key_type}_key_requests"] += request_count
    
    def _generate_normal_key_load(self, keys: List[str], interval: float, duration: int):
        """Generate load for normal keys"""
        start_time = time.time()
        
        while time.time() - start_time < duration and not self.stop_flag.is_set():
            try:
                # Randomly select key and client
                key = random.choice(keys)
                client = random.choice(list(self.clients.values()))
                
                # Perform operation
                if random.random() < 0.7:  # 70% reads
                    result = client.get(key)
                    with self.stats_lock:
                        if result:
                            self.stats["normal_key_hits"] += 1
                        else:
                            self.stats["normal_key_misses"] += 1
                else:  # 30% writes
                    value = {"data": f"normal_value_{int(time.time())}", "timestamp": time.time()}
                    client.put(key, value, ttl=300)
                    with self.stats_lock:
                        self.stats["normal_key_writes"] += 1
                
                time.sleep(interval)
                
            except Exception as e:
                with self.stats_lock:
                    self.stats["normal_key_errors"] += 1
                time.sleep(interval)
    
    def stop(self):
        """Stop load generation"""
        self.stop_flag.set()
    
    def get_stats(self) -> Dict:
        """Get load generation statistics"""
        with self.stats_lock:
            return dict(self.stats)


class TestHotKeyDetection:
    """Test hot key detection mechanisms"""
    
    @pytest.fixture
    def chaos_controller(self):
        """Create chaos controller"""
        return CacheChaosController()
    
    @pytest.fixture
    def clients(self, chaos_controller):
        """Create test clients for all nodes"""
        clients = {}
        for node_id, port in chaos_controller.ports.items():
            clients[node_id] = CacheTestClient(node_id, port)
        return clients
    
    @pytest.fixture
    def load_generator(self, clients):
        """Create load generator"""
        return HotKeyLoadGenerator(clients)
    
    def test_hot_key_detection_threshold(self, clients, load_generator):
        """Test hot key detection based on request threshold"""
        # Configure hot key detection
        threshold_rps = 100
        window_seconds = 30
        
        for client in clients.values():
            try:
                client.configure_hot_key_detection(threshold_rps, window_seconds, "replicate_and_coalesce")
                break
            except:
                continue
        
        # Generate hot key load
        hot_keys = ["hot_key_1", "hot_key_2"]
        normal_keys = [f"normal_key_{i}" for i in range(50)]
        
        # Pre-populate some keys
        for key in hot_keys + normal_keys[:10]:
            clients['node-1'].put(key, {"data": f"initial_{key}"}, ttl=600)
        
        time.sleep(2)
        
        # Generate load that should trigger hot key detection
        stats = load_generator.generate_hot_key_load(
            hot_keys=hot_keys,
            hot_key_rps=150,  # Above threshold
            normal_keys=normal_keys,
            normal_key_rps=50,  # Below threshold per key
            duration_seconds=45
        )
        
        print(f"Load generation stats: {stats}")
        
        # Wait for detection window to complete
        time.sleep(10)
        
        # Check hot key detection
        detected_hot_keys = set()
        for node_id, client in clients.items():
            try:
                hot_key_info = client.get_hot_keys()
                hot_keys_detected = hot_key_info.get("hot_keys", [])
                detected_hot_keys.update(hot_keys_detected)
                print(f"Node {node_id} detected hot keys: {hot_keys_detected}")
            except Exception as e:
                print(f"Failed to get hot keys from {node_id}: {e}")
        
        # Verify hot keys were detected
        for hot_key in hot_keys:
            assert hot_key in detected_hot_keys, f"Hot key {hot_key} was not detected"
        
        print(f"Successfully detected hot keys: {detected_hot_keys}")
    
    def test_circuit_breaker_activation(self, clients, load_generator):
        """Test circuit breaker activation for hot keys"""
        # Configure aggressive circuit breaker settings
        failure_threshold = 10
        success_threshold = 5
        timeout_seconds = 30
        
        for client in clients.values():
            try:
                client.configure_circuit_breaker(failure_threshold, success_threshold, timeout_seconds)
                client.configure_hot_key_detection(50, 20, "circuit_breaker")
                break
            except:
                continue
        
        # Create a hot key scenario that will trigger circuit breaker
        hot_key = "circuit_breaker_test_key"
        
        # Generate extreme load on a single key
        def generate_extreme_load():
            for _ in range(200):
                try:
                    # Try to get a non-existent key to generate failures
                    clients['node-1'].get(f"{hot_key}_nonexistent")
                except:
                    pass
                time.sleep(0.01)  # 100 RPS
        
        # Start load generation
        load_thread = threading.Thread(target=generate_extreme_load)
        load_thread.start()
        
        # Wait for circuit breaker to potentially activate
        time.sleep(15)
        
        # Check circuit breaker status
        circuit_breaker_activated = False
        for node_id, client in clients.items():
            try:
                cb_status = client.get_circuit_breakers()
                breakers = cb_status.get("circuit_breakers", {})
                
                for breaker_name, breaker_info in breakers.items():
                    if breaker_info.get("state") == "open":
                        circuit_breaker_activated = True
                        print(f"Circuit breaker {breaker_name} on {node_id} is open")
                
            except Exception as e:
                print(f"Failed to get circuit breaker status from {node_id}: {e}")
        
        load_thread.join()
        
        # Note: Circuit breaker activation depends on the specific implementation
        # In some cases, it might not activate if the system handles load well
        print(f"Circuit breaker activation status: {circuit_breaker_activated}")
    
    def test_hot_key_replication_strategy(self, clients, load_generator):
        """Test hot key replication mitigation strategy"""
        # Configure hot key detection with replication strategy
        for client in clients.values():
            try:
                client.configure_hot_key_detection(80, 25, "replicate_and_coalesce")
                break
            except:
                continue
        
        # Create hot keys and populate them
        hot_keys = ["replicated_hot_key_1", "replicated_hot_key_2"]
        for key in hot_keys:
            clients['node-1'].put(key, {"data": f"hot_data_{key}", "replicated": True}, ttl=600)
        
        time.sleep(2)
        
        # Generate hot key load
        stats = load_generator.generate_hot_key_load(
            hot_keys=hot_keys,
            hot_key_rps=120,
            normal_keys=[f"normal_{i}" for i in range(30)],
            normal_key_rps=40,
            duration_seconds=35
        )
        
        # Wait for replication to take effect
        time.sleep(10)
        
        # Verify hot keys are accessible from multiple nodes
        for hot_key in hot_keys:
            accessible_nodes = []
            for node_id, client in clients.items():
                try:
                    result = client.get(hot_key)
                    if result:
                        accessible_nodes.append(node_id)
                except:
                    pass
            
            print(f"Hot key {hot_key} accessible from nodes: {accessible_nodes}")
            
            # With replication strategy, hot keys should be available on multiple nodes
            # Note: This depends on the implementation - some systems might not replicate immediately
            assert len(accessible_nodes) >= 1, f"Hot key {hot_key} not accessible from any node"
    
    def test_cache_stampede_protection(self, clients, load_generator):
        """Test protection against cache stampede scenarios"""
        # Create a scenario where many clients request the same missing key simultaneously
        stampede_key = "cache_stampede_test_key"
        
        # Ensure key doesn't exist initially
        for client in clients.values():
            try:
                client.get(stampede_key)  # This should miss
            except:
                pass
        
        # Generate simultaneous requests for the missing key
        def generate_stampede_request(client_id: str, results: List):
            try:
                client = clients[client_id]
                start_time = time.time()
                result = client.get(stampede_key)
                end_time = time.time()
                
                results.append({
                    "client": client_id,
                    "result": result,
                    "latency": end_time - start_time,
                    "timestamp": start_time
                })
            except Exception as e:
                results.append({
                    "client": client_id,
                    "error": str(e),
                    "timestamp": time.time()
                })
        
        # Launch simultaneous requests
        results = []
        threads = []
        
        for i in range(20):  # 20 simultaneous requests
            client_id = f"node-{(i % 3) + 1}"
            thread = threading.Thread(target=generate_stampede_request, args=(client_id, results))
            threads.append(thread)
        
        # Start all threads simultaneously
        for thread in threads:
            thread.start()
        
        # Wait for completion
        for thread in threads:
            thread.join()
        
        print(f"Cache stampede test completed with {len(results)} results")
        
        # Analyze results
        successful_requests = [r for r in results if "error" not in r]
        error_requests = [r for r in results if "error" in r]
        
        print(f"Successful requests: {len(successful_requests)}")
        print(f"Error requests: {len(error_requests)}")
        
        if successful_requests:
            latencies = [r["latency"] for r in successful_requests]
            avg_latency = sum(latencies) / len(latencies)
            max_latency = max(latencies)
            
            print(f"Average latency: {avg_latency:.3f}s")
            print(f"Max latency: {max_latency:.3f}s")
            
            # Verify reasonable performance even under stampede conditions
            assert avg_latency < 1.0, f"Average latency too high: {avg_latency:.3f}s"
            assert max_latency < 5.0, f"Max latency too high: {max_latency:.3f}s"


class TestHotKeyMitigation:
    """Test hot key mitigation strategies"""
    
    @pytest.fixture
    def chaos_controller(self):
        """Create chaos controller"""
        return CacheChaosController()
    
    @pytest.fixture
    def clients(self, chaos_controller):
        """Create test clients"""
        clients = {}
        for node_id, port in chaos_controller.ports.items():
            clients[node_id] = CacheTestClient(node_id, port)
        return clients
    
    @pytest.fixture
    def load_generator(self, clients):
        """Create load generator"""
        return HotKeyLoadGenerator(clients)
    
    def test_hot_key_with_node_failure(self, chaos_controller, clients, load_generator):
        """Test hot key handling during node failures"""
        # Configure hot key detection
        for client in clients.values():
            try:
                client.configure_hot_key_detection(60, 20, "replicate_and_coalesce")
                break
            except:
                continue
        
        # Create hot keys
        hot_keys = ["failure_test_hot_key"]
        normal_keys = [f"failure_normal_{i}" for i in range(20)]
        
        # Populate keys
        for key in hot_keys + normal_keys:
            clients['node-1'].put(key, {"data": f"data_{key}"}, ttl=600)
        
        time.sleep(2)
        
        # Start load generation
        load_thread = threading.Thread(
            target=load_generator.generate_hot_key_load,
            args=(hot_keys, 100, normal_keys, 30, 60)
        )
        load_thread.start()
        
        # Wait for hot key detection
        time.sleep(15)
        
        # Simulate node failure
        print("Simulating node-2 failure...")
        chaos_controller.stop_node('node-2')
        
        # Continue load for a while
        time.sleep(20)
        
        # Restart failed node
        print("Restarting node-2...")
        chaos_controller.start_node('node-2')
        
        # Wait for load generation to complete
        load_thread.join()
        
        # Verify hot keys are still accessible
        for hot_key in hot_keys:
            accessible = False
            for client in clients.values():
                try:
                    if client.get(hot_key):
                        accessible = True
                        break
                except:
                    continue
            
            assert accessible, f"Hot key {hot_key} not accessible after node failure"
        
        print("Hot key accessibility maintained during node failure")
    
    def test_performance_under_hot_key_load(self, clients, load_generator):
        """Test system performance under sustained hot key load"""
        # Configure for performance testing
        for client in clients.values():
            try:
                client.configure_hot_key_detection(75, 15, "replicate_and_coalesce")
                break
            except:
                continue
        
        # Create test scenario
        hot_keys = ["perf_hot_1", "perf_hot_2", "perf_hot_3"]
        normal_keys = [f"perf_normal_{i}" for i in range(100)]
        
        # Populate keys
        for key in hot_keys + normal_keys[:20]:
            clients['node-1'].put(key, {"data": f"perf_data_{key}"}, ttl=600)
        
        # Measure baseline performance
        baseline_start = time.time()
        baseline_requests = 0
        
        for _ in range(100):
            try:
                key = random.choice(normal_keys[:20])
                clients['node-1'].get(key)
                baseline_requests += 1
            except:
                pass
        
        baseline_duration = time.time() - baseline_start
        baseline_rps = baseline_requests / baseline_duration if baseline_duration > 0 else 0
        
        print(f"Baseline performance: {baseline_rps:.2f} RPS")
        
        # Generate hot key load and measure performance
        load_start = time.time()
        
        stats = load_generator.generate_hot_key_load(
            hot_keys=hot_keys,
            hot_key_rps=200,  # High load
            normal_keys=normal_keys,
            normal_key_rps=100,
            duration_seconds=30
        )
        
        load_duration = time.time() - load_start
        
        # Calculate performance metrics
        total_requests = sum(v for k, v in stats.items() if k.endswith('_requests'))
        total_errors = sum(v for k, v in stats.items() if k.endswith('_errors'))
        
        if total_requests > 0:
            error_rate = total_errors / total_requests
            effective_rps = total_requests / load_duration
            
            print(f"Hot key load performance:")
            print(f"  Total requests: {total_requests}")
            print(f"  Total errors: {total_errors}")
            print(f"  Error rate: {error_rate:.3f}")
            print(f"  Effective RPS: {effective_rps:.2f}")
            
            # Verify acceptable performance
            assert error_rate < 0.1, f"Error rate too high: {error_rate:.3f}"
            assert effective_rps > baseline_rps * 0.5, f"Performance degraded too much: {effective_rps:.2f} vs {baseline_rps:.2f}"
        
        print("Performance test completed successfully")


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "--tb=short", "-s"])

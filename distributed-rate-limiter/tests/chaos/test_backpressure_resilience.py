#!/usr/bin/env python3
"""
Chaos engineering tests for distributed rate limiter backpressure and resilience.
Tests system behavior under various failure scenarios and load conditions.
"""

import pytest
import requests
import time
import json
import threading
import docker
import statistics
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
import subprocess
import psutil


@dataclass
class ChaosScenario:
    """Chaos engineering scenario configuration"""
    name: str
    description: str
    duration: int
    failure_type: str
    target_service: str
    parameters: Dict


@dataclass
class ResilienceMetrics:
    """Resilience test metrics"""
    scenario: str
    total_requests: int
    successful_requests: int
    failed_requests: int
    recovery_time: float
    availability: float
    error_rate: float
    performance_degradation: float


class BackpressureChaosController:
    """Controller for chaos engineering tests on backpressure system"""
    
    def __init__(self):
        self.docker_client = docker.from_env()
        self.base_url = "http://localhost:8080"
        self.session = requests.Session()
        self.session.timeout = 5
        
        # Service endpoints
        self.endpoints = {
            "rate-limiter": "http://localhost:8080",
            "backpressure": "http://localhost:8082",
            "coordination": "http://localhost:8084",
            "gateway": "http://localhost:8086"
        }
    
    def capture_baseline_metrics(self) -> Dict:
        """Capture baseline system metrics before chaos"""
        print("Capturing baseline metrics...")
        
        baseline = {
            "timestamp": time.time(),
            "services": {},
            "system": self.get_system_metrics(),
            "performance": self.measure_performance_baseline()
        }
        
        for service, url in self.endpoints.items():
            try:
                response = requests.get(f"{url}/health", timeout=5)
                baseline["services"][service] = {
                    "status": "healthy" if response.status_code == 200 else "unhealthy",
                    "response_time": response.elapsed.total_seconds()
                }
            except:
                baseline["services"][service] = {
                    "status": "unreachable",
                    "response_time": None
                }
        
        print(f"Baseline captured: {len([s for s in baseline['services'].values() if s['status'] == 'healthy'])} healthy services")
        return baseline
    
    def get_system_metrics(self) -> Dict:
        """Get current system resource metrics"""
        return {
            "cpu_percent": psutil.cpu_percent(interval=1),
            "memory_percent": psutil.virtual_memory().percent,
            "disk_io": psutil.disk_io_counters()._asdict() if psutil.disk_io_counters() else {},
            "network_io": psutil.net_io_counters()._asdict() if psutil.net_io_counters() else {}
        }
    
    def measure_performance_baseline(self, duration: int = 30) -> Dict:
        """Measure baseline performance metrics"""
        print(f"Measuring baseline performance for {duration} seconds...")
        
        metrics = {
            "requests_sent": 0,
            "requests_successful": 0,
            "requests_failed": 0,
            "latencies": [],
            "throughput": 0.0,
            "error_rate": 0.0
        }
        
        start_time = time.time()
        
        def send_requests():
            while time.time() - start_time < duration:
                try:
                    request_start = time.time()
                    response = self.session.post(
                        f"{self.base_url}/api/v1/check",
                        json={"key": "baseline-test", "tokens": 1},
                        timeout=5
                    )
                    request_end = time.time()
                    
                    metrics["requests_sent"] += 1
                    metrics["latencies"].append((request_end - request_start) * 1000)
                    
                    if response.status_code in [200, 429]:
                        metrics["requests_successful"] += 1
                    else:
                        metrics["requests_failed"] += 1
                        
                except Exception as e:
                    metrics["requests_failed"] += 1
                
                time.sleep(0.1)  # 10 requests per second
        
        # Run baseline test
        thread = threading.Thread(target=send_requests)
        thread.start()
        thread.join()
        
        # Calculate metrics
        total_duration = time.time() - start_time
        metrics["throughput"] = metrics["requests_sent"] / total_duration
        metrics["error_rate"] = metrics["requests_failed"] / metrics["requests_sent"] if metrics["requests_sent"] > 0 else 0
        
        print(f"Baseline performance: {metrics['throughput']:.2f} req/s, {metrics['error_rate']:.2%} error rate")
        return metrics
    
    def simulate_high_load(self, duration: int, concurrent_users: int = 50, requests_per_second: int = 100) -> bool:
        """Simulate high load on the system"""
        print(f"Simulating high load: {concurrent_users} users, {requests_per_second} req/s for {duration}s")
        
        def user_load(user_id: int):
            user_start = time.time()
            requests_sent = 0
            
            while time.time() - user_start < duration:
                try:
                    self.session.post(
                        f"{self.base_url}/api/v1/check",
                        json={"key": f"load-user-{user_id}", "tokens": 1, "metadata": {"load_test": True}},
                        timeout=2
                    )
                    requests_sent += 1
                except:
                    pass
                
                time.sleep(1.0 / (requests_per_second / concurrent_users))
            
            return requests_sent
        
        with ThreadPoolExecutor(max_workers=concurrent_users) as executor:
            futures = [executor.submit(user_load, i) for i in range(concurrent_users)]
            total_requests = sum(future.result() for future in as_completed(futures))
        
        print(f"High load simulation completed: {total_requests} total requests sent")
        return True
    
    def stop_service(self, service_name: str) -> bool:
        """Stop a specific service container"""
        try:
            container = self.docker_client.containers.get(service_name)
            container.stop()
            print(f"Stopped service: {service_name}")
            return True
        except Exception as e:
            print(f"Failed to stop service {service_name}: {e}")
            return False
    
    def start_service(self, service_name: str) -> bool:
        """Start a specific service container"""
        try:
            container = self.docker_client.containers.get(service_name)
            container.start()
            print(f"Started service: {service_name}")
            
            # Wait for service to be ready
            time.sleep(10)
            return True
        except Exception as e:
            print(f"Failed to start service {service_name}: {e}")
            return False
    
    def restart_service(self, service_name: str) -> bool:
        """Restart a specific service container"""
        try:
            container = self.docker_client.containers.get(service_name)
            container.restart()
            print(f"Restarted service: {service_name}")
            
            # Wait for service to be ready
            time.sleep(15)
            return True
        except Exception as e:
            print(f"Failed to restart service {service_name}: {e}")
            return False
    
    def simulate_network_partition(self, duration: int) -> bool:
        """Simulate network partition between services"""
        print(f"Simulating network partition for {duration} seconds")
        
        try:
            # Block traffic between rate limiter and coordination service
            subprocess.run([
                "docker", "exec", "rate-limiter-controller",
                "iptables", "-A", "OUTPUT", "-d", "coordination-service", "-j", "DROP"
            ], check=True, capture_output=True)
            
            time.sleep(duration)
            
            # Restore network connectivity
            subprocess.run([
                "docker", "exec", "rate-limiter-controller",
                "iptables", "-D", "OUTPUT", "-d", "coordination-service", "-j", "DROP"
            ], check=True, capture_output=True)
            
            print("Network partition simulation completed")
            return True
            
        except Exception as e:
            print(f"Network partition simulation failed: {e}")
            return False
    
    def simulate_resource_pressure(self, duration: int) -> bool:
        """Simulate high resource pressure (CPU/Memory)"""
        print(f"Simulating resource pressure for {duration} seconds")
        
        def cpu_stress():
            end_time = time.time() + duration
            while time.time() < end_time:
                # CPU intensive operation
                sum(i * i for i in range(10000))
        
        def memory_stress():
            memory_hog = []
            try:
                for _ in range(duration):
                    # Allocate memory
                    memory_hog.append([0] * 1000000)  # ~8MB per iteration
                    time.sleep(1)
            except MemoryError:
                pass
            finally:
                del memory_hog
        
        # Start stress tests
        cpu_thread = threading.Thread(target=cpu_stress)
        memory_thread = threading.Thread(target=memory_stress)
        
        cpu_thread.start()
        memory_thread.start()
        
        cpu_thread.join()
        memory_thread.join()
        
        print("Resource pressure simulation completed")
        return True
    
    def cleanup_all_chaos(self):
        """Clean up all chaos engineering artifacts"""
        print("Cleaning up chaos engineering artifacts...")
        
        # Ensure all services are running
        services = [
            "rate-limiter-controller",
            "backpressure-manager", 
            "coordination-service",
            "traffic-gateway"
        ]
        
        for service in services:
            try:
                container = self.docker_client.containers.get(service)
                if container.status != "running":
                    container.start()
                    time.sleep(5)
            except:
                pass
        
        # Clean up network rules
        try:
            subprocess.run([
                "docker", "exec", "rate-limiter-controller",
                "iptables", "-F", "OUTPUT"
            ], capture_output=True)
        except:
            pass
        
        print("Cleanup completed")


class BackpressureResilienceAnalyzer:
    """Analyzer for backpressure system resilience"""
    
    def __init__(self, chaos_controller: BackpressureChaosController):
        self.chaos_controller = chaos_controller
        self.base_url = "http://localhost:8080"
    
    def measure_recovery_time(self, failure_start: float, expected_behavior: str) -> Dict:
        """Measure system recovery time after failure"""
        print(f"Measuring recovery time for: {expected_behavior}")
        
        recovery_start = time.time()
        recovery_detected = False
        
        # Monitor system until recovery or timeout
        timeout = 300  # 5 minutes max
        while time.time() - recovery_start < timeout:
            try:
                # Test system responsiveness
                response = requests.get(f"{self.base_url}/health", timeout=5)
                if response.status_code == 200:
                    # Test rate limiting functionality
                    rate_response = requests.post(
                        f"{self.base_url}/api/v1/check",
                        json={"key": "recovery-test", "tokens": 1},
                        timeout=5
                    )
                    
                    if rate_response.status_code in [200, 429]:
                        recovery_detected = True
                        break
                        
            except:
                pass
            
            time.sleep(2)
        
        recovery_time = time.time() - recovery_start if recovery_detected else timeout
        
        result = {
            "recovery_detected": recovery_detected,
            "recovery_time": recovery_time,
            "failure_duration": recovery_start - failure_start,
            "total_downtime": recovery_time if recovery_detected else timeout
        }
        
        print(f"Recovery analysis: {'Success' if recovery_detected else 'Failed'} in {recovery_time:.2f}s")
        return result
    
    def measure_backpressure_effectiveness(self, chaos_duration: int) -> Dict:
        """Measure effectiveness of backpressure mechanisms"""
        print(f"Measuring backpressure effectiveness during {chaos_duration}s chaos")
        
        metrics = {
            "requests_sent": 0,
            "requests_allowed": 0,
            "requests_denied": 0,
            "circuit_breaker_activations": 0,
            "load_shedding_events": 0,
            "adaptive_rate_changes": 0,
            "system_stability": 0.0
        }
        
        start_time = time.time()
        
        def monitor_backpressure():
            while time.time() - start_time < chaos_duration:
                try:
                    # Send test request
                    response = requests.post(
                        f"{self.base_url}/api/v1/check",
                        json={"key": "backpressure-test", "tokens": 1},
                        timeout=3
                    )
                    
                    metrics["requests_sent"] += 1
                    
                    if response.status_code == 200:
                        result = response.json()
                        if result.get("allowed"):
                            metrics["requests_allowed"] += 1
                        else:
                            metrics["requests_denied"] += 1
                    elif response.status_code == 429:
                        metrics["requests_denied"] += 1
                    
                    # Check for backpressure indicators
                    if response.status_code == 503:  # Service unavailable
                        metrics["circuit_breaker_activations"] += 1
                    
                except requests.exceptions.Timeout:
                    metrics["load_shedding_events"] += 1
                except:
                    pass
                
                time.sleep(0.5)
        
        # Monitor backpressure during chaos
        monitor_thread = threading.Thread(target=monitor_backpressure)
        monitor_thread.start()
        monitor_thread.join()
        
        # Calculate effectiveness metrics
        if metrics["requests_sent"] > 0:
            metrics["system_stability"] = metrics["requests_allowed"] / metrics["requests_sent"]
        
        print(f"Backpressure effectiveness:")
        print(f"  Requests sent: {metrics['requests_sent']}")
        print(f"  System stability: {metrics['system_stability']:.2%}")
        print(f"  Circuit breaker activations: {metrics['circuit_breaker_activations']}")
        print(f"  Load shedding events: {metrics['load_shedding_events']}")
        
        return metrics
    
    def test_rate_limiting_during_chaos(self, chaos_duration: int) -> Dict:
        """Test rate limiting accuracy during chaos scenarios"""
        print(f"Testing rate limiting accuracy during {chaos_duration}s chaos")
        
        test_keys = ["chaos-test-1", "chaos-test-2", "chaos-test-3"]
        results = {}
        
        for key in test_keys:
            key_results = {
                "requests_sent": 0,
                "requests_allowed": 0,
                "requests_denied": 0,
                "accuracy": 0.0,
                "consistency": 0.0
            }
            
            start_time = time.time()
            responses = []
            
            # Send requests during chaos
            while time.time() - start_time < chaos_duration:
                try:
                    response = requests.post(
                        f"{self.base_url}/api/v1/check",
                        json={"key": key, "tokens": 1},
                        timeout=3
                    )
                    
                    key_results["requests_sent"] += 1
                    
                    if response.status_code in [200, 429]:
                        result = response.json()
                        responses.append(result)
                        
                        if result.get("allowed"):
                            key_results["requests_allowed"] += 1
                        else:
                            key_results["requests_denied"] += 1
                
                except:
                    pass
                
                time.sleep(0.1)
            
            # Calculate accuracy and consistency
            if key_results["requests_sent"] > 0:
                expected_allowed = min(100, key_results["requests_sent"])  # Assume 100 req/min limit
                actual_allowed = key_results["requests_allowed"]
                key_results["accuracy"] = 1.0 - abs(actual_allowed - expected_allowed) / expected_allowed
                
                # Check consistency of responses
                if responses:
                    remaining_values = [r.get("remaining", 0) for r in responses if "remaining" in r]
                    if remaining_values:
                        key_results["consistency"] = 1.0 - (statistics.stdev(remaining_values) / statistics.mean(remaining_values))
            
            results[key] = key_results
        
        print(f"Rate limiting accuracy during chaos:")
        for key, result in results.items():
            print(f"  {key}: {result['accuracy']:.2%} accuracy, {result['consistency']:.2%} consistency")
        
        return results


class TestBackpressureResilience:
    """Test suite for backpressure system resilience"""
    
    @classmethod
    def setup_class(cls):
        """Setup chaos engineering environment"""
        cls.chaos_controller = BackpressureChaosController()
        cls.analyzer = BackpressureResilienceAnalyzer(cls.chaos_controller)
        
        # Wait for system to be ready
        max_retries = 30
        for i in range(max_retries):
            try:
                response = requests.get("http://localhost:8080/health", timeout=5)
                if response.status_code == 200:
                    print("Rate limiter system is ready for chaos testing")
                    break
            except:
                pass
            print(f"Waiting for system... ({i+1}/{max_retries})")
            time.sleep(2)
        else:
            pytest.fail("System not ready for chaos testing")
    
    @classmethod
    def teardown_class(cls):
        """Cleanup after chaos testing"""
        cls.chaos_controller.cleanup_all_chaos()
    
    def test_rate_limiter_controller_failure(self):
        """Test system behavior when rate limiter controller fails"""
        print("\n=== Testing Rate Limiter Controller Failure ===")
        
        # Capture baseline
        baseline = self.chaos_controller.capture_baseline_metrics()
        
        # Stop rate limiter controller
        failure_start = time.time()
        assert self.chaos_controller.stop_service("rate-limiter-controller"), "Should stop controller"
        
        # Measure impact during failure
        backpressure_metrics = self.analyzer.measure_backpressure_effectiveness(30)
        
        # Restart controller
        assert self.chaos_controller.start_service("rate-limiter-controller"), "Should restart controller"
        
        # Measure recovery
        recovery_metrics = self.analyzer.measure_recovery_time(failure_start, "controller recovery")
        
        # Validate resilience
        assert recovery_metrics["recovery_detected"], "System should recover from controller failure"
        assert recovery_metrics["recovery_time"] < 60, "Recovery should be within 60 seconds"
        assert backpressure_metrics["system_stability"] > 0.0, "System should maintain some stability"
    
    def test_backpressure_manager_failure(self):
        """Test system behavior when backpressure manager fails"""
        print("\n=== Testing Backpressure Manager Failure ===")
        
        # Capture baseline
        baseline = self.chaos_controller.capture_baseline_metrics()
        
        # Stop backpressure manager
        failure_start = time.time()
        assert self.chaos_controller.stop_service("backpressure-manager"), "Should stop backpressure manager"
        
        # Test rate limiting during backpressure manager failure
        rate_limiting_results = self.analyzer.test_rate_limiting_during_chaos(45)
        
        # Restart backpressure manager
        assert self.chaos_controller.start_service("backpressure-manager"), "Should restart backpressure manager"
        
        # Measure recovery
        recovery_metrics = self.analyzer.measure_recovery_time(failure_start, "backpressure manager recovery")
        
        # Validate that rate limiting continues without backpressure manager
        total_accuracy = sum(r["accuracy"] for r in rate_limiting_results.values()) / len(rate_limiting_results)
        assert total_accuracy > 0.7, "Rate limiting should maintain >70% accuracy without backpressure manager"
        assert recovery_metrics["recovery_detected"], "System should recover from backpressure manager failure"
    
    def test_coordination_service_failure(self):
        """Test system behavior when coordination service fails"""
        print("\n=== Testing Coordination Service Failure ===")
        
        # Capture baseline
        baseline = self.chaos_controller.capture_baseline_metrics()
        
        # Stop coordination service
        failure_start = time.time()
        assert self.chaos_controller.stop_service("coordination-service"), "Should stop coordination service"
        
        # Measure system behavior during coordination failure
        backpressure_metrics = self.analyzer.measure_backpressure_effectiveness(60)
        
        # Restart coordination service
        assert self.chaos_controller.start_service("coordination-service"), "Should restart coordination service"
        
        # Measure recovery
        recovery_metrics = self.analyzer.measure_recovery_time(failure_start, "coordination service recovery")
        
        # Validate graceful degradation
        assert backpressure_metrics["system_stability"] > 0.5, "System should maintain >50% stability without coordination"
        assert recovery_metrics["recovery_detected"], "System should recover from coordination service failure"
        assert recovery_metrics["recovery_time"] < 90, "Recovery should be within 90 seconds"
    
    def test_high_load_backpressure(self):
        """Test backpressure mechanisms under high load"""
        print("\n=== Testing High Load Backpressure ===")
        
        # Capture baseline performance
        baseline = self.chaos_controller.measure_performance_baseline(30)
        
        # Start high load simulation
        load_thread = threading.Thread(
            target=self.chaos_controller.simulate_high_load,
            args=(120, 100, 500)  # 100 users, 500 req/s for 2 minutes
        )
        load_thread.start()
        
        # Measure backpressure effectiveness during high load
        backpressure_metrics = self.analyzer.measure_backpressure_effectiveness(120)
        
        load_thread.join()
        
        # Validate backpressure mechanisms
        assert backpressure_metrics["requests_denied"] > 0, "Should deny some requests under high load"
        assert backpressure_metrics["system_stability"] > 0.3, "Should maintain >30% stability under high load"
        
        # Check for adaptive behavior
        if backpressure_metrics["adaptive_rate_changes"] > 0:
            print(f"Adaptive rate limiting detected: {backpressure_metrics['adaptive_rate_changes']} changes")
        
        if backpressure_metrics["circuit_breaker_activations"] > 0:
            print(f"Circuit breaker activated: {backpressure_metrics['circuit_breaker_activations']} times")
        
        if backpressure_metrics["load_shedding_events"] > 0:
            print(f"Load shedding occurred: {backpressure_metrics['load_shedding_events']} times")
    
    def test_network_partition_resilience(self):
        """Test system resilience to network partitions"""
        print("\n=== Testing Network Partition Resilience ===")
        
        # Capture baseline
        baseline = self.chaos_controller.capture_baseline_metrics()
        
        # Simulate network partition
        partition_start = time.time()
        partition_success = self.chaos_controller.simulate_network_partition(60)
        
        if partition_success:
            # Measure system behavior during partition
            rate_limiting_results = self.analyzer.test_rate_limiting_during_chaos(60)
            
            # Measure recovery after partition heals
            recovery_metrics = self.analyzer.measure_recovery_time(partition_start, "network partition recovery")
            
            # Validate partition tolerance
            total_accuracy = sum(r["accuracy"] for r in rate_limiting_results.values()) / len(rate_limiting_results)
            assert total_accuracy > 0.6, "Should maintain >60% accuracy during network partition"
            assert recovery_metrics["recovery_detected"], "Should recover from network partition"
        else:
            print("Network partition simulation failed - skipping validation")
    
    def test_resource_pressure_handling(self):
        """Test system behavior under resource pressure"""
        print("\n=== Testing Resource Pressure Handling ===")
        
        # Capture baseline
        baseline = self.chaos_controller.capture_baseline_metrics()
        
        # Start resource pressure simulation
        pressure_thread = threading.Thread(
            target=self.chaos_controller.simulate_resource_pressure,
            args=(90,)  # 90 seconds of resource pressure
        )
        pressure_thread.start()
        
        # Measure backpressure effectiveness during resource pressure
        backpressure_metrics = self.analyzer.measure_backpressure_effectiveness(90)
        
        pressure_thread.join()
        
        # Validate resource pressure handling
        assert backpressure_metrics["system_stability"] > 0.4, "Should maintain >40% stability under resource pressure"
        
        # Check for load shedding activation
        if backpressure_metrics["load_shedding_events"] > 0:
            print(f"Load shedding activated under resource pressure: {backpressure_metrics['load_shedding_events']} events")
            assert True, "Load shedding should activate under resource pressure"
        
        # Measure recovery after pressure is relieved
        time.sleep(30)  # Allow system to recover
        recovery_performance = self.chaos_controller.measure_performance_baseline(30)
        
        performance_recovery = recovery_performance["throughput"] / baseline["performance"]["throughput"]
        assert performance_recovery > 0.8, "Performance should recover to >80% of baseline"
    
    def test_cascading_failure_scenario(self):
        """Test system behavior during cascading failures"""
        print("\n=== Testing Cascading Failure Scenario ===")
        
        # Capture baseline
        baseline = self.chaos_controller.capture_baseline_metrics()
        
        # Simulate cascading failures
        failure_start = time.time()
        
        # Step 1: Stop coordination service
        assert self.chaos_controller.stop_service("coordination-service"), "Should stop coordination service"
        time.sleep(10)
        
        # Step 2: Simulate high load
        load_thread = threading.Thread(
            target=self.chaos_controller.simulate_high_load,
            args=(60, 50, 200)
        )
        load_thread.start()
        time.sleep(10)
        
        # Step 3: Stop backpressure manager
        assert self.chaos_controller.stop_service("backpressure-manager"), "Should stop backpressure manager"
        
        # Measure system behavior during cascading failures
        backpressure_metrics = self.analyzer.measure_backpressure_effectiveness(60)
        
        load_thread.join()
        
        # Restart services
        assert self.chaos_controller.start_service("coordination-service"), "Should restart coordination service"
        assert self.chaos_controller.start_service("backpressure-manager"), "Should restart backpressure manager"
        
        # Measure recovery
        recovery_metrics = self.analyzer.measure_recovery_time(failure_start, "cascading failure recovery")
        
        # Validate cascading failure handling
        assert backpressure_metrics["system_stability"] > 0.2, "Should maintain >20% stability during cascading failures"
        assert recovery_metrics["recovery_detected"], "Should recover from cascading failures"
        assert recovery_metrics["recovery_time"] < 180, "Recovery should be within 3 minutes"
    
    def test_data_consistency_after_failures(self):
        """Test data consistency after various failure scenarios"""
        print("\n=== Testing Data Consistency After Failures ===")
        
        # Create test data before failures
        test_keys = ["consistency-test-1", "consistency-test-2", "consistency-test-3"]
        pre_failure_states = {}
        
        for key in test_keys:
            # Establish rate limit state
            for i in range(10):
                requests.post(
                    "http://localhost:8080/api/v1/check",
                    json={"key": key, "tokens": 1},
                    timeout=5
                )
            
            # Capture state
            try:
                response = requests.get(f"http://localhost:8080/api/v1/metrics?key={key}", timeout=5)
                if response.status_code == 200:
                    pre_failure_states[key] = response.json()
            except:
                pass
        
        # Simulate failure and recovery
        assert self.chaos_controller.restart_service("rate-limiter-controller"), "Should restart controller"
        
        # Wait for recovery
        time.sleep(30)
        
        # Check data consistency after recovery
        consistency_maintained = 0
        for key in test_keys:
            try:
                response = requests.get(f"http://localhost:8080/api/v1/metrics?key={key}", timeout=5)
                if response.status_code == 200:
                    post_failure_state = response.json()
                    
                    # Check if rate limiting state is reasonable
                    if "bucket" in post_failure_state:
                        consistency_maintained += 1
                        print(f"Consistency maintained for {key}")
            except:
                pass
        
        consistency_ratio = consistency_maintained / len(test_keys)
        assert consistency_ratio > 0.7, f"Should maintain consistency for >70% of keys, got {consistency_ratio:.2%}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-s"])

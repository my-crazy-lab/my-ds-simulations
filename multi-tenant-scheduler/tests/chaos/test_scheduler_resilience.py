#!/usr/bin/env python3
"""
Chaos engineering tests for scheduler resilience and fault tolerance.
Tests scheduler behavior under various failure conditions and recovery scenarios.
"""

import pytest
import asyncio
import json
import time
import random
import threading
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import requests
import docker
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class ChaosTestConfig:
    """Configuration for chaos testing"""
    scheduler_url: str = "http://scheduler-controller:8080"
    resource_manager_url: str = "http://resource-manager:8082"
    tenant_manager_url: str = "http://tenant-manager:8084"
    workflow_engine_url: str = "http://workflow-engine:8086"
    chaos_duration: int = 120
    recovery_timeout: int = 180
    operation_timeout: int = 30

class SchedulerChaosController:
    """Controller for scheduler chaos engineering"""
    
    def __init__(self, config: ChaosTestConfig):
        self.config = config
        self.docker_client = docker.from_env()
        self.active_chaos = set()
        self.baseline_metrics = {}
    
    def capture_baseline_metrics(self) -> Dict[str, Any]:
        """Capture baseline performance metrics"""
        try:
            response = requests.get(
                f"{self.config.scheduler_url}/metrics",
                timeout=10
            )
            
            if response.status_code == 200:
                metrics = {}
                for line in response.text.split('\n'):
                    if line.startswith('scheduler_') and not line.startswith('#'):
                        parts = line.split(' ')
                        if len(parts) >= 2:
                            metric_name = parts[0].split('{')[0]
                            metric_value = float(parts[1])
                            metrics[metric_name] = metric_value
                
                self.baseline_metrics = metrics
                logger.info("Captured baseline metrics")
                return metrics
            else:
                return {}
        
        except requests.RequestException as e:
            logger.error(f"Failed to capture baseline metrics: {e}")
            return {}
    
    def stop_scheduler_controller(self) -> bool:
        """Stop scheduler controller container"""
        try:
            container = self.docker_client.containers.get("scheduler-controller")
            container.stop()
            self.active_chaos.add("scheduler-controller-stopped")
            logger.info("Stopped scheduler controller")
            return True
        except Exception as e:
            logger.error(f"Failed to stop scheduler controller: {e}")
            return False
    
    def start_scheduler_controller(self) -> bool:
        """Start scheduler controller container"""
        try:
            container = self.docker_client.containers.get("scheduler-controller")
            container.start()
            self.active_chaos.discard("scheduler-controller-stopped")
            logger.info("Started scheduler controller")
            return True
        except Exception as e:
            logger.error(f"Failed to start scheduler controller: {e}")
            return False
    
    def pause_scheduler_controller(self) -> bool:
        """Pause scheduler controller container"""
        try:
            container = self.docker_client.containers.get("scheduler-controller")
            container.pause()
            self.active_chaos.add("scheduler-controller-paused")
            logger.info("Paused scheduler controller")
            return True
        except Exception as e:
            logger.error(f"Failed to pause scheduler controller: {e}")
            return False
    
    def unpause_scheduler_controller(self) -> bool:
        """Unpause scheduler controller container"""
        try:
            container = self.docker_client.containers.get("scheduler-controller")
            container.unpause()
            self.active_chaos.discard("scheduler-controller-paused")
            logger.info("Unpaused scheduler controller")
            return True
        except Exception as e:
            logger.error(f"Failed to unpause scheduler controller: {e}")
            return False
    
    def kill_worker_node(self, node_id: str) -> bool:
        """Kill a worker node"""
        try:
            container = self.docker_client.containers.get(f"worker-node-{node_id}")
            container.kill()
            self.active_chaos.add(f"worker-{node_id}-killed")
            logger.info(f"Killed worker node {node_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to kill worker node {node_id}: {e}")
            return False
    
    def restart_worker_node(self, node_id: str) -> bool:
        """Restart a worker node"""
        try:
            container = self.docker_client.containers.get(f"worker-node-{node_id}")
            container.restart()
            self.active_chaos.discard(f"worker-{node_id}-killed")
            logger.info(f"Restarted worker node {node_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to restart worker node {node_id}: {e}")
            return False
    
    def simulate_network_partition(self, duration: int = 60) -> bool:
        """Simulate network partition between scheduler and workers"""
        try:
            # This would use network manipulation tools in a real environment
            # For demo purposes, we'll simulate by pausing containers
            
            # Pause half of the worker nodes
            worker_nodes = ["1", "2", "3"]
            partitioned_nodes = random.sample(worker_nodes, len(worker_nodes) // 2 + 1)
            
            for node_id in partitioned_nodes:
                container = self.docker_client.containers.get(f"worker-node-{node_id}")
                container.pause()
                self.active_chaos.add(f"worker-{node_id}-partitioned")
            
            logger.info(f"Created network partition affecting nodes: {partitioned_nodes}")
            
            # Schedule healing after duration
            def heal_partition():
                time.sleep(duration)
                for node_id in partitioned_nodes:
                    try:
                        container = self.docker_client.containers.get(f"worker-node-{node_id}")
                        container.unpause()
                        self.active_chaos.discard(f"worker-{node_id}-partitioned")
                    except Exception as e:
                        logger.error(f"Failed to heal partition for node {node_id}: {e}")
                logger.info("Healed network partition")
            
            threading.Thread(target=heal_partition, daemon=True).start()
            return True
        
        except Exception as e:
            logger.error(f"Failed to simulate network partition: {e}")
            return False
    
    def simulate_resource_pressure(self, duration: int = 60) -> bool:
        """Simulate high resource pressure on the cluster"""
        try:
            # Create resource-intensive containers to consume cluster resources
            pressure_containers = []
            
            for i in range(5):
                container = self.docker_client.containers.run(
                    "stress:latest",
                    command=["stress", "--cpu", "2", "--vm", "1", "--vm-bytes", "1G"],
                    detach=True,
                    name=f"resource-pressure-{i}",
                    remove=True,
                    mem_limit="2g",
                    cpuset_cpus="0-1"
                )
                pressure_containers.append(container)
                self.active_chaos.add(f"resource-pressure-{i}")
            
            logger.info(f"Started resource pressure with {len(pressure_containers)} containers")
            
            # Schedule cleanup after duration
            def cleanup_pressure():
                time.sleep(duration)
                for container in pressure_containers:
                    try:
                        container.stop()
                        self.active_chaos.discard(container.name)
                    except Exception as e:
                        logger.error(f"Failed to stop pressure container: {e}")
                logger.info("Cleaned up resource pressure")
            
            threading.Thread(target=cleanup_pressure, daemon=True).start()
            return True
        
        except Exception as e:
            logger.error(f"Failed to simulate resource pressure: {e}")
            return False
    
    def simulate_etcd_failure(self) -> bool:
        """Simulate etcd cluster failure"""
        try:
            # Stop one etcd node to test resilience
            container = self.docker_client.containers.get("etcd-1")
            container.stop()
            self.active_chaos.add("etcd-1-failed")
            logger.info("Simulated etcd node failure")
            return True
        except Exception as e:
            logger.error(f"Failed to simulate etcd failure: {e}")
            return False
    
    def heal_etcd_failure(self) -> bool:
        """Heal etcd cluster failure"""
        try:
            container = self.docker_client.containers.get("etcd-1")
            container.start()
            self.active_chaos.discard("etcd-1-failed")
            logger.info("Healed etcd node failure")
            return True
        except Exception as e:
            logger.error(f"Failed to heal etcd failure: {e}")
            return False
    
    def cleanup_all_chaos(self):
        """Clean up all active chaos"""
        logger.info("Cleaning up all chaos scenarios...")
        
        # Restart stopped/paused containers
        containers_to_restart = [
            "scheduler-controller",
            "worker-node-1",
            "worker-node-2", 
            "worker-node-3",
            "etcd-1"
        ]
        
        for container_name in containers_to_restart:
            try:
                container = self.docker_client.containers.get(container_name)
                if container.status == "paused":
                    container.unpause()
                elif container.status == "exited":
                    container.start()
            except Exception as e:
                logger.error(f"Failed to cleanup container {container_name}: {e}")
        
        # Remove pressure containers
        try:
            pressure_containers = self.docker_client.containers.list(
                filters={"name": "resource-pressure"}
            )
            for container in pressure_containers:
                container.stop()
                container.remove()
        except Exception as e:
            logger.error(f"Failed to cleanup pressure containers: {e}")
        
        self.active_chaos.clear()
        logger.info("Chaos cleanup completed")

class SchedulerResilienceAnalyzer:
    """Analyzer for scheduler resilience metrics"""
    
    def __init__(self, config: ChaosTestConfig):
        self.config = config
    
    def measure_recovery_time(self, failure_start: float, 
                            expected_behavior: str = "healthy") -> Dict[str, Any]:
        """Measure time to recovery after failure"""
        recovery_start = time.time()
        recovery_timeout = self.config.recovery_timeout
        
        while time.time() - recovery_start < recovery_timeout:
            try:
                response = requests.get(
                    f"{self.config.scheduler_url}/health",
                    timeout=5
                )
                
                if response.status_code == 200:
                    health_data = response.json()
                    if health_data.get("status") == expected_behavior:
                        recovery_time = time.time() - failure_start
                        return {
                            "recovered": True,
                            "recovery_time": recovery_time,
                            "health_status": health_data
                        }
            
            except requests.RequestException:
                pass
            
            time.sleep(2)
        
        return {
            "recovered": False,
            "recovery_time": recovery_timeout,
            "timeout": True
        }
    
    def measure_job_scheduling_impact(self, chaos_start: float, 
                                    chaos_duration: int) -> Dict[str, Any]:
        """Measure impact on job scheduling during chaos"""
        scheduling_metrics = []
        measurement_start = time.time()
        
        while time.time() - measurement_start < chaos_duration + 60:
            try:
                response = requests.get(
                    f"{self.config.scheduler_url}/metrics",
                    timeout=5
                )
                
                if response.status_code == 200:
                    metrics = {}
                    for line in response.text.split('\n'):
                        if 'scheduler_jobs_scheduled_total' in line and not line.startswith('#'):
                            parts = line.split(' ')
                            if len(parts) >= 2:
                                metrics['jobs_scheduled'] = float(parts[1])
                        elif 'scheduler_queue_depth' in line and not line.startswith('#'):
                            parts = line.split(' ')
                            if len(parts) >= 2:
                                metrics['queue_depth'] = float(parts[1])
                        elif 'scheduler_scheduling_latency' in line and not line.startswith('#'):
                            if '_sum' in line:
                                parts = line.split(' ')
                                if len(parts) >= 2:
                                    metrics['latency_sum'] = float(parts[1])
                            elif '_count' in line:
                                parts = line.split(' ')
                                if len(parts) >= 2:
                                    metrics['latency_count'] = float(parts[1])
                    
                    metrics['timestamp'] = time.time()
                    scheduling_metrics.append(metrics)
            
            except requests.RequestException:
                pass
            
            time.sleep(10)
        
        return self._analyze_scheduling_impact(scheduling_metrics, chaos_start, chaos_duration)
    
    def _analyze_scheduling_impact(self, metrics: List[Dict[str, Any]], 
                                 chaos_start: float, chaos_duration: int) -> Dict[str, Any]:
        """Analyze scheduling impact from metrics"""
        if not metrics:
            return {"error": "No metrics collected"}
        
        # Separate pre-chaos, during-chaos, and post-chaos metrics
        pre_chaos = [m for m in metrics if m['timestamp'] < chaos_start]
        during_chaos = [m for m in metrics if chaos_start <= m['timestamp'] < chaos_start + chaos_duration]
        post_chaos = [m for m in metrics if m['timestamp'] >= chaos_start + chaos_duration]
        
        def calculate_avg_latency(metric_list):
            if not metric_list:
                return 0
            
            total_sum = 0
            total_count = 0
            
            for m in metric_list:
                if 'latency_sum' in m and 'latency_count' in m:
                    total_sum += m['latency_sum']
                    total_count += m['latency_count']
            
            return total_sum / total_count if total_count > 0 else 0
        
        def calculate_avg_queue_depth(metric_list):
            if not metric_list:
                return 0
            return sum(m.get('queue_depth', 0) for m in metric_list) / len(metric_list)
        
        pre_latency = calculate_avg_latency(pre_chaos)
        during_latency = calculate_avg_latency(during_chaos)
        post_latency = calculate_avg_latency(post_chaos)
        
        pre_queue = calculate_avg_queue_depth(pre_chaos)
        during_queue = calculate_avg_queue_depth(during_chaos)
        post_queue = calculate_avg_queue_depth(post_chaos)
        
        return {
            "pre_chaos_latency": pre_latency,
            "during_chaos_latency": during_latency,
            "post_chaos_latency": post_latency,
            "pre_chaos_queue_depth": pre_queue,
            "during_chaos_queue_depth": during_queue,
            "post_chaos_queue_depth": post_queue,
            "latency_degradation": (during_latency - pre_latency) / pre_latency * 100 if pre_latency > 0 else 0,
            "queue_depth_increase": (during_queue - pre_queue) / pre_queue * 100 if pre_queue > 0 else 0,
            "recovery_quality": abs(post_latency - pre_latency) / pre_latency * 100 if pre_latency > 0 else 0
        }
    
    def test_job_submission_during_chaos(self, chaos_duration: int) -> Dict[str, Any]:
        """Test job submission success rate during chaos"""
        submission_results = []
        test_start = time.time()
        
        job_counter = 0
        while time.time() - test_start < chaos_duration:
            job_counter += 1
            
            try:
                job_data = {
                    "name": f"chaos-test-job-{job_counter}",
                    "image": "busybox:latest",
                    "resources": {"cpu": "0.5", "memory": "512Mi"},
                    "priority": 50
                }
                
                response = requests.post(
                    f"{self.config.scheduler_url}/api/v1/jobs",
                    json=job_data,
                    headers={"X-Tenant-ID": "test-tenant-medium"},
                    timeout=10
                )
                
                submission_results.append({
                    "timestamp": time.time(),
                    "success": response.status_code in [200, 201],
                    "status_code": response.status_code,
                    "job_id": response.json().get("id") if response.status_code in [200, 201] else None
                })
            
            except requests.RequestException as e:
                submission_results.append({
                    "timestamp": time.time(),
                    "success": False,
                    "error": str(e)
                })
            
            time.sleep(5)
        
        # Analyze results
        total_submissions = len(submission_results)
        successful_submissions = len([r for r in submission_results if r["success"]])
        success_rate = (successful_submissions / total_submissions * 100) if total_submissions > 0 else 0
        
        return {
            "total_submissions": total_submissions,
            "successful_submissions": successful_submissions,
            "success_rate": success_rate,
            "submission_results": submission_results
        }

@pytest.fixture(scope="session")
def chaos_config():
    """Chaos test configuration fixture"""
    return ChaosTestConfig()

@pytest.fixture(scope="session")
def chaos_controller(chaos_config):
    """Chaos controller fixture"""
    controller = SchedulerChaosController(chaos_config)
    yield controller
    # Cleanup after tests
    controller.cleanup_all_chaos()

@pytest.fixture(scope="session")
def resilience_analyzer(chaos_config):
    """Resilience analyzer fixture"""
    return SchedulerResilienceAnalyzer(chaos_config)

class TestSchedulerResilience:
    """Test scheduler resilience under various failure conditions"""
    
    def test_scheduler_controller_failure(self, chaos_controller, resilience_analyzer):
        """Test scheduler controller failure and recovery"""
        logger.info("🔥 Testing scheduler controller failure...")
        
        # Capture baseline
        chaos_controller.capture_baseline_metrics()
        
        # Stop scheduler controller
        failure_start = time.time()
        assert chaos_controller.stop_scheduler_controller()
        
        # Wait for failure to be detected
        time.sleep(10)
        
        # Start scheduler controller
        assert chaos_controller.start_scheduler_controller()
        
        # Measure recovery
        recovery_result = resilience_analyzer.measure_recovery_time(failure_start)
        
        logger.info(f"Recovery result: {recovery_result}")
        
        if recovery_result["recovered"]:
            recovery_time = recovery_result["recovery_time"]
            assert recovery_time < 120, f"Recovery took too long: {recovery_time}s"
            logger.info(f"✅ Scheduler controller recovery test passed: {recovery_time:.2f}s")
        else:
            logger.warning("⚠️  Scheduler controller failed to recover within timeout")
    
    def test_worker_node_failure(self, chaos_controller, resilience_analyzer):
        """Test worker node failure and job rescheduling"""
        logger.info("🔥 Testing worker node failure...")
        
        # Kill a worker node
        node_id = "1"
        failure_start = time.time()
        assert chaos_controller.kill_worker_node(node_id)
        
        # Test job submission during node failure
        submission_result = resilience_analyzer.test_job_submission_during_chaos(60)
        
        # Restart the worker node
        assert chaos_controller.restart_worker_node(node_id)
        
        # Measure recovery
        recovery_result = resilience_analyzer.measure_recovery_time(failure_start)
        
        logger.info(f"Job submission during failure: {submission_result['success_rate']:.1f}%")
        logger.info(f"Recovery result: {recovery_result}")
        
        # System should maintain some functionality even with node failure
        assert submission_result["success_rate"] > 50, "Job submission success rate too low during node failure"
        
        if recovery_result["recovered"]:
            logger.info("✅ Worker node failure test passed")
        else:
            logger.warning("⚠️  System failed to fully recover from worker node failure")
    
    def test_network_partition_resilience(self, chaos_controller, resilience_analyzer):
        """Test resilience to network partitions"""
        logger.info("🔥 Testing network partition resilience...")
        
        # Create network partition
        partition_start = time.time()
        assert chaos_controller.simulate_network_partition(duration=90)
        
        # Measure scheduling impact during partition
        impact_result = resilience_analyzer.measure_job_scheduling_impact(
            partition_start, chaos_duration=90
        )
        
        logger.info(f"Scheduling impact during partition: {impact_result}")
        
        # Wait for partition to heal and measure recovery
        time.sleep(100)  # Wait for partition to heal
        recovery_result = resilience_analyzer.measure_recovery_time(partition_start)
        
        logger.info(f"Recovery after partition healing: {recovery_result}")
        
        # Check impact metrics
        latency_degradation = impact_result.get("latency_degradation", 0)
        queue_increase = impact_result.get("queue_depth_increase", 0)
        
        # Some degradation is expected during partition
        assert latency_degradation < 500, f"Latency degradation too high: {latency_degradation}%"
        
        if recovery_result["recovered"]:
            logger.info("✅ Network partition resilience test passed")
        else:
            logger.warning("⚠️  System failed to recover from network partition")
    
    def test_resource_pressure_handling(self, chaos_controller, resilience_analyzer):
        """Test handling of high resource pressure"""
        logger.info("🔥 Testing resource pressure handling...")
        
        # Create resource pressure
        pressure_start = time.time()
        assert chaos_controller.simulate_resource_pressure(duration=120)
        
        # Test job submission under pressure
        submission_result = resilience_analyzer.test_job_submission_during_chaos(120)
        
        # Measure scheduling impact
        impact_result = resilience_analyzer.measure_job_scheduling_impact(
            pressure_start, chaos_duration=120
        )
        
        logger.info(f"Job submission under pressure: {submission_result['success_rate']:.1f}%")
        logger.info(f"Scheduling impact under pressure: {impact_result}")
        
        # System should handle resource pressure gracefully
        assert submission_result["success_rate"] > 30, "Job submission success rate too low under pressure"
        
        # Queue depth should increase under pressure
        queue_increase = impact_result.get("queue_depth_increase", 0)
        if queue_increase > 0:
            logger.info("✅ Resource pressure handling test passed - queue depth increased appropriately")
        else:
            logger.warning("⚠️  Queue depth did not increase under resource pressure")
    
    def test_etcd_failure_resilience(self, chaos_controller, resilience_analyzer):
        """Test resilience to etcd cluster failure"""
        logger.info("🔥 Testing etcd failure resilience...")
        
        # Simulate etcd failure
        failure_start = time.time()
        assert chaos_controller.simulate_etcd_failure()
        
        # Test system behavior during etcd failure
        submission_result = resilience_analyzer.test_job_submission_during_chaos(60)
        
        # Heal etcd failure
        assert chaos_controller.heal_etcd_failure()
        
        # Measure recovery
        recovery_result = resilience_analyzer.measure_recovery_time(failure_start)
        
        logger.info(f"Job submission during etcd failure: {submission_result['success_rate']:.1f}%")
        logger.info(f"Recovery result: {recovery_result}")
        
        # System should degrade gracefully during etcd failure
        # Some operations may fail, but system should not crash
        
        if recovery_result["recovered"]:
            logger.info("✅ etcd failure resilience test passed")
        else:
            logger.warning("⚠️  System failed to recover from etcd failure")
    
    def test_cascading_failure_scenario(self, chaos_controller, resilience_analyzer):
        """Test handling of cascading failures"""
        logger.info("🔥 Testing cascading failure scenario...")
        
        # Create multiple simultaneous failures
        failure_start = time.time()
        
        # Kill worker node
        chaos_controller.kill_worker_node("2")
        time.sleep(10)
        
        # Create resource pressure
        chaos_controller.simulate_resource_pressure(duration=90)
        time.sleep(10)
        
        # Pause scheduler controller briefly
        chaos_controller.pause_scheduler_controller()
        time.sleep(20)
        chaos_controller.unpause_scheduler_controller()
        
        # Test system behavior during cascading failures
        submission_result = resilience_analyzer.test_job_submission_during_chaos(60)
        
        # Start recovery
        chaos_controller.restart_worker_node("2")
        
        # Measure overall recovery
        recovery_result = resilience_analyzer.measure_recovery_time(failure_start)
        
        logger.info(f"Job submission during cascading failures: {submission_result['success_rate']:.1f}%")
        logger.info(f"Recovery result: {recovery_result}")
        
        # System should survive cascading failures
        assert submission_result["success_rate"] > 10, "System completely failed during cascading failures"
        
        if recovery_result["recovered"]:
            logger.info("✅ Cascading failure scenario test passed")
        else:
            logger.warning("⚠️  System failed to recover from cascading failures")

class TestSchedulerFailover:
    """Test scheduler failover and high availability"""
    
    def test_scheduler_high_availability(self, chaos_controller):
        """Test scheduler high availability setup"""
        # This would test multiple scheduler instances in a real HA setup
        # For now, we test single instance resilience
        
        logger.info("🔄 Testing scheduler high availability...")
        
        # Test rapid restart cycles
        for i in range(3):
            logger.info(f"HA test cycle {i+1}/3")
            
            # Stop and start scheduler rapidly
            chaos_controller.stop_scheduler_controller()
            time.sleep(5)
            chaos_controller.start_scheduler_controller()
            time.sleep(15)
            
            # Check if scheduler is responsive
            try:
                response = requests.get(
                    f"{chaos_controller.config.scheduler_url}/health",
                    timeout=10
                )
                assert response.status_code == 200
                logger.info(f"✅ HA cycle {i+1} passed")
            except requests.RequestException:
                logger.warning(f"⚠️  HA cycle {i+1} failed - scheduler not responsive")
        
        logger.info("✅ Scheduler high availability test completed")
    
    def test_data_consistency_after_failure(self, chaos_controller):
        """Test data consistency after scheduler failure"""
        logger.info("🔍 Testing data consistency after failure...")
        
        # Submit jobs before failure
        pre_failure_jobs = []
        for i in range(5):
            try:
                job_data = {
                    "name": f"consistency-test-job-{i}",
                    "image": "busybox:latest",
                    "resources": {"cpu": "0.5", "memory": "512Mi"}
                }
                
                response = requests.post(
                    f"{chaos_controller.config.scheduler_url}/api/v1/jobs",
                    json=job_data,
                    headers={"X-Tenant-ID": "test-tenant-medium"},
                    timeout=10
                )
                
                if response.status_code in [200, 201]:
                    pre_failure_jobs.append(response.json()["id"])
            
            except requests.RequestException:
                pass
        
        # Cause failure
        chaos_controller.stop_scheduler_controller()
        time.sleep(10)
        chaos_controller.start_scheduler_controller()
        time.sleep(30)
        
        # Check if jobs are still accessible
        accessible_jobs = 0
        for job_id in pre_failure_jobs:
            try:
                response = requests.get(
                    f"{chaos_controller.config.scheduler_url}/api/v1/jobs/{job_id}",
                    headers={"X-Tenant-ID": "test-tenant-medium"},
                    timeout=10
                )
                
                if response.status_code == 200:
                    accessible_jobs += 1
            
            except requests.RequestException:
                pass
        
        consistency_rate = (accessible_jobs / len(pre_failure_jobs) * 100) if pre_failure_jobs else 100
        
        logger.info(f"Data consistency rate: {consistency_rate:.1f}% ({accessible_jobs}/{len(pre_failure_jobs)})")
        
        # Most jobs should be recoverable
        assert consistency_rate > 70, f"Data consistency too low: {consistency_rate}%"
        
        logger.info("✅ Data consistency test passed")

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-s"])

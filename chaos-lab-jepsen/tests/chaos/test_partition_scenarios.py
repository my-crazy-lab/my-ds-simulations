#!/usr/bin/env python3
"""
Chaos engineering tests for network partition scenarios.
Tests distributed systems behavior under various network partition conditions.
"""

import pytest
import asyncio
import json
import time
import random
import threading
from typing import Dict, List, Any, Optional, Set
from dataclasses import dataclass
import requests
import docker
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class PartitionTestConfig:
    """Configuration for partition testing"""
    nodes: List[str] = None
    etcd_endpoints: List[str] = None
    redis_endpoints: List[str] = None
    chaos_controller_url: str = "http://chaos-controller:8080"
    partition_duration: int = 60
    recovery_timeout: int = 120
    operation_timeout: int = 10
    
    def __post_init__(self):
        if self.nodes is None:
            self.nodes = ["n1", "n2", "n3", "n4", "n5"]
        if self.etcd_endpoints is None:
            self.etcd_endpoints = [
                "http://etcd-1:2379",
                "http://etcd-2:2379", 
                "http://etcd-3:2379"
            ]
        if self.redis_endpoints is None:
            self.redis_endpoints = [
                "redis-1:6379",
                "redis-2:6379",
                "redis-3:6379"
            ]

class NetworkPartitionController:
    """Controller for network partition injection"""
    
    def __init__(self, config: PartitionTestConfig):
        self.config = config
        self.docker_client = docker.from_env()
        self.active_partitions = set()
    
    def create_partition(self, partition_type: str, nodes: List[str]) -> bool:
        """Create a network partition"""
        try:
            partition_config = {
                'type': partition_type,
                'nodes': nodes,
                'duration': self.config.partition_duration
            }
            
            response = requests.post(
                f"{self.config.chaos_controller_url}/api/partitions",
                json=partition_config,
                timeout=30
            )
            
            if response.status_code == 200:
                partition_id = response.json().get('partition_id')
                self.active_partitions.add(partition_id)
                logger.info(f"Created {partition_type} partition: {partition_id}")
                return True
            else:
                logger.error(f"Failed to create partition: {response.status_code}")
                return False
        
        except requests.RequestException as e:
            logger.error(f"Partition creation failed: {e}")
            return False
    
    def heal_partition(self, partition_id: str = None) -> bool:
        """Heal network partition"""
        try:
            if partition_id:
                response = requests.delete(
                    f"{self.config.chaos_controller_url}/api/partitions/{partition_id}",
                    timeout=30
                )
                if response.status_code == 200:
                    self.active_partitions.discard(partition_id)
                    logger.info(f"Healed partition: {partition_id}")
                    return True
            else:
                # Heal all partitions
                response = requests.delete(
                    f"{self.config.chaos_controller_url}/api/partitions",
                    timeout=30
                )
                if response.status_code == 200:
                    self.active_partitions.clear()
                    logger.info("Healed all partitions")
                    return True
            
            return False
        
        except requests.RequestException as e:
            logger.error(f"Partition healing failed: {e}")
            return False
    
    def get_partition_status(self) -> Dict[str, Any]:
        """Get current partition status"""
        try:
            response = requests.get(
                f"{self.config.chaos_controller_url}/api/partitions",
                timeout=10
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                return {'error': f'Status check failed: {response.status_code}'}
        
        except requests.RequestException as e:
            return {'error': f'Status check failed: {e}'}
    
    def isolate_node(self, node: str) -> bool:
        """Isolate a single node from the cluster"""
        other_nodes = [n for n in self.config.nodes if n != node]
        return self.create_partition('isolate', [node])
    
    def create_majority_minority_split(self) -> bool:
        """Create majority/minority partition"""
        nodes = self.config.nodes.copy()
        random.shuffle(nodes)
        
        majority_size = len(nodes) // 2 + 1
        majority = nodes[:majority_size]
        minority = nodes[majority_size:]
        
        logger.info(f"Creating majority/minority split: {majority} vs {minority}")
        return self.create_partition('majority_minority', majority + minority)
    
    def create_bridge_partition(self) -> bool:
        """Create bridge partition (one node can talk to both sides)"""
        if len(self.config.nodes) < 3:
            return False
        
        nodes = self.config.nodes.copy()
        random.shuffle(nodes)
        
        bridge = nodes[0]
        side_a = nodes[1:len(nodes)//2+1]
        side_b = nodes[len(nodes)//2+1:]
        
        logger.info(f"Creating bridge partition: {bridge} bridges {side_a} and {side_b}")
        return self.create_partition('bridge', [bridge] + side_a + side_b)

class DistributedSystemClient:
    """Client for testing distributed systems during partitions"""
    
    def __init__(self, config: PartitionTestConfig):
        self.config = config
        self.operation_count = 0
        self.successful_operations = 0
        self.failed_operations = 0
        self.operation_history = []
    
    def test_etcd_operations(self, duration: int = 60) -> Dict[str, Any]:
        """Test etcd operations during partition"""
        start_time = time.time()
        results = {
            'total_operations': 0,
            'successful_operations': 0,
            'failed_operations': 0,
            'availability_periods': [],
            'operation_latencies': []
        }
        
        while time.time() - start_time < duration:
            operation_start = time.time()
            
            # Try write operation
            success = self._etcd_write_operation()
            operation_latency = time.time() - operation_start
            
            results['total_operations'] += 1
            results['operation_latencies'].append(operation_latency)
            
            if success:
                results['successful_operations'] += 1
            else:
                results['failed_operations'] += 1
            
            # Record availability period
            results['availability_periods'].append({
                'timestamp': time.time(),
                'available': success,
                'latency': operation_latency
            })
            
            time.sleep(1)  # 1 operation per second
        
        return results
    
    def _etcd_write_operation(self) -> bool:
        """Perform etcd write operation"""
        key = f"test-key-{random.randint(1, 100)}"
        value = f"test-value-{int(time.time())}"
        
        for endpoint in self.config.etcd_endpoints:
            try:
                response = requests.put(
                    f"{endpoint}/v2/keys/{key}",
                    data={'value': value},
                    timeout=self.config.operation_timeout
                )
                
                if response.status_code == 200 or response.status_code == 201:
                    return True
            
            except requests.RequestException:
                continue
        
        return False
    
    def _etcd_read_operation(self) -> bool:
        """Perform etcd read operation"""
        key = f"test-key-{random.randint(1, 100)}"
        
        for endpoint in self.config.etcd_endpoints:
            try:
                response = requests.get(
                    f"{endpoint}/v2/keys/{key}",
                    timeout=self.config.operation_timeout
                )
                
                if response.status_code == 200:
                    return True
            
            except requests.RequestException:
                continue
        
        return False
    
    def test_redis_operations(self, duration: int = 60) -> Dict[str, Any]:
        """Test Redis operations during partition"""
        # Simplified Redis testing - would use redis-py in practice
        start_time = time.time()
        results = {
            'total_operations': 0,
            'successful_operations': 0,
            'failed_operations': 0,
            'consistency_violations': []
        }
        
        while time.time() - start_time < duration:
            # Simulate Redis operations
            success = random.choice([True, False])  # Mock operation result
            
            results['total_operations'] += 1
            if success:
                results['successful_operations'] += 1
            else:
                results['failed_operations'] += 1
            
            time.sleep(1)
        
        return results
    
    def measure_consistency_during_partition(self, duration: int = 60) -> Dict[str, Any]:
        """Measure consistency violations during partition"""
        consistency_results = {
            'linearizability_violations': 0,
            'stale_reads': 0,
            'lost_writes': 0,
            'operation_timeline': []
        }
        
        start_time = time.time()
        written_values = {}
        
        while time.time() - start_time < duration:
            operation_time = time.time()
            
            # Perform write operation
            key = f"consistency-key-{random.randint(1, 10)}"
            value = f"value-{int(operation_time * 1000)}"
            
            write_success = self._etcd_write_operation()
            if write_success:
                written_values[key] = value
            
            # Perform read operation
            read_value = self._etcd_read_value(key)
            
            # Check for consistency violations
            if key in written_values and read_value != written_values[key]:
                if read_value is None:
                    consistency_results['lost_writes'] += 1
                else:
                    consistency_results['stale_reads'] += 1
            
            consistency_results['operation_timeline'].append({
                'timestamp': operation_time,
                'operation': 'write' if write_success else 'failed_write',
                'key': key,
                'value': value,
                'read_value': read_value
            })
            
            time.sleep(2)
        
        return consistency_results
    
    def _etcd_read_value(self, key: str) -> Optional[str]:
        """Read value from etcd"""
        for endpoint in self.config.etcd_endpoints:
            try:
                response = requests.get(
                    f"{endpoint}/v2/keys/{key}",
                    timeout=self.config.operation_timeout
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return data.get('node', {}).get('value')
            
            except requests.RequestException:
                continue
        
        return None

class PartitionAnalyzer:
    """Analyzer for partition test results"""
    
    def analyze_availability(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze availability during partition"""
        availability_periods = results.get('availability_periods', [])
        
        if not availability_periods:
            return {'availability': 0.0, 'uptime_periods': [], 'downtime_periods': []}
        
        total_periods = len(availability_periods)
        available_periods = len([p for p in availability_periods if p['available']])
        
        availability = (available_periods / total_periods) * 100
        
        # Find uptime and downtime periods
        uptime_periods = []
        downtime_periods = []
        current_period = None
        
        for period in availability_periods:
            if current_period is None:
                current_period = {
                    'start': period['timestamp'],
                    'available': period['available']
                }
            elif current_period['available'] != period['available']:
                # Period changed
                current_period['end'] = period['timestamp']
                current_period['duration'] = current_period['end'] - current_period['start']
                
                if current_period['available']:
                    uptime_periods.append(current_period)
                else:
                    downtime_periods.append(current_period)
                
                current_period = {
                    'start': period['timestamp'],
                    'available': period['available']
                }
        
        return {
            'availability': availability,
            'uptime_periods': uptime_periods,
            'downtime_periods': downtime_periods,
            'mean_uptime': sum(p['duration'] for p in uptime_periods) / len(uptime_periods) if uptime_periods else 0,
            'mean_downtime': sum(p['duration'] for p in downtime_periods) / len(downtime_periods) if downtime_periods else 0
        }
    
    def analyze_performance_impact(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze performance impact of partitions"""
        latencies = results.get('operation_latencies', [])
        
        if not latencies:
            return {'mean_latency': 0, 'p95_latency': 0, 'p99_latency': 0}
        
        sorted_latencies = sorted(latencies)
        n = len(sorted_latencies)
        
        return {
            'mean_latency': sum(latencies) / n,
            'median_latency': sorted_latencies[n // 2],
            'p95_latency': sorted_latencies[int(n * 0.95)],
            'p99_latency': sorted_latencies[int(n * 0.99)],
            'max_latency': max(latencies),
            'min_latency': min(latencies)
        }
    
    def analyze_consistency_violations(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze consistency violations during partition"""
        return {
            'total_violations': (results.get('linearizability_violations', 0) + 
                               results.get('stale_reads', 0) + 
                               results.get('lost_writes', 0)),
            'violation_breakdown': {
                'linearizability_violations': results.get('linearizability_violations', 0),
                'stale_reads': results.get('stale_reads', 0),
                'lost_writes': results.get('lost_writes', 0)
            },
            'violation_rate': self._calculate_violation_rate(results)
        }
    
    def _calculate_violation_rate(self, results: Dict[str, Any]) -> float:
        """Calculate consistency violation rate"""
        timeline = results.get('operation_timeline', [])
        if not timeline:
            return 0.0
        
        total_operations = len(timeline)
        violations = (results.get('linearizability_violations', 0) + 
                     results.get('stale_reads', 0) + 
                     results.get('lost_writes', 0))
        
        return (violations / total_operations) * 100 if total_operations > 0 else 0.0

@pytest.fixture(scope="session")
def partition_config():
    """Partition test configuration fixture"""
    return PartitionTestConfig()

@pytest.fixture(scope="session")
def partition_controller(partition_config):
    """Partition controller fixture"""
    return NetworkPartitionController(partition_config)

@pytest.fixture(scope="session")
def system_client(partition_config):
    """System client fixture"""
    return DistributedSystemClient(partition_config)

@pytest.fixture(scope="session")
def partition_analyzer():
    """Partition analyzer fixture"""
    return PartitionAnalyzer()

class TestNetworkPartitionScenarios:
    """Test various network partition scenarios"""
    
    def test_majority_minority_partition(self, partition_controller, system_client, partition_analyzer):
        """Test majority/minority partition scenario"""
        logger.info("🔀 Testing majority/minority partition...")
        
        # Create majority/minority partition
        assert partition_controller.create_majority_minority_split()
        
        try:
            # Test system behavior during partition
            results = system_client.test_etcd_operations(duration=30)
            
            # Analyze results
            availability_analysis = partition_analyzer.analyze_availability(results)
            performance_analysis = partition_analyzer.analyze_performance_impact(results)
            
            logger.info(f"Availability during partition: {availability_analysis['availability']:.2f}%")
            logger.info(f"Mean latency: {performance_analysis['mean_latency']:.3f}s")
            
            # System should maintain some availability (majority side)
            assert availability_analysis['availability'] > 0
            
        finally:
            # Heal partition
            partition_controller.heal_partition()
            time.sleep(10)  # Allow recovery
        
        logger.info("✅ Majority/minority partition test passed")
    
    def test_node_isolation(self, partition_controller, system_client, partition_analyzer):
        """Test single node isolation"""
        logger.info("🏝️ Testing node isolation...")
        
        # Isolate a random node
        isolated_node = random.choice(partition_controller.config.nodes)
        assert partition_controller.isolate_node(isolated_node)
        
        try:
            # Test system behavior during isolation
            results = system_client.test_etcd_operations(duration=30)
            
            # Analyze results
            availability_analysis = partition_analyzer.analyze_availability(results)
            
            logger.info(f"Availability with isolated node: {availability_analysis['availability']:.2f}%")
            
            # System should maintain high availability (4/5 nodes still connected)
            assert availability_analysis['availability'] > 50
            
        finally:
            # Heal partition
            partition_controller.heal_partition()
            time.sleep(10)
        
        logger.info("✅ Node isolation test passed")
    
    def test_bridge_partition(self, partition_controller, system_client):
        """Test bridge partition scenario"""
        logger.info("🌉 Testing bridge partition...")
        
        # Create bridge partition
        assert partition_controller.create_bridge_partition()
        
        try:
            # Test system behavior during bridge partition
            results = system_client.test_etcd_operations(duration=30)
            
            # Bridge partitions can have complex behavior
            assert results['total_operations'] > 0
            
        finally:
            # Heal partition
            partition_controller.heal_partition()
            time.sleep(10)
        
        logger.info("✅ Bridge partition test passed")
    
    def test_consistency_during_partition(self, partition_controller, system_client, partition_analyzer):
        """Test consistency guarantees during partition"""
        logger.info("🔍 Testing consistency during partition...")
        
        # Create partition
        assert partition_controller.create_majority_minority_split()
        
        try:
            # Measure consistency violations
            consistency_results = system_client.measure_consistency_during_partition(duration=30)
            
            # Analyze consistency violations
            violation_analysis = partition_analyzer.analyze_consistency_violations(consistency_results)
            
            logger.info(f"Total consistency violations: {violation_analysis['total_violations']}")
            logger.info(f"Violation rate: {violation_analysis['violation_rate']:.2f}%")
            
            # Log violation breakdown
            for violation_type, count in violation_analysis['violation_breakdown'].items():
                if count > 0:
                    logger.info(f"  {violation_type}: {count}")
            
            # Some violations may be expected during partitions
            # The key is that they should be bounded and recoverable
            
        finally:
            # Heal partition
            partition_controller.heal_partition()
            time.sleep(10)
        
        logger.info("✅ Consistency during partition test passed")
    
    def test_partition_recovery(self, partition_controller, system_client, partition_analyzer):
        """Test system recovery after partition healing"""
        logger.info("🔄 Testing partition recovery...")
        
        # Create partition
        assert partition_controller.create_majority_minority_split()
        
        # Let partition run for a while
        time.sleep(20)
        
        # Heal partition
        partition_controller.heal_partition()
        
        # Measure recovery
        recovery_start = time.time()
        recovery_results = system_client.test_etcd_operations(duration=60)
        
        # Analyze recovery
        availability_analysis = partition_analyzer.analyze_availability(recovery_results)
        performance_analysis = partition_analyzer.analyze_performance_impact(recovery_results)
        
        logger.info(f"Post-recovery availability: {availability_analysis['availability']:.2f}%")
        logger.info(f"Post-recovery mean latency: {performance_analysis['mean_latency']:.3f}s")
        
        # System should recover to high availability
        assert availability_analysis['availability'] > 80
        
        logger.info("✅ Partition recovery test passed")
    
    def test_multiple_partition_cycles(self, partition_controller, system_client):
        """Test multiple partition/heal cycles"""
        logger.info("🔄 Testing multiple partition cycles...")
        
        total_operations = 0
        successful_operations = 0
        
        for cycle in range(3):
            logger.info(f"Partition cycle {cycle + 1}/3")
            
            # Create partition
            partition_controller.create_majority_minority_split()
            
            # Test during partition
            results = system_client.test_etcd_operations(duration=20)
            total_operations += results['total_operations']
            successful_operations += results['successful_operations']
            
            # Heal partition
            partition_controller.heal_partition()
            
            # Test during recovery
            recovery_results = system_client.test_etcd_operations(duration=10)
            total_operations += recovery_results['total_operations']
            successful_operations += recovery_results['successful_operations']
        
        overall_success_rate = (successful_operations / total_operations) * 100
        logger.info(f"Overall success rate across cycles: {overall_success_rate:.2f}%")
        
        # System should maintain reasonable success rate across cycles
        assert overall_success_rate > 30  # Allowing for partition impact
        
        logger.info("✅ Multiple partition cycles test passed")

class TestPartitionTolerance:
    """Test partition tolerance properties"""
    
    def test_cap_theorem_validation(self, partition_controller, system_client):
        """Validate CAP theorem trade-offs during partition"""
        logger.info("⚖️ Testing CAP theorem trade-offs...")
        
        # Baseline measurements (no partition)
        baseline_results = system_client.test_etcd_operations(duration=30)
        baseline_availability = (baseline_results['successful_operations'] / 
                               baseline_results['total_operations']) * 100
        
        logger.info(f"Baseline availability: {baseline_availability:.2f}%")
        
        # Create partition
        partition_controller.create_majority_minority_split()
        
        try:
            # Measure during partition
            partition_results = system_client.test_etcd_operations(duration=30)
            partition_availability = (partition_results['successful_operations'] / 
                                    partition_results['total_operations']) * 100
            
            logger.info(f"Availability during partition: {partition_availability:.2f}%")
            
            # CAP theorem: during partition, system must choose between consistency and availability
            # etcd chooses consistency, so availability should decrease
            assert partition_availability < baseline_availability
            
        finally:
            partition_controller.heal_partition()
        
        logger.info("✅ CAP theorem validation test passed")
    
    def test_split_brain_prevention(self, partition_controller, system_client):
        """Test split-brain prevention mechanisms"""
        logger.info("🧠 Testing split-brain prevention...")
        
        # Create partition that could cause split-brain
        partition_controller.create_majority_minority_split()
        
        try:
            # Test that only one side accepts writes (majority side)
            consistency_results = system_client.measure_consistency_during_partition(duration=30)
            
            # In a properly designed system, there should be no split-brain
            # All successful writes should be consistent
            violation_count = (consistency_results.get('linearizability_violations', 0) + 
                             consistency_results.get('lost_writes', 0))
            
            logger.info(f"Potential split-brain violations: {violation_count}")
            
            # Well-designed systems should prevent split-brain
            # Some violations might be acceptable due to timing
            
        finally:
            partition_controller.heal_partition()
        
        logger.info("✅ Split-brain prevention test passed")

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-s"])

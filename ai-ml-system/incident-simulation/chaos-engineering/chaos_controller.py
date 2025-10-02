#!/usr/bin/env python3
"""
Chaos Engineering Controller
Implements systematic failure injection and recovery testing
"""

import asyncio
import json
import logging
import random
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, asdict
from enum import Enum
import subprocess
import docker
import psutil

import aiohttp
import redis.asyncio as redis
from kafka import KafkaProducer, KafkaConsumer
import prometheus_client
from prometheus_client import Counter, Histogram, Gauge

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Prometheus metrics for chaos engineering
CHAOS_EXPERIMENTS = Counter('chaos_experiments_total', 'Chaos experiments', ['type', 'status'])
SYSTEM_RECOVERY_TIME = Histogram('system_recovery_time_seconds', 'System recovery time')
SERVICE_AVAILABILITY = Gauge('service_availability', 'Service availability', ['service'])
CHAOS_IMPACT_SCORE = Gauge('chaos_impact_score', 'Chaos impact score', ['experiment'])

class ChaosType(Enum):
    NETWORK_PARTITION = "network_partition"
    SERVICE_KILL = "service_kill"
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    DATABASE_FAILURE = "database_failure"
    MESSAGE_QUEUE_FAILURE = "message_queue_failure"
    DISK_FULL = "disk_full"
    HIGH_LATENCY = "high_latency"
    PACKET_LOSS = "packet_loss"

class ChaosTarget(Enum):
    DATA_INGESTION = "data-ingestion"
    RAG_ENGINE = "rag-engine"
    DRIFT_DETECTION = "drift-detection"
    KAFKA = "kafka"
    REDIS = "redis"
    MILVUS = "milvus"
    POSTGRES = "postgres"
    MONGODB = "mongodb"

@dataclass
class ChaosExperiment:
    """Chaos experiment configuration"""
    id: str
    name: str
    type: ChaosType
    target: ChaosTarget
    duration_seconds: int
    parameters: Dict[str, Any]
    expected_impact: str
    recovery_criteria: Dict[str, Any]
    rollback_commands: List[str]

@dataclass
class ChaosResult:
    """Chaos experiment result"""
    experiment_id: str
    start_time: str
    end_time: Optional[str]
    status: str
    impact_metrics: Dict[str, float]
    recovery_time_seconds: Optional[float]
    observations: List[str]
    system_behavior: Dict[str, Any]

class NetworkChaosInjector:
    """Injects network-related chaos"""
    
    def __init__(self):
        self.active_rules = []
    
    async def inject_network_partition(self, target_service: str, duration: int) -> bool:
        """Inject network partition using iptables"""
        try:
            # Block traffic to target service port
            port_map = {
                'data-ingestion': 8080,
                'rag-engine': 8081,
                'drift-detection': 8082,
                'kafka': 9092,
                'redis': 6379,
                'milvus': 19530,
            }
            
            port = port_map.get(target_service)
            if not port:
                logger.error(f"Unknown service: {target_service}")
                return False
            
            # Add iptables rule to drop packets
            rule_cmd = f"sudo iptables -A OUTPUT -p tcp --dport {port} -j DROP"
            subprocess.run(rule_cmd.split(), check=True)
            
            self.active_rules.append(f"OUTPUT -p tcp --dport {port} -j DROP")
            logger.warning(f"Injected network partition for {target_service} (port {port})")
            
            # Schedule cleanup
            asyncio.create_task(self._cleanup_network_rule_after_delay(port, duration))
            
            CHAOS_EXPERIMENTS.labels(type='network_partition', status='injected').inc()
            return True
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to inject network partition: {e}")
            return False
    
    async def inject_high_latency(self, target_interface: str, delay_ms: int, duration: int) -> bool:
        """Inject network latency using tc (traffic control)"""
        try:
            # Add network delay
            cmd = f"sudo tc qdisc add dev {target_interface} root netem delay {delay_ms}ms"
            subprocess.run(cmd.split(), check=True)
            
            logger.warning(f"Injected {delay_ms}ms latency on {target_interface}")
            
            # Schedule cleanup
            asyncio.create_task(self._cleanup_latency_after_delay(target_interface, duration))
            
            CHAOS_EXPERIMENTS.labels(type='high_latency', status='injected').inc()
            return True
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to inject latency: {e}")
            return False
    
    async def inject_packet_loss(self, target_interface: str, loss_percent: int, duration: int) -> bool:
        """Inject packet loss using tc"""
        try:
            # Add packet loss
            cmd = f"sudo tc qdisc add dev {target_interface} root netem loss {loss_percent}%"
            subprocess.run(cmd.split(), check=True)
            
            logger.warning(f"Injected {loss_percent}% packet loss on {target_interface}")
            
            # Schedule cleanup
            asyncio.create_task(self._cleanup_packet_loss_after_delay(target_interface, duration))
            
            CHAOS_EXPERIMENTS.labels(type='packet_loss', status='injected').inc()
            return True
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to inject packet loss: {e}")
            return False
    
    async def _cleanup_network_rule_after_delay(self, port: int, delay: int):
        """Cleanup network rule after delay"""
        await asyncio.sleep(delay)
        try:
            rule_cmd = f"sudo iptables -D OUTPUT -p tcp --dport {port} -j DROP"
            subprocess.run(rule_cmd.split(), check=True)
            logger.info(f"Cleaned up network partition for port {port}")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to cleanup network rule: {e}")
    
    async def _cleanup_latency_after_delay(self, interface: str, delay: int):
        """Cleanup latency injection after delay"""
        await asyncio.sleep(delay)
        try:
            cmd = f"sudo tc qdisc del dev {interface} root"
            subprocess.run(cmd.split(), check=True)
            logger.info(f"Cleaned up latency injection on {interface}")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to cleanup latency: {e}")
    
    async def _cleanup_packet_loss_after_delay(self, interface: str, delay: int):
        """Cleanup packet loss injection after delay"""
        await asyncio.sleep(delay)
        try:
            cmd = f"sudo tc qdisc del dev {interface} root"
            subprocess.run(cmd.split(), check=True)
            logger.info(f"Cleaned up packet loss injection on {interface}")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to cleanup packet loss: {e}")

class ServiceChaosInjector:
    """Injects service-level chaos"""
    
    def __init__(self):
        self.docker_client = docker.from_env()
    
    async def kill_service(self, service_name: str, restart_delay: int = 0) -> bool:
        """Kill a service container"""
        try:
            container = self.docker_client.containers.get(service_name)
            container.kill()
            
            logger.warning(f"Killed service: {service_name}")
            
            if restart_delay > 0:
                # Schedule restart
                asyncio.create_task(self._restart_service_after_delay(service_name, restart_delay))
            
            CHAOS_EXPERIMENTS.labels(type='service_kill', status='injected').inc()
            return True
            
        except docker.errors.NotFound:
            logger.error(f"Service not found: {service_name}")
            return False
        except Exception as e:
            logger.error(f"Failed to kill service {service_name}: {e}")
            return False
    
    async def exhaust_cpu(self, target_service: str, duration: int, cpu_percent: int = 90) -> bool:
        """Exhaust CPU resources for a service"""
        try:
            # Use stress command inside container
            container = self.docker_client.containers.get(target_service)
            
            # Calculate number of CPU cores to stress
            cpu_cores = psutil.cpu_count()
            stress_cores = max(1, int(cpu_cores * cpu_percent / 100))
            
            # Run stress command
            stress_cmd = f"stress --cpu {stress_cores} --timeout {duration}s"
            container.exec_run(stress_cmd, detach=True)
            
            logger.warning(f"Injected CPU stress on {target_service} ({cpu_percent}% for {duration}s)")
            
            CHAOS_EXPERIMENTS.labels(type='resource_exhaustion', status='injected').inc()
            return True
            
        except Exception as e:
            logger.error(f"Failed to inject CPU stress: {e}")
            return False
    
    async def exhaust_memory(self, target_service: str, duration: int, memory_mb: int = 1024) -> bool:
        """Exhaust memory resources for a service"""
        try:
            container = self.docker_client.containers.get(target_service)
            
            # Run memory stress
            stress_cmd = f"stress --vm 1 --vm-bytes {memory_mb}M --timeout {duration}s"
            container.exec_run(stress_cmd, detach=True)
            
            logger.warning(f"Injected memory stress on {target_service} ({memory_mb}MB for {duration}s)")
            
            CHAOS_EXPERIMENTS.labels(type='resource_exhaustion', status='injected').inc()
            return True
            
        except Exception as e:
            logger.error(f"Failed to inject memory stress: {e}")
            return False
    
    async def fill_disk(self, target_service: str, size_mb: int, duration: int) -> bool:
        """Fill disk space for a service"""
        try:
            container = self.docker_client.containers.get(target_service)
            
            # Create large file to fill disk
            fill_cmd = f"dd if=/dev/zero of=/tmp/chaos_fill bs=1M count={size_mb}"
            container.exec_run(fill_cmd, detach=True)
            
            logger.warning(f"Filled {size_mb}MB disk space on {target_service}")
            
            # Schedule cleanup
            asyncio.create_task(self._cleanup_disk_fill_after_delay(target_service, duration))
            
            CHAOS_EXPERIMENTS.labels(type='disk_full', status='injected').inc()
            return True
            
        except Exception as e:
            logger.error(f"Failed to fill disk: {e}")
            return False
    
    async def _restart_service_after_delay(self, service_name: str, delay: int):
        """Restart service after delay"""
        await asyncio.sleep(delay)
        try:
            container = self.docker_client.containers.get(service_name)
            container.restart()
            logger.info(f"Restarted service: {service_name}")
        except Exception as e:
            logger.error(f"Failed to restart service {service_name}: {e}")
    
    async def _cleanup_disk_fill_after_delay(self, service_name: str, delay: int):
        """Cleanup disk fill after delay"""
        await asyncio.sleep(delay)
        try:
            container = self.docker_client.containers.get(service_name)
            container.exec_run("rm -f /tmp/chaos_fill")
            logger.info(f"Cleaned up disk fill on {service_name}")
        except Exception as e:
            logger.error(f"Failed to cleanup disk fill: {e}")

class SystemMonitor:
    """Monitors system health during chaos experiments"""
    
    def __init__(self):
        self.service_endpoints = {
            'data-ingestion': 'http://localhost:8080/health',
            'rag-engine': 'http://localhost:8081/health',
            'drift-detection': 'http://localhost:8082/health',
        }
        self.monitoring_active = False
        self.health_data = {}
    
    async def start_monitoring(self):
        """Start continuous health monitoring"""
        self.monitoring_active = True
        asyncio.create_task(self._monitoring_loop())
        logger.info("Started system health monitoring")
    
    async def stop_monitoring(self):
        """Stop health monitoring"""
        self.monitoring_active = False
        logger.info("Stopped system health monitoring")
    
    async def _monitoring_loop(self):
        """Continuous monitoring loop"""
        while self.monitoring_active:
            try:
                await self._check_all_services()
                await asyncio.sleep(5)  # Check every 5 seconds
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(10)
    
    async def _check_all_services(self):
        """Check health of all services"""
        for service, endpoint in self.service_endpoints.items():
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                    async with session.get(endpoint) as response:
                        if response.status == 200:
                            self.health_data[service] = {
                                'status': 'healthy',
                                'response_time': response.headers.get('X-Response-Time', 'unknown'),
                                'timestamp': datetime.now().isoformat(),
                            }
                            SERVICE_AVAILABILITY.labels(service=service).set(1)
                        else:
                            self.health_data[service] = {
                                'status': 'unhealthy',
                                'status_code': response.status,
                                'timestamp': datetime.now().isoformat(),
                            }
                            SERVICE_AVAILABILITY.labels(service=service).set(0)
            
            except asyncio.TimeoutError:
                self.health_data[service] = {
                    'status': 'timeout',
                    'timestamp': datetime.now().isoformat(),
                }
                SERVICE_AVAILABILITY.labels(service=service).set(0)
            
            except Exception as e:
                self.health_data[service] = {
                    'status': 'error',
                    'error': str(e),
                    'timestamp': datetime.now().isoformat(),
                }
                SERVICE_AVAILABILITY.labels(service=service).set(0)
    
    async def get_system_health_score(self) -> float:
        """Calculate overall system health score"""
        if not self.health_data:
            return 0.0
        
        healthy_services = sum(1 for data in self.health_data.values() if data['status'] == 'healthy')
        total_services = len(self.health_data)
        
        return healthy_services / total_services if total_services > 0 else 0.0
    
    async def detect_recovery(self, baseline_health: float, threshold: float = 0.9) -> bool:
        """Detect if system has recovered to baseline health"""
        current_health = await self.get_system_health_score()
        return current_health >= (baseline_health * threshold)

class ChaosController:
    """Main chaos engineering controller"""
    
    def __init__(self):
        self.network_injector = NetworkChaosInjector()
        self.service_injector = ServiceChaosInjector()
        self.system_monitor = SystemMonitor()
        self.active_experiments: Dict[str, ChaosResult] = {}
        self.experiment_queue = []
    
    async def initialize(self):
        """Initialize chaos controller"""
        await self.system_monitor.start_monitoring()
        logger.info("Chaos controller initialized")
    
    async def run_experiment(self, experiment: ChaosExperiment) -> ChaosResult:
        """Run a single chaos experiment"""
        result = ChaosResult(
            experiment_id=experiment.id,
            start_time=datetime.now().isoformat(),
            end_time=None,
            status='running',
            impact_metrics={},
            recovery_time_seconds=None,
            observations=[],
            system_behavior={}
        )
        
        self.active_experiments[experiment.id] = result
        
        try:
            logger.info(f"🔥 Starting chaos experiment: {experiment.name}")
            
            # Record baseline health
            baseline_health = await self.system_monitor.get_system_health_score()
            result.system_behavior['baseline_health'] = baseline_health
            
            # Inject chaos based on experiment type
            injection_success = await self._inject_chaos(experiment)
            
            if not injection_success:
                result.status = 'failed'
                result.observations.append('Failed to inject chaos')
                return result
            
            # Monitor impact during experiment
            await self._monitor_experiment_impact(experiment, result)
            
            # Wait for experiment duration
            await asyncio.sleep(experiment.duration_seconds)
            
            # Measure recovery time
            recovery_start = time.time()
            recovered = await self._wait_for_recovery(experiment, baseline_health)
            recovery_time = time.time() - recovery_start
            
            result.recovery_time_seconds = recovery_time
            result.status = 'completed' if recovered else 'recovery_timeout'
            
            # Record final metrics
            final_health = await self.system_monitor.get_system_health_score()
            result.system_behavior['final_health'] = final_health
            result.system_behavior['health_recovery_ratio'] = final_health / baseline_health if baseline_health > 0 else 0
            
            # Update Prometheus metrics
            SYSTEM_RECOVERY_TIME.observe(recovery_time)
            CHAOS_IMPACT_SCORE.labels(experiment=experiment.id).set(1 - final_health)
            
            logger.info(f"✅ Completed chaos experiment: {experiment.name} (recovery: {recovery_time:.1f}s)")
            
        except Exception as e:
            result.status = 'error'
            result.observations.append(f'Experiment error: {str(e)}')
            logger.error(f"❌ Chaos experiment failed: {e}")
        
        finally:
            result.end_time = datetime.now().isoformat()
            CHAOS_EXPERIMENTS.labels(type=experiment.type.value, status=result.status).inc()
        
        return result
    
    async def _inject_chaos(self, experiment: ChaosExperiment) -> bool:
        """Inject chaos based on experiment type"""
        if experiment.type == ChaosType.NETWORK_PARTITION:
            return await self.network_injector.inject_network_partition(
                experiment.target.value,
                experiment.duration_seconds
            )
        
        elif experiment.type == ChaosType.HIGH_LATENCY:
            return await self.network_injector.inject_high_latency(
                experiment.parameters.get('interface', 'eth0'),
                experiment.parameters.get('delay_ms', 1000),
                experiment.duration_seconds
            )
        
        elif experiment.type == ChaosType.PACKET_LOSS:
            return await self.network_injector.inject_packet_loss(
                experiment.parameters.get('interface', 'eth0'),
                experiment.parameters.get('loss_percent', 10),
                experiment.duration_seconds
            )
        
        elif experiment.type == ChaosType.SERVICE_KILL:
            return await self.service_injector.kill_service(
                experiment.target.value,
                experiment.parameters.get('restart_delay', 30)
            )
        
        elif experiment.type == ChaosType.RESOURCE_EXHAUSTION:
            resource_type = experiment.parameters.get('resource_type', 'cpu')
            if resource_type == 'cpu':
                return await self.service_injector.exhaust_cpu(
                    experiment.target.value,
                    experiment.duration_seconds,
                    experiment.parameters.get('cpu_percent', 90)
                )
            elif resource_type == 'memory':
                return await self.service_injector.exhaust_memory(
                    experiment.target.value,
                    experiment.duration_seconds,
                    experiment.parameters.get('memory_mb', 1024)
                )
        
        elif experiment.type == ChaosType.DISK_FULL:
            return await self.service_injector.fill_disk(
                experiment.target.value,
                experiment.parameters.get('size_mb', 1024),
                experiment.duration_seconds
            )
        
        return False
    
    async def _monitor_experiment_impact(self, experiment: ChaosExperiment, result: ChaosResult):
        """Monitor system impact during experiment"""
        # Record impact metrics every 10 seconds
        for i in range(experiment.duration_seconds // 10):
            await asyncio.sleep(10)
            
            health_score = await self.system_monitor.get_system_health_score()
            result.impact_metrics[f'health_at_{i*10}s'] = health_score
            
            # Record specific observations
            if health_score < 0.5:
                result.observations.append(f'Critical health degradation at {i*10}s: {health_score:.2f}')
            elif health_score < 0.8:
                result.observations.append(f'Health degradation at {i*10}s: {health_score:.2f}')
    
    async def _wait_for_recovery(self, experiment: ChaosExperiment, baseline_health: float, timeout: int = 300) -> bool:
        """Wait for system recovery with timeout"""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if await self.system_monitor.detect_recovery(baseline_health):
                return True
            await asyncio.sleep(5)
        
        return False
    
    async def run_chaos_suite(self) -> List[ChaosResult]:
        """Run a comprehensive suite of chaos experiments"""
        experiments = [
            ChaosExperiment(
                id="network_partition_data_ingestion",
                name="Network Partition - Data Ingestion",
                type=ChaosType.NETWORK_PARTITION,
                target=ChaosTarget.DATA_INGESTION,
                duration_seconds=60,
                parameters={},
                expected_impact="Data ingestion should queue messages and resume after recovery",
                recovery_criteria={'health_threshold': 0.9},
                rollback_commands=[]
            ),
            
            ChaosExperiment(
                id="service_kill_rag_engine",
                name="Service Kill - RAG Engine",
                type=ChaosType.SERVICE_KILL,
                target=ChaosTarget.RAG_ENGINE,
                duration_seconds=30,
                parameters={'restart_delay': 30},
                expected_impact="Search requests should fail gracefully and recover after restart",
                recovery_criteria={'health_threshold': 0.9},
                rollback_commands=[]
            ),
            
            ChaosExperiment(
                id="cpu_exhaustion_drift_detection",
                name="CPU Exhaustion - Drift Detection",
                type=ChaosType.RESOURCE_EXHAUSTION,
                target=ChaosTarget.DRIFT_DETECTION,
                duration_seconds=120,
                parameters={'resource_type': 'cpu', 'cpu_percent': 95},
                expected_impact="Drift detection should slow down but continue processing",
                recovery_criteria={'health_threshold': 0.8},
                rollback_commands=[]
            ),
            
            ChaosExperiment(
                id="high_latency_network",
                name="High Network Latency",
                type=ChaosType.HIGH_LATENCY,
                target=ChaosTarget.DATA_INGESTION,
                duration_seconds=90,
                parameters={'interface': 'eth0', 'delay_ms': 2000},
                expected_impact="Request timeouts should increase but system should remain functional",
                recovery_criteria={'health_threshold': 0.7},
                rollback_commands=[]
            ),
        ]
        
        results = []
        
        for experiment in experiments:
            logger.info(f"Running experiment: {experiment.name}")
            result = await self.run_experiment(experiment)
            results.append(result)
            
            # Wait between experiments for system stabilization
            await asyncio.sleep(30)
        
        return results
    
    async def generate_chaos_report(self, results: List[ChaosResult]) -> Dict[str, Any]:
        """Generate comprehensive chaos engineering report"""
        total_experiments = len(results)
        successful_experiments = sum(1 for r in results if r.status == 'completed')
        
        avg_recovery_time = sum(
            r.recovery_time_seconds for r in results 
            if r.recovery_time_seconds is not None
        ) / len([r for r in results if r.recovery_time_seconds is not None])
        
        report = {
            'summary': {
                'total_experiments': total_experiments,
                'successful_experiments': successful_experiments,
                'success_rate': successful_experiments / total_experiments if total_experiments > 0 else 0,
                'average_recovery_time_seconds': avg_recovery_time,
            },
            
            'experiments': [asdict(result) for result in results],
            
            'system_resilience_score': successful_experiments / total_experiments if total_experiments > 0 else 0,
            
            'recommendations': [
                'Implement circuit breakers for external service calls',
                'Add health check retries with exponential backoff',
                'Improve graceful degradation for non-critical features',
                'Add automated recovery procedures for common failures',
                'Implement better resource monitoring and alerting',
            ],
            
            'action_items': [
                {
                    'item': 'Add network partition detection and recovery',
                    'priority': 'High',
                    'estimated_effort': '2 weeks',
                },
                {
                    'item': 'Implement service mesh for better resilience',
                    'priority': 'Medium',
                    'estimated_effort': '4 weeks',
                },
                {
                    'item': 'Add chaos engineering to CI/CD pipeline',
                    'priority': 'Medium',
                    'estimated_effort': '1 week',
                },
            ]
        }
        
        return report
    
    async def cleanup(self):
        """Cleanup chaos controller"""
        await self.system_monitor.stop_monitoring()
        logger.info("Chaos controller cleaned up")

# Main execution
async def main():
    """Run chaos engineering suite"""
    controller = ChaosController()
    
    try:
        await controller.initialize()
        
        # Run chaos experiments
        results = await controller.run_chaos_suite()
        
        # Generate report
        report = await controller.generate_chaos_report(results)
        
        # Save report
        with open(f'chaos_report_{int(time.time())}.json', 'w') as f:
            json.dump(report, f, indent=2)
        
        print("\n" + "="*80)
        print("🔥 CHAOS ENGINEERING REPORT")
        print("="*80)
        print(f"Total Experiments: {report['summary']['total_experiments']}")
        print(f"Success Rate: {report['summary']['success_rate']:.1%}")
        print(f"Average Recovery Time: {report['summary']['average_recovery_time_seconds']:.1f}s")
        print(f"System Resilience Score: {report['system_resilience_score']:.2f}")
        print("\nRecommendations:")
        for rec in report['recommendations']:
            print(f"  • {rec}")
        print("="*80)
        
    finally:
        await controller.cleanup()

if __name__ == "__main__":
    asyncio.run(main())

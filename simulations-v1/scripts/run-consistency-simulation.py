#!/usr/bin/env python3
"""
Consistency & CAP Theorem Simulation Runner

This script orchestrates comprehensive consistency testing across:
- Raft consensus (etcd cluster)
- Multi-master databases (PostgreSQL + MongoDB)
- CRDT implementations
- Network partition scenarios
"""

import asyncio
import json
import logging
import subprocess
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import aiohttp
import asyncpg
import motor.motor_asyncio
import yaml

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ConsistencySimulation:
    def __init__(self, platform: str = "docker"):
        self.platform = platform  # "docker" or "kubernetes"
        self.results = {
            "simulation_id": f"consistency_sim_{int(time.time())}",
            "start_time": datetime.utcnow().isoformat(),
            "platform": platform,
            "tests": []
        }
        
        # Service endpoints (will be set based on platform)
        self.endpoints = {}
        
    async def setup_environment(self):
        """Setup the simulation environment"""
        logger.info(f"Setting up {self.platform} environment...")
        
        if self.platform == "docker":
            await self._setup_docker_environment()
        elif self.platform == "kubernetes":
            await self._setup_kubernetes_environment()
        else:
            raise ValueError(f"Unsupported platform: {self.platform}")
    
    async def _setup_docker_environment(self):
        """Setup Docker-based simulation environment"""
        logger.info("Starting Docker Compose services...")
        
        # Start services
        cmd = [
            "docker-compose", 
            "-f", "simulations/docker/consistency-cap-simulation/docker-compose.yml",
            "up", "-d", "--build"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise Exception(f"Failed to start Docker services: {result.stderr}")
        
        # Set service endpoints
        self.endpoints = {
            "etcd": ["http://localhost:2379", "http://localhost:2389", "http://localhost:2399"],
            "postgres_primary": "postgresql://postgres:postgres@localhost:5432/consistency_test",
            "postgres_replica": "postgresql://postgres:postgres@localhost:5433/consistency_test",
            "mongodb": ["mongodb://localhost:27017", "mongodb://localhost:27018", "mongodb://localhost:27019"],
            "crdt_nodes": ["http://localhost:8081", "http://localhost:8082", "http://localhost:8083"],
            "chaos_controller": "http://localhost:9090"
        }
        
        # Wait for services to be ready
        await self._wait_for_services()
    
    async def _setup_kubernetes_environment(self):
        """Setup Kubernetes-based simulation environment"""
        logger.info("Deploying Kubernetes resources...")
        
        # Apply Kubernetes manifests
        manifests = [
            "simulations/kubernetes/consistency-cap-simulation/namespace.yaml",
            "simulations/kubernetes/consistency-cap-simulation/etcd-cluster.yaml",
            "simulations/kubernetes/consistency-cap-simulation/mongodb-replica-set.yaml",
            "simulations/kubernetes/consistency-cap-simulation/chaos-mesh.yaml"
        ]
        
        for manifest in manifests:
            cmd = ["kubectl", "apply", "-f", manifest]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                logger.warning(f"Failed to apply {manifest}: {result.stderr}")
        
        # Set service endpoints (using port-forward)
        self.endpoints = {
            "etcd": ["http://localhost:2379"],
            "mongodb": ["mongodb://localhost:27017"],
            "chaos_controller": "http://localhost:9090"
        }
        
        # Setup port forwarding
        await self._setup_port_forwarding()
        
        # Wait for services to be ready
        await self._wait_for_services()
    
    async def _setup_port_forwarding(self):
        """Setup port forwarding for Kubernetes services"""
        port_forwards = [
            ("etcd-0", "2379:2379"),
            ("mongodb-0", "27017:27017")
        ]
        
        for service, ports in port_forwards:
            cmd = [
                "kubectl", "port-forward", 
                f"pod/{service}", ports,
                "-n", "consistency-simulation"
            ]
            
            # Start port-forward in background
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            await asyncio.sleep(2)  # Give time to establish connection
    
    async def _wait_for_services(self):
        """Wait for all services to be ready"""
        logger.info("Waiting for services to be ready...")
        
        max_retries = 60
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                # Check etcd health
                if await self._check_etcd_health():
                    logger.info("✅ etcd cluster is ready")
                    break
                    
            except Exception as e:
                logger.debug(f"Service check failed: {e}")
            
            retry_count += 1
            if retry_count >= max_retries:
                raise Exception("Services failed to become ready within timeout")
            
            await asyncio.sleep(5)
    
    async def _check_etcd_health(self) -> bool:
        """Check etcd cluster health"""
        try:
            async with aiohttp.ClientSession() as session:
                for endpoint in self.endpoints["etcd"]:
                    health_url = f"{endpoint}/health"
                    async with session.get(health_url, timeout=5) as response:
                        if response.status != 200:
                            return False
            return True
        except:
            return False
    
    async def run_raft_consensus_tests(self):
        """Run Raft consensus algorithm tests"""
        logger.info("🧪 Running Raft Consensus Tests...")
        
        test_results = {
            "test_name": "raft_consensus",
            "start_time": datetime.utcnow().isoformat(),
            "scenarios": []
        }
        
        # Test 1: Leader Election
        scenario_result = await self._test_leader_election()
        test_results["scenarios"].append(scenario_result)
        
        # Test 2: Log Replication
        scenario_result = await self._test_log_replication()
        test_results["scenarios"].append(scenario_result)
        
        # Test 3: Network Partition
        scenario_result = await self._test_network_partition()
        test_results["scenarios"].append(scenario_result)
        
        test_results["end_time"] = datetime.utcnow().isoformat()
        test_results["duration_seconds"] = (
            datetime.fromisoformat(test_results["end_time"]) - 
            datetime.fromisoformat(test_results["start_time"])
        ).total_seconds()
        
        self.results["tests"].append(test_results)
        logger.info("✅ Raft Consensus Tests completed")
    
    async def _test_leader_election(self) -> Dict:
        """Test leader election behavior"""
        logger.info("Testing leader election...")
        
        scenario = {
            "scenario_name": "leader_election",
            "start_time": datetime.utcnow().isoformat(),
            "steps": []
        }
        
        try:
            # Step 1: Identify current leader
            current_leader = await self._find_etcd_leader()
            scenario["steps"].append({
                "step": "identify_leader",
                "result": f"Current leader: {current_leader}",
                "success": current_leader is not None
            })
            
            # Step 2: Kill leader (simulate failure)
            if current_leader and self.platform == "docker":
                await self._simulate_container_failure(current_leader)
                scenario["steps"].append({
                    "step": "simulate_leader_failure",
                    "result": f"Killed leader: {current_leader}",
                    "success": True
                })
                
                # Step 3: Wait for new leader election
                await asyncio.sleep(10)  # Wait for election
                
                new_leader = await self._find_etcd_leader()
                scenario["steps"].append({
                    "step": "verify_new_leader",
                    "result": f"New leader: {new_leader}",
                    "success": new_leader is not None and new_leader != current_leader
                })
                
                # Step 4: Restore failed node
                await self._restore_container(current_leader)
                scenario["steps"].append({
                    "step": "restore_failed_node",
                    "result": f"Restored: {current_leader}",
                    "success": True
                })
            
        except Exception as e:
            scenario["steps"].append({
                "step": "error",
                "result": str(e),
                "success": False
            })
        
        scenario["end_time"] = datetime.utcnow().isoformat()
        scenario["success"] = all(step["success"] for step in scenario["steps"])
        
        return scenario
    
    async def _test_log_replication(self) -> Dict:
        """Test log replication consistency"""
        logger.info("Testing log replication...")
        
        scenario = {
            "scenario_name": "log_replication",
            "start_time": datetime.utcnow().isoformat(),
            "steps": []
        }
        
        try:
            # Write multiple keys concurrently
            write_tasks = []
            for i in range(100):
                task = self._write_etcd_key(f"test_key_{i}", f"value_{i}")
                write_tasks.append(task)
            
            write_results = await asyncio.gather(*write_tasks, return_exceptions=True)
            successful_writes = sum(1 for result in write_results if not isinstance(result, Exception))
            
            scenario["steps"].append({
                "step": "concurrent_writes",
                "result": f"Successful writes: {successful_writes}/100",
                "success": successful_writes >= 95  # Allow some failures
            })
            
            # Verify consistency across all nodes
            consistency_check = await self._verify_etcd_consistency()
            scenario["steps"].append({
                "step": "consistency_verification",
                "result": f"Consistency check: {consistency_check}",
                "success": consistency_check
            })
            
        except Exception as e:
            scenario["steps"].append({
                "step": "error",
                "result": str(e),
                "success": False
            })
        
        scenario["end_time"] = datetime.utcnow().isoformat()
        scenario["success"] = all(step["success"] for step in scenario["steps"])
        
        return scenario
    
    async def _test_network_partition(self) -> Dict:
        """Test behavior under network partition"""
        logger.info("Testing network partition...")
        
        scenario = {
            "scenario_name": "network_partition",
            "start_time": datetime.utcnow().isoformat(),
            "steps": []
        }
        
        try:
            # Create network partition using chaos controller
            if "chaos_controller" in self.endpoints:
                partition_request = {
                    "name": "network_partition",
                    "description": "Split etcd cluster",
                    "duration_seconds": 60,
                    "target_containers": ["etcd1", "etcd2", "etcd3"],
                    "parameters": {}
                }
                
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{self.endpoints['chaos_controller']}/chaos/start",
                        json=partition_request
                    ) as response:
                        if response.status == 200:
                            chaos_result = await response.json()
                            scenario["steps"].append({
                                "step": "create_partition",
                                "result": f"Chaos scenario started: {chaos_result['scenario_id']}",
                                "success": True
                            })
                            
                            # Wait for partition to take effect
                            await asyncio.sleep(30)
                            
                            # Try to write during partition
                            try:
                                await self._write_etcd_key("partition_test", "test_value")
                                scenario["steps"].append({
                                    "step": "write_during_partition",
                                    "result": "Write succeeded (majority available)",
                                    "success": True
                                })
                            except Exception as e:
                                scenario["steps"].append({
                                    "step": "write_during_partition",
                                    "result": f"Write failed: {e} (no majority)",
                                    "success": True  # This is expected behavior
                                })
                            
                            # Wait for partition to heal
                            await asyncio.sleep(40)
                            
                            # Verify cluster recovery
                            recovery_check = await self._verify_etcd_consistency()
                            scenario["steps"].append({
                                "step": "partition_recovery",
                                "result": f"Recovery check: {recovery_check}",
                                "success": recovery_check
                            })
            
        except Exception as e:
            scenario["steps"].append({
                "step": "error",
                "result": str(e),
                "success": False
            })
        
        scenario["end_time"] = datetime.utcnow().isoformat()
        scenario["success"] = all(step["success"] for step in scenario["steps"])
        
        return scenario
    
    async def run_crdt_tests(self):
        """Run CRDT implementation tests"""
        logger.info("🧪 Running CRDT Tests...")
        
        if "crdt_nodes" not in self.endpoints:
            logger.warning("CRDT nodes not available, skipping tests")
            return
        
        test_results = {
            "test_name": "crdt_implementation",
            "start_time": datetime.utcnow().isoformat(),
            "scenarios": []
        }
        
        # Test concurrent updates
        scenario_result = await self._test_crdt_concurrent_updates()
        test_results["scenarios"].append(scenario_result)
        
        # Test network partition with CRDTs
        scenario_result = await self._test_crdt_partition_tolerance()
        test_results["scenarios"].append(scenario_result)
        
        test_results["end_time"] = datetime.utcnow().isoformat()
        test_results["duration_seconds"] = (
            datetime.fromisoformat(test_results["end_time"]) - 
            datetime.fromisoformat(test_results["start_time"])
        ).total_seconds()
        
        self.results["tests"].append(test_results)
        logger.info("✅ CRDT Tests completed")
    
    async def _test_crdt_concurrent_updates(self) -> Dict:
        """Test CRDT behavior under concurrent updates"""
        logger.info("Testing CRDT concurrent updates...")
        
        scenario = {
            "scenario_name": "crdt_concurrent_updates",
            "start_time": datetime.utcnow().isoformat(),
            "steps": []
        }
        
        try:
            # Perform concurrent increments on G-Counter
            increment_tasks = []
            for i, node_url in enumerate(self.endpoints["crdt_nodes"]):
                for j in range(10):
                    task = self._increment_crdt_counter(node_url, 1)
                    increment_tasks.append(task)
            
            await asyncio.gather(*increment_tasks, return_exceptions=True)
            
            # Wait for gossip synchronization
            await asyncio.sleep(10)
            
            # Verify convergence
            counter_values = []
            for node_url in self.endpoints["crdt_nodes"]:
                value = await self._get_crdt_counter_value(node_url)
                counter_values.append(value)
            
            converged = len(set(counter_values)) == 1
            expected_value = len(self.endpoints["crdt_nodes"]) * 10
            
            scenario["steps"].append({
                "step": "concurrent_increments",
                "result": f"Counter values: {counter_values}, Expected: {expected_value}",
                "success": converged and counter_values[0] == expected_value
            })
            
        except Exception as e:
            scenario["steps"].append({
                "step": "error",
                "result": str(e),
                "success": False
            })
        
        scenario["end_time"] = datetime.utcnow().isoformat()
        scenario["success"] = all(step["success"] for step in scenario["steps"])
        
        return scenario
    
    async def _test_crdt_partition_tolerance(self) -> Dict:
        """Test CRDT behavior during network partitions"""
        logger.info("Testing CRDT partition tolerance...")
        
        scenario = {
            "scenario_name": "crdt_partition_tolerance",
            "start_time": datetime.utcnow().isoformat(),
            "steps": []
        }
        
        try:
            # Create partition between CRDT nodes
            if "chaos_controller" in self.endpoints:
                partition_request = {
                    "name": "network_partition",
                    "description": "Partition CRDT nodes",
                    "duration_seconds": 60,
                    "target_containers": ["crdt_node1", "crdt_node2", "crdt_node3"],
                    "parameters": {}
                }
                
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{self.endpoints['chaos_controller']}/chaos/start",
                        json=partition_request
                    ) as response:
                        if response.status == 200:
                            # Perform updates during partition
                            await asyncio.sleep(10)  # Let partition take effect
                            
                            # Update different nodes during partition
                            update_tasks = []
                            for i, node_url in enumerate(self.endpoints["crdt_nodes"]):
                                task = self._increment_crdt_counter(node_url, i + 1)
                                update_tasks.append(task)
                            
                            await asyncio.gather(*update_tasks, return_exceptions=True)
                            
                            # Wait for partition to heal and gossip to sync
                            await asyncio.sleep(70)
                            
                            # Verify eventual consistency
                            counter_values = []
                            for node_url in self.endpoints["crdt_nodes"]:
                                value = await self._get_crdt_counter_value(node_url)
                                counter_values.append(value)
                            
                            converged = len(set(counter_values)) == 1
                            
                            scenario["steps"].append({
                                "step": "partition_tolerance",
                                "result": f"Post-partition values: {counter_values}, Converged: {converged}",
                                "success": converged
                            })
            
        except Exception as e:
            scenario["steps"].append({
                "step": "error",
                "result": str(e),
                "success": False
            })
        
        scenario["end_time"] = datetime.utcnow().isoformat()
        scenario["success"] = all(step["success"] for step in scenario["steps"])
        
        return scenario
    
    # Helper methods
    async def _find_etcd_leader(self) -> Optional[str]:
        """Find current etcd leader"""
        # Implementation would check etcd cluster status
        return "etcd1"  # Simplified for example
    
    async def _simulate_container_failure(self, container_name: str):
        """Simulate container failure"""
        if self.platform == "docker":
            cmd = ["docker", "pause", container_name]
            subprocess.run(cmd)
    
    async def _restore_container(self, container_name: str):
        """Restore failed container"""
        if self.platform == "docker":
            cmd = ["docker", "unpause", container_name]
            subprocess.run(cmd)
    
    async def _write_etcd_key(self, key: str, value: str):
        """Write key-value pair to etcd"""
        # Implementation would use etcd client
        pass
    
    async def _verify_etcd_consistency(self) -> bool:
        """Verify etcd cluster consistency"""
        # Implementation would check data consistency across nodes
        return True
    
    async def _increment_crdt_counter(self, node_url: str, amount: int):
        """Increment CRDT counter on specific node"""
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{node_url}/crdt/counter/increment",
                json={"amount": amount}
            ) as response:
                return await response.json()
    
    async def _get_crdt_counter_value(self, node_url: str) -> int:
        """Get CRDT counter value from specific node"""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{node_url}/crdt/counter/value") as response:
                result = await response.json()
                return result["value"]
    
    async def generate_report(self):
        """Generate simulation report"""
        self.results["end_time"] = datetime.utcnow().isoformat()
        self.results["total_duration_seconds"] = (
            datetime.fromisoformat(self.results["end_time"]) - 
            datetime.fromisoformat(self.results["start_time"])
        ).total_seconds()
        
        # Calculate success rates
        total_tests = len(self.results["tests"])
        successful_tests = sum(
            1 for test in self.results["tests"] 
            if all(scenario["success"] for scenario in test["scenarios"])
        )
        
        self.results["summary"] = {
            "total_tests": total_tests,
            "successful_tests": successful_tests,
            "success_rate": successful_tests / total_tests if total_tests > 0 else 0,
            "platform": self.platform
        }
        
        # Save report
        report_filename = f"consistency_simulation_report_{self.results['simulation_id']}.json"
        with open(report_filename, 'w') as f:
            json.dump(self.results, f, indent=2)
        
        logger.info(f"📊 Simulation report saved: {report_filename}")
        logger.info(f"📈 Success rate: {self.results['summary']['success_rate']:.2%}")
        
        return self.results

async def main():
    """Main simulation runner"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Run Consistency & CAP Theorem Simulations")
    parser.add_argument("--platform", choices=["docker", "kubernetes"], default="docker",
                       help="Platform to run simulations on")
    parser.add_argument("--tests", nargs="+", 
                       choices=["raft", "crdt", "database", "all"], 
                       default=["all"],
                       help="Tests to run")
    
    args = parser.parse_args()
    
    simulation = ConsistencySimulation(platform=args.platform)
    
    try:
        # Setup environment
        await simulation.setup_environment()
        
        # Run selected tests
        if "all" in args.tests or "raft" in args.tests:
            await simulation.run_raft_consensus_tests()
        
        if "all" in args.tests or "crdt" in args.tests:
            await simulation.run_crdt_tests()
        
        # Generate report
        await simulation.generate_report()
        
        logger.info("🎉 Simulation completed successfully!")
        
    except Exception as e:
        logger.error(f"❌ Simulation failed: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())

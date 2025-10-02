#!/usr/bin/env python3
"""
Chaos Engineering Controller for Consistency & CAP Theorem Simulations

This controller implements various chaos scenarios to test distributed systems:
- Network partitions
- Leader failures
- Replica lag simulation
- Clock skew injection
"""

import asyncio
import json
import logging
import random
import subprocess
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import docker
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Chaos Engineering Controller", version="1.0.0")

# Docker client
docker_client = docker.from_env()

class ChaosScenario(BaseModel):
    name: str
    description: str
    duration_seconds: int
    target_containers: List[str]
    parameters: Dict[str, str] = {}

class ChaosController:
    def __init__(self):
        self.active_scenarios: Dict[str, Dict] = {}
        self.scenario_history: List[Dict] = []
        
    async def start_scenario(self, scenario: ChaosScenario) -> str:
        """Start a chaos scenario"""
        scenario_id = f"{scenario.name}_{int(time.time())}"
        
        logger.info(f"Starting chaos scenario: {scenario_id}")
        
        # Record scenario start
        scenario_record = {
            "id": scenario_id,
            "scenario": scenario.dict(),
            "start_time": datetime.utcnow().isoformat(),
            "status": "running",
            "effects": []
        }
        
        self.active_scenarios[scenario_id] = scenario_record
        
        # Execute scenario based on type
        if scenario.name == "network_partition":
            await self._create_network_partition(scenario_id, scenario)
        elif scenario.name == "leader_failure":
            await self._simulate_leader_failure(scenario_id, scenario)
        elif scenario.name == "replica_lag":
            await self._simulate_replica_lag(scenario_id, scenario)
        elif scenario.name == "clock_skew":
            await self._inject_clock_skew(scenario_id, scenario)
        else:
            raise HTTPException(status_code=400, f"Unknown scenario: {scenario.name}")
        
        # Schedule scenario cleanup
        asyncio.create_task(self._cleanup_scenario(scenario_id, scenario.duration_seconds))
        
        return scenario_id
    
    async def _create_network_partition(self, scenario_id: str, scenario: ChaosScenario):
        """Create network partition between containers"""
        logger.info(f"Creating network partition for scenario {scenario_id}")
        
        containers = scenario.target_containers
        if len(containers) < 2:
            raise ValueError("Network partition requires at least 2 containers")
        
        # Split containers into two partitions
        partition1 = containers[:len(containers)//2]
        partition2 = containers[len(containers)//2:]
        
        effects = []
        
        # Block traffic between partitions
        for container1 in partition1:
            for container2 in partition2:
                try:
                    # Get container IPs
                    c1 = docker_client.containers.get(container1)
                    c2 = docker_client.containers.get(container2)
                    
                    c1_ip = c1.attrs['NetworkSettings']['IPAddress']
                    c2_ip = c2.attrs['NetworkSettings']['IPAddress']
                    
                    # Block traffic using iptables
                    block_cmd1 = f"iptables -A INPUT -s {c2_ip} -j DROP"
                    block_cmd2 = f"iptables -A INPUT -s {c1_ip} -j DROP"
                    
                    c1.exec_run(block_cmd1, privileged=True)
                    c2.exec_run(block_cmd2, privileged=True)
                    
                    effects.append({
                        "type": "network_block",
                        "source": container1,
                        "target": container2,
                        "timestamp": datetime.utcnow().isoformat()
                    })
                    
                    logger.info(f"Blocked traffic between {container1} and {container2}")
                    
                except Exception as e:
                    logger.error(f"Failed to block traffic between {container1} and {container2}: {e}")
        
        self.active_scenarios[scenario_id]["effects"] = effects
    
    async def _simulate_leader_failure(self, scenario_id: str, scenario: ChaosScenario):
        """Simulate leader failure by stopping leader container"""
        logger.info(f"Simulating leader failure for scenario {scenario_id}")
        
        # For etcd cluster, find the current leader
        leader_container = await self._find_etcd_leader(scenario.target_containers)
        
        if leader_container:
            try:
                container = docker_client.containers.get(leader_container)
                container.pause()
                
                effect = {
                    "type": "container_pause",
                    "container": leader_container,
                    "timestamp": datetime.utcnow().isoformat()
                }
                
                self.active_scenarios[scenario_id]["effects"] = [effect]
                logger.info(f"Paused leader container: {leader_container}")
                
            except Exception as e:
                logger.error(f"Failed to pause leader container {leader_container}: {e}")
    
    async def _simulate_replica_lag(self, scenario_id: str, scenario: ChaosScenario):
        """Simulate replica lag by introducing network delays"""
        logger.info(f"Simulating replica lag for scenario {scenario_id}")
        
        delay_ms = scenario.parameters.get("delay_ms", "1000")
        effects = []
        
        for container_name in scenario.target_containers:
            try:
                container = docker_client.containers.get(container_name)
                
                # Add network delay using tc (traffic control)
                delay_cmd = f"tc qdisc add dev eth0 root netem delay {delay_ms}ms"
                container.exec_run(delay_cmd, privileged=True)
                
                effects.append({
                    "type": "network_delay",
                    "container": container_name,
                    "delay_ms": delay_ms,
                    "timestamp": datetime.utcnow().isoformat()
                })
                
                logger.info(f"Added {delay_ms}ms delay to {container_name}")
                
            except Exception as e:
                logger.error(f"Failed to add delay to {container_name}: {e}")
        
        self.active_scenarios[scenario_id]["effects"] = effects
    
    async def _inject_clock_skew(self, scenario_id: str, scenario: ChaosScenario):
        """Inject clock skew by adjusting container system time"""
        logger.info(f"Injecting clock skew for scenario {scenario_id}")
        
        skew_seconds = int(scenario.parameters.get("skew_seconds", "60"))
        effects = []
        
        for container_name in scenario.target_containers:
            try:
                container = docker_client.containers.get(container_name)
                
                # Adjust system time
                skew_direction = random.choice([1, -1])
                actual_skew = skew_seconds * skew_direction
                
                time_cmd = f"date -s '{actual_skew} seconds'"
                container.exec_run(time_cmd, privileged=True)
                
                effects.append({
                    "type": "clock_skew",
                    "container": container_name,
                    "skew_seconds": actual_skew,
                    "timestamp": datetime.utcnow().isoformat()
                })
                
                logger.info(f"Applied {actual_skew}s clock skew to {container_name}")
                
            except Exception as e:
                logger.error(f"Failed to apply clock skew to {container_name}: {e}")
        
        self.active_scenarios[scenario_id]["effects"] = effects
    
    async def _find_etcd_leader(self, containers: List[str]) -> Optional[str]:
        """Find the current etcd leader"""
        for container_name in containers:
            try:
                container = docker_client.containers.get(container_name)
                result = container.exec_run("etcdctl endpoint status --write-out=json")
                
                if result.exit_code == 0:
                    status = json.loads(result.output.decode())
                    if status[0]["Status"]["leader"] == status[0]["Status"]["header"]["member_id"]:
                        return container_name
                        
            except Exception as e:
                logger.error(f"Failed to check leader status for {container_name}: {e}")
        
        return None
    
    async def _cleanup_scenario(self, scenario_id: str, duration_seconds: int):
        """Clean up scenario after specified duration"""
        await asyncio.sleep(duration_seconds)
        
        logger.info(f"Cleaning up scenario: {scenario_id}")
        
        if scenario_id not in self.active_scenarios:
            return
        
        scenario_record = self.active_scenarios[scenario_id]
        effects = scenario_record.get("effects", [])
        
        # Reverse all effects
        for effect in effects:
            try:
                if effect["type"] == "network_block":
                    # Remove iptables rules
                    container = docker_client.containers.get(effect["source"])
                    container.exec_run("iptables -F", privileged=True)
                    
                elif effect["type"] == "container_pause":
                    # Unpause container
                    container = docker_client.containers.get(effect["container"])
                    container.unpause()
                    
                elif effect["type"] == "network_delay":
                    # Remove network delay
                    container = docker_client.containers.get(effect["container"])
                    container.exec_run("tc qdisc del dev eth0 root", privileged=True)
                    
                elif effect["type"] == "clock_skew":
                    # Reset system time (sync with host)
                    container = docker_client.containers.get(effect["container"])
                    container.exec_run("ntpdate -s time.nist.gov", privileged=True)
                    
            except Exception as e:
                logger.error(f"Failed to cleanup effect {effect}: {e}")
        
        # Mark scenario as completed
        scenario_record["status"] = "completed"
        scenario_record["end_time"] = datetime.utcnow().isoformat()
        
        # Move to history
        self.scenario_history.append(scenario_record)
        del self.active_scenarios[scenario_id]
        
        logger.info(f"Scenario {scenario_id} cleanup completed")

# Global chaos controller instance
chaos_controller = ChaosController()

@app.post("/chaos/start")
async def start_chaos_scenario(scenario: ChaosScenario):
    """Start a chaos engineering scenario"""
    try:
        scenario_id = await chaos_controller.start_scenario(scenario)
        return {"scenario_id": scenario_id, "status": "started"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/chaos/scenarios")
async def list_active_scenarios():
    """List all active chaos scenarios"""
    return {
        "active_scenarios": chaos_controller.active_scenarios,
        "scenario_count": len(chaos_controller.active_scenarios)
    }

@app.get("/chaos/history")
async def get_scenario_history():
    """Get history of completed scenarios"""
    return {
        "completed_scenarios": chaos_controller.scenario_history,
        "total_completed": len(chaos_controller.scenario_history)
    }

@app.delete("/chaos/scenarios/{scenario_id}")
async def stop_scenario(scenario_id: str):
    """Manually stop a running scenario"""
    if scenario_id not in chaos_controller.active_scenarios:
        raise HTTPException(status_code=404, detail="Scenario not found")
    
    # Trigger immediate cleanup
    asyncio.create_task(chaos_controller._cleanup_scenario(scenario_id, 0))
    
    return {"message": f"Scenario {scenario_id} cleanup initiated"}

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "active_scenarios": len(chaos_controller.active_scenarios)
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)

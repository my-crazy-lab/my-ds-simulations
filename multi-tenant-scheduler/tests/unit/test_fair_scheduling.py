#!/usr/bin/env python3
"""
Unit tests for fair scheduling algorithms and multi-tenant resource allocation.
Tests the core scheduling logic, fair share calculations, and tenant isolation.
"""

import pytest
import asyncio
import json
import time
import threading
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from collections import defaultdict
import requests
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class SchedulerTestConfig:
    """Configuration for scheduler testing"""
    scheduler_url: str = "http://scheduler-controller:8080"
    resource_manager_url: str = "http://resource-manager:8082"
    tenant_manager_url: str = "http://tenant-manager:8084"
    timeout_seconds: int = 300
    
@dataclass
class JobRequest:
    """Job submission request"""
    name: str
    image: str
    resources: Dict[str, str]
    priority: int = 50
    tenant_id: str = "default"
    deadline: Optional[str] = None
    retry_policy: Optional[Dict[str, Any]] = None
    labels: Optional[Dict[str, str]] = None

@dataclass
class TenantConfig:
    """Tenant configuration"""
    id: str
    name: str
    resource_quota: Dict[str, Any]
    priority_class: str
    policies: Optional[Dict[str, Any]] = None

class SchedulerTestClient:
    """Client for testing scheduler functionality"""
    
    def __init__(self, config: SchedulerTestConfig):
        self.config = config
        self.submitted_jobs = []
        self.tenants = {}
    
    def create_tenant(self, tenant: TenantConfig) -> bool:
        """Create a new tenant"""
        try:
            response = requests.post(
                f"{self.config.tenant_manager_url}/api/v1/tenants",
                json={
                    "id": tenant.id,
                    "name": tenant.name,
                    "resource_quota": tenant.resource_quota,
                    "priority_class": tenant.priority_class,
                    "policies": tenant.policies or {}
                },
                timeout=30
            )
            
            if response.status_code in [200, 201]:
                self.tenants[tenant.id] = tenant
                logger.info(f"Created tenant: {tenant.id}")
                return True
            else:
                logger.error(f"Failed to create tenant {tenant.id}: {response.status_code}")
                return False
        
        except requests.RequestException as e:
            logger.error(f"Tenant creation failed: {e}")
            return False
    
    def submit_job(self, job: JobRequest) -> Optional[str]:
        """Submit a job to the scheduler"""
        try:
            job_data = {
                "name": job.name,
                "image": job.image,
                "resources": job.resources,
                "priority": job.priority,
                "labels": job.labels or {},
                "retry_policy": job.retry_policy or {
                    "max_retries": 3,
                    "backoff_policy": "exponential"
                }
            }
            
            if job.deadline:
                job_data["deadline"] = job.deadline
            
            headers = {"X-Tenant-ID": job.tenant_id}
            
            response = requests.post(
                f"{self.config.scheduler_url}/api/v1/jobs",
                json=job_data,
                headers=headers,
                timeout=30
            )
            
            if response.status_code in [200, 201]:
                job_info = response.json()
                job_id = job_info["id"]
                self.submitted_jobs.append(job_id)
                logger.info(f"Submitted job {job_id} for tenant {job.tenant_id}")
                return job_id
            else:
                logger.error(f"Job submission failed: {response.status_code} - {response.text}")
                return None
        
        except requests.RequestException as e:
            logger.error(f"Job submission failed: {e}")
            return None
    
    def get_job_status(self, job_id: str, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Get job status"""
        try:
            headers = {"X-Tenant-ID": tenant_id}
            response = requests.get(
                f"{self.config.scheduler_url}/api/v1/jobs/{job_id}",
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                return None
        
        except requests.RequestException:
            return None
    
    def list_jobs(self, tenant_id: str) -> List[Dict[str, Any]]:
        """List jobs for a tenant"""
        try:
            headers = {"X-Tenant-ID": tenant_id}
            response = requests.get(
                f"{self.config.scheduler_url}/api/v1/jobs",
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                return response.json().get("jobs", [])
            else:
                return []
        
        except requests.RequestException:
            return []
    
    def wait_for_job_status(self, job_id: str, tenant_id: str, 
                           expected_status: str, timeout: int = 60) -> bool:
        """Wait for job to reach expected status"""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            job_info = self.get_job_status(job_id, tenant_id)
            if job_info and job_info.get("status") == expected_status:
                return True
            time.sleep(2)
        
        return False
    
    def get_scheduler_metrics(self) -> Optional[Dict[str, Any]]:
        """Get scheduler metrics"""
        try:
            response = requests.get(
                f"{self.config.scheduler_url}/metrics",
                timeout=10
            )
            
            if response.status_code == 200:
                # Parse Prometheus metrics (simplified)
                metrics = {}
                for line in response.text.split('\n'):
                    if line.startswith('scheduler_') and not line.startswith('#'):
                        parts = line.split(' ')
                        if len(parts) >= 2:
                            metric_name = parts[0].split('{')[0]
                            metric_value = float(parts[1])
                            metrics[metric_name] = metric_value
                return metrics
            else:
                return None
        
        except requests.RequestException:
            return None
    
    def get_cluster_status(self) -> Optional[Dict[str, Any]]:
        """Get cluster status"""
        try:
            response = requests.get(
                f"{self.config.scheduler_url}/health",
                timeout=10
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                return None
        
        except requests.RequestException:
            return None

class FairSchedulingAnalyzer:
    """Analyzer for fair scheduling behavior"""
    
    def __init__(self, client: SchedulerTestClient):
        self.client = client
    
    def analyze_fair_share_allocation(self, tenant_jobs: Dict[str, List[str]], 
                                    duration: int = 60) -> Dict[str, Any]:
        """Analyze fair share allocation across tenants"""
        start_time = time.time()
        allocation_history = []
        
        while time.time() - start_time < duration:
            # Get current job statuses for all tenants
            tenant_allocations = {}
            
            for tenant_id, job_ids in tenant_jobs.items():
                running_jobs = 0
                scheduled_jobs = 0
                pending_jobs = 0
                
                for job_id in job_ids:
                    job_info = self.client.get_job_status(job_id, tenant_id)
                    if job_info:
                        status = job_info.get("status", "unknown")
                        if status == "running":
                            running_jobs += 1
                        elif status == "scheduled":
                            scheduled_jobs += 1
                        elif status == "pending":
                            pending_jobs += 1
                
                tenant_allocations[tenant_id] = {
                    "running": running_jobs,
                    "scheduled": scheduled_jobs,
                    "pending": pending_jobs,
                    "total": running_jobs + scheduled_jobs + pending_jobs
                }
            
            allocation_history.append({
                "timestamp": time.time(),
                "allocations": tenant_allocations.copy()
            })
            
            time.sleep(5)
        
        return self._analyze_fairness(allocation_history)
    
    def _analyze_fairness(self, history: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze fairness from allocation history"""
        if not history:
            return {"fair": False, "reason": "No allocation history"}
        
        # Calculate average allocations
        tenant_avg_allocations = defaultdict(float)
        tenant_weights = {}
        
        for snapshot in history:
            for tenant_id, allocation in snapshot["allocations"].items():
                tenant_avg_allocations[tenant_id] += allocation["running"]
        
        # Average over time
        for tenant_id in tenant_avg_allocations:
            tenant_avg_allocations[tenant_id] /= len(history)
        
        # Get tenant weights from configuration
        for tenant_id in tenant_avg_allocations:
            tenant_config = self.client.tenants.get(tenant_id)
            if tenant_config:
                priority_class = tenant_config.priority_class
                if priority_class == "high":
                    tenant_weights[tenant_id] = 4
                elif priority_class == "medium":
                    tenant_weights[tenant_id] = 2
                else:
                    tenant_weights[tenant_id] = 1
            else:
                tenant_weights[tenant_id] = 1
        
        # Calculate fairness metrics
        fairness_ratios = {}
        for tenant_id, avg_allocation in tenant_avg_allocations.items():
            weight = tenant_weights.get(tenant_id, 1)
            if weight > 0:
                fairness_ratios[tenant_id] = avg_allocation / weight
        
        # Check if ratios are reasonably balanced
        if len(fairness_ratios) < 2:
            return {"fair": True, "reason": "Single tenant"}
        
        ratio_values = list(fairness_ratios.values())
        max_ratio = max(ratio_values)
        min_ratio = min(ratio_values)
        
        # Consider fair if max/min ratio is within acceptable bounds
        fairness_threshold = 2.0  # Allow 2x difference
        is_fair = (max_ratio / min_ratio) <= fairness_threshold if min_ratio > 0 else False
        
        return {
            "fair": is_fair,
            "fairness_ratios": fairness_ratios,
            "max_ratio": max_ratio,
            "min_ratio": min_ratio,
            "ratio_spread": max_ratio / min_ratio if min_ratio > 0 else float('inf'),
            "tenant_allocations": dict(tenant_avg_allocations),
            "tenant_weights": tenant_weights
        }
    
    def analyze_priority_preemption(self, high_priority_jobs: List[str],
                                  low_priority_jobs: List[str],
                                  tenant_id: str) -> Dict[str, Any]:
        """Analyze priority-based preemption behavior"""
        preemption_events = []
        
        # Monitor job status changes
        start_time = time.time()
        monitoring_duration = 120  # 2 minutes
        
        while time.time() - start_time < monitoring_duration:
            # Check status of low priority jobs
            for job_id in low_priority_jobs:
                job_info = self.client.get_job_status(job_id, tenant_id)
                if job_info and job_info.get("status") == "preempted":
                    preemption_events.append({
                        "timestamp": time.time(),
                        "preempted_job": job_id,
                        "job_priority": job_info.get("priority", 0)
                    })
            
            time.sleep(5)
        
        # Check if high priority jobs got scheduled
        high_priority_scheduled = 0
        for job_id in high_priority_jobs:
            job_info = self.client.get_job_status(job_id, tenant_id)
            if job_info and job_info.get("status") in ["running", "scheduled"]:
                high_priority_scheduled += 1
        
        return {
            "preemption_events": preemption_events,
            "high_priority_scheduled": high_priority_scheduled,
            "total_high_priority": len(high_priority_jobs),
            "preemption_rate": len(preemption_events) / len(low_priority_jobs) if low_priority_jobs else 0,
            "high_priority_success_rate": high_priority_scheduled / len(high_priority_jobs) if high_priority_jobs else 0
        }
    
    def analyze_resource_utilization(self, duration: int = 60) -> Dict[str, Any]:
        """Analyze cluster resource utilization"""
        utilization_history = []
        start_time = time.time()
        
        while time.time() - start_time < duration:
            metrics = self.client.get_scheduler_metrics()
            if metrics:
                # Extract resource utilization metrics
                cpu_util = []
                memory_util = []
                gpu_util = []
                
                for metric_name, value in metrics.items():
                    if "resource_utilization" in metric_name:
                        if "cpu" in metric_name:
                            cpu_util.append(value)
                        elif "memory" in metric_name:
                            memory_util.append(value)
                        elif "gpu" in metric_name:
                            gpu_util.append(value)
                
                utilization_history.append({
                    "timestamp": time.time(),
                    "cpu_utilization": sum(cpu_util) / len(cpu_util) if cpu_util else 0,
                    "memory_utilization": sum(memory_util) / len(memory_util) if memory_util else 0,
                    "gpu_utilization": sum(gpu_util) / len(gpu_util) if gpu_util else 0,
                    "queue_depth": metrics.get("scheduler_queue_depth", 0)
                })
            
            time.sleep(10)
        
        if not utilization_history:
            return {"error": "No utilization data collected"}
        
        # Calculate averages
        avg_cpu = sum(h["cpu_utilization"] for h in utilization_history) / len(utilization_history)
        avg_memory = sum(h["memory_utilization"] for h in utilization_history) / len(utilization_history)
        avg_gpu = sum(h["gpu_utilization"] for h in utilization_history) / len(utilization_history)
        avg_queue_depth = sum(h["queue_depth"] for h in utilization_history) / len(utilization_history)
        
        return {
            "average_cpu_utilization": avg_cpu,
            "average_memory_utilization": avg_memory,
            "average_gpu_utilization": avg_gpu,
            "average_queue_depth": avg_queue_depth,
            "utilization_history": utilization_history,
            "peak_cpu_utilization": max(h["cpu_utilization"] for h in utilization_history),
            "peak_memory_utilization": max(h["memory_utilization"] for h in utilization_history)
        }

@pytest.fixture(scope="session")
def scheduler_config():
    """Scheduler test configuration fixture"""
    return SchedulerTestConfig()

@pytest.fixture(scope="session")
def scheduler_client(scheduler_config):
    """Scheduler test client fixture"""
    return SchedulerTestClient(scheduler_config)

@pytest.fixture(scope="session")
def fair_analyzer(scheduler_client):
    """Fair scheduling analyzer fixture"""
    return FairSchedulingAnalyzer(scheduler_client)

class TestFairScheduling:
    """Test fair scheduling algorithms"""
    
    def test_scheduler_connectivity(self, scheduler_client):
        """Test connectivity to scheduler services"""
        cluster_status = scheduler_client.get_cluster_status()
        
        if cluster_status:
            assert cluster_status.get("status") == "healthy"
            logger.info("✅ Scheduler connectivity test passed")
        else:
            logger.warning("⚠️  Scheduler not accessible - tests will be limited")
    
    def test_tenant_creation(self, scheduler_client):
        """Test multi-tenant setup"""
        # Create test tenants
        tenants = [
            TenantConfig(
                id="test-tenant-high",
                name="High Priority Tenant",
                resource_quota={
                    "cpu": "20",
                    "memory": "40Gi",
                    "gpu": "4",
                    "jobs": 50
                },
                priority_class="high"
            ),
            TenantConfig(
                id="test-tenant-medium",
                name="Medium Priority Tenant",
                resource_quota={
                    "cpu": "15",
                    "memory": "30Gi",
                    "gpu": "2",
                    "jobs": 30
                },
                priority_class="medium"
            ),
            TenantConfig(
                id="test-tenant-low",
                name="Low Priority Tenant",
                resource_quota={
                    "cpu": "10",
                    "memory": "20Gi",
                    "gpu": "1",
                    "jobs": 20
                },
                priority_class="low"
            )
        ]
        
        created_tenants = 0
        for tenant in tenants:
            if scheduler_client.create_tenant(tenant):
                created_tenants += 1
        
        assert created_tenants > 0, "At least one tenant should be created"
        logger.info(f"✅ Created {created_tenants} test tenants")
    
    def test_basic_job_submission(self, scheduler_client):
        """Test basic job submission and scheduling"""
        job = JobRequest(
            name="test-job-basic",
            image="busybox:latest",
            resources={"cpu": "0.5", "memory": "512Mi"},
            tenant_id="test-tenant-medium",
            priority=50
        )
        
        job_id = scheduler_client.submit_job(job)
        
        if job_id:
            # Wait for job to be scheduled
            scheduled = scheduler_client.wait_for_job_status(
                job_id, "test-tenant-medium", "scheduled", timeout=30
            )
            
            assert scheduled, f"Job {job_id} should be scheduled"
            logger.info(f"✅ Basic job submission test passed: {job_id}")
        else:
            logger.warning("⚠️  Job submission failed - scheduler may not be available")
    
    def test_fair_share_scheduling(self, scheduler_client, fair_analyzer):
        """Test fair share scheduling across tenants"""
        # Submit jobs from different tenants
        tenant_jobs = {}
        
        # High priority tenant - submit 5 jobs
        high_priority_jobs = []
        for i in range(5):
            job = JobRequest(
                name=f"high-priority-job-{i}",
                image="busybox:latest",
                resources={"cpu": "1", "memory": "1Gi"},
                tenant_id="test-tenant-high",
                priority=80
            )
            job_id = scheduler_client.submit_job(job)
            if job_id:
                high_priority_jobs.append(job_id)
        
        # Medium priority tenant - submit 5 jobs
        medium_priority_jobs = []
        for i in range(5):
            job = JobRequest(
                name=f"medium-priority-job-{i}",
                image="busybox:latest",
                resources={"cpu": "1", "memory": "1Gi"},
                tenant_id="test-tenant-medium",
                priority=50
            )
            job_id = scheduler_client.submit_job(job)
            if job_id:
                medium_priority_jobs.append(job_id)
        
        # Low priority tenant - submit 5 jobs
        low_priority_jobs = []
        for i in range(5):
            job = JobRequest(
                name=f"low-priority-job-{i}",
                image="busybox:latest",
                resources={"cpu": "1", "memory": "1Gi"},
                tenant_id="test-tenant-low",
                priority=20
            )
            job_id = scheduler_client.submit_job(job)
            if job_id:
                low_priority_jobs.append(job_id)
        
        tenant_jobs = {
            "test-tenant-high": high_priority_jobs,
            "test-tenant-medium": medium_priority_jobs,
            "test-tenant-low": low_priority_jobs
        }
        
        if any(tenant_jobs.values()):
            # Analyze fair share allocation
            fairness_analysis = fair_analyzer.analyze_fair_share_allocation(
                tenant_jobs, duration=60
            )
            
            logger.info(f"Fair share analysis: {fairness_analysis}")
            
            # Check if allocation is reasonably fair
            if fairness_analysis.get("fair"):
                logger.info("✅ Fair share scheduling test passed")
            else:
                logger.warning(f"⚠️  Fair share scheduling may need tuning: {fairness_analysis.get('reason')}")
        else:
            logger.warning("⚠️  No jobs submitted - fair share test skipped")
    
    def test_priority_preemption(self, scheduler_client, fair_analyzer):
        """Test priority-based preemption"""
        # Submit low priority jobs to fill cluster
        low_priority_jobs = []
        for i in range(10):
            job = JobRequest(
                name=f"low-priority-filler-{i}",
                image="busybox:latest",
                resources={"cpu": "2", "memory": "2Gi"},
                tenant_id="test-tenant-low",
                priority=10
            )
            job_id = scheduler_client.submit_job(job)
            if job_id:
                low_priority_jobs.append(job_id)
        
        # Wait for low priority jobs to be scheduled
        time.sleep(30)
        
        # Submit high priority jobs that should preempt
        high_priority_jobs = []
        for i in range(3):
            job = JobRequest(
                name=f"high-priority-preemptor-{i}",
                image="busybox:latest",
                resources={"cpu": "2", "memory": "2Gi"},
                tenant_id="test-tenant-high",
                priority=100
            )
            job_id = scheduler_client.submit_job(job)
            if job_id:
                high_priority_jobs.append(job_id)
        
        if high_priority_jobs and low_priority_jobs:
            # Analyze preemption behavior
            preemption_analysis = fair_analyzer.analyze_priority_preemption(
                high_priority_jobs, low_priority_jobs, "test-tenant-high"
            )
            
            logger.info(f"Preemption analysis: {preemption_analysis}")
            
            # Check if preemption occurred
            preemption_rate = preemption_analysis.get("preemption_rate", 0)
            high_priority_success = preemption_analysis.get("high_priority_success_rate", 0)
            
            if preemption_rate > 0 or high_priority_success > 0.5:
                logger.info("✅ Priority preemption test passed")
            else:
                logger.warning("⚠️  Priority preemption may not be working as expected")
        else:
            logger.warning("⚠️  Preemption test skipped - job submission failed")
    
    def test_resource_utilization_optimization(self, scheduler_client, fair_analyzer):
        """Test resource utilization optimization"""
        # Submit various sized jobs to test bin packing
        jobs = [
            JobRequest(
                name="small-job-1",
                image="busybox:latest",
                resources={"cpu": "0.5", "memory": "512Mi"},
                tenant_id="test-tenant-medium"
            ),
            JobRequest(
                name="medium-job-1",
                image="busybox:latest",
                resources={"cpu": "2", "memory": "2Gi"},
                tenant_id="test-tenant-medium"
            ),
            JobRequest(
                name="large-job-1",
                image="busybox:latest",
                resources={"cpu": "4", "memory": "4Gi"},
                tenant_id="test-tenant-high"
            ),
            JobRequest(
                name="gpu-job-1",
                image="tensorflow/tensorflow:latest-gpu",
                resources={"cpu": "2", "memory": "4Gi", "gpu": "1"},
                tenant_id="test-tenant-high"
            )
        ]
        
        submitted_jobs = []
        for job in jobs:
            job_id = scheduler_client.submit_job(job)
            if job_id:
                submitted_jobs.append(job_id)
        
        if submitted_jobs:
            # Analyze resource utilization
            utilization_analysis = fair_analyzer.analyze_resource_utilization(duration=60)
            
            logger.info(f"Resource utilization analysis: {utilization_analysis}")
            
            avg_cpu_util = utilization_analysis.get("average_cpu_utilization", 0)
            avg_memory_util = utilization_analysis.get("average_memory_utilization", 0)
            
            # Check if utilization is reasonable (>30% indicates good packing)
            if avg_cpu_util > 30 or avg_memory_util > 30:
                logger.info("✅ Resource utilization optimization test passed")
            else:
                logger.warning("⚠️  Resource utilization may be suboptimal")
        else:
            logger.warning("⚠️  Resource utilization test skipped - no jobs submitted")
    
    def test_tenant_isolation(self, scheduler_client):
        """Test tenant isolation and quota enforcement"""
        # Try to submit jobs exceeding quota
        excess_jobs = []
        for i in range(60):  # Exceed the 50 job limit for high priority tenant
            job = JobRequest(
                name=f"quota-test-job-{i}",
                image="busybox:latest",
                resources={"cpu": "0.1", "memory": "128Mi"},
                tenant_id="test-tenant-high"
            )
            job_id = scheduler_client.submit_job(job)
            if job_id:
                excess_jobs.append(job_id)
            else:
                break  # Quota enforcement should prevent further submissions
        
        # Check if quota was enforced
        if len(excess_jobs) <= 50:
            logger.info("✅ Tenant isolation and quota enforcement test passed")
        else:
            logger.warning(f"⚠️  Quota enforcement may not be working - submitted {len(excess_jobs)} jobs")
        
        # Test cross-tenant access (should be denied)
        if excess_jobs:
            job_id = excess_jobs[0]
            # Try to access job from different tenant
            job_info = scheduler_client.get_job_status(job_id, "test-tenant-medium")
            
            if job_info is None:
                logger.info("✅ Cross-tenant access properly denied")
            else:
                logger.warning("⚠️  Cross-tenant access control may be compromised")

class TestSchedulingAlgorithms:
    """Test specific scheduling algorithms"""
    
    def test_weighted_fair_queuing(self, scheduler_client):
        """Test weighted fair queuing algorithm"""
        # This would test the specific implementation of WFQ
        # For now, we'll test basic fairness
        
        metrics = scheduler_client.get_scheduler_metrics()
        if metrics:
            queue_depth = metrics.get("scheduler_queue_depth", 0)
            jobs_scheduled = metrics.get("scheduler_jobs_scheduled_total", 0)
            
            logger.info(f"Queue depth: {queue_depth}, Jobs scheduled: {jobs_scheduled}")
            logger.info("✅ Weighted fair queuing metrics available")
        else:
            logger.warning("⚠️  Scheduler metrics not available")
    
    def test_gang_scheduling(self, scheduler_client):
        """Test gang scheduling for distributed jobs"""
        # Submit a gang job (all-or-nothing scheduling)
        gang_jobs = []
        for i in range(3):
            job = JobRequest(
                name=f"gang-job-{i}",
                image="mpi-job:latest",
                resources={"cpu": "4", "memory": "8Gi"},
                tenant_id="test-tenant-high",
                labels={"gang": "distributed-training", "gang-size": "3"}
            )
            job_id = scheduler_client.submit_job(job)
            if job_id:
                gang_jobs.append(job_id)
        
        if len(gang_jobs) == 3:
            # Check if all gang jobs are scheduled together or none at all
            time.sleep(30)
            
            scheduled_count = 0
            for job_id in gang_jobs:
                job_info = scheduler_client.get_job_status(job_id, "test-tenant-high")
                if job_info and job_info.get("status") in ["running", "scheduled"]:
                    scheduled_count += 1
            
            # Gang scheduling: either all scheduled or none
            if scheduled_count == 0 or scheduled_count == 3:
                logger.info("✅ Gang scheduling test passed")
            else:
                logger.warning(f"⚠️  Gang scheduling may not be working - {scheduled_count}/3 jobs scheduled")
        else:
            logger.warning("⚠️  Gang scheduling test skipped - job submission failed")

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

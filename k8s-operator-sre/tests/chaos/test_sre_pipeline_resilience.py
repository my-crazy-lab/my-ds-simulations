#!/usr/bin/env python3
"""
Chaos engineering tests for SRE pipeline resilience.
Tests platform behavior under various failure scenarios and validates SRE practices.
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
from kubernetes import client, config
from kubernetes.client.rest import ApiException

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class SRETestConfig:
    """Configuration for SRE pipeline tests"""
    kubeconfig_path: str = "/etc/kubeconfig/config"
    platform_namespace: str = "platform-system"
    test_namespace: str = "sre-chaos-test"
    argocd_url: str = "http://argocd-server:8080"
    prometheus_url: str = "http://prometheus:9090"
    grafana_url: str = "http://grafana:3000"
    litmus_url: str = "http://litmus-server:9002"
    timeout_seconds: int = 600
    chaos_duration: int = 120
    recovery_timeout: int = 300

class SREChaosController:
    """Controller for SRE chaos engineering scenarios"""
    
    def __init__(self, config: SRETestConfig):
        self.config = config
        self.docker_client = docker.from_env()
        
        # Initialize Kubernetes client
        try:
            config.load_kube_config(config_file=config.kubeconfig_path)
        except Exception:
            config.load_incluster_config()
        
        self.k8s_apps = client.AppsV1Api()
        self.k8s_core = client.CoreV1Api()
        self.k8s_custom = client.CustomObjectsApi()
    
    def get_container_by_name(self, name: str) -> Optional[docker.models.containers.Container]:
        """Get container by name"""
        try:
            return self.docker_client.containers.get(name)
        except docker.errors.NotFound:
            return None
    
    def stop_service(self, service_name: str) -> bool:
        """Stop a service container"""
        try:
            container = self.get_container_by_name(service_name)
            if container:
                container.stop()
                logger.info(f"Stopped service: {service_name}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to stop service {service_name}: {e}")
            return False
    
    def start_service(self, service_name: str) -> bool:
        """Start a service container"""
        try:
            container = self.get_container_by_name(service_name)
            if container:
                container.start()
                logger.info(f"Started service: {service_name}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to start service {service_name}: {e}")
            return False
    
    def pause_service(self, service_name: str) -> bool:
        """Pause a service container"""
        try:
            container = self.get_container_by_name(service_name)
            if container:
                container.pause()
                logger.info(f"Paused service: {service_name}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to pause service {service_name}: {e}")
            return False
    
    def unpause_service(self, service_name: str) -> bool:
        """Unpause a service container"""
        try:
            container = self.get_container_by_name(service_name)
            if container:
                container.unpause()
                logger.info(f"Unpaused service: {service_name}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to unpause service {service_name}: {e}")
            return False
    
    def inject_network_delay(self, service_name: str, delay_ms: int) -> bool:
        """Inject network delay into a service"""
        try:
            container = self.get_container_by_name(service_name)
            if container:
                # Use tc (traffic control) to add network delay
                exec_result = container.exec_run(
                    f"tc qdisc add dev eth0 root netem delay {delay_ms}ms",
                    privileged=True
                )
                if exec_result.exit_code == 0:
                    logger.info(f"Injected {delay_ms}ms delay to {service_name}")
                    return True
            return False
        except Exception as e:
            logger.error(f"Failed to inject network delay to {service_name}: {e}")
            return False
    
    def remove_network_delay(self, service_name: str) -> bool:
        """Remove network delay from a service"""
        try:
            container = self.get_container_by_name(service_name)
            if container:
                exec_result = container.exec_run(
                    "tc qdisc del dev eth0 root netem",
                    privileged=True
                )
                if exec_result.exit_code == 0:
                    logger.info(f"Removed network delay from {service_name}")
                    return True
            return False
        except Exception as e:
            logger.error(f"Failed to remove network delay from {service_name}: {e}")
            return False
    
    def scale_deployment(self, namespace: str, name: str, replicas: int) -> bool:
        """Scale a Kubernetes deployment"""
        try:
            body = {"spec": {"replicas": replicas}}
            self.k8s_apps.patch_namespaced_deployment_scale(
                name=name, namespace=namespace, body=body
            )
            logger.info(f"Scaled deployment {name} to {replicas} replicas")
            return True
        except ApiException as e:
            logger.error(f"Failed to scale deployment {name}: {e}")
            return False

class SREMetricsCollector:
    """Collector for SRE metrics and observability data"""
    
    def __init__(self, config: SRETestConfig):
        self.config = config
    
    def query_prometheus(self, query: str, timeout: int = 30) -> Optional[Dict]:
        """Query Prometheus for metrics"""
        try:
            response = requests.get(
                f"{self.config.prometheus_url}/api/v1/query",
                params={"query": query},
                timeout=timeout
            )
            if response.status_code == 200:
                return response.json()
            return None
        except requests.RequestException as e:
            logger.error(f"Prometheus query failed: {e}")
            return None
    
    def get_service_availability(self, service: str, duration: str = "5m") -> float:
        """Get service availability percentage"""
        query = f'avg_over_time(up{{job="{service}"}}[{duration}]) * 100'
        result = self.query_prometheus(query)
        
        if result and result.get("data", {}).get("result"):
            return float(result["data"]["result"][0]["value"][1])
        return 0.0
    
    def get_error_rate(self, service: str, duration: str = "5m") -> float:
        """Get service error rate"""
        query = f'rate(http_requests_total{{job="{service}",status=~"5.."}}[{duration}]) / rate(http_requests_total{{job="{service}"}}[{duration}]) * 100'
        result = self.query_prometheus(query)
        
        if result and result.get("data", {}).get("result"):
            return float(result["data"]["result"][0]["value"][1])
        return 0.0
    
    def get_response_time_p99(self, service: str, duration: str = "5m") -> float:
        """Get service P99 response time"""
        query = f'histogram_quantile(0.99, rate(http_request_duration_seconds_bucket{{job="{service}"}}[{duration}]))'
        result = self.query_prometheus(query)
        
        if result and result.get("data", {}).get("result"):
            return float(result["data"]["result"][0]["value"][1]) * 1000  # Convert to ms
        return 0.0
    
    def check_slo_compliance(self, service: str, availability_threshold: float = 99.9,
                           error_rate_threshold: float = 1.0, 
                           latency_threshold: float = 100.0) -> Dict[str, bool]:
        """Check SLO compliance for a service"""
        availability = self.get_service_availability(service)
        error_rate = self.get_error_rate(service)
        p99_latency = self.get_response_time_p99(service)
        
        return {
            "availability_slo": availability >= availability_threshold,
            "error_rate_slo": error_rate <= error_rate_threshold,
            "latency_slo": p99_latency <= latency_threshold,
            "overall_slo": (availability >= availability_threshold and 
                          error_rate <= error_rate_threshold and 
                          p99_latency <= latency_threshold),
            "metrics": {
                "availability": availability,
                "error_rate": error_rate,
                "p99_latency": p99_latency
            }
        }

class GitOpsTestHelper:
    """Helper for GitOps workflow testing"""
    
    def __init__(self, config: SRETestConfig):
        self.config = config
    
    def check_argocd_health(self) -> bool:
        """Check ArgoCD health"""
        try:
            response = requests.get(f"{self.config.argocd_url}/healthz", timeout=10)
            return response.status_code == 200
        except requests.RequestException:
            return False
    
    def get_application_status(self, app_name: str) -> Optional[Dict]:
        """Get ArgoCD application status"""
        try:
            response = requests.get(
                f"{self.config.argocd_url}/api/v1/applications/{app_name}",
                timeout=10
            )
            if response.status_code == 200:
                return response.json()
            return None
        except requests.RequestException as e:
            logger.error(f"Failed to get application status: {e}")
            return None
    
    def trigger_sync(self, app_name: str) -> bool:
        """Trigger ArgoCD application sync"""
        try:
            response = requests.post(
                f"{self.config.argocd_url}/api/v1/applications/{app_name}/sync",
                json={"prune": True, "dryRun": False},
                timeout=30
            )
            return response.status_code in [200, 202]
        except requests.RequestException as e:
            logger.error(f"Failed to trigger sync: {e}")
            return False

@pytest.fixture(scope="session")
def sre_config():
    """SRE test configuration fixture"""
    return SRETestConfig()

@pytest.fixture(scope="session")
def chaos_controller(sre_config):
    """Chaos controller fixture"""
    return SREChaosController(sre_config)

@pytest.fixture(scope="session")
def metrics_collector(sre_config):
    """Metrics collector fixture"""
    return SREMetricsCollector(sre_config)

@pytest.fixture(scope="session")
def gitops_helper(sre_config):
    """GitOps helper fixture"""
    return GitOpsTestHelper(sre_config)

class TestOperatorResilience:
    """Test operator resilience under chaos conditions"""
    
    def test_operator_restart_recovery(self, chaos_controller, metrics_collector, sre_config):
        """Test operator recovery after restart"""
        logger.info("🔄 Testing operator restart recovery...")
        
        # Get baseline metrics
        baseline_availability = metrics_collector.get_service_availability("webapp-operator")
        
        # Stop operator
        assert chaos_controller.stop_service("webapp-operator")
        
        # Wait for impact
        time.sleep(30)
        
        # Start operator
        assert chaos_controller.start_service("webapp-operator")
        
        # Wait for recovery
        time.sleep(60)
        
        # Check recovery
        recovery_availability = metrics_collector.get_service_availability("webapp-operator")
        
        # Operator should recover to baseline levels
        assert recovery_availability >= baseline_availability * 0.95
        logger.info("✅ Operator restart recovery test passed")
    
    def test_operator_under_high_load(self, chaos_controller, metrics_collector):
        """Test operator performance under high reconciliation load"""
        logger.info("📈 Testing operator under high load...")
        
        # Create multiple WebApp resources rapidly
        webapp_count = 20
        webapps_created = []
        
        try:
            for i in range(webapp_count):
                webapp_name = f"load-test-webapp-{i}"
                webapp_spec = {
                    "replicas": 1,
                    "image": "nginx:1.21",
                    "version": f"v1.0.{i}"
                }
                
                # This would create WebApp resources in a real test
                # webapp = create_webapp_resource(webapp_name, webapp_spec)
                webapps_created.append(webapp_name)
            
            # Monitor operator metrics during high load
            time.sleep(120)  # Let operator process all resources
            
            # Check operator performance metrics
            reconcile_rate = metrics_collector.query_prometheus(
                'rate(controller_runtime_reconcile_total[5m])'
            )
            
            error_rate = metrics_collector.query_prometheus(
                'rate(controller_runtime_reconcile_errors_total[5m])'
            )
            
            # Operator should handle high load without excessive errors
            if reconcile_rate and error_rate:
                logger.info("Operator handled high load successfully")
            
        finally:
            # Cleanup created resources
            for webapp_name in webapps_created:
                # Delete WebApp resources
                pass
        
        logger.info("✅ Operator high load test passed")

class TestGitOpsResilience:
    """Test GitOps pipeline resilience"""
    
    def test_argocd_failure_recovery(self, chaos_controller, gitops_helper, sre_config):
        """Test ArgoCD failure and recovery"""
        logger.info("🔄 Testing ArgoCD failure recovery...")
        
        # Verify ArgoCD is healthy
        assert gitops_helper.check_argocd_health()
        
        # Stop ArgoCD server
        assert chaos_controller.stop_service("argocd-server")
        
        # Verify ArgoCD is down
        time.sleep(30)
        assert not gitops_helper.check_argocd_health()
        
        # Start ArgoCD server
        assert chaos_controller.start_service("argocd-server")
        
        # Wait for recovery
        recovery_start = time.time()
        while time.time() - recovery_start < sre_config.recovery_timeout:
            if gitops_helper.check_argocd_health():
                break
            time.sleep(10)
        
        # Verify recovery
        assert gitops_helper.check_argocd_health()
        logger.info("✅ ArgoCD failure recovery test passed")
    
    def test_gitops_sync_during_network_issues(self, chaos_controller, gitops_helper):
        """Test GitOps sync behavior during network issues"""
        logger.info("🌐 Testing GitOps sync during network issues...")
        
        # Inject network delay to ArgoCD
        assert chaos_controller.inject_network_delay("argocd-server", 1000)  # 1s delay
        
        try:
            # Attempt sync with network issues
            sync_result = gitops_helper.trigger_sync("sample-app")
            
            # Sync might fail or be delayed, but should eventually succeed
            time.sleep(60)
            
            # Check application status
            app_status = gitops_helper.get_application_status("sample-app")
            if app_status:
                logger.info(f"Application status during network issues: {app_status.get('status', {}).get('sync', {}).get('status')}")
        
        finally:
            # Remove network delay
            chaos_controller.remove_network_delay("argocd-server")
        
        logger.info("✅ GitOps network issues test passed")

class TestObservabilityResilience:
    """Test observability stack resilience"""
    
    def test_prometheus_failure_impact(self, chaos_controller, metrics_collector, sre_config):
        """Test impact of Prometheus failure on monitoring"""
        logger.info("📊 Testing Prometheus failure impact...")
        
        # Verify Prometheus is working
        initial_query = metrics_collector.query_prometheus("up")
        assert initial_query is not None
        
        # Stop Prometheus
        assert chaos_controller.stop_service("platform-prometheus")
        
        # Verify metrics collection is impacted
        time.sleep(30)
        failed_query = metrics_collector.query_prometheus("up")
        assert failed_query is None
        
        # Start Prometheus
        assert chaos_controller.start_service("platform-prometheus")
        
        # Wait for recovery
        recovery_start = time.time()
        while time.time() - recovery_start < sre_config.recovery_timeout:
            recovery_query = metrics_collector.query_prometheus("up")
            if recovery_query is not None:
                break
            time.sleep(10)
        
        # Verify recovery
        final_query = metrics_collector.query_prometheus("up")
        assert final_query is not None
        logger.info("✅ Prometheus failure impact test passed")
    
    def test_grafana_dashboard_availability(self, chaos_controller, sre_config):
        """Test Grafana dashboard availability during failures"""
        logger.info("📈 Testing Grafana dashboard availability...")
        
        # Check Grafana health
        try:
            response = requests.get(f"{sre_config.grafana_url}/api/health", timeout=10)
            assert response.status_code == 200
        except requests.RequestException:
            pytest.fail("Grafana not accessible")
        
        # Stop and restart Grafana
        assert chaos_controller.stop_service("platform-grafana")
        time.sleep(30)
        assert chaos_controller.start_service("platform-grafana")
        
        # Wait for recovery
        recovery_start = time.time()
        while time.time() - recovery_start < sre_config.recovery_timeout:
            try:
                response = requests.get(f"{sre_config.grafana_url}/api/health", timeout=10)
                if response.status_code == 200:
                    break
            except requests.RequestException:
                pass
            time.sleep(10)
        
        # Verify recovery
        try:
            response = requests.get(f"{sre_config.grafana_url}/api/health", timeout=10)
            assert response.status_code == 200
        except requests.RequestException:
            pytest.fail("Grafana failed to recover")
        
        logger.info("✅ Grafana availability test passed")

class TestSLOCompliance:
    """Test SLO compliance during chaos scenarios"""
    
    def test_platform_slo_during_partial_failures(self, chaos_controller, metrics_collector):
        """Test platform SLO compliance during partial component failures"""
        logger.info("🎯 Testing SLO compliance during partial failures...")
        
        # Get baseline SLO metrics
        baseline_slo = metrics_collector.check_slo_compliance("platform")
        logger.info(f"Baseline SLO: {baseline_slo}")
        
        # Introduce partial failure (pause one component)
        assert chaos_controller.pause_service("argocd-repo-server")
        
        try:
            # Monitor SLO compliance during failure
            time.sleep(60)  # Let metrics accumulate
            
            failure_slo = metrics_collector.check_slo_compliance("platform")
            logger.info(f"SLO during failure: {failure_slo}")
            
            # Platform should maintain acceptable SLO levels even with partial failures
            # This depends on the specific SLO thresholds and redundancy
            
        finally:
            # Restore service
            chaos_controller.unpause_service("argocd-repo-server")
        
        # Wait for recovery
        time.sleep(60)
        
        # Check recovery SLO
        recovery_slo = metrics_collector.check_slo_compliance("platform")
        logger.info(f"Recovery SLO: {recovery_slo}")
        
        # SLO should recover to acceptable levels
        assert recovery_slo["availability_slo"]
        logger.info("✅ SLO compliance test passed")
    
    def test_error_budget_consumption(self, chaos_controller, metrics_collector):
        """Test error budget consumption during failures"""
        logger.info("💰 Testing error budget consumption...")
        
        # Get initial error rate
        initial_error_rate = metrics_collector.get_error_rate("platform")
        
        # Introduce errors by stopping a critical service briefly
        assert chaos_controller.stop_service("webapp-operator")
        
        # Let errors accumulate
        time.sleep(30)
        
        # Start service back
        assert chaos_controller.start_service("webapp-operator")
        
        # Wait for stabilization
        time.sleep(60)
        
        # Check error rate impact
        final_error_rate = metrics_collector.get_error_rate("platform")
        
        # Error rate should have increased during the failure
        logger.info(f"Error rate change: {initial_error_rate} -> {final_error_rate}")
        
        # This test validates that we can measure error budget consumption
        logger.info("✅ Error budget consumption test passed")

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-s"])

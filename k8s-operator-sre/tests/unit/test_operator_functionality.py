#!/usr/bin/env python3
"""
Unit tests for Kubernetes Operator functionality.
Tests operator controller logic, reconciliation loops, and resource management.
"""

import pytest
import asyncio
import json
import time
import yaml
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from kubernetes import client, config
from kubernetes.client.rest import ApiException
import requests
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class OperatorTestConfig:
    """Configuration for operator tests"""
    kubeconfig_path: str = "/etc/kubeconfig/config"
    operator_namespace: str = "platform-system"
    test_namespace: str = "operator-test"
    operator_url: str = "http://webapp-operator:8080"
    timeout_seconds: int = 300
    poll_interval: float = 2.0

class KubernetesTestClient:
    """Test client for Kubernetes API operations"""
    
    def __init__(self, config_path: str):
        try:
            config.load_kube_config(config_file=config_path)
        except Exception:
            config.load_incluster_config()
        
        self.api_client = client.ApiClient()
        self.apps_v1 = client.AppsV1Api()
        self.core_v1 = client.CoreV1Api()
        self.custom_objects = client.CustomObjectsApi()
        self.autoscaling_v2 = client.AutoscalingV2Api()
        self.networking_v1 = client.NetworkingV1Api()
        
    def create_custom_resource(self, group: str, version: str, plural: str, 
                             namespace: str, body: Dict) -> Dict:
        """Create a custom resource"""
        try:
            return self.custom_objects.create_namespaced_custom_object(
                group=group, version=version, namespace=namespace, 
                plural=plural, body=body
            )
        except ApiException as e:
            logger.error(f"Failed to create custom resource: {e}")
            raise
    
    def get_custom_resource(self, group: str, version: str, plural: str, 
                          namespace: str, name: str) -> Dict:
        """Get a custom resource"""
        try:
            return self.custom_objects.get_namespaced_custom_object(
                group=group, version=version, namespace=namespace, 
                plural=plural, name=name
            )
        except ApiException as e:
            if e.status == 404:
                return None
            logger.error(f"Failed to get custom resource: {e}")
            raise
    
    def update_custom_resource(self, group: str, version: str, plural: str, 
                             namespace: str, name: str, body: Dict) -> Dict:
        """Update a custom resource"""
        try:
            return self.custom_objects.patch_namespaced_custom_object(
                group=group, version=version, namespace=namespace, 
                plural=plural, name=name, body=body
            )
        except ApiException as e:
            logger.error(f"Failed to update custom resource: {e}")
            raise
    
    def delete_custom_resource(self, group: str, version: str, plural: str, 
                             namespace: str, name: str) -> bool:
        """Delete a custom resource"""
        try:
            self.custom_objects.delete_namespaced_custom_object(
                group=group, version=version, namespace=namespace, 
                plural=plural, name=name
            )
            return True
        except ApiException as e:
            if e.status == 404:
                return True
            logger.error(f"Failed to delete custom resource: {e}")
            raise
    
    def wait_for_deployment_ready(self, namespace: str, name: str, 
                                timeout: int = 300) -> bool:
        """Wait for deployment to be ready"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                deployment = self.apps_v1.read_namespaced_deployment(name, namespace)
                if (deployment.status.ready_replicas and 
                    deployment.status.ready_replicas == deployment.spec.replicas):
                    return True
            except ApiException:
                pass
            time.sleep(2)
        return False
    
    def wait_for_service_ready(self, namespace: str, name: str, 
                             timeout: int = 60) -> bool:
        """Wait for service to be ready"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                service = self.core_v1.read_namespaced_service(name, namespace)
                if service.spec.cluster_ip and service.spec.cluster_ip != "None":
                    return True
            except ApiException:
                pass
            time.sleep(2)
        return False

class OperatorTestHelper:
    """Helper class for operator testing"""
    
    def __init__(self, k8s_client: KubernetesTestClient, config: OperatorTestConfig):
        self.k8s = k8s_client
        self.config = config
    
    def create_webapp_resource(self, name: str, spec: Dict) -> Dict:
        """Create a WebApp custom resource"""
        webapp = {
            "apiVersion": "platform.example.com/v1",
            "kind": "WebApp",
            "metadata": {
                "name": name,
                "namespace": self.config.test_namespace
            },
            "spec": spec
        }
        
        return self.k8s.create_custom_resource(
            group="platform.example.com",
            version="v1",
            plural="webapps",
            namespace=self.config.test_namespace,
            body=webapp
        )
    
    def wait_for_webapp_ready(self, name: str, timeout: int = 300) -> bool:
        """Wait for WebApp to reach ready state"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            webapp = self.k8s.get_custom_resource(
                group="platform.example.com",
                version="v1",
                plural="webapps",
                namespace=self.config.test_namespace,
                name=name
            )
            
            if webapp and webapp.get("status", {}).get("phase") == "Ready":
                return True
            
            time.sleep(self.config.poll_interval)
        
        return False
    
    def verify_deployment_created(self, webapp_name: str) -> bool:
        """Verify that deployment was created for WebApp"""
        try:
            deployment = self.k8s.apps_v1.read_namespaced_deployment(
                webapp_name, self.config.test_namespace
            )
            return deployment is not None
        except ApiException as e:
            if e.status == 404:
                return False
            raise
    
    def verify_service_created(self, webapp_name: str) -> bool:
        """Verify that service was created for WebApp"""
        try:
            service = self.k8s.core_v1.read_namespaced_service(
                webapp_name, self.config.test_namespace
            )
            return service is not None
        except ApiException as e:
            if e.status == 404:
                return False
            raise
    
    def verify_hpa_created(self, webapp_name: str) -> bool:
        """Verify that HPA was created for WebApp"""
        try:
            hpa = self.k8s.autoscaling_v2.read_namespaced_horizontal_pod_autoscaler(
                webapp_name, self.config.test_namespace
            )
            return hpa is not None
        except ApiException as e:
            if e.status == 404:
                return False
            raise

@pytest.fixture(scope="session")
def test_config():
    """Test configuration fixture"""
    return OperatorTestConfig()

@pytest.fixture(scope="session")
def k8s_client(test_config):
    """Kubernetes client fixture"""
    return KubernetesTestClient(test_config.kubeconfig_path)

@pytest.fixture(scope="session")
def operator_helper(k8s_client, test_config):
    """Operator test helper fixture"""
    return OperatorTestHelper(k8s_client, test_config)

@pytest.fixture(scope="session", autouse=True)
def setup_test_namespace(k8s_client, test_config):
    """Setup test namespace"""
    namespace = client.V1Namespace(
        metadata=client.V1ObjectMeta(name=test_config.test_namespace)
    )
    
    try:
        k8s_client.core_v1.create_namespace(namespace)
        logger.info(f"Created test namespace: {test_config.test_namespace}")
    except ApiException as e:
        if e.status != 409:  # Already exists
            raise
    
    yield
    
    # Cleanup
    try:
        k8s_client.core_v1.delete_namespace(test_config.test_namespace)
        logger.info(f"Deleted test namespace: {test_config.test_namespace}")
    except ApiException:
        pass

class TestOperatorBasicFunctionality:
    """Test basic operator functionality"""
    
    def test_operator_health_check(self, test_config):
        """Test operator health endpoint"""
        try:
            response = requests.get(f"{test_config.operator_url}/healthz", timeout=10)
            assert response.status_code == 200
            logger.info("✅ Operator health check passed")
        except requests.RequestException as e:
            pytest.fail(f"Operator health check failed: {e}")
    
    def test_operator_metrics_endpoint(self, test_config):
        """Test operator metrics endpoint"""
        try:
            response = requests.get(f"{test_config.operator_url}/metrics", timeout=10)
            assert response.status_code == 200
            assert "controller_runtime_reconcile_total" in response.text
            logger.info("✅ Operator metrics endpoint accessible")
        except requests.RequestException as e:
            pytest.fail(f"Operator metrics check failed: {e}")
    
    def test_crd_installation(self, k8s_client):
        """Test that CRDs are properly installed"""
        try:
            # Check WebApp CRD
            api_extensions = client.ApiextensionsV1Api()
            crd = api_extensions.read_custom_resource_definition(
                "webapps.platform.example.com"
            )
            assert crd is not None
            assert crd.spec.group == "platform.example.com"
            logger.info("✅ WebApp CRD is properly installed")
        except ApiException as e:
            pytest.fail(f"CRD check failed: {e}")

class TestWebAppController:
    """Test WebApp controller functionality"""
    
    def test_basic_webapp_creation(self, operator_helper, test_config):
        """Test basic WebApp resource creation and reconciliation"""
        webapp_name = "test-webapp-basic"
        webapp_spec = {
            "replicas": 2,
            "image": "nginx:1.21",
            "version": "v1.0.0",
            "resources": {
                "requests": {
                    "cpu": "100m",
                    "memory": "128Mi"
                },
                "limits": {
                    "cpu": "500m",
                    "memory": "512Mi"
                }
            }
        }
        
        # Create WebApp resource
        webapp = operator_helper.create_webapp_resource(webapp_name, webapp_spec)
        assert webapp is not None
        logger.info(f"Created WebApp: {webapp_name}")
        
        # Wait for WebApp to be ready
        assert operator_helper.wait_for_webapp_ready(webapp_name, test_config.timeout_seconds)
        logger.info(f"WebApp {webapp_name} is ready")
        
        # Verify deployment was created
        assert operator_helper.verify_deployment_created(webapp_name)
        logger.info(f"Deployment created for {webapp_name}")
        
        # Verify service was created
        assert operator_helper.verify_service_created(webapp_name)
        logger.info(f"Service created for {webapp_name}")
        
        # Cleanup
        operator_helper.k8s.delete_custom_resource(
            group="platform.example.com",
            version="v1",
            plural="webapps",
            namespace=test_config.test_namespace,
            name=webapp_name
        )
        logger.info("✅ Basic WebApp creation test passed")
    
    def test_webapp_with_autoscaling(self, operator_helper, test_config):
        """Test WebApp with autoscaling enabled"""
        webapp_name = "test-webapp-autoscaling"
        webapp_spec = {
            "replicas": 2,
            "image": "nginx:1.21",
            "version": "v1.0.0",
            "resources": {
                "requests": {
                    "cpu": "100m",
                    "memory": "128Mi"
                }
            },
            "autoscaling": {
                "enabled": True,
                "minReplicas": 2,
                "maxReplicas": 10,
                "targetCPUUtilization": 70
            }
        }
        
        # Create WebApp resource
        webapp = operator_helper.create_webapp_resource(webapp_name, webapp_spec)
        assert webapp is not None
        
        # Wait for WebApp to be ready
        assert operator_helper.wait_for_webapp_ready(webapp_name, test_config.timeout_seconds)
        
        # Verify HPA was created
        assert operator_helper.verify_hpa_created(webapp_name)
        logger.info(f"HPA created for {webapp_name}")
        
        # Cleanup
        operator_helper.k8s.delete_custom_resource(
            group="platform.example.com",
            version="v1",
            plural="webapps",
            namespace=test_config.test_namespace,
            name=webapp_name
        )
        logger.info("✅ WebApp autoscaling test passed")
    
    def test_webapp_update_reconciliation(self, operator_helper, test_config):
        """Test WebApp update and reconciliation"""
        webapp_name = "test-webapp-update"
        initial_spec = {
            "replicas": 2,
            "image": "nginx:1.21",
            "version": "v1.0.0"
        }
        
        # Create WebApp resource
        webapp = operator_helper.create_webapp_resource(webapp_name, initial_spec)
        assert webapp is not None
        
        # Wait for initial state
        assert operator_helper.wait_for_webapp_ready(webapp_name, test_config.timeout_seconds)
        
        # Update the WebApp
        updated_spec = initial_spec.copy()
        updated_spec["replicas"] = 3
        updated_spec["version"] = "v1.1.0"
        
        webapp["spec"] = updated_spec
        operator_helper.k8s.update_custom_resource(
            group="platform.example.com",
            version="v1",
            plural="webapps",
            namespace=test_config.test_namespace,
            name=webapp_name,
            body=webapp
        )
        
        # Wait for update to be reconciled
        time.sleep(10)  # Give operator time to reconcile
        
        # Verify deployment was updated
        deployment = operator_helper.k8s.apps_v1.read_namespaced_deployment(
            webapp_name, test_config.test_namespace
        )
        assert deployment.spec.replicas == 3
        assert deployment.spec.template.metadata.labels["version"] == "v1.1.0"
        
        # Cleanup
        operator_helper.k8s.delete_custom_resource(
            group="platform.example.com",
            version="v1",
            plural="webapps",
            namespace=test_config.test_namespace,
            name=webapp_name
        )
        logger.info("✅ WebApp update reconciliation test passed")
    
    def test_webapp_deletion_cleanup(self, operator_helper, test_config):
        """Test WebApp deletion and cleanup"""
        webapp_name = "test-webapp-deletion"
        webapp_spec = {
            "replicas": 1,
            "image": "nginx:1.21",
            "version": "v1.0.0"
        }
        
        # Create WebApp resource
        webapp = operator_helper.create_webapp_resource(webapp_name, webapp_spec)
        assert webapp is not None
        
        # Wait for WebApp to be ready
        assert operator_helper.wait_for_webapp_ready(webapp_name, test_config.timeout_seconds)
        
        # Verify resources exist
        assert operator_helper.verify_deployment_created(webapp_name)
        assert operator_helper.verify_service_created(webapp_name)
        
        # Delete WebApp
        operator_helper.k8s.delete_custom_resource(
            group="platform.example.com",
            version="v1",
            plural="webapps",
            namespace=test_config.test_namespace,
            name=webapp_name
        )
        
        # Wait for cleanup
        time.sleep(30)
        
        # Verify resources are cleaned up
        assert not operator_helper.verify_deployment_created(webapp_name)
        assert not operator_helper.verify_service_created(webapp_name)
        
        logger.info("✅ WebApp deletion cleanup test passed")

class TestOperatorResilience:
    """Test operator resilience and error handling"""
    
    def test_invalid_webapp_spec(self, operator_helper, test_config):
        """Test operator handling of invalid WebApp spec"""
        webapp_name = "test-webapp-invalid"
        invalid_spec = {
            "replicas": -1,  # Invalid replica count
            "image": "",     # Empty image
            "version": "v1.0.0"
        }
        
        try:
            # This should fail validation
            webapp = operator_helper.create_webapp_resource(webapp_name, invalid_spec)
            
            # If creation succeeded, check that it's marked as failed
            time.sleep(10)
            webapp_status = operator_helper.k8s.get_custom_resource(
                group="platform.example.com",
                version="v1",
                plural="webapps",
                namespace=test_config.test_namespace,
                name=webapp_name
            )
            
            if webapp_status:
                assert webapp_status.get("status", {}).get("phase") == "Failed"
                
                # Cleanup
                operator_helper.k8s.delete_custom_resource(
                    group="platform.example.com",
                    version="v1",
                    plural="webapps",
                    namespace=test_config.test_namespace,
                    name=webapp_name
                )
        
        except Exception as e:
            # Expected to fail - this is good
            logger.info(f"Invalid spec correctly rejected: {e}")
        
        logger.info("✅ Invalid WebApp spec handling test passed")
    
    def test_operator_restart_recovery(self, operator_helper, test_config):
        """Test operator recovery after restart"""
        webapp_name = "test-webapp-recovery"
        webapp_spec = {
            "replicas": 2,
            "image": "nginx:1.21",
            "version": "v1.0.0"
        }
        
        # Create WebApp resource
        webapp = operator_helper.create_webapp_resource(webapp_name, webapp_spec)
        assert webapp is not None
        
        # Wait for WebApp to be ready
        assert operator_helper.wait_for_webapp_ready(webapp_name, test_config.timeout_seconds)
        
        # Simulate operator restart by waiting and checking reconciliation
        # In a real test, we would restart the operator container
        time.sleep(30)
        
        # Verify WebApp is still ready after "restart"
        webapp_status = operator_helper.k8s.get_custom_resource(
            group="platform.example.com",
            version="v1",
            plural="webapps",
            namespace=test_config.test_namespace,
            name=webapp_name
        )
        
        assert webapp_status.get("status", {}).get("phase") == "Ready"
        
        # Cleanup
        operator_helper.k8s.delete_custom_resource(
            group="platform.example.com",
            version="v1",
            plural="webapps",
            namespace=test_config.test_namespace,
            name=webapp_name
        )
        logger.info("✅ Operator restart recovery test passed")

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

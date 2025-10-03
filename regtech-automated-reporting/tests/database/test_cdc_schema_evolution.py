#!/usr/bin/env python3
"""
Comprehensive CDC and Schema Evolution Tests for RegTech Automated Reporting
Tests Change Data Capture, schema registry, and backward/forward compatibility
"""

import asyncio
import json
import logging
import random
import time
import unittest
import uuid
from typing import Dict, List, Optional, Set

import requests

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CDCSchemaTestClient:
    """Test client for CDC and schema evolution operations"""
    
    def __init__(self, regtech_url: str = "http://localhost:8080"):
        self.regtech_url = regtech_url
        self.session = requests.Session()
        self.session.timeout = 30
    
    def register_schema(self, schema_data: Dict) -> Optional[Dict]:
        """Register new schema version"""
        try:
            response = self.session.post(
                f"{self.regtech_url}/api/v1/schemas",
                json=schema_data,
                headers={"Content-Type": "application/json"}
            )
            return response.json() if response.status_code == 201 else None
        except Exception as e:
            logger.error(f"Schema registration failed: {e}")
            return None
    
    def submit_data_change(self, change_data: Dict) -> Optional[Dict]:
        """Submit data change for CDC processing"""
        try:
            response = self.session.post(
                f"{self.regtech_url}/api/v1/cdc/changes",
                json=change_data,
                headers={"Content-Type": "application/json"}
            )
            return response.json() if response.status_code == 201 else None
        except Exception as e:
            logger.error(f"CDC change submission failed: {e}")
            return None
    
    def get_schema_compatibility(self, schema_id: str, new_schema: Dict) -> Optional[Dict]:
        """Check schema compatibility"""
        try:
            response = self.session.post(
                f"{self.regtech_url}/api/v1/schemas/{schema_id}/compatibility",
                json=new_schema,
                headers={"Content-Type": "application/json"}
            )
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"Schema compatibility check failed: {e}")
            return None
    
    def generate_report(self, report_request: Dict) -> Optional[Dict]:
        """Generate regulatory report"""
        try:
            response = self.session.post(
                f"{self.regtech_url}/api/v1/reports/generate",
                json=report_request,
                headers={"Content-Type": "application/json"}
            )
            return response.json() if response.status_code == 201 else None
        except Exception as e:
            logger.error(f"Report generation failed: {e}")
            return None
    
    def get_cdc_lag(self) -> Optional[Dict]:
        """Get CDC processing lag metrics"""
        try:
            response = self.session.get(f"{self.regtech_url}/api/v1/cdc/metrics")
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"CDC metrics retrieval failed: {e}")
            return None


class CDCSchemaAnalyzer:
    """Analyzer for CDC and schema evolution operations"""
    
    def __init__(self, client: CDCSchemaTestClient):
        self.client = client
        self.test_schemas: List[str] = []
        self.test_changes: List[str] = []
    
    def test_cdc_processing_latency(self, num_changes: int = 100) -> Dict:
        """Test CDC processing latency and throughput"""
        logger.info(f"Testing CDC processing with {num_changes} changes")
        
        successful_changes = 0
        processing_times = []
        
        for i in range(num_changes):
            # Generate test data change
            change_data = {
                "change_id": f"CHANGE_{i:06d}",
                "table_name": "transactions",
                "operation": random.choice(["INSERT", "UPDATE", "DELETE"]),
                "timestamp": int(time.time() * 1000),
                "data": {
                    "transaction_id": f"TXN_{i:06d}",
                    "amount": round(random.uniform(100, 10000), 2),
                    "currency": random.choice(["USD", "EUR", "GBP"]),
                    "account_id": f"ACC_{random.randint(1, 1000):06d}",
                    "status": random.choice(["PENDING", "COMPLETED", "FAILED"])
                },
                "schema_version": "v1.0"
            }
            
            processing_start = time.time()
            result = self.client.submit_data_change(change_data)
            processing_end = time.time()
            
            if result and result.get("change_id"):
                successful_changes += 1
                processing_times.append(processing_end - processing_start)
                self.test_changes.append(result["change_id"])
        
        avg_processing_time = (
            sum(processing_times) / len(processing_times)
            if processing_times else 0
        )
        
        p95_processing_time = (
            sorted(processing_times)[int(len(processing_times) * 0.95)]
            if processing_times else 0
        )
        
        # Check CDC lag
        cdc_metrics = self.client.get_cdc_lag()
        current_lag = cdc_metrics.get("lag_ms", 0) if cdc_metrics else 0
        
        return {
            "changes_processed": num_changes,
            "successful_changes": successful_changes,
            "processing_success_rate": successful_changes / num_changes,
            "average_processing_time": avg_processing_time,
            "p95_processing_time": p95_processing_time,
            "current_cdc_lag": current_lag,
            "low_latency_achieved": avg_processing_time < 0.1  # < 100ms
        }
    
    def test_schema_backward_compatibility(self, num_versions: int = 10) -> Dict:
        """Test schema backward compatibility"""
        logger.info(f"Testing schema backward compatibility with {num_versions} versions")
        
        base_schema = {
            "name": "transaction_schema",
            "version": "1.0",
            "fields": [
                {"name": "transaction_id", "type": "string", "required": True},
                {"name": "amount", "type": "decimal", "required": True},
                {"name": "currency", "type": "string", "required": True},
                {"name": "timestamp", "type": "timestamp", "required": True}
            ]
        }
        
        # Register base schema
        base_result = self.client.register_schema(base_schema)
        if not base_result or not base_result.get("schema_id"):
            return {"error": "Failed to register base schema"}
        
        base_schema_id = base_result["schema_id"]
        self.test_schemas.append(base_schema_id)
        
        compatible_versions = 0
        incompatible_versions = 0
        
        for i in range(1, num_versions + 1):
            # Create evolved schema (backward compatible changes)
            evolved_schema = {
                "name": "transaction_schema",
                "version": f"1.{i}",
                "fields": base_schema["fields"].copy()
            }
            
            # Add optional fields (backward compatible)
            if i % 2 == 0:
                evolved_schema["fields"].append({
                    "name": f"optional_field_{i}",
                    "type": "string",
                    "required": False,
                    "default": ""
                })
            
            # Add enum expansion (backward compatible)
            if i % 3 == 0:
                evolved_schema["fields"].append({
                    "name": "status",
                    "type": "enum",
                    "values": ["PENDING", "COMPLETED", "FAILED", f"NEW_STATUS_{i}"],
                    "required": False
                })
            
            # Check compatibility
            compatibility_result = self.client.get_schema_compatibility(
                base_schema_id, evolved_schema
            )
            
            if (compatibility_result and 
                compatibility_result.get("backward_compatible", False)):
                compatible_versions += 1
                
                # Register the compatible schema
                register_result = self.client.register_schema(evolved_schema)
                if register_result and register_result.get("schema_id"):
                    self.test_schemas.append(register_result["schema_id"])
            else:
                incompatible_versions += 1
                logger.warning(f"Schema version 1.{i} is not backward compatible")
        
        return {
            "versions_tested": num_versions,
            "compatible_versions": compatible_versions,
            "incompatible_versions": incompatible_versions,
            "backward_compatibility_rate": compatible_versions / num_versions,
            "schema_evolution_success": compatible_versions / num_versions > 0.8
        }
    
    def test_schema_forward_compatibility(self, num_versions: int = 8) -> Dict:
        """Test schema forward compatibility"""
        logger.info(f"Testing schema forward compatibility with {num_versions} versions")
        
        if len(self.test_schemas) == 0:
            return {"error": "No test schemas available for forward compatibility testing"}
        
        base_schema_id = self.test_schemas[0]
        forward_compatible_versions = 0
        forward_incompatible_versions = 0
        
        for i in range(num_versions):
            # Create future schema version (forward compatible changes)
            future_schema = {
                "name": "transaction_schema",
                "version": f"2.{i}",
                "fields": [
                    {"name": "transaction_id", "type": "string", "required": True},
                    {"name": "amount", "type": "decimal", "required": True},
                    {"name": "currency", "type": "string", "required": True},
                    {"name": "timestamp", "type": "timestamp", "required": True}
                ]
            }
            
            # Remove optional fields (forward compatible)
            if i % 2 == 0:
                future_schema["fields"] = future_schema["fields"][:-1]  # Remove last field
            
            # Change field order (should be forward compatible)
            if i % 3 == 0:
                random.shuffle(future_schema["fields"])
            
            # Check forward compatibility
            compatibility_result = self.client.get_schema_compatibility(
                base_schema_id, future_schema
            )
            
            if (compatibility_result and 
                compatibility_result.get("forward_compatible", False)):
                forward_compatible_versions += 1
            else:
                forward_incompatible_versions += 1
                logger.warning(f"Future schema version 2.{i} is not forward compatible")
        
        return {
            "future_versions_tested": num_versions,
            "forward_compatible_versions": forward_compatible_versions,
            "forward_incompatible_versions": forward_incompatible_versions,
            "forward_compatibility_rate": forward_compatible_versions / num_versions,
            "forward_evolution_success": forward_compatible_versions / num_versions > 0.6
        }
    
    def test_report_generation_consistency(self, num_reports: int = 20) -> Dict:
        """Test report generation consistency across schema versions"""
        logger.info(f"Testing report generation consistency with {num_reports} reports")
        
        if len(self.test_changes) < 50:
            return {"error": "Insufficient test changes for report generation testing"}
        
        successful_reports = 0
        failed_reports = 0
        generation_times = []
        
        for i in range(num_reports):
            report_request = {
                "report_id": f"REPORT_{i:06d}",
                "report_type": random.choice(["TRANSACTION_SUMMARY", "COMPLIANCE_REPORT", "AUDIT_TRAIL"]),
                "date_range": {
                    "start": "2024-01-01T00:00:00Z",
                    "end": "2024-01-31T23:59:59Z"
                },
                "schema_version": random.choice(["v1.0", "v1.1", "v1.2"]),
                "format": random.choice(["JSON", "XML", "CSV"])
            }
            
            generation_start = time.time()
            result = self.client.generate_report(report_request)
            generation_end = time.time()
            
            if result and result.get("report_id"):
                successful_reports += 1
                generation_times.append(generation_end - generation_start)
                
                # Verify report contains expected fields
                report_data = result.get("data", {})
                if not report_data.get("records"):
                    logger.warning(f"Report {result['report_id']} contains no records")
            else:
                failed_reports += 1
        
        avg_generation_time = (
            sum(generation_times) / len(generation_times)
            if generation_times else 0
        )
        
        return {
            "reports_requested": num_reports,
            "successful_reports": successful_reports,
            "failed_reports": failed_reports,
            "report_success_rate": successful_reports / num_reports,
            "average_generation_time": avg_generation_time,
            "generation_efficiency": avg_generation_time < 10.0  # < 10 seconds
        }
    
    def cleanup_test_data(self):
        """Clean up test data"""
        for schema_id in self.test_schemas:
            try:
                self.client.session.delete(f"{self.client.regtech_url}/api/v1/schemas/{schema_id}")
            except Exception:
                pass
        
        for change_id in self.test_changes:
            try:
                self.client.session.delete(f"{self.client.regtech_url}/api/v1/cdc/changes/{change_id}")
            except Exception:
                pass
        
        self.test_schemas.clear()
        self.test_changes.clear()


class TestCDCSchemaEvolution(unittest.TestCase):
    """Test cases for CDC and schema evolution"""
    
    @classmethod
    def setUpClass(cls):
        cls.client = CDCSchemaTestClient()
        cls.analyzer = CDCSchemaAnalyzer(cls.client)
        
        # Wait for RegTech system to be ready
        max_retries = 30
        for i in range(max_retries):
            try:
                # Try to get CDC metrics to verify system is ready
                metrics = cls.client.get_cdc_lag()
                if metrics is not None:
                    logger.info("RegTech automated reporting system is ready")
                    break
            except Exception:
                pass
            time.sleep(1)
        else:
            raise Exception("RegTech system not ready after 30 seconds")
    
    @classmethod
    def tearDownClass(cls):
        cls.analyzer.cleanup_test_data()
    
    def test_cdc_processing_performance(self):
        """Test CDC processing performance and latency"""
        result = self.analyzer.test_cdc_processing_latency(num_changes=50)
        
        self.assertNotIn("error", result)
        self.assertGreater(result["processing_success_rate"], 0.90)
        self.assertTrue(result["low_latency_achieved"])
        
        logger.info(f"CDC Processing Test: {result}")
    
    def test_backward_schema_compatibility(self):
        """Test backward schema compatibility"""
        result = self.analyzer.test_schema_backward_compatibility(num_versions=5)
        
        self.assertNotIn("error", result)
        self.assertGreater(result["backward_compatibility_rate"], 0.80)
        self.assertTrue(result["schema_evolution_success"])
        
        logger.info(f"Backward Compatibility Test: {result}")
    
    def test_forward_schema_compatibility(self):
        """Test forward schema compatibility"""
        result = self.analyzer.test_schema_forward_compatibility(num_versions=4)
        
        self.assertNotIn("error", result)
        self.assertGreater(result["forward_compatibility_rate"], 0.60)
        self.assertTrue(result["forward_evolution_success"])
        
        logger.info(f"Forward Compatibility Test: {result}")
    
    def test_cross_version_report_generation(self):
        """Test report generation consistency across schema versions"""
        result = self.analyzer.test_report_generation_consistency(num_reports=10)
        
        self.assertNotIn("error", result)
        self.assertGreater(result["report_success_rate"], 0.85)
        self.assertTrue(result["generation_efficiency"])
        
        logger.info(f"Report Generation Test: {result}")


if __name__ == "__main__":
    unittest.main()

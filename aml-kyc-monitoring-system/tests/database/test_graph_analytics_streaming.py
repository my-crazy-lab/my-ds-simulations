#!/usr/bin/env python3
"""
Comprehensive Graph Analytics and Streaming Tests for AML/KYC Monitoring
Tests streaming enrichments, graph pattern detection, and compliance features
"""

import asyncio
import json
import logging
import random
import time
import unittest
import uuid
from typing import Dict, List, Optional, Set, Tuple

import requests

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class GraphAnalyticsStreamingTestClient:
    """Test client for graph analytics and streaming operations"""
    
    def __init__(self, aml_system_url: str = "http://localhost:8080"):
        self.aml_system_url = aml_system_url
        self.session = requests.Session()
        self.session.timeout = 30
    
    def submit_transaction_event(self, transaction_data: Dict) -> Optional[Dict]:
        """Submit transaction event for monitoring"""
        try:
            response = self.session.post(
                f"{self.aml_system_url}/api/v1/transactions/events",
                json=transaction_data,
                headers={"Content-Type": "application/json"}
            )
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"Transaction event submission failed: {e}")
            return None
    
    def create_customer_profile(self, customer_data: Dict) -> Optional[Dict]:
        """Create customer profile for KYC"""
        try:
            response = self.session.post(
                f"{self.aml_system_url}/api/v1/customers",
                json=customer_data,
                headers={"Content-Type": "application/json"}
            )
            return response.json() if response.status_code == 201 else None
        except Exception as e:
            logger.error(f"Customer profile creation failed: {e}")
            return None
    
    def update_customer_risk_score(self, customer_id: str, risk_data: Dict) -> bool:
        """Update customer risk score"""
        try:
            response = self.session.put(
                f"{self.aml_system_url}/api/v1/customers/{customer_id}/risk-score",
                json=risk_data,
                headers={"Content-Type": "application/json"}
            )
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Risk score update failed: {e}")
            return False
    
    def query_transaction_graph(self, query_params: Dict) -> Optional[Dict]:
        """Query transaction graph for patterns"""
        try:
            response = self.session.post(
                f"{self.aml_system_url}/api/v1/graph/query",
                json=query_params,
                headers={"Content-Type": "application/json"}
            )
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"Graph query failed: {e}")
            return None
    
    def get_connected_components(self, customer_id: str, max_depth: int = 3) -> Optional[Dict]:
        """Get connected components for customer"""
        try:
            response = self.session.get(
                f"{self.aml_system_url}/api/v1/graph/connected-components/{customer_id}",
                params={"max_depth": max_depth}
            )
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"Connected components query failed: {e}")
            return None
    
    def create_alert(self, alert_data: Dict) -> Optional[Dict]:
        """Create AML alert"""
        try:
            response = self.session.post(
                f"{self.aml_system_url}/api/v1/alerts",
                json=alert_data,
                headers={"Content-Type": "application/json"}
            )
            return response.json() if response.status_code == 201 else None
        except Exception as e:
            logger.error(f"Alert creation failed: {e}")
            return None
    
    def get_alerts(self, customer_id: str = None, status: str = None) -> Optional[List[Dict]]:
        """Get alerts with optional filters"""
        try:
            params = {}
            if customer_id:
                params["customer_id"] = customer_id
            if status:
                params["status"] = status
            
            response = self.session.get(
                f"{self.aml_system_url}/api/v1/alerts",
                params=params
            )
            return response.json().get("alerts", []) if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"Alerts retrieval failed: {e}")
            return None
    
    def enrich_transaction_data(self, transaction_id: str, enrichment_sources: List[str]) -> Optional[Dict]:
        """Enrich transaction with external data sources"""
        try:
            response = self.session.post(
                f"{self.aml_system_url}/api/v1/enrichment/transaction/{transaction_id}",
                json={"sources": enrichment_sources},
                headers={"Content-Type": "application/json"}
            )
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"Transaction enrichment failed: {e}")
            return None
    
    def get_feature_store_data(self, customer_id: str, feature_names: List[str]) -> Optional[Dict]:
        """Get feature store data for customer"""
        try:
            response = self.session.get(
                f"{self.aml_system_url}/api/v1/features/{customer_id}",
                params={"features": ",".join(feature_names)}
            )
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"Feature store query failed: {e}")
            return None
    
    def trigger_model_scoring(self, customer_id: str, model_name: str) -> Optional[Dict]:
        """Trigger ML model scoring for customer"""
        try:
            response = self.session.post(
                f"{self.aml_system_url}/api/v1/scoring/{model_name}",
                json={"customer_id": customer_id},
                headers={"Content-Type": "application/json"}
            )
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"Model scoring failed: {e}")
            return None
    
    def simulate_late_arriving_data(self, transaction_id: str, delay_minutes: int) -> bool:
        """Simulate late-arriving enrichment data"""
        try:
            response = self.session.post(
                f"{self.aml_system_url}/api/v1/test/late-data",
                json={
                    "transaction_id": transaction_id,
                    "delay_minutes": delay_minutes
                }
            )
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Late data simulation failed: {e}")
            return False
    
    def request_gdpr_erasure(self, customer_id: str, erasure_type: str = "full") -> Optional[Dict]:
        """Request GDPR data erasure"""
        try:
            response = self.session.post(
                f"{self.aml_system_url}/api/v1/gdpr/erasure",
                json={
                    "customer_id": customer_id,
                    "erasure_type": erasure_type,
                    "reason": "customer_request"
                },
                headers={"Content-Type": "application/json"}
            )
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"GDPR erasure request failed: {e}")
            return None


class GraphAnalyticsStreamingAnalyzer:
    """Analyzer for graph analytics and streaming behavior"""
    
    def __init__(self, client: GraphAnalyticsStreamingTestClient):
        self.client = client
        self.test_customers: List[str] = []
        self.test_transactions: List[str] = []
    
    def test_streaming_enrichment_performance(self, num_transactions: int = 100) -> Dict:
        """Test streaming enrichment performance and accuracy"""
        logger.info(f"Testing streaming enrichment with {num_transactions} transactions")
        
        # Create test customers
        customers = []
        for i in range(10):
            customer_data = {
                "customer_id": f"CUST{i:06d}",
                "name": f"Test Customer {i}",
                "country": random.choice(["US", "UK", "DE", "FR", "JP"]),
                "risk_category": random.choice(["LOW", "MEDIUM", "HIGH"]),
                "onboarding_date": "2024-01-01"
            }
            
            result = self.client.create_customer_profile(customer_data)
            if result:
                customers.append(customer_data["customer_id"])
                self.test_customers.append(customer_data["customer_id"])
        
        if len(customers) < 8:
            return {"error": "Failed to create sufficient test customers"}
        
        # Submit transactions for enrichment
        successful_submissions = 0
        enrichment_successes = 0
        enrichment_latencies = []
        
        for i in range(num_transactions):
            transaction_data = {
                "transaction_id": f"TXN{i:08d}",
                "customer_id": random.choice(customers),
                "amount": round(random.uniform(100, 50000), 2),
                "currency": random.choice(["USD", "EUR", "GBP"]),
                "counterparty": f"COUNTERPARTY{random.randint(1, 100)}",
                "transaction_type": random.choice(["WIRE", "ACH", "CARD"]),
                "timestamp": int(time.time() * 1000)
            }
            
            # Submit transaction
            submit_start = time.time()
            result = self.client.submit_transaction_event(transaction_data)
            
            if result and result.get("transaction_id"):
                successful_submissions += 1
                self.test_transactions.append(result["transaction_id"])
                
                # Trigger enrichment
                enrichment_sources = ["sanctions_list", "pep_list", "adverse_media"]
                enrichment_start = time.time()
                
                enrichment_result = self.client.enrich_transaction_data(
                    result["transaction_id"],
                    enrichment_sources
                )
                
                enrichment_end = time.time()
                
                if enrichment_result:
                    enrichment_successes += 1
                    enrichment_latencies.append(enrichment_end - enrichment_start)
        
        # Calculate metrics
        avg_enrichment_latency = (
            sum(enrichment_latencies) / len(enrichment_latencies) 
            if enrichment_latencies else 0
        )
        
        return {
            "total_transactions": num_transactions,
            "successful_submissions": successful_submissions,
            "enrichment_successes": enrichment_successes,
            "enrichment_success_rate": enrichment_successes / successful_submissions if successful_submissions > 0 else 0,
            "average_enrichment_latency": avg_enrichment_latency,
            "max_enrichment_latency": max(enrichment_latencies) if enrichment_latencies else 0
        }
    
    def test_graph_pattern_detection(self, num_patterns: int = 20) -> Dict:
        """Test graph pattern detection for suspicious activities"""
        logger.info(f"Testing graph pattern detection with {num_patterns} patterns")
        
        if len(self.test_customers) < 5:
            return {"error": "Insufficient test customers for graph analysis"}
        
        # Create suspicious transaction patterns
        pattern_alerts = 0
        false_positives = 0
        pattern_detection_times = []
        
        for i in range(num_patterns):
            # Create circular transaction pattern (potential money laundering)
            pattern_customers = random.sample(self.test_customers, 4)
            pattern_amount = round(random.uniform(10000, 100000), 2)
            
            # Create circular transactions
            for j in range(len(pattern_customers)):
                from_customer = pattern_customers[j]
                to_customer = pattern_customers[(j + 1) % len(pattern_customers)]
                
                transaction_data = {
                    "transaction_id": f"PATTERN{i:03d}_{j}",
                    "customer_id": from_customer,
                    "counterparty_id": to_customer,
                    "amount": pattern_amount * (0.95 ** j),  # Decreasing amounts
                    "currency": "USD",
                    "transaction_type": "WIRE",
                    "timestamp": int(time.time() * 1000) + j * 1000
                }
                
                self.client.submit_transaction_event(transaction_data)
            
            # Wait for pattern processing
            time.sleep(1)
            
            # Query for circular patterns
            pattern_start = time.time()
            
            query_params = {
                "pattern_type": "circular_transactions",
                "min_amount": pattern_amount * 0.5,
                "time_window": 3600,  # 1 hour
                "min_participants": 3
            }
            
            pattern_result = self.client.query_transaction_graph(query_params)
            pattern_end = time.time()
            
            if pattern_result and pattern_result.get("patterns"):
                pattern_alerts += 1
                pattern_detection_times.append(pattern_end - pattern_start)
                
                # Check if detected pattern matches our created pattern
                detected_patterns = pattern_result["patterns"]
                matching_pattern = any(
                    set(pattern.get("participants", [])).intersection(set(pattern_customers))
                    for pattern in detected_patterns
                )
                
                if not matching_pattern:
                    false_positives += 1
        
        avg_detection_time = (
            sum(pattern_detection_times) / len(pattern_detection_times)
            if pattern_detection_times else 0
        )
        
        return {
            "num_patterns": num_patterns,
            "pattern_alerts": pattern_alerts,
            "false_positives": false_positives,
            "detection_accuracy": (pattern_alerts - false_positives) / pattern_alerts if pattern_alerts > 0 else 0,
            "average_detection_time": avg_detection_time,
            "pattern_detection_rate": pattern_alerts / num_patterns
        }
    
    def test_feature_store_consistency(self, num_customers: int = 20) -> Dict:
        """Test feature store consistency across streaming and batch updates"""
        logger.info(f"Testing feature store consistency with {num_customers} customers")
        
        customers_to_test = self.test_customers[:num_customers] if len(self.test_customers) >= num_customers else self.test_customers
        
        if len(customers_to_test) < 10:
            return {"error": "Insufficient customers for feature store testing"}
        
        consistent_features = 0
        inconsistent_features = 0
        feature_retrieval_times = []
        
        feature_names = [
            "transaction_velocity_7d",
            "high_risk_counterparties",
            "cross_border_ratio",
            "cash_intensive_ratio",
            "risk_score"
        ]
        
        for customer_id in customers_to_test:
            # Get features from feature store
            retrieval_start = time.time()
            features = self.client.get_feature_store_data(customer_id, feature_names)
            retrieval_end = time.time()
            
            if features:
                feature_retrieval_times.append(retrieval_end - retrieval_start)
                
                # Verify feature consistency
                feature_values = features.get("features", {})
                
                # Check if all requested features are present
                if all(feature in feature_values for feature in feature_names):
                    consistent_features += 1
                    
                    # Trigger model scoring to test feature consistency
                    scoring_result = self.client.trigger_model_scoring(customer_id, "aml_risk_model")
                    
                    if not scoring_result:
                        inconsistent_features += 1
                else:
                    inconsistent_features += 1
            else:
                inconsistent_features += 1
        
        avg_retrieval_time = (
            sum(feature_retrieval_times) / len(feature_retrieval_times)
            if feature_retrieval_times else 0
        )
        
        return {
            "customers_tested": len(customers_to_test),
            "consistent_features": consistent_features,
            "inconsistent_features": inconsistent_features,
            "feature_consistency_rate": consistent_features / len(customers_to_test),
            "average_retrieval_time": avg_retrieval_time
        }
    
    def test_late_arriving_data_handling(self, num_transactions: int = 15) -> Dict:
        """Test handling of late-arriving enrichment data"""
        logger.info(f"Testing late-arriving data handling with {num_transactions} transactions")
        
        if not self.test_transactions:
            return {"error": "No test transactions available"}
        
        transactions_to_test = self.test_transactions[:num_transactions]
        
        late_data_handled = 0
        alert_updates = 0
        
        for transaction_id in transactions_to_test:
            # Get initial alerts for transaction
            initial_alerts = self.client.get_alerts()
            initial_alert_count = len([a for a in initial_alerts if a.get("transaction_id") == transaction_id]) if initial_alerts else 0
            
            # Simulate late-arriving data
            delay_minutes = random.randint(5, 30)
            late_data_success = self.client.simulate_late_arriving_data(transaction_id, delay_minutes)
            
            if late_data_success:
                late_data_handled += 1
                
                # Wait for processing
                time.sleep(2)
                
                # Check if alerts were updated
                updated_alerts = self.client.get_alerts()
                updated_alert_count = len([a for a in updated_alerts if a.get("transaction_id") == transaction_id]) if updated_alerts else 0
                
                if updated_alert_count != initial_alert_count:
                    alert_updates += 1
        
        return {
            "transactions_tested": len(transactions_to_test),
            "late_data_handled": late_data_handled,
            "alert_updates": alert_updates,
            "late_data_handling_rate": late_data_handled / len(transactions_to_test),
            "alert_update_rate": alert_updates / late_data_handled if late_data_handled > 0 else 0
        }
    
    def test_gdpr_compliance_erasure(self, num_customers: int = 5) -> Dict:
        """Test GDPR compliance with selective data erasure"""
        logger.info(f"Testing GDPR compliance with {num_customers} customers")
        
        customers_to_erase = self.test_customers[:num_customers] if len(self.test_customers) >= num_customers else self.test_customers
        
        if len(customers_to_erase) < 3:
            return {"error": "Insufficient customers for GDPR testing"}
        
        successful_erasures = 0
        verification_failures = 0
        
        for customer_id in customers_to_erase:
            # Request GDPR erasure
            erasure_result = self.client.request_gdpr_erasure(customer_id, "full")
            
            if erasure_result and erasure_result.get("status") == "accepted":
                successful_erasures += 1
                
                # Wait for erasure processing
                time.sleep(3)
                
                # Verify data has been erased/anonymized
                # Try to get customer features (should be anonymized or empty)
                features = self.client.get_feature_store_data(customer_id, ["risk_score"])
                
                if features and features.get("features"):
                    # Check if data is properly anonymized
                    risk_score = features["features"].get("risk_score")
                    if risk_score is not None and risk_score != "ANONYMIZED":
                        verification_failures += 1
        
        return {
            "customers_tested": len(customers_to_erase),
            "successful_erasures": successful_erasures,
            "verification_failures": verification_failures,
            "gdpr_compliance_rate": (successful_erasures - verification_failures) / len(customers_to_erase),
            "erasure_success_rate": successful_erasures / len(customers_to_erase)
        }
    
    def cleanup_test_data(self):
        """Clean up test data"""
        for customer_id in self.test_customers:
            try:
                self.client.session.delete(f"{self.client.aml_system_url}/api/v1/customers/{customer_id}")
            except Exception:
                pass
        
        for transaction_id in self.test_transactions:
            try:
                self.client.session.delete(f"{self.client.aml_system_url}/api/v1/transactions/{transaction_id}")
            except Exception:
                pass
        
        self.test_customers.clear()
        self.test_transactions.clear()


class TestGraphAnalyticsStreaming(unittest.TestCase):
    """Test cases for graph analytics and streaming"""
    
    @classmethod
    def setUpClass(cls):
        cls.client = GraphAnalyticsStreamingTestClient()
        cls.analyzer = GraphAnalyticsStreamingAnalyzer(cls.client)
        
        # Wait for AML system to be ready
        max_retries = 30
        for i in range(max_retries):
            try:
                # Try to create a test customer to verify system is ready
                test_customer = {
                    "customer_id": "HEALTH_CHECK",
                    "name": "Health Check Customer",
                    "country": "US",
                    "risk_category": "LOW"
                }
                result = cls.client.create_customer_profile(test_customer)
                if result:
                    logger.info("AML/KYC monitoring system is ready")
                    break
            except Exception:
                pass
            time.sleep(1)
        else:
            raise Exception("AML/KYC monitoring system not ready after 30 seconds")
    
    @classmethod
    def tearDownClass(cls):
        cls.analyzer.cleanup_test_data()
    
    def test_streaming_enrichment_accuracy(self):
        """Test streaming enrichment performance and accuracy"""
        result = self.analyzer.test_streaming_enrichment_performance(num_transactions=30)
        
        self.assertNotIn("error", result)
        self.assertGreater(result["enrichment_success_rate"], 0.85)
        self.assertLess(result["average_enrichment_latency"], 2.0)  # < 2 seconds
        
        logger.info(f"Streaming Enrichment Test: {result}")
    
    def test_suspicious_pattern_detection(self):
        """Test graph pattern detection for suspicious activities"""
        result = self.analyzer.test_graph_pattern_detection(num_patterns=10)
        
        self.assertNotIn("error", result)
        self.assertGreater(result["detection_accuracy"], 0.80)
        self.assertGreater(result["pattern_detection_rate"], 0.70)
        
        logger.info(f"Pattern Detection Test: {result}")
    
    def test_feature_store_data_consistency(self):
        """Test feature store consistency across updates"""
        result = self.analyzer.test_feature_store_consistency(num_customers=10)
        
        self.assertNotIn("error", result)
        self.assertGreater(result["feature_consistency_rate"], 0.90)
        self.assertLess(result["average_retrieval_time"], 1.0)  # < 1 second
        
        logger.info(f"Feature Store Consistency Test: {result}")
    
    def test_late_data_impact_on_alerts(self):
        """Test impact of late-arriving data on alerting"""
        result = self.analyzer.test_late_arriving_data_handling(num_transactions=8)
        
        self.assertNotIn("error", result)
        self.assertGreater(result["late_data_handling_rate"], 0.80)
        
        logger.info(f"Late Data Handling Test: {result}")
    
    def test_gdpr_data_erasure_compliance(self):
        """Test GDPR compliance with data erasure"""
        result = self.analyzer.test_gdpr_compliance_erasure(num_customers=3)
        
        self.assertNotIn("error", result)
        self.assertGreater(result["gdpr_compliance_rate"], 0.90)
        self.assertEqual(result["verification_failures"], 0)
        
        logger.info(f"GDPR Compliance Test: {result}")


if __name__ == "__main__":
    unittest.main()

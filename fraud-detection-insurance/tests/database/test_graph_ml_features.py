#!/usr/bin/env python3
"""
Comprehensive Graph Analytics and ML Features Tests for Fraud Detection Insurance
Tests graph-based fraud detection, ML feature consistency, and claims processing
"""

import asyncio
import json
import logging
import random
import time
import unittest
import uuid
from decimal import Decimal
from typing import Dict, List, Optional, Set

import requests

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class GraphMLFeaturesTestClient:
    """Test client for graph analytics and ML features operations"""
    
    def __init__(self, fraud_detection_url: str = "http://localhost:8080"):
        self.fraud_detection_url = fraud_detection_url
        self.session = requests.Session()
        self.session.timeout = 30
    
    def submit_claim(self, claim_data: Dict) -> Optional[Dict]:
        """Submit insurance claim for fraud detection"""
        try:
            response = self.session.post(
                f"{self.fraud_detection_url}/api/v1/claims",
                json=claim_data,
                headers={"Content-Type": "application/json"}
            )
            return response.json() if response.status_code == 201 else None
        except Exception as e:
            logger.error(f"Claim submission failed: {e}")
            return None
    
    def get_fraud_score(self, claim_id: str) -> Optional[Dict]:
        """Get fraud score for claim"""
        try:
            response = self.session.get(f"{self.fraud_detection_url}/api/v1/claims/{claim_id}/fraud-score")
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"Fraud score retrieval failed: {e}")
            return None
    
    def get_connected_entities(self, entity_id: str, entity_type: str) -> Optional[Dict]:
        """Get connected entities in fraud network"""
        try:
            response = self.session.get(
                f"{self.fraud_detection_url}/api/v1/graph/connected/{entity_type}/{entity_id}"
            )
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"Connected entities retrieval failed: {e}")
            return None
    
    def get_ml_features(self, claim_id: str) -> Optional[Dict]:
        """Get ML features for claim"""
        try:
            response = self.session.get(f"{self.fraud_detection_url}/api/v1/features/{claim_id}")
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"ML features retrieval failed: {e}")
            return None
    
    def trigger_model_scoring(self, claim_id: str, model_name: str = "fraud_detection_v2") -> Optional[Dict]:
        """Trigger ML model scoring"""
        try:
            response = self.session.post(
                f"{self.fraud_detection_url}/api/v1/scoring/{model_name}",
                json={"claim_id": claim_id},
                headers={"Content-Type": "application/json"}
            )
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"Model scoring failed: {e}")
            return None


class GraphMLFeaturesAnalyzer:
    """Analyzer for graph analytics and ML features"""
    
    def __init__(self, client: GraphMLFeaturesTestClient):
        self.client = client
        self.test_claims: List[str] = []
    
    def test_graph_fraud_detection_accuracy(self, num_claims: int = 50) -> Dict:
        """Test graph-based fraud detection accuracy"""
        logger.info(f"Testing graph fraud detection with {num_claims} claims")
        
        legitimate_claims = 0
        fraudulent_claims = 0
        correct_detections = 0
        false_positives = 0
        false_negatives = 0
        
        for i in range(num_claims):
            # Create claim with known fraud indicators
            is_fraudulent = random.random() < 0.3  # 30% fraud rate
            
            claim_data = {
                "claim_id": f"CLAIM_{i:06d}",
                "policy_id": f"POLICY_{random.randint(1, 1000):06d}",
                "claimant_id": f"CLAIMANT_{random.randint(1, 500):06d}",
                "claim_amount": round(random.uniform(1000, 100000), 2),
                "claim_type": random.choice(["AUTO", "HOME", "HEALTH", "LIFE"]),
                "incident_date": "2024-01-15",
                "claim_date": "2024-01-20",
                "description": f"Test claim {i}",
                # Add fraud indicators for fraudulent claims
                "suspicious_indicators": {
                    "multiple_recent_claims": is_fraudulent and random.random() < 0.7,
                    "high_claim_amount": is_fraudulent and random.random() < 0.5,
                    "suspicious_timing": is_fraudulent and random.random() < 0.6,
                    "known_fraudster_network": is_fraudulent and random.random() < 0.4
                } if is_fraudulent else {}
            }
            
            result = self.client.submit_claim(claim_data)
            
            if result and result.get("claim_id"):
                claim_id = result["claim_id"]
                self.test_claims.append(claim_id)
                
                if is_fraudulent:
                    fraudulent_claims += 1
                else:
                    legitimate_claims += 1
                
                # Wait for processing
                time.sleep(0.5)
                
                # Get fraud score
                fraud_score_result = self.client.get_fraud_score(claim_id)
                
                if fraud_score_result:
                    fraud_score = fraud_score_result.get("fraud_score", 0.0)
                    is_flagged_fraudulent = fraud_score > 0.7  # Threshold
                    
                    if is_fraudulent and is_flagged_fraudulent:
                        correct_detections += 1
                    elif is_fraudulent and not is_flagged_fraudulent:
                        false_negatives += 1
                    elif not is_fraudulent and is_flagged_fraudulent:
                        false_positives += 1
                    elif not is_fraudulent and not is_flagged_fraudulent:
                        correct_detections += 1
        
        total_processed = legitimate_claims + fraudulent_claims
        accuracy = correct_detections / total_processed if total_processed > 0 else 0
        precision = correct_detections / (correct_detections + false_positives) if (correct_detections + false_positives) > 0 else 0
        recall = correct_detections / (correct_detections + false_negatives) if (correct_detections + false_negatives) > 0 else 0
        
        return {
            "total_claims": num_claims,
            "legitimate_claims": legitimate_claims,
            "fraudulent_claims": fraudulent_claims,
            "correct_detections": correct_detections,
            "false_positives": false_positives,
            "false_negatives": false_negatives,
            "accuracy": accuracy,
            "precision": precision,
            "recall": recall,
            "f1_score": 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
        }
    
    def test_ml_feature_consistency(self, num_claims: int = 30) -> Dict:
        """Test ML feature consistency across scoring runs"""
        logger.info(f"Testing ML feature consistency with {num_claims} claims")
        
        if len(self.test_claims) < num_claims:
            return {"error": "Insufficient test claims for feature consistency testing"}
        
        consistent_features = 0
        inconsistent_features = 0
        feature_retrieval_times = []
        
        claims_to_test = self.test_claims[:num_claims]
        
        for claim_id in claims_to_test:
            # Get features multiple times to test consistency
            retrieval_start = time.time()
            features_1 = self.client.get_ml_features(claim_id)
            retrieval_end = time.time()
            
            if features_1:
                feature_retrieval_times.append(retrieval_end - retrieval_start)
                
                time.sleep(0.1)  # Brief delay
                
                features_2 = self.client.get_ml_features(claim_id)
                
                if features_2:
                    # Compare feature values (should be identical for same claim)
                    features_1_values = features_1.get("features", {})
                    features_2_values = features_2.get("features", {})
                    
                    if features_1_values == features_2_values:
                        consistent_features += 1
                    else:
                        inconsistent_features += 1
                        logger.warning(f"Feature inconsistency detected for claim {claim_id}")
                else:
                    inconsistent_features += 1
            else:
                inconsistent_features += 1
        
        avg_retrieval_time = (
            sum(feature_retrieval_times) / len(feature_retrieval_times)
            if feature_retrieval_times else 0
        )
        
        return {
            "claims_tested": len(claims_to_test),
            "consistent_features": consistent_features,
            "inconsistent_features": inconsistent_features,
            "feature_consistency_rate": consistent_features / len(claims_to_test),
            "average_retrieval_time": avg_retrieval_time
        }
    
    def test_connected_entity_analysis(self, num_entities: int = 20) -> Dict:
        """Test connected entity analysis in fraud networks"""
        logger.info(f"Testing connected entity analysis with {num_entities} entities")
        
        if len(self.test_claims) < 10:
            return {"error": "Insufficient test claims for entity analysis"}
        
        successful_analyses = 0
        network_discoveries = 0
        
        # Test different entity types
        entity_types = ["claimant", "policy", "provider", "adjuster"]
        
        for i in range(num_entities):
            entity_type = random.choice(entity_types)
            entity_id = f"{entity_type.upper()}_{random.randint(1, 100):06d}"
            
            connected_result = self.client.get_connected_entities(entity_id, entity_type)
            
            if connected_result:
                successful_analyses += 1
                
                connected_entities = connected_result.get("connected_entities", [])
                
                # Check for suspicious patterns
                if len(connected_entities) > 5:  # High connectivity might indicate fraud network
                    network_discoveries += 1
                    
                    # Analyze connection strength
                    strong_connections = [
                        conn for conn in connected_entities 
                        if conn.get("connection_strength", 0) > 0.7
                    ]
                    
                    if len(strong_connections) > 2:
                        logger.info(f"Potential fraud network detected around {entity_id}")
        
        return {
            "entities_analyzed": num_entities,
            "successful_analyses": successful_analyses,
            "network_discoveries": network_discoveries,
            "analysis_success_rate": successful_analyses / num_entities,
            "network_discovery_rate": network_discoveries / successful_analyses if successful_analyses > 0 else 0
        }
    
    def test_model_scoring_performance(self, num_scorings: int = 25) -> Dict:
        """Test ML model scoring performance"""
        logger.info(f"Testing model scoring performance with {num_scorings} scorings")
        
        if len(self.test_claims) < num_scorings:
            return {"error": "Insufficient test claims for scoring performance testing"}
        
        successful_scorings = 0
        failed_scorings = 0
        scoring_times = []
        
        claims_to_score = self.test_claims[:num_scorings]
        
        for claim_id in claims_to_score:
            scoring_start = time.time()
            scoring_result = self.client.trigger_model_scoring(claim_id, "fraud_detection_v2")
            scoring_end = time.time()
            
            if scoring_result and scoring_result.get("fraud_score") is not None:
                successful_scorings += 1
                scoring_times.append(scoring_end - scoring_start)
                
                # Verify score is within valid range
                fraud_score = scoring_result.get("fraud_score", 0.0)
                if not (0.0 <= fraud_score <= 1.0):
                    logger.warning(f"Invalid fraud score {fraud_score} for claim {claim_id}")
            else:
                failed_scorings += 1
        
        avg_scoring_time = sum(scoring_times) / len(scoring_times) if scoring_times else 0
        p95_scoring_time = sorted(scoring_times)[int(len(scoring_times) * 0.95)] if scoring_times else 0
        
        return {
            "scorings_attempted": num_scorings,
            "successful_scorings": successful_scorings,
            "failed_scorings": failed_scorings,
            "scoring_success_rate": successful_scorings / num_scorings,
            "average_scoring_time": avg_scoring_time,
            "p95_scoring_time": p95_scoring_time,
            "performance_acceptable": avg_scoring_time < 2.0  # < 2 seconds
        }
    
    def cleanup_test_data(self):
        """Clean up test data"""
        for claim_id in self.test_claims:
            try:
                self.client.session.delete(f"{self.client.fraud_detection_url}/api/v1/claims/{claim_id}")
            except Exception:
                pass
        self.test_claims.clear()


class TestGraphMLFeatures(unittest.TestCase):
    """Test cases for graph analytics and ML features"""
    
    @classmethod
    def setUpClass(cls):
        cls.client = GraphMLFeaturesTestClient()
        cls.analyzer = GraphMLFeaturesAnalyzer(cls.client)
        
        # Wait for fraud detection system to be ready
        max_retries = 30
        for i in range(max_retries):
            try:
                # Try to submit a test claim to verify system is ready
                test_claim = {
                    "claim_id": "HEALTH_CHECK",
                    "policy_id": "POLICY_000000",
                    "claimant_id": "CLAIMANT_000000",
                    "claim_amount": 1000.00,
                    "claim_type": "AUTO"
                }
                result = cls.client.submit_claim(test_claim)
                if result:
                    logger.info("Fraud detection system is ready")
                    break
            except Exception:
                pass
            time.sleep(1)
        else:
            raise Exception("Fraud detection system not ready after 30 seconds")
    
    @classmethod
    def tearDownClass(cls):
        cls.analyzer.cleanup_test_data()
    
    def test_graph_based_fraud_detection(self):
        """Test graph-based fraud detection accuracy"""
        result = self.analyzer.test_graph_fraud_detection_accuracy(num_claims=20)
        
        self.assertNotIn("error", result)
        self.assertGreater(result["accuracy"], 0.70)
        self.assertGreater(result["precision"], 0.60)
        self.assertGreater(result["recall"], 0.60)
        
        logger.info(f"Graph Fraud Detection Test: {result}")
    
    def test_ml_feature_data_consistency(self):
        """Test ML feature consistency across retrievals"""
        result = self.analyzer.test_ml_feature_consistency(num_claims=15)
        
        self.assertNotIn("error", result)
        self.assertGreater(result["feature_consistency_rate"], 0.95)
        self.assertLess(result["average_retrieval_time"], 1.0)  # < 1 second
        
        logger.info(f"ML Feature Consistency Test: {result}")
    
    def test_fraud_network_entity_analysis(self):
        """Test connected entity analysis for fraud networks"""
        result = self.analyzer.test_connected_entity_analysis(num_entities=10)
        
        self.assertNotIn("error", result)
        self.assertGreater(result["analysis_success_rate"], 0.80)
        
        logger.info(f"Connected Entity Analysis Test: {result}")
    
    def test_ml_model_scoring_performance(self):
        """Test ML model scoring performance"""
        result = self.analyzer.test_model_scoring_performance(num_scorings=10)
        
        self.assertNotIn("error", result)
        self.assertGreater(result["scoring_success_rate"], 0.90)
        self.assertTrue(result["performance_acceptable"])
        
        logger.info(f"Model Scoring Performance Test: {result}")


if __name__ == "__main__":
    unittest.main()

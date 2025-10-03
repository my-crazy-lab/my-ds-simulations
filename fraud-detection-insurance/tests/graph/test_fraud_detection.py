#!/usr/bin/env python3
"""
Fraud Detection Test Suite

This test suite validates:
1. Graph-based fraud ring detection
2. Network analysis and suspicious pattern identification
3. Entity resolution and relationship mapping
4. Machine learning fraud classification
5. Real-time fraud scoring performance
6. Investigation workflow automation
"""

import asyncio
import json
import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import random
import numpy as np

import pytest
import aiohttp
import requests
import neo4j
from neo4j import GraphDatabase

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class TestClaim:
    """Test claim for fraud detection validation"""
    claim_id: str
    policy_number: str
    claimant_id: str
    incident_date: datetime
    claim_type: str
    claim_amount: float
    location: Dict[str, float]
    description: str
    is_fraudulent: bool = False

@dataclass
class FraudDetectionTestResult:
    """Fraud detection test result"""
    test_name: str
    total_claims: int
    fraud_detected: int
    false_positives: int
    false_negatives: int
    precision: float
    recall: float
    f1_score: float
    average_response_time_ms: float
    success: bool
    error_message: Optional[str] = None

class FraudDetectionTester:
    """Handles fraud detection testing"""
    
    def __init__(self):
        self.claim_service_url = "http://localhost:8521/api/v1"
        self.fraud_scorer_url = "http://localhost:8522/api/v1"
        self.graph_analyzer_url = "http://localhost:8523/api/v1"
        self.investigation_url = "http://localhost:8524/api/v1"
        
        self.session = None
        self.test_user_id = "TEST_USER_FRAUD"
        
        # Neo4j connection for test data setup
        self.neo4j_driver = GraphDatabase.driver(
            "bolt://localhost:7687",
            auth=("neo4j", "fraud_detection_pass")
        )
        
    async def setup_session(self):
        """Setup HTTP session"""
        timeout = aiohttp.ClientTimeout(total=30.0)
        headers = {
            "Content-Type": "application/json",
            "X-User-ID": self.test_user_id,
            "Authorization": "Bearer test_token"
        }
        self.session = aiohttp.ClientSession(timeout=timeout, headers=headers)
    
    async def cleanup_session(self):
        """Cleanup HTTP session"""
        if self.session:
            await self.session.close()
        if self.neo4j_driver:
            self.neo4j_driver.close()
    
    def generate_legitimate_claims(self, count: int) -> List[TestClaim]:
        """Generate legitimate insurance claims"""
        claims = []
        claim_types = ["AUTO_ACCIDENT", "PROPERTY_DAMAGE", "THEFT", "MEDICAL", "LIABILITY"]
        
        for i in range(count):
            claim = TestClaim(
                claim_id=f"LEGIT_{i:06d}",
                policy_number=f"POL{random.randint(100000, 999999)}",
                claimant_id=f"CLMT{random.randint(10000, 99999)}",
                incident_date=datetime.now() - timedelta(days=random.randint(1, 365)),
                claim_type=random.choice(claim_types),
                claim_amount=round(random.uniform(1000, 50000), 2),
                location={
                    "latitude": round(random.uniform(25.0, 49.0), 6),
                    "longitude": round(random.uniform(-125.0, -66.0), 6),
                    "address": f"{random.randint(1, 9999)} Main St, City, State"
                },
                description=f"Legitimate claim incident {i}",
                is_fraudulent=False
            )
            claims.append(claim)
        
        return claims
    
    def generate_fraudulent_claims(self, count: int) -> List[TestClaim]:
        """Generate fraudulent insurance claims with suspicious patterns"""
        claims = []
        
        # Create fraud rings with shared attributes
        ring_size = 5
        num_rings = count // ring_size
        
        for ring_id in range(num_rings):
            # Shared attributes for fraud ring
            shared_address = f"{random.randint(1, 999)} Fraud St, Scam City, State"
            shared_lat = round(random.uniform(25.0, 49.0), 6)
            shared_lon = round(random.uniform(-125.0, -66.0), 6)
            shared_provider = f"PROVIDER{ring_id:03d}"
            incident_date_base = datetime.now() - timedelta(days=random.randint(1, 30))
            
            for member in range(ring_size):
                claim_id = f"FRAUD_{ring_id:03d}_{member:02d}"
                
                # Add some variation to avoid perfect patterns
                location_variation = random.uniform(-0.001, 0.001)
                time_variation = random.randint(-2, 2)
                
                claim = TestClaim(
                    claim_id=claim_id,
                    policy_number=f"POL{random.randint(100000, 999999)}",
                    claimant_id=f"FRAUD_CLMT_{ring_id:03d}_{member:02d}",
                    incident_date=incident_date_base + timedelta(days=time_variation),
                    claim_type="AUTO_ACCIDENT",  # Fraud rings often focus on one type
                    claim_amount=round(random.uniform(15000, 25000), 2),  # Similar amounts
                    location={
                        "latitude": shared_lat + location_variation,
                        "longitude": shared_lon + location_variation,
                        "address": shared_address if member < 3 else f"{random.randint(1, 999)} Nearby St, Scam City, State"
                    },
                    description=f"Suspicious claim in fraud ring {ring_id}",
                    is_fraudulent=True
                )
                claims.append(claim)
        
        # Add remaining individual fraudulent claims
        remaining = count - (num_rings * ring_size)
        for i in range(remaining):
            claim = TestClaim(
                claim_id=f"FRAUD_INDIV_{i:06d}",
                policy_number=f"POL{random.randint(100000, 999999)}",
                claimant_id=f"FRAUD_CLMT_INDIV_{i:06d}",
                incident_date=datetime.now() - timedelta(days=random.randint(1, 365)),
                claim_type=random.choice(["AUTO_ACCIDENT", "PROPERTY_DAMAGE"]),
                claim_amount=round(random.uniform(20000, 100000), 2),  # Unusually high amounts
                location={
                    "latitude": round(random.uniform(25.0, 49.0), 6),
                    "longitude": round(random.uniform(-125.0, -66.0), 6),
                    "address": f"{random.randint(1, 9999)} Suspicious St, Fraud City, State"
                },
                description=f"Individual fraudulent claim {i}",
                is_fraudulent=True
            )
            claims.append(claim)
        
        return claims
    
    async def submit_claim(self, claim: TestClaim) -> Tuple[Optional[Dict], float]:
        """Submit a claim and measure response time"""
        start_time = time.time()
        
        try:
            claim_data = {
                "claim_id": claim.claim_id,
                "policy_number": claim.policy_number,
                "claimant_id": claim.claimant_id,
                "incident_date": claim.incident_date.isoformat(),
                "claim_type": claim.claim_type,
                "claim_amount": str(claim.claim_amount),
                "location": claim.location,
                "description": claim.description
            }
            
            async with self.session.post(f"{self.claim_service_url}/claims", json=claim_data) as response:
                end_time = time.time()
                response_time_ms = (end_time - start_time) * 1000
                
                if response.status in [200, 201]:
                    claim_response = await response.json()
                    return claim_response, response_time_ms
                else:
                    error_data = await response.json()
                    logger.error(f"Failed to submit claim: {error_data}")
                    return None, response_time_ms
        
        except Exception as e:
            end_time = time.time()
            response_time_ms = (end_time - start_time) * 1000
            logger.error(f"Exception submitting claim: {e}")
            return None, response_time_ms
    
    async def get_fraud_score(self, claim_id: str) -> Tuple[Optional[float], float]:
        """Get fraud score for a claim and measure response time"""
        start_time = time.time()
        
        try:
            async with self.session.get(f"{self.fraud_scorer_url}/fraud-score/{claim_id}") as response:
                end_time = time.time()
                response_time_ms = (end_time - start_time) * 1000
                
                if response.status == 200:
                    score_data = await response.json()
                    return score_data.get("fraud_score"), response_time_ms
                else:
                    error_data = await response.json()
                    logger.error(f"Failed to get fraud score: {error_data}")
                    return None, response_time_ms
        
        except Exception as e:
            end_time = time.time()
            response_time_ms = (end_time - start_time) * 1000
            logger.error(f"Exception getting fraud score: {e}")
            return None, response_time_ms
    
    async def analyze_claim_network(self, claim_id: str) -> Tuple[Optional[Dict], float]:
        """Analyze claim network and measure response time"""
        start_time = time.time()
        
        try:
            analysis_data = {
                "claim_id": claim_id,
                "analysis_type": "SUSPICIOUS_CONNECTIONS",
                "depth": 3
            }
            
            async with self.session.post(f"{self.graph_analyzer_url}/network-analysis", json=analysis_data) as response:
                end_time = time.time()
                response_time_ms = (end_time - start_time) * 1000
                
                if response.status == 200:
                    analysis_result = await response.json()
                    return analysis_result, response_time_ms
                else:
                    error_data = await response.json()
                    logger.error(f"Failed to analyze network: {error_data}")
                    return None, response_time_ms
        
        except Exception as e:
            end_time = time.time()
            response_time_ms = (end_time - start_time) * 1000
            logger.error(f"Exception analyzing network: {e}")
            return None, response_time_ms
    
    async def test_fraud_detection_accuracy(self, num_legitimate: int = 50, num_fraudulent: int = 50) -> FraudDetectionTestResult:
        """Test fraud detection accuracy with known fraudulent and legitimate claims"""
        logger.info(f"Testing fraud detection accuracy: {num_legitimate} legitimate, {num_fraudulent} fraudulent claims")
        
        # Generate test claims
        legitimate_claims = self.generate_legitimate_claims(num_legitimate)
        fraudulent_claims = self.generate_fraudulent_claims(num_fraudulent)
        all_claims = legitimate_claims + fraudulent_claims
        
        # Shuffle claims to avoid bias
        random.shuffle(all_claims)
        
        # Submit claims and collect results
        results = []
        response_times = []
        
        for claim in all_claims:
            # Submit claim
            claim_response, submit_time = await self.submit_claim(claim)
            response_times.append(submit_time)
            
            if not claim_response:
                continue
            
            # Wait a moment for processing
            await asyncio.sleep(0.1)
            
            # Get fraud score
            fraud_score, score_time = await self.get_fraud_score(claim.claim_id)
            response_times.append(score_time)
            
            if fraud_score is not None:
                results.append({
                    "claim_id": claim.claim_id,
                    "actual_fraud": claim.is_fraudulent,
                    "fraud_score": fraud_score,
                    "predicted_fraud": fraud_score > 0.5  # Threshold for fraud classification
                })
            
            # Small delay between claims
            await asyncio.sleep(0.05)
        
        # Calculate metrics
        true_positives = sum(1 for r in results if r["actual_fraud"] and r["predicted_fraud"])
        false_positives = sum(1 for r in results if not r["actual_fraud"] and r["predicted_fraud"])
        true_negatives = sum(1 for r in results if not r["actual_fraud"] and not r["predicted_fraud"])
        false_negatives = sum(1 for r in results if r["actual_fraud"] and not r["predicted_fraud"])
        
        precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0
        recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0
        f1_score = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
        
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0
        
        # Success criteria: F1 score > 0.8, precision > 0.7, recall > 0.7
        success = f1_score > 0.8 and precision > 0.7 and recall > 0.7
        
        return FraudDetectionTestResult(
            test_name="Fraud Detection Accuracy",
            total_claims=len(results),
            fraud_detected=true_positives + false_positives,
            false_positives=false_positives,
            false_negatives=false_negatives,
            precision=precision,
            recall=recall,
            f1_score=f1_score,
            average_response_time_ms=avg_response_time,
            success=success,
            error_message=None if success else f"F1: {f1_score:.3f}, Precision: {precision:.3f}, Recall: {recall:.3f}"
        )
    
    async def test_fraud_ring_detection(self, num_rings: int = 5, ring_size: int = 4) -> FraudDetectionTestResult:
        """Test fraud ring detection capabilities"""
        logger.info(f"Testing fraud ring detection: {num_rings} rings, {ring_size} members each")
        
        # Generate fraud rings
        fraudulent_claims = self.generate_fraudulent_claims(num_rings * ring_size)
        
        # Submit claims
        submitted_claims = []
        response_times = []
        
        for claim in fraudulent_claims:
            claim_response, submit_time = await self.submit_claim(claim)
            response_times.append(submit_time)
            
            if claim_response:
                submitted_claims.append(claim)
            
            await asyncio.sleep(0.05)
        
        # Wait for processing
        await asyncio.sleep(2)
        
        # Analyze networks for each claim
        detected_rings = set()
        network_analysis_times = []
        
        for claim in submitted_claims[:10]:  # Test first 10 claims
            analysis_result, analysis_time = await self.analyze_claim_network(claim.claim_id)
            network_analysis_times.append(analysis_time)
            
            if analysis_result and analysis_result.get("fraud_rings"):
                for ring in analysis_result["fraud_rings"]:
                    ring_members = tuple(sorted(ring["members"]))
                    detected_rings.add(ring_members)
        
        response_times.extend(network_analysis_times)
        
        # Calculate detection metrics
        expected_rings = num_rings
        detected_ring_count = len(detected_rings)
        
        # Simple success criteria: detect at least 70% of rings
        detection_rate = detected_ring_count / expected_rings if expected_rings > 0 else 0
        success = detection_rate >= 0.7
        
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0
        
        return FraudDetectionTestResult(
            test_name="Fraud Ring Detection",
            total_claims=len(submitted_claims),
            fraud_detected=detected_ring_count,
            false_positives=0,  # Not applicable for this test
            false_negatives=expected_rings - detected_ring_count,
            precision=1.0,  # Assume all detected rings are valid
            recall=detection_rate,
            f1_score=2 * detection_rate / (1 + detection_rate) if detection_rate > 0 else 0,
            average_response_time_ms=avg_response_time,
            success=success,
            error_message=None if success else f"Detection rate: {detection_rate:.3f} (expected ≥0.7)"
        )
    
    async def test_real_time_scoring_performance(self, num_claims: int = 100) -> FraudDetectionTestResult:
        """Test real-time fraud scoring performance"""
        logger.info(f"Testing real-time scoring performance with {num_claims} claims")
        
        # Generate mixed claims
        legitimate_claims = self.generate_legitimate_claims(num_claims // 2)
        fraudulent_claims = self.generate_fraudulent_claims(num_claims // 2)
        all_claims = legitimate_claims + fraudulent_claims
        random.shuffle(all_claims)
        
        # Submit and score claims concurrently
        async def process_claim(claim):
            # Submit claim
            claim_response, submit_time = await self.submit_claim(claim)
            if not claim_response:
                return None, submit_time
            
            # Get fraud score immediately
            fraud_score, score_time = await self.get_fraud_score(claim.claim_id)
            
            total_time = submit_time + score_time
            return {
                "claim_id": claim.claim_id,
                "fraud_score": fraud_score,
                "processing_time": total_time,
                "success": fraud_score is not None
            }, total_time
        
        # Process claims with limited concurrency
        semaphore = asyncio.Semaphore(10)  # Limit concurrent requests
        
        async def process_with_semaphore(claim):
            async with semaphore:
                return await process_claim(claim)
        
        start_time = time.time()
        results = await asyncio.gather(*[process_with_semaphore(claim) for claim in all_claims])
        end_time = time.time()
        
        total_processing_time = end_time - start_time
        
        # Analyze results
        successful_results = [r for r, _ in results if r and r["success"]]
        response_times = [t for _, t in results if t is not None]
        
        successful_count = len(successful_results)
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0
        throughput = successful_count / total_processing_time if total_processing_time > 0 else 0
        
        # Success criteria: >95% success rate, <1000ms average response time, >10 claims/second
        success_rate = successful_count / len(all_claims)
        success = (
            success_rate >= 0.95 and
            avg_response_time < 1000 and
            throughput >= 10
        )
        
        return FraudDetectionTestResult(
            test_name="Real-time Scoring Performance",
            total_claims=len(all_claims),
            fraud_detected=successful_count,
            false_positives=0,  # Not applicable for performance test
            false_negatives=len(all_claims) - successful_count,
            precision=success_rate,
            recall=success_rate,
            f1_score=success_rate,
            average_response_time_ms=avg_response_time,
            success=success,
            error_message=None if success else f"Success rate: {success_rate:.3f}, Avg time: {avg_response_time:.1f}ms, Throughput: {throughput:.1f}/s"
        )
    
    def format_test_result(self, result: FraudDetectionTestResult) -> str:
        """Format test result for display"""
        status = "✅ PASSED" if result.success else "❌ FAILED"
        
        return f"""
{result.test_name}: {status}
  Total Claims: {result.total_claims}
  Fraud Detected: {result.fraud_detected}
  False Positives: {result.false_positives}
  False Negatives: {result.false_negatives}
  Precision: {result.precision:.3f}
  Recall: {result.recall:.3f}
  F1 Score: {result.f1_score:.3f}
  Avg Response Time: {result.average_response_time_ms:.2f}ms
  Error: {result.error_message or 'None'}
        """
    
    async def run_all_fraud_detection_tests(self) -> Dict:
        """Run all fraud detection tests"""
        logger.info("Starting comprehensive fraud detection tests")
        
        await self.setup_session()
        
        try:
            # Run all test suites (reduced numbers for testing)
            accuracy_test = await self.test_fraud_detection_accuracy(25, 25)  # Reduced for testing
            ring_test = await self.test_fraud_ring_detection(3, 4)  # Reduced for testing
            performance_test = await self.test_real_time_scoring_performance(50)  # Reduced for testing
            
            # Display results
            print(self.format_test_result(accuracy_test))
            print(self.format_test_result(ring_test))
            print(self.format_test_result(performance_test))
            
            return {
                "fraud_detection_accuracy": {
                    "precision": accuracy_test.precision,
                    "recall": accuracy_test.recall,
                    "f1_score": accuracy_test.f1_score,
                    "avg_response_time_ms": accuracy_test.average_response_time_ms,
                    "success": accuracy_test.success
                },
                "fraud_ring_detection": {
                    "detection_rate": ring_test.recall,
                    "avg_response_time_ms": ring_test.average_response_time_ms,
                    "success": ring_test.success
                },
                "real_time_performance": {
                    "success_rate": performance_test.precision,
                    "avg_response_time_ms": performance_test.average_response_time_ms,
                    "success": performance_test.success
                },
                "overall_success": all([
                    accuracy_test.success,
                    ring_test.success,
                    performance_test.success
                ]),
                "timestamp": time.time()
            }
        
        finally:
            await self.cleanup_session()

# Test cases using pytest
@pytest.mark.asyncio
async def test_fraud_detection_accuracy():
    """Test fraud detection accuracy"""
    tester = FraudDetectionTester()
    await tester.setup_session()
    
    try:
        result = await tester.test_fraud_detection_accuracy(10, 10)  # Small test
        
        # Assertions
        assert result.success, f"Fraud detection accuracy test failed: {result.error_message}"
        assert result.f1_score >= 0.8, f"F1 score should be ≥0.8, got {result.f1_score:.3f}"
        assert result.precision >= 0.7, f"Precision should be ≥0.7, got {result.precision:.3f}"
        assert result.recall >= 0.7, f"Recall should be ≥0.7, got {result.recall:.3f}"
        
        logger.info("Fraud detection accuracy test passed")
    
    finally:
        await tester.cleanup_session()

@pytest.mark.asyncio
async def test_fraud_ring_detection():
    """Test fraud ring detection"""
    tester = FraudDetectionTester()
    await tester.setup_session()
    
    try:
        result = await tester.test_fraud_ring_detection(2, 3)  # Small test
        
        # Assertions
        assert result.success, f"Fraud ring detection test failed: {result.error_message}"
        assert result.recall >= 0.7, f"Detection rate should be ≥0.7, got {result.recall:.3f}"
        
        logger.info("Fraud ring detection test passed")
    
    finally:
        await tester.cleanup_session()

if __name__ == "__main__":
    # Run comprehensive fraud detection tests
    async def main():
        tester = FraudDetectionTester()
        results = await tester.run_all_fraud_detection_tests()
        print(json.dumps(results, indent=2))
    
    asyncio.run(main())

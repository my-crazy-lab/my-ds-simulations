#!/usr/bin/env python3
"""
Fraud Detection Test Suite for Payments Acquiring Gateway

This test suite validates:
1. Real-time fraud scoring
2. Velocity checks and rate limiting
3. Geolocation-based fraud detection
4. ML model accuracy and performance
5. False positive/negative rates
"""

import asyncio
import json
import logging
import random
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import aiohttp
import pytest
import requests
from decimal import Decimal

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class PaymentRequest:
    """Payment request for fraud testing"""
    amount: str
    currency: str = "USD"
    card_number: str = "4111111111111111"
    expiry_month: str = "12"
    expiry_year: str = "2025"
    billing_address: Dict = None
    merchant_id: str = "MERCHANT_001"
    description: str = "Fraud test payment"

@dataclass
class FraudTestResult:
    """Result of a fraud detection test"""
    payment_id: str
    fraud_score: float
    fraud_status: str
    processing_time_ms: int
    expected_result: str
    actual_result: str
    success: bool
    error: Optional[str] = None

class FraudDetectionTester:
    """Handles fraud detection testing"""
    
    def __init__(self):
        self.base_url = "https://localhost:8446/api/v1"
        self.api_key = "pk_test_123456789abcdef123456789abcdef12"
        self.session = None
        self.test_results: List[FraudTestResult] = []
        
    async def setup_session(self):
        """Setup HTTP session with SSL verification disabled for testing"""
        connector = aiohttp.TCPConnector(ssl=False)
        timeout = aiohttp.ClientTimeout(total=30)
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
        )
    
    async def cleanup_session(self):
        """Cleanup HTTP session"""
        if self.session:
            await self.session.close()
    
    async def tokenize_card(self, card_number: str, expiry_month: str, expiry_year: str) -> str:
        """Tokenize a card and return the token"""
        token_request = {
            "card_number": card_number,
            "expiry_month": expiry_month,
            "expiry_year": expiry_year
        }
        
        async with self.session.post(f"{self.base_url}/tokens", json=token_request) as response:
            if response.status == 201:
                data = await response.json()
                return data["data"]["token"]
            else:
                raise Exception(f"Failed to tokenize card: {response.status}")
    
    async def process_payment(self, payment_request: PaymentRequest) -> FraudTestResult:
        """Process a payment and return fraud detection results"""
        start_time = time.time()
        
        try:
            # Tokenize card first
            card_token = await self.tokenize_card(
                payment_request.card_number,
                payment_request.expiry_month,
                payment_request.expiry_year
            )
            
            # Prepare payment request
            payment_data = {
                "amount": payment_request.amount,
                "currency": payment_request.currency,
                "description": payment_request.description,
                "card_token": card_token,
                "billing_address": payment_request.billing_address or {
                    "street": "123 Main St",
                    "city": "New York",
                    "state": "NY",
                    "zip": "10001",
                    "country": "US"
                }
            }
            
            # Process payment
            async with self.session.post(f"{self.base_url}/payments", json=payment_data) as response:
                processing_time = int((time.time() - start_time) * 1000)
                response_data = await response.json()
                
                if response.status in [200, 201]:
                    data = response_data["data"]
                    return FraudTestResult(
                        payment_id=data.get("payment_id", ""),
                        fraud_score=float(data.get("fraud_score", 0.0)),
                        fraud_status=data.get("fraud_status", "CLEAN"),
                        processing_time_ms=processing_time,
                        expected_result="SUCCESS",
                        actual_result=data.get("status", "UNKNOWN"),
                        success=True
                    )
                else:
                    return FraudTestResult(
                        payment_id="",
                        fraud_score=0.0,
                        fraud_status="UNKNOWN",
                        processing_time_ms=processing_time,
                        expected_result="SUCCESS",
                        actual_result="FAILED",
                        success=False,
                        error=f"HTTP {response.status}: {response_data.get('error', 'Unknown error')}"
                    )
        
        except Exception as e:
            processing_time = int((time.time() - start_time) * 1000)
            return FraudTestResult(
                payment_id="",
                fraud_score=0.0,
                fraud_status="UNKNOWN",
                processing_time_ms=processing_time,
                expected_result="SUCCESS",
                actual_result="ERROR",
                success=False,
                error=str(e)
            )
    
    async def test_velocity_fraud(self) -> List[FraudTestResult]:
        """Test velocity-based fraud detection"""
        logger.info("Testing velocity-based fraud detection")
        
        results = []
        card_number = "4111111111111111"
        
        # Send multiple payments rapidly from same card
        for i in range(10):
            payment_request = PaymentRequest(
                amount=f"{random.randint(100, 1000)}00",  # $100-$1000
                card_number=card_number,
                description=f"Velocity test payment {i+1}"
            )
            
            result = await self.process_payment(payment_request)
            results.append(result)
            
            logger.info(f"Payment {i+1}: Fraud Score = {result.fraud_score}, Status = {result.fraud_status}")
            
            # Small delay between payments
            await asyncio.sleep(0.1)
        
        return results
    
    async def test_geolocation_fraud(self) -> List[FraudTestResult]:
        """Test geolocation-based fraud detection"""
        logger.info("Testing geolocation-based fraud detection")
        
        results = []
        
        # Test payments from different suspicious locations
        suspicious_locations = [
            {
                "street": "123 Fraud Street",
                "city": "Scam City",
                "state": "XX",
                "zip": "00000",
                "country": "US"
            },
            {
                "street": "456 Suspicious Ave",
                "city": "Unknown City",
                "state": "YY",
                "zip": "99999",
                "country": "US"
            },
            {
                "street": "789 Risk Road",
                "city": "Danger Zone",
                "state": "ZZ",
                "zip": "11111",
                "country": "US"
            }
        ]
        
        for i, address in enumerate(suspicious_locations):
            payment_request = PaymentRequest(
                amount="50000",  # $500 - moderate amount
                billing_address=address,
                description=f"Geolocation test payment {i+1}"
            )
            
            result = await self.process_payment(payment_request)
            results.append(result)
            
            logger.info(f"Geo test {i+1}: Fraud Score = {result.fraud_score}, Status = {result.fraud_status}")
        
        return results
    
    async def test_amount_based_fraud(self) -> List[FraudTestResult]:
        """Test amount-based fraud detection"""
        logger.info("Testing amount-based fraud detection")
        
        results = []
        
        # Test various amounts to trigger different risk levels
        test_amounts = [
            ("1000", "LOW"),      # $10 - low risk
            ("10000", "MEDIUM"),  # $100 - medium risk
            ("100000", "HIGH"),   # $1000 - high risk
            ("500000", "HIGH"),   # $5000 - very high risk
            ("1000000", "HIGH"),  # $10000 - extremely high risk
        ]
        
        for amount, expected_risk in test_amounts:
            payment_request = PaymentRequest(
                amount=amount,
                description=f"Amount test payment ${int(amount)/100}"
            )
            
            result = await self.process_payment(payment_request)
            result.expected_result = expected_risk
            results.append(result)
            
            logger.info(f"Amount ${int(amount)/100}: Fraud Score = {result.fraud_score}, Status = {result.fraud_status}")
        
        return results
    
    async def test_pattern_based_fraud(self) -> List[FraudTestResult]:
        """Test pattern-based fraud detection"""
        logger.info("Testing pattern-based fraud detection")
        
        results = []
        
        # Test suspicious patterns
        patterns = [
            # Round amounts (often fraudulent)
            {"amount": "100000", "description": "Round amount test"},
            {"amount": "200000", "description": "Round amount test"},
            {"amount": "500000", "description": "Round amount test"},
            
            # Sequential amounts
            {"amount": "123400", "description": "Sequential test 1"},
            {"amount": "123500", "description": "Sequential test 2"},
            {"amount": "123600", "description": "Sequential test 3"},
            
            # Repeated amounts
            {"amount": "77700", "description": "Repeated digits test"},
            {"amount": "88800", "description": "Repeated digits test"},
            {"amount": "99900", "description": "Repeated digits test"},
        ]
        
        for pattern in patterns:
            payment_request = PaymentRequest(
                amount=pattern["amount"],
                description=pattern["description"]
            )
            
            result = await self.process_payment(payment_request)
            results.append(result)
            
            logger.info(f"Pattern test: Fraud Score = {result.fraud_score}, Status = {result.fraud_status}")
        
        return results
    
    async def test_concurrent_fraud_detection(self) -> List[FraudTestResult]:
        """Test fraud detection under concurrent load"""
        logger.info("Testing concurrent fraud detection")
        
        # Create multiple payment requests
        payment_requests = []
        for i in range(20):
            payment_requests.append(PaymentRequest(
                amount=f"{random.randint(100, 10000)}00",
                card_number=f"411111111111{1111 + i % 10}",  # Different cards
                description=f"Concurrent fraud test {i+1}"
            ))
        
        # Process payments concurrently
        tasks = [self.process_payment(req) for req in payment_requests]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out exceptions and convert to results
        valid_results = []
        for result in results:
            if isinstance(result, FraudTestResult):
                valid_results.append(result)
            else:
                logger.error(f"Concurrent test error: {result}")
        
        logger.info(f"Concurrent test completed: {len(valid_results)}/{len(payment_requests)} successful")
        return valid_results
    
    def analyze_results(self, results: List[FraudTestResult], test_name: str) -> Dict:
        """Analyze fraud detection test results"""
        total_tests = len(results)
        successful_tests = sum(1 for r in results if r.success)
        
        if successful_tests == 0:
            return {
                "test_name": test_name,
                "total_tests": total_tests,
                "successful_tests": 0,
                "success_rate": 0.0,
                "error": "No successful tests"
            }
        
        # Calculate fraud score statistics
        fraud_scores = [r.fraud_score for r in results if r.success]
        avg_fraud_score = sum(fraud_scores) / len(fraud_scores) if fraud_scores else 0
        max_fraud_score = max(fraud_scores) if fraud_scores else 0
        min_fraud_score = min(fraud_scores) if fraud_scores else 0
        
        # Calculate processing time statistics
        processing_times = [r.processing_time_ms for r in results if r.success]
        avg_processing_time = sum(processing_times) / len(processing_times) if processing_times else 0
        max_processing_time = max(processing_times) if processing_times else 0
        
        # Count fraud statuses
        fraud_statuses = {}
        for result in results:
            if result.success:
                status = result.fraud_status
                fraud_statuses[status] = fraud_statuses.get(status, 0) + 1
        
        analysis = {
            "test_name": test_name,
            "total_tests": total_tests,
            "successful_tests": successful_tests,
            "success_rate": (successful_tests / total_tests) * 100,
            "fraud_score_stats": {
                "average": round(avg_fraud_score, 3),
                "minimum": round(min_fraud_score, 3),
                "maximum": round(max_fraud_score, 3)
            },
            "processing_time_stats": {
                "average_ms": round(avg_processing_time, 2),
                "maximum_ms": max_processing_time
            },
            "fraud_status_distribution": fraud_statuses,
            "errors": [r.error for r in results if r.error]
        }
        
        logger.info(f"{test_name} Analysis: {json.dumps(analysis, indent=2)}")
        return analysis
    
    async def run_all_fraud_tests(self) -> Dict:
        """Run all fraud detection tests"""
        logger.info("Starting comprehensive fraud detection tests")
        
        await self.setup_session()
        
        try:
            # Run all test suites
            velocity_results = await self.test_velocity_fraud()
            geo_results = await self.test_geolocation_fraud()
            amount_results = await self.test_amount_based_fraud()
            pattern_results = await self.test_pattern_based_fraud()
            concurrent_results = await self.test_concurrent_fraud_detection()
            
            # Analyze results
            analyses = {
                "velocity_fraud": self.analyze_results(velocity_results, "Velocity Fraud Detection"),
                "geolocation_fraud": self.analyze_results(geo_results, "Geolocation Fraud Detection"),
                "amount_fraud": self.analyze_results(amount_results, "Amount-based Fraud Detection"),
                "pattern_fraud": self.analyze_results(pattern_results, "Pattern-based Fraud Detection"),
                "concurrent_fraud": self.analyze_results(concurrent_results, "Concurrent Fraud Detection")
            }
            
            # Overall summary
            all_results = velocity_results + geo_results + amount_results + pattern_results + concurrent_results
            overall_analysis = self.analyze_results(all_results, "Overall Fraud Detection")
            
            return {
                "overall": overall_analysis,
                "detailed": analyses,
                "timestamp": time.time()
            }
        
        finally:
            await self.cleanup_session()

# Test cases using pytest
@pytest.mark.asyncio
async def test_velocity_fraud_detection():
    """Test velocity-based fraud detection"""
    tester = FraudDetectionTester()
    await tester.setup_session()
    
    try:
        results = await tester.test_velocity_fraud()
        
        # Assertions
        assert len(results) == 10, "Should process 10 velocity test payments"
        
        # Later payments should have higher fraud scores
        fraud_scores = [r.fraud_score for r in results if r.success]
        if len(fraud_scores) >= 5:
            early_avg = sum(fraud_scores[:3]) / 3
            later_avg = sum(fraud_scores[-3:]) / 3
            assert later_avg > early_avg, "Later payments should have higher fraud scores"
        
        logger.info("Velocity fraud detection test passed")
    
    finally:
        await tester.cleanup_session()

@pytest.mark.asyncio
async def test_high_amount_fraud_detection():
    """Test high amount fraud detection"""
    tester = FraudDetectionTester()
    await tester.setup_session()
    
    try:
        # Test very high amount
        payment_request = PaymentRequest(amount="1000000")  # $10,000
        result = await tester.process_payment(payment_request)
        
        # Assertions
        assert result.success, f"Payment should be processed: {result.error}"
        assert result.fraud_score > 0.5, f"High amount should trigger fraud detection: {result.fraud_score}"
        
        logger.info("High amount fraud detection test passed")
    
    finally:
        await tester.cleanup_session()

@pytest.mark.asyncio
async def test_fraud_detection_performance():
    """Test fraud detection performance under load"""
    tester = FraudDetectionTester()
    await tester.setup_session()
    
    try:
        results = await tester.test_concurrent_fraud_detection()
        
        # Assertions
        assert len(results) >= 15, "Should process at least 15 concurrent payments"
        
        # Check processing times
        processing_times = [r.processing_time_ms for r in results if r.success]
        if processing_times:
            avg_time = sum(processing_times) / len(processing_times)
            assert avg_time < 5000, f"Average processing time should be under 5s: {avg_time}ms"
        
        logger.info("Fraud detection performance test passed")
    
    finally:
        await tester.cleanup_session()

if __name__ == "__main__":
    # Run comprehensive fraud tests
    async def main():
        tester = FraudDetectionTester()
        results = await tester.run_all_fraud_tests()
        print(json.dumps(results, indent=2))
    
    asyncio.run(main())

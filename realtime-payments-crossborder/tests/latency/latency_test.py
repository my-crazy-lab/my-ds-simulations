#!/usr/bin/env python3
"""
Real-time Payments Latency Test Suite

This test suite validates:
1. Sub-second payment processing (<500ms p95)
2. Cross-border payment latency (<2s p95)
3. Concurrent processing performance
4. Network latency impact
5. End-to-end processing times
"""

import asyncio
import json
import logging
import statistics
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
    """Payment request for latency testing"""
    message_id: str
    payment_type: str
    amount: str
    currency: str = "USD"
    debtor_name: str = "Test Debtor"
    debtor_account: str = "123456789"
    debtor_agent: str = "TESTBANK001"
    creditor_name: str = "Test Creditor"
    creditor_account: str = "987654321"
    creditor_agent: str = "TESTBANK002"
    execution_time: str = "IMMEDIATE"

@dataclass
class CrossBorderPaymentRequest:
    """Cross-border payment request"""
    message_id: str
    payment_type: str = "CROSSBORDER"
    amount: str = "1000.00"
    source_currency: str = "USD"
    target_currency: str = "EUR"
    fx_rate: str = "0.85"
    debtor_name: str = "US Company Inc"
    debtor_account: str = "US123456789"
    debtor_agent: str = "USBANKXXX"
    creditor_name: str = "EU Company GmbH"
    creditor_account: str = "DE89370400440532013000"
    creditor_agent: str = "DEUTDEFFXXX"
    correspondent_route: str = "SWIFT_GPI"

@dataclass
class LatencyResult:
    """Result of a latency test"""
    payment_id: str
    message_id: str
    total_latency_ms: float
    processing_latency_ms: float
    network_latency_ms: float
    validation_latency_ms: float
    settlement_latency_ms: float
    status: str
    success: bool
    error: Optional[str] = None

class LatencyTester:
    """Handles latency testing for real-time payments"""
    
    def __init__(self):
        self.base_url = "http://localhost:8451/api/v1"
        self.session = None
        self.test_results: List[LatencyResult] = []
        
    async def setup_session(self):
        """Setup HTTP session"""
        timeout = aiohttp.ClientTimeout(total=30)
        self.session = aiohttp.ClientSession(
            timeout=timeout,
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer test_token_123"
            }
        )
    
    async def cleanup_session(self):
        """Cleanup HTTP session"""
        if self.session:
            await self.session.close()
    
    async def process_payment(self, payment_request: PaymentRequest) -> LatencyResult:
        """Process a payment and measure latency"""
        start_time = time.time()
        
        try:
            # Prepare payment data
            payment_data = {
                "message_id": payment_request.message_id,
                "payment_type": payment_request.payment_type,
                "amount": payment_request.amount,
                "currency": payment_request.currency,
                "debtor": {
                    "name": payment_request.debtor_name,
                    "account": payment_request.debtor_account,
                    "bank_code": payment_request.debtor_agent
                },
                "creditor": {
                    "name": payment_request.creditor_name,
                    "account": payment_request.creditor_account,
                    "bank_code": payment_request.creditor_agent
                },
                "execution_time": payment_request.execution_time
            }
            
            # Send payment request
            async with self.session.post(f"{self.base_url}/payments", json=payment_data) as response:
                total_latency = (time.time() - start_time) * 1000
                response_data = await response.json()
                
                if response.status in [200, 201]:
                    data = response_data.get("data", {})
                    return LatencyResult(
                        payment_id=data.get("payment_id", ""),
                        message_id=payment_request.message_id,
                        total_latency_ms=total_latency,
                        processing_latency_ms=data.get("processing_time_ms", 0),
                        network_latency_ms=data.get("network_latency_ms", 0),
                        validation_latency_ms=data.get("validation_time_ms", 0),
                        settlement_latency_ms=data.get("settlement_time_ms", 0),
                        status=data.get("status", "UNKNOWN"),
                        success=True
                    )
                else:
                    return LatencyResult(
                        payment_id="",
                        message_id=payment_request.message_id,
                        total_latency_ms=total_latency,
                        processing_latency_ms=0,
                        network_latency_ms=0,
                        validation_latency_ms=0,
                        settlement_latency_ms=0,
                        status="FAILED",
                        success=False,
                        error=f"HTTP {response.status}: {response_data.get('error', 'Unknown error')}"
                    )
        
        except Exception as e:
            total_latency = (time.time() - start_time) * 1000
            return LatencyResult(
                payment_id="",
                message_id=payment_request.message_id,
                total_latency_ms=total_latency,
                processing_latency_ms=0,
                network_latency_ms=0,
                validation_latency_ms=0,
                settlement_latency_ms=0,
                status="ERROR",
                success=False,
                error=str(e)
            )
    
    async def process_crossborder_payment(self, payment_request: CrossBorderPaymentRequest) -> LatencyResult:
        """Process a cross-border payment and measure latency"""
        start_time = time.time()
        
        try:
            # Prepare cross-border payment data
            payment_data = {
                "message_id": payment_request.message_id,
                "payment_type": payment_request.payment_type,
                "amount": payment_request.amount,
                "source_currency": payment_request.source_currency,
                "target_currency": payment_request.target_currency,
                "fx_rate": payment_request.fx_rate,
                "debtor": {
                    "name": payment_request.debtor_name,
                    "account": payment_request.debtor_account,
                    "bank_code": payment_request.debtor_agent
                },
                "creditor": {
                    "name": payment_request.creditor_name,
                    "account": payment_request.creditor_account,
                    "bank_code": payment_request.creditor_agent
                },
                "correspondent_route": payment_request.correspondent_route
            }
            
            # Send cross-border payment request
            async with self.session.post(f"{self.base_url}/payments/crossborder", json=payment_data) as response:
                total_latency = (time.time() - start_time) * 1000
                response_data = await response.json()
                
                if response.status in [200, 201]:
                    data = response_data.get("data", {})
                    return LatencyResult(
                        payment_id=data.get("payment_id", ""),
                        message_id=payment_request.message_id,
                        total_latency_ms=total_latency,
                        processing_latency_ms=data.get("processing_time_ms", 0),
                        network_latency_ms=data.get("network_latency_ms", 0),
                        validation_latency_ms=data.get("validation_time_ms", 0),
                        settlement_latency_ms=data.get("settlement_time_ms", 0),
                        status=data.get("status", "UNKNOWN"),
                        success=True
                    )
                else:
                    return LatencyResult(
                        payment_id="",
                        message_id=payment_request.message_id,
                        total_latency_ms=total_latency,
                        processing_latency_ms=0,
                        network_latency_ms=0,
                        validation_latency_ms=0,
                        settlement_latency_ms=0,
                        status="FAILED",
                        success=False,
                        error=f"HTTP {response.status}: {response_data.get('error', 'Unknown error')}"
                    )
        
        except Exception as e:
            total_latency = (time.time() - start_time) * 1000
            return LatencyResult(
                payment_id="",
                message_id=payment_request.message_id,
                total_latency_ms=total_latency,
                processing_latency_ms=0,
                network_latency_ms=0,
                validation_latency_ms=0,
                settlement_latency_ms=0,
                status="ERROR",
                success=False,
                error=str(e)
            )
    
    async def test_single_payment_latency(self) -> List[LatencyResult]:
        """Test latency for single payments"""
        logger.info("Testing single payment latency")
        
        results = []
        
        # Test multiple single payments
        for i in range(100):
            payment_request = PaymentRequest(
                message_id=f"SINGLE_{i:06d}_{int(time.time() * 1000)}",
                payment_type="INSTANT",
                amount=f"{(i + 1) * 100}.00"
            )
            
            result = await self.process_payment(payment_request)
            results.append(result)
            
            if i % 10 == 0:
                logger.info(f"Processed {i+1}/100 single payments")
        
        return results
    
    async def test_concurrent_payment_latency(self) -> List[LatencyResult]:
        """Test latency under concurrent load"""
        logger.info("Testing concurrent payment latency")
        
        # Create multiple payment requests
        payment_requests = []
        for i in range(50):
            payment_requests.append(PaymentRequest(
                message_id=f"CONCURRENT_{i:06d}_{int(time.time() * 1000)}",
                payment_type="INSTANT",
                amount=f"{(i + 1) * 50}.00"
            ))
        
        # Process payments concurrently
        tasks = [self.process_payment(req) for req in payment_requests]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out exceptions and convert to results
        valid_results = []
        for result in results:
            if isinstance(result, LatencyResult):
                valid_results.append(result)
            else:
                logger.error(f"Concurrent test error: {result}")
        
        logger.info(f"Concurrent test completed: {len(valid_results)}/{len(payment_requests)} successful")
        return valid_results
    
    async def test_crossborder_latency(self) -> List[LatencyResult]:
        """Test cross-border payment latency"""
        logger.info("Testing cross-border payment latency")
        
        results = []
        
        # Test various currency pairs
        currency_pairs = [
            ("USD", "EUR", "0.85"),
            ("USD", "GBP", "0.75"),
            ("EUR", "JPY", "130.50"),
            ("GBP", "CHF", "1.15"),
            ("USD", "CAD", "1.25")
        ]
        
        for i, (source_curr, target_curr, fx_rate) in enumerate(currency_pairs):
            for j in range(10):  # 10 payments per currency pair
                payment_request = CrossBorderPaymentRequest(
                    message_id=f"XB_{source_curr}_{target_curr}_{i}_{j}_{int(time.time() * 1000)}",
                    amount=f"{(j + 1) * 1000}.00",
                    source_currency=source_curr,
                    target_currency=target_curr,
                    fx_rate=fx_rate
                )
                
                result = await self.process_crossborder_payment(payment_request)
                results.append(result)
        
        return results
    
    async def test_high_volume_latency(self) -> List[LatencyResult]:
        """Test latency under high volume"""
        logger.info("Testing high volume payment latency")
        
        # Create high volume of payments
        payment_requests = []
        for i in range(1000):
            payment_requests.append(PaymentRequest(
                message_id=f"VOLUME_{i:06d}_{int(time.time() * 1000)}",
                payment_type="INSTANT",
                amount=f"{(i % 100 + 1) * 10}.00"
            ))
        
        # Process in batches to avoid overwhelming the system
        batch_size = 50
        all_results = []
        
        for i in range(0, len(payment_requests), batch_size):
            batch = payment_requests[i:i + batch_size]
            tasks = [self.process_payment(req) for req in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Filter valid results
            for result in batch_results:
                if isinstance(result, LatencyResult):
                    all_results.append(result)
            
            logger.info(f"Processed batch {i//batch_size + 1}/{len(payment_requests)//batch_size}")
            
            # Small delay between batches
            await asyncio.sleep(0.1)
        
        return all_results
    
    def analyze_latency_results(self, results: List[LatencyResult], test_name: str) -> Dict:
        """Analyze latency test results"""
        successful_results = [r for r in results if r.success]
        
        if not successful_results:
            return {
                "test_name": test_name,
                "total_tests": len(results),
                "successful_tests": 0,
                "success_rate": 0.0,
                "error": "No successful tests"
            }
        
        # Calculate latency statistics
        total_latencies = [r.total_latency_ms for r in successful_results]
        processing_latencies = [r.processing_latency_ms for r in successful_results if r.processing_latency_ms > 0]
        
        analysis = {
            "test_name": test_name,
            "total_tests": len(results),
            "successful_tests": len(successful_results),
            "success_rate": (len(successful_results) / len(results)) * 100,
            "total_latency_stats": {
                "mean_ms": round(statistics.mean(total_latencies), 2),
                "median_ms": round(statistics.median(total_latencies), 2),
                "p95_ms": round(self.percentile(total_latencies, 95), 2),
                "p99_ms": round(self.percentile(total_latencies, 99), 2),
                "min_ms": round(min(total_latencies), 2),
                "max_ms": round(max(total_latencies), 2)
            }
        }
        
        if processing_latencies:
            analysis["processing_latency_stats"] = {
                "mean_ms": round(statistics.mean(processing_latencies), 2),
                "median_ms": round(statistics.median(processing_latencies), 2),
                "p95_ms": round(self.percentile(processing_latencies, 95), 2),
                "p99_ms": round(self.percentile(processing_latencies, 99), 2)
            }
        
        # Check SLA compliance
        p95_latency = analysis["total_latency_stats"]["p95_ms"]
        if "crossborder" in test_name.lower():
            sla_threshold = 2000  # 2 seconds for cross-border
        else:
            sla_threshold = 500   # 500ms for domestic
        
        analysis["sla_compliance"] = {
            "threshold_ms": sla_threshold,
            "p95_latency_ms": p95_latency,
            "compliant": p95_latency <= sla_threshold,
            "compliance_percentage": (sum(1 for lat in total_latencies if lat <= sla_threshold) / len(total_latencies)) * 100
        }
        
        logger.info(f"{test_name} Analysis: {json.dumps(analysis, indent=2)}")
        return analysis
    
    def percentile(self, data: List[float], percentile: int) -> float:
        """Calculate percentile of data"""
        if not data:
            return 0.0
        sorted_data = sorted(data)
        index = (percentile / 100) * (len(sorted_data) - 1)
        if index.is_integer():
            return sorted_data[int(index)]
        else:
            lower = sorted_data[int(index)]
            upper = sorted_data[int(index) + 1]
            return lower + (upper - lower) * (index - int(index))
    
    async def run_all_latency_tests(self) -> Dict:
        """Run all latency tests"""
        logger.info("Starting comprehensive latency tests")
        
        await self.setup_session()
        
        try:
            # Run all test suites
            single_results = await self.test_single_payment_latency()
            concurrent_results = await self.test_concurrent_payment_latency()
            crossborder_results = await self.test_crossborder_latency()
            volume_results = await self.test_high_volume_latency()
            
            # Analyze results
            analyses = {
                "single_payment": self.analyze_latency_results(single_results, "Single Payment Latency"),
                "concurrent_payment": self.analyze_latency_results(concurrent_results, "Concurrent Payment Latency"),
                "crossborder_payment": self.analyze_latency_results(crossborder_results, "Cross-border Payment Latency"),
                "high_volume": self.analyze_latency_results(volume_results, "High Volume Latency")
            }
            
            # Overall summary
            all_results = single_results + concurrent_results + crossborder_results + volume_results
            overall_analysis = self.analyze_latency_results(all_results, "Overall Latency Performance")
            
            return {
                "overall": overall_analysis,
                "detailed": analyses,
                "timestamp": time.time()
            }
        
        finally:
            await self.cleanup_session()

# Test cases using pytest
@pytest.mark.asyncio
async def test_single_payment_latency():
    """Test single payment latency meets SLA"""
    tester = LatencyTester()
    await tester.setup_session()
    
    try:
        results = await tester.test_single_payment_latency()
        
        # Assertions
        assert len(results) == 100, "Should process 100 single payments"
        
        successful_results = [r for r in results if r.success]
        assert len(successful_results) >= 95, "At least 95% should succeed"
        
        # Check latency SLA (500ms p95)
        total_latencies = [r.total_latency_ms for r in successful_results]
        p95_latency = tester.percentile(total_latencies, 95)
        assert p95_latency <= 500, f"P95 latency should be ≤500ms, got {p95_latency}ms"
        
        logger.info("Single payment latency test passed")
    
    finally:
        await tester.cleanup_session()

@pytest.mark.asyncio
async def test_crossborder_payment_latency():
    """Test cross-border payment latency meets SLA"""
    tester = LatencyTester()
    await tester.setup_session()
    
    try:
        results = await tester.test_crossborder_latency()
        
        # Assertions
        assert len(results) >= 40, "Should process multiple cross-border payments"
        
        successful_results = [r for r in results if r.success]
        assert len(successful_results) >= len(results) * 0.9, "At least 90% should succeed"
        
        # Check latency SLA (2000ms p95)
        total_latencies = [r.total_latency_ms for r in successful_results]
        p95_latency = tester.percentile(total_latencies, 95)
        assert p95_latency <= 2000, f"P95 latency should be ≤2000ms, got {p95_latency}ms"
        
        logger.info("Cross-border payment latency test passed")
    
    finally:
        await tester.cleanup_session()

@pytest.mark.asyncio
async def test_concurrent_processing_performance():
    """Test concurrent processing doesn't degrade latency significantly"""
    tester = LatencyTester()
    await tester.setup_session()
    
    try:
        results = await tester.test_concurrent_payment_latency()
        
        # Assertions
        assert len(results) >= 40, "Should process at least 40 concurrent payments"
        
        successful_results = [r for r in results if r.success]
        assert len(successful_results) >= len(results) * 0.8, "At least 80% should succeed under load"
        
        # Check that concurrent processing doesn't severely impact latency
        total_latencies = [r.total_latency_ms for r in successful_results]
        p95_latency = tester.percentile(total_latencies, 95)
        assert p95_latency <= 1000, f"P95 latency under load should be ≤1000ms, got {p95_latency}ms"
        
        logger.info("Concurrent processing performance test passed")
    
    finally:
        await tester.cleanup_session()

if __name__ == "__main__":
    # Run comprehensive latency tests
    async def main():
        tester = LatencyTester()
        results = await tester.run_all_latency_tests()
        print(json.dumps(results, indent=2))
    
    asyncio.run(main())

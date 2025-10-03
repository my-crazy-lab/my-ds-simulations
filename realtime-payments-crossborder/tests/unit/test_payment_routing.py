#!/usr/bin/env python3
"""
Real-time Payments Cross-border Unit Tests

This test suite validates:
1. Real-time payment processing
2. Cross-border routing and settlement
3. ISO 20022 message compliance
4. Currency conversion accuracy
5. Correspondent banking integration
6. Sub-second latency requirements
"""

import asyncio
import json
import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import random
import pytest
import requests
from decimal import Decimal

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class TestCrossBorderPayment:
    """Test cross-border payment for validation"""
    payment_id: str
    sender_bank: str
    receiver_bank: str
    sender_account: str
    receiver_account: str
    amount: Decimal
    source_currency: str
    target_currency: str
    sender_country: str
    receiver_country: str
    purpose_code: str

class RealTimePaymentsTester:
    """Handles real-time payments testing"""
    
    def __init__(self):
        self.payment_router_url = "http://localhost:8504/api/v1"
        self.fx_engine_url = "http://localhost:8505/api/v1"
        self.settlement_engine_url = "http://localhost:8506/api/v1"
        self.max_latency_ms = 2000  # 2 second max for cross-border
        self.domestic_max_latency_ms = 500  # 500ms max for domestic
        
    def setup_test_payments(self) -> List[TestCrossBorderPayment]:
        """Setup test cross-border payments"""
        payments = [
            # US to EU payment
            TestCrossBorderPayment(
                payment_id=f"RTPAY_{uuid.uuid4().hex[:8]}",
                sender_bank="US_BANK_001",
                receiver_bank="EU_BANK_001",
                sender_account="US_ACC_001",
                receiver_account="EU_ACC_001",
                amount=Decimal("1000.00"),
                source_currency="USD",
                target_currency="EUR",
                sender_country="US",
                receiver_country="DE",
                purpose_code="TRADE"
            ),
            # UK to Japan payment
            TestCrossBorderPayment(
                payment_id=f"RTPAY_{uuid.uuid4().hex[:8]}",
                sender_bank="UK_BANK_001",
                receiver_bank="JP_BANK_001",
                sender_account="UK_ACC_001",
                receiver_account="JP_ACC_001",
                amount=Decimal("5000.00"),
                source_currency="GBP",
                target_currency="JPY",
                sender_country="GB",
                receiver_country="JP",
                purpose_code="REMITTANCE"
            ),
            # Domestic US payment
            TestCrossBorderPayment(
                payment_id=f"RTPAY_{uuid.uuid4().hex[:8]}",
                sender_bank="US_BANK_001",
                receiver_bank="US_BANK_002",
                sender_account="US_ACC_002",
                receiver_account="US_ACC_003",
                amount=Decimal("250.00"),
                source_currency="USD",
                target_currency="USD",
                sender_country="US",
                receiver_country="US",
                purpose_code="P2P"
            )
        ]
        return payments
    
    def get_fx_rate(self, from_currency: str, to_currency: str) -> Optional[Decimal]:
        """Get foreign exchange rate"""
        try:
            response = requests.get(
                f"{self.fx_engine_url}/rates/{from_currency}/{to_currency}",
                timeout=5
            )
            
            if response.status_code == 200:
                rate_data = response.json()
                return Decimal(str(rate_data.get("rate", "1.0")))
            
            return None
        
        except Exception as e:
            logger.error(f"Failed to get FX rate {from_currency}/{to_currency}: {e}")
            return None
    
    def process_realtime_payment(self, payment: TestCrossBorderPayment) -> tuple:
        """Process a real-time payment and measure latency"""
        start_time = time.time()
        
        try:
            payment_data = {
                "payment_id": payment.payment_id,
                "sender_bank": payment.sender_bank,
                "receiver_bank": payment.receiver_bank,
                "sender_account": payment.sender_account,
                "receiver_account": payment.receiver_account,
                "amount": str(payment.amount),
                "source_currency": payment.source_currency,
                "target_currency": payment.target_currency,
                "sender_country": payment.sender_country,
                "receiver_country": payment.receiver_country,
                "purpose_code": payment.purpose_code,
                "priority": "HIGH"
            }
            
            response = requests.post(
                f"{self.payment_router_url}/payments/realtime",
                json=payment_data,
                timeout=30
            )
            
            end_time = time.time()
            latency_ms = (end_time - start_time) * 1000
            
            if response.status_code in [200, 201]:
                payment_response = response.json()
                return True, latency_ms, payment_response
            else:
                error_response = response.json() if response.content else {"error": "Unknown error"}
                return False, latency_ms, error_response
        
        except Exception as e:
            end_time = time.time()
            latency_ms = (end_time - start_time) * 1000
            logger.error(f"Real-time payment processing exception: {e}")
            return False, latency_ms, {"error": str(e)}
    
    def test_domestic_payment_latency(self) -> bool:
        """Test domestic payment latency requirements"""
        logger.info("Testing domestic payment latency")
        
        test_payments = self.setup_test_payments()
        domestic_payment = test_payments[2]  # Use domestic payment
        
        # Process payment and measure latency
        success, latency_ms, response = self.process_realtime_payment(domestic_payment)
        
        if not success:
            logger.error(f"Domestic payment failed: {response}")
            return False
        
        # Verify latency requirement
        if latency_ms > self.domestic_max_latency_ms:
            logger.error(f"Domestic payment latency too high: {latency_ms:.2f}ms (max: {self.domestic_max_latency_ms}ms)")
            return False
        
        # Verify payment status
        if response.get("status") != "COMPLETED":
            logger.error(f"Domestic payment not completed: {response.get('status')}")
            return False
        
        logger.info(f"✅ Domestic payment latency test passed: {latency_ms:.2f}ms")
        return True
    
    def test_crossborder_payment_processing(self) -> bool:
        """Test cross-border payment processing"""
        logger.info("Testing cross-border payment processing")
        
        test_payments = self.setup_test_payments()
        crossborder_payment = test_payments[0]  # Use US to EU payment
        
        # Get FX rate first
        fx_rate = self.get_fx_rate(crossborder_payment.source_currency, crossborder_payment.target_currency)
        if fx_rate is None:
            logger.error("Failed to get FX rate for cross-border payment")
            return False
        
        # Process payment
        success, latency_ms, response = self.process_realtime_payment(crossborder_payment)
        
        if not success:
            logger.error(f"Cross-border payment failed: {response}")
            return False
        
        # Verify latency requirement
        if latency_ms > self.max_latency_ms:
            logger.error(f"Cross-border payment latency too high: {latency_ms:.2f}ms (max: {self.max_latency_ms}ms)")
            return False
        
        # Verify currency conversion
        expected_target_amount = crossborder_payment.amount * fx_rate
        actual_target_amount = Decimal(str(response.get("target_amount", "0")))
        
        # Allow 1% tolerance for FX conversion
        tolerance = expected_target_amount * Decimal("0.01")
        if abs(actual_target_amount - expected_target_amount) > tolerance:
            logger.error(f"Currency conversion mismatch: expected ~{expected_target_amount}, got {actual_target_amount}")
            return False
        
        # Verify payment routing
        if response.get("routing_path") is None:
            logger.error("Missing routing path in cross-border payment response")
            return False
        
        logger.info(f"✅ Cross-border payment processing test passed: {latency_ms:.2f}ms")
        return True
    
    def test_iso20022_message_compliance(self) -> bool:
        """Test ISO 20022 message compliance"""
        logger.info("Testing ISO 20022 message compliance")
        
        test_payments = self.setup_test_payments()
        payment = test_payments[0]
        
        # Process payment and get message details
        success, latency_ms, response = self.process_realtime_payment(payment)
        
        if not success:
            logger.error(f"Payment failed for ISO 20022 test: {response}")
            return False
        
        # Verify ISO 20022 message structure
        iso_message = response.get("iso20022_message")
        if not iso_message:
            logger.error("Missing ISO 20022 message in response")
            return False
        
        # Check required ISO 20022 fields
        required_fields = [
            "message_id",
            "creation_date_time",
            "instructing_agent",
            "instructed_agent",
            "debtor_account",
            "creditor_account",
            "instructed_amount"
        ]
        
        for field in required_fields:
            if field not in iso_message:
                logger.error(f"Missing required ISO 20022 field: {field}")
                return False
        
        # Verify message ID format
        message_id = iso_message.get("message_id")
        if not message_id or len(message_id) < 10:
            logger.error(f"Invalid ISO 20022 message ID: {message_id}")
            return False
        
        # Verify amount format
        instructed_amount = iso_message.get("instructed_amount")
        if not instructed_amount or "currency" not in instructed_amount or "amount" not in instructed_amount:
            logger.error(f"Invalid ISO 20022 amount format: {instructed_amount}")
            return False
        
        logger.info("✅ ISO 20022 message compliance test passed")
        return True
    
    def test_correspondent_banking_routing(self) -> bool:
        """Test correspondent banking routing"""
        logger.info("Testing correspondent banking routing")
        
        test_payments = self.setup_test_payments()
        uk_japan_payment = test_payments[1]  # Use UK to Japan payment (requires correspondent)
        
        # Process payment
        success, latency_ms, response = self.process_realtime_payment(uk_japan_payment)
        
        if not success:
            logger.error(f"Correspondent banking payment failed: {response}")
            return False
        
        # Verify correspondent routing
        routing_path = response.get("routing_path", [])
        if len(routing_path) < 2:
            logger.error(f"Insufficient routing path for correspondent banking: {routing_path}")
            return False
        
        # Verify correspondent bank is included
        correspondent_banks = [hop.get("bank_code") for hop in routing_path if hop.get("role") == "CORRESPONDENT"]
        if not correspondent_banks:
            logger.error("No correspondent bank found in routing path")
            return False
        
        # Verify SWIFT codes in routing
        for hop in routing_path:
            swift_code = hop.get("swift_code")
            if not swift_code or len(swift_code) not in [8, 11]:
                logger.error(f"Invalid SWIFT code in routing: {swift_code}")
                return False
        
        logger.info(f"✅ Correspondent banking routing test passed: {len(routing_path)} hops")
        return True
    
    def test_high_frequency_payments(self, num_payments: int = 50) -> bool:
        """Test high-frequency payment processing"""
        logger.info(f"Testing high-frequency payments: {num_payments} payments")
        
        # Generate multiple payments
        payments = []
        for i in range(num_payments):
            payment = TestCrossBorderPayment(
                payment_id=f"HFREQ_PAY_{i:04d}_{uuid.uuid4().hex[:6]}",
                sender_bank="US_BANK_001",
                receiver_bank="US_BANK_002",
                sender_account=f"US_ACC_{i % 10:03d}",
                receiver_account=f"US_ACC_{(i + 1) % 10:03d}",
                amount=Decimal(str(random.uniform(10, 1000))).quantize(Decimal('0.01')),
                source_currency="USD",
                target_currency="USD",
                sender_country="US",
                receiver_country="US",
                purpose_code="P2P"
            )
            payments.append(payment)
        
        # Process payments with controlled concurrency
        successful_payments = 0
        failed_payments = 0
        latencies = []
        
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(self.process_realtime_payment, payments))
        
        end_time = time.time()
        total_time = end_time - start_time
        
        # Analyze results
        for success, latency_ms, response in results:
            latencies.append(latency_ms)
            if success:
                successful_payments += 1
            else:
                failed_payments += 1
        
        # Calculate metrics
        success_rate = successful_payments / num_payments if num_payments > 0 else 0
        avg_latency = sum(latencies) / len(latencies) if latencies else 0
        throughput = successful_payments / total_time if total_time > 0 else 0
        
        # Success criteria
        if success_rate < 0.95:  # 95% success rate
            logger.error(f"Low success rate in high-frequency test: {success_rate:.2%}")
            return False
        
        if avg_latency > self.domestic_max_latency_ms:
            logger.error(f"High average latency: {avg_latency:.2f}ms")
            return False
        
        if throughput < 10:  # At least 10 payments per second
            logger.error(f"Low throughput: {throughput:.2f} payments/second")
            return False
        
        logger.info(f"✅ High-frequency payments test passed: {successful_payments}/{num_payments} successful, {throughput:.2f} TPS, {avg_latency:.2f}ms avg latency")
        return True
    
    def test_payment_settlement_verification(self) -> bool:
        """Test payment settlement verification"""
        logger.info("Testing payment settlement verification")
        
        test_payments = self.setup_test_payments()
        payment = test_payments[0]
        
        # Process payment
        success, latency_ms, response = self.process_realtime_payment(payment)
        
        if not success:
            logger.error(f"Payment failed for settlement test: {response}")
            return False
        
        # Get settlement details
        settlement_id = response.get("settlement_id")
        if not settlement_id:
            logger.error("Missing settlement ID in payment response")
            return False
        
        # Wait a moment for settlement processing
        time.sleep(2)
        
        # Verify settlement status
        try:
            settlement_response = requests.get(
                f"{self.settlement_engine_url}/settlements/{settlement_id}",
                timeout=10
            )
            
            if settlement_response.status_code != 200:
                logger.error(f"Failed to get settlement status: {settlement_response.status_code}")
                return False
            
            settlement_data = settlement_response.json()
            
            # Verify settlement completion
            if settlement_data.get("status") not in ["SETTLED", "COMPLETED"]:
                logger.error(f"Settlement not completed: {settlement_data.get('status')}")
                return False
            
            # Verify settlement amounts
            settlement_amount = Decimal(str(settlement_data.get("amount", "0")))
            if settlement_amount != payment.amount:
                logger.error(f"Settlement amount mismatch: expected {payment.amount}, got {settlement_amount}")
                return False
            
        except Exception as e:
            logger.error(f"Settlement verification failed: {e}")
            return False
        
        logger.info("✅ Payment settlement verification test passed")
        return True
    
    def run_all_tests(self) -> Dict[str, bool]:
        """Run all real-time payments tests"""
        logger.info("Starting comprehensive real-time payments tests")
        
        test_results = {}
        
        # Run all test suites
        test_results["domestic_payment_latency"] = self.test_domestic_payment_latency()
        test_results["crossborder_payment_processing"] = self.test_crossborder_payment_processing()
        test_results["iso20022_message_compliance"] = self.test_iso20022_message_compliance()
        test_results["correspondent_banking_routing"] = self.test_correspondent_banking_routing()
        test_results["high_frequency_payments"] = self.test_high_frequency_payments(25)  # Reduced for testing
        test_results["payment_settlement_verification"] = self.test_payment_settlement_verification()
        
        # Summary
        passed_tests = sum(1 for result in test_results.values() if result)
        total_tests = len(test_results)
        
        logger.info(f"Real-time Payments Tests: {passed_tests}/{total_tests} passed")
        
        for test_name, result in test_results.items():
            status = "✅ PASSED" if result else "❌ FAILED"
            logger.info(f"  {test_name}: {status}")
        
        return test_results

# Test cases using pytest
@pytest.mark.asyncio
async def test_domestic_latency():
    """Test domestic payment latency"""
    tester = RealTimePaymentsTester()
    result = tester.test_domestic_payment_latency()
    assert result, "Domestic payment latency test failed"

@pytest.mark.asyncio
async def test_crossborder_processing():
    """Test cross-border payment processing"""
    tester = RealTimePaymentsTester()
    result = tester.test_crossborder_payment_processing()
    assert result, "Cross-border payment processing test failed"

@pytest.mark.asyncio
async def test_iso20022_compliance():
    """Test ISO 20022 compliance"""
    tester = RealTimePaymentsTester()
    result = tester.test_iso20022_message_compliance()
    assert result, "ISO 20022 compliance test failed"

if __name__ == "__main__":
    # Run comprehensive real-time payments tests
    tester = RealTimePaymentsTester()
    results = tester.run_all_tests()
    
    # Exit with appropriate code
    all_passed = all(results.values())
    exit(0 if all_passed else 1)

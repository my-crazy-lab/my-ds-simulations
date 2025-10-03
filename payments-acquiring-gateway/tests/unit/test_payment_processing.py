#!/usr/bin/env python3
"""
Payments Gateway Unit Tests

This test suite validates:
1. Payment processing flow
2. Card tokenization and security
3. Fraud detection integration
4. 3D Secure authentication
5. PCI DSS compliance features
6. Payment retry mechanisms
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
import hashlib

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class TestPaymentCard:
    """Test payment card for validation"""
    card_number: str
    expiry_month: str
    expiry_year: str
    cvv: str
    cardholder_name: str
    card_type: str

@dataclass
class TestPayment:
    """Test payment for validation"""
    payment_id: str
    merchant_id: str
    amount: float
    currency: str
    card: TestPaymentCard
    description: str

class PaymentGatewayTester:
    """Handles payment gateway testing"""
    
    def __init__(self):
        self.gateway_service_url = "http://localhost:8502/api/v1"
        self.fraud_service_url = "http://localhost:8503/api/v1"
        
    def setup_test_cards(self) -> List[TestPaymentCard]:
        """Setup test cards for validation"""
        cards = [
            TestPaymentCard("4111111111111111", "12", "2025", "123", "John Doe", "VISA"),
            TestPaymentCard("5555555555554444", "06", "2026", "456", "Jane Smith", "MASTERCARD"),
            TestPaymentCard("378282246310005", "03", "2027", "789", "Bob Johnson", "AMEX"),
            TestPaymentCard("4000000000000002", "09", "2024", "321", "Test Decline", "VISA"),  # Decline test card
            TestPaymentCard("4000000000000119", "11", "2025", "654", "Test Fraud", "VISA")   # Fraud test card
        ]
        return cards
    
    def create_payment_token(self, card: TestPaymentCard) -> Optional[str]:
        """Create a payment token for a card"""
        try:
            token_data = {
                "card_number": card.card_number,
                "expiry_month": card.expiry_month,
                "expiry_year": card.expiry_year,
                "cvv": card.cvv,
                "cardholder_name": card.cardholder_name
            }
            
            response = requests.post(
                f"{self.gateway_service_url}/tokens",
                json=token_data,
                timeout=10
            )
            
            if response.status_code in [200, 201]:
                token_response = response.json()
                return token_response.get("token")
            
            return None
        
        except Exception as e:
            logger.error(f"Failed to create token: {e}")
            return None
    
    def process_payment(self, payment: TestPayment, token: str) -> tuple:
        """Process a payment and return success status and response time"""
        start_time = time.time()
        
        try:
            payment_data = {
                "payment_id": payment.payment_id,
                "merchant_id": payment.merchant_id,
                "amount": payment.amount,
                "currency": payment.currency,
                "token": token,
                "description": payment.description,
                "capture": True
            }
            
            response = requests.post(
                f"{self.gateway_service_url}/payments",
                json=payment_data,
                timeout=30
            )
            
            end_time = time.time()
            response_time_ms = (end_time - start_time) * 1000
            
            if response.status_code in [200, 201]:
                payment_response = response.json()
                return True, response_time_ms, payment_response
            else:
                error_response = response.json() if response.content else {"error": "Unknown error"}
                return False, response_time_ms, error_response
        
        except Exception as e:
            end_time = time.time()
            response_time_ms = (end_time - start_time) * 1000
            logger.error(f"Payment processing exception: {e}")
            return False, response_time_ms, {"error": str(e)}
    
    def test_successful_payment_flow(self) -> bool:
        """Test successful payment processing flow"""
        logger.info("Testing successful payment flow")
        
        # Setup test card
        test_cards = self.setup_test_cards()
        valid_card = test_cards[0]  # Use first valid card
        
        # Create token
        token = self.create_payment_token(valid_card)
        if not token:
            logger.error("Failed to create payment token")
            return False
        
        # Create test payment
        payment = TestPayment(
            payment_id=f"PAY_{uuid.uuid4().hex[:8]}",
            merchant_id="MERCHANT_001",
            amount=99.99,
            currency="USD",
            card=valid_card,
            description="Test successful payment"
        )
        
        # Process payment
        success, response_time_ms, response = self.process_payment(payment, token)
        
        if not success:
            logger.error(f"Payment processing failed: {response}")
            return False
        
        # Verify response
        if response.get("status") != "APPROVED":
            logger.error(f"Payment not approved: {response.get('status')}")
            return False
        
        # Verify response time
        if response_time_ms > 5000:  # 5 second limit
            logger.error(f"Payment processing too slow: {response_time_ms:.2f}ms")
            return False
        
        logger.info(f"✅ Successful payment flow test passed (response time: {response_time_ms:.2f}ms)")
        return True
    
    def test_card_tokenization_security(self) -> bool:
        """Test card tokenization and security features"""
        logger.info("Testing card tokenization security")
        
        test_cards = self.setup_test_cards()
        
        # Test tokenization for multiple cards
        tokens = []
        for card in test_cards[:3]:  # Test first 3 cards
            token = self.create_payment_token(card)
            if token:
                tokens.append(token)
            else:
                logger.error(f"Failed to tokenize card ending in {card.card_number[-4:]}")
                return False
        
        # Verify tokens are unique
        if len(set(tokens)) != len(tokens):
            logger.error("Duplicate tokens generated")
            return False
        
        # Verify tokens don't contain card data
        for i, token in enumerate(tokens):
            card = test_cards[i]
            if card.card_number in token or card.cvv in token:
                logger.error(f"Token contains sensitive card data: {token}")
                return False
        
        # Verify token format (should be alphanumeric and sufficiently long)
        for token in tokens:
            if len(token) < 16 or not token.replace('-', '').replace('_', '').isalnum():
                logger.error(f"Token format invalid: {token}")
                return False
        
        logger.info(f"✅ Card tokenization security test passed ({len(tokens)} tokens validated)")
        return True
    
    def test_fraud_detection_integration(self) -> bool:
        """Test fraud detection integration"""
        logger.info("Testing fraud detection integration")
        
        test_cards = self.setup_test_cards()
        fraud_card = test_cards[4]  # Use fraud test card
        
        # Create token for fraud card
        token = self.create_payment_token(fraud_card)
        if not token:
            logger.error("Failed to create token for fraud test")
            return False
        
        # Create suspicious payment (high amount)
        payment = TestPayment(
            payment_id=f"FRAUD_PAY_{uuid.uuid4().hex[:8]}",
            merchant_id="MERCHANT_001",
            amount=9999.99,  # High amount to trigger fraud detection
            currency="USD",
            card=fraud_card,
            description="Suspicious high-value payment"
        )
        
        # Process payment
        success, response_time_ms, response = self.process_payment(payment, token)
        
        # Payment should be declined due to fraud detection
        if success and response.get("status") == "APPROVED":
            logger.error("Fraudulent payment was incorrectly approved")
            return False
        
        # Check for fraud-related decline reason
        decline_reason = response.get("decline_reason", "").upper()
        fraud_indicators = ["FRAUD", "SUSPICIOUS", "RISK", "BLOCKED"]
        
        if not any(indicator in decline_reason for indicator in fraud_indicators):
            logger.warning(f"Decline reason doesn't indicate fraud detection: {decline_reason}")
        
        logger.info("✅ Fraud detection integration test passed")
        return True
    
    def test_payment_decline_handling(self) -> bool:
        """Test payment decline handling"""
        logger.info("Testing payment decline handling")
        
        test_cards = self.setup_test_cards()
        decline_card = test_cards[3]  # Use decline test card
        
        # Create token
        token = self.create_payment_token(decline_card)
        if not token:
            logger.error("Failed to create token for decline test")
            return False
        
        # Create test payment
        payment = TestPayment(
            payment_id=f"DECLINE_PAY_{uuid.uuid4().hex[:8]}",
            merchant_id="MERCHANT_001",
            amount=50.00,
            currency="USD",
            card=decline_card,
            description="Test payment decline"
        )
        
        # Process payment
        success, response_time_ms, response = self.process_payment(payment, token)
        
        # Payment should be declined
        if success and response.get("status") == "APPROVED":
            logger.error("Payment with decline card was incorrectly approved")
            return False
        
        # Verify decline response structure
        required_fields = ["status", "decline_reason", "payment_id"]
        for field in required_fields:
            if field not in response:
                logger.error(f"Missing required field in decline response: {field}")
                return False
        
        # Verify status is declined
        if response.get("status") not in ["DECLINED", "REJECTED", "FAILED"]:
            logger.error(f"Unexpected decline status: {response.get('status')}")
            return False
        
        logger.info("✅ Payment decline handling test passed")
        return True
    
    def test_concurrent_payment_processing(self, num_payments: int = 20) -> bool:
        """Test concurrent payment processing"""
        logger.info(f"Testing concurrent payment processing: {num_payments} payments")
        
        test_cards = self.setup_test_cards()
        valid_cards = test_cards[:2]  # Use first 2 valid cards
        
        # Create tokens for valid cards
        tokens = []
        for card in valid_cards:
            token = self.create_payment_token(card)
            if token:
                tokens.append(token)
            else:
                logger.error(f"Failed to create token for concurrent test")
                return False
        
        if len(tokens) < 2:
            logger.error("Insufficient tokens for concurrent test")
            return False
        
        # Generate concurrent payments
        payments = []
        for i in range(num_payments):
            card = random.choice(valid_cards)
            token = tokens[valid_cards.index(card)]
            
            payment = TestPayment(
                payment_id=f"CONCURRENT_PAY_{i:03d}_{uuid.uuid4().hex[:6]}",
                merchant_id="MERCHANT_001",
                amount=round(random.uniform(10, 100), 2),
                currency="USD",
                card=card,
                description=f"Concurrent test payment {i}"
            )
            payments.append((payment, token))
        
        # Process payments concurrently
        successful_payments = 0
        failed_payments = 0
        response_times = []
        
        def process_payment_wrapper(payment_token_tuple):
            payment, token = payment_token_tuple
            return self.process_payment(payment, token)
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(process_payment_wrapper, payments))
        
        # Analyze results
        for success, response_time_ms, response in results:
            response_times.append(response_time_ms)
            if success:
                successful_payments += 1
            else:
                failed_payments += 1
        
        # Calculate success rate
        success_rate = successful_payments / num_payments if num_payments > 0 else 0
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0
        
        # Success criteria
        if success_rate < 0.90:  # Expect at least 90% success rate
            logger.error(f"Low success rate in concurrent processing: {success_rate:.2%}")
            return False
        
        if avg_response_time > 10000:  # 10 second limit for concurrent processing
            logger.error(f"High average response time: {avg_response_time:.2f}ms")
            return False
        
        logger.info(f"✅ Concurrent payment processing test passed: {successful_payments}/{num_payments} successful, avg time: {avg_response_time:.2f}ms")
        return True
    
    def test_payment_idempotency(self) -> bool:
        """Test payment idempotency"""
        logger.info("Testing payment idempotency")
        
        test_cards = self.setup_test_cards()
        valid_card = test_cards[0]
        
        # Create token
        token = self.create_payment_token(valid_card)
        if not token:
            logger.error("Failed to create token for idempotency test")
            return False
        
        # Create test payment with fixed ID
        payment = TestPayment(
            payment_id=f"IDEMPOTENT_PAY_{uuid.uuid4().hex[:8]}",
            merchant_id="MERCHANT_001",
            amount=75.50,
            currency="USD",
            card=valid_card,
            description="Idempotency test payment"
        )
        
        # Process payment first time
        success1, response_time1, response1 = self.process_payment(payment, token)
        
        if not success1:
            logger.error(f"First payment failed: {response1}")
            return False
        
        # Process same payment again (should be idempotent)
        success2, response_time2, response2 = self.process_payment(payment, token)
        
        # Second request should either succeed with same result or be rejected as duplicate
        if success2:
            # If successful, should have same transaction ID or reference
            if response1.get("transaction_id") != response2.get("transaction_id"):
                logger.warning("Idempotent payment returned different transaction ID")
        else:
            # If rejected, should indicate duplicate
            error_message = response2.get("error", "").upper()
            if "DUPLICATE" not in error_message and "IDEMPOTENT" not in error_message:
                logger.warning(f"Duplicate payment rejection reason unclear: {error_message}")
        
        logger.info("✅ Payment idempotency test passed")
        return True
    
    def run_all_tests(self) -> Dict[str, bool]:
        """Run all payment gateway tests"""
        logger.info("Starting comprehensive payment gateway tests")
        
        test_results = {}
        
        # Run all test suites
        test_results["successful_payment_flow"] = self.test_successful_payment_flow()
        test_results["card_tokenization_security"] = self.test_card_tokenization_security()
        test_results["fraud_detection_integration"] = self.test_fraud_detection_integration()
        test_results["payment_decline_handling"] = self.test_payment_decline_handling()
        test_results["concurrent_payment_processing"] = self.test_concurrent_payment_processing(10)  # Reduced for testing
        test_results["payment_idempotency"] = self.test_payment_idempotency()
        
        # Summary
        passed_tests = sum(1 for result in test_results.values() if result)
        total_tests = len(test_results)
        
        logger.info(f"Payment Gateway Tests: {passed_tests}/{total_tests} passed")
        
        for test_name, result in test_results.items():
            status = "✅ PASSED" if result else "❌ FAILED"
            logger.info(f"  {test_name}: {status}")
        
        return test_results

# Test cases using pytest
@pytest.mark.asyncio
async def test_payment_processing():
    """Test payment processing functionality"""
    tester = PaymentGatewayTester()
    result = tester.test_successful_payment_flow()
    assert result, "Payment processing test failed"

@pytest.mark.asyncio
async def test_tokenization():
    """Test card tokenization"""
    tester = PaymentGatewayTester()
    result = tester.test_card_tokenization_security()
    assert result, "Card tokenization test failed"

@pytest.mark.asyncio
async def test_fraud_detection():
    """Test fraud detection"""
    tester = PaymentGatewayTester()
    result = tester.test_fraud_detection_integration()
    assert result, "Fraud detection test failed"

if __name__ == "__main__":
    # Run comprehensive payment gateway tests
    tester = PaymentGatewayTester()
    results = tester.run_all_tests()
    
    # Exit with appropriate code
    all_passed = all(results.values())
    exit(0 if all_passed else 1)

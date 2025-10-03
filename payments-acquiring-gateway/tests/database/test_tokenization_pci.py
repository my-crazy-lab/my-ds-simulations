#!/usr/bin/env python3
"""
Comprehensive Tokenization and PCI Compliance Tests for Payments Gateway
Tests secure tokenization, PCI scope minimization, and exactly-once settlement
"""

import asyncio
import hashlib
import json
import logging
import random
import re
import time
import unittest
import uuid
from typing import Dict, List, Optional, Set

import requests

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TokenizationPCITestClient:
    """Test client for tokenization and PCI compliance operations"""
    
    def __init__(self, gateway_url: str = "http://localhost:8080"):
        self.gateway_url = gateway_url
        self.session = requests.Session()
        self.session.timeout = 30
    
    def tokenize_card(self, card_data: Dict) -> Optional[Dict]:
        """Tokenize sensitive card data"""
        try:
            response = self.session.post(
                f"{self.gateway_url}/api/v1/tokenization/tokenize",
                json=card_data,
                headers={
                    "Content-Type": "application/json",
                    "X-PCI-Scope": "secure"
                }
            )
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"Tokenization failed: {e}")
            return None
    
    def detokenize_card(self, token: str, request_id: str) -> Optional[Dict]:
        """Detokenize card data (restricted operation)"""
        try:
            response = self.session.post(
                f"{self.gateway_url}/api/v1/tokenization/detokenize",
                json={
                    "token": token,
                    "request_id": request_id,
                    "purpose": "payment_processing"
                },
                headers={
                    "Content-Type": "application/json",
                    "X-PCI-Scope": "secure",
                    "Authorization": "Bearer test-token"
                }
            )
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"Detokenization failed: {e}")
            return None
    
    def authorize_payment(self, payment_data: Dict) -> Optional[Dict]:
        """Authorize payment using tokenized data"""
        try:
            response = self.session.post(
                f"{self.gateway_url}/api/v1/payments/authorize",
                json=payment_data,
                headers={"Content-Type": "application/json"}
            )
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"Payment authorization failed: {e}")
            return None
    
    def capture_payment(self, authorization_id: str, amount: float, idempotency_key: str) -> Optional[Dict]:
        """Capture authorized payment"""
        try:
            response = self.session.post(
                f"{self.gateway_url}/api/v1/payments/{authorization_id}/capture",
                json={
                    "amount": amount,
                    "currency": "USD",
                    "final_capture": True
                },
                headers={
                    "Content-Type": "application/json",
                    "Idempotency-Key": idempotency_key
                }
            )
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"Payment capture failed: {e}")
            return None
    
    def create_settlement_record(self, settlement_data: Dict) -> Optional[Dict]:
        """Create settlement record"""
        try:
            response = self.session.post(
                f"{self.gateway_url}/api/v1/settlements",
                json=settlement_data,
                headers={"Content-Type": "application/json"}
            )
            return response.json() if response.status_code == 201 else None
        except Exception as e:
            logger.error(f"Settlement record creation failed: {e}")
            return None
    
    def get_settlement_records(self, merchant_id: str, date: str) -> Optional[List[Dict]]:
        """Get settlement records for merchant and date"""
        try:
            response = self.session.get(
                f"{self.gateway_url}/api/v1/settlements",
                params={
                    "merchant_id": merchant_id,
                    "date": date
                }
            )
            return response.json().get("records", []) if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"Settlement records retrieval failed: {e}")
            return None
    
    def get_audit_logs(self, start_time: str, end_time: str, level: str = "INFO") -> Optional[List[Dict]]:
        """Get audit logs for specified time range"""
        try:
            response = self.session.get(
                f"{self.gateway_url}/api/v1/audit/logs",
                params={
                    "start_time": start_time,
                    "end_time": end_time,
                    "level": level
                }
            )
            return response.json().get("logs", []) if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"Audit logs retrieval failed: {e}")
            return None
    
    def simulate_psp_retry(self, payment_id: str, retry_count: int = 3) -> List[Dict]:
        """Simulate PSP retry scenarios"""
        results = []
        
        for i in range(retry_count):
            try:
                response = self.session.post(
                    f"{self.gateway_url}/api/v1/test/psp-retry",
                    json={
                        "payment_id": payment_id,
                        "retry_attempt": i + 1,
                        "simulate_failure": i < retry_count - 1  # Fail first attempts
                    }
                )
                
                if response.status_code == 200:
                    results.append(response.json())
                else:
                    results.append({"error": f"Retry {i+1} failed"})
                    
            except Exception as e:
                results.append({"error": str(e)})
                
            time.sleep(0.5)  # Brief delay between retries
        
        return results
    
    def check_pci_compliance(self) -> Optional[Dict]:
        """Check PCI compliance status"""
        try:
            response = self.session.get(f"{self.gateway_url}/api/v1/compliance/pci-status")
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"PCI compliance check failed: {e}")
            return None


class TokenizationPCIAnalyzer:
    """Analyzer for tokenization and PCI compliance"""
    
    def __init__(self, client: TokenizationPCITestClient):
        self.client = client
        self.test_tokens: List[str] = []
    
    def test_secure_tokenization(self, num_cards: int = 50) -> Dict:
        """Test secure tokenization of card data"""
        logger.info(f"Testing secure tokenization with {num_cards} cards")
        
        successful_tokenizations = 0
        failed_tokenizations = 0
        tokens_generated = set()
        
        # Generate test card data
        for i in range(num_cards):
            card_data = {
                "card_number": self._generate_test_card_number(),
                "expiry_month": random.randint(1, 12),
                "expiry_year": random.randint(2024, 2030),
                "cvv": f"{random.randint(100, 999)}",
                "cardholder_name": f"Test Cardholder {i}",
                "request_id": str(uuid.uuid4())
            }
            
            result = self.client.tokenize_card(card_data)
            
            if result and result.get("token"):
                successful_tokenizations += 1
                token = result["token"]
                tokens_generated.add(token)
                self.test_tokens.append(token)
                
                # Verify token format (should not contain PAN)
                if self._contains_sensitive_data(token, card_data["card_number"]):
                    logger.warning(f"Token may contain sensitive data: {token}")
            else:
                failed_tokenizations += 1
        
        # Test token uniqueness
        unique_tokens = len(tokens_generated)
        token_uniqueness = unique_tokens / successful_tokenizations if successful_tokenizations > 0 else 0
        
        return {
            "total_cards": num_cards,
            "successful_tokenizations": successful_tokenizations,
            "failed_tokenizations": failed_tokenizations,
            "unique_tokens": unique_tokens,
            "token_uniqueness": token_uniqueness,
            "tokenization_success_rate": successful_tokenizations / num_cards
        }
    
    def test_exactly_once_settlement(self, num_transactions: int = 30) -> Dict:
        """Test exactly-once settlement record creation"""
        logger.info(f"Testing exactly-once settlement with {num_transactions} transactions")
        
        merchant_id = f"merchant_{int(time.time())}"
        settlement_date = time.strftime("%Y-%m-%d")
        
        successful_settlements = 0
        duplicate_attempts = 0
        settlement_ids = set()
        
        # Create settlement records with intentional duplicates
        for i in range(num_transactions):
            transaction_id = f"txn_{i}_{int(time.time())}"
            amount = round(random.uniform(10.0, 500.0), 2)
            
            settlement_data = {
                "transaction_id": transaction_id,
                "merchant_id": merchant_id,
                "amount": amount,
                "currency": "USD",
                "settlement_date": settlement_date,
                "idempotency_key": f"settle_{transaction_id}"
            }
            
            # Create original settlement
            result = self.client.create_settlement_record(settlement_data)
            if result:
                successful_settlements += 1
                settlement_ids.add(result.get("settlement_id"))
                
                # Attempt duplicate with same idempotency key (should be ignored)
                if random.random() < 0.3:  # 30% chance of duplicate
                    duplicate_result = self.client.create_settlement_record(settlement_data)
                    duplicate_attempts += 1
                    
                    if duplicate_result:
                        # Should return same settlement ID
                        if duplicate_result.get("settlement_id") in settlement_ids:
                            logger.info("Duplicate correctly handled")
                        else:
                            logger.warning("Duplicate created new settlement record")
        
        # Verify settlement records
        settlement_records = self.client.get_settlement_records(merchant_id, settlement_date)
        actual_records = len(settlement_records) if settlement_records else 0
        
        return {
            "total_transactions": num_transactions,
            "successful_settlements": successful_settlements,
            "duplicate_attempts": duplicate_attempts,
            "unique_settlement_ids": len(settlement_ids),
            "actual_settlement_records": actual_records,
            "exactly_once_guarantee": actual_records == successful_settlements,
            "deduplication_effectiveness": duplicate_attempts > 0
        }
    
    def test_pci_compliance_logging(self, num_operations: int = 20) -> Dict:
        """Test PCI-compliant logging (no sensitive data in logs)"""
        logger.info(f"Testing PCI compliance logging with {num_operations} operations")
        
        start_time = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        
        # Perform various operations that should be logged
        operations_performed = 0
        for i in range(num_operations):
            card_data = {
                "card_number": self._generate_test_card_number(),
                "expiry_month": 12,
                "expiry_year": 2025,
                "cvv": "123",
                "cardholder_name": f"Test User {i}",
                "request_id": str(uuid.uuid4())
            }
            
            # Tokenize card
            result = self.client.tokenize_card(card_data)
            if result:
                operations_performed += 1
                
                # Authorize payment
                payment_data = {
                    "token": result["token"],
                    "amount": random.uniform(10.0, 100.0),
                    "currency": "USD",
                    "merchant_id": "test_merchant"
                }
                
                auth_result = self.client.authorize_payment(payment_data)
                if auth_result:
                    operations_performed += 1
        
        time.sleep(2)  # Allow logs to be written
        
        end_time = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        
        # Retrieve and analyze audit logs
        audit_logs = self.client.get_audit_logs(start_time, end_time)
        
        if not audit_logs:
            return {"error": "Failed to retrieve audit logs"}
        
        # Check for sensitive data in logs
        sensitive_data_found = 0
        total_log_entries = len(audit_logs)
        
        for log_entry in audit_logs:
            log_message = json.dumps(log_entry).lower()
            
            # Check for PAN patterns (should not be present)
            if self._contains_pan_pattern(log_message):
                sensitive_data_found += 1
                logger.warning(f"Potential PAN found in log: {log_entry.get('message', '')[:100]}")
        
        pci_compliant_logging = sensitive_data_found == 0
        
        return {
            "operations_performed": operations_performed,
            "total_log_entries": total_log_entries,
            "sensitive_data_found": sensitive_data_found,
            "pci_compliant_logging": pci_compliant_logging,
            "compliance_ratio": 1.0 if pci_compliant_logging else 0.0
        }
    
    def test_psp_retry_idempotency(self, num_payments: int = 10) -> Dict:
        """Test PSP retry scenarios with idempotency"""
        logger.info(f"Testing PSP retry idempotency with {num_payments} payments")
        
        successful_payments = 0
        retry_scenarios = 0
        idempotency_violations = 0
        
        for i in range(num_payments):
            # Create payment
            payment_id = f"payment_{i}_{int(time.time())}"
            
            # Simulate PSP retries
            retry_results = self.client.simulate_psp_retry(payment_id, retry_count=3)
            retry_scenarios += 1
            
            # Analyze retry results
            successful_retries = [r for r in retry_results if "error" not in r]
            
            if successful_retries:
                successful_payments += 1
                
                # Check for idempotency violations (multiple successful charges)
                if len(successful_retries) > 1:
                    # Verify all successful retries have same result
                    first_result = successful_retries[0]
                    for result in successful_retries[1:]:
                        if result.get("charge_id") != first_result.get("charge_id"):
                            idempotency_violations += 1
                            break
        
        return {
            "num_payments": num_payments,
            "successful_payments": successful_payments,
            "retry_scenarios": retry_scenarios,
            "idempotency_violations": idempotency_violations,
            "idempotency_success_rate": 1.0 - (idempotency_violations / retry_scenarios) if retry_scenarios > 0 else 0
        }
    
    def _generate_test_card_number(self) -> str:
        """Generate test card number (Luhn valid)"""
        # Generate test Visa number (starts with 4)
        prefix = "4000000000000"
        
        # Generate random digits
        for _ in range(2):
            prefix += str(random.randint(0, 9))
        
        # Calculate Luhn check digit
        check_digit = self._calculate_luhn_check_digit(prefix)
        return prefix + str(check_digit)
    
    def _calculate_luhn_check_digit(self, number: str) -> int:
        """Calculate Luhn check digit"""
        digits = [int(d) for d in number]
        for i in range(len(digits) - 1, -1, -2):
            digits[i] *= 2
            if digits[i] > 9:
                digits[i] -= 9
        
        total = sum(digits)
        return (10 - (total % 10)) % 10
    
    def _contains_sensitive_data(self, token: str, pan: str) -> bool:
        """Check if token contains sensitive data"""
        # Token should not contain the PAN
        return pan in token or any(pan[i:i+6] in token for i in range(len(pan) - 5))
    
    def _contains_pan_pattern(self, text: str) -> bool:
        """Check if text contains PAN patterns"""
        # Look for sequences of 13-19 digits (credit card patterns)
        pan_pattern = re.compile(r'\b\d{13,19}\b')
        return bool(pan_pattern.search(text))
    
    def cleanup_test_data(self):
        """Clean up test data"""
        for token in self.test_tokens:
            try:
                # Attempt to revoke token (if API supports it)
                self.client.session.delete(f"{self.client.gateway_url}/api/v1/tokenization/tokens/{token}")
            except Exception:
                pass
        self.test_tokens.clear()


class TestTokenizationPCI(unittest.TestCase):
    """Test cases for tokenization and PCI compliance"""
    
    @classmethod
    def setUpClass(cls):
        cls.client = TokenizationPCITestClient()
        cls.analyzer = TokenizationPCIAnalyzer(cls.client)
        
        # Wait for payment gateway to be ready
        max_retries = 30
        for i in range(max_retries):
            try:
                compliance_status = cls.client.check_pci_compliance()
                if compliance_status and compliance_status.get("status") == "ready":
                    logger.info("Payment gateway is ready")
                    break
            except Exception:
                pass
            time.sleep(1)
        else:
            raise Exception("Payment gateway not ready after 30 seconds")
    
    @classmethod
    def tearDownClass(cls):
        cls.analyzer.cleanup_test_data()
    
    def test_secure_card_tokenization(self):
        """Test secure tokenization of card data"""
        result = self.analyzer.test_secure_tokenization(num_cards=20)
        
        self.assertGreater(result["tokenization_success_rate"], 0.95)
        self.assertGreater(result["token_uniqueness"], 0.99)
        
        logger.info(f"Secure Tokenization Test: {result}")
    
    def test_exactly_once_settlement_records(self):
        """Test exactly-once settlement record creation"""
        result = self.analyzer.test_exactly_once_settlement(num_transactions=15)
        
        self.assertTrue(result["exactly_once_guarantee"])
        self.assertTrue(result["deduplication_effectiveness"])
        
        logger.info(f"Exactly-Once Settlement Test: {result}")
    
    def test_pci_compliant_audit_logging(self):
        """Test PCI-compliant audit logging"""
        result = self.analyzer.test_pci_compliance_logging(num_operations=10)
        
        self.assertNotIn("error", result)
        self.assertTrue(result["pci_compliant_logging"])
        self.assertEqual(result["sensitive_data_found"], 0)
        
        logger.info(f"PCI Compliance Logging Test: {result}")
    
    def test_psp_retry_idempotency_guarantees(self):
        """Test PSP retry scenarios with idempotency"""
        result = self.analyzer.test_psp_retry_idempotency(num_payments=5)
        
        self.assertGreater(result["idempotency_success_rate"], 0.95)
        self.assertEqual(result["idempotency_violations"], 0)
        
        logger.info(f"PSP Retry Idempotency Test: {result}")


if __name__ == "__main__":
    unittest.main()

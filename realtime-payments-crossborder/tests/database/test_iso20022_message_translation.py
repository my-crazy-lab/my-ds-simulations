#!/usr/bin/env python3
"""
Comprehensive ISO 20022 Message Translation Tests for Real-time Payments
Tests schema evolution, message routing, and cross-border payment processing
"""

import asyncio
import json
import logging
import random
import time
import unittest
import uuid
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional

import requests

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ISO20022TranslationTestClient:
    """Test client for ISO 20022 message translation operations"""
    
    def __init__(self, payment_router_url: str = "http://localhost:8080"):
        self.payment_router_url = payment_router_url
        self.session = requests.Session()
        self.session.timeout = 30
    
    def submit_pacs008_message(self, message_data: Dict) -> Optional[Dict]:
        """Submit PACS.008 (Customer Credit Transfer) message"""
        try:
            response = self.session.post(
                f"{self.payment_router_url}/api/v1/iso20022/pacs.008",
                json=message_data,
                headers={
                    "Content-Type": "application/json",
                    "X-Message-Type": "pacs.008.001.08"
                }
            )
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"PACS.008 submission failed: {e}")
            return None
    
    def submit_pacs002_message(self, message_data: Dict) -> Optional[Dict]:
        """Submit PACS.002 (Payment Status Report) message"""
        try:
            response = self.session.post(
                f"{self.payment_router_url}/api/v1/iso20022/pacs.002",
                json=message_data,
                headers={
                    "Content-Type": "application/json",
                    "X-Message-Type": "pacs.002.001.10"
                }
            )
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"PACS.002 submission failed: {e}")
            return None
    
    def submit_camt054_message(self, message_data: Dict) -> Optional[Dict]:
        """Submit CAMT.054 (Bank to Customer Debit/Credit Notification) message"""
        try:
            response = self.session.post(
                f"{self.payment_router_url}/api/v1/iso20022/camt.054",
                json=message_data,
                headers={
                    "Content-Type": "application/json",
                    "X-Message-Type": "camt.054.001.08"
                }
            )
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"CAMT.054 submission failed: {e}")
            return None
    
    def get_message_status(self, message_id: str) -> Optional[Dict]:
        """Get message processing status"""
        try:
            response = self.session.get(f"{self.payment_router_url}/api/v1/messages/{message_id}/status")
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"Message status retrieval failed: {e}")
            return None
    
    def get_routing_table(self) -> Optional[Dict]:
        """Get current routing table configuration"""
        try:
            response = self.session.get(f"{self.payment_router_url}/api/v1/routing/table")
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"Routing table retrieval failed: {e}")
            return None
    
    def update_routing_rule(self, rule_data: Dict) -> bool:
        """Update routing rule"""
        try:
            response = self.session.put(
                f"{self.payment_router_url}/api/v1/routing/rules",
                json=rule_data,
                headers={"Content-Type": "application/json"}
            )
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Routing rule update failed: {e}")
            return False
    
    def get_translation_errors(self, start_time: str, end_time: str) -> Optional[List[Dict]]:
        """Get translation errors for time range"""
        try:
            response = self.session.get(
                f"{self.payment_router_url}/api/v1/translation/errors",
                params={
                    "start_time": start_time,
                    "end_time": end_time
                }
            )
            return response.json().get("errors", []) if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"Translation errors retrieval failed: {e}")
            return None
    
    def validate_iso20022_schema(self, message_type: str, message_data: Dict) -> Optional[Dict]:
        """Validate ISO 20022 message against schema"""
        try:
            response = self.session.post(
                f"{self.payment_router_url}/api/v1/validation/iso20022",
                json={
                    "message_type": message_type,
                    "message_data": message_data
                },
                headers={"Content-Type": "application/json"}
            )
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"Schema validation failed: {e}")
            return None
    
    def simulate_network_delay(self, target_rail: str, delay_ms: int) -> bool:
        """Simulate network delay for specific payment rail"""
        try:
            response = self.session.post(
                f"{self.payment_router_url}/api/v1/test/network-delay",
                json={
                    "target_rail": target_rail,
                    "delay_ms": delay_ms
                }
            )
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Network delay simulation failed: {e}")
            return False
    
    def trigger_message_replay(self, message_ids: List[str]) -> Optional[Dict]:
        """Trigger message replay for reconciliation"""
        try:
            response = self.session.post(
                f"{self.payment_router_url}/api/v1/replay/messages",
                json={"message_ids": message_ids},
                headers={"Content-Type": "application/json"}
            )
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"Message replay failed: {e}")
            return None


class ISO20022TranslationAnalyzer:
    """Analyzer for ISO 20022 message translation"""
    
    def __init__(self, client: ISO20022TranslationTestClient):
        self.client = client
        self.test_messages: List[str] = []
    
    def test_message_translation_accuracy(self, num_messages: int = 50) -> Dict:
        """Test accuracy of ISO 20022 message translation"""
        logger.info(f"Testing message translation accuracy with {num_messages} messages")
        
        successful_translations = 0
        failed_translations = 0
        validation_errors = 0
        
        message_types = ["pacs.008", "pacs.002", "camt.054"]
        
        for i in range(num_messages):
            message_type = random.choice(message_types)
            message_data = self._generate_test_message(message_type, i)
            
            # Validate message schema first
            validation_result = self.client.validate_iso20022_schema(message_type, message_data)
            
            if validation_result and validation_result.get("valid"):
                # Submit message for translation
                if message_type == "pacs.008":
                    result = self.client.submit_pacs008_message(message_data)
                elif message_type == "pacs.002":
                    result = self.client.submit_pacs002_message(message_data)
                elif message_type == "camt.054":
                    result = self.client.submit_camt054_message(message_data)
                
                if result and result.get("message_id"):
                    successful_translations += 1
                    self.test_messages.append(result["message_id"])
                else:
                    failed_translations += 1
            else:
                validation_errors += 1
                failed_translations += 1
        
        # Check translation errors
        end_time = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        start_time = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 300))  # 5 minutes ago
        
        translation_errors = self.client.get_translation_errors(start_time, end_time)
        error_count = len(translation_errors) if translation_errors else 0
        
        return {
            "total_messages": num_messages,
            "successful_translations": successful_translations,
            "failed_translations": failed_translations,
            "validation_errors": validation_errors,
            "translation_errors": error_count,
            "translation_accuracy": successful_translations / num_messages if num_messages > 0 else 0,
            "schema_compliance": (num_messages - validation_errors) / num_messages if num_messages > 0 else 0
        }
    
    def test_routing_consistency(self, num_payments: int = 30) -> Dict:
        """Test routing table consistency and updates"""
        logger.info(f"Testing routing consistency with {num_payments} payments")
        
        # Get initial routing table
        initial_routing = self.client.get_routing_table()
        if not initial_routing:
            return {"error": "Failed to get initial routing table"}
        
        # Create test routing rule
        test_rule = {
            "rule_id": f"test_rule_{int(time.time())}",
            "conditions": {
                "currency": "EUR",
                "amount_range": {"min": 0, "max": 10000},
                "destination_country": "DE"
            },
            "target_rail": "SEPA_INSTANT",
            "priority": 100
        }
        
        # Update routing table
        rule_update_success = self.client.update_routing_rule(test_rule)
        if not rule_update_success:
            return {"error": "Failed to update routing rule"}
        
        # Wait for routing table propagation
        time.sleep(2)
        
        # Send payments that should match the new rule
        matching_payments = 0
        correctly_routed = 0
        
        for i in range(num_payments):
            # Create payment that matches the rule
            payment_data = {
                "message_id": str(uuid.uuid4()),
                "instruction_id": f"INST{i:06d}",
                "amount": random.uniform(100, 5000),
                "currency": "EUR",
                "debtor": {
                    "name": f"Test Debtor {i}",
                    "account": f"DE89370400440532013{i:03d}"
                },
                "creditor": {
                    "name": f"Test Creditor {i}",
                    "account": f"DE89370400440532014{i:03d}"
                },
                "destination_country": "DE"
            }
            
            result = self.client.submit_pacs008_message(payment_data)
            
            if result:
                matching_payments += 1
                
                # Check if routed to correct rail
                if result.get("target_rail") == "SEPA_INSTANT":
                    correctly_routed += 1
        
        # Verify routing table consistency
        final_routing = self.client.get_routing_table()
        routing_consistent = (
            final_routing and 
            test_rule["rule_id"] in [rule.get("rule_id") for rule in final_routing.get("rules", [])]
        )
        
        return {
            "num_payments": num_payments,
            "matching_payments": matching_payments,
            "correctly_routed": correctly_routed,
            "routing_accuracy": correctly_routed / matching_payments if matching_payments > 0 else 0,
            "routing_table_consistent": routing_consistent,
            "rule_update_success": rule_update_success
        }
    
    def test_message_sequencing_guarantees(self, num_sequences: int = 10) -> Dict:
        """Test message sequencing guarantees across rails"""
        logger.info(f"Testing message sequencing with {num_sequences} sequences")
        
        successful_sequences = 0
        sequencing_violations = 0
        
        for seq_id in range(num_sequences):
            # Create sequence of related messages
            sequence_messages = []
            
            # 1. Original payment (PACS.008)
            payment_msg = {
                "message_id": f"PAY{seq_id:03d}001",
                "instruction_id": f"INST{seq_id:06d}",
                "amount": 1000.00,
                "currency": "USD",
                "sequence_number": 1,
                "sequence_id": f"SEQ{seq_id:03d}",
                "debtor": {"name": "Test Debtor", "account": "US123456789"},
                "creditor": {"name": "Test Creditor", "account": "US987654321"}
            }
            
            # 2. Status report (PACS.002)
            status_msg = {
                "message_id": f"STS{seq_id:03d}002",
                "original_message_id": payment_msg["message_id"],
                "status": "ACCP",  # Accepted
                "sequence_number": 2,
                "sequence_id": f"SEQ{seq_id:03d}",
                "reason_code": "AC01"
            }
            
            # 3. Credit notification (CAMT.054)
            notification_msg = {
                "message_id": f"NTF{seq_id:03d}003",
                "related_message_id": payment_msg["message_id"],
                "amount": 1000.00,
                "currency": "USD",
                "sequence_number": 3,
                "sequence_id": f"SEQ{seq_id:03d}",
                "account": "US987654321",
                "transaction_type": "CREDIT"
            }
            
            # Submit messages in sequence
            results = []
            
            result1 = self.client.submit_pacs008_message(payment_msg)
            if result1:
                results.append(result1)
                time.sleep(0.1)  # Small delay
                
                result2 = self.client.submit_pacs002_message(status_msg)
                if result2:
                    results.append(result2)
                    time.sleep(0.1)
                    
                    result3 = self.client.submit_camt054_message(notification_msg)
                    if result3:
                        results.append(result3)
            
            # Verify sequence processing
            if len(results) == 3:
                successful_sequences += 1
                
                # Check if messages were processed in order
                timestamps = [r.get("processed_at") for r in results if r.get("processed_at")]
                if len(timestamps) == 3:
                    # Verify chronological order
                    if not (timestamps[0] <= timestamps[1] <= timestamps[2]):
                        sequencing_violations += 1
            
            time.sleep(0.5)  # Brief pause between sequences
        
        return {
            "num_sequences": num_sequences,
            "successful_sequences": successful_sequences,
            "sequencing_violations": sequencing_violations,
            "sequencing_accuracy": (successful_sequences - sequencing_violations) / successful_sequences if successful_sequences > 0 else 0,
            "sequence_guarantee": sequencing_violations == 0
        }
    
    def test_message_replayability(self, num_messages: int = 20) -> Dict:
        """Test message replayability for reconciliation"""
        logger.info(f"Testing message replayability with {num_messages} messages")
        
        # Submit original messages
        original_messages = []
        for i in range(num_messages):
            message_data = self._generate_test_message("pacs.008", i)
            result = self.client.submit_pacs008_message(message_data)
            
            if result and result.get("message_id"):
                original_messages.append(result["message_id"])
        
        if len(original_messages) < num_messages * 0.8:  # At least 80% success
            return {"error": "Failed to submit sufficient original messages"}
        
        # Wait for processing
        time.sleep(3)
        
        # Trigger replay
        replay_result = self.client.trigger_message_replay(original_messages)
        
        if not replay_result:
            return {"error": "Failed to trigger message replay"}
        
        # Wait for replay completion
        time.sleep(5)
        
        # Verify replay results
        replayed_messages = replay_result.get("replayed_messages", [])
        replay_errors = replay_result.get("errors", [])
        
        successful_replays = len(replayed_messages)
        replay_accuracy = successful_replays / len(original_messages) if original_messages else 0
        
        return {
            "original_messages": len(original_messages),
            "successful_replays": successful_replays,
            "replay_errors": len(replay_errors),
            "replay_accuracy": replay_accuracy,
            "replayability_guarantee": replay_accuracy > 0.95
        }
    
    def _generate_test_message(self, message_type: str, index: int) -> Dict:
        """Generate test message data"""
        base_data = {
            "message_id": f"{message_type.upper()}{index:06d}",
            "creation_date_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "number_of_transactions": 1
        }
        
        if message_type == "pacs.008":
            base_data.update({
                "instruction_id": f"INST{index:06d}",
                "amount": round(random.uniform(10.0, 10000.0), 2),
                "currency": random.choice(["USD", "EUR", "GBP"]),
                "debtor": {
                    "name": f"Test Debtor {index}",
                    "account": f"US12345678{index:04d}"
                },
                "creditor": {
                    "name": f"Test Creditor {index}",
                    "account": f"US87654321{index:04d}"
                },
                "remittance_info": f"Test payment {index}"
            })
        elif message_type == "pacs.002":
            base_data.update({
                "original_message_id": f"PACS008{index:06d}",
                "status": random.choice(["ACCP", "RJCT", "PDNG"]),
                "reason_code": "AC01"
            })
        elif message_type == "camt.054":
            base_data.update({
                "account": f"US12345678{index:04d}",
                "amount": round(random.uniform(10.0, 10000.0), 2),
                "currency": random.choice(["USD", "EUR", "GBP"]),
                "transaction_type": random.choice(["CREDIT", "DEBIT"]),
                "related_message_id": f"PACS008{index:06d}"
            })
        
        return base_data
    
    def cleanup_test_data(self):
        """Clean up test data"""
        for message_id in self.test_messages:
            try:
                # Attempt to delete test message (if API supports it)
                self.client.session.delete(f"{self.client.payment_router_url}/api/v1/messages/{message_id}")
            except Exception:
                pass
        self.test_messages.clear()


class TestISO20022Translation(unittest.TestCase):
    """Test cases for ISO 20022 message translation"""
    
    @classmethod
    def setUpClass(cls):
        cls.client = ISO20022TranslationTestClient()
        cls.analyzer = ISO20022TranslationAnalyzer(cls.client)
        
        # Wait for payment router to be ready
        max_retries = 30
        for i in range(max_retries):
            try:
                routing_table = cls.client.get_routing_table()
                if routing_table and routing_table.get("status") == "ready":
                    logger.info("Payment router is ready")
                    break
            except Exception:
                pass
            time.sleep(1)
        else:
            raise Exception("Payment router not ready after 30 seconds")
    
    @classmethod
    def tearDownClass(cls):
        cls.analyzer.cleanup_test_data()
    
    def test_iso20022_translation_accuracy(self):
        """Test ISO 20022 message translation accuracy"""
        result = self.analyzer.test_message_translation_accuracy(num_messages=25)
        
        self.assertGreater(result["translation_accuracy"], 0.90)
        self.assertGreater(result["schema_compliance"], 0.95)
        self.assertLess(result["translation_errors"], 3)
        
        logger.info(f"ISO 20022 Translation Test: {result}")
    
    def test_routing_table_consistency(self):
        """Test routing table consistency and updates"""
        result = self.analyzer.test_routing_consistency(num_payments=15)
        
        self.assertNotIn("error", result)
        self.assertTrue(result["routing_table_consistent"])
        self.assertGreater(result["routing_accuracy"], 0.85)
        
        logger.info(f"Routing Consistency Test: {result}")
    
    def test_message_sequencing_across_rails(self):
        """Test message sequencing guarantees"""
        result = self.analyzer.test_message_sequencing_guarantees(num_sequences=5)
        
        self.assertTrue(result["sequence_guarantee"])
        self.assertGreater(result["sequencing_accuracy"], 0.90)
        
        logger.info(f"Message Sequencing Test: {result}")
    
    def test_reconciliation_replayability(self):
        """Test message replayability for reconciliation"""
        result = self.analyzer.test_message_replayability(num_messages=10)
        
        self.assertNotIn("error", result)
        self.assertTrue(result["replayability_guarantee"])
        self.assertGreater(result["replay_accuracy"], 0.95)
        
        logger.info(f"Message Replayability Test: {result}")


if __name__ == "__main__":
    unittest.main()

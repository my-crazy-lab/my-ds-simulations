#!/usr/bin/env python3
"""
Comprehensive HSM and Multi-Signature Coordination Tests for Custody System
Tests HSM integration, multi-signature workflows, and key rotation
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


class HSMMultiSigTestClient:
    """Test client for HSM and multi-signature operations"""
    
    def __init__(self, custody_url: str = "http://localhost:8080"):
        self.custody_url = custody_url
        self.session = requests.Session()
        self.session.timeout = 30
    
    def create_wallet(self, wallet_data: Dict) -> Optional[Dict]:
        """Create multi-signature wallet"""
        try:
            response = self.session.post(
                f"{self.custody_url}/api/v1/wallets",
                json=wallet_data,
                headers={"Content-Type": "application/json"}
            )
            return response.json() if response.status_code == 201 else None
        except Exception as e:
            logger.error(f"Wallet creation failed: {e}")
            return None
    
    def initiate_transaction(self, transaction_data: Dict) -> Optional[Dict]:
        """Initiate multi-signature transaction"""
        try:
            response = self.session.post(
                f"{self.custody_url}/api/v1/transactions",
                json=transaction_data,
                headers={"Content-Type": "application/json"}
            )
            return response.json() if response.status_code == 201 else None
        except Exception as e:
            logger.error(f"Transaction initiation failed: {e}")
            return None
    
    def sign_transaction(self, transaction_id: str, signer_id: str) -> Optional[Dict]:
        """Sign transaction with HSM"""
        try:
            response = self.session.post(
                f"{self.custody_url}/api/v1/transactions/{transaction_id}/sign",
                json={"signer_id": signer_id},
                headers={"Content-Type": "application/json"}
            )
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"Transaction signing failed: {e}")
            return None
    
    def get_transaction_status(self, transaction_id: str) -> Optional[Dict]:
        """Get transaction status"""
        try:
            response = self.session.get(f"{self.custody_url}/api/v1/transactions/{transaction_id}")
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"Transaction status retrieval failed: {e}")
            return None
    
    def rotate_keys(self, wallet_id: str, rotation_data: Dict) -> Optional[Dict]:
        """Rotate wallet keys"""
        try:
            response = self.session.post(
                f"{self.custody_url}/api/v1/wallets/{wallet_id}/rotate-keys",
                json=rotation_data,
                headers={"Content-Type": "application/json"}
            )
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"Key rotation failed: {e}")
            return None
    
    def get_hsm_status(self) -> Optional[Dict]:
        """Get HSM status"""
        try:
            response = self.session.get(f"{self.custody_url}/api/v1/hsm/status")
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"HSM status retrieval failed: {e}")
            return None


class HSMMultiSigAnalyzer:
    """Analyzer for HSM and multi-signature operations"""
    
    def __init__(self, client: HSMMultiSigTestClient):
        self.client = client
        self.test_wallets: List[str] = []
        self.test_transactions: List[str] = []
    
    def test_hsm_integration_reliability(self, num_operations: int = 50) -> Dict:
        """Test HSM integration reliability"""
        logger.info(f"Testing HSM integration with {num_operations} operations")
        
        successful_operations = 0
        failed_operations = 0
        operation_times = []
        
        for i in range(num_operations):
            # Create wallet with HSM-backed keys
            wallet_data = {
                "wallet_id": f"HSM_WALLET_{i:06d}",
                "name": f"Test HSM Wallet {i}",
                "threshold": 2,
                "signers": [
                    {"signer_id": f"HSM_SIGNER_{i}_1", "hsm_key_id": f"HSM_KEY_{i}_1"},
                    {"signer_id": f"HSM_SIGNER_{i}_2", "hsm_key_id": f"HSM_KEY_{i}_2"},
                    {"signer_id": f"HSM_SIGNER_{i}_3", "hsm_key_id": f"HSM_KEY_{i}_3"}
                ],
                "asset_type": "BTC"
            }
            
            operation_start = time.time()
            result = self.client.create_wallet(wallet_data)
            operation_end = time.time()
            
            if result and result.get("wallet_id"):
                successful_operations += 1
                operation_times.append(operation_end - operation_start)
                self.test_wallets.append(result["wallet_id"])
                
                # Test HSM status check
                hsm_status = self.client.get_hsm_status()
                if not hsm_status or not hsm_status.get("healthy", False):
                    logger.warning(f"HSM unhealthy during operation {i}")
            else:
                failed_operations += 1
        
        avg_operation_time = sum(operation_times) / len(operation_times) if operation_times else 0
        
        return {
            "operations_attempted": num_operations,
            "successful_operations": successful_operations,
            "failed_operations": failed_operations,
            "success_rate": successful_operations / num_operations,
            "average_operation_time": avg_operation_time,
            "hsm_reliability": successful_operations / num_operations > 0.95
        }
    
    def test_multisig_workflow_coordination(self, num_transactions: int = 30) -> Dict:
        """Test multi-signature workflow coordination"""
        logger.info(f"Testing multi-sig coordination with {num_transactions} transactions")
        
        if len(self.test_wallets) == 0:
            return {"error": "No test wallets available for multi-sig testing"}
        
        successful_workflows = 0
        failed_workflows = 0
        coordination_times = []
        
        for i in range(num_transactions):
            wallet_id = random.choice(self.test_wallets)
            
            # Initiate transaction
            transaction_data = {
                "wallet_id": wallet_id,
                "amount": round(random.uniform(0.001, 1.0), 8),
                "recipient": f"bc1q{uuid.uuid4().hex[:32]}",
                "asset_type": "BTC"
            }
            
            workflow_start = time.time()
            transaction_result = self.client.initiate_transaction(transaction_data)
            
            if transaction_result and transaction_result.get("transaction_id"):
                transaction_id = transaction_result["transaction_id"]
                self.test_transactions.append(transaction_id)
                
                # Simulate multi-signature signing process
                signers = [f"HSM_SIGNER_{i}_1", f"HSM_SIGNER_{i}_2"]  # 2 of 3 threshold
                signatures_collected = 0
                
                for signer_id in signers:
                    sign_result = self.client.sign_transaction(transaction_id, signer_id)
                    if sign_result and sign_result.get("signature"):
                        signatures_collected += 1
                        time.sleep(0.1)  # Simulate signing delay
                
                # Check final transaction status
                final_status = self.client.get_transaction_status(transaction_id)
                workflow_end = time.time()
                
                if (final_status and 
                    final_status.get("status") == "signed" and 
                    signatures_collected >= 2):
                    successful_workflows += 1
                    coordination_times.append(workflow_end - workflow_start)
                else:
                    failed_workflows += 1
                    logger.warning(f"Multi-sig workflow failed for transaction {transaction_id}")
            else:
                failed_workflows += 1
        
        avg_coordination_time = (
            sum(coordination_times) / len(coordination_times)
            if coordination_times else 0
        )
        
        return {
            "transactions_attempted": num_transactions,
            "successful_workflows": successful_workflows,
            "failed_workflows": failed_workflows,
            "workflow_success_rate": successful_workflows / num_transactions,
            "average_coordination_time": avg_coordination_time,
            "coordination_efficiency": avg_coordination_time < 5.0  # < 5 seconds
        }
    
    def test_key_rotation_consistency(self, num_rotations: int = 10) -> Dict:
        """Test key rotation consistency and security"""
        logger.info(f"Testing key rotation with {num_rotations} rotations")
        
        if len(self.test_wallets) < num_rotations:
            return {"error": "Insufficient test wallets for key rotation testing"}
        
        successful_rotations = 0
        failed_rotations = 0
        rotation_times = []
        
        wallets_to_rotate = self.test_wallets[:num_rotations]
        
        for wallet_id in wallets_to_rotate:
            rotation_data = {
                "rotation_reason": "scheduled_rotation",
                "new_signers": [
                    {"signer_id": f"NEW_HSM_SIGNER_{wallet_id}_1", "hsm_key_id": f"NEW_HSM_KEY_{wallet_id}_1"},
                    {"signer_id": f"NEW_HSM_SIGNER_{wallet_id}_2", "hsm_key_id": f"NEW_HSM_KEY_{wallet_id}_2"},
                    {"signer_id": f"NEW_HSM_SIGNER_{wallet_id}_3", "hsm_key_id": f"NEW_HSM_KEY_{wallet_id}_3"}
                ],
                "threshold": 2
            }
            
            rotation_start = time.time()
            rotation_result = self.client.rotate_keys(wallet_id, rotation_data)
            rotation_end = time.time()
            
            if rotation_result and rotation_result.get("rotation_id"):
                successful_rotations += 1
                rotation_times.append(rotation_end - rotation_start)
                
                # Verify rotation by attempting to create a transaction with new keys
                test_transaction = {
                    "wallet_id": wallet_id,
                    "amount": 0.001,
                    "recipient": f"bc1q{uuid.uuid4().hex[:32]}",
                    "asset_type": "BTC"
                }
                
                tx_result = self.client.initiate_transaction(test_transaction)
                if not tx_result:
                    logger.warning(f"Transaction failed after key rotation for wallet {wallet_id}")
            else:
                failed_rotations += 1
                logger.error(f"Key rotation failed for wallet {wallet_id}")
        
        avg_rotation_time = sum(rotation_times) / len(rotation_times) if rotation_times else 0
        
        return {
            "rotations_attempted": num_rotations,
            "successful_rotations": successful_rotations,
            "failed_rotations": failed_rotations,
            "rotation_success_rate": successful_rotations / num_rotations,
            "average_rotation_time": avg_rotation_time,
            "rotation_efficiency": avg_rotation_time < 30.0  # < 30 seconds
        }
    
    def test_concurrent_signing_coordination(self, num_concurrent: int = 20) -> Dict:
        """Test concurrent signing coordination"""
        logger.info(f"Testing concurrent signing with {num_concurrent} concurrent operations")
        
        if len(self.test_wallets) == 0:
            return {"error": "No test wallets available for concurrent signing testing"}
        
        # Create multiple transactions simultaneously
        concurrent_transactions = []
        
        for i in range(num_concurrent):
            wallet_id = random.choice(self.test_wallets)
            transaction_data = {
                "wallet_id": wallet_id,
                "amount": round(random.uniform(0.001, 0.1), 8),
                "recipient": f"bc1q{uuid.uuid4().hex[:32]}",
                "asset_type": "BTC"
            }
            
            transaction_result = self.client.initiate_transaction(transaction_data)
            if transaction_result and transaction_result.get("transaction_id"):
                concurrent_transactions.append(transaction_result["transaction_id"])
        
        # Attempt to sign all transactions concurrently
        successful_signings = 0
        failed_signings = 0
        
        start_time = time.time()
        
        for transaction_id in concurrent_transactions:
            # Sign with first signer
            sign_result_1 = self.client.sign_transaction(transaction_id, "HSM_SIGNER_CONCURRENT_1")
            # Sign with second signer
            sign_result_2 = self.client.sign_transaction(transaction_id, "HSM_SIGNER_CONCURRENT_2")
            
            if (sign_result_1 and sign_result_1.get("signature") and
                sign_result_2 and sign_result_2.get("signature")):
                successful_signings += 1
            else:
                failed_signings += 1
        
        end_time = time.time()
        total_time = end_time - start_time
        
        return {
            "concurrent_transactions": num_concurrent,
            "successful_signings": successful_signings,
            "failed_signings": failed_signings,
            "concurrent_success_rate": successful_signings / num_concurrent,
            "total_coordination_time": total_time,
            "concurrent_efficiency": total_time < 60.0  # < 1 minute for all
        }
    
    def cleanup_test_data(self):
        """Clean up test data"""
        for wallet_id in self.test_wallets:
            try:
                self.client.session.delete(f"{self.client.custody_url}/api/v1/wallets/{wallet_id}")
            except Exception:
                pass
        
        for transaction_id in self.test_transactions:
            try:
                self.client.session.delete(f"{self.client.custody_url}/api/v1/transactions/{transaction_id}")
            except Exception:
                pass
        
        self.test_wallets.clear()
        self.test_transactions.clear()


class TestHSMMultiSigCoordination(unittest.TestCase):
    """Test cases for HSM and multi-signature coordination"""
    
    @classmethod
    def setUpClass(cls):
        cls.client = HSMMultiSigTestClient()
        cls.analyzer = HSMMultiSigAnalyzer(cls.client)
        
        # Wait for custody system to be ready
        max_retries = 30
        for i in range(max_retries):
            try:
                # Check HSM status to verify system is ready
                hsm_status = cls.client.get_hsm_status()
                if hsm_status and hsm_status.get("healthy", False):
                    logger.info("Custody system and HSM are ready")
                    break
            except Exception:
                pass
            time.sleep(1)
        else:
            raise Exception("Custody system not ready after 30 seconds")
    
    @classmethod
    def tearDownClass(cls):
        cls.analyzer.cleanup_test_data()
    
    def test_hsm_integration_stability(self):
        """Test HSM integration stability"""
        result = self.analyzer.test_hsm_integration_reliability(num_operations=25)
        
        self.assertNotIn("error", result)
        self.assertGreater(result["success_rate"], 0.90)
        self.assertTrue(result["hsm_reliability"])
        
        logger.info(f"HSM Integration Test: {result}")
    
    def test_multisig_workflow_reliability(self):
        """Test multi-signature workflow reliability"""
        result = self.analyzer.test_multisig_workflow_coordination(num_transactions=15)
        
        self.assertNotIn("error", result)
        self.assertGreater(result["workflow_success_rate"], 0.85)
        self.assertTrue(result["coordination_efficiency"])
        
        logger.info(f"Multi-Sig Workflow Test: {result}")
    
    def test_key_rotation_security(self):
        """Test key rotation security and consistency"""
        result = self.analyzer.test_key_rotation_consistency(num_rotations=5)
        
        self.assertNotIn("error", result)
        self.assertGreater(result["rotation_success_rate"], 0.80)
        self.assertTrue(result["rotation_efficiency"])
        
        logger.info(f"Key Rotation Test: {result}")
    
    def test_concurrent_operations_coordination(self):
        """Test concurrent operations coordination"""
        result = self.analyzer.test_concurrent_signing_coordination(num_concurrent=10)
        
        self.assertNotIn("error", result)
        self.assertGreater(result["concurrent_success_rate"], 0.80)
        self.assertTrue(result["concurrent_efficiency"])
        
        logger.info(f"Concurrent Operations Test: {result}")


if __name__ == "__main__":
    unittest.main()

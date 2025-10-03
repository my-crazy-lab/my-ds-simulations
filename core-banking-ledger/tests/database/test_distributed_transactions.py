#!/usr/bin/env python3
"""
Comprehensive Distributed Transactions Tests for Core Banking Ledger
Tests ACID properties, distributed transactions, and double-entry bookkeeping
"""

import asyncio
import json
import logging
import random
import time
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

import requests

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DistributedTransactionTestClient:
    """Test client for distributed transaction operations"""
    
    def __init__(self, ledger_url: str = "http://localhost:8080"):
        self.ledger_url = ledger_url
        self.session = requests.Session()
        self.session.timeout = 30
    
    def create_account(self, account_id: str, account_type: str, initial_balance: Decimal = Decimal('0')) -> Optional[Dict]:
        """Create a new account"""
        try:
            response = self.session.post(
                f"{self.ledger_url}/api/v1/accounts",
                json={
                    "account_id": account_id,
                    "account_type": account_type,
                    "initial_balance": str(initial_balance),
                    "currency": "USD",
                    "metadata": {
                        "created_by": "test_system",
                        "purpose": "testing"
                    }
                },
                headers={"Content-Type": "application/json"}
            )
            return response.json() if response.status_code == 201 else None
        except Exception as e:
            logger.error(f"Account creation failed: {e}")
            return None
    
    def get_account_balance(self, account_id: str) -> Optional[Dict]:
        """Get account balance and details"""
        try:
            response = self.session.get(f"{self.ledger_url}/api/v1/accounts/{account_id}")
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"Balance retrieval failed: {e}")
            return None
    
    def create_transaction(self, transaction_data: Dict) -> Optional[Dict]:
        """Create a double-entry transaction"""
        try:
            response = self.session.post(
                f"{self.ledger_url}/api/v1/transactions",
                json=transaction_data,
                headers={"Content-Type": "application/json"}
            )
            return response.json() if response.status_code == 201 else None
        except Exception as e:
            logger.error(f"Transaction creation failed: {e}")
            return None
    
    def get_transaction(self, transaction_id: str) -> Optional[Dict]:
        """Get transaction details"""
        try:
            response = self.session.get(f"{self.ledger_url}/api/v1/transactions/{transaction_id}")
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"Transaction retrieval failed: {e}")
            return None
    
    def start_distributed_transaction(self, participants: List[str]) -> Optional[str]:
        """Start a distributed transaction across multiple shards"""
        try:
            response = self.session.post(
                f"{self.ledger_url}/api/v1/distributed-transactions/begin",
                json={
                    "participants": participants,
                    "timeout": 30000,  # 30 seconds
                    "isolation_level": "SERIALIZABLE"
                }
            )
            result = response.json() if response.status_code == 200 else None
            return result.get("transaction_id") if result else None
        except Exception as e:
            logger.error(f"Distributed transaction start failed: {e}")
            return None
    
    def commit_distributed_transaction(self, transaction_id: str) -> bool:
        """Commit distributed transaction"""
        try:
            response = self.session.post(
                f"{self.ledger_url}/api/v1/distributed-transactions/{transaction_id}/commit"
            )
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Distributed transaction commit failed: {e}")
            return False
    
    def rollback_distributed_transaction(self, transaction_id: str) -> bool:
        """Rollback distributed transaction"""
        try:
            response = self.session.post(
                f"{self.ledger_url}/api/v1/distributed-transactions/{transaction_id}/rollback"
            )
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Distributed transaction rollback failed: {e}")
            return False
    
    def create_cross_shard_transfer(self, from_account: str, to_account: str, 
                                   amount: Decimal, reference: str) -> Optional[Dict]:
        """Create cross-shard transfer"""
        try:
            response = self.session.post(
                f"{self.ledger_url}/api/v1/transfers/cross-shard",
                json={
                    "from_account": from_account,
                    "to_account": to_account,
                    "amount": str(amount),
                    "currency": "USD",
                    "reference": reference,
                    "description": f"Cross-shard transfer: {reference}"
                }
            )
            return response.json() if response.status_code == 201 else None
        except Exception as e:
            logger.error(f"Cross-shard transfer failed: {e}")
            return None
    
    def get_audit_trail(self, account_id: str, limit: int = 100) -> Optional[List[Dict]]:
        """Get audit trail for account"""
        try:
            response = self.session.get(
                f"{self.ledger_url}/api/v1/accounts/{account_id}/audit-trail",
                params={"limit": limit}
            )
            return response.json().get("entries", []) if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"Audit trail retrieval failed: {e}")
            return None
    
    def trigger_reconciliation(self, shard_id: str = None) -> Optional[Dict]:
        """Trigger reconciliation process"""
        try:
            url = f"{self.ledger_url}/api/v1/reconciliation/trigger"
            if shard_id:
                url += f"?shard_id={shard_id}"
            
            response = self.session.post(url)
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"Reconciliation trigger failed: {e}")
            return None
    
    def simulate_network_partition(self, shard_ids: List[str], duration: int = 10) -> bool:
        """Simulate network partition between shards"""
        try:
            response = self.session.post(
                f"{self.ledger_url}/api/v1/test/partition",
                json={
                    "shard_ids": shard_ids,
                    "duration": duration
                }
            )
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Partition simulation failed: {e}")
            return False


class DistributedTransactionAnalyzer:
    """Analyzer for distributed transaction behavior"""
    
    def __init__(self, client: DistributedTransactionTestClient):
        self.client = client
        self.test_accounts: List[str] = []
    
    def test_acid_properties(self, num_transactions: int = 50) -> Dict:
        """Test ACID properties in distributed transactions"""
        logger.info(f"Testing ACID properties with {num_transactions} transactions")
        
        # Create test accounts
        accounts = []
        for i in range(4):
            account_id = f"acid_test_{i}_{int(time.time())}"
            initial_balance = Decimal('1000.00')
            
            result = self.client.create_account(account_id, "CHECKING", initial_balance)
            if result:
                accounts.append(account_id)
                self.test_accounts.append(account_id)
        
        if len(accounts) < 4:
            return {"error": "Failed to create test accounts"}
        
        # Perform concurrent transactions
        successful_transactions = 0
        failed_transactions = 0
        total_amount_transferred = Decimal('0')
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = []
            
            for i in range(num_transactions):
                from_account = random.choice(accounts)
                to_account = random.choice([acc for acc in accounts if acc != from_account])
                amount = Decimal(str(random.uniform(1.0, 50.0))).quantize(Decimal('0.01'))
                
                future = executor.submit(
                    self._perform_transfer,
                    from_account,
                    to_account,
                    amount,
                    f"acid_test_{i}"
                )
                futures.append((future, amount))
            
            for future, amount in futures:
                try:
                    result = future.result(timeout=30)
                    if result:
                        successful_transactions += 1
                        total_amount_transferred += amount
                    else:
                        failed_transactions += 1
                except Exception:
                    failed_transactions += 1
        
        # Verify consistency (sum of all balances should remain constant)
        final_balances = []
        total_final_balance = Decimal('0')
        
        for account_id in accounts:
            balance_result = self.client.get_account_balance(account_id)
            if balance_result:
                balance = Decimal(balance_result["balance"])
                final_balances.append(balance)
                total_final_balance += balance
        
        initial_total = Decimal('4000.00')  # 4 accounts * 1000 each
        balance_consistent = abs(total_final_balance - initial_total) < Decimal('0.01')
        
        return {
            "total_transactions": num_transactions,
            "successful_transactions": successful_transactions,
            "failed_transactions": failed_transactions,
            "total_amount_transferred": str(total_amount_transferred),
            "initial_total_balance": str(initial_total),
            "final_total_balance": str(total_final_balance),
            "balance_consistent": balance_consistent,
            "consistency_ratio": 1.0 if balance_consistent else 0.0
        }
    
    def test_cross_shard_transactions(self, num_transfers: int = 20) -> Dict:
        """Test cross-shard distributed transactions"""
        logger.info(f"Testing cross-shard transactions with {num_transfers} transfers")
        
        # Create accounts on different shards
        shard_accounts = {}
        for shard_id in ["shard_1", "shard_2", "shard_3"]:
            account_id = f"cross_shard_{shard_id}_{int(time.time())}"
            initial_balance = Decimal('2000.00')
            
            result = self.client.create_account(account_id, "CHECKING", initial_balance)
            if result:
                shard_accounts[shard_id] = account_id
                self.test_accounts.append(account_id)
        
        if len(shard_accounts) < 3:
            return {"error": "Failed to create shard accounts"}
        
        # Perform cross-shard transfers
        successful_transfers = 0
        failed_transfers = 0
        
        for i in range(num_transfers):
            from_shard = random.choice(list(shard_accounts.keys()))
            to_shard = random.choice([s for s in shard_accounts.keys() if s != from_shard])
            
            from_account = shard_accounts[from_shard]
            to_account = shard_accounts[to_shard]
            amount = Decimal(str(random.uniform(10.0, 100.0))).quantize(Decimal('0.01'))
            
            result = self.client.create_cross_shard_transfer(
                from_account,
                to_account,
                amount,
                f"cross_shard_test_{i}"
            )
            
            if result:
                successful_transfers += 1
            else:
                failed_transfers += 1
        
        # Verify final consistency
        final_balances = {}
        total_final_balance = Decimal('0')
        
        for shard_id, account_id in shard_accounts.items():
            balance_result = self.client.get_account_balance(account_id)
            if balance_result:
                balance = Decimal(balance_result["balance"])
                final_balances[shard_id] = balance
                total_final_balance += balance
        
        initial_total = Decimal('6000.00')  # 3 accounts * 2000 each
        balance_consistent = abs(total_final_balance - initial_total) < Decimal('0.01')
        
        return {
            "num_transfers": num_transfers,
            "successful_transfers": successful_transfers,
            "failed_transfers": failed_transfers,
            "shard_balances": {k: str(v) for k, v in final_balances.items()},
            "initial_total": str(initial_total),
            "final_total": str(total_final_balance),
            "cross_shard_consistency": balance_consistent
        }
    
    def test_partition_tolerance(self, partition_duration: int = 10) -> Dict:
        """Test behavior during network partitions"""
        logger.info(f"Testing partition tolerance for {partition_duration} seconds")
        
        # Create test accounts
        accounts = []
        for i in range(2):
            account_id = f"partition_test_{i}_{int(time.time())}"
            initial_balance = Decimal('1500.00')
            
            result = self.client.create_account(account_id, "CHECKING", initial_balance)
            if result:
                accounts.append(account_id)
                self.test_accounts.append(account_id)
        
        if len(accounts) < 2:
            return {"error": "Failed to create test accounts"}
        
        # Simulate network partition
        partition_success = self.client.simulate_network_partition(
            ["shard_1", "shard_2"], 
            partition_duration
        )
        
        if not partition_success:
            return {"error": "Failed to simulate partition"}
        
        # Attempt transactions during partition
        partition_transactions = 0
        successful_during_partition = 0
        
        start_time = time.time()
        while time.time() - start_time < partition_duration:
            result = self._perform_transfer(
                accounts[0],
                accounts[1],
                Decimal('10.00'),
                f"partition_test_{int(time.time())}"
            )
            
            partition_transactions += 1
            if result:
                successful_during_partition += 1
            
            time.sleep(0.5)
        
        # Wait for partition to heal
        time.sleep(3)
        
        # Verify consistency after partition heals
        final_balances = []
        for account_id in accounts:
            balance_result = self.client.get_account_balance(account_id)
            if balance_result:
                final_balances.append(Decimal(balance_result["balance"]))
        
        total_final = sum(final_balances) if final_balances else Decimal('0')
        initial_total = Decimal('3000.00')  # 2 accounts * 1500 each
        consistency_after_partition = abs(total_final - initial_total) < Decimal('0.01')
        
        return {
            "partition_duration": partition_duration,
            "partition_transactions": partition_transactions,
            "successful_during_partition": successful_during_partition,
            "final_balances": [str(b) for b in final_balances],
            "consistency_after_partition": consistency_after_partition,
            "availability_during_partition": successful_during_partition / partition_transactions if partition_transactions > 0 else 0
        }
    
    def _perform_transfer(self, from_account: str, to_account: str, 
                         amount: Decimal, reference: str) -> bool:
        """Perform a single transfer transaction"""
        transaction_data = {
            "transaction_id": str(uuid.uuid4()),
            "reference": reference,
            "description": f"Transfer {amount} from {from_account} to {to_account}",
            "entries": [
                {
                    "account_id": from_account,
                    "amount": str(-amount),  # Debit
                    "entry_type": "DEBIT"
                },
                {
                    "account_id": to_account,
                    "amount": str(amount),   # Credit
                    "entry_type": "CREDIT"
                }
            ]
        }
        
        result = self.client.create_transaction(transaction_data)
        return result is not None
    
    def cleanup_test_accounts(self):
        """Clean up test accounts"""
        for account_id in self.test_accounts:
            try:
                self.client.session.delete(f"{self.client.ledger_url}/api/v1/accounts/{account_id}")
            except Exception:
                pass
        self.test_accounts.clear()


class TestDistributedTransactions(unittest.TestCase):
    """Test cases for distributed transactions"""
    
    @classmethod
    def setUpClass(cls):
        cls.client = DistributedTransactionTestClient()
        cls.analyzer = DistributedTransactionAnalyzer(cls.client)
        
        # Wait for ledger service to be ready
        max_retries = 30
        for i in range(max_retries):
            try:
                # Try to create a test account to verify service is ready
                test_result = cls.client.create_account("health_check", "CHECKING", Decimal('0'))
                if test_result:
                    logger.info("Core banking ledger is ready")
                    break
            except Exception:
                pass
            time.sleep(1)
        else:
            raise Exception("Core banking ledger not ready after 30 seconds")
    
    @classmethod
    def tearDownClass(cls):
        cls.analyzer.cleanup_test_accounts()
    
    def test_acid_transaction_properties(self):
        """Test ACID properties in distributed environment"""
        result = self.analyzer.test_acid_properties(num_transactions=20)
        
        self.assertNotIn("error", result)
        self.assertTrue(result["balance_consistent"])
        self.assertGreater(result["successful_transactions"], 15)
        
        logger.info(f"ACID Properties Test: {result}")
    
    def test_cross_shard_consistency(self):
        """Test cross-shard transaction consistency"""
        result = self.analyzer.test_cross_shard_transactions(num_transfers=10)
        
        self.assertNotIn("error", result)
        self.assertTrue(result["cross_shard_consistency"])
        self.assertGreater(result["successful_transfers"], 8)
        
        logger.info(f"Cross-Shard Consistency Test: {result}")
    
    def test_network_partition_handling(self):
        """Test behavior during network partitions"""
        result = self.analyzer.test_partition_tolerance(partition_duration=5)
        
        self.assertNotIn("error", result)
        self.assertTrue(result["consistency_after_partition"])
        
        logger.info(f"Partition Tolerance Test: {result}")


if __name__ == "__main__":
    unittest.main()

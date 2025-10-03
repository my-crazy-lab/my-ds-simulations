#!/usr/bin/env python3
"""
Core Banking Ledger Unit Tests

This test suite validates:
1. Double-entry bookkeeping correctness
2. ACID transaction properties
3. Account balance calculations
4. Transaction validation
5. Audit trail integrity
6. Concurrent transaction handling
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
import psycopg2
from decimal import Decimal

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class TestAccount:
    """Test account for validation"""
    account_id: str
    account_type: str
    currency: str
    initial_balance: Decimal

@dataclass
class TestTransaction:
    """Test transaction for validation"""
    transaction_id: str
    from_account: str
    to_account: str
    amount: Decimal
    currency: str
    description: str

class CoreBankingLedgerTester:
    """Handles core banking ledger testing"""
    
    def __init__(self):
        self.ledger_service_url = "http://localhost:8501/api/v1"
        self.db_connection_string = "postgresql://banking_user:secure_banking_pass@localhost:5433/core_banking"
        
    def setup_test_accounts(self) -> List[TestAccount]:
        """Setup test accounts for validation"""
        accounts = [
            TestAccount("ACC001", "CHECKING", "USD", Decimal("10000.00")),
            TestAccount("ACC002", "SAVINGS", "USD", Decimal("5000.00")),
            TestAccount("ACC003", "CHECKING", "EUR", Decimal("8000.00")),
            TestAccount("ACC004", "BUSINESS", "USD", Decimal("50000.00")),
            TestAccount("ACC005", "SAVINGS", "GBP", Decimal("3000.00"))
        ]
        return accounts
    
    def create_account(self, account: TestAccount) -> bool:
        """Create a test account"""
        try:
            account_data = {
                "account_id": account.account_id,
                "account_type": account.account_type,
                "currency": account.currency,
                "initial_balance": str(account.initial_balance)
            }
            
            response = requests.post(
                f"{self.ledger_service_url}/accounts",
                json=account_data,
                timeout=10
            )
            
            return response.status_code in [200, 201]
        
        except Exception as e:
            logger.error(f"Failed to create account {account.account_id}: {e}")
            return False
    
    def get_account_balance(self, account_id: str) -> Optional[Decimal]:
        """Get account balance"""
        try:
            response = requests.get(
                f"{self.ledger_service_url}/accounts/{account_id}/balance",
                timeout=10
            )
            
            if response.status_code == 200:
                balance_data = response.json()
                return Decimal(balance_data.get("balance", "0"))
            
            return None
        
        except Exception as e:
            logger.error(f"Failed to get balance for {account_id}: {e}")
            return None
    
    def create_transaction(self, transaction: TestTransaction) -> bool:
        """Create a test transaction"""
        try:
            transaction_data = {
                "transaction_id": transaction.transaction_id,
                "from_account": transaction.from_account,
                "to_account": transaction.to_account,
                "amount": str(transaction.amount),
                "currency": transaction.currency,
                "description": transaction.description
            }
            
            response = requests.post(
                f"{self.ledger_service_url}/transactions",
                json=transaction_data,
                timeout=10
            )
            
            return response.status_code in [200, 201]
        
        except Exception as e:
            logger.error(f"Failed to create transaction {transaction.transaction_id}: {e}")
            return False
    
    def verify_double_entry_bookkeeping(self, transaction: TestTransaction) -> bool:
        """Verify double-entry bookkeeping for a transaction"""
        try:
            # Connect to database to verify journal entries
            conn = psycopg2.connect(self.db_connection_string)
            cursor = conn.cursor()
            
            # Check journal entries for this transaction
            cursor.execute("""
                SELECT account_id, debit_amount, credit_amount 
                FROM journal_entries 
                WHERE transaction_id = %s
                ORDER BY account_id
            """, (transaction.transaction_id,))
            
            entries = cursor.fetchall()
            
            if len(entries) != 2:
                logger.error(f"Expected 2 journal entries, found {len(entries)}")
                return False
            
            # Verify debit and credit amounts balance
            total_debits = sum(Decimal(entry[1] or 0) for entry in entries)
            total_credits = sum(Decimal(entry[2] or 0) for entry in entries)
            
            if total_debits != total_credits:
                logger.error(f"Debits ({total_debits}) != Credits ({total_credits})")
                return False
            
            # Verify amounts match transaction
            if total_debits != transaction.amount:
                logger.error(f"Journal amounts ({total_debits}) != Transaction amount ({transaction.amount})")
                return False
            
            cursor.close()
            conn.close()
            
            return True
        
        except Exception as e:
            logger.error(f"Failed to verify double-entry for {transaction.transaction_id}: {e}")
            return False
    
    def test_basic_transaction_flow(self) -> bool:
        """Test basic transaction flow"""
        logger.info("Testing basic transaction flow")
        
        # Setup test accounts
        accounts = self.setup_test_accounts()
        
        # Create accounts
        for account in accounts[:2]:  # Use first 2 accounts
            if not self.create_account(account):
                logger.error(f"Failed to create account {account.account_id}")
                return False
        
        # Wait for account creation
        time.sleep(1)
        
        # Get initial balances
        initial_balance_1 = self.get_account_balance(accounts[0].account_id)
        initial_balance_2 = self.get_account_balance(accounts[1].account_id)
        
        if initial_balance_1 is None or initial_balance_2 is None:
            logger.error("Failed to get initial balances")
            return False
        
        # Create test transaction
        transaction = TestTransaction(
            transaction_id=f"TXN_{uuid.uuid4().hex[:8]}",
            from_account=accounts[0].account_id,
            to_account=accounts[1].account_id,
            amount=Decimal("100.00"),
            currency="USD",
            description="Test transfer"
        )
        
        # Execute transaction
        if not self.create_transaction(transaction):
            logger.error("Failed to create transaction")
            return False
        
        # Wait for transaction processing
        time.sleep(2)
        
        # Verify balances
        final_balance_1 = self.get_account_balance(accounts[0].account_id)
        final_balance_2 = self.get_account_balance(accounts[1].account_id)
        
        if final_balance_1 is None or final_balance_2 is None:
            logger.error("Failed to get final balances")
            return False
        
        # Verify balance changes
        expected_balance_1 = initial_balance_1 - transaction.amount
        expected_balance_2 = initial_balance_2 + transaction.amount
        
        if final_balance_1 != expected_balance_1:
            logger.error(f"Account 1 balance mismatch: expected {expected_balance_1}, got {final_balance_1}")
            return False
        
        if final_balance_2 != expected_balance_2:
            logger.error(f"Account 2 balance mismatch: expected {expected_balance_2}, got {final_balance_2}")
            return False
        
        # Verify double-entry bookkeeping
        if not self.verify_double_entry_bookkeeping(transaction):
            logger.error("Double-entry bookkeeping verification failed")
            return False
        
        logger.info("✅ Basic transaction flow test passed")
        return True
    
    def test_concurrent_transactions(self, num_transactions: int = 50) -> bool:
        """Test concurrent transaction processing"""
        logger.info(f"Testing concurrent transactions: {num_transactions} transactions")
        
        # Setup test accounts
        accounts = self.setup_test_accounts()
        
        # Create accounts
        for account in accounts[:4]:  # Use first 4 accounts
            if not self.create_account(account):
                logger.error(f"Failed to create account {account.account_id}")
                return False
        
        time.sleep(2)
        
        # Get initial balances
        initial_balances = {}
        for account in accounts[:4]:
            balance = self.get_account_balance(account.account_id)
            if balance is None:
                logger.error(f"Failed to get initial balance for {account.account_id}")
                return False
            initial_balances[account.account_id] = balance
        
        # Generate concurrent transactions
        transactions = []
        for i in range(num_transactions):
            from_account = random.choice(accounts[:2])  # First 2 accounts as sources
            to_account = random.choice(accounts[2:4])   # Last 2 accounts as destinations
            
            transaction = TestTransaction(
                transaction_id=f"CONCURRENT_TXN_{i:04d}_{uuid.uuid4().hex[:6]}",
                from_account=from_account.account_id,
                to_account=to_account.account_id,
                amount=Decimal(str(random.uniform(10, 100))).quantize(Decimal('0.01')),
                currency="USD",
                description=f"Concurrent test transaction {i}"
            )
            transactions.append(transaction)
        
        # Execute transactions concurrently
        successful_transactions = 0
        
        def execute_transaction(txn):
            if self.create_transaction(txn):
                return txn
            return None
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(execute_transaction, transactions))
            successful_transactions = sum(1 for result in results if result is not None)
        
        # Wait for all transactions to process
        time.sleep(5)
        
        # Verify final balances
        final_balances = {}
        for account in accounts[:4]:
            balance = self.get_account_balance(account.account_id)
            if balance is None:
                logger.error(f"Failed to get final balance for {account.account_id}")
                return False
            final_balances[account.account_id] = balance
        
        # Calculate expected balance changes
        expected_changes = {account.account_id: Decimal('0') for account in accounts[:4]}
        
        for result in results:
            if result is not None:
                expected_changes[result.from_account] -= result.amount
                expected_changes[result.to_account] += result.amount
        
        # Verify balance changes
        for account in accounts[:4]:
            expected_balance = initial_balances[account.account_id] + expected_changes[account.account_id]
            actual_balance = final_balances[account.account_id]
            
            if expected_balance != actual_balance:
                logger.error(f"Balance mismatch for {account.account_id}: expected {expected_balance}, got {actual_balance}")
                return False
        
        success_rate = successful_transactions / num_transactions
        if success_rate < 0.95:  # Expect at least 95% success rate
            logger.error(f"Low success rate: {success_rate:.2%}")
            return False
        
        logger.info(f"✅ Concurrent transactions test passed: {successful_transactions}/{num_transactions} successful")
        return True
    
    def test_insufficient_funds_handling(self) -> bool:
        """Test insufficient funds handling"""
        logger.info("Testing insufficient funds handling")
        
        # Setup test accounts
        accounts = self.setup_test_accounts()
        
        # Create account with low balance
        low_balance_account = TestAccount("LOW_BAL_001", "CHECKING", "USD", Decimal("50.00"))
        high_balance_account = accounts[0]
        
        if not self.create_account(low_balance_account):
            logger.error("Failed to create low balance account")
            return False
        
        if not self.create_account(high_balance_account):
            logger.error("Failed to create high balance account")
            return False
        
        time.sleep(1)
        
        # Get initial balance
        initial_balance = self.get_account_balance(low_balance_account.account_id)
        if initial_balance is None:
            logger.error("Failed to get initial balance")
            return False
        
        # Attempt transaction with insufficient funds
        transaction = TestTransaction(
            transaction_id=f"INSUFFICIENT_TXN_{uuid.uuid4().hex[:8]}",
            from_account=low_balance_account.account_id,
            to_account=high_balance_account.account_id,
            amount=Decimal("1000.00"),  # More than available balance
            currency="USD",
            description="Insufficient funds test"
        )
        
        # This transaction should fail
        transaction_success = self.create_transaction(transaction)
        
        time.sleep(2)
        
        # Verify balance unchanged
        final_balance = self.get_account_balance(low_balance_account.account_id)
        if final_balance is None:
            logger.error("Failed to get final balance")
            return False
        
        if final_balance != initial_balance:
            logger.error(f"Balance changed unexpectedly: {initial_balance} -> {final_balance}")
            return False
        
        # Transaction should have been rejected
        if transaction_success:
            logger.error("Transaction with insufficient funds was incorrectly accepted")
            return False
        
        logger.info("✅ Insufficient funds handling test passed")
        return True
    
    def test_audit_trail_integrity(self) -> bool:
        """Test audit trail integrity"""
        logger.info("Testing audit trail integrity")
        
        # Setup test accounts
        accounts = self.setup_test_accounts()
        
        # Create accounts
        for account in accounts[:2]:
            if not self.create_account(account):
                logger.error(f"Failed to create account {account.account_id}")
                return False
        
        time.sleep(1)
        
        # Create multiple transactions
        transactions = []
        for i in range(5):
            transaction = TestTransaction(
                transaction_id=f"AUDIT_TXN_{i:03d}_{uuid.uuid4().hex[:6]}",
                from_account=accounts[0].account_id,
                to_account=accounts[1].account_id,
                amount=Decimal(f"{10 + i}.00"),
                currency="USD",
                description=f"Audit test transaction {i}"
            )
            
            if self.create_transaction(transaction):
                transactions.append(transaction)
            
            time.sleep(0.5)
        
        time.sleep(2)
        
        # Verify audit trail in database
        try:
            conn = psycopg2.connect(self.db_connection_string)
            cursor = conn.cursor()
            
            # Check that all transactions have audit entries
            for transaction in transactions:
                cursor.execute("""
                    SELECT COUNT(*) FROM audit_log 
                    WHERE transaction_id = %s
                """, (transaction.transaction_id,))
                
                audit_count = cursor.fetchone()[0]
                if audit_count == 0:
                    logger.error(f"No audit entries found for transaction {transaction.transaction_id}")
                    return False
            
            # Verify audit log completeness
            cursor.execute("""
                SELECT transaction_id, action, timestamp, user_id
                FROM audit_log 
                WHERE transaction_id LIKE 'AUDIT_TXN_%'
                ORDER BY timestamp
            """)
            
            audit_entries = cursor.fetchall()
            
            if len(audit_entries) < len(transactions):
                logger.error(f"Insufficient audit entries: expected >= {len(transactions)}, got {len(audit_entries)}")
                return False
            
            cursor.close()
            conn.close()
            
            logger.info(f"✅ Audit trail integrity test passed: {len(audit_entries)} audit entries verified")
            return True
        
        except Exception as e:
            logger.error(f"Failed to verify audit trail: {e}")
            return False
    
    def run_all_tests(self) -> Dict[str, bool]:
        """Run all core banking ledger tests"""
        logger.info("Starting comprehensive core banking ledger tests")
        
        test_results = {}
        
        # Run all test suites
        test_results["basic_transaction_flow"] = self.test_basic_transaction_flow()
        test_results["concurrent_transactions"] = self.test_concurrent_transactions(25)  # Reduced for testing
        test_results["insufficient_funds_handling"] = self.test_insufficient_funds_handling()
        test_results["audit_trail_integrity"] = self.test_audit_trail_integrity()
        
        # Summary
        passed_tests = sum(1 for result in test_results.values() if result)
        total_tests = len(test_results)
        
        logger.info(f"Core Banking Ledger Tests: {passed_tests}/{total_tests} passed")
        
        for test_name, result in test_results.items():
            status = "✅ PASSED" if result else "❌ FAILED"
            logger.info(f"  {test_name}: {status}")
        
        return test_results

# Test cases using pytest
@pytest.mark.asyncio
async def test_basic_transaction():
    """Test basic transaction functionality"""
    tester = CoreBankingLedgerTester()
    result = tester.test_basic_transaction_flow()
    assert result, "Basic transaction flow test failed"

@pytest.mark.asyncio
async def test_concurrent_processing():
    """Test concurrent transaction processing"""
    tester = CoreBankingLedgerTester()
    result = tester.test_concurrent_transactions(10)  # Small test
    assert result, "Concurrent transactions test failed"

@pytest.mark.asyncio
async def test_insufficient_funds():
    """Test insufficient funds handling"""
    tester = CoreBankingLedgerTester()
    result = tester.test_insufficient_funds_handling()
    assert result, "Insufficient funds handling test failed"

if __name__ == "__main__":
    # Run comprehensive core banking tests
    tester = CoreBankingLedgerTester()
    results = tester.run_all_tests()
    
    # Exit with appropriate code
    all_passed = all(results.values())
    exit(0 if all_passed else 1)

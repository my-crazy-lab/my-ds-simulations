#!/usr/bin/env python3
"""
Core Banking Ledger Performance Tests

This test suite validates:
1. High-volume transaction processing
2. Concurrent user simulation
3. Database performance under load
4. Response time requirements
5. Throughput benchmarks
6. System scalability limits
"""

import asyncio
import json
import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Dict, List, Optional
from datetime import datetime
import random
import statistics
import requests
from decimal import Decimal

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class PerformanceTestResult:
    """Performance test result"""
    test_name: str
    total_transactions: int
    successful_transactions: int
    failed_transactions: int
    total_time_seconds: float
    transactions_per_second: float
    average_response_time_ms: float
    p95_response_time_ms: float
    p99_response_time_ms: float
    success: bool
    error_message: Optional[str] = None

class LedgerPerformanceTester:
    """Handles core banking ledger performance testing"""
    
    def __init__(self):
        self.ledger_service_url = "http://localhost:8501/api/v1"
        self.target_tps = 1000  # Target transactions per second
        self.max_response_time_ms = 500  # Maximum acceptable response time
        
    def create_test_accounts(self, num_accounts: int) -> List[str]:
        """Create test accounts for performance testing"""
        account_ids = []
        
        for i in range(num_accounts):
            account_id = f"PERF_ACC_{i:06d}"
            account_data = {
                "account_id": account_id,
                "account_type": "CHECKING",
                "currency": "USD",
                "initial_balance": "10000.00"
            }
            
            try:
                response = requests.post(
                    f"{self.ledger_service_url}/accounts",
                    json=account_data,
                    timeout=10
                )
                
                if response.status_code in [200, 201]:
                    account_ids.append(account_id)
                else:
                    logger.warning(f"Failed to create account {account_id}: {response.status_code}")
            
            except Exception as e:
                logger.warning(f"Exception creating account {account_id}: {e}")
        
        logger.info(f"Created {len(account_ids)} test accounts")
        return account_ids
    
    def execute_transaction(self, from_account: str, to_account: str, amount: Decimal) -> tuple:
        """Execute a single transaction and measure response time"""
        transaction_id = f"PERF_TXN_{uuid.uuid4().hex[:12]}"
        
        transaction_data = {
            "transaction_id": transaction_id,
            "from_account": from_account,
            "to_account": to_account,
            "amount": str(amount),
            "currency": "USD",
            "description": f"Performance test transaction"
        }
        
        start_time = time.time()
        
        try:
            response = requests.post(
                f"{self.ledger_service_url}/transactions",
                json=transaction_data,
                timeout=30
            )
            
            end_time = time.time()
            response_time_ms = (end_time - start_time) * 1000
            
            success = response.status_code in [200, 201]
            return success, response_time_ms, transaction_id
        
        except Exception as e:
            end_time = time.time()
            response_time_ms = (end_time - start_time) * 1000
            logger.warning(f"Transaction {transaction_id} failed: {e}")
            return False, response_time_ms, transaction_id
    
    def test_high_volume_transactions(self, num_transactions: int = 1000, num_accounts: int = 100) -> PerformanceTestResult:
        """Test high-volume transaction processing"""
        logger.info(f"Testing high-volume transactions: {num_transactions} transactions, {num_accounts} accounts")
        
        # Create test accounts
        account_ids = self.create_test_accounts(num_accounts)
        
        if len(account_ids) < 10:
            return PerformanceTestResult(
                test_name="High Volume Transactions",
                total_transactions=0,
                successful_transactions=0,
                failed_transactions=0,
                total_time_seconds=0,
                transactions_per_second=0,
                average_response_time_ms=0,
                p95_response_time_ms=0,
                p99_response_time_ms=0,
                success=False,
                error_message="Insufficient test accounts created"
            )
        
        # Wait for account creation to complete
        time.sleep(5)
        
        # Generate transactions
        transactions = []
        for i in range(num_transactions):
            from_account = random.choice(account_ids)
            to_account = random.choice(account_ids)
            
            # Ensure different accounts
            while to_account == from_account:
                to_account = random.choice(account_ids)
            
            amount = Decimal(str(random.uniform(1, 100))).quantize(Decimal('0.01'))
            transactions.append((from_account, to_account, amount))
        
        # Execute transactions with controlled concurrency
        successful_transactions = 0
        failed_transactions = 0
        response_times = []
        
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=20) as executor:
            # Submit all transactions
            future_to_transaction = {
                executor.submit(self.execute_transaction, from_acc, to_acc, amt): (from_acc, to_acc, amt)
                for from_acc, to_acc, amt in transactions
            }
            
            # Collect results
            for future in as_completed(future_to_transaction):
                try:
                    success, response_time_ms, transaction_id = future.result()
                    response_times.append(response_time_ms)
                    
                    if success:
                        successful_transactions += 1
                    else:
                        failed_transactions += 1
                
                except Exception as e:
                    logger.warning(f"Transaction execution exception: {e}")
                    failed_transactions += 1
                    response_times.append(30000)  # 30 second timeout
        
        end_time = time.time()
        total_time_seconds = end_time - start_time
        
        # Calculate performance metrics
        transactions_per_second = successful_transactions / total_time_seconds if total_time_seconds > 0 else 0
        average_response_time_ms = statistics.mean(response_times) if response_times else 0
        p95_response_time_ms = statistics.quantiles(response_times, n=20)[18] if len(response_times) >= 20 else 0
        p99_response_time_ms = statistics.quantiles(response_times, n=100)[98] if len(response_times) >= 100 else 0
        
        # Success criteria
        success_rate = successful_transactions / num_transactions if num_transactions > 0 else 0
        success = (
            success_rate >= 0.95 and  # 95% success rate
            transactions_per_second >= self.target_tps * 0.5 and  # At least 50% of target TPS
            average_response_time_ms <= self.max_response_time_ms  # Within response time limit
        )
        
        return PerformanceTestResult(
            test_name="High Volume Transactions",
            total_transactions=num_transactions,
            successful_transactions=successful_transactions,
            failed_transactions=failed_transactions,
            total_time_seconds=total_time_seconds,
            transactions_per_second=transactions_per_second,
            average_response_time_ms=average_response_time_ms,
            p95_response_time_ms=p95_response_time_ms,
            p99_response_time_ms=p99_response_time_ms,
            success=success,
            error_message=None if success else f"Success rate: {success_rate:.2%}, TPS: {transactions_per_second:.1f}, Avg time: {average_response_time_ms:.1f}ms"
        )
    
    def test_concurrent_users(self, num_users: int = 50, transactions_per_user: int = 20) -> PerformanceTestResult:
        """Test concurrent user simulation"""
        logger.info(f"Testing concurrent users: {num_users} users, {transactions_per_user} transactions each")
        
        # Create test accounts (more accounts for user simulation)
        num_accounts = max(100, num_users * 2)
        account_ids = self.create_test_accounts(num_accounts)
        
        if len(account_ids) < num_users:
            return PerformanceTestResult(
                test_name="Concurrent Users",
                total_transactions=0,
                successful_transactions=0,
                failed_transactions=0,
                total_time_seconds=0,
                transactions_per_second=0,
                average_response_time_ms=0,
                p95_response_time_ms=0,
                p99_response_time_ms=0,
                success=False,
                error_message="Insufficient test accounts for user simulation"
            )
        
        time.sleep(5)
        
        def simulate_user(user_id: int) -> tuple:
            """Simulate a single user's transaction activity"""
            user_successful = 0
            user_failed = 0
            user_response_times = []
            
            # Assign accounts to user
            user_accounts = account_ids[user_id * 2:(user_id * 2) + 2]
            if len(user_accounts) < 2:
                user_accounts = random.sample(account_ids, 2)
            
            for txn_num in range(transactions_per_user):
                from_account = random.choice(user_accounts)
                to_account = random.choice(account_ids)
                
                # Ensure different accounts
                while to_account == from_account:
                    to_account = random.choice(account_ids)
                
                amount = Decimal(str(random.uniform(5, 50))).quantize(Decimal('0.01'))
                
                success, response_time_ms, _ = self.execute_transaction(from_account, to_account, amount)
                user_response_times.append(response_time_ms)
                
                if success:
                    user_successful += 1
                else:
                    user_failed += 1
                
                # Small delay between user transactions
                time.sleep(random.uniform(0.1, 0.5))
            
            return user_successful, user_failed, user_response_times
        
        # Execute concurrent user simulation
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=num_users) as executor:
            user_futures = [executor.submit(simulate_user, user_id) for user_id in range(num_users)]
            
            total_successful = 0
            total_failed = 0
            all_response_times = []
            
            for future in as_completed(user_futures):
                try:
                    user_successful, user_failed, user_response_times = future.result()
                    total_successful += user_successful
                    total_failed += user_failed
                    all_response_times.extend(user_response_times)
                
                except Exception as e:
                    logger.warning(f"User simulation exception: {e}")
                    total_failed += transactions_per_user
        
        end_time = time.time()
        total_time_seconds = end_time - start_time
        
        # Calculate performance metrics
        total_transactions = num_users * transactions_per_user
        transactions_per_second = total_successful / total_time_seconds if total_time_seconds > 0 else 0
        average_response_time_ms = statistics.mean(all_response_times) if all_response_times else 0
        p95_response_time_ms = statistics.quantiles(all_response_times, n=20)[18] if len(all_response_times) >= 20 else 0
        p99_response_time_ms = statistics.quantiles(all_response_times, n=100)[98] if len(all_response_times) >= 100 else 0
        
        # Success criteria
        success_rate = total_successful / total_transactions if total_transactions > 0 else 0
        success = (
            success_rate >= 0.90 and  # 90% success rate for concurrent users
            average_response_time_ms <= self.max_response_time_ms * 2  # Allow higher response time for concurrent load
        )
        
        return PerformanceTestResult(
            test_name="Concurrent Users",
            total_transactions=total_transactions,
            successful_transactions=total_successful,
            failed_transactions=total_failed,
            total_time_seconds=total_time_seconds,
            transactions_per_second=transactions_per_second,
            average_response_time_ms=average_response_time_ms,
            p95_response_time_ms=p95_response_time_ms,
            p99_response_time_ms=p99_response_time_ms,
            success=success,
            error_message=None if success else f"Success rate: {success_rate:.2%}, Avg time: {average_response_time_ms:.1f}ms"
        )
    
    def test_sustained_load(self, duration_seconds: int = 60, target_tps: int = 100) -> PerformanceTestResult:
        """Test sustained load over time"""
        logger.info(f"Testing sustained load: {duration_seconds}s duration, {target_tps} TPS target")
        
        # Create test accounts
        account_ids = self.create_test_accounts(50)
        
        if len(account_ids) < 10:
            return PerformanceTestResult(
                test_name="Sustained Load",
                total_transactions=0,
                successful_transactions=0,
                failed_transactions=0,
                total_time_seconds=0,
                transactions_per_second=0,
                average_response_time_ms=0,
                p95_response_time_ms=0,
                p99_response_time_ms=0,
                success=False,
                error_message="Insufficient test accounts created"
            )
        
        time.sleep(3)
        
        # Calculate transaction interval
        transaction_interval = 1.0 / target_tps
        
        successful_transactions = 0
        failed_transactions = 0
        response_times = []
        
        start_time = time.time()
        end_time = start_time + duration_seconds
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = []
            
            while time.time() < end_time:
                # Generate transaction
                from_account = random.choice(account_ids)
                to_account = random.choice(account_ids)
                
                while to_account == from_account:
                    to_account = random.choice(account_ids)
                
                amount = Decimal(str(random.uniform(1, 50))).quantize(Decimal('0.01'))
                
                # Submit transaction
                future = executor.submit(self.execute_transaction, from_account, to_account, amount)
                futures.append(future)
                
                # Wait for next transaction
                time.sleep(transaction_interval)
            
            # Collect results
            for future in as_completed(futures):
                try:
                    success, response_time_ms, _ = future.result()
                    response_times.append(response_time_ms)
                    
                    if success:
                        successful_transactions += 1
                    else:
                        failed_transactions += 1
                
                except Exception as e:
                    logger.warning(f"Sustained load transaction exception: {e}")
                    failed_transactions += 1
        
        actual_end_time = time.time()
        total_time_seconds = actual_end_time - start_time
        
        # Calculate performance metrics
        total_transactions = successful_transactions + failed_transactions
        actual_tps = successful_transactions / total_time_seconds if total_time_seconds > 0 else 0
        average_response_time_ms = statistics.mean(response_times) if response_times else 0
        p95_response_time_ms = statistics.quantiles(response_times, n=20)[18] if len(response_times) >= 20 else 0
        p99_response_time_ms = statistics.quantiles(response_times, n=100)[98] if len(response_times) >= 100 else 0
        
        # Success criteria
        success_rate = successful_transactions / total_transactions if total_transactions > 0 else 0
        tps_achievement = actual_tps / target_tps if target_tps > 0 else 0
        
        success = (
            success_rate >= 0.95 and  # 95% success rate
            tps_achievement >= 0.8 and  # Achieve at least 80% of target TPS
            average_response_time_ms <= self.max_response_time_ms
        )
        
        return PerformanceTestResult(
            test_name="Sustained Load",
            total_transactions=total_transactions,
            successful_transactions=successful_transactions,
            failed_transactions=failed_transactions,
            total_time_seconds=total_time_seconds,
            transactions_per_second=actual_tps,
            average_response_time_ms=average_response_time_ms,
            p95_response_time_ms=p95_response_time_ms,
            p99_response_time_ms=p99_response_time_ms,
            success=success,
            error_message=None if success else f"Success rate: {success_rate:.2%}, TPS achievement: {tps_achievement:.2%}, Avg time: {average_response_time_ms:.1f}ms"
        )
    
    def format_test_result(self, result: PerformanceTestResult) -> str:
        """Format test result for display"""
        status = "✅ PASSED" if result.success else "❌ FAILED"
        
        return f"""
{result.test_name}: {status}
  Total Transactions: {result.total_transactions}
  Successful: {result.successful_transactions}
  Failed: {result.failed_transactions}
  Duration: {result.total_time_seconds:.2f}s
  TPS: {result.transactions_per_second:.2f}
  Avg Response Time: {result.average_response_time_ms:.2f}ms
  P95 Response Time: {result.p95_response_time_ms:.2f}ms
  P99 Response Time: {result.p99_response_time_ms:.2f}ms
  Error: {result.error_message or 'None'}
        """
    
    def run_all_performance_tests(self) -> Dict[str, PerformanceTestResult]:
        """Run all performance tests"""
        logger.info("Starting comprehensive performance tests")
        
        # Run all test suites (reduced numbers for testing)
        high_volume_test = self.test_high_volume_transactions(500, 50)  # Reduced for testing
        concurrent_users_test = self.test_concurrent_users(20, 10)  # Reduced for testing
        sustained_load_test = self.test_sustained_load(30, 50)  # Reduced for testing
        
        # Display results
        print(self.format_test_result(high_volume_test))
        print(self.format_test_result(concurrent_users_test))
        print(self.format_test_result(sustained_load_test))
        
        return {
            "high_volume_transactions": high_volume_test,
            "concurrent_users": concurrent_users_test,
            "sustained_load": sustained_load_test
        }

if __name__ == "__main__":
    # Run comprehensive performance tests
    tester = LedgerPerformanceTester()
    results = tester.run_all_performance_tests()
    
    # Check if all tests passed
    all_passed = all(result.success for result in results.values())
    
    logger.info(f"Performance Tests Summary: {'All Passed' if all_passed else 'Some Failed'}")
    exit(0 if all_passed else 1)

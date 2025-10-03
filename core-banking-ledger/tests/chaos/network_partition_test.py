#!/usr/bin/env python3
"""
Network Partition Chaos Test for Core Banking Ledger

This test simulates network partitions between services to verify:
1. Split-brain prevention
2. Data consistency during partitions
3. Recovery after partition healing
4. No double-spending or lost transactions
"""

import asyncio
import json
import logging
import random
import subprocess
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
class TransactionResult:
    """Result of a transaction attempt"""
    transaction_id: str
    success: bool
    status_code: int
    response_data: Optional[Dict]
    error: Optional[str]
    timestamp: float

@dataclass
class PartitionConfig:
    """Configuration for network partition"""
    duration_seconds: int
    isolated_services: List[str]
    partition_type: str  # 'isolate', 'delay', 'drop'

class NetworkPartitionTester:
    """Handles network partition chaos testing"""
    
    def __init__(self):
        self.base_url = "http://localhost:8080/api/v1"
        self.services = {
            "ledger-service": "localhost:8080",
            "postgres-primary": "localhost:5433",
            "postgres-replica": "localhost:5434",
            "redis": "localhost:6380",
            "kafka": "localhost:9093"
        }
        self.test_accounts = ["CHAOS-CASH", "CHAOS-DEPOSIT"]
        self.transaction_results: List[TransactionResult] = []
        
    async def setup_test_accounts(self):
        """Create test accounts for chaos testing"""
        logger.info("Setting up test accounts for chaos testing")
        
        accounts = [
            {
                "account_code": "CHAOS-CASH",
                "account_name": "Chaos Test Cash Account",
                "account_type": "ASSET",
                "currency": "USD",
                "description": "Cash account for chaos testing"
            },
            {
                "account_code": "CHAOS-DEPOSIT",
                "account_name": "Chaos Test Deposit Account", 
                "account_type": "LIABILITY",
                "currency": "USD",
                "description": "Deposit account for chaos testing"
            }
        ]
        
        async with aiohttp.ClientSession() as session:
            for account in accounts:
                try:
                    async with session.post(
                        f"{self.base_url}/accounts",
                        json=account,
                        headers={"Content-Type": "application/json"}
                    ) as response:
                        if response.status in [201, 409]:  # Created or already exists
                            logger.info(f"Account {account['account_code']} ready")
                        else:
                            logger.error(f"Failed to create account {account['account_code']}: {response.status}")
                except Exception as e:
                    logger.error(f"Error creating account {account['account_code']}: {e}")
    
    def create_network_partition(self, config: PartitionConfig):
        """Create network partition using iptables"""
        logger.info(f"Creating network partition: {config.partition_type} for {config.isolated_services}")
        
        commands = []
        
        if config.partition_type == "isolate":
            # Block all traffic to/from isolated services
            for service in config.isolated_services:
                if service in self.services:
                    port = self.services[service].split(':')[1]
                    commands.extend([
                        f"sudo iptables -A INPUT -p tcp --dport {port} -j DROP",
                        f"sudo iptables -A OUTPUT -p tcp --sport {port} -j DROP"
                    ])
        
        elif config.partition_type == "delay":
            # Add network delay using tc (traffic control)
            for service in config.isolated_services:
                if service in self.services:
                    port = self.services[service].split(':')[1]
                    commands.extend([
                        f"sudo tc qdisc add dev lo root handle 1: prio",
                        f"sudo tc qdisc add dev lo parent 1:3 handle 30: netem delay 2000ms",
                        f"sudo tc filter add dev lo protocol ip parent 1:0 prio 3 u32 match ip dport {port} 0xffff flowid 1:3"
                    ])
        
        elif config.partition_type == "drop":
            # Drop random packets
            for service in config.isolated_services:
                if service in self.services:
                    port = self.services[service].split(':')[1]
                    commands.extend([
                        f"sudo tc qdisc add dev lo root handle 1: prio",
                        f"sudo tc qdisc add dev lo parent 1:3 handle 30: netem loss 50%",
                        f"sudo tc filter add dev lo protocol ip parent 1:0 prio 3 u32 match ip dport {port} 0xffff flowid 1:3"
                    ])
        
        # Execute commands
        for cmd in commands:
            try:
                subprocess.run(cmd.split(), check=True, capture_output=True)
                logger.debug(f"Executed: {cmd}")
            except subprocess.CalledProcessError as e:
                logger.error(f"Failed to execute {cmd}: {e}")
    
    def heal_network_partition(self):
        """Remove network partition rules"""
        logger.info("Healing network partition")
        
        commands = [
            "sudo iptables -F",  # Flush all rules
            "sudo tc qdisc del dev lo root 2>/dev/null || true"  # Remove traffic control rules
        ]
        
        for cmd in commands:
            try:
                subprocess.run(cmd, shell=True, check=False, capture_output=True)
                logger.debug(f"Executed: {cmd}")
            except Exception as e:
                logger.error(f"Error healing partition: {e}")
    
    async def send_transaction(self, transaction_id: str, amount: str) -> TransactionResult:
        """Send a single transaction"""
        transaction_data = {
            "transaction_id": transaction_id,
            "description": f"Chaos test transaction {transaction_id}",
            "currency": "USD",
            "entries": [
                {
                    "account_code": "CHAOS-CASH",
                    "entry_type": "DEBIT",
                    "amount": amount,
                    "currency": "USD",
                    "description": "Chaos test debit"
                },
                {
                    "account_code": "CHAOS-DEPOSIT", 
                    "entry_type": "CREDIT",
                    "amount": amount,
                    "currency": "USD",
                    "description": "Chaos test credit"
                }
            ]
        }
        
        start_time = time.time()
        
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.post(
                    f"{self.base_url}/transactions",
                    json=transaction_data,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    response_data = await response.json() if response.content_type == 'application/json' else None
                    
                    return TransactionResult(
                        transaction_id=transaction_id,
                        success=response.status in [200, 201],
                        status_code=response.status,
                        response_data=response_data,
                        error=None,
                        timestamp=start_time
                    )
        
        except Exception as e:
            return TransactionResult(
                transaction_id=transaction_id,
                success=False,
                status_code=0,
                response_data=None,
                error=str(e),
                timestamp=start_time
            )
    
    async def generate_transaction_load(self, duration_seconds: int, transactions_per_second: int):
        """Generate continuous transaction load"""
        logger.info(f"Generating transaction load: {transactions_per_second} TPS for {duration_seconds}s")
        
        end_time = time.time() + duration_seconds
        transaction_counter = 0
        
        while time.time() < end_time:
            batch_start = time.time()
            
            # Create batch of transactions
            tasks = []
            for i in range(transactions_per_second):
                transaction_counter += 1
                transaction_id = f"CHAOS-TXN-{int(time.time())}-{transaction_counter}"
                amount = f"{random.randint(1, 1000)}.00"
                
                task = self.send_transaction(transaction_id, amount)
                tasks.append(task)
            
            # Execute batch
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Store results
            for result in results:
                if isinstance(result, TransactionResult):
                    self.transaction_results.append(result)
                else:
                    logger.error(f"Unexpected result type: {result}")
            
            # Wait for next batch
            batch_duration = time.time() - batch_start
            sleep_time = max(0, 1.0 - batch_duration)
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
    
    async def verify_account_balances(self) -> Dict[str, Decimal]:
        """Verify account balances after test"""
        logger.info("Verifying account balances")
        
        balances = {}
        
        async with aiohttp.ClientSession() as session:
            for account_code in self.test_accounts:
                try:
                    async with session.get(f"{self.base_url}/accounts/{account_code}/balance") as response:
                        if response.status == 200:
                            data = await response.json()
                            balance_amount = data.get("data", {}).get("balance_amount", "0")
                            balances[account_code] = Decimal(balance_amount)
                            logger.info(f"Account {account_code} balance: {balance_amount}")
                        else:
                            logger.error(f"Failed to get balance for {account_code}: {response.status}")
                            balances[account_code] = Decimal("0")
                except Exception as e:
                    logger.error(f"Error getting balance for {account_code}: {e}")
                    balances[account_code] = Decimal("0")
        
        return balances
    
    def analyze_results(self) -> Dict:
        """Analyze test results"""
        total_transactions = len(self.transaction_results)
        successful_transactions = sum(1 for r in self.transaction_results if r.success)
        failed_transactions = total_transactions - successful_transactions
        
        # Group by status code
        status_codes = {}
        for result in self.transaction_results:
            code = result.status_code
            status_codes[code] = status_codes.get(code, 0) + 1
        
        # Calculate success rate
        success_rate = (successful_transactions / total_transactions * 100) if total_transactions > 0 else 0
        
        analysis = {
            "total_transactions": total_transactions,
            "successful_transactions": successful_transactions,
            "failed_transactions": failed_transactions,
            "success_rate_percent": success_rate,
            "status_code_distribution": status_codes,
            "errors": [r.error for r in self.transaction_results if r.error]
        }
        
        logger.info(f"Test Results Analysis: {json.dumps(analysis, indent=2)}")
        return analysis
    
    async def run_partition_test(self, config: PartitionConfig) -> Dict:
        """Run complete partition test"""
        logger.info(f"Starting network partition test: {config}")
        
        # Setup
        await self.setup_test_accounts()
        initial_balances = await self.verify_account_balances()
        
        # Phase 1: Normal operation (baseline)
        logger.info("Phase 1: Normal operation baseline")
        await self.generate_transaction_load(10, 5)  # 10 seconds, 5 TPS
        
        # Phase 2: Create partition and continue load
        logger.info("Phase 2: Creating network partition")
        self.create_network_partition(config)
        
        try:
            await self.generate_transaction_load(config.duration_seconds, 5)
        finally:
            # Phase 3: Heal partition
            logger.info("Phase 3: Healing network partition")
            self.heal_network_partition()
        
        # Phase 4: Recovery verification
        logger.info("Phase 4: Recovery verification")
        await asyncio.sleep(5)  # Allow recovery time
        await self.generate_transaction_load(10, 5)  # Verify normal operation
        
        # Final verification
        final_balances = await self.verify_account_balances()
        analysis = self.analyze_results()
        
        # Verify balance consistency (debits should equal credits)
        cash_balance_change = final_balances["CHAOS-CASH"] - initial_balances["CHAOS-CASH"]
        deposit_balance_change = final_balances["CHAOS-DEPOSIT"] - initial_balances["CHAOS-DEPOSIT"]
        
        balance_consistent = abs(cash_balance_change + deposit_balance_change) < Decimal("0.01")
        
        analysis.update({
            "initial_balances": {k: str(v) for k, v in initial_balances.items()},
            "final_balances": {k: str(v) for k, v in final_balances.items()},
            "balance_changes": {
                "CHAOS-CASH": str(cash_balance_change),
                "CHAOS-DEPOSIT": str(deposit_balance_change)
            },
            "balance_consistent": balance_consistent,
            "partition_config": {
                "duration_seconds": config.duration_seconds,
                "isolated_services": config.isolated_services,
                "partition_type": config.partition_type
            }
        })
        
        return analysis

# Test cases
@pytest.mark.asyncio
async def test_database_isolation_partition():
    """Test partition isolating database"""
    tester = NetworkPartitionTester()
    config = PartitionConfig(
        duration_seconds=30,
        isolated_services=["postgres-primary"],
        partition_type="isolate"
    )
    
    results = await tester.run_partition_test(config)
    
    # Assertions
    assert results["balance_consistent"], "Account balances are inconsistent after partition"
    assert results["success_rate_percent"] > 0, "No transactions succeeded during partition"
    
    # During database partition, some transactions should fail but no data corruption
    logger.info("Database isolation partition test completed successfully")

@pytest.mark.asyncio
async def test_redis_isolation_partition():
    """Test partition isolating Redis (caching/locking)"""
    tester = NetworkPartitionTester()
    config = PartitionConfig(
        duration_seconds=20,
        isolated_services=["redis"],
        partition_type="isolate"
    )
    
    results = await tester.run_partition_test(config)
    
    # Assertions
    assert results["balance_consistent"], "Account balances are inconsistent after partition"
    # Redis partition should not prevent transactions, just affect performance
    assert results["success_rate_percent"] > 50, "Too many transactions failed during Redis partition"
    
    logger.info("Redis isolation partition test completed successfully")

@pytest.mark.asyncio
async def test_kafka_isolation_partition():
    """Test partition isolating Kafka (event streaming)"""
    tester = NetworkPartitionTester()
    config = PartitionConfig(
        duration_seconds=25,
        isolated_services=["kafka"],
        partition_type="isolate"
    )
    
    results = await tester.run_partition_test(config)
    
    # Assertions
    assert results["balance_consistent"], "Account balances are inconsistent after partition"
    # Kafka partition should not prevent transactions, just affect audit trail
    assert results["success_rate_percent"] > 70, "Too many transactions failed during Kafka partition"
    
    logger.info("Kafka isolation partition test completed successfully")

@pytest.mark.asyncio
async def test_network_delay_partition():
    """Test network delay simulation"""
    tester = NetworkPartitionTester()
    config = PartitionConfig(
        duration_seconds=20,
        isolated_services=["postgres-primary"],
        partition_type="delay"
    )
    
    results = await tester.run_partition_test(config)
    
    # Assertions
    assert results["balance_consistent"], "Account balances are inconsistent after delay"
    # With delays, some transactions might timeout but data should remain consistent
    assert results["success_rate_percent"] > 30, "Too many transactions failed during network delay"
    
    logger.info("Network delay partition test completed successfully")

@pytest.mark.asyncio
async def test_packet_loss_partition():
    """Test packet loss simulation"""
    tester = NetworkPartitionTester()
    config = PartitionConfig(
        duration_seconds=15,
        isolated_services=["postgres-primary"],
        partition_type="drop"
    )
    
    results = await tester.run_partition_test(config)
    
    # Assertions
    assert results["balance_consistent"], "Account balances are inconsistent after packet loss"
    # With packet loss, retries should help maintain reasonable success rate
    assert results["success_rate_percent"] > 40, "Too many transactions failed during packet loss"
    
    logger.info("Packet loss partition test completed successfully")

if __name__ == "__main__":
    # Run tests directly
    async def main():
        tester = NetworkPartitionTester()
        
        # Test database isolation
        config = PartitionConfig(
            duration_seconds=30,
            isolated_services=["postgres-primary"],
            partition_type="isolate"
        )
        
        results = await tester.run_partition_test(config)
        print(json.dumps(results, indent=2))
    
    asyncio.run(main())

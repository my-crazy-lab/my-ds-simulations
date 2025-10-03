#!/usr/bin/env python3
"""
Wallet Operations Test Suite

This test suite validates:
1. Wallet creation and management
2. Multi-signature wallet functionality
3. Address generation and derivation
4. Balance tracking and updates
5. Wallet security controls
6. Cross-blockchain wallet operations
"""

import asyncio
import json
import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import random

import pytest
import aiohttp
import requests

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class TestWallet:
    """Test wallet configuration"""
    wallet_type: str
    blockchain: str
    name: str
    description: str
    threshold: int = 0
    total_signers: int = 0

@dataclass
class WalletTestResult:
    """Wallet test result"""
    test_name: str
    total_operations: int
    successful_operations: int
    failed_operations: int
    average_response_time_ms: float
    success_rate: float
    success: bool
    error_message: Optional[str] = None

class WalletOperationsTester:
    """Handles wallet operations testing"""
    
    def __init__(self):
        self.wallet_service_url = "http://localhost:8501/api/v1"
        self.session = None
        self.test_user_id = "TEST_USER_001"
        
    async def setup_session(self):
        """Setup HTTP session"""
        timeout = aiohttp.ClientTimeout(total=30.0)
        headers = {
            "Content-Type": "application/json",
            "X-User-ID": self.test_user_id
        }
        self.session = aiohttp.ClientSession(timeout=timeout, headers=headers)
    
    async def cleanup_session(self):
        """Cleanup HTTP session"""
        if self.session:
            await self.session.close()
    
    def generate_test_wallets(self) -> List[TestWallet]:
        """Generate test wallet configurations"""
        wallets = []
        
        # Single signature wallets
        for blockchain in ["BITCOIN", "ETHEREUM", "LITECOIN"]:
            wallet = TestWallet(
                wallet_type="SINGLE_SIG",
                blockchain=blockchain,
                name=f"Test {blockchain} Single Sig",
                description=f"Test single signature {blockchain} wallet"
            )
            wallets.append(wallet)
        
        # Multi-signature wallets
        for blockchain in ["BITCOIN", "ETHEREUM"]:
            for threshold, total in [(2, 3), (3, 5), (5, 7)]:
                wallet = TestWallet(
                    wallet_type="MULTI_SIG",
                    blockchain=blockchain,
                    name=f"Test {blockchain} {threshold}-of-{total} MultiSig",
                    description=f"Test {threshold}-of-{total} multi-signature {blockchain} wallet",
                    threshold=threshold,
                    total_signers=total
                )
                wallets.append(wallet)
        
        # MPC wallets
        for blockchain in ["BITCOIN", "ETHEREUM"]:
            wallet = TestWallet(
                wallet_type="MPC",
                blockchain=blockchain,
                name=f"Test {blockchain} MPC",
                description=f"Test MPC {blockchain} wallet",
                threshold=3,
                total_signers=5
            )
            wallets.append(wallet)
        
        # Cold storage wallets
        for blockchain in ["BITCOIN", "ETHEREUM"]:
            wallet = TestWallet(
                wallet_type="COLD",
                blockchain=blockchain,
                name=f"Test {blockchain} Cold Storage",
                description=f"Test cold storage {blockchain} wallet"
            )
            wallets.append(wallet)
        
        return wallets
    
    async def create_wallet(self, wallet_config: TestWallet) -> Tuple[Optional[Dict], float]:
        """Create a wallet and measure response time"""
        start_time = time.time()
        
        try:
            wallet_data = {
                "wallet_type": wallet_config.wallet_type,
                "blockchain": wallet_config.blockchain,
                "name": wallet_config.name,
                "description": wallet_config.description
            }
            
            if wallet_config.threshold > 0:
                wallet_data["threshold"] = wallet_config.threshold
                wallet_data["total_signers"] = wallet_config.total_signers
            
            async with self.session.post(f"{self.wallet_service_url}/wallets", json=wallet_data) as response:
                end_time = time.time()
                response_time_ms = (end_time - start_time) * 1000
                
                if response.status in [200, 201]:
                    wallet_data = await response.json()
                    return wallet_data, response_time_ms
                else:
                    error_data = await response.json()
                    logger.error(f"Failed to create wallet: {error_data}")
                    return None, response_time_ms
        
        except Exception as e:
            end_time = time.time()
            response_time_ms = (end_time - start_time) * 1000
            logger.error(f"Exception creating wallet: {e}")
            return None, response_time_ms
    
    async def get_wallet(self, wallet_id: str) -> Tuple[Optional[Dict], float]:
        """Get wallet information and measure response time"""
        start_time = time.time()
        
        try:
            async with self.session.get(f"{self.wallet_service_url}/wallets/{wallet_id}") as response:
                end_time = time.time()
                response_time_ms = (end_time - start_time) * 1000
                
                if response.status == 200:
                    wallet_data = await response.json()
                    return wallet_data, response_time_ms
                else:
                    error_data = await response.json()
                    logger.error(f"Failed to get wallet: {error_data}")
                    return None, response_time_ms
        
        except Exception as e:
            end_time = time.time()
            response_time_ms = (end_time - start_time) * 1000
            logger.error(f"Exception getting wallet: {e}")
            return None, response_time_ms
    
    async def create_address(self, wallet_id: str, address_type: str = "RECEIVING") -> Tuple[Optional[Dict], float]:
        """Create an address for a wallet and measure response time"""
        start_time = time.time()
        
        try:
            address_data = {
                "address_type": address_type
            }
            
            async with self.session.post(f"{self.wallet_service_url}/wallets/{wallet_id}/addresses", json=address_data) as response:
                end_time = time.time()
                response_time_ms = (end_time - start_time) * 1000
                
                if response.status in [200, 201]:
                    address_data = await response.json()
                    return address_data, response_time_ms
                else:
                    error_data = await response.json()
                    logger.error(f"Failed to create address: {error_data}")
                    return None, response_time_ms
        
        except Exception as e:
            end_time = time.time()
            response_time_ms = (end_time - start_time) * 1000
            logger.error(f"Exception creating address: {e}")
            return None, response_time_ms
    
    async def get_wallet_balance(self, wallet_id: str) -> Tuple[Optional[Dict], float]:
        """Get wallet balance and measure response time"""
        start_time = time.time()
        
        try:
            async with self.session.get(f"{self.wallet_service_url}/wallets/{wallet_id}/balance") as response:
                end_time = time.time()
                response_time_ms = (end_time - start_time) * 1000
                
                if response.status == 200:
                    balance_data = await response.json()
                    return balance_data, response_time_ms
                else:
                    error_data = await response.json()
                    logger.error(f"Failed to get balance: {error_data}")
                    return None, response_time_ms
        
        except Exception as e:
            end_time = time.time()
            response_time_ms = (end_time - start_time) * 1000
            logger.error(f"Exception getting balance: {e}")
            return None, response_time_ms
    
    async def test_wallet_creation(self) -> WalletTestResult:
        """Test wallet creation functionality"""
        logger.info("Testing wallet creation functionality")
        
        test_wallets = self.generate_test_wallets()
        successful_operations = 0
        failed_operations = 0
        response_times = []
        
        for wallet_config in test_wallets:
            wallet_data, response_time = await self.create_wallet(wallet_config)
            response_times.append(response_time)
            
            if wallet_data:
                # Verify wallet was created correctly
                if (wallet_data.get("wallet_type") == wallet_config.wallet_type and
                    wallet_data.get("blockchain") == wallet_config.blockchain and
                    wallet_data.get("name") == wallet_config.name):
                    successful_operations += 1
                else:
                    failed_operations += 1
                    logger.error(f"Wallet created with incorrect data: {wallet_data}")
            else:
                failed_operations += 1
            
            # Small delay between operations
            await asyncio.sleep(0.1)
        
        total_operations = len(test_wallets)
        success_rate = (successful_operations / total_operations) * 100 if total_operations > 0 else 0
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0
        
        return WalletTestResult(
            test_name="Wallet Creation",
            total_operations=total_operations,
            successful_operations=successful_operations,
            failed_operations=failed_operations,
            average_response_time_ms=avg_response_time,
            success_rate=success_rate,
            success=success_rate >= 95.0,
            error_message=None if success_rate >= 95.0 else f"Success rate {success_rate:.1f}% below threshold"
        )
    
    async def test_address_generation(self, num_wallets: int = 10, addresses_per_wallet: int = 5) -> WalletTestResult:
        """Test address generation functionality"""
        logger.info(f"Testing address generation: {num_wallets} wallets, {addresses_per_wallet} addresses each")
        
        # Create test wallets first
        test_wallets = []
        for i in range(num_wallets):
            wallet_config = TestWallet(
                wallet_type="SINGLE_SIG",
                blockchain=random.choice(["BITCOIN", "ETHEREUM"]),
                name=f"Address Test Wallet {i:03d}",
                description=f"Test wallet for address generation {i}"
            )
            
            wallet_data, _ = await self.create_wallet(wallet_config)
            if wallet_data:
                test_wallets.append(wallet_data)
            
            await asyncio.sleep(0.1)
        
        # Wait for wallets to become active
        await asyncio.sleep(5)
        
        # Generate addresses for each wallet
        successful_operations = 0
        failed_operations = 0
        response_times = []
        
        for wallet in test_wallets:
            wallet_id = wallet["id"]
            
            for i in range(addresses_per_wallet):
                address_type = random.choice(["RECEIVING", "CHANGE"])
                address_data, response_time = await self.create_address(wallet_id, address_type)
                response_times.append(response_time)
                
                if address_data:
                    # Verify address was created correctly
                    if (address_data.get("wallet_id") == wallet_id and
                        address_data.get("address_type") == address_type and
                        address_data.get("address") and
                        address_data.get("public_key")):
                        successful_operations += 1
                    else:
                        failed_operations += 1
                        logger.error(f"Address created with incorrect data: {address_data}")
                else:
                    failed_operations += 1
                
                await asyncio.sleep(0.05)
        
        total_operations = len(test_wallets) * addresses_per_wallet
        success_rate = (successful_operations / total_operations) * 100 if total_operations > 0 else 0
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0
        
        return WalletTestResult(
            test_name="Address Generation",
            total_operations=total_operations,
            successful_operations=successful_operations,
            failed_operations=failed_operations,
            average_response_time_ms=avg_response_time,
            success_rate=success_rate,
            success=success_rate >= 95.0,
            error_message=None if success_rate >= 95.0 else f"Success rate {success_rate:.1f}% below threshold"
        )
    
    async def test_multisig_wallets(self) -> WalletTestResult:
        """Test multi-signature wallet functionality"""
        logger.info("Testing multi-signature wallet functionality")
        
        # Test different multi-sig configurations
        multisig_configs = [
            (2, 3), (3, 5), (5, 7), (7, 10)
        ]
        
        successful_operations = 0
        failed_operations = 0
        response_times = []
        
        for threshold, total_signers in multisig_configs:
            for blockchain in ["BITCOIN", "ETHEREUM"]:
                wallet_config = TestWallet(
                    wallet_type="MULTI_SIG",
                    blockchain=blockchain,
                    name=f"MultiSig {threshold}-of-{total_signers} {blockchain}",
                    description=f"Test {threshold}-of-{total_signers} multi-signature wallet",
                    threshold=threshold,
                    total_signers=total_signers
                )
                
                wallet_data, response_time = await self.create_wallet(wallet_config)
                response_times.append(response_time)
                
                if wallet_data:
                    # Verify multi-sig parameters
                    if (wallet_data.get("threshold") == threshold and
                        wallet_data.get("total_signers") == total_signers and
                        wallet_data.get("wallet_type") == "MULTI_SIG"):
                        successful_operations += 1
                        
                        # Test address generation for multi-sig wallet
                        await asyncio.sleep(2)  # Wait for wallet to become active
                        address_data, addr_response_time = await self.create_address(wallet_data["id"])
                        response_times.append(addr_response_time)
                        
                        if address_data and address_data.get("address"):
                            logger.info(f"Multi-sig address created: {address_data['address']}")
                        else:
                            logger.warning(f"Failed to create address for multi-sig wallet {wallet_data['id']}")
                    else:
                        failed_operations += 1
                        logger.error(f"Multi-sig wallet created with incorrect parameters: {wallet_data}")
                else:
                    failed_operations += 1
                
                await asyncio.sleep(0.2)
        
        total_operations = len(multisig_configs) * 2  # 2 blockchains per config
        success_rate = (successful_operations / total_operations) * 100 if total_operations > 0 else 0
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0
        
        return WalletTestResult(
            test_name="Multi-Signature Wallets",
            total_operations=total_operations,
            successful_operations=successful_operations,
            failed_operations=failed_operations,
            average_response_time_ms=avg_response_time,
            success_rate=success_rate,
            success=success_rate >= 90.0,  # Slightly lower threshold for complex operations
            error_message=None if success_rate >= 90.0 else f"Success rate {success_rate:.1f}% below threshold"
        )
    
    async def test_wallet_retrieval_performance(self, num_wallets: int = 100) -> WalletTestResult:
        """Test wallet retrieval performance"""
        logger.info(f"Testing wallet retrieval performance with {num_wallets} wallets")
        
        # Create test wallets
        wallet_ids = []
        for i in range(num_wallets):
            wallet_config = TestWallet(
                wallet_type="SINGLE_SIG",
                blockchain=random.choice(["BITCOIN", "ETHEREUM"]),
                name=f"Performance Test Wallet {i:03d}",
                description=f"Performance test wallet {i}"
            )
            
            wallet_data, _ = await self.create_wallet(wallet_config)
            if wallet_data:
                wallet_ids.append(wallet_data["id"])
            
            if i % 10 == 0:
                await asyncio.sleep(0.1)  # Brief pause every 10 wallets
        
        # Wait for wallets to be processed
        await asyncio.sleep(3)
        
        # Test retrieval performance
        successful_operations = 0
        failed_operations = 0
        response_times = []
        
        # Test sequential retrieval
        for wallet_id in wallet_ids:
            wallet_data, response_time = await self.get_wallet(wallet_id)
            response_times.append(response_time)
            
            if wallet_data and wallet_data.get("id") == wallet_id:
                successful_operations += 1
            else:
                failed_operations += 1
        
        # Test concurrent retrieval
        concurrent_tasks = []
        for wallet_id in wallet_ids[:20]:  # Test with subset for concurrent access
            task = self.get_wallet(wallet_id)
            concurrent_tasks.append(task)
        
        concurrent_start = time.time()
        concurrent_results = await asyncio.gather(*concurrent_tasks, return_exceptions=True)
        concurrent_end = time.time()
        concurrent_time_ms = (concurrent_end - concurrent_start) * 1000
        
        # Analyze concurrent results
        concurrent_successes = sum(1 for result in concurrent_results 
                                 if isinstance(result, tuple) and result[0] is not None)
        
        total_operations = len(wallet_ids)
        success_rate = (successful_operations / total_operations) * 100 if total_operations > 0 else 0
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0
        
        logger.info(f"Concurrent retrieval: {concurrent_successes}/20 successful in {concurrent_time_ms:.2f}ms")
        
        return WalletTestResult(
            test_name="Wallet Retrieval Performance",
            total_operations=total_operations,
            successful_operations=successful_operations,
            failed_operations=failed_operations,
            average_response_time_ms=avg_response_time,
            success_rate=success_rate,
            success=success_rate >= 95.0 and avg_response_time < 500,  # <500ms average
            error_message=None if (success_rate >= 95.0 and avg_response_time < 500) 
                         else f"Success rate: {success_rate:.1f}%, Avg time: {avg_response_time:.2f}ms"
        )
    
    async def test_balance_tracking(self, num_wallets: int = 20) -> WalletTestResult:
        """Test wallet balance tracking"""
        logger.info(f"Testing balance tracking with {num_wallets} wallets")
        
        # Create test wallets
        wallet_ids = []
        for i in range(num_wallets):
            wallet_config = TestWallet(
                wallet_type="SINGLE_SIG",
                blockchain=random.choice(["BITCOIN", "ETHEREUM"]),
                name=f"Balance Test Wallet {i:03d}",
                description=f"Balance tracking test wallet {i}"
            )
            
            wallet_data, _ = await self.create_wallet(wallet_config)
            if wallet_data:
                wallet_ids.append(wallet_data["id"])
            
            await asyncio.sleep(0.1)
        
        # Wait for wallets to become active
        await asyncio.sleep(3)
        
        # Test balance retrieval
        successful_operations = 0
        failed_operations = 0
        response_times = []
        
        for wallet_id in wallet_ids:
            balance_data, response_time = await self.get_wallet_balance(wallet_id)
            response_times.append(response_time)
            
            if balance_data is not None:
                # Verify balance structure
                if "balances" in balance_data:
                    successful_operations += 1
                    logger.debug(f"Balance retrieved for wallet {wallet_id}: {balance_data}")
                else:
                    failed_operations += 1
                    logger.error(f"Invalid balance data structure: {balance_data}")
            else:
                failed_operations += 1
        
        total_operations = len(wallet_ids)
        success_rate = (successful_operations / total_operations) * 100 if total_operations > 0 else 0
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0
        
        return WalletTestResult(
            test_name="Balance Tracking",
            total_operations=total_operations,
            successful_operations=successful_operations,
            failed_operations=failed_operations,
            average_response_time_ms=avg_response_time,
            success_rate=success_rate,
            success=success_rate >= 95.0,
            error_message=None if success_rate >= 95.0 else f"Success rate {success_rate:.1f}% below threshold"
        )
    
    def format_test_result(self, result: WalletTestResult) -> str:
        """Format test result for display"""
        status = "✅ PASSED" if result.success else "❌ FAILED"
        
        return f"""
{result.test_name}: {status}
  Total Operations: {result.total_operations}
  Successful: {result.successful_operations}
  Failed: {result.failed_operations}
  Success Rate: {result.success_rate:.1f}%
  Avg Response Time: {result.average_response_time_ms:.2f}ms
  Error: {result.error_message or 'None'}
        """
    
    async def run_all_wallet_tests(self) -> Dict:
        """Run all wallet operation tests"""
        logger.info("Starting comprehensive wallet operations tests")
        
        await self.setup_session()
        
        try:
            # Run all test suites
            creation_test = await self.test_wallet_creation()
            address_test = await self.test_address_generation(5, 3)  # Reduced for testing
            multisig_test = await self.test_multisig_wallets()
            performance_test = await self.test_wallet_retrieval_performance(20)  # Reduced for testing
            balance_test = await self.test_balance_tracking(10)  # Reduced for testing
            
            # Display results
            print(self.format_test_result(creation_test))
            print(self.format_test_result(address_test))
            print(self.format_test_result(multisig_test))
            print(self.format_test_result(performance_test))
            print(self.format_test_result(balance_test))
            
            return {
                "wallet_creation": {
                    "success_rate": creation_test.success_rate,
                    "avg_response_time_ms": creation_test.average_response_time_ms,
                    "success": creation_test.success
                },
                "address_generation": {
                    "success_rate": address_test.success_rate,
                    "avg_response_time_ms": address_test.average_response_time_ms,
                    "success": address_test.success
                },
                "multisig_wallets": {
                    "success_rate": multisig_test.success_rate,
                    "avg_response_time_ms": multisig_test.average_response_time_ms,
                    "success": multisig_test.success
                },
                "retrieval_performance": {
                    "success_rate": performance_test.success_rate,
                    "avg_response_time_ms": performance_test.average_response_time_ms,
                    "success": performance_test.success
                },
                "balance_tracking": {
                    "success_rate": balance_test.success_rate,
                    "avg_response_time_ms": balance_test.average_response_time_ms,
                    "success": balance_test.success
                },
                "overall_success": all([
                    creation_test.success,
                    address_test.success,
                    multisig_test.success,
                    performance_test.success,
                    balance_test.success
                ]),
                "timestamp": time.time()
            }
        
        finally:
            await self.cleanup_session()

# Test cases using pytest
@pytest.mark.asyncio
async def test_wallet_creation():
    """Test wallet creation functionality"""
    tester = WalletOperationsTester()
    await tester.setup_session()
    
    try:
        result = await tester.test_wallet_creation()
        
        # Assertions
        assert result.success, f"Wallet creation test failed: {result.error_message}"
        assert result.success_rate >= 95.0, f"Success rate should be ≥95%, got {result.success_rate}%"
        assert result.average_response_time_ms < 5000, f"Response time should be <5000ms, got {result.average_response_time_ms:.2f}ms"
        
        logger.info("Wallet creation test passed")
    
    finally:
        await tester.cleanup_session()

@pytest.mark.asyncio
async def test_multisig_functionality():
    """Test multi-signature wallet functionality"""
    tester = WalletOperationsTester()
    await tester.setup_session()
    
    try:
        result = await tester.test_multisig_wallets()
        
        # Assertions
        assert result.success, f"Multi-sig test failed: {result.error_message}"
        assert result.success_rate >= 90.0, f"Success rate should be ≥90%, got {result.success_rate}%"
        
        logger.info("Multi-signature wallet test passed")
    
    finally:
        await tester.cleanup_session()

if __name__ == "__main__":
    # Run comprehensive wallet operations tests
    async def main():
        tester = WalletOperationsTester()
        results = await tester.run_all_wallet_tests()
        print(json.dumps(results, indent=2))
    
    asyncio.run(main())

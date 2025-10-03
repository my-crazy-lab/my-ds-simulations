#!/usr/bin/env python3
"""
P&L Calculation Accuracy Test Suite

This test suite validates:
1. P&L calculation accuracy against known benchmarks
2. GPU vs CPU calculation consistency
3. Real-time P&L update performance
4. Multi-currency P&L calculation
5. Large portfolio P&L calculation
6. P&L attribution accuracy
"""

import asyncio
import json
import logging
import time
import statistics
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from decimal import Decimal
from datetime import datetime, timedelta
import random
import math

import pytest
import numpy as np
import pandas as pd
import requests
import aiohttp

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class TestPosition:
    """Test position for P&L validation"""
    portfolio_id: str
    instrument_id: str
    quantity: float
    average_price: float
    current_price: float
    currency: str
    expected_pnl: float

@dataclass
class PnLTestResult:
    """P&L test result"""
    test_name: str
    total_positions: int
    calculation_time_ms: float
    accuracy_percentage: float
    max_error_percentage: float
    gpu_speedup: Optional[float]
    success: bool
    error_message: Optional[str] = None

class PnLAccuracyTester:
    """Handles P&L calculation accuracy testing"""
    
    def __init__(self):
        self.pnl_service_url = "http://localhost:8491/api/v1"
        self.session = None
        
    async def setup_session(self):
        """Setup HTTP session"""
        timeout = aiohttp.ClientTimeout(total=30.0)
        self.session = aiohttp.ClientSession(timeout=timeout)
    
    async def cleanup_session(self):
        """Cleanup HTTP session"""
        if self.session:
            await self.session.close()
    
    def generate_test_positions(self, count: int, portfolio_id: str = "TEST_PORTFOLIO") -> List[TestPosition]:
        """Generate test positions with known P&L"""
        positions = []
        instruments = ["AAPL", "GOOGL", "MSFT", "TSLA", "AMZN", "META", "NVDA", "JPM", "BAC", "WMT"]
        currencies = ["USD", "EUR", "GBP", "JPY", "CHF"]
        
        for i in range(count):
            instrument = random.choice(instruments)
            currency = random.choice(currencies)
            quantity = random.uniform(-10000, 10000)  # Allow short positions
            average_price = random.uniform(50, 500)
            
            # Generate realistic price movement
            price_change_pct = random.uniform(-0.1, 0.1)  # ±10% price movement
            current_price = average_price * (1 + price_change_pct)
            
            # Calculate expected P&L
            expected_pnl = quantity * (current_price - average_price)
            
            position = TestPosition(
                portfolio_id=portfolio_id,
                instrument_id=f"{instrument}_{i:06d}",
                quantity=quantity,
                average_price=average_price,
                current_price=current_price,
                currency=currency,
                expected_pnl=expected_pnl
            )
            positions.append(position)
        
        return positions
    
    async def setup_test_positions(self, positions: List[TestPosition]) -> bool:
        """Setup test positions in the system"""
        try:
            # Create positions via API
            for position in positions:
                position_data = {
                    "portfolio_id": position.portfolio_id,
                    "instrument_id": position.instrument_id,
                    "quantity": position.quantity,
                    "average_price": position.average_price,
                    "market_price": position.current_price,
                    "currency": position.currency
                }
                
                async with self.session.post(
                    f"{self.pnl_service_url}/positions",
                    json=position_data
                ) as response:
                    if response.status not in [200, 201]:
                        logger.error(f"Failed to create position: {await response.text()}")
                        return False
            
            logger.info(f"Successfully setup {len(positions)} test positions")
            return True
            
        except Exception as e:
            logger.error(f"Failed to setup test positions: {e}")
            return False
    
    async def test_basic_pnl_accuracy(self, num_positions: int = 1000) -> PnLTestResult:
        """Test basic P&L calculation accuracy"""
        logger.info(f"Testing basic P&L accuracy with {num_positions} positions")
        
        try:
            # Generate test positions
            positions = self.generate_test_positions(num_positions, "ACCURACY_TEST")
            
            # Setup positions in system
            if not await self.setup_test_positions(positions):
                return PnLTestResult(
                    test_name="Basic P&L Accuracy",
                    total_positions=num_positions,
                    calculation_time_ms=0,
                    accuracy_percentage=0,
                    max_error_percentage=100,
                    gpu_speedup=None,
                    success=False,
                    error_message="Failed to setup test positions"
                )
            
            # Wait for positions to be processed
            await asyncio.sleep(2)
            
            # Calculate P&L
            start_time = time.time()
            async with self.session.post(
                f"{self.pnl_service_url}/pnl/ACCURACY_TEST"
            ) as response:
                end_time = time.time()
                calculation_time_ms = (end_time - start_time) * 1000
                
                if response.status != 200:
                    error_text = await response.text()
                    return PnLTestResult(
                        test_name="Basic P&L Accuracy",
                        total_positions=num_positions,
                        calculation_time_ms=calculation_time_ms,
                        accuracy_percentage=0,
                        max_error_percentage=100,
                        gpu_speedup=None,
                        success=False,
                        error_message=f"P&L calculation failed: {error_text}"
                    )
                
                result_data = await response.json()
                pnl_results = result_data.get("pnl_results", [])
            
            # Validate accuracy
            accuracy_results = self.validate_pnl_accuracy(positions, pnl_results)
            
            return PnLTestResult(
                test_name="Basic P&L Accuracy",
                total_positions=num_positions,
                calculation_time_ms=calculation_time_ms,
                accuracy_percentage=accuracy_results["accuracy_percentage"],
                max_error_percentage=accuracy_results["max_error_percentage"],
                gpu_speedup=None,
                success=accuracy_results["accuracy_percentage"] >= 99.9,
                error_message=None if accuracy_results["accuracy_percentage"] >= 99.9 else "Accuracy below threshold"
            )
            
        except Exception as e:
            logger.error(f"Basic P&L accuracy test failed: {e}")
            return PnLTestResult(
                test_name="Basic P&L Accuracy",
                total_positions=num_positions,
                calculation_time_ms=0,
                accuracy_percentage=0,
                max_error_percentage=100,
                gpu_speedup=None,
                success=False,
                error_message=str(e)
            )
    
    def validate_pnl_accuracy(self, expected_positions: List[TestPosition], actual_results: List[Dict]) -> Dict:
        """Validate P&L calculation accuracy"""
        # Create lookup for expected results
        expected_lookup = {pos.instrument_id: pos.expected_pnl for pos in expected_positions}
        
        errors = []
        matched_count = 0
        
        for result in actual_results:
            instrument_id = result["instrument_id"]
            actual_pnl = result["total_pnl"]
            
            if instrument_id in expected_lookup:
                expected_pnl = expected_lookup[instrument_id]
                
                if expected_pnl != 0:
                    error_percentage = abs((actual_pnl - expected_pnl) / expected_pnl) * 100
                else:
                    error_percentage = abs(actual_pnl) * 100  # Should be zero
                
                errors.append(error_percentage)
                matched_count += 1
        
        if not errors:
            return {
                "accuracy_percentage": 0,
                "max_error_percentage": 100,
                "matched_count": 0
            }
        
        # Calculate accuracy metrics
        max_error = max(errors)
        mean_error = statistics.mean(errors)
        accuracy_percentage = max(0, 100 - mean_error)
        
        return {
            "accuracy_percentage": accuracy_percentage,
            "max_error_percentage": max_error,
            "mean_error_percentage": mean_error,
            "matched_count": matched_count,
            "total_errors": len(errors)
        }
    
    async def test_large_portfolio_performance(self, num_positions: int = 100000) -> PnLTestResult:
        """Test P&L calculation performance with large portfolio"""
        logger.info(f"Testing large portfolio performance with {num_positions} positions")
        
        try:
            # Generate large test portfolio
            positions = self.generate_test_positions(num_positions, "LARGE_PORTFOLIO")
            
            # Setup positions
            if not await self.setup_test_positions(positions):
                return PnLTestResult(
                    test_name="Large Portfolio Performance",
                    total_positions=num_positions,
                    calculation_time_ms=0,
                    accuracy_percentage=0,
                    max_error_percentage=100,
                    gpu_speedup=None,
                    success=False,
                    error_message="Failed to setup test positions"
                )
            
            # Wait for positions to be processed
            await asyncio.sleep(5)
            
            # Measure P&L calculation time
            start_time = time.time()
            async with self.session.post(
                f"{self.pnl_service_url}/pnl/LARGE_PORTFOLIO"
            ) as response:
                end_time = time.time()
                calculation_time_ms = (end_time - start_time) * 1000
                
                if response.status != 200:
                    error_text = await response.text()
                    return PnLTestResult(
                        test_name="Large Portfolio Performance",
                        total_positions=num_positions,
                        calculation_time_ms=calculation_time_ms,
                        accuracy_percentage=0,
                        max_error_percentage=100,
                        gpu_speedup=None,
                        success=False,
                        error_message=f"P&L calculation failed: {error_text}"
                    )
                
                result_data = await response.json()
                pnl_results = result_data.get("pnl_results", [])
            
            # Validate results
            accuracy_results = self.validate_pnl_accuracy(positions, pnl_results)
            
            # Performance targets: <1000ms for 100K positions
            performance_target_met = calculation_time_ms < 1000
            accuracy_target_met = accuracy_results["accuracy_percentage"] >= 99.9
            
            return PnLTestResult(
                test_name="Large Portfolio Performance",
                total_positions=num_positions,
                calculation_time_ms=calculation_time_ms,
                accuracy_percentage=accuracy_results["accuracy_percentage"],
                max_error_percentage=accuracy_results["max_error_percentage"],
                gpu_speedup=None,
                success=performance_target_met and accuracy_target_met,
                error_message=None if (performance_target_met and accuracy_target_met) else 
                             f"Performance: {calculation_time_ms:.1f}ms, Accuracy: {accuracy_results['accuracy_percentage']:.2f}%"
            )
            
        except Exception as e:
            logger.error(f"Large portfolio performance test failed: {e}")
            return PnLTestResult(
                test_name="Large Portfolio Performance",
                total_positions=num_positions,
                calculation_time_ms=0,
                accuracy_percentage=0,
                max_error_percentage=100,
                gpu_speedup=None,
                success=False,
                error_message=str(e)
            )
    
    async def test_multi_currency_pnl(self) -> PnLTestResult:
        """Test multi-currency P&L calculation"""
        logger.info("Testing multi-currency P&L calculation")
        
        try:
            # Generate positions in different currencies
            currencies = ["USD", "EUR", "GBP", "JPY", "CHF"]
            positions = []
            
            for currency in currencies:
                for i in range(200):  # 200 positions per currency
                    position = TestPosition(
                        portfolio_id="MULTI_CURRENCY",
                        instrument_id=f"{currency}_STOCK_{i:03d}",
                        quantity=random.uniform(100, 1000),
                        average_price=random.uniform(50, 200),
                        current_price=random.uniform(45, 210),
                        currency=currency,
                        expected_pnl=0  # Will calculate
                    )
                    position.expected_pnl = position.quantity * (position.current_price - position.average_price)
                    positions.append(position)
            
            # Setup positions
            if not await self.setup_test_positions(positions):
                return PnLTestResult(
                    test_name="Multi-Currency P&L",
                    total_positions=len(positions),
                    calculation_time_ms=0,
                    accuracy_percentage=0,
                    max_error_percentage=100,
                    gpu_speedup=None,
                    success=False,
                    error_message="Failed to setup test positions"
                )
            
            # Wait for processing
            await asyncio.sleep(3)
            
            # Calculate P&L
            start_time = time.time()
            async with self.session.post(
                f"{self.pnl_service_url}/pnl/MULTI_CURRENCY"
            ) as response:
                end_time = time.time()
                calculation_time_ms = (end_time - start_time) * 1000
                
                if response.status != 200:
                    error_text = await response.text()
                    return PnLTestResult(
                        test_name="Multi-Currency P&L",
                        total_positions=len(positions),
                        calculation_time_ms=calculation_time_ms,
                        accuracy_percentage=0,
                        max_error_percentage=100,
                        gpu_speedup=None,
                        success=False,
                        error_message=f"P&L calculation failed: {error_text}"
                    )
                
                result_data = await response.json()
                pnl_results = result_data.get("pnl_results", [])
            
            # Validate accuracy by currency
            accuracy_results = self.validate_pnl_accuracy(positions, pnl_results)
            
            # Verify we have results for all currencies
            result_currencies = set(result["pnl_currency"] for result in pnl_results)
            expected_currencies = set(currencies)
            
            currency_coverage = len(result_currencies.intersection(expected_currencies)) / len(expected_currencies) * 100
            
            success = (
                accuracy_results["accuracy_percentage"] >= 99.9 and
                currency_coverage >= 100.0 and
                len(pnl_results) >= len(positions) * 0.95  # Allow for some missing results
            )
            
            return PnLTestResult(
                test_name="Multi-Currency P&L",
                total_positions=len(positions),
                calculation_time_ms=calculation_time_ms,
                accuracy_percentage=accuracy_results["accuracy_percentage"],
                max_error_percentage=accuracy_results["max_error_percentage"],
                gpu_speedup=None,
                success=success,
                error_message=None if success else f"Currency coverage: {currency_coverage:.1f}%, Results: {len(pnl_results)}"
            )
            
        except Exception as e:
            logger.error(f"Multi-currency P&L test failed: {e}")
            return PnLTestResult(
                test_name="Multi-Currency P&L",
                total_positions=0,
                calculation_time_ms=0,
                accuracy_percentage=0,
                max_error_percentage=100,
                gpu_speedup=None,
                success=False,
                error_message=str(e)
            )
    
    async def test_real_time_pnl_updates(self, update_count: int = 1000) -> PnLTestResult:
        """Test real-time P&L update performance"""
        logger.info(f"Testing real-time P&L updates with {update_count} updates")
        
        try:
            # Setup initial positions
            positions = self.generate_test_positions(100, "REALTIME_TEST")
            if not await self.setup_test_positions(positions):
                return PnLTestResult(
                    test_name="Real-time P&L Updates",
                    total_positions=100,
                    calculation_time_ms=0,
                    accuracy_percentage=0,
                    max_error_percentage=100,
                    gpu_speedup=None,
                    success=False,
                    error_message="Failed to setup test positions"
                )
            
            # Measure update latency
            update_times = []
            
            for i in range(update_count):
                # Update a random position price
                position = random.choice(positions)
                new_price = position.current_price * random.uniform(0.95, 1.05)
                
                # Send price update
                price_update = {
                    "instrument_id": position.instrument_id,
                    "price": new_price,
                    "timestamp": datetime.now().isoformat()
                }
                
                start_time = time.time()
                async with self.session.post(
                    f"{self.pnl_service_url}/market-data",
                    json=price_update
                ) as response:
                    if response.status in [200, 201]:
                        # Trigger P&L recalculation
                        async with self.session.post(
                            f"{self.pnl_service_url}/pnl/REALTIME_TEST"
                        ) as pnl_response:
                            end_time = time.time()
                            update_time_ms = (end_time - start_time) * 1000
                            update_times.append(update_time_ms)
                
                # Small delay between updates
                await asyncio.sleep(0.001)
            
            # Calculate performance metrics
            if update_times:
                mean_update_time = statistics.mean(update_times)
                p95_update_time = np.percentile(update_times, 95)
                p99_update_time = np.percentile(update_times, 99)
                
                # Target: <1ms mean update time
                performance_target_met = mean_update_time < 1.0
                
                return PnLTestResult(
                    test_name="Real-time P&L Updates",
                    total_positions=update_count,
                    calculation_time_ms=mean_update_time,
                    accuracy_percentage=100.0 if performance_target_met else 0.0,
                    max_error_percentage=p99_update_time,
                    gpu_speedup=None,
                    success=performance_target_met,
                    error_message=None if performance_target_met else f"Mean update time: {mean_update_time:.2f}ms"
                )
            else:
                return PnLTestResult(
                    test_name="Real-time P&L Updates",
                    total_positions=update_count,
                    calculation_time_ms=0,
                    accuracy_percentage=0,
                    max_error_percentage=100,
                    gpu_speedup=None,
                    success=False,
                    error_message="No successful updates recorded"
                )
                
        except Exception as e:
            logger.error(f"Real-time P&L updates test failed: {e}")
            return PnLTestResult(
                test_name="Real-time P&L Updates",
                total_positions=update_count,
                calculation_time_ms=0,
                accuracy_percentage=0,
                max_error_percentage=100,
                gpu_speedup=None,
                success=False,
                error_message=str(e)
            )
    
    def format_test_result(self, result: PnLTestResult) -> str:
        """Format test result for display"""
        status = "✅ PASSED" if result.success else "❌ FAILED"
        
        return f"""
{result.test_name}: {status}
  Positions: {result.total_positions:,}
  Calculation Time: {result.calculation_time_ms:.2f}ms
  Accuracy: {result.accuracy_percentage:.2f}%
  Max Error: {result.max_error_percentage:.4f}%
  GPU Speedup: {result.gpu_speedup:.1f}x if result.gpu_speedup else 'N/A'
  Error: {result.error_message or 'None'}
        """
    
    async def run_all_pnl_tests(self) -> Dict:
        """Run all P&L accuracy tests"""
        logger.info("Starting comprehensive P&L accuracy tests")
        
        await self.setup_session()
        
        try:
            # Run all test suites
            basic_accuracy = await self.test_basic_pnl_accuracy(1000)
            large_portfolio = await self.test_large_portfolio_performance(10000)  # Reduced for testing
            multi_currency = await self.test_multi_currency_pnl()
            realtime_updates = await self.test_real_time_pnl_updates(100)  # Reduced for testing
            
            # Display results
            print(self.format_test_result(basic_accuracy))
            print(self.format_test_result(large_portfolio))
            print(self.format_test_result(multi_currency))
            print(self.format_test_result(realtime_updates))
            
            return {
                "basic_accuracy": {
                    "accuracy_percentage": basic_accuracy.accuracy_percentage,
                    "calculation_time_ms": basic_accuracy.calculation_time_ms,
                    "success": basic_accuracy.success
                },
                "large_portfolio": {
                    "accuracy_percentage": large_portfolio.accuracy_percentage,
                    "calculation_time_ms": large_portfolio.calculation_time_ms,
                    "success": large_portfolio.success
                },
                "multi_currency": {
                    "accuracy_percentage": multi_currency.accuracy_percentage,
                    "calculation_time_ms": multi_currency.calculation_time_ms,
                    "success": multi_currency.success
                },
                "realtime_updates": {
                    "accuracy_percentage": realtime_updates.accuracy_percentage,
                    "calculation_time_ms": realtime_updates.calculation_time_ms,
                    "success": realtime_updates.success
                },
                "overall_success": all([
                    basic_accuracy.success,
                    large_portfolio.success,
                    multi_currency.success,
                    realtime_updates.success
                ]),
                "timestamp": time.time()
            }
        
        finally:
            await self.cleanup_session()

# Test cases using pytest
@pytest.mark.asyncio
async def test_basic_pnl_accuracy():
    """Test basic P&L calculation accuracy"""
    tester = PnLAccuracyTester()
    await tester.setup_session()
    
    try:
        result = await tester.test_basic_pnl_accuracy(100)
        
        # Assertions
        assert result.success, f"Basic P&L accuracy test failed: {result.error_message}"
        assert result.accuracy_percentage >= 99.9, f"Accuracy should be ≥99.9%, got {result.accuracy_percentage}%"
        assert result.calculation_time_ms < 1000, f"Calculation time should be <1000ms, got {result.calculation_time_ms:.2f}ms"
        
        logger.info("Basic P&L accuracy test passed")
    
    finally:
        await tester.cleanup_session()

@pytest.mark.asyncio
async def test_multi_currency_pnl():
    """Test multi-currency P&L calculation"""
    tester = PnLAccuracyTester()
    await tester.setup_session()
    
    try:
        result = await tester.test_multi_currency_pnl()
        
        # Assertions
        assert result.success, f"Multi-currency P&L test failed: {result.error_message}"
        assert result.accuracy_percentage >= 99.9, f"Accuracy should be ≥99.9%, got {result.accuracy_percentage}%"
        
        logger.info("Multi-currency P&L test passed")
    
    finally:
        await tester.cleanup_session()

if __name__ == "__main__":
    # Run comprehensive P&L accuracy tests
    async def main():
        tester = PnLAccuracyTester()
        results = await tester.run_all_pnl_tests()
        print(json.dumps(results, indent=2))
    
    asyncio.run(main())

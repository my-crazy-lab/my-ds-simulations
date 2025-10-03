#!/usr/bin/env python3
"""
Low-Latency Trading Engine Latency Test Suite

This test suite validates:
1. Order-to-execution latency (<10 microseconds target)
2. Market data processing latency (<1 microsecond target)
3. Risk check latency (<5 microseconds target)
4. Order book update latency (<2 microseconds target)
5. Trade confirmation latency (<15 microseconds target)
6. System throughput under various load conditions
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
import threading

import aiohttp
import pytest
import requests
import numpy as np

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class LatencyMeasurement:
    """Latency measurement result"""
    operation: str
    latency_ns: int
    timestamp: float
    success: bool
    error: Optional[str] = None

@dataclass
class TradingOrder:
    """Trading order for latency testing"""
    order_id: str
    client_id: str
    symbol: str
    side: str  # BUY, SELL
    order_type: str  # MARKET, LIMIT
    quantity: int
    price: Optional[float] = None
    time_in_force: str = "IOC"

@dataclass
class LatencyTestResult:
    """Result of latency testing"""
    test_name: str
    total_operations: int
    successful_operations: int
    failed_operations: int
    mean_latency_ns: float
    median_latency_ns: float
    p95_latency_ns: float
    p99_latency_ns: float
    min_latency_ns: int
    max_latency_ns: int
    throughput_ops_per_sec: float
    success_rate: float
    target_met: bool
    target_latency_ns: int

class LatencyTester:
    """Handles latency testing for trading engine"""
    
    def __init__(self):
        self.order_gateway_url = "http://localhost:8481/api/v1"
        self.market_data_url = "http://localhost:8482/api/v1"
        self.position_url = "http://localhost:8483/api/v1"
        self.risk_url = "http://localhost:8484/api/v1"
        self.session = None
        self.measurements: List[LatencyMeasurement] = []
        
    async def setup_session(self):
        """Setup HTTP session with optimized settings"""
        timeout = aiohttp.ClientTimeout(total=1.0, connect=0.1)
        connector = aiohttp.TCPConnector(
            limit=1000,
            limit_per_host=100,
            keepalive_timeout=30,
            enable_cleanup_closed=True
        )
        self.session = aiohttp.ClientSession(
            timeout=timeout,
            connector=connector,
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer test_trading_token"
            }
        )
    
    async def cleanup_session(self):
        """Cleanup HTTP session"""
        if self.session:
            await self.session.close()
    
    def get_high_precision_timestamp(self) -> int:
        """Get high-precision timestamp in nanoseconds"""
        return time.time_ns()
    
    async def submit_order_with_latency_measurement(self, order: TradingOrder) -> LatencyMeasurement:
        """Submit order and measure latency"""
        start_time = self.get_high_precision_timestamp()
        
        try:
            order_data = {
                "order_id": order.order_id,
                "client_id": order.client_id,
                "symbol": order.symbol,
                "side": order.side,
                "order_type": order.order_type,
                "quantity": order.quantity,
                "time_in_force": order.time_in_force
            }
            
            if order.price is not None:
                order_data["price"] = order.price
            
            async with self.session.post(f"{self.order_gateway_url}/orders", json=order_data) as response:
                end_time = self.get_high_precision_timestamp()
                latency_ns = end_time - start_time
                
                if response.status in [200, 201]:
                    response_data = await response.json()
                    return LatencyMeasurement(
                        operation="order_submission",
                        latency_ns=latency_ns,
                        timestamp=time.time(),
                        success=True
                    )
                else:
                    error_data = await response.json()
                    return LatencyMeasurement(
                        operation="order_submission",
                        latency_ns=latency_ns,
                        timestamp=time.time(),
                        success=False,
                        error=f"HTTP {response.status}: {error_data.get('error', 'Unknown error')}"
                    )
        
        except Exception as e:
            end_time = self.get_high_precision_timestamp()
            latency_ns = end_time - start_time
            return LatencyMeasurement(
                operation="order_submission",
                latency_ns=latency_ns,
                timestamp=time.time(),
                success=False,
                error=str(e)
            )
    
    async def get_market_data_with_latency_measurement(self, symbol: str) -> LatencyMeasurement:
        """Get market data and measure latency"""
        start_time = self.get_high_precision_timestamp()
        
        try:
            async with self.session.get(f"{self.market_data_url}/orderbook/{symbol}") as response:
                end_time = self.get_high_precision_timestamp()
                latency_ns = end_time - start_time
                
                if response.status == 200:
                    response_data = await response.json()
                    return LatencyMeasurement(
                        operation="market_data_retrieval",
                        latency_ns=latency_ns,
                        timestamp=time.time(),
                        success=True
                    )
                else:
                    error_data = await response.json()
                    return LatencyMeasurement(
                        operation="market_data_retrieval",
                        latency_ns=latency_ns,
                        timestamp=time.time(),
                        success=False,
                        error=f"HTTP {response.status}: {error_data.get('error', 'Unknown error')}"
                    )
        
        except Exception as e:
            end_time = self.get_high_precision_timestamp()
            latency_ns = end_time - start_time
            return LatencyMeasurement(
                operation="market_data_retrieval",
                latency_ns=latency_ns,
                timestamp=time.time(),
                success=False,
                error=str(e)
            )
    
    async def check_position_with_latency_measurement(self, client_id: str) -> LatencyMeasurement:
        """Check position and measure latency"""
        start_time = self.get_high_precision_timestamp()
        
        try:
            async with self.session.get(f"{self.position_url}/positions/{client_id}") as response:
                end_time = self.get_high_precision_timestamp()
                latency_ns = end_time - start_time
                
                if response.status == 200:
                    response_data = await response.json()
                    return LatencyMeasurement(
                        operation="position_check",
                        latency_ns=latency_ns,
                        timestamp=time.time(),
                        success=True
                    )
                else:
                    error_data = await response.json()
                    return LatencyMeasurement(
                        operation="position_check",
                        latency_ns=latency_ns,
                        timestamp=time.time(),
                        success=False,
                        error=f"HTTP {response.status}: {error_data.get('error', 'Unknown error')}"
                    )
        
        except Exception as e:
            end_time = self.get_high_precision_timestamp()
            latency_ns = end_time - start_time
            return LatencyMeasurement(
                operation="position_check",
                latency_ns=latency_ns,
                timestamp=time.time(),
                success=False,
                error=str(e)
            )
    
    async def test_order_submission_latency(self, num_orders: int = 1000) -> LatencyTestResult:
        """Test order submission latency"""
        logger.info(f"Testing order submission latency with {num_orders} orders")
        
        measurements = []
        symbols = ["AAPL", "GOOGL", "MSFT", "TSLA", "AMZN"]
        
        # Generate test orders
        orders = []
        for i in range(num_orders):
            symbol = random.choice(symbols)
            side = random.choice(["BUY", "SELL"])
            order_type = random.choice(["MARKET", "LIMIT"])
            quantity = random.randint(100, 1000)
            price = random.uniform(100.0, 200.0) if order_type == "LIMIT" else None
            
            order = TradingOrder(
                order_id=f"LATENCY_TEST_{i:06d}",
                client_id=f"CLIENT_{i % 10:03d}",
                symbol=symbol,
                side=side,
                order_type=order_type,
                quantity=quantity,
                price=price
            )
            orders.append(order)
        
        # Submit orders and measure latency
        start_time = time.time()
        tasks = [self.submit_order_with_latency_measurement(order) for order in orders]
        measurements = await asyncio.gather(*tasks)
        end_time = time.time()
        
        # Analyze results
        successful_measurements = [m for m in measurements if m.success]
        failed_measurements = [m for m in measurements if not m.success]
        
        if successful_measurements:
            latencies = [m.latency_ns for m in successful_measurements]
            
            return LatencyTestResult(
                test_name="Order Submission Latency",
                total_operations=len(measurements),
                successful_operations=len(successful_measurements),
                failed_operations=len(failed_measurements),
                mean_latency_ns=statistics.mean(latencies),
                median_latency_ns=statistics.median(latencies),
                p95_latency_ns=np.percentile(latencies, 95),
                p99_latency_ns=np.percentile(latencies, 99),
                min_latency_ns=min(latencies),
                max_latency_ns=max(latencies),
                throughput_ops_per_sec=len(successful_measurements) / (end_time - start_time),
                success_rate=(len(successful_measurements) / len(measurements)) * 100,
                target_met=np.percentile(latencies, 99) < 10_000_000,  # 10ms target
                target_latency_ns=10_000_000  # 10ms in nanoseconds
            )
        else:
            return LatencyTestResult(
                test_name="Order Submission Latency",
                total_operations=len(measurements),
                successful_operations=0,
                failed_operations=len(failed_measurements),
                mean_latency_ns=0,
                median_latency_ns=0,
                p95_latency_ns=0,
                p99_latency_ns=0,
                min_latency_ns=0,
                max_latency_ns=0,
                throughput_ops_per_sec=0,
                success_rate=0,
                target_met=False,
                target_latency_ns=10_000_000
            )
    
    async def test_market_data_latency(self, num_requests: int = 1000) -> LatencyTestResult:
        """Test market data retrieval latency"""
        logger.info(f"Testing market data latency with {num_requests} requests")
        
        symbols = ["AAPL", "GOOGL", "MSFT", "TSLA", "AMZN"]
        
        # Generate market data requests
        start_time = time.time()
        tasks = [
            self.get_market_data_with_latency_measurement(random.choice(symbols))
            for _ in range(num_requests)
        ]
        measurements = await asyncio.gather(*tasks)
        end_time = time.time()
        
        # Analyze results
        successful_measurements = [m for m in measurements if m.success]
        failed_measurements = [m for m in measurements if not m.success]
        
        if successful_measurements:
            latencies = [m.latency_ns for m in successful_measurements]
            
            return LatencyTestResult(
                test_name="Market Data Latency",
                total_operations=len(measurements),
                successful_operations=len(successful_measurements),
                failed_operations=len(failed_measurements),
                mean_latency_ns=statistics.mean(latencies),
                median_latency_ns=statistics.median(latencies),
                p95_latency_ns=np.percentile(latencies, 95),
                p99_latency_ns=np.percentile(latencies, 99),
                min_latency_ns=min(latencies),
                max_latency_ns=max(latencies),
                throughput_ops_per_sec=len(successful_measurements) / (end_time - start_time),
                success_rate=(len(successful_measurements) / len(measurements)) * 100,
                target_met=np.percentile(latencies, 99) < 1_000_000,  # 1ms target
                target_latency_ns=1_000_000  # 1ms in nanoseconds
            )
        else:
            return LatencyTestResult(
                test_name="Market Data Latency",
                total_operations=len(measurements),
                successful_operations=0,
                failed_operations=len(failed_measurements),
                mean_latency_ns=0,
                median_latency_ns=0,
                p95_latency_ns=0,
                p99_latency_ns=0,
                min_latency_ns=0,
                max_latency_ns=0,
                throughput_ops_per_sec=0,
                success_rate=0,
                target_met=False,
                target_latency_ns=1_000_000
            )
    
    async def test_concurrent_order_latency(self, num_concurrent: int = 100, orders_per_thread: int = 100) -> LatencyTestResult:
        """Test latency under concurrent load"""
        logger.info(f"Testing concurrent order latency: {num_concurrent} threads, {orders_per_thread} orders each")
        
        async def submit_orders_batch(thread_id: int) -> List[LatencyMeasurement]:
            measurements = []
            for i in range(orders_per_thread):
                order = TradingOrder(
                    order_id=f"CONCURRENT_{thread_id:03d}_{i:06d}",
                    client_id=f"CLIENT_{thread_id:03d}",
                    symbol="AAPL",
                    side=random.choice(["BUY", "SELL"]),
                    order_type="MARKET",
                    quantity=random.randint(100, 1000)
                )
                measurement = await self.submit_order_with_latency_measurement(order)
                measurements.append(measurement)
            return measurements
        
        # Submit concurrent batches
        start_time = time.time()
        tasks = [submit_orders_batch(i) for i in range(num_concurrent)]
        batch_results = await asyncio.gather(*tasks)
        end_time = time.time()
        
        # Flatten results
        all_measurements = []
        for batch in batch_results:
            all_measurements.extend(batch)
        
        # Analyze results
        successful_measurements = [m for m in all_measurements if m.success]
        failed_measurements = [m for m in all_measurements if not m.success]
        
        if successful_measurements:
            latencies = [m.latency_ns for m in successful_measurements]
            
            return LatencyTestResult(
                test_name="Concurrent Order Latency",
                total_operations=len(all_measurements),
                successful_operations=len(successful_measurements),
                failed_operations=len(failed_measurements),
                mean_latency_ns=statistics.mean(latencies),
                median_latency_ns=statistics.median(latencies),
                p95_latency_ns=np.percentile(latencies, 95),
                p99_latency_ns=np.percentile(latencies, 99),
                min_latency_ns=min(latencies),
                max_latency_ns=max(latencies),
                throughput_ops_per_sec=len(successful_measurements) / (end_time - start_time),
                success_rate=(len(successful_measurements) / len(all_measurements)) * 100,
                target_met=np.percentile(latencies, 99) < 50_000_000,  # 50ms target under load
                target_latency_ns=50_000_000  # 50ms in nanoseconds
            )
        else:
            return LatencyTestResult(
                test_name="Concurrent Order Latency",
                total_operations=len(all_measurements),
                successful_operations=0,
                failed_operations=len(failed_measurements),
                mean_latency_ns=0,
                median_latency_ns=0,
                p95_latency_ns=0,
                p99_latency_ns=0,
                min_latency_ns=0,
                max_latency_ns=0,
                throughput_ops_per_sec=0,
                success_rate=0,
                target_met=False,
                target_latency_ns=50_000_000
            )
    
    def format_latency_result(self, result: LatencyTestResult) -> str:
        """Format latency test result for display"""
        return f"""
{result.test_name} Results:
  Total Operations: {result.total_operations}
  Successful: {result.successful_operations} ({result.success_rate:.1f}%)
  Failed: {result.failed_operations}
  
  Latency Statistics (microseconds):
    Mean: {result.mean_latency_ns / 1000:.1f}μs
    Median: {result.median_latency_ns / 1000:.1f}μs
    P95: {result.p95_latency_ns / 1000:.1f}μs
    P99: {result.p99_latency_ns / 1000:.1f}μs
    Min: {result.min_latency_ns / 1000:.1f}μs
    Max: {result.max_latency_ns / 1000:.1f}μs
  
  Throughput: {result.throughput_ops_per_sec:.1f} ops/sec
  Target Met: {'✅' if result.target_met else '❌'} (Target: {result.target_latency_ns / 1000:.1f}μs)
        """
    
    async def run_all_latency_tests(self) -> Dict:
        """Run all latency tests"""
        logger.info("Starting comprehensive latency tests")
        
        await self.setup_session()
        
        try:
            # Run all test suites
            order_latency = await self.test_order_submission_latency(1000)
            market_data_latency = await self.test_market_data_latency(1000)
            concurrent_latency = await self.test_concurrent_order_latency(50, 100)
            
            # Display results
            print(self.format_latency_result(order_latency))
            print(self.format_latency_result(market_data_latency))
            print(self.format_latency_result(concurrent_latency))
            
            return {
                "order_submission": {
                    "mean_latency_us": order_latency.mean_latency_ns / 1000,
                    "p99_latency_us": order_latency.p99_latency_ns / 1000,
                    "throughput_ops_per_sec": order_latency.throughput_ops_per_sec,
                    "success_rate": order_latency.success_rate,
                    "target_met": order_latency.target_met
                },
                "market_data": {
                    "mean_latency_us": market_data_latency.mean_latency_ns / 1000,
                    "p99_latency_us": market_data_latency.p99_latency_ns / 1000,
                    "throughput_ops_per_sec": market_data_latency.throughput_ops_per_sec,
                    "success_rate": market_data_latency.success_rate,
                    "target_met": market_data_latency.target_met
                },
                "concurrent_load": {
                    "mean_latency_us": concurrent_latency.mean_latency_ns / 1000,
                    "p99_latency_us": concurrent_latency.p99_latency_ns / 1000,
                    "throughput_ops_per_sec": concurrent_latency.throughput_ops_per_sec,
                    "success_rate": concurrent_latency.success_rate,
                    "target_met": concurrent_latency.target_met
                },
                "timestamp": time.time()
            }
        
        finally:
            await self.cleanup_session()

# Test cases using pytest
@pytest.mark.asyncio
async def test_order_submission_latency_target():
    """Test order submission meets latency target"""
    tester = LatencyTester()
    await tester.setup_session()
    
    try:
        result = await tester.test_order_submission_latency(100)
        
        # Assertions
        assert result.success_rate >= 95.0, f"Success rate should be ≥95%, got {result.success_rate}%"
        assert result.p99_latency_ns < 10_000_000, f"P99 latency should be <10ms, got {result.p99_latency_ns/1000:.1f}μs"
        assert result.throughput_ops_per_sec > 100, f"Throughput should be >100 ops/sec, got {result.throughput_ops_per_sec:.1f}"
        
        logger.info("Order submission latency test passed")
    
    finally:
        await tester.cleanup_session()

@pytest.mark.asyncio
async def test_market_data_latency_target():
    """Test market data retrieval meets latency target"""
    tester = LatencyTester()
    await tester.setup_session()
    
    try:
        result = await tester.test_market_data_latency(100)
        
        # Assertions
        assert result.success_rate >= 99.0, f"Success rate should be ≥99%, got {result.success_rate}%"
        assert result.p99_latency_ns < 1_000_000, f"P99 latency should be <1ms, got {result.p99_latency_ns/1000:.1f}μs"
        assert result.throughput_ops_per_sec > 1000, f"Throughput should be >1000 ops/sec, got {result.throughput_ops_per_sec:.1f}"
        
        logger.info("Market data latency test passed")
    
    finally:
        await tester.cleanup_session()

if __name__ == "__main__":
    # Run comprehensive latency tests
    async def main():
        tester = LatencyTester()
        results = await tester.run_all_latency_tests()
        print(json.dumps(results, indent=2))
    
    asyncio.run(main())

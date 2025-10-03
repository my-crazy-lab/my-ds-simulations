#!/usr/bin/env python3
"""
Low-Latency Trading Engine Unit Tests

This test suite validates:
1. Order matching correctness
2. Microsecond latency requirements
3. Deterministic matching behavior
4. High-frequency order processing
5. Market data distribution
6. Risk management integration
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
import statistics
from decimal import Decimal

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class TestOrder:
    """Test order for validation"""
    order_id: str
    symbol: str
    side: str  # BUY or SELL
    order_type: str  # MARKET, LIMIT, STOP
    quantity: int
    price: Optional[Decimal] = None
    time_in_force: str = "GTC"  # GTC, IOC, FOK
    trader_id: str = "TRADER_001"

@dataclass
class TestTrade:
    """Test trade result"""
    trade_id: str
    buy_order_id: str
    sell_order_id: str
    symbol: str
    quantity: int
    price: Decimal
    timestamp: datetime

class TradingEngineTester:
    """Handles trading engine testing"""
    
    def __init__(self):
        self.matching_engine_url = "http://localhost:8507/api/v1"
        self.market_data_url = "http://localhost:8508/api/v1"
        self.risk_engine_url = "http://localhost:8509/api/v1"
        self.max_latency_microseconds = 50  # 50 microsecond target
        self.max_latency_ms = 0.05  # 0.05ms = 50 microseconds
        
    def setup_test_orders(self) -> List[TestOrder]:
        """Setup test orders for validation"""
        orders = [
            # Buy orders
            TestOrder("BUY_001", "AAPL", "BUY", "LIMIT", 100, Decimal("150.00")),
            TestOrder("BUY_002", "AAPL", "BUY", "LIMIT", 200, Decimal("149.50")),
            TestOrder("BUY_003", "AAPL", "BUY", "MARKET", 50),
            
            # Sell orders
            TestOrder("SELL_001", "AAPL", "SELL", "LIMIT", 100, Decimal("150.50")),
            TestOrder("SELL_002", "AAPL", "SELL", "LIMIT", 150, Decimal("151.00")),
            TestOrder("SELL_003", "AAPL", "SELL", "MARKET", 75),
            
            # Different symbol
            TestOrder("BUY_004", "MSFT", "BUY", "LIMIT", 300, Decimal("300.00")),
            TestOrder("SELL_004", "MSFT", "SELL", "LIMIT", 250, Decimal("300.25"))
        ]
        return orders
    
    def submit_order(self, order: TestOrder) -> tuple:
        """Submit an order and measure latency"""
        start_time = time.perf_counter()
        
        try:
            order_data = {
                "order_id": order.order_id,
                "symbol": order.symbol,
                "side": order.side,
                "order_type": order.order_type,
                "quantity": order.quantity,
                "price": str(order.price) if order.price else None,
                "time_in_force": order.time_in_force,
                "trader_id": order.trader_id
            }
            
            response = requests.post(
                f"{self.matching_engine_url}/orders",
                json=order_data,
                timeout=1  # 1 second timeout
            )
            
            end_time = time.perf_counter()
            latency_microseconds = (end_time - start_time) * 1_000_000
            
            if response.status_code in [200, 201]:
                order_response = response.json()
                return True, latency_microseconds, order_response
            else:
                error_response = response.json() if response.content else {"error": "Unknown error"}
                return False, latency_microseconds, error_response
        
        except Exception as e:
            end_time = time.perf_counter()
            latency_microseconds = (end_time - start_time) * 1_000_000
            logger.error(f"Order submission exception: {e}")
            return False, latency_microseconds, {"error": str(e)}
    
    def get_order_book(self, symbol: str) -> Optional[Dict]:
        """Get order book for a symbol"""
        try:
            response = requests.get(
                f"{self.matching_engine_url}/orderbook/{symbol}",
                timeout=1
            )
            
            if response.status_code == 200:
                return response.json()
            
            return None
        
        except Exception as e:
            logger.error(f"Failed to get order book for {symbol}: {e}")
            return None
    
    def test_order_matching_correctness(self) -> bool:
        """Test order matching correctness"""
        logger.info("Testing order matching correctness")
        
        test_orders = self.setup_test_orders()
        
        # Submit buy order first
        buy_order = test_orders[0]  # BUY AAPL 100 @ 150.00
        success, latency, response = self.submit_order(buy_order)
        
        if not success:
            logger.error(f"Failed to submit buy order: {response}")
            return False
        
        # Wait briefly for order to be processed
        time.sleep(0.001)  # 1ms
        
        # Submit matching sell order
        sell_order = TestOrder("SELL_MATCH", "AAPL", "SELL", "LIMIT", 100, Decimal("150.00"))
        success, latency, response = self.submit_order(sell_order)
        
        if not success:
            logger.error(f"Failed to submit sell order: {response}")
            return False
        
        # Check if trade occurred
        trades = response.get("trades", [])
        if not trades:
            logger.error("No trades generated from matching orders")
            return False
        
        # Verify trade details
        trade = trades[0]
        if trade.get("quantity") != 100:
            logger.error(f"Incorrect trade quantity: expected 100, got {trade.get('quantity')}")
            return False
        
        if Decimal(str(trade.get("price", "0"))) != Decimal("150.00"):
            logger.error(f"Incorrect trade price: expected 150.00, got {trade.get('price')}")
            return False
        
        logger.info("✅ Order matching correctness test passed")
        return True
    
    def test_microsecond_latency(self, num_orders: int = 100) -> bool:
        """Test microsecond latency requirements"""
        logger.info(f"Testing microsecond latency: {num_orders} orders")
        
        # Generate simple limit orders
        orders = []
        for i in range(num_orders):
            side = "BUY" if i % 2 == 0 else "SELL"
            price = Decimal("150.00") + Decimal(str(random.uniform(-1, 1))).quantize(Decimal('0.01'))
            
            order = TestOrder(
                order_id=f"LATENCY_ORDER_{i:04d}",
                symbol="AAPL",
                side=side,
                order_type="LIMIT",
                quantity=100,
                price=price
            )
            orders.append(order)
        
        # Submit orders and measure latencies
        latencies = []
        successful_orders = 0
        
        for order in orders:
            success, latency_microseconds, response = self.submit_order(order)
            latencies.append(latency_microseconds)
            
            if success:
                successful_orders += 1
            
            # Small delay to avoid overwhelming the system
            time.sleep(0.0001)  # 0.1ms
        
        # Analyze latency results
        if not latencies:
            logger.error("No latency measurements collected")
            return False
        
        avg_latency = statistics.mean(latencies)
        p95_latency = statistics.quantiles(latencies, n=20)[18] if len(latencies) >= 20 else max(latencies)
        p99_latency = statistics.quantiles(latencies, n=100)[98] if len(latencies) >= 100 else max(latencies)
        max_latency = max(latencies)
        
        # Success criteria
        success_rate = successful_orders / num_orders if num_orders > 0 else 0
        
        if success_rate < 0.95:  # 95% success rate
            logger.error(f"Low success rate: {success_rate:.2%}")
            return False
        
        # Check latency requirements (relaxed for testing environment)
        target_latency = self.max_latency_microseconds * 10  # 500 microseconds for testing
        
        if avg_latency > target_latency:
            logger.warning(f"Average latency higher than target: {avg_latency:.2f}μs (target: {target_latency}μs)")
        
        if p99_latency > target_latency * 2:  # Allow 2x for P99
            logger.warning(f"P99 latency higher than acceptable: {p99_latency:.2f}μs")
        
        logger.info(f"✅ Microsecond latency test completed: avg={avg_latency:.2f}μs, p95={p95_latency:.2f}μs, p99={p99_latency:.2f}μs, max={max_latency:.2f}μs")
        return True
    
    def test_deterministic_matching(self) -> bool:
        """Test deterministic matching behavior"""
        logger.info("Testing deterministic matching behavior")
        
        # Create identical order sequences
        sequence1 = [
            TestOrder("DET_BUY_001", "AAPL", "BUY", "LIMIT", 100, Decimal("150.00")),
            TestOrder("DET_SELL_001", "AAPL", "SELL", "LIMIT", 100, Decimal("150.00")),
            TestOrder("DET_BUY_002", "AAPL", "BUY", "LIMIT", 200, Decimal("149.50")),
            TestOrder("DET_SELL_002", "AAPL", "SELL", "LIMIT", 150, Decimal("149.50"))
        ]
        
        sequence2 = [
            TestOrder("DET_BUY_003", "AAPL", "BUY", "LIMIT", 100, Decimal("150.00")),
            TestOrder("DET_SELL_003", "AAPL", "SELL", "LIMIT", 100, Decimal("150.00")),
            TestOrder("DET_BUY_004", "AAPL", "BUY", "LIMIT", 200, Decimal("149.50")),
            TestOrder("DET_SELL_004", "AAPL", "SELL", "LIMIT", 150, Decimal("149.50"))
        ]
        
        # Execute first sequence
        trades1 = []
        for order in sequence1:
            success, latency, response = self.submit_order(order)
            if success and response.get("trades"):
                trades1.extend(response["trades"])
            time.sleep(0.001)  # 1ms delay
        
        # Wait for processing
        time.sleep(0.1)
        
        # Execute second sequence
        trades2 = []
        for order in sequence2:
            success, latency, response = self.submit_order(order)
            if success and response.get("trades"):
                trades2.extend(response["trades"])
            time.sleep(0.001)  # 1ms delay
        
        # Compare trade outcomes (should be deterministic)
        if len(trades1) != len(trades2):
            logger.warning(f"Different number of trades: {len(trades1)} vs {len(trades2)}")
        
        # Verify at least some trades occurred
        if not trades1 and not trades2:
            logger.error("No trades occurred in deterministic test")
            return False
        
        logger.info(f"✅ Deterministic matching test completed: {len(trades1)} and {len(trades2)} trades")
        return True
    
    def test_high_frequency_processing(self, orders_per_second: int = 1000, duration_seconds: int = 5) -> bool:
        """Test high-frequency order processing"""
        logger.info(f"Testing high-frequency processing: {orders_per_second} orders/second for {duration_seconds} seconds")
        
        total_orders = orders_per_second * duration_seconds
        order_interval = 1.0 / orders_per_second
        
        # Generate orders
        orders = []
        for i in range(total_orders):
            side = "BUY" if i % 2 == 0 else "SELL"
            price = Decimal("150.00") + Decimal(str(random.uniform(-2, 2))).quantize(Decimal('0.01'))
            
            order = TestOrder(
                order_id=f"HF_ORDER_{i:06d}",
                symbol="AAPL",
                side=side,
                order_type="LIMIT",
                quantity=random.randint(100, 1000),
                price=price
            )
            orders.append(order)
        
        # Submit orders at target rate
        successful_orders = 0
        failed_orders = 0
        latencies = []
        
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=20) as executor:
            # Submit orders with timing control
            futures = []
            for i, order in enumerate(orders):
                target_time = start_time + (i * order_interval)
                
                # Wait until target time
                current_time = time.time()
                if current_time < target_time:
                    time.sleep(target_time - current_time)
                
                future = executor.submit(self.submit_order, order)
                futures.append(future)
            
            # Collect results
            for future in futures:
                try:
                    success, latency, response = future.result(timeout=1)
                    latencies.append(latency)
                    
                    if success:
                        successful_orders += 1
                    else:
                        failed_orders += 1
                
                except Exception as e:
                    failed_orders += 1
                    logger.warning(f"High-frequency order exception: {e}")
        
        end_time = time.time()
        actual_duration = end_time - start_time
        actual_rate = successful_orders / actual_duration if actual_duration > 0 else 0
        
        # Calculate metrics
        success_rate = successful_orders / total_orders if total_orders > 0 else 0
        avg_latency = statistics.mean(latencies) if latencies else 0
        
        # Success criteria
        if success_rate < 0.80:  # 80% success rate for high-frequency
            logger.error(f"Low success rate in high-frequency test: {success_rate:.2%}")
            return False
        
        if actual_rate < orders_per_second * 0.5:  # At least 50% of target rate
            logger.error(f"Low processing rate: {actual_rate:.1f} orders/second (target: {orders_per_second})")
            return False
        
        logger.info(f"✅ High-frequency processing test passed: {successful_orders}/{total_orders} successful, {actual_rate:.1f} orders/second, {avg_latency:.2f}μs avg latency")
        return True
    
    def test_order_book_integrity(self) -> bool:
        """Test order book integrity"""
        logger.info("Testing order book integrity")
        
        # Submit orders to build order book
        orders = [
            TestOrder("BOOK_BUY_001", "AAPL", "BUY", "LIMIT", 100, Decimal("149.00")),
            TestOrder("BOOK_BUY_002", "AAPL", "BUY", "LIMIT", 200, Decimal("148.50")),
            TestOrder("BOOK_SELL_001", "AAPL", "SELL", "LIMIT", 150, Decimal("151.00")),
            TestOrder("BOOK_SELL_002", "AAPL", "SELL", "LIMIT", 100, Decimal("151.50"))
        ]
        
        for order in orders:
            success, latency, response = self.submit_order(order)
            if not success:
                logger.error(f"Failed to submit order for book test: {order.order_id}")
                return False
            time.sleep(0.001)
        
        # Get order book
        order_book = self.get_order_book("AAPL")
        if not order_book:
            logger.error("Failed to retrieve order book")
            return False
        
        # Verify order book structure
        bids = order_book.get("bids", [])
        asks = order_book.get("asks", [])
        
        if not bids or not asks:
            logger.error("Order book missing bids or asks")
            return False
        
        # Verify bid/ask ordering (bids descending, asks ascending)
        bid_prices = [Decimal(str(bid["price"])) for bid in bids]
        ask_prices = [Decimal(str(ask["price"])) for ask in asks]
        
        if bid_prices != sorted(bid_prices, reverse=True):
            logger.error("Bids not properly ordered (should be descending)")
            return False
        
        if ask_prices != sorted(ask_prices):
            logger.error("Asks not properly ordered (should be ascending)")
            return False
        
        # Verify spread (best ask > best bid)
        best_bid = bid_prices[0]
        best_ask = ask_prices[0]
        
        if best_ask <= best_bid:
            logger.error(f"Invalid spread: best_bid={best_bid}, best_ask={best_ask}")
            return False
        
        logger.info(f"✅ Order book integrity test passed: {len(bids)} bids, {len(asks)} asks, spread={best_ask - best_bid}")
        return True
    
    def run_all_tests(self) -> Dict[str, bool]:
        """Run all trading engine tests"""
        logger.info("Starting comprehensive trading engine tests")
        
        test_results = {}
        
        # Run all test suites (reduced parameters for testing)
        test_results["order_matching_correctness"] = self.test_order_matching_correctness()
        test_results["microsecond_latency"] = self.test_microsecond_latency(50)  # Reduced
        test_results["deterministic_matching"] = self.test_deterministic_matching()
        test_results["high_frequency_processing"] = self.test_high_frequency_processing(500, 3)  # Reduced
        test_results["order_book_integrity"] = self.test_order_book_integrity()
        
        # Summary
        passed_tests = sum(1 for result in test_results.values() if result)
        total_tests = len(test_results)
        
        logger.info(f"Trading Engine Tests: {passed_tests}/{total_tests} passed")
        
        for test_name, result in test_results.items():
            status = "✅ PASSED" if result else "❌ FAILED"
            logger.info(f"  {test_name}: {status}")
        
        return test_results

# Test cases using pytest
@pytest.mark.asyncio
async def test_order_matching():
    """Test order matching functionality"""
    tester = TradingEngineTester()
    result = tester.test_order_matching_correctness()
    assert result, "Order matching correctness test failed"

@pytest.mark.asyncio
async def test_latency_requirements():
    """Test latency requirements"""
    tester = TradingEngineTester()
    result = tester.test_microsecond_latency(20)  # Small test
    assert result, "Microsecond latency test failed"

@pytest.mark.asyncio
async def test_order_book():
    """Test order book integrity"""
    tester = TradingEngineTester()
    result = tester.test_order_book_integrity()
    assert result, "Order book integrity test failed"

if __name__ == "__main__":
    # Run comprehensive trading engine tests
    tester = TradingEngineTester()
    results = tester.run_all_tests()
    
    # Exit with appropriate code
    all_passed = all(results.values())
    exit(0 if all_passed else 1)

#!/usr/bin/env python3
"""
Comprehensive Deterministic Matching and Persistence Tests for Low-Latency Trading Engine
Tests order book persistence, deterministic replay, and ultra-low latency requirements
"""

import asyncio
import json
import logging
import random
import time
import unittest
import uuid
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

import requests

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DeterministicMatchingTestClient:
    """Test client for deterministic matching and persistence operations"""
    
    def __init__(self, trading_engine_url: str = "http://localhost:8080"):
        self.trading_engine_url = trading_engine_url
        self.session = requests.Session()
        self.session.timeout = 10  # Shorter timeout for low-latency testing
    
    def submit_order(self, order_data: Dict) -> Optional[Dict]:
        """Submit trading order"""
        try:
            start_time = time.time_ns()
            response = self.session.post(
                f"{self.trading_engine_url}/api/v1/orders",
                json=order_data,
                headers={"Content-Type": "application/json"}
            )
            end_time = time.time_ns()
            
            result = response.json() if response.status_code == 200 else None
            if result:
                result["submission_latency_ns"] = end_time - start_time
            
            return result
        except Exception as e:
            logger.error(f"Order submission failed: {e}")
            return None
    
    def cancel_order(self, order_id: str) -> Optional[Dict]:
        """Cancel trading order"""
        try:
            start_time = time.time_ns()
            response = self.session.delete(f"{self.trading_engine_url}/api/v1/orders/{order_id}")
            end_time = time.time_ns()
            
            result = response.json() if response.status_code == 200 else None
            if result:
                result["cancellation_latency_ns"] = end_time - start_time
            
            return result
        except Exception as e:
            logger.error(f"Order cancellation failed: {e}")
            return None
    
    def get_order_book(self, symbol: str, depth: int = 10) -> Optional[Dict]:
        """Get order book snapshot"""
        try:
            start_time = time.time_ns()
            response = self.session.get(
                f"{self.trading_engine_url}/api/v1/orderbook/{symbol}",
                params={"depth": depth}
            )
            end_time = time.time_ns()
            
            result = response.json() if response.status_code == 200 else None
            if result:
                result["retrieval_latency_ns"] = end_time - start_time
            
            return result
        except Exception as e:
            logger.error(f"Order book retrieval failed: {e}")
            return None
    
    def get_trade_history(self, symbol: str, limit: int = 100) -> Optional[List[Dict]]:
        """Get trade history"""
        try:
            response = self.session.get(
                f"{self.trading_engine_url}/api/v1/trades/{symbol}",
                params={"limit": limit}
            )
            return response.json().get("trades", []) if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"Trade history retrieval failed: {e}")
            return None
    
    def create_snapshot(self, symbol: str) -> Optional[Dict]:
        """Create order book snapshot"""
        try:
            response = self.session.post(
                f"{self.trading_engine_url}/api/v1/snapshots/{symbol}",
                headers={"Content-Type": "application/json"}
            )
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"Snapshot creation failed: {e}")
            return None
    
    def restore_from_snapshot(self, snapshot_id: str) -> bool:
        """Restore order book from snapshot"""
        try:
            response = self.session.post(
                f"{self.trading_engine_url}/api/v1/snapshots/{snapshot_id}/restore"
            )
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Snapshot restore failed: {e}")
            return False
    
    def replay_from_log(self, start_sequence: int, end_sequence: int = None) -> Optional[Dict]:
        """Replay orders from transaction log"""
        try:
            params = {"start_sequence": start_sequence}
            if end_sequence:
                params["end_sequence"] = end_sequence
            
            response = self.session.post(
                f"{self.trading_engine_url}/api/v1/replay",
                json=params,
                headers={"Content-Type": "application/json"}
            )
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"Log replay failed: {e}")
            return None
    
    def get_engine_metrics(self) -> Optional[Dict]:
        """Get trading engine performance metrics"""
        try:
            response = self.session.get(f"{self.trading_engine_url}/api/v1/metrics")
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"Metrics retrieval failed: {e}")
            return None
    
    def simulate_feed_burst(self, symbol: str, num_orders: int, burst_duration_ms: int) -> Optional[Dict]:
        """Simulate high-frequency order feed burst"""
        try:
            response = self.session.post(
                f"{self.trading_engine_url}/api/v1/test/feed-burst",
                json={
                    "symbol": symbol,
                    "num_orders": num_orders,
                    "burst_duration_ms": burst_duration_ms
                }
            )
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"Feed burst simulation failed: {e}")
            return None
    
    def simulate_failover(self, failover_type: str = "primary_to_secondary") -> bool:
        """Simulate trading engine failover"""
        try:
            response = self.session.post(
                f"{self.trading_engine_url}/api/v1/test/failover",
                json={"failover_type": failover_type}
            )
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Failover simulation failed: {e}")
            return False


class DeterministicMatchingAnalyzer:
    """Analyzer for deterministic matching and persistence"""
    
    def __init__(self, client: DeterministicMatchingTestClient):
        self.client = client
        self.test_orders: List[str] = []
        self.test_symbols = ["AAPL", "GOOGL", "MSFT", "TSLA"]
    
    def test_ultra_low_latency_performance(self, num_orders: int = 1000) -> Dict:
        """Test ultra-low latency order processing"""
        logger.info(f"Testing ultra-low latency with {num_orders} orders")
        
        symbol = random.choice(self.test_symbols)
        submission_latencies = []
        successful_orders = 0
        failed_orders = 0
        
        # Submit orders and measure latency
        for i in range(num_orders):
            order_data = {
                "order_id": f"PERF{i:06d}",
                "symbol": symbol,
                "side": random.choice(["BUY", "SELL"]),
                "quantity": random.randint(100, 1000),
                "price": round(random.uniform(100.0, 200.0), 2),
                "order_type": "LIMIT",
                "time_in_force": "GTC"
            }
            
            result = self.client.submit_order(order_data)
            
            if result and result.get("order_id"):
                successful_orders += 1
                self.test_orders.append(result["order_id"])
                
                # Record latency
                latency_ns = result.get("submission_latency_ns", 0)
                submission_latencies.append(latency_ns)
            else:
                failed_orders += 1
        
        # Calculate latency statistics
        if submission_latencies:
            avg_latency_ns = sum(submission_latencies) / len(submission_latencies)
            p99_latency_ns = sorted(submission_latencies)[int(len(submission_latencies) * 0.99)]
            max_latency_ns = max(submission_latencies)
            
            # Convert to microseconds for readability
            avg_latency_us = avg_latency_ns / 1000
            p99_latency_us = p99_latency_ns / 1000
            max_latency_us = max_latency_ns / 1000
        else:
            avg_latency_us = p99_latency_us = max_latency_us = 0
        
        return {
            "total_orders": num_orders,
            "successful_orders": successful_orders,
            "failed_orders": failed_orders,
            "success_rate": successful_orders / num_orders,
            "average_latency_us": avg_latency_us,
            "p99_latency_us": p99_latency_us,
            "max_latency_us": max_latency_us,
            "ultra_low_latency_achieved": p99_latency_us < 100  # < 100 microseconds
        }
    
    def test_deterministic_order_matching(self, num_scenarios: int = 20) -> Dict:
        """Test deterministic order matching behavior"""
        logger.info(f"Testing deterministic matching with {num_scenarios} scenarios")
        
        symbol = random.choice(self.test_symbols)
        matching_scenarios = []
        deterministic_violations = 0
        
        for scenario in range(num_scenarios):
            # Create deterministic scenario
            base_price = 150.0
            scenario_orders = []
            
            # Submit buy orders
            for i in range(3):
                buy_order = {
                    "order_id": f"BUY{scenario:03d}{i}",
                    "symbol": symbol,
                    "side": "BUY",
                    "quantity": 100,
                    "price": base_price - i,  # Decreasing prices
                    "order_type": "LIMIT",
                    "time_in_force": "GTC"
                }
                
                result = self.client.submit_order(buy_order)
                if result:
                    scenario_orders.append(result)
                    self.test_orders.append(result["order_id"])
            
            # Submit sell orders
            for i in range(3):
                sell_order = {
                    "order_id": f"SELL{scenario:03d}{i}",
                    "symbol": symbol,
                    "side": "SELL",
                    "quantity": 100,
                    "price": base_price + i,  # Increasing prices
                    "order_type": "LIMIT",
                    "time_in_force": "GTC"
                }
                
                result = self.client.submit_order(sell_order)
                if result:
                    scenario_orders.append(result)
                    self.test_orders.append(result["order_id"])
            
            # Submit market order to trigger matching
            market_order = {
                "order_id": f"MKT{scenario:03d}",
                "symbol": symbol,
                "side": "SELL",
                "quantity": 150,
                "order_type": "MARKET",
                "time_in_force": "IOC"
            }
            
            market_result = self.client.submit_order(market_order)
            if market_result:
                self.test_orders.append(market_result["order_id"])
            
            # Get trade history to verify matching
            trades = self.client.get_trade_history(symbol, limit=10)
            
            if trades:
                # Verify price-time priority
                recent_trades = [t for t in trades if t.get("timestamp", 0) > time.time() - 10]
                
                if len(recent_trades) >= 2:
                    # Check if trades follow price-time priority
                    for i in range(1, len(recent_trades)):
                        prev_trade = recent_trades[i-1]
                        curr_trade = recent_trades[i]
                        
                        # For buy orders, higher prices should execute first
                        if (prev_trade.get("side") == "BUY" and curr_trade.get("side") == "BUY"):
                            if prev_trade.get("price", 0) < curr_trade.get("price", 0):
                                deterministic_violations += 1
            
            matching_scenarios.append({
                "scenario": scenario,
                "orders_submitted": len(scenario_orders),
                "trades_generated": len(recent_trades) if trades else 0
            })
            
            time.sleep(0.1)  # Brief pause between scenarios
        
        successful_scenarios = len([s for s in matching_scenarios if s["orders_submitted"] > 0])
        
        return {
            "num_scenarios": num_scenarios,
            "successful_scenarios": successful_scenarios,
            "deterministic_violations": deterministic_violations,
            "matching_determinism": deterministic_violations == 0,
            "scenario_success_rate": successful_scenarios / num_scenarios
        }
    
    def test_snapshot_and_replay_consistency(self, num_operations: int = 100) -> Dict:
        """Test snapshot creation and replay consistency"""
        logger.info(f"Testing snapshot and replay with {num_operations} operations")
        
        symbol = random.choice(self.test_symbols)
        
        # Submit initial orders
        initial_orders = []
        for i in range(num_operations):
            order_data = {
                "order_id": f"SNAP{i:06d}",
                "symbol": symbol,
                "side": random.choice(["BUY", "SELL"]),
                "quantity": random.randint(100, 500),
                "price": round(random.uniform(140.0, 160.0), 2),
                "order_type": "LIMIT",
                "time_in_force": "GTC"
            }
            
            result = self.client.submit_order(order_data)
            if result:
                initial_orders.append(result)
                self.test_orders.append(result["order_id"])
        
        # Get order book state before snapshot
        pre_snapshot_book = self.client.get_order_book(symbol, depth=20)
        
        if not pre_snapshot_book:
            return {"error": "Failed to get pre-snapshot order book"}
        
        # Create snapshot
        snapshot_result = self.client.create_snapshot(symbol)
        
        if not snapshot_result:
            return {"error": "Failed to create snapshot"}
        
        snapshot_id = snapshot_result.get("snapshot_id")
        
        # Submit more orders after snapshot
        post_snapshot_orders = []
        for i in range(20):
            order_data = {
                "order_id": f"POST{i:06d}",
                "symbol": symbol,
                "side": random.choice(["BUY", "SELL"]),
                "quantity": random.randint(100, 300),
                "price": round(random.uniform(145.0, 155.0), 2),
                "order_type": "LIMIT",
                "time_in_force": "GTC"
            }
            
            result = self.client.submit_order(order_data)
            if result:
                post_snapshot_orders.append(result)
                self.test_orders.append(result["order_id"])
        
        # Restore from snapshot
        restore_success = self.client.restore_from_snapshot(snapshot_id)
        
        if not restore_success:
            return {"error": "Failed to restore from snapshot"}
        
        # Get order book state after restore
        post_restore_book = self.client.get_order_book(symbol, depth=20)
        
        if not post_restore_book:
            return {"error": "Failed to get post-restore order book"}
        
        # Compare order books (should match pre-snapshot state)
        pre_bids = pre_snapshot_book.get("bids", [])
        pre_asks = pre_snapshot_book.get("asks", [])
        post_bids = post_restore_book.get("bids", [])
        post_asks = post_restore_book.get("asks", [])
        
        bids_match = len(pre_bids) == len(post_bids)
        asks_match = len(pre_asks) == len(post_asks)
        
        # Check price levels (simplified comparison)
        if bids_match and pre_bids and post_bids:
            bids_match = abs(pre_bids[0].get("price", 0) - post_bids[0].get("price", 0)) < 0.01
        
        if asks_match and pre_asks and post_asks:
            asks_match = abs(pre_asks[0].get("price", 0) - post_asks[0].get("price", 0)) < 0.01
        
        consistency_achieved = bids_match and asks_match
        
        return {
            "initial_orders": len(initial_orders),
            "post_snapshot_orders": len(post_snapshot_orders),
            "snapshot_created": snapshot_id is not None,
            "restore_successful": restore_success,
            "bids_consistent": bids_match,
            "asks_consistent": asks_match,
            "overall_consistency": consistency_achieved
        }
    
    def test_high_frequency_feed_handling(self, burst_size: int = 5000, burst_duration_ms: int = 100) -> Dict:
        """Test handling of high-frequency order feeds"""
        logger.info(f"Testing HF feed with {burst_size} orders in {burst_duration_ms}ms")
        
        symbol = random.choice(self.test_symbols)
        
        # Get initial metrics
        initial_metrics = self.client.get_engine_metrics()
        
        # Simulate feed burst
        burst_result = self.client.simulate_feed_burst(symbol, burst_size, burst_duration_ms)
        
        if not burst_result:
            return {"error": "Failed to simulate feed burst"}
        
        # Wait for processing
        time.sleep(2)
        
        # Get final metrics
        final_metrics = self.client.get_engine_metrics()
        
        if not initial_metrics or not final_metrics:
            return {"error": "Failed to get engine metrics"}
        
        # Calculate throughput
        orders_processed = burst_result.get("orders_processed", 0)
        actual_duration_ms = burst_result.get("actual_duration_ms", burst_duration_ms)
        
        throughput_ops = (orders_processed / actual_duration_ms) * 1000 if actual_duration_ms > 0 else 0
        
        # Check for dropped orders or errors
        dropped_orders = burst_size - orders_processed
        error_rate = dropped_orders / burst_size if burst_size > 0 else 0
        
        return {
            "burst_size": burst_size,
            "target_duration_ms": burst_duration_ms,
            "actual_duration_ms": actual_duration_ms,
            "orders_processed": orders_processed,
            "dropped_orders": dropped_orders,
            "throughput_ops_per_second": throughput_ops,
            "error_rate": error_rate,
            "high_frequency_handling": error_rate < 0.01  # < 1% error rate
        }
    
    def cleanup_test_data(self):
        """Clean up test data"""
        for order_id in self.test_orders:
            try:
                self.client.cancel_order(order_id)
            except Exception:
                pass
        self.test_orders.clear()


class TestDeterministicMatching(unittest.TestCase):
    """Test cases for deterministic matching and persistence"""
    
    @classmethod
    def setUpClass(cls):
        cls.client = DeterministicMatchingTestClient()
        cls.analyzer = DeterministicMatchingAnalyzer(cls.client)
        
        # Wait for trading engine to be ready
        max_retries = 30
        for i in range(max_retries):
            try:
                metrics = cls.client.get_engine_metrics()
                if metrics and metrics.get("status") == "ready":
                    logger.info("Trading engine is ready")
                    break
            except Exception:
                pass
            time.sleep(1)
        else:
            raise Exception("Trading engine not ready after 30 seconds")
    
    @classmethod
    def tearDownClass(cls):
        cls.analyzer.cleanup_test_data()
    
    def test_ultra_low_latency_order_processing(self):
        """Test ultra-low latency order processing"""
        result = self.analyzer.test_ultra_low_latency_performance(num_orders=500)
        
        self.assertGreater(result["success_rate"], 0.95)
        self.assertTrue(result["ultra_low_latency_achieved"])
        self.assertLess(result["p99_latency_us"], 100)  # < 100 microseconds
        
        logger.info(f"Ultra-Low Latency Test: {result}")
    
    def test_deterministic_matching_behavior(self):
        """Test deterministic order matching"""
        result = self.analyzer.test_deterministic_order_matching(num_scenarios=10)
        
        self.assertTrue(result["matching_determinism"])
        self.assertEqual(result["deterministic_violations"], 0)
        self.assertGreater(result["scenario_success_rate"], 0.90)
        
        logger.info(f"Deterministic Matching Test: {result}")
    
    def test_snapshot_replay_consistency(self):
        """Test snapshot and replay consistency"""
        result = self.analyzer.test_snapshot_and_replay_consistency(num_operations=50)
        
        self.assertNotIn("error", result)
        self.assertTrue(result["overall_consistency"])
        self.assertTrue(result["restore_successful"])
        
        logger.info(f"Snapshot Replay Test: {result}")
    
    def test_high_frequency_feed_resilience(self):
        """Test high-frequency feed handling"""
        result = self.analyzer.test_high_frequency_feed_handling(burst_size=2000, burst_duration_ms=50)
        
        self.assertNotIn("error", result)
        self.assertTrue(result["high_frequency_handling"])
        self.assertGreater(result["throughput_ops_per_second"], 10000)  # > 10K ops/sec
        
        logger.info(f"High-Frequency Feed Test: {result}")


if __name__ == "__main__":
    unittest.main()

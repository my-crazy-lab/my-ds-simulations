#!/usr/bin/env python3
"""
Comprehensive Stateful Aggregation and P&L Tests for Market Risk Engine
Tests real-time risk calculation, stateful aggregation, and P&L systems
"""

import asyncio
import json
import logging
import random
import time
import unittest
import uuid
from decimal import Decimal
from typing import Dict, List, Optional, Set

import requests

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class StatefulAggregationTestClient:
    """Test client for stateful aggregation and P&L operations"""
    
    def __init__(self, risk_engine_url: str = "http://localhost:8080"):
        self.risk_engine_url = risk_engine_url
        self.session = requests.Session()
        self.session.timeout = 30
    
    def submit_market_data(self, market_data: Dict) -> Optional[Dict]:
        """Submit market data for risk calculation"""
        try:
            response = self.session.post(
                f"{self.risk_engine_url}/api/v1/market-data",
                json=market_data,
                headers={"Content-Type": "application/json"}
            )
            return response.json() if response.status_code == 201 else None
        except Exception as e:
            logger.error(f"Market data submission failed: {e}")
            return None
    
    def get_portfolio_pnl(self, portfolio_id: str) -> Optional[Dict]:
        """Get portfolio P&L"""
        try:
            response = self.session.get(f"{self.risk_engine_url}/api/v1/portfolios/{portfolio_id}/pnl")
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"P&L retrieval failed: {e}")
            return None
    
    def get_risk_metrics(self, portfolio_id: str) -> Optional[Dict]:
        """Get risk metrics for portfolio"""
        try:
            response = self.session.get(f"{self.risk_engine_url}/api/v1/portfolios/{portfolio_id}/risk")
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"Risk metrics retrieval failed: {e}")
            return None
    
    def create_checkpoint(self, checkpoint_id: str) -> Optional[Dict]:
        """Create state checkpoint"""
        try:
            response = self.session.post(
                f"{self.risk_engine_url}/api/v1/checkpoints",
                json={"checkpoint_id": checkpoint_id},
                headers={"Content-Type": "application/json"}
            )
            return response.json() if response.status_code == 201 else None
        except Exception as e:
            logger.error(f"Checkpoint creation failed: {e}")
            return None
    
    def restore_from_checkpoint(self, checkpoint_id: str) -> Optional[Dict]:
        """Restore from checkpoint"""
        try:
            response = self.session.post(
                f"{self.risk_engine_url}/api/v1/restore/{checkpoint_id}",
                headers={"Content-Type": "application/json"}
            )
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"Checkpoint restore failed: {e}")
            return None


class StatefulAggregationAnalyzer:
    """Analyzer for stateful aggregation and P&L calculations"""
    
    def __init__(self, client: StatefulAggregationTestClient):
        self.client = client
        self.test_portfolios: List[str] = []
        self.test_checkpoints: List[str] = []
    
    def test_real_time_pnl_calculation(self, num_updates: int = 100) -> Dict:
        """Test real-time P&L calculation accuracy"""
        logger.info(f"Testing real-time P&L calculation with {num_updates} updates")
        
        portfolio_id = f"PORTFOLIO_{uuid.uuid4().hex[:8]}"
        self.test_portfolios.append(portfolio_id)
        
        # Initialize portfolio with positions
        instruments = ["AAPL", "GOOGL", "MSFT", "TSLA", "AMZN"]
        positions = {instrument: random.randint(-1000, 1000) for instrument in instruments}
        
        successful_updates = 0
        pnl_calculations = []
        calculation_times = []
        
        for i in range(num_updates):
            # Generate market data update
            instrument = random.choice(instruments)
            price_change = random.uniform(-0.05, 0.05)  # ±5% price change
            
            market_data = {
                "instrument": instrument,
                "price": round(100 * (1 + price_change), 2),
                "timestamp": int(time.time() * 1000),
                "portfolio_id": portfolio_id,
                "position": positions.get(instrument, 0)
            }
            
            # Submit market data and measure calculation time
            calc_start = time.time()
            result = self.client.submit_market_data(market_data)
            
            if result:
                # Get updated P&L
                pnl_result = self.client.get_portfolio_pnl(portfolio_id)
                calc_end = time.time()
                
                if pnl_result:
                    successful_updates += 1
                    calculation_times.append(calc_end - calc_start)
                    pnl_calculations.append(pnl_result.get("total_pnl", 0))
        
        avg_calculation_time = (
            sum(calculation_times) / len(calculation_times)
            if calculation_times else 0
        )
        
        # Check for P&L consistency
        pnl_variance = (
            max(pnl_calculations) - min(pnl_calculations)
            if len(pnl_calculations) > 1 else 0
        )
        
        return {
            "updates_processed": num_updates,
            "successful_updates": successful_updates,
            "update_success_rate": successful_updates / num_updates,
            "average_calculation_time": avg_calculation_time,
            "pnl_variance": pnl_variance,
            "real_time_performance": avg_calculation_time < 0.1  # < 100ms
        }
    
    def test_stateful_aggregation_consistency(self, num_aggregations: int = 50) -> Dict:
        """Test stateful aggregation consistency across updates"""
        logger.info(f"Testing stateful aggregation consistency with {num_aggregations} aggregations")
        
        if len(self.test_portfolios) == 0:
            return {"error": "No test portfolios available for aggregation testing"}
        
        portfolio_id = self.test_portfolios[0]
        consistent_aggregations = 0
        inconsistent_aggregations = 0
        
        # Baseline aggregation
        baseline_risk = self.client.get_risk_metrics(portfolio_id)
        
        if not baseline_risk:
            return {"error": "Failed to get baseline risk metrics"}
        
        for i in range(num_aggregations):
            # Submit small market data update
            market_data = {
                "instrument": "AAPL",
                "price": 150.0 + random.uniform(-1, 1),
                "timestamp": int(time.time() * 1000),
                "portfolio_id": portfolio_id,
                "position": 100
            }
            
            self.client.submit_market_data(market_data)
            time.sleep(0.05)  # Brief delay for processing
            
            # Get updated risk metrics
            updated_risk = self.client.get_risk_metrics(portfolio_id)
            
            if updated_risk:
                # Check aggregation consistency
                baseline_var = baseline_risk.get("var_95", 0)
                updated_var = updated_risk.get("var_95", 0)
                
                # VaR should change but remain reasonable
                var_change_ratio = abs(updated_var - baseline_var) / baseline_var if baseline_var != 0 else 0
                
                if var_change_ratio < 0.5:  # Less than 50% change is reasonable
                    consistent_aggregations += 1
                else:
                    inconsistent_aggregations += 1
                    logger.warning(f"Large VaR change detected: {var_change_ratio:.2%}")
                
                baseline_risk = updated_risk
            else:
                inconsistent_aggregations += 1
        
        return {
            "aggregations_tested": num_aggregations,
            "consistent_aggregations": consistent_aggregations,
            "inconsistent_aggregations": inconsistent_aggregations,
            "aggregation_consistency_rate": consistent_aggregations / num_aggregations
        }
    
    def test_checkpoint_restore_accuracy(self, num_checkpoints: int = 10) -> Dict:
        """Test checkpoint and restore accuracy"""
        logger.info(f"Testing checkpoint/restore accuracy with {num_checkpoints} checkpoints")
        
        if len(self.test_portfolios) == 0:
            return {"error": "No test portfolios available for checkpoint testing"}
        
        portfolio_id = self.test_portfolios[0]
        successful_checkpoints = 0
        successful_restores = 0
        
        for i in range(num_checkpoints):
            checkpoint_id = f"CHECKPOINT_{i}_{uuid.uuid4().hex[:8]}"
            self.test_checkpoints.append(checkpoint_id)
            
            # Get current state
            current_pnl = self.client.get_portfolio_pnl(portfolio_id)
            current_risk = self.client.get_risk_metrics(portfolio_id)
            
            if current_pnl and current_risk:
                # Create checkpoint
                checkpoint_result = self.client.create_checkpoint(checkpoint_id)
                
                if checkpoint_result:
                    successful_checkpoints += 1
                    
                    # Make some changes
                    for j in range(5):
                        market_data = {
                            "instrument": f"TEST_{j}",
                            "price": random.uniform(50, 200),
                            "timestamp": int(time.time() * 1000),
                            "portfolio_id": portfolio_id,
                            "position": random.randint(-100, 100)
                        }
                        self.client.submit_market_data(market_data)
                    
                    time.sleep(0.5)  # Allow processing
                    
                    # Restore from checkpoint
                    restore_result = self.client.restore_from_checkpoint(checkpoint_id)
                    
                    if restore_result:
                        time.sleep(0.5)  # Allow restore processing
                        
                        # Verify restoration
                        restored_pnl = self.client.get_portfolio_pnl(portfolio_id)
                        restored_risk = self.client.get_risk_metrics(portfolio_id)
                        
                        if restored_pnl and restored_risk:
                            # Check if values are close to original
                            pnl_diff = abs(
                                restored_pnl.get("total_pnl", 0) - current_pnl.get("total_pnl", 0)
                            )
                            
                            if pnl_diff < 0.01:  # Within 1 cent
                                successful_restores += 1
                            else:
                                logger.warning(f"P&L mismatch after restore: {pnl_diff}")
        
        return {
            "checkpoints_attempted": num_checkpoints,
            "successful_checkpoints": successful_checkpoints,
            "successful_restores": successful_restores,
            "checkpoint_success_rate": successful_checkpoints / num_checkpoints,
            "restore_accuracy_rate": successful_restores / successful_checkpoints if successful_checkpoints > 0 else 0
        }
    
    def test_high_frequency_updates_performance(self, num_updates: int = 1000) -> Dict:
        """Test performance under high-frequency updates"""
        logger.info(f"Testing high-frequency updates performance with {num_updates} updates")
        
        portfolio_id = f"HF_PORTFOLIO_{uuid.uuid4().hex[:8]}"
        self.test_portfolios.append(portfolio_id)
        
        update_times = []
        successful_updates = 0
        
        start_time = time.time()
        
        for i in range(num_updates):
            market_data = {
                "instrument": f"HF_INSTRUMENT_{i % 10}",
                "price": random.uniform(50, 200),
                "timestamp": int(time.time() * 1000000),  # Microsecond precision
                "portfolio_id": portfolio_id,
                "position": random.randint(-1000, 1000)
            }
            
            update_start = time.time()
            result = self.client.submit_market_data(market_data)
            update_end = time.time()
            
            if result:
                successful_updates += 1
                update_times.append(update_end - update_start)
        
        end_time = time.time()
        total_time = end_time - start_time
        
        avg_update_time = sum(update_times) / len(update_times) if update_times else 0
        p95_update_time = sorted(update_times)[int(len(update_times) * 0.95)] if update_times else 0
        throughput = successful_updates / total_time if total_time > 0 else 0
        
        return {
            "updates_attempted": num_updates,
            "successful_updates": successful_updates,
            "total_time": total_time,
            "average_update_time": avg_update_time,
            "p95_update_time": p95_update_time,
            "throughput_per_second": throughput,
            "high_performance_achieved": throughput > 100  # > 100 updates/sec
        }
    
    def cleanup_test_data(self):
        """Clean up test data"""
        for portfolio_id in self.test_portfolios:
            try:
                self.client.session.delete(f"{self.client.risk_engine_url}/api/v1/portfolios/{portfolio_id}")
            except Exception:
                pass
        
        for checkpoint_id in self.test_checkpoints:
            try:
                self.client.session.delete(f"{self.client.risk_engine_url}/api/v1/checkpoints/{checkpoint_id}")
            except Exception:
                pass
        
        self.test_portfolios.clear()
        self.test_checkpoints.clear()


class TestStatefulAggregationPnL(unittest.TestCase):
    """Test cases for stateful aggregation and P&L calculations"""
    
    @classmethod
    def setUpClass(cls):
        cls.client = StatefulAggregationTestClient()
        cls.analyzer = StatefulAggregationAnalyzer(cls.client)
        
        # Wait for risk engine to be ready
        max_retries = 30
        for i in range(max_retries):
            try:
                # Try to submit test market data to verify system is ready
                test_data = {
                    "instrument": "HEALTH_CHECK",
                    "price": 100.0,
                    "timestamp": int(time.time() * 1000),
                    "portfolio_id": "HEALTH_CHECK_PORTFOLIO",
                    "position": 0
                }
                result = cls.client.submit_market_data(test_data)
                if result:
                    logger.info("Market risk engine is ready")
                    break
            except Exception:
                pass
            time.sleep(1)
        else:
            raise Exception("Market risk engine not ready after 30 seconds")
    
    @classmethod
    def tearDownClass(cls):
        cls.analyzer.cleanup_test_data()
    
    def test_real_time_pnl_accuracy(self):
        """Test real-time P&L calculation accuracy"""
        result = self.analyzer.test_real_time_pnl_calculation(num_updates=50)
        
        self.assertNotIn("error", result)
        self.assertGreater(result["update_success_rate"], 0.90)
        self.assertTrue(result["real_time_performance"])
        
        logger.info(f"Real-time P&L Test: {result}")
    
    def test_stateful_aggregation_reliability(self):
        """Test stateful aggregation consistency"""
        result = self.analyzer.test_stateful_aggregation_consistency(num_aggregations=25)
        
        self.assertNotIn("error", result)
        self.assertGreater(result["aggregation_consistency_rate"], 0.85)
        
        logger.info(f"Stateful Aggregation Test: {result}")
    
    def test_checkpoint_restore_functionality(self):
        """Test checkpoint and restore functionality"""
        result = self.analyzer.test_checkpoint_restore_accuracy(num_checkpoints=5)
        
        self.assertNotIn("error", result)
        self.assertGreater(result["checkpoint_success_rate"], 0.80)
        self.assertGreater(result["restore_accuracy_rate"], 0.80)
        
        logger.info(f"Checkpoint/Restore Test: {result}")
    
    def test_high_frequency_performance(self):
        """Test high-frequency updates performance"""
        result = self.analyzer.test_high_frequency_updates_performance(num_updates=500)
        
        self.assertNotIn("error", result)
        self.assertGreater(result["successful_updates"] / result["updates_attempted"], 0.90)
        self.assertTrue(result["high_performance_achieved"])
        
        logger.info(f"High-Frequency Performance Test: {result}")


if __name__ == "__main__":
    unittest.main()

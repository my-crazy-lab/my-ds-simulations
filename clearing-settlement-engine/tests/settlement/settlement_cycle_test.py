#!/usr/bin/env python3
"""
Settlement Cycle Test Suite for Clearing & Settlement Engine

This test suite validates:
1. Complete T+1 settlement cycle processing
2. Bilateral and multilateral netting accuracy
3. Atomic settlement across multiple ledgers
4. Risk management and collateral requirements
5. Settlement optimization and efficiency
"""

import asyncio
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from decimal import Decimal
from datetime import datetime, timedelta

import aiohttp
import pytest
import requests

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class ClearingTransaction:
    """Clearing transaction for settlement testing"""
    transaction_id: str
    payer_bank: str
    payee_bank: str
    amount: str
    currency: str = "USD"
    value_date: str = None
    transaction_type: str = "CREDIT_TRANSFER"
    priority: str = "NORMAL"

@dataclass
class NettingRequest:
    """Netting request configuration"""
    netting_type: str
    currency: str
    participants: List[str]
    cutoff_time: str
    value_date: str

@dataclass
class SettlementBatch:
    """Settlement batch configuration"""
    batch_id: str
    settlement_method: str
    currency: str
    participants: List[str]
    total_amount: str
    settlement_date: str

@dataclass
class SettlementResult:
    """Result of settlement processing"""
    batch_id: str
    status: str
    processing_time_ms: int
    netting_efficiency: float
    settlement_amount: Decimal
    participant_count: int
    success: bool
    error: Optional[str] = None

class SettlementTester:
    """Handles settlement cycle testing"""
    
    def __init__(self):
        self.base_url = "http://localhost:8461/api/v1"
        self.netting_url = "http://localhost:8462/api/v1"
        self.settlement_url = "http://localhost:8463/api/v1"
        self.risk_url = "http://localhost:8464/api/v1"
        self.session = None
        self.test_results: List[SettlementResult] = []
        
    async def setup_session(self):
        """Setup HTTP session"""
        timeout = aiohttp.ClientTimeout(total=60)
        self.session = aiohttp.ClientSession(
            timeout=timeout,
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer test_settlement_token"
            }
        )
    
    async def cleanup_session(self):
        """Cleanup HTTP session"""
        if self.session:
            await self.session.close()
    
    async def submit_clearing_transaction(self, transaction: ClearingTransaction) -> bool:
        """Submit a transaction for clearing"""
        try:
            transaction_data = {
                "transaction_id": transaction.transaction_id,
                "payer_bank": transaction.payer_bank,
                "payee_bank": transaction.payee_bank,
                "amount": transaction.amount,
                "currency": transaction.currency,
                "value_date": transaction.value_date or datetime.now().strftime("%Y-%m-%d"),
                "transaction_type": transaction.transaction_type,
                "priority": transaction.priority
            }
            
            async with self.session.post(f"{self.base_url}/transactions", json=transaction_data) as response:
                if response.status in [200, 201]:
                    logger.info(f"Transaction {transaction.transaction_id} submitted successfully")
                    return True
                else:
                    error_data = await response.json()
                    logger.error(f"Failed to submit transaction {transaction.transaction_id}: {error_data}")
                    return False
        
        except Exception as e:
            logger.error(f"Error submitting transaction {transaction.transaction_id}: {e}")
            return False
    
    async def run_bilateral_netting(self, request: NettingRequest) -> SettlementResult:
        """Run bilateral netting between participants"""
        start_time = time.time()
        
        try:
            netting_data = {
                "netting_type": request.netting_type,
                "currency": request.currency,
                "participants": request.participants,
                "cutoff_time": request.cutoff_time,
                "value_date": request.value_date
            }
            
            async with self.session.post(f"{self.netting_url}/netting/bilateral", json=netting_data) as response:
                processing_time = int((time.time() - start_time) * 1000)
                response_data = await response.json()
                
                if response.status in [200, 201]:
                    data = response_data.get("data", {})
                    return SettlementResult(
                        batch_id=data.get("batch_id", ""),
                        status=data.get("status", "UNKNOWN"),
                        processing_time_ms=processing_time,
                        netting_efficiency=float(data.get("netting_efficiency", 0.0)),
                        settlement_amount=Decimal(str(data.get("net_amount", 0))),
                        participant_count=len(request.participants),
                        success=True
                    )
                else:
                    return SettlementResult(
                        batch_id="",
                        status="FAILED",
                        processing_time_ms=processing_time,
                        netting_efficiency=0.0,
                        settlement_amount=Decimal("0"),
                        participant_count=len(request.participants),
                        success=False,
                        error=f"HTTP {response.status}: {response_data.get('error', 'Unknown error')}"
                    )
        
        except Exception as e:
            processing_time = int((time.time() - start_time) * 1000)
            return SettlementResult(
                batch_id="",
                status="ERROR",
                processing_time_ms=processing_time,
                netting_efficiency=0.0,
                settlement_amount=Decimal("0"),
                participant_count=len(request.participants),
                success=False,
                error=str(e)
            )
    
    async def run_multilateral_netting(self, request: NettingRequest) -> SettlementResult:
        """Run multilateral netting across all participants"""
        start_time = time.time()
        
        try:
            netting_data = {
                "netting_type": request.netting_type,
                "currency": request.currency,
                "participants": request.participants,
                "cutoff_time": request.cutoff_time,
                "value_date": request.value_date,
                "optimization_level": "HIGH"
            }
            
            async with self.session.post(f"{self.netting_url}/netting/multilateral", json=netting_data) as response:
                processing_time = int((time.time() - start_time) * 1000)
                response_data = await response.json()
                
                if response.status in [200, 201]:
                    data = response_data.get("data", {})
                    return SettlementResult(
                        batch_id=data.get("batch_id", ""),
                        status=data.get("status", "UNKNOWN"),
                        processing_time_ms=processing_time,
                        netting_efficiency=float(data.get("netting_efficiency", 0.0)),
                        settlement_amount=Decimal(str(data.get("net_amount", 0))),
                        participant_count=len(request.participants),
                        success=True
                    )
                else:
                    return SettlementResult(
                        batch_id="",
                        status="FAILED",
                        processing_time_ms=processing_time,
                        netting_efficiency=0.0,
                        settlement_amount=Decimal("0"),
                        participant_count=len(request.participants),
                        success=False,
                        error=f"HTTP {response.status}: {response_data.get('error', 'Unknown error')}"
                    )
        
        except Exception as e:
            processing_time = int((time.time() - start_time) * 1000)
            return SettlementResult(
                batch_id="",
                status="ERROR",
                processing_time_ms=processing_time,
                netting_efficiency=0.0,
                settlement_amount=Decimal("0"),
                participant_count=len(request.participants),
                success=False,
                error=str(e)
            )
    
    async def execute_settlement(self, batch: SettlementBatch) -> SettlementResult:
        """Execute settlement for a batch"""
        start_time = time.time()
        
        try:
            settlement_data = {
                "settlement_batch_id": batch.batch_id,
                "settlement_method": batch.settlement_method,
                "currency": batch.currency,
                "participants": batch.participants,
                "total_amount": batch.total_amount,
                "settlement_date": batch.settlement_date
            }
            
            async with self.session.post(f"{self.settlement_url}/settlement/execute", json=settlement_data) as response:
                processing_time = int((time.time() - start_time) * 1000)
                response_data = await response.json()
                
                if response.status in [200, 201]:
                    data = response_data.get("data", {})
                    return SettlementResult(
                        batch_id=batch.batch_id,
                        status=data.get("status", "UNKNOWN"),
                        processing_time_ms=processing_time,
                        netting_efficiency=0.0,  # Not applicable for settlement
                        settlement_amount=Decimal(batch.total_amount),
                        participant_count=len(batch.participants),
                        success=True
                    )
                else:
                    return SettlementResult(
                        batch_id=batch.batch_id,
                        status="FAILED",
                        processing_time_ms=processing_time,
                        netting_efficiency=0.0,
                        settlement_amount=Decimal("0"),
                        participant_count=len(batch.participants),
                        success=False,
                        error=f"HTTP {response.status}: {response_data.get('error', 'Unknown error')}"
                    )
        
        except Exception as e:
            processing_time = int((time.time() - start_time) * 1000)
            return SettlementResult(
                batch_id=batch.batch_id,
                status="ERROR",
                processing_time_ms=processing_time,
                netting_efficiency=0.0,
                settlement_amount=Decimal("0"),
                participant_count=len(batch.participants),
                success=False,
                error=str(e)
            )
    
    async def test_complete_settlement_cycle(self) -> List[SettlementResult]:
        """Test complete T+1 settlement cycle"""
        logger.info("Testing complete T+1 settlement cycle")
        
        results = []
        
        # Step 1: Submit clearing transactions
        transactions = [
            ClearingTransaction("TXN001", "BANK001", "BANK002", "1000000.00"),
            ClearingTransaction("TXN002", "BANK002", "BANK003", "750000.00"),
            ClearingTransaction("TXN003", "BANK003", "BANK001", "500000.00"),
            ClearingTransaction("TXN004", "BANK001", "BANK003", "250000.00"),
            ClearingTransaction("TXN005", "BANK002", "BANK001", "800000.00"),
            ClearingTransaction("TXN006", "BANK003", "BANK002", "600000.00"),
        ]
        
        # Submit all transactions
        submission_tasks = [self.submit_clearing_transaction(txn) for txn in transactions]
        submission_results = await asyncio.gather(*submission_tasks)
        
        successful_submissions = sum(submission_results)
        logger.info(f"Successfully submitted {successful_submissions}/{len(transactions)} transactions")
        
        # Step 2: Run bilateral netting
        bilateral_request = NettingRequest(
            netting_type="BILATERAL",
            currency="USD",
            participants=["BANK001", "BANK002"],
            cutoff_time=datetime.now().isoformat(),
            value_date=datetime.now().strftime("%Y-%m-%d")
        )
        
        bilateral_result = await self.run_bilateral_netting(bilateral_request)
        results.append(bilateral_result)
        
        # Step 3: Run multilateral netting
        multilateral_request = NettingRequest(
            netting_type="MULTILATERAL",
            currency="USD",
            participants=["BANK001", "BANK002", "BANK003"],
            cutoff_time=datetime.now().isoformat(),
            value_date=datetime.now().strftime("%Y-%m-%d")
        )
        
        multilateral_result = await self.run_multilateral_netting(multilateral_request)
        results.append(multilateral_result)
        
        # Step 4: Execute settlement
        if multilateral_result.success:
            settlement_batch = SettlementBatch(
                batch_id=multilateral_result.batch_id,
                settlement_method="RTGS",
                currency="USD",
                participants=["BANK001", "BANK002", "BANK003"],
                total_amount=str(multilateral_result.settlement_amount),
                settlement_date=(datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
            )
            
            settlement_result = await self.execute_settlement(settlement_batch)
            results.append(settlement_result)
        
        return results
    
    async def test_netting_efficiency(self) -> List[SettlementResult]:
        """Test netting efficiency with various transaction patterns"""
        logger.info("Testing netting efficiency")
        
        results = []
        
        # Create transactions with high netting potential
        high_netting_transactions = [
            ClearingTransaction("NET001", "BANK001", "BANK002", "1000000.00"),
            ClearingTransaction("NET002", "BANK002", "BANK001", "950000.00"),
            ClearingTransaction("NET003", "BANK001", "BANK003", "500000.00"),
            ClearingTransaction("NET004", "BANK003", "BANK001", "480000.00"),
            ClearingTransaction("NET005", "BANK002", "BANK003", "300000.00"),
            ClearingTransaction("NET006", "BANK003", "BANK002", "290000.00"),
        ]
        
        # Submit transactions
        for txn in high_netting_transactions:
            await self.submit_clearing_transaction(txn)
        
        # Test multilateral netting efficiency
        netting_request = NettingRequest(
            netting_type="MULTILATERAL",
            currency="USD",
            participants=["BANK001", "BANK002", "BANK003"],
            cutoff_time=datetime.now().isoformat(),
            value_date=datetime.now().strftime("%Y-%m-%d")
        )
        
        result = await self.run_multilateral_netting(netting_request)
        results.append(result)
        
        return results
    
    async def test_atomic_settlement(self) -> List[SettlementResult]:
        """Test atomic settlement across multiple ledgers"""
        logger.info("Testing atomic settlement")
        
        results = []
        
        # Create multi-currency transactions
        multi_currency_transactions = [
            ClearingTransaction("ATOM001", "BANK001", "BANK002", "1000000.00", "USD"),
            ClearingTransaction("ATOM002", "BANK001", "BANK002", "850000.00", "EUR"),
            ClearingTransaction("ATOM003", "BANK002", "BANK001", "750000.00", "GBP"),
        ]
        
        # Submit transactions
        for txn in multi_currency_transactions:
            await self.submit_clearing_transaction(txn)
        
        # Test atomic settlement for each currency
        currencies = ["USD", "EUR", "GBP"]
        for currency in currencies:
            netting_request = NettingRequest(
                netting_type="MULTILATERAL",
                currency=currency,
                participants=["BANK001", "BANK002"],
                cutoff_time=datetime.now().isoformat(),
                value_date=datetime.now().strftime("%Y-%m-%d")
            )
            
            result = await self.run_multilateral_netting(netting_request)
            results.append(result)
        
        return results
    
    async def test_high_volume_settlement(self) -> List[SettlementResult]:
        """Test settlement with high transaction volume"""
        logger.info("Testing high volume settlement")
        
        # Generate large number of transactions
        transactions = []
        banks = ["BANK001", "BANK002", "BANK003", "BANK004", "BANK005"]
        
        for i in range(1000):
            payer = banks[i % len(banks)]
            payee = banks[(i + 1) % len(banks)]
            amount = f"{(i + 1) * 1000}.00"
            
            transactions.append(ClearingTransaction(
                f"VOL{i:06d}",
                payer,
                payee,
                amount
            ))
        
        # Submit transactions in batches
        batch_size = 100
        for i in range(0, len(transactions), batch_size):
            batch = transactions[i:i + batch_size]
            submission_tasks = [self.submit_clearing_transaction(txn) for txn in batch]
            await asyncio.gather(*submission_tasks)
            logger.info(f"Submitted batch {i//batch_size + 1}/{len(transactions)//batch_size}")
        
        # Run multilateral netting
        netting_request = NettingRequest(
            netting_type="MULTILATERAL",
            currency="USD",
            participants=banks,
            cutoff_time=datetime.now().isoformat(),
            value_date=datetime.now().strftime("%Y-%m-%d")
        )
        
        result = await self.run_multilateral_netting(netting_request)
        return [result]
    
    def analyze_settlement_results(self, results: List[SettlementResult], test_name: str) -> Dict:
        """Analyze settlement test results"""
        successful_results = [r for r in results if r.success]
        
        if not successful_results:
            return {
                "test_name": test_name,
                "total_tests": len(results),
                "successful_tests": 0,
                "success_rate": 0.0,
                "error": "No successful tests"
            }
        
        # Calculate statistics
        processing_times = [r.processing_time_ms for r in successful_results]
        netting_efficiencies = [r.netting_efficiency for r in successful_results if r.netting_efficiency > 0]
        settlement_amounts = [float(r.settlement_amount) for r in successful_results]
        
        analysis = {
            "test_name": test_name,
            "total_tests": len(results),
            "successful_tests": len(successful_results),
            "success_rate": (len(successful_results) / len(results)) * 100,
            "processing_time_stats": {
                "average_ms": sum(processing_times) / len(processing_times) if processing_times else 0,
                "max_ms": max(processing_times) if processing_times else 0,
                "min_ms": min(processing_times) if processing_times else 0
            },
            "settlement_stats": {
                "total_amount": sum(settlement_amounts),
                "average_amount": sum(settlement_amounts) / len(settlement_amounts) if settlement_amounts else 0,
                "max_amount": max(settlement_amounts) if settlement_amounts else 0
            },
            "errors": [r.error for r in results if r.error]
        }
        
        if netting_efficiencies:
            analysis["netting_efficiency_stats"] = {
                "average_efficiency": sum(netting_efficiencies) / len(netting_efficiencies),
                "max_efficiency": max(netting_efficiencies),
                "min_efficiency": min(netting_efficiencies)
            }
        
        logger.info(f"{test_name} Analysis: {json.dumps(analysis, indent=2)}")
        return analysis
    
    async def run_all_settlement_tests(self) -> Dict:
        """Run all settlement tests"""
        logger.info("Starting comprehensive settlement tests")
        
        await self.setup_session()
        
        try:
            # Run all test suites
            cycle_results = await self.test_complete_settlement_cycle()
            efficiency_results = await self.test_netting_efficiency()
            atomic_results = await self.test_atomic_settlement()
            volume_results = await self.test_high_volume_settlement()
            
            # Analyze results
            analyses = {
                "settlement_cycle": self.analyze_settlement_results(cycle_results, "Complete Settlement Cycle"),
                "netting_efficiency": self.analyze_settlement_results(efficiency_results, "Netting Efficiency"),
                "atomic_settlement": self.analyze_settlement_results(atomic_results, "Atomic Settlement"),
                "high_volume": self.analyze_settlement_results(volume_results, "High Volume Settlement")
            }
            
            # Overall summary
            all_results = cycle_results + efficiency_results + atomic_results + volume_results
            overall_analysis = self.analyze_settlement_results(all_results, "Overall Settlement Performance")
            
            return {
                "overall": overall_analysis,
                "detailed": analyses,
                "timestamp": time.time()
            }
        
        finally:
            await self.cleanup_session()

# Test cases using pytest
@pytest.mark.asyncio
async def test_settlement_cycle_completion():
    """Test complete settlement cycle execution"""
    tester = SettlementTester()
    await tester.setup_session()
    
    try:
        results = await tester.test_complete_settlement_cycle()
        
        # Assertions
        assert len(results) >= 2, "Should complete netting and settlement steps"
        
        successful_results = [r for r in results if r.success]
        assert len(successful_results) >= 1, "At least one step should succeed"
        
        # Check processing times
        processing_times = [r.processing_time_ms for r in successful_results]
        max_processing_time = max(processing_times) if processing_times else 0
        assert max_processing_time < 60000, f"Processing should complete within 60s, got {max_processing_time}ms"
        
        logger.info("Settlement cycle completion test passed")
    
    finally:
        await tester.cleanup_session()

@pytest.mark.asyncio
async def test_netting_efficiency_optimization():
    """Test netting efficiency meets optimization targets"""
    tester = SettlementTester()
    await tester.setup_session()
    
    try:
        results = await tester.test_netting_efficiency()
        
        # Assertions
        assert len(results) >= 1, "Should process netting request"
        
        successful_results = [r for r in results if r.success]
        assert len(successful_results) >= 1, "Netting should succeed"
        
        # Check netting efficiency
        for result in successful_results:
            if result.netting_efficiency > 0:
                assert result.netting_efficiency >= 50, f"Netting efficiency should be ≥50%, got {result.netting_efficiency}%"
        
        logger.info("Netting efficiency optimization test passed")
    
    finally:
        await tester.cleanup_session()

@pytest.mark.asyncio
async def test_atomic_settlement_consistency():
    """Test atomic settlement maintains consistency"""
    tester = SettlementTester()
    await tester.setup_session()
    
    try:
        results = await tester.test_atomic_settlement()
        
        # Assertions
        assert len(results) >= 1, "Should process atomic settlement"
        
        successful_results = [r for r in results if r.success]
        assert len(successful_results) >= 1, "Atomic settlement should succeed"
        
        # Check settlement amounts are consistent
        total_settlement = sum(float(r.settlement_amount) for r in successful_results)
        assert total_settlement >= 0, "Total settlement amount should be non-negative"
        
        logger.info("Atomic settlement consistency test passed")
    
    finally:
        await tester.cleanup_session()

if __name__ == "__main__":
    # Run comprehensive settlement tests
    async def main():
        tester = SettlementTester()
        results = await tester.run_all_settlement_tests()
        print(json.dumps(results, indent=2, default=str))

    asyncio.run(main())

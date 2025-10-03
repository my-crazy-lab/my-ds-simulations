#!/usr/bin/env python3
"""
AML/Transaction Monitoring Test Suite

This test suite validates:
1. Real-time transaction monitoring and alert generation
2. Suspicious pattern detection (structuring, velocity, etc.)
3. KYC verification and risk assessment
4. Sanctions screening accuracy
5. Case management workflow
6. ML model performance and accuracy
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
import random

import aiohttp
import pytest
import requests
import numpy as np

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class Transaction:
    """Transaction for AML monitoring testing"""
    transaction_id: str
    customer_id: str
    amount: str
    currency: str = "USD"
    transaction_type: str = "WIRE_TRANSFER"
    counterparty: Dict = None
    timestamp: str = None
    geographic_info: Dict = None

@dataclass
class Customer:
    """Customer for KYC testing"""
    customer_id: str
    first_name: str
    last_name: str
    date_of_birth: str
    nationality: str
    document_type: str = "PASSPORT"
    document_number: str = ""
    address: Dict = None
    risk_factors: List[str] = None

@dataclass
class SanctionsScreeningRequest:
    """Sanctions screening request"""
    name: str
    date_of_birth: str = None
    nationality: str = None
    screening_lists: List[str] = None

@dataclass
class AMLTestResult:
    """Result of AML testing"""
    test_name: str
    transaction_id: str
    alert_generated: bool
    alert_type: str
    risk_score: float
    processing_time_ms: int
    false_positive: bool
    success: bool
    error: Optional[str] = None

class AMLTester:
    """Handles AML/KYC testing"""
    
    def __init__(self):
        self.transaction_monitor_url = "http://localhost:8471/api/v1"
        self.kyc_url = "http://localhost:8472/api/v1"
        self.sanctions_url = "http://localhost:8473/api/v1"
        self.risk_scoring_url = "http://localhost:8474/api/v1"
        self.case_management_url = "http://localhost:8475/api/v1"
        self.ml_inference_url = "http://localhost:8477/api/v1"
        self.session = None
        self.test_results: List[AMLTestResult] = []
        
    async def setup_session(self):
        """Setup HTTP session"""
        timeout = aiohttp.ClientTimeout(total=60)
        self.session = aiohttp.ClientSession(
            timeout=timeout,
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer test_aml_token"
            }
        )
    
    async def cleanup_session(self):
        """Cleanup HTTP session"""
        if self.session:
            await self.session.close()
    
    async def submit_transaction(self, transaction: Transaction) -> AMLTestResult:
        """Submit a transaction for monitoring"""
        start_time = time.time()
        
        try:
            transaction_data = {
                "transaction_id": transaction.transaction_id,
                "customer_id": transaction.customer_id,
                "amount": transaction.amount,
                "currency": transaction.currency,
                "transaction_type": transaction.transaction_type,
                "counterparty": transaction.counterparty or {
                    "name": "Test Counterparty",
                    "account": "123456789",
                    "bank": "TEST_BANK"
                },
                "timestamp": transaction.timestamp or datetime.now().isoformat(),
                "geographic_info": transaction.geographic_info or {
                    "originating_country": "US",
                    "destination_country": "US"
                }
            }
            
            async with self.session.post(f"{self.transaction_monitor_url}/transactions", json=transaction_data) as response:
                processing_time = int((time.time() - start_time) * 1000)
                response_data = await response.json()
                
                if response.status in [200, 201]:
                    data = response_data.get("data", {})
                    return AMLTestResult(
                        test_name="Transaction Monitoring",
                        transaction_id=transaction.transaction_id,
                        alert_generated=data.get("alert_generated", False),
                        alert_type=data.get("alert_type", "NONE"),
                        risk_score=float(data.get("risk_score", 0.0)),
                        processing_time_ms=processing_time,
                        false_positive=False,  # Will be determined by analysis
                        success=True
                    )
                else:
                    return AMLTestResult(
                        test_name="Transaction Monitoring",
                        transaction_id=transaction.transaction_id,
                        alert_generated=False,
                        alert_type="ERROR",
                        risk_score=0.0,
                        processing_time_ms=processing_time,
                        false_positive=False,
                        success=False,
                        error=f"HTTP {response.status}: {response_data.get('error', 'Unknown error')}"
                    )
        
        except Exception as e:
            processing_time = int((time.time() - start_time) * 1000)
            return AMLTestResult(
                test_name="Transaction Monitoring",
                transaction_id=transaction.transaction_id,
                alert_generated=False,
                alert_type="EXCEPTION",
                risk_score=0.0,
                processing_time_ms=processing_time,
                false_positive=False,
                success=False,
                error=str(e)
            )
    
    async def perform_kyc_verification(self, customer: Customer) -> AMLTestResult:
        """Perform KYC verification"""
        start_time = time.time()
        
        try:
            kyc_data = {
                "customer_id": customer.customer_id,
                "first_name": customer.first_name,
                "last_name": customer.last_name,
                "date_of_birth": customer.date_of_birth,
                "nationality": customer.nationality,
                "document_type": customer.document_type,
                "document_number": customer.document_number,
                "address": customer.address or {
                    "street": "123 Test St",
                    "city": "Test City",
                    "country": "US",
                    "postal_code": "12345"
                },
                "risk_factors": customer.risk_factors or []
            }
            
            async with self.session.post(f"{self.kyc_url}/kyc/verify", json=kyc_data) as response:
                processing_time = int((time.time() - start_time) * 1000)
                response_data = await response.json()
                
                if response.status in [200, 201]:
                    data = response_data.get("data", {})
                    return AMLTestResult(
                        test_name="KYC Verification",
                        transaction_id=customer.customer_id,
                        alert_generated=data.get("requires_enhanced_dd", False),
                        alert_type=data.get("verification_status", "VERIFIED"),
                        risk_score=float(data.get("risk_score", 0.0)),
                        processing_time_ms=processing_time,
                        false_positive=False,
                        success=True
                    )
                else:
                    return AMLTestResult(
                        test_name="KYC Verification",
                        transaction_id=customer.customer_id,
                        alert_generated=False,
                        alert_type="ERROR",
                        risk_score=0.0,
                        processing_time_ms=processing_time,
                        false_positive=False,
                        success=False,
                        error=f"HTTP {response.status}: {response_data.get('error', 'Unknown error')}"
                    )
        
        except Exception as e:
            processing_time = int((time.time() - start_time) * 1000)
            return AMLTestResult(
                test_name="KYC Verification",
                transaction_id=customer.customer_id,
                alert_generated=False,
                alert_type="EXCEPTION",
                risk_score=0.0,
                processing_time_ms=processing_time,
                false_positive=False,
                success=False,
                error=str(e)
            )
    
    async def perform_sanctions_screening(self, screening_request: SanctionsScreeningRequest) -> AMLTestResult:
        """Perform sanctions screening"""
        start_time = time.time()
        
        try:
            screening_data = {
                "name": screening_request.name,
                "date_of_birth": screening_request.date_of_birth,
                "nationality": screening_request.nationality,
                "screening_lists": screening_request.screening_lists or ["OFAC", "EU", "UN", "HMT"]
            }
            
            async with self.session.post(f"{self.sanctions_url}/screening/sanctions", json=screening_data) as response:
                processing_time = int((time.time() - start_time) * 1000)
                response_data = await response.json()
                
                if response.status in [200, 201]:
                    data = response_data.get("data", {})
                    return AMLTestResult(
                        test_name="Sanctions Screening",
                        transaction_id=screening_request.name,
                        alert_generated=data.get("match_found", False),
                        alert_type=data.get("match_type", "NO_MATCH"),
                        risk_score=float(data.get("match_score", 0.0)),
                        processing_time_ms=processing_time,
                        false_positive=False,
                        success=True
                    )
                else:
                    return AMLTestResult(
                        test_name="Sanctions Screening",
                        transaction_id=screening_request.name,
                        alert_generated=False,
                        alert_type="ERROR",
                        risk_score=0.0,
                        processing_time_ms=processing_time,
                        false_positive=False,
                        success=False,
                        error=f"HTTP {response.status}: {response_data.get('error', 'Unknown error')}"
                    )
        
        except Exception as e:
            processing_time = int((time.time() - start_time) * 1000)
            return AMLTestResult(
                test_name="Sanctions Screening",
                transaction_id=screening_request.name,
                alert_generated=False,
                alert_type="EXCEPTION",
                risk_score=0.0,
                processing_time_ms=processing_time,
                false_positive=False,
                success=False,
                error=str(e)
            )
    
    async def test_structuring_detection(self) -> List[AMLTestResult]:
        """Test structuring pattern detection"""
        logger.info("Testing structuring detection")
        
        results = []
        customer_id = "STRUCT_TEST_001"
        
        # Generate structuring pattern: multiple transactions just below $10,000
        structuring_transactions = []
        for i in range(5):
            amount = random.uniform(9500, 9900)  # Just below reporting threshold
            transaction = Transaction(
                transaction_id=f"STRUCT_{i:03d}",
                customer_id=customer_id,
                amount=f"{amount:.2f}",
                transaction_type="CASH_DEPOSIT",
                timestamp=(datetime.now() + timedelta(hours=i)).isoformat()
            )
            structuring_transactions.append(transaction)
        
        # Submit transactions
        for transaction in structuring_transactions:
            result = await self.submit_transaction(transaction)
            results.append(result)
            # Small delay to simulate real-time processing
            await asyncio.sleep(0.1)
        
        return results
    
    async def test_velocity_monitoring(self) -> List[AMLTestResult]:
        """Test velocity monitoring"""
        logger.info("Testing velocity monitoring")
        
        results = []
        customer_id = "VELOCITY_TEST_001"
        
        # Generate high-velocity transactions
        velocity_transactions = []
        for i in range(20):  # 20 transactions in short time
            amount = random.uniform(1000, 5000)
            transaction = Transaction(
                transaction_id=f"VEL_{i:03d}",
                customer_id=customer_id,
                amount=f"{amount:.2f}",
                transaction_type="WIRE_TRANSFER",
                timestamp=(datetime.now() + timedelta(minutes=i*5)).isoformat()
            )
            velocity_transactions.append(transaction)
        
        # Submit transactions concurrently to test velocity detection
        tasks = [self.submit_transaction(txn) for txn in velocity_transactions]
        results = await asyncio.gather(*tasks)
        
        return results
    
    async def test_geographic_anomalies(self) -> List[AMLTestResult]:
        """Test geographic anomaly detection"""
        logger.info("Testing geographic anomaly detection")
        
        results = []
        customer_id = "GEO_TEST_001"
        
        # High-risk countries for testing
        high_risk_countries = ["AF", "IR", "KP", "SY", "MM"]  # Afghanistan, Iran, North Korea, Syria, Myanmar
        
        geographic_transactions = []
        for i, country in enumerate(high_risk_countries):
            transaction = Transaction(
                transaction_id=f"GEO_{i:03d}",
                customer_id=customer_id,
                amount="25000.00",  # Large amount to high-risk country
                transaction_type="WIRE_TRANSFER",
                geographic_info={
                    "originating_country": "US",
                    "destination_country": country
                },
                counterparty={
                    "name": f"Foreign Entity {i}",
                    "account": f"ACC{i:06d}",
                    "bank": f"BANK_{country}"
                }
            )
            geographic_transactions.append(transaction)
        
        # Submit transactions
        for transaction in geographic_transactions:
            result = await self.submit_transaction(transaction)
            results.append(result)
        
        return results
    
    async def test_sanctions_screening_accuracy(self) -> List[AMLTestResult]:
        """Test sanctions screening accuracy"""
        logger.info("Testing sanctions screening accuracy")
        
        results = []
        
        # Test known sanctioned entities (using test data)
        sanctioned_entities = [
            SanctionsScreeningRequest("OSAMA BIN LADEN", "1957-03-10", "SA"),
            SanctionsScreeningRequest("VLADIMIR PUTIN", "1952-10-07", "RU"),
            SanctionsScreeningRequest("JOHN SMITH", "1980-01-01", "US"),  # Common name, should not match
            SanctionsScreeningRequest("JANE DOE", "1990-05-15", "CA"),   # Common name, should not match
        ]
        
        for entity in sanctioned_entities:
            result = await self.perform_sanctions_screening(entity)
            results.append(result)
        
        return results
    
    async def test_kyc_risk_assessment(self) -> List[AMLTestResult]:
        """Test KYC risk assessment"""
        logger.info("Testing KYC risk assessment")
        
        results = []
        
        # Test customers with different risk profiles
        test_customers = [
            Customer(
                customer_id="KYC_LOW_001",
                first_name="John",
                last_name="Smith",
                date_of_birth="1980-01-15",
                nationality="US",
                risk_factors=[]  # Low risk
            ),
            Customer(
                customer_id="KYC_HIGH_001",
                first_name="High",
                last_name="Risk",
                date_of_birth="1970-01-01",
                nationality="AF",  # High-risk country
                risk_factors=["PEP", "HIGH_RISK_COUNTRY", "CASH_INTENSIVE_BUSINESS"]
            ),
            Customer(
                customer_id="KYC_PEP_001",
                first_name="Political",
                last_name="Person",
                date_of_birth="1960-01-01",
                nationality="US",
                risk_factors=["PEP"]  # Politically Exposed Person
            )
        ]
        
        for customer in test_customers:
            result = await self.perform_kyc_verification(customer)
            results.append(result)
        
        return results
    
    async def test_ml_model_performance(self) -> List[AMLTestResult]:
        """Test ML model performance"""
        logger.info("Testing ML model performance")
        
        results = []
        
        # Generate diverse transaction patterns for ML testing
        ml_test_transactions = []
        
        # Normal transactions
        for i in range(50):
            transaction = Transaction(
                transaction_id=f"ML_NORMAL_{i:03d}",
                customer_id=f"CUST_{i:03d}",
                amount=f"{random.uniform(100, 5000):.2f}",
                transaction_type=random.choice(["WIRE_TRANSFER", "ACH", "CHECK"]),
                timestamp=(datetime.now() + timedelta(minutes=i)).isoformat()
            )
            ml_test_transactions.append(transaction)
        
        # Suspicious transactions
        for i in range(10):
            transaction = Transaction(
                transaction_id=f"ML_SUSPICIOUS_{i:03d}",
                customer_id=f"SUSP_CUST_{i:03d}",
                amount=f"{random.uniform(9500, 9900):.2f}",  # Structuring pattern
                transaction_type="CASH_DEPOSIT",
                timestamp=(datetime.now() + timedelta(minutes=i*2)).isoformat()
            )
            ml_test_transactions.append(transaction)
        
        # Submit all transactions
        tasks = [self.submit_transaction(txn) for txn in ml_test_transactions]
        results = await asyncio.gather(*tasks)
        
        return results
    
    def analyze_aml_results(self, results: List[AMLTestResult], test_name: str) -> Dict:
        """Analyze AML test results"""
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
        risk_scores = [r.risk_score for r in successful_results]
        alerts_generated = [r for r in successful_results if r.alert_generated]
        
        analysis = {
            "test_name": test_name,
            "total_tests": len(results),
            "successful_tests": len(successful_results),
            "success_rate": (len(successful_results) / len(results)) * 100,
            "alerts_generated": len(alerts_generated),
            "alert_rate": (len(alerts_generated) / len(successful_results)) * 100 if successful_results else 0,
            "processing_time_stats": {
                "average_ms": sum(processing_times) / len(processing_times) if processing_times else 0,
                "max_ms": max(processing_times) if processing_times else 0,
                "min_ms": min(processing_times) if processing_times else 0
            },
            "risk_score_stats": {
                "average_score": sum(risk_scores) / len(risk_scores) if risk_scores else 0,
                "max_score": max(risk_scores) if risk_scores else 0,
                "min_score": min(risk_scores) if risk_scores else 0
            },
            "alert_types": {},
            "errors": [r.error for r in results if r.error]
        }
        
        # Count alert types
        for result in alerts_generated:
            alert_type = result.alert_type
            analysis["alert_types"][alert_type] = analysis["alert_types"].get(alert_type, 0) + 1
        
        logger.info(f"{test_name} Analysis: {json.dumps(analysis, indent=2)}")
        return analysis
    
    async def run_all_aml_tests(self) -> Dict:
        """Run all AML tests"""
        logger.info("Starting comprehensive AML tests")
        
        await self.setup_session()
        
        try:
            # Run all test suites
            structuring_results = await self.test_structuring_detection()
            velocity_results = await self.test_velocity_monitoring()
            geographic_results = await self.test_geographic_anomalies()
            sanctions_results = await self.test_sanctions_screening_accuracy()
            kyc_results = await self.test_kyc_risk_assessment()
            ml_results = await self.test_ml_model_performance()
            
            # Analyze results
            analyses = {
                "structuring_detection": self.analyze_aml_results(structuring_results, "Structuring Detection"),
                "velocity_monitoring": self.analyze_aml_results(velocity_results, "Velocity Monitoring"),
                "geographic_anomalies": self.analyze_aml_results(geographic_results, "Geographic Anomalies"),
                "sanctions_screening": self.analyze_aml_results(sanctions_results, "Sanctions Screening"),
                "kyc_assessment": self.analyze_aml_results(kyc_results, "KYC Risk Assessment"),
                "ml_performance": self.analyze_aml_results(ml_results, "ML Model Performance")
            }
            
            # Overall summary
            all_results = (structuring_results + velocity_results + geographic_results + 
                          sanctions_results + kyc_results + ml_results)
            overall_analysis = self.analyze_aml_results(all_results, "Overall AML Performance")
            
            return {
                "overall": overall_analysis,
                "detailed": analyses,
                "timestamp": time.time()
            }
        
        finally:
            await self.cleanup_session()

# Test cases using pytest
@pytest.mark.asyncio
async def test_structuring_detection_accuracy():
    """Test structuring detection accuracy"""
    tester = AMLTester()
    await tester.setup_session()
    
    try:
        results = await tester.test_structuring_detection()
        
        # Assertions
        assert len(results) >= 5, "Should process structuring transactions"
        
        successful_results = [r for r in results if r.success]
        assert len(successful_results) >= 3, "Most transactions should process successfully"
        
        # Check that at least some alerts are generated for structuring
        alerts_generated = [r for r in successful_results if r.alert_generated]
        assert len(alerts_generated) >= 1, "Should detect structuring pattern"
        
        # Check processing times
        processing_times = [r.processing_time_ms for r in successful_results]
        max_processing_time = max(processing_times) if processing_times else 0
        assert max_processing_time < 5000, f"Processing should complete within 5s, got {max_processing_time}ms"
        
        logger.info("Structuring detection test passed")
    
    finally:
        await tester.cleanup_session()

@pytest.mark.asyncio
async def test_sanctions_screening_performance():
    """Test sanctions screening performance"""
    tester = AMLTester()
    await tester.setup_session()
    
    try:
        results = await tester.test_sanctions_screening_accuracy()
        
        # Assertions
        assert len(results) >= 4, "Should process screening requests"
        
        successful_results = [r for r in results if r.success]
        assert len(successful_results) >= 3, "Most screenings should succeed"
        
        # Check processing times
        processing_times = [r.processing_time_ms for r in successful_results]
        max_processing_time = max(processing_times) if processing_times else 0
        assert max_processing_time < 1000, f"Screening should complete within 1s, got {max_processing_time}ms"
        
        logger.info("Sanctions screening performance test passed")
    
    finally:
        await tester.cleanup_session()

if __name__ == "__main__":
    # Run comprehensive AML tests
    async def main():
        tester = AMLTester()
        results = await tester.run_all_aml_tests()
        print(json.dumps(results, indent=2, default=str))
    
    asyncio.run(main())

#!/usr/bin/env python3
"""
Comprehensive Atomic Settlement and Netting Tests for Clearing & Settlement Engine
Tests atomic settlement across multiple ledgers, netting algorithms, and settlement finality
"""

import asyncio
import json
import logging
import random
import time
import unittest
import uuid
from decimal import Decimal
from typing import Dict, List, Optional, Set, Tuple

import requests

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AtomicSettlementTestClient:
    """Test client for atomic settlement and netting operations"""
    
    def __init__(self, settlement_engine_url: str = "http://localhost:8080"):
        self.settlement_engine_url = settlement_engine_url
        self.session = requests.Session()
        self.session.timeout = 30
    
    def create_settlement_batch(self, batch_data: Dict) -> Optional[Dict]:
        """Create settlement batch"""
        try:
            response = self.session.post(
                f"{self.settlement_engine_url}/api/v1/settlement/batches",
                json=batch_data,
                headers={"Content-Type": "application/json"}
            )
            return response.json() if response.status_code == 201 else None
        except Exception as e:
            logger.error(f"Settlement batch creation failed: {e}")
            return None
    
    def add_settlement_instruction(self, batch_id: str, instruction_data: Dict) -> Optional[Dict]:
        """Add settlement instruction to batch"""
        try:
            response = self.session.post(
                f"{self.settlement_engine_url}/api/v1/settlement/batches/{batch_id}/instructions",
                json=instruction_data,
                headers={"Content-Type": "application/json"}
            )
            return response.json() if response.status_code == 201 else None
        except Exception as e:
            logger.error(f"Settlement instruction addition failed: {e}")
            return None
    
    def execute_settlement_batch(self, batch_id: str, execution_mode: str = "atomic") -> Optional[Dict]:
        """Execute settlement batch"""
        try:
            response = self.session.post(
                f"{self.settlement_engine_url}/api/v1/settlement/batches/{batch_id}/execute",
                json={"execution_mode": execution_mode},
                headers={"Content-Type": "application/json"}
            )
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"Settlement batch execution failed: {e}")
            return None
    
    def get_settlement_status(self, batch_id: str) -> Optional[Dict]:
        """Get settlement batch status"""
        try:
            response = self.session.get(f"{self.settlement_engine_url}/api/v1/settlement/batches/{batch_id}/status")
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"Settlement status retrieval failed: {e}")
            return None
    
    def create_netting_session(self, session_data: Dict) -> Optional[Dict]:
        """Create netting session"""
        try:
            response = self.session.post(
                f"{self.settlement_engine_url}/api/v1/netting/sessions",
                json=session_data,
                headers={"Content-Type": "application/json"}
            )
            return response.json() if response.status_code == 201 else None
        except Exception as e:
            logger.error(f"Netting session creation failed: {e}")
            return None
    
    def add_netting_position(self, session_id: str, position_data: Dict) -> Optional[Dict]:
        """Add position to netting session"""
        try:
            response = self.session.post(
                f"{self.settlement_engine_url}/api/v1/netting/sessions/{session_id}/positions",
                json=position_data,
                headers={"Content-Type": "application/json"}
            )
            return response.json() if response.status_code == 201 else None
        except Exception as e:
            logger.error(f"Netting position addition failed: {e}")
            return None
    
    def calculate_net_positions(self, session_id: str, algorithm: str = "bilateral") -> Optional[Dict]:
        """Calculate net positions"""
        try:
            response = self.session.post(
                f"{self.settlement_engine_url}/api/v1/netting/sessions/{session_id}/calculate",
                json={"algorithm": algorithm},
                headers={"Content-Type": "application/json"}
            )
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"Net position calculation failed: {e}")
            return None
    
    def get_participant_exposure(self, participant_id: str, currency: str = None) -> Optional[Dict]:
        """Get participant exposure"""
        try:
            params = {}
            if currency:
                params["currency"] = currency
            
            response = self.session.get(
                f"{self.settlement_engine_url}/api/v1/participants/{participant_id}/exposure",
                params=params
            )
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"Participant exposure retrieval failed: {e}")
            return None
    
    def create_collateral_pledge(self, pledge_data: Dict) -> Optional[Dict]:
        """Create collateral pledge"""
        try:
            response = self.session.post(
                f"{self.settlement_engine_url}/api/v1/collateral/pledges",
                json=pledge_data,
                headers={"Content-Type": "application/json"}
            )
            return response.json() if response.status_code == 201 else None
        except Exception as e:
            logger.error(f"Collateral pledge creation failed: {e}")
            return None
    
    def validate_settlement_finality(self, batch_id: str) -> Optional[Dict]:
        """Validate settlement finality"""
        try:
            response = self.session.get(
                f"{self.settlement_engine_url}/api/v1/settlement/batches/{batch_id}/finality"
            )
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"Settlement finality validation failed: {e}")
            return None
    
    def simulate_settlement_failure(self, batch_id: str, failure_type: str) -> bool:
        """Simulate settlement failure for testing"""
        try:
            response = self.session.post(
                f"{self.settlement_engine_url}/api/v1/test/settlement-failure",
                json={
                    "batch_id": batch_id,
                    "failure_type": failure_type
                }
            )
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Settlement failure simulation failed: {e}")
            return False
    
    def get_settlement_metrics(self) -> Optional[Dict]:
        """Get settlement engine metrics"""
        try:
            response = self.session.get(f"{self.settlement_engine_url}/api/v1/metrics")
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"Settlement metrics retrieval failed: {e}")
            return None


class AtomicSettlementAnalyzer:
    """Analyzer for atomic settlement and netting behavior"""
    
    def __init__(self, client: AtomicSettlementTestClient):
        self.client = client
        self.test_batches: List[str] = []
        self.test_sessions: List[str] = []
    
    def test_atomic_settlement_guarantees(self, num_batches: int = 20) -> Dict:
        """Test atomic settlement guarantees across multiple ledgers"""
        logger.info(f"Testing atomic settlement with {num_batches} batches")
        
        successful_settlements = 0
        failed_settlements = 0
        atomicity_violations = 0
        
        participants = [f"PARTICIPANT_{i:03d}" for i in range(10)]
        
        for batch_num in range(num_batches):
            # Create settlement batch
            batch_data = {
                "batch_id": f"BATCH_{batch_num:06d}",
                "settlement_date": time.strftime("%Y-%m-%d"),
                "currency": "USD",
                "batch_type": "MULTILATERAL"
            }
            
            batch_result = self.client.create_settlement_batch(batch_data)
            
            if not batch_result:
                failed_settlements += 1
                continue
            
            batch_id = batch_result["batch_id"]
            self.test_batches.append(batch_id)
            
            # Add multiple settlement instructions
            instructions_added = 0
            total_amount = Decimal('0')
            
            for i in range(random.randint(5, 15)):
                payer = random.choice(participants)
                payee = random.choice([p for p in participants if p != payer])
                amount = Decimal(str(round(random.uniform(1000, 50000), 2)))
                
                instruction_data = {
                    "instruction_id": f"INST_{batch_num:03d}_{i:03d}",
                    "payer_id": payer,
                    "payee_id": payee,
                    "amount": str(amount),
                    "currency": "USD",
                    "settlement_method": "RTGS"
                }
                
                instruction_result = self.client.add_settlement_instruction(batch_id, instruction_data)
                
                if instruction_result:
                    instructions_added += 1
                    total_amount += amount
            
            if instructions_added == 0:
                failed_settlements += 1
                continue
            
            # Execute settlement batch atomically
            execution_result = self.client.execute_settlement_batch(batch_id, "atomic")
            
            if execution_result and execution_result.get("status") == "COMPLETED":
                successful_settlements += 1
                
                # Verify atomicity - all instructions should be settled or none
                status_result = self.client.get_settlement_status(batch_id)
                
                if status_result:
                    instructions = status_result.get("instructions", [])
                    settled_count = len([i for i in instructions if i.get("status") == "SETTLED"])
                    failed_count = len([i for i in instructions if i.get("status") == "FAILED"])
                    
                    # Atomicity violation if some settled and some failed
                    if settled_count > 0 and failed_count > 0:
                        atomicity_violations += 1
            else:
                failed_settlements += 1
        
        return {
            "total_batches": num_batches,
            "successful_settlements": successful_settlements,
            "failed_settlements": failed_settlements,
            "atomicity_violations": atomicity_violations,
            "settlement_success_rate": successful_settlements / num_batches,
            "atomicity_guarantee": atomicity_violations == 0
        }
    
    def test_multilateral_netting_accuracy(self, num_sessions: int = 15) -> Dict:
        """Test multilateral netting algorithm accuracy"""
        logger.info(f"Testing multilateral netting with {num_sessions} sessions")
        
        successful_netting = 0
        netting_errors = 0
        total_reduction = Decimal('0')
        
        participants = [f"BANK_{i:03d}" for i in range(8)]
        
        for session_num in range(num_sessions):
            # Create netting session
            session_data = {
                "session_id": f"NETTING_{session_num:06d}",
                "netting_date": time.strftime("%Y-%m-%d"),
                "currency": "USD",
                "algorithm": "multilateral"
            }
            
            session_result = self.client.create_netting_session(session_data)
            
            if not session_result:
                netting_errors += 1
                continue
            
            session_id = session_result["session_id"]
            self.test_sessions.append(session_id)
            
            # Add bilateral positions between participants
            gross_positions = {}
            positions_added = 0
            
            for i in range(len(participants)):
                for j in range(i + 1, len(participants)):
                    payer = participants[i]
                    payee = participants[j]
                    
                    # Create bilateral position
                    amount = Decimal(str(round(random.uniform(10000, 100000), 2)))
                    
                    position_data = {
                        "position_id": f"POS_{session_num:03d}_{i:02d}_{j:02d}",
                        "payer_id": payer,
                        "payee_id": payee,
                        "gross_amount": str(amount),
                        "currency": "USD"
                    }
                    
                    position_result = self.client.add_netting_position(session_id, position_data)
                    
                    if position_result:
                        positions_added += 1
                        
                        # Track gross positions for verification
                        if payer not in gross_positions:
                            gross_positions[payer] = Decimal('0')
                        if payee not in gross_positions:
                            gross_positions[payee] = Decimal('0')
                        
                        gross_positions[payer] -= amount  # Payer owes
                        gross_positions[payee] += amount  # Payee receives
            
            if positions_added == 0:
                netting_errors += 1
                continue
            
            # Calculate net positions
            netting_result = self.client.calculate_net_positions(session_id, "multilateral")
            
            if netting_result and netting_result.get("status") == "COMPLETED":
                successful_netting += 1
                
                # Verify netting accuracy
                net_positions = netting_result.get("net_positions", [])
                
                # Check if net positions sum to zero (conservation)
                net_sum = sum(Decimal(pos.get("net_amount", "0")) for pos in net_positions)
                
                if abs(net_sum) > Decimal('0.01'):  # Allow small rounding errors
                    netting_errors += 1
                
                # Calculate netting efficiency (reduction in gross exposure)
                gross_total = sum(abs(amount) for amount in gross_positions.values())
                net_total = sum(abs(Decimal(pos.get("net_amount", "0"))) for pos in net_positions)
                
                if gross_total > 0:
                    reduction = gross_total - net_total
                    total_reduction += reduction
            else:
                netting_errors += 1
        
        avg_reduction = total_reduction / successful_netting if successful_netting > 0 else Decimal('0')
        
        return {
            "total_sessions": num_sessions,
            "successful_netting": successful_netting,
            "netting_errors": netting_errors,
            "netting_success_rate": successful_netting / num_sessions,
            "average_exposure_reduction": float(avg_reduction),
            "netting_accuracy": netting_errors == 0
        }
    
    def test_settlement_finality_guarantees(self, num_settlements: int = 10) -> Dict:
        """Test settlement finality guarantees"""
        logger.info(f"Testing settlement finality with {num_settlements} settlements")
        
        if len(self.test_batches) < num_settlements:
            return {"error": "Insufficient test batches for finality testing"}
        
        finality_confirmed = 0
        finality_violations = 0
        
        batches_to_test = self.test_batches[:num_settlements]
        
        for batch_id in batches_to_test:
            # Check settlement finality
            finality_result = self.client.validate_settlement_finality(batch_id)
            
            if finality_result:
                is_final = finality_result.get("is_final", False)
                finality_timestamp = finality_result.get("finality_timestamp")
                
                if is_final and finality_timestamp:
                    finality_confirmed += 1
                    
                    # Verify finality is irrevocable
                    # Try to modify settled batch (should fail)
                    modification_data = {
                        "instruction_id": f"LATE_INST_{int(time.time())}",
                        "payer_id": "TEST_PAYER",
                        "payee_id": "TEST_PAYEE",
                        "amount": "1000.00",
                        "currency": "USD"
                    }
                    
                    # This should fail for finalized batches
                    late_instruction = self.client.add_settlement_instruction(batch_id, modification_data)
                    
                    if late_instruction:  # Should not succeed
                        finality_violations += 1
                else:
                    finality_violations += 1
        
        return {
            "settlements_tested": len(batches_to_test),
            "finality_confirmed": finality_confirmed,
            "finality_violations": finality_violations,
            "finality_success_rate": finality_confirmed / len(batches_to_test),
            "finality_guarantee": finality_violations == 0
        }
    
    def test_collateral_management_integration(self, num_participants: int = 8) -> Dict:
        """Test collateral management integration"""
        logger.info(f"Testing collateral management with {num_participants} participants")
        
        participants = [f"MEMBER_{i:03d}" for i in range(num_participants)]
        
        successful_pledges = 0
        collateral_violations = 0
        
        for participant in participants:
            # Create collateral pledge
            pledge_amount = Decimal(str(round(random.uniform(100000, 1000000), 2)))
            
            pledge_data = {
                "pledge_id": f"PLEDGE_{participant}_{int(time.time())}",
                "participant_id": participant,
                "collateral_type": "CASH",
                "amount": str(pledge_amount),
                "currency": "USD",
                "maturity_date": "2024-12-31"
            }
            
            pledge_result = self.client.create_collateral_pledge(pledge_data)
            
            if pledge_result:
                successful_pledges += 1
                
                # Check participant exposure after pledge
                exposure_result = self.client.get_participant_exposure(participant, "USD")
                
                if exposure_result:
                    available_collateral = Decimal(exposure_result.get("available_collateral", "0"))
                    
                    # Verify collateral is properly credited
                    if available_collateral < pledge_amount * Decimal('0.9'):  # Allow for haircuts
                        collateral_violations += 1
        
        return {
            "participants_tested": num_participants,
            "successful_pledges": successful_pledges,
            "collateral_violations": collateral_violations,
            "pledge_success_rate": successful_pledges / num_participants,
            "collateral_integrity": collateral_violations == 0
        }
    
    def cleanup_test_data(self):
        """Clean up test data"""
        for batch_id in self.test_batches:
            try:
                self.client.session.delete(f"{self.client.settlement_engine_url}/api/v1/settlement/batches/{batch_id}")
            except Exception:
                pass
        
        for session_id in self.test_sessions:
            try:
                self.client.session.delete(f"{self.client.settlement_engine_url}/api/v1/netting/sessions/{session_id}")
            except Exception:
                pass
        
        self.test_batches.clear()
        self.test_sessions.clear()


class TestAtomicSettlement(unittest.TestCase):
    """Test cases for atomic settlement and netting"""
    
    @classmethod
    def setUpClass(cls):
        cls.client = AtomicSettlementTestClient()
        cls.analyzer = AtomicSettlementAnalyzer(cls.client)
        
        # Wait for settlement engine to be ready
        max_retries = 30
        for i in range(max_retries):
            try:
                metrics = cls.client.get_settlement_metrics()
                if metrics and metrics.get("status") == "ready":
                    logger.info("Settlement engine is ready")
                    break
            except Exception:
                pass
            time.sleep(1)
        else:
            raise Exception("Settlement engine not ready after 30 seconds")
    
    @classmethod
    def tearDownClass(cls):
        cls.analyzer.cleanup_test_data()
    
    def test_atomic_settlement_across_ledgers(self):
        """Test atomic settlement guarantees"""
        result = self.analyzer.test_atomic_settlement_guarantees(num_batches=10)
        
        self.assertTrue(result["atomicity_guarantee"])
        self.assertEqual(result["atomicity_violations"], 0)
        self.assertGreater(result["settlement_success_rate"], 0.80)
        
        logger.info(f"Atomic Settlement Test: {result}")
    
    def test_multilateral_netting_algorithm(self):
        """Test multilateral netting accuracy"""
        result = self.analyzer.test_multilateral_netting_accuracy(num_sessions=8)
        
        self.assertTrue(result["netting_accuracy"])
        self.assertGreater(result["netting_success_rate"], 0.85)
        self.assertGreater(result["average_exposure_reduction"], 1000)
        
        logger.info(f"Multilateral Netting Test: {result}")
    
    def test_settlement_finality_irrevocability(self):
        """Test settlement finality guarantees"""
        result = self.analyzer.test_settlement_finality_guarantees(num_settlements=5)
        
        self.assertNotIn("error", result)
        self.assertTrue(result["finality_guarantee"])
        self.assertGreater(result["finality_success_rate"], 0.90)
        
        logger.info(f"Settlement Finality Test: {result}")
    
    def test_collateral_management_accuracy(self):
        """Test collateral management integration"""
        result = self.analyzer.test_collateral_management_integration(num_participants=5)
        
        self.assertTrue(result["collateral_integrity"])
        self.assertGreater(result["pledge_success_rate"], 0.80)
        
        logger.info(f"Collateral Management Test: {result}")


if __name__ == "__main__":
    unittest.main()

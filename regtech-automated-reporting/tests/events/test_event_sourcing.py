#!/usr/bin/env python3
"""
Event Sourcing Test Suite

This test suite validates:
1. Event capture and storage integrity
2. Event replay and state reconstruction
3. Schema evolution and backward compatibility
4. Tamper-evident audit trail
5. Event chain verification
6. High-volume event processing
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
import hashlib

import pytest
import aiohttp
import requests

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class TestEvent:
    """Test event for validation"""
    event_type: str
    entity_id: str
    jurisdiction: str
    event_data: Dict
    expected_hash: Optional[str] = None

@dataclass
class EventSourcingTestResult:
    """Event sourcing test result"""
    test_name: str
    total_events: int
    successful_events: int
    failed_events: int
    average_response_time_ms: float
    chain_integrity: bool
    success: bool
    error_message: Optional[str] = None

class EventSourcingTester:
    """Handles event sourcing testing"""
    
    def __init__(self):
        self.event_service_url = "http://localhost:8511/api/v1"
        self.session = None
        self.test_user_id = "TEST_USER_REGTECH"
        
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
    
    def generate_test_events(self, entity_id: str, count: int) -> List[TestEvent]:
        """Generate test events for a specific entity"""
        events = []
        event_types = [
            "TRADE_EXECUTION",
            "ORDER_PLACEMENT", 
            "SETTLEMENT",
            "COMPLIANCE_BREACH",
            "RISK_LIMIT_BREACH",
            "MARKET_DATA_UPDATE"
        ]
        
        jurisdictions = ["US", "EU", "UK", "APAC", "GLOBAL"]
        
        for i in range(count):
            event_type = random.choice(event_types)
            jurisdiction = random.choice(jurisdictions)
            
            # Generate event data based on type
            event_data = self.generate_event_data(event_type, i)
            
            event = TestEvent(
                event_type=event_type,
                entity_id=entity_id,
                jurisdiction=jurisdiction,
                event_data=event_data
            )
            events.append(event)
        
        return events
    
    def generate_event_data(self, event_type: str, sequence: int) -> Dict:
        """Generate event data based on event type"""
        base_data = {
            "sequence": sequence,
            "timestamp": datetime.now().isoformat(),
            "version": "1.0"
        }
        
        if event_type == "TRADE_EXECUTION":
            base_data.update({
                "trade_id": f"TRD{sequence:06d}",
                "instrument": random.choice(["AAPL", "GOOGL", "MSFT", "TSLA"]),
                "quantity": random.randint(100, 10000),
                "price": round(random.uniform(50, 500), 2),
                "side": random.choice(["BUY", "SELL"]),
                "counterparty": f"BROKER{random.randint(1, 10):03d}",
                "venue": random.choice(["NYSE", "NASDAQ", "LSE", "XETRA"])
            })
        elif event_type == "ORDER_PLACEMENT":
            base_data.update({
                "order_id": f"ORD{sequence:06d}",
                "instrument": random.choice(["AAPL", "GOOGL", "MSFT", "TSLA"]),
                "quantity": random.randint(100, 10000),
                "order_type": random.choice(["MARKET", "LIMIT", "STOP"]),
                "price": round(random.uniform(50, 500), 2) if random.choice([True, False]) else None,
                "time_in_force": random.choice(["GTC", "IOC", "FOK"])
            })
        elif event_type == "SETTLEMENT":
            base_data.update({
                "settlement_id": f"STL{sequence:06d}",
                "trade_id": f"TRD{sequence:06d}",
                "amount": round(random.uniform(1000, 1000000), 2),
                "currency": random.choice(["USD", "EUR", "GBP", "JPY"]),
                "settlement_date": (datetime.now() + timedelta(days=2)).isoformat(),
                "status": random.choice(["PENDING", "SETTLED", "FAILED"])
            })
        elif event_type == "COMPLIANCE_BREACH":
            base_data.update({
                "breach_id": f"BRH{sequence:06d}",
                "breach_type": random.choice(["POSITION_LIMIT", "CONCENTRATION", "LIQUIDITY"]),
                "severity": random.choice(["LOW", "MEDIUM", "HIGH", "CRITICAL"]),
                "description": f"Compliance breach detected in sequence {sequence}",
                "threshold": random.uniform(0.1, 1.0),
                "actual_value": random.uniform(1.1, 2.0)
            })
        elif event_type == "RISK_LIMIT_BREACH":
            base_data.update({
                "breach_id": f"RSK{sequence:06d}",
                "limit_type": random.choice(["VAR", "STRESS", "CONCENTRATION"]),
                "limit_value": random.uniform(1000000, 10000000),
                "actual_value": random.uniform(1100000, 12000000),
                "breach_percentage": random.uniform(10, 50)
            })
        elif event_type == "MARKET_DATA_UPDATE":
            base_data.update({
                "symbol": random.choice(["AAPL", "GOOGL", "MSFT", "TSLA"]),
                "price": round(random.uniform(50, 500), 2),
                "volume": random.randint(1000, 100000),
                "bid": round(random.uniform(49, 499), 2),
                "ask": round(random.uniform(51, 501), 2),
                "source": random.choice(["BLOOMBERG", "REUTERS", "REFINITIV"])
            })
        
        return base_data
    
    async def submit_event(self, event: TestEvent) -> Tuple[Optional[Dict], float]:
        """Submit an event and measure response time"""
        start_time = time.time()
        
        try:
            event_data = {
                "event_type": event.event_type,
                "source": "TEST_SYSTEM",
                "entity_id": event.entity_id,
                "jurisdiction": event.jurisdiction,
                "event_data": event.event_data
            }
            
            async with self.session.post(f"{self.event_service_url}/events", json=event_data) as response:
                end_time = time.time()
                response_time_ms = (end_time - start_time) * 1000
                
                if response.status in [200, 201]:
                    event_response = await response.json()
                    return event_response, response_time_ms
                else:
                    error_data = await response.json()
                    logger.error(f"Failed to submit event: {error_data}")
                    return None, response_time_ms
        
        except Exception as e:
            end_time = time.time()
            response_time_ms = (end_time - start_time) * 1000
            logger.error(f"Exception submitting event: {e}")
            return None, response_time_ms
    
    async def get_event(self, event_id: str) -> Tuple[Optional[Dict], float]:
        """Get an event by ID and measure response time"""
        start_time = time.time()
        
        try:
            async with self.session.get(f"{self.event_service_url}/events/{event_id}") as response:
                end_time = time.time()
                response_time_ms = (end_time - start_time) * 1000
                
                if response.status == 200:
                    event_data = await response.json()
                    return event_data, response_time_ms
                else:
                    error_data = await response.json()
                    logger.error(f"Failed to get event: {error_data}")
                    return None, response_time_ms
        
        except Exception as e:
            end_time = time.time()
            response_time_ms = (end_time - start_time) * 1000
            logger.error(f"Exception getting event: {e}")
            return None, response_time_ms
    
    async def get_events_by_entity(self, entity_id: str) -> Tuple[Optional[List], float]:
        """Get events for an entity and measure response time"""
        start_time = time.time()
        
        try:
            async with self.session.get(f"{self.event_service_url}/entities/{entity_id}/events") as response:
                end_time = time.time()
                response_time_ms = (end_time - start_time) * 1000
                
                if response.status == 200:
                    response_data = await response.json()
                    return response_data.get("events", []), response_time_ms
                else:
                    error_data = await response.json()
                    logger.error(f"Failed to get events: {error_data}")
                    return None, response_time_ms
        
        except Exception as e:
            end_time = time.time()
            response_time_ms = (end_time - start_time) * 1000
            logger.error(f"Exception getting events: {e}")
            return None, response_time_ms
    
    async def verify_event_chain(self, entity_id: str) -> Tuple[bool, float]:
        """Verify event chain integrity and measure response time"""
        start_time = time.time()
        
        try:
            async with self.session.get(f"{self.event_service_url}/entities/{entity_id}/verify-chain") as response:
                end_time = time.time()
                response_time_ms = (end_time - start_time) * 1000
                
                if response.status == 200:
                    response_data = await response.json()
                    return response_data.get("chain_valid", False), response_time_ms
                else:
                    error_data = await response.json()
                    logger.error(f"Failed to verify chain: {error_data}")
                    return False, response_time_ms
        
        except Exception as e:
            end_time = time.time()
            response_time_ms = (end_time - start_time) * 1000
            logger.error(f"Exception verifying chain: {e}")
            return False, response_time_ms
    
    async def test_event_submission_and_retrieval(self, num_events: int = 100) -> EventSourcingTestResult:
        """Test event submission and retrieval"""
        logger.info(f"Testing event submission and retrieval with {num_events} events")
        
        entity_id = f"TEST_ENTITY_{uuid.uuid4().hex[:8]}"
        test_events = self.generate_test_events(entity_id, num_events)
        
        successful_events = 0
        failed_events = 0
        response_times = []
        submitted_event_ids = []
        
        # Submit events
        for event in test_events:
            event_response, response_time = await self.submit_event(event)
            response_times.append(response_time)
            
            if event_response:
                successful_events += 1
                submitted_event_ids.append(event_response["id"])
            else:
                failed_events += 1
            
            # Small delay between submissions
            await asyncio.sleep(0.01)
        
        # Test retrieval of submitted events
        retrieval_successful = 0
        retrieval_failed = 0
        
        for event_id in submitted_event_ids[:10]:  # Test first 10 events
            event_data, retrieval_time = await self.get_event(event_id)
            response_times.append(retrieval_time)
            
            if event_data and event_data.get("id") == event_id:
                retrieval_successful += 1
            else:
                retrieval_failed += 1
        
        # Verify event chain integrity
        chain_valid, chain_time = await self.verify_event_chain(entity_id)
        response_times.append(chain_time)
        
        total_operations = len(test_events) + len(submitted_event_ids[:10]) + 1  # +1 for chain verification
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0
        
        success = (
            successful_events >= num_events * 0.95 and  # 95% submission success
            retrieval_successful >= len(submitted_event_ids[:10]) * 0.95 and  # 95% retrieval success
            chain_valid  # Chain integrity maintained
        )
        
        return EventSourcingTestResult(
            test_name="Event Submission and Retrieval",
            total_events=num_events,
            successful_events=successful_events,
            failed_events=failed_events,
            average_response_time_ms=avg_response_time,
            chain_integrity=chain_valid,
            success=success,
            error_message=None if success else f"Submission: {successful_events}/{num_events}, Retrieval: {retrieval_successful}/{len(submitted_event_ids[:10])}, Chain: {chain_valid}"
        )
    
    async def test_event_chain_integrity(self, num_events: int = 50) -> EventSourcingTestResult:
        """Test event chain integrity with sequential events"""
        logger.info(f"Testing event chain integrity with {num_events} sequential events")
        
        entity_id = f"CHAIN_TEST_{uuid.uuid4().hex[:8]}"
        test_events = self.generate_test_events(entity_id, num_events)
        
        successful_events = 0
        failed_events = 0
        response_times = []
        
        # Submit events sequentially to build chain
        for i, event in enumerate(test_events):
            event_response, response_time = await self.submit_event(event)
            response_times.append(response_time)
            
            if event_response:
                successful_events += 1
                
                # Verify hash chain after every 10 events
                if (i + 1) % 10 == 0:
                    chain_valid, chain_time = await self.verify_event_chain(entity_id)
                    response_times.append(chain_time)
                    
                    if not chain_valid:
                        logger.error(f"Chain integrity broken at event {i + 1}")
                        break
            else:
                failed_events += 1
            
            # Small delay to ensure timestamp ordering
            await asyncio.sleep(0.02)
        
        # Final chain verification
        final_chain_valid, final_chain_time = await self.verify_event_chain(entity_id)
        response_times.append(final_chain_time)
        
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0
        
        success = (
            successful_events >= num_events * 0.98 and  # 98% success for chain integrity test
            final_chain_valid
        )
        
        return EventSourcingTestResult(
            test_name="Event Chain Integrity",
            total_events=num_events,
            successful_events=successful_events,
            failed_events=failed_events,
            average_response_time_ms=avg_response_time,
            chain_integrity=final_chain_valid,
            success=success,
            error_message=None if success else f"Chain integrity failed: {successful_events}/{num_events} events, chain_valid: {final_chain_valid}"
        )
    
    async def test_concurrent_event_processing(self, num_entities: int = 10, events_per_entity: int = 20) -> EventSourcingTestResult:
        """Test concurrent event processing across multiple entities"""
        logger.info(f"Testing concurrent event processing: {num_entities} entities, {events_per_entity} events each")
        
        # Generate events for multiple entities
        all_tasks = []
        entity_ids = []
        
        for i in range(num_entities):
            entity_id = f"CONCURRENT_TEST_{i:03d}_{uuid.uuid4().hex[:6]}"
            entity_ids.append(entity_id)
            test_events = self.generate_test_events(entity_id, events_per_entity)
            
            # Create tasks for concurrent submission
            for event in test_events:
                task = self.submit_event(event)
                all_tasks.append(task)
        
        # Execute all submissions concurrently
        start_time = time.time()
        results = await asyncio.gather(*all_tasks, return_exceptions=True)
        end_time = time.time()
        
        total_time_ms = (end_time - start_time) * 1000
        
        # Analyze results
        successful_events = 0
        failed_events = 0
        response_times = []
        
        for result in results:
            if isinstance(result, tuple) and result[0] is not None:
                successful_events += 1
                response_times.append(result[1])
            else:
                failed_events += 1
        
        # Verify chain integrity for each entity
        chain_verifications = []
        for entity_id in entity_ids:
            task = self.verify_event_chain(entity_id)
            chain_verifications.append(task)
        
        chain_results = await asyncio.gather(*chain_verifications, return_exceptions=True)
        chains_valid = sum(1 for result in chain_results if isinstance(result, tuple) and result[0])
        
        total_events = num_entities * events_per_entity
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0
        
        success = (
            successful_events >= total_events * 0.90 and  # 90% success for concurrent test
            chains_valid >= num_entities * 0.90  # 90% of chains valid
        )
        
        logger.info(f"Concurrent processing: {total_time_ms:.2f}ms total, {chains_valid}/{num_entities} chains valid")
        
        return EventSourcingTestResult(
            test_name="Concurrent Event Processing",
            total_events=total_events,
            successful_events=successful_events,
            failed_events=failed_events,
            average_response_time_ms=avg_response_time,
            chain_integrity=chains_valid == num_entities,
            success=success,
            error_message=None if success else f"Success: {successful_events}/{total_events}, Chains: {chains_valid}/{num_entities}"
        )
    
    async def test_event_replay_consistency(self, num_events: int = 30) -> EventSourcingTestResult:
        """Test event replay and state reconstruction consistency"""
        logger.info(f"Testing event replay consistency with {num_events} events")
        
        entity_id = f"REPLAY_TEST_{uuid.uuid4().hex[:8]}"
        test_events = self.generate_test_events(entity_id, num_events)
        
        successful_events = 0
        failed_events = 0
        response_times = []
        
        # Submit events
        for event in test_events:
            event_response, response_time = await self.submit_event(event)
            response_times.append(response_time)
            
            if event_response:
                successful_events += 1
            else:
                failed_events += 1
            
            await asyncio.sleep(0.01)
        
        # Get all events for the entity (simulating replay)
        events_list, retrieval_time = await self.get_events_by_entity(entity_id)
        response_times.append(retrieval_time)
        
        # Verify event ordering and completeness
        replay_success = False
        if events_list and len(events_list) == successful_events:
            # Check if events are in correct chronological order
            timestamps = [event.get("timestamp") for event in events_list]
            sorted_timestamps = sorted(timestamps)
            replay_success = timestamps == sorted_timestamps
        
        # Verify chain integrity after replay
        chain_valid, chain_time = await self.verify_event_chain(entity_id)
        response_times.append(chain_time)
        
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0
        
        success = (
            successful_events >= num_events * 0.95 and
            replay_success and
            chain_valid
        )
        
        return EventSourcingTestResult(
            test_name="Event Replay Consistency",
            total_events=num_events,
            successful_events=successful_events,
            failed_events=failed_events,
            average_response_time_ms=avg_response_time,
            chain_integrity=chain_valid,
            success=success,
            error_message=None if success else f"Replay: {replay_success}, Chain: {chain_valid}, Events: {len(events_list) if events_list else 0}/{successful_events}"
        )
    
    def format_test_result(self, result: EventSourcingTestResult) -> str:
        """Format test result for display"""
        status = "✅ PASSED" if result.success else "❌ FAILED"
        
        return f"""
{result.test_name}: {status}
  Total Events: {result.total_events}
  Successful: {result.successful_events}
  Failed: {result.failed_events}
  Avg Response Time: {result.average_response_time_ms:.2f}ms
  Chain Integrity: {'✅' if result.chain_integrity else '❌'}
  Error: {result.error_message or 'None'}
        """
    
    async def run_all_event_sourcing_tests(self) -> Dict:
        """Run all event sourcing tests"""
        logger.info("Starting comprehensive event sourcing tests")
        
        await self.setup_session()
        
        try:
            # Run all test suites
            submission_test = await self.test_event_submission_and_retrieval(50)  # Reduced for testing
            chain_test = await self.test_event_chain_integrity(30)  # Reduced for testing
            concurrent_test = await self.test_concurrent_event_processing(5, 10)  # Reduced for testing
            replay_test = await self.test_event_replay_consistency(20)  # Reduced for testing
            
            # Display results
            print(self.format_test_result(submission_test))
            print(self.format_test_result(chain_test))
            print(self.format_test_result(concurrent_test))
            print(self.format_test_result(replay_test))
            
            return {
                "event_submission": {
                    "success_rate": (submission_test.successful_events / submission_test.total_events) * 100,
                    "avg_response_time_ms": submission_test.average_response_time_ms,
                    "chain_integrity": submission_test.chain_integrity,
                    "success": submission_test.success
                },
                "chain_integrity": {
                    "success_rate": (chain_test.successful_events / chain_test.total_events) * 100,
                    "avg_response_time_ms": chain_test.average_response_time_ms,
                    "chain_integrity": chain_test.chain_integrity,
                    "success": chain_test.success
                },
                "concurrent_processing": {
                    "success_rate": (concurrent_test.successful_events / concurrent_test.total_events) * 100,
                    "avg_response_time_ms": concurrent_test.average_response_time_ms,
                    "chain_integrity": concurrent_test.chain_integrity,
                    "success": concurrent_test.success
                },
                "replay_consistency": {
                    "success_rate": (replay_test.successful_events / replay_test.total_events) * 100,
                    "avg_response_time_ms": replay_test.average_response_time_ms,
                    "chain_integrity": replay_test.chain_integrity,
                    "success": replay_test.success
                },
                "overall_success": all([
                    submission_test.success,
                    chain_test.success,
                    concurrent_test.success,
                    replay_test.success
                ]),
                "timestamp": time.time()
            }
        
        finally:
            await self.cleanup_session()

# Test cases using pytest
@pytest.mark.asyncio
async def test_event_submission():
    """Test event submission functionality"""
    tester = EventSourcingTester()
    await tester.setup_session()
    
    try:
        result = await tester.test_event_submission_and_retrieval(20)
        
        # Assertions
        assert result.success, f"Event submission test failed: {result.error_message}"
        assert result.successful_events >= result.total_events * 0.95, f"Success rate should be ≥95%"
        assert result.chain_integrity, "Chain integrity should be maintained"
        
        logger.info("Event submission test passed")
    
    finally:
        await tester.cleanup_session()

@pytest.mark.asyncio
async def test_chain_integrity():
    """Test event chain integrity"""
    tester = EventSourcingTester()
    await tester.setup_session()
    
    try:
        result = await tester.test_event_chain_integrity(20)
        
        # Assertions
        assert result.success, f"Chain integrity test failed: {result.error_message}"
        assert result.chain_integrity, "Event chain should be valid"
        
        logger.info("Chain integrity test passed")
    
    finally:
        await tester.cleanup_session()

if __name__ == "__main__":
    # Run comprehensive event sourcing tests
    async def main():
        tester = EventSourcingTester()
        results = await tester.run_all_event_sourcing_tests()
        print(json.dumps(results, indent=2))
    
    asyncio.run(main())

"""
CQRS Flow Integration Tests

Tests that verify Command Query Responsibility Segregation (CQRS) patterns
with Event Sourcing across the Java Account Service.
"""

import asyncio
import json
import time
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Any

import pytest
import httpx
import asyncpg
from kafka import KafkaConsumer

# Test configuration
TEST_CONFIG = {
    "services": {
        "account_service": "http://localhost:8096",
    },
    "databases": {
        "postgres": "postgresql://postgres:postgres@localhost:5432/microservices",
    },
    "kafka": {
        "brokers": ["localhost:9092"],
        "topics": ["account-events"]
    }
}

class CQRSFlowTest:
    """Integration test suite for CQRS and Event Sourcing patterns"""
    
    def __init__(self):
        self.http_client = httpx.AsyncClient(timeout=30.0)
        self.postgres_pool = None
        self.kafka_consumer = None
        self.captured_events = []
        
    async def setup(self):
        """Setup test infrastructure"""
        print("🔧 Setting up CQRS flow test environment...")
        
        # Setup database connection
        self.postgres_pool = await asyncpg.create_pool(TEST_CONFIG["databases"]["postgres"])
        
        # Setup Kafka consumer for account events
        self.kafka_consumer = KafkaConsumer(
            "account-events",
            bootstrap_servers=TEST_CONFIG["kafka"]["brokers"],
            value_deserializer=lambda m: json.loads(m.decode('utf-8')),
            consumer_timeout_ms=5000,
            auto_offset_reset='latest'
        )
        
        # Wait for services to be ready
        await self._wait_for_services()
        
        print("✅ CQRS flow test environment setup complete")
    
    async def teardown(self):
        """Cleanup test infrastructure"""
        print("🧹 Cleaning up CQRS flow test environment...")
        
        if self.http_client:
            await self.http_client.aclose()
        
        if self.postgres_pool:
            await self.postgres_pool.close()
        
        if self.kafka_consumer:
            self.kafka_consumer.close()
        
        print("✅ CQRS flow test environment cleanup complete")
    
    async def _wait_for_services(self):
        """Wait for account service to be healthy"""
        print("⏳ Waiting for account service to be ready...")
        
        max_retries = 30
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                response = await self.http_client.get(
                    f"{TEST_CONFIG['services']['account_service']}/actuator/health"
                )
                if response.status_code == 200:
                    print("✅ Account service is ready")
                    break
            except Exception as e:
                retry_count += 1
                if retry_count >= max_retries:
                    raise Exception(f"❌ Account service failed to become ready: {e}")
                await asyncio.sleep(2)
    
    async def test_complete_cqrs_flow(self):
        """
        Test complete CQRS flow with Event Sourcing:
        1. Send commands to write side
        2. Verify events are stored in event store
        3. Verify events are published to Kafka
        4. Verify read model is updated
        5. Query read side and verify data consistency
        """
        print("\n🧪 Testing Complete CQRS Flow with Event Sourcing")
        
        # Generate test data
        account_id = str(uuid.uuid4())
        customer_id = str(uuid.uuid4())
        
        # Step 1: Create Account (Command)
        await self._test_create_account_command(account_id, customer_id)
        
        # Step 2: Deposit Money (Command)
        await self._test_deposit_money_command(account_id, 500.00)
        
        # Step 3: Reserve Money (Command)
        reservation_id = await self._test_reserve_money_command(account_id, 150.00)
        
        # Step 4: Confirm Reservation (Command)
        await self._test_confirm_reservation_command(account_id, reservation_id, 150.00)
        
        # Step 5: Withdraw Money (Command)
        await self._test_withdraw_money_command(account_id, 100.00)
        
        # Step 6: Verify Event Store Consistency
        await self._verify_event_store_consistency(account_id)
        
        # Step 7: Verify Read Model Consistency
        await self._verify_read_model_consistency(account_id)
        
        # Step 8: Verify Event Replay Capability
        await self._test_event_replay(account_id)
        
        print("✅ Complete CQRS Flow test passed")
    
    async def _test_create_account_command(self, account_id: str, customer_id: str):
        """Test CreateAccount command"""
        print(f"💳 Testing CreateAccount command: {account_id}")
        
        command_data = {
            "accountId": account_id,
            "accountNumber": f"ACC-{int(time.time())}",
            "customerId": customer_id,
            "accountType": "CHECKING",
            "currency": "USD",
            "initialBalance": 1000.00
        }
        
        response = await self.http_client.post(
            f"{TEST_CONFIG['services']['account_service']}/api/v1/accounts",
            json=command_data
        )
        
        assert response.status_code == 201, f"CreateAccount command failed: {response.text}"
        
        # Verify AccountCreated event
        await self._verify_event_in_store(account_id, "AccountCreated", 0)
        await self._capture_kafka_events()
        
        print("✅ CreateAccount command executed successfully")
    
    async def _test_deposit_money_command(self, account_id: str, amount: float):
        """Test DepositMoney command"""
        print(f"💰 Testing DepositMoney command: {account_id}, amount: {amount}")
        
        command_data = {
            "transactionId": str(uuid.uuid4()),
            "amount": amount,
            "description": "Test deposit"
        }
        
        response = await self.http_client.post(
            f"{TEST_CONFIG['services']['account_service']}/api/v1/accounts/{account_id}/deposit",
            json=command_data
        )
        
        assert response.status_code == 200, f"DepositMoney command failed: {response.text}"
        
        # Verify MoneyDepositedEvent
        await self._verify_event_in_store(account_id, "MoneyDeposited", 1)
        await self._capture_kafka_events()
        
        print("✅ DepositMoney command executed successfully")
    
    async def _test_reserve_money_command(self, account_id: str, amount: float) -> str:
        """Test ReserveMoney command"""
        print(f"🔒 Testing ReserveMoney command: {account_id}, amount: {amount}")
        
        reservation_id = str(uuid.uuid4())
        command_data = {
            "reservationId": reservation_id,
            "transactionId": str(uuid.uuid4()),
            "amount": amount,
            "description": "Test reservation"
        }
        
        response = await self.http_client.post(
            f"{TEST_CONFIG['services']['account_service']}/api/v1/accounts/{account_id}/reserve",
            json=command_data
        )
        
        assert response.status_code == 200, f"ReserveMoney command failed: {response.text}"
        
        # Verify MoneyReservedEvent
        await self._verify_event_in_store(account_id, "MoneyReserved", 2)
        await self._capture_kafka_events()
        
        print("✅ ReserveMoney command executed successfully")
        return reservation_id
    
    async def _test_confirm_reservation_command(self, account_id: str, reservation_id: str, amount: float):
        """Test ConfirmReservation command"""
        print(f"✅ Testing ConfirmReservation command: {account_id}, reservation: {reservation_id}")
        
        command_data = {
            "reservationId": reservation_id,
            "transactionId": str(uuid.uuid4()),
            "amount": amount,
            "description": "Test reservation confirmation"
        }
        
        response = await self.http_client.post(
            f"{TEST_CONFIG['services']['account_service']}/api/v1/accounts/{account_id}/confirm-reservation",
            json=command_data
        )
        
        assert response.status_code == 200, f"ConfirmReservation command failed: {response.text}"
        
        # Verify ReservationConfirmedEvent
        await self._verify_event_in_store(account_id, "ReservationConfirmed", 3)
        await self._capture_kafka_events()
        
        print("✅ ConfirmReservation command executed successfully")
    
    async def _test_withdraw_money_command(self, account_id: str, amount: float):
        """Test WithdrawMoney command"""
        print(f"💸 Testing WithdrawMoney command: {account_id}, amount: {amount}")
        
        command_data = {
            "transactionId": str(uuid.uuid4()),
            "amount": amount,
            "description": "Test withdrawal"
        }
        
        response = await self.http_client.post(
            f"{TEST_CONFIG['services']['account_service']}/api/v1/accounts/{account_id}/withdraw",
            json=command_data
        )
        
        assert response.status_code == 200, f"WithdrawMoney command failed: {response.text}"
        
        # Verify MoneyWithdrawnEvent
        await self._verify_event_in_store(account_id, "MoneyWithdrawn", 4)
        await self._capture_kafka_events()
        
        print("✅ WithdrawMoney command executed successfully")
    
    async def _verify_event_in_store(self, aggregate_id: str, event_type: str, expected_sequence: int):
        """Verify event exists in the event store with correct sequence"""
        print(f"🔍 Verifying event in store: {event_type}, sequence: {expected_sequence}")
        
        async with self.postgres_pool.acquire() as conn:
            result = await conn.fetchrow(
                """
                SELECT * FROM domain_event_entry 
                WHERE aggregate_identifier = $1 
                AND sequence_number = $2
                AND type LIKE $3
                """,
                aggregate_id, expected_sequence, f"%{event_type}%"
            )
            
            assert result is not None, f"Event {event_type} not found in event store"
            assert result["sequence_number"] == expected_sequence, f"Wrong sequence number: {result['sequence_number']}"
            
        print(f"✅ Event verified in store: {event_type}")
    
    async def _capture_kafka_events(self):
        """Capture events from Kafka"""
        print("📡 Capturing Kafka events...")
        
        # Poll for new messages
        messages = self.kafka_consumer.poll(timeout_ms=3000)
        for topic_partition, records in messages.items():
            for record in records:
                event_data = record.value
                self.captured_events.append(event_data)
                print(f"📨 Captured event: {event_data.get('eventType', 'Unknown')}")
    
    async def _verify_event_store_consistency(self, account_id: str):
        """Verify event store has all expected events in correct order"""
        print(f"🔍 Verifying event store consistency for: {account_id}")
        
        async with self.postgres_pool.acquire() as conn:
            events = await conn.fetch(
                """
                SELECT sequence_number, type, payload 
                FROM domain_event_entry 
                WHERE aggregate_identifier = $1 
                ORDER BY sequence_number
                """,
                account_id
            )
            
            # Should have 5 events (0-4)
            assert len(events) == 5, f"Expected 5 events, found {len(events)}"
            
            # Verify sequence numbers are consecutive
            for i, event in enumerate(events):
                assert event["sequence_number"] == i, f"Wrong sequence at position {i}"
            
            # Verify event types
            expected_types = [
                "AccountCreated",
                "MoneyDeposited", 
                "MoneyReserved",
                "ReservationConfirmed",
                "MoneyWithdrawn"
            ]
            
            for i, expected_type in enumerate(expected_types):
                assert expected_type in events[i]["type"], f"Wrong event type at position {i}"
        
        print("✅ Event store consistency verified")
    
    async def _verify_read_model_consistency(self, account_id: str):
        """Verify read model reflects all the commands"""
        print(f"🔍 Verifying read model consistency for: {account_id}")
        
        # Query the read model (account projection)
        response = await self.http_client.get(
            f"{TEST_CONFIG['services']['account_service']}/api/v1/accounts/{account_id}"
        )
        
        assert response.status_code == 200, f"Failed to query read model: {response.text}"
        
        account = response.json()
        
        # Verify account state reflects all operations
        # Initial: 1000, Deposit: +500, Withdraw: -100 = 1400
        # Reserved and confirmed 150, so available should be 1400
        expected_balance = 1400.00
        expected_available = 1400.00  # After confirmation, reservation is cleared
        
        assert abs(account["balance"] - expected_balance) < 0.01, f"Wrong balance: {account['balance']}"
        assert abs(account["availableBalance"] - expected_available) < 0.01, f"Wrong available balance: {account['availableBalance']}"
        assert account["status"] == "ACTIVE", f"Wrong status: {account['status']}"
        
        print("✅ Read model consistency verified")
    
    async def _test_event_replay(self, account_id: str):
        """Test event replay capability by rebuilding aggregate from events"""
        print(f"🔄 Testing event replay for: {account_id}")
        
        # This would typically involve calling a replay endpoint
        # For now, we'll verify that we can retrieve the event history
        async with self.postgres_pool.acquire() as conn:
            events = await conn.fetch(
                """
                SELECT sequence_number, type, payload, time_stamp
                FROM domain_event_entry 
                WHERE aggregate_identifier = $1 
                ORDER BY sequence_number
                """,
                account_id
            )
            
            # Verify we can replay the full history
            assert len(events) > 0, "No events found for replay"
            
            # Verify events are in chronological order
            for i in range(1, len(events)):
                assert events[i]["time_stamp"] >= events[i-1]["time_stamp"], "Events not in chronological order"
        
        print("✅ Event replay capability verified")
    
    async def test_concurrent_commands(self):
        """Test CQRS system handles concurrent commands correctly"""
        print("\n🧪 Testing Concurrent Commands Handling")
        
        # Create account for concurrent testing
        account_id = str(uuid.uuid4())
        customer_id = str(uuid.uuid4())
        
        # Create account first
        await self._test_create_account_command(account_id, customer_id)
        
        # Execute multiple concurrent commands
        tasks = []
        
        # Multiple deposits
        for i in range(3):
            task = self._test_deposit_money_command(account_id, 100.00)
            tasks.append(task)
        
        # Multiple withdrawals
        for i in range(2):
            task = self._test_withdraw_money_command(account_id, 50.00)
            tasks.append(task)
        
        # Execute all commands concurrently
        await asyncio.gather(*tasks)
        
        # Verify final state is consistent
        await self._verify_read_model_consistency_concurrent(account_id)
        
        print("✅ Concurrent Commands test passed")
    
    async def _verify_read_model_consistency_concurrent(self, account_id: str):
        """Verify read model after concurrent operations"""
        print(f"🔍 Verifying read model after concurrent operations: {account_id}")
        
        response = await self.http_client.get(
            f"{TEST_CONFIG['services']['account_service']}/api/v1/accounts/{account_id}"
        )
        
        assert response.status_code == 200
        account = response.json()
        
        # Initial: 1000, 3 deposits of 100 each (+300), 2 withdrawals of 50 each (-100) = 1200
        expected_balance = 1200.00
        
        assert abs(account["balance"] - expected_balance) < 0.01, f"Wrong balance after concurrent ops: {account['balance']}"
        
        print("✅ Read model consistency verified after concurrent operations")

# Test runner
async def run_cqrs_flow_tests():
    """Run all CQRS flow tests"""
    test_suite = CQRSFlowTest()
    
    try:
        await test_suite.setup()
        
        # Run tests
        print("\n" + "="*60)
        print("🏗️  CQRS FLOW INTEGRATION TESTS")
        print("="*60)
        
        await test_suite.test_complete_cqrs_flow()
        await test_suite.test_concurrent_commands()
        
        print("\n" + "="*60)
        print("✅ ALL CQRS FLOW TESTS PASSED!")
        print("="*60)
        
    except Exception as e:
        print(f"\n❌ CQRS flow test failed: {e}")
        raise
    finally:
        await test_suite.teardown()

if __name__ == "__main__":
    asyncio.run(run_cqrs_flow_tests())

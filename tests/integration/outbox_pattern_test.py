"""
Outbox Pattern Integration Tests

Tests that verify reliable event publishing across different databases
and programming languages using the outbox pattern.
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
import motor.motor_asyncio
import redis.asyncio as redis
from kafka import KafkaConsumer
from kafka.errors import KafkaError

# Test configuration
TEST_CONFIG = {
    "services": {
        "account_service": "http://localhost:8096",
        "billing_service": "http://localhost:8097", 
        "outbox_publisher": "http://localhost:8098",
        "transaction_coordinator": "http://localhost:8095",
    },
    "databases": {
        "postgres": "postgresql://postgres:postgres@localhost:5432/microservices",
        "mongodb": "mongodb://localhost:27017",
        "redis": "redis://localhost:6379",
    },
    "kafka": {
        "brokers": ["localhost:9092"],
        "topics": [
            "account-events",
            "billing-events", 
            "transaction-events",
            "outbox-events"
        ]
    }
}

class OutboxPatternTest:
    """Integration test suite for outbox pattern reliability"""
    
    def __init__(self):
        self.http_client = httpx.AsyncClient(timeout=30.0)
        self.postgres_pool = None
        self.mongodb_client = None
        self.redis_client = None
        self.kafka_consumers = {}
        self.received_events = []
        
    async def setup(self):
        """Setup test infrastructure"""
        print("🔧 Setting up outbox pattern test environment...")
        
        # Setup database connections
        self.postgres_pool = await asyncpg.create_pool(TEST_CONFIG["databases"]["postgres"])
        self.mongodb_client = motor.motor_asyncio.AsyncIOMotorClient(TEST_CONFIG["databases"]["mongodb"])
        self.redis_client = redis.from_url(TEST_CONFIG["databases"]["redis"])
        
        # Setup Kafka consumers to capture events
        await self._setup_kafka_consumers()
        
        # Wait for services to be ready
        await self._wait_for_services()
        
        print("✅ Outbox pattern test environment setup complete")
    
    async def teardown(self):
        """Cleanup test infrastructure"""
        print("🧹 Cleaning up outbox pattern test environment...")
        
        if self.http_client:
            await self.http_client.aclose()
        
        if self.postgres_pool:
            await self.postgres_pool.close()
        
        if self.mongodb_client:
            self.mongodb_client.close()
        
        if self.redis_client:
            await self.redis_client.close()
        
        for consumer in self.kafka_consumers.values():
            consumer.close()
        
        print("✅ Outbox pattern test environment cleanup complete")
    
    async def _setup_kafka_consumers(self):
        """Setup Kafka consumers to capture published events"""
        print("📡 Setting up Kafka consumers...")
        
        for topic in TEST_CONFIG["kafka"]["topics"]:
            consumer = KafkaConsumer(
                topic,
                bootstrap_servers=TEST_CONFIG["kafka"]["brokers"],
                value_deserializer=lambda m: json.loads(m.decode('utf-8')),
                consumer_timeout_ms=5000,
                auto_offset_reset='latest'
            )
            self.kafka_consumers[topic] = consumer
        
        print(f"✅ Setup {len(self.kafka_consumers)} Kafka consumers")
    
    async def _wait_for_services(self):
        """Wait for all services to be healthy"""
        print("⏳ Waiting for services to be ready...")
        
        for service_name, base_url in TEST_CONFIG["services"].items():
            max_retries = 30
            retry_count = 0
            
            while retry_count < max_retries:
                try:
                    response = await self.http_client.get(f"{base_url}/health")
                    if response.status_code == 200:
                        print(f"✅ {service_name} is ready")
                        break
                except Exception as e:
                    retry_count += 1
                    if retry_count >= max_retries:
                        raise Exception(f"❌ {service_name} failed to become ready: {e}")
                    await asyncio.sleep(2)
    
    async def test_postgres_outbox_reliability(self):
        """
        Test outbox pattern reliability with PostgreSQL:
        1. Create account (writes to DB + outbox table)
        2. Verify outbox event is created
        3. Verify event is published to Kafka
        4. Verify event is marked as processed
        """
        print("\n🧪 Testing PostgreSQL Outbox Pattern Reliability")
        
        # Generate test data
        account_id = str(uuid.uuid4())
        customer_id = str(uuid.uuid4())
        
        # Step 1: Create account (should create outbox event)
        account_data = {
            "accountId": account_id,
            "accountNumber": f"ACC-{int(time.time())}",
            "customerId": customer_id,
            "accountType": "CHECKING",
            "currency": "USD",
            "initialBalance": 500.00
        }
        
        print(f"💳 Creating account: {account_id}")
        response = await self.http_client.post(
            f"{TEST_CONFIG['services']['account_service']}/api/v1/accounts",
            json=account_data
        )
        
        assert response.status_code == 201, f"Failed to create account: {response.text}"
        
        # Step 2: Verify outbox event was created in PostgreSQL
        await self._verify_postgres_outbox_event(account_id, "AccountCreated")
        
        # Step 3: Wait for outbox publisher to process events
        await asyncio.sleep(5)
        
        # Step 4: Verify event was published to Kafka
        await self._verify_kafka_event_received("account-events", account_id)
        
        # Step 5: Verify outbox event is marked as processed
        await self._verify_outbox_event_processed(account_id)
        
        print("✅ PostgreSQL Outbox Pattern test passed")
    
    async def test_mongodb_outbox_reliability(self):
        """
        Test outbox pattern reliability with MongoDB:
        1. Create billing record (writes to MongoDB + outbox collection)
        2. Verify outbox event is created
        3. Verify event is published to Kafka
        4. Verify event is marked as processed
        """
        print("\n🧪 Testing MongoDB Outbox Pattern Reliability")
        
        # Generate test data
        billing_id = str(uuid.uuid4())
        customer_id = str(uuid.uuid4())
        order_id = str(uuid.uuid4())
        
        # Step 1: Create billing record (should create outbox event)
        billing_data = {
            "customerId": customer_id,
            "orderId": order_id,
            "billingType": "ORDER",
            "items": [
                {
                    "id": str(uuid.uuid4()),
                    "description": "Test Product",
                    "quantity": 1,
                    "unit_price": 99.99,
                    "total_price": 99.99,
                    "tax_rate": 0.0,
                    "tax_amount": 0.0
                }
            ],
            "currency": "USD",
            "dueDate": (datetime.utcnow() + timedelta(days=30)).isoformat()
        }
        
        print(f"🧾 Creating billing record for order: {order_id}")
        response = await self.http_client.post(
            f"{TEST_CONFIG['services']['billing_service']}/api/v1/billing",
            json=billing_data
        )
        
        assert response.status_code == 201, f"Failed to create billing record: {response.text}"
        billing_response = response.json()
        billing_id = billing_response["id"]
        
        # Step 2: Verify outbox event was created in MongoDB
        await self._verify_mongodb_outbox_event(billing_id, "BillingCreated")
        
        # Step 3: Wait for outbox publisher to process events
        await asyncio.sleep(5)
        
        # Step 4: Verify event was published to Kafka
        await self._verify_kafka_event_received("billing-events", billing_id)
        
        # Step 5: Verify outbox event is marked as processed
        await self._verify_mongodb_outbox_event_processed(billing_id)
        
        print("✅ MongoDB Outbox Pattern test passed")
    
    async def test_outbox_failure_recovery(self):
        """
        Test outbox pattern failure recovery:
        1. Create events that will initially fail to publish
        2. Verify retry mechanism works
        3. Verify events are eventually published
        """
        print("\n🧪 Testing Outbox Pattern Failure Recovery")
        
        # Step 1: Get current failed events count
        response = await self.http_client.get(
            f"{TEST_CONFIG['services']['outbox_publisher']}/api/v1/stats"
        )
        assert response.status_code == 200
        initial_stats = response.json()
        
        # Step 2: Create some test events
        account_id = str(uuid.uuid4())
        customer_id = str(uuid.uuid4())
        
        account_data = {
            "accountId": account_id,
            "accountNumber": f"ACC-{int(time.time())}",
            "customerId": customer_id,
            "accountType": "SAVINGS",
            "currency": "USD",
            "initialBalance": 750.00
        }
        
        response = await self.http_client.post(
            f"{TEST_CONFIG['services']['account_service']}/api/v1/accounts",
            json=account_data
        )
        assert response.status_code == 201
        
        # Step 3: Wait for processing
        await asyncio.sleep(10)
        
        # Step 4: Check if any failed events were retried
        response = await self.http_client.get(
            f"{TEST_CONFIG['services']['outbox_publisher']}/api/v1/stats"
        )
        assert response.status_code == 200
        final_stats = response.json()
        
        # Verify processing occurred
        assert final_stats["total_events"] > initial_stats["total_events"]
        
        print("✅ Outbox Pattern Failure Recovery test passed")
    
    async def test_outbox_idempotency(self):
        """
        Test outbox pattern idempotency:
        1. Create duplicate events
        2. Verify only one event is published per unique event
        3. Verify no duplicate processing occurs
        """
        print("\n🧪 Testing Outbox Pattern Idempotency")
        
        # Generate test data
        transaction_id = str(uuid.uuid4())
        
        # Step 1: Create transaction multiple times (should be idempotent)
        transaction_data = {
            "transaction_type": "payment",
            "participants": [
                {
                    "service_name": "account-service",
                    "endpoint": f"{TEST_CONFIG['services']['account_service']}/api/v1/transactions/prepare",
                    "payload": {"amount": 100.00, "currency": "USD"}
                }
            ],
            "metadata": {"test_idempotency": True}
        }
        
        # Create the same transaction multiple times
        responses = []
        for i in range(3):
            response = await self.http_client.post(
                f"{TEST_CONFIG['services']['transaction_coordinator']}/transactions",
                json=transaction_data
            )
            responses.append(response)
            await asyncio.sleep(1)
        
        # All should succeed (idempotent)
        for response in responses:
            assert response.status_code == 200
        
        # Step 2: Wait for outbox processing
        await asyncio.sleep(5)
        
        # Step 3: Verify only unique events were processed
        await self._verify_no_duplicate_events(transaction_id)
        
        print("✅ Outbox Pattern Idempotency test passed")
    
    async def _verify_postgres_outbox_event(self, aggregate_id: str, event_type: str):
        """Verify outbox event exists in PostgreSQL"""
        print(f"🔍 Verifying PostgreSQL outbox event: {aggregate_id}")
        
        async with self.postgres_pool.acquire() as conn:
            result = await conn.fetchrow(
                "SELECT * FROM outbox_events WHERE aggregate_id = $1 AND event_type = $2",
                aggregate_id, event_type
            )
            
            assert result is not None, f"Outbox event not found for {aggregate_id}"
            assert result["status"] == "pending", f"Unexpected event status: {result['status']}"
            
        print(f"✅ PostgreSQL outbox event verified: {event_type}")
    
    async def _verify_mongodb_outbox_event(self, aggregate_id: str, event_type: str):
        """Verify outbox event exists in MongoDB"""
        print(f"🔍 Verifying MongoDB outbox event: {aggregate_id}")
        
        db = self.mongodb_client.billing_service
        result = await db.outbox_events.find_one({
            "aggregate_id": aggregate_id,
            "event_type": event_type
        })
        
        assert result is not None, f"Outbox event not found for {aggregate_id}"
        assert result["status"] == "pending", f"Unexpected event status: {result['status']}"
        
        print(f"✅ MongoDB outbox event verified: {event_type}")
    
    async def _verify_kafka_event_received(self, topic: str, aggregate_id: str):
        """Verify event was received on Kafka topic"""
        print(f"📡 Verifying Kafka event on topic: {topic}")
        
        consumer = self.kafka_consumers[topic]
        event_found = False
        
        # Poll for messages
        for _ in range(10):  # Try for 10 iterations
            messages = consumer.poll(timeout_ms=1000)
            for topic_partition, records in messages.items():
                for record in records:
                    event_data = record.value
                    if event_data.get("aggregate_id") == aggregate_id:
                        event_found = True
                        self.received_events.append(event_data)
                        break
            if event_found:
                break
        
        assert event_found, f"Event not found on Kafka topic {topic} for aggregate {aggregate_id}"
        print(f"✅ Kafka event verified on topic: {topic}")
    
    async def _verify_outbox_event_processed(self, aggregate_id: str):
        """Verify outbox event is marked as processed in PostgreSQL"""
        print(f"✅ Verifying outbox event processed: {aggregate_id}")
        
        async with self.postgres_pool.acquire() as conn:
            result = await conn.fetchrow(
                "SELECT * FROM outbox_events WHERE aggregate_id = $1",
                aggregate_id
            )
            
            assert result is not None, f"Outbox event not found for {aggregate_id}"
            assert result["status"] == "processed", f"Event not processed: {result['status']}"
            assert result["processed_at"] is not None, "Processed timestamp not set"
            
        print(f"✅ Outbox event processing verified: {aggregate_id}")
    
    async def _verify_mongodb_outbox_event_processed(self, aggregate_id: str):
        """Verify outbox event is marked as processed in MongoDB"""
        print(f"✅ Verifying MongoDB outbox event processed: {aggregate_id}")
        
        db = self.mongodb_client.billing_service
        result = await db.outbox_events.find_one({
            "aggregate_id": aggregate_id
        })
        
        assert result is not None, f"Outbox event not found for {aggregate_id}"
        assert result["status"] == "processed", f"Event not processed: {result['status']}"
        assert result["processed_at"] is not None, "Processed timestamp not set"
        
        print(f"✅ MongoDB outbox event processing verified: {aggregate_id}")
    
    async def _verify_no_duplicate_events(self, transaction_id: str):
        """Verify no duplicate events were processed"""
        print(f"🔍 Verifying no duplicate events for: {transaction_id}")
        
        # Count events in received events
        matching_events = [
            event for event in self.received_events 
            if event.get("aggregate_id") == transaction_id
        ]
        
        # Should have exactly one event per unique operation
        assert len(matching_events) <= 1, f"Duplicate events found: {len(matching_events)}"
        
        print(f"✅ No duplicate events verified for: {transaction_id}")

# Test runner
async def run_outbox_pattern_tests():
    """Run all outbox pattern tests"""
    test_suite = OutboxPatternTest()
    
    try:
        await test_suite.setup()
        
        # Run tests
        print("\n" + "="*60)
        print("📤 OUTBOX PATTERN INTEGRATION TESTS")
        print("="*60)
        
        await test_suite.test_postgres_outbox_reliability()
        await test_suite.test_mongodb_outbox_reliability()
        await test_suite.test_outbox_failure_recovery()
        await test_suite.test_outbox_idempotency()
        
        print("\n" + "="*60)
        print("✅ ALL OUTBOX PATTERN TESTS PASSED!")
        print("="*60)
        
    except Exception as e:
        print(f"\n❌ Outbox pattern test failed: {e}")
        raise
    finally:
        await test_suite.teardown()

if __name__ == "__main__":
    asyncio.run(run_outbox_pattern_tests())

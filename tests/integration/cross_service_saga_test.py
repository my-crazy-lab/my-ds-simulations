"""
Cross-Service Saga Integration Tests

Tests that demonstrate end-to-end Saga transactions across multiple services
with different programming languages and databases.
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
from kafka import KafkaProducer, KafkaConsumer
from kafka.errors import KafkaError

# Test configuration
TEST_CONFIG = {
    "services": {
        "transaction_coordinator": "http://localhost:8095",
        "account_service": "http://localhost:8096", 
        "billing_service": "http://localhost:8097",
        "outbox_publisher": "http://localhost:8098",
        "fraud_detection": "http://localhost:8099",
        "saga_orchestrator": "http://localhost:8080",
    },
    "databases": {
        "postgres": "postgresql://postgres:postgres@localhost:5432/microservices",
        "mongodb": "mongodb://localhost:27017",
        "redis": "redis://localhost:6379",
    },
    "kafka": {
        "brokers": ["localhost:9092"],
        "topics": [
            "transaction-events",
            "account-events", 
            "billing-events",
            "saga-events",
            "fraud-events"
        ]
    }
}

class CrossServiceSagaTest:
    """Integration test suite for cross-service Saga patterns"""
    
    def __init__(self):
        self.http_client = httpx.AsyncClient(timeout=30.0)
        self.postgres_pool = None
        self.mongodb_client = None
        self.redis_client = None
        self.kafka_producer = None
        self.kafka_consumers = {}
        self.test_data = {}
        
    async def setup(self):
        """Setup test infrastructure"""
        print("🔧 Setting up integration test environment...")
        
        # Setup database connections
        self.postgres_pool = await asyncpg.create_pool(TEST_CONFIG["databases"]["postgres"])
        self.mongodb_client = motor.motor_asyncio.AsyncIOMotorClient(TEST_CONFIG["databases"]["mongodb"])
        self.redis_client = redis.from_url(TEST_CONFIG["databases"]["redis"])
        
        # Setup Kafka
        self.kafka_producer = KafkaProducer(
            bootstrap_servers=TEST_CONFIG["kafka"]["brokers"],
            value_serializer=lambda v: json.dumps(v).encode('utf-8')
        )
        
        # Wait for services to be ready
        await self._wait_for_services()
        
        print("✅ Test environment setup complete")
    
    async def teardown(self):
        """Cleanup test infrastructure"""
        print("🧹 Cleaning up test environment...")
        
        if self.http_client:
            await self.http_client.aclose()
        
        if self.postgres_pool:
            await self.postgres_pool.close()
        
        if self.mongodb_client:
            self.mongodb_client.close()
        
        if self.redis_client:
            await self.redis_client.close()
        
        if self.kafka_producer:
            self.kafka_producer.close()
        
        for consumer in self.kafka_consumers.values():
            consumer.close()
        
        print("✅ Test environment cleanup complete")
    
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
    
    async def test_complete_order_saga(self):
        """
        Test a complete order processing saga that involves:
        1. Fraud detection check
        2. Account balance reservation
        3. Billing record creation
        4. Transaction coordination
        5. Outbox event publishing
        """
        print("\n🧪 Testing Complete Order Processing Saga")
        
        # Generate test data
        test_order = {
            "order_id": str(uuid.uuid4()),
            "customer_id": str(uuid.uuid4()),
            "account_id": str(uuid.uuid4()),
            "amount": 150.00,
            "currency": "USD",
            "items": [
                {
                    "id": str(uuid.uuid4()),
                    "description": "Test Product",
                    "quantity": 2,
                    "unit_price": 75.00,
                    "total_price": 150.00,
                    "tax_rate": 0.0,
                    "tax_amount": 0.0
                }
            ],
            "merchant_id": "test_merchant",
            "merchant_category": "retail",
            "country": "US",
            "device_fingerprint": "test_device_123",
            "ip_address": "192.168.1.100"
        }
        
        self.test_data["order"] = test_order
        
        # Step 1: Create account for testing
        await self._create_test_account(test_order["account_id"], test_order["customer_id"])
        
        # Step 2: Start the saga
        saga_id = await self._start_order_processing_saga(test_order)
        
        # Step 3: Monitor saga execution
        saga_result = await self._monitor_saga_execution(saga_id)
        
        # Step 4: Verify all services were called correctly
        await self._verify_saga_results(saga_id, test_order)
        
        print("✅ Complete Order Processing Saga test passed")
        return saga_result
    
    async def _create_test_account(self, account_id: str, customer_id: str):
        """Create a test account with sufficient balance"""
        print(f"💳 Creating test account: {account_id}")
        
        account_data = {
            "accountId": account_id,
            "accountNumber": f"ACC-{int(time.time())}",
            "customerId": customer_id,
            "accountType": "CHECKING",
            "currency": "USD",
            "initialBalance": 1000.00
        }
        
        response = await self.http_client.post(
            f"{TEST_CONFIG['services']['account_service']}/api/v1/accounts",
            json=account_data
        )
        
        assert response.status_code == 201, f"Failed to create account: {response.text}"
        print(f"✅ Account created successfully: {account_id}")
    
    async def _start_order_processing_saga(self, order_data: Dict) -> str:
        """Start the order processing saga"""
        print(f"🚀 Starting order processing saga for order: {order_data['order_id']}")
        
        # Create saga definition
        saga_definition = {
            "saga_type": "OrderProcessingSaga",
            "steps": [
                {
                    "step_id": "fraud_check",
                    "service_name": "fraud-detection-service",
                    "action_endpoint": f"{TEST_CONFIG['services']['fraud_detection']}/api/v1/fraud/assess",
                    "action_payload": {
                        "transaction_id": order_data["order_id"],
                        "user_id": order_data["customer_id"],
                        "amount": order_data["amount"],
                        "currency": order_data["currency"],
                        "merchant_id": order_data["merchant_id"],
                        "merchant_category": order_data["merchant_category"],
                        "country": order_data["country"],
                        "device_fingerprint": order_data["device_fingerprint"],
                        "ip_address": order_data["ip_address"],
                        "transaction_type": "purchase",
                        "timestamp": datetime.utcnow().isoformat(),
                        "user_created_at": (datetime.utcnow() - timedelta(days=365)).isoformat()
                    },
                    "compensation_endpoint": f"{TEST_CONFIG['services']['fraud_detection']}/api/v1/fraud/compensate",
                    "compensation_payload": {
                        "transaction_id": order_data["order_id"],
                        "reason": "saga_compensation"
                    },
                    "retry_policy": {
                        "max_attempts": 3,
                        "initial_delay_ms": 1000,
                        "max_delay_ms": 5000,
                        "backoff_multiplier": 2.0
                    },
                    "depends_on": []
                },
                {
                    "step_id": "reserve_funds",
                    "service_name": "account-service",
                    "action_endpoint": f"{TEST_CONFIG['services']['account_service']}/api/v1/accounts/{order_data['account_id']}/reserve",
                    "action_payload": {
                        "reservationId": str(uuid.uuid4()),
                        "transactionId": order_data["order_id"],
                        "amount": order_data["amount"],
                        "description": f"Order reservation: {order_data['order_id']}"
                    },
                    "compensation_endpoint": f"{TEST_CONFIG['services']['account_service']}/api/v1/accounts/{order_data['account_id']}/release-reservation",
                    "compensation_payload": {
                        "reservationId": str(uuid.uuid4()),
                        "transactionId": order_data["order_id"],
                        "amount": order_data["amount"]
                    },
                    "retry_policy": {
                        "max_attempts": 3,
                        "initial_delay_ms": 1000,
                        "max_delay_ms": 5000,
                        "backoff_multiplier": 2.0
                    },
                    "depends_on": ["fraud_check"]
                },
                {
                    "step_id": "create_billing",
                    "service_name": "billing-service",
                    "action_endpoint": f"{TEST_CONFIG['services']['billing_service']}/api/v1/billing",
                    "action_payload": {
                        "customerId": order_data["customer_id"],
                        "orderId": order_data["order_id"],
                        "billingType": "ORDER",
                        "items": order_data["items"],
                        "currency": order_data["currency"],
                        "dueDate": (datetime.utcnow() + timedelta(days=30)).isoformat()
                    },
                    "compensation_endpoint": f"{TEST_CONFIG['services']['billing_service']}/api/v1/billing/cancel",
                    "compensation_payload": {
                        "orderId": order_data["order_id"],
                        "reason": "saga_compensation"
                    },
                    "retry_policy": {
                        "max_attempts": 3,
                        "initial_delay_ms": 1000,
                        "max_delay_ms": 5000,
                        "backoff_multiplier": 2.0
                    },
                    "depends_on": ["reserve_funds"]
                },
                {
                    "step_id": "confirm_payment",
                    "service_name": "account-service",
                    "action_endpoint": f"{TEST_CONFIG['services']['account_service']}/api/v1/accounts/{order_data['account_id']}/confirm-reservation",
                    "action_payload": {
                        "reservationId": str(uuid.uuid4()),
                        "transactionId": order_data["order_id"],
                        "amount": order_data["amount"],
                        "description": f"Order payment: {order_data['order_id']}"
                    },
                    "compensation_endpoint": f"{TEST_CONFIG['services']['account_service']}/api/v1/accounts/{order_data['account_id']}/refund",
                    "compensation_payload": {
                        "transactionId": order_data["order_id"],
                        "amount": order_data["amount"],
                        "reason": "saga_compensation"
                    },
                    "retry_policy": {
                        "max_attempts": 3,
                        "initial_delay_ms": 1000,
                        "max_delay_ms": 5000,
                        "backoff_multiplier": 2.0
                    },
                    "depends_on": ["create_billing"]
                }
            ],
            "metadata": {
                "order_id": order_data["order_id"],
                "customer_id": order_data["customer_id"],
                "total_amount": order_data["amount"],
                "test_run": True
            },
            "timeout_seconds": 300
        }
        
        # Start saga via transaction coordinator
        response = await self.http_client.post(
            f"{TEST_CONFIG['services']['transaction_coordinator']}/sagas",
            json=saga_definition
        )
        
        assert response.status_code == 200, f"Failed to start saga: {response.text}"
        
        saga_response = response.json()
        saga_id = saga_response["id"]
        
        print(f"✅ Saga started successfully: {saga_id}")
        return saga_id
    
    async def _monitor_saga_execution(self, saga_id: str, timeout_seconds: int = 120) -> Dict:
        """Monitor saga execution until completion"""
        print(f"👀 Monitoring saga execution: {saga_id}")
        
        start_time = time.time()
        
        while time.time() - start_time < timeout_seconds:
            response = await self.http_client.get(
                f"{TEST_CONFIG['services']['transaction_coordinator']}/sagas/{saga_id}"
            )
            
            assert response.status_code == 200, f"Failed to get saga status: {response.text}"
            
            saga_status = response.json()
            status = saga_status["status"]
            
            print(f"📊 Saga {saga_id} status: {status}")
            
            if status in ["Completed", "Compensated", "Failed"]:
                print(f"🏁 Saga execution finished with status: {status}")
                return saga_status
            
            await asyncio.sleep(2)
        
        raise TimeoutError(f"Saga {saga_id} did not complete within {timeout_seconds} seconds")
    
    async def _verify_saga_results(self, saga_id: str, order_data: Dict):
        """Verify that all saga steps executed correctly"""
        print(f"🔍 Verifying saga results for: {saga_id}")
        
        # Verify outbox events were published
        await self._verify_outbox_events(order_data["order_id"])
        
        # Verify account balance changes
        await self._verify_account_changes(order_data["account_id"], order_data["amount"])
        
        # Verify billing record creation
        await self._verify_billing_record(order_data["customer_id"], order_data["order_id"])
        
        # Verify fraud assessment
        await self._verify_fraud_assessment(order_data["order_id"])
        
        print("✅ All saga results verified successfully")
    
    async def _verify_outbox_events(self, order_id: str):
        """Verify outbox events were created and published"""
        print(f"📤 Verifying outbox events for order: {order_id}")
        
        response = await self.http_client.get(
            f"{TEST_CONFIG['services']['outbox_publisher']}/api/v1/stats"
        )
        
        assert response.status_code == 200
        stats = response.json()
        
        assert stats["total_events"] > 0, "No outbox events found"
        print(f"✅ Found {stats['total_events']} outbox events")
    
    async def _verify_account_changes(self, account_id: str, expected_deduction: float):
        """Verify account balance was properly updated"""
        print(f"💰 Verifying account changes for: {account_id}")
        
        response = await self.http_client.get(
            f"{TEST_CONFIG['services']['account_service']}/api/v1/accounts/{account_id}"
        )
        
        assert response.status_code == 200
        account = response.json()
        
        # Account should have less balance after the transaction
        assert account["balance"] < 1000.00, "Account balance was not deducted"
        print(f"✅ Account balance updated: {account['balance']}")
    
    async def _verify_billing_record(self, customer_id: str, order_id: str):
        """Verify billing record was created"""
        print(f"🧾 Verifying billing record for customer: {customer_id}")
        
        response = await self.http_client.get(
            f"{TEST_CONFIG['services']['billing_service']}/api/v1/billing/customer/{customer_id}"
        )
        
        assert response.status_code == 200
        billing_records = response.json()
        
        # Find billing record for this order
        order_billing = next((b for b in billing_records if b.get("order_id") == order_id), None)
        assert order_billing is not None, "Billing record not found for order"
        
        print(f"✅ Billing record created: {order_billing['id']}")
    
    async def _verify_fraud_assessment(self, transaction_id: str):
        """Verify fraud assessment was performed"""
        print(f"🛡️ Verifying fraud assessment for transaction: {transaction_id}")
        
        response = await self.http_client.get(
            f"{TEST_CONFIG['services']['fraud_detection']}/api/v1/fraud/assessments/{transaction_id}"
        )
        
        assert response.status_code == 200
        assessment = response.json()
        
        assert assessment["transaction_id"] == transaction_id
        assert "fraud_score" in assessment
        assert "decision" in assessment
        
        print(f"✅ Fraud assessment completed: {assessment['decision']}")

# Test runner
async def run_integration_tests():
    """Run all integration tests"""
    test_suite = CrossServiceSagaTest()
    
    try:
        await test_suite.setup()
        
        # Run tests
        print("\n" + "="*60)
        print("🧪 CROSS-SERVICE SAGA INTEGRATION TESTS")
        print("="*60)
        
        await test_suite.test_complete_order_saga()
        
        print("\n" + "="*60)
        print("✅ ALL INTEGRATION TESTS PASSED!")
        print("="*60)
        
    except Exception as e:
        print(f"\n❌ Integration test failed: {e}")
        raise
    finally:
        await test_suite.teardown()

if __name__ == "__main__":
    asyncio.run(run_integration_tests())

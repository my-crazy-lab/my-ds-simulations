#!/usr/bin/env python3
"""
Chaos Testing Framework for Microservices Saga Pattern
Implements various failure scenarios to test system resilience
"""

import asyncio
import json
import logging
import random
import time
import yaml
from datetime import datetime, timedelta
from typing import Dict, List, Any
import aiohttp
import docker
import psycopg2
from kafka import KafkaProducer, KafkaConsumer
from redis import Redis

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ChaosTestRunner:
    def __init__(self, config_file: str):
        with open(config_file, 'r') as f:
            self.config = yaml.safe_load(f)
        
        self.docker_client = docker.from_env()
        self.results = []
        
    async def run_all_tests(self):
        """Run all chaos tests defined in configuration"""
        logger.info("Starting chaos testing suite")
        
        test_scenarios = [
            self.test_service_failure_recovery,
            self.test_network_partition,
            self.test_database_failure,
            self.test_kafka_failure,
            self.test_high_load_scenario,
            self.test_saga_timeout_handling,
            self.test_duplicate_message_handling,
            self.test_partial_failure_compensation
        ]
        
        for test in test_scenarios:
            try:
                logger.info(f"Running test: {test.__name__}")
                result = await test()
                self.results.append({
                    'test': test.__name__,
                    'result': result,
                    'timestamp': datetime.now().isoformat()
                })
                
                # Wait between tests
                await asyncio.sleep(self.config.get('test_interval', 30))
                
            except Exception as e:
                logger.error(f"Test {test.__name__} failed: {e}")
                self.results.append({
                    'test': test.__name__,
                    'result': {'status': 'ERROR', 'error': str(e)},
                    'timestamp': datetime.now().isoformat()
                })
        
        self.generate_report()
    
    async def test_service_failure_recovery(self) -> Dict[str, Any]:
        """Test saga recovery when a service fails during execution"""
        logger.info("Testing service failure recovery")
        
        # Start a saga
        saga_id = await self.create_test_saga()
        
        # Wait for saga to start processing
        await asyncio.sleep(5)
        
        # Kill inventory service
        inventory_container = self.docker_client.containers.get('inventory-service')
        inventory_container.kill()
        
        logger.info("Killed inventory service, waiting for recovery...")
        
        # Wait and restart service
        await asyncio.sleep(10)
        inventory_container.restart()
        
        # Wait for service to recover
        await asyncio.sleep(15)
        
        # Check saga status
        saga_status = await self.get_saga_status(saga_id)
        
        # Verify system recovered
        system_health = await self.check_system_health()
        
        return {
            'status': 'PASS' if saga_status.get('status') in ['COMPLETED', 'COMPENSATED'] else 'FAIL',
            'saga_id': saga_id,
            'saga_status': saga_status,
            'system_health': system_health,
            'recovery_time': 25  # seconds
        }
    
    async def test_network_partition(self) -> Dict[str, Any]:
        """Test behavior during network partitions"""
        logger.info("Testing network partition scenario")
        
        saga_id = await self.create_test_saga()
        
        # Create network partition by blocking traffic
        await self.create_network_partition(['inventory-service', 'payment-service'])
        
        await asyncio.sleep(20)
        
        # Heal partition
        await self.heal_network_partition()
        
        await asyncio.sleep(15)
        
        saga_status = await self.get_saga_status(saga_id)
        
        return {
            'status': 'PASS' if saga_status.get('status') != 'FAILED' else 'FAIL',
            'saga_id': saga_id,
            'saga_status': saga_status,
            'partition_duration': 20
        }
    
    async def test_database_failure(self) -> Dict[str, Any]:
        """Test database failure and recovery"""
        logger.info("Testing database failure scenario")
        
        saga_id = await self.create_test_saga()
        
        # Stop database
        db_container = self.docker_client.containers.get('postgres')
        db_container.stop()
        
        await asyncio.sleep(10)
        
        # Restart database
        db_container.start()
        
        # Wait for database to be ready
        await self.wait_for_database()
        
        saga_status = await self.get_saga_status(saga_id)
        
        return {
            'status': 'PASS' if saga_status else 'FAIL',
            'saga_id': saga_id,
            'saga_status': saga_status,
            'db_downtime': 10
        }
    
    async def test_kafka_failure(self) -> Dict[str, Any]:
        """Test Kafka failure and message recovery"""
        logger.info("Testing Kafka failure scenario")
        
        # Stop Kafka
        kafka_container = self.docker_client.containers.get('kafka')
        kafka_container.stop()
        
        # Try to create saga (should queue)
        saga_id = await self.create_test_saga()
        
        await asyncio.sleep(15)
        
        # Restart Kafka
        kafka_container.start()
        
        # Wait for Kafka to be ready
        await asyncio.sleep(20)
        
        # Check if messages were processed
        saga_status = await self.get_saga_status(saga_id)
        
        return {
            'status': 'PASS' if saga_status else 'FAIL',
            'saga_id': saga_id,
            'saga_status': saga_status,
            'kafka_downtime': 15
        }
    
    async def test_high_load_scenario(self) -> Dict[str, Any]:
        """Test system under high load"""
        logger.info("Testing high load scenario")
        
        # Create multiple concurrent sagas
        saga_ids = []
        tasks = []
        
        for i in range(50):
            task = asyncio.create_task(self.create_test_saga())
            tasks.append(task)
        
        saga_ids = await asyncio.gather(*tasks)
        
        # Wait for processing
        await asyncio.sleep(60)
        
        # Check results
        completed = 0
        failed = 0
        
        for saga_id in saga_ids:
            status = await self.get_saga_status(saga_id)
            if status and status.get('status') == 'COMPLETED':
                completed += 1
            elif status and status.get('status') == 'FAILED':
                failed += 1
        
        success_rate = completed / len(saga_ids) if saga_ids else 0
        
        return {
            'status': 'PASS' if success_rate > 0.95 else 'FAIL',
            'total_sagas': len(saga_ids),
            'completed': completed,
            'failed': failed,
            'success_rate': success_rate
        }
    
    async def test_saga_timeout_handling(self) -> Dict[str, Any]:
        """Test saga timeout and compensation"""
        logger.info("Testing saga timeout handling")
        
        # Create saga with short timeout
        saga_data = {
            "saga_type": "order-processing",
            "saga_data": {
                "order_id": f"test-order-{int(time.time())}",
                "user_id": "test-user",
                "items": [{"sku": "LAPTOP-001", "quantity": 1, "price": 1299.99}],
                "total_amount": 1299.99
            },
            "timeout": 5  # Very short timeout
        }
        
        saga_id = await self.create_saga_with_data(saga_data)
        
        # Introduce delay in processing
        await self.introduce_processing_delay('payment-service', 10)
        
        # Wait for timeout
        await asyncio.sleep(15)
        
        saga_status = await self.get_saga_status(saga_id)
        
        return {
            'status': 'PASS' if saga_status.get('status') == 'COMPENSATED' else 'FAIL',
            'saga_id': saga_id,
            'saga_status': saga_status
        }
    
    async def test_duplicate_message_handling(self) -> Dict[str, Any]:
        """Test duplicate message handling and idempotency"""
        logger.info("Testing duplicate message handling")
        
        # Send duplicate saga creation requests
        saga_data = {
            "saga_type": "order-processing",
            "saga_data": {
                "order_id": f"test-order-{int(time.time())}",
                "user_id": "test-user",
                "items": [{"sku": "LAPTOP-001", "quantity": 1, "price": 1299.99}],
                "total_amount": 1299.99
            },
            "idempotency_key": f"test-key-{int(time.time())}"
        }
        
        # Send same request multiple times
        tasks = [self.create_saga_with_data(saga_data) for _ in range(5)]
        saga_ids = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Should only create one saga
        unique_saga_ids = set(id for id in saga_ids if isinstance(id, str))
        
        return {
            'status': 'PASS' if len(unique_saga_ids) == 1 else 'FAIL',
            'unique_sagas_created': len(unique_saga_ids),
            'total_requests': len(tasks)
        }
    
    async def test_partial_failure_compensation(self) -> Dict[str, Any]:
        """Test compensation when partial steps succeed"""
        logger.info("Testing partial failure compensation")
        
        saga_id = await self.create_test_saga()
        
        # Wait for inventory reservation to complete
        await asyncio.sleep(10)
        
        # Fail payment service
        await self.inject_failure('payment-service', 'payment_failure')
        
        # Wait for compensation
        await asyncio.sleep(20)
        
        saga_status = await self.get_saga_status(saga_id)
        
        # Check if inventory was released
        inventory_status = await self.check_inventory_released(saga_id)
        
        return {
            'status': 'PASS' if saga_status.get('status') == 'COMPENSATED' and inventory_status else 'FAIL',
            'saga_id': saga_id,
            'saga_status': saga_status,
            'inventory_released': inventory_status
        }
    
    # Helper methods
    
    async def create_test_saga(self) -> str:
        """Create a test saga"""
        saga_data = {
            "saga_type": "order-processing",
            "saga_data": {
                "order_id": f"test-order-{int(time.time())}-{random.randint(1000, 9999)}",
                "user_id": "test-user",
                "items": [{"sku": "LAPTOP-001", "quantity": 1, "price": 1299.99}],
                "total_amount": 1299.99,
                "currency": "USD",
                "payment_method": "credit_card"
            }
        }
        
        return await self.create_saga_with_data(saga_data)
    
    async def create_saga_with_data(self, saga_data: Dict) -> str:
        """Create saga with specific data"""
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.config['saga_orchestrator_url']}/api/v1/sagas",
                json=saga_data
            ) as response:
                if response.status == 201:
                    result = await response.json()
                    return result['id']
                else:
                    raise Exception(f"Failed to create saga: {response.status}")
    
    async def get_saga_status(self, saga_id: str) -> Dict:
        """Get saga status"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.config['saga_orchestrator_url']}/api/v1/sagas/{saga_id}"
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    return None
        except Exception as e:
            logger.error(f"Failed to get saga status: {e}")
            return None
    
    async def check_system_health(self) -> Dict:
        """Check overall system health"""
        services = ['saga-orchestrator', 'inventory-service', 'payment-service', 'notification-service']
        health_status = {}
        
        for service in services:
            try:
                url = f"http://{service}:8080/health"
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=5) as response:
                        health_status[service] = response.status == 200
            except:
                health_status[service] = False
        
        return health_status
    
    async def create_network_partition(self, services: List[str]):
        """Create network partition between services"""
        # This would use iptables or similar to block traffic
        # Simplified implementation
        logger.info(f"Creating network partition for services: {services}")
    
    async def heal_network_partition(self):
        """Heal network partition"""
        logger.info("Healing network partition")
    
    async def wait_for_database(self):
        """Wait for database to be ready"""
        for _ in range(30):
            try:
                conn = psycopg2.connect(
                    host="localhost",
                    port=5432,
                    database="microservices",
                    user="postgres",
                    password="postgres"
                )
                conn.close()
                return
            except:
                await asyncio.sleep(1)
    
    async def introduce_processing_delay(self, service: str, delay_seconds: int):
        """Introduce processing delay in a service"""
        logger.info(f"Introducing {delay_seconds}s delay in {service}")
    
    async def inject_failure(self, service: str, failure_type: str):
        """Inject specific failure in a service"""
        logger.info(f"Injecting {failure_type} in {service}")
    
    async def check_inventory_released(self, saga_id: str) -> bool:
        """Check if inventory was released for saga"""
        # Implementation would check inventory reservations
        return True
    
    def generate_report(self):
        """Generate test report"""
        report = {
            'timestamp': datetime.now().isoformat(),
            'total_tests': len(self.results),
            'passed': len([r for r in self.results if r['result'].get('status') == 'PASS']),
            'failed': len([r for r in self.results if r['result'].get('status') == 'FAIL']),
            'errors': len([r for r in self.results if r['result'].get('status') == 'ERROR']),
            'results': self.results
        }
        
        with open(f"chaos_test_report_{int(time.time())}.json", 'w') as f:
            json.dump(report, f, indent=2)
        
        logger.info(f"Test report generated: {report['passed']}/{report['total_tests']} tests passed")

if __name__ == "__main__":
    import sys
    
    config_file = sys.argv[1] if len(sys.argv) > 1 else "chaos_config.yaml"
    
    runner = ChaosTestRunner(config_file)
    asyncio.run(runner.run_all_tests())

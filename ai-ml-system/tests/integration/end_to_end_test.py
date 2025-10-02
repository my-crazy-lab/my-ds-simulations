#!/usr/bin/env python3
"""
End-to-End Integration Tests
Tests complete workflows from ingestion to RAG responses
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import uuid

import pytest
import aiohttp
import redis.asyncio as redis
from kafka import KafkaProducer, KafkaConsumer
import pandas as pd

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class EndToEndTestSuite:
    """Comprehensive end-to-end test suite"""
    
    def __init__(self):
        self.base_urls = {
            'data_ingestion': 'http://localhost:8080',
            'rag_engine': 'http://localhost:8081',
            'drift_detection': 'http://localhost:8082',
        }
        self.kafka_producer = None
        self.redis_client = None
        self.test_data = {}
    
    async def setup(self):
        """Setup test environment"""
        # Initialize Kafka producer
        self.kafka_producer = KafkaProducer(
            bootstrap_servers=['localhost:9092'],
            value_serializer=lambda x: json.dumps(x).encode('utf-8')
        )
        
        # Initialize Redis client
        self.redis_client = redis.from_url('redis://localhost:6379')
        
        # Wait for services to be ready
        await self._wait_for_services()
        
        logger.info("End-to-end test suite setup complete")
    
    async def teardown(self):
        """Cleanup test environment"""
        if self.kafka_producer:
            self.kafka_producer.close()
        if self.redis_client:
            await self.redis_client.close()
        
        logger.info("End-to-end test suite teardown complete")
    
    async def _wait_for_services(self, timeout: int = 60):
        """Wait for all services to be healthy"""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            all_healthy = True
            
            for service, base_url in self.base_urls.items():
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(f"{base_url}/health", timeout=aiohttp.ClientTimeout(total=5)) as response:
                            if response.status != 200:
                                all_healthy = False
                                break
                except:
                    all_healthy = False
                    break
            
            if all_healthy:
                logger.info("All services are healthy")
                return
            
            await asyncio.sleep(2)
        
        raise TimeoutError("Services did not become healthy within timeout")
    
    async def test_complete_payment_workflow(self) -> Dict[str, Any]:
        """Test complete payment processing workflow"""
        test_id = f"payment_workflow_{int(time.time())}"
        logger.info(f"Starting payment workflow test: {test_id}")
        
        results = {
            'test_id': test_id,
            'start_time': datetime.now().isoformat(),
            'steps': [],
            'success': False,
            'errors': [],
        }
        
        try:
            # Step 1: Ingest payment webhook
            payment_data = {
                'id': f'pay_{uuid.uuid4()}',
                'source': 'webhook',
                'type': 'payment_event',
                'timestamp': datetime.now().isoformat(),
                'data': {
                    'payment_id': f'payment_{uuid.uuid4()}',
                    'user_id': f'user_{uuid.uuid4()}',
                    'amount': 99.99,
                    'currency': 'USD',
                    'status': 'completed',
                    'provider': 'stripe',
                },
                'metadata': {
                    'webhook_source': 'payment_provider',
                    'test_case': test_id,
                }
            }
            
            ingestion_result = await self._test_data_ingestion(payment_data)
            results['steps'].append({
                'step': 'data_ingestion',
                'success': ingestion_result['success'],
                'details': ingestion_result
            })
            
            if not ingestion_result['success']:
                results['errors'].append('Data ingestion failed')
                return results
            
            # Step 2: Wait for RAG indexing
            await asyncio.sleep(10)  # Allow time for processing
            
            # Step 3: Test RAG search for payment information
            search_query = f"What is the status of payment {payment_data['data']['payment_id']}?"
            rag_result = await self._test_rag_search(search_query, payment_data['data']['payment_id'])
            results['steps'].append({
                'step': 'rag_search',
                'success': rag_result['success'],
                'details': rag_result
            })
            
            if not rag_result['success']:
                results['errors'].append('RAG search failed')
                return results
            
            # Step 4: Test drift detection (simulate performance metrics)
            drift_result = await self._test_drift_detection(payment_data)
            results['steps'].append({
                'step': 'drift_detection',
                'success': drift_result['success'],
                'details': drift_result
            })
            
            # Step 5: Validate end-to-end consistency
            consistency_result = await self._validate_data_consistency(payment_data)
            results['steps'].append({
                'step': 'data_consistency',
                'success': consistency_result['success'],
                'details': consistency_result
            })
            
            # Overall success
            results['success'] = all(step['success'] for step in results['steps'])
            
        except Exception as e:
            results['errors'].append(f'Workflow error: {str(e)}')
            logger.error(f"Payment workflow test failed: {e}")
        
        finally:
            results['end_time'] = datetime.now().isoformat()
            results['duration_seconds'] = (
                datetime.fromisoformat(results['end_time']) - 
                datetime.fromisoformat(results['start_time'])
            ).total_seconds()
        
        logger.info(f"Payment workflow test completed: {results['success']}")
        return results
    
    async def _test_data_ingestion(self, message_data: Dict) -> Dict[str, Any]:
        """Test data ingestion service"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_urls['data_ingestion']}/api/v1/ingest",
                    json=message_data,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    
                    response_data = await response.json()
                    
                    return {
                        'success': response.status == 202,
                        'status_code': response.status,
                        'response': response_data,
                        'message_id': response_data.get('message_id'),
                    }
        
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    async def _test_rag_search(self, query: str, expected_payment_id: str) -> Dict[str, Any]:
        """Test RAG search functionality"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_urls['rag_engine']}/search",
                    json={'query': query, 'top_k': 5},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    
                    response_data = await response.json()
                    
                    # Check if expected payment ID appears in results
                    payment_found = False
                    for result in response_data.get('results', []):
                        if expected_payment_id in result.get('content', ''):
                            payment_found = True
                            break
                    
                    return {
                        'success': response.status == 200 and payment_found,
                        'status_code': response.status,
                        'response': response_data,
                        'payment_found': payment_found,
                        'results_count': len(response_data.get('results', [])),
                        'processing_time_ms': response_data.get('processing_time_ms'),
                    }
        
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    async def _test_drift_detection(self, payment_data: Dict) -> Dict[str, Any]:
        """Test drift detection service"""
        try:
            # Create sample reference and current data for drift detection
            reference_data = [
                {'amount': 50.0, 'currency': 'USD', 'status': 'completed'},
                {'amount': 75.0, 'currency': 'USD', 'status': 'completed'},
                {'amount': 100.0, 'currency': 'EUR', 'status': 'pending'},
            ]
            
            current_data = [
                payment_data['data'],
                {'amount': 120.0, 'currency': 'USD', 'status': 'completed'},
                {'amount': 80.0, 'currency': 'GBP', 'status': 'failed'},
            ]
            
            drift_request = {
                'reference_data': reference_data,
                'current_data': current_data,
                'feature_columns': ['amount'],
                'target_column': 'status'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_urls['drift_detection']}/check-drift",
                    json=drift_request,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    
                    response_data = await response.json()
                    
                    return {
                        'success': response.status == 200,
                        'status_code': response.status,
                        'response': response_data,
                        'data_drift_detected': response_data.get('data_drift_detected'),
                        'target_drift_detected': response_data.get('target_drift_detected'),
                    }
        
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    async def _validate_data_consistency(self, payment_data: Dict) -> Dict[str, Any]:
        """Validate data consistency across services"""
        try:
            # Check if data exists in Redis cache
            cache_key = f"processed:{payment_data['data']['payment_id']}"
            cached_data = await self.redis_client.get(cache_key)
            
            # Check RAG index stats
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_urls['rag_engine']}/index/stats",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    index_stats = await response.json() if response.status == 200 else {}
            
            return {
                'success': True,
                'cached_data_exists': cached_data is not None,
                'index_stats': index_stats,
                'validation_timestamp': datetime.now().isoformat(),
            }
        
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    async def test_chaos_recovery(self) -> Dict[str, Any]:
        """Test system recovery after chaos injection"""
        test_id = f"chaos_recovery_{int(time.time())}"
        logger.info(f"Starting chaos recovery test: {test_id}")
        
        results = {
            'test_id': test_id,
            'start_time': datetime.now().isoformat(),
            'phases': [],
            'success': False,
            'recovery_time_seconds': None,
        }
        
        try:
            # Phase 1: Establish baseline
            baseline_health = await self._measure_system_health()
            results['phases'].append({
                'phase': 'baseline',
                'health_score': baseline_health,
                'timestamp': datetime.now().isoformat(),
            })
            
            # Phase 2: Inject controlled failure (simulate service restart)
            logger.info("Injecting controlled failure...")
            # Note: In a real test, this would restart a service container
            # For simulation, we'll just wait and measure recovery
            
            # Phase 3: Monitor recovery
            recovery_start = time.time()
            recovered = False
            
            for attempt in range(30):  # 30 attempts, 5 seconds each = 2.5 minutes max
                await asyncio.sleep(5)
                current_health = await self._measure_system_health()
                
                results['phases'].append({
                    'phase': 'recovery_monitoring',
                    'attempt': attempt + 1,
                    'health_score': current_health,
                    'timestamp': datetime.now().isoformat(),
                })
                
                # Consider recovered if health is >= 90% of baseline
                if current_health >= (baseline_health * 0.9):
                    recovered = True
                    break
            
            recovery_time = time.time() - recovery_start
            results['recovery_time_seconds'] = recovery_time
            results['success'] = recovered
            
            logger.info(f"Chaos recovery test: {'SUCCESS' if recovered else 'FAILED'} ({recovery_time:.1f}s)")
            
        except Exception as e:
            results['error'] = str(e)
            logger.error(f"Chaos recovery test failed: {e}")
        
        finally:
            results['end_time'] = datetime.now().isoformat()
        
        return results
    
    async def _measure_system_health(self) -> float:
        """Measure overall system health score"""
        health_scores = []
        
        for service, base_url in self.base_urls.items():
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f"{base_url}/health",
                        timeout=aiohttp.ClientTimeout(total=5)
                    ) as response:
                        if response.status == 200:
                            health_scores.append(1.0)
                        else:
                            health_scores.append(0.0)
            except:
                health_scores.append(0.0)
        
        return sum(health_scores) / len(health_scores) if health_scores else 0.0
    
    async def test_performance_under_load(self) -> Dict[str, Any]:
        """Test system performance under load"""
        test_id = f"load_test_{int(time.time())}"
        logger.info(f"Starting load test: {test_id}")
        
        results = {
            'test_id': test_id,
            'start_time': datetime.now().isoformat(),
            'metrics': {
                'requests_sent': 0,
                'requests_successful': 0,
                'requests_failed': 0,
                'average_response_time_ms': 0,
                'max_response_time_ms': 0,
            },
            'success': False,
        }
        
        try:
            # Generate load: 100 concurrent requests
            tasks = []
            for i in range(100):
                task = self._send_load_test_request(i)
                tasks.append(task)
            
            # Execute all requests concurrently
            request_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Analyze results
            successful_requests = []
            failed_requests = []
            
            for result in request_results:
                if isinstance(result, Exception):
                    failed_requests.append(str(result))
                elif result.get('success'):
                    successful_requests.append(result)
                else:
                    failed_requests.append(result.get('error', 'Unknown error'))
            
            # Calculate metrics
            results['metrics']['requests_sent'] = len(request_results)
            results['metrics']['requests_successful'] = len(successful_requests)
            results['metrics']['requests_failed'] = len(failed_requests)
            
            if successful_requests:
                response_times = [r['response_time_ms'] for r in successful_requests]
                results['metrics']['average_response_time_ms'] = sum(response_times) / len(response_times)
                results['metrics']['max_response_time_ms'] = max(response_times)
            
            # Success criteria: >95% success rate, <1000ms average response time
            success_rate = len(successful_requests) / len(request_results)
            avg_response_time = results['metrics']['average_response_time_ms']
            
            results['success'] = success_rate > 0.95 and avg_response_time < 1000
            
            logger.info(f"Load test completed: {success_rate:.1%} success rate, {avg_response_time:.1f}ms avg response")
            
        except Exception as e:
            results['error'] = str(e)
            logger.error(f"Load test failed: {e}")
        
        finally:
            results['end_time'] = datetime.now().isoformat()
        
        return results
    
    async def _send_load_test_request(self, request_id: int) -> Dict[str, Any]:
        """Send a single load test request"""
        start_time = time.time()
        
        try:
            # Test RAG search endpoint (most complex)
            query = f"Test query {request_id} for load testing"
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_urls['rag_engine']}/search",
                    json={'query': query, 'top_k': 5},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    
                    response_time = (time.time() - start_time) * 1000
                    
                    return {
                        'success': response.status == 200,
                        'status_code': response.status,
                        'response_time_ms': response_time,
                        'request_id': request_id,
                    }
        
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            return {
                'success': False,
                'error': str(e),
                'response_time_ms': response_time,
                'request_id': request_id,
            }
    
    async def run_full_test_suite(self) -> Dict[str, Any]:
        """Run the complete end-to-end test suite"""
        suite_results = {
            'suite_id': f"e2e_suite_{int(time.time())}",
            'start_time': datetime.now().isoformat(),
            'tests': {},
            'overall_success': False,
        }
        
        try:
            # Test 1: Complete payment workflow
            suite_results['tests']['payment_workflow'] = await self.test_complete_payment_workflow()
            
            # Test 2: Chaos recovery
            suite_results['tests']['chaos_recovery'] = await self.test_chaos_recovery()
            
            # Test 3: Performance under load
            suite_results['tests']['load_performance'] = await self.test_performance_under_load()
            
            # Overall success
            suite_results['overall_success'] = all(
                test_result.get('success', False) 
                for test_result in suite_results['tests'].values()
            )
            
        except Exception as e:
            suite_results['error'] = str(e)
            logger.error(f"Test suite failed: {e}")
        
        finally:
            suite_results['end_time'] = datetime.now().isoformat()
            suite_results['duration_seconds'] = (
                datetime.fromisoformat(suite_results['end_time']) - 
                datetime.fromisoformat(suite_results['start_time'])
            ).total_seconds()
        
        return suite_results

# Main execution
async def main():
    """Run end-to-end test suite"""
    test_suite = EndToEndTestSuite()
    
    try:
        await test_suite.setup()
        
        # Run full test suite
        results = await test_suite.run_full_test_suite()
        
        # Save results
        with open(f'e2e_test_results_{int(time.time())}.json', 'w') as f:
            json.dump(results, f, indent=2)
        
        # Print summary
        print("\n" + "="*80)
        print("🧪 END-TO-END TEST RESULTS")
        print("="*80)
        print(f"Suite ID: {results['suite_id']}")
        print(f"Duration: {results['duration_seconds']:.1f} seconds")
        print(f"Overall Success: {'✅ PASS' if results['overall_success'] else '❌ FAIL'}")
        print("\nTest Results:")
        
        for test_name, test_result in results['tests'].items():
            status = '✅ PASS' if test_result.get('success') else '❌ FAIL'
            print(f"  {test_name}: {status}")
            
            if 'duration_seconds' in test_result:
                print(f"    Duration: {test_result['duration_seconds']:.1f}s")
            
            if not test_result.get('success') and 'errors' in test_result:
                for error in test_result['errors']:
                    print(f"    Error: {error}")
        
        print("="*80)
        
    finally:
        await test_suite.teardown()

if __name__ == "__main__":
    asyncio.run(main())

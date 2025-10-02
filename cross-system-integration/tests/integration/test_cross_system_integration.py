#!/usr/bin/env python3
"""
Integration tests for cross-system functionality
"""

import pytest
import asyncio
import httpx
import json
import time
from datetime import datetime
from typing import Dict, Any

# Test configuration
TEST_CONFIG = {
    'event_bus_url': 'http://localhost:8090',
    'orchestrator_url': 'http://localhost:8091',
    'chatops_url': 'http://localhost:8092',
    'timeout': 30.0
}

class CrossSystemIntegrationTest:
    """Integration test suite for cross-system functionality"""
    
    def __init__(self):
        self.clients = {}
        self.test_session_id = f"test_session_{int(time.time())}"
        
    async def setup(self):
        """Setup test clients and verify services are running"""
        self.clients = {
            'event_bus': httpx.AsyncClient(base_url=TEST_CONFIG['event_bus_url']),
            'orchestrator': httpx.AsyncClient(base_url=TEST_CONFIG['orchestrator_url']),
            'chatops': httpx.AsyncClient(base_url=TEST_CONFIG['chatops_url'])
        }
        
        # Verify all services are healthy
        for service_name, client in self.clients.items():
            try:
                response = await client.get('/health', timeout=TEST_CONFIG['timeout'])
                assert response.status_code == 200, f"{service_name} is not healthy"
                print(f"✅ {service_name} is healthy")
            except Exception as e:
                pytest.fail(f"❌ {service_name} health check failed: {e}")
                
    async def teardown(self):
        """Cleanup test clients"""
        for client in self.clients.values():
            await client.aclose()
            
    async def test_end_to_end_saga_workflow(self) -> Dict[str, Any]:
        """Test complete saga workflow from ChatOps to execution"""
        print("\n🔄 Testing end-to-end saga workflow...")
        
        results = {
            'test_name': 'end_to_end_saga_workflow',
            'steps': [],
            'success': True,
            'error': None
        }
        
        try:
            # Step 1: Use ChatOps to start a saga
            print("Step 1: Starting saga via ChatOps...")
            chatops_request = {
                'session_id': self.test_session_id,
                'user_id': 'integration_test',
                'message': 'start saga payment_saga'
            }
            
            response = await self.clients['chatops'].post('/api/v1/chat', json=chatops_request)
            assert response.status_code == 200
            
            chat_response = response.json()
            assert chat_response['intent'] == 'execute_operation'
            assert 'Saga Started Successfully' in chat_response['response']
            
            results['steps'].append({
                'step': 'chatops_start_saga',
                'status': 'success',
                'response_time': chat_response.get('processing_time', 0)
            })
            
            # Extract execution ID from response
            execution_id = None
            if 'exec_' in chat_response['response']:
                # Simple extraction - in real implementation, would parse more carefully
                lines = chat_response['response'].split('\n')
                for line in lines:
                    if 'Execution ID:' in line:
                        execution_id = line.split(':')[1].strip()
                        break
            
            print(f"✅ Saga started via ChatOps, execution_id: {execution_id}")
            
            # Step 2: Query saga status via orchestrator API
            print("Step 2: Querying saga status...")
            response = await self.clients['orchestrator'].get('/api/v1/sagas')
            assert response.status_code == 200
            
            sagas_data = response.json()
            assert 'executions' in sagas_data
            
            # Find our execution
            our_execution = None
            for execution in sagas_data['executions']:
                if execution_id and execution['id'] == execution_id:
                    our_execution = execution
                    break
            
            if our_execution:
                print(f"✅ Found saga execution: {our_execution['status']}")
                results['steps'].append({
                    'step': 'query_saga_status',
                    'status': 'success',
                    'saga_status': our_execution['status']
                })
            else:
                print("⚠️ Saga execution not found in active list (may have completed)")
                results['steps'].append({
                    'step': 'query_saga_status',
                    'status': 'completed_or_not_found'
                })
            
            # Step 3: Use ChatOps to check system status
            print("Step 3: Checking system status via ChatOps...")
            status_request = {
                'session_id': self.test_session_id,
                'user_id': 'integration_test',
                'message': 'what is the system status?'
            }
            
            response = await self.clients['chatops'].post('/api/v1/chat', json=status_request)
            assert response.status_code == 200
            
            status_response = response.json()
            assert status_response['intent'] == 'system_status'
            assert 'System Status Report' in status_response['response']
            
            results['steps'].append({
                'step': 'chatops_system_status',
                'status': 'success',
                'response_time': status_response.get('processing_time', 0)
            })
            
            print("✅ System status retrieved via ChatOps")
            
            # Step 4: Test troubleshooting assistance
            print("Step 4: Testing troubleshooting assistance...")
            troubleshoot_request = {
                'session_id': self.test_session_id,
                'user_id': 'integration_test',
                'message': 'help me troubleshoot saga failures'
            }
            
            response = await self.clients['chatops'].post('/api/v1/chat', json=troubleshoot_request)
            assert response.status_code == 200
            
            troubleshoot_response = response.json()
            assert troubleshoot_response['intent'] == 'troubleshoot'
            assert 'Troubleshooting Assistance' in troubleshoot_response['response']
            
            results['steps'].append({
                'step': 'chatops_troubleshoot',
                'status': 'success',
                'response_time': troubleshoot_response.get('processing_time', 0)
            })
            
            print("✅ Troubleshooting assistance working")
            
            print("🎉 End-to-end saga workflow test completed successfully!")
            
        except Exception as e:
            results['success'] = False
            results['error'] = str(e)
            print(f"❌ End-to-end test failed: {e}")
            
        return results
        
    async def test_event_bus_routing(self) -> Dict[str, Any]:
        """Test event bus routing functionality"""
        print("\n📡 Testing event bus routing...")
        
        results = {
            'test_name': 'event_bus_routing',
            'steps': [],
            'success': True,
            'error': None
        }
        
        try:
            # Step 1: Publish an event
            print("Step 1: Publishing test event...")
            test_event = {
                'type': 'saga.started',
                'source': 'microservices',
                'data': {
                    'saga_id': 'test_saga',
                    'correlation_id': f'test_corr_{int(time.time())}',
                    'user_id': 'integration_test'
                },
                'metadata': {
                    'priority': 'normal',
                    'tags': ['test', 'integration']
                }
            }
            
            response = await self.clients['event_bus'].post('/api/v1/events', json=test_event)
            assert response.status_code == 200
            
            event_response = response.json()
            assert 'event_id' in event_response
            
            results['steps'].append({
                'step': 'publish_event',
                'status': 'success',
                'event_id': event_response['event_id']
            })
            
            print(f"✅ Event published: {event_response['event_id']}")
            
            # Step 2: Query events
            print("Step 2: Querying events...")
            response = await self.clients['event_bus'].get('/api/v1/events?limit=10')
            assert response.status_code == 200
            
            events_data = response.json()
            assert 'events' in events_data
            
            results['steps'].append({
                'step': 'query_events',
                'status': 'success',
                'event_count': len(events_data['events'])
            })
            
            print(f"✅ Retrieved {len(events_data['events'])} events")
            
            # Step 3: Check system status
            print("Step 3: Checking event bus status...")
            response = await self.clients['event_bus'].get('/api/v1/status')
            assert response.status_code == 200
            
            status_data = response.json()
            assert 'status' in status_data
            
            results['steps'].append({
                'step': 'check_status',
                'status': 'success',
                'system_status': status_data['status']
            })
            
            print("✅ Event bus status check completed")
            
            print("🎉 Event bus routing test completed successfully!")
            
        except Exception as e:
            results['success'] = False
            results['error'] = str(e)
            print(f"❌ Event bus routing test failed: {e}")
            
        return results
        
    async def test_ml_prediction_integration(self) -> Dict[str, Any]:
        """Test ML prediction integration"""
        print("\n🤖 Testing ML prediction integration...")
        
        results = {
            'test_name': 'ml_prediction_integration',
            'steps': [],
            'success': True,
            'error': None
        }
        
        try:
            # Step 1: Start a saga and get ML prediction
            print("Step 1: Starting saga with ML prediction...")
            saga_request = {
                'saga_id': 'payment_saga',
                'correlation_id': f'ml_test_{int(time.time())}',
                'context': {
                    'user_id': 'ml_test_user',
                    'amount': 150.0,
                    'system_load': 0.3,
                    'historical_success_rate': 0.95
                }
            }
            
            response = await self.clients['orchestrator'].post('/api/v1/sagas/start', json=saga_request)
            assert response.status_code == 200
            
            saga_response = response.json()
            assert 'execution_id' in saga_response
            assert 'ml_prediction' in saga_response
            
            ml_prediction = saga_response['ml_prediction']
            assert 'failure_probability' in ml_prediction
            assert 'risk_level' in ml_prediction
            assert 'confidence' in ml_prediction
            
            results['steps'].append({
                'step': 'start_saga_with_ml',
                'status': 'success',
                'execution_id': saga_response['execution_id'],
                'ml_prediction': ml_prediction
            })
            
            print(f"✅ Saga started with ML prediction:")
            print(f"   Risk Level: {ml_prediction['risk_level']}")
            print(f"   Failure Probability: {ml_prediction['failure_probability']:.3f}")
            print(f"   Confidence: {ml_prediction['confidence']:.3f}")
            
            # Step 2: Verify prediction quality
            print("Step 2: Verifying prediction quality...")
            
            # Basic validation of prediction values
            assert 0.0 <= ml_prediction['failure_probability'] <= 1.0
            assert 0.0 <= ml_prediction['confidence'] <= 1.0
            assert ml_prediction['risk_level'] in ['low', 'medium', 'high', 'critical']
            
            results['steps'].append({
                'step': 'validate_prediction',
                'status': 'success',
                'validation': 'passed'
            })
            
            print("✅ ML prediction validation passed")
            
            # Step 3: Test ChatOps integration with ML insights
            print("Step 3: Testing ChatOps ML integration...")
            chatops_request = {
                'session_id': self.test_session_id,
                'user_id': 'ml_integration_test',
                'message': f'show saga status for {saga_response["execution_id"]}'
            }
            
            response = await self.clients['chatops'].post('/api/v1/chat', json=chatops_request)
            assert response.status_code == 200
            
            chat_response = response.json()
            # ChatOps should provide information about the saga
            assert chat_response['intent'] in ['saga_status', 'general_query']
            
            results['steps'].append({
                'step': 'chatops_ml_integration',
                'status': 'success',
                'response_time': chat_response.get('processing_time', 0)
            })
            
            print("✅ ChatOps ML integration working")
            
            print("🎉 ML prediction integration test completed successfully!")
            
        except Exception as e:
            results['success'] = False
            results['error'] = str(e)
            print(f"❌ ML prediction integration test failed: {e}")
            
        return results
        
    async def test_performance_under_load(self) -> Dict[str, Any]:
        """Test system performance under moderate load"""
        print("\n⚡ Testing performance under load...")
        
        results = {
            'test_name': 'performance_under_load',
            'steps': [],
            'success': True,
            'error': None,
            'metrics': {}
        }
        
        try:
            # Step 1: Concurrent ChatOps requests
            print("Step 1: Testing concurrent ChatOps requests...")
            
            async def make_chatops_request(i):
                request = {
                    'session_id': f'load_test_{i}',
                    'user_id': f'load_user_{i}',
                    'message': 'what is the system status?'
                }
                start_time = time.time()
                response = await self.clients['chatops'].post('/api/v1/chat', json=request)
                end_time = time.time()
                return {
                    'status_code': response.status_code,
                    'response_time': end_time - start_time,
                    'request_id': i
                }
            
            # Make 10 concurrent requests
            concurrent_requests = 10
            start_time = time.time()
            tasks = [make_chatops_request(i) for i in range(concurrent_requests)]
            responses = await asyncio.gather(*tasks, return_exceptions=True)
            total_time = time.time() - start_time
            
            # Analyze results
            successful_requests = [r for r in responses if not isinstance(r, Exception) and r['status_code'] == 200]
            failed_requests = [r for r in responses if isinstance(r, Exception) or (hasattr(r, 'status_code') and r['status_code'] != 200)]
            
            avg_response_time = sum(r['response_time'] for r in successful_requests) / len(successful_requests) if successful_requests else 0
            
            results['steps'].append({
                'step': 'concurrent_chatops_requests',
                'status': 'success' if len(successful_requests) >= concurrent_requests * 0.8 else 'partial_failure',
                'successful_requests': len(successful_requests),
                'failed_requests': len(failed_requests),
                'avg_response_time': avg_response_time,
                'total_time': total_time
            })
            
            print(f"✅ Concurrent requests: {len(successful_requests)}/{concurrent_requests} successful")
            print(f"   Average response time: {avg_response_time:.3f}s")
            
            # Step 2: Sequential saga starts
            print("Step 2: Testing sequential saga starts...")
            
            saga_times = []
            successful_sagas = 0
            
            for i in range(5):  # Start 5 sagas sequentially
                saga_request = {
                    'saga_id': 'payment_saga',
                    'correlation_id': f'perf_test_{i}_{int(time.time())}',
                    'context': {'user_id': f'perf_user_{i}', 'amount': 100.0}
                }
                
                start_time = time.time()
                try:
                    response = await self.clients['orchestrator'].post('/api/v1/sagas/start', json=saga_request)
                    end_time = time.time()
                    
                    if response.status_code == 200:
                        successful_sagas += 1
                        saga_times.append(end_time - start_time)
                        
                except Exception as e:
                    print(f"   Saga {i} failed: {e}")
                    
            avg_saga_time = sum(saga_times) / len(saga_times) if saga_times else 0
            
            results['steps'].append({
                'step': 'sequential_saga_starts',
                'status': 'success' if successful_sagas >= 4 else 'partial_failure',
                'successful_sagas': successful_sagas,
                'avg_saga_start_time': avg_saga_time
            })
            
            print(f"✅ Sequential sagas: {successful_sagas}/5 successful")
            print(f"   Average start time: {avg_saga_time:.3f}s")
            
            # Overall performance metrics
            results['metrics'] = {
                'chatops_avg_response_time': avg_response_time,
                'saga_avg_start_time': avg_saga_time,
                'concurrent_success_rate': len(successful_requests) / concurrent_requests,
                'sequential_success_rate': successful_sagas / 5
            }
            
            print("🎉 Performance under load test completed!")
            
        except Exception as e:
            results['success'] = False
            results['error'] = str(e)
            print(f"❌ Performance test failed: {e}")
            
        return results

@pytest.mark.asyncio
async def test_cross_system_integration():
    """Main integration test function"""
    print("🚀 Starting Cross-System Integration Tests")
    print("=" * 60)
    
    test_suite = CrossSystemIntegrationTest()
    
    try:
        # Setup
        await test_suite.setup()
        
        # Run all tests
        test_results = []
        
        # Test 1: End-to-end saga workflow
        result1 = await test_suite.test_end_to_end_saga_workflow()
        test_results.append(result1)
        
        # Test 2: Event bus routing
        result2 = await test_suite.test_event_bus_routing()
        test_results.append(result2)
        
        # Test 3: ML prediction integration
        result3 = await test_suite.test_ml_prediction_integration()
        test_results.append(result3)
        
        # Test 4: Performance under load
        result4 = await test_suite.test_performance_under_load()
        test_results.append(result4)
        
        # Summary
        print("\n" + "=" * 60)
        print("📊 INTEGRATION TEST SUMMARY")
        print("=" * 60)
        
        total_tests = len(test_results)
        successful_tests = sum(1 for r in test_results if r['success'])
        
        for result in test_results:
            status_icon = "✅" if result['success'] else "❌"
            print(f"{status_icon} {result['test_name']}: {'PASSED' if result['success'] else 'FAILED'}")
            if not result['success'] and result['error']:
                print(f"   Error: {result['error']}")
                
        print(f"\nOverall Success Rate: {successful_tests}/{total_tests} ({successful_tests/total_tests*100:.1f}%)")
        
        # Assert overall success
        assert successful_tests == total_tests, f"Integration tests failed: {total_tests - successful_tests} out of {total_tests} tests failed"
        
        print("\n🎉 All integration tests passed successfully!")
        
    finally:
        # Cleanup
        await test_suite.teardown()

if __name__ == '__main__':
    asyncio.run(test_cross_system_integration())

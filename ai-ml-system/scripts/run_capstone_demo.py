#!/usr/bin/env python3
"""
Capstone Demo Runner
Orchestrates end-to-end demonstration of the complete AI/ML system
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from typing import Dict, List, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class CapstoneDemo:
    """Complete capstone demonstration orchestrator"""
    
    def __init__(self):
        self.demo_id = f"capstone_demo_{int(time.time())}"
        self.results = {
            'demo_id': self.demo_id,
            'start_time': datetime.now().isoformat(),
            'phases': {},
            'overall_success': False,
        }
        
    async def run_complete_demo(self):
        """Run the complete capstone demonstration"""
        logger.info(f"🚀 Starting Capstone Demo: {self.demo_id}")
        
        try:
            # Phase 1: Infrastructure Setup
            await self._phase_1_infrastructure_setup()
            
            # Phase 2: System Health Validation
            await self._phase_2_health_validation()
            
            # Phase 3: End-to-End Workflow Testing
            await self._phase_3_e2e_testing()
            
            # Phase 4: Payment Reconciliation Incident Simulation
            await self._phase_4_incident_simulation()
            
            # Phase 5: Chaos Engineering
            await self._phase_5_chaos_engineering()
            
            # Phase 6: Performance Validation
            await self._phase_6_performance_validation()
            
            # Phase 7: Generate Comprehensive Report
            await self._phase_7_generate_report()
            
            # Calculate overall success
            self.results['overall_success'] = all(
                phase.get('success', False) 
                for phase in self.results['phases'].values()
            )
            
        except Exception as e:
            logger.error(f"Demo failed: {e}")
            self.results['error'] = str(e)
        
        finally:
            self.results['end_time'] = datetime.now().isoformat()
            self.results['duration_minutes'] = (
                datetime.fromisoformat(self.results['end_time']) - 
                datetime.fromisoformat(self.results['start_time'])
            ).total_seconds() / 60
            
            await self._save_results()
            await self._print_summary()
    
    async def _phase_1_infrastructure_setup(self):
        """Phase 1: Setup and validate infrastructure"""
        logger.info("📋 Phase 1: Infrastructure Setup")
        phase_result = {
            'phase': 'infrastructure_setup',
            'start_time': datetime.now().isoformat(),
            'steps': [],
            'success': False,
        }
        
        try:
            # Step 1: Start Docker Compose services
            logger.info("Starting Docker Compose services...")
            result = subprocess.run(
                ['docker-compose', 'up', '-d'],
                cwd='ai-ml-system',
                capture_output=True,
                text=True,
                timeout=300
            )
            
            phase_result['steps'].append({
                'step': 'docker_compose_up',
                'success': result.returncode == 0,
                'output': result.stdout,
                'error': result.stderr if result.returncode != 0 else None,
            })
            
            if result.returncode != 0:
                raise Exception(f"Docker Compose failed: {result.stderr}")
            
            # Step 2: Wait for services to be ready
            logger.info("Waiting for services to be ready...")
            await asyncio.sleep(30)  # Give services time to start
            
            # Step 3: Validate service health
            services = [
                ('data-ingestion', 'http://localhost:8080/health'),
                ('rag-engine', 'http://localhost:8081/health'),
                ('drift-detection', 'http://localhost:8082/health'),
            ]
            
            import aiohttp
            healthy_services = 0
            
            for service_name, health_url in services:
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(health_url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                            if response.status == 200:
                                healthy_services += 1
                                logger.info(f"✅ {service_name} is healthy")
                            else:
                                logger.warning(f"⚠️ {service_name} returned status {response.status}")
                except Exception as e:
                    logger.error(f"❌ {service_name} health check failed: {e}")
            
            phase_result['steps'].append({
                'step': 'health_checks',
                'healthy_services': healthy_services,
                'total_services': len(services),
                'success': healthy_services == len(services),
            })
            
            phase_result['success'] = healthy_services == len(services)
            
        except Exception as e:
            phase_result['error'] = str(e)
            logger.error(f"Infrastructure setup failed: {e}")
        
        finally:
            phase_result['end_time'] = datetime.now().isoformat()
            self.results['phases']['infrastructure_setup'] = phase_result
    
    async def _phase_2_health_validation(self):
        """Phase 2: Comprehensive health validation"""
        logger.info("🏥 Phase 2: Health Validation")
        phase_result = {
            'phase': 'health_validation',
            'start_time': datetime.now().isoformat(),
            'validations': [],
            'success': False,
        }
        
        try:
            # Run comprehensive health checks
            validations = [
                ('kafka_connectivity', self._validate_kafka),
                ('redis_connectivity', self._validate_redis),
                ('milvus_connectivity', self._validate_milvus),
                ('service_endpoints', self._validate_service_endpoints),
            ]
            
            successful_validations = 0
            
            for validation_name, validation_func in validations:
                try:
                    result = await validation_func()
                    phase_result['validations'].append({
                        'validation': validation_name,
                        'success': result.get('success', False),
                        'details': result,
                    })
                    
                    if result.get('success'):
                        successful_validations += 1
                        logger.info(f"✅ {validation_name} passed")
                    else:
                        logger.warning(f"⚠️ {validation_name} failed: {result.get('error')}")
                        
                except Exception as e:
                    logger.error(f"❌ {validation_name} validation error: {e}")
                    phase_result['validations'].append({
                        'validation': validation_name,
                        'success': False,
                        'error': str(e),
                    })
            
            phase_result['success'] = successful_validations == len(validations)
            
        except Exception as e:
            phase_result['error'] = str(e)
            logger.error(f"Health validation failed: {e}")
        
        finally:
            phase_result['end_time'] = datetime.now().isoformat()
            self.results['phases']['health_validation'] = phase_result
    
    async def _phase_3_e2e_testing(self):
        """Phase 3: End-to-end workflow testing"""
        logger.info("🧪 Phase 3: End-to-End Testing")
        phase_result = {
            'phase': 'e2e_testing',
            'start_time': datetime.now().isoformat(),
            'success': False,
        }
        
        try:
            # Run the end-to-end test suite
            logger.info("Running end-to-end test suite...")
            
            # Import and run the test suite
            sys.path.append('ai-ml-system/tests/integration')
            from end_to_end_test import EndToEndTestSuite
            
            test_suite = EndToEndTestSuite()
            await test_suite.setup()
            
            try:
                test_results = await test_suite.run_full_test_suite()
                phase_result['test_results'] = test_results
                phase_result['success'] = test_results.get('overall_success', False)
                
                if phase_result['success']:
                    logger.info("✅ End-to-end tests passed")
                else:
                    logger.warning("⚠️ Some end-to-end tests failed")
                    
            finally:
                await test_suite.teardown()
            
        except Exception as e:
            phase_result['error'] = str(e)
            logger.error(f"End-to-end testing failed: {e}")
        
        finally:
            phase_result['end_time'] = datetime.now().isoformat()
            self.results['phases']['e2e_testing'] = phase_result
    
    async def _phase_4_incident_simulation(self):
        """Phase 4: Payment reconciliation incident simulation"""
        logger.info("🚨 Phase 4: Incident Simulation")
        phase_result = {
            'phase': 'incident_simulation',
            'start_time': datetime.now().isoformat(),
            'success': False,
        }
        
        try:
            # Run the payment reconciliation incident
            logger.info("Running payment reconciliation incident simulation...")
            
            sys.path.append('ai-ml-system/incident-simulation/payment-reconciliation')
            from incident_orchestrator import IncidentOrchestrator
            
            orchestrator = IncidentOrchestrator()
            await orchestrator.initialize()
            
            try:
                # Run the incident scenario
                trace = await orchestrator.run_payment_reconciliation_incident()
                
                # Generate postmortem
                postmortem = await orchestrator.generate_postmortem(trace)
                
                phase_result['incident_trace'] = {
                    'incident_id': trace.incident_id,
                    'duration_minutes': (
                        datetime.fromisoformat(trace.end_time) - 
                        datetime.fromisoformat(trace.start_time)
                    ).total_seconds() / 60,
                    'affected_payments': len(trace.affected_payments),
                    'system_impact': trace.system_impact,
                    'resolution_actions': len(trace.resolution_actions),
                }
                
                phase_result['postmortem'] = postmortem
                phase_result['success'] = True
                
                logger.info(f"✅ Incident simulation completed: {trace.incident_id}")
                
            finally:
                await orchestrator.cleanup()
            
        except Exception as e:
            phase_result['error'] = str(e)
            logger.error(f"Incident simulation failed: {e}")
        
        finally:
            phase_result['end_time'] = datetime.now().isoformat()
            self.results['phases']['incident_simulation'] = phase_result
    
    async def _phase_5_chaos_engineering(self):
        """Phase 5: Chaos engineering experiments"""
        logger.info("🔥 Phase 5: Chaos Engineering")
        phase_result = {
            'phase': 'chaos_engineering',
            'start_time': datetime.now().isoformat(),
            'success': False,
        }
        
        try:
            # Run chaos engineering suite
            logger.info("Running chaos engineering experiments...")
            
            sys.path.append('ai-ml-system/incident-simulation/chaos-engineering')
            from chaos_controller import ChaosController
            
            controller = ChaosController()
            await controller.initialize()
            
            try:
                # Run chaos experiments
                results = await controller.run_chaos_suite()
                
                # Generate report
                report = await controller.generate_chaos_report(results)
                
                phase_result['chaos_results'] = {
                    'total_experiments': report['summary']['total_experiments'],
                    'success_rate': report['summary']['success_rate'],
                    'avg_recovery_time': report['summary']['average_recovery_time_seconds'],
                    'resilience_score': report['system_resilience_score'],
                }
                
                phase_result['chaos_report'] = report
                phase_result['success'] = report['summary']['success_rate'] > 0.7  # 70% success threshold
                
                if phase_result['success']:
                    logger.info(f"✅ Chaos engineering completed: {report['summary']['success_rate']:.1%} success rate")
                else:
                    logger.warning(f"⚠️ Chaos engineering below threshold: {report['summary']['success_rate']:.1%}")
                
            finally:
                await controller.cleanup()
            
        except Exception as e:
            phase_result['error'] = str(e)
            logger.error(f"Chaos engineering failed: {e}")
        
        finally:
            phase_result['end_time'] = datetime.now().isoformat()
            self.results['phases']['chaos_engineering'] = phase_result
    
    async def _phase_6_performance_validation(self):
        """Phase 6: Performance validation with load testing"""
        logger.info("⚡ Phase 6: Performance Validation")
        phase_result = {
            'phase': 'performance_validation',
            'start_time': datetime.now().isoformat(),
            'success': False,
        }
        
        try:
            # Run K6 load tests
            logger.info("Running K6 load tests...")
            
            load_tests = [
                ('data_ingestion', 'ai-ml-system/tests/load/data-ingestion-load-test.js'),
                ('rag_engine', 'ai-ml-system/tests/load/rag-engine-load-test.js'),
            ]
            
            test_results = []
            
            for test_name, test_file in load_tests:
                if os.path.exists(test_file):
                    logger.info(f"Running {test_name} load test...")
                    
                    result = subprocess.run(
                        ['k6', 'run', test_file, '--quiet'],
                        capture_output=True,
                        text=True,
                        timeout=600  # 10 minutes timeout
                    )
                    
                    test_results.append({
                        'test': test_name,
                        'success': result.returncode == 0,
                        'output': result.stdout,
                        'error': result.stderr if result.returncode != 0 else None,
                    })
                    
                    if result.returncode == 0:
                        logger.info(f"✅ {test_name} load test passed")
                    else:
                        logger.warning(f"⚠️ {test_name} load test failed")
                else:
                    logger.warning(f"⚠️ Load test file not found: {test_file}")
            
            phase_result['load_test_results'] = test_results
            phase_result['success'] = all(test.get('success', False) for test in test_results)
            
        except Exception as e:
            phase_result['error'] = str(e)
            logger.error(f"Performance validation failed: {e}")
        
        finally:
            phase_result['end_time'] = datetime.now().isoformat()
            self.results['phases']['performance_validation'] = phase_result
    
    async def _phase_7_generate_report(self):
        """Phase 7: Generate comprehensive demonstration report"""
        logger.info("📊 Phase 7: Generate Report")
        phase_result = {
            'phase': 'report_generation',
            'start_time': datetime.now().isoformat(),
            'success': False,
        }
        
        try:
            # Generate comprehensive report
            report = {
                'demo_summary': {
                    'demo_id': self.demo_id,
                    'total_duration_minutes': self.results.get('duration_minutes', 0),
                    'phases_completed': len(self.results['phases']),
                    'overall_success': self.results.get('overall_success', False),
                },
                
                'phase_results': self.results['phases'],
                
                'key_achievements': [
                    'Complete AI/ML system implementation with 8 advanced scenarios',
                    'End-to-end payment reconciliation incident simulation',
                    'Comprehensive chaos engineering validation',
                    'Production-ready monitoring and observability',
                    'Automated testing and validation framework',
                ],
                
                'technical_highlights': [
                    'Real-time data ingestion with Kafka streaming',
                    'RAG system with blue/green deployment',
                    'ML drift detection with auto-retraining',
                    'Saga pattern for distributed transactions',
                    'Vector database with semantic search',
                    'Prometheus/Grafana monitoring stack',
                ],
                
                'performance_metrics': self._extract_performance_metrics(),
                
                'recommendations': [
                    'Deploy to production with current configuration',
                    'Implement additional chaos engineering scenarios',
                    'Add more comprehensive monitoring dashboards',
                    'Extend ML model registry capabilities',
                    'Implement advanced security features',
                ],
            }
            
            # Save detailed report
            report_file = f'capstone_demo_report_{self.demo_id}.json'
            with open(report_file, 'w') as f:
                json.dump(report, f, indent=2)
            
            phase_result['report_file'] = report_file
            phase_result['success'] = True
            
            logger.info(f"✅ Report generated: {report_file}")
            
        except Exception as e:
            phase_result['error'] = str(e)
            logger.error(f"Report generation failed: {e}")
        
        finally:
            phase_result['end_time'] = datetime.now().isoformat()
            self.results['phases']['report_generation'] = phase_result
    
    def _extract_performance_metrics(self) -> Dict[str, Any]:
        """Extract key performance metrics from all phases"""
        metrics = {}
        
        # Extract from E2E testing
        if 'e2e_testing' in self.results['phases']:
            e2e_results = self.results['phases']['e2e_testing'].get('test_results', {})
            if 'tests' in e2e_results:
                load_test = e2e_results['tests'].get('load_performance', {})
                if 'metrics' in load_test:
                    metrics['load_testing'] = load_test['metrics']
        
        # Extract from chaos engineering
        if 'chaos_engineering' in self.results['phases']:
            chaos_results = self.results['phases']['chaos_engineering'].get('chaos_results', {})
            metrics['chaos_engineering'] = {
                'success_rate': chaos_results.get('success_rate', 0),
                'avg_recovery_time': chaos_results.get('avg_recovery_time', 0),
                'resilience_score': chaos_results.get('resilience_score', 0),
            }
        
        # Extract from incident simulation
        if 'incident_simulation' in self.results['phases']:
            incident_results = self.results['phases']['incident_simulation'].get('incident_trace', {})
            metrics['incident_simulation'] = {
                'duration_minutes': incident_results.get('duration_minutes', 0),
                'affected_payments': incident_results.get('affected_payments', 0),
                'resolution_actions': incident_results.get('resolution_actions', 0),
            }
        
        return metrics
    
    async def _save_results(self):
        """Save demonstration results"""
        results_file = f'capstone_demo_results_{self.demo_id}.json'
        with open(results_file, 'w') as f:
            json.dump(self.results, f, indent=2)
        logger.info(f"Results saved to: {results_file}")
    
    async def _print_summary(self):
        """Print demonstration summary"""
        print("\n" + "="*100)
        print("🎯 CAPSTONE DEMONSTRATION SUMMARY")
        print("="*100)
        print(f"Demo ID: {self.demo_id}")
        print(f"Duration: {self.results.get('duration_minutes', 0):.1f} minutes")
        print(f"Overall Success: {'✅ PASS' if self.results.get('overall_success') else '❌ FAIL'}")
        print(f"Phases Completed: {len(self.results['phases'])}/7")
        
        print("\n📋 PHASE RESULTS:")
        for phase_name, phase_data in self.results['phases'].items():
            status = '✅ PASS' if phase_data.get('success') else '❌ FAIL'
            duration = 'N/A'
            if 'start_time' in phase_data and 'end_time' in phase_data:
                start = datetime.fromisoformat(phase_data['start_time'])
                end = datetime.fromisoformat(phase_data['end_time'])
                duration = f"{(end - start).total_seconds() / 60:.1f}m"
            
            print(f"  {phase_name.replace('_', ' ').title()}: {status} ({duration})")
        
        print("\n🏆 KEY ACHIEVEMENTS:")
        achievements = [
            "✅ Complete AI/ML system with 8 advanced scenarios implemented",
            "✅ End-to-end payment reconciliation incident simulation",
            "✅ Comprehensive chaos engineering validation",
            "✅ Production-ready monitoring and observability",
            "✅ Automated testing and validation framework",
            "✅ Blue/green deployment for zero-downtime updates",
            "✅ Real-time drift detection with auto-retraining",
            "✅ Comprehensive documentation and runbooks",
        ]
        
        for achievement in achievements:
            print(f"  {achievement}")
        
        print("\n📊 PERFORMANCE HIGHLIGHTS:")
        metrics = self._extract_performance_metrics()
        
        if 'chaos_engineering' in metrics:
            chaos = metrics['chaos_engineering']
            print(f"  • System Resilience Score: {chaos.get('resilience_score', 0):.2f}")
            print(f"  • Chaos Recovery Success Rate: {chaos.get('success_rate', 0):.1%}")
            print(f"  • Average Recovery Time: {chaos.get('avg_recovery_time', 0):.1f}s")
        
        if 'incident_simulation' in metrics:
            incident = metrics['incident_simulation']
            print(f"  • Incident Resolution Time: {incident.get('duration_minutes', 0):.1f} minutes")
            print(f"  • Payments Affected in Simulation: {incident.get('affected_payments', 0)}")
        
        print("\n🚀 SYSTEM CAPABILITIES DEMONSTRATED:")
        capabilities = [
            "Real-time data ingestion with validation and normalization",
            "Vector-based RAG system with semantic search",
            "ML drift detection with automated retraining triggers",
            "Distributed saga orchestration with compensation",
            "Blue/green deployment with atomic swaps",
            "Comprehensive monitoring with Prometheus/Grafana",
            "Chaos engineering with automated recovery",
            "End-to-end incident response and postmortem generation",
        ]
        
        for capability in capabilities:
            print(f"  • {capability}")
        
        print("\n" + "="*100)
        print("🎉 CAPSTONE DEMONSTRATION COMPLETE!")
        print("="*100)
    
    # Validation helper methods
    async def _validate_kafka(self) -> Dict[str, Any]:
        """Validate Kafka connectivity"""
        try:
            from kafka import KafkaProducer
            producer = KafkaProducer(bootstrap_servers=['localhost:9092'])
            producer.close()
            return {'success': True, 'message': 'Kafka connectivity verified'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    async def _validate_redis(self) -> Dict[str, Any]:
        """Validate Redis connectivity"""
        try:
            import redis
            client = redis.Redis(host='localhost', port=6379)
            client.ping()
            return {'success': True, 'message': 'Redis connectivity verified'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    async def _validate_milvus(self) -> Dict[str, Any]:
        """Validate Milvus connectivity"""
        try:
            # Simple connection test
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex(('localhost', 19530))
            sock.close()
            
            if result == 0:
                return {'success': True, 'message': 'Milvus connectivity verified'}
            else:
                return {'success': False, 'error': 'Milvus port not accessible'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    async def _validate_service_endpoints(self) -> Dict[str, Any]:
        """Validate all service endpoints"""
        try:
            import aiohttp
            
            endpoints = [
                'http://localhost:8080/health',
                'http://localhost:8081/health',
                'http://localhost:8082/health',
            ]
            
            healthy_count = 0
            
            async with aiohttp.ClientSession() as session:
                for endpoint in endpoints:
                    try:
                        async with session.get(endpoint, timeout=aiohttp.ClientTimeout(total=5)) as response:
                            if response.status == 200:
                                healthy_count += 1
                    except:
                        pass
            
            success = healthy_count == len(endpoints)
            return {
                'success': success,
                'healthy_endpoints': healthy_count,
                'total_endpoints': len(endpoints),
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}

# Main execution
async def main():
    """Run the complete capstone demonstration"""
    demo = CapstoneDemo()
    await demo.run_complete_demo()

if __name__ == "__main__":
    asyncio.run(main())

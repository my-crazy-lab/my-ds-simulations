#!/usr/bin/env python3
"""
End-to-End Payment Reconciliation Incident Orchestrator
Simulates: late/duplicate webhooks → out-of-order processing → incorrect RAG answers
"""

import asyncio
import json
import logging
import random
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum
import uuid

import aiohttp
import redis.asyncio as redis
from kafka import KafkaProducer
import prometheus_client
from prometheus_client import Counter, Histogram, Gauge

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Prometheus metrics for incident tracking
INCIDENT_EVENTS = Counter('incident_events_total', 'Incident events', ['type', 'status'])
INCIDENT_DURATION = Histogram('incident_duration_seconds', 'Incident duration')
SYSTEM_HEALTH = Gauge('system_health_score', 'Overall system health', ['component'])
RECONCILIATION_ERRORS = Counter('reconciliation_errors_total', 'Reconciliation errors', ['error_type'])

class IncidentType(Enum):
    WEBHOOK_DELAY = "webhook_delay"
    WEBHOOK_DUPLICATE = "webhook_duplicate"
    OUT_OF_ORDER_PROCESSING = "out_of_order_processing"
    SAGA_COMPENSATION_FAILURE = "saga_compensation_failure"
    RAG_STALE_DATA = "rag_stale_data"
    DB_INCONSISTENCY = "db_inconsistency"

class IncidentSeverity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

@dataclass
class PaymentEvent:
    """Payment event structure"""
    payment_id: str
    user_id: str
    amount: float
    currency: str
    status: str
    provider: str
    timestamp: str
    webhook_id: str
    idempotency_key: str
    metadata: Dict[str, Any]

@dataclass
class IncidentScenario:
    """Incident scenario configuration"""
    id: str
    name: str
    description: str
    severity: IncidentSeverity
    duration_minutes: int
    affected_components: List[str]
    injection_config: Dict[str, Any]
    expected_symptoms: List[str]
    remediation_steps: List[str]

@dataclass
class IncidentTrace:
    """End-to-end incident trace"""
    incident_id: str
    scenario: IncidentScenario
    start_time: str
    end_time: Optional[str]
    events: List[Dict[str, Any]]
    affected_payments: List[str]
    system_impact: Dict[str, float]
    resolution_actions: List[str]
    lessons_learned: List[str]

class PaymentWebhookSimulator:
    """Simulates payment provider webhooks with various failure modes"""
    
    def __init__(self, kafka_producer: KafkaProducer, redis_client: redis.Redis):
        self.kafka_producer = kafka_producer
        self.redis_client = redis_client
        self.payment_providers = ['stripe', 'paypal', 'square', 'adyen']
        
    async def simulate_normal_webhook(self, payment_id: str, user_id: str) -> PaymentEvent:
        """Simulate normal webhook delivery"""
        event = PaymentEvent(
            payment_id=payment_id,
            user_id=user_id,
            amount=round(random.uniform(10.0, 1000.0), 2),
            currency=random.choice(['USD', 'EUR', 'GBP']),
            status=random.choice(['completed', 'pending', 'failed']),
            provider=random.choice(self.payment_providers),
            timestamp=datetime.now().isoformat(),
            webhook_id=str(uuid.uuid4()),
            idempotency_key=f"webhook_{payment_id}_{int(time.time())}",
            metadata={
                'transaction_fee': round(random.uniform(0.5, 5.0), 2),
                'payment_method': random.choice(['card', 'bank_transfer', 'wallet']),
                'risk_score': round(random.uniform(0.0, 1.0), 3),
            }
        )
        
        # Send to Kafka
        self.kafka_producer.send('payment-webhooks', value=asdict(event))
        logger.info(f"Sent normal webhook for payment {payment_id}")
        
        return event
    
    async def simulate_delayed_webhook(self, payment_id: str, user_id: str, delay_minutes: int) -> PaymentEvent:
        """Simulate delayed webhook delivery"""
        # Create event with past timestamp but deliver now
        past_time = datetime.now() - timedelta(minutes=delay_minutes)
        
        event = PaymentEvent(
            payment_id=payment_id,
            user_id=user_id,
            amount=round(random.uniform(10.0, 1000.0), 2),
            currency=random.choice(['USD', 'EUR', 'GBP']),
            status='completed',
            provider=random.choice(self.payment_providers),
            timestamp=past_time.isoformat(),  # Past timestamp
            webhook_id=str(uuid.uuid4()),
            idempotency_key=f"webhook_{payment_id}_{int(past_time.timestamp())}",
            metadata={
                'delayed_delivery': True,
                'original_timestamp': past_time.isoformat(),
                'actual_delivery_time': datetime.now().isoformat(),
                'delay_minutes': delay_minutes,
            }
        )
        
        # Send to Kafka
        self.kafka_producer.send('payment-webhooks', value=asdict(event))
        logger.warning(f"Sent delayed webhook for payment {payment_id} (delayed by {delay_minutes} minutes)")
        
        INCIDENT_EVENTS.labels(type='webhook_delay', status='injected').inc()
        return event
    
    async def simulate_duplicate_webhook(self, original_event: PaymentEvent, duplicate_count: int = 2) -> List[PaymentEvent]:
        """Simulate duplicate webhook delivery"""
        duplicates = []
        
        for i in range(duplicate_count):
            # Create duplicate with slight variations
            duplicate = PaymentEvent(
                payment_id=original_event.payment_id,
                user_id=original_event.user_id,
                amount=original_event.amount,
                currency=original_event.currency,
                status=original_event.status,
                provider=original_event.provider,
                timestamp=original_event.timestamp,
                webhook_id=str(uuid.uuid4()),  # Different webhook ID
                idempotency_key=original_event.idempotency_key,  # Same idempotency key
                metadata={
                    **original_event.metadata,
                    'is_duplicate': True,
                    'duplicate_sequence': i + 1,
                    'original_webhook_id': original_event.webhook_id,
                }
            )
            
            # Send with slight delay to simulate network issues
            await asyncio.sleep(random.uniform(0.1, 2.0))
            self.kafka_producer.send('payment-webhooks', value=asdict(duplicate))
            duplicates.append(duplicate)
            
            logger.warning(f"Sent duplicate webhook #{i+1} for payment {original_event.payment_id}")
        
        INCIDENT_EVENTS.labels(type='webhook_duplicate', status='injected').inc(duplicate_count)
        return duplicates

class SagaOrchestrationSimulator:
    """Simulates saga orchestration failures"""
    
    def __init__(self, base_url: str):
        self.base_url = base_url
        
    async def simulate_saga_timeout(self, payment_id: str) -> Dict[str, Any]:
        """Simulate saga timeout scenario"""
        saga_data = {
            'type': 'payment_processing',
            'data': {
                'payment_id': payment_id,
                'timeout_simulation': True,
                'step_delays': {
                    'inventory_reserve': 30,  # 30 second delay
                    'payment_charge': 45,     # 45 second delay
                    'notification_send': 60,  # 60 second delay (will timeout)
                }
            }
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.base_url}/api/v1/sagas", json=saga_data) as response:
                    result = await response.json()
                    logger.warning(f"Initiated saga with timeout simulation for payment {payment_id}")
                    INCIDENT_EVENTS.labels(type='saga_timeout', status='injected').inc()
                    return result
        except Exception as e:
            logger.error(f"Failed to simulate saga timeout: {e}")
            return {'error': str(e)}
    
    async def simulate_compensation_failure(self, payment_id: str) -> Dict[str, Any]:
        """Simulate saga compensation failure"""
        saga_data = {
            'type': 'payment_processing',
            'data': {
                'payment_id': payment_id,
                'compensation_failure': True,
                'failing_step': 'inventory_release',  # Compensation will fail here
                'failure_rate': 1.0,  # 100% failure rate
            }
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.base_url}/api/v1/sagas", json=saga_data) as response:
                    result = await response.json()
                    logger.warning(f"Initiated saga with compensation failure for payment {payment_id}")
                    INCIDENT_EVENTS.labels(type='compensation_failure', status='injected').inc()
                    return result
        except Exception as e:
            logger.error(f"Failed to simulate compensation failure: {e}")
            return {'error': str(e)}

class RAGDataCorruptionSimulator:
    """Simulates RAG data corruption and stale information"""
    
    def __init__(self, rag_base_url: str, redis_client: redis.Redis):
        self.rag_base_url = rag_base_url
        self.redis_client = redis_client
    
    async def inject_stale_payment_data(self, payment_id: str, incorrect_status: str) -> bool:
        """Inject stale payment data into RAG system"""
        try:
            # Create misleading payment information
            stale_data = {
                'id': f"stale_payment_{payment_id}",
                'source': 'payment_system',
                'type': 'payment_status',
                'timestamp': (datetime.now() - timedelta(hours=2)).isoformat(),
                'data': {
                    'payment_id': payment_id,
                    'status': incorrect_status,  # Incorrect status
                    'content': f"Payment {payment_id} is {incorrect_status}. Customer support: contact billing team.",
                    'last_updated': (datetime.now() - timedelta(hours=2)).isoformat(),
                    'is_stale_injection': True,  # Mark for tracking
                },
                'metadata': {
                    'source': 'payment_reconciliation',
                    'priority': 'high',
                    'incident_injection': True,
                }
            }
            
            # Send directly to processed messages topic (bypassing validation)
            # This simulates data that got corrupted after validation
            await self.redis_client.setex(
                f"stale_payment_data:{payment_id}",
                3600,  # 1 hour TTL
                json.dumps(stale_data)
            )
            
            logger.warning(f"Injected stale payment data for {payment_id} with incorrect status: {incorrect_status}")
            INCIDENT_EVENTS.labels(type='rag_stale_data', status='injected').inc()
            return True
            
        except Exception as e:
            logger.error(f"Failed to inject stale payment data: {e}")
            return False
    
    async def verify_rag_corruption(self, payment_id: str) -> Dict[str, Any]:
        """Verify that RAG system returns corrupted data"""
        try:
            query = f"What is the status of payment {payment_id}?"
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.rag_base_url}/search",
                    json={'query': query, 'top_k': 5}
                ) as response:
                    result = await response.json()
                    
                    # Check if stale data appears in results
                    stale_found = False
                    for doc in result.get('results', []):
                        if 'is_stale_injection' in doc.get('metadata', {}):
                            stale_found = True
                            break
                    
                    return {
                        'query': query,
                        'stale_data_found': stale_found,
                        'results_count': len(result.get('results', [])),
                        'results': result.get('results', [])
                    }
                    
        except Exception as e:
            logger.error(f"Failed to verify RAG corruption: {e}")
            return {'error': str(e)}

class IncidentOrchestrator:
    """Orchestrates end-to-end incident scenarios"""
    
    def __init__(self):
        self.kafka_producer = KafkaProducer(
            bootstrap_servers=['localhost:9092'],
            value_serializer=lambda x: json.dumps(x).encode('utf-8')
        )
        self.redis_client = None
        self.webhook_simulator = None
        self.saga_simulator = None
        self.rag_simulator = None
        self.active_incidents: Dict[str, IncidentTrace] = {}
        
    async def initialize(self):
        """Initialize all components"""
        self.redis_client = redis.from_url('redis://localhost:6379')
        self.webhook_simulator = PaymentWebhookSimulator(self.kafka_producer, self.redis_client)
        self.saga_simulator = SagaOrchestrationSimulator('http://localhost:8080')
        self.rag_simulator = RAGDataCorruptionSimulator('http://localhost:8081', self.redis_client)
        
        logger.info("Incident orchestrator initialized")
    
    async def run_payment_reconciliation_incident(self) -> IncidentTrace:
        """Run the complete payment reconciliation incident scenario"""
        incident_id = f"payment_reconciliation_{int(time.time())}"
        
        scenario = IncidentScenario(
            id=incident_id,
            name="Payment Reconciliation Gone Wrong",
            description="Late/duplicate webhooks cause out-of-order processing and incorrect RAG answers",
            severity=IncidentSeverity.HIGH,
            duration_minutes=30,
            affected_components=['webhooks', 'saga-orchestrator', 'rag-engine', 'payment-db'],
            injection_config={
                'webhook_delay_minutes': 15,
                'duplicate_count': 3,
                'saga_timeout_enabled': True,
                'rag_corruption_enabled': True,
            },
            expected_symptoms=[
                'Duplicate payment processing attempts',
                'Saga compensation failures',
                'Incorrect payment status in customer support responses',
                'Database inconsistencies between services',
            ],
            remediation_steps=[
                'Stop webhook processing',
                'Run payment reconciliation job',
                'Trigger RAG reindexing',
                'Validate saga compensation',
                'Resume normal operations',
            ]
        )
        
        trace = IncidentTrace(
            incident_id=incident_id,
            scenario=scenario,
            start_time=datetime.now().isoformat(),
            end_time=None,
            events=[],
            affected_payments=[],
            system_impact={},
            resolution_actions=[],
            lessons_learned=[]
        )
        
        self.active_incidents[incident_id] = trace
        
        try:
            logger.info(f"🚨 Starting incident scenario: {scenario.name}")
            
            # Phase 1: Generate normal payment events
            await self._phase_1_normal_operations(trace)
            
            # Phase 2: Inject webhook delays and duplicates
            await self._phase_2_webhook_chaos(trace)
            
            # Phase 3: Trigger saga failures
            await self._phase_3_saga_failures(trace)
            
            # Phase 4: Corrupt RAG data
            await self._phase_4_rag_corruption(trace)
            
            # Phase 5: Observe system impact
            await self._phase_5_impact_assessment(trace)
            
            # Phase 6: Execute remediation
            await self._phase_6_remediation(trace)
            
            trace.end_time = datetime.now().isoformat()
            logger.info(f"✅ Completed incident scenario: {scenario.name}")
            
        except Exception as e:
            logger.error(f"❌ Incident scenario failed: {e}")
            trace.events.append({
                'timestamp': datetime.now().isoformat(),
                'type': 'incident_failure',
                'details': {'error': str(e)}
            })
        
        return trace
    
    async def _phase_1_normal_operations(self, trace: IncidentTrace):
        """Phase 1: Generate normal payment operations"""
        logger.info("Phase 1: Generating normal payment operations")
        
        # Generate 10 normal payments
        for i in range(10):
            payment_id = f"pay_{int(time.time())}_{i}"
            user_id = f"user_{random.randint(1000, 9999)}"
            
            event = await self.webhook_simulator.simulate_normal_webhook(payment_id, user_id)
            trace.affected_payments.append(payment_id)
            
            trace.events.append({
                'timestamp': datetime.now().isoformat(),
                'phase': 'normal_operations',
                'type': 'payment_webhook',
                'payment_id': payment_id,
                'details': {'status': 'normal', 'amount': event.amount}
            })
            
            await asyncio.sleep(0.5)  # Small delay between payments
        
        logger.info(f"Generated {len(trace.affected_payments)} normal payments")
    
    async def _phase_2_webhook_chaos(self, trace: IncidentTrace):
        """Phase 2: Inject webhook delays and duplicates"""
        logger.info("Phase 2: Injecting webhook chaos")
        
        # Select some payments for chaos injection
        chaos_payments = trace.affected_payments[:5]
        
        for payment_id in chaos_payments:
            user_id = f"user_{random.randint(1000, 9999)}"
            
            # Create delayed webhook
            delayed_event = await self.webhook_simulator.simulate_delayed_webhook(
                payment_id, user_id, delay_minutes=15
            )
            
            # Create duplicates
            duplicates = await self.webhook_simulator.simulate_duplicate_webhook(
                delayed_event, duplicate_count=3
            )
            
            trace.events.append({
                'timestamp': datetime.now().isoformat(),
                'phase': 'webhook_chaos',
                'type': 'delayed_webhook',
                'payment_id': payment_id,
                'details': {'delay_minutes': 15, 'duplicates': len(duplicates)}
            })
            
            await asyncio.sleep(1.0)
        
        logger.warning(f"Injected webhook chaos for {len(chaos_payments)} payments")
    
    async def _phase_3_saga_failures(self, trace: IncidentTrace):
        """Phase 3: Trigger saga orchestration failures"""
        logger.info("Phase 3: Triggering saga failures")
        
        # Select payments for saga failures
        saga_failure_payments = trace.affected_payments[2:7]
        
        for payment_id in saga_failure_payments:
            # Alternate between timeout and compensation failures
            if len(trace.events) % 2 == 0:
                result = await self.saga_simulator.simulate_saga_timeout(payment_id)
                failure_type = 'timeout'
            else:
                result = await self.saga_simulator.simulate_compensation_failure(payment_id)
                failure_type = 'compensation_failure'
            
            trace.events.append({
                'timestamp': datetime.now().isoformat(),
                'phase': 'saga_failures',
                'type': f'saga_{failure_type}',
                'payment_id': payment_id,
                'details': result
            })
            
            await asyncio.sleep(2.0)
        
        logger.warning(f"Triggered saga failures for {len(saga_failure_payments)} payments")
    
    async def _phase_4_rag_corruption(self, trace: IncidentTrace):
        """Phase 4: Corrupt RAG data with stale information"""
        logger.info("Phase 4: Corrupting RAG data")
        
        # Select payments for RAG corruption
        rag_corruption_payments = trace.affected_payments[1:6]
        
        for payment_id in rag_corruption_payments:
            # Inject incorrect status
            incorrect_status = random.choice(['failed', 'pending', 'refunded'])
            
            success = await self.rag_simulator.inject_stale_payment_data(payment_id, incorrect_status)
            
            if success:
                # Verify corruption appears in search results
                verification = await self.rag_simulator.verify_rag_corruption(payment_id)
                
                trace.events.append({
                    'timestamp': datetime.now().isoformat(),
                    'phase': 'rag_corruption',
                    'type': 'stale_data_injection',
                    'payment_id': payment_id,
                    'details': {
                        'incorrect_status': incorrect_status,
                        'verification': verification
                    }
                })
            
            await asyncio.sleep(1.0)
        
        logger.warning(f"Corrupted RAG data for {len(rag_corruption_payments)} payments")
    
    async def _phase_5_impact_assessment(self, trace: IncidentTrace):
        """Phase 5: Assess system impact"""
        logger.info("Phase 5: Assessing system impact")
        
        # Simulate impact metrics
        impact_metrics = {
            'webhook_processing_errors': random.randint(15, 25),
            'saga_compensation_failures': random.randint(3, 8),
            'rag_stale_responses': random.randint(10, 20),
            'customer_support_tickets': random.randint(5, 15),
            'payment_reconciliation_discrepancies': random.randint(8, 12),
        }
        
        trace.system_impact = impact_metrics
        
        trace.events.append({
            'timestamp': datetime.now().isoformat(),
            'phase': 'impact_assessment',
            'type': 'system_impact',
            'details': impact_metrics
        })
        
        # Update Prometheus metrics
        for metric, value in impact_metrics.items():
            RECONCILIATION_ERRORS.labels(error_type=metric).inc(value)
        
        logger.warning(f"System impact assessed: {impact_metrics}")
    
    async def _phase_6_remediation(self, trace: IncidentTrace):
        """Phase 6: Execute remediation steps"""
        logger.info("Phase 6: Executing remediation")
        
        remediation_actions = [
            'Paused webhook processing queue',
            'Initiated payment reconciliation job',
            'Triggered RAG index refresh',
            'Validated saga compensation states',
            'Cleared stale cache entries',
            'Resumed normal operations',
        ]
        
        for action in remediation_actions:
            trace.resolution_actions.append(action)
            
            trace.events.append({
                'timestamp': datetime.now().isoformat(),
                'phase': 'remediation',
                'type': 'remediation_action',
                'details': {'action': action}
            })
            
            # Simulate remediation time
            await asyncio.sleep(2.0)
            logger.info(f"✅ {action}")
        
        # Add lessons learned
        trace.lessons_learned = [
            'Implement stronger webhook deduplication with longer TTL',
            'Add saga timeout monitoring and alerting',
            'Implement RAG data freshness validation',
            'Create automated payment reconciliation checks',
            'Add cross-service consistency validation',
        ]
        
        logger.info("Remediation completed")
    
    async def generate_postmortem(self, trace: IncidentTrace) -> Dict[str, Any]:
        """Generate comprehensive postmortem report"""
        duration = datetime.fromisoformat(trace.end_time) - datetime.fromisoformat(trace.start_time)
        
        postmortem = {
            'incident_id': trace.incident_id,
            'title': trace.scenario.name,
            'severity': trace.scenario.severity.value,
            'duration_minutes': duration.total_seconds() / 60,
            'start_time': trace.start_time,
            'end_time': trace.end_time,
            
            'summary': {
                'description': trace.scenario.description,
                'root_cause': 'Payment provider webhook delivery issues combined with insufficient deduplication',
                'affected_payments': len(trace.affected_payments),
                'system_components': trace.scenario.affected_components,
            },
            
            'timeline': trace.events,
            
            'impact': {
                'customer_facing': {
                    'incorrect_payment_status_responses': trace.system_impact.get('rag_stale_responses', 0),
                    'customer_support_tickets': trace.system_impact.get('customer_support_tickets', 0),
                },
                'internal': {
                    'webhook_processing_errors': trace.system_impact.get('webhook_processing_errors', 0),
                    'saga_failures': trace.system_impact.get('saga_compensation_failures', 0),
                    'data_inconsistencies': trace.system_impact.get('payment_reconciliation_discrepancies', 0),
                }
            },
            
            'resolution': {
                'actions_taken': trace.resolution_actions,
                'time_to_resolution_minutes': duration.total_seconds() / 60,
            },
            
            'lessons_learned': trace.lessons_learned,
            
            'action_items': [
                {
                    'item': 'Implement webhook deduplication with 24h TTL',
                    'owner': 'Platform Team',
                    'priority': 'High',
                    'due_date': (datetime.now() + timedelta(days=7)).isoformat(),
                },
                {
                    'item': 'Add saga timeout monitoring dashboard',
                    'owner': 'SRE Team',
                    'priority': 'Medium',
                    'due_date': (datetime.now() + timedelta(days=14)).isoformat(),
                },
                {
                    'item': 'Implement RAG data freshness validation',
                    'owner': 'ML Team',
                    'priority': 'High',
                    'due_date': (datetime.now() + timedelta(days=10)).isoformat(),
                },
                {
                    'item': 'Create automated reconciliation job',
                    'owner': 'Backend Team',
                    'priority': 'Medium',
                    'due_date': (datetime.now() + timedelta(days=21)).isoformat(),
                },
            ],
            
            'prevention_measures': [
                'Implement circuit breakers for webhook processing',
                'Add cross-service data consistency checks',
                'Create payment reconciliation monitoring',
                'Implement RAG answer confidence scoring',
                'Add automated incident detection rules',
            ]
        }
        
        return postmortem
    
    async def cleanup(self):
        """Cleanup resources"""
        if self.kafka_producer:
            self.kafka_producer.close()
        if self.redis_client:
            await self.redis_client.close()

# Main execution
async def main():
    """Run the payment reconciliation incident simulation"""
    orchestrator = IncidentOrchestrator()
    
    try:
        await orchestrator.initialize()
        
        # Run the incident scenario
        trace = await orchestrator.run_payment_reconciliation_incident()
        
        # Generate postmortem
        postmortem = await orchestrator.generate_postmortem(trace)
        
        # Save postmortem to file
        with open(f'postmortem_{trace.incident_id}.json', 'w') as f:
            json.dump(postmortem, f, indent=2)
        
        print("\n" + "="*80)
        print("🚨 INCIDENT POSTMORTEM SUMMARY")
        print("="*80)
        print(f"Incident ID: {postmortem['incident_id']}")
        print(f"Title: {postmortem['title']}")
        print(f"Severity: {postmortem['severity'].upper()}")
        print(f"Duration: {postmortem['duration_minutes']:.1f} minutes")
        print(f"Affected Payments: {postmortem['summary']['affected_payments']}")
        print(f"Customer Impact: {postmortem['impact']['customer_facing']['customer_support_tickets']} support tickets")
        print(f"System Errors: {postmortem['impact']['internal']['webhook_processing_errors']} webhook errors")
        print("\nLessons Learned:")
        for lesson in postmortem['lessons_learned']:
            print(f"  • {lesson}")
        print("\nAction Items:")
        for item in postmortem['action_items']:
            print(f"  • {item['item']} ({item['priority']} priority)")
        print("="*80)
        
    finally:
        await orchestrator.cleanup()

if __name__ == "__main__":
    asyncio.run(main())

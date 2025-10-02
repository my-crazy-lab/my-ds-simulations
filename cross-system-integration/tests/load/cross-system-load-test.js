import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';

// Custom metrics
const errorRate = new Rate('error_rate');
const responseTime = new Trend('response_time');
const requestCount = new Counter('request_count');

// Test configuration
export const options = {
  stages: [
    { duration: '2m', target: 10 },   // Ramp up to 10 users
    { duration: '5m', target: 10 },   // Stay at 10 users
    { duration: '2m', target: 20 },   // Ramp up to 20 users
    { duration: '5m', target: 20 },   // Stay at 20 users
    { duration: '2m', target: 0 },    // Ramp down to 0 users
  ],
  thresholds: {
    http_req_duration: ['p(95)<2000'], // 95% of requests must complete below 2s
    error_rate: ['rate<0.05'],         // Error rate must be below 5%
    response_time: ['p(95)<1500'],     // 95% of response times below 1.5s
  },
};

// Base URLs
const BASE_URLS = {
  eventBus: 'http://localhost:8090',
  orchestrator: 'http://localhost:8091',
  chatops: 'http://localhost:8092',
};

// Test data generators
function generateSagaRequest() {
  return {
    saga_id: 'payment_saga',
    correlation_id: `load_test_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
    context: {
      user_id: `user_${Math.floor(Math.random() * 1000)}`,
      amount: Math.floor(Math.random() * 1000) + 10,
      system_load: Math.random() * 0.8,
      historical_success_rate: 0.9 + Math.random() * 0.1,
    },
  };
}

function generateChatRequest() {
  const messages = [
    'what is the system status?',
    'show saga status',
    'help me troubleshoot issues',
    'start saga payment_saga',
    'query metrics last 1 hour',
    'check system health',
  ];
  
  return {
    session_id: `load_session_${__VU}_${__ITER}`,
    user_id: `load_user_${__VU}`,
    message: messages[Math.floor(Math.random() * messages.length)],
  };
}

function generateEvent() {
  const eventTypes = ['saga.started', 'saga.completed', 'data.ingested', 'drift.detected'];
  const sources = ['microservices', 'analytics', 'ai-ml'];
  
  return {
    type: eventTypes[Math.floor(Math.random() * eventTypes.length)],
    source: sources[Math.floor(Math.random() * sources.length)],
    data: {
      correlation_id: `load_event_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      user_id: `user_${Math.floor(Math.random() * 1000)}`,
      timestamp: new Date().toISOString(),
    },
    metadata: {
      priority: Math.random() > 0.8 ? 'high' : 'normal',
      tags: ['load-test', 'performance'],
    },
  };
}

// Test scenarios
export default function () {
  const scenario = Math.random();
  
  if (scenario < 0.4) {
    // 40% - ChatOps requests
    testChatOpsEngine();
  } else if (scenario < 0.7) {
    // 30% - Saga orchestration
    testIntelligentOrchestrator();
  } else {
    // 30% - Event bus operations
    testEventBus();
  }
  
  sleep(1); // Wait 1 second between iterations
}

function testChatOpsEngine() {
  const startTime = Date.now();
  
  // Test chat message processing
  const chatRequest = generateChatRequest();
  const chatResponse = http.post(
    `${BASE_URLS.chatops}/api/v1/chat`,
    JSON.stringify(chatRequest),
    {
      headers: { 'Content-Type': 'application/json' },
      timeout: '30s',
    }
  );
  
  const success = check(chatResponse, {
    'ChatOps: status is 200': (r) => r.status === 200,
    'ChatOps: response has intent': (r) => {
      try {
        const body = JSON.parse(r.body);
        return body.intent !== undefined;
      } catch (e) {
        return false;
      }
    },
    'ChatOps: response time < 2s': (r) => r.timings.duration < 2000,
  });
  
  // Record metrics
  const responseTimeMs = Date.now() - startTime;
  responseTime.add(responseTimeMs);
  requestCount.add(1);
  errorRate.add(!success);
  
  if (success) {
    // Test session retrieval
    const sessionResponse = http.get(
      `${BASE_URLS.chatops}/api/v1/sessions/${chatRequest.session_id}`,
      { timeout: '10s' }
    );
    
    check(sessionResponse, {
      'ChatOps: session retrieval successful': (r) => r.status === 200 || r.status === 404,
    });
  }
}

function testIntelligentOrchestrator() {
  const startTime = Date.now();
  
  // Test saga start
  const sagaRequest = generateSagaRequest();
  const sagaResponse = http.post(
    `${BASE_URLS.orchestrator}/api/v1/sagas/start`,
    JSON.stringify(sagaRequest),
    {
      headers: { 'Content-Type': 'application/json' },
      timeout: '30s',
    }
  );
  
  const success = check(sagaResponse, {
    'Orchestrator: status is 200': (r) => r.status === 200,
    'Orchestrator: response has execution_id': (r) => {
      try {
        const body = JSON.parse(r.body);
        return body.execution_id !== undefined;
      } catch (e) {
        return false;
      }
    },
    'Orchestrator: response has ML prediction': (r) => {
      try {
        const body = JSON.parse(r.body);
        return body.ml_prediction !== undefined;
      } catch (e) {
        return false;
      }
    },
    'Orchestrator: response time < 3s': (r) => r.timings.duration < 3000,
  });
  
  // Record metrics
  const responseTimeMs = Date.now() - startTime;
  responseTime.add(responseTimeMs);
  requestCount.add(1);
  errorRate.add(!success);
  
  if (success) {
    // Test saga list retrieval
    const listResponse = http.get(
      `${BASE_URLS.orchestrator}/api/v1/sagas`,
      { timeout: '10s' }
    );
    
    check(listResponse, {
      'Orchestrator: saga list retrieval successful': (r) => r.status === 200,
    });
    
    // Test saga definitions
    const definitionsResponse = http.get(
      `${BASE_URLS.orchestrator}/api/v1/definitions`,
      { timeout: '10s' }
    );
    
    check(definitionsResponse, {
      'Orchestrator: definitions retrieval successful': (r) => r.status === 200,
    });
  }
}

function testEventBus() {
  const startTime = Date.now();
  
  // Test event publishing
  const event = generateEvent();
  const publishResponse = http.post(
    `${BASE_URLS.eventBus}/api/v1/events`,
    JSON.stringify(event),
    {
      headers: { 'Content-Type': 'application/json' },
      timeout: '30s',
    }
  );
  
  const success = check(publishResponse, {
    'EventBus: status is 200': (r) => r.status === 200,
    'EventBus: response has event_id': (r) => {
      try {
        const body = JSON.parse(r.body);
        return body.event_id !== undefined;
      } catch (e) {
        return false;
      }
    },
    'EventBus: response time < 1s': (r) => r.timings.duration < 1000,
  });
  
  // Record metrics
  const responseTimeMs = Date.now() - startTime;
  responseTime.add(responseTimeMs);
  requestCount.add(1);
  errorRate.add(!success);
  
  if (success) {
    // Test event querying
    const queryResponse = http.get(
      `${BASE_URLS.eventBus}/api/v1/events?limit=10`,
      { timeout: '10s' }
    );
    
    check(queryResponse, {
      'EventBus: event query successful': (r) => r.status === 200,
    });
    
    // Test system status
    const statusResponse = http.get(
      `${BASE_URLS.eventBus}/api/v1/status`,
      { timeout: '10s' }
    );
    
    check(statusResponse, {
      'EventBus: status check successful': (r) => r.status === 200,
    });
  }
}

// Setup function (runs once per VU)
export function setup() {
  console.log('🚀 Starting Cross-System Load Test');
  console.log('Target services:');
  console.log(`  - Event Bus: ${BASE_URLS.eventBus}`);
  console.log(`  - Intelligent Orchestrator: ${BASE_URLS.orchestrator}`);
  console.log(`  - ChatOps Engine: ${BASE_URLS.chatops}`);
  
  // Verify all services are healthy before starting load test
  const healthChecks = [
    { name: 'Event Bus', url: `${BASE_URLS.eventBus}/health` },
    { name: 'Intelligent Orchestrator', url: `${BASE_URLS.orchestrator}/health` },
    { name: 'ChatOps Engine', url: `${BASE_URLS.chatops}/health` },
  ];
  
  for (const service of healthChecks) {
    const response = http.get(service.url, { timeout: '10s' });
    if (response.status !== 200) {
      throw new Error(`${service.name} is not healthy (status: ${response.status})`);
    }
    console.log(`✅ ${service.name} is healthy`);
  }
  
  console.log('All services are healthy. Starting load test...');
  return { startTime: Date.now() };
}

// Teardown function (runs once after all VUs finish)
export function teardown(data) {
  const duration = (Date.now() - data.startTime) / 1000;
  console.log(`🏁 Load test completed in ${duration.toFixed(2)} seconds`);
  
  // Final health check
  console.log('Performing final health checks...');
  const healthChecks = [
    { name: 'Event Bus', url: `${BASE_URLS.eventBus}/health` },
    { name: 'Intelligent Orchestrator', url: `${BASE_URLS.orchestrator}/health` },
    { name: 'ChatOps Engine', url: `${BASE_URLS.chatops}/health` },
  ];
  
  for (const service of healthChecks) {
    const response = http.get(service.url, { timeout: '10s' });
    const status = response.status === 200 ? '✅' : '❌';
    console.log(`${status} ${service.name} final health: ${response.status}`);
  }
}

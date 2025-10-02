import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';

// Custom metrics
const sagaCreationSuccessRate = new Rate('saga_creation_success_rate');
const sagaCompletionSuccessRate = new Rate('saga_completion_success_rate');
const sagaCreationDuration = new Trend('saga_creation_duration');
const sagaErrors = new Counter('saga_errors');

// Test configuration
export const options = {
  stages: [
    { duration: '30s', target: 5 },   // Ramp up to 5 users
    { duration: '1m', target: 5 },    // Stay at 5 users
    { duration: '30s', target: 10 },  // Ramp up to 10 users
    { duration: '1m', target: 10 },   // Stay at 10 users
    { duration: '30s', target: 0 },   // Ramp down to 0 users
  ],
  thresholds: {
    http_req_duration: ['p(95)<2000'], // 95% of requests must complete below 2s
    saga_creation_success_rate: ['rate>0.9'], // 90% success rate for saga creation
    saga_completion_success_rate: ['rate>0.8'], // 80% success rate for saga completion
    saga_errors: ['count<10'], // Less than 10 errors total
  },
};

const BASE_URL = 'http://localhost:8080';

export default function () {
  // Test health endpoint
  const healthRes = http.get(`${BASE_URL}/health`);
  check(healthRes, {
    'health check status is 200': (r) => r.status === 200,
    'health check response time < 100ms': (r) => r.timings.duration < 100,
  });

  // Create saga scenarios
  const scenarios = [
    {
      type: 'order_processing',
      data: {
        order_id: `order-${Math.floor(Math.random() * 10000)}`,
        user_id: `user-${Math.floor(Math.random() * 1000)}`,
        amount: Math.floor(Math.random() * 500) + 50,
        items: [
          { id: 'item-1', quantity: Math.floor(Math.random() * 5) + 1 },
          { id: 'item-2', quantity: Math.floor(Math.random() * 3) + 1 },
        ]
      }
    },
    {
      type: 'refund_processing',
      data: {
        refund_id: `refund-${Math.floor(Math.random() * 10000)}`,
        order_id: `order-${Math.floor(Math.random() * 10000)}`,
        amount: Math.floor(Math.random() * 200) + 20,
        reason: 'customer_request'
      }
    }
  ];

  // Randomly select a scenario
  const scenario = scenarios[Math.floor(Math.random() * scenarios.length)];

  // Create saga
  const createPayload = JSON.stringify(scenario);
  const createRes = http.post(`${BASE_URL}/api/v1/sagas`, createPayload, {
    headers: { 'Content-Type': 'application/json' },
  });

  const createSuccess = check(createRes, {
    'saga creation status is 201': (r) => r.status === 201,
    'saga creation response time < 500ms': (r) => r.timings.duration < 500,
    'saga has valid ID': (r) => {
      try {
        const saga = JSON.parse(r.body);
        return saga.id && saga.id.length > 0;
      } catch (e) {
        return false;
      }
    },
  });

  sagaCreationSuccessRate.add(createSuccess);
  sagaCreationDuration.add(createRes.timings.duration);

  if (!createSuccess) {
    sagaErrors.add(1);
    console.error(`Failed to create saga: ${createRes.status} ${createRes.body}`);
    return;
  }

  // Parse saga response
  let saga;
  try {
    saga = JSON.parse(createRes.body);
  } catch (e) {
    sagaErrors.add(1);
    console.error(`Failed to parse saga response: ${e.message}`);
    return;
  }

  // Wait a bit for saga to process
  sleep(1);

  // Check saga status
  const statusRes = http.get(`${BASE_URL}/api/v1/sagas/${saga.id}`);
  const statusSuccess = check(statusRes, {
    'saga status check is 200': (r) => r.status === 200,
    'saga status response time < 200ms': (r) => r.timings.duration < 200,
  });

  if (statusSuccess) {
    try {
      const updatedSaga = JSON.parse(statusRes.body);
      
      // Check saga completion
      const isCompleted = updatedSaga.status === 'completed' || 
                         updatedSaga.status === 'compensated';
      
      sagaCompletionSuccessRate.add(isCompleted);
      
      // Log saga progress
      if (__VU === 1 && __ITER % 5 === 0) { // Log every 5th iteration for VU 1
        console.log(`Saga ${saga.id}: ${updatedSaga.status} (${updatedSaga.steps.length} steps)`);
        
        // Log step details
        updatedSaga.steps.forEach((step, index) => {
          console.log(`  Step ${index + 1}: ${step.type} - ${step.status}`);
        });
      }
      
    } catch (e) {
      sagaErrors.add(1);
      console.error(`Failed to parse saga status response: ${e.message}`);
    }
  } else {
    sagaErrors.add(1);
  }

  // List sagas occasionally
  if (Math.random() < 0.1) { // 10% chance
    const listRes = http.get(`${BASE_URL}/api/v1/sagas`);
    check(listRes, {
      'saga list status is 200': (r) => r.status === 200,
      'saga list response time < 300ms': (r) => r.timings.duration < 300,
    });
  }

  // Random sleep between requests
  sleep(Math.random() * 2 + 0.5); // 0.5-2.5 seconds
}

export function handleSummary(data) {
  return {
    'k6-results.json': JSON.stringify(data, null, 2),
    stdout: `
📊 K6 Load Test Results Summary
===============================

🎯 Test Configuration:
   • Duration: ~4 minutes with ramping
   • Max VUs: 10 concurrent users
   • Scenarios: Order Processing & Refund Processing

📈 Key Metrics:
   • Total Requests: ${data.metrics.http_reqs.values.count}
   • Request Rate: ${data.metrics.http_reqs.values.rate.toFixed(2)}/s
   • Average Response Time: ${data.metrics.http_req_duration.values.avg.toFixed(2)}ms
   • 95th Percentile: ${data.metrics.http_req_duration.values['p(95)'].toFixed(2)}ms

✅ Success Rates:
   • Saga Creation: ${(data.metrics.saga_creation_success_rate.values.rate * 100).toFixed(1)}%
   • Saga Completion: ${(data.metrics.saga_completion_success_rate.values.rate * 100).toFixed(1)}%
   • Total Errors: ${data.metrics.saga_errors.values.count}

🚀 Performance:
   • Average Saga Creation Time: ${data.metrics.saga_creation_duration.values.avg.toFixed(2)}ms
   • Failed Requests: ${data.metrics.http_req_failed.values.count}
   • Data Received: ${(data.metrics.data_received.values.count / 1024).toFixed(2)} KB

${data.metrics.http_req_duration.values['p(95)'] < 2000 ? '✅' : '❌'} Response Time Threshold: < 2000ms
${data.metrics.saga_creation_success_rate.values.rate > 0.9 ? '✅' : '❌'} Creation Success Rate: > 90%
${data.metrics.saga_completion_success_rate.values.rate > 0.8 ? '✅' : '❌'} Completion Success Rate: > 80%
${data.metrics.saga_errors.values.count < 10 ? '✅' : '❌'} Error Count: < 10

===============================
`,
  };
}

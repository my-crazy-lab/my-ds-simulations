import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';

// Custom metrics
const sagaCreationRate = new Rate('saga_creation_success_rate');
const sagaCreationDuration = new Trend('saga_creation_duration');
const sagaCompletionRate = new Rate('saga_completion_success_rate');
const sagaErrors = new Counter('saga_errors');

// Test configuration
export const options = {
  stages: [
    { duration: '2m', target: 10 },   // Ramp up to 10 users
    { duration: '5m', target: 10 },   // Stay at 10 users
    { duration: '2m', target: 20 },   // Ramp up to 20 users
    { duration: '5m', target: 20 },   // Stay at 20 users
    { duration: '2m', target: 50 },   // Ramp up to 50 users
    { duration: '5m', target: 50 },   // Stay at 50 users
    { duration: '2m', target: 0 },    // Ramp down to 0 users
  ],
  thresholds: {
    http_req_duration: ['p(95)<500'], // 95% of requests must complete below 500ms
    saga_creation_success_rate: ['rate>0.95'], // 95% success rate for saga creation
    saga_completion_success_rate: ['rate>0.90'], // 90% success rate for saga completion
    saga_errors: ['count<100'], // Less than 100 errors total
  },
};

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8080';

// Test data generators
function generateOrderData() {
  const orderId = `order-${Math.random().toString(36).substr(2, 9)}`;
  const userId = `user-${Math.random().toString(36).substr(2, 6)}`;
  
  return {
    type: 'order_processing',
    data: {
      order_id: orderId,
      user_id: userId,
      items: [
        {
          sku: `LAPTOP${Math.floor(Math.random() * 1000).toString().padStart(3, '0')}`,
          quantity: Math.floor(Math.random() * 5) + 1,
          price: Math.floor(Math.random() * 1000) + 500
        }
      ],
      total_amount: Math.floor(Math.random() * 5000) + 1000,
      payment_method: 'credit_card'
    }
  };
}

function generateRefundData() {
  const orderId = `order-${Math.random().toString(36).substr(2, 9)}`;
  
  return {
    type: 'refund_processing',
    data: {
      order_id: orderId,
      refund_amount: Math.floor(Math.random() * 1000) + 100,
      reason: 'customer_request'
    }
  };
}

// Main test function
export default function () {
  const testScenario = Math.random();
  
  if (testScenario < 0.7) {
    // 70% - Order processing saga
    testOrderProcessingSaga();
  } else if (testScenario < 0.9) {
    // 20% - Refund processing saga
    testRefundProcessingSaga();
  } else {
    // 10% - Query operations
    testQueryOperations();
  }
  
  sleep(Math.random() * 2 + 1); // Random sleep between 1-3 seconds
}

function testOrderProcessingSaga() {
  const orderData = generateOrderData();
  
  // Create saga
  const createResponse = http.post(
    `${BASE_URL}/api/v1/sagas`,
    JSON.stringify(orderData),
    {
      headers: {
        'Content-Type': 'application/json',
        'X-Idempotency-Key': `idem-${Date.now()}-${Math.random()}`
      },
    }
  );
  
  const createSuccess = check(createResponse, {
    'saga creation status is 201': (r) => r.status === 201,
    'saga creation response has id': (r) => {
      try {
        const body = JSON.parse(r.body);
        return body.id !== undefined;
      } catch (e) {
        return false;
      }
    },
  });
  
  sagaCreationRate.add(createSuccess);
  sagaCreationDuration.add(createResponse.timings.duration);
  
  if (!createSuccess) {
    sagaErrors.add(1);
    console.error(`Saga creation failed: ${createResponse.status} - ${createResponse.body}`);
    return;
  }
  
  const sagaId = JSON.parse(createResponse.body).id;
  
  // Poll saga status until completion or timeout
  let attempts = 0;
  const maxAttempts = 30; // 30 seconds timeout
  let sagaCompleted = false;
  
  while (attempts < maxAttempts && !sagaCompleted) {
    sleep(1); // Wait 1 second between polls
    attempts++;
    
    const statusResponse = http.get(`${BASE_URL}/api/v1/sagas/${sagaId}`);
    
    const statusCheck = check(statusResponse, {
      'saga status query successful': (r) => r.status === 200,
    });
    
    if (statusCheck) {
      try {
        const saga = JSON.parse(statusResponse.body);
        if (saga.status === 'completed' || saga.status === 'failed' || saga.status === 'compensated') {
          sagaCompleted = true;
          sagaCompletionRate.add(saga.status === 'completed');
          
          if (saga.status !== 'completed') {
            console.log(`Saga ${sagaId} ended with status: ${saga.status}`);
          }
        }
      } catch (e) {
        sagaErrors.add(1);
        console.error(`Failed to parse saga status response: ${e.message}`);
        break;
      }
    } else {
      sagaErrors.add(1);
      console.error(`Saga status query failed: ${statusResponse.status}`);
      break;
    }
  }
  
  if (!sagaCompleted) {
    sagaErrors.add(1);
    console.error(`Saga ${sagaId} did not complete within timeout`);
  }
}

function testRefundProcessingSaga() {
  const refundData = generateRefundData();
  
  // Create refund saga
  const createResponse = http.post(
    `${BASE_URL}/api/v1/sagas`,
    JSON.stringify(refundData),
    {
      headers: {
        'Content-Type': 'application/json',
        'X-Idempotency-Key': `idem-${Date.now()}-${Math.random()}`
      },
    }
  );
  
  const createSuccess = check(createResponse, {
    'refund saga creation status is 201': (r) => r.status === 201,
    'refund saga creation response has id': (r) => {
      try {
        const body = JSON.parse(r.body);
        return body.id !== undefined;
      } catch (e) {
        return false;
      }
    },
  });
  
  sagaCreationRate.add(createSuccess);
  
  if (!createSuccess) {
    sagaErrors.add(1);
    console.error(`Refund saga creation failed: ${createResponse.status} - ${createResponse.body}`);
  }
}

function testQueryOperations() {
  // Test listing sagas
  const listResponse = http.get(`${BASE_URL}/api/v1/sagas?limit=10&offset=0`);
  
  check(listResponse, {
    'saga list query successful': (r) => r.status === 200,
    'saga list response is array': (r) => {
      try {
        const body = JSON.parse(r.body);
        return Array.isArray(body);
      } catch (e) {
        return false;
      }
    },
  });
  
  // Test health check
  const healthResponse = http.get(`${BASE_URL}/health`);
  
  check(healthResponse, {
    'health check successful': (r) => r.status === 200,
    'health check response valid': (r) => {
      try {
        const body = JSON.parse(r.body);
        return body.status === 'healthy';
      } catch (e) {
        return false;
      }
    },
  });
  
  // Test metrics endpoint
  const metricsResponse = http.get(`${BASE_URL}/metrics`);
  
  check(metricsResponse, {
    'metrics endpoint accessible': (r) => r.status === 200,
    'metrics response not empty': (r) => r.body.length > 0,
  });
}

// Setup function - runs once before the test
export function setup() {
  console.log('Starting Saga Orchestrator Load Test');
  console.log(`Target URL: ${BASE_URL}`);
  
  // Verify service is accessible
  const healthResponse = http.get(`${BASE_URL}/health`);
  if (healthResponse.status !== 200) {
    throw new Error(`Service not accessible: ${healthResponse.status}`);
  }
  
  console.log('Service health check passed');
  return { baseUrl: BASE_URL };
}

// Teardown function - runs once after the test
export function teardown(data) {
  console.log('Saga Orchestrator Load Test completed');
  console.log(`Base URL used: ${data.baseUrl}`);
}

// Handle summary - custom summary output
export function handleSummary(data) {
  return {
    'stdout': textSummary(data, { indent: ' ', enableColors: true }),
    'summary.json': JSON.stringify(data),
    'summary.html': htmlReport(data),
  };
}

function textSummary(data, options = {}) {
  const indent = options.indent || '';
  const enableColors = options.enableColors || false;
  
  let summary = `${indent}Saga Orchestrator Load Test Summary\n`;
  summary += `${indent}=====================================\n\n`;
  
  // Test duration
  const testDuration = (data.state.testRunDurationMs / 1000).toFixed(2);
  summary += `${indent}Test Duration: ${testDuration}s\n`;
  
  // VU information
  summary += `${indent}Virtual Users: ${data.options.stages.map(s => s.target).join(' -> ')}\n\n`;
  
  // HTTP metrics
  const httpReqs = data.metrics.http_reqs;
  const httpReqDuration = data.metrics.http_req_duration;
  
  if (httpReqs) {
    summary += `${indent}HTTP Requests:\n`;
    summary += `${indent}  Total: ${httpReqs.values.count}\n`;
    summary += `${indent}  Rate: ${httpReqs.values.rate.toFixed(2)}/s\n`;
  }
  
  if (httpReqDuration) {
    summary += `${indent}  Duration (avg): ${httpReqDuration.values.avg.toFixed(2)}ms\n`;
    summary += `${indent}  Duration (p95): ${httpReqDuration.values['p(95)'].toFixed(2)}ms\n`;
  }
  
  // Custom metrics
  const sagaCreationRate = data.metrics.saga_creation_success_rate;
  const sagaCompletionRate = data.metrics.saga_completion_success_rate;
  const sagaErrors = data.metrics.saga_errors;
  
  summary += `\n${indent}Saga Metrics:\n`;
  if (sagaCreationRate) {
    summary += `${indent}  Creation Success Rate: ${(sagaCreationRate.values.rate * 100).toFixed(2)}%\n`;
  }
  if (sagaCompletionRate) {
    summary += `${indent}  Completion Success Rate: ${(sagaCompletionRate.values.rate * 100).toFixed(2)}%\n`;
  }
  if (sagaErrors) {
    summary += `${indent}  Total Errors: ${sagaErrors.values.count}\n`;
  }
  
  return summary;
}

function htmlReport(data) {
  // Simple HTML report - in a real scenario, you'd use a proper template
  return `
<!DOCTYPE html>
<html>
<head>
    <title>Saga Orchestrator Load Test Report</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .metric { margin: 10px 0; }
        .success { color: green; }
        .warning { color: orange; }
        .error { color: red; }
    </style>
</head>
<body>
    <h1>Saga Orchestrator Load Test Report</h1>
    <div class="metric">Test Duration: ${(data.state.testRunDurationMs / 1000).toFixed(2)}s</div>
    <div class="metric">HTTP Requests: ${data.metrics.http_reqs ? data.metrics.http_reqs.values.count : 'N/A'}</div>
    <div class="metric">Saga Creation Success Rate: ${data.metrics.saga_creation_success_rate ? (data.metrics.saga_creation_success_rate.values.rate * 100).toFixed(2) + '%' : 'N/A'}</div>
    <div class="metric">Saga Completion Success Rate: ${data.metrics.saga_completion_success_rate ? (data.metrics.saga_completion_success_rate.values.rate * 100).toFixed(2) + '%' : 'N/A'}</div>
    <div class="metric">Total Errors: ${data.metrics.saga_errors ? data.metrics.saga_errors.values.count : 'N/A'}</div>
</body>
</html>`;
}

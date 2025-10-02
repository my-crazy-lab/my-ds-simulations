import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';

// Custom metrics for data ingestion
const ingestionSuccessRate = new Rate('ingestion_success_rate');
const ingestionDuration = new Trend('ingestion_duration');
const validationErrors = new Counter('validation_errors');
const duplicateMessages = new Counter('duplicate_messages');
const processingErrors = new Counter('processing_errors');

// Test configuration
export const options = {
  stages: [
    { duration: '2m', target: 10 },   // Ramp up to 10 users
    { duration: '5m', target: 10 },   // Stay at 10 users
    { duration: '2m', target: 50 },   // Ramp up to 50 users
    { duration: '5m', target: 50 },   // Stay at 50 users
    { duration: '2m', target: 100 },  // Ramp up to 100 users
    { duration: '5m', target: 100 },  // Stay at 100 users
    { duration: '3m', target: 0 },    // Ramp down to 0 users
  ],
  thresholds: {
    http_req_duration: ['p(95)<3000'], // 95% of requests must complete below 3s (SLO requirement)
    ingestion_success_rate: ['rate>0.99'], // 99% success rate (≤1% invalid records SLO)
    ingestion_duration: ['p(95)<3000'], // End-to-end latency <3s for 95th percentile
    validation_errors: ['count<100'], // Less than 100 validation errors total
    processing_errors: ['count<50'], // Less than 50 processing errors total
  },
};

const BASE_URL = 'http://localhost:8080';

// Message templates for different sources and types
const messageTemplates = {
  zalo_chat: {
    source: 'zalo',
    type: 'chat_message',
    data: {
      user_id: '${USER_ID}',
      conversation_id: 'conv-${CONV_ID}',
      content: '${CONTENT}',
      sender_id: 'user-${SENDER_ID}',
    },
    metadata: {
      platform: 'zalo',
    }
  },
  webhook_event: {
    source: 'webhook',
    type: 'user_event',
    data: {
      event_name: '${EVENT_NAME}',
      user_id: 'user-${USER_ID}',
      properties: {
        device_type: '${DEVICE_TYPE}',
        session_id: 'session-${SESSION_ID}',
      }
    },
    metadata: {
      webhook_source: 'partner_api',
      webhook_signature: 'sha256=${SIGNATURE}',
    }
  },
  csv_import: {
    source: 'csv',
    type: 'chat_message',
    data: {
      content: '${CONTENT}',
      sender_id: 'user-${SENDER_ID}',
      timestamp: '${TIMESTAMP}',
    },
    metadata: {
      csv_file: 'import_${FILE_ID}.csv',
      row_number: '${ROW_NUMBER}',
    }
  },
  api_message: {
    source: 'api',
    type: 'chat_message',
    data: {
      content: '${CONTENT}',
      sender_id: 'user-${SENDER_ID}',
      phone: '${PHONE}',
      email: '${EMAIL}',
    },
    metadata: {
      client_id: 'client-${CLIENT_ID}',
    }
  }
};

// Sample data for message generation
const sampleData = {
  contents: [
    'Hello, how can I help you today?',
    'I need assistance with my order',
    'Thank you for your help!',
    'Can you provide more information?',
    'I would like to make a complaint',
    'Great service, thank you!',
    'I have a question about billing',
    'Please update my account information',
    'When will my order be delivered?',
    'I want to cancel my subscription',
  ],
  eventNames: [
    'user_login',
    'user_logout',
    'page_view',
    'button_click',
    'form_submit',
    'purchase_complete',
    'cart_add',
    'search_query',
    'profile_update',
    'support_ticket_create',
  ],
  deviceTypes: ['mobile', 'desktop', 'tablet'],
  phoneNumbers: [
    '0901234567',
    '84987654321',
    '+84912345678',
    '0123456789',
    '84909876543',
  ],
  emails: [
    'user1@example.com',
    'test.user@gmail.com',
    'customer@company.com',
    'support@service.com',
    'admin@platform.com',
  ]
};

function generateRandomMessage() {
  const templates = Object.keys(messageTemplates);
  const templateKey = templates[Math.floor(Math.random() * templates.length)];
  const template = JSON.parse(JSON.stringify(messageTemplates[templateKey]));
  
  // Generate unique IDs
  const messageId = `msg-${Date.now()}-${Math.floor(Math.random() * 10000)}`;
  const userId = Math.floor(Math.random() * 10000);
  const senderId = Math.floor(Math.random() * 1000);
  
  // Replace placeholders in template
  const messageStr = JSON.stringify(template)
    .replace(/\$\{USER_ID\}/g, userId)
    .replace(/\$\{SENDER_ID\}/g, senderId)
    .replace(/\$\{CONV_ID\}/g, Math.floor(Math.random() * 1000))
    .replace(/\$\{SESSION_ID\}/g, Math.floor(Math.random() * 10000))
    .replace(/\$\{CLIENT_ID\}/g, Math.floor(Math.random() * 100))
    .replace(/\$\{FILE_ID\}/g, Math.floor(Math.random() * 50))
    .replace(/\$\{ROW_NUMBER\}/g, Math.floor(Math.random() * 10000))
    .replace(/\$\{SIGNATURE\}/g, Math.random().toString(36).substring(7))
    .replace(/\$\{CONTENT\}/g, sampleData.contents[Math.floor(Math.random() * sampleData.contents.length)])
    .replace(/\$\{EVENT_NAME\}/g, sampleData.eventNames[Math.floor(Math.random() * sampleData.eventNames.length)])
    .replace(/\$\{DEVICE_TYPE\}/g, sampleData.deviceTypes[Math.floor(Math.random() * sampleData.deviceTypes.length)])
    .replace(/\$\{PHONE\}/g, sampleData.phoneNumbers[Math.floor(Math.random() * sampleData.phoneNumbers.length)])
    .replace(/\$\{EMAIL\}/g, sampleData.emails[Math.floor(Math.random() * sampleData.emails.length)])
    .replace(/\$\{TIMESTAMP\}/g, new Date().toISOString());
  
  const message = JSON.parse(messageStr);
  message.id = messageId;
  message.timestamp = new Date().toISOString();
  
  return message;
}

function generateDuplicateMessage(originalMessage) {
  // Create a duplicate by using the same idempotency key
  const duplicate = JSON.parse(JSON.stringify(originalMessage));
  duplicate.id = `dup-${Date.now()}-${Math.floor(Math.random() * 1000)}`;
  duplicate.idempotency_key = originalMessage.idempotency_key || `key-${originalMessage.id}`;
  return duplicate;
}

function generateInvalidMessage() {
  const invalidMessages = [
    // Missing required fields
    {
      id: '',
      source: '',
      type: '',
      data: null,
    },
    // Invalid timestamp (too far in future)
    {
      id: `invalid-${Date.now()}`,
      source: 'api',
      type: 'chat_message',
      timestamp: new Date(Date.now() + 2 * 60 * 60 * 1000).toISOString(), // 2 hours in future
      data: { content: 'Invalid message', sender_id: 'user-123' },
    },
    // Invalid timestamp (too old)
    {
      id: `invalid-${Date.now()}`,
      source: 'api',
      type: 'chat_message',
      timestamp: new Date(Date.now() - 31 * 24 * 60 * 60 * 1000).toISOString(), // 31 days old
      data: { content: 'Old message', sender_id: 'user-123' },
    },
    // Missing Zalo required fields
    {
      id: `invalid-${Date.now()}`,
      source: 'zalo',
      type: 'chat_message',
      timestamp: new Date().toISOString(),
      data: { content: 'Missing user_id' }, // Missing user_id and conversation_id
    },
    // Empty chat content
    {
      id: `invalid-${Date.now()}`,
      source: 'api',
      type: 'chat_message',
      timestamp: new Date().toISOString(),
      data: { content: '', sender_id: 'user-123' },
    },
  ];
  
  return invalidMessages[Math.floor(Math.random() * invalidMessages.length)];
}

export default function () {
  // Test health endpoint
  const healthRes = http.get(`${BASE_URL}/health`);
  check(healthRes, {
    'health check status is 200': (r) => r.status === 200,
    'health check response time < 100ms': (r) => r.timings.duration < 100,
  });

  // Determine message type based on probability
  const rand = Math.random();
  let message;
  let expectedStatus = 202; // Accepted
  let isValidMessage = true;

  if (rand < 0.7) {
    // 70% valid messages
    message = generateRandomMessage();
  } else if (rand < 0.8) {
    // 10% duplicate messages
    const originalMessage = generateRandomMessage();
    message = generateDuplicateMessage(originalMessage);
    
    // Send original first
    const originalPayload = JSON.stringify(originalMessage);
    http.post(`${BASE_URL}/api/v1/ingest`, originalPayload, {
      headers: { 'Content-Type': 'application/json' },
    });
    
    // Now send duplicate (should be handled gracefully)
    duplicateMessages.add(1);
  } else {
    // 20% invalid messages (to test validation)
    message = generateInvalidMessage();
    expectedStatus = 400; // Bad Request or 500 Internal Server Error
    isValidMessage = false;
  }

  // Send message to ingestion endpoint
  const payload = JSON.stringify(message);
  const startTime = Date.now();
  
  const response = http.post(`${BASE_URL}/api/v1/ingest`, payload, {
    headers: { 'Content-Type': 'application/json' },
  });
  
  const duration = Date.now() - startTime;
  ingestionDuration.add(duration);

  // Check response
  const success = check(response, {
    'ingestion request completed': (r) => r.status !== 0,
    'response time acceptable': (r) => r.timings.duration < 5000, // 5s max
  });

  if (isValidMessage) {
    const validSuccess = check(response, {
      'valid message accepted': (r) => r.status === 202,
      'valid response format': (r) => {
        try {
          const body = JSON.parse(r.body);
          return body.status === 'accepted' && body.message_id;
        } catch (e) {
          return false;
        }
      },
    });
    
    ingestionSuccessRate.add(validSuccess);
    
    if (!validSuccess) {
      processingErrors.add(1);
      if (__VU === 1) { // Log errors from VU 1 only
        console.error(`Valid message failed: ${response.status} ${response.body}`);
      }
    }
  } else {
    // Invalid messages should be rejected
    const invalidHandled = check(response, {
      'invalid message rejected': (r) => r.status === 400 || r.status === 500,
    });
    
    if (invalidHandled) {
      validationErrors.add(1);
    } else {
      processingErrors.add(1);
      if (__VU === 1) {
        console.error(`Invalid message not properly rejected: ${response.status} ${response.body}`);
      }
    }
  }

  // Log progress periodically
  if (__VU === 1 && __ITER % 50 === 0) {
    console.log(`Iteration ${__ITER}: ${response.status} (${duration}ms)`);
  }

  // Random sleep between requests (0.1-1.0 seconds)
  sleep(Math.random() * 0.9 + 0.1);
}

export function handleSummary(data) {
  const ingestionRate = data.metrics.ingestion_success_rate ? data.metrics.ingestion_success_rate.values.rate : 0;
  const avgDuration = data.metrics.ingestion_duration ? data.metrics.ingestion_duration.values.avg : 0;
  const p95Duration = data.metrics.http_req_duration ? data.metrics.http_req_duration.values['p(95)'] : 0;
  
  return {
    'ingestion-load-test-results.json': JSON.stringify(data, null, 2),
    stdout: `
📊 Data Ingestion Load Test Results
===================================

🎯 Test Configuration:
   • Duration: ~24 minutes with ramping stages
   • Max VUs: 100 concurrent users
   • Message Types: Zalo, Webhook, CSV, API (70% valid, 10% duplicate, 20% invalid)

📈 Key Metrics:
   • Total Requests: ${data.metrics.http_reqs.values.count}
   • Request Rate: ${data.metrics.http_reqs.values.rate.toFixed(2)}/s
   • Average Response Time: ${data.metrics.http_req_duration.values.avg.toFixed(2)}ms
   • 95th Percentile: ${p95Duration.toFixed(2)}ms

✅ Success Rates:
   • Ingestion Success Rate: ${(ingestionRate * 100).toFixed(1)}%
   • Validation Errors: ${data.metrics.validation_errors.values.count}
   • Processing Errors: ${data.metrics.processing_errors.values.count}
   • Duplicate Messages: ${data.metrics.duplicate_messages.values.count}

🚀 Performance:
   • Average Ingestion Duration: ${avgDuration.toFixed(2)}ms
   • Failed Requests: ${data.metrics.http_req_failed.values.count}
   • Data Sent: ${(data.metrics.data_sent.values.count / 1024 / 1024).toFixed(2)} MB
   • Data Received: ${(data.metrics.data_received.values.count / 1024).toFixed(2)} KB

📋 SLO Compliance:
${p95Duration < 3000 ? '✅' : '❌'} End-to-end Latency: < 3s (95th percentile) - ${p95Duration.toFixed(2)}ms
${ingestionRate > 0.99 ? '✅' : '❌'} Invalid Records: ≤ 1% - ${((1 - ingestionRate) * 100).toFixed(1)}%
${data.metrics.validation_errors.values.count < 100 ? '✅' : '❌'} Validation Errors: < 100 - ${data.metrics.validation_errors.values.count}
${data.metrics.processing_errors.values.count < 50 ? '✅' : '❌'} Processing Errors: < 50 - ${data.metrics.processing_errors.values.count}

===================================
`,
  };
}

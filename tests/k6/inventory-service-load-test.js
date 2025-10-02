import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';

// Custom metrics
const inventoryOperationRate = new Rate('inventory_operation_success_rate');
const reservationRate = new Rate('reservation_success_rate');
const inventoryErrors = new Counter('inventory_errors');
const reservationDuration = new Trend('reservation_duration');

// Test configuration
export const options = {
  scenarios: {
    // Scenario 1: Read-heavy workload (70% of traffic)
    read_heavy: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '2m', target: 20 },
        { duration: '5m', target: 20 },
        { duration: '2m', target: 0 },
      ],
      exec: 'readHeavyWorkload',
    },
    // Scenario 2: Write-heavy workload (20% of traffic)
    write_heavy: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '2m', target: 5 },
        { duration: '5m', target: 5 },
        { duration: '2m', target: 0 },
      ],
      exec: 'writeHeavyWorkload',
    },
    // Scenario 3: Reservation stress test (10% of traffic)
    reservation_stress: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '2m', target: 3 },
        { duration: '5m', target: 3 },
        { duration: '2m', target: 0 },
      ],
      exec: 'reservationStressTest',
    },
  },
  thresholds: {
    http_req_duration: ['p(95)<1000'], // 95% of requests must complete below 1s
    inventory_operation_success_rate: ['rate>0.95'], // 95% success rate
    reservation_success_rate: ['rate>0.90'], // 90% success rate for reservations
    inventory_errors: ['count<50'], // Less than 50 errors total
  },
};

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8081';

// Test data generators
function generateInventoryItem() {
  const sku = `ITEM${Math.floor(Math.random() * 10000).toString().padStart(4, '0')}`;
  const categories = ['Electronics', 'Clothing', 'Books', 'Home', 'Sports'];
  const category = categories[Math.floor(Math.random() * categories.length)];
  
  return {
    sku: sku,
    name: `Test ${category} Item ${Math.floor(Math.random() * 1000)}`,
    description: `A test ${category.toLowerCase()} item for load testing`,
    quantity: Math.floor(Math.random() * 100) + 10,
    price: Math.floor(Math.random() * 500) + 10,
    category: category,
  };
}

function generateReservationRequest() {
  return {
    quantity: Math.floor(Math.random() * 5) + 1,
    reservation_id: `res-${Math.random().toString(36).substr(2, 9)}`,
    expires_in_minutes: Math.floor(Math.random() * 30) + 5,
  };
}

// Scenario 1: Read-heavy workload
export function readHeavyWorkload() {
  const operations = [
    () => listInventoryItems(),
    () => getRandomInventoryItem(),
    () => listReservations(),
    () => checkHealthAndMetrics(),
  ];
  
  // Execute random read operation
  const operation = operations[Math.floor(Math.random() * operations.length)];
  operation();
  
  sleep(Math.random() * 2 + 0.5); // Random sleep between 0.5-2.5 seconds
}

// Scenario 2: Write-heavy workload
export function writeHeavyWorkload() {
  const operations = [
    () => createInventoryItem(),
    () => updateInventoryItem(),
    () => createAndReleaseReservation(),
  ];
  
  // Execute random write operation
  const operation = operations[Math.floor(Math.random() * operations.length)];
  operation();
  
  sleep(Math.random() * 3 + 1); // Random sleep between 1-4 seconds
}

// Scenario 3: Reservation stress test
export function reservationStressTest() {
  // Focus on reservation operations that can cause contention
  const operations = [
    () => concurrentReservationTest(),
    () => reservationReleaseTest(),
    () => expiredReservationTest(),
  ];
  
  const operation = operations[Math.floor(Math.random() * operations.length)];
  operation();
  
  sleep(Math.random() * 2 + 1); // Random sleep between 1-3 seconds
}

// Individual test functions
function listInventoryItems() {
  const limit = Math.floor(Math.random() * 20) + 5; // 5-25 items
  const offset = Math.floor(Math.random() * 100);
  
  const response = http.get(`${BASE_URL}/api/v1/inventory?limit=${limit}&offset=${offset}`);
  
  const success = check(response, {
    'inventory list status is 200': (r) => r.status === 200,
    'inventory list response is array': (r) => {
      try {
        const body = JSON.parse(r.body);
        return Array.isArray(body);
      } catch (e) {
        return false;
      }
    },
  });
  
  inventoryOperationRate.add(success);
  if (!success) {
    inventoryErrors.add(1);
  }
}

function getRandomInventoryItem() {
  // First get a list to find an existing SKU
  const listResponse = http.get(`${BASE_URL}/api/v1/inventory?limit=10`);
  
  if (listResponse.status === 200) {
    try {
      const items = JSON.parse(listResponse.body);
      if (items.length > 0) {
        const randomItem = items[Math.floor(Math.random() * items.length)];
        const response = http.get(`${BASE_URL}/api/v1/inventory/${randomItem.sku}`);
        
        const success = check(response, {
          'get inventory item status is 200': (r) => r.status === 200,
          'get inventory item has sku': (r) => {
            try {
              const body = JSON.parse(r.body);
              return body.sku === randomItem.sku;
            } catch (e) {
              return false;
            }
          },
        });
        
        inventoryOperationRate.add(success);
        if (!success) {
          inventoryErrors.add(1);
        }
      }
    } catch (e) {
      inventoryErrors.add(1);
    }
  }
}

function createInventoryItem() {
  const item = generateInventoryItem();
  
  const response = http.post(
    `${BASE_URL}/api/v1/inventory`,
    JSON.stringify(item),
    {
      headers: { 'Content-Type': 'application/json' },
    }
  );
  
  const success = check(response, {
    'create inventory item status is 201': (r) => r.status === 201,
    'create inventory item response has id': (r) => {
      try {
        const body = JSON.parse(r.body);
        return body.id !== undefined;
      } catch (e) {
        return false;
      }
    },
  });
  
  inventoryOperationRate.add(success);
  if (!success) {
    inventoryErrors.add(1);
    console.error(`Create item failed: ${response.status} - ${response.body}`);
  }
  
  return success ? JSON.parse(response.body) : null;
}

function updateInventoryItem() {
  // First create an item to update
  const createdItem = createInventoryItem();
  if (!createdItem) return;
  
  sleep(0.1); // Small delay to ensure creation is processed
  
  const updates = {
    name: `Updated ${createdItem.name}`,
    quantity: createdItem.quantity + Math.floor(Math.random() * 10),
    price: createdItem.price + Math.floor(Math.random() * 50),
  };
  
  const response = http.put(
    `${BASE_URL}/api/v1/inventory/${createdItem.sku}`,
    JSON.stringify(updates),
    {
      headers: { 'Content-Type': 'application/json' },
    }
  );
  
  const success = check(response, {
    'update inventory item status is 200': (r) => r.status === 200,
    'update inventory item response valid': (r) => {
      try {
        const body = JSON.parse(r.body);
        return body.name === updates.name;
      } catch (e) {
        return false;
      }
    },
  });
  
  inventoryOperationRate.add(success);
  if (!success) {
    inventoryErrors.add(1);
  }
}

function createAndReleaseReservation() {
  // First create an item with sufficient stock
  const item = generateInventoryItem();
  item.quantity = 50; // Ensure sufficient stock
  
  const createResponse = http.post(
    `${BASE_URL}/api/v1/inventory`,
    JSON.stringify(item),
    {
      headers: { 'Content-Type': 'application/json' },
    }
  );
  
  if (createResponse.status !== 201) {
    inventoryErrors.add(1);
    return;
  }
  
  sleep(0.1); // Small delay
  
  // Create reservation
  const reservationRequest = generateReservationRequest();
  reservationRequest.quantity = Math.min(reservationRequest.quantity, 5); // Don't exceed available stock
  
  const reserveResponse = http.post(
    `${BASE_URL}/api/v1/inventory/${item.sku}/reserve`,
    JSON.stringify(reservationRequest),
    {
      headers: { 'Content-Type': 'application/json' },
    }
  );
  
  const reserveSuccess = check(reserveResponse, {
    'create reservation status is 201': (r) => r.status === 201,
    'create reservation response has id': (r) => {
      try {
        const body = JSON.parse(r.body);
        return body.id !== undefined;
      } catch (e) {
        return false;
      }
    },
  });
  
  reservationRate.add(reserveSuccess);
  reservationDuration.add(reserveResponse.timings.duration);
  
  if (!reserveSuccess) {
    inventoryErrors.add(1);
    return;
  }
  
  const reservation = JSON.parse(reserveResponse.body);
  
  sleep(Math.random() * 2 + 0.5); // Hold reservation for a bit
  
  // Release reservation
  const releaseResponse = http.post(
    `${BASE_URL}/api/v1/inventory/${item.sku}/release`,
    JSON.stringify({ reservation_id: reservation.id }),
    {
      headers: { 'Content-Type': 'application/json' },
    }
  );
  
  const releaseSuccess = check(releaseResponse, {
    'release reservation status is 200': (r) => r.status === 200,
  });
  
  if (!releaseSuccess) {
    inventoryErrors.add(1);
  }
}

function concurrentReservationTest() {
  // Create item with limited stock to test contention
  const item = generateInventoryItem();
  item.quantity = 10; // Limited stock
  
  const createResponse = http.post(
    `${BASE_URL}/api/v1/inventory`,
    JSON.stringify(item),
    {
      headers: { 'Content-Type': 'application/json' },
    }
  );
  
  if (createResponse.status !== 201) {
    inventoryErrors.add(1);
    return;
  }
  
  sleep(0.1);
  
  // Try to reserve more than available (should fail gracefully)
  const reservationRequest = generateReservationRequest();
  reservationRequest.quantity = 15; // More than available
  
  const reserveResponse = http.post(
    `${BASE_URL}/api/v1/inventory/${item.sku}/reserve`,
    JSON.stringify(reservationRequest),
    {
      headers: { 'Content-Type': 'application/json' },
    }
  );
  
  // This should fail with insufficient stock
  const expectedFailure = check(reserveResponse, {
    'insufficient stock handled correctly': (r) => r.status === 400 || r.status === 409,
  });
  
  if (!expectedFailure && reserveResponse.status !== 201) {
    inventoryErrors.add(1);
  }
}

function reservationReleaseTest() {
  // Test reservation and immediate release
  const item = generateInventoryItem();
  
  const createResponse = http.post(
    `${BASE_URL}/api/v1/inventory`,
    JSON.stringify(item),
    {
      headers: { 'Content-Type': 'application/json' },
    }
  );
  
  if (createResponse.status !== 201) return;
  
  const reservationRequest = generateReservationRequest();
  const reserveResponse = http.post(
    `${BASE_URL}/api/v1/inventory/${item.sku}/reserve`,
    JSON.stringify(reservationRequest),
    {
      headers: { 'Content-Type': 'application/json' },
    }
  );
  
  if (reserveResponse.status === 201) {
    const reservation = JSON.parse(reserveResponse.body);
    
    // Immediate release
    const releaseResponse = http.post(
      `${BASE_URL}/api/v1/inventory/${item.sku}/release`,
      JSON.stringify({ reservation_id: reservation.id }),
      {
        headers: { 'Content-Type': 'application/json' },
      }
    );
    
    const success = check(releaseResponse, {
      'immediate release successful': (r) => r.status === 200,
    });
    
    if (!success) {
      inventoryErrors.add(1);
    }
  }
}

function expiredReservationTest() {
  // Create reservation with very short expiry (if supported)
  const item = generateInventoryItem();
  
  const createResponse = http.post(
    `${BASE_URL}/api/v1/inventory`,
    JSON.stringify(item),
    {
      headers: { 'Content-Type': 'application/json' },
    }
  );
  
  if (createResponse.status !== 201) return;
  
  const reservationRequest = generateReservationRequest();
  reservationRequest.expires_in_minutes = 1; // Very short expiry
  
  const reserveResponse = http.post(
    `${BASE_URL}/api/v1/inventory/${item.sku}/reserve`,
    JSON.stringify(reservationRequest),
    {
      headers: { 'Content-Type': 'application/json' },
    }
  );
  
  const success = check(reserveResponse, {
    'short expiry reservation created': (r) => r.status === 201,
  });
  
  reservationRate.add(success);
  if (!success) {
    inventoryErrors.add(1);
  }
}

function listReservations() {
  const response = http.get(`${BASE_URL}/api/v1/reservations?limit=10`);
  
  const success = check(response, {
    'list reservations status is 200': (r) => r.status === 200,
    'list reservations response is array': (r) => {
      try {
        const body = JSON.parse(r.body);
        return Array.isArray(body);
      } catch (e) {
        return false;
      }
    },
  });
  
  inventoryOperationRate.add(success);
  if (!success) {
    inventoryErrors.add(1);
  }
}

function checkHealthAndMetrics() {
  // Health check
  const healthResponse = http.get(`${BASE_URL}/health`);
  const healthSuccess = check(healthResponse, {
    'health check successful': (r) => r.status === 200,
  });
  
  // Metrics check
  const metricsResponse = http.get(`${BASE_URL}/metrics`);
  const metricsSuccess = check(metricsResponse, {
    'metrics endpoint accessible': (r) => r.status === 200,
  });
  
  if (!healthSuccess || !metricsSuccess) {
    inventoryErrors.add(1);
  }
}

// Setup and teardown
export function setup() {
  console.log('Starting Inventory Service Load Test');
  console.log(`Target URL: ${BASE_URL}`);
  
  const healthResponse = http.get(`${BASE_URL}/health`);
  if (healthResponse.status !== 200) {
    throw new Error(`Service not accessible: ${healthResponse.status}`);
  }
  
  return { baseUrl: BASE_URL };
}

export function teardown(data) {
  console.log('Inventory Service Load Test completed');
}

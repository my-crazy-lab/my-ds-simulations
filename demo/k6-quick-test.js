import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  vus: 3, // 3 virtual users
  duration: '30s', // run for 30 seconds
};

const BASE_URL = 'http://localhost:8080';

export default function () {
  // Test health endpoint
  const healthRes = http.get(`${BASE_URL}/health`);
  check(healthRes, {
    'health check is 200': (r) => r.status === 200,
  });

  // Create a saga
  const sagaPayload = JSON.stringify({
    type: 'order_processing',
    data: {
      order_id: `order-${Math.floor(Math.random() * 1000)}`,
      user_id: `user-${Math.floor(Math.random() * 100)}`,
      amount: Math.floor(Math.random() * 500) + 50,
    }
  });

  const createRes = http.post(`${BASE_URL}/api/v1/sagas`, sagaPayload, {
    headers: { 'Content-Type': 'application/json' },
  });

  const createSuccess = check(createRes, {
    'saga creation is 201': (r) => r.status === 201,
    'saga has ID': (r) => {
      try {
        const saga = JSON.parse(r.body);
        return saga.id && saga.id.length > 0;
      } catch (e) {
        return false;
      }
    },
  });

  if (createSuccess) {
    const saga = JSON.parse(createRes.body);
    console.log(`Created saga ${saga.id} with status ${saga.status}`);
    
    // Wait a bit and check status
    sleep(1);
    
    const statusRes = http.get(`${BASE_URL}/api/v1/sagas/${saga.id}`);
    check(statusRes, {
      'saga status check is 200': (r) => r.status === 200,
    });
    
    if (statusRes.status === 200) {
      const updatedSaga = JSON.parse(statusRes.body);
      console.log(`Saga ${saga.id} final status: ${updatedSaga.status}`);
    }
  }

  sleep(1);
}

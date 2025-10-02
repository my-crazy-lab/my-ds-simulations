import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';

// Custom metrics
const syncOperationRate = new Rate('sync_operation_success_rate');
const conflictResolutionRate = new Rate('conflict_resolution_success_rate');
const crdtMergeRate = new Rate('crdt_merge_success_rate');
const syncErrors = new Counter('sync_errors');
const syncDuration = new Trend('sync_duration');
const conflictResolutionDuration = new Trend('conflict_resolution_duration');

// Test configuration
export const options = {
  scenarios: {
    // Scenario 1: Device sync simulation (60% of traffic)
    device_sync: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '1m', target: 10 },
        { duration: '3m', target: 10 },
        { duration: '1m', target: 0 },
      ],
      exec: 'deviceSyncWorkload',
    },
    // Scenario 2: Conflict resolution stress test (30% of traffic)
    conflict_resolution: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '1m', target: 5 },
        { duration: '3m', target: 5 },
        { duration: '1m', target: 0 },
      ],
      exec: 'conflictResolutionWorkload',
    },
    // Scenario 3: CRDT operations (10% of traffic)
    crdt_operations: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '1m', target: 2 },
        { duration: '3m', target: 2 },
        { duration: '1m', target: 0 },
      ],
      exec: 'crdtOperationsWorkload',
    },
  },
  thresholds: {
    http_req_duration: ['p(95)<2000'], // 95% of requests must complete below 2s
    sync_operation_success_rate: ['rate>0.90'], // 90% success rate for sync operations
    conflict_resolution_success_rate: ['rate>0.95'], // 95% success rate for conflict resolution
    crdt_merge_success_rate: ['rate>0.98'], // 98% success rate for CRDT merges
    sync_errors: ['count<30'], // Less than 30 errors total
  },
};

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8091';

// Test data generators
function generateDeviceId() {
  return `device-${Math.random().toString(36).substr(2, 8)}`;
}

function generateUserId() {
  return `user-${Math.random().toString(36).substr(2, 6)}`;
}

function generateDocumentId() {
  return `doc-${Math.random().toString(36).substr(2, 10)}`;
}

function generateTimestamp(offsetMs = 0) {
  return new Date(Date.now() + offsetMs).toISOString();
}

function generateSyncData() {
  const deviceId = generateDeviceId();
  const changes = [];
  
  // Generate 1-5 changes per sync
  const numChanges = Math.floor(Math.random() * 5) + 1;
  
  for (let i = 0; i < numChanges; i++) {
    changes.push({
      entity_id: generateDocumentId(),
      entity_type: 'document',
      crdt_type: 'LWWRegister',
      operations: [
        {
          type: 'set',
          value: `Content from ${deviceId} - ${Math.random().toString(36).substr(2, 10)}`,
          timestamp: generateTimestamp(Math.random() * 1000), // Random timestamp within last second
          node_id: deviceId,
        }
      ],
      vector_clock: {
        [deviceId]: Math.floor(Math.random() * 100) + 1,
      }
    });
  }
  
  return {
    device_id: deviceId,
    user_id: generateUserId(),
    changes: changes,
    sync_timestamp: generateTimestamp(),
  };
}

function generateConflictingData() {
  const entityId = generateDocumentId();
  const baseTimestamp = Date.now();
  
  return {
    entity_id: entityId,
    local_state: {
      crdt_type: 'LWWRegister',
      value: `Local value - ${Math.random().toString(36).substr(2, 8)}`,
      timestamp: new Date(baseTimestamp).toISOString(),
      node_id: 'device-local',
    },
    remote_state: {
      crdt_type: 'LWWRegister',
      value: `Remote value - ${Math.random().toString(36).substr(2, 8)}`,
      timestamp: new Date(baseTimestamp + Math.random() * 2000 - 1000).toISOString(), // ±1 second
      node_id: 'device-remote',
    }
  };
}

function generateCRDTMergeData() {
  const crdtTypes = ['LWWRegister', 'GCounter', 'PNCounter'];
  const crdtType = crdtTypes[Math.floor(Math.random() * crdtTypes.length)];
  
  switch (crdtType) {
    case 'LWWRegister':
      return {
        crdt_type: 'LWWRegister',
        local_state: {
          value: `Local-${Math.random().toString(36).substr(2, 6)}`,
          timestamp: generateTimestamp(-Math.random() * 1000),
          node_id: 'node1',
        },
        remote_state: {
          value: `Remote-${Math.random().toString(36).substr(2, 6)}`,
          timestamp: generateTimestamp(Math.random() * 1000),
          node_id: 'node2',
        }
      };
    
    case 'GCounter':
      return {
        crdt_type: 'GCounter',
        local_state: {
          counters: {
            'node1': Math.floor(Math.random() * 50),
            'node2': Math.floor(Math.random() * 30),
          }
        },
        remote_state: {
          counters: {
            'node1': Math.floor(Math.random() * 40),
            'node2': Math.floor(Math.random() * 60),
            'node3': Math.floor(Math.random() * 20),
          }
        }
      };
    
    case 'PNCounter':
      return {
        crdt_type: 'PNCounter',
        local_state: {
          positive: {
            'node1': Math.floor(Math.random() * 50),
            'node2': Math.floor(Math.random() * 30),
          },
          negative: {
            'node1': Math.floor(Math.random() * 10),
            'node2': Math.floor(Math.random() * 5),
          }
        },
        remote_state: {
          positive: {
            'node1': Math.floor(Math.random() * 40),
            'node2': Math.floor(Math.random() * 60),
          },
          negative: {
            'node1': Math.floor(Math.random() * 15),
            'node2': Math.floor(Math.random() * 8),
          }
        }
      };
  }
}

// Scenario 1: Device sync workload
export function deviceSyncWorkload() {
  const operations = [
    () => registerDevice(),
    () => uploadChanges(),
    () => downloadChanges(),
    () => getVectorClock(),
  ];
  
  const operation = operations[Math.floor(Math.random() * operations.length)];
  operation();
  
  sleep(Math.random() * 2 + 0.5); // Random sleep between 0.5-2.5 seconds
}

// Scenario 2: Conflict resolution workload
export function conflictResolutionWorkload() {
  const operations = [
    () => resolveConflict(),
    () => listConflicts(),
    () => getConflictHistory(),
  ];
  
  const operation = operations[Math.floor(Math.random() * operations.length)];
  operation();
  
  sleep(Math.random() * 1.5 + 0.5); // Random sleep between 0.5-2 seconds
}

// Scenario 3: CRDT operations workload
export function crdtOperationsWorkload() {
  const operations = [
    () => mergeCRDT(),
    () => compareCRDT(),
    () => getCRDTState(),
  ];
  
  const operation = operations[Math.floor(Math.random() * operations.length)];
  operation();
  
  sleep(Math.random() * 1 + 0.5); // Random sleep between 0.5-1.5 seconds
}

// Individual test functions
function registerDevice() {
  const deviceData = {
    device_id: generateDeviceId(),
    user_id: generateUserId(),
    device_type: 'mobile',
    platform: Math.random() > 0.5 ? 'ios' : 'android',
  };
  
  const response = http.post(
    `${BASE_URL}/api/v1/sync/register-device`,
    JSON.stringify(deviceData),
    {
      headers: { 'Content-Type': 'application/json' },
    }
  );
  
  const success = check(response, {
    'device registration status is 201': (r) => r.status === 201,
    'device registration response has device_id': (r) => {
      try {
        const body = JSON.parse(r.body);
        return body.device_id === deviceData.device_id;
      } catch (e) {
        return false;
      }
    },
  });
  
  syncOperationRate.add(success);
  if (!success) {
    syncErrors.add(1);
    console.error(`Device registration failed: ${response.status} - ${response.body}`);
  }
}

function uploadChanges() {
  const syncData = generateSyncData();
  
  const response = http.post(
    `${BASE_URL}/api/v1/sync/upload`,
    JSON.stringify(syncData),
    {
      headers: { 'Content-Type': 'application/json' },
    }
  );
  
  const success = check(response, {
    'upload changes status is 200': (r) => r.status === 200,
    'upload changes response has sync_id': (r) => {
      try {
        const body = JSON.parse(r.body);
        return body.sync_id !== undefined;
      } catch (e) {
        return false;
      }
    },
  });
  
  syncOperationRate.add(success);
  syncDuration.add(response.timings.duration);
  
  if (!success) {
    syncErrors.add(1);
    console.error(`Upload changes failed: ${response.status} - ${response.body}`);
  }
}

function downloadChanges() {
  const deviceId = generateDeviceId();
  const lastSyncTimestamp = generateTimestamp(-Math.random() * 3600000); // Random time in last hour
  
  const response = http.get(
    `${BASE_URL}/api/v1/sync/download?device_id=${deviceId}&since=${encodeURIComponent(lastSyncTimestamp)}`
  );
  
  const success = check(response, {
    'download changes status is 200': (r) => r.status === 200,
    'download changes response has changes': (r) => {
      try {
        const body = JSON.parse(r.body);
        return Array.isArray(body.changes);
      } catch (e) {
        return false;
      }
    },
  });
  
  syncOperationRate.add(success);
  syncDuration.add(response.timings.duration);
  
  if (!success) {
    syncErrors.add(1);
  }
}

function getVectorClock() {
  const deviceId = generateDeviceId();
  
  const response = http.get(`${BASE_URL}/api/v1/sync/vector-clock?device_id=${deviceId}`);
  
  const success = check(response, {
    'get vector clock status is 200': (r) => r.status === 200,
    'get vector clock response has clock': (r) => {
      try {
        const body = JSON.parse(r.body);
        return body.vector_clock !== undefined;
      } catch (e) {
        return false;
      }
    },
  });
  
  syncOperationRate.add(success);
  if (!success) {
    syncErrors.add(1);
  }
}

function resolveConflict() {
  const conflictData = generateConflictingData();
  
  const response = http.post(
    `${BASE_URL}/api/v1/sync/resolve-conflict`,
    JSON.stringify(conflictData),
    {
      headers: { 'Content-Type': 'application/json' },
    }
  );
  
  const success = check(response, {
    'resolve conflict status is 200': (r) => r.status === 200,
    'resolve conflict response has resolution': (r) => {
      try {
        const body = JSON.parse(r.body);
        return body.resolved_state !== undefined;
      } catch (e) {
        return false;
      }
    },
  });
  
  conflictResolutionRate.add(success);
  conflictResolutionDuration.add(response.timings.duration);
  
  if (!success) {
    syncErrors.add(1);
    console.error(`Conflict resolution failed: ${response.status} - ${response.body}`);
  }
}

function listConflicts() {
  const userId = generateUserId();
  
  const response = http.get(`${BASE_URL}/api/v1/conflicts?user_id=${userId}&limit=10`);
  
  const success = check(response, {
    'list conflicts status is 200': (r) => r.status === 200,
    'list conflicts response is array': (r) => {
      try {
        const body = JSON.parse(r.body);
        return Array.isArray(body);
      } catch (e) {
        return false;
      }
    },
  });
  
  syncOperationRate.add(success);
  if (!success) {
    syncErrors.add(1);
  }
}

function getConflictHistory() {
  const entityId = generateDocumentId();
  
  const response = http.get(`${BASE_URL}/api/v1/conflicts/${entityId}/history`);
  
  const success = check(response, {
    'get conflict history status is 200 or 404': (r) => r.status === 200 || r.status === 404,
  });
  
  syncOperationRate.add(success);
  if (!success) {
    syncErrors.add(1);
  }
}

function mergeCRDT() {
  const mergeData = generateCRDTMergeData();
  
  const response = http.post(
    `${BASE_URL}/api/v1/crdt/merge`,
    JSON.stringify(mergeData),
    {
      headers: { 'Content-Type': 'application/json' },
    }
  );
  
  const success = check(response, {
    'CRDT merge status is 200': (r) => r.status === 200,
    'CRDT merge response has merged state': (r) => {
      try {
        const body = JSON.parse(r.body);
        return body.merged_state !== undefined;
      } catch (e) {
        return false;
      }
    },
  });
  
  crdtMergeRate.add(success);
  
  if (!success) {
    syncErrors.add(1);
    console.error(`CRDT merge failed: ${response.status} - ${response.body}`);
  }
}

function compareCRDT() {
  const compareData = generateCRDTMergeData();
  
  const response = http.post(
    `${BASE_URL}/api/v1/crdt/compare`,
    JSON.stringify(compareData),
    {
      headers: { 'Content-Type': 'application/json' },
    }
  );
  
  const success = check(response, {
    'CRDT compare status is 200': (r) => r.status === 200,
    'CRDT compare response has comparison': (r) => {
      try {
        const body = JSON.parse(r.body);
        return body.comparison !== undefined;
      } catch (e) {
        return false;
      }
    },
  });
  
  crdtMergeRate.add(success);
  if (!success) {
    syncErrors.add(1);
  }
}

function getCRDTState() {
  const entityId = generateDocumentId();
  const crdtType = 'LWWRegister';
  
  const response = http.get(`${BASE_URL}/api/v1/crdt/${entityId}/state?type=${crdtType}`);
  
  const success = check(response, {
    'get CRDT state status is 200 or 404': (r) => r.status === 200 || r.status === 404,
  });
  
  syncOperationRate.add(success);
  if (!success && response.status !== 404) {
    syncErrors.add(1);
  }
}

// Setup and teardown
export function setup() {
  console.log('Starting Sync Service Load Test');
  console.log(`Target URL: ${BASE_URL}`);
  
  const healthResponse = http.get(`${BASE_URL}/health`);
  if (healthResponse.status !== 200) {
    throw new Error(`Service not accessible: ${healthResponse.status}`);
  }
  
  console.log('Service health check passed');
  return { baseUrl: BASE_URL };
}

export function teardown(data) {
  console.log('Sync Service Load Test completed');
  console.log(`Base URL used: ${data.baseUrl}`);
}

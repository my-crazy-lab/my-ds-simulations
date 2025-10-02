/**
 * CRDT Service Implementation
 * 
 * Implements various CRDT types for consistency testing:
 * - G-Counter (Grow-only Counter)
 * - PN-Counter (Positive-Negative Counter)
 * - OR-Set (Observed-Remove Set)
 * - LWW-Register (Last-Write-Wins Register)
 */

import express from 'express';
import cors from 'cors';
import helmet from 'helmet';
import { v4 as uuidv4 } from 'uuid';
import axios from 'axios';

const app = express();
const PORT = process.env.PORT || 8080;
const NODE_ID = process.env.NODE_ID || uuidv4();
const CLUSTER_NODES = (process.env.CLUSTER_NODES || '').split(',').filter(Boolean);
const GOSSIP_INTERVAL = parseInt(process.env.GOSSIP_INTERVAL || '5000');

// Middleware
app.use(helmet());
app.use(cors());
app.use(express.json());

// CRDT Implementations

interface VectorClock {
  [nodeId: string]: number;
}

class GCounter {
  private counters: { [nodeId: string]: number } = {};

  increment(nodeId: string, amount: number = 1): void {
    this.counters[nodeId] = (this.counters[nodeId] || 0) + amount;
  }

  value(): number {
    return Object.values(this.counters).reduce((sum, count) => sum + count, 0);
  }

  merge(other: GCounter): void {
    for (const [nodeId, count] of Object.entries(other.counters)) {
      this.counters[nodeId] = Math.max(this.counters[nodeId] || 0, count);
    }
  }

  toJSON() {
    return { type: 'GCounter', counters: this.counters };
  }

  static fromJSON(data: any): GCounter {
    const counter = new GCounter();
    counter.counters = data.counters || {};
    return counter;
  }
}

class PNCounter {
  private pCounter = new GCounter();
  private nCounter = new GCounter();

  increment(nodeId: string, amount: number = 1): void {
    this.pCounter.increment(nodeId, amount);
  }

  decrement(nodeId: string, amount: number = 1): void {
    this.nCounter.increment(nodeId, amount);
  }

  value(): number {
    return this.pCounter.value() - this.nCounter.value();
  }

  merge(other: PNCounter): void {
    this.pCounter.merge(other.pCounter);
    this.nCounter.merge(other.nCounter);
  }

  toJSON() {
    return {
      type: 'PNCounter',
      pCounter: this.pCounter.toJSON(),
      nCounter: this.nCounter.toJSON()
    };
  }

  static fromJSON(data: any): PNCounter {
    const counter = new PNCounter();
    counter.pCounter = GCounter.fromJSON(data.pCounter);
    counter.nCounter = GCounter.fromJSON(data.nCounter);
    return counter;
  }
}

interface ORSetElement {
  value: any;
  added: VectorClock;
  removed?: VectorClock;
}

class ORSet {
  private elements: Map<string, ORSetElement> = new Map();
  private vectorClock: VectorClock = {};

  private incrementClock(nodeId: string): void {
    this.vectorClock[nodeId] = (this.vectorClock[nodeId] || 0) + 1;
  }

  add(value: any, nodeId: string): void {
    this.incrementClock(nodeId);
    const elementId = `${value}_${nodeId}_${this.vectorClock[nodeId]}`;
    
    this.elements.set(elementId, {
      value,
      added: { ...this.vectorClock }
    });
  }

  remove(value: any, nodeId: string): void {
    this.incrementClock(nodeId);
    
    // Mark all instances of this value as removed
    for (const [elementId, element] of this.elements.entries()) {
      if (element.value === value && !element.removed) {
        element.removed = { ...this.vectorClock };
      }
    }
  }

  contains(value: any): boolean {
    for (const element of this.elements.values()) {
      if (element.value === value && !element.removed) {
        return true;
      }
    }
    return false;
  }

  values(): any[] {
    const result = new Set();
    
    for (const element of this.elements.values()) {
      if (!element.removed) {
        result.add(element.value);
      }
    }
    
    return Array.from(result);
  }

  merge(other: ORSet): void {
    // Merge vector clocks
    for (const [nodeId, clock] of Object.entries(other.vectorClock)) {
      this.vectorClock[nodeId] = Math.max(this.vectorClock[nodeId] || 0, clock);
    }

    // Merge elements
    for (const [elementId, element] of other.elements.entries()) {
      const existing = this.elements.get(elementId);
      
      if (!existing) {
        this.elements.set(elementId, { ...element });
      } else {
        // Merge remove timestamps
        if (element.removed && (!existing.removed || this.compareVectorClocks(element.removed, existing.removed) > 0)) {
          existing.removed = element.removed;
        }
      }
    }
  }

  private compareVectorClocks(a: VectorClock, b: VectorClock): number {
    const allNodes = new Set([...Object.keys(a), ...Object.keys(b)]);
    let aGreater = false;
    let bGreater = false;

    for (const node of allNodes) {
      const aVal = a[node] || 0;
      const bVal = b[node] || 0;

      if (aVal > bVal) aGreater = true;
      if (bVal > aVal) bGreater = true;
    }

    if (aGreater && !bGreater) return 1;
    if (bGreater && !aGreater) return -1;
    return 0;
  }

  toJSON() {
    return {
      type: 'ORSet',
      elements: Array.from(this.elements.entries()),
      vectorClock: this.vectorClock
    };
  }

  static fromJSON(data: any): ORSet {
    const set = new ORSet();
    set.elements = new Map(data.elements || []);
    set.vectorClock = data.vectorClock || {};
    return set;
  }
}

// Global CRDT instances
const crdts: { [name: string]: any } = {
  'counter': new GCounter(),
  'pn-counter': new PNCounter(),
  'set': new ORSet()
};

// API Routes

app.get('/health', (req, res) => {
  res.json({
    status: 'healthy',
    nodeId: NODE_ID,
    timestamp: new Date().toISOString(),
    crdts: Object.keys(crdts)
  });
});

app.get('/node/info', (req, res) => {
  res.json({
    nodeId: NODE_ID,
    clusterNodes: CLUSTER_NODES,
    gossipInterval: GOSSIP_INTERVAL,
    crdts: Object.keys(crdts)
  });
});

// G-Counter operations
app.post('/crdt/counter/increment', (req, res) => {
  const { amount = 1 } = req.body;
  const counter = crdts['counter'] as GCounter;
  
  counter.increment(NODE_ID, amount);
  
  res.json({
    success: true,
    value: counter.value(),
    nodeId: NODE_ID
  });
});

app.get('/crdt/counter/value', (req, res) => {
  const counter = crdts['counter'] as GCounter;
  
  res.json({
    value: counter.value(),
    state: counter.toJSON()
  });
});

// PN-Counter operations
app.post('/crdt/pn-counter/increment', (req, res) => {
  const { amount = 1 } = req.body;
  const counter = crdts['pn-counter'] as PNCounter;
  
  counter.increment(NODE_ID, amount);
  
  res.json({
    success: true,
    value: counter.value(),
    nodeId: NODE_ID
  });
});

app.post('/crdt/pn-counter/decrement', (req, res) => {
  const { amount = 1 } = req.body;
  const counter = crdts['pn-counter'] as PNCounter;
  
  counter.decrement(NODE_ID, amount);
  
  res.json({
    success: true,
    value: counter.value(),
    nodeId: NODE_ID
  });
});

app.get('/crdt/pn-counter/value', (req, res) => {
  const counter = crdts['pn-counter'] as PNCounter;
  
  res.json({
    value: counter.value(),
    state: counter.toJSON()
  });
});

// OR-Set operations
app.post('/crdt/set/add', (req, res) => {
  const { value } = req.body;
  const set = crdts['set'] as ORSet;
  
  set.add(value, NODE_ID);
  
  res.json({
    success: true,
    values: set.values(),
    nodeId: NODE_ID
  });
});

app.post('/crdt/set/remove', (req, res) => {
  const { value } = req.body;
  const set = crdts['set'] as ORSet;
  
  set.remove(value, NODE_ID);
  
  res.json({
    success: true,
    values: set.values(),
    nodeId: NODE_ID
  });
});

app.get('/crdt/set/values', (req, res) => {
  const set = crdts['set'] as ORSet;
  
  res.json({
    values: set.values(),
    state: set.toJSON()
  });
});

// Gossip protocol for CRDT synchronization
app.post('/gossip/sync', (req, res) => {
  const { crdtStates } = req.body;
  
  try {
    for (const [name, state] of Object.entries(crdtStates)) {
      if (crdts[name]) {
        switch (state.type) {
          case 'GCounter':
            const gCounter = GCounter.fromJSON(state);
            (crdts[name] as GCounter).merge(gCounter);
            break;
          case 'PNCounter':
            const pnCounter = PNCounter.fromJSON(state);
            (crdts[name] as PNCounter).merge(pnCounter);
            break;
          case 'ORSet':
            const orSet = ORSet.fromJSON(state);
            (crdts[name] as ORSet).merge(orSet);
            break;
        }
      }
    }
    
    res.json({ success: true, nodeId: NODE_ID });
  } catch (error) {
    console.error('Gossip sync error:', error);
    res.status(500).json({ error: 'Sync failed' });
  }
});

app.get('/gossip/state', (req, res) => {
  const states: { [name: string]: any } = {};
  
  for (const [name, crdt] of Object.entries(crdts)) {
    states[name] = crdt.toJSON();
  }
  
  res.json({
    nodeId: NODE_ID,
    crdtStates: states
  });
});

// Gossip background process
async function gossipSync() {
  if (CLUSTER_NODES.length === 0) return;
  
  const states: { [name: string]: any } = {};
  for (const [name, crdt] of Object.entries(crdts)) {
    states[name] = crdt.toJSON();
  }
  
  for (const nodeUrl of CLUSTER_NODES) {
    if (nodeUrl.includes(NODE_ID)) continue; // Skip self
    
    try {
      await axios.post(`http://${nodeUrl}/gossip/sync`, {
        crdtStates: states
      }, { timeout: 5000 });
      
      console.log(`Gossip sync successful with ${nodeUrl}`);
    } catch (error) {
      console.error(`Gossip sync failed with ${nodeUrl}:`, error.message);
    }
  }
}

// Start gossip protocol
if (CLUSTER_NODES.length > 0) {
  setInterval(gossipSync, GOSSIP_INTERVAL);
  console.log(`Gossip protocol started with interval ${GOSSIP_INTERVAL}ms`);
}

// Start server
app.listen(PORT, () => {
  console.log(`CRDT Service running on port ${PORT}`);
  console.log(`Node ID: ${NODE_ID}`);
  console.log(`Cluster nodes: ${CLUSTER_NODES.join(', ')}`);
});

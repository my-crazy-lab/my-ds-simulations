// MongoDB initialization script for microservices

// Switch to admin database
db = db.getSiblingDB('admin');

// Create service users
db.createUser({
  user: 'transaction_coordinator_user',
  pwd: 'transaction_coordinator_pass',
  roles: [
    { role: 'readWrite', db: 'transaction_coordinator' },
    { role: 'dbAdmin', db: 'transaction_coordinator' }
  ]
});

db.createUser({
  user: 'billing_service_user',
  pwd: 'billing_service_pass',
  roles: [
    { role: 'readWrite', db: 'billing_service' },
    { role: 'dbAdmin', db: 'billing_service' }
  ]
});

db.createUser({
  user: 'outbox_user',
  pwd: 'outbox_pass',
  roles: [
    { role: 'readWrite', db: 'outbox_events' },
    { role: 'dbAdmin', db: 'outbox_events' }
  ]
});

// Initialize transaction_coordinator database
db = db.getSiblingDB('transaction_coordinator');

// Create collections with validation
db.createCollection('transactions', {
  validator: {
    $jsonSchema: {
      bsonType: 'object',
      required: ['id', 'status', 'transaction_type', 'participants', 'created_at'],
      properties: {
        id: { bsonType: 'string' },
        status: { 
          bsonType: 'string',
          enum: ['Pending', 'Preparing', 'Prepared', 'Committing', 'Committed', 'Aborting', 'Aborted', 'Failed']
        },
        transaction_type: { bsonType: 'string' },
        participants: { bsonType: 'array' },
        created_at: { bsonType: 'date' },
        updated_at: { bsonType: 'date' },
        completed_at: { bsonType: ['date', 'null'] },
        timeout_at: { bsonType: ['date', 'null'] },
        error_message: { bsonType: ['string', 'null'] },
        metadata: { bsonType: 'object' },
        participant_responses: { bsonType: 'object' }
      }
    }
  }
});

db.createCollection('sagas', {
  validator: {
    $jsonSchema: {
      bsonType: 'object',
      required: ['id', 'status', 'saga_type', 'steps', 'created_at'],
      properties: {
        id: { bsonType: 'string' },
        status: {
          bsonType: 'string',
          enum: ['Created', 'Running', 'Completed', 'Compensating', 'Compensated', 'Failed']
        },
        saga_type: { bsonType: 'string' },
        steps: { bsonType: 'array' },
        step_executions: { bsonType: 'object' },
        created_at: { bsonType: 'date' },
        updated_at: { bsonType: 'date' },
        completed_at: { bsonType: ['date', 'null'] },
        timeout_at: { bsonType: ['date', 'null'] },
        error_message: { bsonType: ['string', 'null'] },
        metadata: { bsonType: 'object' },
        current_step_index: { bsonType: 'int' },
        compensation_steps: { bsonType: 'array' }
      }
    }
  }
});

db.createCollection('outbox_events', {
  validator: {
    $jsonSchema: {
      bsonType: 'object',
      required: ['id', 'aggregate_id', 'aggregate_type', 'event_type', 'event_data', 'created_at', 'status'],
      properties: {
        id: { bsonType: 'string' },
        aggregate_id: { bsonType: 'string' },
        aggregate_type: { bsonType: 'string' },
        event_type: { bsonType: 'string' },
        event_data: { bsonType: 'object' },
        metadata: { bsonType: 'object' },
        created_at: { bsonType: 'date' },
        processed_at: { bsonType: ['date', 'null'] },
        status: {
          bsonType: 'string',
          enum: ['pending', 'processing', 'processed', 'failed', 'dead_letter']
        },
        retry_count: { bsonType: 'int' },
        max_retries: { bsonType: 'int' },
        next_retry_at: { bsonType: ['date', 'null'] },
        error_message: { bsonType: ['string', 'null'] },
        topic: { bsonType: 'string' },
        partition_key: { bsonType: ['string', 'null'] },
        headers: { bsonType: 'object' },
        source: { bsonType: 'string' }
      }
    }
  }
});

// Create indexes for transaction_coordinator
db.transactions.createIndex({ 'id': 1 }, { unique: true });
db.transactions.createIndex({ 'status': 1, 'created_at': 1 });
db.transactions.createIndex({ 'transaction_type': 1 });
db.transactions.createIndex({ 'timeout_at': 1 }, { sparse: true });

db.sagas.createIndex({ 'id': 1 }, { unique: true });
db.sagas.createIndex({ 'status': 1, 'created_at': 1 });
db.sagas.createIndex({ 'saga_type': 1 });
db.sagas.createIndex({ 'timeout_at': 1 }, { sparse: true });

db.outbox_events.createIndex({ 'id': 1 }, { unique: true });
db.outbox_events.createIndex({ 'status': 1, 'created_at': 1 });
db.outbox_events.createIndex({ 'aggregate_id': 1, 'aggregate_type': 1 });
db.outbox_events.createIndex({ 'status': 1, 'next_retry_at': 1 }, { sparse: true });
db.outbox_events.createIndex({ 'source': 1 });

// Initialize billing_service database
db = db.getSiblingDB('billing_service');

db.createCollection('billing_records', {
  validator: {
    $jsonSchema: {
      bsonType: 'object',
      required: ['id', 'customer_id', 'billing_type', 'status', 'items', 'total_amount', 'currency', 'created_at'],
      properties: {
        id: { bsonType: 'string' },
        customer_id: { bsonType: 'string' },
        order_id: { bsonType: ['string', 'null'] },
        transaction_id: { bsonType: ['string', 'null'] },
        billing_type: {
          bsonType: 'string',
          enum: ['ORDER', 'SUBSCRIPTION', 'ONE_TIME', 'REFUND']
        },
        status: {
          bsonType: 'string',
          enum: ['DRAFT', 'FINALIZED', 'INVOICED', 'PAID', 'PARTIALLY_PAID', 'CANCELLED', 'REFUNDED']
        },
        items: { bsonType: 'array' },
        subtotal: { bsonType: 'number' },
        tax_amount: { bsonType: 'number' },
        discount_amount: { bsonType: 'number' },
        total_amount: { bsonType: 'number' },
        currency: { bsonType: 'string' },
        billing_address: { bsonType: ['object', 'null'] },
        due_date: { bsonType: ['date', 'null'] },
        paid_date: { bsonType: ['date', 'null'] },
        payment_status: {
          bsonType: 'string',
          enum: ['PENDING', 'PAID', 'PARTIAL', 'FAILED', 'REFUNDED']
        },
        payment_method: { bsonType: ['string', 'null'] },
        payment_reference: { bsonType: ['string', 'null'] },
        notes: { bsonType: ['string', 'null'] },
        metadata: { bsonType: 'object' },
        created_at: { bsonType: 'date' },
        updated_at: { bsonType: 'date' },
        version: { bsonType: 'int' }
      }
    }
  }
});

db.createCollection('invoices', {
  validator: {
    $jsonSchema: {
      bsonType: 'object',
      required: ['id', 'invoice_number', 'billing_id', 'customer_id', 'amount', 'currency', 'status', 'created_at'],
      properties: {
        id: { bsonType: 'string' },
        invoice_number: { bsonType: 'string' },
        billing_id: { bsonType: 'string' },
        customer_id: { bsonType: 'string' },
        amount: { bsonType: 'number' },
        currency: { bsonType: 'string' },
        status: {
          bsonType: 'string',
          enum: ['DRAFT', 'SENT', 'PAID', 'OVERDUE', 'CANCELLED']
        },
        due_date: { bsonType: 'date' },
        paid_date: { bsonType: ['date', 'null'] },
        created_at: { bsonType: 'date' },
        updated_at: { bsonType: 'date' }
      }
    }
  }
});

// Create indexes for billing_service
db.billing_records.createIndex({ 'id': 1 }, { unique: true });
db.billing_records.createIndex({ 'customer_id': 1, 'created_at': -1 });
db.billing_records.createIndex({ 'status': 1 });
db.billing_records.createIndex({ 'billing_type': 1 });
db.billing_records.createIndex({ 'due_date': 1 }, { sparse: true });
db.billing_records.createIndex({ 'order_id': 1 }, { sparse: true });
db.billing_records.createIndex({ 'transaction_id': 1 }, { sparse: true });

db.invoices.createIndex({ 'id': 1 }, { unique: true });
db.invoices.createIndex({ 'invoice_number': 1 }, { unique: true });
db.invoices.createIndex({ 'billing_id': 1 });
db.invoices.createIndex({ 'customer_id': 1, 'created_at': -1 });
db.invoices.createIndex({ 'status': 1 });
db.invoices.createIndex({ 'due_date': 1 });

// Initialize outbox_events database (MongoDB version)
db = db.getSiblingDB('outbox_events');

db.createCollection('events', {
  validator: {
    $jsonSchema: {
      bsonType: 'object',
      required: ['id', 'aggregate_id', 'aggregate_type', 'event_type', 'event_data', 'created_at', 'status', 'source'],
      properties: {
        id: { bsonType: 'string' },
        aggregate_id: { bsonType: 'string' },
        aggregate_type: { bsonType: 'string' },
        event_type: { bsonType: 'string' },
        event_data: { bsonType: 'object' },
        metadata: { bsonType: 'object' },
        created_at: { bsonType: 'date' },
        processed_at: { bsonType: ['date', 'null'] },
        status: {
          bsonType: 'string',
          enum: ['pending', 'processing', 'processed', 'failed', 'dead_letter']
        },
        retry_count: { bsonType: 'int' },
        max_retries: { bsonType: 'int' },
        next_retry_at: { bsonType: ['date', 'null'] },
        error_message: { bsonType: ['string', 'null'] },
        topic: { bsonType: 'string' },
        partition_key: { bsonType: ['string', 'null'] },
        headers: { bsonType: 'object' },
        source: { bsonType: 'string' }
      }
    }
  }
});

// Create indexes for outbox_events
db.events.createIndex({ 'id': 1 }, { unique: true });
db.events.createIndex({ 'status': 1, 'created_at': 1 });
db.events.createIndex({ 'aggregate_id': 1, 'aggregate_type': 1 });
db.events.createIndex({ 'status': 1, 'next_retry_at': 1 }, { sparse: true });
db.events.createIndex({ 'source': 1 });
db.events.createIndex({ 'event_type': 1 });

print('MongoDB initialization completed successfully');
print('Created databases: transaction_coordinator, billing_service, outbox_events');
print('Created users with appropriate permissions');
print('Created collections with validation schemas and indexes');

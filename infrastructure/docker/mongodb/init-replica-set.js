// MongoDB Replica Set Initialization

// Wait for MongoDB to be ready
sleep(5000);

// Initialize replica set
try {
    rs.initiate({
        _id: "rs0",
        members: [
            { _id: 0, host: "mongodb-primary:27017", priority: 2 },
            { _id: 1, host: "mongodb-secondary1:27017", priority: 1 },
            { _id: 2, host: "mongodb-secondary2:27017", priority: 1 }
        ]
    });
    
    print("Replica set initialized successfully");
} catch (e) {
    print("Replica set initialization failed: " + e);
}

// Wait for replica set to be ready
sleep(10000);

// Switch to microservices database
db = db.getSiblingDB('microservices');

// Create collections with validation schemas
db.createCollection("user_profiles", {
    validator: {
        $jsonSchema: {
            bsonType: "object",
            required: ["user_id", "email", "created_at"],
            properties: {
                user_id: {
                    bsonType: "string",
                    description: "User ID must be a string and is required"
                },
                email: {
                    bsonType: "string",
                    pattern: "^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$",
                    description: "Email must be a valid email address"
                },
                profile_data: {
                    bsonType: "object",
                    description: "User profile data"
                },
                preferences: {
                    bsonType: "object",
                    description: "User preferences"
                },
                created_at: {
                    bsonType: "date",
                    description: "Creation timestamp"
                },
                updated_at: {
                    bsonType: "date",
                    description: "Last update timestamp"
                },
                version: {
                    bsonType: "int",
                    minimum: 1,
                    description: "Document version for optimistic locking"
                },
                vector_clock: {
                    bsonType: "object",
                    description: "Vector clock for conflict resolution"
                }
            }
        }
    }
});

db.createCollection("sync_conflicts", {
    validator: {
        $jsonSchema: {
            bsonType: "object",
            required: ["entity_type", "entity_id", "conflict_type", "created_at"],
            properties: {
                entity_type: {
                    bsonType: "string",
                    description: "Type of entity in conflict"
                },
                entity_id: {
                    bsonType: "string",
                    description: "ID of entity in conflict"
                },
                conflict_type: {
                    bsonType: "string",
                    enum: ["concurrent_update", "delete_update", "create_create"],
                    description: "Type of conflict"
                },
                local_version: {
                    bsonType: "object",
                    description: "Local version of the data"
                },
                remote_version: {
                    bsonType: "object",
                    description: "Remote version of the data"
                },
                resolved_version: {
                    bsonType: "object",
                    description: "Resolved version after conflict resolution"
                },
                resolution_strategy: {
                    bsonType: "string",
                    enum: ["last_write_wins", "merge", "manual", "crdt"],
                    description: "Strategy used to resolve conflict"
                },
                created_at: {
                    bsonType: "date",
                    description: "Conflict detection timestamp"
                },
                resolved_at: {
                    bsonType: "date",
                    description: "Conflict resolution timestamp"
                }
            }
        }
    }
});

db.createCollection("device_sync_state", {
    validator: {
        $jsonSchema: {
            bsonType: "object",
            required: ["device_id", "user_id", "last_sync_at"],
            properties: {
                device_id: {
                    bsonType: "string",
                    description: "Unique device identifier"
                },
                user_id: {
                    bsonType: "string",
                    description: "User ID owning the device"
                },
                last_sync_at: {
                    bsonType: "date",
                    description: "Last successful sync timestamp"
                },
                sync_token: {
                    bsonType: "string",
                    description: "Token for incremental sync"
                },
                vector_clock: {
                    bsonType: "object",
                    description: "Device vector clock state"
                },
                pending_operations: {
                    bsonType: "array",
                    description: "Operations pending sync"
                }
            }
        }
    }
});

// Create indexes for performance
db.user_profiles.createIndex({ "user_id": 1 }, { unique: true });
db.user_profiles.createIndex({ "email": 1 }, { unique: true });
db.user_profiles.createIndex({ "updated_at": 1 });
db.user_profiles.createIndex({ "vector_clock.device_id": 1, "vector_clock.timestamp": 1 });

db.sync_conflicts.createIndex({ "entity_type": 1, "entity_id": 1 });
db.sync_conflicts.createIndex({ "created_at": 1 });
db.sync_conflicts.createIndex({ "resolution_strategy": 1 });

db.device_sync_state.createIndex({ "device_id": 1 }, { unique: true });
db.device_sync_state.createIndex({ "user_id": 1 });
db.device_sync_state.createIndex({ "last_sync_at": 1 });

// Insert sample data
db.user_profiles.insertMany([
    {
        user_id: "user-001",
        email: "john.doe@example.com",
        profile_data: {
            first_name: "John",
            last_name: "Doe",
            phone: "+1-555-0123",
            address: {
                street: "123 Main St",
                city: "New York",
                state: "NY",
                zip: "10001"
            }
        },
        preferences: {
            notifications: {
                email: true,
                sms: false,
                push: true
            },
            theme: "dark",
            language: "en"
        },
        created_at: new Date(),
        updated_at: new Date(),
        version: 1,
        vector_clock: {
            "device-001": 1,
            "server": 1
        }
    },
    {
        user_id: "user-002",
        email: "jane.smith@example.com",
        profile_data: {
            first_name: "Jane",
            last_name: "Smith",
            phone: "+1-555-0124",
            address: {
                street: "456 Oak Ave",
                city: "Los Angeles",
                state: "CA",
                zip: "90210"
            }
        },
        preferences: {
            notifications: {
                email: true,
                sms: true,
                push: true
            },
            theme: "light",
            language: "en"
        },
        created_at: new Date(),
        updated_at: new Date(),
        version: 1,
        vector_clock: {
            "device-002": 1,
            "server": 1
        }
    }
]);

// Create sharded collections for high-volume data
sh.enableSharding("microservices");

// Shard user_profiles by user_id
sh.shardCollection("microservices.user_profiles", { "user_id": 1 });

// Create capped collection for real-time events
db.createCollection("real_time_events", {
    capped: true,
    size: 100000000, // 100MB
    max: 1000000     // 1M documents
});

db.real_time_events.createIndex({ "timestamp": 1 });
db.real_time_events.createIndex({ "user_id": 1, "timestamp": 1 });

print("MongoDB initialization completed successfully");

// Create change streams for real-time sync
db.user_profiles.watch(
    [
        { $match: { "operationType": { $in: ["insert", "update", "delete"] } } }
    ],
    { fullDocument: "updateLookup" }
);

print("Change streams configured for real-time sync");

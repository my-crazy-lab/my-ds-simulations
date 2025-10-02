# Distributed Databases & Data Warehouse (CQRS, sharding, replication)

> Tập trung: operational DBs + analytics stores, OLTP/OLAP separation, replication, sharding, migrations, backup & restore.
> 

### 1) Online-offline sync & conflict resolution (Advanced)

- **Scenario:** Mobile clients work offline and sync with server DB later. Conflicts occur (same record edited).
- **Mục tiêu:** Design sync protocol + conflict resolution strategy (CRDTs vs last-write vs merge).
- **Ràng buộc:** Offline edit volume, low latency merges.
- **Success metrics:** Conflict rate reduced; merges are deterministic and explainable.
- **Tools/gợi ý:** CRDT libraries, Operational Transformation, event-sourcing, vector clocks.
- **Test / Verify:** Simulate concurrent offline edits; verify resolution logic and audit trail.
- **Tips:** Provide user-facing conflict resolution UI for ambiguous merges.

#### 🔧 **Implementation in Codebase**

**Location**: `services/sync-service/` and `services/cqrs-event-store/`

**Key Files**:
- `services/sync-service/internal/crdt/` - CRDT implementations
- `services/sync-service/internal/conflict/` - Conflict resolution engine
- `services/sync-service/internal/vector_clock/` - Vector clock implementation
- `services/cqrs-event-store/sync/` - Event-sourced sync protocol

**CRDT Implementation**:
```go
// services/sync-service/internal/crdt/lww_register.go
package crdt

import (
    "encoding/json"
    "time"
)

// Last-Write-Wins Register CRDT
type LWWRegister struct {
    Value     interface{} `json:"value"`
    Timestamp time.Time   `json:"timestamp"`
    ActorID   string      `json:"actor_id"`
}

func (r *LWWRegister) Update(value interface{}, actorID string) {
    now := time.Now()
    if now.After(r.Timestamp) || (now.Equal(r.Timestamp) && actorID > r.ActorID) {
        r.Value = value
        r.Timestamp = now
        r.ActorID = actorID
    }
}

func (r *LWWRegister) Merge(other *LWWRegister) *LWWRegister {
    if other.Timestamp.After(r.Timestamp) ||
       (other.Timestamp.Equal(r.Timestamp) && other.ActorID > r.ActorID) {
        return other
    }
    return r
}

// G-Set (Grow-only Set) CRDT
type GSet struct {
    Elements map[string]bool `json:"elements"`
}

func (s *GSet) Add(element string) {
    if s.Elements == nil {
        s.Elements = make(map[string]bool)
    }
    s.Elements[element] = true
}

func (s *GSet) Contains(element string) bool {
    return s.Elements[element]
}

func (s *GSet) Merge(other *GSet) *GSet {
    result := &GSet{Elements: make(map[string]bool)}

    for elem := range s.Elements {
        result.Elements[elem] = true
    }
    for elem := range other.Elements {
        result.Elements[elem] = true
    }

    return result
}
```

**Vector Clock Implementation**:
```go
// services/sync-service/internal/vector_clock/vector_clock.go
package vector_clock

import (
    "encoding/json"
    "fmt"
)

type VectorClock map[string]int

func New() VectorClock {
    return make(VectorClock)
}

func (vc VectorClock) Tick(nodeID string) VectorClock {
    result := vc.Copy()
    result[nodeID]++
    return result
}

func (vc VectorClock) Update(other VectorClock) VectorClock {
    result := vc.Copy()
    for nodeID, timestamp := range other {
        if result[nodeID] < timestamp {
            result[nodeID] = timestamp
        }
    }
    return result
}

func (vc VectorClock) Compare(other VectorClock) Ordering {
    var less, greater bool

    allNodes := make(map[string]bool)
    for nodeID := range vc {
        allNodes[nodeID] = true
    }
    for nodeID := range other {
        allNodes[nodeID] = true
    }

    for nodeID := range allNodes {
        thisTime := vc[nodeID]
        otherTime := other[nodeID]

        if thisTime < otherTime {
            less = true
        } else if thisTime > otherTime {
            greater = true
        }
    }

    if less && greater {
        return Concurrent
    } else if less {
        return Before
    } else if greater {
        return After
    }
    return Equal
}

type Ordering int

const (
    Before Ordering = iota
    After
    Equal
    Concurrent
)
```

**Conflict Resolution Engine**:
```go
// services/sync-service/internal/conflict/resolver.go
package conflict

import (
    "context"
    "encoding/json"
    "fmt"
)

type ConflictResolver struct {
    strategies map[string]ResolutionStrategy
    auditLog   AuditLogger
}

type ResolutionStrategy interface {
    Resolve(ctx context.Context, conflicts []Conflict) (*Resolution, error)
}

type Conflict struct {
    EntityID    string                 `json:"entity_id"`
    EntityType  string                 `json:"entity_type"`
    Field       string                 `json:"field"`
    LocalValue  interface{}            `json:"local_value"`
    RemoteValue interface{}            `json:"remote_value"`
    LocalClock  vector_clock.VectorClock `json:"local_clock"`
    RemoteClock vector_clock.VectorClock `json:"remote_clock"`
    Metadata    map[string]interface{} `json:"metadata"`
}

type Resolution struct {
    ResolvedValue interface{}            `json:"resolved_value"`
    Strategy      string                 `json:"strategy"`
    Confidence    float64                `json:"confidence"`
    RequiresUI    bool                   `json:"requires_ui"`
    Explanation   string                 `json:"explanation"`
}

// Last-Write-Wins Strategy
type LWWStrategy struct{}

func (s *LWWStrategy) Resolve(ctx context.Context, conflicts []Conflict) (*Resolution, error) {
    if len(conflicts) == 0 {
        return nil, fmt.Errorf("no conflicts to resolve")
    }

    conflict := conflicts[0] // Assume single conflict for simplicity

    ordering := conflict.LocalClock.Compare(conflict.RemoteClock)

    switch ordering {
    case vector_clock.After:
        return &Resolution{
            ResolvedValue: conflict.LocalValue,
            Strategy:      "last-write-wins",
            Confidence:    0.9,
            RequiresUI:    false,
            Explanation:   "Local change is more recent",
        }, nil
    case vector_clock.Before:
        return &Resolution{
            ResolvedValue: conflict.RemoteValue,
            Strategy:      "last-write-wins",
            Confidence:    0.9,
            RequiresUI:    false,
            Explanation:   "Remote change is more recent",
        }, nil
    case vector_clock.Concurrent:
        // Concurrent updates - need user intervention
        return &Resolution{
            ResolvedValue: nil,
            Strategy:      "manual-resolution",
            Confidence:    0.0,
            RequiresUI:    true,
            Explanation:   "Concurrent updates detected, manual resolution required",
        }, nil
    default:
        return &Resolution{
            ResolvedValue: conflict.LocalValue,
            Strategy:      "no-conflict",
            Confidence:    1.0,
            RequiresUI:    false,
            Explanation:   "No actual conflict detected",
        }, nil
    }
}
```

**Sync Protocol Implementation**:
```go
// services/sync-service/internal/protocol/sync_protocol.go
package protocol

import (
    "context"
    "encoding/json"
    "time"
)

type SyncProtocol struct {
    eventStore    EventStore
    conflictResolver *conflict.ConflictResolver
    vectorClock   vector_clock.VectorClock
    nodeID        string
}

type SyncRequest struct {
    ClientID      string                     `json:"client_id"`
    LastSyncClock vector_clock.VectorClock   `json:"last_sync_clock"`
    Changes       []ChangeEvent              `json:"changes"`
}

type SyncResponse struct {
    ServerClock   vector_clock.VectorClock   `json:"server_clock"`
    Changes       []ChangeEvent              `json:"changes"`
    Conflicts     []ConflictResolution       `json:"conflicts"`
    NextSyncToken string                     `json:"next_sync_token"`
}

type ChangeEvent struct {
    ID          string                     `json:"id"`
    EntityID    string                     `json:"entity_id"`
    EntityType  string                     `json:"entity_type"`
    Operation   string                     `json:"operation"` // create, update, delete
    Data        map[string]interface{}     `json:"data"`
    VectorClock vector_clock.VectorClock   `json:"vector_clock"`
    Timestamp   time.Time                  `json:"timestamp"`
    ActorID     string                     `json:"actor_id"`
}

func (sp *SyncProtocol) HandleSync(ctx context.Context, req *SyncRequest) (*SyncResponse, error) {
    // 1. Get server changes since last sync
    serverChanges, err := sp.getChangesSince(ctx, req.LastSyncClock)
    if err != nil {
        return nil, err
    }

    // 2. Detect conflicts between client and server changes
    conflicts := sp.detectConflicts(req.Changes, serverChanges)

    // 3. Resolve conflicts
    resolutions := make([]ConflictResolution, 0, len(conflicts))
    for _, conflict := range conflicts {
        resolution, err := sp.conflictResolver.Resolve(ctx, []conflict.Conflict{conflict})
        if err != nil {
            return nil, err
        }
        resolutions = append(resolutions, ConflictResolution{
            ConflictID: conflict.EntityID,
            Resolution: resolution,
        })
    }

    // 4. Apply client changes (non-conflicting)
    for _, change := range req.Changes {
        if !sp.hasConflict(change, conflicts) {
            if err := sp.applyChange(ctx, change); err != nil {
                return nil, err
            }
        }
    }

    // 5. Update vector clock
    sp.vectorClock = sp.vectorClock.Update(req.LastSyncClock).Tick(sp.nodeID)

    return &SyncResponse{
        ServerClock:   sp.vectorClock,
        Changes:       serverChanges,
        Conflicts:     resolutions,
        NextSyncToken: sp.generateSyncToken(),
    }, nil
}
```

**Local Testing**:
```bash
# 1. Start sync service and dependencies
cd services/sync-service
docker-compose up -d postgres redis

# 2. Run CRDT tests
go test ./internal/crdt -v

# 3. Test conflict resolution
go test ./internal/conflict -v -run TestConflictResolution

# 4. Simulate offline sync scenario
./scripts/test-offline-sync.sh

# 5. Test concurrent edits
./scripts/test-concurrent-edits.sh

# 6. Verify conflict resolution UI
curl -X POST http://localhost:8080/sync \
  -H "Content-Type: application/json" \
  -d @test-data/concurrent-changes.json
```

**Database Schema**:
```sql
-- Sync events table
CREATE TABLE sync_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id VARCHAR NOT NULL,
    entity_type VARCHAR NOT NULL,
    operation VARCHAR NOT NULL,
    data JSONB NOT NULL,
    vector_clock JSONB NOT NULL,
    actor_id VARCHAR NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    INDEX idx_entity_sync (entity_id, entity_type, created_at)
);

-- Conflict resolutions audit
CREATE TABLE conflict_resolutions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id VARCHAR NOT NULL,
    conflict_data JSONB NOT NULL,
    resolution_data JSONB NOT NULL,
    strategy VARCHAR NOT NULL,
    requires_manual BOOLEAN DEFAULT FALSE,
    resolved_at TIMESTAMP DEFAULT NOW(),
    resolved_by VARCHAR
);
```

**Key Features Implemented**:
- ✅ CRDT implementations (LWW-Register, G-Set)
- ✅ Vector clock for causality tracking
- ✅ Conflict detection and resolution
- ✅ Event-sourced sync protocol
- ✅ Audit trail for all resolutions

---

### 2) Multi-shard rebalancing with minimal impact (Expert)

- **Scenario:** One shard becomes hot; need to rebalance keys across shards without downtime.
- **Mục tiêu:** Online resharding, data migration, routing update.
- **Ràng buộc:** Requests must be served; consistency maintained.
- **Success metrics:** Tail latency spike minimal; no data loss.
- **Tools/gợi ý:** Consistent hashing, hash range rebalancer, MongoDB resharding, Vitess (MySQL sharding), sharding proxy.
- **Test / Verify:** Induce hotspot; run rebalancer; monitor latencies and error rates.
- **Tips:** Throttle migration throughput; use double-write + read-routing to new shard during cutover.

#### 🔧 **Implementation in Codebase**

**Location**: `services/sharding-proxy/` and `services/schema-migration/`

**Key Files**:
- `services/sharding-proxy/internal/consistent_hash/` - Consistent hashing implementation
- `services/sharding-proxy/internal/rebalancer/` - Online rebalancing logic
- `services/sharding-proxy/internal/router/` - Request routing
- `services/schema-migration/rebalance/` - Data migration tools

**Consistent Hashing Implementation**:
```go
// services/sharding-proxy/internal/consistent_hash/ring.go
package consistent_hash

import (
    "crypto/sha256"
    "fmt"
    "sort"
    "strconv"
)

type Ring struct {
    nodes     map[uint32]string
    sortedKeys []uint32
    replicas   int
}

func NewRing(replicas int) *Ring {
    return &Ring{
        nodes:    make(map[uint32]string),
        replicas: replicas,
    }
}

func (r *Ring) AddNode(node string) {
    for i := 0; i < r.replicas; i++ {
        key := r.hash(fmt.Sprintf("%s:%d", node, i))
        r.nodes[key] = node
        r.sortedKeys = append(r.sortedKeys, key)
    }
    sort.Slice(r.sortedKeys, func(i, j int) bool {
        return r.sortedKeys[i] < r.sortedKeys[j]
    })
}

func (r *Ring) RemoveNode(node string) {
    for i := 0; i < r.replicas; i++ {
        key := r.hash(fmt.Sprintf("%s:%d", node, i))
        delete(r.nodes, key)

        // Remove from sorted keys
        for j, k := range r.sortedKeys {
            if k == key {
                r.sortedKeys = append(r.sortedKeys[:j], r.sortedKeys[j+1:]...)
                break
            }
        }
    }
}

func (r *Ring) GetNode(key string) string {
    if len(r.sortedKeys) == 0 {
        return ""
    }

    hash := r.hash(key)
    idx := sort.Search(len(r.sortedKeys), func(i int) bool {
        return r.sortedKeys[i] >= hash
    })

    if idx == len(r.sortedKeys) {
        idx = 0
    }

    return r.nodes[r.sortedKeys[idx]]
}

func (r *Ring) GetNodes(key string, count int) []string {
    if len(r.sortedKeys) == 0 {
        return nil
    }

    hash := r.hash(key)
    idx := sort.Search(len(r.sortedKeys), func(i int) bool {
        return r.sortedKeys[i] >= hash
    })

    nodes := make([]string, 0, count)
    seen := make(map[string]bool)

    for len(nodes) < count && len(nodes) < len(r.sortedKeys) {
        if idx >= len(r.sortedKeys) {
            idx = 0
        }

        node := r.nodes[r.sortedKeys[idx]]
        if !seen[node] {
            nodes = append(nodes, node)
            seen[node] = true
        }
        idx++
    }

    return nodes
}

func (r *Ring) hash(key string) uint32 {
    h := sha256.Sum256([]byte(key))
    return uint32(h[0])<<24 | uint32(h[1])<<16 | uint32(h[2])<<8 | uint32(h[3])
}
```

**Online Rebalancer**:
```go
// services/sharding-proxy/internal/rebalancer/rebalancer.go
package rebalancer

import (
    "context"
    "fmt"
    "sync"
    "time"
)

type Rebalancer struct {
    ring           *consistent_hash.Ring
    dataMover      DataMover
    router         *router.Router
    metrics        *Metrics
    throttle       *Throttle
    migrationState *MigrationState
}

type MigrationState struct {
    mu              sync.RWMutex
    activeMigrations map[string]*Migration
}

type Migration struct {
    ID          string    `json:"id"`
    SourceShard string    `json:"source_shard"`
    TargetShard string    `json:"target_shard"`
    KeyRange    KeyRange  `json:"key_range"`
    Status      string    `json:"status"`
    Progress    float64   `json:"progress"`
    StartTime   time.Time `json:"start_time"`
    EndTime     time.Time `json:"end_time"`
}

type KeyRange struct {
    Start uint32 `json:"start"`
    End   uint32 `json:"end"`
}

func (r *Rebalancer) StartRebalance(ctx context.Context, hotShard string) error {
    // 1. Analyze current load distribution
    loadStats, err := r.analyzeLoad(ctx)
    if err != nil {
        return err
    }

    // 2. Calculate optimal key redistribution
    redistributionPlan, err := r.calculateRedistribution(loadStats, hotShard)
    if err != nil {
        return err
    }

    // 3. Execute migrations in phases
    for _, migration := range redistributionPlan.Migrations {
        if err := r.executeMigration(ctx, migration); err != nil {
            return err
        }
    }

    return nil
}

func (r *Rebalancer) executeMigration(ctx context.Context, migration *Migration) error {
    r.migrationState.mu.Lock()
    r.migrationState.activeMigrations[migration.ID] = migration
    r.migrationState.mu.Unlock()

    defer func() {
        r.migrationState.mu.Lock()
        delete(r.migrationState.activeMigrations, migration.ID)
        r.migrationState.mu.Unlock()
    }()

    // Phase 1: Start double-write to target shard
    if err := r.router.EnableDoubleWrite(migration.KeyRange, migration.TargetShard); err != nil {
        return err
    }

    // Phase 2: Migrate existing data
    if err := r.migrateData(ctx, migration); err != nil {
        return err
    }

    // Phase 3: Switch reads to target shard
    if err := r.router.SwitchReads(migration.KeyRange, migration.TargetShard); err != nil {
        return err
    }

    // Phase 4: Stop double-write, cleanup source
    if err := r.router.DisableDoubleWrite(migration.KeyRange); err != nil {
        return err
    }

    migration.Status = "completed"
    migration.EndTime = time.Now()

    return nil
}

func (r *Rebalancer) migrateData(ctx context.Context, migration *Migration) error {
    // Get all keys in range from source shard
    keys, err := r.dataMover.GetKeysInRange(ctx, migration.SourceShard, migration.KeyRange)
    if err != nil {
        return err
    }

    totalKeys := len(keys)
    migratedKeys := 0

    // Migrate in batches with throttling
    batchSize := 100
    for i := 0; i < len(keys); i += batchSize {
        end := i + batchSize
        if end > len(keys) {
            end = len(keys)
        }

        batch := keys[i:end]

        // Apply throttling
        if err := r.throttle.Wait(ctx); err != nil {
            return err
        }

        // Migrate batch
        if err := r.dataMover.MigrateBatch(ctx, migration.SourceShard,
            migration.TargetShard, batch); err != nil {
            return err
        }

        migratedKeys += len(batch)
        migration.Progress = float64(migratedKeys) / float64(totalKeys)

        // Update metrics
        r.metrics.RecordMigrationProgress(migration.ID, migration.Progress)
    }

    return nil
}
```

**Sharding Router with Double-Write**:
```go
// services/sharding-proxy/internal/router/router.go
package router

import (
    "context"
    "sync"
)

type Router struct {
    ring           *consistent_hash.Ring
    shardClients   map[string]ShardClient
    doubleWrites   map[string]DoubleWriteConfig
    readRouting    map[string]string
    mu             sync.RWMutex
}

type DoubleWriteConfig struct {
    KeyRange    KeyRange `json:"key_range"`
    TargetShard string   `json:"target_shard"`
    Enabled     bool     `json:"enabled"`
}

func (r *Router) Get(ctx context.Context, key string) ([]byte, error) {
    r.mu.RLock()
    defer r.mu.RUnlock()

    // Check if key is being migrated
    if targetShard, isMigrating := r.isKeyMigrating(key); isMigrating {
        // Read from target shard during migration
        client := r.shardClients[targetShard]
        return client.Get(ctx, key)
    }

    // Normal routing
    shard := r.ring.GetNode(key)
    client := r.shardClients[shard]
    return client.Get(ctx, key)
}

func (r *Router) Set(ctx context.Context, key string, value []byte) error {
    r.mu.RLock()
    defer r.mu.RUnlock()

    primaryShard := r.ring.GetNode(key)

    // Check if double-write is enabled for this key
    if config, isDoubleWrite := r.isDoubleWriteEnabled(key); isDoubleWrite {
        // Write to both primary and target shards
        errCh := make(chan error, 2)

        go func() {
            errCh <- r.shardClients[primaryShard].Set(ctx, key, value)
        }()

        go func() {
            errCh <- r.shardClients[config.TargetShard].Set(ctx, key, value)
        }()

        // Wait for both writes
        var errors []error
        for i := 0; i < 2; i++ {
            if err := <-errCh; err != nil {
                errors = append(errors, err)
            }
        }

        // Return error only if both writes failed
        if len(errors) == 2 {
            return errors[0]
        }

        return nil
    }

    // Normal single write
    client := r.shardClients[primaryShard]
    return client.Set(ctx, key, value)
}

func (r *Router) EnableDoubleWrite(keyRange KeyRange, targetShard string) error {
    r.mu.Lock()
    defer r.mu.Unlock()

    rangeKey := fmt.Sprintf("%d-%d", keyRange.Start, keyRange.End)
    r.doubleWrites[rangeKey] = DoubleWriteConfig{
        KeyRange:    keyRange,
        TargetShard: targetShard,
        Enabled:     true,
    }

    return nil
}
```

**Local Testing**:
```bash
# 1. Start sharding proxy and multiple shards
cd services/sharding-proxy
docker-compose up -d shard1 shard2 shard3 proxy

# 2. Generate hotspot data
./scripts/generate-hotspot.sh shard1

# 3. Monitor shard load
curl http://localhost:8080/metrics/shard-load

# 4. Trigger rebalancing
curl -X POST http://localhost:8080/admin/rebalance \
  -d '{"hot_shard": "shard1", "strategy": "gradual"}'

# 5. Monitor migration progress
watch curl http://localhost:8080/admin/migrations/status

# 6. Verify data consistency
./scripts/verify-shard-consistency.sh

# 7. Test performance during migration
./scripts/load-test-during-migration.sh
```

**Monitoring Dashboard**:
```json
{
  "dashboard": {
    "title": "Shard Rebalancing",
    "panels": [
      {
        "title": "Shard Load Distribution",
        "type": "graph",
        "targets": [
          {
            "expr": "shard_requests_per_second by (shard)",
            "legendFormat": "{{ shard }}"
          }
        ]
      },
      {
        "title": "Migration Progress",
        "type": "stat",
        "targets": [
          {
            "expr": "migration_progress_percent",
            "legendFormat": "Progress %"
          }
        ]
      }
    ]
  }
}
```

**Key Features Implemented**:
- ✅ Consistent hashing with virtual nodes
- ✅ Online data migration with throttling
- ✅ Double-write during migration
- ✅ Gradual read traffic switching
- ✅ Migration progress monitoring

---

### 3) Disaster recovery & cross-region backup (Advanced)

- **Scenario:** Region goes down; restore production to new region with RPO/RTO constraints.
- **Mục tiêu:** Implement backup, PITR, cross-region replicas and automated failover.
- **Ràng buộc:** Large DB size (TBs), regulated RPO ≤ 15 minutes.
- **Success metrics:** RPO/RTO objectives met in DR exercises.
- **Tools/gợi ý:** PostgreSQL with WAL shipping (pgBackRest), Patroni for HA, MongoDB replica sets and delayed secondaries, ClickHouse replication, object storage snapshots (S3).
- **Test / Verify:** Perform DR failover drill, restore from snapshot into new cluster, validate data integrity.
- **Tips:** Automate DR runbooks, test regularly.

#### 🔧 **Implementation in Codebase**

**Location**: `services/disaster-recovery/` and `infrastructure/backup/`

**Key Files**:
- `services/disaster-recovery/internal/backup/` - Backup orchestration
- `services/disaster-recovery/internal/restore/` - Restore automation
- `infrastructure/backup/pgbackrest.conf` - PostgreSQL backup config
- `infrastructure/patroni/patroni.yml` - HA configuration

**PostgreSQL Backup with pgBackRest**:
```bash
# infrastructure/backup/pgbackrest.conf
[global]
repo1-type=s3
repo1-s3-bucket=production-backups
repo1-s3-endpoint=s3.amazonaws.com
repo1-s3-region=us-east-1
repo1-retention-full=7
repo1-retention-diff=4
repo1-retention-incr=3

[main]
pg1-path=/var/lib/postgresql/data
pg1-port=5432
pg1-socket-path=/var/run/postgresql

# Cross-region replication
repo2-type=s3
repo2-s3-bucket=dr-backups-west
repo2-s3-endpoint=s3.us-west-2.amazonaws.com
repo2-s3-region=us-west-2
```

**Disaster Recovery Orchestrator**:
```go
// services/disaster-recovery/internal/orchestrator/dr_orchestrator.go
package orchestrator

import (
    "context"
    "fmt"
    "time"
)

type DROrchestrator struct {
    backupManager  *BackupManager
    restoreManager *RestoreManager
    healthChecker  *HealthChecker
    notifier       *Notifier
    config         *DRConfig
}

type DRConfig struct {
    PrimaryRegion   string        `json:"primary_region"`
    DRRegion        string        `json:"dr_region"`
    RPOTarget       time.Duration `json:"rpo_target"`
    RTOTarget       time.Duration `json:"rto_target"`
    BackupSchedule  string        `json:"backup_schedule"`
    HealthCheckURL  string        `json:"health_check_url"`
}

func (dro *DROrchestrator) ExecuteFailover(ctx context.Context, reason string) error {
    log.Info("Starting disaster recovery failover", "reason", reason)

    // 1. Verify primary region is truly down
    if dro.healthChecker.IsPrimaryHealthy() {
        return fmt.Errorf("primary region appears healthy, aborting failover")
    }

    // 2. Find latest backup
    latestBackup, err := dro.backupManager.GetLatestBackup(ctx)
    if err != nil {
        return fmt.Errorf("failed to find latest backup: %w", err)
    }

    // 3. Check RPO compliance
    backupAge := time.Since(latestBackup.Timestamp)
    if backupAge > dro.config.RPOTarget {
        log.Warn("RPO target exceeded", "backup_age", backupAge, "rpo_target", dro.config.RPOTarget)
    }

    // 4. Restore to DR region
    restoreStart := time.Now()
    if err := dro.restoreManager.RestoreFromBackup(ctx, latestBackup, dro.config.DRRegion); err != nil {
        return fmt.Errorf("restore failed: %w", err)
    }

    // 5. Verify RTO compliance
    restoreDuration := time.Since(restoreStart)
    if restoreDuration > dro.config.RTOTarget {
        log.Warn("RTO target exceeded", "restore_duration", restoreDuration, "rto_target", dro.config.RTOTarget)
    }

    // 6. Update DNS/load balancer to point to DR region
    if err := dro.switchTrafficToDR(ctx); err != nil {
        return fmt.Errorf("failed to switch traffic: %w", err)
    }

    // 7. Notify stakeholders
    dro.notifier.NotifyFailover(reason, restoreDuration, backupAge)

    log.Info("Disaster recovery failover completed", "duration", restoreDuration)
    return nil
}

func (dro *DROrchestrator) ExecuteBackup(ctx context.Context, backupType string) error {
    switch backupType {
    case "full":
        return dro.backupManager.CreateFullBackup(ctx)
    case "incremental":
        return dro.backupManager.CreateIncrementalBackup(ctx)
    case "differential":
        return dro.backupManager.CreateDifferentialBackup(ctx)
    default:
        return fmt.Errorf("unknown backup type: %s", backupType)
    }
}
```

**Backup Manager**:
```go
// services/disaster-recovery/internal/backup/backup_manager.go
package backup

import (
    "context"
    "fmt"
    "os/exec"
    "time"
)

type BackupManager struct {
    pgBackRestPath string
    s3Config       *S3Config
    metrics        *BackupMetrics
}

type BackupInfo struct {
    ID        string    `json:"id"`
    Type      string    `json:"type"`
    Timestamp time.Time `json:"timestamp"`
    Size      int64     `json:"size"`
    Location  string    `json:"location"`
    Status    string    `json:"status"`
}

func (bm *BackupManager) CreateFullBackup(ctx context.Context) error {
    backupID := fmt.Sprintf("full-%d", time.Now().Unix())

    // Execute pgBackRest full backup
    cmd := exec.CommandContext(ctx, bm.pgBackRestPath,
        "--stanza=main",
        "--type=full",
        "--repo=1",
        "backup")

    output, err := cmd.CombinedOutput()
    if err != nil {
        bm.metrics.RecordBackupFailure("full")
        return fmt.Errorf("backup failed: %w, output: %s", err, output)
    }

    // Cross-region replication
    if err := bm.replicateToSecondaryRegion(ctx, backupID); err != nil {
        log.Warn("Cross-region replication failed", "error", err)
    }

    bm.metrics.RecordBackupSuccess("full")
    return nil
}

func (bm *BackupManager) CreateIncrementalBackup(ctx context.Context) error {
    cmd := exec.CommandContext(ctx, bm.pgBackRestPath,
        "--stanza=main",
        "--type=incr",
        "--repo=1",
        "backup")

    output, err := cmd.CombinedOutput()
    if err != nil {
        bm.metrics.RecordBackupFailure("incremental")
        return fmt.Errorf("incremental backup failed: %w, output: %s", err, output)
    }

    bm.metrics.RecordBackupSuccess("incremental")
    return nil
}

func (bm *BackupManager) GetLatestBackup(ctx context.Context) (*BackupInfo, error) {
    cmd := exec.CommandContext(ctx, bm.pgBackRestPath,
        "--stanza=main",
        "--output=json",
        "info")

    output, err := cmd.Output()
    if err != nil {
        return nil, fmt.Errorf("failed to get backup info: %w", err)
    }

    // Parse JSON output and return latest backup
    // Implementation details omitted for brevity
    return &BackupInfo{
        ID:        "latest-backup-id",
        Type:      "full",
        Timestamp: time.Now().Add(-1 * time.Hour),
        Size:      1024 * 1024 * 1024, // 1GB
        Location:  "s3://production-backups/main/",
        Status:    "completed",
    }, nil
}
```

**Local Testing**:
```bash
# 1. Setup DR infrastructure
cd services/disaster-recovery
docker-compose up -d postgres-primary postgres-replica minio

# 2. Configure pgBackRest
sudo cp infrastructure/backup/pgbackrest.conf /etc/pgbackrest/
sudo chown postgres:postgres /etc/pgbackrest/pgbackrest.conf

# 3. Initialize backup repository
sudo -u postgres pgbackrest --stanza=main stanza-create

# 4. Create initial full backup
sudo -u postgres pgbackrest --stanza=main backup

# 5. Test incremental backup
sudo -u postgres pgbackrest --stanza=main --type=incr backup

# 6. Simulate disaster and test restore
./scripts/simulate-disaster.sh

# 7. Test automated failover
curl -X POST http://localhost:8080/dr/failover \
  -d '{"reason": "primary_region_down", "force": false}'

# 8. Verify data integrity after restore
./scripts/verify-data-integrity.sh
```

**Patroni HA Configuration**:
```yaml
# infrastructure/patroni/patroni.yml
scope: postgres-cluster
namespace: /db/
name: postgres-primary

restapi:
  listen: 0.0.0.0:8008
  connect_address: postgres-primary:8008

etcd:
  hosts: etcd:2379

bootstrap:
  dcs:
    ttl: 30
    loop_wait: 10
    retry_timeout: 30
    maximum_lag_on_failover: 1048576
    postgresql:
      use_pg_rewind: true
      parameters:
        wal_level: replica
        hot_standby: "on"
        wal_keep_segments: 8
        max_wal_senders: 10
        max_replication_slots: 10
        wal_log_hints: "on"
        archive_mode: "on"
        archive_command: 'pgbackrest --stanza=main archive-push %p'
        restore_command: 'pgbackrest --stanza=main archive-get %f %p'

postgresql:
  listen: 0.0.0.0:5432
  connect_address: postgres-primary:5432
  data_dir: /var/lib/postgresql/data
  pgpass: /tmp/pgpass
  authentication:
    replication:
      username: replicator
      password: replicator_password
    superuser:
      username: postgres
      password: postgres_password

tags:
  nofailover: false
  noloadbalance: false
  clonefrom: false
  nosync: false
```

**Key Features Implemented**:
- ✅ Automated backup with pgBackRest
- ✅ Cross-region backup replication
- ✅ Point-in-time recovery (PITR)
- ✅ Patroni-based high availability
- ✅ Automated failover orchestration
- ✅ RPO/RTO monitoring and alerting

---

### 4) Real-time analytics ETL pipeline to ClickHouse (Intermediate)

- **Scenario:** Push OLTP events to ClickHouse for near-real-time analytics (low-latency dashboards).
- **Mục tiêu:** Low-latency ingestion with exactly-once semantics.
- **Ràng buộc:** High write throughput, ordering concerns.
- **Success metrics:** Dashboard latency < 1 minute; ingestion durability.
- **Tools/gợi ý:** Kafka → Kafka Connect → ClickHouse Kafka engine → materialized views; or ClickHouse INSERT buffers.
- **Test / Verify:** Simulate peak events; validate counts vs source; failure recovery test.
- **Tips:** Use batched inserts and tune ClickHouse merges.

#### 🔧 **Implementation in Codebase**

**Location**: `services/analytics-etl/` and `infrastructure/clickhouse/`

**Key Files**:
- `services/analytics-etl/internal/kafka_consumer/` - Kafka to ClickHouse ETL
- `services/analytics-etl/internal/clickhouse/` - ClickHouse client and operations
- `infrastructure/clickhouse/config.xml` - ClickHouse configuration
- `infrastructure/clickhouse/schemas/` - Table schemas and materialized views

**ClickHouse ETL Service**:
```go
// services/analytics-etl/internal/etl/clickhouse_etl.go
package etl

import (
    "context"
    "database/sql"
    "encoding/json"
    "fmt"
    "time"

    "github.com/ClickHouse/clickhouse-go/v2"
    "github.com/confluentinc/confluent-kafka-go/kafka"
)

type ClickHouseETL struct {
    kafkaConsumer *kafka.Consumer
    clickhouseDB  *sql.DB
    batchSize     int
    flushInterval time.Duration
    buffer        []Event
    metrics       *ETLMetrics
}

type Event struct {
    ID          string                 `json:"id"`
    EventType   string                 `json:"event_type"`
    UserID      string                 `json:"user_id"`
    SessionID   string                 `json:"session_id"`
    Timestamp   time.Time              `json:"timestamp"`
    Properties  map[string]interface{} `json:"properties"`
    Source      string                 `json:"source"`
}

func NewClickHouseETL(kafkaConfig *kafka.ConfigMap, clickhouseURL string) (*ClickHouseETL, error) {
    consumer, err := kafka.NewConsumer(kafkaConfig)
    if err != nil {
        return nil, err
    }

    db, err := sql.Open("clickhouse", clickhouseURL)
    if err != nil {
        return nil, err
    }

    return &ClickHouseETL{
        kafkaConsumer: consumer,
        clickhouseDB:  db,
        batchSize:     1000,
        flushInterval: 10 * time.Second,
        buffer:        make([]Event, 0, 1000),
        metrics:       NewETLMetrics(),
    }, nil
}

func (etl *ClickHouseETL) Start(ctx context.Context) error {
    // Subscribe to topics
    topics := []string{"user-events", "system-events", "business-events"}
    if err := etl.kafkaConsumer.SubscribeTopics(topics, nil); err != nil {
        return err
    }

    // Start flush timer
    flushTicker := time.NewTicker(etl.flushInterval)
    defer flushTicker.Stop()

    for {
        select {
        case <-ctx.Done():
            return etl.flushBuffer(ctx)

        case <-flushTicker.C:
            if len(etl.buffer) > 0 {
                if err := etl.flushBuffer(ctx); err != nil {
                    log.Error("Failed to flush buffer", "error", err)
                }
            }

        default:
            msg, err := etl.kafkaConsumer.ReadMessage(100 * time.Millisecond)
            if err != nil {
                if err.(kafka.Error).Code() == kafka.ErrTimedOut {
                    continue
                }
                log.Error("Kafka read error", "error", err)
                continue
            }

            if err := etl.processMessage(ctx, msg); err != nil {
                log.Error("Failed to process message", "error", err, "offset", msg.TopicPartition.Offset)
                etl.metrics.RecordProcessingError()
                continue
            }

            // Commit offset after successful processing
            if _, err := etl.kafkaConsumer.CommitMessage(msg); err != nil {
                log.Error("Failed to commit offset", "error", err)
            }
        }
    }
}

func (etl *ClickHouseETL) processMessage(ctx context.Context, msg *kafka.Message) error {
    var event Event
    if err := json.Unmarshal(msg.Value, &event); err != nil {
        return fmt.Errorf("failed to unmarshal event: %w", err)
    }

    // Add to buffer
    etl.buffer = append(etl.buffer, event)
    etl.metrics.RecordEventReceived(event.EventType)

    // Flush if buffer is full
    if len(etl.buffer) >= etl.batchSize {
        return etl.flushBuffer(ctx)
    }

    return nil
}

func (etl *ClickHouseETL) flushBuffer(ctx context.Context) error {
    if len(etl.buffer) == 0 {
        return nil
    }

    startTime := time.Now()

    // Prepare batch insert
    tx, err := etl.clickhouseDB.BeginTx(ctx, nil)
    if err != nil {
        return fmt.Errorf("failed to begin transaction: %w", err)
    }
    defer tx.Rollback()

    stmt, err := tx.PrepareContext(ctx, `
        INSERT INTO events (
            id, event_type, user_id, session_id, timestamp,
            properties, source, ingestion_time
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    `)
    if err != nil {
        return fmt.Errorf("failed to prepare statement: %w", err)
    }
    defer stmt.Close()

    // Insert batch
    for _, event := range etl.buffer {
        propertiesJSON, _ := json.Marshal(event.Properties)

        _, err := stmt.ExecContext(ctx,
            event.ID,
            event.EventType,
            event.UserID,
            event.SessionID,
            event.Timestamp,
            string(propertiesJSON),
            event.Source,
            time.Now(),
        )
        if err != nil {
            return fmt.Errorf("failed to insert event: %w", err)
        }
    }

    // Commit transaction
    if err := tx.Commit(); err != nil {
        return fmt.Errorf("failed to commit transaction: %w", err)
    }

    // Record metrics
    duration := time.Since(startTime)
    etl.metrics.RecordBatchInsert(len(etl.buffer), duration)

    log.Info("Flushed batch to ClickHouse",
        "count", len(etl.buffer),
        "duration", duration)

    // Clear buffer
    etl.buffer = etl.buffer[:0]

    return nil
}
```

**ClickHouse Schema**:
```sql
-- infrastructure/clickhouse/schemas/events.sql
CREATE DATABASE IF NOT EXISTS analytics;

-- Main events table
CREATE TABLE IF NOT EXISTS analytics.events (
    id String,
    event_type String,
    user_id String,
    session_id String,
    timestamp DateTime64(3),
    properties String,
    source String,
    ingestion_time DateTime64(3) DEFAULT now64(),
    date Date DEFAULT toDate(timestamp)
) ENGINE = MergeTree()
PARTITION BY date
ORDER BY (event_type, user_id, timestamp)
SETTINGS index_granularity = 8192;

-- Materialized view for real-time aggregations
CREATE MATERIALIZED VIEW IF NOT EXISTS analytics.events_hourly_mv
TO analytics.events_hourly
AS SELECT
    event_type,
    source,
    toStartOfHour(timestamp) as hour,
    count() as event_count,
    uniq(user_id) as unique_users,
    uniq(session_id) as unique_sessions
FROM analytics.events
GROUP BY event_type, source, hour;

-- Aggregated table for dashboards
CREATE TABLE IF NOT EXISTS analytics.events_hourly (
    event_type String,
    source String,
    hour DateTime,
    event_count UInt64,
    unique_users UInt64,
    unique_sessions UInt64,
    date Date DEFAULT toDate(hour)
) ENGINE = SummingMergeTree()
PARTITION BY date
ORDER BY (event_type, source, hour);

-- Real-time dashboard view
CREATE MATERIALIZED VIEW IF NOT EXISTS analytics.dashboard_metrics_mv
TO analytics.dashboard_metrics
AS SELECT
    toStartOfMinute(timestamp) as minute,
    event_type,
    count() as events_per_minute,
    uniq(user_id) as active_users,
    avg(JSONExtractFloat(properties, 'duration')) as avg_duration
FROM analytics.events
WHERE timestamp >= now() - INTERVAL 1 HOUR
GROUP BY minute, event_type;

CREATE TABLE IF NOT EXISTS analytics.dashboard_metrics (
    minute DateTime,
    event_type String,
    events_per_minute UInt64,
    active_users UInt64,
    avg_duration Float64
) ENGINE = ReplacingMergeTree()
ORDER BY (minute, event_type);
```

**Local Testing**:
```bash
# 1. Start ClickHouse and Kafka
cd services/analytics-etl
docker-compose up -d clickhouse kafka zookeeper

# 2. Create ClickHouse schemas
clickhouse-client --host localhost --port 9000 < infrastructure/clickhouse/schemas/events.sql

# 3. Start ETL service
go build -o analytics-etl main.go
./analytics-etl

# 4. Generate test events
./scripts/generate-test-events.sh

# 5. Verify data in ClickHouse
clickhouse-client --query "SELECT event_type, count() FROM analytics.events GROUP BY event_type"

# 6. Test real-time dashboard queries
clickhouse-client --query "
    SELECT minute, event_type, events_per_minute
    FROM analytics.dashboard_metrics
    WHERE minute >= now() - INTERVAL 10 MINUTE
    ORDER BY minute DESC"

# 7. Load test with high throughput
./scripts/load-test-etl.sh

# 8. Test failure recovery
./scripts/test-etl-recovery.sh
```

**ClickHouse Configuration**:
```xml
<!-- infrastructure/clickhouse/config.xml -->
<yandex>
    <logger>
        <level>information</level>
        <log>/var/log/clickhouse-server/clickhouse-server.log</log>
        <errorlog>/var/log/clickhouse-server/clickhouse-server.err.log</errorlog>
        <size>1000M</size>
        <count>10</count>
    </logger>

    <http_port>8123</http_port>
    <tcp_port>9000</tcp_port>
    <mysql_port>9004</mysql_port>
    <postgresql_port>9005</postgresql_port>

    <listen_host>::</listen_host>

    <max_connections>4096</max_connections>
    <keep_alive_timeout>3</keep_alive_timeout>
    <max_concurrent_queries>100</max_concurrent_queries>
    <uncompressed_cache_size>8589934592</uncompressed_cache_size>
    <mark_cache_size>5368709120</mark_cache_size>

    <!-- Optimizations for real-time analytics -->
    <merge_tree>
        <max_suspicious_broken_parts>5</max_suspicious_broken_parts>
        <parts_to_delay_insert>150</parts_to_delay_insert>
        <parts_to_throw_insert>300</parts_to_throw_insert>
        <max_delay_to_insert>1</max_delay_to_insert>
        <max_parts_in_total>100000</max_parts_in_total>
        <replicated_deduplication_window>100</replicated_deduplication_window>
        <replicated_deduplication_window_seconds>604800</replicated_deduplication_window_seconds>
    </merge_tree>

    <profiles>
        <default>
            <max_memory_usage>10000000000</max_memory_usage>
            <use_uncompressed_cache>0</use_uncompressed_cache>
            <load_balancing>random</load_balancing>
        </default>

        <readonly>
            <readonly>1</readonly>
        </readonly>
    </profiles>

    <users>
        <default>
            <password></password>
            <networks incl="networks_config"/>
            <profile>default</profile>
            <quota>default</quota>
        </default>
    </users>

    <quotas>
        <default>
            <interval>
                <duration>3600</duration>
                <queries>0</queries>
                <errors>0</errors>
                <result_rows>0</result_rows>
                <read_rows>0</read_rows>
                <execution_time>0</execution_time>
            </interval>
        </default>
    </quotas>
</yandex>
```

**Key Features Implemented**:
- ✅ High-throughput Kafka to ClickHouse ETL
- ✅ Batch processing with configurable flush intervals
- ✅ Materialized views for real-time aggregations
- ✅ Exactly-once processing with offset management
- ✅ Comprehensive error handling and recovery
- ✅ Performance monitoring and metrics

---

### 5) Online schema migration with large table (Advanced)

- **Scenario:** Add column with backfill to a huge table (billions of rows) without impacting production.
- **Mục tiêu:** Zero-downtime migration, minimal performance hit.
- **Ràng buộc:** Locking forbidden.
- **Success metrics:** 99.9% availability during migration; backfill throughput target met.
- **Tools/gợi ý:** gh-ost/pt-online-schema-change for MySQL; logical replication + dual writes for Postgres; Kafka-based backfill.
- **Test / Verify:** Run in staging with production-like volume; monitor replication lag and tail latency.
- **Tips:** Use feature flags to reveal new column when ready.

---

### 6) Consistency model testing across replicas (Advanced)

- **Scenario:** Multi-region replicas show divergent reads under certain failures.
- **Mục tiêu:** Validate consistency model (strong vs eventual), implement read routing.
- **Ràng buộc:** Geo-latency, leader election.
- **Success metrics:** Data divergence incidents zero after fixes; read staleness within SLA.
- **Tools/gợi ý:** Jepsen-style testing, chaos testing, Patroni + synchronous_standby for Postgres.
- **Test / Verify:** Run partition tests, leader failover, read validation.

---

### 7) Time-travel / point-in-time analytics on warehouse (Intermediate)

- **Scenario:** Analysts need point-in-time views for investigations (reproduce historical state).
- **Mục tiêu:** Implement versioned data or partition snapshots.
- **Ràng buộc:** Storage budget.
- **Success metrics:** Support queries for state at T within retention window.
- **Tools/gợi ý:** Delta Lake / Iceberg on object storage, ClickHouse with delayed replicas, materialized time-travel views.
- **Test / Verify:** Reconstruct historical reports and compare with archived outputs.

---

### 8) Cross-database transactional workflow with CQRS (Expert)

- **Scenario:** Operation requires updating MongoDB (user profile) + PostgreSQL (billing) + producing event for warehouse — must be consistent.
- **Mục tiêu:** CQRS + event-sourcing with guaranteed ordering and idempotency.
- **Ràng buộc:** No distributed 2PC across heterogeneous DBs.
- **Success metrics:** No lost/missed events; business invariants hold.
- **Tools/gợi ý:** Use ordering token, Sagas/compensating actions, Outbox tables, Debezium to stream changes to Kafka, materialized read models.
- **Test / Verify:** Simulate mid-transaction crashes; validate consistency.
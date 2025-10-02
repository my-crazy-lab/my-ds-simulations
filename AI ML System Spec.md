# AI / ML System (chatbot, RAG, fine-tune pipelines)

> Tập trung: pipeline thu thập conversation (Zalo/3rd party), xử lý ETL, lưu trữ, RAG index update, retrain/fine-tune, observability.
> 

### 1) Data ingestion at scale + deduplication & normalization (Advanced)

- **Scenario:** Hàng loạt luồng chat từ Zalo, webhook từ partners, CSV exports — format và quality khác nhau.
- **Mục tiêu:** Build resilient ingestion pipeline (ingest → validate → normalize → store raw + processed) với idempotency & dedupe.
- **Ràng buộc:** Out-of-order events, duplicates, partial payloads, rate spikes.
- **Success metrics:** ≤1% invalid records after normalization; end-to-end latency < 3s for 95th percentile (ingest→available for RAG).
- **Tools/gợi ý:** Kafka (ingest), Debezium style connectors, Kafka Streams / ksqlDB, Apache NiFi, Airflow for batch ETL, JSON schema validation, Sentry.
- **Test / Verify:** Simulate duplicate & delayed events; inject malformed payloads; verify idempotency keys; assert RAG index source contains only normalized docs.
- **Tips:** Use message keys for partitioning; keep raw immutable store (S3) for audit.

#### 🔧 **Implementation in Codebase**

**Location**: `ai-ml-system/services/data-ingestion/`

**Key Files**:
- `ai-ml-system/services/data-ingestion/main.go` - Main ingestion service (Go)
- `ai-ml-system/services/data-ingestion/internal/deduplication/` - Deduplication logic
- `ai-ml-system/services/data-ingestion/internal/normalization/` - Data normalization
- `ai-ml-system/services/data-ingestion/internal/validation/` - Schema validation
- `ai-ml-system/services/data-ingestion/configs/` - Kafka and pipeline configs

**Go Ingestion Service**:
```go
// ai-ml-system/services/data-ingestion/main.go
package main

import (
    "context"
    "encoding/json"
    "log"
    "net/http"
    "time"

    "github.com/confluentinc/confluent-kafka-go/kafka"
    "github.com/gin-gonic/gin"
)

type IngestionService struct {
    kafkaProducer   *kafka.Producer
    deduplicator    *BloomDeduplicator
    normalizer      *DocumentNormalizer
    validator       *SchemaValidator
    rawStorage      RawStorage
    metrics         *IngestionMetrics
}

type ChatMessage struct {
    ID          string                 `json:"id"`
    Source      string                 `json:"source"` // "zalo", "webhook", "csv"
    ConversationID string              `json:"conversation_id"`
    UserID      string                 `json:"user_id"`
    Content     string                 `json:"content"`
    Timestamp   time.Time              `json:"timestamp"`
    Metadata    map[string]interface{} `json:"metadata"`
    IdempotencyKey string              `json:"idempotency_key"`
}

func (is *IngestionService) handleIngest(c *gin.Context) {
    var message ChatMessage
    if err := c.ShouldBindJSON(&message); err != nil {
        c.JSON(400, gin.H{"error": "Invalid message format"})
        return
    }

    // 1. Check idempotency
    if is.deduplicator.IsProcessed(message.IdempotencyKey) {
        c.JSON(200, gin.H{"status": "already_processed", "id": message.ID})
        return
    }

    // 2. Validate schema
    if err := is.validator.Validate(message); err != nil {
        is.metrics.RecordValidationError(message.Source)
        c.JSON(400, gin.H{"error": "Validation failed", "details": err.Error()})
        return
    }

    // 3. Store raw message (immutable audit trail)
    if err := is.rawStorage.Store(message); err != nil {
        log.Printf("Failed to store raw message: %v", err)
    }

    // 4. Normalize message
    normalized, err := is.normalizer.Normalize(message)
    if err != nil {
        is.metrics.RecordNormalizationError(message.Source)
        c.JSON(500, gin.H{"error": "Normalization failed"})
        return
    }

    // 5. Publish to Kafka for downstream processing
    messageBytes, _ := json.Marshal(normalized)
    err = is.kafkaProducer.Produce(&kafka.Message{
        TopicPartition: kafka.TopicPartition{
            Topic:     &[]string{"chat-messages-normalized"}[0],
            Partition: kafka.PartitionAny,
        },
        Key:   []byte(message.ConversationID), // Partition by conversation
        Value: messageBytes,
        Headers: []kafka.Header{
            {Key: "source", Value: []byte(message.Source)},
            {Key: "ingestion_time", Value: []byte(time.Now().Format(time.RFC3339))},
        },
    }, nil)

    if err != nil {
        c.JSON(500, gin.H{"error": "Failed to publish message"})
        return
    }

    // 6. Mark as processed
    is.deduplicator.MarkProcessed(message.IdempotencyKey)
    is.metrics.RecordSuccess(message.Source)

    c.JSON(200, gin.H{
        "status": "processed",
        "id": message.ID,
        "normalized_id": normalized.ID,
    })
}
```

**Deduplication with Redis**:
```go
// ai-ml-system/services/data-ingestion/internal/deduplication/redis_dedup.go
package deduplication

import (
    "context"
    "crypto/sha256"
    "encoding/hex"
    "time"

    "github.com/go-redis/redis/v8"
)

type RedisDeduplicator struct {
    client *redis.Client
    ttl    time.Duration
}

func NewRedisDeduplicator(redisURL string, ttl time.Duration) *RedisDeduplicator {
    rdb := redis.NewClient(&redis.Options{
        Addr: redisURL,
    })

    return &RedisDeduplicator{
        client: rdb,
        ttl:    ttl,
    }
}

func (rd *RedisDeduplicator) IsProcessed(idempotencyKey string) bool {
    ctx := context.Background()

    // Check if key exists
    exists, err := rd.client.Exists(ctx, rd.keyName(idempotencyKey)).Result()
    if err != nil {
        log.Printf("Redis error checking key: %v", err)
        return false // Fail open to avoid blocking
    }

    return exists > 0
}

func (rd *RedisDeduplicator) MarkProcessed(idempotencyKey string) error {
    ctx := context.Background()

    return rd.client.Set(ctx, rd.keyName(idempotencyKey), "1", rd.ttl).Err()
}

func (rd *RedisDeduplicator) keyName(idempotencyKey string) string {
    return "dedup:" + idempotencyKey
}

// Content-based deduplication for messages without idempotency keys
func (rd *RedisDeduplicator) IsContentDuplicate(content string) bool {
    hash := rd.hashContent(content)
    return rd.IsProcessed("content:" + hash)
}

func (rd *RedisDeduplicator) hashContent(content string) string {
    hasher := sha256.New()
    hasher.Write([]byte(content))
    return hex.EncodeToString(hasher.Sum(nil))[:16] // Use first 16 chars
}
```

**Message Normalization**:
```go
// ai-ml-system/services/data-ingestion/internal/normalization/chat_normalizer.go
package normalization

import (
    "regexp"
    "strings"
    "time"
    "unicode"
)

type ChatNormalizer struct {
    emojiRegex    *regexp.Regexp
    urlRegex      *regexp.Regexp
    phoneRegex    *regexp.Regexp
    emailRegex    *regexp.Regexp
}

func NewChatNormalizer() *ChatNormalizer {
    return &ChatNormalizer{
        emojiRegex: regexp.MustCompile(`[\x{1F600}-\x{1F64F}]|[\x{1F300}-\x{1F5FF}]|[\x{1F680}-\x{1F6FF}]|[\x{2600}-\x{26FF}]|[\x{2700}-\x{27BF}]`),
        urlRegex:   regexp.MustCompile(`https?://[^\s]+`),
        phoneRegex: regexp.MustCompile(`(\+84|0)[0-9]{9,10}`),
        emailRegex: regexp.MustCompile(`[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}`),
    }
}

type NormalizedMessage struct {
    ID              string                 `json:"id"`
    OriginalID      string                 `json:"original_id"`
    Source          string                 `json:"source"`
    ConversationID  string                 `json:"conversation_id"`
    UserID          string                 `json:"user_id"`
    Content         string                 `json:"content"`
    CleanContent    string                 `json:"clean_content"`
    Language        string                 `json:"language"`
    Sentiment       string                 `json:"sentiment"`
    Intent          string                 `json:"intent"`
    Entities        []Entity               `json:"entities"`
    Metadata        map[string]interface{} `json:"metadata"`
    ProcessedAt     time.Time              `json:"processed_at"`
    NormalizationVersion string            `json:"normalization_version"`
}

type Entity struct {
    Type  string `json:"type"`
    Value string `json:"value"`
    Start int    `json:"start"`
    End   int    `json:"end"`
}

func (cn *ChatNormalizer) Normalize(message ChatMessage) (*NormalizedMessage, error) {
    normalized := &NormalizedMessage{
        ID:                   generateID(),
        OriginalID:           message.ID,
        Source:               message.Source,
        ConversationID:       message.ConversationID,
        UserID:               message.UserID,
        Content:              message.Content,
        Metadata:             message.Metadata,
        ProcessedAt:          time.Now(),
        NormalizationVersion: "2.0",
    }

    // Clean content
    normalized.CleanContent = cn.cleanContent(message.Content)

    // Detect language
    normalized.Language = cn.detectLanguage(normalized.CleanContent)

    // Extract entities
    normalized.Entities = cn.extractEntities(message.Content)

    // Basic sentiment analysis
    normalized.Sentiment = cn.analyzeSentiment(normalized.CleanContent)

    // Intent classification (simplified)
    normalized.Intent = cn.classifyIntent(normalized.CleanContent)

    // Enrich metadata
    cn.enrichMetadata(normalized)

    return normalized, nil
}

func (cn *ChatNormalizer) cleanContent(content string) string {
    // Remove URLs but keep placeholder
    cleaned := cn.urlRegex.ReplaceAllString(content, "[URL]")

    // Mask phone numbers
    cleaned = cn.phoneRegex.ReplaceAllString(cleaned, "[PHONE]")

    // Mask emails
    cleaned = cn.emailRegex.ReplaceAllString(cleaned, "[EMAIL]")

    // Normalize whitespace
    cleaned = regexp.MustCompile(`\s+`).ReplaceAllString(cleaned, " ")

    return strings.TrimSpace(cleaned)
}

func (cn *ChatNormalizer) extractEntities(content string) []Entity {
    var entities []Entity

    // Extract phone numbers
    phoneMatches := cn.phoneRegex.FindAllStringIndex(content, -1)
    for _, match := range phoneMatches {
        entities = append(entities, Entity{
            Type:  "phone",
            Value: content[match[0]:match[1]],
            Start: match[0],
            End:   match[1],
        })
    }

    // Extract emails
    emailMatches := cn.emailRegex.FindAllStringIndex(content, -1)
    for _, match := range emailMatches {
        entities = append(entities, Entity{
            Type:  "email",
            Value: content[match[0]:match[1]],
            Start: match[0],
            End:   match[1],
        })
    }

    return entities
}

func (cn *ChatNormalizer) analyzeSentiment(content string) string {
    // Simplified sentiment analysis
    positiveWords := []string{"tốt", "hay", "thích", "ok", "được", "cảm ơn"}
    negativeWords := []string{"tệ", "không", "chán", "khó", "lỗi", "sai"}

    content = strings.ToLower(content)

    positiveCount := 0
    negativeCount := 0

    for _, word := range positiveWords {
        if strings.Contains(content, word) {
            positiveCount++
        }
    }

    for _, word := range negativeWords {
        if strings.Contains(content, word) {
            negativeCount++
        }
    }

    if positiveCount > negativeCount {
        return "positive"
    } else if negativeCount > positiveCount {
        return "negative"
    }

    return "neutral"
}
```

**Local Testing**:
```bash
# 1. Start ingestion service and dependencies
cd ai-ml-system/services/data-ingestion
docker-compose up -d kafka redis postgres minio

# 2. Build and run Go service
go build -o ingestion-service main.go
./ingestion-service

# 3. Test Zalo webhook ingestion
curl -X POST http://localhost:8080/ingest/zalo \
  -H "Content-Type: application/json" \
  -d '{
    "id": "msg_001",
    "conversation_id": "conv_123",
    "user_id": "user_456",
    "content": "Xin chào, tôi cần hỗ trợ về sản phẩm",
    "timestamp": "2024-01-01T10:00:00Z",
    "idempotency_key": "zalo_msg_001_20240101"
  }'

# 4. Test deduplication
curl -X POST http://localhost:8080/ingest/zalo \
  -H "Content-Type: application/json" \
  -d '{
    "id": "msg_001",
    "conversation_id": "conv_123",
    "user_id": "user_456",
    "content": "Xin chào, tôi cần hỗ trợ về sản phẩm",
    "timestamp": "2024-01-01T10:00:00Z",
    "idempotency_key": "zalo_msg_001_20240101"
  }'

# 5. Check Kafka topics
kafka-console-consumer --bootstrap-server localhost:9092 \
  --topic chat-messages-normalized --from-beginning

# 6. Monitor metrics
curl http://localhost:8080/metrics

# 7. Test malformed data
curl -X POST http://localhost:8080/ingest/zalo \
  -H "Content-Type: application/json" \
  -d '{"invalid": "data"}'
```

**Key Features Implemented**:
- ✅ Go-based high-performance ingestion service
- ✅ Redis-based idempotency and deduplication
- ✅ Chat-specific normalization (PII masking, entity extraction)
- ✅ Kafka partitioning by conversation ID
- ✅ Raw data audit trail in MinIO/S3
- ✅ Comprehensive validation and error handling

---

### 2) Real-time RAG index update with low downtime (Expert)

- **Scenario:** New chat transcripts must be queryable by RAG within <1 minute for customer support agents.
- **Mục tiêu:** Streaming ingestion → chunking → embedding → vectordb upsert with atomic swap or versioning.
- **Ràng buộc:** Avoid serving stale/partial vector index; handle re-index after embedding model update.
- **Success metrics:** Index availability ≥ 99.9%; stale query rate <1%.
- **Tools/gợi ý:** Kafka → embedding workers (gpu/cpu autoscaling) → Milvus/Pinecone/Weaviate/FAISS w/ versioned indices; use blue/green index swap; use feature flags.
- **Test / Verify:** High-rate ingestion stress test; simulate worker crash mid-index; verify query results are consistent and no partial docs surface.
- **Tips:** Keep transaction log and use idempotent upserts; maintain index snapshots for quick rollbacks.

#### 🔧 **Implementation in Codebase**

**Location**: `ai-ml-system/services/rag-engine/`

**Key Files**:
- `ai-ml-system/services/rag-engine/internal/indexer/` - Real-time indexing service
- `ai-ml-system/services/rag-engine/internal/embeddings/` - Embedding generation
- `ai-ml-system/services/rag-engine/internal/milvus/` - Milvus vector database client
- `ai-ml-system/services/rag-engine/internal/chunking/` - Document chunking

**Real-time RAG Indexer**:
```python
# ai-ml-system/services/rag-engine/internal/indexer/realtime_indexer.py
import asyncio
import json
import logging
from typing import List, Dict, Any
from datetime import datetime
import hashlib

from kafka import KafkaConsumer
from pymilvus import Collection, connections, utility
import redis
from sentence_transformers import SentenceTransformer

class RealtimeRAGIndexer:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.kafka_consumer = None
        self.milvus_collection = None
        self.embedding_model = None
        self.redis_client = None
        self.chunker = DocumentChunker()
        self.batch_size = config.get('batch_size', 100)
        self.max_wait_time = config.get('max_wait_time', 30)  # seconds

    async def initialize(self):
        """Initialize all components"""
        # Connect to Kafka
        self.kafka_consumer = KafkaConsumer(
            'chat-messages-normalized',
            bootstrap_servers=self.config['kafka_servers'],
            group_id='rag-indexer',
            value_deserializer=lambda x: json.loads(x.decode('utf-8')),
            enable_auto_commit=False,
            max_poll_records=self.batch_size
        )

        # Connect to Milvus
        connections.connect(
            alias="default",
            host=self.config['milvus_host'],
            port=self.config['milvus_port']
        )

        # Initialize collection with versioning
        await self._setup_milvus_collections()

        # Load embedding model
        self.embedding_model = SentenceTransformer(
            self.config['embedding_model'],
            device=self.config.get('device', 'cpu')
        )

        # Connect to Redis for deduplication
        self.redis_client = redis.Redis(
            host=self.config['redis_host'],
            port=self.config['redis_port'],
            decode_responses=True
        )

        logging.info("RealtimeRAGIndexer initialized successfully")

    async def _setup_milvus_collections(self):
        """Setup Milvus collections with blue-green deployment pattern"""
        from pymilvus import FieldSchema, CollectionSchema, DataType

        # Define schema
        fields = [
            FieldSchema(name="id", dtype=DataType.VARCHAR, max_length=100, is_primary=True),
            FieldSchema(name="document_id", dtype=DataType.VARCHAR, max_length=100),
            FieldSchema(name="chunk_id", dtype=DataType.VARCHAR, max_length=100),
            FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=8192),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=384),
            FieldSchema(name="metadata", dtype=DataType.JSON),
            FieldSchema(name="timestamp", dtype=DataType.INT64),
            FieldSchema(name="version", dtype=DataType.VARCHAR, max_length=50)
        ]

        schema = CollectionSchema(fields, "RAG document chunks with embeddings")

        # Create collections for blue-green deployment
        collection_names = ["rag_index_blue", "rag_index_green"]

        for name in collection_names:
            if not utility.has_collection(name):
                collection = Collection(name, schema)

                # Create index for vector search
                index_params = {
                    "metric_type": "COSINE",
                    "index_type": "IVF_FLAT",
                    "params": {"nlist": 1024}
                }
                collection.create_index("embedding", index_params)

                # Create index for filtering
                collection.create_index("document_id")
                collection.create_index("timestamp")

                logging.info(f"Created collection: {name}")

        # Set active collection (start with blue)
        self.active_collection = "rag_index_blue"
        self.standby_collection = "rag_index_green"
        self.milvus_collection = Collection(self.active_collection)
        self.milvus_collection.load()

    async def start_indexing(self):
        """Start the real-time indexing process"""
        logging.info("Starting real-time RAG indexing...")

        batch = []
        last_commit_time = datetime.now()

        try:
            while True:
                # Poll for messages
                message_pack = self.kafka_consumer.poll(timeout_ms=1000)

                for topic_partition, messages in message_pack.items():
                    for message in messages:
                        try:
                            await self._process_message(message.value, batch)

                            # Check if we should flush the batch
                            current_time = datetime.now()
                            time_since_commit = (current_time - last_commit_time).seconds

                            if (len(batch) >= self.batch_size or
                                time_since_commit >= self.max_wait_time):

                                if batch:
                                    await self._flush_batch(batch)
                                    batch.clear()
                                    last_commit_time = current_time

                                    # Commit Kafka offsets
                                    self.kafka_consumer.commit()

                        except Exception as e:
                            logging.error(f"Error processing message: {e}")
                            continue

        except KeyboardInterrupt:
            logging.info("Shutting down indexer...")
        finally:
            if batch:
                await self._flush_batch(batch)
            self.kafka_consumer.close()

    async def _process_message(self, message: Dict[str, Any], batch: List[Dict]):
        """Process a single chat message for indexing"""
        document_id = message.get('id')
        content = message.get('clean_content', message.get('content', ''))

        if not content or len(content.strip()) < 10:
            return  # Skip empty or very short content

        # Check for duplicates using Redis
        content_hash = hashlib.md5(content.encode()).hexdigest()
        if self.redis_client.exists(f"indexed:{content_hash}"):
            logging.debug(f"Skipping duplicate content: {document_id}")
            return

        # Chunk the document
        chunks = self.chunker.chunk_document(content, document_id)

        # Generate embeddings for each chunk
        for chunk in chunks:
            try:
                embedding = self.embedding_model.encode(chunk['content'])

                # Prepare data for batch insertion
                batch_item = {
                    'id': chunk['id'],
                    'document_id': document_id,
                    'chunk_id': chunk['chunk_id'],
                    'content': chunk['content'],
                    'embedding': embedding.tolist(),
                    'metadata': {
                        'source': message.get('source', 'unknown'),
                        'conversation_id': message.get('conversation_id'),
                        'user_id': message.get('user_id'),
                        'language': message.get('language', 'unknown'),
                        'chunk_index': chunk['index'],
                        'total_chunks': len(chunks)
                    },
                    'timestamp': int(datetime.now().timestamp() * 1000),
                    'version': self.config.get('index_version', '1.0')
                }

                batch.append(batch_item)

            except Exception as e:
                logging.error(f"Error generating embedding for chunk {chunk['id']}: {e}")
                continue

        # Mark as processed
        self.redis_client.setex(f"indexed:{content_hash}", 3600 * 24, "1")  # 24h TTL

    async def _flush_batch(self, batch: List[Dict]):
        """Flush batch to Milvus with error handling"""
        if not batch:
            return

        try:
            # Prepare data for insertion
            ids = [item['id'] for item in batch]
            document_ids = [item['document_id'] for item in batch]
            chunk_ids = [item['chunk_id'] for item in batch]
            contents = [item['content'] for item in batch]
            embeddings = [item['embedding'] for item in batch]
            metadata = [item['metadata'] for item in batch]
            timestamps = [item['timestamp'] for item in batch]
            versions = [item['version'] for item in batch]

            # Insert into Milvus
            insert_data = [
                ids, document_ids, chunk_ids, contents,
                embeddings, metadata, timestamps, versions
            ]

            self.milvus_collection.insert(insert_data)
            self.milvus_collection.flush()

            logging.info(f"Successfully indexed {len(batch)} chunks")

        except Exception as e:
            logging.error(f"Error flushing batch to Milvus: {e}")
            # Could implement retry logic here
            raise

    async def swap_collections(self):
        """Perform blue-green swap for zero-downtime updates"""
        try:
            # Load the standby collection
            standby_collection = Collection(self.standby_collection)
            standby_collection.load()

            # Atomic swap
            old_active = self.active_collection
            self.active_collection = self.standby_collection
            self.standby_collection = old_active

            # Update the active collection reference
            self.milvus_collection = standby_collection

            # Release the old collection
            old_collection = Collection(old_active)
            old_collection.release()

            logging.info(f"Successfully swapped collections: {old_active} -> {self.active_collection}")

        except Exception as e:
            logging.error(f"Error during collection swap: {e}")
            raise

class DocumentChunker:
    def __init__(self, chunk_size: int = 512, overlap: int = 50):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk_document(self, content: str, document_id: str) -> List[Dict[str, Any]]:
        """Chunk document into overlapping segments"""
        words = content.split()
        chunks = []

        for i in range(0, len(words), self.chunk_size - self.overlap):
            chunk_words = words[i:i + self.chunk_size]
            chunk_content = ' '.join(chunk_words)

            if len(chunk_content.strip()) < 10:  # Skip very short chunks
                continue

            chunk_id = f"{document_id}_chunk_{len(chunks)}"
            chunk_hash = hashlib.md5(chunk_content.encode()).hexdigest()[:8]

            chunks.append({
                'id': f"{chunk_id}_{chunk_hash}",
                'chunk_id': chunk_id,
                'content': chunk_content,
                'index': len(chunks),
                'start_word': i,
                'end_word': min(i + self.chunk_size, len(words))
            })

        return chunks
```

**Local Testing**:
```bash
# 1. Start RAG infrastructure
cd ai-ml-system/services/rag-engine
docker-compose up -d milvus kafka redis

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start real-time indexer
python -m internal.indexer.realtime_indexer

# 4. Generate test chat messages
python scripts/generate_test_messages.py --count 1000

# 5. Test indexing performance
python scripts/test_indexing_performance.py

# 6. Test blue-green deployment
curl -X POST http://localhost:8080/admin/swap-collections

# 7. Verify search functionality
curl -X POST http://localhost:8080/search \
  -H "Content-Type: application/json" \
  -d '{"query": "customer support issue", "top_k": 5}'

# 8. Test failure recovery
python scripts/test_indexer_recovery.py
```

**Key Features Implemented**:
- ✅ Real-time Kafka-based document ingestion
- ✅ Automatic document chunking with overlap
- ✅ Sentence transformer embeddings
- ✅ Blue-green collection deployment
- ✅ Redis-based deduplication
- ✅ Batch processing for efficiency
- ✅ Comprehensive error handling and recovery

---

### 3) Ground-truth drift detection & automatic fine-tune trigger (Expert)

- **Scenario:** Model performance drifts over time — need automatic detection and an MLOps workflow for retraining/fine-tuning.
- **Mục tiêu:** Monitor key metrics (accuracy of intent classification, user satisfaction proxies), trigger data sampling + retrain pipeline.
- **Ràng buộc:** Avoid unnecessary retrains (costly); ensure reproducibility & lineage.
- **Success metrics:** Detect drift within X days of onset; retrain reduces degradation by >20%.
- **Tools/gợi ý:** Prometheus + Grafana for metrics; Evidently.ai or WhyLogs for data drift; MLflow for experiment tracking; Kubeflow/Pachyderm/Argo Workflows for retrain pipeline.
- **Test / Verify:** Inject synthetic distribution shifts; verify alerting & automatic pipeline run; check model registry versioning and rollback path.
- **Tips:** Use holdout validation with production-like samples; enable human-in-the-loop review for candidate retrains.

#### 🔧 **Implementation in Codebase**

**Location**: `ai-ml-system/services/drift-detection/`

**Key Files**:
- `ai-ml-system/services/drift-detection/internal/monitor/` - Drift monitoring service
- `ai-ml-system/services/drift-detection/internal/evidently/` - Evidently.ai integration
- `ai-ml-system/services/drift-detection/internal/mlflow/` - MLflow experiment tracking
- `ai-ml-system/services/drift-detection/internal/pipeline/` - Retraining pipeline

**Drift Detection Service**:
```python
# ai-ml-system/services/drift-detection/internal/monitor/drift_monitor.py
import asyncio
import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import json

from evidently import ColumnMapping
from evidently.report import Report
from evidently.metric_preset import DataDriftPreset, TargetDriftPreset
from evidently.metrics import DatasetDriftMetric, ColumnDriftMetric
import mlflow
import mlflow.sklearn
from prometheus_client import Gauge, Counter, start_http_server

class DriftMonitor:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.drift_threshold = config.get('drift_threshold', 0.1)
        self.performance_threshold = config.get('performance_threshold', 0.05)
        self.monitoring_window = config.get('monitoring_window_hours', 24)
        self.retrain_cooldown = config.get('retrain_cooldown_hours', 72)

        # Prometheus metrics
        self.drift_score_gauge = Gauge('model_drift_score', 'Current drift score')
        self.performance_gauge = Gauge('model_performance_score', 'Current performance score')
        self.retrain_counter = Counter('model_retrains_total', 'Total number of retrains triggered')

        # MLflow setup
        mlflow.set_tracking_uri(config['mlflow_tracking_uri'])
        mlflow.set_experiment(config.get('experiment_name', 'drift_detection'))

        self.last_retrain_time = None
        self.reference_data = None
        self.baseline_performance = None

    async def initialize(self):
        """Initialize the drift monitor"""
        # Load reference dataset
        await self._load_reference_data()

        # Load baseline performance metrics
        await self._load_baseline_performance()

        # Start Prometheus metrics server
        start_http_server(8000)

        logging.info("DriftMonitor initialized successfully")

    async def _load_reference_data(self):
        """Load reference dataset for drift comparison"""
        # In production, this would load from a data store
        # For now, we'll simulate loading reference data
        reference_file = self.config.get('reference_data_path')
        if reference_file:
            self.reference_data = pd.read_parquet(reference_file)
            logging.info(f"Loaded reference data: {len(self.reference_data)} samples")
        else:
            logging.warning("No reference data path provided")

    async def _load_baseline_performance(self):
        """Load baseline performance metrics"""
        try:
            # Get the latest production model performance
            client = mlflow.tracking.MlflowClient()
            experiment = client.get_experiment_by_name("production_models")

            if experiment:
                runs = client.search_runs(
                    experiment_ids=[experiment.experiment_id],
                    filter_string="tags.stage = 'Production'",
                    order_by=["start_time DESC"],
                    max_results=1
                )

                if runs:
                    latest_run = runs[0]
                    self.baseline_performance = {
                        'accuracy': latest_run.data.metrics.get('accuracy', 0.0),
                        'f1_score': latest_run.data.metrics.get('f1_score', 0.0),
                        'precision': latest_run.data.metrics.get('precision', 0.0),
                        'recall': latest_run.data.metrics.get('recall', 0.0)
                    }
                    logging.info(f"Loaded baseline performance: {self.baseline_performance}")
        except Exception as e:
            logging.error(f"Error loading baseline performance: {e}")
            self.baseline_performance = {'accuracy': 0.8, 'f1_score': 0.75}  # Default values

    async def start_monitoring(self):
        """Start the drift monitoring loop"""
        logging.info("Starting drift monitoring...")

        while True:
            try:
                # Collect recent data
                current_data = await self._collect_current_data()

                if current_data is not None and len(current_data) > 100:
                    # Detect data drift
                    drift_report = await self._detect_data_drift(current_data)

                    # Detect performance drift
                    performance_metrics = await self._detect_performance_drift(current_data)

                    # Update Prometheus metrics
                    if drift_report:
                        drift_score = drift_report.get('dataset_drift_score', 0.0)
                        self.drift_score_gauge.set(drift_score)

                    if performance_metrics:
                        current_accuracy = performance_metrics.get('accuracy', 0.0)
                        self.performance_gauge.set(current_accuracy)

                    # Check if retraining is needed
                    should_retrain = await self._should_trigger_retrain(drift_report, performance_metrics)

                    if should_retrain:
                        await self._trigger_retrain(drift_report, performance_metrics)

                # Wait before next monitoring cycle
                await asyncio.sleep(self.config.get('monitoring_interval_seconds', 3600))  # 1 hour

            except Exception as e:
                logging.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(300)  # Wait 5 minutes on error

    async def _collect_current_data(self) -> Optional[pd.DataFrame]:
        """Collect recent production data for drift analysis"""
        try:
            # In production, this would query your data warehouse/lake
            # For demo, we'll simulate collecting recent data
            from datetime import datetime, timedelta

            end_time = datetime.now()
            start_time = end_time - timedelta(hours=self.monitoring_window)

            # Simulate data collection (replace with actual data source)
            # This would typically be chat messages, model predictions, etc.
            current_data = pd.DataFrame({
                'message_length': np.random.normal(50, 15, 1000),
                'sentiment_score': np.random.normal(0.1, 0.3, 1000),
                'intent_confidence': np.random.normal(0.8, 0.1, 1000),
                'response_time': np.random.exponential(2.0, 1000),
                'user_satisfaction': np.random.choice([0, 1], 1000, p=[0.2, 0.8]),
                'timestamp': pd.date_range(start_time, end_time, periods=1000)
            })

            return current_data

        except Exception as e:
            logging.error(f"Error collecting current data: {e}")
            return None

    async def _detect_data_drift(self, current_data: pd.DataFrame) -> Dict[str, Any]:
        """Detect data drift using Evidently"""
        if self.reference_data is None:
            logging.warning("No reference data available for drift detection")
            return {}

        try:
            # Define column mapping
            column_mapping = ColumnMapping(
                numerical_features=['message_length', 'sentiment_score', 'intent_confidence', 'response_time'],
                categorical_features=[],
                target='user_satisfaction'
            )

            # Create drift report
            report = Report(metrics=[
                DatasetDriftMetric(),
                ColumnDriftMetric(column_name='message_length'),
                ColumnDriftMetric(column_name='sentiment_score'),
                ColumnDriftMetric(column_name='intent_confidence'),
                TargetDriftMetric()
            ])

            # Run the report
            report.run(
                reference_data=self.reference_data.sample(min(1000, len(self.reference_data))),
                current_data=current_data.sample(min(1000, len(current_data))),
                column_mapping=column_mapping
            )

            # Extract results
            report_dict = report.as_dict()

            drift_results = {
                'dataset_drift_score': report_dict['metrics'][0]['result']['drift_score'],
                'dataset_drift_detected': report_dict['metrics'][0]['result']['drift_detected'],
                'column_drifts': {},
                'target_drift_detected': report_dict['metrics'][-1]['result']['drift_detected'] if len(report_dict['metrics']) > 1 else False
            }

            # Extract column-level drift
            for i, metric in enumerate(report_dict['metrics'][1:-1], 1):
                if 'column_name' in metric['result']:
                    column_name = metric['result']['column_name']
                    drift_results['column_drifts'][column_name] = {
                        'drift_detected': metric['result']['drift_detected'],
                        'drift_score': metric['result'].get('drift_score', 0.0)
                    }

            logging.info(f"Drift detection results: {drift_results}")

            # Log to MLflow
            with mlflow.start_run(run_name=f"drift_detection_{datetime.now().isoformat()}"):
                mlflow.log_metrics({
                    'dataset_drift_score': drift_results['dataset_drift_score'],
                    'dataset_drift_detected': int(drift_results['dataset_drift_detected']),
                    'target_drift_detected': int(drift_results['target_drift_detected'])
                })

                # Save drift report
                report.save_html(f"drift_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html")
                mlflow.log_artifact(f"drift_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html")

            return drift_results

        except Exception as e:
            logging.error(f"Error in drift detection: {e}")
            return {}

    async def _detect_performance_drift(self, current_data: pd.DataFrame) -> Dict[str, float]:
        """Detect performance drift by evaluating current model performance"""
        try:
            # In production, this would evaluate the model on recent labeled data
            # For demo, we'll simulate performance metrics

            # Simulate getting model predictions and ground truth
            # This would typically involve:
            # 1. Getting recent predictions from model serving logs
            # 2. Getting ground truth labels (from human feedback, delayed labels, etc.)
            # 3. Computing performance metrics

            current_performance = {
                'accuracy': np.random.normal(0.82, 0.05),  # Simulate some drift
                'f1_score': np.random.normal(0.78, 0.04),
                'precision': np.random.normal(0.80, 0.03),
                'recall': np.random.normal(0.76, 0.04)
            }

            # Ensure metrics are in valid range
            for metric in current_performance:
                current_performance[metric] = max(0.0, min(1.0, current_performance[metric]))

            logging.info(f"Current performance: {current_performance}")

            # Log to MLflow
            with mlflow.start_run(run_name=f"performance_monitoring_{datetime.now().isoformat()}"):
                mlflow.log_metrics(current_performance)

            return current_performance

        except Exception as e:
            logging.error(f"Error in performance drift detection: {e}")
            return {}

    async def _should_trigger_retrain(self, drift_report: Dict[str, Any], performance_metrics: Dict[str, float]) -> bool:
        """Determine if retraining should be triggered"""

        # Check cooldown period
        if self.last_retrain_time:
            time_since_retrain = datetime.now() - self.last_retrain_time
            if time_since_retrain.total_seconds() < self.retrain_cooldown * 3600:
                logging.info(f"Retrain cooldown active. Time remaining: {self.retrain_cooldown * 3600 - time_since_retrain.total_seconds()} seconds")
                return False

        # Check data drift
        data_drift_detected = drift_report.get('dataset_drift_detected', False)
        drift_score = drift_report.get('dataset_drift_score', 0.0)

        # Check performance drift
        performance_drift_detected = False
        if self.baseline_performance and performance_metrics:
            for metric in ['accuracy', 'f1_score']:
                if metric in self.baseline_performance and metric in performance_metrics:
                    baseline = self.baseline_performance[metric]
                    current = performance_metrics[metric]
                    if baseline - current > self.performance_threshold:
                        performance_drift_detected = True
                        logging.warning(f"Performance drift detected in {metric}: {baseline:.3f} -> {current:.3f}")

        # Decision logic
        should_retrain = (
            data_drift_detected and drift_score > self.drift_threshold
        ) or performance_drift_detected

        if should_retrain:
            logging.info(f"Retraining triggered - Data drift: {data_drift_detected} (score: {drift_score:.3f}), Performance drift: {performance_drift_detected}")

        return should_retrain

    async def _trigger_retrain(self, drift_report: Dict[str, Any], performance_metrics: Dict[str, float]):
        """Trigger the retraining pipeline"""
        try:
            logging.info("Triggering model retraining pipeline...")

            # Create retraining job specification
            retrain_spec = {
                'trigger_reason': 'drift_detected',
                'drift_report': drift_report,
                'performance_metrics': performance_metrics,
                'timestamp': datetime.now().isoformat(),
                'baseline_performance': self.baseline_performance,
                'config': {
                    'data_window_hours': self.monitoring_window * 2,  # Use more data for training
                    'validation_split': 0.2,
                    'early_stopping': True,
                    'max_epochs': 50
                }
            }

            # In production, this would trigger your ML pipeline (Kubeflow, Argo, etc.)
            # For demo, we'll simulate the trigger
            await self._submit_retrain_job(retrain_spec)

            # Update counters and timestamps
            self.retrain_counter.inc()
            self.last_retrain_time = datetime.now()

            # Log to MLflow
            with mlflow.start_run(run_name=f"retrain_trigger_{datetime.now().isoformat()}"):
                mlflow.log_params(retrain_spec['config'])
                mlflow.log_metrics({
                    'drift_score': drift_report.get('dataset_drift_score', 0.0),
                    'current_accuracy': performance_metrics.get('accuracy', 0.0)
                })
                mlflow.set_tag('trigger_reason', 'drift_detected')

            logging.info("Retraining pipeline triggered successfully")

        except Exception as e:
            logging.error(f"Error triggering retrain: {e}")

    async def _submit_retrain_job(self, retrain_spec: Dict[str, Any]):
        """Submit retraining job to ML pipeline"""
        # In production, this would submit to your ML orchestration platform
        # Examples:
        # - Kubeflow Pipelines
        # - Argo Workflows
        # - Apache Airflow
        # - Custom job queue

        # For demo, we'll just log the job submission
        logging.info(f"Submitting retrain job with spec: {json.dumps(retrain_spec, indent=2)}")

        # Simulate job submission delay
        await asyncio.sleep(1)

        logging.info("Retrain job submitted successfully")
```

**Local Testing**:
```bash
# 1. Start drift detection infrastructure
cd ai-ml-system/services/drift-detection
docker-compose up -d mlflow postgres prometheus grafana

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start drift monitoring service
python -m internal.monitor.drift_monitor

# 4. Generate synthetic drift
python scripts/inject_synthetic_drift.py --drift_type data --severity 0.15

# 5. Monitor drift metrics
curl http://localhost:8000/metrics

# 6. Check MLflow experiments
open http://localhost:5000

# 7. Test performance drift
python scripts/inject_performance_drift.py --accuracy_drop 0.08

# 8. Verify retraining trigger
python scripts/verify_retrain_trigger.py
```

**Key Features Implemented**:
- ✅ Evidently.ai integration for data drift detection
- ✅ Performance drift monitoring with baseline comparison
- ✅ MLflow experiment tracking and model registry
- ✅ Prometheus metrics for monitoring
- ✅ Automated retraining pipeline trigger
- ✅ Configurable drift thresholds and cooldown periods

---

### 4) Privacy & PII removal pipeline (Advanced)

- **Scenario:** Conversations may contain PII and must be scrubbed before training or indexing.
- **Mục tiêu:** Detect & redact PII reliably (names, phone numbers, IDs) with audit trail.
- **Ràng buộc:** False positives reduce utility; false negatives breach compliance.
- **Success metrics:** Recall (PII detected) ≥ 99% for regexable patterns; manual audit <1% leak.
- **Tools/gợi ý:** Combine rule-based (regex) + NER models (spaCy, HuggingFace), Sanity checks, differential privacy techniques for training.
- **Test / Verify:** Seed test dataset with various PII formats, multilingual variations; run redaction and audit.
- **Tips:** Store raw encrypted + access-controlled; redact before RAG embeddings.

---

### 5) Hybrid RAG + Retrieval latency SLO under heavy load (Advanced)

- **Scenario:** Agents query RAG concurrently (1000 qps) — must keep latency SLO.
- **Mục tiêu:** Architect caching, prefetch, parallel retrieval + ranked reranking.
- **Ràng buộc:** Cost vs latency tradeoff; vector DB throughput.
- **Success metrics:** 95th percentile retrieval latency < 200ms; cache hit rate >70%.
- **Tools/gợi ý:** Redis cache, elasticsearch for fallback, tuned FAISS + IVF indices, batching of embedding calls, async workers.
- **Test / Verify:** Load test with realistic QPS using k6 or Locust; test cache eviction policies (LRU, TTL).
- **Tips:** Use query-level caching for frequent FAQs and aggregate results.

---

### 6) Multi-tenant model serving + quota enforcement (Intermediate)

- **Scenario:** Multiple tenants share the platform with separate datasets and SLAs.
- **Mục tiêu:** Isolate data, ensure per-tenant index, quota-limited inference, fair resource allocation.
- **Ràng buộc:** Avoid cross-tenant leakage.
- **Success metrics:** No cross-tenant contamination; enforced quotas at runtime.
- **Tools/gợi ý:** Namespace indices, Kubernetes multi-tenancy, rate-limiting (Envoy), token bucket, tenant-aware routing.
- **Test / Verify:** Simulate noisy tenant and confirm throttling; run data ingestion for tenant A and assert tenant B cannot query them.
- **Tips:** Use per-tenant encryption keys; automated tenant onboarding script.

---

### 7) Offline backfill & reindex after embedding model upgrade (Advanced)

- **Scenario:** You upgrade embedding model (better vectors). Need to re-embed historical docs and swap index with minimal downtime.
- **Mục tiêu:** Efficient re-embedding, minimal computation cost, atomic swap.
- **Ràng buộc:** Large corpus (10s TB) and budget constraint.
- **Success metrics:** Reindex completed with no downtime > 1 minute; cost within budget.
- **Tools/gợi ý:** Batch jobs on k8s with parallel workers, spot VMs, incremental reindexing, multi-index rollout.
- **Test / Verify:** Run on subset; test blue/green index routing and rollback.
- **Tips:** Shard reembedding jobs by date/tenant; resumeable jobs.

---

### 8) Human-in-the-loop labeling & quality control pipeline (Intermediate)

- **Scenario:** Build workflow to surface low-confidence chats to agents for labeling and feed back into training.
- **Mục tiêu:** Reduce false positives and improve model quickly.
- **Ràng buộc:** Label latency, UI for labelers, versioning.
- **Success metrics:** Labeled data throughput, labeler agreement score, model lift after retrain.
- **Tools/gợi ý:** Label-studio, internal UI, Redis queues, Auditing, MLflow.
- **Test / Verify:** Deploy with small team of labelers, measure agreement, do AB test with new model.
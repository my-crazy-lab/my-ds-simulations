# RAG Engine Service

Real-time Retrieval-Augmented Generation (RAG) indexing system with streaming updates, blue/green deployments, and high-performance search capabilities.

## 🎯 **Key Features**

### **Real-time Indexing**
- **Streaming ingestion** from Kafka with automatic chunking and embedding
- **Idempotent processing** with Redis-based deduplication
- **Sub-minute latency** from message ingestion to searchable index
- **Automatic retry** and error handling for failed indexing operations

### **Blue/Green Deployments**
- **Zero-downtime** index updates with atomic swaps
- **Health checks** and rollback capabilities
- **Version management** with automatic cleanup of old indices
- **A/B testing** support for index quality validation

### **High-Performance Search**
- **Vector similarity search** with cosine similarity
- **Redis caching** for frequently accessed queries
- **Parallel processing** with async/await patterns
- **Sub-200ms p95 latency** at 1000+ QPS

### **Production-Ready**
- **Comprehensive monitoring** with Prometheus metrics
- **Structured logging** with correlation IDs
- **Health checks** and readiness probes
- **Graceful shutdown** and resource cleanup

## 🏗️ **Architecture**

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Kafka Topic   │───▶│   RAG Engine     │───▶│   Milvus VDB    │
│ processed-msgs  │    │                  │    │   (Blue/Green)  │
└─────────────────┘    │  ┌─────────────┐ │    └─────────────────┘
                       │  │  Chunker    │ │              │
┌─────────────────┐    │  └─────────────┘ │              │
│     Redis       │◀───┤  ┌─────────────┐ │              │
│   (Cache +      │    │  │ Embeddings  │ │              ▼
│  Deduplication) │    │  └─────────────┘ │    ┌─────────────────┐
└─────────────────┘    │  ┌─────────────┐ │    │   Search API    │
                       │  │Blue/Green   │ │    │  (FastAPI)      │
                       │  │Deployment   │ │    └─────────────────┘
                       │  └─────────────┘ │
                       └──────────────────┘
```

## 🚀 **Quick Start**

### **1. Prerequisites**
```bash
# Install Python dependencies
pip install -r requirements.txt

# Start infrastructure (from project root)
cd ai-ml-system
docker-compose up -d kafka milvus redis
```

### **2. Configuration**
```bash
# Environment variables
export KAFKA_BOOTSTRAP_SERVERS="localhost:9092"
export KAFKA_TOPIC="processed-messages"
export MILVUS_HOST="localhost"
export MILVUS_PORT="19530"
export REDIS_URL="redis://localhost:6379"
export EMBEDDING_MODEL="all-MiniLM-L6-v2"
```

### **3. Start the Service**
```bash
cd services/rag-engine
python main.py
```

### **4. Test the API**
```bash
# Health check
curl http://localhost:8081/health

# Search documents
curl -X POST http://localhost:8081/search \
  -H "Content-Type: application/json" \
  -d '{"query": "how to reset password", "top_k": 5}'

# Index statistics
curl http://localhost:8081/index/stats
```

## 📊 **Performance Targets**

| Metric | Target | Monitoring |
|--------|--------|------------|
| **Ingestion Latency** | <1 minute end-to-end | `rag_indexing_duration_seconds` |
| **Search Latency** | <200ms p95 | `http_req_duration` |
| **Throughput** | ≥1000 QPS | `http_reqs_per_sec` |
| **Availability** | ≥99.9% uptime | `up` metric |
| **Cache Hit Rate** | >70% for common queries | `rag_cache_hit_rate` |
| **Index Freshness** | <1% stale queries | `rag_stale_queries_total` |

## 🔧 **API Reference**

### **Search Endpoint**
```http
POST /search
Content-Type: application/json

{
  "query": "search query text",
  "top_k": 10
}
```

**Response:**
```json
{
  "results": [
    {
      "chunk_id": "doc1_chunk_0",
      "document_id": "doc1",
      "content": "relevant content snippet",
      "score": 0.95,
      "metadata": {
        "source": "api",
        "timestamp": "2023-01-01T00:00:00Z"
      }
    }
  ],
  "query": "search query text",
  "total_results": 5,
  "processing_time_ms": 45.2
}
```

### **Health Check**
```http
GET /health
```

**Response:**
```json
{
  "status": "healthy",
  "service": "rag-index",
  "timestamp": "2023-01-01T00:00:00Z",
  "index_version": "v1",
  "index_size": 10000
}
```

### **Index Statistics**
```http
GET /index/stats
```

**Response:**
```json
{
  "collection_name": "document_embeddings_v1",
  "total_documents": 10000,
  "index_version": "v1",
  "embedding_dimension": 384,
  "chunk_size": 512,
  "chunk_overlap": 50
}
```

## 🔄 **Blue/Green Deployment**

### **Deployment Process**
1. **Create new index** with updated version
2. **Build index** by processing all documents
3. **Health check** new index for quality validation
4. **Atomic swap** to activate new index
5. **Monitor** for issues and rollback if needed
6. **Cleanup** old index versions

### **Deployment Commands**
```python
from blue_green_deployment import BlueGreenDeploymentManager

# Initialize deployment manager
manager = BlueGreenDeploymentManager(
    redis_url="redis://localhost:6379",
    milvus_host="localhost",
    milvus_port=19530,
    collection_prefix="document_embeddings"
)

# Create new index version
metadata, collection_name = await manager.create_new_index("v2.0")

# Update status during build process
await manager.update_index_status(collection_name, DeploymentStatus.BUILDING)
await manager.update_index_status(collection_name, DeploymentStatus.READY, 
                                 document_count=15000, health_score=0.95)

# Perform atomic swap
success = await manager.perform_atomic_swap(collection_name)

# Rollback if needed
if not success:
    await manager.rollback_deployment()
```

## 📈 **Monitoring & Observability**

### **Prometheus Metrics**
```
# Processing metrics
rag_messages_processed_total{status="success|error"}
rag_embedding_duration_seconds
rag_indexing_duration_seconds

# Search metrics  
rag_vectordb_operations_total{operation="search|upsert", status="success|error"}
rag_index_size
rag_stale_queries_total

# Deployment metrics
rag_deployment_operations_total{operation="create_index|atomic_swap|rollback", status="success|error"}
rag_active_index{version="v1", color="blue|green"}
rag_deployment_duration_seconds
```

### **Grafana Dashboard Queries**
```promql
# Search latency p95
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))

# Cache hit rate
rate(rag_cache_hits_total[5m]) / rate(rag_search_requests_total[5m])

# Index freshness
rate(rag_stale_queries_total[5m]) / rate(rag_search_requests_total[5m])

# Throughput
rate(http_requests_total[1m])
```

## 🧪 **Testing**

### **Unit Tests**
```bash
cd tests/unit/rag-engine
python -m pytest test_rag_service.py -v
```

### **Load Testing**
```bash
# Install K6
brew install k6  # macOS
# or download from https://k6.io/docs/getting-started/installation/

# Run load test
cd tests/load
k6 run rag-engine-load-test.js
```

### **Integration Testing**
```bash
# Start test environment
docker-compose -f docker-compose.test.yml up -d

# Run integration tests
python -m pytest tests/integration/test_rag_integration.py -v
```

## 🔧 **Configuration**

### **Environment Variables**
```bash
# Kafka Configuration
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
KAFKA_TOPIC=processed-messages
KAFKA_GROUP_ID=rag-indexer

# Milvus Configuration
MILVUS_HOST=localhost
MILVUS_PORT=19530
MILVUS_COLLECTION_NAME=document_embeddings

# Redis Configuration
REDIS_URL=redis://localhost:6379

# Embedding Configuration
EMBEDDING_MODEL=all-MiniLM-L6-v2
EMBEDDING_DIMENSION=384

# Chunking Configuration
CHUNK_SIZE=512
CHUNK_OVERLAP=50

# Deployment Configuration
INDEX_VERSION=v1
BLUE_GREEN_ENABLED=true
```

### **Production Tuning**
```python
# Milvus index parameters
index_params = {
    "metric_type": "COSINE",
    "index_type": "IVF_FLAT",  # or "HNSW" for better performance
    "params": {"nlist": 1024}  # Adjust based on data size
}

# Search parameters
search_params = {
    "metric_type": "COSINE",
    "params": {"nprobe": 10}  # Higher = more accurate, slower
}
```

## 🚨 **Troubleshooting**

### **Common Issues**

**1. High Search Latency**
```bash
# Check Milvus index status
curl http://localhost:8081/index/stats

# Monitor embedding generation time
# Look for rag_embedding_duration_seconds metric

# Optimize search parameters
# Reduce nprobe or switch to HNSW index
```

**2. Low Cache Hit Rate**
```bash
# Check Redis connection
redis-cli ping

# Monitor cache metrics
# Look for rag_cache_hit_rate metric

# Analyze query patterns
# Implement query normalization
```

**3. Index Build Failures**
```bash
# Check Milvus logs
docker logs milvus-standalone

# Verify embedding model
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# Check disk space and memory
df -h
free -m
```

### **Health Check Failures**
```bash
# Check service dependencies
curl http://localhost:8081/health

# Verify Kafka connectivity
kafka-console-consumer --bootstrap-server localhost:9092 --topic processed-messages

# Test Milvus connection
python -c "from pymilvus import connections; connections.connect(host='localhost', port='19530')"
```

## 📚 **Additional Resources**

- [Milvus Documentation](https://milvus.io/docs)
- [Sentence Transformers](https://www.sbert.net/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Prometheus Monitoring](https://prometheus.io/docs/)
- [K6 Load Testing](https://k6.io/docs/)

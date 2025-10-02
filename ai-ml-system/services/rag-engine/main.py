#!/usr/bin/env python3
"""
Real-time RAG Index System
Streaming ingestion → chunking → embedding → vectordb upsert with atomic swap
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import redis.asyncio as redis
from kafka import KafkaConsumer
from kafka.errors import KafkaError
import numpy as np
from sentence_transformers import SentenceTransformer
import pymilvus
from pymilvus import connections, Collection, FieldSchema, CollectionSchema, DataType, utility
import prometheus_client
from prometheus_client import Counter, Histogram, Gauge, generate_latest

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Prometheus metrics
MESSAGES_PROCESSED = Counter('rag_messages_processed_total', 'Total processed messages', ['status'])
EMBEDDING_DURATION = Histogram('rag_embedding_duration_seconds', 'Time spent generating embeddings')
INDEXING_DURATION = Histogram('rag_indexing_duration_seconds', 'Time spent indexing documents')
VECTOR_DB_OPERATIONS = Counter('rag_vectordb_operations_total', 'Vector DB operations', ['operation', 'status'])
INDEX_SIZE = Gauge('rag_index_size', 'Current index size')
STALE_QUERIES = Counter('rag_stale_queries_total', 'Number of stale queries served')

@dataclass
class ProcessedMessage:
    """Processed message from data ingestion pipeline"""
    id: str
    original_id: str
    source: str
    type: str
    timestamp: str
    processed_at: str
    data: Dict
    metadata: Dict
    idempotency_key: str
    validation_status: str
    normalization_applied: List[str]

@dataclass
class DocumentChunk:
    """Document chunk for embedding and indexing"""
    chunk_id: str
    document_id: str
    content: str
    metadata: Dict
    chunk_index: int
    total_chunks: int
    embedding: Optional[List[float]] = None

@dataclass
class IndexedDocument:
    """Indexed document in vector database"""
    document_id: str
    chunks: List[DocumentChunk]
    indexed_at: str
    index_version: str

class RAGIndexConfig:
    """Configuration for RAG indexing system"""
    
    # Kafka settings
    KAFKA_BOOTSTRAP_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
    KAFKA_TOPIC = os.getenv('KAFKA_TOPIC', 'processed-messages')
    KAFKA_GROUP_ID = os.getenv('KAFKA_GROUP_ID', 'rag-indexer')
    
    # Milvus settings
    MILVUS_HOST = os.getenv('MILVUS_HOST', 'localhost')
    MILVUS_PORT = int(os.getenv('MILVUS_PORT', '19530'))
    MILVUS_COLLECTION_NAME = os.getenv('MILVUS_COLLECTION_NAME', 'document_embeddings')
    
    # Redis settings
    REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379')
    
    # Embedding settings
    EMBEDDING_MODEL = os.getenv('EMBEDDING_MODEL', 'all-MiniLM-L6-v2')
    EMBEDDING_DIMENSION = int(os.getenv('EMBEDDING_DIMENSION', '384'))
    
    # Chunking settings
    CHUNK_SIZE = int(os.getenv('CHUNK_SIZE', '512'))
    CHUNK_OVERLAP = int(os.getenv('CHUNK_OVERLAP', '50'))
    
    # Index settings
    INDEX_VERSION = os.getenv('INDEX_VERSION', 'v1')
    BLUE_GREEN_ENABLED = os.getenv('BLUE_GREEN_ENABLED', 'true').lower() == 'true'

class DocumentChunker:
    """Handles document chunking for RAG indexing"""
    
    def __init__(self, chunk_size: int = 512, overlap: int = 50):
        self.chunk_size = chunk_size
        self.overlap = overlap
    
    def chunk_document(self, document_id: str, content: str, metadata: Dict) -> List[DocumentChunk]:
        """Split document into overlapping chunks"""
        if not content or len(content.strip()) == 0:
            return []
        
        # Simple word-based chunking (in production, use more sophisticated methods)
        words = content.split()
        chunks = []
        
        for i in range(0, len(words), self.chunk_size - self.overlap):
            chunk_words = words[i:i + self.chunk_size]
            chunk_content = ' '.join(chunk_words)
            
            if len(chunk_content.strip()) == 0:
                continue
            
            chunk_id = f"{document_id}_chunk_{len(chunks)}"
            chunk = DocumentChunk(
                chunk_id=chunk_id,
                document_id=document_id,
                content=chunk_content,
                metadata=metadata.copy(),
                chunk_index=len(chunks),
                total_chunks=0  # Will be updated after all chunks are created
            )
            chunks.append(chunk)
        
        # Update total_chunks for all chunks
        for chunk in chunks:
            chunk.total_chunks = len(chunks)
        
        return chunks

class EmbeddingService:
    """Handles document embedding generation"""
    
    def __init__(self, model_name: str = 'all-MiniLM-L6-v2'):
        self.model_name = model_name
        self.model = None
        self._load_model()
    
    def _load_model(self):
        """Load the embedding model"""
        try:
            logger.info(f"Loading embedding model: {self.model_name}")
            self.model = SentenceTransformer(self.model_name)
            logger.info("Embedding model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            raise
    
    @EMBEDDING_DURATION.time()
    def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a list of texts"""
        if not self.model:
            raise RuntimeError("Embedding model not loaded")
        
        try:
            embeddings = self.model.encode(texts, convert_to_numpy=True)
            return embeddings.tolist()
        except Exception as e:
            logger.error(f"Failed to generate embeddings: {e}")
            raise
    
    def embed_chunks(self, chunks: List[DocumentChunk]) -> List[DocumentChunk]:
        """Generate embeddings for document chunks"""
        if not chunks:
            return chunks
        
        texts = [chunk.content for chunk in chunks]
        embeddings = self.generate_embeddings(texts)
        
        for chunk, embedding in zip(chunks, embeddings):
            chunk.embedding = embedding
        
        return chunks

class VectorDBService:
    """Handles vector database operations with Milvus"""
    
    def __init__(self, config: RAGIndexConfig):
        self.config = config
        self.collection = None
        self.current_index_version = config.INDEX_VERSION
        self._connect()
        self._setup_collection()
    
    def _connect(self):
        """Connect to Milvus"""
        try:
            connections.connect(
                alias="default",
                host=self.config.MILVUS_HOST,
                port=self.config.MILVUS_PORT
            )
            logger.info("Connected to Milvus")
        except Exception as e:
            logger.error(f"Failed to connect to Milvus: {e}")
            raise
    
    def _setup_collection(self):
        """Setup Milvus collection schema"""
        try:
            collection_name = f"{self.config.MILVUS_COLLECTION_NAME}_{self.current_index_version}"
            
            # Define collection schema
            fields = [
                FieldSchema(name="chunk_id", dtype=DataType.VARCHAR, max_length=255, is_primary=True),
                FieldSchema(name="document_id", dtype=DataType.VARCHAR, max_length=255),
                FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=self.config.EMBEDDING_DIMENSION),
                FieldSchema(name="chunk_index", dtype=DataType.INT64),
                FieldSchema(name="total_chunks", dtype=DataType.INT64),
                FieldSchema(name="indexed_at", dtype=DataType.VARCHAR, max_length=50),
                FieldSchema(name="source", dtype=DataType.VARCHAR, max_length=50),
                FieldSchema(name="metadata_json", dtype=DataType.VARCHAR, max_length=65535),
            ]
            
            schema = CollectionSchema(fields, f"RAG document embeddings {self.current_index_version}")
            
            # Create collection if it doesn't exist
            if not utility.has_collection(collection_name):
                self.collection = Collection(collection_name, schema)
                logger.info(f"Created collection: {collection_name}")
                
                # Create index for vector field
                index_params = {
                    "metric_type": "COSINE",
                    "index_type": "IVF_FLAT",
                    "params": {"nlist": 1024}
                }
                self.collection.create_index("embedding", index_params)
                logger.info("Created vector index")
            else:
                self.collection = Collection(collection_name)
                logger.info(f"Using existing collection: {collection_name}")
            
            # Load collection
            self.collection.load()
            
        except Exception as e:
            logger.error(f"Failed to setup collection: {e}")
            raise
    
    @INDEXING_DURATION.time()
    def upsert_chunks(self, chunks: List[DocumentChunk]) -> bool:
        """Upsert document chunks to vector database"""
        if not chunks:
            return True
        
        try:
            # Prepare data for insertion
            chunk_ids = [chunk.chunk_id for chunk in chunks]
            document_ids = [chunk.document_id for chunk in chunks]
            contents = [chunk.content for chunk in chunks]
            embeddings = [chunk.embedding for chunk in chunks]
            chunk_indices = [chunk.chunk_index for chunk in chunks]
            total_chunks = [chunk.total_chunks for chunk in chunks]
            indexed_ats = [datetime.now().isoformat() for _ in chunks]
            sources = [chunk.metadata.get('source', 'unknown') for chunk in chunks]
            metadata_jsons = [json.dumps(chunk.metadata) for chunk in chunks]
            
            # Insert data
            data = [
                chunk_ids,
                document_ids,
                contents,
                embeddings,
                chunk_indices,
                total_chunks,
                indexed_ats,
                sources,
                metadata_jsons,
            ]
            
            self.collection.insert(data)
            self.collection.flush()
            
            VECTOR_DB_OPERATIONS.labels(operation='upsert', status='success').inc(len(chunks))
            logger.info(f"Upserted {len(chunks)} chunks to vector database")
            
            # Update index size metric
            INDEX_SIZE.set(self.collection.num_entities)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to upsert chunks: {e}")
            VECTOR_DB_OPERATIONS.labels(operation='upsert', status='error').inc()
            return False
    
    def search_similar(self, query_embedding: List[float], top_k: int = 10) -> List[Dict]:
        """Search for similar documents"""
        try:
            search_params = {"metric_type": "COSINE", "params": {"nprobe": 10}}
            
            results = self.collection.search(
                data=[query_embedding],
                anns_field="embedding",
                param=search_params,
                limit=top_k,
                output_fields=["chunk_id", "document_id", "content", "chunk_index", "source", "metadata_json"]
            )
            
            search_results = []
            for hits in results:
                for hit in hits:
                    result = {
                        "chunk_id": hit.entity.get("chunk_id"),
                        "document_id": hit.entity.get("document_id"),
                        "content": hit.entity.get("content"),
                        "chunk_index": hit.entity.get("chunk_index"),
                        "source": hit.entity.get("source"),
                        "metadata": json.loads(hit.entity.get("metadata_json", "{}")),
                        "score": hit.score,
                        "distance": hit.distance,
                    }
                    search_results.append(result)
            
            VECTOR_DB_OPERATIONS.labels(operation='search', status='success').inc()
            return search_results
            
        except Exception as e:
            logger.error(f"Failed to search similar documents: {e}")
            VECTOR_DB_OPERATIONS.labels(operation='search', status='error').inc()
            return []

class RAGIndexService:
    """Main RAG indexing service"""
    
    def __init__(self):
        self.config = RAGIndexConfig()
        self.chunker = DocumentChunker(self.config.CHUNK_SIZE, self.config.CHUNK_OVERLAP)
        self.embedding_service = EmbeddingService(self.config.EMBEDDING_MODEL)
        self.vector_db = VectorDBService(self.config)
        self.redis_client = None
        self.kafka_consumer = None
        self.running = False
    
    async def start(self):
        """Start the RAG indexing service"""
        logger.info("Starting RAG Index Service")
        
        # Connect to Redis
        self.redis_client = redis.from_url(self.config.REDIS_URL)
        
        # Setup Kafka consumer
        self.kafka_consumer = KafkaConsumer(
            self.config.KAFKA_TOPIC,
            bootstrap_servers=self.config.KAFKA_BOOTSTRAP_SERVERS,
            group_id=self.config.KAFKA_GROUP_ID,
            value_deserializer=lambda x: json.loads(x.decode('utf-8')),
            auto_offset_reset='latest',
            enable_auto_commit=True,
        )
        
        self.running = True
        
        # Start message processing loop
        asyncio.create_task(self._process_messages())
        
        logger.info("RAG Index Service started")
    
    async def stop(self):
        """Stop the RAG indexing service"""
        logger.info("Stopping RAG Index Service")
        self.running = False
        
        if self.kafka_consumer:
            self.kafka_consumer.close()
        
        if self.redis_client:
            await self.redis_client.close()
        
        logger.info("RAG Index Service stopped")
    
    async def _process_messages(self):
        """Process messages from Kafka stream"""
        logger.info("Starting message processing loop")
        
        while self.running:
            try:
                # Poll for messages (non-blocking)
                message_batch = self.kafka_consumer.poll(timeout_ms=1000)
                
                for topic_partition, messages in message_batch.items():
                    for message in messages:
                        await self._process_single_message(message.value)
                
            except KafkaError as e:
                logger.error(f"Kafka error: {e}")
                await asyncio.sleep(5)  # Wait before retrying
            except Exception as e:
                logger.error(f"Error processing messages: {e}")
                await asyncio.sleep(1)
    
    async def _process_single_message(self, message_data: Dict):
        """Process a single message from the stream"""
        try:
            # Parse processed message
            processed_msg = ProcessedMessage(**message_data)
            
            # Only process chat messages and documents
            if processed_msg.type not in ['chat_message', 'document', 'user_event']:
                return
            
            # Extract content for indexing
            content = self._extract_content(processed_msg)
            if not content:
                return
            
            # Check if already indexed (idempotency)
            cache_key = f"indexed:{processed_msg.idempotency_key}"
            if await self.redis_client.exists(cache_key):
                logger.debug(f"Message {processed_msg.id} already indexed, skipping")
                return
            
            # Chunk document
            chunks = self.chunker.chunk_document(
                document_id=processed_msg.id,
                content=content,
                metadata={
                    'source': processed_msg.source,
                    'type': processed_msg.type,
                    'timestamp': processed_msg.timestamp,
                    'original_id': processed_msg.original_id,
                    **processed_msg.metadata
                }
            )
            
            if not chunks:
                logger.warning(f"No chunks generated for message {processed_msg.id}")
                return
            
            # Generate embeddings
            embedded_chunks = self.embedding_service.embed_chunks(chunks)
            
            # Upsert to vector database
            success = self.vector_db.upsert_chunks(embedded_chunks)
            
            if success:
                # Mark as indexed in cache (TTL: 24 hours)
                await self.redis_client.setex(cache_key, 86400, "indexed")
                
                MESSAGES_PROCESSED.labels(status='success').inc()
                logger.info(f"Successfully indexed message {processed_msg.id} with {len(chunks)} chunks")
            else:
                MESSAGES_PROCESSED.labels(status='error').inc()
                logger.error(f"Failed to index message {processed_msg.id}")
                
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            MESSAGES_PROCESSED.labels(status='error').inc()
    
    def _extract_content(self, message: ProcessedMessage) -> Optional[str]:
        """Extract indexable content from processed message"""
        if message.type == 'chat_message':
            return message.data.get('content', '')
        elif message.type == 'document':
            return message.data.get('text', '') or message.data.get('content', '')
        elif message.type == 'user_event':
            # Index event descriptions or properties
            event_name = message.data.get('event_name', '')
            properties = message.data.get('properties', {})
            return f"{event_name} {json.dumps(properties)}"
        
        return None
    
    async def search(self, query: str, top_k: int = 10) -> List[Dict]:
        """Search for similar documents"""
        try:
            # Generate query embedding
            query_embedding = self.embedding_service.generate_embeddings([query])[0]
            
            # Search in vector database
            results = self.vector_db.search_similar(query_embedding, top_k)
            
            return results
            
        except Exception as e:
            logger.error(f"Error searching documents: {e}")
            return []

# Global service instance
rag_service = RAGIndexService()

# FastAPI app
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await rag_service.start()
    yield
    # Shutdown
    await rag_service.stop()

app = FastAPI(
    title="RAG Index Service",
    description="Real-time RAG indexing with streaming updates",
    version="1.0.0",
    lifespan=lifespan
)

# API Models
class SearchRequest(BaseModel):
    query: str
    top_k: int = 10

class SearchResponse(BaseModel):
    results: List[Dict]
    query: str
    total_results: int
    processing_time_ms: float

# API Endpoints
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "rag-index",
        "timestamp": datetime.now().isoformat(),
        "index_version": rag_service.config.INDEX_VERSION,
        "index_size": rag_service.vector_db.collection.num_entities if rag_service.vector_db.collection else 0,
    }

@app.post("/search", response_model=SearchResponse)
async def search_documents(request: SearchRequest):
    """Search for similar documents"""
    start_time = time.time()
    
    try:
        results = await rag_service.search(request.query, request.top_k)
        processing_time = (time.time() - start_time) * 1000
        
        return SearchResponse(
            results=results,
            query=request.query,
            total_results=len(results),
            processing_time_ms=processing_time
        )
        
    except Exception as e:
        logger.error(f"Search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/metrics")
async def get_metrics():
    """Prometheus metrics endpoint"""
    return JSONResponse(
        content=generate_latest().decode('utf-8'),
        media_type="text/plain"
    )

@app.get("/index/stats")
async def get_index_stats():
    """Get index statistics"""
    try:
        collection = rag_service.vector_db.collection
        if not collection:
            raise HTTPException(status_code=503, detail="Vector database not available")
        
        stats = {
            "collection_name": collection.name,
            "total_documents": collection.num_entities,
            "index_version": rag_service.config.INDEX_VERSION,
            "embedding_dimension": rag_service.config.EMBEDDING_DIMENSION,
            "chunk_size": rag_service.config.CHUNK_SIZE,
            "chunk_overlap": rag_service.config.CHUNK_OVERLAP,
        }
        
        return stats
        
    except Exception as e:
        logger.error(f"Error getting index stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8081,
        reload=False,
        log_level="info"
    )

#!/usr/bin/env python3
"""
Unit tests for RAG Index Service
"""

import pytest
import asyncio
import json
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime
import numpy as np

# Import the modules to test
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '../../../services/rag-engine'))

from main import (
    DocumentChunker, EmbeddingService, VectorDBService, RAGIndexService,
    ProcessedMessage, DocumentChunk, RAGIndexConfig
)
from blue_green_deployment import BlueGreenDeploymentManager, IndexMetadata, IndexColor, DeploymentStatus

class TestDocumentChunker:
    """Test document chunking functionality"""
    
    def test_chunk_document_basic(self):
        """Test basic document chunking"""
        chunker = DocumentChunker(chunk_size=10, overlap=2)
        
        content = "This is a test document with multiple words that should be chunked properly"
        metadata = {"source": "test", "type": "document"}
        
        chunks = chunker.chunk_document("doc-001", content, metadata)
        
        assert len(chunks) > 1
        assert all(chunk.document_id == "doc-001" for chunk in chunks)
        assert all(chunk.metadata == metadata for chunk in chunks)
        assert all(chunk.total_chunks == len(chunks) for chunk in chunks)
        
        # Check chunk indices
        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i
    
    def test_chunk_document_empty_content(self):
        """Test chunking with empty content"""
        chunker = DocumentChunker()
        
        chunks = chunker.chunk_document("doc-002", "", {"source": "test"})
        assert len(chunks) == 0
        
        chunks = chunker.chunk_document("doc-003", "   ", {"source": "test"})
        assert len(chunks) == 0
    
    def test_chunk_document_short_content(self):
        """Test chunking with content shorter than chunk size"""
        chunker = DocumentChunker(chunk_size=100, overlap=10)
        
        content = "Short content"
        chunks = chunker.chunk_document("doc-004", content, {"source": "test"})
        
        assert len(chunks) == 1
        assert chunks[0].content == content
        assert chunks[0].chunk_index == 0
        assert chunks[0].total_chunks == 1
    
    def test_chunk_overlap(self):
        """Test that chunks have proper overlap"""
        chunker = DocumentChunker(chunk_size=5, overlap=2)
        
        content = "one two three four five six seven eight nine ten"
        chunks = chunker.chunk_document("doc-005", content, {"source": "test"})
        
        assert len(chunks) >= 2
        
        # Check that there's overlap between consecutive chunks
        for i in range(len(chunks) - 1):
            chunk1_words = chunks[i].content.split()
            chunk2_words = chunks[i + 1].content.split()
            
            # Should have some overlapping words
            overlap_found = any(word in chunk2_words for word in chunk1_words[-2:])
            assert overlap_found, f"No overlap found between chunks {i} and {i+1}"

class TestEmbeddingService:
    """Test embedding generation functionality"""
    
    @pytest.fixture
    def mock_sentence_transformer(self):
        """Mock SentenceTransformer"""
        with patch('main.SentenceTransformer') as mock_st:
            mock_model = Mock()
            mock_model.encode.return_value = np.array([[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]])
            mock_st.return_value = mock_model
            yield mock_model
    
    def test_embedding_service_initialization(self, mock_sentence_transformer):
        """Test embedding service initialization"""
        service = EmbeddingService("test-model")
        
        assert service.model_name == "test-model"
        assert service.model is not None
    
    def test_generate_embeddings(self, mock_sentence_transformer):
        """Test embedding generation"""
        service = EmbeddingService("test-model")
        
        texts = ["Hello world", "Test document"]
        embeddings = service.generate_embeddings(texts)
        
        assert len(embeddings) == 2
        assert len(embeddings[0]) == 3  # Mock returns 3-dimensional embeddings
        assert embeddings[0] == [0.1, 0.2, 0.3]
        assert embeddings[1] == [0.4, 0.5, 0.6]
        
        # Verify model was called correctly
        mock_sentence_transformer.encode.assert_called_once_with(texts, convert_to_numpy=True)
    
    def test_embed_chunks(self, mock_sentence_transformer):
        """Test embedding document chunks"""
        service = EmbeddingService("test-model")
        
        chunks = [
            DocumentChunk("chunk1", "doc1", "Content 1", {}, 0, 2),
            DocumentChunk("chunk2", "doc1", "Content 2", {}, 1, 2),
        ]
        
        embedded_chunks = service.embed_chunks(chunks)
        
        assert len(embedded_chunks) == 2
        assert embedded_chunks[0].embedding == [0.1, 0.2, 0.3]
        assert embedded_chunks[1].embedding == [0.4, 0.5, 0.6]
    
    def test_embed_empty_chunks(self, mock_sentence_transformer):
        """Test embedding empty chunk list"""
        service = EmbeddingService("test-model")
        
        embedded_chunks = service.embed_chunks([])
        assert len(embedded_chunks) == 0

class TestVectorDBService:
    """Test vector database operations"""
    
    @pytest.fixture
    def mock_milvus(self):
        """Mock Milvus connections and operations"""
        with patch('main.connections') as mock_conn, \
             patch('main.Collection') as mock_collection_class, \
             patch('main.utility') as mock_utility:
            
            mock_collection = Mock()
            mock_collection.num_entities = 100
            mock_collection.name = "test_collection_v1"
            mock_collection_class.return_value = mock_collection
            
            mock_utility.has_collection.return_value = False
            
            yield {
                'connections': mock_conn,
                'Collection': mock_collection_class,
                'utility': mock_utility,
                'collection': mock_collection
            }
    
    def test_vector_db_initialization(self, mock_milvus):
        """Test vector database service initialization"""
        config = RAGIndexConfig()
        service = VectorDBService(config)
        
        # Verify Milvus connection was attempted
        mock_milvus['connections'].connect.assert_called_once()
        
        # Verify collection setup
        mock_milvus['utility'].has_collection.assert_called()
    
    def test_upsert_chunks(self, mock_milvus):
        """Test upserting document chunks"""
        config = RAGIndexConfig()
        service = VectorDBService(config)
        
        chunks = [
            DocumentChunk("chunk1", "doc1", "Content 1", {"source": "test"}, 0, 1, [0.1, 0.2, 0.3]),
        ]
        
        result = service.upsert_chunks(chunks)
        
        assert result is True
        mock_milvus['collection'].insert.assert_called_once()
        mock_milvus['collection'].flush.assert_called_once()
    
    def test_upsert_empty_chunks(self, mock_milvus):
        """Test upserting empty chunk list"""
        config = RAGIndexConfig()
        service = VectorDBService(config)
        
        result = service.upsert_chunks([])
        assert result is True
        
        # Should not call insert for empty list
        mock_milvus['collection'].insert.assert_not_called()
    
    def test_search_similar(self, mock_milvus):
        """Test similarity search"""
        config = RAGIndexConfig()
        service = VectorDBService(config)
        
        # Mock search results
        mock_hit = Mock()
        mock_hit.entity.get.side_effect = lambda key: {
            "chunk_id": "chunk1",
            "document_id": "doc1",
            "content": "Test content",
            "chunk_index": 0,
            "source": "test",
            "metadata_json": '{"key": "value"}'
        }.get(key)
        mock_hit.score = 0.95
        mock_hit.distance = 0.05
        
        mock_hits = [mock_hit]
        mock_milvus['collection'].search.return_value = [mock_hits]
        
        query_embedding = [0.1, 0.2, 0.3]
        results = service.search_similar(query_embedding, top_k=5)
        
        assert len(results) == 1
        assert results[0]["chunk_id"] == "chunk1"
        assert results[0]["score"] == 0.95
        assert results[0]["metadata"] == {"key": "value"}
        
        mock_milvus['collection'].search.assert_called_once()

class TestRAGIndexService:
    """Test main RAG indexing service"""
    
    @pytest.fixture
    def mock_dependencies(self):
        """Mock all external dependencies"""
        with patch('main.redis.from_url') as mock_redis, \
             patch('main.KafkaConsumer') as mock_kafka, \
             patch('main.DocumentChunker') as mock_chunker, \
             patch('main.EmbeddingService') as mock_embedding, \
             patch('main.VectorDBService') as mock_vectordb:
            
            # Setup mocks
            mock_redis_client = AsyncMock()
            mock_redis.return_value = mock_redis_client
            
            mock_kafka_consumer = Mock()
            mock_kafka.return_value = mock_kafka_consumer
            
            mock_chunker_instance = Mock()
            mock_chunker.return_value = mock_chunker_instance
            
            mock_embedding_instance = Mock()
            mock_embedding.return_value = mock_embedding_instance
            
            mock_vectordb_instance = Mock()
            mock_vectordb.return_value = mock_vectordb_instance
            
            yield {
                'redis': mock_redis_client,
                'kafka': mock_kafka_consumer,
                'chunker': mock_chunker_instance,
                'embedding': mock_embedding_instance,
                'vectordb': mock_vectordb_instance
            }
    
    @pytest.mark.asyncio
    async def test_service_initialization(self, mock_dependencies):
        """Test RAG service initialization"""
        service = RAGIndexService()
        
        assert service.config is not None
        assert service.chunker is not None
        assert service.embedding_service is not None
        assert service.vector_db is not None
    
    @pytest.mark.asyncio
    async def test_extract_content_chat_message(self, mock_dependencies):
        """Test content extraction from chat message"""
        service = RAGIndexService()
        
        message = ProcessedMessage(
            id="msg-001",
            original_id="orig-001",
            source="api",
            type="chat_message",
            timestamp="2023-01-01T00:00:00Z",
            processed_at="2023-01-01T00:00:01Z",
            data={"content": "Hello world"},
            metadata={},
            idempotency_key="key-001",
            validation_status="valid",
            normalization_applied=[]
        )
        
        content = service._extract_content(message)
        assert content == "Hello world"
    
    @pytest.mark.asyncio
    async def test_extract_content_document(self, mock_dependencies):
        """Test content extraction from document"""
        service = RAGIndexService()
        
        message = ProcessedMessage(
            id="doc-001",
            original_id="orig-001",
            source="api",
            type="document",
            timestamp="2023-01-01T00:00:00Z",
            processed_at="2023-01-01T00:00:01Z",
            data={"text": "Document content"},
            metadata={},
            idempotency_key="key-001",
            validation_status="valid",
            normalization_applied=[]
        )
        
        content = service._extract_content(message)
        assert content == "Document content"
    
    @pytest.mark.asyncio
    async def test_extract_content_user_event(self, mock_dependencies):
        """Test content extraction from user event"""
        service = RAGIndexService()
        
        message = ProcessedMessage(
            id="evt-001",
            original_id="orig-001",
            source="api",
            type="user_event",
            timestamp="2023-01-01T00:00:00Z",
            processed_at="2023-01-01T00:00:01Z",
            data={
                "event_name": "user_login",
                "properties": {"device": "mobile"}
            },
            metadata={},
            idempotency_key="key-001",
            validation_status="valid",
            normalization_applied=[]
        )
        
        content = service._extract_content(message)
        assert "user_login" in content
        assert "mobile" in content
    
    @pytest.mark.asyncio
    async def test_process_single_message(self, mock_dependencies):
        """Test processing a single message"""
        service = RAGIndexService()
        
        # Setup mocks
        mock_dependencies['redis'].exists.return_value = False  # Not already indexed
        
        mock_chunks = [
            DocumentChunk("chunk1", "msg-001", "Content", {}, 0, 1, [0.1, 0.2, 0.3])
        ]
        mock_dependencies['chunker'].chunk_document.return_value = mock_chunks
        mock_dependencies['embedding'].embed_chunks.return_value = mock_chunks
        mock_dependencies['vectordb'].upsert_chunks.return_value = True
        
        message_data = {
            "id": "msg-001",
            "original_id": "orig-001",
            "source": "api",
            "type": "chat_message",
            "timestamp": "2023-01-01T00:00:00Z",
            "processed_at": "2023-01-01T00:00:01Z",
            "data": {"content": "Test message"},
            "metadata": {},
            "idempotency_key": "key-001",
            "validation_status": "valid",
            "normalization_applied": []
        }
        
        await service._process_single_message(message_data)
        
        # Verify processing steps
        mock_dependencies['chunker'].chunk_document.assert_called_once()
        mock_dependencies['embedding'].embed_chunks.assert_called_once()
        mock_dependencies['vectordb'].upsert_chunks.assert_called_once()
        mock_dependencies['redis'].setex.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_process_duplicate_message(self, mock_dependencies):
        """Test processing a duplicate message"""
        service = RAGIndexService()
        
        # Setup mocks - message already exists
        mock_dependencies['redis'].exists.return_value = True
        
        message_data = {
            "id": "msg-001",
            "original_id": "orig-001",
            "source": "api",
            "type": "chat_message",
            "timestamp": "2023-01-01T00:00:00Z",
            "processed_at": "2023-01-01T00:00:01Z",
            "data": {"content": "Test message"},
            "metadata": {},
            "idempotency_key": "key-001",
            "validation_status": "valid",
            "normalization_applied": []
        }
        
        await service._process_single_message(message_data)
        
        # Should not process duplicate
        mock_dependencies['chunker'].chunk_document.assert_not_called()
        mock_dependencies['embedding'].embed_chunks.assert_not_called()
        mock_dependencies['vectordb'].upsert_chunks.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_search(self, mock_dependencies):
        """Test document search"""
        service = RAGIndexService()
        
        # Setup mocks
        mock_dependencies['embedding'].generate_embeddings.return_value = [[0.1, 0.2, 0.3]]
        mock_dependencies['vectordb'].search_similar.return_value = [
            {
                "chunk_id": "chunk1",
                "document_id": "doc1",
                "content": "Test content",
                "score": 0.95
            }
        ]
        
        results = await service.search("test query", top_k=5)
        
        assert len(results) == 1
        assert results[0]["chunk_id"] == "chunk1"
        assert results[0]["score"] == 0.95
        
        mock_dependencies['embedding'].generate_embeddings.assert_called_once_with(["test query"])
        mock_dependencies['vectordb'].search_similar.assert_called_once()

class TestBlueGreenDeployment:
    """Test blue/green deployment functionality"""
    
    @pytest.fixture
    def mock_redis_and_milvus(self):
        """Mock Redis and Milvus for deployment tests"""
        with patch('blue_green_deployment.redis.from_url') as mock_redis, \
             patch('blue_green_deployment.connections') as mock_conn, \
             patch('blue_green_deployment.utility') as mock_utility, \
             patch('blue_green_deployment.Collection') as mock_collection:
            
            mock_redis_client = AsyncMock()
            mock_redis.return_value = mock_redis_client
            
            yield {
                'redis': mock_redis_client,
                'connections': mock_conn,
                'utility': mock_utility,
                'Collection': mock_collection
            }
    
    @pytest.mark.asyncio
    async def test_create_new_index(self, mock_redis_and_milvus):
        """Test creating a new index"""
        manager = BlueGreenDeploymentManager(
            redis_url="redis://localhost",
            milvus_host="localhost",
            milvus_port=19530,
            collection_prefix="test_collection"
        )
        
        # No active index exists
        mock_redis_and_milvus['redis'].get.return_value = None
        
        metadata, collection_name = await manager.create_new_index("v2.0")
        
        assert metadata.version == "v2.0"
        assert metadata.color == IndexColor.BLUE
        assert metadata.status == DeploymentStatus.PREPARING
        assert "test_collection_blue_v2.0" in collection_name
        
        # Verify Redis was called to store metadata
        mock_redis_and_milvus['redis'].setex.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_update_index_status(self, mock_redis_and_milvus):
        """Test updating index status"""
        manager = BlueGreenDeploymentManager(
            redis_url="redis://localhost",
            milvus_host="localhost",
            milvus_port=19530,
            collection_prefix="test_collection"
        )
        
        # Mock existing metadata
        existing_metadata = IndexMetadata("v1.0", IndexColor.BLUE, DeploymentStatus.BUILDING)
        mock_redis_and_milvus['redis'].get.return_value = json.dumps(existing_metadata.to_dict())
        
        await manager.update_index_status(
            "test_collection_blue_v1.0",
            DeploymentStatus.READY,
            document_count=1000,
            health_score=0.95
        )
        
        # Verify Redis was called to update metadata
        mock_redis_and_milvus['redis'].setex.assert_called_once()
        
        # Check the updated data
        call_args = mock_redis_and_milvus['redis'].setex.call_args
        updated_data = json.loads(call_args[0][2])
        assert updated_data['status'] == 'ready'
        assert updated_data['document_count'] == 1000
        assert updated_data['health_score'] == 0.95
    
    @pytest.mark.asyncio
    async def test_health_check_success(self, mock_redis_and_milvus):
        """Test successful health check"""
        manager = BlueGreenDeploymentManager(
            redis_url="redis://localhost",
            milvus_host="localhost",
            milvus_port=19530,
            collection_prefix="test_collection"
        )
        
        # Mock collection exists and is healthy
        mock_redis_and_milvus['utility'].has_collection.return_value = True
        
        mock_collection = Mock()
        mock_collection.is_loaded = True
        mock_collection.num_entities = 1000
        mock_collection.search.return_value = [[Mock()]]  # Successful search
        mock_redis_and_milvus['Collection'].return_value = mock_collection
        
        is_healthy, health_score, details = await manager.run_health_check("test_collection")
        
        assert is_healthy is True
        assert health_score >= 0.7
        assert details['collection_exists'] is True
        assert details['collection_loaded'] is True
        assert details['num_entities'] == 1000
        assert details['search_functional'] is True
    
    @pytest.mark.asyncio
    async def test_health_check_failure(self, mock_redis_and_milvus):
        """Test failed health check"""
        manager = BlueGreenDeploymentManager(
            redis_url="redis://localhost",
            milvus_host="localhost",
            milvus_port=19530,
            collection_prefix="test_collection"
        )
        
        # Mock collection doesn't exist
        mock_redis_and_milvus['utility'].has_collection.return_value = False
        
        is_healthy, health_score, details = await manager.run_health_check("nonexistent_collection")
        
        assert is_healthy is False
        assert health_score == 0.0
        assert "error" in details
    
    @pytest.mark.asyncio
    async def test_atomic_swap_success(self, mock_redis_and_milvus):
        """Test successful atomic swap"""
        manager = BlueGreenDeploymentManager(
            redis_url="redis://localhost",
            milvus_host="localhost",
            milvus_port=19530,
            collection_prefix="test_collection"
        )
        
        # Mock new index metadata
        new_metadata = IndexMetadata("v2.0", IndexColor.GREEN, DeploymentStatus.READY)
        mock_redis_and_milvus['redis'].get.return_value = json.dumps(new_metadata.to_dict())
        
        # Mock successful health check
        with patch.object(manager, 'run_health_check') as mock_health:
            mock_health.return_value = (True, 0.95, {"status": "healthy"})
            
            # Mock current active index
            with patch.object(manager, 'get_active_index') as mock_get_active:
                mock_get_active.return_value = IndexMetadata("v1.0", IndexColor.BLUE, DeploymentStatus.ACTIVE)
                
                # Mock Redis pipeline
                mock_pipeline = AsyncMock()
                mock_redis_and_milvus['redis'].pipeline.return_value.__aenter__.return_value = mock_pipeline
                
                result = await manager.perform_atomic_swap("test_collection_green_v2.0")
                
                assert result is True
                mock_health.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_rollback_deployment(self, mock_redis_and_milvus):
        """Test deployment rollback"""
        manager = BlueGreenDeploymentManager(
            redis_url="redis://localhost",
            milvus_host="localhost",
            milvus_port=19530,
            collection_prefix="test_collection"
        )
        
        # Mock active and standby indices
        active_metadata = IndexMetadata("v2.0", IndexColor.GREEN, DeploymentStatus.ACTIVE)
        standby_metadata = IndexMetadata("v1.0", IndexColor.BLUE, DeploymentStatus.DEPRECATED)
        
        with patch.object(manager, 'get_active_index') as mock_get_active, \
             patch.object(manager, 'get_standby_index') as mock_get_standby, \
             patch.object(manager, 'run_health_check') as mock_health:
            
            mock_get_active.return_value = active_metadata
            mock_get_standby.return_value = standby_metadata
            mock_health.return_value = (True, 0.90, {"status": "healthy"})
            
            # Mock Redis pipeline
            mock_pipeline = AsyncMock()
            mock_redis_and_milvus['redis'].pipeline.return_value.__aenter__.return_value = mock_pipeline
            
            result = await manager.rollback_deployment()
            
            assert result is True
            mock_health.assert_called_once()

if __name__ == "__main__":
    pytest.main([__file__, "-v"])

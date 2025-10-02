#!/usr/bin/env python3
"""
Unit tests for ChatOps Engine
"""

import pytest
import asyncio
import json
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime

# Import the classes we want to test
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '../../services/chatops-engine'))

from main import (
    ChatMessage, Intent, RAGDocument, ChatRequest,
    NLPProcessor, RAGEngine, ChatOpsEngine
)

class TestChatMessage:
    """Test cases for ChatMessage"""
    
    def test_create_chat_message(self):
        """Test creating a chat message"""
        message = ChatMessage(
            id="msg_123",
            session_id="session_123",
            user_id="user_123",
            message="What is the system status?",
            timestamp=datetime.now(),
            intent="system_status",
            entities={"service": "all"},
            response="System is healthy"
        )
        
        assert message.id == "msg_123"
        assert message.session_id == "session_123"
        assert message.user_id == "user_123"
        assert message.message == "What is the system status?"
        assert message.intent == "system_status"
        assert message.entities == {"service": "all"}
        assert message.response == "System is healthy"
        
    def test_chat_message_defaults(self):
        """Test chat message default values"""
        message = ChatMessage(
            id="msg_123",
            session_id="session_123",
            user_id="user_123",
            message="Test message",
            timestamp=datetime.now()
        )
        
        assert message.entities == {}
        assert message.intent is None
        assert message.response is None

class TestIntent:
    """Test cases for Intent"""
    
    def test_create_intent(self):
        """Test creating an intent"""
        intent = Intent(
            name="system_status",
            confidence=0.95,
            entities={"service": "payment"},
            parameters={"timeout": 30}
        )
        
        assert intent.name == "system_status"
        assert intent.confidence == 0.95
        assert intent.entities == {"service": "payment"}
        assert intent.parameters == {"timeout": 30}
        
    def test_intent_defaults(self):
        """Test intent default values"""
        intent = Intent(
            name="test_intent",
            confidence=0.8,
            entities={}
        )
        
        assert intent.parameters == {}

class TestRAGDocument:
    """Test cases for RAGDocument"""
    
    def test_create_rag_document(self):
        """Test creating a RAG document"""
        doc = RAGDocument(
            id="doc_123",
            title="System Architecture",
            content="The system consists of microservices...",
            source="documentation",
            metadata={"category": "architecture", "priority": "high"},
            embedding=[0.1, 0.2, 0.3]
        )
        
        assert doc.id == "doc_123"
        assert doc.title == "System Architecture"
        assert doc.content.startswith("The system consists")
        assert doc.source == "documentation"
        assert doc.metadata["category"] == "architecture"
        assert doc.embedding == [0.1, 0.2, 0.3]

class TestNLPProcessor:
    """Test cases for NLPProcessor"""
    
    @pytest.fixture
    def nlp_processor(self):
        """Create NLP processor instance for testing"""
        processor = NLPProcessor()
        # Mock the embedding model to avoid loading actual model
        processor.embedding_model = Mock()
        processor.embedding_model.encode = Mock(return_value=[0.1, 0.2, 0.3])
        return processor
    
    @pytest.mark.asyncio
    async def test_initialize_nlp_processor(self):
        """Test NLP processor initialization"""
        processor = NLPProcessor()
        
        with patch('sentence_transformers.SentenceTransformer') as mock_transformer:
            mock_model = Mock()
            mock_transformer.return_value = mock_model
            
            await processor.initialize()
            
            assert processor.embedding_model == mock_model
            assert len(processor.intent_patterns) > 0
            assert 'system_status' in processor.intent_patterns
            assert 'troubleshoot' in processor.intent_patterns
            
    @pytest.mark.asyncio
    async def test_parse_intent_system_status(self, nlp_processor):
        """Test parsing system status intent"""
        await nlp_processor.initialize()
        
        messages = [
            "What is the system status?",
            "Check system health",
            "How is the system doing?",
            "Is the system up?"
        ]
        
        for message in messages:
            intent = await nlp_processor.parse_intent(message)
            assert intent.name == 'system_status'
            assert intent.confidence == 0.8
            
    @pytest.mark.asyncio
    async def test_parse_intent_saga_status(self, nlp_processor):
        """Test parsing saga status intent"""
        await nlp_processor.initialize()
        
        messages = [
            "Show me saga status",
            "What is the transaction status?",
            "Check workflow status",
            "Display saga information"
        ]
        
        for message in messages:
            intent = await nlp_processor.parse_intent(message)
            assert intent.name == 'saga_status'
            assert intent.confidence == 0.8
            
    @pytest.mark.asyncio
    async def test_parse_intent_troubleshoot(self, nlp_processor):
        """Test parsing troubleshoot intent"""
        await nlp_processor.initialize()
        
        messages = [
            "Why did the saga fail?",
            "What went wrong with the payment?",
            "Help me troubleshoot this error",
            "Debug the system issue"
        ]
        
        for message in messages:
            intent = await nlp_processor.parse_intent(message)
            assert intent.name == 'troubleshoot'
            assert intent.confidence == 0.8
            
    @pytest.mark.asyncio
    async def test_parse_intent_execute_operation(self, nlp_processor):
        """Test parsing execute operation intent"""
        await nlp_processor.initialize()
        
        messages = [
            "Start saga payment_saga",
            "Run the workflow",
            "Execute the transaction",
            "Trigger the process"
        ]
        
        for message in messages:
            intent = await nlp_processor.parse_intent(message)
            assert intent.name == 'execute_operation'
            assert intent.confidence == 0.8
            
    @pytest.mark.asyncio
    async def test_parse_intent_general_query(self, nlp_processor):
        """Test parsing general query (default)"""
        await nlp_processor.initialize()
        
        intent = await nlp_processor.parse_intent("Hello, how are you?")
        assert intent.name == 'general_query'
        assert intent.confidence == 0.5
        
    @pytest.mark.asyncio
    async def test_extract_entities_saga_id(self, nlp_processor):
        """Test extracting saga ID entity"""
        await nlp_processor.initialize()
        
        entities = await nlp_processor._extract_entities("Start saga payment_saga", "execute_operation")
        assert entities.get('saga_id') == 'payment_saga'
        
        entities = await nlp_processor._extract_entities("Check saga_status for order-saga", "saga_status")
        assert entities.get('saga_id') == 'order-saga'
        
    @pytest.mark.asyncio
    async def test_extract_entities_service(self, nlp_processor):
        """Test extracting service entity"""
        await nlp_processor.initialize()
        
        entities = await nlp_processor._extract_entities("Check service payment-service", "system_status")
        assert entities.get('service') == 'payment-service'
        
    @pytest.mark.asyncio
    async def test_extract_entities_time_range(self, nlp_processor):
        """Test extracting time range entity"""
        await nlp_processor.initialize()
        
        test_cases = [
            ("Show metrics for last 2 hours", {"value": 2, "unit": "hours"}),
            ("Data from past 30 minutes", {"value": 30, "unit": "minutes"}),
            ("Statistics for last 7 days", {"value": 7, "unit": "days"})
        ]
        
        for message, expected in test_cases:
            entities = await nlp_processor._extract_entities(message, "metrics")
            assert entities.get('time_range') == expected
            
    @pytest.mark.asyncio
    async def test_generate_embedding(self, nlp_processor):
        """Test embedding generation"""
        embedding = await nlp_processor.generate_embedding("Test text")
        assert embedding == [0.1, 0.2, 0.3]  # Mocked return value

class TestRAGEngine:
    """Test cases for RAGEngine"""
    
    @pytest.fixture
    def rag_engine(self):
        """Create RAG engine instance for testing"""
        mock_redis = Mock()
        return RAGEngine(mock_redis)
    
    @pytest.mark.asyncio
    async def test_initialize_rag_engine(self, rag_engine):
        """Test RAG engine initialization"""
        mock_nlp = Mock()
        mock_nlp.generate_embedding = AsyncMock(return_value=[0.1, 0.2, 0.3])
        
        await rag_engine.initialize(mock_nlp)
        
        assert rag_engine.nlp_processor == mock_nlp
        assert len(rag_engine.knowledge_base) > 0
        assert 'system_architecture' in rag_engine.knowledge_base
        assert 'saga_troubleshooting' in rag_engine.knowledge_base
        
    @pytest.mark.asyncio
    async def test_retrieve_relevant_docs(self, rag_engine):
        """Test retrieving relevant documents"""
        # Initialize with mock NLP processor
        mock_nlp = Mock()
        mock_nlp.generate_embedding = AsyncMock(return_value=[0.1, 0.2, 0.3])
        await rag_engine.initialize(mock_nlp)
        
        # Mock cosine similarity to return predictable results
        with patch.object(rag_engine, '_cosine_similarity') as mock_similarity:
            mock_similarity.side_effect = [0.9, 0.7, 0.5, 0.3]  # Decreasing similarity
            
            docs = await rag_engine.retrieve_relevant_docs("system architecture", top_k=2)
            
            assert len(docs) == 2
            # Should return docs in order of similarity
            assert docs[0].id == 'system_architecture'  # Highest similarity
            
    def test_cosine_similarity(self, rag_engine):
        """Test cosine similarity calculation"""
        vec1 = [1.0, 0.0, 0.0]
        vec2 = [1.0, 0.0, 0.0]
        similarity = rag_engine._cosine_similarity(vec1, vec2)
        assert similarity == 1.0  # Identical vectors
        
        vec1 = [1.0, 0.0, 0.0]
        vec2 = [0.0, 1.0, 0.0]
        similarity = rag_engine._cosine_similarity(vec1, vec2)
        assert similarity == 0.0  # Orthogonal vectors
        
        vec1 = [0.0, 0.0, 0.0]
        vec2 = [1.0, 0.0, 0.0]
        similarity = rag_engine._cosine_similarity(vec1, vec2)
        assert similarity == 0.0  # Zero vector

class TestChatOpsEngine:
    """Test cases for ChatOpsEngine"""
    
    @pytest.fixture
    def chatops_engine(self):
        """Create ChatOps engine instance for testing"""
        return ChatOpsEngine()
    
    @pytest.mark.asyncio
    async def test_initialize_chatops_engine(self, chatops_engine):
        """Test ChatOps engine initialization"""
        with patch('redis.from_url') as mock_redis:
            with patch.object(chatops_engine.nlp_processor, 'initialize', new_callable=AsyncMock):
                with patch('httpx.AsyncClient') as mock_client:
                    mock_rag_engine = Mock()
                    mock_rag_engine.initialize = AsyncMock()
                    
                    with patch('main.RAGEngine', return_value=mock_rag_engine):
                        await chatops_engine.initialize()
                        
                        mock_redis.assert_called_once()
                        assert chatops_engine.redis_client is not None
                        assert len(chatops_engine.service_clients) > 0
                        
    @pytest.mark.asyncio
    async def test_process_message_system_status(self, chatops_engine):
        """Test processing system status message"""
        # Setup mocks
        chatops_engine.nlp_processor = Mock()
        chatops_engine.nlp_processor.parse_intent = AsyncMock(return_value=Intent(
            name='system_status',
            confidence=0.9,
            entities={}
        ))
        
        # Mock service health checks
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.elapsed.total_seconds.return_value = 0.1
        
        mock_client = Mock()
        mock_client.get = AsyncMock(return_value=mock_response)
        chatops_engine.service_clients = {'test_service': mock_client}
        
        request = ChatRequest(
            session_id='session_123',
            user_id='user_123',
            message='What is the system status?'
        )
        
        response = await chatops_engine.process_message(request)
        
        assert response['intent'] == 'system_status'
        assert 'System Status Report' in response['response']
        assert response['processing_time'] > 0
        
    @pytest.mark.asyncio
    async def test_process_message_saga_status(self, chatops_engine):
        """Test processing saga status message"""
        # Setup mocks
        chatops_engine.nlp_processor = Mock()
        chatops_engine.nlp_processor.parse_intent = AsyncMock(return_value=Intent(
            name='saga_status',
            confidence=0.9,
            entities={}
        ))
        
        # Mock orchestrator response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'executions': [
                {
                    'id': 'exec_123',
                    'saga_id': 'payment_saga',
                    'status': 'running',
                    'started_at': '2023-01-01T00:00:00',
                    'ml_prediction': {
                        'risk_level': 'low',
                        'failure_probability': 0.1
                    }
                }
            ]
        }
        
        mock_client = Mock()
        mock_client.get = AsyncMock(return_value=mock_response)
        chatops_engine.service_clients = {'intelligent_orchestrator': mock_client}
        
        request = ChatRequest(
            session_id='session_123',
            user_id='user_123',
            message='Show saga status'
        )
        
        response = await chatops_engine.process_message(request)
        
        assert response['intent'] == 'saga_status'
        assert 'Active Saga Executions' in response['response']
        assert 'exec_123' in response['response']
        
    @pytest.mark.asyncio
    async def test_process_message_troubleshoot(self, chatops_engine):
        """Test processing troubleshoot message"""
        # Setup mocks
        chatops_engine.nlp_processor = Mock()
        chatops_engine.nlp_processor.parse_intent = AsyncMock(return_value=Intent(
            name='troubleshoot',
            confidence=0.9,
            entities={'saga_id': 'payment_saga'}
        ))
        
        # Mock RAG engine
        mock_rag_doc = RAGDocument(
            id='troubleshoot_doc',
            title='Troubleshooting Guide',
            content='Common issues and solutions...',
            source='runbook',
            metadata={}
        )
        
        chatops_engine.rag_engine = Mock()
        chatops_engine.rag_engine.retrieve_relevant_docs = AsyncMock(return_value=[mock_rag_doc])
        
        request = ChatRequest(
            session_id='session_123',
            user_id='user_123',
            message='Why did payment_saga fail?'
        )
        
        response = await chatops_engine.process_message(request)
        
        assert response['intent'] == 'troubleshoot'
        assert 'Troubleshooting Assistance' in response['response']
        assert 'payment_saga' in response['response']
        
    @pytest.mark.asyncio
    async def test_process_message_execute_operation(self, chatops_engine):
        """Test processing execute operation message"""
        # Setup mocks
        chatops_engine.nlp_processor = Mock()
        chatops_engine.nlp_processor.parse_intent = AsyncMock(return_value=Intent(
            name='execute_operation',
            confidence=0.9,
            entities={'saga_id': 'payment_saga'}
        ))
        
        # Mock orchestrator response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'execution_id': 'exec_456',
            'saga_id': 'payment_saga',
            'status': 'running',
            'ml_prediction': {
                'risk_level': 'medium',
                'failure_probability': 0.3,
                'recommendations': ['Increase timeout values']
            }
        }
        
        mock_client = Mock()
        mock_client.post = AsyncMock(return_value=mock_response)
        chatops_engine.service_clients = {'intelligent_orchestrator': mock_client}
        
        request = ChatRequest(
            session_id='session_123',
            user_id='user_123',
            message='Start saga payment_saga'
        )
        
        response = await chatops_engine.process_message(request)
        
        assert response['intent'] == 'execute_operation'
        assert 'Saga Started Successfully' in response['response']
        assert 'exec_456' in response['response']
        
    @pytest.mark.asyncio
    async def test_process_message_error_handling(self, chatops_engine):
        """Test error handling in message processing"""
        # Setup mocks to raise exception
        chatops_engine.nlp_processor = Mock()
        chatops_engine.nlp_processor.parse_intent = AsyncMock(side_effect=Exception("Test error"))
        
        request = ChatRequest(
            session_id='session_123',
            user_id='user_123',
            message='Test message'
        )
        
        response = await chatops_engine.process_message(request)
        
        assert response['intent'] == 'error'
        assert 'error processing your request' in response['response']
        assert 'Test error' in response['response']
        
    @pytest.mark.asyncio
    async def test_session_management(self, chatops_engine):
        """Test chat session management"""
        chatops_engine.nlp_processor = Mock()
        chatops_engine.nlp_processor.parse_intent = AsyncMock(return_value=Intent(
            name='general_query',
            confidence=0.5,
            entities={}
        ))
        
        chatops_engine.rag_engine = Mock()
        chatops_engine.rag_engine.retrieve_relevant_docs = AsyncMock(return_value=[])
        
        request = ChatRequest(
            session_id='new_session',
            user_id='user_123',
            message='Hello'
        )
        
        # Process first message
        await chatops_engine.process_message(request)
        
        # Check session was created
        assert 'new_session' in chatops_engine.active_sessions
        session = chatops_engine.active_sessions['new_session']
        assert session['user_id'] == 'user_123'
        assert len(session['messages']) == 1
        
        # Process second message
        request.message = 'How are you?'
        await chatops_engine.process_message(request)
        
        # Check message was added to existing session
        assert len(session['messages']) == 2

if __name__ == '__main__':
    pytest.main([__file__, '-v'])

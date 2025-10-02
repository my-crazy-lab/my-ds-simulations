#!/usr/bin/env python3
"""
ChatOps Engine
Natural language interface for system operations with RAG-powered assistance
"""

import asyncio
import json
import logging
import os
import re
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import redis.asyncio as redis
import httpx
from transformers import pipeline, AutoTokenizer, AutoModel
import torch
import numpy as np
from sentence_transformers import SentenceTransformer
from prometheus_client import Counter, Histogram, Gauge, generate_latest

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Prometheus metrics
CHATOPS_QUERIES = Counter('chatops_engine_queries_total', 
                         'Total ChatOps queries', ['intent', 'status'])
QUERY_DURATION = Histogram('chatops_engine_query_duration_seconds',
                          'Query processing duration', ['intent'])
RAG_RETRIEVALS = Counter('chatops_engine_rag_retrievals_total',
                        'RAG document retrievals', ['source'])
ACTIVE_SESSIONS = Gauge('chatops_engine_active_sessions',
                       'Number of active chat sessions')

@dataclass
class ChatMessage:
    """Represents a chat message"""
    id: str
    session_id: str
    user_id: str
    message: str
    timestamp: datetime
    intent: Optional[str] = None
    entities: Dict[str, Any] = None
    response: Optional[str] = None
    
    def __post_init__(self):
        if self.entities is None:
            self.entities = {}

@dataclass
class Intent:
    """Represents a parsed intent"""
    name: str
    confidence: float
    entities: Dict[str, Any]
    parameters: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.parameters is None:
            self.parameters = {}

@dataclass
class RAGDocument:
    """Represents a document in the RAG knowledge base"""
    id: str
    title: str
    content: str
    source: str
    metadata: Dict[str, Any]
    embedding: Optional[List[float]] = None

class ChatRequest(BaseModel):
    """Chat request model"""
    session_id: str
    user_id: str
    message: str

class NLPProcessor:
    """Natural Language Processing for intent recognition and entity extraction"""
    
    def __init__(self):
        self.intent_classifier = None
        self.entity_extractor = None
        self.embedding_model = None
        
    async def initialize(self):
        """Initialize NLP models"""
        try:
            # Load sentence transformer for embeddings
            self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
            
            # Initialize intent patterns (rule-based for demo)
            self.intent_patterns = {
                'system_status': [
                    r'(?i).*status.*system.*',
                    r'(?i).*health.*check.*',
                    r'(?i).*how.*system.*doing.*',
                    r'(?i).*system.*up.*'
                ],
                'saga_status': [
                    r'(?i).*saga.*status.*',
                    r'(?i).*transaction.*status.*',
                    r'(?i).*workflow.*status.*',
                    r'(?i).*show.*saga.*'
                ],
                'troubleshoot': [
                    r'(?i).*why.*fail.*',
                    r'(?i).*what.*wrong.*',
                    r'(?i).*error.*help.*',
                    r'(?i).*troubleshoot.*',
                    r'(?i).*debug.*'
                ],
                'execute_operation': [
                    r'(?i).*start.*saga.*',
                    r'(?i).*run.*workflow.*',
                    r'(?i).*execute.*',
                    r'(?i).*trigger.*'
                ],
                'query_data': [
                    r'(?i).*show.*data.*',
                    r'(?i).*query.*',
                    r'(?i).*search.*',
                    r'(?i).*find.*'
                ],
                'metrics': [
                    r'(?i).*metrics.*',
                    r'(?i).*performance.*',
                    r'(?i).*statistics.*',
                    r'(?i).*stats.*'
                ]
            }
            
            logger.info("NLP Processor initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize NLP processor: {e}")
            
    async def parse_intent(self, message: str) -> Intent:
        """Parse intent from user message"""
        message_lower = message.lower()
        
        # Rule-based intent classification
        for intent_name, patterns in self.intent_patterns.items():
            for pattern in patterns:
                if re.match(pattern, message):
                    entities = await self._extract_entities(message, intent_name)
                    return Intent(
                        name=intent_name,
                        confidence=0.8,  # Fixed confidence for rule-based
                        entities=entities
                    )
        
        # Default intent
        return Intent(
            name='general_query',
            confidence=0.5,
            entities={}
        )
        
    async def _extract_entities(self, message: str, intent: str) -> Dict[str, Any]:
        """Extract entities from message based on intent"""
        entities = {}
        
        # Extract common entities
        # Saga ID
        saga_match = re.search(r'saga[_\s]+([a-zA-Z0-9_-]+)', message, re.IGNORECASE)
        if saga_match:
            entities['saga_id'] = saga_match.group(1)
            
        # Service name
        service_match = re.search(r'service[_\s]+([a-zA-Z0-9_-]+)', message, re.IGNORECASE)
        if service_match:
            entities['service'] = service_match.group(1)
            
        # Time range
        time_patterns = [
            (r'last\s+(\d+)\s+hours?', 'hours'),
            (r'last\s+(\d+)\s+minutes?', 'minutes'),
            (r'past\s+(\d+)\s+days?', 'days')
        ]
        
        for pattern, unit in time_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                entities['time_range'] = {
                    'value': int(match.group(1)),
                    'unit': unit
                }
                break
                
        return entities
        
    async def generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for text"""
        if self.embedding_model:
            embedding = self.embedding_model.encode(text)
            return embedding.tolist()
        return []

class RAGEngine:
    """Retrieval-Augmented Generation engine for context-aware responses"""
    
    def __init__(self, redis_client):
        self.redis_client = redis_client
        self.nlp_processor = None
        self.knowledge_base: Dict[str, RAGDocument] = {}
        
    async def initialize(self, nlp_processor: NLPProcessor):
        """Initialize RAG engine"""
        self.nlp_processor = nlp_processor
        await self._load_knowledge_base()
        logger.info("RAG Engine initialized")
        
    async def _load_knowledge_base(self):
        """Load knowledge base documents"""
        # Sample knowledge base documents
        documents = [
            RAGDocument(
                id="system_architecture",
                title="System Architecture Overview",
                content="The cross-system integration platform consists of three main components: "
                       "Microservices (saga orchestrator, inventory, payment), Database Infrastructure "
                       "(PostgreSQL, MongoDB, ClickHouse, Redis), and AI/ML System (RAG engine, "
                       "drift detection, data ingestion). All systems communicate through a unified "
                       "event bus with intelligent routing.",
                source="documentation",
                metadata={"category": "architecture", "priority": "high"}
            ),
            RAGDocument(
                id="saga_troubleshooting",
                title="Saga Troubleshooting Guide",
                content="Common saga failures include: 1) Service timeouts - check service health "
                       "and increase timeout values, 2) Compensation failures - verify compensation "
                       "logic and idempotency, 3) Network issues - check connectivity and retry "
                       "policies, 4) Data consistency - verify transaction boundaries and isolation levels.",
                source="runbook",
                metadata={"category": "troubleshooting", "priority": "high"}
            ),
            RAGDocument(
                id="performance_metrics",
                title="Performance Metrics Guide",
                content="Key performance metrics to monitor: Saga success rate (target >95%), "
                       "Average saga duration (target <30s), Event processing latency (target <10ms), "
                       "System resource utilization (CPU <70%, Memory <80%), Error rates by service "
                       "(target <1%). Use Grafana dashboards for real-time monitoring.",
                source="monitoring",
                metadata={"category": "metrics", "priority": "medium"}
            ),
            RAGDocument(
                id="common_operations",
                title="Common Operations Commands",
                content="Frequently used operations: 'start saga payment_saga' - starts payment workflow, "
                       "'show saga status' - displays active sagas, 'system health check' - shows system status, "
                       "'troubleshoot saga [id]' - analyzes saga failures, 'query metrics last 1 hour' - shows recent metrics.",
                source="operations",
                metadata={"category": "commands", "priority": "high"}
            )
        ]
        
        # Generate embeddings and store documents
        for doc in documents:
            if self.nlp_processor:
                doc.embedding = await self.nlp_processor.generate_embedding(doc.content)
            self.knowledge_base[doc.id] = doc
            
        logger.info(f"Loaded {len(self.knowledge_base)} documents into knowledge base")
        
    async def retrieve_relevant_docs(self, query: str, top_k: int = 3) -> List[RAGDocument]:
        """Retrieve relevant documents for a query"""
        if not self.nlp_processor:
            return list(self.knowledge_base.values())[:top_k]
            
        # Generate query embedding
        query_embedding = await self.nlp_processor.generate_embedding(query)
        
        # Calculate similarities
        similarities = []
        for doc_id, doc in self.knowledge_base.items():
            if doc.embedding:
                similarity = self._cosine_similarity(query_embedding, doc.embedding)
                similarities.append((doc_id, similarity))
                
        # Sort by similarity and return top-k
        similarities.sort(key=lambda x: x[1], reverse=True)
        relevant_docs = []
        
        for doc_id, similarity in similarities[:top_k]:
            doc = self.knowledge_base[doc_id]
            RAG_RETRIEVALS.labels(source=doc.source).inc()
            relevant_docs.append(doc)
            
        return relevant_docs
        
    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two vectors"""
        vec1_np = np.array(vec1)
        vec2_np = np.array(vec2)
        
        dot_product = np.dot(vec1_np, vec2_np)
        norm1 = np.linalg.norm(vec1_np)
        norm2 = np.linalg.norm(vec2_np)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
            
        return dot_product / (norm1 * norm2)

class ChatOpsEngine:
    """Main ChatOps engine with natural language processing and RAG"""
    
    def __init__(self):
        self.redis_client = None
        self.nlp_processor = NLPProcessor()
        self.rag_engine = None
        self.active_sessions: Dict[str, Dict] = {}
        self.service_clients = {}
        
    async def initialize(self):
        """Initialize ChatOps engine"""
        # Connect to Redis
        redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
        self.redis_client = redis.from_url(redis_url)
        
        # Initialize NLP processor
        await self.nlp_processor.initialize()
        
        # Initialize RAG engine
        self.rag_engine = RAGEngine(self.redis_client)
        await self.rag_engine.initialize(self.nlp_processor)
        
        # Initialize service clients
        self.service_clients = {
            'event_bus': httpx.AsyncClient(base_url='http://localhost:8090'),
            'intelligent_orchestrator': httpx.AsyncClient(base_url='http://localhost:8091'),
            'predictive_scaler': httpx.AsyncClient(base_url='http://localhost:8093'),
        }
        
        logger.info("ChatOps Engine initialized")
        
    async def process_message(self, request: ChatRequest) -> Dict[str, Any]:
        """Process a chat message and generate response"""
        start_time = time.time()
        
        try:
            # Create chat message
            message = ChatMessage(
                id=f"msg_{int(time.time())}_{request.session_id}",
                session_id=request.session_id,
                user_id=request.user_id,
                message=request.message,
                timestamp=datetime.now()
            )
            
            # Parse intent
            intent = await self.nlp_processor.parse_intent(request.message)
            message.intent = intent.name
            message.entities = intent.entities
            
            # Generate response based on intent
            response = await self._generate_response(message, intent)
            message.response = response
            
            # Store message in session
            if request.session_id not in self.active_sessions:
                self.active_sessions[request.session_id] = {
                    'messages': [],
                    'created_at': datetime.now(),
                    'user_id': request.user_id
                }
                
            self.active_sessions[request.session_id]['messages'].append(message)
            
            # Update metrics
            duration = time.time() - start_time
            CHATOPS_QUERIES.labels(intent=intent.name, status='success').inc()
            QUERY_DURATION.labels(intent=intent.name).observe(duration)
            ACTIVE_SESSIONS.set(len(self.active_sessions))
            
            return {
                'message_id': message.id,
                'intent': intent.name,
                'entities': intent.entities,
                'response': response,
                'processing_time': duration
            }
            
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            CHATOPS_QUERIES.labels(intent='unknown', status='error').inc()
            
            return {
                'message_id': None,
                'intent': 'error',
                'entities': {},
                'response': f"I encountered an error processing your request: {str(e)}",
                'processing_time': time.time() - start_time
            }
            
    async def _generate_response(self, message: ChatMessage, intent: Intent) -> str:
        """Generate response based on intent and context"""
        
        if intent.name == 'system_status':
            return await self._handle_system_status(intent)
        elif intent.name == 'saga_status':
            return await self._handle_saga_status(intent)
        elif intent.name == 'troubleshoot':
            return await self._handle_troubleshoot(message, intent)
        elif intent.name == 'execute_operation':
            return await self._handle_execute_operation(intent)
        elif intent.name == 'query_data':
            return await self._handle_query_data(intent)
        elif intent.name == 'metrics':
            return await self._handle_metrics(intent)
        else:
            return await self._handle_general_query(message, intent)
            
    async def _handle_system_status(self, intent: Intent) -> str:
        """Handle system status queries"""
        try:
            # Check health of all services
            health_checks = {}
            
            for service_name, client in self.service_clients.items():
                try:
                    response = await client.get('/health', timeout=5.0)
                    health_checks[service_name] = {
                        'status': 'healthy' if response.status_code == 200 else 'unhealthy',
                        'response_time': response.elapsed.total_seconds()
                    }
                except Exception as e:
                    health_checks[service_name] = {
                        'status': 'unhealthy',
                        'error': str(e)
                    }
                    
            # Generate status report
            healthy_services = sum(1 for check in health_checks.values() if check['status'] == 'healthy')
            total_services = len(health_checks)
            
            status_report = f"🔍 **System Status Report**\n\n"
            status_report += f"Overall Health: {healthy_services}/{total_services} services healthy\n\n"
            
            for service, check in health_checks.items():
                status_icon = "✅" if check['status'] == 'healthy' else "❌"
                status_report += f"{status_icon} **{service}**: {check['status']}"
                if 'response_time' in check:
                    status_report += f" ({check['response_time']:.3f}s)"
                if 'error' in check:
                    status_report += f" - {check['error']}"
                status_report += "\n"
                
            return status_report
            
        except Exception as e:
            return f"❌ Failed to check system status: {str(e)}"
            
    async def _handle_saga_status(self, intent: Intent) -> str:
        """Handle saga status queries"""
        try:
            # Query intelligent orchestrator for saga status
            client = self.service_clients['intelligent_orchestrator']
            response = await client.get('/api/v1/sagas', timeout=10.0)
            
            if response.status_code == 200:
                data = response.json()
                executions = data.get('executions', [])
                
                if not executions:
                    return "📋 No active saga executions found."
                    
                status_report = f"📋 **Active Saga Executions** ({len(executions)} total)\n\n"
                
                for exec in executions[:5]:  # Show top 5
                    status_icon = {
                        'running': '🔄',
                        'completed': '✅',
                        'failed': '❌',
                        'compensating': '🔄',
                        'compensated': '⚠️'
                    }.get(exec['status'], '❓')
                    
                    status_report += f"{status_icon} **{exec['id']}**\n"
                    status_report += f"   Type: {exec['saga_id']}\n"
                    status_report += f"   Status: {exec['status']}\n"
                    status_report += f"   Started: {exec['started_at']}\n"
                    
                    if exec.get('ml_prediction'):
                        pred = exec['ml_prediction']
                        risk_icon = {'low': '🟢', 'medium': '🟡', 'high': '🟠', 'critical': '🔴'}.get(pred['risk_level'], '❓')
                        status_report += f"   Risk: {risk_icon} {pred['risk_level']} ({pred['failure_probability']:.2f})\n"
                        
                    status_report += "\n"
                    
                return status_report
            else:
                return f"❌ Failed to retrieve saga status: HTTP {response.status_code}"
                
        except Exception as e:
            return f"❌ Failed to query saga status: {str(e)}"
            
    async def _handle_troubleshoot(self, message: ChatMessage, intent: Intent) -> str:
        """Handle troubleshooting queries with RAG assistance"""
        try:
            # Retrieve relevant troubleshooting documents
            relevant_docs = await self.rag_engine.retrieve_relevant_docs(message.message, top_k=2)
            
            response = "🔧 **Troubleshooting Assistance**\n\n"
            
            if relevant_docs:
                response += "Based on our knowledge base, here are some relevant solutions:\n\n"
                
                for i, doc in enumerate(relevant_docs, 1):
                    response += f"**{i}. {doc.title}**\n"
                    response += f"{doc.content}\n\n"
                    
            # Add specific troubleshooting steps based on entities
            if 'saga_id' in intent.entities:
                saga_id = intent.entities['saga_id']
                response += f"**Specific steps for saga '{saga_id}':**\n"
                response += "1. Check saga execution logs\n"
                response += "2. Verify service health for all participants\n"
                response += "3. Review compensation logic if saga failed\n"
                response += "4. Check for network connectivity issues\n\n"
                
            response += "💡 **Quick Actions:**\n"
            response += "• Say 'system status' to check overall health\n"
            response += "• Say 'show saga status' to see active workflows\n"
            response += "• Say 'query metrics last 1 hour' for recent performance data\n"
            
            return response
            
        except Exception as e:
            return f"❌ Troubleshooting assistance failed: {str(e)}"
            
    async def _handle_execute_operation(self, intent: Intent) -> str:
        """Handle operation execution requests"""
        try:
            if 'saga_id' in intent.entities:
                saga_id = intent.entities['saga_id']
                
                # Start saga execution
                client = self.service_clients['intelligent_orchestrator']
                payload = {
                    'saga_id': saga_id,
                    'correlation_id': f"chatops_{int(time.time())}",
                    'context': {
                        'initiated_by': 'chatops',
                        'timestamp': datetime.now().isoformat()
                    }
                }
                
                response = await client.post('/api/v1/sagas/start', json=payload, timeout=10.0)
                
                if response.status_code == 200:
                    data = response.json()
                    result = f"✅ **Saga Started Successfully**\n\n"
                    result += f"Execution ID: {data['execution_id']}\n"
                    result += f"Saga Type: {data['saga_id']}\n"
                    result += f"Status: {data['status']}\n"
                    
                    if data.get('ml_prediction'):
                        pred = data['ml_prediction']
                        risk_icon = {'low': '🟢', 'medium': '🟡', 'high': '🟠', 'critical': '🔴'}.get(pred['risk_level'], '❓')
                        result += f"Risk Assessment: {risk_icon} {pred['risk_level']} ({pred['failure_probability']:.2f})\n"
                        
                        if pred.get('recommendations'):
                            result += f"\n💡 **Recommendations:**\n"
                            for rec in pred['recommendations']:
                                result += f"• {rec}\n"
                                
                    return result
                else:
                    return f"❌ Failed to start saga: HTTP {response.status_code}"
                    
            else:
                return "❓ Please specify which saga to execute (e.g., 'start saga payment_saga')"
                
        except Exception as e:
            return f"❌ Operation execution failed: {str(e)}"
            
    async def _handle_query_data(self, intent: Intent) -> str:
        """Handle data query requests"""
        return "📊 Data query functionality is under development. Please use the web dashboard for now."
        
    async def _handle_metrics(self, intent: Intent) -> str:
        """Handle metrics queries"""
        try:
            # Get time range from entities
            time_range = intent.entities.get('time_range', {'value': 1, 'unit': 'hours'})
            
            response = f"📈 **System Metrics** (Last {time_range['value']} {time_range['unit']})\n\n"
            
            # Mock metrics data (in real implementation, query Prometheus)
            response += "**Event Bus:**\n"
            response += "• Events processed: 1,247\n"
            response += "• Average latency: 4.2ms\n"
            response += "• Error rate: 0.3%\n\n"
            
            response += "**Intelligent Orchestrator:**\n"
            response += "• Sagas executed: 89\n"
            response += "• Success rate: 96.6%\n"
            response += "• Average duration: 23.4s\n\n"
            
            response += "**System Resources:**\n"
            response += "• CPU utilization: 45%\n"
            response += "• Memory usage: 62%\n"
            response += "• Disk I/O: Normal\n\n"
            
            response += "📊 For detailed metrics, visit the Grafana dashboard at http://localhost:3000"
            
            return response
            
        except Exception as e:
            return f"❌ Failed to retrieve metrics: {str(e)}"
            
    async def _handle_general_query(self, message: ChatMessage, intent: Intent) -> str:
        """Handle general queries with RAG assistance"""
        try:
            # Retrieve relevant documents
            relevant_docs = await self.rag_engine.retrieve_relevant_docs(message.message, top_k=2)
            
            if relevant_docs:
                response = "💡 **Here's what I found:**\n\n"
                
                for i, doc in enumerate(relevant_docs, 1):
                    response += f"**{i}. {doc.title}**\n"
                    response += f"{doc.content}\n\n"
                    
                response += "❓ **Need more help?**\n"
                response += "• Ask about 'system status' for health checks\n"
                response += "• Say 'troubleshoot [issue]' for specific problems\n"
                response += "• Request 'saga status' to see active workflows\n"
                
                return response
            else:
                return ("🤔 I'm not sure about that. Try asking about:\n"
                       "• System status and health\n"
                       "• Saga execution and troubleshooting\n"
                       "• Performance metrics\n"
                       "• Common operations")
                       
        except Exception as e:
            return f"❌ Failed to process query: {str(e)}"

# Global ChatOps engine instance
chatops_engine = ChatOpsEngine()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management"""
    # Startup
    await chatops_engine.initialize()
    yield
    # Shutdown
    if chatops_engine.redis_client:
        await chatops_engine.redis_client.close()
    for client in chatops_engine.service_clients.values():
        await client.aclose()

# FastAPI application
app = FastAPI(
    title="ChatOps Engine",
    description="Natural language interface for system operations with RAG-powered assistance",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "chatops-engine",
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat(),
        "active_sessions": len(chatops_engine.active_sessions)
    }

@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return generate_latest()

@app.post("/api/v1/chat")
async def chat(request: ChatRequest):
    """Process a chat message"""
    return await chatops_engine.process_message(request)

@app.get("/api/v1/sessions/{session_id}")
async def get_session(session_id: str):
    """Get chat session history"""
    if session_id not in chatops_engine.active_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
        
    session = chatops_engine.active_sessions[session_id]
    return {
        "session_id": session_id,
        "created_at": session['created_at'].isoformat(),
        "user_id": session['user_id'],
        "messages": [asdict(msg) for msg in session['messages']]
    }

@app.get("/api/v1/sessions")
async def list_sessions():
    """List all active sessions"""
    sessions = []
    for session_id, session_data in chatops_engine.active_sessions.items():
        sessions.append({
            "session_id": session_id,
            "created_at": session_data['created_at'].isoformat(),
            "user_id": session_data['user_id'],
            "message_count": len(session_data['messages'])
        })
    
    return {"sessions": sessions, "count": len(sessions)}

@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for real-time chat"""
    await websocket.accept()
    
    try:
        while True:
            # Receive message
            data = await websocket.receive_text()
            message_data = json.loads(data)
            
            # Process message
            request = ChatRequest(
                session_id=session_id,
                user_id=message_data.get('user_id', 'anonymous'),
                message=message_data.get('message', '')
            )
            
            response = await chatops_engine.process_message(request)
            
            # Send response
            await websocket.send_text(json.dumps(response))
            
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for session {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error for session {session_id}: {e}")
        await websocket.close()

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8092,
        reload=True,
        log_level="info"
    )

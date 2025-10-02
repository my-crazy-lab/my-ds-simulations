"""
Fraud Detection Service

A high-performance fraud detection service built with FastAPI that provides:
- Real-time fraud scoring using ML models
- Saga pattern integration for transaction compensation
- Event-driven architecture with Kafka
- Redis caching for low-latency responses
- Comprehensive monitoring and observability
"""

import asyncio
import logging
import signal
import sys
from contextlib import asynccontextmanager
from typing import Dict, Any

import structlog
import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.core.monitoring import setup_monitoring, setup_tracing
from app.infrastructure.database import DatabaseManager
from app.infrastructure.messaging import KafkaManager
from app.infrastructure.cache import CacheManager
from app.services.fraud_detector import FraudDetectionService
from app.services.saga_coordinator import SagaCoordinatorService
from app.services.model_manager import ModelManager
from app.api.v1 import fraud, health, admin
from app.middleware.error_handler import ErrorHandlerMiddleware
from app.middleware.request_id import RequestIDMiddleware
from app.middleware.timing import TimingMiddleware

# Configure structured logging
setup_logging()
logger = structlog.get_logger(__name__)

# Global managers
database_manager: DatabaseManager = None
kafka_manager: KafkaManager = None
cache_manager: CacheManager = None
fraud_service: FraudDetectionService = None
saga_coordinator: SagaCoordinatorService = None
model_manager: ModelManager = None

# Rate limiter
limiter = Limiter(key_func=get_remote_address)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    global database_manager, kafka_manager, cache_manager
    global fraud_service, saga_coordinator, model_manager
    
    settings = get_settings()
    
    try:
        logger.info("Starting Fraud Detection Service", version="1.0.0")
        
        # Initialize infrastructure
        logger.info("Initializing infrastructure components...")
        
        database_manager = DatabaseManager(settings)
        await database_manager.initialize()
        
        cache_manager = CacheManager(settings)
        await cache_manager.initialize()
        
        kafka_manager = KafkaManager(settings)
        await kafka_manager.initialize()
        
        # Initialize services
        logger.info("Initializing business services...")
        
        model_manager = ModelManager(settings)
        await model_manager.initialize()
        
        fraud_service = FraudDetectionService(
            database_manager=database_manager,
            cache_manager=cache_manager,
            model_manager=model_manager,
            settings=settings
        )
        await fraud_service.initialize()
        
        saga_coordinator = SagaCoordinatorService(
            kafka_manager=kafka_manager,
            fraud_service=fraud_service,
            settings=settings
        )
        await saga_coordinator.initialize()
        
        # Start background tasks
        logger.info("Starting background services...")
        
        # Start Kafka consumers
        asyncio.create_task(kafka_manager.start_consumers())
        
        # Start saga coordinator
        asyncio.create_task(saga_coordinator.start())
        
        # Start model refresh task
        asyncio.create_task(model_manager.start_refresh_task())
        
        logger.info("Fraud Detection Service started successfully")
        
        yield
        
    except Exception as e:
        logger.error("Failed to start Fraud Detection Service", error=str(e))
        raise
    finally:
        # Cleanup
        logger.info("Shutting down Fraud Detection Service...")
        
        if saga_coordinator:
            await saga_coordinator.stop()
        
        if kafka_manager:
            await kafka_manager.stop()
        
        if cache_manager:
            await cache_manager.close()
        
        if database_manager:
            await database_manager.close()
        
        logger.info("Fraud Detection Service stopped")

def create_app() -> FastAPI:
    """Create and configure FastAPI application"""
    settings = get_settings()
    
    # Setup monitoring and tracing
    setup_monitoring()
    setup_tracing(settings.service_name, settings.jaeger_endpoint)
    
    app = FastAPI(
        title="Fraud Detection Service",
        description="Real-time fraud detection with ML and Saga pattern integration",
        version="1.0.0",
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url="/redoc" if settings.environment != "production" else None,
        lifespan=lifespan
    )
    
    # Add middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.add_middleware(ErrorHandlerMiddleware)
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(TimingMiddleware)
    
    # Add rate limiting
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    
    # Include routers
    app.include_router(fraud.router, prefix="/api/v1/fraud", tags=["fraud"])
    app.include_router(health.router, prefix="/health", tags=["health"])
    app.include_router(admin.router, prefix="/admin", tags=["admin"])
    
    # Add Prometheus metrics endpoint
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)
    
    @app.get("/")
    async def root():
        """Root endpoint"""
        return {
            "service": "fraud-detection-service",
            "version": "1.0.0",
            "status": "running",
            "docs": "/docs",
            "health": "/health",
            "metrics": "/metrics"
        }
    
    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):
        """Add security headers"""
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response
    
    return app

def setup_signal_handlers():
    """Setup signal handlers for graceful shutdown"""
    def signal_handler(signum, frame):
        logger.info("Received shutdown signal", signal=signum)
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

async def main():
    """Main application entry point"""
    settings = get_settings()
    
    # Setup signal handlers
    setup_signal_handlers()
    
    # Create app
    app = create_app()
    
    # Configure uvicorn
    config = uvicorn.Config(
        app,
        host=settings.host,
        port=settings.port,
        log_config=None,  # We handle logging ourselves
        access_log=False,  # We handle access logging in middleware
        server_header=False,
        date_header=False,
    )
    
    server = uvicorn.Server(config)
    
    try:
        logger.info(
            "Starting server",
            host=settings.host,
            port=settings.port,
            environment=settings.environment
        )
        await server.serve()
    except Exception as e:
        logger.error("Server failed to start", error=str(e))
        raise

if __name__ == "__main__":
    asyncio.run(main())

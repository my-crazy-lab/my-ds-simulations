"""
Audit Service - Event Sourcing with PostgreSQL
Tracks all system events for compliance and debugging
"""

import asyncio
import logging
import signal
import sys
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
import uvicorn
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from prometheus_client import make_asgi_app

from app.config import get_settings
from app.database import init_db, get_db_session
from app.infrastructure.kafka_consumer import KafkaEventConsumer
from app.infrastructure.metrics import setup_metrics
from app.infrastructure.tracing import setup_tracing
from app.models.audit_event import AuditEvent
from app.services.audit_service import AuditService
from app.services.event_sourcing_service import EventSourcingService
from app.api.routes import audit_router, health_router, saga_router

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# Global variables for background services
kafka_consumer: KafkaEventConsumer = None
background_tasks_running = True


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager"""
    global kafka_consumer, background_tasks_running
    
    settings = get_settings()
    
    try:
        # Initialize database
        await init_db()
        logger.info("Database initialized")
        
        # Setup tracing
        setup_tracing(settings.service_name, settings.jaeger_endpoint)
        logger.info("Tracing initialized")
        
        # Setup metrics
        setup_metrics()
        logger.info("Metrics initialized")
        
        # Initialize Kafka consumer
        kafka_consumer = KafkaEventConsumer(
            bootstrap_servers=settings.kafka_brokers,
            group_id="audit-service-group",
            topics=["saga-events", "order-events", "payment-events", "user-events", "wallet-events"]
        )
        
        # Start background services
        background_tasks_running = True
        asyncio.create_task(kafka_consumer.start())
        logger.info("Background services started")
        
        yield
        
    except Exception as e:
        logger.error("Failed to initialize application", error=str(e))
        raise
    finally:
        # Cleanup
        background_tasks_running = False
        if kafka_consumer:
            await kafka_consumer.stop()
        logger.info("Application shutdown complete")


def create_app() -> FastAPI:
    """Create and configure FastAPI application"""
    settings = get_settings()
    
    app = FastAPI(
        title="Audit Service",
        description="Event Sourcing and Audit Trail Service",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url="/redoc" if settings.environment != "production" else None,
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
    
    # Add Prometheus metrics endpoint
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)
    
    # Include routers
    app.include_router(health_router, prefix="/health", tags=["health"])
    app.include_router(audit_router, prefix="/api/v1/audit", tags=["audit"])
    app.include_router(saga_router, prefix="/api/v1/saga", tags=["saga"])
    
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request, exc):
        logger.error(
            "HTTP exception occurred",
            path=request.url.path,
            method=request.method,
            status_code=exc.status_code,
            detail=exc.detail
        )
        return {"error": exc.detail, "status_code": exc.status_code}
    
    @app.exception_handler(Exception)
    async def general_exception_handler(request, exc):
        logger.error(
            "Unhandled exception occurred",
            path=request.url.path,
            method=request.method,
            error=str(exc),
            exc_info=True
        )
        return {"error": "Internal server error", "status_code": 500}
    
    return app


app = create_app()


def signal_handler(signum, frame):
    """Handle shutdown signals"""
    global background_tasks_running
    logger.info(f"Received signal {signum}, shutting down...")
    background_tasks_running = False
    sys.exit(0)


if __name__ == "__main__":
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    settings = get_settings()
    
    # Configure uvicorn logging
    log_config = uvicorn.config.LOGGING_CONFIG
    log_config["formatters"]["default"]["fmt"] = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    log_config["formatters"]["access"]["fmt"] = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        reload=settings.environment == "development",
        workers=1 if settings.environment == "development" else settings.workers,
        log_config=log_config,
    )

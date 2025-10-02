#!/usr/bin/env python3
"""
Intelligent Saga Orchestrator
ML-powered saga orchestration with failure prediction and optimization
"""

import asyncio
import json
import logging
import os
import signal
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import redis.asyncio as redis
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
import joblib
import mlflow
import mlflow.sklearn
from prometheus_client import Counter, Histogram, Gauge, generate_latest
from prometheus_client import CONTENT_TYPE_LATEST

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Prometheus metrics
SAGA_EXECUTIONS = Counter('intelligent_orchestrator_saga_executions_total', 
                         'Total saga executions', ['saga_type', 'status'])
SAGA_DURATION = Histogram('intelligent_orchestrator_saga_duration_seconds',
                         'Saga execution duration', ['saga_type'])
FAILURE_PREDICTIONS = Counter('intelligent_orchestrator_failure_predictions_total',
                             'Failure predictions made', ['prediction'])
ML_MODEL_ACCURACY = Gauge('intelligent_orchestrator_ml_model_accuracy',
                         'Current ML model accuracy')
ACTIVE_SAGAS = Gauge('intelligent_orchestrator_active_sagas',
                    'Number of currently active sagas')

@dataclass
class SagaStep:
    """Represents a single step in a saga"""
    id: str
    name: str
    service: str
    action: str
    compensation_action: str
    timeout: int = 30
    retry_count: int = 3
    dependencies: List[str] = None
    
    def __post_init__(self):
        if self.dependencies is None:
            self.dependencies = []

@dataclass
class SagaDefinition:
    """Defines a saga workflow"""
    id: str
    name: str
    description: str
    steps: List[SagaStep]
    timeout: int = 300
    max_retries: int = 3
    
@dataclass
class SagaExecution:
    """Represents a saga execution instance"""
    id: str
    saga_id: str
    correlation_id: str
    status: str  # pending, running, completed, failed, compensating, compensated
    current_step: int = 0
    started_at: datetime = None
    completed_at: datetime = None
    error_message: str = None
    context: Dict[str, Any] = None
    ml_prediction: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.context is None:
            self.context = {}
        if self.started_at is None:
            self.started_at = datetime.now()

class SagaRequest(BaseModel):
    """Request to start a saga"""
    saga_id: str
    correlation_id: str
    context: Dict[str, Any] = {}

class MLPredictor:
    """ML model for predicting saga failure probability"""
    
    def __init__(self):
        self.model = None
        self.scaler = StandardScaler()
        self.feature_columns = [
            'step_count', 'total_timeout', 'avg_step_timeout',
            'service_count', 'dependency_count', 'historical_success_rate',
            'system_load', 'error_rate_last_hour', 'avg_response_time'
        ]
        self.is_trained = False
        
    async def load_model(self, model_path: str = None):
        """Load pre-trained model or create new one"""
        try:
            if model_path and os.path.exists(model_path):
                self.model = joblib.load(model_path)
                self.is_trained = True
                logger.info(f"Loaded ML model from {model_path}")
            else:
                # Create and train a basic model with synthetic data
                await self._train_initial_model()
                logger.info("Created initial ML model with synthetic data")
        except Exception as e:
            logger.error(f"Failed to load ML model: {e}")
            # Fallback to simple heuristic model
            self.model = None
            
    async def _train_initial_model(self):
        """Train initial model with synthetic data"""
        # Generate synthetic training data
        np.random.seed(42)
        n_samples = 1000
        
        # Create synthetic features
        data = {
            'step_count': np.random.randint(2, 10, n_samples),
            'total_timeout': np.random.randint(60, 600, n_samples),
            'avg_step_timeout': np.random.randint(10, 60, n_samples),
            'service_count': np.random.randint(1, 5, n_samples),
            'dependency_count': np.random.randint(0, 8, n_samples),
            'historical_success_rate': np.random.uniform(0.7, 0.99, n_samples),
            'system_load': np.random.uniform(0.1, 0.9, n_samples),
            'error_rate_last_hour': np.random.uniform(0.0, 0.1, n_samples),
            'avg_response_time': np.random.uniform(50, 500, n_samples)
        }
        
        df = pd.DataFrame(data)
        
        # Create synthetic target (failure probability)
        # Higher failure probability for complex sagas with high system load
        failure_prob = (
            (df['step_count'] / 10) * 0.3 +
            (df['system_load']) * 0.4 +
            (df['error_rate_last_hour'] * 10) * 0.2 +
            (1 - df['historical_success_rate']) * 0.1
        )
        
        # Add some noise
        failure_prob += np.random.normal(0, 0.05, n_samples)
        failure_prob = np.clip(failure_prob, 0, 1)
        
        # Convert to binary classification (failure if prob > 0.3)
        y = (failure_prob > 0.3).astype(int)
        
        # Train model
        X = df[self.feature_columns]
        X_scaled = self.scaler.fit_transform(X)
        
        self.model = RandomForestClassifier(n_estimators=100, random_state=42)
        self.model.fit(X_scaled, y)
        self.is_trained = True
        
        # Log to MLflow
        with mlflow.start_run(run_name="initial_model_training"):
            mlflow.log_param("n_samples", n_samples)
            mlflow.log_param("model_type", "RandomForestClassifier")
            mlflow.log_param("n_estimators", 100)
            
            # Calculate accuracy on training data (for demo purposes)
            accuracy = self.model.score(X_scaled, y)
            mlflow.log_metric("training_accuracy", accuracy)
            ML_MODEL_ACCURACY.set(accuracy)
            
            # Save model
            mlflow.sklearn.log_model(self.model, "model")
            
        logger.info(f"Trained initial model with accuracy: {accuracy:.3f}")
        
    async def predict_failure_probability(self, saga_def: SagaDefinition, 
                                        context: Dict[str, Any]) -> Dict[str, Any]:
        """Predict failure probability for a saga"""
        try:
            if not self.is_trained:
                # Fallback to heuristic prediction
                return await self._heuristic_prediction(saga_def, context)
                
            # Extract features
            features = await self._extract_features(saga_def, context)
            
            # Scale features
            feature_array = np.array([features[col] for col in self.feature_columns]).reshape(1, -1)
            feature_scaled = self.scaler.transform(feature_array)
            
            # Make prediction
            failure_prob = self.model.predict_proba(feature_scaled)[0][1]
            confidence = max(self.model.predict_proba(feature_scaled)[0]) - 0.5
            
            # Get feature importance
            feature_importance = dict(zip(self.feature_columns, self.model.feature_importances_))
            
            prediction = {
                'failure_probability': float(failure_prob),
                'confidence': float(confidence),
                'risk_level': self._get_risk_level(failure_prob),
                'feature_importance': feature_importance,
                'recommendations': await self._generate_recommendations(failure_prob, features)
            }
            
            FAILURE_PREDICTIONS.labels(prediction=prediction['risk_level']).inc()
            
            return prediction
            
        except Exception as e:
            logger.error(f"ML prediction failed: {e}")
            return await self._heuristic_prediction(saga_def, context)
            
    async def _extract_features(self, saga_def: SagaDefinition, 
                              context: Dict[str, Any]) -> Dict[str, float]:
        """Extract features for ML prediction"""
        # Calculate saga complexity features
        step_count = len(saga_def.steps)
        total_timeout = saga_def.timeout
        avg_step_timeout = sum(step.timeout for step in saga_def.steps) / step_count
        service_count = len(set(step.service for step in saga_def.steps))
        dependency_count = sum(len(step.dependencies) for step in saga_def.steps)
        
        # Get system metrics (simulated for demo)
        historical_success_rate = context.get('historical_success_rate', 0.95)
        system_load = context.get('system_load', 0.3)
        error_rate_last_hour = context.get('error_rate_last_hour', 0.02)
        avg_response_time = context.get('avg_response_time', 150)
        
        return {
            'step_count': float(step_count),
            'total_timeout': float(total_timeout),
            'avg_step_timeout': float(avg_step_timeout),
            'service_count': float(service_count),
            'dependency_count': float(dependency_count),
            'historical_success_rate': float(historical_success_rate),
            'system_load': float(system_load),
            'error_rate_last_hour': float(error_rate_last_hour),
            'avg_response_time': float(avg_response_time)
        }
        
    async def _heuristic_prediction(self, saga_def: SagaDefinition, 
                                  context: Dict[str, Any]) -> Dict[str, Any]:
        """Fallback heuristic prediction when ML model is not available"""
        step_count = len(saga_def.steps)
        service_count = len(set(step.service for step in saga_def.steps))
        
        # Simple heuristic: more steps and services = higher failure probability
        base_prob = min(0.1 + (step_count * 0.05) + (service_count * 0.03), 0.8)
        
        # Adjust based on system load
        system_load = context.get('system_load', 0.3)
        failure_prob = base_prob * (1 + system_load)
        failure_prob = min(failure_prob, 0.9)
        
        return {
            'failure_probability': failure_prob,
            'confidence': 0.6,  # Lower confidence for heuristic
            'risk_level': self._get_risk_level(failure_prob),
            'feature_importance': {},
            'recommendations': await self._generate_recommendations(failure_prob, {})
        }
        
    def _get_risk_level(self, failure_prob: float) -> str:
        """Convert failure probability to risk level"""
        if failure_prob < 0.2:
            return 'low'
        elif failure_prob < 0.5:
            return 'medium'
        elif failure_prob < 0.8:
            return 'high'
        else:
            return 'critical'
            
    async def _generate_recommendations(self, failure_prob: float, 
                                      features: Dict[str, float]) -> List[str]:
        """Generate optimization recommendations"""
        recommendations = []
        
        if failure_prob > 0.7:
            recommendations.append("Consider breaking down the saga into smaller transactions")
            recommendations.append("Implement circuit breakers for external service calls")
            
        if failure_prob > 0.5:
            recommendations.append("Increase timeout values for critical steps")
            recommendations.append("Add retry logic with exponential backoff")
            
        if failure_prob > 0.3:
            recommendations.append("Monitor system load and consider load balancing")
            recommendations.append("Implement health checks for all participating services")
            
        return recommendations

class IntelligentOrchestrator:
    """Main orchestrator service with ML-powered optimization"""
    
    def __init__(self):
        self.redis_client = None
        self.ml_predictor = MLPredictor()
        self.saga_definitions: Dict[str, SagaDefinition] = {}
        self.active_executions: Dict[str, SagaExecution] = {}
        
    async def initialize(self):
        """Initialize the orchestrator"""
        # Connect to Redis
        redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
        self.redis_client = redis.from_url(redis_url)
        
        # Load ML model
        await self.ml_predictor.load_model()
        
        # Load saga definitions
        await self._load_saga_definitions()
        
        logger.info("Intelligent Orchestrator initialized")
        
    async def _load_saga_definitions(self):
        """Load saga definitions from configuration"""
        # For demo, create some sample saga definitions
        payment_saga = SagaDefinition(
            id="payment_saga",
            name="Payment Processing Saga",
            description="Process payment with inventory reservation",
            steps=[
                SagaStep(
                    id="reserve_inventory",
                    name="Reserve Inventory",
                    service="inventory-service",
                    action="reserve",
                    compensation_action="release",
                    timeout=30
                ),
                SagaStep(
                    id="process_payment",
                    name="Process Payment",
                    service="payment-service", 
                    action="charge",
                    compensation_action="refund",
                    timeout=45,
                    dependencies=["reserve_inventory"]
                ),
                SagaStep(
                    id="send_confirmation",
                    name="Send Confirmation",
                    service="notification-service",
                    action="send_email",
                    compensation_action="send_cancellation",
                    timeout=15,
                    dependencies=["process_payment"]
                )
            ],
            timeout=300
        )
        
        self.saga_definitions[payment_saga.id] = payment_saga
        logger.info(f"Loaded {len(self.saga_definitions)} saga definitions")
        
    async def start_saga(self, request: SagaRequest) -> SagaExecution:
        """Start a new saga execution with ML-powered optimization"""
        if request.saga_id not in self.saga_definitions:
            raise ValueError(f"Saga definition not found: {request.saga_id}")
            
        saga_def = self.saga_definitions[request.saga_id]
        
        # Create execution instance
        execution = SagaExecution(
            id=f"exec_{int(time.time())}_{request.correlation_id}",
            saga_id=request.saga_id,
            correlation_id=request.correlation_id,
            status="pending",
            context=request.context
        )
        
        # Get ML prediction
        try:
            prediction = await self.ml_predictor.predict_failure_probability(saga_def, request.context)
            execution.ml_prediction = prediction
            
            logger.info(f"ML prediction for saga {execution.id}: "
                       f"failure_prob={prediction['failure_probability']:.3f}, "
                       f"risk_level={prediction['risk_level']}")
                       
        except Exception as e:
            logger.error(f"ML prediction failed for saga {execution.id}: {e}")
            
        # Store execution
        self.active_executions[execution.id] = execution
        ACTIVE_SAGAS.set(len(self.active_executions))
        
        # Start execution asynchronously
        asyncio.create_task(self._execute_saga(execution))
        
        return execution
        
    async def _execute_saga(self, execution: SagaExecution):
        """Execute a saga with intelligent optimization"""
        saga_def = self.saga_definitions[execution.saga_id]
        execution.status = "running"
        start_time = time.time()
        
        try:
            logger.info(f"Starting saga execution: {execution.id}")
            
            # Apply ML-based optimizations
            if execution.ml_prediction:
                await self._apply_optimizations(execution, saga_def)
            
            # Execute steps
            for i, step in enumerate(saga_def.steps):
                execution.current_step = i
                
                # Check dependencies
                if not await self._check_dependencies(step, execution):
                    raise Exception(f"Dependencies not met for step {step.id}")
                
                # Execute step with optimized parameters
                await self._execute_step(step, execution)
                
            # Mark as completed
            execution.status = "completed"
            execution.completed_at = datetime.now()
            
            duration = time.time() - start_time
            SAGA_EXECUTIONS.labels(saga_type=execution.saga_id, status="completed").inc()
            SAGA_DURATION.labels(saga_type=execution.saga_id).observe(duration)
            
            logger.info(f"Saga execution completed: {execution.id} in {duration:.2f}s")
            
        except Exception as e:
            logger.error(f"Saga execution failed: {execution.id} - {e}")
            execution.status = "failed"
            execution.error_message = str(e)
            execution.completed_at = datetime.now()
            
            # Start compensation
            await self._compensate_saga(execution, saga_def)
            
            duration = time.time() - start_time
            SAGA_EXECUTIONS.labels(saga_type=execution.saga_id, status="failed").inc()
            SAGA_DURATION.labels(saga_type=execution.saga_id).observe(duration)
            
        finally:
            # Clean up
            if execution.id in self.active_executions:
                del self.active_executions[execution.id]
            ACTIVE_SAGAS.set(len(self.active_executions))
            
    async def _apply_optimizations(self, execution: SagaExecution, saga_def: SagaDefinition):
        """Apply ML-based optimizations to saga execution"""
        prediction = execution.ml_prediction
        
        if prediction['risk_level'] in ['high', 'critical']:
            # Increase timeouts for high-risk sagas
            for step in saga_def.steps:
                step.timeout = int(step.timeout * 1.5)
                step.retry_count = min(step.retry_count + 1, 5)
                
            logger.info(f"Applied high-risk optimizations to saga {execution.id}")
            
        elif prediction['risk_level'] == 'medium':
            # Moderate optimizations
            for step in saga_def.steps:
                step.timeout = int(step.timeout * 1.2)
                
            logger.info(f"Applied medium-risk optimizations to saga {execution.id}")
            
    async def _check_dependencies(self, step: SagaStep, execution: SagaExecution) -> bool:
        """Check if step dependencies are satisfied"""
        # For demo, assume dependencies are always satisfied
        return True
        
    async def _execute_step(self, step: SagaStep, execution: SagaExecution):
        """Execute a single saga step"""
        logger.info(f"Executing step {step.id} for saga {execution.id}")
        
        # Simulate step execution
        await asyncio.sleep(0.1)  # Simulate processing time
        
        # For demo, randomly fail some steps to test compensation
        import random
        if random.random() < 0.1:  # 10% failure rate
            raise Exception(f"Step {step.id} failed (simulated)")
            
        logger.info(f"Step {step.id} completed for saga {execution.id}")
        
    async def _compensate_saga(self, execution: SagaExecution, saga_def: SagaDefinition):
        """Execute compensation logic for failed saga"""
        execution.status = "compensating"
        logger.info(f"Starting compensation for saga {execution.id}")
        
        # Execute compensation steps in reverse order
        for i in range(execution.current_step, -1, -1):
            step = saga_def.steps[i]
            await self._compensate_step(step, execution)
            
        execution.status = "compensated"
        logger.info(f"Compensation completed for saga {execution.id}")
        
    async def _compensate_step(self, step: SagaStep, execution: SagaExecution):
        """Execute compensation for a single step"""
        logger.info(f"Compensating step {step.id} for saga {execution.id}")
        
        # Simulate compensation
        await asyncio.sleep(0.05)
        
        logger.info(f"Step {step.id} compensated for saga {execution.id}")

# Global orchestrator instance
orchestrator = IntelligentOrchestrator()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management"""
    # Startup
    await orchestrator.initialize()
    yield
    # Shutdown
    if orchestrator.redis_client:
        await orchestrator.redis_client.close()

# FastAPI application
app = FastAPI(
    title="Intelligent Saga Orchestrator",
    description="ML-powered saga orchestration with failure prediction and optimization",
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
        "service": "intelligent-orchestrator",
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat(),
        "active_sagas": len(orchestrator.active_executions)
    }

@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return generate_latest()

@app.post("/api/v1/sagas/start")
async def start_saga(request: SagaRequest):
    """Start a new saga execution"""
    try:
        execution = await orchestrator.start_saga(request)
        return {
            "execution_id": execution.id,
            "saga_id": execution.saga_id,
            "status": execution.status,
            "ml_prediction": execution.ml_prediction
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/v1/sagas/{execution_id}")
async def get_saga_execution(execution_id: str):
    """Get saga execution status"""
    if execution_id not in orchestrator.active_executions:
        raise HTTPException(status_code=404, detail="Execution not found")
        
    execution = orchestrator.active_executions[execution_id]
    return asdict(execution)

@app.get("/api/v1/sagas")
async def list_saga_executions():
    """List all active saga executions"""
    return {
        "executions": [asdict(exec) for exec in orchestrator.active_executions.values()],
        "count": len(orchestrator.active_executions)
    }

@app.get("/api/v1/definitions")
async def list_saga_definitions():
    """List all saga definitions"""
    return {
        "definitions": [asdict(defn) for defn in orchestrator.saga_definitions.values()],
        "count": len(orchestrator.saga_definitions)
    }

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8091,
        reload=True,
        log_level="info"
    )

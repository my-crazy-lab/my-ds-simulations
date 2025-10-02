#!/usr/bin/env python3
"""
ML Drift Detection & Auto Fine-tune System
Monitors model performance, detects drift, and triggers automatic retraining
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from enum import Enum
import numpy as np
import pandas as pd

import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import redis.asyncio as redis
from kafka import KafkaConsumer, KafkaProducer
import mlflow
import mlflow.sklearn
from evidently import ColumnMapping
from evidently.report import Report
from evidently.metric_preset import DataDriftPreset, TargetDriftPreset
from evidently.metrics import DatasetDriftMetric, DatasetMissingValuesMetric
import prometheus_client
from prometheus_client import Counter, Histogram, Gauge, generate_latest

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Prometheus metrics
DRIFT_DETECTIONS = Counter('drift_detections_total', 'Drift detections', ['type', 'severity'])
MODEL_PERFORMANCE = Gauge('model_performance_score', 'Current model performance', ['model_version', 'metric'])
RETRAIN_TRIGGERS = Counter('retrain_triggers_total', 'Retrain triggers', ['reason'])
DRIFT_SCORE = Gauge('drift_score', 'Current drift score', ['feature_type'])
MONITORING_DURATION = Histogram('drift_monitoring_duration_seconds', 'Time spent on drift monitoring')

class DriftType(Enum):
    DATA_DRIFT = "data_drift"
    TARGET_DRIFT = "target_drift"
    CONCEPT_DRIFT = "concept_drift"
    PERFORMANCE_DRIFT = "performance_drift"

class DriftSeverity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class RetrainReason(Enum):
    DRIFT_DETECTED = "drift_detected"
    PERFORMANCE_DEGRADATION = "performance_degradation"
    SCHEDULED = "scheduled"
    MANUAL = "manual"

@dataclass
class DriftAlert:
    """Drift detection alert"""
    id: str
    timestamp: str
    drift_type: DriftType
    severity: DriftSeverity
    score: float
    threshold: float
    affected_features: List[str]
    model_version: str
    details: Dict[str, Any]
    action_required: bool

@dataclass
class ModelPerformanceMetrics:
    """Model performance tracking"""
    model_version: str
    timestamp: str
    accuracy: float
    precision: float
    recall: float
    f1_score: float
    auc_roc: Optional[float]
    prediction_count: int
    error_rate: float
    latency_p95: float

@dataclass
class RetrainJob:
    """Retraining job configuration"""
    job_id: str
    model_version: str
    reason: RetrainReason
    triggered_at: str
    config: Dict[str, Any]
    status: str
    progress: float
    estimated_completion: Optional[str]

class DriftDetectionConfig:
    """Configuration for drift detection system"""
    
    # Kafka settings
    KAFKA_BOOTSTRAP_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
    KAFKA_PREDICTIONS_TOPIC = os.getenv('KAFKA_PREDICTIONS_TOPIC', 'model-predictions')
    KAFKA_RETRAINING_TOPIC = os.getenv('KAFKA_RETRAINING_TOPIC', 'model-retraining')
    KAFKA_GROUP_ID = os.getenv('KAFKA_GROUP_ID', 'drift-detector')
    
    # Redis settings
    REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379')
    
    # MLflow settings
    MLFLOW_TRACKING_URI = os.getenv('MLFLOW_TRACKING_URI', 'http://localhost:5000')
    MLFLOW_EXPERIMENT_NAME = os.getenv('MLFLOW_EXPERIMENT_NAME', 'chatbot-model')
    
    # Drift detection thresholds
    DATA_DRIFT_THRESHOLD = float(os.getenv('DATA_DRIFT_THRESHOLD', '0.3'))
    TARGET_DRIFT_THRESHOLD = float(os.getenv('TARGET_DRIFT_THRESHOLD', '0.2'))
    PERFORMANCE_DRIFT_THRESHOLD = float(os.getenv('PERFORMANCE_DRIFT_THRESHOLD', '0.1'))
    
    # Monitoring settings
    MONITORING_WINDOW_HOURS = int(os.getenv('MONITORING_WINDOW_HOURS', '24'))
    REFERENCE_WINDOW_DAYS = int(os.getenv('REFERENCE_WINDOW_DAYS', '7'))
    MIN_SAMPLES_FOR_DRIFT = int(os.getenv('MIN_SAMPLES_FOR_DRIFT', '100'))
    
    # Auto-retrain settings
    AUTO_RETRAIN_ENABLED = os.getenv('AUTO_RETRAIN_ENABLED', 'true').lower() == 'true'
    RETRAIN_COOLDOWN_HOURS = int(os.getenv('RETRAIN_COOLDOWN_HOURS', '6'))
    MAX_RETRAIN_ATTEMPTS = int(os.getenv('MAX_RETRAIN_ATTEMPTS', '3'))

class DataDriftDetector:
    """Detects data drift using Evidently AI"""
    
    def __init__(self, config: DriftDetectionConfig):
        self.config = config
        self.reference_data: Optional[pd.DataFrame] = None
        self.feature_columns: List[str] = []
        self.target_column: Optional[str] = None
    
    def set_reference_data(self, reference_df: pd.DataFrame, feature_columns: List[str], target_column: str):
        """Set reference dataset for drift detection"""
        self.reference_data = reference_df.copy()
        self.feature_columns = feature_columns
        self.target_column = target_column
        logger.info(f"Reference data set with {len(reference_df)} samples, {len(feature_columns)} features")
    
    def detect_data_drift(self, current_data: pd.DataFrame) -> Tuple[bool, float, Dict]:
        """Detect data drift between reference and current data"""
        if self.reference_data is None:
            raise ValueError("Reference data not set")
        
        if len(current_data) < self.config.MIN_SAMPLES_FOR_DRIFT:
            logger.warning(f"Insufficient samples for drift detection: {len(current_data)}")
            return False, 0.0, {}
        
        try:
            # Create column mapping
            column_mapping = ColumnMapping()
            column_mapping.numerical_features = self.feature_columns
            if self.target_column:
                column_mapping.target = self.target_column
            
            # Create drift report
            data_drift_report = Report(metrics=[
                DataDriftPreset(),
                DatasetDriftMetric(),
                DatasetMissingValuesMetric(),
            ])
            
            data_drift_report.run(
                reference_data=self.reference_data,
                current_data=current_data,
                column_mapping=column_mapping
            )
            
            # Extract drift metrics
            report_dict = data_drift_report.as_dict()
            
            # Get overall drift score
            dataset_drift = report_dict['metrics'][1]['result']
            drift_score = dataset_drift.get('drift_score', 0.0)
            drift_detected = drift_score > self.config.DATA_DRIFT_THRESHOLD
            
            # Get per-feature drift information
            feature_drift = {}
            if 'metrics' in report_dict and len(report_dict['metrics']) > 0:
                for metric in report_dict['metrics']:
                    if metric['metric'] == 'DataDriftPreset':
                        for feature_name, feature_result in metric['result'].items():
                            if isinstance(feature_result, dict) and 'drift_score' in feature_result:
                                feature_drift[feature_name] = feature_result['drift_score']
            
            drift_details = {
                'overall_drift_score': drift_score,
                'feature_drift_scores': feature_drift,
                'samples_analyzed': len(current_data),
                'reference_samples': len(self.reference_data),
                'drift_threshold': self.config.DATA_DRIFT_THRESHOLD,
            }
            
            logger.info(f"Data drift detection: score={drift_score:.3f}, detected={drift_detected}")
            return drift_detected, drift_score, drift_details
            
        except Exception as e:
            logger.error(f"Error in data drift detection: {e}")
            return False, 0.0, {"error": str(e)}
    
    def detect_target_drift(self, current_data: pd.DataFrame) -> Tuple[bool, float, Dict]:
        """Detect target drift"""
        if self.reference_data is None or self.target_column is None:
            return False, 0.0, {"error": "Reference data or target column not set"}
        
        if self.target_column not in current_data.columns:
            return False, 0.0, {"error": f"Target column {self.target_column} not found"}
        
        try:
            # Create column mapping
            column_mapping = ColumnMapping()
            column_mapping.target = self.target_column
            
            # Create target drift report
            target_drift_report = Report(metrics=[TargetDriftPreset()])
            
            target_drift_report.run(
                reference_data=self.reference_data,
                current_data=current_data,
                column_mapping=column_mapping
            )
            
            # Extract target drift metrics
            report_dict = target_drift_report.as_dict()
            
            # Get target drift score (simplified)
            target_drift_score = 0.0
            drift_detected = False
            
            if 'metrics' in report_dict and len(report_dict['metrics']) > 0:
                # Extract target distribution comparison
                ref_target_dist = self.reference_data[self.target_column].value_counts(normalize=True)
                curr_target_dist = current_data[self.target_column].value_counts(normalize=True)
                
                # Calculate KL divergence or similar metric
                common_values = set(ref_target_dist.index) & set(curr_target_dist.index)
                if common_values:
                    kl_div = 0.0
                    for value in common_values:
                        p = ref_target_dist.get(value, 1e-10)
                        q = curr_target_dist.get(value, 1e-10)
                        kl_div += p * np.log(p / q)
                    
                    target_drift_score = min(kl_div, 1.0)  # Cap at 1.0
                    drift_detected = target_drift_score > self.config.TARGET_DRIFT_THRESHOLD
            
            drift_details = {
                'target_drift_score': target_drift_score,
                'reference_distribution': ref_target_dist.to_dict(),
                'current_distribution': curr_target_dist.to_dict(),
                'drift_threshold': self.config.TARGET_DRIFT_THRESHOLD,
            }
            
            logger.info(f"Target drift detection: score={target_drift_score:.3f}, detected={drift_detected}")
            return drift_detected, target_drift_score, drift_details
            
        except Exception as e:
            logger.error(f"Error in target drift detection: {e}")
            return False, 0.0, {"error": str(e)}

class PerformanceMonitor:
    """Monitors model performance and detects degradation"""
    
    def __init__(self, config: DriftDetectionConfig):
        self.config = config
        self.baseline_metrics: Optional[ModelPerformanceMetrics] = None
    
    def set_baseline_performance(self, metrics: ModelPerformanceMetrics):
        """Set baseline performance metrics"""
        self.baseline_metrics = metrics
        logger.info(f"Baseline performance set: accuracy={metrics.accuracy:.3f}, f1={metrics.f1_score:.3f}")
    
    def detect_performance_drift(self, current_metrics: ModelPerformanceMetrics) -> Tuple[bool, float, Dict]:
        """Detect performance degradation"""
        if self.baseline_metrics is None:
            logger.warning("No baseline metrics set for performance drift detection")
            return False, 0.0, {}
        
        try:
            # Calculate performance degradation
            accuracy_drop = self.baseline_metrics.accuracy - current_metrics.accuracy
            f1_drop = self.baseline_metrics.f1_score - current_metrics.f1_score
            error_rate_increase = current_metrics.error_rate - self.baseline_metrics.error_rate
            
            # Calculate overall performance drift score
            performance_drift_score = max(
                accuracy_drop / self.baseline_metrics.accuracy,
                f1_drop / self.baseline_metrics.f1_score,
                error_rate_increase
            )
            
            drift_detected = performance_drift_score > self.config.PERFORMANCE_DRIFT_THRESHOLD
            
            drift_details = {
                'performance_drift_score': performance_drift_score,
                'accuracy_drop': accuracy_drop,
                'f1_drop': f1_drop,
                'error_rate_increase': error_rate_increase,
                'baseline_accuracy': self.baseline_metrics.accuracy,
                'current_accuracy': current_metrics.accuracy,
                'baseline_f1': self.baseline_metrics.f1_score,
                'current_f1': current_metrics.f1_score,
                'drift_threshold': self.config.PERFORMANCE_DRIFT_THRESHOLD,
            }
            
            logger.info(f"Performance drift detection: score={performance_drift_score:.3f}, detected={drift_detected}")
            return drift_detected, performance_drift_score, drift_details
            
        except Exception as e:
            logger.error(f"Error in performance drift detection: {e}")
            return False, 0.0, {"error": str(e)}

class MLflowIntegration:
    """Integration with MLflow for experiment tracking"""
    
    def __init__(self, config: DriftDetectionConfig):
        self.config = config
        mlflow.set_tracking_uri(config.MLFLOW_TRACKING_URI)
        mlflow.set_experiment(config.MLFLOW_EXPERIMENT_NAME)
    
    def log_drift_detection(self, alert: DriftAlert):
        """Log drift detection to MLflow"""
        try:
            with mlflow.start_run(run_name=f"drift_detection_{alert.id}"):
                mlflow.log_param("drift_type", alert.drift_type.value)
                mlflow.log_param("severity", alert.severity.value)
                mlflow.log_param("model_version", alert.model_version)
                mlflow.log_metric("drift_score", alert.score)
                mlflow.log_metric("threshold", alert.threshold)
                mlflow.log_param("affected_features", ",".join(alert.affected_features))
                mlflow.log_dict(alert.details, "drift_details.json")
                
                logger.info(f"Logged drift detection {alert.id} to MLflow")
                
        except Exception as e:
            logger.error(f"Error logging to MLflow: {e}")
    
    def log_performance_metrics(self, metrics: ModelPerformanceMetrics):
        """Log performance metrics to MLflow"""
        try:
            with mlflow.start_run(run_name=f"performance_monitoring_{metrics.model_version}"):
                mlflow.log_param("model_version", metrics.model_version)
                mlflow.log_metric("accuracy", metrics.accuracy)
                mlflow.log_metric("precision", metrics.precision)
                mlflow.log_metric("recall", metrics.recall)
                mlflow.log_metric("f1_score", metrics.f1_score)
                if metrics.auc_roc:
                    mlflow.log_metric("auc_roc", metrics.auc_roc)
                mlflow.log_metric("error_rate", metrics.error_rate)
                mlflow.log_metric("latency_p95", metrics.latency_p95)
                mlflow.log_metric("prediction_count", metrics.prediction_count)
                
        except Exception as e:
            logger.error(f"Error logging performance metrics to MLflow: {e}")
    
    def trigger_retrain_job(self, job: RetrainJob) -> bool:
        """Trigger retraining job via MLflow"""
        try:
            with mlflow.start_run(run_name=f"retrain_job_{job.job_id}"):
                mlflow.log_param("job_id", job.job_id)
                mlflow.log_param("model_version", job.model_version)
                mlflow.log_param("reason", job.reason.value)
                mlflow.log_dict(job.config, "retrain_config.json")
                
                # In a real implementation, this would trigger a training pipeline
                # For now, we'll just log the job
                logger.info(f"Triggered retrain job {job.job_id} via MLflow")
                return True
                
        except Exception as e:
            logger.error(f"Error triggering retrain job: {e}")
            return False

class DriftDetectionService:
    """Main drift detection service"""
    
    def __init__(self):
        self.config = DriftDetectionConfig()
        self.data_drift_detector = DataDriftDetector(self.config)
        self.performance_monitor = PerformanceMonitor(self.config)
        self.mlflow_integration = MLflowIntegration(self.config)
        self.redis_client = None
        self.kafka_consumer = None
        self.kafka_producer = None
        self.running = False
        self.last_retrain_time: Optional[datetime] = None
    
    async def start(self):
        """Start the drift detection service"""
        logger.info("Starting Drift Detection Service")
        
        # Connect to Redis
        self.redis_client = redis.from_url(self.config.REDIS_URL)
        
        # Setup Kafka
        self.kafka_consumer = KafkaConsumer(
            self.config.KAFKA_PREDICTIONS_TOPIC,
            bootstrap_servers=self.config.KAFKA_BOOTSTRAP_SERVERS,
            group_id=self.config.KAFKA_GROUP_ID,
            value_deserializer=lambda x: json.loads(x.decode('utf-8')),
            auto_offset_reset='latest',
        )
        
        self.kafka_producer = KafkaProducer(
            bootstrap_servers=self.config.KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=lambda x: json.dumps(x).encode('utf-8')
        )
        
        self.running = True
        
        # Start monitoring loop
        asyncio.create_task(self._monitoring_loop())
        
        logger.info("Drift Detection Service started")
    
    async def stop(self):
        """Stop the drift detection service"""
        logger.info("Stopping Drift Detection Service")
        self.running = False
        
        if self.kafka_consumer:
            self.kafka_consumer.close()
        if self.kafka_producer:
            self.kafka_producer.close()
        if self.redis_client:
            await self.redis_client.close()
        
        logger.info("Drift Detection Service stopped")
    
    @MONITORING_DURATION.time()
    async def _monitoring_loop(self):
        """Main monitoring loop"""
        logger.info("Starting drift monitoring loop")
        
        while self.running:
            try:
                # Collect recent predictions and performance data
                current_data = await self._collect_current_data()
                
                if current_data is not None and len(current_data) >= self.config.MIN_SAMPLES_FOR_DRIFT:
                    # Run drift detection
                    await self._run_drift_detection(current_data)
                
                # Sleep before next monitoring cycle
                await asyncio.sleep(300)  # 5 minutes
                
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(60)  # Wait 1 minute before retrying
    
    async def _collect_current_data(self) -> Optional[pd.DataFrame]:
        """Collect current prediction data for drift analysis"""
        try:
            # In a real implementation, this would collect data from the predictions topic
            # For now, we'll simulate data collection
            
            # Get data from Redis cache or database
            cache_key = "current_predictions_data"
            cached_data = await self.redis_client.get(cache_key)
            
            if cached_data:
                data_dict = json.loads(cached_data)
                return pd.DataFrame(data_dict)
            
            return None
            
        except Exception as e:
            logger.error(f"Error collecting current data: {e}")
            return None
    
    async def _run_drift_detection(self, current_data: pd.DataFrame):
        """Run comprehensive drift detection"""
        try:
            alerts = []
            
            # Data drift detection
            if self.data_drift_detector.reference_data is not None:
                data_drift_detected, data_drift_score, data_drift_details = \
                    self.data_drift_detector.detect_data_drift(current_data)
                
                if data_drift_detected:
                    severity = self._calculate_drift_severity(data_drift_score, self.config.DATA_DRIFT_THRESHOLD)
                    alert = DriftAlert(
                        id=f"data_drift_{int(time.time())}",
                        timestamp=datetime.now().isoformat(),
                        drift_type=DriftType.DATA_DRIFT,
                        severity=severity,
                        score=data_drift_score,
                        threshold=self.config.DATA_DRIFT_THRESHOLD,
                        affected_features=list(data_drift_details.get('feature_drift_scores', {}).keys()),
                        model_version="current",
                        details=data_drift_details,
                        action_required=severity in [DriftSeverity.HIGH, DriftSeverity.CRITICAL]
                    )
                    alerts.append(alert)
                
                # Update Prometheus metrics
                DRIFT_SCORE.labels(feature_type='data').set(data_drift_score)
                if data_drift_detected:
                    DRIFT_DETECTIONS.labels(type='data', severity=severity.value).inc()
            
            # Target drift detection
            target_drift_detected, target_drift_score, target_drift_details = \
                self.data_drift_detector.detect_target_drift(current_data)
            
            if target_drift_detected:
                severity = self._calculate_drift_severity(target_drift_score, self.config.TARGET_DRIFT_THRESHOLD)
                alert = DriftAlert(
                    id=f"target_drift_{int(time.time())}",
                    timestamp=datetime.now().isoformat(),
                    drift_type=DriftType.TARGET_DRIFT,
                    severity=severity,
                    score=target_drift_score,
                    threshold=self.config.TARGET_DRIFT_THRESHOLD,
                    affected_features=["target"],
                    model_version="current",
                    details=target_drift_details,
                    action_required=severity in [DriftSeverity.HIGH, DriftSeverity.CRITICAL]
                )
                alerts.append(alert)
                
                DRIFT_SCORE.labels(feature_type='target').set(target_drift_score)
                if target_drift_detected:
                    DRIFT_DETECTIONS.labels(type='target', severity=severity.value).inc()
            
            # Process alerts
            for alert in alerts:
                await self._process_drift_alert(alert)
            
        except Exception as e:
            logger.error(f"Error in drift detection: {e}")
    
    def _calculate_drift_severity(self, score: float, threshold: float) -> DriftSeverity:
        """Calculate drift severity based on score and threshold"""
        ratio = score / threshold
        
        if ratio >= 3.0:
            return DriftSeverity.CRITICAL
        elif ratio >= 2.0:
            return DriftSeverity.HIGH
        elif ratio >= 1.5:
            return DriftSeverity.MEDIUM
        else:
            return DriftSeverity.LOW
    
    async def _process_drift_alert(self, alert: DriftAlert):
        """Process drift alert and take appropriate actions"""
        try:
            # Log to MLflow
            self.mlflow_integration.log_drift_detection(alert)
            
            # Store alert in Redis
            alert_key = f"drift_alert:{alert.id}"
            await self.redis_client.setex(alert_key, 86400 * 7, json.dumps(asdict(alert)))
            
            # Check if retraining should be triggered
            if alert.action_required and self.config.AUTO_RETRAIN_ENABLED:
                await self._consider_retraining(alert)
            
            logger.info(f"Processed drift alert: {alert.id} ({alert.drift_type.value}, {alert.severity.value})")
            
        except Exception as e:
            logger.error(f"Error processing drift alert: {e}")
    
    async def _consider_retraining(self, alert: DriftAlert):
        """Consider triggering model retraining"""
        try:
            # Check cooldown period
            if self.last_retrain_time:
                time_since_last = datetime.now() - self.last_retrain_time
                if time_since_last < timedelta(hours=self.config.RETRAIN_COOLDOWN_HOURS):
                    logger.info(f"Retraining in cooldown period, skipping")
                    return
            
            # Create retrain job
            job = RetrainJob(
                job_id=f"retrain_{int(time.time())}",
                model_version="current",
                reason=RetrainReason.DRIFT_DETECTED,
                triggered_at=datetime.now().isoformat(),
                config={
                    "drift_alert_id": alert.id,
                    "drift_type": alert.drift_type.value,
                    "drift_score": alert.score,
                    "auto_triggered": True,
                },
                status="pending",
                progress=0.0,
                estimated_completion=None
            )
            
            # Trigger retraining
            success = self.mlflow_integration.trigger_retrain_job(job)
            
            if success:
                # Send to retraining topic
                self.kafka_producer.send(
                    self.config.KAFKA_RETRAINING_TOPIC,
                    value=asdict(job)
                )
                
                self.last_retrain_time = datetime.now()
                RETRAIN_TRIGGERS.labels(reason=job.reason.value).inc()
                
                logger.info(f"Triggered retraining job: {job.job_id}")
            
        except Exception as e:
            logger.error(f"Error considering retraining: {e}")

# Global service instance
drift_service = DriftDetectionService()

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await drift_service.start()
    yield
    # Shutdown
    await drift_service.stop()

app = FastAPI(
    title="Drift Detection Service",
    description="ML drift detection and auto fine-tuning system",
    version="1.0.0",
    lifespan=lifespan
)

# API Models
class DriftCheckRequest(BaseModel):
    reference_data: List[Dict]
    current_data: List[Dict]
    feature_columns: List[str]
    target_column: Optional[str] = None

class DriftCheckResponse(BaseModel):
    data_drift_detected: bool
    data_drift_score: float
    target_drift_detected: bool
    target_drift_score: float
    details: Dict

# API Endpoints
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "drift-detection",
        "timestamp": datetime.now().isoformat(),
        "monitoring_active": drift_service.running,
    }

@app.post("/check-drift", response_model=DriftCheckResponse)
async def check_drift(request: DriftCheckRequest):
    """Manual drift check endpoint"""
    try:
        # Convert to DataFrames
        reference_df = pd.DataFrame(request.reference_data)
        current_df = pd.DataFrame(request.current_data)
        
        # Set reference data
        drift_service.data_drift_detector.set_reference_data(
            reference_df, request.feature_columns, request.target_column
        )
        
        # Run drift detection
        data_drift_detected, data_drift_score, data_drift_details = \
            drift_service.data_drift_detector.detect_data_drift(current_df)
        
        target_drift_detected, target_drift_score, target_drift_details = \
            drift_service.data_drift_detector.detect_target_drift(current_df)
        
        return DriftCheckResponse(
            data_drift_detected=data_drift_detected,
            data_drift_score=data_drift_score,
            target_drift_detected=target_drift_detected,
            target_drift_score=target_drift_score,
            details={
                "data_drift": data_drift_details,
                "target_drift": target_drift_details,
            }
        )
        
    except Exception as e:
        logger.error(f"Error in drift check: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/metrics")
async def get_metrics():
    """Prometheus metrics endpoint"""
    return JSONResponse(
        content=prometheus_client.generate_latest().decode('utf-8'),
        media_type="text/plain"
    )

@app.get("/alerts")
async def get_recent_alerts():
    """Get recent drift alerts"""
    try:
        # Get alerts from Redis
        alert_keys = await drift_service.redis_client.keys("drift_alert:*")
        alerts = []
        
        for key in alert_keys[-10:]:  # Get last 10 alerts
            alert_data = await drift_service.redis_client.get(key)
            if alert_data:
                alerts.append(json.loads(alert_data))
        
        return {"alerts": alerts}
        
    except Exception as e:
        logger.error(f"Error getting alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8082,
        reload=False,
        log_level="info"
    )

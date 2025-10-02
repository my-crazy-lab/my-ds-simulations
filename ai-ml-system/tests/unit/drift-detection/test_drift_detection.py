#!/usr/bin/env python3
"""
Unit tests for Drift Detection Service
"""

import pytest
import asyncio
import json
import pandas as pd
import numpy as np
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timedelta

# Import the modules to test
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '../../../services/drift-detection'))

from main import (
    DataDriftDetector, PerformanceMonitor, MLflowIntegration, DriftDetectionService,
    DriftDetectionConfig, DriftAlert, ModelPerformanceMetrics, RetrainJob,
    DriftType, DriftSeverity, RetrainReason
)

class TestDataDriftDetector:
    """Test data drift detection functionality"""
    
    @pytest.fixture
    def sample_reference_data(self):
        """Create sample reference dataset"""
        np.random.seed(42)
        return pd.DataFrame({
            'feature1': np.random.normal(0, 1, 1000),
            'feature2': np.random.normal(5, 2, 1000),
            'feature3': np.random.uniform(0, 10, 1000),
            'target': np.random.choice(['A', 'B', 'C'], 1000, p=[0.5, 0.3, 0.2])
        })
    
    @pytest.fixture
    def sample_current_data_no_drift(self):
        """Create sample current dataset with no drift"""
        np.random.seed(43)
        return pd.DataFrame({
            'feature1': np.random.normal(0, 1, 500),
            'feature2': np.random.normal(5, 2, 500),
            'feature3': np.random.uniform(0, 10, 500),
            'target': np.random.choice(['A', 'B', 'C'], 500, p=[0.5, 0.3, 0.2])
        })
    
    @pytest.fixture
    def sample_current_data_with_drift(self):
        """Create sample current dataset with drift"""
        np.random.seed(44)
        return pd.DataFrame({
            'feature1': np.random.normal(2, 1.5, 500),  # Mean and std shifted
            'feature2': np.random.normal(8, 3, 500),    # Mean and std shifted
            'feature3': np.random.uniform(5, 15, 500),  # Range shifted
            'target': np.random.choice(['A', 'B', 'C'], 500, p=[0.2, 0.3, 0.5])  # Distribution changed
        })
    
    def test_drift_detector_initialization(self):
        """Test drift detector initialization"""
        config = DriftDetectionConfig()
        detector = DataDriftDetector(config)
        
        assert detector.config == config
        assert detector.reference_data is None
        assert detector.feature_columns == []
        assert detector.target_column is None
    
    def test_set_reference_data(self, sample_reference_data):
        """Test setting reference data"""
        config = DriftDetectionConfig()
        detector = DataDriftDetector(config)
        
        feature_columns = ['feature1', 'feature2', 'feature3']
        target_column = 'target'
        
        detector.set_reference_data(sample_reference_data, feature_columns, target_column)
        
        assert detector.reference_data is not None
        assert len(detector.reference_data) == 1000
        assert detector.feature_columns == feature_columns
        assert detector.target_column == target_column
    
    @patch('main.Report')
    def test_detect_data_drift_no_drift(self, mock_report, sample_reference_data, sample_current_data_no_drift):
        """Test data drift detection with no drift"""
        config = DriftDetectionConfig()
        detector = DataDriftDetector(config)
        
        # Set reference data
        feature_columns = ['feature1', 'feature2', 'feature3']
        detector.set_reference_data(sample_reference_data, feature_columns, 'target')
        
        # Mock Evidently report
        mock_report_instance = Mock()
        mock_report.return_value = mock_report_instance
        mock_report_instance.as_dict.return_value = {
            'metrics': [
                {'metric': 'DataDriftPreset', 'result': {}},
                {'metric': 'DatasetDriftMetric', 'result': {'drift_score': 0.1}},
            ]
        }
        
        # Run drift detection
        drift_detected, drift_score, details = detector.detect_data_drift(sample_current_data_no_drift)
        
        assert drift_detected is False  # 0.1 < 0.3 threshold
        assert drift_score == 0.1
        assert 'overall_drift_score' in details
        assert details['samples_analyzed'] == 500
    
    @patch('main.Report')
    def test_detect_data_drift_with_drift(self, mock_report, sample_reference_data, sample_current_data_with_drift):
        """Test data drift detection with drift"""
        config = DriftDetectionConfig()
        detector = DataDriftDetector(config)
        
        # Set reference data
        feature_columns = ['feature1', 'feature2', 'feature3']
        detector.set_reference_data(sample_reference_data, feature_columns, 'target')
        
        # Mock Evidently report with high drift score
        mock_report_instance = Mock()
        mock_report.return_value = mock_report_instance
        mock_report_instance.as_dict.return_value = {
            'metrics': [
                {'metric': 'DataDriftPreset', 'result': {
                    'feature1': {'drift_score': 0.8},
                    'feature2': {'drift_score': 0.6},
                    'feature3': {'drift_score': 0.4},
                }},
                {'metric': 'DatasetDriftMetric', 'result': {'drift_score': 0.6}},
            ]
        }
        
        # Run drift detection
        drift_detected, drift_score, details = detector.detect_data_drift(sample_current_data_with_drift)
        
        assert drift_detected is True  # 0.6 > 0.3 threshold
        assert drift_score == 0.6
        assert 'feature_drift_scores' in details
        assert details['feature_drift_scores']['feature1'] == 0.8
    
    def test_detect_data_drift_insufficient_samples(self, sample_reference_data):
        """Test drift detection with insufficient samples"""
        config = DriftDetectionConfig()
        config.MIN_SAMPLES_FOR_DRIFT = 1000
        detector = DataDriftDetector(config)
        
        # Set reference data
        feature_columns = ['feature1', 'feature2', 'feature3']
        detector.set_reference_data(sample_reference_data, feature_columns, 'target')
        
        # Create small current dataset
        small_data = pd.DataFrame({
            'feature1': [1, 2, 3],
            'feature2': [4, 5, 6],
            'feature3': [7, 8, 9],
            'target': ['A', 'B', 'C']
        })
        
        drift_detected, drift_score, details = detector.detect_data_drift(small_data)
        
        assert drift_detected is False
        assert drift_score == 0.0
        assert details == {}
    
    def test_detect_target_drift(self, sample_reference_data, sample_current_data_with_drift):
        """Test target drift detection"""
        config = DriftDetectionConfig()
        detector = DataDriftDetector(config)
        
        # Set reference data
        feature_columns = ['feature1', 'feature2', 'feature3']
        detector.set_reference_data(sample_reference_data, feature_columns, 'target')
        
        # Run target drift detection
        drift_detected, drift_score, details = detector.detect_target_drift(sample_current_data_with_drift)
        
        # Should detect drift due to different target distribution
        assert isinstance(drift_detected, bool)
        assert isinstance(drift_score, float)
        assert 'target_drift_score' in details
        assert 'reference_distribution' in details
        assert 'current_distribution' in details

class TestPerformanceMonitor:
    """Test performance monitoring functionality"""
    
    @pytest.fixture
    def baseline_metrics(self):
        """Create baseline performance metrics"""
        return ModelPerformanceMetrics(
            model_version="v1.0",
            timestamp="2023-01-01T00:00:00Z",
            accuracy=0.85,
            precision=0.83,
            recall=0.87,
            f1_score=0.85,
            auc_roc=0.90,
            prediction_count=10000,
            error_rate=0.15,
            latency_p95=150.0
        )
    
    @pytest.fixture
    def degraded_metrics(self):
        """Create degraded performance metrics"""
        return ModelPerformanceMetrics(
            model_version="v1.0",
            timestamp="2023-01-02T00:00:00Z",
            accuracy=0.70,  # Significant drop
            precision=0.68,
            recall=0.72,
            f1_score=0.70,  # Significant drop
            auc_roc=0.75,
            prediction_count=10000,
            error_rate=0.30,  # Significant increase
            latency_p95=200.0
        )
    
    def test_performance_monitor_initialization(self):
        """Test performance monitor initialization"""
        config = DriftDetectionConfig()
        monitor = PerformanceMonitor(config)
        
        assert monitor.config == config
        assert monitor.baseline_metrics is None
    
    def test_set_baseline_performance(self, baseline_metrics):
        """Test setting baseline performance"""
        config = DriftDetectionConfig()
        monitor = PerformanceMonitor(config)
        
        monitor.set_baseline_performance(baseline_metrics)
        
        assert monitor.baseline_metrics == baseline_metrics
    
    def test_detect_performance_drift_no_degradation(self, baseline_metrics):
        """Test performance drift detection with no degradation"""
        config = DriftDetectionConfig()
        monitor = PerformanceMonitor(config)
        monitor.set_baseline_performance(baseline_metrics)
        
        # Create similar metrics (no significant degradation)
        current_metrics = ModelPerformanceMetrics(
            model_version="v1.0",
            timestamp="2023-01-02T00:00:00Z",
            accuracy=0.84,  # Small drop
            precision=0.82,
            recall=0.86,
            f1_score=0.84,  # Small drop
            auc_roc=0.89,
            prediction_count=10000,
            error_rate=0.16,  # Small increase
            latency_p95=155.0
        )
        
        drift_detected, drift_score, details = monitor.detect_performance_drift(current_metrics)
        
        assert drift_detected is False  # Should be below threshold
        assert drift_score < config.PERFORMANCE_DRIFT_THRESHOLD
        assert 'performance_drift_score' in details
        assert 'accuracy_drop' in details
    
    def test_detect_performance_drift_with_degradation(self, baseline_metrics, degraded_metrics):
        """Test performance drift detection with significant degradation"""
        config = DriftDetectionConfig()
        monitor = PerformanceMonitor(config)
        monitor.set_baseline_performance(baseline_metrics)
        
        drift_detected, drift_score, details = monitor.detect_performance_drift(degraded_metrics)
        
        assert drift_detected is True  # Should exceed threshold
        assert drift_score > config.PERFORMANCE_DRIFT_THRESHOLD
        assert details['accuracy_drop'] > 0
        assert details['f1_drop'] > 0
        assert details['error_rate_increase'] > 0
    
    def test_detect_performance_drift_no_baseline(self):
        """Test performance drift detection without baseline"""
        config = DriftDetectionConfig()
        monitor = PerformanceMonitor(config)
        
        current_metrics = ModelPerformanceMetrics(
            model_version="v1.0",
            timestamp="2023-01-02T00:00:00Z",
            accuracy=0.70,
            precision=0.68,
            recall=0.72,
            f1_score=0.70,
            auc_roc=0.75,
            prediction_count=10000,
            error_rate=0.30,
            latency_p95=200.0
        )
        
        drift_detected, drift_score, details = monitor.detect_performance_drift(current_metrics)
        
        assert drift_detected is False
        assert drift_score == 0.0
        assert details == {}

class TestMLflowIntegration:
    """Test MLflow integration functionality"""
    
    @pytest.fixture
    def sample_drift_alert(self):
        """Create sample drift alert"""
        return DriftAlert(
            id="drift_001",
            timestamp="2023-01-01T00:00:00Z",
            drift_type=DriftType.DATA_DRIFT,
            severity=DriftSeverity.HIGH,
            score=0.6,
            threshold=0.3,
            affected_features=["feature1", "feature2"],
            model_version="v1.0",
            details={"drift_score": 0.6, "samples": 1000},
            action_required=True
        )
    
    @pytest.fixture
    def sample_performance_metrics(self):
        """Create sample performance metrics"""
        return ModelPerformanceMetrics(
            model_version="v1.0",
            timestamp="2023-01-01T00:00:00Z",
            accuracy=0.85,
            precision=0.83,
            recall=0.87,
            f1_score=0.85,
            auc_roc=0.90,
            prediction_count=10000,
            error_rate=0.15,
            latency_p95=150.0
        )
    
    @patch('main.mlflow')
    def test_mlflow_initialization(self, mock_mlflow):
        """Test MLflow integration initialization"""
        config = DriftDetectionConfig()
        integration = MLflowIntegration(config)
        
        mock_mlflow.set_tracking_uri.assert_called_once_with(config.MLFLOW_TRACKING_URI)
        mock_mlflow.set_experiment.assert_called_once_with(config.MLFLOW_EXPERIMENT_NAME)
    
    @patch('main.mlflow')
    def test_log_drift_detection(self, mock_mlflow, sample_drift_alert):
        """Test logging drift detection to MLflow"""
        config = DriftDetectionConfig()
        integration = MLflowIntegration(config)
        
        # Mock MLflow context manager
        mock_run_context = Mock()
        mock_mlflow.start_run.return_value.__enter__.return_value = mock_run_context
        
        integration.log_drift_detection(sample_drift_alert)
        
        # Verify MLflow calls
        mock_mlflow.start_run.assert_called_once()
        mock_mlflow.log_param.assert_called()
        mock_mlflow.log_metric.assert_called()
        mock_mlflow.log_dict.assert_called_once()
    
    @patch('main.mlflow')
    def test_log_performance_metrics(self, mock_mlflow, sample_performance_metrics):
        """Test logging performance metrics to MLflow"""
        config = DriftDetectionConfig()
        integration = MLflowIntegration(config)
        
        # Mock MLflow context manager
        mock_run_context = Mock()
        mock_mlflow.start_run.return_value.__enter__.return_value = mock_run_context
        
        integration.log_performance_metrics(sample_performance_metrics)
        
        # Verify MLflow calls
        mock_mlflow.start_run.assert_called_once()
        mock_mlflow.log_param.assert_called()
        mock_mlflow.log_metric.assert_called()
    
    @patch('main.mlflow')
    def test_trigger_retrain_job(self, mock_mlflow):
        """Test triggering retrain job via MLflow"""
        config = DriftDetectionConfig()
        integration = MLflowIntegration(config)
        
        # Mock MLflow context manager
        mock_run_context = Mock()
        mock_mlflow.start_run.return_value.__enter__.return_value = mock_run_context
        
        job = RetrainJob(
            job_id="retrain_001",
            model_version="v1.0",
            reason=RetrainReason.DRIFT_DETECTED,
            triggered_at="2023-01-01T00:00:00Z",
            config={"learning_rate": 0.001},
            status="pending",
            progress=0.0,
            estimated_completion=None
        )
        
        result = integration.trigger_retrain_job(job)
        
        assert result is True
        mock_mlflow.start_run.assert_called_once()
        mock_mlflow.log_param.assert_called()
        mock_mlflow.log_dict.assert_called_once()

class TestDriftDetectionService:
    """Test main drift detection service"""
    
    @pytest.fixture
    def mock_dependencies(self):
        """Mock all external dependencies"""
        with patch('main.redis.from_url') as mock_redis, \
             patch('main.KafkaConsumer') as mock_kafka_consumer, \
             patch('main.KafkaProducer') as mock_kafka_producer:
            
            mock_redis_client = AsyncMock()
            mock_redis.return_value = mock_redis_client
            
            mock_consumer = Mock()
            mock_kafka_consumer.return_value = mock_consumer
            
            mock_producer = Mock()
            mock_kafka_producer.return_value = mock_producer
            
            yield {
                'redis': mock_redis_client,
                'kafka_consumer': mock_consumer,
                'kafka_producer': mock_producer
            }
    
    @pytest.mark.asyncio
    async def test_service_initialization(self, mock_dependencies):
        """Test drift detection service initialization"""
        service = DriftDetectionService()
        
        assert service.config is not None
        assert service.data_drift_detector is not None
        assert service.performance_monitor is not None
        assert service.mlflow_integration is not None
        assert service.running is False
    
    @pytest.mark.asyncio
    async def test_service_start_stop(self, mock_dependencies):
        """Test service start and stop"""
        service = DriftDetectionService()
        
        # Start service
        await service.start()
        assert service.running is True
        assert service.redis_client is not None
        assert service.kafka_consumer is not None
        assert service.kafka_producer is not None
        
        # Stop service
        await service.stop()
        assert service.running is False
    
    def test_calculate_drift_severity(self):
        """Test drift severity calculation"""
        service = DriftDetectionService()
        
        # Test different severity levels
        assert service._calculate_drift_severity(0.9, 0.3) == DriftSeverity.CRITICAL  # 3x threshold
        assert service._calculate_drift_severity(0.6, 0.3) == DriftSeverity.HIGH      # 2x threshold
        assert service._calculate_drift_severity(0.45, 0.3) == DriftSeverity.MEDIUM   # 1.5x threshold
        assert service._calculate_drift_severity(0.35, 0.3) == DriftSeverity.LOW      # Just above threshold
    
    @pytest.mark.asyncio
    async def test_collect_current_data(self, mock_dependencies):
        """Test collecting current data"""
        service = DriftDetectionService()
        service.redis_client = mock_dependencies['redis']
        
        # Mock cached data
        sample_data = {
            'feature1': [1, 2, 3],
            'feature2': [4, 5, 6],
            'target': ['A', 'B', 'C']
        }
        mock_dependencies['redis'].get.return_value = json.dumps(sample_data)
        
        result = await service._collect_current_data()
        
        assert result is not None
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 3
        assert list(result.columns) == ['feature1', 'feature2', 'target']
    
    @pytest.mark.asyncio
    async def test_collect_current_data_no_cache(self, mock_dependencies):
        """Test collecting current data with no cached data"""
        service = DriftDetectionService()
        service.redis_client = mock_dependencies['redis']
        
        # Mock no cached data
        mock_dependencies['redis'].get.return_value = None
        
        result = await service._collect_current_data()
        
        assert result is None

if __name__ == "__main__":
    pytest.main([__file__, "-v"])

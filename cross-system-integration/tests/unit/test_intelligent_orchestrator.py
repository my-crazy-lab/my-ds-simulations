#!/usr/bin/env python3
"""
Unit tests for Intelligent Orchestrator
"""

import pytest
import asyncio
import json
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timedelta

# Import the classes we want to test
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '../../services/intelligent-orchestrator'))

from main import (
    SagaStep, SagaDefinition, SagaExecution, SagaRequest,
    MLPredictor, IntelligentOrchestrator
)

class TestSagaStep:
    """Test cases for SagaStep"""
    
    def test_create_saga_step(self):
        """Test creating a saga step"""
        step = SagaStep(
            id="test_step",
            name="Test Step",
            service="test-service",
            action="test_action",
            compensation_action="undo_action",
            timeout=30,
            retry_count=3,
            dependencies=["dep1", "dep2"]
        )
        
        assert step.id == "test_step"
        assert step.name == "Test Step"
        assert step.service == "test-service"
        assert step.action == "test_action"
        assert step.compensation_action == "undo_action"
        assert step.timeout == 30
        assert step.retry_count == 3
        assert step.dependencies == ["dep1", "dep2"]
        
    def test_saga_step_defaults(self):
        """Test saga step default values"""
        step = SagaStep(
            id="test_step",
            name="Test Step",
            service="test-service",
            action="test_action",
            compensation_action="undo_action"
        )
        
        assert step.timeout == 30
        assert step.retry_count == 3
        assert step.dependencies == []

class TestSagaDefinition:
    """Test cases for SagaDefinition"""
    
    def test_create_saga_definition(self):
        """Test creating a saga definition"""
        steps = [
            SagaStep("step1", "Step 1", "service1", "action1", "undo1"),
            SagaStep("step2", "Step 2", "service2", "action2", "undo2", dependencies=["step1"])
        ]
        
        saga_def = SagaDefinition(
            id="test_saga",
            name="Test Saga",
            description="A test saga",
            steps=steps,
            timeout=300,
            max_retries=3
        )
        
        assert saga_def.id == "test_saga"
        assert saga_def.name == "Test Saga"
        assert saga_def.description == "A test saga"
        assert len(saga_def.steps) == 2
        assert saga_def.timeout == 300
        assert saga_def.max_retries == 3

class TestSagaExecution:
    """Test cases for SagaExecution"""
    
    def test_create_saga_execution(self):
        """Test creating a saga execution"""
        execution = SagaExecution(
            id="exec_123",
            saga_id="test_saga",
            correlation_id="corr_123",
            status="pending",
            context={"user_id": "123"}
        )
        
        assert execution.id == "exec_123"
        assert execution.saga_id == "test_saga"
        assert execution.correlation_id == "corr_123"
        assert execution.status == "pending"
        assert execution.current_step == 0
        assert execution.context == {"user_id": "123"}
        assert execution.started_at is not None
        assert execution.completed_at is None
        
    def test_saga_execution_defaults(self):
        """Test saga execution default values"""
        execution = SagaExecution(
            id="exec_123",
            saga_id="test_saga",
            correlation_id="corr_123",
            status="pending"
        )
        
        assert execution.context == {}
        assert execution.current_step == 0
        assert execution.started_at is not None

class TestMLPredictor:
    """Test cases for MLPredictor"""
    
    @pytest.fixture
    def ml_predictor(self):
        """Create ML predictor instance for testing"""
        return MLPredictor()
    
    @pytest.mark.asyncio
    async def test_load_model_creates_initial_model(self, ml_predictor):
        """Test that load_model creates an initial model when no model file exists"""
        with patch('os.path.exists', return_value=False):
            with patch.object(ml_predictor, '_train_initial_model', new_callable=AsyncMock) as mock_train:
                await ml_predictor.load_model()
                mock_train.assert_called_once()
                
    @pytest.mark.asyncio
    async def test_extract_features(self, ml_predictor):
        """Test feature extraction from saga definition"""
        steps = [
            SagaStep("step1", "Step 1", "service1", "action1", "undo1"),
            SagaStep("step2", "Step 2", "service2", "action2", "undo2", dependencies=["step1"]),
            SagaStep("step3", "Step 3", "service1", "action3", "undo3")  # Same service as step1
        ]
        
        saga_def = SagaDefinition(
            id="test_saga",
            name="Test Saga",
            description="Test",
            steps=steps,
            timeout=300
        )
        
        context = {
            'historical_success_rate': 0.95,
            'system_load': 0.4,
            'error_rate_last_hour': 0.02,
            'avg_response_time': 150
        }
        
        features = await ml_predictor._extract_features(saga_def, context)
        
        assert features['step_count'] == 3.0
        assert features['total_timeout'] == 300.0
        assert features['service_count'] == 2.0  # service1 and service2
        assert features['dependency_count'] == 1.0  # Only step2 has dependencies
        assert features['historical_success_rate'] == 0.95
        assert features['system_load'] == 0.4
        assert features['error_rate_last_hour'] == 0.02
        assert features['avg_response_time'] == 150.0
        
    @pytest.mark.asyncio
    async def test_heuristic_prediction(self, ml_predictor):
        """Test heuristic prediction fallback"""
        steps = [
            SagaStep("step1", "Step 1", "service1", "action1", "undo1"),
            SagaStep("step2", "Step 2", "service2", "action2", "undo2"),
            SagaStep("step3", "Step 3", "service3", "action3", "undo3")
        ]
        
        saga_def = SagaDefinition(
            id="test_saga",
            name="Test Saga",
            description="Test",
            steps=steps
        )
        
        context = {'system_load': 0.5}
        
        prediction = await ml_predictor._heuristic_prediction(saga_def, context)
        
        assert 'failure_probability' in prediction
        assert 'confidence' in prediction
        assert 'risk_level' in prediction
        assert 'recommendations' in prediction
        assert prediction['confidence'] == 0.6  # Lower confidence for heuristic
        assert 0.0 <= prediction['failure_probability'] <= 1.0
        
    def test_get_risk_level(self, ml_predictor):
        """Test risk level classification"""
        assert ml_predictor._get_risk_level(0.1) == 'low'
        assert ml_predictor._get_risk_level(0.3) == 'medium'
        assert ml_predictor._get_risk_level(0.6) == 'high'
        assert ml_predictor._get_risk_level(0.9) == 'critical'
        
    @pytest.mark.asyncio
    async def test_generate_recommendations(self, ml_predictor):
        """Test recommendation generation"""
        # High risk recommendations
        recommendations = await ml_predictor._generate_recommendations(0.8, {})
        assert len(recommendations) > 0
        assert any('breaking down' in rec.lower() for rec in recommendations)
        assert any('circuit breaker' in rec.lower() for rec in recommendations)
        
        # Medium risk recommendations
        recommendations = await ml_predictor._generate_recommendations(0.4, {})
        assert len(recommendations) > 0
        assert any('timeout' in rec.lower() for rec in recommendations)
        
        # Low risk recommendations
        recommendations = await ml_predictor._generate_recommendations(0.2, {})
        assert len(recommendations) > 0

class TestIntelligentOrchestrator:
    """Test cases for IntelligentOrchestrator"""
    
    @pytest.fixture
    def orchestrator(self):
        """Create orchestrator instance for testing"""
        return IntelligentOrchestrator()
    
    @pytest.mark.asyncio
    async def test_initialize_orchestrator(self, orchestrator):
        """Test orchestrator initialization"""
        with patch('redis.from_url') as mock_redis:
            with patch.object(orchestrator.ml_predictor, 'load_model', new_callable=AsyncMock):
                with patch.object(orchestrator, '_load_saga_definitions', new_callable=AsyncMock):
                    await orchestrator.initialize()
                    
                    mock_redis.assert_called_once()
                    assert orchestrator.redis_client is not None
                    
    @pytest.mark.asyncio
    async def test_load_saga_definitions(self, orchestrator):
        """Test loading saga definitions"""
        await orchestrator._load_saga_definitions()
        
        assert len(orchestrator.saga_definitions) > 0
        assert 'payment_saga' in orchestrator.saga_definitions
        
        payment_saga = orchestrator.saga_definitions['payment_saga']
        assert payment_saga.name == "Payment Processing Saga"
        assert len(payment_saga.steps) == 3
        
    @pytest.mark.asyncio
    async def test_start_saga_success(self, orchestrator):
        """Test successful saga start"""
        # Setup
        await orchestrator._load_saga_definitions()
        orchestrator.ml_predictor = Mock()
        orchestrator.ml_predictor.predict_failure_probability = AsyncMock(return_value={
            'failure_probability': 0.2,
            'confidence': 0.8,
            'risk_level': 'low',
            'recommendations': []
        })
        
        request = SagaRequest(
            saga_id='payment_saga',
            correlation_id='test_corr_123',
            context={'user_id': '123', 'amount': 100.0}
        )
        
        with patch.object(orchestrator, '_execute_saga', new_callable=AsyncMock):
            execution = await orchestrator.start_saga(request)
            
            assert execution.saga_id == 'payment_saga'
            assert execution.correlation_id == 'test_corr_123'
            assert execution.status == 'pending'
            assert execution.context == {'user_id': '123', 'amount': 100.0}
            assert execution.ml_prediction is not None
            assert execution.ml_prediction['risk_level'] == 'low'
            
    @pytest.mark.asyncio
    async def test_start_saga_invalid_definition(self, orchestrator):
        """Test starting saga with invalid definition"""
        request = SagaRequest(
            saga_id='nonexistent_saga',
            correlation_id='test_corr_123',
            context={}
        )
        
        with pytest.raises(ValueError, match="Saga definition not found"):
            await orchestrator.start_saga(request)
            
    @pytest.mark.asyncio
    async def test_apply_optimizations_high_risk(self, orchestrator):
        """Test applying optimizations for high-risk saga"""
        await orchestrator._load_saga_definitions()
        saga_def = orchestrator.saga_definitions['payment_saga']
        
        execution = SagaExecution(
            id='test_exec',
            saga_id='payment_saga',
            correlation_id='test_corr',
            status='pending',
            ml_prediction={
                'failure_probability': 0.8,
                'risk_level': 'high'
            }
        )
        
        # Store original timeout values
        original_timeouts = [step.timeout for step in saga_def.steps]
        original_retries = [step.retry_count for step in saga_def.steps]
        
        await orchestrator._apply_optimizations(execution, saga_def)
        
        # Check that timeouts and retries were increased
        for i, step in enumerate(saga_def.steps):
            assert step.timeout > original_timeouts[i]
            assert step.retry_count >= original_retries[i]
            
    @pytest.mark.asyncio
    async def test_apply_optimizations_medium_risk(self, orchestrator):
        """Test applying optimizations for medium-risk saga"""
        await orchestrator._load_saga_definitions()
        saga_def = orchestrator.saga_definitions['payment_saga']
        
        execution = SagaExecution(
            id='test_exec',
            saga_id='payment_saga',
            correlation_id='test_corr',
            status='pending',
            ml_prediction={
                'failure_probability': 0.4,
                'risk_level': 'medium'
            }
        )
        
        # Store original timeout values
        original_timeouts = [step.timeout for step in saga_def.steps]
        
        await orchestrator._apply_optimizations(execution, saga_def)
        
        # Check that timeouts were moderately increased
        for i, step in enumerate(saga_def.steps):
            assert step.timeout >= original_timeouts[i]
            
    @pytest.mark.asyncio
    async def test_check_dependencies(self, orchestrator):
        """Test dependency checking"""
        step = SagaStep("test_step", "Test", "service", "action", "undo", dependencies=["dep1"])
        execution = SagaExecution("exec", "saga", "corr", "running")
        
        # For demo, dependencies are always satisfied
        result = await orchestrator._check_dependencies(step, execution)
        assert result is True
        
    @pytest.mark.asyncio
    async def test_execute_step_success(self, orchestrator):
        """Test successful step execution"""
        step = SagaStep("test_step", "Test", "service", "action", "undo")
        execution = SagaExecution("exec", "saga", "corr", "running")
        
        # Should complete without exception
        await orchestrator._execute_step(step, execution)
        
    @pytest.mark.asyncio
    async def test_execute_step_failure(self, orchestrator):
        """Test step execution failure"""
        step = SagaStep("test_step", "Test", "service", "action", "undo")
        execution = SagaExecution("exec", "saga", "corr", "running")
        
        # Mock random to always fail
        with patch('random.random', return_value=0.05):  # Less than 0.1 failure rate
            with pytest.raises(Exception, match="Step test_step failed"):
                await orchestrator._execute_step(step, execution)
                
    @pytest.mark.asyncio
    async def test_compensate_step(self, orchestrator):
        """Test step compensation"""
        step = SagaStep("test_step", "Test", "service", "action", "undo")
        execution = SagaExecution("exec", "saga", "corr", "compensating")
        
        # Should complete without exception
        await orchestrator._compensate_step(step, execution)

if __name__ == '__main__':
    pytest.main([__file__, '-v'])

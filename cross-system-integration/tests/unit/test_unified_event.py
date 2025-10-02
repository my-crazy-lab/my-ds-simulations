#!/usr/bin/env python3
"""
Unit tests for unified event system
"""

import pytest
import json
import time
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

# Mock the Go event types for Python testing
class EventType:
    SAGA_STARTED = "saga.started"
    SAGA_COMPLETED = "saga.completed"
    SAGA_FAILED = "saga.failed"
    DATA_INGESTED = "data.ingested"
    DRIFT_DETECTED = "drift.detected"

class EventSource:
    MICROSERVICES = "microservices"
    ANALYTICS = "analytics"
    AIML = "ai-ml"

class EventPriority:
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"

class UnifiedEvent:
    """Python version of UnifiedEvent for testing"""
    
    def __init__(self, event_type, source, data):
        self.id = f"test_{int(time.time())}"
        self.type = event_type
        self.source = source
        self.timestamp = datetime.now()
        self.correlation_id = f"corr_{int(time.time())}"
        self.causation_id = None
        self.data = data or {}
        self.metadata = {
            'version': '1.0',
            'priority': EventPriority.NORMAL,
            'tags': [],
            'ttl': None,
            'retry_count': 0,
            'max_retries': 3,
            'properties': {}
        }
        self.ml_context = None
    
    def with_correlation_id(self, correlation_id):
        self.correlation_id = correlation_id
        return self
    
    def with_priority(self, priority):
        self.metadata['priority'] = priority
        return self
    
    def with_tags(self, *tags):
        self.metadata['tags'].extend(tags)
        return self
    
    def with_ttl(self, ttl_seconds):
        self.metadata['ttl'] = ttl_seconds
        return self
    
    def with_ml_context(self, ml_context):
        self.ml_context = ml_context
        return self
    
    def is_expired(self):
        if not self.metadata.get('ttl'):
            return False
        elapsed = (datetime.now() - self.timestamp).total_seconds()
        return elapsed > self.metadata['ttl']
    
    def should_retry(self):
        return self.metadata['retry_count'] < self.metadata['max_retries']
    
    def increment_retry(self):
        self.metadata['retry_count'] += 1
    
    def to_json(self):
        return json.dumps({
            'id': self.id,
            'type': self.type,
            'source': self.source,
            'timestamp': self.timestamp.isoformat(),
            'correlation_id': self.correlation_id,
            'causation_id': self.causation_id,
            'data': self.data,
            'metadata': self.metadata,
            'ml_context': self.ml_context
        })
    
    def validate(self):
        errors = []
        if not self.id:
            errors.append("event ID is required")
        if not self.type:
            errors.append("event type is required")
        if not self.source:
            errors.append("event source is required")
        if not self.correlation_id:
            errors.append("correlation ID is required")
        if self.data is None:
            errors.append("event data is required")
        return errors

class TestUnifiedEvent:
    """Test cases for UnifiedEvent"""
    
    def test_create_basic_event(self):
        """Test creating a basic event"""
        data = {'user_id': '123', 'amount': 100.0}
        event = UnifiedEvent(EventType.SAGA_STARTED, EventSource.MICROSERVICES, data)
        
        assert event.id is not None
        assert event.type == EventType.SAGA_STARTED
        assert event.source == EventSource.MICROSERVICES
        assert event.data == data
        assert event.metadata['priority'] == EventPriority.NORMAL
        assert event.correlation_id is not None
        
    def test_event_builder_pattern(self):
        """Test event builder pattern"""
        event = (UnifiedEvent(EventType.SAGA_FAILED, EventSource.MICROSERVICES, {})
                .with_correlation_id('test-correlation')
                .with_priority(EventPriority.HIGH)
                .with_tags('urgent', 'payment')
                .with_ttl(3600))
        
        assert event.correlation_id == 'test-correlation'
        assert event.metadata['priority'] == EventPriority.HIGH
        assert 'urgent' in event.metadata['tags']
        assert 'payment' in event.metadata['tags']
        assert event.metadata['ttl'] == 3600
        
    def test_ml_context(self):
        """Test ML context functionality"""
        ml_context = {
            'model_version': '1.2.3',
            'prediction_score': 0.85,
            'confidence': 0.92,
            'feature_vector': [0.1, 0.2, 0.3]
        }
        
        event = UnifiedEvent(EventType.DRIFT_DETECTED, EventSource.AIML, {})
        event.with_ml_context(ml_context)
        
        assert event.ml_context == ml_context
        assert event.ml_context['model_version'] == '1.2.3'
        assert event.ml_context['prediction_score'] == 0.85
        
    def test_event_expiration(self):
        """Test event TTL and expiration"""
        event = UnifiedEvent(EventType.DATA_INGESTED, EventSource.ANALYTICS, {})
        
        # Event without TTL should not expire
        assert not event.is_expired()
        
        # Event with TTL in future should not expire
        event.with_ttl(3600)  # 1 hour
        assert not event.is_expired()
        
        # Simulate expired event
        event.timestamp = datetime.now() - timedelta(hours=2)
        assert event.is_expired()
        
    def test_retry_logic(self):
        """Test retry logic"""
        event = UnifiedEvent(EventType.SAGA_FAILED, EventSource.MICROSERVICES, {})
        
        # Should be able to retry initially
        assert event.should_retry()
        assert event.metadata['retry_count'] == 0
        
        # Increment retries
        for i in range(3):
            event.increment_retry()
            assert event.metadata['retry_count'] == i + 1
            
        # Should not retry after max retries
        assert not event.should_retry()
        
    def test_event_validation(self):
        """Test event validation"""
        # Valid event
        event = UnifiedEvent(EventType.SAGA_STARTED, EventSource.MICROSERVICES, {'test': 'data'})
        errors = event.validate()
        assert len(errors) == 0
        
        # Invalid event - missing required fields
        invalid_event = UnifiedEvent('', '', None)
        invalid_event.id = ''
        invalid_event.correlation_id = ''
        errors = invalid_event.validate()
        
        assert len(errors) > 0
        assert any('event ID is required' in error for error in errors)
        assert any('event type is required' in error for error in errors)
        assert any('event source is required' in error for error in errors)
        assert any('correlation ID is required' in error for error in errors)
        assert any('event data is required' in error for error in errors)
        
    def test_json_serialization(self):
        """Test JSON serialization"""
        data = {'user_id': '123', 'amount': 100.0}
        event = UnifiedEvent(EventType.SAGA_STARTED, EventSource.MICROSERVICES, data)
        event.with_priority(EventPriority.HIGH).with_tags('test')
        
        json_str = event.to_json()
        assert json_str is not None
        
        # Parse back and verify
        parsed = json.loads(json_str)
        assert parsed['id'] == event.id
        assert parsed['type'] == event.type
        assert parsed['source'] == event.source
        assert parsed['data'] == data
        assert parsed['metadata']['priority'] == EventPriority.HIGH
        assert 'test' in parsed['metadata']['tags']

class EventFilter:
    """Event filter for testing"""
    
    def __init__(self, types=None, sources=None, tags=None, min_priority=None):
        self.types = types or []
        self.sources = sources or []
        self.tags = tags or []
        self.min_priority = min_priority
        
    def matches(self, event):
        # Check types
        if self.types and event.type not in self.types:
            return False
            
        # Check sources
        if self.sources and event.source not in self.sources:
            return False
            
        # Check tags
        if self.tags:
            event_tags = event.metadata.get('tags', [])
            for required_tag in self.tags:
                if required_tag not in event_tags:
                    return False
                    
        # Check priority
        if self.min_priority:
            priority_levels = {
                EventPriority.LOW: 1,
                EventPriority.NORMAL: 2,
                EventPriority.HIGH: 3,
                EventPriority.CRITICAL: 4
            }
            event_level = priority_levels.get(event.metadata['priority'], 0)
            min_level = priority_levels.get(self.min_priority, 0)
            if event_level < min_level:
                return False
                
        return True

class TestEventFilter:
    """Test cases for EventFilter"""
    
    def test_filter_by_type(self):
        """Test filtering by event type"""
        filter_obj = EventFilter(types=[EventType.SAGA_STARTED, EventType.SAGA_COMPLETED])
        
        # Matching event
        event1 = UnifiedEvent(EventType.SAGA_STARTED, EventSource.MICROSERVICES, {})
        assert filter_obj.matches(event1)
        
        # Non-matching event
        event2 = UnifiedEvent(EventType.DRIFT_DETECTED, EventSource.AIML, {})
        assert not filter_obj.matches(event2)
        
    def test_filter_by_source(self):
        """Test filtering by event source"""
        filter_obj = EventFilter(sources=[EventSource.MICROSERVICES])
        
        # Matching event
        event1 = UnifiedEvent(EventType.SAGA_STARTED, EventSource.MICROSERVICES, {})
        assert filter_obj.matches(event1)
        
        # Non-matching event
        event2 = UnifiedEvent(EventType.DATA_INGESTED, EventSource.ANALYTICS, {})
        assert not filter_obj.matches(event2)
        
    def test_filter_by_tags(self):
        """Test filtering by tags"""
        filter_obj = EventFilter(tags=['urgent', 'payment'])
        
        # Matching event
        event1 = UnifiedEvent(EventType.SAGA_FAILED, EventSource.MICROSERVICES, {})
        event1.with_tags('urgent', 'payment', 'retry')
        assert filter_obj.matches(event1)
        
        # Non-matching event (missing required tag)
        event2 = UnifiedEvent(EventType.SAGA_FAILED, EventSource.MICROSERVICES, {})
        event2.with_tags('urgent')  # Missing 'payment' tag
        assert not filter_obj.matches(event2)
        
    def test_filter_by_priority(self):
        """Test filtering by minimum priority"""
        filter_obj = EventFilter(min_priority=EventPriority.HIGH)
        
        # Matching events (high and critical priority)
        event1 = UnifiedEvent(EventType.SAGA_FAILED, EventSource.MICROSERVICES, {})
        event1.with_priority(EventPriority.HIGH)
        assert filter_obj.matches(event1)
        
        event2 = UnifiedEvent(EventType.SAGA_FAILED, EventSource.MICROSERVICES, {})
        event2.with_priority(EventPriority.CRITICAL)
        assert filter_obj.matches(event2)
        
        # Non-matching events (normal and low priority)
        event3 = UnifiedEvent(EventType.SAGA_FAILED, EventSource.MICROSERVICES, {})
        event3.with_priority(EventPriority.NORMAL)
        assert not filter_obj.matches(event3)
        
        event4 = UnifiedEvent(EventType.SAGA_FAILED, EventSource.MICROSERVICES, {})
        event4.with_priority(EventPriority.LOW)
        assert not filter_obj.matches(event4)
        
    def test_combined_filters(self):
        """Test combining multiple filters"""
        filter_obj = EventFilter(
            types=[EventType.SAGA_FAILED],
            sources=[EventSource.MICROSERVICES],
            tags=['urgent'],
            min_priority=EventPriority.HIGH
        )
        
        # Event matching all criteria
        event1 = (UnifiedEvent(EventType.SAGA_FAILED, EventSource.MICROSERVICES, {})
                 .with_tags('urgent', 'payment')
                 .with_priority(EventPriority.HIGH))
        assert filter_obj.matches(event1)
        
        # Event failing type check
        event2 = (UnifiedEvent(EventType.SAGA_STARTED, EventSource.MICROSERVICES, {})
                 .with_tags('urgent')
                 .with_priority(EventPriority.HIGH))
        assert not filter_obj.matches(event2)
        
        # Event failing priority check
        event3 = (UnifiedEvent(EventType.SAGA_FAILED, EventSource.MICROSERVICES, {})
                 .with_tags('urgent')
                 .with_priority(EventPriority.NORMAL))
        assert not filter_obj.matches(event3)

if __name__ == '__main__':
    pytest.main([__file__, '-v'])

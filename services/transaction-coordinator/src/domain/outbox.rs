use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use uuid::Uuid;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OutboxEvent {
    pub id: Uuid,
    pub aggregate_id: String,
    pub aggregate_type: String,
    pub event_type: String,
    pub event_data: serde_json::Value,
    pub metadata: HashMap<String, serde_json::Value>,
    pub created_at: DateTime<Utc>,
    pub processed_at: Option<DateTime<Utc>>,
    pub status: OutboxEventStatus,
    pub retry_count: u32,
    pub max_retries: u32,
    pub next_retry_at: Option<DateTime<Utc>>,
    pub error_message: Option<String>,
    pub correlation_id: Option<String>,
    pub causation_id: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum OutboxEventStatus {
    Pending,
    Processing,
    Processed,
    Failed,
    DeadLetter,
}

impl OutboxEvent {
    pub fn new(
        aggregate_id: String,
        aggregate_type: String,
        event_type: String,
        event_data: serde_json::Value,
        metadata: HashMap<String, serde_json::Value>,
    ) -> Self {
        Self {
            id: Uuid::new_v4(),
            aggregate_id,
            aggregate_type,
            event_type,
            event_data,
            metadata,
            created_at: Utc::now(),
            processed_at: None,
            status: OutboxEventStatus::Pending,
            retry_count: 0,
            max_retries: 5,
            next_retry_at: None,
            error_message: None,
            correlation_id: None,
            causation_id: None,
        }
    }

    pub fn with_correlation_id(mut self, correlation_id: String) -> Self {
        self.correlation_id = Some(correlation_id);
        self
    }

    pub fn with_causation_id(mut self, causation_id: String) -> Self {
        self.causation_id = Some(causation_id);
        self
    }

    pub fn with_max_retries(mut self, max_retries: u32) -> Self {
        self.max_retries = max_retries;
        self
    }

    pub fn mark_processing(&mut self) {
        self.status = OutboxEventStatus::Processing;
    }

    pub fn mark_processed(&mut self) {
        self.status = OutboxEventStatus::Processed;
        self.processed_at = Some(Utc::now());
        self.error_message = None;
    }

    pub fn mark_failed(&mut self, error_message: String) {
        self.retry_count += 1;
        self.error_message = Some(error_message);

        if self.retry_count >= self.max_retries {
            self.status = OutboxEventStatus::DeadLetter;
        } else {
            self.status = OutboxEventStatus::Failed;
            // Exponential backoff: 2^retry_count seconds
            let delay_seconds = 2_u64.pow(self.retry_count);
            self.next_retry_at = Some(Utc::now() + chrono::Duration::seconds(delay_seconds as i64));
        }
    }

    pub fn can_retry(&self) -> bool {
        matches!(self.status, OutboxEventStatus::Failed) &&
        self.retry_count < self.max_retries &&
        self.next_retry_at.map_or(true, |retry_at| Utc::now() >= retry_at)
    }

    pub fn reset_for_retry(&mut self) {
        self.status = OutboxEventStatus::Pending;
        self.next_retry_at = None;
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OutboxEventFilter {
    pub aggregate_type: Option<String>,
    pub event_type: Option<String>,
    pub status: Option<OutboxEventStatus>,
    pub created_after: Option<DateTime<Utc>>,
    pub created_before: Option<DateTime<Utc>>,
    pub limit: Option<u32>,
}

impl Default for OutboxEventFilter {
    fn default() -> Self {
        Self {
            aggregate_type: None,
            event_type: None,
            status: None,
            created_after: None,
            created_before: None,
            limit: Some(100),
        }
    }
}

// Event types for different domain events
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TransactionCreatedEvent {
    pub transaction_id: Uuid,
    pub transaction_type: String,
    pub participants: Vec<String>,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TransactionCommittedEvent {
    pub transaction_id: Uuid,
    pub transaction_type: String,
    pub committed_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TransactionAbortedEvent {
    pub transaction_id: Uuid,
    pub transaction_type: String,
    pub reason: Option<String>,
    pub aborted_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SagaCreatedEvent {
    pub saga_id: Uuid,
    pub saga_type: String,
    pub steps: Vec<String>,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SagaCompletedEvent {
    pub saga_id: Uuid,
    pub saga_type: String,
    pub completed_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SagaCompensatedEvent {
    pub saga_id: Uuid,
    pub saga_type: String,
    pub reason: Option<String>,
    pub compensated_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SagaStepCompletedEvent {
    pub saga_id: Uuid,
    pub step_id: String,
    pub step_type: String,
    pub response_data: Option<serde_json::Value>,
    pub completed_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SagaStepFailedEvent {
    pub saga_id: Uuid,
    pub step_id: String,
    pub step_type: String,
    pub error_message: String,
    pub failed_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SagaStepCompensatedEvent {
    pub saga_id: Uuid,
    pub step_id: String,
    pub step_type: String,
    pub compensated_at: DateTime<Utc>,
}

// Helper functions for creating domain events
impl OutboxEvent {
    pub fn transaction_created(transaction_id: Uuid, transaction_type: String, participants: Vec<String>) -> Self {
        let event_data = TransactionCreatedEvent {
            transaction_id,
            transaction_type: transaction_type.clone(),
            participants,
            created_at: Utc::now(),
        };

        Self::new(
            transaction_id.to_string(),
            "Transaction".to_string(),
            "TransactionCreated".to_string(),
            serde_json::to_value(event_data).unwrap(),
            HashMap::new(),
        )
    }

    pub fn transaction_committed(transaction_id: Uuid, transaction_type: String) -> Self {
        let event_data = TransactionCommittedEvent {
            transaction_id,
            transaction_type: transaction_type.clone(),
            committed_at: Utc::now(),
        };

        Self::new(
            transaction_id.to_string(),
            "Transaction".to_string(),
            "TransactionCommitted".to_string(),
            serde_json::to_value(event_data).unwrap(),
            HashMap::new(),
        )
    }

    pub fn saga_created(saga_id: Uuid, saga_type: String, steps: Vec<String>) -> Self {
        let event_data = SagaCreatedEvent {
            saga_id,
            saga_type: saga_type.clone(),
            steps,
            created_at: Utc::now(),
        };

        Self::new(
            saga_id.to_string(),
            "Saga".to_string(),
            "SagaCreated".to_string(),
            serde_json::to_value(event_data).unwrap(),
            HashMap::new(),
        )
    }

    pub fn saga_step_completed(saga_id: Uuid, step_id: String, step_type: String, response_data: Option<serde_json::Value>) -> Self {
        let event_data = SagaStepCompletedEvent {
            saga_id,
            step_id: step_id.clone(),
            step_type,
            response_data,
            completed_at: Utc::now(),
        };

        Self::new(
            saga_id.to_string(),
            "Saga".to_string(),
            "SagaStepCompleted".to_string(),
            serde_json::to_value(event_data).unwrap(),
            HashMap::new(),
        )
    }
}

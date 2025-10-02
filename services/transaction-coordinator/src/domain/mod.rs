use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use uuid::Uuid;

// Re-export domain types
pub use self::transaction::*;
pub use self::saga::*;
pub use self::outbox::*;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CreateTransactionRequest {
    pub transaction_type: String,
    pub participants: Vec<TransactionParticipant>,
    pub metadata: HashMap<String, serde_json::Value>,
    pub timeout_seconds: Option<u64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TransactionParticipant {
    pub service_name: String,
    pub endpoint: String,
    pub operation: String,
    pub payload: serde_json::Value,
    pub compensation_endpoint: Option<String>,
    pub compensation_payload: Option<serde_json::Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TransactionResponse {
    pub id: Uuid,
    pub status: TransactionStatus,
    pub transaction_type: String,
    pub participants: Vec<TransactionParticipant>,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
    pub completed_at: Option<DateTime<Utc>>,
    pub error_message: Option<String>,
    pub metadata: HashMap<String, serde_json::Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CreateSagaRequest {
    pub saga_type: String,
    pub steps: Vec<SagaStep>,
    pub metadata: HashMap<String, serde_json::Value>,
    pub timeout_seconds: Option<u64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SagaStep {
    pub step_id: String,
    pub service_name: String,
    pub action_endpoint: String,
    pub action_payload: serde_json::Value,
    pub compensation_endpoint: String,
    pub compensation_payload: serde_json::Value,
    pub retry_policy: RetryPolicy,
    pub depends_on: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RetryPolicy {
    pub max_attempts: u32,
    pub initial_delay_ms: u64,
    pub max_delay_ms: u64,
    pub backoff_multiplier: f64,
}

impl Default for RetryPolicy {
    fn default() -> Self {
        Self {
            max_attempts: 3,
            initial_delay_ms: 1000,
            max_delay_ms: 30000,
            backoff_multiplier: 2.0,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SagaResponse {
    pub id: Uuid,
    pub status: SagaStatus,
    pub saga_type: String,
    pub steps: Vec<SagaStepExecution>,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
    pub completed_at: Option<DateTime<Utc>>,
    pub error_message: Option<String>,
    pub metadata: HashMap<String, serde_json::Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SagaStepExecution {
    pub step_id: String,
    pub status: StepStatus,
    pub started_at: Option<DateTime<Utc>>,
    pub completed_at: Option<DateTime<Utc>>,
    pub attempt_count: u32,
    pub error_message: Option<String>,
    pub response_data: Option<serde_json::Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum TransactionStatus {
    Pending,
    Preparing,
    Prepared,
    Committing,
    Committed,
    Aborting,
    Aborted,
    Failed,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum SagaStatus {
    Created,
    Running,
    Completed,
    Compensating,
    Compensated,
    Failed,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum StepStatus {
    Pending,
    Running,
    Completed,
    Compensating,
    Compensated,
    Failed,
    Skipped,
}

// Error types
#[derive(Debug, thiserror::Error)]
pub enum TransactionError {
    #[error("Transaction not found: {0}")]
    NotFound(Uuid),
    
    #[error("Invalid transaction state: expected {expected}, got {actual}")]
    InvalidState { expected: String, actual: String },
    
    #[error("Participant error: {service} - {message}")]
    ParticipantError { service: String, message: String },
    
    #[error("Timeout error: transaction {0} timed out")]
    Timeout(Uuid),
    
    #[error("Database error: {0}")]
    Database(#[from] mongodb::error::Error),
    
    #[error("Redis error: {0}")]
    Redis(#[from] redis::RedisError),
    
    #[error("Serialization error: {0}")]
    Serialization(#[from] serde_json::Error),
    
    #[error("HTTP error: {0}")]
    Http(#[from] reqwest::Error),
    
    #[error("Internal error: {0}")]
    Internal(String),
}

#[derive(Debug, thiserror::Error)]
pub enum SagaError {
    #[error("Saga not found: {0}")]
    NotFound(Uuid),
    
    #[error("Invalid saga state: expected {expected}, got {actual}")]
    InvalidState { expected: String, actual: String },
    
    #[error("Step execution error: {step_id} - {message}")]
    StepError { step_id: String, message: String },
    
    #[error("Compensation error: {step_id} - {message}")]
    CompensationError { step_id: String, message: String },
    
    #[error("Dependency error: step {step_id} depends on failed step {dependency}")]
    DependencyError { step_id: String, dependency: String },
    
    #[error("Timeout error: saga {0} timed out")]
    Timeout(Uuid),
    
    #[error("Database error: {0}")]
    Database(#[from] mongodb::error::Error),
    
    #[error("Serialization error: {0}")]
    Serialization(#[from] serde_json::Error),
    
    #[error("HTTP error: {0}")]
    Http(#[from] reqwest::Error),
    
    #[error("Internal error: {0}")]
    Internal(String),
}

pub type TransactionResult<T> = Result<T, TransactionError>;
pub type SagaResult<T> = Result<T, SagaError>;

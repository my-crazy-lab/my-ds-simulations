use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use uuid::Uuid;

use super::{TransactionStatus, TransactionParticipant, TransactionResponse};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Transaction {
    pub id: Uuid,
    pub status: TransactionStatus,
    pub transaction_type: String,
    pub participants: Vec<TransactionParticipant>,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
    pub completed_at: Option<DateTime<Utc>>,
    pub timeout_at: Option<DateTime<Utc>>,
    pub error_message: Option<String>,
    pub metadata: HashMap<String, serde_json::Value>,
    pub participant_responses: HashMap<String, ParticipantResponse>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ParticipantResponse {
    pub service_name: String,
    pub status: ParticipantStatus,
    pub response_data: Option<serde_json::Value>,
    pub error_message: Option<String>,
    pub timestamp: DateTime<Utc>,
    pub attempt_count: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum ParticipantStatus {
    Pending,
    Preparing,
    Prepared,
    Committed,
    Aborted,
    Failed,
}

impl Transaction {
    pub fn new(
        transaction_type: String,
        participants: Vec<TransactionParticipant>,
        metadata: HashMap<String, serde_json::Value>,
        timeout_seconds: Option<u64>,
    ) -> Self {
        let now = Utc::now();
        let timeout_at = timeout_seconds.map(|seconds| now + chrono::Duration::seconds(seconds as i64));
        
        Self {
            id: Uuid::new_v4(),
            status: TransactionStatus::Pending,
            transaction_type,
            participants,
            created_at: now,
            updated_at: now,
            completed_at: None,
            timeout_at,
            error_message: None,
            metadata,
            participant_responses: HashMap::new(),
        }
    }

    pub fn update_status(&mut self, status: TransactionStatus) {
        self.status = status;
        self.updated_at = Utc::now();
        
        if matches!(status, TransactionStatus::Committed | TransactionStatus::Aborted | TransactionStatus::Failed) {
            self.completed_at = Some(Utc::now());
        }
    }

    pub fn add_participant_response(&mut self, service_name: String, response: ParticipantResponse) {
        self.participant_responses.insert(service_name, response);
        self.updated_at = Utc::now();
    }

    pub fn set_error(&mut self, error_message: String) {
        self.error_message = Some(error_message);
        self.updated_at = Utc::now();
    }

    pub fn is_timed_out(&self) -> bool {
        if let Some(timeout_at) = self.timeout_at {
            Utc::now() > timeout_at
        } else {
            false
        }
    }

    pub fn can_commit(&self) -> bool {
        matches!(self.status, TransactionStatus::Prepared) &&
        self.participant_responses.values().all(|r| r.status == ParticipantStatus::Prepared)
    }

    pub fn can_abort(&self) -> bool {
        !matches!(self.status, TransactionStatus::Committed | TransactionStatus::Aborted)
    }

    pub fn all_participants_responded(&self) -> bool {
        self.participants.len() == self.participant_responses.len()
    }

    pub fn has_failed_participants(&self) -> bool {
        self.participant_responses.values().any(|r| r.status == ParticipantStatus::Failed)
    }
}

impl From<Transaction> for TransactionResponse {
    fn from(transaction: Transaction) -> Self {
        Self {
            id: transaction.id,
            status: transaction.status,
            transaction_type: transaction.transaction_type,
            participants: transaction.participants,
            created_at: transaction.created_at,
            updated_at: transaction.updated_at,
            completed_at: transaction.completed_at,
            error_message: transaction.error_message,
            metadata: transaction.metadata,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PrepareRequest {
    pub transaction_id: Uuid,
    pub operation: String,
    pub payload: serde_json::Value,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PrepareResponse {
    pub transaction_id: Uuid,
    pub status: ParticipantStatus,
    pub response_data: Option<serde_json::Value>,
    pub error_message: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CommitRequest {
    pub transaction_id: Uuid,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CommitResponse {
    pub transaction_id: Uuid,
    pub status: ParticipantStatus,
    pub response_data: Option<serde_json::Value>,
    pub error_message: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AbortRequest {
    pub transaction_id: Uuid,
    pub reason: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AbortResponse {
    pub transaction_id: Uuid,
    pub status: ParticipantStatus,
    pub error_message: Option<String>,
}

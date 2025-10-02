use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use uuid::Uuid;

use super::{SagaStatus, StepStatus, SagaStep, SagaStepExecution, SagaResponse, RetryPolicy};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Saga {
    pub id: Uuid,
    pub status: SagaStatus,
    pub saga_type: String,
    pub steps: Vec<SagaStep>,
    pub step_executions: HashMap<String, SagaStepExecution>,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
    pub completed_at: Option<DateTime<Utc>>,
    pub timeout_at: Option<DateTime<Utc>>,
    pub error_message: Option<String>,
    pub metadata: HashMap<String, serde_json::Value>,
    pub current_step_index: usize,
    pub compensation_steps: Vec<String>,
}

impl Saga {
    pub fn new(
        saga_type: String,
        steps: Vec<SagaStep>,
        metadata: HashMap<String, serde_json::Value>,
        timeout_seconds: Option<u64>,
    ) -> Self {
        let now = Utc::now();
        let timeout_at = timeout_seconds.map(|seconds| now + chrono::Duration::seconds(seconds as i64));
        
        let mut step_executions = HashMap::new();
        for step in &steps {
            step_executions.insert(
                step.step_id.clone(),
                SagaStepExecution {
                    step_id: step.step_id.clone(),
                    status: StepStatus::Pending,
                    started_at: None,
                    completed_at: None,
                    attempt_count: 0,
                    error_message: None,
                    response_data: None,
                },
            );
        }

        Self {
            id: Uuid::new_v4(),
            status: SagaStatus::Created,
            saga_type,
            steps,
            step_executions,
            created_at: now,
            updated_at: now,
            completed_at: None,
            timeout_at,
            error_message: None,
            metadata,
            current_step_index: 0,
            compensation_steps: Vec::new(),
        }
    }

    pub fn update_status(&mut self, status: SagaStatus) {
        self.status = status;
        self.updated_at = Utc::now();
        
        if matches!(status, SagaStatus::Completed | SagaStatus::Compensated | SagaStatus::Failed) {
            self.completed_at = Some(Utc::now());
        }
    }

    pub fn start_step(&mut self, step_id: &str) -> Result<(), String> {
        if let Some(execution) = self.step_executions.get_mut(step_id) {
            execution.status = StepStatus::Running;
            execution.started_at = Some(Utc::now());
            execution.attempt_count += 1;
            self.updated_at = Utc::now();
            Ok(())
        } else {
            Err(format!("Step not found: {}", step_id))
        }
    }

    pub fn complete_step(&mut self, step_id: &str, response_data: Option<serde_json::Value>) -> Result<(), String> {
        if let Some(execution) = self.step_executions.get_mut(step_id) {
            execution.status = StepStatus::Completed;
            execution.completed_at = Some(Utc::now());
            execution.response_data = response_data;
            self.updated_at = Utc::now();
            Ok(())
        } else {
            Err(format!("Step not found: {}", step_id))
        }
    }

    pub fn fail_step(&mut self, step_id: &str, error_message: String) -> Result<(), String> {
        if let Some(execution) = self.step_executions.get_mut(step_id) {
            execution.status = StepStatus::Failed;
            execution.completed_at = Some(Utc::now());
            execution.error_message = Some(error_message);
            self.updated_at = Utc::now();
            Ok(())
        } else {
            Err(format!("Step not found: {}", step_id))
        }
    }

    pub fn start_compensation(&mut self, step_id: &str) -> Result<(), String> {
        if let Some(execution) = self.step_executions.get_mut(step_id) {
            execution.status = StepStatus::Compensating;
            execution.attempt_count += 1;
            self.updated_at = Utc::now();
            Ok(())
        } else {
            Err(format!("Step not found: {}", step_id))
        }
    }

    pub fn complete_compensation(&mut self, step_id: &str) -> Result<(), String> {
        if let Some(execution) = self.step_executions.get_mut(step_id) {
            execution.status = StepStatus::Compensated;
            execution.completed_at = Some(Utc::now());
            self.updated_at = Utc::now();
            Ok(())
        } else {
            Err(format!("Step not found: {}", step_id))
        }
    }

    pub fn get_next_step(&self) -> Option<&SagaStep> {
        if self.current_step_index < self.steps.len() {
            Some(&self.steps[self.current_step_index])
        } else {
            None
        }
    }

    pub fn get_ready_steps(&self) -> Vec<&SagaStep> {
        self.steps
            .iter()
            .filter(|step| {
                let execution = self.step_executions.get(&step.step_id).unwrap();
                execution.status == StepStatus::Pending && self.are_dependencies_satisfied(&step.depends_on)
            })
            .collect()
    }

    pub fn are_dependencies_satisfied(&self, dependencies: &[String]) -> bool {
        dependencies.iter().all(|dep| {
            if let Some(execution) = self.step_executions.get(dep) {
                execution.status == StepStatus::Completed
            } else {
                false
            }
        })
    }

    pub fn get_compensation_steps(&self) -> Vec<&SagaStep> {
        self.compensation_steps
            .iter()
            .filter_map(|step_id| {
                self.steps.iter().find(|step| step.step_id == *step_id)
            })
            .collect()
    }

    pub fn add_compensation_step(&mut self, step_id: String) {
        if !self.compensation_steps.contains(&step_id) {
            self.compensation_steps.push(step_id);
        }
    }

    pub fn is_timed_out(&self) -> bool {
        if let Some(timeout_at) = self.timeout_at {
            Utc::now() > timeout_at
        } else {
            false
        }
    }

    pub fn is_completed(&self) -> bool {
        self.step_executions.values().all(|execution| {
            matches!(execution.status, StepStatus::Completed | StepStatus::Skipped)
        })
    }

    pub fn has_failed_steps(&self) -> bool {
        self.step_executions.values().any(|execution| execution.status == StepStatus::Failed)
    }

    pub fn set_error(&mut self, error_message: String) {
        self.error_message = Some(error_message);
        self.updated_at = Utc::now();
    }
}

impl From<Saga> for SagaResponse {
    fn from(saga: Saga) -> Self {
        let step_executions: Vec<SagaStepExecution> = saga
            .step_executions
            .into_values()
            .collect();

        Self {
            id: saga.id,
            status: saga.status,
            saga_type: saga.saga_type,
            steps: step_executions,
            created_at: saga.created_at,
            updated_at: saga.updated_at,
            completed_at: saga.completed_at,
            error_message: saga.error_message,
            metadata: saga.metadata,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SagaActionRequest {
    pub saga_id: Uuid,
    pub step_id: String,
    pub action_payload: serde_json::Value,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SagaActionResponse {
    pub saga_id: Uuid,
    pub step_id: String,
    pub status: StepStatus,
    pub response_data: Option<serde_json::Value>,
    pub error_message: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SagaCompensationRequest {
    pub saga_id: Uuid,
    pub step_id: String,
    pub compensation_payload: serde_json::Value,
    pub reason: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SagaCompensationResponse {
    pub saga_id: Uuid,
    pub step_id: String,
    pub status: StepStatus,
    pub error_message: Option<String>,
}

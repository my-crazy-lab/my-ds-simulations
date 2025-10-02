use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Order {
    #[serde(rename = "_id")]
    pub id: Uuid,
    pub customer_id: Uuid,
    pub items: Vec<OrderItem>,
    pub total_amount: f64,
    pub status: OrderStatus,
    pub saga_id: Option<Uuid>,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
    pub version: i64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OrderItem {
    pub product_id: Uuid,
    pub quantity: i32,
    pub unit_price: f64,
    pub total_price: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum OrderStatus {
    Pending,
    PaymentProcessing,
    InventoryReserved,
    Confirmed,
    Shipped,
    Delivered,
    Cancelled,
    Failed,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CreateOrderRequest {
    pub customer_id: Uuid,
    pub items: Vec<CreateOrderItem>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CreateOrderItem {
    pub product_id: Uuid,
    pub quantity: i32,
    pub unit_price: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OutboxEvent {
    #[serde(rename = "_id")]
    pub id: Uuid,
    pub aggregate_id: Uuid,
    pub event_type: String,
    pub event_data: serde_json::Value,
    pub created_at: DateTime<Utc>,
    pub processed: bool,
    pub processed_at: Option<DateTime<Utc>>,
    pub retry_count: i32,
    pub max_retries: i32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SagaTransaction {
    #[serde(rename = "_id")]
    pub id: Uuid,
    pub saga_id: Uuid,
    pub order_id: Uuid,
    pub step: String,
    pub status: SagaTransactionStatus,
    pub compensation_data: Option<serde_json::Value>,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum SagaTransactionStatus {
    Pending,
    Completed,
    Failed,
    Compensated,
}

impl Order {
    pub fn new(customer_id: Uuid, items: Vec<OrderItem>) -> Self {
        let total_amount = items.iter().map(|item| item.total_price).sum();
        let now = Utc::now();

        Self {
            id: Uuid::new_v4(),
            customer_id,
            items,
            total_amount,
            status: OrderStatus::Pending,
            saga_id: None,
            created_at: now,
            updated_at: now,
            version: 1,
        }
    }

    pub fn update_status(&mut self, status: OrderStatus) {
        self.status = status;
        self.updated_at = Utc::now();
        self.version += 1;
    }

    pub fn set_saga_id(&mut self, saga_id: Uuid) {
        self.saga_id = Some(saga_id);
        self.updated_at = Utc::now();
        self.version += 1;
    }

    pub fn can_be_cancelled(&self) -> bool {
        matches!(
            self.status,
            OrderStatus::Pending | OrderStatus::PaymentProcessing | OrderStatus::InventoryReserved
        )
    }

    pub fn can_be_completed(&self) -> bool {
        matches!(self.status, OrderStatus::InventoryReserved)
    }
}

impl OrderItem {
    pub fn new(product_id: Uuid, quantity: i32, unit_price: f64) -> Self {
        Self {
            product_id,
            quantity,
            unit_price,
            total_price: quantity as f64 * unit_price,
        }
    }
}

impl OutboxEvent {
    pub fn new(
        aggregate_id: Uuid,
        event_type: String,
        event_data: serde_json::Value,
    ) -> Self {
        Self {
            id: Uuid::new_v4(),
            aggregate_id,
            event_type,
            event_data,
            created_at: Utc::now(),
            processed: false,
            processed_at: None,
            retry_count: 0,
            max_retries: 3,
        }
    }

    pub fn mark_processed(&mut self) {
        self.processed = true;
        self.processed_at = Some(Utc::now());
    }

    pub fn increment_retry(&mut self) {
        self.retry_count += 1;
    }

    pub fn can_retry(&self) -> bool {
        self.retry_count < self.max_retries
    }
}

impl SagaTransaction {
    pub fn new(saga_id: Uuid, order_id: Uuid, step: String) -> Self {
        let now = Utc::now();
        Self {
            id: Uuid::new_v4(),
            saga_id,
            order_id,
            step,
            status: SagaTransactionStatus::Pending,
            compensation_data: None,
            created_at: now,
            updated_at: now,
        }
    }

    pub fn complete(&mut self) {
        self.status = SagaTransactionStatus::Completed;
        self.updated_at = Utc::now();
    }

    pub fn fail(&mut self) {
        self.status = SagaTransactionStatus::Failed;
        self.updated_at = Utc::now();
    }

    pub fn compensate(&mut self, compensation_data: serde_json::Value) {
        self.status = SagaTransactionStatus::Compensated;
        self.compensation_data = Some(compensation_data);
        self.updated_at = Utc::now();
    }
}

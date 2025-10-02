use axum::{
    extract::{Path, State},
    http::StatusCode,
    response::Json,
    routing::{get, post},
    Router,
};
use std::sync::Arc;
use tokio::net::TcpListener;
use tower_http::cors::CorsLayer;
use tracing::{info, warn, error};
use uuid::Uuid;

mod config;
mod domain;
mod handlers;
mod infrastructure;
mod services;

use config::Config;
use domain::*;
use infrastructure::*;
use services::*;

#[derive(Clone)]
pub struct AppState {
    pub transaction_service: Arc<TransactionCoordinatorService>,
    pub saga_service: Arc<SagaOrchestratorService>,
    pub outbox_service: Arc<OutboxService>,
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    // Initialize tracing
    tracing_subscriber::fmt()
        .with_env_filter("transaction_coordinator=debug,tower_http=debug")
        .init();

    info!("Starting Transaction Coordinator Service");

    // Load configuration
    let config = Config::from_env()?;
    
    // Initialize infrastructure
    let mongo_client = MongoRepository::new(&config.mongodb_url).await?;
    let redis_client = RedisRepository::new(&config.redis_url).await?;
    let kafka_producer = KafkaEventPublisher::new(&config.kafka_brokers).await?;
    
    // Initialize services
    let transaction_service = Arc::new(
        TransactionCoordinatorService::new(
            Arc::new(mongo_client.clone()),
            Arc::new(redis_client.clone()),
            Arc::new(kafka_producer.clone()),
        )
    );
    
    let saga_service = Arc::new(
        SagaOrchestratorService::new(
            Arc::new(mongo_client.clone()),
            Arc::new(kafka_producer.clone()),
        )
    );
    
    let outbox_service = Arc::new(
        OutboxService::new(
            Arc::new(mongo_client),
            Arc::new(kafka_producer),
        )
    );

    // Start background services
    let outbox_processor = outbox_service.clone();
    tokio::spawn(async move {
        outbox_processor.start_processing().await;
    });

    let saga_processor = saga_service.clone();
    tokio::spawn(async move {
        saga_processor.start_processing().await;
    });

    // Create application state
    let app_state = AppState {
        transaction_service,
        saga_service,
        outbox_service,
    };

    // Build router
    let app = Router::new()
        .route("/health", get(health_check))
        .route("/transactions", post(create_transaction))
        .route("/transactions/:id", get(get_transaction))
        .route("/transactions/:id/commit", post(commit_transaction))
        .route("/transactions/:id/rollback", post(rollback_transaction))
        .route("/sagas", post(create_saga))
        .route("/sagas/:id", get(get_saga))
        .route("/sagas/:id/compensate", post(compensate_saga))
        .route("/metrics", get(get_metrics))
        .layer(CorsLayer::permissive())
        .with_state(app_state);

    // Start server
    let listener = TcpListener::bind(&config.server_address).await?;
    info!("Transaction Coordinator listening on {}", config.server_address);
    
    axum::serve(listener, app).await?;
    
    Ok(())
}

async fn health_check() -> Json<serde_json::Value> {
    Json(serde_json::json!({
        "status": "healthy",
        "service": "transaction-coordinator",
        "timestamp": chrono::Utc::now()
    }))
}

async fn create_transaction(
    State(state): State<AppState>,
    Json(request): Json<CreateTransactionRequest>,
) -> Result<Json<TransactionResponse>, StatusCode> {
    match state.transaction_service.create_transaction(request).await {
        Ok(transaction) => Ok(Json(transaction.into())),
        Err(e) => {
            error!("Failed to create transaction: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}

async fn get_transaction(
    State(state): State<AppState>,
    Path(id): Path<Uuid>,
) -> Result<Json<TransactionResponse>, StatusCode> {
    match state.transaction_service.get_transaction(id).await {
        Ok(Some(transaction)) => Ok(Json(transaction.into())),
        Ok(None) => Err(StatusCode::NOT_FOUND),
        Err(e) => {
            error!("Failed to get transaction: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}

async fn commit_transaction(
    State(state): State<AppState>,
    Path(id): Path<Uuid>,
) -> Result<Json<TransactionResponse>, StatusCode> {
    match state.transaction_service.commit_transaction(id).await {
        Ok(transaction) => Ok(Json(transaction.into())),
        Err(e) => {
            error!("Failed to commit transaction: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}

async fn rollback_transaction(
    State(state): State<AppState>,
    Path(id): Path<Uuid>,
) -> Result<Json<TransactionResponse>, StatusCode> {
    match state.transaction_service.rollback_transaction(id).await {
        Ok(transaction) => Ok(Json(transaction.into())),
        Err(e) => {
            error!("Failed to rollback transaction: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}

async fn create_saga(
    State(state): State<AppState>,
    Json(request): Json<CreateSagaRequest>,
) -> Result<Json<SagaResponse>, StatusCode> {
    match state.saga_service.create_saga(request).await {
        Ok(saga) => Ok(Json(saga.into())),
        Err(e) => {
            error!("Failed to create saga: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}

async fn get_saga(
    State(state): State<AppState>,
    Path(id): Path<Uuid>,
) -> Result<Json<SagaResponse>, StatusCode> {
    match state.saga_service.get_saga(id).await {
        Ok(Some(saga)) => Ok(Json(saga.into())),
        Ok(None) => Err(StatusCode::NOT_FOUND),
        Err(e) => {
            error!("Failed to get saga: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}

async fn compensate_saga(
    State(state): State<AppState>,
    Path(id): Path<Uuid>,
) -> Result<Json<SagaResponse>, StatusCode> {
    match state.saga_service.compensate_saga(id).await {
        Ok(saga) => Ok(Json(saga.into())),
        Err(e) => {
            error!("Failed to compensate saga: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}

async fn get_metrics() -> Result<String, StatusCode> {
    use prometheus::{Encoder, TextEncoder};
    
    let encoder = TextEncoder::new();
    let metric_families = prometheus::gather();
    
    match encoder.encode_to_string(&metric_families) {
        Ok(metrics) => Ok(metrics),
        Err(e) => {
            error!("Failed to encode metrics: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}

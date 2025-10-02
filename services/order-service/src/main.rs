use anyhow::Result;
use axum::{
    extract::{Path, State},
    http::StatusCode,
    response::Json,
    routing::{get, post},
    Router,
};
use axum_prometheus::PrometheusMetricLayer;
use std::sync::Arc;
use tokio::net::TcpListener;
use tower_http::{cors::CorsLayer, trace::TraceLayer};
use tracing::{info, instrument};
use uuid::Uuid;

mod config;
mod domain;
mod handlers;
mod infrastructure;
mod saga;
mod services;

use config::Config;
use domain::{Order, OrderStatus};
use handlers::OrderHandler;
use infrastructure::{
    database::MongoRepository,
    kafka::KafkaProducer,
    outbox::OutboxProcessor,
    redis::RedisClient,
};
use services::OrderService;

#[derive(Clone)]
pub struct AppState {
    pub order_service: Arc<OrderService>,
    pub order_handler: Arc<OrderHandler>,
}

#[tokio::main]
async fn main() -> Result<()> {
    // Initialize tracing
    tracing_subscriber::fmt()
        .with_env_filter(tracing_subscriber::EnvFilter::from_default_env())
        .init();

    // Load configuration
    let config = Config::from_env()?;
    info!("Starting Order Service on port {}", config.port);

    // Initialize infrastructure
    let mongo_repo = Arc::new(MongoRepository::new(&config.mongodb_url).await?);
    let kafka_producer = Arc::new(KafkaProducer::new(&config.kafka_brokers)?);
    let redis_client = Arc::new(RedisClient::new(&config.redis_url)?);

    // Initialize services
    let order_service = Arc::new(OrderService::new(
        mongo_repo.clone(),
        kafka_producer.clone(),
        redis_client.clone(),
    ));

    let order_handler = Arc::new(OrderHandler::new(order_service.clone()));

    // Start outbox processor
    let outbox_processor = OutboxProcessor::new(mongo_repo.clone(), kafka_producer.clone());
    let outbox_handle = tokio::spawn(async move {
        outbox_processor.start().await;
    });

    // Create app state
    let app_state = AppState {
        order_service,
        order_handler,
    };

    // Setup metrics
    let (prometheus_layer, metric_handle) = PrometheusMetricLayer::pair();

    // Build router
    let app = Router::new()
        .route("/health", get(health_check))
        .route("/metrics", get(|| async move { metric_handle.render() }))
        .route("/api/v1/orders", post(create_order))
        .route("/api/v1/orders/:id", get(get_order))
        .route("/api/v1/orders", get(list_orders))
        .route("/api/v1/orders/:id/cancel", post(cancel_order))
        .route("/api/v1/orders/:id/complete", post(complete_order))
        .route("/api/v1/saga/compensate/:id", post(compensate_order))
        .with_state(app_state)
        .layer(TraceLayer::new_for_http())
        .layer(CorsLayer::permissive())
        .layer(prometheus_layer);

    // Start server
    let listener = TcpListener::bind(format!("0.0.0.0:{}", config.port)).await?;
    info!("Order Service listening on {}", listener.local_addr()?);

    axum::serve(listener, app).await?;

    // Cleanup
    outbox_handle.abort();
    Ok(())
}

#[instrument]
async fn health_check() -> Json<serde_json::Value> {
    Json(serde_json::json!({
        "status": "healthy",
        "service": "order-service",
        "version": "0.1.0"
    }))
}

#[instrument(skip(state))]
async fn create_order(
    State(state): State<AppState>,
    Json(payload): Json<serde_json::Value>,
) -> Result<Json<Order>, StatusCode> {
    match state.order_handler.create_order(payload).await {
        Ok(order) => Ok(Json(order)),
        Err(_) => Err(StatusCode::INTERNAL_SERVER_ERROR),
    }
}

#[instrument(skip(state))]
async fn get_order(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> Result<Json<Order>, StatusCode> {
    let order_id = Uuid::parse_str(&id).map_err(|_| StatusCode::BAD_REQUEST)?;
    
    match state.order_handler.get_order(order_id).await {
        Ok(Some(order)) => Ok(Json(order)),
        Ok(None) => Err(StatusCode::NOT_FOUND),
        Err(_) => Err(StatusCode::INTERNAL_SERVER_ERROR),
    }
}

#[instrument(skip(state))]
async fn list_orders(State(state): State<AppState>) -> Result<Json<Vec<Order>>, StatusCode> {
    match state.order_handler.list_orders().await {
        Ok(orders) => Ok(Json(orders)),
        Err(_) => Err(StatusCode::INTERNAL_SERVER_ERROR),
    }
}

#[instrument(skip(state))]
async fn cancel_order(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> Result<Json<Order>, StatusCode> {
    let order_id = Uuid::parse_str(&id).map_err(|_| StatusCode::BAD_REQUEST)?;
    
    match state.order_handler.cancel_order(order_id).await {
        Ok(order) => Ok(Json(order)),
        Err(_) => Err(StatusCode::INTERNAL_SERVER_ERROR),
    }
}

#[instrument(skip(state))]
async fn complete_order(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> Result<Json<Order>, StatusCode> {
    let order_id = Uuid::parse_str(&id).map_err(|_| StatusCode::BAD_REQUEST)?;
    
    match state.order_handler.complete_order(order_id).await {
        Ok(order) => Ok(Json(order)),
        Err(_) => Err(StatusCode::INTERNAL_SERVER_ERROR),
    }
}

#[instrument(skip(state))]
async fn compensate_order(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> Result<StatusCode, StatusCode> {
    let order_id = Uuid::parse_str(&id).map_err(|_| StatusCode::BAD_REQUEST)?;
    
    match state.order_handler.compensate_order(order_id).await {
        Ok(_) => Ok(StatusCode::OK),
        Err(_) => Err(StatusCode::INTERNAL_SERVER_ERROR),
    }
}

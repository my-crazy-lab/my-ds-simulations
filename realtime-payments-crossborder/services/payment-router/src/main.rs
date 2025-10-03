use actix_web::{web, App, HttpServer, HttpResponse, Result, middleware::Logger};
use serde::{Deserialize, Serialize};
use sqlx::{PgPool, Row};
use redis::Client as RedisClient;
use uuid::Uuid;
use std::time::{SystemTime, UNIX_EPOCH, Instant};
use std::env;
use log::{info, error, warn};
use tokio::time::{sleep, Duration};

// Configuration structure
#[derive(Clone)]
struct AppConfig {
    database_url: String,
    redis_url: String,
    kafka_brokers: String,
    service_name: String,
    port: u16,
}

impl AppConfig {
    fn from_env() -> Self {
        Self {
            database_url: env::var("DATABASE_URL")
                .unwrap_or_else(|_| "postgres://realtime_user:secure_realtime_pass@localhost:5436/realtime_payments".to_string()),
            redis_url: env::var("REDIS_URL")
                .unwrap_or_else(|_| "redis://localhost:6382".to_string()),
            kafka_brokers: env::var("KAFKA_BROKERS")
                .unwrap_or_else(|_| "localhost:9095".to_string()),
            service_name: env::var("SERVICE_NAME")
                .unwrap_or_else(|_| "payment-router".to_string()),
            port: env::var("PORT")
                .unwrap_or_else(|_| "8080".to_string())
                .parse()
                .unwrap_or(8080),
        }
    }
}

// Application state
#[derive(Clone)]
struct AppState {
    config: AppConfig,
    db_pool: PgPool,
    redis_client: RedisClient,
}

// Payment request structures
#[derive(Deserialize, Serialize, Debug)]
struct PaymentRequest {
    message_id: String,
    payment_type: String,
    amount: String,
    currency: String,
    debtor: PartyInfo,
    creditor: PartyInfo,
    execution_time: Option<String>,
    remittance_info: Option<String>,
}

#[derive(Deserialize, Serialize, Debug)]
struct CrossBorderPaymentRequest {
    message_id: String,
    payment_type: String,
    amount: String,
    source_currency: String,
    target_currency: String,
    fx_rate: String,
    debtor: PartyInfo,
    creditor: PartyInfo,
    correspondent_route: Option<String>,
    purpose_code: Option<String>,
}

#[derive(Deserialize, Serialize, Debug)]
struct PartyInfo {
    name: String,
    account: String,
    bank_code: String,
    country: Option<String>,
}

// Payment response structures
#[derive(Serialize, Debug)]
struct PaymentResponse {
    payment_id: String,
    message_id: String,
    status: String,
    amount: String,
    currency: String,
    processing_time_ms: u64,
    network_latency_ms: Option<u64>,
    validation_time_ms: Option<u64>,
    settlement_time_ms: Option<u64>,
    created_at: String,
}

#[derive(Serialize)]
struct HealthResponse {
    status: String,
    service: String,
    version: String,
    timestamp: String,
    uptime_seconds: u64,
}

#[derive(Serialize)]
struct ApiResponse<T> {
    data: T,
    success: bool,
    timestamp: String,
}

#[derive(Serialize)]
struct ErrorResponse {
    error: String,
    code: String,
    timestamp: String,
}

// Payment processing service
struct PaymentProcessor {
    state: AppState,
    start_time: SystemTime,
}

impl PaymentProcessor {
    fn new(state: AppState) -> Self {
        Self {
            state,
            start_time: SystemTime::now(),
        }
    }

    async fn process_domestic_payment(&self, request: PaymentRequest) -> Result<PaymentResponse, String> {
        let start_time = Instant::now();
        let payment_id = format!("pay_{}", Uuid::new_v4().simple());

        info!("Processing domestic payment: {} for amount {} {}", 
              request.message_id, request.amount, request.currency);

        // Validate payment request
        let validation_start = Instant::now();
        self.validate_payment_request(&request).await?;
        let validation_time = validation_start.elapsed().as_millis() as u64;

        // Check for duplicate message
        if self.is_duplicate_message(&request.message_id).await? {
            return Err("Duplicate message ID".to_string());
        }

        // Route payment through appropriate network
        let network_start = Instant::now();
        let network_type = self.determine_network_type(&request).await?;
        let network_latency = self.route_to_network(&payment_id, &network_type).await?;
        let network_time = network_start.elapsed().as_millis() as u64;

        // Perform settlement
        let settlement_start = Instant::now();
        self.process_settlement(&payment_id, &request).await?;
        let settlement_time = settlement_start.elapsed().as_millis() as u64;

        // Store payment in database
        self.store_payment(&payment_id, &request, "COMPLETED").await?;

        // Publish event to Kafka
        self.publish_payment_event(&payment_id, "COMPLETED", &request).await?;

        let total_processing_time = start_time.elapsed().as_millis() as u64;

        info!("Payment {} processed successfully in {}ms", payment_id, total_processing_time);

        Ok(PaymentResponse {
            payment_id,
            message_id: request.message_id,
            status: "COMPLETED".to_string(),
            amount: request.amount,
            currency: request.currency,
            processing_time_ms: total_processing_time,
            network_latency_ms: Some(network_latency),
            validation_time_ms: Some(validation_time),
            settlement_time_ms: Some(settlement_time),
            created_at: chrono::Utc::now().to_rfc3339(),
        })
    }

    async fn process_crossborder_payment(&self, request: CrossBorderPaymentRequest) -> Result<PaymentResponse, String> {
        let start_time = Instant::now();
        let payment_id = format!("pay_{}", Uuid::new_v4().simple());

        info!("Processing cross-border payment: {} for amount {} {} -> {}", 
              request.message_id, request.amount, request.source_currency, request.target_currency);

        // Validate cross-border payment request
        let validation_start = Instant::now();
        self.validate_crossborder_request(&request).await?;
        let validation_time = validation_start.elapsed().as_millis() as u64;

        // Check sanctions screening
        self.perform_sanctions_screening(&request).await?;

        // Perform FX conversion if needed
        let fx_start = Instant::now();
        let converted_amount = self.perform_fx_conversion(&request).await?;
        let fx_time = fx_start.elapsed().as_millis() as u64;

        // Route through correspondent banking network
        let network_start = Instant::now();
        let correspondent_route = request.correspondent_route.unwrap_or_else(|| "SWIFT_GPI".to_string());
        let network_latency = self.route_to_correspondent(&payment_id, &correspondent_route).await?;
        let network_time = network_start.elapsed().as_millis() as u64;

        // Process cross-border settlement
        let settlement_start = Instant::now();
        self.process_crossborder_settlement(&payment_id, &request, &converted_amount).await?;
        let settlement_time = settlement_start.elapsed().as_millis() as u64;

        // Store cross-border payment
        self.store_crossborder_payment(&payment_id, &request, "PROCESSING").await?;

        // Publish event
        self.publish_crossborder_event(&payment_id, "PROCESSING", &request).await?;

        let total_processing_time = start_time.elapsed().as_millis() as u64;

        info!("Cross-border payment {} initiated successfully in {}ms", payment_id, total_processing_time);

        Ok(PaymentResponse {
            payment_id,
            message_id: request.message_id,
            status: "PROCESSING".to_string(),
            amount: request.amount,
            currency: request.source_currency,
            processing_time_ms: total_processing_time,
            network_latency_ms: Some(network_latency),
            validation_time_ms: Some(validation_time),
            settlement_time_ms: Some(settlement_time),
            created_at: chrono::Utc::now().to_rfc3339(),
        })
    }

    async fn validate_payment_request(&self, request: &PaymentRequest) -> Result<(), String> {
        // Validate amount
        let amount: f64 = request.amount.parse()
            .map_err(|_| "Invalid amount format")?;
        
        if amount <= 0.0 {
            return Err("Amount must be positive".to_string());
        }

        // Validate currency
        if !["USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD"].contains(&request.currency.as_str()) {
            return Err("Unsupported currency".to_string());
        }

        // Validate account numbers
        if request.debtor.account.is_empty() || request.creditor.account.is_empty() {
            return Err("Account numbers cannot be empty".to_string());
        }

        Ok(())
    }

    async fn validate_crossborder_request(&self, request: &CrossBorderPaymentRequest) -> Result<(), String> {
        // Validate amount
        let amount: f64 = request.amount.parse()
            .map_err(|_| "Invalid amount format")?;
        
        if amount <= 0.0 {
            return Err("Amount must be positive".to_string());
        }

        // Validate currencies
        if request.source_currency == request.target_currency {
            return Err("Source and target currencies must be different".to_string());
        }

        // Validate FX rate
        let fx_rate: f64 = request.fx_rate.parse()
            .map_err(|_| "Invalid FX rate format")?;
        
        if fx_rate <= 0.0 {
            return Err("FX rate must be positive".to_string());
        }

        Ok(())
    }

    async fn is_duplicate_message(&self, message_id: &str) -> Result<bool, String> {
        // Check Redis for duplicate message ID
        let mut conn = self.state.redis_client.get_connection()
            .map_err(|e| format!("Redis connection error: {}", e))?;
        
        let exists: bool = redis::cmd("EXISTS")
            .arg(format!("msg:{}", message_id))
            .query(&mut conn)
            .map_err(|e| format!("Redis query error: {}", e))?;

        if !exists {
            // Set message ID with expiration (24 hours)
            let _: () = redis::cmd("SETEX")
                .arg(format!("msg:{}", message_id))
                .arg(86400) // 24 hours
                .arg("1")
                .query(&mut conn)
                .map_err(|e| format!("Redis set error: {}", e))?;
        }

        Ok(exists)
    }

    async fn determine_network_type(&self, request: &PaymentRequest) -> Result<String, String> {
        // Simple routing logic based on currency and amount
        let amount: f64 = request.amount.parse().unwrap_or(0.0);
        
        match request.currency.as_str() {
            "USD" => {
                if amount >= 1000000.0 { // $1M+
                    Ok("FEDWIRE".to_string())
                } else {
                    Ok("RTP".to_string())
                }
            },
            "EUR" => Ok("SEPA_INSTANT".to_string()),
            "GBP" => Ok("FASTER_PAYMENTS".to_string()),
            _ => Ok("SWIFT_GPI".to_string()),
        }
    }

    async fn route_to_network(&self, payment_id: &str, network_type: &str) -> Result<u64, String> {
        // Simulate network routing latency
        let latency_ms = match network_type {
            "FEDWIRE" => 50,
            "RTP" => 30,
            "SEPA_INSTANT" => 40,
            "FASTER_PAYMENTS" => 25,
            _ => 100,
        };

        // Simulate network processing time
        sleep(Duration::from_millis(latency_ms)).await;

        info!("Payment {} routed to {} network", payment_id, network_type);
        Ok(latency_ms)
    }

    async fn route_to_correspondent(&self, payment_id: &str, route: &str) -> Result<u64, String> {
        // Simulate correspondent banking latency
        let latency_ms = match route {
            "SWIFT_GPI" => 200,
            "CORRESPONDENT_DIRECT" => 150,
            _ => 300,
        };

        sleep(Duration::from_millis(latency_ms)).await;

        info!("Cross-border payment {} routed via {}", payment_id, route);
        Ok(latency_ms)
    }

    async fn process_settlement(&self, payment_id: &str, request: &PaymentRequest) -> Result<(), String> {
        // Simulate settlement processing
        sleep(Duration::from_millis(20)).await;
        info!("Settlement processed for payment {}", payment_id);
        Ok(())
    }

    async fn process_crossborder_settlement(&self, payment_id: &str, request: &CrossBorderPaymentRequest, converted_amount: &str) -> Result<(), String> {
        // Simulate cross-border settlement
        sleep(Duration::from_millis(50)).await;
        info!("Cross-border settlement processed for payment {}", payment_id);
        Ok(())
    }

    async fn perform_sanctions_screening(&self, request: &CrossBorderPaymentRequest) -> Result<(), String> {
        // Simulate sanctions screening
        sleep(Duration::from_millis(10)).await;
        
        // Simple screening logic
        if request.debtor.name.to_lowercase().contains("blocked") || 
           request.creditor.name.to_lowercase().contains("blocked") {
            return Err("Sanctions screening failed".to_string());
        }

        Ok(())
    }

    async fn perform_fx_conversion(&self, request: &CrossBorderPaymentRequest) -> Result<String, String> {
        // Simulate FX conversion
        sleep(Duration::from_millis(15)).await;
        
        let amount: f64 = request.amount.parse().unwrap_or(0.0);
        let fx_rate: f64 = request.fx_rate.parse().unwrap_or(1.0);
        let converted_amount = amount * fx_rate;
        
        Ok(format!("{:.2}", converted_amount))
    }

    async fn store_payment(&self, payment_id: &str, request: &PaymentRequest, status: &str) -> Result<(), String> {
        // Store payment in database
        let query = r#"
            INSERT INTO payment_messages (
                id, message_id, message_type, payment_type, amount, currency,
                debtor_name, debtor_account, debtor_agent,
                creditor_name, creditor_account, creditor_agent,
                status, remittance_info, processing_time_ms
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
        "#;

        sqlx::query(query)
            .bind(Uuid::parse_str(payment_id.trim_start_matches("pay_")).unwrap())
            .bind(&request.message_id)
            .bind("pacs.008")
            .bind(&request.payment_type)
            .bind(request.amount.parse::<f64>().unwrap_or(0.0))
            .bind(&request.currency)
            .bind(&request.debtor.name)
            .bind(&request.debtor.account)
            .bind(&request.debtor.bank_code)
            .bind(&request.creditor.name)
            .bind(&request.creditor.account)
            .bind(&request.creditor.bank_code)
            .bind(status)
            .bind(&request.remittance_info)
            .bind(0i32) // Will be updated later
            .execute(&self.state.db_pool)
            .await
            .map_err(|e| format!("Database error: {}", e))?;

        Ok(())
    }

    async fn store_crossborder_payment(&self, payment_id: &str, request: &CrossBorderPaymentRequest, status: &str) -> Result<(), String> {
        // Store cross-border payment in database
        let query = r#"
            INSERT INTO payment_messages (
                id, message_id, message_type, payment_type, amount, currency,
                source_currency, target_currency, fx_rate,
                debtor_name, debtor_account, debtor_agent,
                creditor_name, creditor_account, creditor_agent,
                status, purpose_code, processing_time_ms
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18)
        "#;

        sqlx::query(query)
            .bind(Uuid::parse_str(payment_id.trim_start_matches("pay_")).unwrap())
            .bind(&request.message_id)
            .bind("pacs.008")
            .bind(&request.payment_type)
            .bind(request.amount.parse::<f64>().unwrap_or(0.0))
            .bind(&request.source_currency)
            .bind(&request.source_currency)
            .bind(&request.target_currency)
            .bind(request.fx_rate.parse::<f64>().unwrap_or(1.0))
            .bind(&request.debtor.name)
            .bind(&request.debtor.account)
            .bind(&request.debtor.bank_code)
            .bind(&request.creditor.name)
            .bind(&request.creditor.account)
            .bind(&request.creditor.bank_code)
            .bind(status)
            .bind(&request.purpose_code)
            .bind(0i32)
            .execute(&self.state.db_pool)
            .await
            .map_err(|e| format!("Database error: {}", e))?;

        Ok(())
    }

    async fn publish_payment_event(&self, payment_id: &str, status: &str, request: &PaymentRequest) -> Result<(), String> {
        // Simulate Kafka event publishing
        info!("Published payment event for {}: {}", payment_id, status);
        Ok(())
    }

    async fn publish_crossborder_event(&self, payment_id: &str, status: &str, request: &CrossBorderPaymentRequest) -> Result<(), String> {
        // Simulate Kafka event publishing
        info!("Published cross-border payment event for {}: {}", payment_id, status);
        Ok(())
    }

    fn get_uptime(&self) -> u64 {
        self.start_time.elapsed().unwrap_or_default().as_secs()
    }
}

// HTTP handlers
async fn process_payment(
    data: web::Data<PaymentProcessor>,
    request: web::Json<PaymentRequest>,
) -> Result<HttpResponse> {
    match data.process_domestic_payment(request.into_inner()).await {
        Ok(response) => Ok(HttpResponse::Created().json(ApiResponse {
            data: response,
            success: true,
            timestamp: chrono::Utc::now().to_rfc3339(),
        })),
        Err(error) => Ok(HttpResponse::BadRequest().json(ErrorResponse {
            error,
            code: "PAYMENT_PROCESSING_ERROR".to_string(),
            timestamp: chrono::Utc::now().to_rfc3339(),
        })),
    }
}

async fn process_crossborder_payment(
    data: web::Data<PaymentProcessor>,
    request: web::Json<CrossBorderPaymentRequest>,
) -> Result<HttpResponse> {
    match data.process_crossborder_payment(request.into_inner()).await {
        Ok(response) => Ok(HttpResponse::Created().json(ApiResponse {
            data: response,
            success: true,
            timestamp: chrono::Utc::now().to_rfc3339(),
        })),
        Err(error) => Ok(HttpResponse::BadRequest().json(ErrorResponse {
            error,
            code: "CROSSBORDER_PROCESSING_ERROR".to_string(),
            timestamp: chrono::Utc::now().to_rfc3339(),
        })),
    }
}

async fn health_check(data: web::Data<PaymentProcessor>) -> Result<HttpResponse> {
    Ok(HttpResponse::Ok().json(HealthResponse {
        status: "healthy".to_string(),
        service: data.state.config.service_name.clone(),
        version: "1.0.0".to_string(),
        timestamp: chrono::Utc::now().to_rfc3339(),
        uptime_seconds: data.get_uptime(),
    }))
}

#[actix_web::main]
async fn main() -> std::io::Result<()> {
    env_logger::init();
    
    let config = AppConfig::from_env();
    info!("Starting {} on port {}", config.service_name, config.port);

    // Initialize database connection
    let db_pool = PgPool::connect(&config.database_url)
        .await
        .expect("Failed to connect to database");

    // Initialize Redis connection
    let redis_client = RedisClient::open(config.redis_url.clone())
        .expect("Failed to create Redis client");

    let app_state = AppState {
        config: config.clone(),
        db_pool,
        redis_client,
    };

    let payment_processor = PaymentProcessor::new(app_state);

    HttpServer::new(move || {
        App::new()
            .app_data(web::Data::new(payment_processor.clone()))
            .wrap(Logger::default())
            .route("/health", web::get().to(health_check))
            .service(
                web::scope("/api/v1")
                    .route("/payments", web::post().to(process_payment))
                    .route("/payments/crossborder", web::post().to(process_crossborder_payment))
            )
    })
    .bind(("0.0.0.0", config.port))?
    .run()
    .await
}

package main

import (
	"context"
	"crypto/tls"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"syscall"
	"time"

	"github.com/gin-contrib/cors"
	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	"go.opentelemetry.io/contrib/instrumentation/github.com/gin-gonic/gin/otelgin"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/exporters/jaeger"
	"go.opentelemetry.io/otel/sdk/resource"
	tracesdk "go.opentelemetry.io/otel/sdk/trace"
	semconv "go.opentelemetry.io/otel/semconv/v1.4.0"
)

// Configuration structure
type Config struct {
	Port                      string
	DatabaseURL               string
	RedisURL                  string
	KafkaBrokers              string
	SchemaRegistryURL         string
	TokenizationServiceURL    string
	FraudDetectionServiceURL  string
	ThreeDSecureServiceURL    string
	JaegerEndpoint            string
	LogLevel                  string
	ServiceName               string
	TLSCertPath               string
	TLSKeyPath                string
}

// Payment request structure
type PaymentRequest struct {
	MerchantID      string                 `json:"merchant_id" binding:"required"`
	Amount          string                 `json:"amount" binding:"required"`
	Currency        string                 `json:"currency" binding:"required"`
	Description     string                 `json:"description"`
	CardToken       string                 `json:"card_token" binding:"required"`
	Capture         *bool                  `json:"capture"`
	BillingAddress  *BillingAddress        `json:"billing_address"`
	ThreeDSecure    *ThreeDSecureRequest   `json:"three_d_secure"`
	Metadata        map[string]interface{} `json:"metadata"`
}

type BillingAddress struct {
	Street  string `json:"street"`
	City    string `json:"city"`
	State   string `json:"state"`
	Zip     string `json:"zip"`
	Country string `json:"country"`
}

type ThreeDSecureRequest struct {
	Enabled   bool   `json:"enabled"`
	ReturnURL string `json:"return_url"`
}

// Payment response structure
type PaymentResponse struct {
	PaymentID        string                 `json:"payment_id"`
	Status           string                 `json:"status"`
	Amount           string                 `json:"amount"`
	Currency         string                 `json:"currency"`
	Description      string                 `json:"description"`
	FraudScore       *float64               `json:"fraud_score,omitempty"`
	FraudStatus      string                 `json:"fraud_status"`
	ThreeDSStatus    string                 `json:"three_ds_status"`
	ThreeDSRedirectURL *string              `json:"three_ds_redirect_url,omitempty"`
	ProcessingTimeMS int64                  `json:"processing_time_ms"`
	CreatedAt        time.Time              `json:"created_at"`
	Metadata         map[string]interface{} `json:"metadata,omitempty"`
}

// Metrics
var (
	paymentsTotal = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "payments_total",
			Help: "Total number of payment requests",
		},
		[]string{"status", "currency", "fraud_status"},
	)

	paymentDuration = prometheus.NewHistogramVec(
		prometheus.HistogramOpts{
			Name:    "payment_duration_seconds",
			Help:    "Payment processing duration",
			Buckets: prometheus.DefBuckets,
		},
		[]string{"status"},
	)

	fraudScoreGauge = prometheus.NewGaugeVec(
		prometheus.GaugeOpts{
			Name: "fraud_score",
			Help: "Current fraud score for payments",
		},
		[]string{"payment_id"},
	)
)

func init() {
	prometheus.MustRegister(paymentsTotal)
	prometheus.MustRegister(paymentDuration)
	prometheus.MustRegister(fraudScoreGauge)
}

// Load configuration from environment variables
func loadConfig() *Config {
	return &Config{
		Port:                      getEnv("PORT", "8443"),
		DatabaseURL:               getEnv("DATABASE_URL", "postgres://payments_user:secure_payments_pass@localhost:5435/payments_gateway?sslmode=disable"),
		RedisURL:                  getEnv("REDIS_URL", "redis://localhost:6381"),
		KafkaBrokers:              getEnv("KAFKA_BROKERS", "localhost:9094"),
		SchemaRegistryURL:         getEnv("SCHEMA_REGISTRY_URL", "http://localhost:8083"),
		TokenizationServiceURL:    getEnv("TOKENIZATION_SERVICE_URL", "https://localhost:8445"),
		FraudDetectionServiceURL:  getEnv("FRAUD_DETECTION_SERVICE_URL", "http://localhost:8447"),
		ThreeDSecureServiceURL:    getEnv("THREE_D_SECURE_SERVICE_URL", "http://localhost:8448"),
		JaegerEndpoint:            getEnv("JAEGER_ENDPOINT", "http://localhost:14268/api/traces"),
		LogLevel:                  getEnv("LOG_LEVEL", "info"),
		ServiceName:               getEnv("SERVICE_NAME", "authorization-service"),
		TLSCertPath:               getEnv("TLS_CERT_PATH", "/certs/server.crt"),
		TLSKeyPath:                getEnv("TLS_KEY_PATH", "/certs/server.key"),
	}
}

func getEnv(key, defaultValue string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return defaultValue
}

// Initialize OpenTelemetry tracing
func initTracer(config *Config) func() {
	exp, err := jaeger.New(jaeger.WithCollectorEndpoint(jaeger.WithEndpoint(config.JaegerEndpoint)))
	if err != nil {
		log.Printf("Failed to initialize Jaeger exporter: %v", err)
		return func() {}
	}

	tp := tracesdk.NewTracerProvider(
		tracesdk.WithBatcher(exp),
		tracesdk.WithResource(resource.NewWithAttributes(
			semconv.SchemaURL,
			semconv.ServiceNameKey.String(config.ServiceName),
		)),
	)

	otel.SetTracerProvider(tp)

	return func() {
		ctx, cancel := context.WithTimeout(context.Background(), time.Second*5)
		defer cancel()
		if err := tp.Shutdown(ctx); err != nil {
			log.Printf("Error shutting down tracer provider: %v", err)
		}
	}
}

// Payment service structure
type PaymentService struct {
	config *Config
}

func NewPaymentService(config *Config) *PaymentService {
	return &PaymentService{
		config: config,
	}
}

// Process payment
func (ps *PaymentService) ProcessPayment(ctx context.Context, req *PaymentRequest) (*PaymentResponse, error) {
	startTime := time.Now()
	paymentID := "pay_" + generateID()

	// Validate card token with tokenization service
	cardInfo, err := ps.validateCardToken(ctx, req.CardToken)
	if err != nil {
		return nil, fmt.Errorf("invalid card token: %w", err)
	}

	// Run fraud detection
	fraudResult, err := ps.runFraudDetection(ctx, req, cardInfo)
	if err != nil {
		log.Printf("Fraud detection failed: %v", err)
		// Continue with default fraud status
		fraudResult = &FraudResult{
			Score:  0.0,
			Status: "CLEAN",
		}
	}

	// Check if payment should be blocked
	if fraudResult.Status == "BLOCK" {
		paymentsTotal.WithLabelValues("FAILED", req.Currency, fraudResult.Status).Inc()
		return &PaymentResponse{
			PaymentID:        paymentID,
			Status:           "FAILED",
			Amount:           req.Amount,
			Currency:         req.Currency,
			Description:      req.Description,
			FraudScore:       &fraudResult.Score,
			FraudStatus:      fraudResult.Status,
			ThreeDSStatus:    "NOT_ENROLLED",
			ProcessingTimeMS: time.Since(startTime).Milliseconds(),
			CreatedAt:        time.Now(),
		}, nil
	}

	// Handle 3D Secure if enabled
	threeDSResult := &ThreeDSecureResult{
		Status: "NOT_ENROLLED",
	}
	if req.ThreeDSecure != nil && req.ThreeDSecure.Enabled {
		threeDSResult, err = ps.handle3DSecure(ctx, req, cardInfo)
		if err != nil {
			log.Printf("3D Secure processing failed: %v", err)
		}
	}

	// Process authorization with PSP
	authResult, err := ps.authorizePayment(ctx, req, cardInfo, fraudResult, threeDSResult)
	if err != nil {
		paymentsTotal.WithLabelValues("FAILED", req.Currency, fraudResult.Status).Inc()
		return nil, fmt.Errorf("authorization failed: %w", err)
	}

	// Record metrics
	processingTime := time.Since(startTime)
	paymentsTotal.WithLabelValues(authResult.Status, req.Currency, fraudResult.Status).Inc()
	paymentDuration.WithLabelValues(authResult.Status).Observe(processingTime.Seconds())
	fraudScoreGauge.WithLabelValues(paymentID).Set(fraudResult.Score)

	return &PaymentResponse{
		PaymentID:          paymentID,
		Status:             authResult.Status,
		Amount:             req.Amount,
		Currency:           req.Currency,
		Description:        req.Description,
		FraudScore:         &fraudResult.Score,
		FraudStatus:        fraudResult.Status,
		ThreeDSStatus:      threeDSResult.Status,
		ThreeDSRedirectURL: threeDSResult.RedirectURL,
		ProcessingTimeMS:   processingTime.Milliseconds(),
		CreatedAt:          time.Now(),
		Metadata:           req.Metadata,
	}, nil
}

// Card information structure
type CardInfo struct {
	Token     string `json:"token"`
	LastFour  string `json:"last_four"`
	Brand     string `json:"brand"`
	ExpiryMonth string `json:"expiry_month"`
	ExpiryYear  string `json:"expiry_year"`
}

// Fraud detection result
type FraudResult struct {
	Score  float64 `json:"score"`
	Status string  `json:"status"`
	Reason string  `json:"reason"`
}

// 3D Secure result
type ThreeDSecureResult struct {
	Status      string  `json:"status"`
	RedirectURL *string `json:"redirect_url,omitempty"`
	TransactionID string `json:"transaction_id,omitempty"`
}

// Authorization result
type AuthorizationResult struct {
	Status           string `json:"status"`
	PSPTransactionID string `json:"psp_transaction_id"`
	PSPReference     string `json:"psp_reference"`
}

// Validate card token with tokenization service
func (ps *PaymentService) validateCardToken(ctx context.Context, token string) (*CardInfo, error) {
	// Simulate tokenization service call
	// In real implementation, this would make HTTP request to tokenization service
	return &CardInfo{
		Token:       token,
		LastFour:    "1111",
		Brand:       "VISA",
		ExpiryMonth: "12",
		ExpiryYear:  "2025",
	}, nil
}

// Run fraud detection
func (ps *PaymentService) runFraudDetection(ctx context.Context, req *PaymentRequest, cardInfo *CardInfo) (*FraudResult, error) {
	// Simulate fraud detection service call
	// In real implementation, this would make HTTP request to fraud detection service
	
	// Simple fraud scoring based on amount
	amount, _ := strconv.ParseFloat(req.Amount, 64)
	score := 0.0
	status := "CLEAN"
	
	if amount > 100000 { // $1000+
		score = 0.8
		status = "REVIEW"
	} else if amount > 50000 { // $500+
		score = 0.4
		status = "CLEAN"
	} else {
		score = 0.1
		status = "CLEAN"
	}
	
	return &FraudResult{
		Score:  score,
		Status: status,
		Reason: "Amount-based scoring",
	}, nil
}

// Handle 3D Secure authentication
func (ps *PaymentService) handle3DSecure(ctx context.Context, req *PaymentRequest, cardInfo *CardInfo) (*ThreeDSecureResult, error) {
	// Simulate 3D Secure service call
	// In real implementation, this would make HTTP request to 3D Secure service
	
	// For test cards, simulate enrollment
	if cardInfo.Brand == "VISA" {
		redirectURL := "https://3ds-simulator.com/challenge?txn=" + generateID()
		return &ThreeDSecureResult{
			Status:        "ENROLLED",
			RedirectURL:   &redirectURL,
			TransactionID: "3ds_" + generateID(),
		}, nil
	}
	
	return &ThreeDSecureResult{
		Status: "NOT_ENROLLED",
	}, nil
}

// Authorize payment with PSP
func (ps *PaymentService) authorizePayment(ctx context.Context, req *PaymentRequest, cardInfo *CardInfo, fraudResult *FraudResult, threeDSResult *ThreeDSecureResult) (*AuthorizationResult, error) {
	// Simulate PSP authorization
	// In real implementation, this would make HTTP request to PSP
	
	// Simulate success for most payments
	if fraudResult.Status != "BLOCK" {
		return &AuthorizationResult{
			Status:           "AUTHORIZED",
			PSPTransactionID: "psp_" + generateID(),
			PSPReference:     "ref_" + generateID(),
		}, nil
	}
	
	return &AuthorizationResult{
		Status: "FAILED",
	}, nil
}

// Generate random ID
func generateID() string {
	return uuid.New().String()[:24]
}

// HTTP handlers
func (ps *PaymentService) handleProcessPayment(c *gin.Context) {
	var req PaymentRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	response, err := ps.ProcessPayment(c.Request.Context(), &req)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusCreated, gin.H{"data": response})
}

func (ps *PaymentService) handleHealth(c *gin.Context) {
	c.JSON(http.StatusOK, gin.H{
		"status":  "healthy",
		"service": "authorization-service",
		"version": "1.0.0",
		"time":    time.Now().UTC(),
	})
}

func main() {
	config := loadConfig()
	
	// Initialize tracing
	cleanup := initTracer(config)
	defer cleanup()

	// Create payment service
	paymentService := NewPaymentService(config)

	// Setup Gin router
	gin.SetMode(gin.ReleaseMode)
	router := gin.New()
	
	// Middleware
	router.Use(gin.Logger())
	router.Use(gin.Recovery())
	router.Use(otelgin.Middleware("authorization-service"))
	router.Use(cors.New(cors.Config{
		AllowOrigins:     []string{"*"},
		AllowMethods:     []string{"GET", "POST", "PUT", "DELETE", "OPTIONS"},
		AllowHeaders:     []string{"*"},
		ExposeHeaders:    []string{"*"},
		AllowCredentials: true,
	}))

	// Routes
	v1 := router.Group("/api/v1")
	{
		v1.POST("/payments", paymentService.handleProcessPayment)
	}
	
	// Health and metrics
	router.GET("/health", paymentService.handleHealth)
	router.GET("/metrics", gin.WrapH(promhttp.Handler()))

	// Setup HTTPS server
	server := &http.Server{
		Addr:    ":" + config.Port,
		Handler: router,
		TLSConfig: &tls.Config{
			MinVersion: tls.VersionTLS13,
		},
	}

	// Start server
	go func() {
		log.Printf("Starting Authorization Service on port %s", config.Port)
		if err := server.ListenAndServeTLS(config.TLSCertPath, config.TLSKeyPath); err != nil && err != http.ErrServerClosed {
			log.Fatalf("Failed to start server: %v", err)
		}
	}()

	// Wait for interrupt signal to gracefully shutdown
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit
	log.Println("Shutting down server...")

	// Graceful shutdown
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	if err := server.Shutdown(ctx); err != nil {
		log.Fatal("Server forced to shutdown:", err)
	}

	log.Println("Server exited")
}

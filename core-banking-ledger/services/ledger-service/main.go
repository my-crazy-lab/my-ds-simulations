package main

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/exporters/jaeger"
	"go.opentelemetry.io/otel/sdk/resource"
	tracesdk "go.opentelemetry.io/otel/sdk/trace"
	semconv "go.opentelemetry.io/otel/semconv/v1.4.0"

	"ledger-service/internal/config"
	"ledger-service/internal/database"
	"ledger-service/internal/handlers"
	"ledger-service/internal/kafka"
	"ledger-service/internal/metrics"
	"ledger-service/internal/middleware"
	"ledger-service/internal/redis"
	"ledger-service/internal/services"
)

var (
	// Build information
	version   = "1.0.0"
	buildTime = "unknown"
	gitCommit = "unknown"
)

func main() {
	// Load configuration
	cfg, err := config.Load()
	if err != nil {
		log.Fatalf("Failed to load configuration: %v", err)
	}

	// Initialize tracing
	tp, err := initTracer(cfg.ServiceName, cfg.JaegerEndpoint)
	if err != nil {
		log.Fatalf("Failed to initialize tracer: %v", err)
	}
	defer func() {
		if err := tp.Shutdown(context.Background()); err != nil {
			log.Printf("Error shutting down tracer provider: %v", err)
		}
	}()

	// Initialize metrics
	metricsRegistry := prometheus.NewRegistry()
	appMetrics := metrics.NewMetrics(metricsRegistry)

	// Initialize database connections
	db, err := database.NewConnection(cfg.DatabaseURL)
	if err != nil {
		log.Fatalf("Failed to connect to primary database: %v", err)
	}
	defer db.Close()

	replicaDB, err := database.NewConnection(cfg.ReplicaDatabaseURL)
	if err != nil {
		log.Fatalf("Failed to connect to replica database: %v", err)
	}
	defer replicaDB.Close()

	// Initialize Redis client
	redisClient, err := redis.NewClient(cfg.RedisURL)
	if err != nil {
		log.Fatalf("Failed to connect to Redis: %v", err)
	}
	defer redisClient.Close()

	// Initialize Kafka producer and consumer
	kafkaProducer, err := kafka.NewProducer(cfg.KafkaBrokers, cfg.SchemaRegistryURL)
	if err != nil {
		log.Fatalf("Failed to create Kafka producer: %v", err)
	}
	defer kafkaProducer.Close()

	kafkaConsumer, err := kafka.NewConsumer(cfg.KafkaBrokers, "ledger-service-group")
	if err != nil {
		log.Fatalf("Failed to create Kafka consumer: %v", err)
	}
	defer kafkaConsumer.Close()

	// Initialize services
	ledgerService := services.NewLedgerService(db, replicaDB, redisClient, kafkaProducer, appMetrics)
	accountService := services.NewAccountService(db, replicaDB, redisClient, kafkaProducer, appMetrics)
	transactionService := services.NewTransactionService(db, replicaDB, redisClient, kafkaProducer, appMetrics)
	auditService := services.NewAuditService(db, kafkaProducer, appMetrics)

	// Initialize handlers
	ledgerHandler := handlers.NewLedgerHandler(ledgerService, appMetrics)
	accountHandler := handlers.NewAccountHandler(accountService, appMetrics)
	transactionHandler := handlers.NewTransactionHandler(transactionService, appMetrics)
	auditHandler := handlers.NewAuditHandler(auditService, appMetrics)

	// Setup HTTP router
	router := setupRouter(cfg, ledgerHandler, accountHandler, transactionHandler, auditHandler, appMetrics)

	// Setup metrics server
	metricsServer := &http.Server{
		Addr:    fmt.Sprintf(":%d", cfg.MetricsPort),
		Handler: promhttp.HandlerFor(metricsRegistry, promhttp.HandlerOpts{}),
	}

	// Setup main HTTP server
	server := &http.Server{
		Addr:         fmt.Sprintf(":%d", cfg.Port),
		Handler:      router,
		ReadTimeout:  30 * time.Second,
		WriteTimeout: 30 * time.Second,
		IdleTimeout:  120 * time.Second,
	}

	// Start servers
	go func() {
		log.Printf("Starting metrics server on port %d", cfg.MetricsPort)
		if err := metricsServer.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("Failed to start metrics server: %v", err)
		}
	}()

	go func() {
		log.Printf("Starting ledger service on port %d", cfg.Port)
		if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("Failed to start server: %v", err)
		}
	}()

	// Start Kafka consumer
	go func() {
		log.Println("Starting Kafka consumer")
		if err := kafkaConsumer.Start(context.Background(), handleKafkaMessage); err != nil {
			log.Printf("Kafka consumer error: %v", err)
		}
	}()

	// Wait for interrupt signal to gracefully shutdown
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit

	log.Println("Shutting down servers...")

	// Graceful shutdown
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	if err := server.Shutdown(ctx); err != nil {
		log.Printf("Server forced to shutdown: %v", err)
	}

	if err := metricsServer.Shutdown(ctx); err != nil {
		log.Printf("Metrics server forced to shutdown: %v", err)
	}

	log.Println("Servers exited")
}

func setupRouter(cfg *config.Config, ledgerHandler *handlers.LedgerHandler, accountHandler *handlers.AccountHandler, transactionHandler *handlers.TransactionHandler, auditHandler *handlers.AuditHandler, metrics *metrics.Metrics) *gin.Engine {
	// Set Gin mode
	if cfg.Environment == "production" {
		gin.SetMode(gin.ReleaseMode)
	}

	router := gin.New()

	// Middleware
	router.Use(middleware.Logger())
	router.Use(middleware.Recovery())
	router.Use(middleware.CORS())
	router.Use(middleware.RequestID())
	router.Use(middleware.Tracing())
	router.Use(middleware.Metrics(metrics))
	router.Use(middleware.RateLimit(cfg.RateLimit))

	// Health check endpoints
	router.GET("/health", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{
			"status":    "healthy",
			"service":   "ledger-service",
			"version":   version,
			"timestamp": time.Now().UTC(),
		})
	})

	router.GET("/ready", func(c *gin.Context) {
		// TODO: Add readiness checks for database, Redis, Kafka
		c.JSON(http.StatusOK, gin.H{
			"status": "ready",
		})
	})

	// API routes
	v1 := router.Group("/api/v1")
	{
		// Ledger operations
		ledger := v1.Group("/ledger")
		{
			ledger.GET("/balance/:accountCode", ledgerHandler.GetBalance)
			ledger.GET("/balances", ledgerHandler.GetAllBalances)
			ledger.POST("/transfer", ledgerHandler.Transfer)
			ledger.GET("/transactions/:accountCode", ledgerHandler.GetTransactionHistory)
		}

		// Account management
		accounts := v1.Group("/accounts")
		{
			accounts.POST("", accountHandler.CreateAccount)
			accounts.GET("/:accountCode", accountHandler.GetAccount)
			accounts.PUT("/:accountCode", accountHandler.UpdateAccount)
			accounts.DELETE("/:accountCode", accountHandler.DeactivateAccount)
			accounts.GET("", accountHandler.ListAccounts)
			accounts.GET("/:accountCode/balance", accountHandler.GetAccountBalance)
			accounts.GET("/:accountCode/transactions", accountHandler.GetAccountTransactions)
		}

		// Transaction processing
		transactions := v1.Group("/transactions")
		{
			transactions.POST("", transactionHandler.CreateTransaction)
			transactions.GET("/:transactionId", transactionHandler.GetTransaction)
			transactions.PUT("/:transactionId/status", transactionHandler.UpdateTransactionStatus)
			transactions.POST("/:transactionId/reverse", transactionHandler.ReverseTransaction)
			transactions.GET("", transactionHandler.ListTransactions)
			transactions.POST("/batch", transactionHandler.ProcessBatch)
		}

		// Audit and compliance
		audit := v1.Group("/audit")
		{
			audit.GET("/trail/:entityId", auditHandler.GetAuditTrail)
			audit.GET("/events", auditHandler.GetAuditEvents)
			audit.POST("/verify", auditHandler.VerifyIntegrity)
			audit.GET("/reconciliation/:batchId", auditHandler.GetReconciliationReport)
		}

		// Administrative endpoints
		admin := v1.Group("/admin")
		{
			admin.POST("/reconcile", ledgerHandler.TriggerReconciliation)
			admin.GET("/metrics", func(c *gin.Context) {
				c.JSON(http.StatusOK, metrics.GetSummary())
			})
			admin.POST("/cleanup", ledgerHandler.CleanupExpiredRecords)
		}
	}

	return router
}

func initTracer(serviceName, jaegerEndpoint string) (*tracesdk.TracerProvider, error) {
	// Create the Jaeger exporter
	exp, err := jaeger.New(jaeger.WithCollectorEndpoint(jaeger.WithEndpoint(jaegerEndpoint)))
	if err != nil {
		return nil, err
	}

	tp := tracesdk.NewTracerProvider(
		tracesdk.WithBatcher(exp),
		tracesdk.WithResource(resource.NewWithAttributes(
			semconv.SchemaURL,
			semconv.ServiceNameKey.String(serviceName),
			semconv.ServiceVersionKey.String(version),
		)),
	)

	otel.SetTracerProvider(tp)
	return tp, nil
}

func handleKafkaMessage(ctx context.Context, message []byte) error {
	// TODO: Implement Kafka message handling for audit events, reconciliation, etc.
	log.Printf("Received Kafka message: %s", string(message))
	return nil
}

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
	"github.com/microservices-saga/services/saga-orchestrator/internal/config"
	"github.com/microservices-saga/services/saga-orchestrator/internal/handlers"
	"github.com/microservices-saga/services/saga-orchestrator/internal/infrastructure"
	"github.com/microservices-saga/services/saga-orchestrator/internal/orchestrator"
	"github.com/microservices-saga/services/saga-orchestrator/internal/repository"
	"github.com/microservices-saga/services/saga-orchestrator/internal/services"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	"github.com/sirupsen/logrus"
	"go.opentelemetry.io/contrib/instrumentation/github.com/gin-gonic/gin/otelgin"
)

func main() {
	// Load configuration
	cfg, err := config.Load()
	if err != nil {
		log.Fatalf("Failed to load configuration: %v", err)
	}

	// Setup logger
	logger := logrus.New()
	logger.SetLevel(logrus.InfoLevel)
	if cfg.LogLevel == "debug" {
		logger.SetLevel(logrus.DebugLevel)
	}
	logger.SetFormatter(&logrus.JSONFormatter{})

	// Initialize tracing
	tracerProvider, err := infrastructure.InitTracing(cfg.ServiceName, cfg.JaegerEndpoint)
	if err != nil {
		logger.Fatalf("Failed to initialize tracing: %v", err)
	}
	defer func() {
		if err := tracerProvider.Shutdown(context.Background()); err != nil {
			logger.Errorf("Error shutting down tracer provider: %v", err)
		}
	}()

	// Initialize metrics
	metrics := infrastructure.NewMetrics()

	// Initialize database
	db, err := infrastructure.NewDatabase(cfg.DatabaseURL)
	if err != nil {
		logger.Fatalf("Failed to connect to database: %v", err)
	}
	defer db.Close()

	// Initialize Redis
	redisClient, err := infrastructure.NewRedisClient(cfg.RedisURL)
	if err != nil {
		logger.Fatalf("Failed to connect to Redis: %v", err)
	}
	defer redisClient.Close()

	// Initialize Kafka
	kafkaProducer, err := infrastructure.NewKafkaProducer(cfg.KafkaBrokers)
	if err != nil {
		logger.Fatalf("Failed to create Kafka producer: %v", err)
	}
	defer kafkaProducer.Close()

	kafkaConsumer, err := infrastructure.NewKafkaConsumer(cfg.KafkaBrokers, "saga-orchestrator-group")
	if err != nil {
		logger.Fatalf("Failed to create Kafka consumer: %v", err)
	}
	defer kafkaConsumer.Close()

	// Initialize repositories
	sagaRepo := repository.NewSagaRepository(db)
	outboxRepo := repository.NewOutboxRepository(db)

	// Initialize services
	eventService := services.NewEventService(kafkaProducer, logger)
	idempotencyService := services.NewIdempotencyService(redisClient, logger)
	compensationService := services.NewCompensationService(eventService, logger)

	// Initialize saga orchestrator
	sagaOrchestrator := orchestrator.NewSagaOrchestrator(
		sagaRepo,
		outboxRepo,
		eventService,
		idempotencyService,
		compensationService,
		metrics,
		logger,
	)

	// Start background workers
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Start saga processor
	go sagaOrchestrator.StartSagaProcessor(ctx)

	// Start event consumer
	go func() {
		if err := sagaOrchestrator.StartEventConsumer(ctx, kafkaConsumer); err != nil {
			logger.Errorf("Event consumer error: %v", err)
		}
	}()

	// Start outbox processor
	go sagaOrchestrator.StartOutboxProcessor(ctx)

	// Setup HTTP server
	router := gin.New()
	router.Use(gin.Recovery())
	router.Use(otelgin.Middleware(cfg.ServiceName))
	router.Use(infrastructure.LoggingMiddleware(logger))
	router.Use(infrastructure.MetricsMiddleware(metrics))

	// Health check
	router.GET("/health", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"status": "healthy", "service": cfg.ServiceName})
	})

	// Metrics endpoint
	router.GET("/metrics", gin.WrapH(promhttp.Handler()))

	// Initialize handlers
	sagaHandler := handlers.NewSagaHandler(sagaOrchestrator, idempotencyService, logger)

	// API routes
	v1 := router.Group("/api/v1")
	{
		v1.POST("/sagas", sagaHandler.CreateSaga)
		v1.GET("/sagas/:id", sagaHandler.GetSaga)
		v1.GET("/sagas", sagaHandler.ListSagas)
		v1.POST("/sagas/:id/compensate", sagaHandler.CompensateSaga)
		v1.POST("/sagas/:id/retry", sagaHandler.RetrySaga)
	}

	// Start HTTP server
	server := &http.Server{
		Addr:    fmt.Sprintf(":%d", cfg.Port),
		Handler: router,
	}

	go func() {
		logger.Infof("Starting HTTP server on port %d", cfg.Port)
		if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			logger.Fatalf("Failed to start HTTP server: %v", err)
		}
	}()

	// Start metrics server
	metricsServer := &http.Server{
		Addr:    fmt.Sprintf(":%d", cfg.MetricsPort),
		Handler: promhttp.Handler(),
	}

	go func() {
		logger.Infof("Starting metrics server on port %d", cfg.MetricsPort)
		if err := metricsServer.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			logger.Fatalf("Failed to start metrics server: %v", err)
		}
	}()

	// Wait for interrupt signal
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit

	logger.Info("Shutting down servers...")

	// Graceful shutdown
	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer shutdownCancel()

	if err := server.Shutdown(shutdownCtx); err != nil {
		logger.Errorf("HTTP server forced to shutdown: %v", err)
	}

	if err := metricsServer.Shutdown(shutdownCtx); err != nil {
		logger.Errorf("Metrics server forced to shutdown: %v", err)
	}

	cancel() // Cancel background workers

	logger.Info("Server exited")
}

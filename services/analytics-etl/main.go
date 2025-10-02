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
	"github.com/microservices-saga/services/analytics-etl/internal/config"
	"github.com/microservices-saga/services/analytics-etl/internal/handlers"
	"github.com/microservices-saga/services/analytics-etl/internal/infrastructure"
	"github.com/microservices-saga/services/analytics-etl/internal/pipeline"
	"github.com/microservices-saga/services/analytics-etl/internal/processors"
	"github.com/microservices-saga/services/analytics-etl/internal/repository"
	"github.com/microservices-saga/services/analytics-etl/internal/services"
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

	// Initialize databases
	postgresDB, err := infrastructure.NewDatabase(cfg.PostgresURL)
	if err != nil {
		logger.Fatalf("Failed to connect to PostgreSQL: %v", err)
	}
	defer postgresDB.Close()

	clickhouseDB, err := infrastructure.NewClickHouseDB(cfg.ClickHouseURL)
	if err != nil {
		logger.Fatalf("Failed to connect to ClickHouse: %v", err)
	}
	defer clickhouseDB.Close()

	// Initialize Kafka
	kafkaProducer, err := infrastructure.NewKafkaProducer(cfg.KafkaBrokers)
	if err != nil {
		logger.Fatalf("Failed to create Kafka producer: %v", err)
	}
	defer kafkaProducer.Close()

	kafkaConsumer, err := infrastructure.NewKafkaConsumer(cfg.KafkaBrokers, "analytics-etl-group")
	if err != nil {
		logger.Fatalf("Failed to create Kafka consumer: %v", err)
	}
	defer kafkaConsumer.Close()

	// Initialize Redis for deduplication
	redisClient, err := infrastructure.NewRedisClient(cfg.RedisURL)
	if err != nil {
		logger.Fatalf("Failed to connect to Redis: %v", err)
	}
	defer redisClient.Close()

	// Initialize repositories
	sourceRepo := repository.NewSourceRepository(postgresDB)
	targetRepo := repository.NewTargetRepository(clickhouseDB)
	checkpointRepo := repository.NewCheckpointRepository(redisClient)

	// Initialize processors
	eventProcessor := processors.NewEventProcessor(logger)
	transformProcessor := processors.NewTransformProcessor(logger)
	aggregationProcessor := processors.NewAggregationProcessor(logger)
	deduplicationProcessor := processors.NewDeduplicationProcessor(redisClient, logger)

	// Initialize services
	etlService := services.NewETLService(
		sourceRepo,
		targetRepo,
		checkpointRepo,
		kafkaProducer,
		metrics,
		logger,
	)

	// Initialize pipeline
	etlPipeline := pipeline.NewETLPipeline(
		eventProcessor,
		transformProcessor,
		aggregationProcessor,
		deduplicationProcessor,
		etlService,
		metrics,
		logger,
	)

	// Start background workers
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Start CDC consumer
	go etlPipeline.StartCDCConsumer(ctx, kafkaConsumer)

	// Start batch processor
	go etlPipeline.StartBatchProcessor(ctx)

	// Start real-time processor
	go etlPipeline.StartRealTimeProcessor(ctx, kafkaConsumer)

	// Start aggregation processor
	go etlPipeline.StartAggregationProcessor(ctx)

	// Start checkpoint manager
	go etlService.StartCheckpointManager(ctx)

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
	etlHandler := handlers.NewETLHandler(etlService, etlPipeline, logger)
	metricsHandler := handlers.NewMetricsHandler(targetRepo, logger)

	// API routes
	v1 := router.Group("/api/v1")
	{
		// ETL management endpoints
		v1.GET("/pipeline/status", etlHandler.GetPipelineStatus)
		v1.POST("/pipeline/start", etlHandler.StartPipeline)
		v1.POST("/pipeline/stop", etlHandler.StopPipeline)
		v1.POST("/pipeline/restart", etlHandler.RestartPipeline)
		
		// Checkpoint management
		v1.GET("/checkpoints", etlHandler.ListCheckpoints)
		v1.GET("/checkpoints/:source", etlHandler.GetCheckpoint)
		v1.POST("/checkpoints/:source/reset", etlHandler.ResetCheckpoint)
		
		// Data quality endpoints
		v1.GET("/data-quality/metrics", etlHandler.GetDataQualityMetrics)
		v1.GET("/data-quality/issues", etlHandler.GetDataQualityIssues)
		
		// Analytics endpoints
		v1.GET("/analytics/saga-metrics", metricsHandler.GetSagaMetrics)
		v1.GET("/analytics/inventory-metrics", metricsHandler.GetInventoryMetrics)
		v1.GET("/analytics/payment-metrics", metricsHandler.GetPaymentMetrics)
		v1.GET("/analytics/real-time-dashboard", metricsHandler.GetRealTimeDashboard)
		
		// Backfill endpoints
		v1.POST("/backfill/start", etlHandler.StartBackfill)
		v1.GET("/backfill/status/:job_id", etlHandler.GetBackfillStatus)
		v1.POST("/backfill/cancel/:job_id", etlHandler.CancelBackfill)
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

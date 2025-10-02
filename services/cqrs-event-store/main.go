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
	"github.com/microservices-saga/services/cqrs-event-store/internal/config"
	"github.com/microservices-saga/services/cqrs-event-store/internal/eventstore"
	"github.com/microservices-saga/services/cqrs-event-store/internal/handlers"
	"github.com/microservices-saga/services/cqrs-event-store/internal/infrastructure"
	"github.com/microservices-saga/services/cqrs-event-store/internal/projections"
	"github.com/microservices-saga/services/cqrs-event-store/internal/repository"
	"github.com/microservices-saga/services/cqrs-event-store/internal/services"
	"github.com/microservices-saga/services/cqrs-event-store/internal/snapshots"
	"github.com/microservices-saga/services/cqrs-event-store/internal/timetravel"
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

	mongoDB, err := infrastructure.NewMongoDB(cfg.MongoURL)
	if err != nil {
		logger.Fatalf("Failed to connect to MongoDB: %v", err)
	}
	defer mongoDB.Disconnect(context.Background())

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

	kafkaConsumer, err := infrastructure.NewKafkaConsumer(cfg.KafkaBrokers, "cqrs-event-store-group")
	if err != nil {
		logger.Fatalf("Failed to create Kafka consumer: %v", err)
	}
	defer kafkaConsumer.Close()

	// Initialize Redis for caching
	redisClient, err := infrastructure.NewRedisClient(cfg.RedisURL)
	if err != nil {
		logger.Fatalf("Failed to connect to Redis: %v", err)
	}
	defer redisClient.Close()

	// Initialize repositories
	eventRepo := repository.NewEventRepository(postgresDB)
	snapshotRepo := repository.NewSnapshotRepository(postgresDB)
	projectionRepo := repository.NewProjectionRepository(mongoDB)
	analyticsRepo := repository.NewAnalyticsRepository(clickhouseDB)

	// Initialize event store
	eventStore := eventstore.NewEventStore(
		eventRepo,
		snapshotRepo,
		kafkaProducer,
		cfg.EventStoreConfig,
		metrics,
		logger,
	)

	// Initialize snapshot manager
	snapshotManager := snapshots.NewManager(
		snapshotRepo,
		eventStore,
		cfg.SnapshotConfig,
		metrics,
		logger,
	)

	// Initialize projection manager
	projectionManager := projections.NewManager(
		projectionRepo,
		eventStore,
		kafkaConsumer,
		cfg.ProjectionConfig,
		metrics,
		logger,
	)

	// Initialize time-travel service
	timeTravelService := timetravel.NewService(
		eventStore,
		snapshotManager,
		analyticsRepo,
		cfg.TimeTravelConfig,
		metrics,
		logger,
	)

	// Initialize services
	commandService := services.NewCommandService(
		eventStore,
		projectionManager,
		metrics,
		logger,
	)

	queryService := services.NewQueryService(
		projectionRepo,
		analyticsRepo,
		timeTravelService,
		redisClient,
		metrics,
		logger,
	)

	sagaService := services.NewSagaService(
		eventStore,
		commandService,
		cfg.SagaConfig,
		metrics,
		logger,
	)

	// Start background workers
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Start event store processor
	go eventStore.StartEventProcessor(ctx)

	// Start projection manager
	go projectionManager.StartProjectionProcessor(ctx)

	// Start snapshot manager
	go snapshotManager.StartSnapshotProcessor(ctx)

	// Start saga coordinator
	go sagaService.StartSagaCoordinator(ctx)

	// Start analytics processor
	go timeTravelService.StartAnalyticsProcessor(ctx)

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
	commandHandler := handlers.NewCommandHandler(commandService, logger)
	queryHandler := handlers.NewQueryHandler(queryService, logger)
	eventHandler := handlers.NewEventHandler(eventStore, logger)
	projectionHandler := handlers.NewProjectionHandler(projectionManager, logger)
	timeTravelHandler := handlers.NewTimeTravelHandler(timeTravelService, logger)
	sagaHandler := handlers.NewSagaHandler(sagaService, logger)

	// API routes
	v1 := router.Group("/api/v1")
	{
		// Command endpoints (Write side)
		v1.POST("/commands", commandHandler.ExecuteCommand)
		v1.POST("/commands/batch", commandHandler.ExecuteBatchCommands)
		v1.GET("/commands/:id/status", commandHandler.GetCommandStatus)
		
		// Query endpoints (Read side)
		v1.GET("/queries", queryHandler.ExecuteQuery)
		v1.POST("/queries/complex", queryHandler.ExecuteComplexQuery)
		v1.GET("/queries/:id/result", queryHandler.GetQueryResult)
		
		// Event store endpoints
		v1.GET("/events", eventHandler.GetEvents)
		v1.GET("/events/:aggregate_id", eventHandler.GetAggregateEvents)
		v1.POST("/events/:aggregate_id/replay", eventHandler.ReplayEvents)
		v1.GET("/events/stream", eventHandler.StreamEvents)
		
		// Projection endpoints
		v1.GET("/projections", projectionHandler.ListProjections)
		v1.GET("/projections/:name", projectionHandler.GetProjection)
		v1.POST("/projections/:name/rebuild", projectionHandler.RebuildProjection)
		v1.POST("/projections/:name/reset", projectionHandler.ResetProjection)
		v1.GET("/projections/:name/status", projectionHandler.GetProjectionStatus)
		
		// Time-travel endpoints
		v1.GET("/time-travel/snapshots", timeTravelHandler.ListSnapshots)
		v1.POST("/time-travel/restore", timeTravelHandler.RestoreToPointInTime)
		v1.GET("/time-travel/timeline/:aggregate_id", timeTravelHandler.GetTimeline)
		v1.POST("/time-travel/compare", timeTravelHandler.CompareStates)
		v1.GET("/time-travel/analytics", timeTravelHandler.GetAnalytics)
		
		// Saga endpoints
		v1.GET("/sagas", sagaHandler.ListSagas)
		v1.GET("/sagas/:id", sagaHandler.GetSaga)
		v1.POST("/sagas", sagaHandler.StartSaga)
		v1.POST("/sagas/:id/compensate", sagaHandler.CompensateSaga)
		v1.GET("/sagas/:id/status", sagaHandler.GetSagaStatus)
		
		// Analytics endpoints
		v1.GET("/analytics/events", timeTravelHandler.GetEventAnalytics)
		v1.GET("/analytics/aggregates", timeTravelHandler.GetAggregateAnalytics)
		v1.GET("/analytics/performance", timeTravelHandler.GetPerformanceAnalytics)
		v1.GET("/analytics/trends", timeTravelHandler.GetTrendAnalytics)
		
		// Snapshot endpoints
		v1.GET("/snapshots", eventHandler.ListSnapshots)
		v1.POST("/snapshots/:aggregate_id", eventHandler.CreateSnapshot)
		v1.DELETE("/snapshots/:id", eventHandler.DeleteSnapshot)
		
		// Cross-database transaction endpoints
		v1.POST("/transactions/distributed", commandHandler.ExecuteDistributedTransaction)
		v1.GET("/transactions/:id/status", commandHandler.GetTransactionStatus)
		v1.POST("/transactions/:id/commit", commandHandler.CommitTransaction)
		v1.POST("/transactions/:id/rollback", commandHandler.RollbackTransaction)
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

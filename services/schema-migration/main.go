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
	"github.com/microservices-saga/services/schema-migration/internal/config"
	"github.com/microservices-saga/services/schema-migration/internal/handlers"
	"github.com/microservices-saga/services/schema-migration/internal/infrastructure"
	"github.com/microservices-saga/services/schema-migration/internal/migration"
	"github.com/microservices-saga/services/schema-migration/internal/repository"
	"github.com/microservices-saga/services/schema-migration/internal/services"
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
	primaryDB, err := infrastructure.NewDatabase(cfg.PrimaryDatabaseURL)
	if err != nil {
		logger.Fatalf("Failed to connect to primary database: %v", err)
	}
	defer primaryDB.Close()

	replicaDB, err := infrastructure.NewDatabase(cfg.ReplicaDatabaseURL)
	if err != nil {
		logger.Fatalf("Failed to connect to replica database: %v", err)
	}
	defer replicaDB.Close()

	// Initialize Redis for coordination
	redisClient, err := infrastructure.NewRedisClient(cfg.RedisURL)
	if err != nil {
		logger.Fatalf("Failed to connect to Redis: %v", err)
	}
	defer redisClient.Close()

	// Initialize repositories
	migrationRepo := repository.NewMigrationRepository(primaryDB)
	lockRepo := repository.NewLockRepository(redisClient)
	backfillRepo := repository.NewBackfillRepository(primaryDB)

	// Initialize migration engines
	postgresEngine := migration.NewPostgreSQLEngine(primaryDB, replicaDB, logger)
	onlineEngine := migration.NewOnlineEngine(primaryDB, cfg.OnlineMigrationConfig, metrics, logger)
	backfillEngine := migration.NewBackfillEngine(primaryDB, cfg.BackfillConfig, metrics, logger)

	// Initialize migration coordinator
	coordinator := migration.NewCoordinator(
		migrationRepo,
		lockRepo,
		postgresEngine,
		onlineEngine,
		backfillEngine,
		cfg.CoordinatorConfig,
		metrics,
		logger,
	)

	// Initialize services
	migrationService := services.NewMigrationService(
		coordinator,
		migrationRepo,
		backfillRepo,
		metrics,
		logger,
	)

	// Start background workers
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Start migration monitor
	go coordinator.StartMigrationMonitor(ctx)

	// Start backfill processor
	go backfillEngine.StartBackfillProcessor(ctx)

	// Start health checker
	go migrationService.StartHealthChecker(ctx)

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
	migrationHandler := handlers.NewMigrationHandler(migrationService, logger)
	backfillHandler := handlers.NewBackfillHandler(backfillEngine, logger)

	// API routes
	v1 := router.Group("/api/v1")
	{
		// Migration management endpoints
		v1.GET("/migrations", migrationHandler.ListMigrations)
		v1.GET("/migrations/:id", migrationHandler.GetMigration)
		v1.POST("/migrations", migrationHandler.CreateMigration)
		v1.POST("/migrations/:id/execute", migrationHandler.ExecuteMigration)
		v1.POST("/migrations/:id/rollback", migrationHandler.RollbackMigration)
		v1.DELETE("/migrations/:id", migrationHandler.DeleteMigration)
		
		// Migration status and monitoring
		v1.GET("/migrations/:id/status", migrationHandler.GetMigrationStatus)
		v1.GET("/migrations/:id/progress", migrationHandler.GetMigrationProgress)
		v1.POST("/migrations/:id/pause", migrationHandler.PauseMigration)
		v1.POST("/migrations/:id/resume", migrationHandler.ResumeMigration)
		v1.POST("/migrations/:id/cancel", migrationHandler.CancelMigration)
		
		// Schema validation
		v1.POST("/migrations/validate", migrationHandler.ValidateMigration)
		v1.POST("/migrations/dry-run", migrationHandler.DryRunMigration)
		
		// Backfill management
		v1.GET("/backfills", backfillHandler.ListBackfills)
		v1.GET("/backfills/:id", backfillHandler.GetBackfill)
		v1.POST("/backfills", backfillHandler.CreateBackfill)
		v1.POST("/backfills/:id/start", backfillHandler.StartBackfill)
		v1.POST("/backfills/:id/pause", backfillHandler.PauseBackfill)
		v1.POST("/backfills/:id/resume", backfillHandler.ResumeBackfill)
		v1.POST("/backfills/:id/cancel", backfillHandler.CancelBackfill)
		
		// Feature flags for gradual rollout
		v1.GET("/feature-flags", migrationHandler.ListFeatureFlags)
		v1.POST("/feature-flags", migrationHandler.CreateFeatureFlag)
		v1.PUT("/feature-flags/:name", migrationHandler.UpdateFeatureFlag)
		v1.DELETE("/feature-flags/:name", migrationHandler.DeleteFeatureFlag)
		
		// Performance monitoring
		v1.GET("/performance/metrics", migrationHandler.GetPerformanceMetrics)
		v1.GET("/performance/impact", migrationHandler.GetPerformanceImpact)
		
		// Lock management
		v1.GET("/locks", migrationHandler.ListLocks)
		v1.POST("/locks/:name/acquire", migrationHandler.AcquireLock)
		v1.POST("/locks/:name/release", migrationHandler.ReleaseLock)
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

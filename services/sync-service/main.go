package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/microservices-saga/services/sync-service/internal/config"
	"github.com/microservices-saga/services/sync-service/internal/crdt"
	"github.com/microservices-saga/services/sync-service/internal/handlers"
	"github.com/microservices-saga/services/sync-service/internal/infrastructure"
	"github.com/microservices-saga/services/sync-service/internal/repository"
	"github.com/microservices-saga/services/sync-service/internal/services"
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

	// Initialize Redis
	redisClient, err := infrastructure.NewRedisClient(cfg.RedisURL)
	if err != nil {
		logger.Fatalf("Failed to connect to Redis: %v", err)
	}
	defer redisClient.Close()

	// Initialize repositories
	syncRepo := repository.NewSyncRepository(postgresDB, mongoDB)
	conflictRepo := repository.NewConflictRepository(mongoDB)
	deviceRepo := repository.NewDeviceRepository(mongoDB)

	// Initialize CRDT registry
	crdtRegistry := crdt.NewRegistry()
	crdtRegistry.RegisterCRDT("LWWRegister", crdt.NewLWWRegister)
	crdtRegistry.RegisterCRDT("GCounter", crdt.NewGCounter)
	crdtRegistry.RegisterCRDT("PNCounter", crdt.NewPNCounter)
	crdtRegistry.RegisterCRDT("GSet", crdt.NewGSet)
	crdtRegistry.RegisterCRDT("ORSet", crdt.NewORSet)
	crdtRegistry.RegisterCRDT("LWWMap", crdt.NewLWWMap)

	// Initialize services
	conflictResolver := services.NewConflictResolver(crdtRegistry, conflictRepo, logger)
	syncService := services.NewSyncService(syncRepo, deviceRepo, conflictResolver, redisClient, metrics, logger)
	vectorClockService := services.NewVectorClockService(redisClient, logger)

	// Start background workers
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Start conflict resolution worker
	go conflictResolver.StartConflictResolutionWorker(ctx)

	// Start sync monitoring
	go syncService.StartSyncMonitoring(ctx)

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
	syncHandler := handlers.NewSyncHandler(syncService, vectorClockService, logger)
	conflictHandler := handlers.NewConflictHandler(conflictResolver, logger)

	// API routes
	v1 := router.Group("/api/v1")
	{
		// Sync endpoints
		v1.POST("/sync/upload", syncHandler.UploadChanges)
		v1.GET("/sync/download", syncHandler.DownloadChanges)
		v1.POST("/sync/register-device", syncHandler.RegisterDevice)
		v1.GET("/sync/status/:device_id", syncHandler.GetSyncStatus)
		
		// Conflict resolution endpoints
		v1.GET("/conflicts", conflictHandler.ListConflicts)
		v1.GET("/conflicts/:id", conflictHandler.GetConflict)
		v1.POST("/conflicts/:id/resolve", conflictHandler.ResolveConflict)
		v1.POST("/conflicts/:id/auto-resolve", conflictHandler.AutoResolveConflict)
		
		// Vector clock endpoints
		v1.GET("/vector-clock/:device_id", syncHandler.GetVectorClock)
		v1.POST("/vector-clock/:device_id/increment", syncHandler.IncrementVectorClock)
		
		// CRDT endpoints
		v1.POST("/crdt/merge", syncHandler.MergeCRDT)
		v1.GET("/crdt/state/:entity_type/:entity_id", syncHandler.GetCRDTState)
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

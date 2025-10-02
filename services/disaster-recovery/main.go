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
	"github.com/microservices-saga/services/disaster-recovery/internal/backup"
	"github.com/microservices-saga/services/disaster-recovery/internal/config"
	"github.com/microservices-saga/services/disaster-recovery/internal/failover"
	"github.com/microservices-saga/services/disaster-recovery/internal/handlers"
	"github.com/microservices-saga/services/disaster-recovery/internal/infrastructure"
	"github.com/microservices-saga/services/disaster-recovery/internal/monitoring"
	"github.com/microservices-saga/services/disaster-recovery/internal/pitr"
	"github.com/microservices-saga/services/disaster-recovery/internal/replication"
	"github.com/microservices-saga/services/disaster-recovery/internal/repository"
	"github.com/microservices-saga/services/disaster-recovery/internal/services"
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

	// Initialize object storage for backups
	objectStorage, err := infrastructure.NewObjectStorage(cfg.S3Config)
	if err != nil {
		logger.Fatalf("Failed to initialize object storage: %v", err)
	}

	// Initialize repositories
	backupRepo := repository.NewBackupRepository(primaryDB, objectStorage)
	replicationRepo := repository.NewReplicationRepository(primaryDB, replicaDB)
	failoverRepo := repository.NewFailoverRepository(primaryDB, replicaDB)

	// Initialize backup manager
	backupManager := backup.NewManager(
		backupRepo,
		objectStorage,
		cfg.BackupConfig,
		metrics,
		logger,
	)

	// Initialize PITR manager
	pitrManager := pitr.NewManager(
		backupRepo,
		objectStorage,
		cfg.PITRConfig,
		metrics,
		logger,
	)

	// Initialize replication manager
	replicationManager := replication.NewManager(
		replicationRepo,
		cfg.ReplicationConfig,
		metrics,
		logger,
	)

	// Initialize failover manager
	failoverManager := failover.NewManager(
		failoverRepo,
		replicationManager,
		cfg.FailoverConfig,
		metrics,
		logger,
	)

	// Initialize monitoring
	healthMonitor := monitoring.NewHealthMonitor(
		primaryDB,
		replicaDB,
		replicationManager,
		metrics,
		logger,
	)

	// Initialize services
	drService := services.NewDRService(
		backupManager,
		pitrManager,
		replicationManager,
		failoverManager,
		healthMonitor,
		metrics,
		logger,
	)

	// Start background workers
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Start backup scheduler
	go backupManager.StartScheduler(ctx)

	// Start replication monitor
	go replicationManager.StartMonitor(ctx)

	// Start health monitor
	go healthMonitor.StartMonitoring(ctx)

	// Start failover detector
	go failoverManager.StartFailoverDetector(ctx)

	// Start WAL archiver
	go pitrManager.StartWALArchiver(ctx)

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
	drHandler := handlers.NewDRHandler(drService, logger)
	backupHandler := handlers.NewBackupHandler(backupManager, logger)
	pitrHandler := handlers.NewPITRHandler(pitrManager, logger)
	failoverHandler := handlers.NewFailoverHandler(failoverManager, logger)

	// API routes
	v1 := router.Group("/api/v1")
	{
		// DR management endpoints
		v1.GET("/dr/status", drHandler.GetDRStatus)
		v1.GET("/dr/health", drHandler.GetHealthStatus)
		v1.POST("/dr/test", drHandler.RunDRTest)
		
		// Backup endpoints
		v1.GET("/backups", backupHandler.ListBackups)
		v1.GET("/backups/:id", backupHandler.GetBackup)
		v1.POST("/backups", backupHandler.CreateBackup)
		v1.DELETE("/backups/:id", backupHandler.DeleteBackup)
		v1.POST("/backups/:id/restore", backupHandler.RestoreBackup)
		v1.POST("/backups/:id/verify", backupHandler.VerifyBackup)
		
		// PITR endpoints
		v1.GET("/pitr/status", pitrHandler.GetPITRStatus)
		v1.POST("/pitr/restore", pitrHandler.RestoreToPointInTime)
		v1.GET("/pitr/wal-archives", pitrHandler.ListWALArchives)
		v1.POST("/pitr/wal-archives/cleanup", pitrHandler.CleanupWALArchives)
		
		// Failover endpoints
		v1.GET("/failover/status", failoverHandler.GetFailoverStatus)
		v1.POST("/failover/initiate", failoverHandler.InitiateFailover)
		v1.POST("/failover/failback", failoverHandler.InitiateFailback)
		v1.GET("/failover/history", failoverHandler.GetFailoverHistory)
		
		// Replication endpoints
		v1.GET("/replication/status", drHandler.GetReplicationStatus)
		v1.GET("/replication/lag", drHandler.GetReplicationLag)
		v1.POST("/replication/resync", drHandler.ResyncReplica)
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

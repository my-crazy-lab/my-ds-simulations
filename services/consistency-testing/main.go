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
	"github.com/microservices-saga/services/consistency-testing/internal/config"
	"github.com/microservices-saga/services/consistency-testing/internal/handlers"
	"github.com/microservices-saga/services/consistency-testing/internal/infrastructure"
	"github.com/microservices-saga/services/consistency-testing/internal/jepsen"
	"github.com/microservices-saga/services/consistency-testing/internal/nemesis"
	"github.com/microservices-saga/services/consistency-testing/internal/repository"
	"github.com/microservices-saga/services/consistency-testing/internal/services"
	"github.com/microservices-saga/services/consistency-testing/internal/workloads"
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

	// Initialize databases for testing
	primaryDB, err := infrastructure.NewDatabase(cfg.PrimaryDatabaseURL)
	if err != nil {
		logger.Fatalf("Failed to connect to primary database: %v", err)
	}
	defer primaryDB.Close()

	replicaDBs := make([]*infrastructure.Database, len(cfg.ReplicaDatabaseURLs))
	for i, url := range cfg.ReplicaDatabaseURLs {
		db, err := infrastructure.NewDatabase(url)
		if err != nil {
			logger.Fatalf("Failed to connect to replica database %d: %v", i, err)
		}
		defer db.Close()
		replicaDBs[i] = db
	}

	// Initialize MongoDB cluster for testing
	mongoCluster, err := infrastructure.NewMongoCluster(cfg.MongoClusterURLs)
	if err != nil {
		logger.Fatalf("Failed to connect to MongoDB cluster: %v", err)
	}
	defer mongoCluster.Disconnect(context.Background())

	// Initialize ClickHouse cluster for testing
	clickhouseCluster, err := infrastructure.NewClickHouseCluster(cfg.ClickHouseClusterURLs)
	if err != nil {
		logger.Fatalf("Failed to connect to ClickHouse cluster: %v", err)
	}
	defer clickhouseCluster.Close()

	// Initialize repositories
	testRepo := repository.NewTestRepository(primaryDB)
	resultRepo := repository.NewResultRepository(primaryDB)
	historyRepo := repository.NewHistoryRepository(primaryDB)

	// Initialize nemesis (fault injection)
	networkNemesis := nemesis.NewNetworkNemesis(cfg.NemesisConfig, logger)
	processNemesis := nemesis.NewProcessNemesis(cfg.NemesisConfig, logger)
	clockNemesis := nemesis.NewClockNemesis(cfg.NemesisConfig, logger)

	// Initialize workloads
	bankWorkload := workloads.NewBankWorkload(primaryDB, replicaDBs, logger)
	registerWorkload := workloads.NewRegisterWorkload(primaryDB, replicaDBs, logger)
	setWorkload := workloads.NewSetWorkload(mongoCluster, logger)
	queueWorkload := workloads.NewQueueWorkload(primaryDB, replicaDBs, logger)

	// Initialize Jepsen-style test framework
	jepsenFramework := jepsen.NewFramework(
		testRepo,
		resultRepo,
		historyRepo,
		[]nemesis.Nemesis{networkNemesis, processNemesis, clockNemesis},
		[]workloads.Workload{bankWorkload, registerWorkload, setWorkload, queueWorkload},
		cfg.JepsenConfig,
		metrics,
		logger,
	)

	// Initialize services
	testService := services.NewTestService(
		jepsenFramework,
		testRepo,
		resultRepo,
		metrics,
		logger,
	)

	// Initialize consistency checkers
	linearizabilityChecker := services.NewLinearizabilityChecker(logger)
	sequentialChecker := services.NewSequentialConsistencyChecker(logger)
	eventualChecker := services.NewEventualConsistencyChecker(logger)

	// Start background workers
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Start test scheduler
	go testService.StartTestScheduler(ctx)

	// Start result analyzer
	go testService.StartResultAnalyzer(ctx)

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
	testHandler := handlers.NewTestHandler(testService, jepsenFramework, logger)
	resultHandler := handlers.NewResultHandler(resultRepo, linearizabilityChecker, sequentialChecker, eventualChecker, logger)
	nemesisHandler := handlers.NewNemesisHandler(networkNemesis, processNemesis, clockNemesis, logger)

	// API routes
	v1 := router.Group("/api/v1")
	{
		// Test management endpoints
		v1.GET("/tests", testHandler.ListTests)
		v1.GET("/tests/:id", testHandler.GetTest)
		v1.POST("/tests", testHandler.CreateTest)
		v1.POST("/tests/:id/start", testHandler.StartTest)
		v1.POST("/tests/:id/stop", testHandler.StopTest)
		v1.DELETE("/tests/:id", testHandler.DeleteTest)
		
		// Test execution and monitoring
		v1.GET("/tests/:id/status", testHandler.GetTestStatus)
		v1.GET("/tests/:id/progress", testHandler.GetTestProgress)
		v1.GET("/tests/:id/logs", testHandler.GetTestLogs)
		
		// Workload endpoints
		v1.GET("/workloads", testHandler.ListWorkloads)
		v1.GET("/workloads/:name", testHandler.GetWorkload)
		v1.POST("/workloads/:name/configure", testHandler.ConfigureWorkload)
		
		// Nemesis (fault injection) endpoints
		v1.GET("/nemesis", nemesisHandler.ListNemesis)
		v1.POST("/nemesis/network/partition", nemesisHandler.CreateNetworkPartition)
		v1.POST("/nemesis/network/heal", nemesisHandler.HealNetworkPartition)
		v1.POST("/nemesis/process/kill", nemesisHandler.KillProcess)
		v1.POST("/nemesis/process/start", nemesisHandler.StartProcess)
		v1.POST("/nemesis/clock/skew", nemesisHandler.SkewClock)
		v1.POST("/nemesis/clock/reset", nemesisHandler.ResetClock)
		
		// Result analysis endpoints
		v1.GET("/results", resultHandler.ListResults)
		v1.GET("/results/:id", resultHandler.GetResult)
		v1.POST("/results/:id/analyze", resultHandler.AnalyzeResult)
		v1.GET("/results/:id/violations", resultHandler.GetViolations)
		v1.GET("/results/:id/timeline", resultHandler.GetTimeline)
		
		// Consistency checking endpoints
		v1.POST("/consistency/linearizability", resultHandler.CheckLinearizability)
		v1.POST("/consistency/sequential", resultHandler.CheckSequentialConsistency)
		v1.POST("/consistency/eventual", resultHandler.CheckEventualConsistency)
		
		// History analysis endpoints
		v1.GET("/history/:test_id", resultHandler.GetHistory)
		v1.POST("/history/:test_id/visualize", resultHandler.VisualizeHistory)
		v1.POST("/history/:test_id/export", resultHandler.ExportHistory)
		
		// Cluster management endpoints
		v1.GET("/cluster/status", testHandler.GetClusterStatus)
		v1.POST("/cluster/reset", testHandler.ResetCluster)
		v1.GET("/cluster/topology", testHandler.GetClusterTopology)
		
		// Performance analysis endpoints
		v1.GET("/performance/metrics", resultHandler.GetPerformanceMetrics)
		v1.GET("/performance/latency", resultHandler.GetLatencyMetrics)
		v1.GET("/performance/throughput", resultHandler.GetThroughputMetrics)
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

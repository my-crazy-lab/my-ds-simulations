package main

import (
	"context"
	"fmt"
	"log"
	"net"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"strings"
	"syscall"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/exporters/jaeger"
	"go.opentelemetry.io/otel/sdk/trace"
	"google.golang.org/grpc"

	"./internal/config"
	"./internal/processor"
	"./internal/state"
	"./internal/rebalancer"
	"./internal/coordinator"
	pb "./proto"
)

// Prometheus metrics
var (
	messagesProcessedTotal = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "stream_processor_messages_processed_total",
			Help: "Total number of messages processed",
		},
		[]string{"processor_id", "topic", "partition", "status"},
	)

	processingLatencySeconds = prometheus.NewHistogramVec(
		prometheus.HistogramOpts{
			Name:    "stream_processor_processing_latency_seconds",
			Help:    "Message processing latency in seconds",
			Buckets: prometheus.DefBuckets,
		},
		[]string{"processor_id", "topic", "operation"},
	)

	stateSizeBytes = prometheus.NewGaugeVec(
		prometheus.GaugeOpts{
			Name: "stream_processor_state_size_bytes",
			Help: "Size of state stores in bytes",
		},
		[]string{"processor_id", "state_store", "partition"},
	)

	rebalancingDurationSeconds = prometheus.NewHistogramVec(
		prometheus.HistogramOpts{
			Name:    "stream_processor_rebalancing_duration_seconds",
			Help:    "Time spent rebalancing in seconds",
			Buckets: []float64{1, 5, 10, 30, 60, 120, 300},
		},
		[]string{"processor_id", "rebalance_type"},
	)

	exactlyOnceViolationsTotal = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "stream_processor_exactly_once_violations_total",
			Help: "Total number of exactly-once violations detected",
		},
		[]string{"processor_id", "violation_type"},
	)

	stateOperationsTotal = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "stream_processor_state_operations_total",
			Help: "Total number of state operations",
		},
		[]string{"processor_id", "state_store", "operation", "status"},
	)

	partitionLagSeconds = prometheus.NewGaugeVec(
		prometheus.GaugeOpts{
			Name: "stream_processor_partition_lag_seconds",
			Help: "Processing lag for partitions in seconds",
		},
		[]string{"processor_id", "topic", "partition"},
	)

	checkpointDurationSeconds = prometheus.NewHistogramVec(
		prometheus.HistogramOpts{
			Name:    "stream_processor_checkpoint_duration_seconds",
			Help:    "Time spent creating checkpoints in seconds",
			Buckets: []float64{0.1, 0.5, 1, 2, 5, 10, 30},
		},
		[]string{"processor_id", "checkpoint_type"},
	)
)

func init() {
	prometheus.MustRegister(messagesProcessedTotal)
	prometheus.MustRegister(processingLatencySeconds)
	prometheus.MustRegister(stateSizeBytes)
	prometheus.MustRegister(rebalancingDurationSeconds)
	prometheus.MustRegister(exactlyOnceViolationsTotal)
	prometheus.MustRegister(stateOperationsTotal)
	prometheus.MustRegister(partitionLagSeconds)
	prometheus.MustRegister(checkpointDurationSeconds)
}

type Server struct {
	config         *config.Config
	processor      *processor.StreamProcessor
	stateManager   *state.Manager
	rebalancer     *rebalancer.Rebalancer
	coordinator    *coordinator.Coordinator
	httpServer     *http.Server
	grpcServer     *grpc.Server
	shutdownChan   chan struct{}
}

func NewServer(cfg *config.Config) (*Server, error) {
	// Initialize state manager
	stateManager, err := state.NewManager(cfg)
	if err != nil {
		return nil, fmt.Errorf("failed to initialize state manager: %w", err)
	}

	// Initialize coordinator
	coordinator, err := coordinator.NewCoordinator(cfg)
	if err != nil {
		return nil, fmt.Errorf("failed to initialize coordinator: %w", err)
	}

	// Initialize rebalancer
	rebalancer, err := rebalancer.NewRebalancer(cfg, coordinator, stateManager)
	if err != nil {
		return nil, fmt.Errorf("failed to initialize rebalancer: %w", err)
	}

	// Initialize stream processor
	processor, err := processor.NewStreamProcessor(cfg, stateManager, rebalancer, coordinator)
	if err != nil {
		return nil, fmt.Errorf("failed to initialize stream processor: %w", err)
	}

	return &Server{
		config:       cfg,
		processor:    processor,
		stateManager: stateManager,
		rebalancer:   rebalancer,
		coordinator:  coordinator,
		shutdownChan: make(chan struct{}),
	}, nil
}

func (s *Server) Start() error {
	// Start coordinator
	if err := s.coordinator.Start(); err != nil {
		return fmt.Errorf("failed to start coordinator: %w", err)
	}

	// Start state manager
	if err := s.stateManager.Start(); err != nil {
		return fmt.Errorf("failed to start state manager: %w", err)
	}

	// Start rebalancer
	if err := s.rebalancer.Start(); err != nil {
		return fmt.Errorf("failed to start rebalancer: %w", err)
	}

	// Start stream processor
	if err := s.processor.Start(); err != nil {
		return fmt.Errorf("failed to start stream processor: %w", err)
	}

	// Start gRPC server
	go s.startGRPCServer()

	// Start HTTP server
	go s.startHTTPServer()

	// Start metrics collection
	go s.startMetricsCollection()

	log.Printf("Stream processor %s started", s.config.ProcessorID)
	return nil
}

func (s *Server) startGRPCServer() {
	lis, err := net.Listen("tcp", fmt.Sprintf(":%d", s.config.GRPCPort))
	if err != nil {
		log.Fatalf("Failed to listen on gRPC port: %v", err)
	}

	s.grpcServer = grpc.NewServer()
	pb.RegisterStreamProcessorServiceServer(s.grpcServer, s.processor)

	log.Printf("gRPC server listening on port %d", s.config.GRPCPort)
	if err := s.grpcServer.Serve(lis); err != nil {
		log.Fatalf("Failed to serve gRPC: %v", err)
	}
}

func (s *Server) startHTTPServer() {
	gin.SetMode(gin.ReleaseMode)
	router := gin.New()
	router.Use(gin.Logger(), gin.Recovery())

	// Health check endpoint
	router.GET("/health", s.handleHealth)

	// Processor endpoints
	processor := router.Group("/processor")
	{
		processor.GET("/status", s.handleProcessorStatus)
		processor.GET("/partitions", s.handlePartitions)
		processor.GET("/metrics", s.handleProcessorMetrics)
		processor.POST("/start", s.handleStartProcessing)
		processor.POST("/stop", s.handleStopProcessing)
		processor.POST("/checkpoint", s.handleCreateCheckpoint)
	}

	// State store endpoints
	state := router.Group("/state")
	{
		state.GET("/stores", s.handleListStateStores)
		state.GET("/stores/:store", s.handleStateStoreInfo)
		state.GET("/stores/:store/:key", s.handleGetState)
		state.PUT("/stores/:store/:key", s.handlePutState)
		state.DELETE("/stores/:store/:key", s.handleDeleteState)
		state.POST("/stores/:store/snapshot", s.handleCreateSnapshot)
		state.GET("/stores/:store/snapshots", s.handleListSnapshots)
	}

	// Rebalancing endpoints
	rebalance := router.Group("/rebalance")
	{
		rebalance.GET("/status", s.handleRebalanceStatus)
		rebalance.POST("/trigger", s.handleTriggerRebalance)
		rebalance.GET("/history", s.handleRebalanceHistory)
	}

	// Admin endpoints
	admin := router.Group("/admin")
	{
		admin.GET("/cluster/status", s.handleClusterStatus)
		admin.GET("/partition-assignment", s.handlePartitionAssignment)
		admin.POST("/scale-out", s.handleScaleOut)
		admin.POST("/scale-in", s.handleScaleIn)
		admin.GET("/exactly-once/status", s.handleExactlyOnceStatus)
		admin.POST("/exactly-once/validate", s.handleValidateExactlyOnce)
	}

	// Metrics endpoint
	router.GET("/metrics", gin.WrapH(promhttp.Handler()))

	s.httpServer = &http.Server{
		Addr:    fmt.Sprintf(":%d", s.config.HTTPPort),
		Handler: router,
	}

	log.Printf("HTTP server listening on port %d", s.config.HTTPPort)
	if err := s.httpServer.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		log.Fatalf("Failed to serve HTTP: %v", err)
	}
}

func (s *Server) startMetricsCollection() {
	ticker := time.NewTicker(10 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-ticker.C:
			s.collectMetrics()
		case <-s.shutdownChan:
			return
		}
	}
}

func (s *Server) collectMetrics() {
	processorID := s.config.ProcessorID

	// Collect processing metrics
	processingStats := s.processor.GetProcessingStats()
	for topic, topicStats := range processingStats.TopicStats {
		for partition, partitionStats := range topicStats.PartitionStats {
			partitionStr := strconv.Itoa(partition)
			
			messagesProcessedTotal.WithLabelValues(
				processorID, topic, partitionStr, "success").Add(float64(partitionStats.MessagesProcessed))
			messagesProcessedTotal.WithLabelValues(
				processorID, topic, partitionStr, "error").Add(float64(partitionStats.ProcessingErrors))
			
			partitionLagSeconds.WithLabelValues(
				processorID, topic, partitionStr).Set(partitionStats.LagSeconds)
		}
	}

	// Collect state metrics
	stateStats := s.stateManager.GetStateStats()
	for storeName, storeStats := range stateStats.StoreStats {
		for partition, partitionStats := range storeStats.PartitionStats {
			partitionStr := strconv.Itoa(partition)
			
			stateSizeBytes.WithLabelValues(
				processorID, storeName, partitionStr).Set(float64(partitionStats.SizeBytes))
			
			stateOperationsTotal.WithLabelValues(
				processorID, storeName, "get", "success").Add(float64(partitionStats.GetOperations))
			stateOperationsTotal.WithLabelValues(
				processorID, storeName, "put", "success").Add(float64(partitionStats.PutOperations))
			stateOperationsTotal.WithLabelValues(
				processorID, storeName, "delete", "success").Add(float64(partitionStats.DeleteOperations))
		}
	}

	// Collect rebalancing metrics
	rebalanceStats := s.rebalancer.GetRebalanceStats()
	if rebalanceStats.LastRebalanceDuration > 0 {
		rebalancingDurationSeconds.WithLabelValues(
			processorID, "partition_assignment").Observe(rebalanceStats.LastRebalanceDuration.Seconds())
	}

	// Collect exactly-once metrics
	exactlyOnceStats := s.processor.GetExactlyOnceStats()
	exactlyOnceViolationsTotal.WithLabelValues(
		processorID, "duplicate_processing").Add(float64(exactlyOnceStats.DuplicateProcessingDetected))
	exactlyOnceViolationsTotal.WithLabelValues(
		processorID, "out_of_order").Add(float64(exactlyOnceStats.OutOfOrderProcessing))
}

// HTTP Handlers
func (s *Server) handleHealth(c *gin.Context) {
	status := "healthy"
	if !s.processor.IsHealthy() || !s.stateManager.IsHealthy() || !s.rebalancer.IsHealthy() {
		status = "unhealthy"
		c.JSON(http.StatusServiceUnavailable, gin.H{"status": status})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"status":       status,
		"processor_id": s.config.ProcessorID,
		"uptime":       time.Since(s.processor.GetStartTime()).String(),
		"version":      "1.0.0",
	})
}

func (s *Server) handleProcessorStatus(c *gin.Context) {
	status := s.processor.GetStatus()
	c.JSON(http.StatusOK, status)
}

func (s *Server) handlePartitions(c *gin.Context) {
	partitions := s.processor.GetAssignedPartitions()
	c.JSON(http.StatusOK, gin.H{"partitions": partitions})
}

func (s *Server) handleProcessorMetrics(c *gin.Context) {
	metrics := s.processor.GetProcessingStats()
	c.JSON(http.StatusOK, metrics)
}

func (s *Server) handleStartProcessing(c *gin.Context) {
	var req struct {
		Topics []string `json:"topics" binding:"required"`
	}

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	timer := prometheus.NewTimer(processingLatencySeconds.WithLabelValues(
		s.config.ProcessorID, "admin", "start_processing"))
	defer timer.ObserveDuration()

	err := s.processor.StartProcessing(req.Topics)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"message": "Processing started",
		"topics":  req.Topics,
	})
}

func (s *Server) handleStopProcessing(c *gin.Context) {
	timer := prometheus.NewTimer(processingLatencySeconds.WithLabelValues(
		s.config.ProcessorID, "admin", "stop_processing"))
	defer timer.ObserveDuration()

	err := s.processor.StopProcessing()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"message": "Processing stopped"})
}

func (s *Server) handleCreateCheckpoint(c *gin.Context) {
	timer := prometheus.NewTimer(checkpointDurationSeconds.WithLabelValues(
		s.config.ProcessorID, "manual"))
	defer timer.ObserveDuration()

	checkpointID, err := s.processor.CreateCheckpoint()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"message":       "Checkpoint created",
		"checkpoint_id": checkpointID,
	})
}

func (s *Server) handleListStateStores(c *gin.Context) {
	stores := s.stateManager.ListStateStores()
	c.JSON(http.StatusOK, gin.H{"state_stores": stores})
}

func (s *Server) handleStateStoreInfo(c *gin.Context) {
	storeName := c.Param("store")
	info := s.stateManager.GetStateStoreInfo(storeName)
	if info == nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "State store not found"})
		return
	}
	c.JSON(http.StatusOK, info)
}

func (s *Server) handleGetState(c *gin.Context) {
	storeName := c.Param("store")
	key := c.Param("key")

	timer := prometheus.NewTimer(processingLatencySeconds.WithLabelValues(
		s.config.ProcessorID, "state", "get"))
	defer timer.ObserveDuration()

	value, err := s.stateManager.Get(storeName, key)
	if err != nil {
		stateOperationsTotal.WithLabelValues(
			s.config.ProcessorID, storeName, "get", "error").Inc()
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	stateOperationsTotal.WithLabelValues(
		s.config.ProcessorID, storeName, "get", "success").Inc()

	if value == nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Key not found"})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"key":   key,
		"value": value,
	})
}

func (s *Server) handlePutState(c *gin.Context) {
	storeName := c.Param("store")
	key := c.Param("key")

	var req struct {
		Value interface{} `json:"value" binding:"required"`
	}

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	timer := prometheus.NewTimer(processingLatencySeconds.WithLabelValues(
		s.config.ProcessorID, "state", "put"))
	defer timer.ObserveDuration()

	err := s.stateManager.Put(storeName, key, req.Value)
	if err != nil {
		stateOperationsTotal.WithLabelValues(
			s.config.ProcessorID, storeName, "put", "error").Inc()
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	stateOperationsTotal.WithLabelValues(
		s.config.ProcessorID, storeName, "put", "success").Inc()

	c.JSON(http.StatusOK, gin.H{
		"message": "State updated",
		"key":     key,
	})
}

func (s *Server) handleDeleteState(c *gin.Context) {
	storeName := c.Param("store")
	key := c.Param("key")

	timer := prometheus.NewTimer(processingLatencySeconds.WithLabelValues(
		s.config.ProcessorID, "state", "delete"))
	defer timer.ObserveDuration()

	err := s.stateManager.Delete(storeName, key)
	if err != nil {
		stateOperationsTotal.WithLabelValues(
			s.config.ProcessorID, storeName, "delete", "error").Inc()
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	stateOperationsTotal.WithLabelValues(
		s.config.ProcessorID, storeName, "delete", "success").Inc()

	c.JSON(http.StatusOK, gin.H{
		"message": "State deleted",
		"key":     key,
	})
}

func (s *Server) handleCreateSnapshot(c *gin.Context) {
	storeName := c.Param("store")

	timer := prometheus.NewTimer(checkpointDurationSeconds.WithLabelValues(
		s.config.ProcessorID, "snapshot"))
	defer timer.ObserveDuration()

	snapshotID, err := s.stateManager.CreateSnapshot(storeName)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"message":     "Snapshot created",
		"snapshot_id": snapshotID,
		"store":       storeName,
	})
}

func (s *Server) handleListSnapshots(c *gin.Context) {
	storeName := c.Param("store")
	snapshots := s.stateManager.ListSnapshots(storeName)
	c.JSON(http.StatusOK, gin.H{"snapshots": snapshots})
}

func (s *Server) handleRebalanceStatus(c *gin.Context) {
	status := s.rebalancer.GetStatus()
	c.JSON(http.StatusOK, status)
}

func (s *Server) handleTriggerRebalance(c *gin.Context) {
	timer := prometheus.NewTimer(rebalancingDurationSeconds.WithLabelValues(
		s.config.ProcessorID, "manual"))
	defer timer.ObserveDuration()

	err := s.rebalancer.TriggerRebalance()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"message": "Rebalancing triggered"})
}

func (s *Server) handleRebalanceHistory(c *gin.Context) {
	history := s.rebalancer.GetRebalanceHistory()
	c.JSON(http.StatusOK, gin.H{"rebalance_history": history})
}

func (s *Server) handleClusterStatus(c *gin.Context) {
	status := s.coordinator.GetClusterStatus()
	c.JSON(http.StatusOK, status)
}

func (s *Server) handlePartitionAssignment(c *gin.Context) {
	assignment := s.coordinator.GetPartitionAssignment()
	c.JSON(http.StatusOK, gin.H{"partition_assignment": assignment})
}

func (s *Server) handleScaleOut(c *gin.Context) {
	var req struct {
		NewProcessors []string `json:"new_processors" binding:"required"`
	}

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	err := s.coordinator.ScaleOut(req.NewProcessors)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"message":        "Scale out initiated",
		"new_processors": req.NewProcessors,
	})
}

func (s *Server) handleScaleIn(c *gin.Context) {
	var req struct {
		RemoveProcessors []string `json:"remove_processors" binding:"required"`
	}

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	err := s.coordinator.ScaleIn(req.RemoveProcessors)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"message":           "Scale in initiated",
		"remove_processors": req.RemoveProcessors,
	})
}

func (s *Server) handleExactlyOnceStatus(c *gin.Context) {
	status := s.processor.GetExactlyOnceStats()
	c.JSON(http.StatusOK, status)
}

func (s *Server) handleValidateExactlyOnce(c *gin.Context) {
	var req struct {
		Topic     string `json:"topic" binding:"required"`
		Duration  int    `json:"duration_seconds"`
		KeyRange  int    `json:"key_range"`
	}

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	if req.Duration == 0 {
		req.Duration = 60
	}
	if req.KeyRange == 0 {
		req.KeyRange = 1000
	}

	validationID, err := s.processor.StartExactlyOnceValidation(req.Topic, req.Duration, req.KeyRange)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"message":       "Exactly-once validation started",
		"validation_id": validationID,
		"duration":      req.Duration,
	})
}

func (s *Server) Shutdown(ctx context.Context) error {
	log.Println("Shutting down stream processor...")

	// Signal metrics collection to stop
	close(s.shutdownChan)

	// Shutdown HTTP server
	if s.httpServer != nil {
		if err := s.httpServer.Shutdown(ctx); err != nil {
			log.Printf("HTTP server shutdown error: %v", err)
		}
	}

	// Shutdown gRPC server
	if s.grpcServer != nil {
		s.grpcServer.GracefulStop()
	}

	// Shutdown components in reverse order
	if s.processor != nil {
		if err := s.processor.Shutdown(); err != nil {
			log.Printf("Stream processor shutdown error: %v", err)
		}
	}

	if s.rebalancer != nil {
		if err := s.rebalancer.Shutdown(); err != nil {
			log.Printf("Rebalancer shutdown error: %v", err)
		}
	}

	if s.stateManager != nil {
		if err := s.stateManager.Shutdown(); err != nil {
			log.Printf("State manager shutdown error: %v", err)
		}
	}

	if s.coordinator != nil {
		if err := s.coordinator.Shutdown(); err != nil {
			log.Printf("Coordinator shutdown error: %v", err)
		}
	}

	log.Println("Stream processor shutdown completed")
	return nil
}

func main() {
	// Initialize tracing
	exp, err := jaeger.New(jaeger.WithCollectorEndpoint(jaeger.WithEndpoint("http://jaeger:14268/api/traces")))
	if err != nil {
		log.Printf("Failed to initialize Jaeger exporter: %v", err)
	} else {
		tp := trace.NewTracerProvider(trace.WithBatcher(exp))
		otel.SetTracerProvider(tp)
	}

	// Load configuration
	cfg, err := config.LoadConfig()
	if err != nil {
		log.Fatalf("Failed to load configuration: %v", err)
	}

	// Create and start server
	server, err := NewServer(cfg)
	if err != nil {
		log.Fatalf("Failed to create server: %v", err)
	}

	if err := server.Start(); err != nil {
		log.Fatalf("Failed to start server: %v", err)
	}

	// Wait for shutdown signal
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)
	<-sigChan

	// Graceful shutdown
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	if err := server.Shutdown(ctx); err != nil {
		log.Fatalf("Server shutdown failed: %v", err)
	}
}

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
	"google.golang.org/grpc"

	"./internal/config"
	"./internal/kvstore"
	"./internal/storage"
	pb "./proto"
)

var (
	// Prometheus metrics
	operationsTotal = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "kvstore_operations_total",
			Help: "Total number of KV store operations",
		},
		[]string{"node_id", "operation", "consistency_level", "status"},
	)

	operationDuration = prometheus.NewHistogramVec(
		prometheus.HistogramOpts{
			Name:    "kvstore_operation_duration_seconds",
			Help:    "Duration of KV store operations",
			Buckets: prometheus.DefBuckets,
		},
		[]string{"node_id", "operation", "consistency_level"},
	)

	consistencyViolations = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "kvstore_consistency_violations_total",
			Help: "Total number of consistency violations detected",
		},
		[]string{"node_id", "violation_type"},
	)

	quorumFailures = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "kvstore_quorum_failures_total",
			Help: "Total number of quorum operation failures",
		},
		[]string{"node_id", "operation"},
	)

	readRepairTotal = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "kvstore_read_repair_total",
			Help: "Total number of read repair operations",
		},
		[]string{"node_id"},
	)

	storageSize = prometheus.NewGaugeVec(
		prometheus.GaugeOpts{
			Name: "kvstore_storage_size_bytes",
			Help: "Current storage size in bytes",
		},
		[]string{"node_id", "consistency_level"},
	)
)

func init() {
	prometheus.MustRegister(
		operationsTotal,
		operationDuration,
		consistencyViolations,
		quorumFailures,
		readRepairTotal,
		storageSize,
	)
}

type Server struct {
	config     *config.Config
	kvstore    *kvstore.Store
	storage    storage.Storage
	httpServer *http.Server
	grpcServer *grpc.Server
}

func main() {
	// Load configuration
	cfg, err := config.Load()
	if err != nil {
		log.Fatalf("Failed to load configuration: %v", err)
	}

	// Initialize tracing
	if err := initTracing(cfg); err != nil {
		log.Printf("Failed to initialize tracing: %v", err)
	}

	// Create server
	server, err := NewServer(cfg)
	if err != nil {
		log.Fatalf("Failed to create server: %v", err)
	}

	// Start server
	if err := server.Start(); err != nil {
		log.Fatalf("Failed to start server: %v", err)
	}

	// Wait for shutdown signal
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)
	<-sigChan

	log.Println("Shutting down server...")
	server.Stop()
}

func NewServer(cfg *config.Config) (*Server, error) {
	// Initialize storage
	storage, err := storage.NewRocksDBStorage(cfg.DataDir)
	if err != nil {
		return nil, fmt.Errorf("failed to initialize storage: %w", err)
	}

	// Initialize KV store
	kvstore, err := kvstore.NewStore(cfg, storage)
	if err != nil {
		return nil, fmt.Errorf("failed to initialize KV store: %w", err)
	}

	return &Server{
		config:  cfg,
		kvstore: kvstore,
		storage: storage,
	}, nil
}

func (s *Server) Start() error {
	// Start KV store
	if err := s.kvstore.Start(); err != nil {
		return fmt.Errorf("failed to start KV store: %w", err)
	}

	// Start gRPC server
	go s.startGRPCServer()

	// Start HTTP server
	go s.startHTTPServer()

	// Start metrics collection
	go s.collectMetrics()

	log.Printf("KV store node %s started successfully", s.config.NodeID)
	return nil
}

func (s *Server) Stop() {
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	// Stop HTTP server
	if s.httpServer != nil {
		s.httpServer.Shutdown(ctx)
	}

	// Stop gRPC server
	if s.grpcServer != nil {
		s.grpcServer.GracefulStop()
	}

	// Stop KV store
	s.kvstore.Stop()

	// Close storage
	s.storage.Close()

	log.Println("Server stopped successfully")
}

func (s *Server) startGRPCServer() {
	lis, err := net.Listen("tcp", fmt.Sprintf(":%d", s.config.GRPCPort))
	if err != nil {
		log.Fatalf("Failed to listen on gRPC port: %v", err)
	}

	s.grpcServer = grpc.NewServer()
	pb.RegisterKVStoreServiceServer(s.grpcServer, s.kvstore)

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
	router.GET("/health", s.healthCheck)

	// Metrics endpoint
	router.GET("/metrics", gin.WrapH(promhttp.Handler()))

	// KV API endpoints
	kv := router.Group("/kv")
	{
		kv.GET("/:key", s.getValue)
		kv.PUT("/:key", s.putValue)
		kv.DELETE("/:key", s.deleteValue)
		kv.POST("/batch", s.batchOperations)
	}

	// Admin API endpoints
	admin := router.Group("/admin")
	{
		admin.GET("/status", s.getStatus)
		admin.GET("/nodes", s.getNodes)
		admin.GET("/consistency", s.getConsistencyStatus)
		admin.POST("/repair", s.triggerRepair)
		admin.POST("/anti-entropy", s.triggerAntiEntropy)
	}

	s.httpServer = &http.Server{
		Addr:    fmt.Sprintf(":%d", s.config.HTTPPort),
		Handler: router,
	}

	log.Printf("HTTP server listening on port %d", s.config.HTTPPort)
	if err := s.httpServer.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		log.Fatalf("Failed to serve HTTP: %v", err)
	}
}

func (s *Server) collectMetrics() {
	ticker := time.NewTicker(10 * time.Second)
	defer ticker.Stop()

	for range ticker.C {
		// Collect storage metrics
		stats := s.storage.GetStats()
		storageSize.WithLabelValues(s.config.NodeID, "strong").Set(float64(stats.StrongConsistencySize))
		storageSize.WithLabelValues(s.config.NodeID, "eventual").Set(float64(stats.EventualConsistencySize))
	}
}

// HTTP Handlers

func (s *Server) healthCheck(c *gin.Context) {
	status := s.kvstore.GetStatus()
	c.JSON(http.StatusOK, gin.H{
		"status":           "healthy",
		"node_id":          s.config.NodeID,
		"consistency_mode": s.config.ConsistencyMode,
		"raft_enabled":     s.config.EnableRaft,
		"quorum_enabled":   s.config.EnableQuorum,
		"cluster_status":   status,
	})
}

func (s *Server) getValue(c *gin.Context) {
	key := c.Param("key")
	consistencyLevel := c.DefaultQuery("consistency", "eventual")

	start := time.Now()
	value, version, err := s.kvstore.Get(key, consistencyLevel)
	duration := time.Since(start)

	// Record metrics
	status := "success"
	if err != nil {
		status = "error"
	}
	operationsTotal.WithLabelValues(s.config.NodeID, "get", consistencyLevel, status).Inc()
	operationDuration.WithLabelValues(s.config.NodeID, "get", consistencyLevel).Observe(duration.Seconds())

	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"key":               key,
		"value":             value,
		"version":           version,
		"consistency_level": consistencyLevel,
		"node_id":           s.config.NodeID,
	})
}

func (s *Server) putValue(c *gin.Context) {
	key := c.Param("key")
	consistencyLevel := c.DefaultQuery("consistency", "eventual")
	ifVersion := c.Query("if-version")

	var req struct {
		Value string `json:"value" binding:"required"`
	}

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	start := time.Now()
	var version int64
	var err error

	if ifVersion != "" {
		expectedVersion, parseErr := strconv.ParseInt(ifVersion, 10, 64)
		if parseErr != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": "invalid if-version parameter"})
			return
		}
		version, err = s.kvstore.PutIfVersion(key, req.Value, expectedVersion, consistencyLevel)
	} else {
		version, err = s.kvstore.Put(key, req.Value, consistencyLevel)
	}

	duration := time.Since(start)

	// Record metrics
	status := "success"
	if err != nil {
		status = "error"
	}
	operationsTotal.WithLabelValues(s.config.NodeID, "put", consistencyLevel, status).Inc()
	operationDuration.WithLabelValues(s.config.NodeID, "put", consistencyLevel).Observe(duration.Seconds())

	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"key":               key,
		"value":             req.Value,
		"version":           version,
		"consistency_level": consistencyLevel,
		"node_id":           s.config.NodeID,
	})
}

func (s *Server) deleteValue(c *gin.Context) {
	key := c.Param("key")
	consistencyLevel := c.DefaultQuery("consistency", "eventual")

	start := time.Now()
	err := s.kvstore.Delete(key, consistencyLevel)
	duration := time.Since(start)

	// Record metrics
	status := "success"
	if err != nil {
		status = "error"
	}
	operationsTotal.WithLabelValues(s.config.NodeID, "delete", consistencyLevel, status).Inc()
	operationDuration.WithLabelValues(s.config.NodeID, "delete", consistencyLevel).Observe(duration.Seconds())

	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"key":               key,
		"deleted":           true,
		"consistency_level": consistencyLevel,
		"node_id":           s.config.NodeID,
	})
}

func (s *Server) batchOperations(c *gin.Context) {
	consistencyLevel := c.DefaultQuery("consistency", "eventual")

	var req struct {
		Operations []struct {
			Type  string `json:"type" binding:"required"`
			Key   string `json:"key" binding:"required"`
			Value string `json:"value,omitempty"`
		} `json:"operations" binding:"required"`
	}

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	start := time.Now()
	results, err := s.kvstore.Batch(req.Operations, consistencyLevel)
	duration := time.Since(start)

	// Record metrics
	status := "success"
	if err != nil {
		status = "error"
	}
	operationsTotal.WithLabelValues(s.config.NodeID, "batch", consistencyLevel, status).Inc()
	operationDuration.WithLabelValues(s.config.NodeID, "batch", consistencyLevel).Observe(duration.Seconds())

	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"results":           results,
		"consistency_level": consistencyLevel,
		"node_id":           s.config.NodeID,
	})
}

func (s *Server) getStatus(c *gin.Context) {
	status := s.kvstore.GetStatus()
	c.JSON(http.StatusOK, status)
}

func (s *Server) getNodes(c *gin.Context) {
	nodes := s.kvstore.GetNodes()
	c.JSON(http.StatusOK, gin.H{"nodes": nodes})
}

func (s *Server) getConsistencyStatus(c *gin.Context) {
	status := s.kvstore.GetConsistencyStatus()
	c.JSON(http.StatusOK, status)
}

func (s *Server) triggerRepair(c *gin.Context) {
	err := s.kvstore.TriggerReadRepair()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	readRepairTotal.WithLabelValues(s.config.NodeID).Inc()
	c.JSON(http.StatusOK, gin.H{"message": "Read repair triggered successfully"})
}

func (s *Server) triggerAntiEntropy(c *gin.Context) {
	err := s.kvstore.TriggerAntiEntropy()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"message": "Anti-entropy process triggered successfully"})
}

func initTracing(cfg *config.Config) error {
	if cfg.JaegerEndpoint == "" {
		return nil
	}

	exp, err := jaeger.New(jaeger.WithCollectorEndpoint(jaeger.WithEndpoint(cfg.JaegerEndpoint)))
	if err != nil {
		return err
	}

	tp := tracesdk.NewTracerProvider(
		tracesdk.WithBatcher(exp),
		tracesdk.WithResource(resource.NewWithAttributes(
			semconv.SchemaURL,
			semconv.ServiceNameKey.String("kvstore-node"),
			semconv.ServiceVersionKey.String("1.0.0"),
		)),
	)

	otel.SetTracerProvider(tp)
	return nil
}

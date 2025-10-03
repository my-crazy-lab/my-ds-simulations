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
	"./internal/cache"
	"./internal/consistent_hash"
	"./internal/hot_key"
	"./internal/circuit_breaker"
	"./internal/replication"
	pb "./proto"
)

// Prometheus metrics
var (
	cacheOperationsTotal = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "cache_operations_total",
			Help: "Total number of cache operations",
		},
		[]string{"node_id", "operation", "status"},
	)

	cacheLatencySeconds = prometheus.NewHistogramVec(
		prometheus.HistogramOpts{
			Name:    "cache_latency_seconds",
			Help:    "Cache operation latency in seconds",
			Buckets: []float64{0.0001, 0.0005, 0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0},
		},
		[]string{"node_id", "operation"},
	)

	cacheHitRatio = prometheus.NewGaugeVec(
		prometheus.GaugeOpts{
			Name: "cache_hit_ratio",
			Help: "Cache hit ratio",
		},
		[]string{"node_id"},
	)

	cacheMemoryUsageBytes = prometheus.NewGaugeVec(
		prometheus.GaugeOpts{
			Name: "cache_memory_usage_bytes",
			Help: "Cache memory usage in bytes",
		},
		[]string{"node_id", "type"},
	)

	hotKeysDetected = prometheus.NewGaugeVec(
		prometheus.GaugeOpts{
			Name: "cache_hot_keys_detected",
			Help: "Number of hot keys currently detected",
		},
		[]string{"node_id"},
	)

	circuitBreakerState = prometheus.NewGaugeVec(
		prometheus.GaugeOpts{
			Name: "cache_circuit_breaker_state",
			Help: "Circuit breaker state (0=closed, 1=open, 2=half-open)",
		},
		[]string{"node_id", "breaker_name"},
	)

	replicationLagSeconds = prometheus.NewGaugeVec(
		prometheus.GaugeOpts{
			Name: "cache_replication_lag_seconds",
			Help: "Replication lag in seconds",
		},
		[]string{"node_id", "replica_node"},
	)

	consistentHashRingSize = prometheus.NewGaugeVec(
		prometheus.GaugeOpts{
			Name: "cache_hash_ring_size",
			Help: "Number of nodes in consistent hash ring",
		},
		[]string{"node_id"},
	)

	keyDistributionBalance = prometheus.NewGaugeVec(
		prometheus.GaugeOpts{
			Name: "cache_key_distribution_balance",
			Help: "Key distribution balance score (0-1, 1 is perfectly balanced)",
		},
		[]string{"node_id"},
	)
)

func init() {
	prometheus.MustRegister(cacheOperationsTotal)
	prometheus.MustRegister(cacheLatencySeconds)
	prometheus.MustRegister(cacheHitRatio)
	prometheus.MustRegister(cacheMemoryUsageBytes)
	prometheus.MustRegister(hotKeysDetected)
	prometheus.MustRegister(circuitBreakerState)
	prometheus.MustRegister(replicationLagSeconds)
	prometheus.MustRegister(consistentHashRingSize)
	prometheus.MustRegister(keyDistributionBalance)
}

type Server struct {
	config              *config.Config
	cache               *cache.Cache
	hashRing            *consistent_hash.Ring
	hotKeyDetector      *hot_key.Detector
	circuitBreaker      *circuit_breaker.Manager
	replicationManager  *replication.Manager
	httpServer          *http.Server
	grpcServer          *grpc.Server
	shutdownChan        chan struct{}
}

func NewServer(cfg *config.Config) (*Server, error) {
	// Initialize cache
	cache, err := cache.NewCache(cfg)
	if err != nil {
		return nil, fmt.Errorf("failed to initialize cache: %w", err)
	}

	// Initialize consistent hash ring
	hashRing, err := consistent_hash.NewRing(cfg)
	if err != nil {
		return nil, fmt.Errorf("failed to initialize hash ring: %w", err)
	}

	// Initialize hot key detector
	hotKeyDetector, err := hot_key.NewDetector(cfg)
	if err != nil {
		return nil, fmt.Errorf("failed to initialize hot key detector: %w", err)
	}

	// Initialize circuit breaker
	circuitBreaker, err := circuit_breaker.NewManager(cfg)
	if err != nil {
		return nil, fmt.Errorf("failed to initialize circuit breaker: %w", err)
	}

	// Initialize replication manager
	replicationManager, err := replication.NewManager(cfg, cache, hashRing)
	if err != nil {
		return nil, fmt.Errorf("failed to initialize replication manager: %w", err)
	}

	return &Server{
		config:             cfg,
		cache:              cache,
		hashRing:           hashRing,
		hotKeyDetector:     hotKeyDetector,
		circuitBreaker:     circuitBreaker,
		replicationManager: replicationManager,
		shutdownChan:       make(chan struct{}),
	}, nil
}

func (s *Server) Start() error {
	// Start components
	if err := s.cache.Start(); err != nil {
		return fmt.Errorf("failed to start cache: %w", err)
	}

	if err := s.hashRing.Start(); err != nil {
		return fmt.Errorf("failed to start hash ring: %w", err)
	}

	if err := s.hotKeyDetector.Start(); err != nil {
		return fmt.Errorf("failed to start hot key detector: %w", err)
	}

	if err := s.circuitBreaker.Start(); err != nil {
		return fmt.Errorf("failed to start circuit breaker: %w", err)
	}

	if err := s.replicationManager.Start(); err != nil {
		return fmt.Errorf("failed to start replication manager: %w", err)
	}

	// Start gRPC server
	go s.startGRPCServer()

	// Start HTTP server
	go s.startHTTPServer()

	// Start metrics collection
	go s.startMetricsCollection()

	log.Printf("Cache node %s started", s.config.NodeID)
	return nil
}

func (s *Server) startGRPCServer() {
	lis, err := net.Listen("tcp", fmt.Sprintf(":%d", s.config.GRPCPort))
	if err != nil {
		log.Fatalf("Failed to listen on gRPC port: %v", err)
	}

	s.grpcServer = grpc.NewServer()
	pb.RegisterCacheServiceServer(s.grpcServer, s)

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

	// Cache endpoints
	cache := router.Group("/cache")
	{
		cache.GET("/:key", s.handleGet)
		cache.PUT("/:key", s.handlePut)
		cache.DELETE("/:key", s.handleDelete)
		cache.POST("/batch", s.handleBatch)
		cache.GET("/:key/exists", s.handleExists)
		cache.POST("/:key/expire", s.handleExpire)
		cache.GET("/:key/ttl", s.handleTTL)
	}

	// Admin endpoints
	admin := router.Group("/admin")
	{
		admin.GET("/status", s.handleStatus)
		admin.GET("/stats", s.handleStats)
		admin.GET("/hot-keys", s.handleHotKeys)
		admin.GET("/circuit-breakers", s.handleCircuitBreakers)
		admin.GET("/hash-ring", s.handleHashRing)
		admin.GET("/replication", s.handleReplication)
		admin.POST("/rebalance", s.handleRebalance)
		admin.POST("/flush", s.handleFlush)
		admin.POST("/hot-key-config", s.handleHotKeyConfig)
		admin.POST("/circuit-breaker-config", s.handleCircuitBreakerConfig)
	}

	// Cluster endpoints
	cluster := router.Group("/cluster")
	{
		cluster.GET("/status", s.handleClusterStatus)
		cluster.GET("/nodes", s.handleClusterNodes)
		cluster.POST("/join", s.handleJoinCluster)
		cluster.POST("/leave", s.handleLeaveCluster)
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
	nodeID := s.config.NodeID

	// Collect cache metrics
	stats := s.cache.GetStats()
	
	cacheHitRatio.WithLabelValues(nodeID).Set(stats.HitRatio)
	cacheMemoryUsageBytes.WithLabelValues(nodeID, "used").Set(float64(stats.MemoryUsed))
	cacheMemoryUsageBytes.WithLabelValues(nodeID, "limit").Set(float64(stats.MemoryLimit))

	// Collect hot key metrics
	hotKeys := s.hotKeyDetector.GetHotKeys()
	hotKeysDetected.WithLabelValues(nodeID).Set(float64(len(hotKeys)))

	// Collect circuit breaker metrics
	breakers := s.circuitBreaker.GetAllBreakers()
	for name, breaker := range breakers {
		state := 0.0
		switch breaker.State() {
		case "open":
			state = 1.0
		case "half-open":
			state = 2.0
		}
		circuitBreakerState.WithLabelValues(nodeID, name).Set(state)
	}

	// Collect hash ring metrics
	ringStats := s.hashRing.GetStats()
	consistentHashRingSize.WithLabelValues(nodeID).Set(float64(ringStats.NodeCount))
	keyDistributionBalance.WithLabelValues(nodeID).Set(ringStats.DistributionBalance)

	// Collect replication metrics
	replStats := s.replicationManager.GetStats()
	for replica, lag := range replStats.ReplicationLag {
		replicationLagSeconds.WithLabelValues(nodeID, replica).Set(lag.Seconds())
	}
}

// HTTP Handlers
func (s *Server) handleHealth(c *gin.Context) {
	status := "healthy"
	if !s.cache.IsHealthy() || !s.hashRing.IsHealthy() {
		status = "unhealthy"
		c.JSON(http.StatusServiceUnavailable, gin.H{"status": status})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"status":    status,
		"node_id":   s.config.NodeID,
		"uptime":    time.Since(s.cache.GetStartTime()).String(),
		"version":   "1.0.0",
	})
}

func (s *Server) handleGet(c *gin.Context) {
	key := c.Param("key")
	
	timer := prometheus.NewTimer(cacheLatencySeconds.WithLabelValues(s.config.NodeID, "get"))
	defer timer.ObserveDuration()

	// Check if key is hot and apply mitigation
	if s.hotKeyDetector.IsHotKey(key) {
		// Apply hot key mitigation strategies
		if s.circuitBreaker.IsOpen(key) {
			cacheOperationsTotal.WithLabelValues(s.config.NodeID, "get", "circuit_breaker_open").Inc()
			c.JSON(http.StatusServiceUnavailable, gin.H{"error": "Circuit breaker open for hot key"})
			return
		}
	}

	value, exists, err := s.cache.Get(key)
	if err != nil {
		cacheOperationsTotal.WithLabelValues(s.config.NodeID, "get", "error").Inc()
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	if !exists {
		cacheOperationsTotal.WithLabelValues(s.config.NodeID, "get", "miss").Inc()
		c.JSON(http.StatusNotFound, gin.H{"error": "Key not found"})
		return
	}

	cacheOperationsTotal.WithLabelValues(s.config.NodeID, "get", "hit").Inc()
	
	// Record hot key access
	s.hotKeyDetector.RecordAccess(key)

	c.JSON(http.StatusOK, gin.H{
		"key":   key,
		"value": value,
	})
}

func (s *Server) handlePut(c *gin.Context) {
	key := c.Param("key")

	var req struct {
		Value interface{} `json:"value" binding:"required"`
		TTL   int         `json:"ttl"`
	}

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	timer := prometheus.NewTimer(cacheLatencySeconds.WithLabelValues(s.config.NodeID, "put"))
	defer timer.ObserveDuration()

	// Check if this is a hot key write
	if s.hotKeyDetector.IsHotKey(key) {
		// Apply write-through for hot keys
		if err := s.replicationManager.WriteThrough(key, req.Value, time.Duration(req.TTL)*time.Second); err != nil {
			cacheOperationsTotal.WithLabelValues(s.config.NodeID, "put", "write_through_error").Inc()
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}
	}

	err := s.cache.Put(key, req.Value, time.Duration(req.TTL)*time.Second)
	if err != nil {
		cacheOperationsTotal.WithLabelValues(s.config.NodeID, "put", "error").Inc()
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	cacheOperationsTotal.WithLabelValues(s.config.NodeID, "put", "success").Inc()
	
	// Record hot key access
	s.hotKeyDetector.RecordAccess(key)

	c.JSON(http.StatusOK, gin.H{
		"message": "Key stored successfully",
		"key":     key,
	})
}

func (s *Server) handleDelete(c *gin.Context) {
	key := c.Param("key")

	timer := prometheus.NewTimer(cacheLatencySeconds.WithLabelValues(s.config.NodeID, "delete"))
	defer timer.ObserveDuration()

	err := s.cache.Delete(key)
	if err != nil {
		cacheOperationsTotal.WithLabelValues(s.config.NodeID, "delete", "error").Inc()
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	cacheOperationsTotal.WithLabelValues(s.config.NodeID, "delete", "success").Inc()

	c.JSON(http.StatusOK, gin.H{
		"message": "Key deleted successfully",
		"key":     key,
	})
}

func (s *Server) handleBatch(c *gin.Context) {
	var req struct {
		Operations []struct {
			Op    string      `json:"op" binding:"required"`
			Key   string      `json:"key" binding:"required"`
			Value interface{} `json:"value"`
			TTL   int         `json:"ttl"`
		} `json:"operations" binding:"required"`
	}

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	timer := prometheus.NewTimer(cacheLatencySeconds.WithLabelValues(s.config.NodeID, "batch"))
	defer timer.ObserveDuration()

	results := make([]map[string]interface{}, len(req.Operations))

	for i, op := range req.Operations {
		result := map[string]interface{}{
			"op":  op.Op,
			"key": op.Key,
		}

		switch op.Op {
		case "get":
			value, exists, err := s.cache.Get(op.Key)
			if err != nil {
				result["error"] = err.Error()
				cacheOperationsTotal.WithLabelValues(s.config.NodeID, "batch_get", "error").Inc()
			} else if !exists {
				result["error"] = "Key not found"
				cacheOperationsTotal.WithLabelValues(s.config.NodeID, "batch_get", "miss").Inc()
			} else {
				result["value"] = value
				cacheOperationsTotal.WithLabelValues(s.config.NodeID, "batch_get", "hit").Inc()
			}

		case "put":
			err := s.cache.Put(op.Key, op.Value, time.Duration(op.TTL)*time.Second)
			if err != nil {
				result["error"] = err.Error()
				cacheOperationsTotal.WithLabelValues(s.config.NodeID, "batch_put", "error").Inc()
			} else {
				result["success"] = true
				cacheOperationsTotal.WithLabelValues(s.config.NodeID, "batch_put", "success").Inc()
			}

		case "delete":
			err := s.cache.Delete(op.Key)
			if err != nil {
				result["error"] = err.Error()
				cacheOperationsTotal.WithLabelValues(s.config.NodeID, "batch_delete", "error").Inc()
			} else {
				result["success"] = true
				cacheOperationsTotal.WithLabelValues(s.config.NodeID, "batch_delete", "success").Inc()
			}

		default:
			result["error"] = "Unknown operation"
		}

		results[i] = result
		
		// Record access for hot key detection
		s.hotKeyDetector.RecordAccess(op.Key)
	}

	c.JSON(http.StatusOK, gin.H{
		"results": results,
	})
}

func (s *Server) handleExists(c *gin.Context) {
	key := c.Param("key")

	timer := prometheus.NewTimer(cacheLatencySeconds.WithLabelValues(s.config.NodeID, "exists"))
	defer timer.ObserveDuration()

	exists := s.cache.Exists(key)
	
	cacheOperationsTotal.WithLabelValues(s.config.NodeID, "exists", "success").Inc()

	c.JSON(http.StatusOK, gin.H{
		"key":    key,
		"exists": exists,
	})
}

func (s *Server) handleExpire(c *gin.Context) {
	key := c.Param("key")

	var req struct {
		TTL int `json:"ttl" binding:"required"`
	}

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	timer := prometheus.NewTimer(cacheLatencySeconds.WithLabelValues(s.config.NodeID, "expire"))
	defer timer.ObserveDuration()

	err := s.cache.Expire(key, time.Duration(req.TTL)*time.Second)
	if err != nil {
		cacheOperationsTotal.WithLabelValues(s.config.NodeID, "expire", "error").Inc()
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	cacheOperationsTotal.WithLabelValues(s.config.NodeID, "expire", "success").Inc()

	c.JSON(http.StatusOK, gin.H{
		"message": "TTL set successfully",
		"key":     key,
		"ttl":     req.TTL,
	})
}

func (s *Server) handleTTL(c *gin.Context) {
	key := c.Param("key")

	timer := prometheus.NewTimer(cacheLatencySeconds.WithLabelValues(s.config.NodeID, "ttl"))
	defer timer.ObserveDuration()

	ttl, err := s.cache.TTL(key)
	if err != nil {
		cacheOperationsTotal.WithLabelValues(s.config.NodeID, "ttl", "error").Inc()
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	cacheOperationsTotal.WithLabelValues(s.config.NodeID, "ttl", "success").Inc()

	c.JSON(http.StatusOK, gin.H{
		"key": key,
		"ttl": int(ttl.Seconds()),
	})
}

func (s *Server) handleStatus(c *gin.Context) {
	status := s.cache.GetStatus()
	c.JSON(http.StatusOK, status)
}

func (s *Server) handleStats(c *gin.Context) {
	stats := s.cache.GetStats()
	c.JSON(http.StatusOK, stats)
}

func (s *Server) handleHotKeys(c *gin.Context) {
	hotKeys := s.hotKeyDetector.GetHotKeys()
	c.JSON(http.StatusOK, gin.H{"hot_keys": hotKeys})
}

func (s *Server) handleCircuitBreakers(c *gin.Context) {
	breakers := s.circuitBreaker.GetAllBreakers()
	breakerStatus := make(map[string]interface{})
	
	for name, breaker := range breakers {
		breakerStatus[name] = map[string]interface{}{
			"state":         breaker.State(),
			"failure_count": breaker.FailureCount(),
			"success_count": breaker.SuccessCount(),
			"last_failure":  breaker.LastFailure(),
		}
	}
	
	c.JSON(http.StatusOK, gin.H{"circuit_breakers": breakerStatus})
}

func (s *Server) handleHashRing(c *gin.Context) {
	ringInfo := s.hashRing.GetInfo()
	c.JSON(http.StatusOK, ringInfo)
}

func (s *Server) handleReplication(c *gin.Context) {
	replStats := s.replicationManager.GetStats()
	c.JSON(http.StatusOK, replStats)
}

func (s *Server) handleRebalance(c *gin.Context) {
	err := s.hashRing.Rebalance()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"message": "Rebalancing initiated"})
}

func (s *Server) handleFlush(c *gin.Context) {
	err := s.cache.Flush()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"message": "Cache flushed successfully"})
}

func (s *Server) handleHotKeyConfig(c *gin.Context) {
	var req struct {
		ThresholdRPS    int `json:"threshold_requests_per_second"`
		WindowSeconds   int `json:"detection_window_seconds"`
		Strategy        string `json:"mitigation_strategy"`
	}

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	config := hot_key.Config{
		ThresholdRPS:  req.ThresholdRPS,
		WindowSeconds: req.WindowSeconds,
		Strategy:      req.Strategy,
	}

	err := s.hotKeyDetector.UpdateConfig(config)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"message": "Hot key configuration updated"})
}

func (s *Server) handleCircuitBreakerConfig(c *gin.Context) {
	var req struct {
		FailureThreshold int `json:"failure_threshold"`
		SuccessThreshold int `json:"success_threshold"`
		TimeoutSeconds   int `json:"timeout_seconds"`
	}

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	config := circuit_breaker.Config{
		FailureThreshold: req.FailureThreshold,
		SuccessThreshold: req.SuccessThreshold,
		Timeout:          time.Duration(req.TimeoutSeconds) * time.Second,
	}

	err := s.circuitBreaker.UpdateConfig(config)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"message": "Circuit breaker configuration updated"})
}

func (s *Server) handleClusterStatus(c *gin.Context) {
	status := s.hashRing.GetClusterStatus()
	c.JSON(http.StatusOK, status)
}

func (s *Server) handleClusterNodes(c *gin.Context) {
	nodes := s.hashRing.GetNodes()
	c.JSON(http.StatusOK, gin.H{"nodes": nodes})
}

func (s *Server) handleJoinCluster(c *gin.Context) {
	var req struct {
		NodeID   string `json:"node_id" binding:"required"`
		Address  string `json:"address" binding:"required"`
	}

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	err := s.hashRing.AddNode(req.NodeID, req.Address)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"message": "Node joined cluster",
		"node_id": req.NodeID,
	})
}

func (s *Server) handleLeaveCluster(c *gin.Context) {
	var req struct {
		NodeID string `json:"node_id" binding:"required"`
	}

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	err := s.hashRing.RemoveNode(req.NodeID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"message": "Node left cluster",
		"node_id": req.NodeID,
	})
}

func (s *Server) Shutdown(ctx context.Context) error {
	log.Println("Shutting down cache node...")

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
	if s.replicationManager != nil {
		if err := s.replicationManager.Shutdown(); err != nil {
			log.Printf("Replication manager shutdown error: %v", err)
		}
	}

	if s.circuitBreaker != nil {
		if err := s.circuitBreaker.Shutdown(); err != nil {
			log.Printf("Circuit breaker shutdown error: %v", err)
		}
	}

	if s.hotKeyDetector != nil {
		if err := s.hotKeyDetector.Shutdown(); err != nil {
			log.Printf("Hot key detector shutdown error: %v", err)
		}
	}

	if s.hashRing != nil {
		if err := s.hashRing.Shutdown(); err != nil {
			log.Printf("Hash ring shutdown error: %v", err)
		}
	}

	if s.cache != nil {
		if err := s.cache.Shutdown(); err != nil {
			log.Printf("Cache shutdown error: %v", err)
		}
	}

	log.Println("Cache node shutdown completed")
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

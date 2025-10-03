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
	"./internal/crdt"
	"./internal/gossip"
	"./internal/replication"
	"./internal/storage"
	"./internal/antientropy"
	pb "./proto"
)

// Prometheus metrics
var (
	crdtOperationsTotal = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "geodatastore_crdt_operations_total",
			Help: "Total number of CRDT operations",
		},
		[]string{"node_id", "region", "crdt_type", "operation"},
	)

	replicationLagSeconds = prometheus.NewGaugeVec(
		prometheus.GaugeOpts{
			Name: "geodatastore_replication_lag_seconds",
			Help: "Replication lag in seconds between regions",
		},
		[]string{"node_id", "source_region", "target_region"},
	)

	conflictsResolvedTotal = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "geodatastore_conflicts_resolved_total",
			Help: "Total number of conflicts resolved",
		},
		[]string{"node_id", "region", "crdt_type", "resolution_strategy"},
	)

	antiEntropySyncsTotal = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "geodatastore_anti_entropy_syncs_total",
			Help: "Total number of anti-entropy synchronization events",
		},
		[]string{"node_id", "region", "sync_type", "status"},
	)

	vectorClockSize = prometheus.NewGaugeVec(
		prometheus.GaugeOpts{
			Name: "geodatastore_vector_clock_size",
			Help: "Size of vector clocks",
		},
		[]string{"node_id", "region", "key"},
	)

	gossipMessagesTotal = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "geodatastore_gossip_messages_total",
			Help: "Total number of gossip messages",
		},
		[]string{"node_id", "region", "message_type", "direction"},
	)

	operationDuration = prometheus.NewHistogramVec(
		prometheus.HistogramOpts{
			Name:    "geodatastore_operation_duration_seconds",
			Help:    "Duration of geodatastore operations",
			Buckets: prometheus.DefBuckets,
		},
		[]string{"node_id", "region", "operation", "status"},
	)
)

func init() {
	prometheus.MustRegister(crdtOperationsTotal)
	prometheus.MustRegister(replicationLagSeconds)
	prometheus.MustRegister(conflictsResolvedTotal)
	prometheus.MustRegister(antiEntropySyncsTotal)
	prometheus.MustRegister(vectorClockSize)
	prometheus.MustRegister(gossipMessagesTotal)
	prometheus.MustRegister(operationDuration)
}

type Server struct {
	config           *config.Config
	storage          storage.Storage
	crdtStore        *crdt.Store
	gossipManager    *gossip.Manager
	replicationMgr   *replication.Manager
	antiEntropyMgr   *antientropy.Manager
	httpServer       *http.Server
	grpcServer       *grpc.Server
	shutdownComplete chan struct{}
}

func NewServer(cfg *config.Config) (*Server, error) {
	// Initialize storage
	storage, err := storage.NewRocksDBStorage(cfg.DataDir)
	if err != nil {
		return nil, fmt.Errorf("failed to initialize storage: %w", err)
	}

	// Initialize CRDT store
	crdtStore, err := crdt.NewStore(cfg, storage)
	if err != nil {
		return nil, fmt.Errorf("failed to initialize CRDT store: %w", err)
	}

	// Initialize gossip manager
	gossipManager, err := gossip.NewManager(cfg, crdtStore)
	if err != nil {
		return nil, fmt.Errorf("failed to initialize gossip manager: %w", err)
	}

	// Initialize replication manager
	replicationMgr, err := replication.NewManager(cfg, crdtStore, gossipManager)
	if err != nil {
		return nil, fmt.Errorf("failed to initialize replication manager: %w", err)
	}

	// Initialize anti-entropy manager
	antiEntropyMgr, err := antientropy.NewManager(cfg, crdtStore, replicationMgr)
	if err != nil {
		return nil, fmt.Errorf("failed to initialize anti-entropy manager: %w", err)
	}

	return &Server{
		config:           cfg,
		storage:          storage,
		crdtStore:        crdtStore,
		gossipManager:    gossipManager,
		replicationMgr:   replicationMgr,
		antiEntropyMgr:   antiEntropyMgr,
		shutdownComplete: make(chan struct{}),
	}, nil
}

func (s *Server) Start() error {
	// Start gossip manager
	if err := s.gossipManager.Start(); err != nil {
		return fmt.Errorf("failed to start gossip manager: %w", err)
	}

	// Start replication manager
	if err := s.replicationMgr.Start(); err != nil {
		return fmt.Errorf("failed to start replication manager: %w", err)
	}

	// Start anti-entropy manager
	if err := s.antiEntropyMgr.Start(); err != nil {
		return fmt.Errorf("failed to start anti-entropy manager: %w", err)
	}

	// Start gRPC server
	go s.startGRPCServer()

	// Start HTTP server
	go s.startHTTPServer()

	// Start metrics collection
	go s.startMetricsCollection()

	log.Printf("Geo-replicated datastore node %s started in region %s", s.config.NodeID, s.config.Region)
	return nil
}

func (s *Server) startGRPCServer() {
	lis, err := net.Listen("tcp", fmt.Sprintf(":%d", s.config.GRPCPort))
	if err != nil {
		log.Fatalf("Failed to listen on gRPC port: %v", err)
	}

	s.grpcServer = grpc.NewServer()
	pb.RegisterGeoDatastoreServiceServer(s.grpcServer, s.replicationMgr)

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

	// Admin endpoints
	admin := router.Group("/admin")
	{
		admin.GET("/status", s.handleStatus)
		admin.GET("/regions", s.handleListRegions)
		admin.GET("/replication/lag", s.handleReplicationLag)
		admin.POST("/anti-entropy/full-sync", s.handleFullSync)
		admin.POST("/anti-entropy/sync/:region", s.handleSyncRegion)
		admin.GET("/conflicts", s.handleListConflicts)
		admin.POST("/conflicts/:id/resolve", s.handleResolveConflict)
		admin.GET("/gossip/status", s.handleGossipStatus)
		admin.GET("/vector-clocks", s.handleVectorClocks)
	}

	// CRDT endpoints
	crdt := router.Group("/crdt")
	{
		// Counter operations
		counters := crdt.Group("/counters")
		{
			counters.POST("/:key", s.handleCreateCounter)
			counters.GET("/:key", s.handleGetCounter)
			counters.POST("/:key/increment", s.handleIncrementCounter)
			counters.POST("/:key/decrement", s.handleDecrementCounter)
			counters.DELETE("/:key", s.handleDeleteCounter)
		}

		// Set operations
		sets := crdt.Group("/sets")
		{
			sets.POST("/:key", s.handleCreateSet)
			sets.GET("/:key", s.handleGetSet)
			sets.POST("/:key/add", s.handleAddToSet)
			sets.POST("/:key/remove", s.handleRemoveFromSet)
			sets.DELETE("/:key", s.handleDeleteSet)
		}

		// Register operations
		registers := crdt.Group("/registers")
		{
			registers.POST("/:key", s.handleCreateRegister)
			registers.GET("/:key", s.handleGetRegister)
			registers.PUT("/:key", s.handleSetRegister)
			registers.DELETE("/:key", s.handleDeleteRegister)
		}

		// Map operations
		maps := crdt.Group("/maps")
		{
			maps.POST("/:key", s.handleCreateMap)
			maps.GET("/:key", s.handleGetMap)
			maps.PUT("/:key/:field", s.handleSetMapField)
			maps.DELETE("/:key/:field", s.handleDeleteMapField)
			maps.DELETE("/:key", s.handleDeleteMap)
		}
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
		case <-s.shutdownComplete:
			return
		}
	}
}

func (s *Server) collectMetrics() {
	nodeID := s.config.NodeID
	region := s.config.Region

	// Collect replication lag metrics
	for targetRegion, lag := range s.replicationMgr.GetReplicationLag() {
		replicationLagSeconds.WithLabelValues(nodeID, region, targetRegion).Set(lag.Seconds())
	}

	// Collect vector clock size metrics
	for key, clockSize := range s.crdtStore.GetVectorClockSizes() {
		vectorClockSize.WithLabelValues(nodeID, region, key).Set(float64(clockSize))
	}

	// Collect gossip metrics
	gossipStats := s.gossipManager.GetStats()
	for msgType, count := range gossipStats.MessagesSent {
		gossipMessagesTotal.WithLabelValues(nodeID, region, msgType, "sent").Add(float64(count))
	}
	for msgType, count := range gossipStats.MessagesReceived {
		gossipMessagesTotal.WithLabelValues(nodeID, region, msgType, "received").Add(float64(count))
	}
}

// HTTP Handlers
func (s *Server) handleHealth(c *gin.Context) {
	status := "healthy"
	if !s.gossipManager.IsHealthy() || !s.replicationMgr.IsHealthy() {
		status = "unhealthy"
		c.JSON(http.StatusServiceUnavailable, gin.H{"status": status})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"status":     status,
		"node_id":    s.config.NodeID,
		"region":     s.config.Region,
		"datacenter": s.config.Datacenter,
		"uptime":     time.Since(s.crdtStore.GetStartTime()).String(),
	})
}

func (s *Server) handleStatus(c *gin.Context) {
	status := gin.H{
		"node_id":    s.config.NodeID,
		"region":     s.config.Region,
		"datacenter": s.config.Datacenter,
		"cluster_nodes": s.config.ClusterNodes,
		"region_nodes":  s.config.RegionNodes,
		"gossip_status": s.gossipManager.GetStatus(),
		"replication_status": s.replicationMgr.GetStatus(),
		"anti_entropy_status": s.antiEntropyMgr.GetStatus(),
		"crdt_stats": s.crdtStore.GetStats(),
	}
	c.JSON(http.StatusOK, status)
}

func (s *Server) handleListRegions(c *gin.Context) {
	regions := s.gossipManager.GetKnownRegions()
	c.JSON(http.StatusOK, gin.H{"regions": regions})
}

func (s *Server) handleReplicationLag(c *gin.Context) {
	lag := s.replicationMgr.GetReplicationLag()
	c.JSON(http.StatusOK, gin.H{"replication_lag": lag})
}

func (s *Server) handleFullSync(c *gin.Context) {
	timer := prometheus.NewTimer(operationDuration.WithLabelValues(
		s.config.NodeID, s.config.Region, "full_sync", "success"))
	defer timer.ObserveDuration()

	err := s.antiEntropyMgr.TriggerFullSync()
	if err != nil {
		operationDuration.WithLabelValues(
			s.config.NodeID, s.config.Region, "full_sync", "error").Observe(0)
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"message": "Full synchronization triggered"})
}

func (s *Server) handleSyncRegion(c *gin.Context) {
	region := c.Param("region")
	
	timer := prometheus.NewTimer(operationDuration.WithLabelValues(
		s.config.NodeID, s.config.Region, "sync_region", "success"))
	defer timer.ObserveDuration()

	err := s.antiEntropyMgr.TriggerRegionSync(region)
	if err != nil {
		operationDuration.WithLabelValues(
			s.config.NodeID, s.config.Region, "sync_region", "error").Observe(0)
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"message": "Region synchronization triggered",
		"region":  region,
	})
}

func (s *Server) handleListConflicts(c *gin.Context) {
	conflicts := s.crdtStore.GetConflicts()
	c.JSON(http.StatusOK, gin.H{"conflicts": conflicts})
}

func (s *Server) handleResolveConflict(c *gin.Context) {
	conflictID := c.Param("id")
	
	var req struct {
		Strategy string `json:"strategy" binding:"required"`
	}

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	timer := prometheus.NewTimer(operationDuration.WithLabelValues(
		s.config.NodeID, s.config.Region, "resolve_conflict", "success"))
	defer timer.ObserveDuration()

	err := s.crdtStore.ResolveConflict(conflictID, req.Strategy)
	if err != nil {
		operationDuration.WithLabelValues(
			s.config.NodeID, s.config.Region, "resolve_conflict", "error").Observe(0)
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	conflictsResolvedTotal.WithLabelValues(
		s.config.NodeID, s.config.Region, "unknown", req.Strategy).Inc()

	c.JSON(http.StatusOK, gin.H{
		"message":     "Conflict resolved",
		"conflict_id": conflictID,
		"strategy":    req.Strategy,
	})
}

func (s *Server) handleGossipStatus(c *gin.Context) {
	status := s.gossipManager.GetStatus()
	c.JSON(http.StatusOK, status)
}

func (s *Server) handleVectorClocks(c *gin.Context) {
	clocks := s.crdtStore.GetVectorClocks()
	c.JSON(http.StatusOK, gin.H{"vector_clocks": clocks})
}

// CRDT Counter Handlers
func (s *Server) handleCreateCounter(c *gin.Context) {
	key := c.Param("key")
	
	var req struct {
		Type         string `json:"type" binding:"required"`
		InitialValue int64  `json:"initial_value"`
	}

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	timer := prometheus.NewTimer(operationDuration.WithLabelValues(
		s.config.NodeID, s.config.Region, "create_counter", "success"))
	defer timer.ObserveDuration()

	err := s.crdtStore.CreateCounter(key, req.Type, req.InitialValue)
	if err != nil {
		operationDuration.WithLabelValues(
			s.config.NodeID, s.config.Region, "create_counter", "error").Observe(0)
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	crdtOperationsTotal.WithLabelValues(
		s.config.NodeID, s.config.Region, req.Type, "create").Inc()

	c.JSON(http.StatusCreated, gin.H{
		"message": "Counter created successfully",
		"key":     key,
		"type":    req.Type,
	})
}

func (s *Server) handleGetCounter(c *gin.Context) {
	key := c.Param("key")
	consistency := c.DefaultQuery("consistency", "eventual")

	timer := prometheus.NewTimer(operationDuration.WithLabelValues(
		s.config.NodeID, s.config.Region, "get_counter", "success"))
	defer timer.ObserveDuration()

	value, metadata, err := s.crdtStore.GetCounter(key, consistency)
	if err != nil {
		operationDuration.WithLabelValues(
			s.config.NodeID, s.config.Region, "get_counter", "error").Observe(0)
		c.JSON(http.StatusNotFound, gin.H{"error": err.Error()})
		return
	}

	crdtOperationsTotal.WithLabelValues(
		s.config.NodeID, s.config.Region, metadata.Type, "get").Inc()

	c.JSON(http.StatusOK, gin.H{
		"key":      key,
		"value":    value,
		"metadata": metadata,
	})
}

func (s *Server) handleIncrementCounter(c *gin.Context) {
	key := c.Param("key")
	
	var req struct {
		Value int64 `json:"value"`
	}

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	if req.Value == 0 {
		req.Value = 1
	}

	timer := prometheus.NewTimer(operationDuration.WithLabelValues(
		s.config.NodeID, s.config.Region, "increment_counter", "success"))
	defer timer.ObserveDuration()

	newValue, err := s.crdtStore.IncrementCounter(key, req.Value)
	if err != nil {
		operationDuration.WithLabelValues(
			s.config.NodeID, s.config.Region, "increment_counter", "error").Observe(0)
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	crdtOperationsTotal.WithLabelValues(
		s.config.NodeID, s.config.Region, "counter", "increment").Inc()

	c.JSON(http.StatusOK, gin.H{
		"key":       key,
		"increment": req.Value,
		"new_value": newValue,
	})
}

func (s *Server) Shutdown(ctx context.Context) error {
	log.Println("Shutting down geo-replicated datastore node...")

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

	// Shutdown managers
	if s.antiEntropyMgr != nil {
		if err := s.antiEntropyMgr.Shutdown(); err != nil {
			log.Printf("Anti-entropy manager shutdown error: %v", err)
		}
	}

	if s.replicationMgr != nil {
		if err := s.replicationMgr.Shutdown(); err != nil {
			log.Printf("Replication manager shutdown error: %v", err)
		}
	}

	if s.gossipManager != nil {
		if err := s.gossipManager.Shutdown(); err != nil {
			log.Printf("Gossip manager shutdown error: %v", err)
		}
	}

	// Close storage
	if s.storage != nil {
		if err := s.storage.Close(); err != nil {
			log.Printf("Storage shutdown error: %v", err)
		}
	}

	close(s.shutdownComplete)
	log.Println("Geo-replicated datastore node shutdown completed")
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

package main

import (
	"context"
	"fmt"
	"log"
	"net"
	"net/http"
	"os"
	"os/signal"
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
	"./internal/raft"
	"./internal/storage"
	pb "./proto"
)

var (
	// Prometheus metrics
	raftTerm = prometheus.NewGaugeVec(
		prometheus.GaugeOpts{
			Name: "raft_term_current",
			Help: "Current Raft term",
		},
		[]string{"node_id"},
	)

	raftState = prometheus.NewGaugeVec(
		prometheus.GaugeOpts{
			Name: "raft_state",
			Help: "Current Raft state (0=Follower, 1=Candidate, 2=Leader)",
		},
		[]string{"node_id"},
	)

	raftLogEntries = prometheus.NewGaugeVec(
		prometheus.GaugeOpts{
			Name: "raft_log_entries_total",
			Help: "Total number of log entries",
		},
		[]string{"node_id"},
	)

	raftCommits = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "raft_commits_total",
			Help: "Total number of committed entries",
		},
		[]string{"node_id"},
	)

	raftElections = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "raft_leader_elections_total",
			Help: "Total number of leader elections",
		},
		[]string{"node_id"},
	)
)

func init() {
	prometheus.MustRegister(raftTerm, raftState, raftLogEntries, raftCommits, raftElections)
}

type Server struct {
	config     *config.Config
	raftNode   *raft.Node
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
	storage, err := storage.NewRocksDBStorage(cfg.DataDir, cfg.WALDir)
	if err != nil {
		return nil, fmt.Errorf("failed to initialize storage: %w", err)
	}

	// Initialize Raft node
	raftNode, err := raft.NewNode(cfg, storage)
	if err != nil {
		return nil, fmt.Errorf("failed to initialize Raft node: %w", err)
	}

	return &Server{
		config:   cfg,
		raftNode: raftNode,
		storage:  storage,
	}, nil
}

func (s *Server) Start() error {
	// Start Raft node
	if err := s.raftNode.Start(); err != nil {
		return fmt.Errorf("failed to start Raft node: %w", err)
	}

	// Start gRPC server
	go s.startGRPCServer()

	// Start HTTP server
	go s.startHTTPServer()

	// Start metrics collection
	go s.collectMetrics()

	log.Printf("Raft node %s started successfully", s.config.NodeID)
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

	// Stop Raft node
	s.raftNode.Stop()

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
	pb.RegisterRaftServiceServer(s.grpcServer, s.raftNode)

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
	}

	// Admin API endpoints
	admin := router.Group("/admin")
	{
		admin.GET("/status", s.getStatus)
		admin.GET("/nodes", s.getNodes)
		admin.POST("/nodes", s.addNode)
		admin.DELETE("/nodes/:id", s.removeNode)
		admin.POST("/snapshot", s.takeSnapshot)
		admin.POST("/compact", s.compactLog)
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
	ticker := time.NewTicker(5 * time.Second)
	defer ticker.Stop()

	for range ticker.C {
		state := s.raftNode.GetState()

		raftTerm.WithLabelValues(s.config.NodeID).Set(float64(state.Term))
		raftState.WithLabelValues(s.config.NodeID).Set(float64(state.State))
		raftLogEntries.WithLabelValues(s.config.NodeID).Set(float64(state.LogLength))

		if state.CommitIndex > 0 {
			raftCommits.WithLabelValues(s.config.NodeID).Add(1)
		}
	}
}

// HTTP Handlers

func (s *Server) healthCheck(c *gin.Context) {
	state := s.raftNode.GetState()
	c.JSON(http.StatusOK, gin.H{
		"status":    "healthy",
		"node_id":   s.config.NodeID,
		"state":     state.State.String(),
		"term":      state.Term,
		"leader_id": state.LeaderID,
	})
}

func (s *Server) getValue(c *gin.Context) {
	key := c.Param("key")

	value, err := s.raftNode.Get(key)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"key":   key,
		"value": value,
	})
}

func (s *Server) putValue(c *gin.Context) {
	key := c.Param("key")

	var req struct {
		Value string `json:"value" binding:"required"`
	}

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	if err := s.raftNode.Put(key, req.Value); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"key":   key,
		"value": req.Value,
	})
}

func (s *Server) deleteValue(c *gin.Context) {
	key := c.Param("key")

	if err := s.raftNode.Delete(key); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"key":     key,
		"deleted": true,
	})
}

func (s *Server) getStatus(c *gin.Context) {
	state := s.raftNode.GetState()
	nodes := s.raftNode.GetNodes()

	c.JSON(http.StatusOK, gin.H{
		"node_id":      s.config.NodeID,
		"state":        state.State.String(),
		"term":         state.Term,
		"leader_id":    state.LeaderID,
		"commit_index": state.CommitIndex,
		"log_length":   state.LogLength,
		"nodes":        nodes,
	})
}

func (s *Server) getNodes(c *gin.Context) {
	nodes := s.raftNode.GetNodes()
	c.JSON(http.StatusOK, gin.H{"nodes": nodes})
}

func (s *Server) addNode(c *gin.Context) {
	var req struct {
		ID      string `json:"id" binding:"required"`
		Address string `json:"address" binding:"required"`
	}

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	if err := s.raftNode.AddNode(req.ID, req.Address); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"message": "Node added successfully",
		"node_id": req.ID,
	})
}

func (s *Server) removeNode(c *gin.Context) {
	nodeID := c.Param("id")

	if err := s.raftNode.RemoveNode(nodeID); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"message": "Node removed successfully",
		"node_id": nodeID,
	})
}

func (s *Server) takeSnapshot(c *gin.Context) {
	if err := s.raftNode.TakeSnapshot(); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"message": "Snapshot taken successfully"})
}

func (s *Server) compactLog(c *gin.Context) {
	if err := s.raftNode.CompactLog(); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"message": "Log compacted successfully"})
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
			semconv.ServiceNameKey.String("raft-node"),
			semconv.ServiceVersionKey.String("1.0.0"),
		)),
	)

	otel.SetTracerProvider(tp)
	return nil
}

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

	"./internal/broker"
	"./internal/config"
	"./internal/log"
	"./internal/replication"
	"./internal/storage"
	pb "./proto"
)

// Prometheus metrics
var (
	messagesProduced = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "commitlog_messages_produced_total",
			Help: "Total number of messages produced",
		},
		[]string{"broker_id", "topic", "partition"},
	)

	messagesConsumed = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "commitlog_messages_consumed_total",
			Help: "Total number of messages consumed",
		},
		[]string{"broker_id", "topic", "partition", "consumer_group"},
	)

	partitionSize = prometheus.NewGaugeVec(
		prometheus.GaugeOpts{
			Name: "commitlog_partition_size_bytes",
			Help: "Size of partition in bytes",
		},
		[]string{"broker_id", "topic", "partition"},
	)

	replicationLag = prometheus.NewGaugeVec(
		prometheus.GaugeOpts{
			Name: "commitlog_replication_lag_ms",
			Help: "Replication lag in milliseconds",
		},
		[]string{"broker_id", "topic", "partition", "follower"},
	)

	consumerLag = prometheus.NewGaugeVec(
		prometheus.GaugeOpts{
			Name: "commitlog_consumer_lag",
			Help: "Consumer lag (messages behind)",
		},
		[]string{"broker_id", "topic", "partition", "consumer_group"},
	)

	operationDuration = prometheus.NewHistogramVec(
		prometheus.HistogramOpts{
			Name:    "commitlog_operation_duration_seconds",
			Help:    "Duration of commit log operations",
			Buckets: prometheus.DefBuckets,
		},
		[]string{"broker_id", "operation", "status"},
	)
)

func init() {
	prometheus.MustRegister(messagesProduced)
	prometheus.MustRegister(messagesConsumed)
	prometheus.MustRegister(partitionSize)
	prometheus.MustRegister(replicationLag)
	prometheus.MustRegister(consumerLag)
	prometheus.MustRegister(operationDuration)
}

type Server struct {
	config           *config.Config
	broker           *broker.Broker
	storage          storage.Storage
	replicationMgr   *replication.Manager
	httpServer       *http.Server
	grpcServer       *grpc.Server
	shutdownComplete chan struct{}
}

func NewServer(cfg *config.Config) (*Server, error) {
	// Initialize storage
	storage, err := storage.NewSegmentedStorage(cfg.DataDir, cfg.LogSegmentSize)
	if err != nil {
		return nil, fmt.Errorf("failed to initialize storage: %w", err)
	}

	// Initialize replication manager
	replicationMgr, err := replication.NewManager(cfg, storage)
	if err != nil {
		return nil, fmt.Errorf("failed to initialize replication manager: %w", err)
	}

	// Initialize broker
	broker, err := broker.NewBroker(cfg, storage, replicationMgr)
	if err != nil {
		return nil, fmt.Errorf("failed to initialize broker: %w", err)
	}

	return &Server{
		config:           cfg,
		broker:           broker,
		storage:          storage,
		replicationMgr:   replicationMgr,
		shutdownComplete: make(chan struct{}),
	}, nil
}

func (s *Server) Start() error {
	// Start replication manager
	if err := s.replicationMgr.Start(); err != nil {
		return fmt.Errorf("failed to start replication manager: %w", err)
	}

	// Start broker
	if err := s.broker.Start(); err != nil {
		return fmt.Errorf("failed to start broker: %w", err)
	}

	// Start gRPC server
	go s.startGRPCServer()

	// Start HTTP server
	go s.startHTTPServer()

	// Start metrics collection
	go s.startMetricsCollection()

	log.Printf("Commit log broker %d started successfully", s.config.BrokerID)
	return nil
}

func (s *Server) startGRPCServer() {
	lis, err := net.Listen("tcp", fmt.Sprintf(":%d", s.config.GRPCPort))
	if err != nil {
		log.Fatalf("Failed to listen on gRPC port: %v", err)
	}

	s.grpcServer = grpc.NewServer()
	pb.RegisterCommitLogServiceServer(s.grpcServer, s.broker)

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
		admin.GET("/topics", s.handleListTopics)
		admin.POST("/topics", s.handleCreateTopic)
		admin.GET("/topics/:topic", s.handleTopicDetails)
		admin.DELETE("/topics/:topic", s.handleDeleteTopic)
		admin.POST("/topics/:topic/compact", s.handleCompactTopic)
		admin.GET("/consumer-groups", s.handleListConsumerGroups)
		admin.GET("/consumer-groups/:group", s.handleConsumerGroupDetails)
	}

	// Producer endpoints
	producer := router.Group("/produce")
	{
		producer.POST("/:topic", s.handleProduce)
		producer.POST("/:topic/batch", s.handleProduceBatch)
		producer.POST("/:topic/transaction", s.handleProduceTransaction)
	}

	// Consumer endpoints
	consumer := router.Group("/consume")
	{
		consumer.GET("/:topic", s.handleConsume)
		consumer.POST("/consumers/:group", s.handleJoinConsumerGroup)
		consumer.DELETE("/consumers/:group/:consumer", s.handleLeaveConsumerGroup)
		consumer.POST("/consumers/:group/:consumer/offsets", s.handleCommitOffsets)
		consumer.GET("/consumers/:group/:consumer/offsets", s.handleGetOffsets)
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
	brokerID := strconv.Itoa(s.config.BrokerID)

	// Collect partition size metrics
	topics := s.broker.GetTopics()
	for topicName, topic := range topics {
		for partitionID, partition := range topic.GetPartitions() {
			size := partition.GetSize()
			partitionSize.WithLabelValues(brokerID, topicName, strconv.Itoa(partitionID)).Set(float64(size))

			// Collect replication lag for followers
			if !partition.IsLeader() {
				lag := partition.GetReplicationLag()
				replicationLag.WithLabelValues(brokerID, topicName, strconv.Itoa(partitionID), "follower").Set(float64(lag))
			}
		}
	}

	// Collect consumer lag metrics
	consumerGroups := s.broker.GetConsumerGroups()
	for groupName, group := range consumerGroups {
		for topicName, partitionOffsets := range group.GetOffsets() {
			for partitionID, offset := range partitionOffsets {
				highWaterMark := s.broker.GetHighWaterMark(topicName, partitionID)
				lag := highWaterMark - offset
				consumerLag.WithLabelValues(brokerID, topicName, strconv.Itoa(partitionID), groupName).Set(float64(lag))
			}
		}
	}
}

// HTTP Handlers
func (s *Server) handleHealth(c *gin.Context) {
	status := "healthy"
	if !s.broker.IsHealthy() {
		status = "unhealthy"
		c.JSON(http.StatusServiceUnavailable, gin.H{"status": status})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"status":    status,
		"broker_id": s.config.BrokerID,
		"uptime":    time.Since(s.broker.GetStartTime()).String(),
	})
}

func (s *Server) handleStatus(c *gin.Context) {
	status := s.broker.GetStatus()
	c.JSON(http.StatusOK, status)
}

func (s *Server) handleListTopics(c *gin.Context) {
	topics := s.broker.ListTopics()
	c.JSON(http.StatusOK, gin.H{"topics": topics})
}

func (s *Server) handleCreateTopic(c *gin.Context) {
	var req struct {
		Name              string `json:"name" binding:"required"`
		Partitions        int    `json:"partitions" binding:"required,min=1"`
		ReplicationFactor int    `json:"replication_factor" binding:"required,min=1"`
		Config            map[string]string `json:"config"`
	}

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	timer := prometheus.NewTimer(operationDuration.WithLabelValues(
		strconv.Itoa(s.config.BrokerID), "create_topic", "success"))
	defer timer.ObserveDuration()

	err := s.broker.CreateTopic(req.Name, req.Partitions, req.ReplicationFactor, req.Config)
	if err != nil {
		operationDuration.WithLabelValues(
			strconv.Itoa(s.config.BrokerID), "create_topic", "error").Observe(0)
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusCreated, gin.H{
		"message": "Topic created successfully",
		"topic":   req.Name,
	})
}

func (s *Server) handleTopicDetails(c *gin.Context) {
	topicName := c.Param("topic")
	details, err := s.broker.GetTopicDetails(topicName)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, details)
}

func (s *Server) handleDeleteTopic(c *gin.Context) {
	topicName := c.Param("topic")
	
	timer := prometheus.NewTimer(operationDuration.WithLabelValues(
		strconv.Itoa(s.config.BrokerID), "delete_topic", "success"))
	defer timer.ObserveDuration()

	err := s.broker.DeleteTopic(topicName)
	if err != nil {
		operationDuration.WithLabelValues(
			strconv.Itoa(s.config.BrokerID), "delete_topic", "error").Observe(0)
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"message": "Topic deleted successfully"})
}

func (s *Server) handleCompactTopic(c *gin.Context) {
	topicName := c.Param("topic")
	
	timer := prometheus.NewTimer(operationDuration.WithLabelValues(
		strconv.Itoa(s.config.BrokerID), "compact_topic", "success"))
	defer timer.ObserveDuration()

	err := s.broker.CompactTopic(topicName)
	if err != nil {
		operationDuration.WithLabelValues(
			strconv.Itoa(s.config.BrokerID), "compact_topic", "error").Observe(0)
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"message": "Topic compaction triggered"})
}

func (s *Server) handleProduce(c *gin.Context) {
	topicName := c.Param("topic")
	
	var req struct {
		Key       string `json:"key"`
		Value     string `json:"value" binding:"required"`
		Partition *int   `json:"partition"`
		Headers   map[string]string `json:"headers"`
	}

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	timer := prometheus.NewTimer(operationDuration.WithLabelValues(
		strconv.Itoa(s.config.BrokerID), "produce", "success"))
	defer timer.ObserveDuration()

	result, err := s.broker.Produce(topicName, req.Key, req.Value, req.Partition, req.Headers)
	if err != nil {
		operationDuration.WithLabelValues(
			strconv.Itoa(s.config.BrokerID), "produce", "error").Observe(0)
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	// Update metrics
	messagesProduced.WithLabelValues(
		strconv.Itoa(s.config.BrokerID), 
		topicName, 
		strconv.Itoa(result.Partition),
	).Inc()

	c.JSON(http.StatusOK, result)
}

func (s *Server) handleConsume(c *gin.Context) {
	topicName := c.Param("topic")
	consumerGroup := c.Query("group")
	consumerID := c.Query("consumer")
	maxMessages := 100

	if maxStr := c.Query("max_messages"); maxStr != "" {
		if max, err := strconv.Atoi(maxStr); err == nil && max > 0 {
			maxMessages = max
		}
	}

	timer := prometheus.NewTimer(operationDuration.WithLabelValues(
		strconv.Itoa(s.config.BrokerID), "consume", "success"))
	defer timer.ObserveDuration()

	messages, err := s.broker.Consume(topicName, consumerGroup, consumerID, maxMessages)
	if err != nil {
		operationDuration.WithLabelValues(
			strconv.Itoa(s.config.BrokerID), "consume", "error").Observe(0)
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	// Update metrics
	for _, msg := range messages {
		messagesConsumed.WithLabelValues(
			strconv.Itoa(s.config.BrokerID),
			topicName,
			strconv.Itoa(msg.Partition),
			consumerGroup,
		).Inc()
	}

	c.JSON(http.StatusOK, gin.H{"messages": messages})
}

func (s *Server) Shutdown(ctx context.Context) error {
	log.Println("Shutting down commit log broker...")

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

	// Shutdown broker
	if s.broker != nil {
		if err := s.broker.Shutdown(); err != nil {
			log.Printf("Broker shutdown error: %v", err)
		}
	}

	// Shutdown replication manager
	if s.replicationMgr != nil {
		if err := s.replicationMgr.Shutdown(); err != nil {
			log.Printf("Replication manager shutdown error: %v", err)
		}
	}

	// Close storage
	if s.storage != nil {
		if err := s.storage.Close(); err != nil {
			log.Printf("Storage shutdown error: %v", err)
		}
	}

	close(s.shutdownComplete)
	log.Println("Commit log broker shutdown completed")
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

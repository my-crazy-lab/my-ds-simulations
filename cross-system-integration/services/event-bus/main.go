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
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	"github.com/sirupsen/logrus"
	"github.com/cross-system-integration/shared/events"
	"github.com/cross-system-integration/services/event-bus/internal/config"
	"github.com/cross-system-integration/services/event-bus/internal/handlers"
	"github.com/cross-system-integration/services/event-bus/internal/infrastructure"
	"github.com/cross-system-integration/services/event-bus/internal/router"
	"github.com/cross-system-integration/services/event-bus/internal/services"
)

var (
	// Prometheus metrics
	eventsReceived = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "event_bus_events_received_total",
			Help: "Total number of events received",
		},
		[]string{"source", "type", "priority"},
	)

	eventsRouted = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "event_bus_events_routed_total",
			Help: "Total number of events routed",
		},
		[]string{"source", "type", "destination"},
	)

	eventProcessingDuration = prometheus.NewHistogramVec(
		prometheus.HistogramOpts{
			Name:    "event_bus_processing_duration_seconds",
			Help:    "Event processing duration in seconds",
			Buckets: prometheus.DefBuckets,
		},
		[]string{"source", "type"},
	)

	activeSubscriptions = prometheus.NewGaugeVec(
		prometheus.GaugeOpts{
			Name: "event_bus_active_subscriptions",
			Help: "Number of active event subscriptions",
		},
		[]string{"source", "type"},
	)

	eventQueueSize = prometheus.NewGaugeVec(
		prometheus.GaugeOpts{
			Name: "event_bus_queue_size",
			Help: "Current size of event queues",
		},
		[]string{"queue_name"},
	)
)

func init() {
	// Register Prometheus metrics
	prometheus.MustRegister(eventsReceived)
	prometheus.MustRegister(eventsRouted)
	prometheus.MustRegister(eventProcessingDuration)
	prometheus.MustRegister(activeSubscriptions)
	prometheus.MustRegister(eventQueueSize)
}

func main() {
	// Load configuration
	cfg, err := config.Load()
	if err != nil {
		log.Fatalf("Failed to load configuration: %v", err)
	}

	// Setup logger
	logger := logrus.New()
	logger.SetLevel(logrus.Level(cfg.LogLevel))
	logger.SetFormatter(&logrus.JSONFormatter{})

	logger.WithFields(logrus.Fields{
		"service": "event-bus",
		"version": cfg.Version,
		"port":    cfg.Port,
	}).Info("Starting Event Bus service")

	// Initialize infrastructure
	kafkaProducer, err := infrastructure.NewKafkaProducer(cfg.Kafka)
	if err != nil {
		logger.Fatalf("Failed to create Kafka producer: %v", err)
	}
	defer kafkaProducer.Close()

	kafkaConsumer, err := infrastructure.NewKafkaConsumer(cfg.Kafka)
	if err != nil {
		logger.Fatalf("Failed to create Kafka consumer: %v", err)
	}
	defer kafkaConsumer.Close()

	redisClient, err := infrastructure.NewRedisClient(cfg.Redis)
	if err != nil {
		logger.Fatalf("Failed to create Redis client: %v", err)
	}
	defer redisClient.Close()

	// Initialize services
	eventValidator := services.NewEventValidator(logger)
	eventTransformer := services.NewEventTransformer(logger)
	eventRouter := router.NewEventRouter(kafkaProducer, redisClient, logger)
	subscriptionManager := services.NewSubscriptionManager(redisClient, logger)

	// Initialize event bus service
	eventBusService := services.NewEventBusService(
		eventValidator,
		eventTransformer,
		eventRouter,
		subscriptionManager,
		logger,
	)

	// Start background workers
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Start event consumer
	go func() {
		if err := eventBusService.StartEventConsumer(ctx, kafkaConsumer); err != nil {
			logger.Errorf("Event consumer error: %v", err)
		}
	}()

	// Start subscription manager
	go func() {
		if err := subscriptionManager.Start(ctx); err != nil {
			logger.Errorf("Subscription manager error: %v", err)
		}
	}()

	// Start metrics collector
	go func() {
		ticker := time.NewTicker(30 * time.Second)
		defer ticker.Stop()

		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				updateMetrics(eventBusService, subscriptionManager)
			}
		}
	}()

	// Setup HTTP server
	router := gin.New()
	router.Use(gin.Recovery())
	router.Use(loggingMiddleware(logger))
	router.Use(metricsMiddleware())

	// Health check endpoint
	router.GET("/health", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{
			"status":    "healthy",
			"service":   "event-bus",
			"version":   cfg.Version,
			"timestamp": time.Now().ISO8601(),
		})
	})

	// Metrics endpoint
	router.GET("/metrics", gin.WrapH(promhttp.Handler()))

	// Initialize handlers
	eventHandler := handlers.NewEventHandler(eventBusService, logger)
	subscriptionHandler := handlers.NewSubscriptionHandler(subscriptionManager, logger)

	// API routes
	v1 := router.Group("/api/v1")
	{
		// Event management
		v1.POST("/events", eventHandler.PublishEvent)
		v1.GET("/events", eventHandler.QueryEvents)
		v1.GET("/events/:id", eventHandler.GetEvent)

		// Subscription management
		v1.POST("/subscriptions", subscriptionHandler.CreateSubscription)
		v1.GET("/subscriptions", subscriptionHandler.ListSubscriptions)
		v1.GET("/subscriptions/:id", subscriptionHandler.GetSubscription)
		v1.PUT("/subscriptions/:id", subscriptionHandler.UpdateSubscription)
		v1.DELETE("/subscriptions/:id", subscriptionHandler.DeleteSubscription)

		// Event routing
		v1.GET("/routing/rules", eventHandler.GetRoutingRules)
		v1.POST("/routing/rules", eventHandler.CreateRoutingRule)
		v1.PUT("/routing/rules/:id", eventHandler.UpdateRoutingRule)
		v1.DELETE("/routing/rules/:id", eventHandler.DeleteRoutingRule)

		// System status
		v1.GET("/status", eventHandler.GetSystemStatus)
		v1.GET("/stats", eventHandler.GetEventStats)
	}

	// Start HTTP server
	server := &http.Server{
		Addr:    fmt.Sprintf(":%d", cfg.Port),
		Handler: router,
	}

	// Graceful shutdown
	go func() {
		sigChan := make(chan os.Signal, 1)
		signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)
		<-sigChan

		logger.Info("Shutting down Event Bus service...")

		// Cancel context to stop background workers
		cancel()

		// Shutdown HTTP server
		ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
		defer cancel()

		if err := server.Shutdown(ctx); err != nil {
			logger.Errorf("Server shutdown error: %v", err)
		}
	}()

	logger.Infof("Event Bus service listening on port %d", cfg.Port)
	if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		logger.Fatalf("Server error: %v", err)
	}

	logger.Info("Event Bus service stopped")
}

// loggingMiddleware adds request logging
func loggingMiddleware(logger *logrus.Logger) gin.HandlerFunc {
	return func(c *gin.Context) {
		start := time.Now()
		path := c.Request.URL.Path
		raw := c.Request.URL.RawQuery

		// Process request
		c.Next()

		// Log request
		latency := time.Since(start)
		clientIP := c.ClientIP()
		method := c.Request.Method
		statusCode := c.Writer.Status()

		if raw != "" {
			path = path + "?" + raw
		}

		logger.WithFields(logrus.Fields{
			"status_code": statusCode,
			"latency":     latency,
			"client_ip":   clientIP,
			"method":      method,
			"path":        path,
		}).Info("HTTP request")
	}
}

// metricsMiddleware adds metrics collection
func metricsMiddleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		start := time.Now()

		// Process request
		c.Next()

		// Record metrics
		duration := time.Since(start).Seconds()
		path := c.FullPath()
		method := c.Request.Method
		status := fmt.Sprintf("%d", c.Writer.Status())

		// Record HTTP metrics (if needed)
		// httpRequestDuration.WithLabelValues(method, path, status).Observe(duration)
		_ = duration
		_ = path
		_ = method
		_ = status
	}
}

// updateMetrics updates Prometheus metrics
func updateMetrics(eventBusService *services.EventBusService, subscriptionManager *services.SubscriptionManager) {
	// Update queue sizes
	queueSizes := eventBusService.GetQueueSizes()
	for queueName, size := range queueSizes {
		eventQueueSize.WithLabelValues(queueName).Set(float64(size))
	}

	// Update subscription counts
	subscriptionCounts := subscriptionManager.GetSubscriptionCounts()
	for key, count := range subscriptionCounts {
		// Parse key to extract source and type
		var source, eventType string
		if err := json.Unmarshal([]byte(key), &struct {
			Source string `json:"source"`
			Type   string `json:"type"`
		}{Source: source, Type: eventType}); err == nil {
			activeSubscriptions.WithLabelValues(source, eventType).Set(float64(count))
		}
	}
}

// recordEventMetrics records event-related metrics
func recordEventMetrics(event *events.UnifiedEvent, action string) {
	source := string(event.Source)
	eventType := string(event.Type)
	priority := string(event.Metadata.Priority)

	switch action {
	case "received":
		eventsReceived.WithLabelValues(source, eventType, priority).Inc()
	case "routed":
		// This would need destination info
		eventsRouted.WithLabelValues(source, eventType, "unknown").Inc()
	}
}

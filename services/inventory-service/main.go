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
	"github.com/microservices-saga/services/inventory-service/internal/config"
	"github.com/microservices-saga/services/inventory-service/internal/handlers"
	"github.com/microservices-saga/services/inventory-service/internal/infrastructure"
	"github.com/microservices-saga/services/inventory-service/internal/repository"
	"github.com/microservices-saga/services/inventory-service/internal/services"
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

	// Initialize database
	db, err := infrastructure.NewDatabase(cfg.DatabaseURL)
	if err != nil {
		logger.Fatalf("Failed to connect to database: %v", err)
	}
	defer db.Close()

	// Initialize Kafka
	kafkaProducer, err := infrastructure.NewKafkaProducer(cfg.KafkaBrokers)
	if err != nil {
		logger.Fatalf("Failed to create Kafka producer: %v", err)
	}
	defer kafkaProducer.Close()

	kafkaConsumer, err := infrastructure.NewKafkaConsumer(cfg.KafkaBrokers, "inventory-service-group")
	if err != nil {
		logger.Fatalf("Failed to create Kafka consumer: %v", err)
	}
	defer kafkaConsumer.Close()

	// Initialize repositories
	inventoryRepo := repository.NewInventoryRepository(db)
	outboxRepo := repository.NewOutboxRepository(db)

	// Initialize services
	eventService := services.NewEventService(kafkaProducer, logger)
	inventoryService := services.NewInventoryService(inventoryRepo, outboxRepo, eventService, metrics, logger)

	// Start background workers
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Start event consumer
	go func() {
		if err := inventoryService.StartEventConsumer(ctx, kafkaConsumer); err != nil {
			logger.Errorf("Event consumer error: %v", err)
		}
	}()

	// Start outbox processor
	go inventoryService.StartOutboxProcessor(ctx)

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
	inventoryHandler := handlers.NewInventoryHandler(inventoryService, logger)

	// API routes
	v1 := router.Group("/api/v1")
	{
		v1.GET("/inventory", inventoryHandler.ListItems)
		v1.GET("/inventory/:sku", inventoryHandler.GetItem)
		v1.POST("/inventory", inventoryHandler.CreateItem)
		v1.PUT("/inventory/:sku", inventoryHandler.UpdateItem)
		v1.DELETE("/inventory/:sku", inventoryHandler.DeleteItem)
		
		// Reservation endpoints
		v1.POST("/inventory/:sku/reserve", inventoryHandler.ReserveItem)
		v1.POST("/inventory/:sku/release", inventoryHandler.ReleaseReservation)
		v1.GET("/reservations", inventoryHandler.ListReservations)
		v1.GET("/reservations/:id", inventoryHandler.GetReservation)
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

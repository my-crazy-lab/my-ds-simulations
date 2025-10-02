package main

import (
	"context"
	"fmt"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	"github.com/sirupsen/logrus"
	"github.com/spf13/viper"

	"outbox-publisher/internal/config"
	"outbox-publisher/internal/domain"
	"outbox-publisher/internal/infrastructure/database"
	"outbox-publisher/internal/infrastructure/messaging"
	"outbox-publisher/internal/infrastructure/monitoring"
	"outbox-publisher/internal/services"
)

var (
	logger = logrus.New()
)

func init() {
	// Configure logging
	logger.SetFormatter(&logrus.JSONFormatter{})
	logger.SetLevel(logrus.InfoLevel)
	
	// Load configuration
	viper.SetConfigName("config")
	viper.SetConfigType("yaml")
	viper.AddConfigPath("./config")
	viper.AddConfigPath(".")
	viper.AutomaticEnv()
	
	if err := viper.ReadInConfig(); err != nil {
		logger.WithError(err).Warn("Failed to read config file, using defaults")
	}
}

func main() {
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Load configuration
	cfg, err := config.Load()
	if err != nil {
		logger.WithError(err).Fatal("Failed to load configuration")
	}

	// Initialize monitoring
	monitoring.InitMetrics()
	monitoring.InitTracing(cfg.Tracing.ServiceName, cfg.Tracing.JaegerEndpoint)

	// Initialize database connections
	pgPool, err := database.NewPostgresPool(cfg.Database.PostgresURL)
	if err != nil {
		logger.WithError(err).Fatal("Failed to connect to PostgreSQL")
	}
	defer pgPool.Close()

	mongoClient, err := database.NewMongoClient(cfg.Database.MongoURL)
	if err != nil {
		logger.WithError(err).Fatal("Failed to connect to MongoDB")
	}
	defer mongoClient.Disconnect(ctx)

	redisClient, err := database.NewRedisClient(cfg.Database.RedisURL)
	if err != nil {
		logger.WithError(err).Fatal("Failed to connect to Redis")
	}
	defer redisClient.Close()

	// Initialize Kafka producer
	kafkaProducer, err := messaging.NewKafkaProducer(cfg.Kafka.Brokers)
	if err != nil {
		logger.WithError(err).Fatal("Failed to create Kafka producer")
	}
	defer kafkaProducer.Close()

	// Initialize repositories
	postgresRepo := database.NewPostgresOutboxRepository(pgPool)
	mongoRepo := database.NewMongoOutboxRepository(mongoClient)

	// Initialize outbox publisher service
	outboxPublisher := services.NewOutboxPublisher(
		postgresRepo,
		mongoRepo,
		redisClient,
		kafkaProducer,
		cfg.OutboxPublisher,
		logger,
	)

	// Start outbox publisher
	go func() {
		if err := outboxPublisher.Start(ctx); err != nil {
			logger.WithError(err).Error("Outbox publisher stopped with error")
		}
	}()

	// Setup HTTP server
	router := setupRouter(outboxPublisher)
	server := &http.Server{
		Addr:    fmt.Sprintf(":%d", cfg.Server.Port),
		Handler: router,
	}

	// Start HTTP server
	go func() {
		logger.WithField("port", cfg.Server.Port).Info("Starting HTTP server")
		if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			logger.WithError(err).Fatal("Failed to start HTTP server")
		}
	}()

	// Wait for interrupt signal
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit

	logger.Info("Shutting down server...")

	// Graceful shutdown
	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer shutdownCancel()

	// Stop outbox publisher
	cancel()

	// Shutdown HTTP server
	if err := server.Shutdown(shutdownCtx); err != nil {
		logger.WithError(err).Error("Server forced to shutdown")
	}

	logger.Info("Server exited")
}

func setupRouter(outboxPublisher *services.OutboxPublisher) *gin.Engine {
	gin.SetMode(gin.ReleaseMode)
	router := gin.New()

	// Middleware
	router.Use(gin.Logger())
	router.Use(gin.Recovery())
	router.Use(corsMiddleware())

	// Health check endpoint
	router.GET("/health", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{
			"status":    "healthy",
			"service":   "outbox-publisher",
			"timestamp": time.Now().UTC(),
		})
	})

	// Readiness check endpoint
	router.GET("/ready", func(c *gin.Context) {
		if outboxPublisher.IsReady() {
			c.JSON(http.StatusOK, gin.H{
				"status": "ready",
			})
		} else {
			c.JSON(http.StatusServiceUnavailable, gin.H{
				"status": "not ready",
			})
		}
	})

	// Metrics endpoint
	router.GET("/metrics", gin.WrapH(promhttp.Handler()))

	// API endpoints
	api := router.Group("/api/v1")
	{
		// Get outbox statistics
		api.GET("/stats", func(c *gin.Context) {
			stats := outboxPublisher.GetStats()
			c.JSON(http.StatusOK, stats)
		})

		// Get pending events count
		api.GET("/pending", func(c *gin.Context) {
			count, err := outboxPublisher.GetPendingEventsCount(c.Request.Context())
			if err != nil {
				c.JSON(http.StatusInternalServerError, gin.H{
					"error": err.Error(),
				})
				return
			}
			c.JSON(http.StatusOK, gin.H{
				"pending_events": count,
			})
		})

		// Get failed events count
		api.GET("/failed", func(c *gin.Context) {
			count, err := outboxPublisher.GetFailedEventsCount(c.Request.Context())
			if err != nil {
				c.JSON(http.StatusInternalServerError, gin.H{
					"error": err.Error(),
				})
				return
			}
			c.JSON(http.StatusOK, gin.H{
				"failed_events": count,
			})
		})

		// Retry failed events
		api.POST("/retry-failed", func(c *gin.Context) {
			count, err := outboxPublisher.RetryFailedEvents(c.Request.Context())
			if err != nil {
				c.JSON(http.StatusInternalServerError, gin.H{
					"error": err.Error(),
				})
				return
			}
			c.JSON(http.StatusOK, gin.H{
				"retried_events": count,
			})
		})

		// Cleanup processed events
		api.POST("/cleanup", func(c *gin.Context) {
			var request struct {
				OlderThanHours int `json:"older_than_hours" binding:"required,min=1"`
			}
			
			if err := c.ShouldBindJSON(&request); err != nil {
				c.JSON(http.StatusBadRequest, gin.H{
					"error": err.Error(),
				})
				return
			}

			count, err := outboxPublisher.CleanupProcessedEvents(c.Request.Context(), request.OlderThanHours)
			if err != nil {
				c.JSON(http.StatusInternalServerError, gin.H{
					"error": err.Error(),
				})
				return
			}
			c.JSON(http.StatusOK, gin.H{
				"cleaned_events": count,
			})
		})

		// Manual event publishing (for testing)
		api.POST("/publish", func(c *gin.Context) {
			var event domain.OutboxEvent
			if err := c.ShouldBindJSON(&event); err != nil {
				c.JSON(http.StatusBadRequest, gin.H{
					"error": err.Error(),
				})
				return
			}

			if err := outboxPublisher.PublishEvent(c.Request.Context(), &event); err != nil {
				c.JSON(http.StatusInternalServerError, gin.H{
					"error": err.Error(),
				})
				return
			}

			c.JSON(http.StatusOK, gin.H{
				"message": "Event published successfully",
				"event_id": event.ID,
			})
		})
	}

	return router
}

func corsMiddleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		c.Header("Access-Control-Allow-Origin", "*")
		c.Header("Access-Control-Allow-Credentials", "true")
		c.Header("Access-Control-Allow-Headers", "Content-Type, Content-Length, Accept-Encoding, X-CSRF-Token, Authorization, accept, origin, Cache-Control, X-Requested-With")
		c.Header("Access-Control-Allow-Methods", "POST, OPTIONS, GET, PUT, DELETE")

		if c.Request.Method == "OPTIONS" {
			c.AbortWithStatus(204)
			return
		}

		c.Next()
	}
}

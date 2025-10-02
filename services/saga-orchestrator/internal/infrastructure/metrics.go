package infrastructure

import (
	"time"

	"github.com/gin-gonic/gin"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
	"github.com/sirupsen/logrus"
)

// Metrics holds all Prometheus metrics for the saga orchestrator
type Metrics struct {
	// Saga metrics
	SagasCreated     *prometheus.CounterVec
	SagasCompleted   *prometheus.CounterVec
	SagasFailed      *prometheus.CounterVec
	SagasCompensated *prometheus.CounterVec
	SagasRetried     *prometheus.CounterVec
	SagaDuration     *prometheus.HistogramVec

	// Step metrics
	SagaStepsExecuted *prometheus.CounterVec
	SagaStepsCompleted *prometheus.CounterVec
	SagaStepsFailed   *prometheus.CounterVec
	SagaStepDuration  *prometheus.HistogramVec

	// Outbox metrics
	OutboxEventsCreated   *prometheus.CounterVec
	OutboxEventsProcessed *prometheus.CounterVec
	OutboxEventsFailed    *prometheus.CounterVec
	OutboxProcessingLag   *prometheus.GaugeVec

	// HTTP metrics
	HTTPRequestsTotal    *prometheus.CounterVec
	HTTPRequestDuration  *prometheus.HistogramVec
	HTTPRequestsInFlight *prometheus.GaugeVec

	// Database metrics
	DatabaseConnections     *prometheus.GaugeVec
	DatabaseQueryDuration   *prometheus.HistogramVec
	DatabaseQueriesTotal    *prometheus.CounterVec

	// Kafka metrics
	KafkaMessagesProduced *prometheus.CounterVec
	KafkaMessagesConsumed *prometheus.CounterVec
	KafkaProduceErrors    *prometheus.CounterVec
	KafkaConsumeErrors    *prometheus.CounterVec
}

// NewMetrics creates and registers all Prometheus metrics
func NewMetrics() *Metrics {
	return &Metrics{
		// Saga metrics
		SagasCreated: promauto.NewCounterVec(
			prometheus.CounterOpts{
				Name: "saga_created_total",
				Help: "Total number of sagas created",
			},
			[]string{"saga_type"},
		),
		SagasCompleted: promauto.NewCounterVec(
			prometheus.CounterOpts{
				Name: "saga_completed_total",
				Help: "Total number of sagas completed successfully",
			},
			[]string{"saga_type"},
		),
		SagasFailed: promauto.NewCounterVec(
			prometheus.CounterOpts{
				Name: "saga_failed_total",
				Help: "Total number of sagas that failed",
			},
			[]string{"saga_type"},
		),
		SagasCompensated: promauto.NewCounterVec(
			prometheus.CounterOpts{
				Name: "saga_compensated_total",
				Help: "Total number of sagas that were compensated",
			},
			[]string{"saga_type"},
		),
		SagasRetried: promauto.NewCounterVec(
			prometheus.CounterOpts{
				Name: "saga_retried_total",
				Help: "Total number of saga retries",
			},
			[]string{"saga_type"},
		),
		SagaDuration: promauto.NewHistogramVec(
			prometheus.HistogramOpts{
				Name:    "saga_duration_seconds",
				Help:    "Duration of saga execution in seconds",
				Buckets: prometheus.ExponentialBuckets(0.1, 2, 10),
			},
			[]string{"saga_type"},
		),

		// Step metrics
		SagaStepsExecuted: promauto.NewCounterVec(
			prometheus.CounterOpts{
				Name: "saga_steps_executed_total",
				Help: "Total number of saga steps executed",
			},
			[]string{"saga_type", "step_name"},
		),
		SagaStepsCompleted: promauto.NewCounterVec(
			prometheus.CounterOpts{
				Name: "saga_steps_completed_total",
				Help: "Total number of saga steps completed successfully",
			},
			[]string{"saga_type", "step_name"},
		),
		SagaStepsFailed: promauto.NewCounterVec(
			prometheus.CounterOpts{
				Name: "saga_steps_failed_total",
				Help: "Total number of saga steps that failed",
			},
			[]string{"saga_type", "step_name"},
		),
		SagaStepDuration: promauto.NewHistogramVec(
			prometheus.HistogramOpts{
				Name:    "saga_step_duration_seconds",
				Help:    "Duration of saga step execution in seconds",
				Buckets: prometheus.ExponentialBuckets(0.01, 2, 10),
			},
			[]string{"saga_type", "step_name"},
		),

		// Outbox metrics
		OutboxEventsCreated: promauto.NewCounterVec(
			prometheus.CounterOpts{
				Name: "outbox_events_created_total",
				Help: "Total number of outbox events created",
			},
			[]string{"event_type"},
		),
		OutboxEventsProcessed: promauto.NewCounterVec(
			prometheus.CounterOpts{
				Name: "outbox_events_processed_total",
				Help: "Total number of outbox events processed",
			},
			[]string{"event_type"},
		),
		OutboxEventsFailed: promauto.NewCounterVec(
			prometheus.CounterOpts{
				Name: "outbox_events_failed_total",
				Help: "Total number of outbox events that failed processing",
			},
			[]string{"event_type"},
		),
		OutboxProcessingLag: promauto.NewGaugeVec(
			prometheus.GaugeOpts{
				Name: "outbox_processing_lag_seconds",
				Help: "Lag in outbox event processing in seconds",
			},
			[]string{"event_type"},
		),

		// HTTP metrics
		HTTPRequestsTotal: promauto.NewCounterVec(
			prometheus.CounterOpts{
				Name: "http_requests_total",
				Help: "Total number of HTTP requests",
			},
			[]string{"method", "path", "status"},
		),
		HTTPRequestDuration: promauto.NewHistogramVec(
			prometheus.HistogramOpts{
				Name:    "http_request_duration_seconds",
				Help:    "Duration of HTTP requests in seconds",
				Buckets: prometheus.DefBuckets,
			},
			[]string{"method", "path"},
		),
		HTTPRequestsInFlight: promauto.NewGaugeVec(
			prometheus.GaugeOpts{
				Name: "http_requests_in_flight",
				Help: "Number of HTTP requests currently being processed",
			},
			[]string{"method", "path"},
		),

		// Database metrics
		DatabaseConnections: promauto.NewGaugeVec(
			prometheus.GaugeOpts{
				Name: "database_connections",
				Help: "Number of database connections",
			},
			[]string{"state"}, // open, idle, in_use
		),
		DatabaseQueryDuration: promauto.NewHistogramVec(
			prometheus.HistogramOpts{
				Name:    "database_query_duration_seconds",
				Help:    "Duration of database queries in seconds",
				Buckets: prometheus.ExponentialBuckets(0.001, 2, 10),
			},
			[]string{"operation"},
		),
		DatabaseQueriesTotal: promauto.NewCounterVec(
			prometheus.CounterOpts{
				Name: "database_queries_total",
				Help: "Total number of database queries",
			},
			[]string{"operation", "status"},
		),

		// Kafka metrics
		KafkaMessagesProduced: promauto.NewCounterVec(
			prometheus.CounterOpts{
				Name: "kafka_messages_produced_total",
				Help: "Total number of Kafka messages produced",
			},
			[]string{"topic"},
		),
		KafkaMessagesConsumed: promauto.NewCounterVec(
			prometheus.CounterOpts{
				Name: "kafka_messages_consumed_total",
				Help: "Total number of Kafka messages consumed",
			},
			[]string{"topic"},
		),
		KafkaProduceErrors: promauto.NewCounterVec(
			prometheus.CounterOpts{
				Name: "kafka_produce_errors_total",
				Help: "Total number of Kafka produce errors",
			},
			[]string{"topic", "error_type"},
		),
		KafkaConsumeErrors: promauto.NewCounterVec(
			prometheus.CounterOpts{
				Name: "kafka_consume_errors_total",
				Help: "Total number of Kafka consume errors",
			},
			[]string{"topic", "error_type"},
		),
	}
}

// MetricsMiddleware creates a Gin middleware for HTTP metrics
func MetricsMiddleware(metrics *Metrics) gin.HandlerFunc {
	return func(c *gin.Context) {
		start := time.Now()
		path := c.FullPath()
		method := c.Request.Method

		// Track in-flight requests
		metrics.HTTPRequestsInFlight.WithLabelValues(method, path).Inc()
		defer metrics.HTTPRequestsInFlight.WithLabelValues(method, path).Dec()

		// Process request
		c.Next()

		// Record metrics
		duration := time.Since(start).Seconds()
		status := string(rune(c.Writer.Status()))

		metrics.HTTPRequestsTotal.WithLabelValues(method, path, status).Inc()
		metrics.HTTPRequestDuration.WithLabelValues(method, path).Observe(duration)
	}
}

// LoggingMiddleware creates a Gin middleware for structured logging
func LoggingMiddleware(logger *logrus.Logger) gin.HandlerFunc {
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

		entry := logger.WithFields(logrus.Fields{
			"status":     statusCode,
			"latency":    latency,
			"client_ip":  clientIP,
			"method":     method,
			"path":       path,
			"user_agent": c.Request.UserAgent(),
		})

		if len(c.Errors) > 0 {
			entry.Error(c.Errors.String())
		} else {
			entry.Info("HTTP request processed")
		}
	}
}

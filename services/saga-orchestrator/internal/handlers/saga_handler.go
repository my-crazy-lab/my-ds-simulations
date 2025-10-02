package handlers

import (
	"net/http"
	"strconv"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"github.com/microservices-saga/services/saga-orchestrator/internal/models"
	"github.com/microservices-saga/services/saga-orchestrator/internal/orchestrator"
	"github.com/microservices-saga/services/saga-orchestrator/internal/services"
	"github.com/sirupsen/logrus"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
)

var tracer = otel.Tracer("saga-orchestrator-handlers")

// SagaHandler handles HTTP requests for saga operations
type SagaHandler struct {
	orchestrator       *orchestrator.SagaOrchestrator
	idempotencyService services.IdempotencyService
	logger             *logrus.Logger
}

// NewSagaHandler creates a new saga handler
func NewSagaHandler(
	orchestrator *orchestrator.SagaOrchestrator,
	idempotencyService services.IdempotencyService,
	logger *logrus.Logger,
) *SagaHandler {
	return &SagaHandler{
		orchestrator:       orchestrator,
		idempotencyService: idempotencyService,
		logger:             logger,
	}
}

// CreateSaga creates a new saga
func (h *SagaHandler) CreateSaga(c *gin.Context) {
	ctx, span := tracer.Start(c.Request.Context(), "handler.CreateSaga")
	defer span.End()

	var req models.CreateSagaRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		span.RecordError(err)
		c.JSON(http.StatusBadRequest, gin.H{
			"error":   "Invalid request body",
			"details": err.Error(),
		})
		return
	}

	span.SetAttributes(
		attribute.String("saga.type", req.SagaType),
		attribute.String("correlation.id", stringValue(req.CorrelationID)),
		attribute.String("idempotency.key", stringValue(req.IdempotencyKey)),
	)

	h.logger.WithFields(logrus.Fields{
		"saga_type":       req.SagaType,
		"correlation_id":  req.CorrelationID,
		"idempotency_key": req.IdempotencyKey,
	}).Info("Creating new saga")

	saga, err := h.orchestrator.CreateSaga(ctx, &req)
	if err != nil {
		span.RecordError(err)
		h.logger.WithError(err).Error("Failed to create saga")
		c.JSON(http.StatusInternalServerError, gin.H{
			"error":   "Failed to create saga",
			"details": err.Error(),
		})
		return
	}

	response := saga.ToResponse()
	span.SetAttributes(attribute.String("saga.id", saga.ID.String()))

	c.JSON(http.StatusCreated, response)
}

// GetSaga retrieves a saga by ID
func (h *SagaHandler) GetSaga(c *gin.Context) {
	ctx, span := tracer.Start(c.Request.Context(), "handler.GetSaga")
	defer span.End()

	sagaIDStr := c.Param("id")
	sagaID, err := uuid.Parse(sagaIDStr)
	if err != nil {
		span.RecordError(err)
		c.JSON(http.StatusBadRequest, gin.H{
			"error":   "Invalid saga ID",
			"details": err.Error(),
		})
		return
	}

	span.SetAttributes(attribute.String("saga.id", sagaID.String()))

	saga, err := h.orchestrator.GetSaga(ctx, sagaID)
	if err != nil {
		span.RecordError(err)
		h.logger.WithError(err).WithField("saga_id", sagaID).Error("Failed to get saga")
		c.JSON(http.StatusNotFound, gin.H{
			"error":   "Saga not found",
			"details": err.Error(),
		})
		return
	}

	response := saga.ToResponse()
	c.JSON(http.StatusOK, response)
}

// ListSagas retrieves sagas with pagination
func (h *SagaHandler) ListSagas(c *gin.Context) {
	ctx, span := tracer.Start(c.Request.Context(), "handler.ListSagas")
	defer span.End()

	// Parse query parameters
	limitStr := c.DefaultQuery("limit", "20")
	offsetStr := c.DefaultQuery("offset", "0")
	statusStr := c.Query("status")

	limit, err := strconv.Atoi(limitStr)
	if err != nil || limit <= 0 || limit > 100 {
		c.JSON(http.StatusBadRequest, gin.H{
			"error": "Invalid limit parameter (must be between 1 and 100)",
		})
		return
	}

	offset, err := strconv.Atoi(offsetStr)
	if err != nil || offset < 0 {
		c.JSON(http.StatusBadRequest, gin.H{
			"error": "Invalid offset parameter (must be >= 0)",
		})
		return
	}

	var status *models.SagaStatus
	if statusStr != "" {
		s := models.SagaStatus(statusStr)
		status = &s
	}

	span.SetAttributes(
		attribute.Int("limit", limit),
		attribute.Int("offset", offset),
	)
	if status != nil {
		span.SetAttributes(attribute.String("status", string(*status)))
	}

	sagas, total, err := h.orchestrator.ListSagas(ctx, limit, offset, status)
	if err != nil {
		span.RecordError(err)
		h.logger.WithError(err).Error("Failed to list sagas")
		c.JSON(http.StatusInternalServerError, gin.H{
			"error":   "Failed to list sagas",
			"details": err.Error(),
		})
		return
	}

	// Convert to response format
	var responses []models.SagaResponse
	for _, saga := range sagas {
		responses = append(responses, *saga.ToResponse())
	}

	page := offset/limit + 1
	response := models.SagaListResponse{
		Sagas:      responses,
		TotalCount: total,
		Page:       page,
		PageSize:   limit,
	}

	span.SetAttributes(
		attribute.Int("total.count", total),
		attribute.Int("returned.count", len(responses)),
	)

	c.JSON(http.StatusOK, response)
}

// CompensateSaga initiates compensation for a saga
func (h *SagaHandler) CompensateSaga(c *gin.Context) {
	ctx, span := tracer.Start(c.Request.Context(), "handler.CompensateSaga")
	defer span.End()

	sagaIDStr := c.Param("id")
	sagaID, err := uuid.Parse(sagaIDStr)
	if err != nil {
		span.RecordError(err)
		c.JSON(http.StatusBadRequest, gin.H{
			"error":   "Invalid saga ID",
			"details": err.Error(),
		})
		return
	}

	var req models.CompensateSagaRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		span.RecordError(err)
		c.JSON(http.StatusBadRequest, gin.H{
			"error":   "Invalid request body",
			"details": err.Error(),
		})
		return
	}

	span.SetAttributes(
		attribute.String("saga.id", sagaID.String()),
		attribute.String("reason", req.Reason),
	)

	h.logger.WithFields(logrus.Fields{
		"saga_id": sagaID,
		"reason":  req.Reason,
	}).Info("Compensating saga")

	err = h.orchestrator.CompensateSaga(ctx, sagaID, req.Reason)
	if err != nil {
		span.RecordError(err)
		h.logger.WithError(err).WithField("saga_id", sagaID).Error("Failed to compensate saga")
		c.JSON(http.StatusInternalServerError, gin.H{
			"error":   "Failed to compensate saga",
			"details": err.Error(),
		})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"message": "Saga compensation initiated",
		"saga_id": sagaID,
	})
}

// RetrySaga retries a failed saga
func (h *SagaHandler) RetrySaga(c *gin.Context) {
	ctx, span := tracer.Start(c.Request.Context(), "handler.RetrySaga")
	defer span.End()

	sagaIDStr := c.Param("id")
	sagaID, err := uuid.Parse(sagaIDStr)
	if err != nil {
		span.RecordError(err)
		c.JSON(http.StatusBadRequest, gin.H{
			"error":   "Invalid saga ID",
			"details": err.Error(),
		})
		return
	}

	var req models.RetrySagaRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		span.RecordError(err)
		c.JSON(http.StatusBadRequest, gin.H{
			"error":   "Invalid request body",
			"details": err.Error(),
		})
		return
	}

	span.SetAttributes(
		attribute.String("saga.id", sagaID.String()),
		attribute.Int("from.step", req.FromStep),
	)

	h.logger.WithFields(logrus.Fields{
		"saga_id":   sagaID,
		"from_step": req.FromStep,
	}).Info("Retrying saga")

	err = h.orchestrator.RetrySaga(ctx, sagaID, req.FromStep)
	if err != nil {
		span.RecordError(err)
		h.logger.WithError(err).WithField("saga_id", sagaID).Error("Failed to retry saga")
		c.JSON(http.StatusInternalServerError, gin.H{
			"error":   "Failed to retry saga",
			"details": err.Error(),
		})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"message":   "Saga retry initiated",
		"saga_id":   sagaID,
		"from_step": req.FromStep,
	})
}

// Helper function
func stringValue(s *string) string {
	if s == nil {
		return ""
	}
	return *s
}

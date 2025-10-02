package orchestrator

import (
	"context"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/microservices-saga/services/saga-orchestrator/internal/models"
	"github.com/sirupsen/logrus"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"
)

// Mock implementations
type MockSagaRepository struct {
	mock.Mock
}

func (m *MockSagaRepository) Create(ctx context.Context, saga *models.SagaInstance) error {
	args := m.Called(ctx, saga)
	return args.Error(0)
}

func (m *MockSagaRepository) GetByID(ctx context.Context, id uuid.UUID) (*models.SagaInstance, error) {
	args := m.Called(ctx, id)
	return args.Get(0).(*models.SagaInstance), args.Error(1)
}

func (m *MockSagaRepository) Update(ctx context.Context, saga *models.SagaInstance) error {
	args := m.Called(ctx, saga)
	return args.Error(0)
}

func (m *MockSagaRepository) List(ctx context.Context, limit, offset int) ([]*models.SagaInstance, error) {
	args := m.Called(ctx, limit, offset)
	return args.Get(0).([]*models.SagaInstance), args.Error(1)
}

func (m *MockSagaRepository) GetByStatus(ctx context.Context, status models.SagaStatus) ([]*models.SagaInstance, error) {
	args := m.Called(ctx, status)
	return args.Get(0).([]*models.SagaInstance), args.Error(1)
}

type MockOutboxRepository struct {
	mock.Mock
}

func (m *MockOutboxRepository) Create(ctx context.Context, event *models.OutboxEvent) error {
	args := m.Called(ctx, event)
	return args.Error(0)
}

func (m *MockOutboxRepository) GetUnprocessed(ctx context.Context, limit int) ([]*models.OutboxEvent, error) {
	args := m.Called(ctx, limit)
	return args.Get(0).([]*models.OutboxEvent), args.Error(1)
}

func (m *MockOutboxRepository) MarkProcessed(ctx context.Context, id uuid.UUID) error {
	args := m.Called(ctx, id)
	return args.Error(0)
}

type MockEventService struct {
	mock.Mock
}

func (m *MockEventService) PublishEvent(ctx context.Context, topic string, event interface{}) error {
	args := m.Called(ctx, topic, event)
	return args.Error(0)
}

type MockIdempotencyService struct {
	mock.Mock
}

func (m *MockIdempotencyService) IsProcessed(ctx context.Context, key string) (bool, error) {
	args := m.Called(ctx, key)
	return args.Bool(0), args.Error(1)
}

func (m *MockIdempotencyService) MarkProcessed(ctx context.Context, key string, ttl time.Duration) error {
	args := m.Called(ctx, key, ttl)
	return args.Error(0)
}

type MockCompensationService struct {
	mock.Mock
}

func (m *MockCompensationService) ExecuteCompensation(ctx context.Context, saga *models.SagaInstance, step *models.SagaStep) error {
	args := m.Called(ctx, saga, step)
	return args.Error(0)
}

type MockMetrics struct {
	mock.Mock
}

func (m *MockMetrics) IncrementSagaCreated(sagaType string) {
	m.Called(sagaType)
}

func (m *MockMetrics) IncrementSagaCompleted(sagaType string) {
	m.Called(sagaType)
}

func (m *MockMetrics) IncrementSagaFailed(sagaType string) {
	m.Called(sagaType)
}

func (m *MockMetrics) IncrementSagaCompensated(sagaType string) {
	m.Called(sagaType)
}

func (m *MockMetrics) RecordSagaDuration(sagaType string, duration time.Duration) {
	m.Called(sagaType, duration)
}

func (m *MockMetrics) IncrementStepExecuted(stepType string) {
	m.Called(stepType)
}

func (m *MockMetrics) IncrementStepFailed(stepType string) {
	m.Called(stepType)
}

func (m *MockMetrics) IncrementStepCompensated(stepType string) {
	m.Called(stepType)
}

// Test cases
func TestSagaOrchestrator_CreateSaga(t *testing.T) {
	// Setup
	mockSagaRepo := new(MockSagaRepository)
	mockOutboxRepo := new(MockOutboxRepository)
	mockEventService := new(MockEventService)
	mockIdempotencyService := new(MockIdempotencyService)
	mockCompensationService := new(MockCompensationService)
	mockMetrics := new(MockMetrics)
	logger := logrus.New()

	orchestrator := NewSagaOrchestrator(
		mockSagaRepo,
		mockOutboxRepo,
		mockEventService,
		mockIdempotencyService,
		mockCompensationService,
		mockMetrics,
		logger,
	)

	// Test data
	ctx := context.Background()
	sagaType := "order_processing"
	data := map[string]interface{}{
		"order_id": "test-001",
		"user_id":  "user-123",
	}

	// Mock expectations
	mockSagaRepo.On("Create", ctx, mock.AnythingOfType("*models.SagaInstance")).Return(nil)
	mockMetrics.On("IncrementSagaCreated", sagaType).Return()

	// Execute
	saga, err := orchestrator.CreateSaga(ctx, sagaType, data)

	// Assert
	assert.NoError(t, err)
	assert.NotNil(t, saga)
	assert.Equal(t, sagaType, saga.Type)
	assert.Equal(t, models.SagaStatusPending, saga.Status)
	assert.Equal(t, data, saga.Data)

	// Verify mocks
	mockSagaRepo.AssertExpectations(t)
	mockMetrics.AssertExpectations(t)
}

func TestSagaOrchestrator_ExecuteSaga_Success(t *testing.T) {
	// Setup
	mockSagaRepo := new(MockSagaRepository)
	mockOutboxRepo := new(MockOutboxRepository)
	mockEventService := new(MockEventService)
	mockIdempotencyService := new(MockIdempotencyService)
	mockCompensationService := new(MockCompensationService)
	mockMetrics := new(MockMetrics)
	logger := logrus.New()

	orchestrator := NewSagaOrchestrator(
		mockSagaRepo,
		mockOutboxRepo,
		mockEventService,
		mockIdempotencyService,
		mockCompensationService,
		mockMetrics,
		logger,
	)

	// Test data
	ctx := context.Background()
	sagaID := uuid.New()
	saga := &models.SagaInstance{
		ID:     sagaID,
		Type:   "order_processing",
		Status: models.SagaStatusPending,
		Steps: []*models.SagaStep{
			{
				ID:     uuid.New(),
				Type:   "reserve_inventory",
				Status: models.StepStatusPending,
			},
		},
	}

	// Mock expectations
	mockSagaRepo.On("GetByID", ctx, sagaID).Return(saga, nil)
	mockSagaRepo.On("Update", ctx, saga).Return(nil)
	mockEventService.On("PublishEvent", ctx, "inventory.commands", mock.Anything).Return(nil)
	mockMetrics.On("IncrementStepExecuted", "reserve_inventory").Return()

	// Execute
	err := orchestrator.ExecuteSaga(ctx, sagaID)

	// Assert
	assert.NoError(t, err)
	assert.Equal(t, models.SagaStatusRunning, saga.Status)

	// Verify mocks
	mockSagaRepo.AssertExpectations(t)
	mockEventService.AssertExpectations(t)
	mockMetrics.AssertExpectations(t)
}

func TestSagaOrchestrator_CompensateSaga(t *testing.T) {
	// Setup
	mockSagaRepo := new(MockSagaRepository)
	mockOutboxRepo := new(MockOutboxRepository)
	mockEventService := new(MockEventService)
	mockIdempotencyService := new(MockIdempotencyService)
	mockCompensationService := new(MockCompensationService)
	mockMetrics := new(MockMetrics)
	logger := logrus.New()

	orchestrator := NewSagaOrchestrator(
		mockSagaRepo,
		mockOutboxRepo,
		mockEventService,
		mockIdempotencyService,
		mockCompensationService,
		mockMetrics,
		logger,
	)

	// Test data
	ctx := context.Background()
	sagaID := uuid.New()
	saga := &models.SagaInstance{
		ID:     sagaID,
		Type:   "order_processing",
		Status: models.SagaStatusFailed,
		Steps: []*models.SagaStep{
			{
				ID:     uuid.New(),
				Type:   "reserve_inventory",
				Status: models.StepStatusCompleted,
			},
		},
	}

	// Mock expectations
	mockSagaRepo.On("GetByID", ctx, sagaID).Return(saga, nil)
	mockSagaRepo.On("Update", ctx, saga).Return(nil)
	mockCompensationService.On("ExecuteCompensation", ctx, saga, saga.Steps[0]).Return(nil)
	mockMetrics.On("IncrementSagaCompensated", "order_processing").Return()
	mockMetrics.On("IncrementStepCompensated", "reserve_inventory").Return()

	// Execute
	err := orchestrator.CompensateSaga(ctx, sagaID)

	// Assert
	assert.NoError(t, err)
	assert.Equal(t, models.SagaStatusCompensated, saga.Status)

	// Verify mocks
	mockSagaRepo.AssertExpectations(t)
	mockCompensationService.AssertExpectations(t)
	mockMetrics.AssertExpectations(t)
}

func TestSagaOrchestrator_HandleStepCompleted(t *testing.T) {
	// Setup
	mockSagaRepo := new(MockSagaRepository)
	mockOutboxRepo := new(MockOutboxRepository)
	mockEventService := new(MockEventService)
	mockIdempotencyService := new(MockIdempotencyService)
	mockCompensationService := new(MockCompensationService)
	mockMetrics := new(MockMetrics)
	logger := logrus.New()

	orchestrator := NewSagaOrchestrator(
		mockSagaRepo,
		mockOutboxRepo,
		mockEventService,
		mockIdempotencyService,
		mockCompensationService,
		mockMetrics,
		logger,
	)

	// Test data
	ctx := context.Background()
	sagaID := uuid.New()
	stepID := uuid.New()
	saga := &models.SagaInstance{
		ID:     sagaID,
		Type:   "order_processing",
		Status: models.SagaStatusRunning,
		Steps: []*models.SagaStep{
			{
				ID:     stepID,
				Type:   "reserve_inventory",
				Status: models.StepStatusRunning,
			},
			{
				ID:     uuid.New(),
				Type:   "process_payment",
				Status: models.StepStatusPending,
			},
		},
	}

	event := &models.StepCompletedEvent{
		SagaID: sagaID,
		StepID: stepID,
		Result: map[string]interface{}{"reservation_id": "res-123"},
	}

	// Mock expectations
	mockSagaRepo.On("GetByID", ctx, sagaID).Return(saga, nil)
	mockSagaRepo.On("Update", ctx, saga).Return(nil)
	mockEventService.On("PublishEvent", ctx, "payment.commands", mock.Anything).Return(nil)
	mockMetrics.On("IncrementStepExecuted", "process_payment").Return()

	// Execute
	err := orchestrator.HandleStepCompleted(ctx, event)

	// Assert
	assert.NoError(t, err)
	assert.Equal(t, models.StepStatusCompleted, saga.Steps[0].Status)
	assert.Equal(t, models.StepStatusRunning, saga.Steps[1].Status)

	// Verify mocks
	mockSagaRepo.AssertExpectations(t)
	mockEventService.AssertExpectations(t)
	mockMetrics.AssertExpectations(t)
}

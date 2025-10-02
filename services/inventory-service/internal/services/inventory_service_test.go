package services

import (
	"context"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/microservices-saga/services/inventory-service/internal/models"
	"github.com/sirupsen/logrus"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"
)

// Mock implementations
type MockInventoryRepository struct {
	mock.Mock
}

func (m *MockInventoryRepository) Create(ctx context.Context, item *models.InventoryItem) error {
	args := m.Called(ctx, item)
	return args.Error(0)
}

func (m *MockInventoryRepository) GetBySKU(ctx context.Context, sku string) (*models.InventoryItem, error) {
	args := m.Called(ctx, sku)
	if args.Get(0) == nil {
		return nil, args.Error(1)
	}
	return args.Get(0).(*models.InventoryItem), args.Error(1)
}

func (m *MockInventoryRepository) Update(ctx context.Context, item *models.InventoryItem) error {
	args := m.Called(ctx, item)
	return args.Error(0)
}

func (m *MockInventoryRepository) List(ctx context.Context, limit, offset int) ([]*models.InventoryItem, error) {
	args := m.Called(ctx, limit, offset)
	return args.Get(0).([]*models.InventoryItem), args.Error(1)
}

func (m *MockInventoryRepository) Delete(ctx context.Context, sku string) error {
	args := m.Called(ctx, sku)
	return args.Error(0)
}

func (m *MockInventoryRepository) CreateReservation(ctx context.Context, reservation *models.Reservation) error {
	args := m.Called(ctx, reservation)
	return args.Error(0)
}

func (m *MockInventoryRepository) GetReservation(ctx context.Context, id uuid.UUID) (*models.Reservation, error) {
	args := m.Called(ctx, id)
	if args.Get(0) == nil {
		return nil, args.Error(1)
	}
	return args.Get(0).(*models.Reservation), args.Error(1)
}

func (m *MockInventoryRepository) UpdateReservation(ctx context.Context, reservation *models.Reservation) error {
	args := m.Called(ctx, reservation)
	return args.Error(0)
}

func (m *MockInventoryRepository) ListReservations(ctx context.Context, limit, offset int) ([]*models.Reservation, error) {
	args := m.Called(ctx, limit, offset)
	return args.Get(0).([]*models.Reservation), args.Error(1)
}

func (m *MockInventoryRepository) GetExpiredReservations(ctx context.Context) ([]*models.Reservation, error) {
	args := m.Called(ctx)
	return args.Get(0).([]*models.Reservation), args.Error(1)
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

type MockMetrics struct {
	mock.Mock
}

func (m *MockMetrics) IncrementItemCreated() {
	m.Called()
}

func (m *MockMetrics) IncrementItemUpdated() {
	m.Called()
}

func (m *MockMetrics) IncrementItemDeleted() {
	m.Called()
}

func (m *MockMetrics) IncrementReservationCreated() {
	m.Called()
}

func (m *MockMetrics) IncrementReservationReleased() {
	m.Called()
}

func (m *MockMetrics) IncrementReservationExpired() {
	m.Called()
}

func (m *MockMetrics) RecordInventoryLevel(sku string, quantity int) {
	m.Called(sku, quantity)
}

// Test cases
func TestInventoryService_CreateItem(t *testing.T) {
	// Setup
	mockInventoryRepo := new(MockInventoryRepository)
	mockOutboxRepo := new(MockOutboxRepository)
	mockEventService := new(MockEventService)
	mockMetrics := new(MockMetrics)
	logger := logrus.New()

	service := NewInventoryService(mockInventoryRepo, mockOutboxRepo, mockEventService, mockMetrics, logger)

	// Test data
	ctx := context.Background()
	item := &models.InventoryItem{
		SKU:         "LAPTOP001",
		Name:        "Gaming Laptop",
		Description: "High-performance gaming laptop",
		Quantity:    10,
		Price:       1299.99,
	}

	// Mock expectations
	mockInventoryRepo.On("GetBySKU", ctx, item.SKU).Return(nil, models.ErrItemNotFound)
	mockInventoryRepo.On("Create", ctx, item).Return(nil)
	mockOutboxRepo.On("Create", ctx, mock.AnythingOfType("*models.OutboxEvent")).Return(nil)
	mockMetrics.On("IncrementItemCreated").Return()
	mockMetrics.On("RecordInventoryLevel", item.SKU, item.Quantity).Return()

	// Execute
	err := service.CreateItem(ctx, item)

	// Assert
	assert.NoError(t, err)
	assert.NotEqual(t, uuid.Nil, item.ID)
	assert.WithinDuration(t, time.Now(), item.CreatedAt, time.Second)

	// Verify mocks
	mockInventoryRepo.AssertExpectations(t)
	mockOutboxRepo.AssertExpectations(t)
	mockMetrics.AssertExpectations(t)
}

func TestInventoryService_ReserveItem_Success(t *testing.T) {
	// Setup
	mockInventoryRepo := new(MockInventoryRepository)
	mockOutboxRepo := new(MockOutboxRepository)
	mockEventService := new(MockEventService)
	mockMetrics := new(MockMetrics)
	logger := logrus.New()

	service := NewInventoryService(mockInventoryRepo, mockOutboxRepo, mockEventService, mockMetrics, logger)

	// Test data
	ctx := context.Background()
	sku := "LAPTOP001"
	quantity := 2
	reservationID := uuid.New()

	item := &models.InventoryItem{
		ID:       uuid.New(),
		SKU:      sku,
		Name:     "Gaming Laptop",
		Quantity: 10,
	}

	// Mock expectations
	mockInventoryRepo.On("GetBySKU", ctx, sku).Return(item, nil)
	mockInventoryRepo.On("Update", ctx, item).Return(nil)
	mockInventoryRepo.On("CreateReservation", ctx, mock.AnythingOfType("*models.Reservation")).Return(nil)
	mockOutboxRepo.On("Create", ctx, mock.AnythingOfType("*models.OutboxEvent")).Return(nil)
	mockMetrics.On("IncrementReservationCreated").Return()
	mockMetrics.On("RecordInventoryLevel", sku, 8).Return() // 10 - 2 = 8

	// Execute
	reservation, err := service.ReserveItem(ctx, sku, quantity, reservationID)

	// Assert
	assert.NoError(t, err)
	assert.NotNil(t, reservation)
	assert.Equal(t, sku, reservation.SKU)
	assert.Equal(t, quantity, reservation.Quantity)
	assert.Equal(t, reservationID, reservation.ID)
	assert.Equal(t, models.ReservationStatusActive, reservation.Status)
	assert.Equal(t, 8, item.Quantity) // Available quantity reduced

	// Verify mocks
	mockInventoryRepo.AssertExpectations(t)
	mockOutboxRepo.AssertExpectations(t)
	mockMetrics.AssertExpectations(t)
}

func TestInventoryService_ReserveItem_InsufficientStock(t *testing.T) {
	// Setup
	mockInventoryRepo := new(MockInventoryRepository)
	mockOutboxRepo := new(MockOutboxRepository)
	mockEventService := new(MockEventService)
	mockMetrics := new(MockMetrics)
	logger := logrus.New()

	service := NewInventoryService(mockInventoryRepo, mockOutboxRepo, mockEventService, mockMetrics, logger)

	// Test data
	ctx := context.Background()
	sku := "LAPTOP001"
	quantity := 15 // More than available
	reservationID := uuid.New()

	item := &models.InventoryItem{
		ID:       uuid.New(),
		SKU:      sku,
		Name:     "Gaming Laptop",
		Quantity: 10, // Only 10 available
	}

	// Mock expectations
	mockInventoryRepo.On("GetBySKU", ctx, sku).Return(item, nil)

	// Execute
	reservation, err := service.ReserveItem(ctx, sku, quantity, reservationID)

	// Assert
	assert.Error(t, err)
	assert.Nil(t, reservation)
	assert.Contains(t, err.Error(), "insufficient stock")

	// Verify mocks
	mockInventoryRepo.AssertExpectations(t)
}

func TestInventoryService_ReleaseReservation(t *testing.T) {
	// Setup
	mockInventoryRepo := new(MockInventoryRepository)
	mockOutboxRepo := new(MockOutboxRepository)
	mockEventService := new(MockEventService)
	mockMetrics := new(MockMetrics)
	logger := logrus.New()

	service := NewInventoryService(mockInventoryRepo, mockOutboxRepo, mockEventService, mockMetrics, logger)

	// Test data
	ctx := context.Background()
	reservationID := uuid.New()
	sku := "LAPTOP001"

	reservation := &models.Reservation{
		ID:       reservationID,
		SKU:      sku,
		Quantity: 2,
		Status:   models.ReservationStatusActive,
	}

	item := &models.InventoryItem{
		ID:       uuid.New(),
		SKU:      sku,
		Name:     "Gaming Laptop",
		Quantity: 8, // Current available quantity
	}

	// Mock expectations
	mockInventoryRepo.On("GetReservation", ctx, reservationID).Return(reservation, nil)
	mockInventoryRepo.On("GetBySKU", ctx, sku).Return(item, nil)
	mockInventoryRepo.On("UpdateReservation", ctx, reservation).Return(nil)
	mockInventoryRepo.On("Update", ctx, item).Return(nil)
	mockOutboxRepo.On("Create", ctx, mock.AnythingOfType("*models.OutboxEvent")).Return(nil)
	mockMetrics.On("IncrementReservationReleased").Return()
	mockMetrics.On("RecordInventoryLevel", sku, 10).Return() // 8 + 2 = 10

	// Execute
	err := service.ReleaseReservation(ctx, reservationID)

	// Assert
	assert.NoError(t, err)
	assert.Equal(t, models.ReservationStatusReleased, reservation.Status)
	assert.Equal(t, 10, item.Quantity) // Quantity restored

	// Verify mocks
	mockInventoryRepo.AssertExpectations(t)
	mockOutboxRepo.AssertExpectations(t)
	mockMetrics.AssertExpectations(t)
}

func TestInventoryService_UpdateItem(t *testing.T) {
	// Setup
	mockInventoryRepo := new(MockInventoryRepository)
	mockOutboxRepo := new(MockOutboxRepository)
	mockEventService := new(MockEventService)
	mockMetrics := new(MockMetrics)
	logger := logrus.New()

	service := NewInventoryService(mockInventoryRepo, mockOutboxRepo, mockEventService, mockMetrics, logger)

	// Test data
	ctx := context.Background()
	sku := "LAPTOP001"
	
	existingItem := &models.InventoryItem{
		ID:       uuid.New(),
		SKU:      sku,
		Name:     "Gaming Laptop",
		Quantity: 10,
		Price:    1299.99,
	}

	updates := &models.InventoryItem{
		Name:     "Updated Gaming Laptop",
		Quantity: 15,
		Price:    1399.99,
	}

	// Mock expectations
	mockInventoryRepo.On("GetBySKU", ctx, sku).Return(existingItem, nil)
	mockInventoryRepo.On("Update", ctx, existingItem).Return(nil)
	mockOutboxRepo.On("Create", ctx, mock.AnythingOfType("*models.OutboxEvent")).Return(nil)
	mockMetrics.On("IncrementItemUpdated").Return()
	mockMetrics.On("RecordInventoryLevel", sku, 15).Return()

	// Execute
	err := service.UpdateItem(ctx, sku, updates)

	// Assert
	assert.NoError(t, err)
	assert.Equal(t, updates.Name, existingItem.Name)
	assert.Equal(t, updates.Quantity, existingItem.Quantity)
	assert.Equal(t, updates.Price, existingItem.Price)
	assert.WithinDuration(t, time.Now(), existingItem.UpdatedAt, time.Second)

	// Verify mocks
	mockInventoryRepo.AssertExpectations(t)
	mockOutboxRepo.AssertExpectations(t)
	mockMetrics.AssertExpectations(t)
}

func TestInventoryService_ProcessExpiredReservations(t *testing.T) {
	// Setup
	mockInventoryRepo := new(MockInventoryRepository)
	mockOutboxRepo := new(MockOutboxRepository)
	mockEventService := new(MockEventService)
	mockMetrics := new(MockMetrics)
	logger := logrus.New()

	service := NewInventoryService(mockInventoryRepo, mockOutboxRepo, mockEventService, mockMetrics, logger)

	// Test data
	ctx := context.Background()
	sku := "LAPTOP001"
	
	expiredReservation := &models.Reservation{
		ID:        uuid.New(),
		SKU:       sku,
		Quantity:  2,
		Status:    models.ReservationStatusActive,
		ExpiresAt: time.Now().Add(-time.Hour), // Expired 1 hour ago
	}

	item := &models.InventoryItem{
		ID:       uuid.New(),
		SKU:      sku,
		Quantity: 8,
	}

	// Mock expectations
	mockInventoryRepo.On("GetExpiredReservations", ctx).Return([]*models.Reservation{expiredReservation}, nil)
	mockInventoryRepo.On("GetBySKU", ctx, sku).Return(item, nil)
	mockInventoryRepo.On("UpdateReservation", ctx, expiredReservation).Return(nil)
	mockInventoryRepo.On("Update", ctx, item).Return(nil)
	mockOutboxRepo.On("Create", ctx, mock.AnythingOfType("*models.OutboxEvent")).Return(nil)
	mockMetrics.On("IncrementReservationExpired").Return()
	mockMetrics.On("RecordInventoryLevel", sku, 10).Return()

	// Execute
	err := service.ProcessExpiredReservations(ctx)

	// Assert
	assert.NoError(t, err)
	assert.Equal(t, models.ReservationStatusExpired, expiredReservation.Status)
	assert.Equal(t, 10, item.Quantity) // Quantity restored

	// Verify mocks
	mockInventoryRepo.AssertExpectations(t)
	mockOutboxRepo.AssertExpectations(t)
	mockMetrics.AssertExpectations(t)
}

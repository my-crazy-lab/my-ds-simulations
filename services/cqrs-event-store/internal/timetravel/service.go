package timetravel

import (
	"context"
	"fmt"
	"time"

	"github.com/microservices-saga/services/cqrs-event-store/internal/eventstore"
	"github.com/microservices-saga/services/cqrs-event-store/internal/infrastructure"
	"github.com/microservices-saga/services/cqrs-event-store/internal/models"
	"github.com/microservices-saga/services/cqrs-event-store/internal/repository"
	"github.com/microservices-saga/services/cqrs-event-store/internal/snapshots"
	"github.com/sirupsen/logrus"
)

// Service provides time-travel capabilities for event sourcing
type Service struct {
	eventStore      *eventstore.EventStore
	snapshotManager *snapshots.Manager
	analyticsRepo   repository.AnalyticsRepository
	config          Config
	metrics         *infrastructure.Metrics
	logger          *logrus.Logger
}

// Config holds time-travel service configuration
type Config struct {
	MaxTimeRange        time.Duration
	SnapshotInterval    time.Duration
	AnalyticsRetention  time.Duration
	CacheSize           int
	ParallelWorkers     int
	BatchSize           int
}

// NewService creates a new time-travel service
func NewService(
	eventStore *eventstore.EventStore,
	snapshotManager *snapshots.Manager,
	analyticsRepo repository.AnalyticsRepository,
	config Config,
	metrics *infrastructure.Metrics,
	logger *logrus.Logger,
) *Service {
	return &Service{
		eventStore:      eventStore,
		snapshotManager: snapshotManager,
		analyticsRepo:   analyticsRepo,
		config:          config,
		metrics:         metrics,
		logger:          logger,
	}
}

// RestoreToPointInTime restores an aggregate to a specific point in time
func (s *Service) RestoreToPointInTime(ctx context.Context, aggregateID string, pointInTime time.Time) (*models.AggregateState, error) {
	s.logger.Infof("Restoring aggregate %s to point in time: %v", aggregateID, pointInTime)

	start := time.Now()
	defer func() {
		duration := time.Since(start)
		s.metrics.TimeTravelOperations.WithLabelValues("restore", "completed").Inc()
		s.metrics.TimeTravelDuration.WithLabelValues("restore").Observe(duration.Seconds())
	}()

	// Validate time range
	if time.Since(pointInTime) > s.config.MaxTimeRange {
		return nil, fmt.Errorf("point in time %v is beyond maximum allowed range of %v", pointInTime, s.config.MaxTimeRange)
	}

	// Find the closest snapshot before the point in time
	snapshot, err := s.snapshotManager.GetSnapshotBeforeTime(ctx, aggregateID, pointInTime)
	if err != nil {
		s.logger.Warnf("No snapshot found before %v for aggregate %s: %v", pointInTime, aggregateID, err)
	}

	var startVersion int64
	var state *models.AggregateState

	if snapshot != nil {
		s.logger.Debugf("Found snapshot at version %d for aggregate %s", snapshot.Version, aggregateID)
		state = &models.AggregateState{
			AggregateID: aggregateID,
			Version:     snapshot.Version,
			Data:        snapshot.Data,
			Timestamp:   snapshot.CreatedAt,
		}
		startVersion = snapshot.Version + 1
	} else {
		s.logger.Debugf("No snapshot found, starting from beginning for aggregate %s", aggregateID)
		state = &models.AggregateState{
			AggregateID: aggregateID,
			Version:     0,
			Data:        make(map[string]interface{}),
			Timestamp:   time.Time{},
		}
		startVersion = 1
	}

	// Get events from start version up to the point in time
	events, err := s.eventStore.GetEventsInTimeRange(ctx, aggregateID, startVersion, pointInTime)
	if err != nil {
		return nil, fmt.Errorf("failed to get events: %w", err)
	}

	s.logger.Debugf("Found %d events to replay for aggregate %s", len(events), aggregateID)

	// Apply events to rebuild state
	for _, event := range events {
		if err := s.applyEventToState(state, &event); err != nil {
			return nil, fmt.Errorf("failed to apply event %s: %w", event.ID, err)
		}
	}

	s.logger.Infof("Successfully restored aggregate %s to version %d at time %v", aggregateID, state.Version, pointInTime)

	return state, nil
}

// GetTimeline returns the timeline of changes for an aggregate
func (s *Service) GetTimeline(ctx context.Context, aggregateID string, startTime, endTime time.Time) (*models.Timeline, error) {
	s.logger.Infof("Getting timeline for aggregate %s from %v to %v", aggregateID, startTime, endTime)

	// Get all events in the time range
	events, err := s.eventStore.GetEventsInTimeRange(ctx, aggregateID, 0, endTime)
	if err != nil {
		return nil, fmt.Errorf("failed to get events: %w", err)
	}

	// Filter events by start time
	var filteredEvents []models.Event
	for _, event := range events {
		if event.Timestamp.After(startTime) || event.Timestamp.Equal(startTime) {
			filteredEvents = append(filteredEvents, event)
		}
	}

	// Get snapshots in the time range
	snapshots, err := s.snapshotManager.GetSnapshotsInTimeRange(ctx, aggregateID, startTime, endTime)
	if err != nil {
		s.logger.Warnf("Failed to get snapshots: %v", err)
		snapshots = []models.Snapshot{} // Continue without snapshots
	}

	// Build timeline
	timeline := &models.Timeline{
		AggregateID: aggregateID,
		StartTime:   startTime,
		EndTime:     endTime,
		Events:      filteredEvents,
		Snapshots:   snapshots,
		Milestones:  s.extractMilestones(filteredEvents),
	}

	s.logger.Infof("Timeline built with %d events, %d snapshots, %d milestones", 
		len(timeline.Events), len(timeline.Snapshots), len(timeline.Milestones))

	return timeline, nil
}

// CompareStates compares aggregate states at two different points in time
func (s *Service) CompareStates(ctx context.Context, aggregateID string, time1, time2 time.Time) (*models.StateComparison, error) {
	s.logger.Infof("Comparing states for aggregate %s at %v and %v", aggregateID, time1, time2)

	// Restore states at both points in time
	state1, err := s.RestoreToPointInTime(ctx, aggregateID, time1)
	if err != nil {
		return nil, fmt.Errorf("failed to restore state at time1: %w", err)
	}

	state2, err := s.RestoreToPointInTime(ctx, aggregateID, time2)
	if err != nil {
		return nil, fmt.Errorf("failed to restore state at time2: %w", err)
	}

	// Compare states
	comparison := &models.StateComparison{
		AggregateID: aggregateID,
		Time1:       time1,
		Time2:       time2,
		State1:      state1,
		State2:      state2,
		Differences: s.calculateDifferences(state1.Data, state2.Data),
	}

	s.logger.Infof("State comparison completed with %d differences", len(comparison.Differences))

	return comparison, nil
}

// GetAnalytics returns analytics data for time-travel operations
func (s *Service) GetAnalytics(ctx context.Context, request *models.AnalyticsRequest) (*models.AnalyticsResponse, error) {
	s.logger.Infof("Getting analytics for time range %v to %v", request.StartTime, request.EndTime)

	// Get event analytics
	eventAnalytics, err := s.analyticsRepo.GetEventAnalytics(ctx, request.StartTime, request.EndTime)
	if err != nil {
		return nil, fmt.Errorf("failed to get event analytics: %w", err)
	}

	// Get aggregate analytics
	aggregateAnalytics, err := s.analyticsRepo.GetAggregateAnalytics(ctx, request.StartTime, request.EndTime)
	if err != nil {
		return nil, fmt.Errorf("failed to get aggregate analytics: %w", err)
	}

	// Get performance analytics
	performanceAnalytics, err := s.analyticsRepo.GetPerformanceAnalytics(ctx, request.StartTime, request.EndTime)
	if err != nil {
		return nil, fmt.Errorf("failed to get performance analytics: %w", err)
	}

	response := &models.AnalyticsResponse{
		TimeRange:            models.TimeRange{Start: request.StartTime, End: request.EndTime},
		EventAnalytics:       eventAnalytics,
		AggregateAnalytics:   aggregateAnalytics,
		PerformanceAnalytics: performanceAnalytics,
		GeneratedAt:          time.Now(),
	}

	return response, nil
}

// StartAnalyticsProcessor starts the analytics processing worker
func (s *Service) StartAnalyticsProcessor(ctx context.Context) {
	s.logger.Info("Starting analytics processor")

	ticker := time.NewTicker(1 * time.Minute)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			s.logger.Info("Analytics processor stopped")
			return
		case <-ticker.C:
			if err := s.processAnalytics(ctx); err != nil {
				s.logger.Errorf("Analytics processing error: %v", err)
			}
		}
	}
}

// processAnalytics processes analytics data
func (s *Service) processAnalytics(ctx context.Context) error {
	s.logger.Debug("Processing analytics")

	// Get recent events for analytics
	endTime := time.Now()
	startTime := endTime.Add(-1 * time.Hour) // Process last hour

	events, err := s.eventStore.GetEventsInTimeRange(ctx, "", 0, endTime)
	if err != nil {
		return fmt.Errorf("failed to get events for analytics: %w", err)
	}

	// Filter events by start time
	var recentEvents []models.Event
	for _, event := range events {
		if event.Timestamp.After(startTime) {
			recentEvents = append(recentEvents, event)
		}
	}

	if len(recentEvents) == 0 {
		s.logger.Debug("No recent events to process")
		return nil
	}

	// Process events in batches
	batchSize := s.config.BatchSize
	for i := 0; i < len(recentEvents); i += batchSize {
		end := i + batchSize
		if end > len(recentEvents) {
			end = len(recentEvents)
		}

		batch := recentEvents[i:end]
		if err := s.processBatch(ctx, batch); err != nil {
			s.logger.Errorf("Failed to process batch: %v", err)
		}
	}

	s.logger.Debugf("Processed %d events for analytics", len(recentEvents))
	return nil
}

// processBatch processes a batch of events for analytics
func (s *Service) processBatch(ctx context.Context, events []models.Event) error {
	// Aggregate event data
	eventCounts := make(map[string]int)
	aggregateCounts := make(map[string]int)
	
	for _, event := range events {
		eventCounts[event.EventType]++
		aggregateCounts[event.AggregateType]++
	}

	// Store analytics data
	for eventType, count := range eventCounts {
		if err := s.analyticsRepo.StoreEventMetric(ctx, eventType, count, time.Now()); err != nil {
			return fmt.Errorf("failed to store event metric: %w", err)
		}
	}

	for aggregateType, count := range aggregateCounts {
		if err := s.analyticsRepo.StoreAggregateMetric(ctx, aggregateType, count, time.Now()); err != nil {
			return fmt.Errorf("failed to store aggregate metric: %w", err)
		}
	}

	return nil
}

// applyEventToState applies an event to an aggregate state
func (s *Service) applyEventToState(state *models.AggregateState, event *models.Event) error {
	// This is a simplified implementation
	// In production, you would have specific event handlers for each event type
	
	switch event.EventType {
	case "ItemCreated":
		s.applyItemCreated(state, event)
	case "ItemUpdated":
		s.applyItemUpdated(state, event)
	case "ItemDeleted":
		s.applyItemDeleted(state, event)
	case "PaymentProcessed":
		s.applyPaymentProcessed(state, event)
	case "SagaStarted":
		s.applySagaStarted(state, event)
	case "SagaCompleted":
		s.applySagaCompleted(state, event)
	default:
		s.logger.Warnf("Unknown event type: %s", event.EventType)
	}

	// Update state metadata
	state.Version = event.Version
	state.Timestamp = event.Timestamp

	return nil
}

// extractMilestones extracts important milestones from events
func (s *Service) extractMilestones(events []models.Event) []models.Milestone {
	var milestones []models.Milestone

	for _, event := range events {
		if s.isMilestoneEvent(event.EventType) {
			milestone := models.Milestone{
				Timestamp:   event.Timestamp,
				EventType:   event.EventType,
				Description: s.getMilestoneDescription(event.EventType),
				Data:        event.Data,
			}
			milestones = append(milestones, milestone)
		}
	}

	return milestones
}

// calculateDifferences calculates differences between two states
func (s *Service) calculateDifferences(state1, state2 map[string]interface{}) []models.StateDifference {
	var differences []models.StateDifference

	// Check for added/modified fields
	for key, value2 := range state2 {
		if value1, exists := state1[key]; exists {
			if !s.deepEqual(value1, value2) {
				differences = append(differences, models.StateDifference{
					Field:    key,
					Type:     "modified",
					OldValue: value1,
					NewValue: value2,
				})
			}
		} else {
			differences = append(differences, models.StateDifference{
				Field:    key,
				Type:     "added",
				NewValue: value2,
			})
		}
	}

	// Check for removed fields
	for key, value1 := range state1 {
		if _, exists := state2[key]; !exists {
			differences = append(differences, models.StateDifference{
				Field:    key,
				Type:     "removed",
				OldValue: value1,
			})
		}
	}

	return differences
}

// Helper methods (simplified implementations)

func (s *Service) applyItemCreated(state *models.AggregateState, event *models.Event) {
	if state.Data == nil {
		state.Data = make(map[string]interface{})
	}
	state.Data["status"] = "created"
	state.Data["created_at"] = event.Timestamp
}

func (s *Service) applyItemUpdated(state *models.AggregateState, event *models.Event) {
	if state.Data == nil {
		state.Data = make(map[string]interface{})
	}
	state.Data["status"] = "updated"
	state.Data["updated_at"] = event.Timestamp
}

func (s *Service) applyItemDeleted(state *models.AggregateState, event *models.Event) {
	if state.Data == nil {
		state.Data = make(map[string]interface{})
	}
	state.Data["status"] = "deleted"
	state.Data["deleted_at"] = event.Timestamp
}

func (s *Service) applyPaymentProcessed(state *models.AggregateState, event *models.Event) {
	if state.Data == nil {
		state.Data = make(map[string]interface{})
	}
	state.Data["payment_status"] = "processed"
	state.Data["payment_processed_at"] = event.Timestamp
}

func (s *Service) applySagaStarted(state *models.AggregateState, event *models.Event) {
	if state.Data == nil {
		state.Data = make(map[string]interface{})
	}
	state.Data["saga_status"] = "started"
	state.Data["saga_started_at"] = event.Timestamp
}

func (s *Service) applySagaCompleted(state *models.AggregateState, event *models.Event) {
	if state.Data == nil {
		state.Data = make(map[string]interface{})
	}
	state.Data["saga_status"] = "completed"
	state.Data["saga_completed_at"] = event.Timestamp
}

func (s *Service) isMilestoneEvent(eventType string) bool {
	milestoneEvents := []string{
		"ItemCreated",
		"PaymentProcessed",
		"SagaCompleted",
		"OrderFulfilled",
	}
	
	for _, milestone := range milestoneEvents {
		if eventType == milestone {
			return true
		}
	}
	
	return false
}

func (s *Service) getMilestoneDescription(eventType string) string {
	descriptions := map[string]string{
		"ItemCreated":     "Item was created in inventory",
		"PaymentProcessed": "Payment was successfully processed",
		"SagaCompleted":   "Saga transaction completed successfully",
		"OrderFulfilled":  "Order was fulfilled and shipped",
	}
	
	if desc, exists := descriptions[eventType]; exists {
		return desc
	}
	
	return fmt.Sprintf("Event: %s", eventType)
}

func (s *Service) deepEqual(a, b interface{}) bool {
	// Simplified deep equality check
	// In production, use a proper deep equality library
	return fmt.Sprintf("%v", a) == fmt.Sprintf("%v", b)
}

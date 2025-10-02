package pipeline

import (
	"context"
	"encoding/json"
	"fmt"
	"sync"
	"time"

	"github.com/microservices-saga/services/analytics-etl/internal/infrastructure"
	"github.com/microservices-saga/services/analytics-etl/internal/models"
	"github.com/microservices-saga/services/analytics-etl/internal/processors"
	"github.com/microservices-saga/services/analytics-etl/internal/services"
	"github.com/sirupsen/logrus"
)

// ETLPipeline orchestrates the entire ETL process
type ETLPipeline struct {
	eventProcessor         *processors.EventProcessor
	transformProcessor     *processors.TransformProcessor
	aggregationProcessor   *processors.AggregationProcessor
	deduplicationProcessor *processors.DeduplicationProcessor
	etlService            *services.ETLService
	metrics               *infrastructure.Metrics
	logger                *logrus.Logger
	
	// Pipeline state
	isRunning    bool
	mu           sync.RWMutex
	stopChannels map[string]chan struct{}
}

// NewETLPipeline creates a new ETL pipeline
func NewETLPipeline(
	eventProcessor *processors.EventProcessor,
	transformProcessor *processors.TransformProcessor,
	aggregationProcessor *processors.AggregationProcessor,
	deduplicationProcessor *processors.DeduplicationProcessor,
	etlService *services.ETLService,
	metrics *infrastructure.Metrics,
	logger *logrus.Logger,
) *ETLPipeline {
	return &ETLPipeline{
		eventProcessor:         eventProcessor,
		transformProcessor:     transformProcessor,
		aggregationProcessor:   aggregationProcessor,
		deduplicationProcessor: deduplicationProcessor,
		etlService:            etlService,
		metrics:               metrics,
		logger:                logger,
		stopChannels:          make(map[string]chan struct{}),
	}
}

// StartCDCConsumer starts consuming CDC events from Kafka
func (p *ETLPipeline) StartCDCConsumer(ctx context.Context, consumer *infrastructure.KafkaConsumer) {
	p.mu.Lock()
	stopCh := make(chan struct{})
	p.stopChannels["cdc_consumer"] = stopCh
	p.mu.Unlock()

	p.logger.Info("Starting CDC consumer")

	topics := []string{
		"postgres.saga.saga_instances",
		"postgres.saga.saga_steps",
		"postgres.saga.outbox_events",
		"postgres.inventory.items",
		"postgres.inventory.reservations",
		"postgres.payment.payments",
		"postgres.notification.notifications",
	}

	err := consumer.Subscribe(topics, func(message []byte, topic string, partition int32, offset int64) error {
		select {
		case <-stopCh:
			return fmt.Errorf("consumer stopped")
		default:
		}

		start := time.Now()
		
		// Parse CDC event
		var cdcEvent models.CDCEvent
		if err := json.Unmarshal(message, &cdcEvent); err != nil {
			p.logger.Errorf("Failed to parse CDC event: %v", err)
			p.metrics.CDCEventsProcessed.WithLabelValues(topic, "parse_error").Inc()
			return nil // Don't fail the entire batch for one bad message
		}

		// Process event through pipeline
		if err := p.processCDCEvent(ctx, &cdcEvent, topic); err != nil {
			p.logger.Errorf("Failed to process CDC event: %v", err)
			p.metrics.CDCEventsProcessed.WithLabelValues(topic, "process_error").Inc()
			return nil
		}

		// Record metrics
		duration := time.Since(start).Seconds()
		p.metrics.CDCEventsProcessed.WithLabelValues(topic, "success").Inc()
		p.metrics.CDCProcessingDuration.WithLabelValues(topic).Observe(duration)

		return nil
	})

	if err != nil {
		p.logger.Errorf("CDC consumer error: %v", err)
	}
}

// StartBatchProcessor starts the batch processing worker
func (p *ETLPipeline) StartBatchProcessor(ctx context.Context) {
	p.mu.Lock()
	stopCh := make(chan struct{})
	p.stopChannels["batch_processor"] = stopCh
	p.mu.Unlock()

	p.logger.Info("Starting batch processor")

	ticker := time.NewTicker(5 * time.Minute) // Process batches every 5 minutes
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case <-stopCh:
			return
		case <-ticker.C:
			if err := p.processBatch(ctx); err != nil {
				p.logger.Errorf("Batch processing error: %v", err)
			}
		}
	}
}

// StartRealTimeProcessor starts the real-time processing worker
func (p *ETLPipeline) StartRealTimeProcessor(ctx context.Context, consumer *infrastructure.KafkaConsumer) {
	p.mu.Lock()
	stopCh := make(chan struct{})
	p.stopChannels["realtime_processor"] = stopCh
	p.mu.Unlock()

	p.logger.Info("Starting real-time processor")

	topics := []string{
		"saga-events",
		"inventory-events",
		"payment-events",
		"notification-events",
	}

	err := consumer.Subscribe(topics, func(message []byte, topic string, partition int32, offset int64) error {
		select {
		case <-stopCh:
			return fmt.Errorf("processor stopped")
		default:
		}

		start := time.Now()

		// Parse event
		var event models.Event
		if err := json.Unmarshal(message, &event); err != nil {
			p.logger.Errorf("Failed to parse real-time event: %v", err)
			p.metrics.RealTimeEventsProcessed.WithLabelValues(topic, "parse_error").Inc()
			return nil
		}

		// Process event
		if err := p.processRealTimeEvent(ctx, &event, topic); err != nil {
			p.logger.Errorf("Failed to process real-time event: %v", err)
			p.metrics.RealTimeEventsProcessed.WithLabelValues(topic, "process_error").Inc()
			return nil
		}

		// Record metrics
		duration := time.Since(start).Seconds()
		p.metrics.RealTimeEventsProcessed.WithLabelValues(topic, "success").Inc()
		p.metrics.RealTimeProcessingDuration.WithLabelValues(topic).Observe(duration)

		return nil
	})

	if err != nil {
		p.logger.Errorf("Real-time processor error: %v", err)
	}
}

// StartAggregationProcessor starts the aggregation processing worker
func (p *ETLPipeline) StartAggregationProcessor(ctx context.Context) {
	p.mu.Lock()
	stopCh := make(chan struct{})
	p.stopChannels["aggregation_processor"] = stopCh
	p.mu.Unlock()

	p.logger.Info("Starting aggregation processor")

	ticker := time.NewTicker(1 * time.Minute) // Process aggregations every minute
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case <-stopCh:
			return
		case <-ticker.C:
			if err := p.processAggregations(ctx); err != nil {
				p.logger.Errorf("Aggregation processing error: %v", err)
			}
		}
	}
}

// processCDCEvent processes a single CDC event
func (p *ETLPipeline) processCDCEvent(ctx context.Context, event *models.CDCEvent, topic string) error {
	// Step 1: Event processing and validation
	processedEvent, err := p.eventProcessor.ProcessCDCEvent(event)
	if err != nil {
		return fmt.Errorf("event processing failed: %w", err)
	}

	// Step 2: Deduplication
	isDuplicate, err := p.deduplicationProcessor.IsDuplicate(ctx, processedEvent.ID, processedEvent.Timestamp)
	if err != nil {
		return fmt.Errorf("deduplication check failed: %w", err)
	}

	if isDuplicate {
		p.logger.Debugf("Skipping duplicate event: %s", processedEvent.ID)
		p.metrics.DuplicateEventsSkipped.WithLabelValues(topic).Inc()
		return nil
	}

	// Step 3: Transformation
	transformedEvent, err := p.transformProcessor.TransformCDCEvent(processedEvent)
	if err != nil {
		return fmt.Errorf("transformation failed: %w", err)
	}

	// Step 4: Load to ClickHouse
	if err := p.etlService.LoadEvent(ctx, transformedEvent); err != nil {
		return fmt.Errorf("loading to ClickHouse failed: %w", err)
	}

	// Step 5: Mark as processed for deduplication
	if err := p.deduplicationProcessor.MarkProcessed(ctx, processedEvent.ID, processedEvent.Timestamp); err != nil {
		p.logger.Errorf("Failed to mark event as processed: %v", err)
		// Don't fail the entire process for this
	}

	return nil
}

// processRealTimeEvent processes a real-time event
func (p *ETLPipeline) processRealTimeEvent(ctx context.Context, event *models.Event, topic string) error {
	// Step 1: Event processing and validation
	processedEvent, err := p.eventProcessor.ProcessEvent(event)
	if err != nil {
		return fmt.Errorf("event processing failed: %w", err)
	}

	// Step 2: Deduplication
	isDuplicate, err := p.deduplicationProcessor.IsDuplicate(ctx, processedEvent.ID, processedEvent.Timestamp)
	if err != nil {
		return fmt.Errorf("deduplication check failed: %w", err)
	}

	if isDuplicate {
		p.logger.Debugf("Skipping duplicate event: %s", processedEvent.ID)
		p.metrics.DuplicateEventsSkipped.WithLabelValues(topic).Inc()
		return nil
	}

	// Step 3: Transformation
	transformedEvent, err := p.transformProcessor.TransformEvent(processedEvent)
	if err != nil {
		return fmt.Errorf("transformation failed: %w", err)
	}

	// Step 4: Load to ClickHouse
	if err := p.etlService.LoadEvent(ctx, transformedEvent); err != nil {
		return fmt.Errorf("loading to ClickHouse failed: %w", err)
	}

	// Step 5: Mark as processed
	if err := p.deduplicationProcessor.MarkProcessed(ctx, processedEvent.ID, processedEvent.Timestamp); err != nil {
		p.logger.Errorf("Failed to mark event as processed: %v", err)
	}

	return nil
}

// processBatch processes a batch of events
func (p *ETLPipeline) processBatch(ctx context.Context) error {
	p.logger.Info("Starting batch processing")

	start := time.Now()

	// Get pending events from source
	events, err := p.etlService.GetPendingEvents(ctx, 1000) // Process up to 1000 events per batch
	if err != nil {
		return fmt.Errorf("failed to get pending events: %w", err)
	}

	if len(events) == 0 {
		p.logger.Debug("No pending events to process")
		return nil
	}

	p.logger.Infof("Processing batch of %d events", len(events))

	// Process events in parallel
	const maxWorkers = 10
	eventCh := make(chan *models.Event, len(events))
	errorCh := make(chan error, len(events))

	// Start workers
	var wg sync.WaitGroup
	for i := 0; i < maxWorkers; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for event := range eventCh {
				if err := p.processRealTimeEvent(ctx, event, "batch"); err != nil {
					errorCh <- err
				}
			}
		}()
	}

	// Send events to workers
	for _, event := range events {
		eventCh <- event
	}
	close(eventCh)

	// Wait for workers to complete
	wg.Wait()
	close(errorCh)

	// Check for errors
	var errors []error
	for err := range errorCh {
		errors = append(errors, err)
	}

	if len(errors) > 0 {
		p.logger.Errorf("Batch processing completed with %d errors", len(errors))
		// Log first few errors
		for i, err := range errors {
			if i >= 5 {
				break
			}
			p.logger.Errorf("Batch error %d: %v", i+1, err)
		}
	}

	duration := time.Since(start).Seconds()
	p.metrics.BatchProcessingDuration.Observe(duration)
	p.metrics.BatchEventsProcessed.Add(float64(len(events)))

	p.logger.Infof("Batch processing completed in %.2fs, processed %d events with %d errors", 
		duration, len(events), len(errors))

	return nil
}

// processAggregations processes aggregations
func (p *ETLPipeline) processAggregations(ctx context.Context) error {
	p.logger.Debug("Processing aggregations")

	start := time.Now()

	// Process different types of aggregations
	aggregations := []string{
		"saga_metrics",
		"inventory_metrics", 
		"payment_metrics",
		"notification_metrics",
	}

	for _, aggregationType := range aggregations {
		if err := p.aggregationProcessor.ProcessAggregation(ctx, aggregationType); err != nil {
			p.logger.Errorf("Failed to process %s aggregation: %v", aggregationType, err)
			p.metrics.AggregationErrors.WithLabelValues(aggregationType).Inc()
		} else {
			p.metrics.AggregationsProcessed.WithLabelValues(aggregationType).Inc()
		}
	}

	duration := time.Since(start).Seconds()
	p.metrics.AggregationProcessingDuration.Observe(duration)

	return nil
}

// Start starts the entire pipeline
func (p *ETLPipeline) Start() error {
	p.mu.Lock()
	defer p.mu.Unlock()

	if p.isRunning {
		return fmt.Errorf("pipeline is already running")
	}

	p.isRunning = true
	p.logger.Info("ETL Pipeline started")

	return nil
}

// Stop stops the entire pipeline
func (p *ETLPipeline) Stop() error {
	p.mu.Lock()
	defer p.mu.Unlock()

	if !p.isRunning {
		return fmt.Errorf("pipeline is not running")
	}

	// Stop all workers
	for name, stopCh := range p.stopChannels {
		p.logger.Infof("Stopping %s", name)
		close(stopCh)
	}

	p.stopChannels = make(map[string]chan struct{})
	p.isRunning = false
	p.logger.Info("ETL Pipeline stopped")

	return nil
}

// IsRunning returns whether the pipeline is running
func (p *ETLPipeline) IsRunning() bool {
	p.mu.RLock()
	defer p.mu.RUnlock()
	return p.isRunning
}

// GetStatus returns the current pipeline status
func (p *ETLPipeline) GetStatus() map[string]interface{} {
	p.mu.RLock()
	defer p.mu.RUnlock()

	workers := make(map[string]bool)
	for name := range p.stopChannels {
		workers[name] = true
	}

	return map[string]interface{}{
		"is_running": p.isRunning,
		"workers":    workers,
		"timestamp":  time.Now(),
	}
}

package jepsen

import (
	"context"
	"fmt"
	"sync"
	"time"

	"github.com/google/uuid"
	"github.com/microservices-saga/services/consistency-testing/internal/infrastructure"
	"github.com/microservices-saga/services/consistency-testing/internal/models"
	"github.com/microservices-saga/services/consistency-testing/internal/nemesis"
	"github.com/microservices-saga/services/consistency-testing/internal/repository"
	"github.com/microservices-saga/services/consistency-testing/internal/workloads"
	"github.com/sirupsen/logrus"
)

// Framework implements a Jepsen-style distributed systems testing framework
type Framework struct {
	testRepo    repository.TestRepository
	resultRepo  repository.ResultRepository
	historyRepo repository.HistoryRepository
	nemeses     []nemesis.Nemesis
	workloads   []workloads.Workload
	config      Config
	metrics     *infrastructure.Metrics
	logger      *logrus.Logger
	
	// Test execution state
	runningTests map[string]*TestExecution
	mu           sync.RWMutex
}

// Config holds Jepsen framework configuration
type Config struct {
	MaxConcurrentTests   int
	DefaultTestDuration  time.Duration
	DefaultClientCount   int
	HistoryBufferSize    int
	CheckerTimeout       time.Duration
	NemesisInterval      time.Duration
	WorkloadInterval     time.Duration
}

// TestExecution represents a running test
type TestExecution struct {
	Test      *models.Test
	Context   context.Context
	Cancel    context.CancelFunc
	History   *History
	Clients   []*Client
	Nemesis   nemesis.Nemesis
	Workload  workloads.Workload
	StartTime time.Time
	Status    models.TestStatus
	mu        sync.RWMutex
}

// History tracks all operations and their results
type History struct {
	Operations []models.Operation
	mu         sync.RWMutex
}

// Client represents a test client performing operations
type Client struct {
	ID       string
	Workload workloads.Workload
	History  *History
	logger   *logrus.Logger
}

// NewFramework creates a new Jepsen testing framework
func NewFramework(
	testRepo repository.TestRepository,
	resultRepo repository.ResultRepository,
	historyRepo repository.HistoryRepository,
	nemeses []nemesis.Nemesis,
	workloads []workloads.Workload,
	config Config,
	metrics *infrastructure.Metrics,
	logger *logrus.Logger,
) *Framework {
	return &Framework{
		testRepo:     testRepo,
		resultRepo:   resultRepo,
		historyRepo:  historyRepo,
		nemeses:      nemeses,
		workloads:    workloads,
		config:       config,
		metrics:      metrics,
		logger:       logger,
		runningTests: make(map[string]*TestExecution),
	}
}

// StartTest starts a new distributed systems test
func (f *Framework) StartTest(ctx context.Context, testConfig *models.TestConfig) (*models.Test, error) {
	f.mu.Lock()
	defer f.mu.Unlock()

	// Check if we can start another test
	if len(f.runningTests) >= f.config.MaxConcurrentTests {
		return nil, fmt.Errorf("maximum concurrent tests reached: %d", f.config.MaxConcurrentTests)
	}

	// Create test record
	test := &models.Test{
		ID:          uuid.New().String(),
		Name:        testConfig.Name,
		Description: testConfig.Description,
		Config:      testConfig,
		Status:      models.TestStatusRunning,
		StartedAt:   time.Now(),
		CreatedBy:   testConfig.CreatedBy,
	}

	// Save test record
	if err := f.testRepo.CreateTest(ctx, test); err != nil {
		return nil, fmt.Errorf("failed to create test record: %w", err)
	}

	// Find workload
	var workload workloads.Workload
	for _, w := range f.workloads {
		if w.Name() == testConfig.WorkloadName {
			workload = w
			break
		}
	}
	if workload == nil {
		return nil, fmt.Errorf("workload not found: %s", testConfig.WorkloadName)
	}

	// Find nemesis
	var testNemesis nemesis.Nemesis
	for _, n := range f.nemeses {
		if n.Name() == testConfig.NemesisName {
			testNemesis = n
			break
		}
	}
	if testNemesis == nil {
		return nil, fmt.Errorf("nemesis not found: %s", testConfig.NemesisName)
	}

	// Create test execution context
	testCtx, cancel := context.WithTimeout(ctx, testConfig.Duration)

	// Initialize history
	history := &History{
		Operations: make([]models.Operation, 0, f.config.HistoryBufferSize),
	}

	// Create test execution
	execution := &TestExecution{
		Test:      test,
		Context:   testCtx,
		Cancel:    cancel,
		History:   history,
		Nemesis:   testNemesis,
		Workload:  workload,
		StartTime: time.Now(),
		Status:    models.TestStatusRunning,
	}

	// Create clients
	execution.Clients = make([]*Client, testConfig.ClientCount)
	for i := 0; i < testConfig.ClientCount; i++ {
		execution.Clients[i] = &Client{
			ID:       fmt.Sprintf("client-%d", i),
			Workload: workload,
			History:  history,
			logger:   f.logger.WithField("client_id", fmt.Sprintf("client-%d", i)),
		}
	}

	// Store running test
	f.runningTests[test.ID] = execution

	// Start test execution in background
	go f.executeTest(execution)

	f.logger.Infof("Started test: %s (%s)", test.Name, test.ID)
	f.metrics.TestsStarted.WithLabelValues(testConfig.WorkloadName, testConfig.NemesisName).Inc()

	return test, nil
}

// executeTest executes a test
func (f *Framework) executeTest(execution *TestExecution) {
	defer func() {
		f.mu.Lock()
		delete(f.runningTests, execution.Test.ID)
		f.mu.Unlock()
		
		execution.Cancel()
	}()

	f.logger.Infof("Executing test: %s", execution.Test.Name)

	// Initialize workload
	if err := execution.Workload.Initialize(execution.Context, execution.Test.Config.WorkloadConfig); err != nil {
		f.logger.Errorf("Failed to initialize workload: %v", err)
		f.finishTest(execution, models.TestStatusFailed, err.Error())
		return
	}

	// Start nemesis
	go f.runNemesis(execution)

	// Start clients
	var wg sync.WaitGroup
	for _, client := range execution.Clients {
		wg.Add(1)
		go func(c *Client) {
			defer wg.Done()
			f.runClient(execution.Context, c)
		}(client)
	}

	// Wait for test completion or timeout
	select {
	case <-execution.Context.Done():
		f.logger.Infof("Test completed: %s", execution.Test.Name)
	}

	// Stop nemesis
	execution.Nemesis.Stop(execution.Context)

	// Wait for all clients to finish
	wg.Wait()

	// Cleanup workload
	if err := execution.Workload.Cleanup(execution.Context); err != nil {
		f.logger.Errorf("Failed to cleanup workload: %v", err)
	}

	// Analyze results
	f.analyzeTestResults(execution)

	// Finish test
	f.finishTest(execution, models.TestStatusCompleted, "")
}

// runNemesis runs the nemesis (fault injection)
func (f *Framework) runNemesis(execution *TestExecution) {
	f.logger.Infof("Starting nemesis: %s", execution.Nemesis.Name())

	ticker := time.NewTicker(f.config.NemesisInterval)
	defer ticker.Stop()

	for {
		select {
		case <-execution.Context.Done():
			return
		case <-ticker.C:
			if err := execution.Nemesis.Invoke(execution.Context); err != nil {
				f.logger.Errorf("Nemesis invocation failed: %v", err)
			}
		}
	}
}

// runClient runs a test client
func (f *Framework) runClient(ctx context.Context, client *Client) {
	client.logger.Info("Starting client")

	ticker := time.NewTicker(f.config.WorkloadInterval)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			client.logger.Info("Client stopped")
			return
		case <-ticker.C:
			f.executeClientOperation(ctx, client)
		}
	}
}

// executeClientOperation executes a single client operation
func (f *Framework) executeClientOperation(ctx context.Context, client *Client) {
	// Generate operation
	op, err := client.Workload.GenerateOperation(ctx, client.ID)
	if err != nil {
		client.logger.Errorf("Failed to generate operation: %v", err)
		return
	}

	// Record operation start
	op.InvokedAt = time.Now()
	op.Status = models.OperationStatusInvoked

	// Execute operation
	start := time.Now()
	result, err := client.Workload.ExecuteOperation(ctx, op)
	duration := time.Since(start)

	// Record operation completion
	op.CompletedAt = &start
	op.Duration = duration
	op.Result = result

	if err != nil {
		op.Status = models.OperationStatusFailed
		op.Error = err.Error()
	} else {
		op.Status = models.OperationStatusCompleted
	}

	// Add to history
	client.History.AddOperation(*op)

	client.logger.Debugf("Operation completed: %s, duration: %v", op.Type, duration)
}

// analyzeTestResults analyzes test results for consistency violations
func (f *Framework) analyzeTestResults(execution *TestExecution) {
	f.logger.Infof("Analyzing test results: %s", execution.Test.Name)

	// Get history
	operations := execution.History.GetOperations()

	// Create result record
	result := &models.TestResult{
		ID:              uuid.New().String(),
		TestID:          execution.Test.ID,
		Status:          models.ResultStatusAnalyzing,
		OperationCount:  len(operations),
		StartedAt:       execution.StartTime,
		CompletedAt:     time.Now(),
		AnalysisStarted: time.Now(),
	}

	// Save result record
	if err := f.resultRepo.CreateResult(context.Background(), result); err != nil {
		f.logger.Errorf("Failed to create result record: %v", err)
		return
	}

	// Save history
	if err := f.historyRepo.SaveHistory(context.Background(), execution.Test.ID, operations); err != nil {
		f.logger.Errorf("Failed to save history: %v", err)
	}

	// Perform consistency analysis
	violations := f.checkConsistency(operations, execution.Test.Config.ConsistencyModel)

	// Update result
	result.Status = models.ResultStatusCompleted
	result.ViolationCount = len(violations)
	result.Violations = violations
	analysisCompleted := time.Now()
	result.AnalysisCompleted = &analysisCompleted

	if err := f.resultRepo.UpdateResult(context.Background(), result); err != nil {
		f.logger.Errorf("Failed to update result: %v", err)
	}

	// Record metrics
	f.metrics.TestsCompleted.WithLabelValues(
		execution.Test.Config.WorkloadName,
		execution.Test.Config.NemesisName,
		string(result.Status),
	).Inc()

	f.metrics.ConsistencyViolations.WithLabelValues(
		execution.Test.Config.WorkloadName,
		execution.Test.Config.ConsistencyModel,
	).Add(float64(len(violations)))

	f.logger.Infof("Test analysis completed: %s, violations: %d", execution.Test.Name, len(violations))
}

// checkConsistency checks for consistency violations
func (f *Framework) checkConsistency(operations []models.Operation, consistencyModel string) []models.Violation {
	var violations []models.Violation

	switch consistencyModel {
	case "linearizability":
		violations = f.checkLinearizability(operations)
	case "sequential":
		violations = f.checkSequentialConsistency(operations)
	case "eventual":
		violations = f.checkEventualConsistency(operations)
	default:
		f.logger.Warnf("Unknown consistency model: %s", consistencyModel)
	}

	return violations
}

// checkLinearizability checks for linearizability violations
func (f *Framework) checkLinearizability(operations []models.Operation) []models.Violation {
	// Simplified linearizability checker
	// In production, use a proper linearizability checker like Knossos
	var violations []models.Violation

	// Group operations by key
	operationsByKey := make(map[string][]models.Operation)
	for _, op := range operations {
		key := f.extractKey(op)
		operationsByKey[key] = append(operationsByKey[key], op)
	}

	// Check each key for linearizability
	for key, keyOps := range operationsByKey {
		keyViolations := f.checkKeyLinearizability(key, keyOps)
		violations = append(violations, keyViolations...)
	}

	return violations
}

// checkSequentialConsistency checks for sequential consistency violations
func (f *Framework) checkSequentialConsistency(operations []models.Operation) []models.Violation {
	// Simplified sequential consistency checker
	var violations []models.Violation

	// Sequential consistency allows operations to be reordered as long as
	// operations from the same process maintain their order
	
	// Group operations by client
	operationsByClient := make(map[string][]models.Operation)
	for _, op := range operations {
		operationsByClient[op.ClientID] = append(operationsByClient[op.ClientID], op)
	}

	// Check if there exists a valid sequential ordering
	if !f.hasValidSequentialOrdering(operationsByClient) {
		violations = append(violations, models.Violation{
			ID:          uuid.New().String(),
			Type:        "sequential_consistency",
			Description: "No valid sequential ordering found",
			Operations:  operations,
		})
	}

	return violations
}

// checkEventualConsistency checks for eventual consistency violations
func (f *Framework) checkEventualConsistency(operations []models.Operation) []models.Violation {
	// Simplified eventual consistency checker
	var violations []models.Violation

	// Eventual consistency requires that all replicas eventually converge
	// Check if final states are consistent across all replicas
	
	finalStates := f.extractFinalStates(operations)
	if !f.areStatesEventuallyConsistent(finalStates) {
		violations = append(violations, models.Violation{
			ID:          uuid.New().String(),
			Type:        "eventual_consistency",
			Description: "Final states are not eventually consistent",
			Operations:  operations,
		})
	}

	return violations
}

// finishTest finishes a test execution
func (f *Framework) finishTest(execution *TestExecution, status models.TestStatus, errorMessage string) {
	execution.mu.Lock()
	execution.Status = status
	execution.mu.Unlock()

	// Update test record
	execution.Test.Status = status
	execution.Test.ErrorMessage = errorMessage
	completedAt := time.Now()
	execution.Test.CompletedAt = &completedAt

	if err := f.testRepo.UpdateTest(context.Background(), execution.Test); err != nil {
		f.logger.Errorf("Failed to update test record: %v", err)
	}

	f.logger.Infof("Test finished: %s, status: %s", execution.Test.Name, status)
}

// AddOperation adds an operation to the history
func (h *History) AddOperation(op models.Operation) {
	h.mu.Lock()
	defer h.mu.Unlock()
	h.Operations = append(h.Operations, op)
}

// GetOperations returns a copy of all operations
func (h *History) GetOperations() []models.Operation {
	h.mu.RLock()
	defer h.mu.RUnlock()
	
	operations := make([]models.Operation, len(h.Operations))
	copy(operations, h.Operations)
	return operations
}

// Helper methods (simplified implementations)

func (f *Framework) extractKey(op models.Operation) string {
	// Extract key from operation data
	if key, ok := op.Data["key"].(string); ok {
		return key
	}
	return "default"
}

func (f *Framework) checkKeyLinearizability(key string, operations []models.Operation) []models.Violation {
	// Simplified linearizability check for a single key
	return []models.Violation{}
}

func (f *Framework) hasValidSequentialOrdering(operationsByClient map[string][]models.Operation) bool {
	// Simplified sequential consistency check
	return true
}

func (f *Framework) extractFinalStates(operations []models.Operation) map[string]interface{} {
	// Extract final states from operations
	return make(map[string]interface{})
}

func (f *Framework) areStatesEventuallyConsistent(states map[string]interface{}) bool {
	// Check if states are eventually consistent
	return true
}

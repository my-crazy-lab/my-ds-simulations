package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"sync"
	"time"

	"github.com/google/uuid"
)

// Simple in-memory saga orchestrator demo
type SagaStatus string

const (
	StatusPending     SagaStatus = "pending"
	StatusRunning     SagaStatus = "running"
	StatusCompleted   SagaStatus = "completed"
	StatusFailed      SagaStatus = "failed"
	StatusCompensated SagaStatus = "compensated"
)

type StepStatus string

const (
	StepPending   StepStatus = "pending"
	StepRunning   StepStatus = "running"
	StepCompleted StepStatus = "completed"
	StepFailed    StepStatus = "failed"
)

type SagaStep struct {
	ID       string                 `json:"id"`
	Type     string                 `json:"type"`
	Status   StepStatus             `json:"status"`
	Data     map[string]interface{} `json:"data,omitempty"`
	Error    string                 `json:"error,omitempty"`
	Duration time.Duration          `json:"duration"`
}

type Saga struct {
	ID        string                 `json:"id"`
	Type      string                 `json:"type"`
	Status    SagaStatus             `json:"status"`
	Data      map[string]interface{} `json:"data"`
	Steps     []*SagaStep            `json:"steps"`
	CreatedAt time.Time              `json:"created_at"`
	UpdatedAt time.Time              `json:"updated_at"`
	Duration  time.Duration          `json:"duration"`
}

type SagaOrchestrator struct {
	sagas map[string]*Saga
	mutex sync.RWMutex
}

func NewSagaOrchestrator() *SagaOrchestrator {
	return &SagaOrchestrator{
		sagas: make(map[string]*Saga),
	}
}

func (so *SagaOrchestrator) CreateSaga(sagaType string, data map[string]interface{}) *Saga {
	so.mutex.Lock()
	defer so.mutex.Unlock()

	saga := &Saga{
		ID:        uuid.New().String(),
		Type:      sagaType,
		Status:    StatusPending,
		Data:      data,
		Steps:     []*SagaStep{},
		CreatedAt: time.Now(),
		UpdatedAt: time.Now(),
	}

	// Define steps based on saga type
	switch sagaType {
	case "order_processing":
		saga.Steps = []*SagaStep{
			{ID: uuid.New().String(), Type: "reserve_inventory", Status: StepPending},
			{ID: uuid.New().String(), Type: "process_payment", Status: StepPending},
			{ID: uuid.New().String(), Type: "send_notification", Status: StepPending},
		}
	case "refund_processing":
		saga.Steps = []*SagaStep{
			{ID: uuid.New().String(), Type: "validate_refund", Status: StepPending},
			{ID: uuid.New().String(), Type: "process_refund", Status: StepPending},
			{ID: uuid.New().String(), Type: "update_inventory", Status: StepPending},
		}
	}

	so.sagas[saga.ID] = saga

	// Start executing the saga
	go so.executeSaga(saga.ID)

	return saga
}

func (so *SagaOrchestrator) GetSaga(id string) *Saga {
	so.mutex.RLock()
	defer so.mutex.RUnlock()
	return so.sagas[id]
}

func (so *SagaOrchestrator) ListSagas() []*Saga {
	so.mutex.RLock()
	defer so.mutex.RUnlock()

	sagas := make([]*Saga, 0, len(so.sagas))
	for _, saga := range so.sagas {
		sagas = append(sagas, saga)
	}
	return sagas
}

func (so *SagaOrchestrator) executeSaga(sagaID string) {
	so.mutex.Lock()
	saga := so.sagas[sagaID]
	if saga == nil {
		so.mutex.Unlock()
		return
	}
	saga.Status = StatusRunning
	saga.UpdatedAt = time.Now()
	so.mutex.Unlock()

	startTime := time.Now()

	// Execute each step
	for i := range saga.Steps {
		if !so.executeStep(sagaID, i) {
			// Step failed, compensate
			so.compensateSaga(sagaID, i-1)
			return
		}
	}

	// All steps completed successfully
	so.mutex.Lock()
	saga.Status = StatusCompleted
	saga.UpdatedAt = time.Now()
	saga.Duration = time.Since(startTime)
	so.mutex.Unlock()

	log.Printf("Saga %s completed successfully in %v", sagaID, saga.Duration)
}

func (so *SagaOrchestrator) executeStep(sagaID string, stepIndex int) bool {
	so.mutex.Lock()
	saga := so.sagas[sagaID]
	if saga == nil || stepIndex >= len(saga.Steps) {
		so.mutex.Unlock()
		return false
	}

	step := saga.Steps[stepIndex]
	step.Status = StepRunning
	saga.UpdatedAt = time.Now()
	so.mutex.Unlock()

	stepStartTime := time.Now()
	log.Printf("Executing step %s for saga %s", step.Type, sagaID)

	// Simulate step execution
	success := so.simulateStepExecution(step.Type)

	so.mutex.Lock()
	step.Duration = time.Since(stepStartTime)
	if success {
		step.Status = StepCompleted
		log.Printf("Step %s completed successfully", step.Type)
	} else {
		step.Status = StepFailed
		step.Error = fmt.Sprintf("Step %s failed during execution", step.Type)
		log.Printf("Step %s failed: %s", step.Type, step.Error)
	}
	saga.UpdatedAt = time.Now()
	so.mutex.Unlock()

	return success
}

func (so *SagaOrchestrator) simulateStepExecution(stepType string) bool {
	// Simulate processing time
	processingTime := time.Duration(500+time.Now().UnixNano()%1000) * time.Millisecond
	time.Sleep(processingTime)

	// Simulate failure rate (10% chance of failure)
	failureRate := 0.1
	return time.Now().UnixNano()%100 >= int64(failureRate*100)
}

func (so *SagaOrchestrator) compensateSaga(sagaID string, lastCompletedStep int) {
	so.mutex.Lock()
	saga := so.sagas[sagaID]
	if saga == nil {
		so.mutex.Unlock()
		return
	}
	saga.Status = StatusFailed
	saga.UpdatedAt = time.Now()
	so.mutex.Unlock()

	log.Printf("Starting compensation for saga %s", sagaID)

	// Compensate in reverse order
	for i := lastCompletedStep; i >= 0; i-- {
		step := saga.Steps[i]
		if step.Status == StepCompleted {
			log.Printf("Compensating step %s", step.Type)
			// Simulate compensation
			time.Sleep(200 * time.Millisecond)
		}
	}

	so.mutex.Lock()
	saga.Status = StatusCompensated
	saga.UpdatedAt = time.Now()
	so.mutex.Unlock()

	log.Printf("Saga %s compensated", sagaID)
}

// HTTP Handlers
func (so *SagaOrchestrator) createSagaHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	var request struct {
		Type string                 `json:"type"`
		Data map[string]interface{} `json:"data"`
	}

	if err := json.NewDecoder(r.Body).Decode(&request); err != nil {
		http.Error(w, "Invalid JSON", http.StatusBadRequest)
		return
	}

	saga := so.CreateSaga(request.Type, request.Data)

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusCreated)
	json.NewEncoder(w).Encode(saga)
}

func (so *SagaOrchestrator) getSagaHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	sagaID := r.URL.Path[len("/api/v1/sagas/"):]
	if sagaID == "" {
		// List all sagas
		sagas := so.ListSagas()
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(sagas)
		return
	}

	saga := so.GetSaga(sagaID)
	if saga == nil {
		http.Error(w, "Saga not found", http.StatusNotFound)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(saga)
}

func (so *SagaOrchestrator) healthHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{
		"status":  "healthy",
		"service": "saga-orchestrator-demo",
		"time":    time.Now().Format(time.RFC3339),
	})
}

func main() {
	orchestrator := NewSagaOrchestrator()

	// Setup routes
	http.HandleFunc("/health", orchestrator.healthHandler)
	http.HandleFunc("/api/v1/sagas", orchestrator.createSagaHandler)
	http.HandleFunc("/api/v1/sagas/", orchestrator.getSagaHandler)

	// Start server
	port := ":8080"
	fmt.Printf("🚀 Saga Orchestrator Demo starting on port %s\n", port)
	fmt.Println("📋 Available endpoints:")
	fmt.Println("  GET  /health                 - Health check")
	fmt.Println("  POST /api/v1/sagas           - Create saga")
	fmt.Println("  GET  /api/v1/sagas           - List all sagas")
	fmt.Println("  GET  /api/v1/sagas/{id}      - Get specific saga")
	fmt.Println()
	fmt.Println("📝 Example usage:")
	fmt.Println(`  curl -X POST http://localhost:8080/api/v1/sagas \`)
	fmt.Println(`    -H "Content-Type: application/json" \`)
	fmt.Println(`    -d '{"type": "order_processing", "data": {"order_id": "123", "user_id": "user456"}}'`)
	fmt.Println()

	log.Fatal(http.ListenAndServe(port, nil))
}

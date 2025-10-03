package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"sort"
	"strconv"
	"sync"
	"syscall"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	clientv3 "go.etcd.io/etcd/client/v3"
)

// Job represents a job in the scheduler
type Job struct {
	ID          string            `json:"id"`
	Name        string            `json:"name"`
	TenantID    string            `json:"tenant_id"`
	Image       string            `json:"image"`
	Command     []string          `json:"command,omitempty"`
	Resources   ResourceRequest   `json:"resources"`
	Priority    int               `json:"priority"`
	Status      string            `json:"status"`
	CreatedAt   time.Time         `json:"created_at"`
	StartedAt   *time.Time        `json:"started_at,omitempty"`
	CompletedAt *time.Time        `json:"completed_at,omitempty"`
	NodeID      string            `json:"node_id,omitempty"`
	RetryPolicy RetryPolicy       `json:"retry_policy"`
	Labels      map[string]string `json:"labels,omitempty"`
	Annotations map[string]string `json:"annotations,omitempty"`
	Deadline    *time.Time        `json:"deadline,omitempty"`
}

// ResourceRequest defines resource requirements for a job
type ResourceRequest struct {
	CPU     string `json:"cpu"`
	Memory  string `json:"memory"`
	GPU     string `json:"gpu,omitempty"`
	Storage string `json:"storage,omitempty"`
}

// RetryPolicy defines retry behavior for failed jobs
type RetryPolicy struct {
	MaxRetries    int    `json:"max_retries"`
	BackoffPolicy string `json:"backoff_policy"`
	RetryCount    int    `json:"retry_count"`
}

// Tenant represents a tenant in the multi-tenant system
type Tenant struct {
	ID            string                 `json:"id"`
	Name          string                 `json:"name"`
	ResourceQuota ResourceQuota          `json:"resource_quota"`
	PriorityClass string                 `json:"priority_class"`
	Policies      map[string]interface{} `json:"policies"`
	CreatedAt     time.Time              `json:"created_at"`
}

// ResourceQuota defines resource limits for a tenant
type ResourceQuota struct {
	CPU     string `json:"cpu"`
	Memory  string `json:"memory"`
	GPU     string `json:"gpu,omitempty"`
	Storage string `json:"storage,omitempty"`
	Jobs    int    `json:"jobs"`
}

// WorkerNode represents a worker node in the cluster
type WorkerNode struct {
	ID            string            `json:"id"`
	Address       string            `json:"address"`
	Status        string            `json:"status"`
	Resources     NodeResources     `json:"resources"`
	UsedResources NodeResources     `json:"used_resources"`
	Labels        map[string]string `json:"labels"`
	LastHeartbeat time.Time         `json:"last_heartbeat"`
}

// NodeResources represents available resources on a node
type NodeResources struct {
	CPU     float64 `json:"cpu"`
	Memory  int64   `json:"memory"`
	GPU     int     `json:"gpu"`
	Storage int64   `json:"storage"`
}

// SchedulerController manages job scheduling and resource allocation
type SchedulerController struct {
	etcdClient            *clientv3.Client
	jobs                  map[string]*Job
	tenants               map[string]*Tenant
	nodes                 map[string]*WorkerNode
	jobQueue              []*Job
	mutex                 sync.RWMutex
	metrics               *SchedulerMetrics
	fairShareEnabled      bool
	preemptionEnabled     bool
	gangSchedulingEnabled bool
}

// SchedulerMetrics contains Prometheus metrics
type SchedulerMetrics struct {
	JobsTotal           prometheus.Counter
	JobsScheduled       prometheus.Counter
	JobsFailed          prometheus.Counter
	SchedulingLatency   prometheus.Histogram
	QueueDepth          prometheus.Gauge
	ResourceUtilization prometheus.GaugeVec
}

func NewSchedulerController() *SchedulerController {
	// Initialize etcd client
	etcdEndpoints := []string{"etcd-1:2379", "etcd-2:2379", "etcd-3:2379"}
	if endpoints := os.Getenv("ETCD_ENDPOINTS"); endpoints != "" {
		etcdEndpoints = []string{endpoints}
	}

	etcdClient, err := clientv3.New(clientv3.Config{
		Endpoints:   etcdEndpoints,
		DialTimeout: 5 * time.Second,
	})
	if err != nil {
		log.Fatalf("Failed to connect to etcd: %v", err)
	}

	// Initialize metrics
	metrics := &SchedulerMetrics{
		JobsTotal: prometheus.NewCounter(prometheus.CounterOpts{
			Name: "scheduler_jobs_total",
			Help: "Total number of jobs submitted",
		}),
		JobsScheduled: prometheus.NewCounter(prometheus.CounterOpts{
			Name: "scheduler_jobs_scheduled_total",
			Help: "Total number of jobs scheduled",
		}),
		JobsFailed: prometheus.NewCounter(prometheus.CounterOpts{
			Name: "scheduler_jobs_failed_total",
			Help: "Total number of jobs failed",
		}),
		SchedulingLatency: prometheus.NewHistogram(prometheus.HistogramOpts{
			Name:    "scheduler_scheduling_latency_seconds",
			Help:    "Latency of job scheduling decisions",
			Buckets: prometheus.DefBuckets,
		}),
		QueueDepth: prometheus.NewGauge(prometheus.GaugeOpts{
			Name: "scheduler_queue_depth",
			Help: "Current depth of job queue",
		}),
		ResourceUtilization: *prometheus.NewGaugeVec(prometheus.GaugeOpts{
			Name: "scheduler_resource_utilization",
			Help: "Resource utilization by type",
		}, []string{"resource_type", "node_id"}),
	}

	// Register metrics
	prometheus.MustRegister(metrics.JobsTotal)
	prometheus.MustRegister(metrics.JobsScheduled)
	prometheus.MustRegister(metrics.JobsFailed)
	prometheus.MustRegister(metrics.SchedulingLatency)
	prometheus.MustRegister(metrics.QueueDepth)
	prometheus.MustRegister(metrics.ResourceUtilization)

	return &SchedulerController{
		etcdClient:            etcdClient,
		jobs:                  make(map[string]*Job),
		tenants:               make(map[string]*Tenant),
		nodes:                 make(map[string]*WorkerNode),
		jobQueue:              make([]*Job, 0),
		metrics:               metrics,
		fairShareEnabled:      os.Getenv("FAIR_SHARE_ENABLED") == "true",
		preemptionEnabled:     os.Getenv("PREEMPTION_ENABLED") == "true",
		gangSchedulingEnabled: os.Getenv("GANG_SCHEDULING_ENABLED") == "true",
	}
}

// SubmitJob handles job submission
func (sc *SchedulerController) SubmitJob(c *gin.Context) {
	var job Job
	if err := c.ShouldBindJSON(&job); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	// Get tenant ID from header
	tenantID := c.GetHeader("X-Tenant-ID")
	if tenantID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "X-Tenant-ID header required"})
		return
	}

	// Validate tenant exists and has quota
	sc.mutex.RLock()
	tenant, exists := sc.tenants[tenantID]
	sc.mutex.RUnlock()

	if !exists {
		c.JSON(http.StatusForbidden, gin.H{"error": "Tenant not found"})
		return
	}

	// Check resource quota
	if !sc.checkResourceQuota(tenant, &job) {
		c.JSON(http.StatusForbidden, gin.H{"error": "Resource quota exceeded"})
		return
	}

	// Initialize job
	job.ID = uuid.New().String()
	job.TenantID = tenantID
	job.Status = "pending"
	job.CreatedAt = time.Now()
	job.RetryPolicy.RetryCount = 0

	// Set default priority based on tenant priority class
	if job.Priority == 0 {
		job.Priority = sc.getTenantPriority(tenant.PriorityClass)
	}

	// Store job
	sc.mutex.Lock()
	sc.jobs[job.ID] = &job
	sc.jobQueue = append(sc.jobQueue, &job)
	sc.mutex.Unlock()

	// Update metrics
	sc.metrics.JobsTotal.Inc()
	sc.metrics.QueueDepth.Set(float64(len(sc.jobQueue)))

	// Store in etcd for persistence
	jobData, _ := json.Marshal(job)
	sc.etcdClient.Put(context.Background(), fmt.Sprintf("/scheduler/jobs/%s", job.ID), string(jobData))

	c.JSON(http.StatusCreated, job)
}

// GetJob retrieves job information
func (sc *SchedulerController) GetJob(c *gin.Context) {
	jobID := c.Param("id")
	tenantID := c.GetHeader("X-Tenant-ID")

	sc.mutex.RLock()
	job, exists := sc.jobs[jobID]
	sc.mutex.RUnlock()

	if !exists {
		c.JSON(http.StatusNotFound, gin.H{"error": "Job not found"})
		return
	}

	// Check tenant access
	if job.TenantID != tenantID {
		c.JSON(http.StatusForbidden, gin.H{"error": "Access denied"})
		return
	}

	c.JSON(http.StatusOK, job)
}

// ListJobs lists jobs for a tenant
func (sc *SchedulerController) ListJobs(c *gin.Context) {
	tenantID := c.GetHeader("X-Tenant-ID")
	if tenantID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "X-Tenant-ID header required"})
		return
	}

	sc.mutex.RLock()
	var tenantJobs []*Job
	for _, job := range sc.jobs {
		if job.TenantID == tenantID {
			tenantJobs = append(tenantJobs, job)
		}
	}
	sc.mutex.RUnlock()

	c.JSON(http.StatusOK, gin.H{"jobs": tenantJobs})
}

// ScheduleJobs implements the main scheduling logic
func (sc *SchedulerController) ScheduleJobs() {
	ticker := time.NewTicker(5 * time.Second)
	defer ticker.Stop()

	for range ticker.C {
		sc.runSchedulingCycle()
	}
}

func (sc *SchedulerController) runSchedulingCycle() {
	start := time.Now()
	defer func() {
		sc.metrics.SchedulingLatency.Observe(time.Since(start).Seconds())
	}()

	sc.mutex.Lock()
	defer sc.mutex.Unlock()

	if len(sc.jobQueue) == 0 {
		return
	}

	// Sort jobs by priority and fair share
	sc.sortJobQueue()

	// Try to schedule jobs
	scheduledJobs := 0
	for i := 0; i < len(sc.jobQueue); i++ {
		job := sc.jobQueue[i]
		if job.Status != "pending" {
			continue
		}

		// Find suitable node
		node := sc.findSuitableNode(job)
		if node == nil {
			// Try preemption if enabled
			if sc.preemptionEnabled {
				node = sc.tryPreemption(job)
			}
			if node == nil {
				continue
			}
		}

		// Schedule job
		if sc.scheduleJobOnNode(job, node) {
			scheduledJobs++
			sc.metrics.JobsScheduled.Inc()

			// Remove from queue
			sc.jobQueue = append(sc.jobQueue[:i], sc.jobQueue[i+1:]...)
			i-- // Adjust index after removal
		}
	}

	sc.metrics.QueueDepth.Set(float64(len(sc.jobQueue)))

	if scheduledJobs > 0 {
		log.Printf("Scheduled %d jobs in scheduling cycle", scheduledJobs)
	}
}

func (sc *SchedulerController) sortJobQueue() {
	if sc.fairShareEnabled {
		sc.sortByFairShare()
	} else {
		sc.sortByPriority()
	}
}

func (sc *SchedulerController) sortByPriority() {
	sort.Slice(sc.jobQueue, func(i, j int) bool {
		jobI, jobJ := sc.jobQueue[i], sc.jobQueue[j]

		// Higher priority first
		if jobI.Priority != jobJ.Priority {
			return jobI.Priority > jobJ.Priority
		}

		// Earlier submission time for same priority
		return jobI.CreatedAt.Before(jobJ.CreatedAt)
	})
}

func (sc *SchedulerController) sortByFairShare() {
	// Calculate fair share ratios for each tenant
	tenantShares := sc.calculateFairShares()

	sort.Slice(sc.jobQueue, func(i, j int) bool {
		jobI, jobJ := sc.jobQueue[i], sc.jobQueue[j]

		shareI := tenantShares[jobI.TenantID]
		shareJ := tenantShares[jobJ.TenantID]

		// Lower share ratio gets higher priority (more starved)
		if shareI != shareJ {
			return shareI < shareJ
		}

		// Fall back to job priority
		if jobI.Priority != jobJ.Priority {
			return jobI.Priority > jobJ.Priority
		}

		return jobI.CreatedAt.Before(jobJ.CreatedAt)
	})
}

func (sc *SchedulerController) calculateFairShares() map[string]float64 {
	tenantShares := make(map[string]float64)
	tenantUsage := make(map[string]int)
	tenantWeights := make(map[string]int)

	// Calculate current usage and weights
	for _, job := range sc.jobs {
		if job.Status == "running" {
			tenantUsage[job.TenantID]++
		}
	}

	for tenantID, tenant := range sc.tenants {
		weight := sc.getTenantWeight(tenant.PriorityClass)
		tenantWeights[tenantID] = weight

		usage := tenantUsage[tenantID]
		if weight > 0 {
			tenantShares[tenantID] = float64(usage) / float64(weight)
		}
	}

	return tenantShares
}

func (sc *SchedulerController) findSuitableNode(job *Job) *WorkerNode {
	for _, node := range sc.nodes {
		if node.Status != "ready" {
			continue
		}

		if sc.nodeHasResources(node, job) {
			return node
		}
	}
	return nil
}

func (sc *SchedulerController) nodeHasResources(node *WorkerNode, job *Job) bool {
	// Parse resource requirements
	cpuReq := sc.parseCPU(job.Resources.CPU)
	memReq := sc.parseMemory(job.Resources.Memory)
	gpuReq := sc.parseGPU(job.Resources.GPU)

	// Check available resources
	availCPU := node.Resources.CPU - node.UsedResources.CPU
	availMem := node.Resources.Memory - node.UsedResources.Memory
	availGPU := node.Resources.GPU - node.UsedResources.GPU

	return availCPU >= cpuReq && availMem >= memReq && availGPU >= gpuReq
}

func (sc *SchedulerController) scheduleJobOnNode(job *Job, node *WorkerNode) bool {
	// Update job status
	job.Status = "scheduled"
	job.NodeID = node.ID
	now := time.Now()
	job.StartedAt = &now

	// Update node resources
	cpuReq := sc.parseCPU(job.Resources.CPU)
	memReq := sc.parseMemory(job.Resources.Memory)
	gpuReq := sc.parseGPU(job.Resources.GPU)

	node.UsedResources.CPU += cpuReq
	node.UsedResources.Memory += memReq
	node.UsedResources.GPU += gpuReq

	// Update metrics
	sc.updateResourceUtilizationMetrics(node)

	// Persist changes
	jobData, _ := json.Marshal(job)
	sc.etcdClient.Put(context.Background(), fmt.Sprintf("/scheduler/jobs/%s", job.ID), string(jobData))

	nodeData, _ := json.Marshal(node)
	sc.etcdClient.Put(context.Background(), fmt.Sprintf("/scheduler/nodes/%s", node.ID), string(nodeData))

	log.Printf("Scheduled job %s on node %s", job.ID, node.ID)
	return true
}

func (sc *SchedulerController) tryPreemption(job *Job) *WorkerNode {
	// Find nodes with lower priority jobs that can be preempted
	for _, node := range sc.nodes {
		if node.Status != "ready" {
			continue
		}

		// Find preemptible jobs on this node
		preemptibleJobs := sc.findPreemptibleJobs(node, job)
		if len(preemptibleJobs) == 0 {
			continue
		}

		// Calculate if preemption would free enough resources
		if sc.wouldPreemptionWork(node, job, preemptibleJobs) {
			// Perform preemption
			sc.preemptJobs(preemptibleJobs)
			return node
		}
	}
	return nil
}

func (sc *SchedulerController) findPreemptibleJobs(node *WorkerNode, job *Job) []*Job {
	var preemptible []*Job

	for _, existingJob := range sc.jobs {
		if existingJob.Status == "running" &&
			existingJob.NodeID == node.ID &&
			existingJob.Priority < job.Priority {
			preemptible = append(preemptible, existingJob)
		}
	}

	return preemptible
}

func (sc *SchedulerController) wouldPreemptionWork(node *WorkerNode, job *Job, preemptibleJobs []*Job) bool {
	// Calculate resources that would be freed
	var freedCPU, freedGPU float64
	var freedMem int64

	for _, pJob := range preemptibleJobs {
		freedCPU += sc.parseCPU(pJob.Resources.CPU)
		freedMem += sc.parseMemory(pJob.Resources.Memory)
		freedGPU += float64(sc.parseGPU(pJob.Resources.GPU))
	}

	// Check if freed resources are sufficient
	reqCPU := sc.parseCPU(job.Resources.CPU)
	reqMem := sc.parseMemory(job.Resources.Memory)
	reqGPU := float64(sc.parseGPU(job.Resources.GPU))

	availCPU := node.Resources.CPU - node.UsedResources.CPU + freedCPU
	availMem := node.Resources.Memory - node.UsedResources.Memory + freedMem
	availGPU := float64(node.Resources.GPU-node.UsedResources.GPU) + freedGPU

	return availCPU >= reqCPU && availMem >= reqMem && availGPU >= reqGPU
}

func (sc *SchedulerController) preemptJobs(jobs []*Job) {
	for _, job := range jobs {
		job.Status = "preempted"
		job.CompletedAt = &[]time.Time{time.Now()}[0]

		// Add back to queue with higher priority
		job.Priority += 10
		job.Status = "pending"
		job.StartedAt = nil
		job.CompletedAt = nil
		job.NodeID = ""

		sc.jobQueue = append(sc.jobQueue, job)

		log.Printf("Preempted job %s", job.ID)
	}
}

// Helper functions
func (sc *SchedulerController) checkResourceQuota(tenant *Tenant, job *Job) bool {
	// Count current tenant jobs
	runningJobs := 0
	for _, existingJob := range sc.jobs {
		if existingJob.TenantID == tenant.ID && existingJob.Status == "running" {
			runningJobs++
		}
	}

	return runningJobs < tenant.ResourceQuota.Jobs
}

func (sc *SchedulerController) getTenantPriority(priorityClass string) int {
	switch priorityClass {
	case "high":
		return 100
	case "medium":
		return 50
	case "low":
		return 10
	default:
		return 25
	}
}

func (sc *SchedulerController) getTenantWeight(priorityClass string) int {
	switch priorityClass {
	case "high":
		return 4
	case "medium":
		return 2
	case "low":
		return 1
	default:
		return 1
	}
}

func (sc *SchedulerController) parseCPU(cpu string) float64 {
	if cpu == "" {
		return 0.1 // Default 100m
	}
	// Simplified CPU parsing (would need proper parsing in production)
	if val, err := strconv.ParseFloat(cpu, 64); err == nil {
		return val
	}
	return 0.1
}

func (sc *SchedulerController) parseMemory(memory string) int64 {
	if memory == "" {
		return 128 * 1024 * 1024 // Default 128Mi
	}
	// Simplified memory parsing
	if val, err := strconv.ParseInt(memory, 10, 64); err == nil {
		return val
	}
	return 128 * 1024 * 1024
}

func (sc *SchedulerController) parseGPU(gpu string) int {
	if gpu == "" {
		return 0
	}
	if val, err := strconv.Atoi(gpu); err == nil {
		return val
	}
	return 0
}

func (sc *SchedulerController) updateResourceUtilizationMetrics(node *WorkerNode) {
	cpuUtil := node.UsedResources.CPU / node.Resources.CPU * 100
	memUtil := float64(node.UsedResources.Memory) / float64(node.Resources.Memory) * 100

	sc.metrics.ResourceUtilization.WithLabelValues("cpu", node.ID).Set(cpuUtil)
	sc.metrics.ResourceUtilization.WithLabelValues("memory", node.ID).Set(memUtil)

	if node.Resources.GPU > 0 {
		gpuUtil := float64(node.UsedResources.GPU) / float64(node.Resources.GPU) * 100
		sc.metrics.ResourceUtilization.WithLabelValues("gpu", node.ID).Set(gpuUtil)
	}
}

// Health check endpoint
func (sc *SchedulerController) HealthCheck(c *gin.Context) {
	c.JSON(http.StatusOK, gin.H{
		"status":       "healthy",
		"timestamp":    time.Now(),
		"queue_depth":  len(sc.jobQueue),
		"active_nodes": len(sc.nodes),
	})
}

func main() {
	// Initialize scheduler
	scheduler := NewSchedulerController()

	// Initialize some sample tenants and nodes for demo
	scheduler.initializeSampleData()

	// Start scheduling loop
	go scheduler.ScheduleJobs()

	// Setup HTTP server
	gin.SetMode(gin.ReleaseMode)
	r := gin.Default()

	// API routes
	api := r.Group("/api/v1")
	{
		api.POST("/jobs", scheduler.SubmitJob)
		api.GET("/jobs/:id", scheduler.GetJob)
		api.GET("/jobs", scheduler.ListJobs)
	}

	// Health and metrics
	r.GET("/health", scheduler.HealthCheck)
	r.GET("/metrics", gin.WrapH(promhttp.Handler()))

	// Start server
	server := &http.Server{
		Addr:    ":8080",
		Handler: r,
	}

	// Graceful shutdown
	go func() {
		if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("Server failed to start: %v", err)
		}
	}()

	// Wait for interrupt signal
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit

	log.Println("Shutting down scheduler...")

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	if err := server.Shutdown(ctx); err != nil {
		log.Fatal("Server forced to shutdown:", err)
	}

	scheduler.etcdClient.Close()
	log.Println("Scheduler stopped")
}

func (sc *SchedulerController) initializeSampleData() {
	// Sample tenants
	tenants := []*Tenant{
		{
			ID:   "tenant-a",
			Name: "Tenant A",
			ResourceQuota: ResourceQuota{
				CPU:     "50",
				Memory:  "100Gi",
				GPU:     "5",
				Storage: "500Gi",
				Jobs:    100,
			},
			PriorityClass: "high",
			CreatedAt:     time.Now(),
		},
		{
			ID:   "tenant-b",
			Name: "Tenant B",
			ResourceQuota: ResourceQuota{
				CPU:     "30",
				Memory:  "60Gi",
				GPU:     "2",
				Storage: "300Gi",
				Jobs:    50,
			},
			PriorityClass: "medium",
			CreatedAt:     time.Now(),
		},
	}

	// Sample nodes
	nodes := []*WorkerNode{
		{
			ID:      "worker-1",
			Address: "worker-node-1:8080",
			Status:  "ready",
			Resources: NodeResources{
				CPU:     8.0,
				Memory:  16 * 1024 * 1024 * 1024, // 16Gi
				GPU:     2,
				Storage: 100 * 1024 * 1024 * 1024, // 100Gi
			},
			UsedResources: NodeResources{},
			Labels:        map[string]string{"zone": "us-west-1a"},
			LastHeartbeat: time.Now(),
		},
		{
			ID:      "worker-2",
			Address: "worker-node-2:8080",
			Status:  "ready",
			Resources: NodeResources{
				CPU:     8.0,
				Memory:  16 * 1024 * 1024 * 1024,
				GPU:     2,
				Storage: 100 * 1024 * 1024 * 1024,
			},
			UsedResources: NodeResources{},
			Labels:        map[string]string{"zone": "us-west-1b"},
			LastHeartbeat: time.Now(),
		},
		{
			ID:      "worker-3",
			Address: "worker-node-3:8080",
			Status:  "ready",
			Resources: NodeResources{
				CPU:     8.0,
				Memory:  16 * 1024 * 1024 * 1024,
				GPU:     2,
				Storage: 100 * 1024 * 1024 * 1024,
			},
			UsedResources: NodeResources{},
			Labels:        map[string]string{"zone": "us-west-1c"},
			LastHeartbeat: time.Now(),
		},
	}

	sc.mutex.Lock()
	for _, tenant := range tenants {
		sc.tenants[tenant.ID] = tenant
	}
	for _, node := range nodes {
		sc.nodes[node.ID] = node
	}
	sc.mutex.Unlock()

	log.Printf("Initialized %d tenants and %d nodes", len(tenants), len(nodes))
}

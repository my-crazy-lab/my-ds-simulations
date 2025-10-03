package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"math/rand"
	"net/http"
	"os"
	"sync"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	"github.com/redis/go-redis/v9"
	clientv3 "go.etcd.io/etcd/client/v3"
)

// Core data structures
type RateLimitRequest struct {
	Key      string                 `json:"key"`
	Tokens   int64                  `json:"tokens"`
	Metadata map[string]interface{} `json:"metadata"`
}

type RateLimitResponse struct {
	Allowed    bool  `json:"allowed"`
	Remaining  int64 `json:"remaining"`
	ResetTime  int64 `json:"reset_time"`
	RetryAfter int64 `json:"retry_after,omitempty"`
}

type RateLimitPolicy struct {
	Name       string            `json:"name"`
	Algorithm  string            `json:"algorithm"` // token_bucket, sliding_window, leaky_bucket, adaptive
	Limit      int64             `json:"limit"`
	Window     string            `json:"window"`
	Burst      int64             `json:"burst"`
	Dimensions []string          `json:"dimensions"`
	Priority   string            `json:"priority"`
	Metadata   map[string]string `json:"metadata"`
}

type TokenBucket struct {
	Capacity   int64     `json:"capacity"`
	Tokens     int64     `json:"tokens"`
	RefillRate int64     `json:"refill_rate"`
	LastRefill time.Time `json:"last_refill"`
	mutex      sync.Mutex
}

type SlidingWindow struct {
	WindowSize time.Duration `json:"window_size"`
	Buckets    []int64       `json:"buckets"`
	BucketSize time.Duration `json:"bucket_size"`
	StartTime  time.Time     `json:"start_time"`
	mutex      sync.RWMutex
}

type AdaptiveRateLimiter struct {
	BaseRate       int64   `json:"base_rate"`
	CurrentRate    int64   `json:"current_rate"`
	LoadThreshold  float64 `json:"load_threshold"`
	AdjustmentRate float64 `json:"adjustment_rate"`
	mutex          sync.RWMutex
}

type CircuitBreaker struct {
	State             string        `json:"state"` // closed, open, half_open
	FailureCount      int64         `json:"failure_count"`
	SuccessCount      int64         `json:"success_count"`
	FailureThreshold  int64         `json:"failure_threshold"`
	RecoveryThreshold int64         `json:"recovery_threshold"`
	Timeout           time.Duration `json:"timeout"`
	LastFailure       time.Time     `json:"last_failure"`
	mutex             sync.RWMutex
}

type LoadShedder struct {
	LoadThreshold  float64         `json:"load_threshold"`
	SheddingRate   float64         `json:"shedding_rate"`
	PriorityLevels []PriorityLevel `json:"priority_levels"`
	random         *rand.Rand
}

type PriorityLevel struct {
	Level      int     `json:"level"`
	Multiplier float64 `json:"multiplier"`
}

type SystemLoad struct {
	CPU     float64 `json:"cpu"`
	Memory  float64 `json:"memory"`
	Network float64 `json:"network"`
	Overall float64 `json:"overall"`
}

// Rate Limiter Controller
type RateLimiterController struct {
	mode             string
	nodeID           string
	etcdClient       *clientv3.Client
	redisClient      *redis.ClusterClient
	policies         map[string]*RateLimitPolicy
	tokenBuckets     map[string]*TokenBucket
	slidingWindows   map[string]*SlidingWindow
	adaptiveLimiters map[string]*AdaptiveRateLimiter
	circuitBreakers  map[string]*CircuitBreaker
	loadShedder      *LoadShedder
	systemLoad       *SystemLoad
	mutex            sync.RWMutex

	// Metrics
	requestsTotal    prometheus.Counter
	requestsAllowed  prometheus.Counter
	requestsDenied   prometheus.Counter
	latencyHistogram prometheus.Histogram
	tokenBucketGauge prometheus.GaugeVec
	systemLoadGauge  prometheus.GaugeVec
}

// Prometheus metrics
var (
	requestsTotal = prometheus.NewCounter(prometheus.CounterOpts{
		Name: "rate_limiter_requests_total",
		Help: "Total number of rate limit requests",
	})

	requestsAllowed = prometheus.NewCounter(prometheus.CounterOpts{
		Name: "rate_limiter_requests_allowed_total",
		Help: "Total number of allowed requests",
	})

	requestsDenied = prometheus.NewCounter(prometheus.CounterOpts{
		Name: "rate_limiter_requests_denied_total",
		Help: "Total number of denied requests",
	})

	latencyHistogram = prometheus.NewHistogram(prometheus.HistogramOpts{
		Name:    "rate_limiter_request_duration_seconds",
		Help:    "Rate limiter request duration",
		Buckets: prometheus.DefBuckets,
	})

	tokenBucketGauge = prometheus.NewGaugeVec(prometheus.GaugeOpts{
		Name: "rate_limiter_token_bucket_tokens",
		Help: "Current tokens in token bucket",
	}, []string{"key", "policy"})

	systemLoadGauge = prometheus.NewGaugeVec(prometheus.GaugeOpts{
		Name: "rate_limiter_system_load",
		Help: "Current system load metrics",
	}, []string{"type"})
)

func init() {
	prometheus.MustRegister(requestsTotal)
	prometheus.MustRegister(requestsAllowed)
	prometheus.MustRegister(requestsDenied)
	prometheus.MustRegister(latencyHistogram)
	prometheus.MustRegister(tokenBucketGauge)
	prometheus.MustRegister(systemLoadGauge)
}

func NewRateLimiterController() *RateLimiterController {
	mode := getEnv("RATE_LIMITER_MODE", "controller")
	nodeID := getEnv("NODE_ID", "controller")

	// Initialize etcd client
	etcdClient, err := clientv3.New(clientv3.Config{
		Endpoints:   []string{"etcd-1:2379", "etcd-2:2379", "etcd-3:2379"},
		DialTimeout: 5 * time.Second,
	})
	if err != nil {
		log.Printf("Failed to connect to etcd: %v", err)
	}

	// Initialize Redis cluster client
	redisClient := redis.NewClusterClient(&redis.ClusterOptions{
		Addrs: []string{"redis-1:6379", "redis-2:6379", "redis-3:6379"},
	})

	controller := &RateLimiterController{
		mode:             mode,
		nodeID:           nodeID,
		etcdClient:       etcdClient,
		redisClient:      redisClient,
		policies:         make(map[string]*RateLimitPolicy),
		tokenBuckets:     make(map[string]*TokenBucket),
		slidingWindows:   make(map[string]*SlidingWindow),
		adaptiveLimiters: make(map[string]*AdaptiveRateLimiter),
		circuitBreakers:  make(map[string]*CircuitBreaker),
		systemLoad:       &SystemLoad{},
		requestsTotal:    requestsTotal,
		requestsAllowed:  requestsAllowed,
		requestsDenied:   requestsDenied,
		latencyHistogram: latencyHistogram,
		tokenBucketGauge: *tokenBucketGauge,
		systemLoadGauge:  *systemLoadGauge,
	}

	// Initialize load shedder
	controller.loadShedder = &LoadShedder{
		LoadThreshold: 0.8,
		SheddingRate:  0.1,
		PriorityLevels: []PriorityLevel{
			{Level: 1, Multiplier: 0.1}, // High priority
			{Level: 2, Multiplier: 0.5}, // Medium priority
			{Level: 3, Multiplier: 1.0}, // Low priority
		},
		random: rand.New(rand.NewSource(time.Now().UnixNano())),
	}

	// Initialize sample policies
	controller.initializeSamplePolicies()

	// Start background tasks
	go controller.monitorSystemLoad()
	go controller.syncTokenBuckets()
	go controller.updateAdaptiveRates()

	return controller
}

func (rlc *RateLimiterController) initializeSamplePolicies() {
	policies := []*RateLimitPolicy{
		{
			Name:       "api-rate-limit",
			Algorithm:  "token_bucket",
			Limit:      1000,
			Window:     "1m",
			Burst:      100,
			Dimensions: []string{"user_id", "api_key"},
			Priority:   "high",
		},
		{
			Name:       "user-rate-limit",
			Algorithm:  "sliding_window",
			Limit:      500,
			Window:     "1m",
			Burst:      50,
			Dimensions: []string{"user_id"},
			Priority:   "medium",
		},
		{
			Name:       "ip-rate-limit",
			Algorithm:  "adaptive",
			Limit:      100,
			Window:     "1m",
			Burst:      20,
			Dimensions: []string{"ip_address"},
			Priority:   "low",
		},
	}

	for _, policy := range policies {
		rlc.policies[policy.Name] = policy
		log.Printf("Initialized policy: %s", policy.Name)
	}
}

// Token Bucket Algorithm Implementation
func (tb *TokenBucket) Allow(tokens int64) bool {
	tb.mutex.Lock()
	defer tb.mutex.Unlock()

	now := time.Now()
	elapsed := now.Sub(tb.LastRefill).Seconds()

	// Refill tokens
	newTokens := int64(elapsed * float64(tb.RefillRate))
	tb.Tokens = min(tb.Capacity, tb.Tokens+newTokens)
	tb.LastRefill = now

	// Check if request can be served
	if tb.Tokens >= tokens {
		tb.Tokens -= tokens
		return true
	}
	return false
}

func (tb *TokenBucket) GetRemaining() int64 {
	tb.mutex.Lock()
	defer tb.mutex.Unlock()
	return tb.Tokens
}

// Sliding Window Algorithm Implementation
func (sw *SlidingWindow) Allow(limit int64) bool {
	sw.mutex.Lock()
	defer sw.mutex.Unlock()

	now := time.Now()
	sw.cleanup(now)

	// Count requests in current window
	total := int64(0)
	for _, count := range sw.Buckets {
		total += count
	}

	if total < limit {
		// Add request to current bucket
		bucketIndex := sw.getCurrentBucket(now)
		sw.Buckets[bucketIndex]++
		return true
	}
	return false
}

func (sw *SlidingWindow) cleanup(now time.Time) {
	// Remove old buckets outside the window
	bucketsToKeep := int(sw.WindowSize / sw.BucketSize)

	if len(sw.Buckets) > bucketsToKeep {
		sw.Buckets = sw.Buckets[len(sw.Buckets)-bucketsToKeep:]
	}
}

func (sw *SlidingWindow) getCurrentBucket(now time.Time) int {
	bucketIndex := int(now.Sub(sw.StartTime) / sw.BucketSize)

	// Extend buckets if needed
	for len(sw.Buckets) <= bucketIndex {
		sw.Buckets = append(sw.Buckets, 0)
	}

	return bucketIndex
}

// Adaptive Rate Limiter Implementation
func (arl *AdaptiveRateLimiter) UpdateRate(systemLoad float64) {
	arl.mutex.Lock()
	defer arl.mutex.Unlock()

	if systemLoad > arl.LoadThreshold {
		// Decrease rate under high load
		adjustment := float64(arl.CurrentRate) * arl.AdjustmentRate
		arl.CurrentRate = max(arl.BaseRate/4, arl.CurrentRate-int64(adjustment))
	} else {
		// Increase rate under low load
		adjustment := float64(arl.CurrentRate) * arl.AdjustmentRate
		arl.CurrentRate = min(arl.BaseRate*2, arl.CurrentRate+int64(adjustment))
	}
}

func (arl *AdaptiveRateLimiter) GetCurrentRate() int64 {
	arl.mutex.RLock()
	defer arl.mutex.RUnlock()
	return arl.CurrentRate
}

// Circuit Breaker Implementation
func (cb *CircuitBreaker) Allow() bool {
	cb.mutex.RLock()
	defer cb.mutex.RUnlock()

	switch cb.State {
	case "closed":
		return true
	case "open":
		if time.Since(cb.LastFailure) > cb.Timeout {
			cb.State = "half_open"
			return true
		}
		return false
	case "half_open":
		return true
	}
	return false
}

func (cb *CircuitBreaker) RecordSuccess() {
	cb.mutex.Lock()
	defer cb.mutex.Unlock()

	cb.SuccessCount++

	if cb.State == "half_open" && cb.SuccessCount >= cb.RecoveryThreshold {
		cb.State = "closed"
		cb.FailureCount = 0
		cb.SuccessCount = 0
	}
}

func (cb *CircuitBreaker) RecordFailure() {
	cb.mutex.Lock()
	defer cb.mutex.Unlock()

	cb.FailureCount++
	cb.LastFailure = time.Now()

	if cb.FailureCount >= cb.FailureThreshold {
		cb.State = "open"
	}
}

// Load Shedding Implementation
func (ls *LoadShedder) ShouldShed(priority int, systemLoad float64) bool {
	if systemLoad <= ls.LoadThreshold {
		return false
	}

	// Calculate shedding probability based on load and priority
	overload := systemLoad - ls.LoadThreshold
	sheddingProb := overload * ls.SheddingRate

	// Adjust probability based on priority
	if priority < len(ls.PriorityLevels) {
		priorityMultiplier := ls.PriorityLevels[priority].Multiplier
		sheddingProb *= priorityMultiplier
	}

	return ls.random.Float64() < sheddingProb
}

// System monitoring
func (rlc *RateLimiterController) monitorSystemLoad() {
	ticker := time.NewTicker(5 * time.Second)
	defer ticker.Stop()

	for range ticker.C {
		// Simulate system load monitoring
		rlc.mutex.Lock()
		rlc.systemLoad.CPU = 0.3 + rand.Float64()*0.4     // 30-70%
		rlc.systemLoad.Memory = 0.4 + rand.Float64()*0.3  // 40-70%
		rlc.systemLoad.Network = 0.2 + rand.Float64()*0.3 // 20-50%
		rlc.systemLoad.Overall = (rlc.systemLoad.CPU + rlc.systemLoad.Memory + rlc.systemLoad.Network) / 3
		rlc.mutex.Unlock()

		// Update Prometheus metrics
		rlc.systemLoadGauge.WithLabelValues("cpu").Set(rlc.systemLoad.CPU)
		rlc.systemLoadGauge.WithLabelValues("memory").Set(rlc.systemLoad.Memory)
		rlc.systemLoadGauge.WithLabelValues("network").Set(rlc.systemLoad.Network)
		rlc.systemLoadGauge.WithLabelValues("overall").Set(rlc.systemLoad.Overall)
	}
}

func (rlc *RateLimiterController) syncTokenBuckets() {
	ticker := time.NewTicker(1 * time.Second)
	defer ticker.Stop()

	for range ticker.C {
		rlc.mutex.RLock()
		for key, bucket := range rlc.tokenBuckets {
			// Sync token bucket state to Redis
			bucketData, _ := json.Marshal(bucket)
			rlc.redisClient.Set(context.Background(), fmt.Sprintf("bucket:%s", key), bucketData, time.Minute)

			// Update Prometheus metrics
			rlc.tokenBucketGauge.WithLabelValues(key, "default").Set(float64(bucket.GetRemaining()))
		}
		rlc.mutex.RUnlock()
	}
}

func (rlc *RateLimiterController) updateAdaptiveRates() {
	ticker := time.NewTicker(10 * time.Second)
	defer ticker.Stop()

	for range ticker.C {
		rlc.mutex.Lock()
		systemLoad := rlc.systemLoad.Overall

		for _, limiter := range rlc.adaptiveLimiters {
			limiter.UpdateRate(systemLoad)
		}
		rlc.mutex.Unlock()
	}
}

// HTTP API handlers
func (rlc *RateLimiterController) checkRateLimit(c *gin.Context) {
	start := time.Now()
	defer func() {
		rlc.latencyHistogram.Observe(time.Since(start).Seconds())
	}()

	var req RateLimitRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	rlc.requestsTotal.Inc()

	// Check load shedding first
	priority := rlc.getPriority(req.Metadata)
	if rlc.loadShedder.ShouldShed(priority, rlc.systemLoad.Overall) {
		rlc.requestsDenied.Inc()
		c.JSON(http.StatusTooManyRequests, RateLimitResponse{
			Allowed:    false,
			Remaining:  0,
			ResetTime:  time.Now().Add(time.Minute).Unix(),
			RetryAfter: 60,
		})
		return
	}

	// Apply rate limiting
	allowed := rlc.applyRateLimit(req.Key, req.Tokens)

	if allowed {
		rlc.requestsAllowed.Inc()
		c.JSON(http.StatusOK, RateLimitResponse{
			Allowed:   true,
			Remaining: rlc.getRemaining(req.Key),
			ResetTime: time.Now().Add(time.Minute).Unix(),
		})
	} else {
		rlc.requestsDenied.Inc()
		c.JSON(http.StatusTooManyRequests, RateLimitResponse{
			Allowed:    false,
			Remaining:  0,
			ResetTime:  time.Now().Add(time.Minute).Unix(),
			RetryAfter: 60,
		})
	}
}

func (rlc *RateLimiterController) applyRateLimit(key string, tokens int64) bool {
	rlc.mutex.Lock()
	defer rlc.mutex.Unlock()

	// Get or create token bucket
	bucket, exists := rlc.tokenBuckets[key]
	if !exists {
		bucket = &TokenBucket{
			Capacity:   1000,
			Tokens:     1000,
			RefillRate: 100, // 100 tokens per second
			LastRefill: time.Now(),
		}
		rlc.tokenBuckets[key] = bucket
	}

	return bucket.Allow(tokens)
}

func (rlc *RateLimiterController) getRemaining(key string) int64 {
	rlc.mutex.RLock()
	defer rlc.mutex.RUnlock()

	if bucket, exists := rlc.tokenBuckets[key]; exists {
		return bucket.GetRemaining()
	}
	return 0
}

func (rlc *RateLimiterController) getPriority(metadata map[string]interface{}) int {
	if priority, exists := metadata["priority"]; exists {
		if p, ok := priority.(string); ok {
			switch p {
			case "high":
				return 0
			case "medium":
				return 1
			case "low":
				return 2
			}
		}
	}
	return 2 // Default to low priority
}

func (rlc *RateLimiterController) createPolicy(c *gin.Context) {
	var policy RateLimitPolicy
	if err := c.ShouldBindJSON(&policy); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	rlc.mutex.Lock()
	rlc.policies[policy.Name] = &policy
	rlc.mutex.Unlock()

	log.Printf("Created policy: %s", policy.Name)
	c.JSON(http.StatusCreated, gin.H{"message": "Policy created successfully"})
}

func (rlc *RateLimiterController) getMetrics(c *gin.Context) {
	key := c.Query("key")

	rlc.mutex.RLock()
	defer rlc.mutex.RUnlock()

	metrics := gin.H{
		"system_load": rlc.systemLoad,
		"policies":    len(rlc.policies),
		"buckets":     len(rlc.tokenBuckets),
	}

	if key != "" {
		if bucket, exists := rlc.tokenBuckets[key]; exists {
			metrics["bucket"] = gin.H{
				"key":         key,
				"tokens":      bucket.GetRemaining(),
				"capacity":    bucket.Capacity,
				"refill_rate": bucket.RefillRate,
			}
		}
	}

	c.JSON(http.StatusOK, metrics)
}

func (rlc *RateLimiterController) healthCheck(c *gin.Context) {
	c.JSON(http.StatusOK, gin.H{
		"status":    "healthy",
		"mode":      rlc.mode,
		"node_id":   rlc.nodeID,
		"timestamp": time.Now().Unix(),
	})
}

// Utility functions
func getEnv(key, defaultValue string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return defaultValue
}

func min(a, b int64) int64 {
	if a < b {
		return a
	}
	return b
}

func max(a, b int64) int64 {
	if a > b {
		return a
	}
	return b
}

func main() {
	// Initialize rate limiter controller
	controller := NewRateLimiterController()

	// Setup Gin router
	gin.SetMode(gin.ReleaseMode)
	router := gin.Default()

	// API routes
	v1 := router.Group("/api/v1")
	{
		v1.POST("/check", controller.checkRateLimit)
		v1.POST("/policies", controller.createPolicy)
		v1.GET("/metrics", controller.getMetrics)
	}

	// Health check
	router.GET("/health", controller.healthCheck)

	// Metrics endpoint
	router.GET("/metrics", gin.WrapH(promhttp.Handler()))

	// Start server
	port := getEnv("PORT", "8080")
	log.Printf("Starting Rate Limiter Controller on port %s", port)
	log.Fatal(http.ListenAndServe(":"+port, router))
}

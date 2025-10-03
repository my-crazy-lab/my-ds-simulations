#!/usr/bin/env python3
"""
Unit tests for distributed rate limiting algorithms and functionality.
Tests token bucket, sliding window, adaptive rate limiting, and backpressure mechanisms.
"""

import pytest
import requests
import time
import json
import threading
import statistics
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed


@dataclass
class RateLimitConfig:
    """Rate limit configuration for testing"""
    name: str
    algorithm: str
    limit: int
    window: str
    burst: int
    dimensions: List[str]
    priority: str


@dataclass
class LoadTestResult:
    """Load test result metrics"""
    total_requests: int
    allowed_requests: int
    denied_requests: int
    success_rate: float
    avg_latency: float
    p95_latency: float
    p99_latency: float
    throughput: float


class RateLimiterTestClient:
    """Test client for rate limiter API"""
    
    def __init__(self, base_url: str = "http://localhost:8080"):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.timeout = 10
    
    def check_rate_limit(self, key: str, tokens: int = 1, metadata: Optional[Dict] = None) -> Optional[Dict]:
        """Check rate limit for a key"""
        try:
            payload = {
                "key": key,
                "tokens": tokens,
                "metadata": metadata or {}
            }
            
            response = self.session.post(
                f"{self.base_url}/api/v1/check",
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code in [200, 429]:
                return response.json()
            else:
                print(f"Unexpected status code: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"Rate limit check failed: {e}")
            return None
    
    def create_policy(self, policy: RateLimitConfig) -> bool:
        """Create a rate limiting policy"""
        try:
            payload = {
                "name": policy.name,
                "algorithm": policy.algorithm,
                "limit": policy.limit,
                "window": policy.window,
                "burst": policy.burst,
                "dimensions": policy.dimensions,
                "priority": policy.priority
            }
            
            response = self.session.post(
                f"{self.base_url}/api/v1/policies",
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            
            return response.status_code in [200, 201]
            
        except Exception as e:
            print(f"Policy creation failed: {e}")
            return False
    
    def get_metrics(self, key: Optional[str] = None) -> Optional[Dict]:
        """Get rate limiter metrics"""
        try:
            params = {"key": key} if key else {}
            response = self.session.get(f"{self.base_url}/api/v1/metrics", params=params)
            
            if response.status_code == 200:
                return response.json()
            return None
            
        except Exception as e:
            print(f"Metrics retrieval failed: {e}")
            return None
    
    def health_check(self) -> bool:
        """Check if rate limiter is healthy"""
        try:
            response = self.session.get(f"{self.base_url}/health")
            return response.status_code == 200
        except:
            return False


class RateLimitingAnalyzer:
    """Analyzer for rate limiting behavior and performance"""
    
    def __init__(self, client: RateLimiterTestClient):
        self.client = client
    
    def analyze_token_bucket_behavior(self, key: str, rate: int, burst: int, duration: int) -> Dict:
        """Analyze token bucket algorithm behavior"""
        print(f"Analyzing token bucket behavior for key: {key}")
        
        results = {
            "algorithm": "token_bucket",
            "rate": rate,
            "burst": burst,
            "duration": duration,
            "requests": [],
            "allowed_count": 0,
            "denied_count": 0,
            "burst_handling": False,
            "rate_enforcement": False
        }
        
        start_time = time.time()
        
        # Test burst handling - send burst requests quickly
        print("Testing burst handling...")
        burst_start = time.time()
        for i in range(burst + 10):  # Send more than burst limit
            result = self.client.check_rate_limit(f"{key}-burst", 1, {"test": "burst"})
            if result:
                results["requests"].append({
                    "timestamp": time.time() - start_time,
                    "allowed": result.get("allowed", False),
                    "remaining": result.get("remaining", 0),
                    "phase": "burst"
                })
                if result.get("allowed"):
                    results["allowed_count"] += 1
                else:
                    results["denied_count"] += 1
        
        burst_duration = time.time() - burst_start
        results["burst_handling"] = results["allowed_count"] <= burst
        
        # Wait for token refill
        print("Waiting for token refill...")
        time.sleep(2)
        
        # Test sustained rate - send requests at the configured rate
        print("Testing sustained rate enforcement...")
        rate_start = time.time()
        interval = 1.0 / rate  # Interval between requests
        
        for i in range(rate * 2):  # Send twice the rate
            result = self.client.check_rate_limit(f"{key}-rate", 1, {"test": "rate"})
            if result:
                results["requests"].append({
                    "timestamp": time.time() - start_time,
                    "allowed": result.get("allowed", False),
                    "remaining": result.get("remaining", 0),
                    "phase": "rate"
                })
                if result.get("allowed"):
                    results["allowed_count"] += 1
                else:
                    results["denied_count"] += 1
            
            time.sleep(interval / 2)  # Send at 2x rate to test limiting
        
        rate_duration = time.time() - rate_start
        rate_requests = [r for r in results["requests"] if r["phase"] == "rate"]
        rate_allowed = sum(1 for r in rate_requests if r["allowed"])
        expected_allowed = int(rate * rate_duration)
        
        results["rate_enforcement"] = abs(rate_allowed - expected_allowed) <= rate * 0.1  # 10% tolerance
        
        print(f"Token bucket analysis completed:")
        print(f"  Burst handling: {results['burst_handling']}")
        print(f"  Rate enforcement: {results['rate_enforcement']}")
        print(f"  Total allowed: {results['allowed_count']}")
        print(f"  Total denied: {results['denied_count']}")
        
        return results
    
    def analyze_sliding_window_behavior(self, key: str, limit: int, window_seconds: int) -> Dict:
        """Analyze sliding window algorithm behavior"""
        print(f"Analyzing sliding window behavior for key: {key}")
        
        results = {
            "algorithm": "sliding_window",
            "limit": limit,
            "window_seconds": window_seconds,
            "requests": [],
            "allowed_count": 0,
            "denied_count": 0,
            "window_enforcement": False,
            "precision": 0.0
        }
        
        start_time = time.time()
        
        # Send requests at different intervals to test window behavior
        intervals = [0.1, 0.2, 0.5, 1.0]  # Different request intervals
        
        for interval in intervals:
            print(f"Testing with {interval}s intervals...")
            phase_start = time.time()
            
            # Send requests for one window duration
            while time.time() - phase_start < window_seconds:
                result = self.client.check_rate_limit(f"{key}-window", 1, {"interval": interval})
                if result:
                    results["requests"].append({
                        "timestamp": time.time() - start_time,
                        "allowed": result.get("allowed", False),
                        "remaining": result.get("remaining", 0),
                        "interval": interval
                    })
                    if result.get("allowed"):
                        results["allowed_count"] += 1
                    else:
                        results["denied_count"] += 1
                
                time.sleep(interval)
            
            # Wait for window to slide
            time.sleep(window_seconds / 2)
        
        # Analyze window enforcement
        window_requests = results["requests"]
        if window_requests:
            # Check if requests within any window period exceed the limit
            window_violations = 0
            for i, req in enumerate(window_requests):
                window_start = req["timestamp"]
                window_end = window_start + window_seconds
                
                window_count = sum(1 for r in window_requests 
                                 if window_start <= r["timestamp"] < window_end and r["allowed"])
                
                if window_count > limit:
                    window_violations += 1
            
            results["window_enforcement"] = window_violations == 0
            results["precision"] = 1.0 - (window_violations / len(window_requests))
        
        print(f"Sliding window analysis completed:")
        print(f"  Window enforcement: {results['window_enforcement']}")
        print(f"  Precision: {results['precision']:.2%}")
        print(f"  Total allowed: {results['allowed_count']}")
        print(f"  Total denied: {results['denied_count']}")
        
        return results
    
    def analyze_adaptive_rate_limiting(self, key: str, base_rate: int, duration: int) -> Dict:
        """Analyze adaptive rate limiting behavior"""
        print(f"Analyzing adaptive rate limiting for key: {key}")
        
        results = {
            "algorithm": "adaptive",
            "base_rate": base_rate,
            "duration": duration,
            "requests": [],
            "rate_changes": [],
            "adaptation_detected": False,
            "load_responsiveness": 0.0
        }
        
        start_time = time.time()
        
        # Monitor rate changes over time
        def monitor_rates():
            while time.time() - start_time < duration:
                metrics = self.client.get_metrics(key)
                if metrics and "bucket" in metrics:
                    results["rate_changes"].append({
                        "timestamp": time.time() - start_time,
                        "rate": metrics["bucket"].get("refill_rate", base_rate),
                        "system_load": metrics.get("system_load", {}).get("overall", 0.0)
                    })
                time.sleep(1)
        
        # Start monitoring in background
        monitor_thread = threading.Thread(target=monitor_rates)
        monitor_thread.daemon = True
        monitor_thread.start()
        
        # Generate varying load to trigger adaptation
        load_phases = [
            {"name": "low", "rate": base_rate // 2, "duration": duration // 3},
            {"name": "high", "rate": base_rate * 2, "duration": duration // 3},
            {"name": "normal", "rate": base_rate, "duration": duration // 3}
        ]
        
        for phase in load_phases:
            print(f"Testing {phase['name']} load phase...")
            phase_start = time.time()
            interval = 1.0 / phase["rate"]
            
            while time.time() - phase_start < phase["duration"]:
                result = self.client.check_rate_limit(f"{key}-adaptive", 1, {"phase": phase["name"]})
                if result:
                    results["requests"].append({
                        "timestamp": time.time() - start_time,
                        "allowed": result.get("allowed", False),
                        "remaining": result.get("remaining", 0),
                        "phase": phase["name"]
                    })
                
                time.sleep(interval)
        
        # Wait for monitoring to complete
        monitor_thread.join(timeout=5)
        
        # Analyze adaptation behavior
        if len(results["rate_changes"]) > 1:
            rates = [r["rate"] for r in results["rate_changes"]]
            rate_variance = statistics.variance(rates) if len(rates) > 1 else 0
            results["adaptation_detected"] = rate_variance > (base_rate * 0.1) ** 2
            
            # Calculate load responsiveness
            load_changes = []
            rate_changes = []
            for i in range(1, len(results["rate_changes"])):
                prev = results["rate_changes"][i-1]
                curr = results["rate_changes"][i]
                
                load_change = curr["system_load"] - prev["system_load"]
                rate_change = curr["rate"] - prev["rate"]
                
                if abs(load_change) > 0.1:  # Significant load change
                    load_changes.append(load_change)
                    rate_changes.append(rate_change)
            
            if load_changes and rate_changes:
                # Calculate correlation between load and rate changes
                correlation = statistics.correlation(load_changes, rate_changes) if len(load_changes) > 1 else 0
                results["load_responsiveness"] = abs(correlation)
        
        print(f"Adaptive rate limiting analysis completed:")
        print(f"  Adaptation detected: {results['adaptation_detected']}")
        print(f"  Load responsiveness: {results['load_responsiveness']:.2f}")
        print(f"  Rate changes: {len(results['rate_changes'])}")
        
        return results
    
    def perform_load_test(self, key: str, concurrent_users: int, requests_per_user: int, 
                         request_interval: float = 0.1) -> LoadTestResult:
        """Perform load test on rate limiter"""
        print(f"Performing load test: {concurrent_users} users, {requests_per_user} requests each")
        
        results = []
        latencies = []
        start_time = time.time()
        
        def user_requests(user_id: int) -> List[Dict]:
            user_results = []
            for i in range(requests_per_user):
                request_start = time.time()
                result = self.client.check_rate_limit(f"{key}-user-{user_id}", 1, {"user": user_id})
                request_end = time.time()
                
                latency = (request_end - request_start) * 1000  # Convert to milliseconds
                
                user_results.append({
                    "user_id": user_id,
                    "request_id": i,
                    "allowed": result.get("allowed", False) if result else False,
                    "latency": latency,
                    "timestamp": request_start - start_time
                })
                
                time.sleep(request_interval)
            
            return user_results
        
        # Execute concurrent requests
        with ThreadPoolExecutor(max_workers=concurrent_users) as executor:
            futures = [executor.submit(user_requests, user_id) for user_id in range(concurrent_users)]
            
            for future in as_completed(futures):
                try:
                    user_results = future.result()
                    results.extend(user_results)
                    latencies.extend([r["latency"] for r in user_results])
                except Exception as e:
                    print(f"User request failed: {e}")
        
        # Calculate metrics
        total_requests = len(results)
        allowed_requests = sum(1 for r in results if r["allowed"])
        denied_requests = total_requests - allowed_requests
        success_rate = allowed_requests / total_requests if total_requests > 0 else 0
        
        avg_latency = statistics.mean(latencies) if latencies else 0
        p95_latency = statistics.quantiles(latencies, n=20)[18] if len(latencies) > 20 else 0
        p99_latency = statistics.quantiles(latencies, n=100)[98] if len(latencies) > 100 else 0
        
        total_duration = time.time() - start_time
        throughput = total_requests / total_duration if total_duration > 0 else 0
        
        load_result = LoadTestResult(
            total_requests=total_requests,
            allowed_requests=allowed_requests,
            denied_requests=denied_requests,
            success_rate=success_rate,
            avg_latency=avg_latency,
            p95_latency=p95_latency,
            p99_latency=p99_latency,
            throughput=throughput
        )
        
        print(f"Load test completed:")
        print(f"  Total requests: {load_result.total_requests}")
        print(f"  Success rate: {load_result.success_rate:.2%}")
        print(f"  Average latency: {load_result.avg_latency:.2f}ms")
        print(f"  P95 latency: {load_result.p95_latency:.2f}ms")
        print(f"  P99 latency: {load_result.p99_latency:.2f}ms")
        print(f"  Throughput: {load_result.throughput:.2f} req/s")
        
        return load_result


class TestRateLimiting:
    """Test suite for rate limiting functionality"""
    
    @classmethod
    def setup_class(cls):
        """Setup test environment"""
        cls.client = RateLimiterTestClient()
        cls.analyzer = RateLimitingAnalyzer(cls.client)
        
        # Wait for rate limiter to be ready
        max_retries = 30
        for i in range(max_retries):
            if cls.client.health_check():
                print("Rate limiter is ready")
                break
            print(f"Waiting for rate limiter... ({i+1}/{max_retries})")
            time.sleep(2)
        else:
            pytest.fail("Rate limiter not available after 60 seconds")
    
    def test_rate_limiter_connectivity(self):
        """Test basic connectivity to rate limiter"""
        assert self.client.health_check(), "Rate limiter should be accessible"
        
        # Test basic rate limit check
        result = self.client.check_rate_limit("test-connectivity", 1)
        assert result is not None, "Should receive response from rate limiter"
        assert "allowed" in result, "Response should contain 'allowed' field"
    
    def test_token_bucket_algorithm(self):
        """Test token bucket rate limiting algorithm"""
        print("\n=== Testing Token Bucket Algorithm ===")
        
        # Create token bucket policy
        policy = RateLimitConfig(
            name="test-token-bucket",
            algorithm="token_bucket",
            limit=100,  # 100 requests per minute
            window="1m",
            burst=20,   # Allow burst of 20 requests
            dimensions=["key"],
            priority="medium"
        )
        
        assert self.client.create_policy(policy), "Should create token bucket policy"
        
        # Analyze token bucket behavior
        analysis = self.analyzer.analyze_token_bucket_behavior("test-token-bucket", 100, 20, 10)
        
        assert analysis["burst_handling"], "Should handle burst requests correctly"
        assert analysis["rate_enforcement"], "Should enforce rate limits correctly"
        assert analysis["allowed_count"] > 0, "Should allow some requests"
        assert analysis["denied_count"] > 0, "Should deny some requests when limit exceeded"
    
    def test_sliding_window_algorithm(self):
        """Test sliding window rate limiting algorithm"""
        print("\n=== Testing Sliding Window Algorithm ===")
        
        # Create sliding window policy
        policy = RateLimitConfig(
            name="test-sliding-window",
            algorithm="sliding_window",
            limit=50,   # 50 requests per window
            window="30s",
            burst=10,
            dimensions=["key"],
            priority="medium"
        )
        
        assert self.client.create_policy(policy), "Should create sliding window policy"
        
        # Analyze sliding window behavior
        analysis = self.analyzer.analyze_sliding_window_behavior("test-sliding-window", 50, 30)
        
        assert analysis["window_enforcement"], "Should enforce window limits correctly"
        assert analysis["precision"] > 0.8, "Should have high precision in window enforcement"
        assert analysis["allowed_count"] > 0, "Should allow requests within limits"
    
    def test_adaptive_rate_limiting(self):
        """Test adaptive rate limiting algorithm"""
        print("\n=== Testing Adaptive Rate Limiting ===")
        
        # Create adaptive rate limiting policy
        policy = RateLimitConfig(
            name="test-adaptive",
            algorithm="adaptive",
            limit=75,   # Base rate of 75 requests per minute
            window="1m",
            burst=15,
            dimensions=["key"],
            priority="high"
        )
        
        assert self.client.create_policy(policy), "Should create adaptive policy"
        
        # Analyze adaptive behavior
        analysis = self.analyzer.analyze_adaptive_rate_limiting("test-adaptive", 75, 30)
        
        assert analysis["adaptation_detected"], "Should detect rate adaptation"
        assert analysis["load_responsiveness"] > 0.3, "Should respond to load changes"
        assert len(analysis["rate_changes"]) > 5, "Should record multiple rate changes"
    
    def test_multi_dimensional_rate_limiting(self):
        """Test rate limiting with multiple dimensions"""
        print("\n=== Testing Multi-Dimensional Rate Limiting ===")
        
        # Test rate limiting by user and API key
        user_results = []
        api_results = []
        
        # Test user-based rate limiting
        for i in range(10):
            result = self.client.check_rate_limit("user:12345", 1, {"user_id": "12345", "api_key": "key1"})
            if result:
                user_results.append(result["allowed"])
        
        # Test API key-based rate limiting
        for i in range(10):
            result = self.client.check_rate_limit("api:key1", 1, {"user_id": "67890", "api_key": "key1"})
            if result:
                api_results.append(result["allowed"])
        
        assert len(user_results) > 0, "Should process user-based requests"
        assert len(api_results) > 0, "Should process API key-based requests"
        assert any(user_results), "Should allow some user requests"
        assert any(api_results), "Should allow some API requests"
    
    def test_priority_based_rate_limiting(self):
        """Test priority-based rate limiting"""
        print("\n=== Testing Priority-Based Rate Limiting ===")
        
        high_priority_results = []
        low_priority_results = []
        
        # Send high priority requests
        for i in range(20):
            result = self.client.check_rate_limit("priority-test", 1, {"priority": "high"})
            if result:
                high_priority_results.append(result["allowed"])
        
        # Send low priority requests
        for i in range(20):
            result = self.client.check_rate_limit("priority-test", 1, {"priority": "low"})
            if result:
                low_priority_results.append(result["allowed"])
        
        high_success_rate = sum(high_priority_results) / len(high_priority_results) if high_priority_results else 0
        low_success_rate = sum(low_priority_results) / len(low_priority_results) if low_priority_results else 0
        
        assert high_success_rate >= low_success_rate, "High priority requests should have better success rate"
    
    def test_rate_limiter_performance(self):
        """Test rate limiter performance under load"""
        print("\n=== Testing Rate Limiter Performance ===")
        
        # Perform load test
        load_result = self.analyzer.perform_load_test("performance-test", 10, 50, 0.05)
        
        assert load_result.total_requests > 0, "Should process requests"
        assert load_result.avg_latency < 100, "Average latency should be under 100ms"
        assert load_result.p95_latency < 200, "P95 latency should be under 200ms"
        assert load_result.throughput > 50, "Should handle at least 50 req/s"
        
        print(f"Performance test results:")
        print(f"  Throughput: {load_result.throughput:.2f} req/s")
        print(f"  Success rate: {load_result.success_rate:.2%}")
        print(f"  Average latency: {load_result.avg_latency:.2f}ms")
    
    def test_rate_limiter_accuracy(self):
        """Test rate limiter accuracy"""
        print("\n=== Testing Rate Limiter Accuracy ===")
        
        # Test with known rate limit
        limit = 100
        test_requests = 150
        allowed_count = 0
        
        for i in range(test_requests):
            result = self.client.check_rate_limit("accuracy-test", 1)
            if result and result.get("allowed"):
                allowed_count += 1
            time.sleep(0.01)  # Small delay to avoid overwhelming
        
        accuracy = abs(allowed_count - limit) / limit
        assert accuracy < 0.1, f"Rate limiting accuracy should be within 10%, got {accuracy:.2%}"
        
        print(f"Accuracy test results:")
        print(f"  Expected: {limit} requests")
        print(f"  Allowed: {allowed_count} requests")
        print(f"  Accuracy: {(1-accuracy):.2%}")


class TestRateLimitingAlgorithms:
    """Test suite for specific rate limiting algorithms"""
    
    @classmethod
    def setup_class(cls):
        cls.client = RateLimiterTestClient()
        cls.analyzer = RateLimitingAnalyzer(cls.client)
    
    def test_token_bucket_refill_rate(self):
        """Test token bucket refill rate accuracy"""
        print("\n=== Testing Token Bucket Refill Rate ===")
        
        # Test with different refill rates
        refill_rates = [10, 50, 100]  # tokens per second
        
        for rate in refill_rates:
            print(f"Testing refill rate: {rate} tokens/second")
            
            # Exhaust tokens first
            for i in range(20):
                self.client.check_rate_limit(f"refill-test-{rate}", 1)
            
            # Wait for refill
            time.sleep(2)
            
            # Test sustained rate
            start_time = time.time()
            allowed_count = 0
            
            for i in range(rate * 2):  # Test for 2 seconds worth
                result = self.client.check_rate_limit(f"refill-test-{rate}", 1)
                if result and result.get("allowed"):
                    allowed_count += 1
                time.sleep(1.0 / rate)  # Request at the refill rate
            
            duration = time.time() - start_time
            expected_tokens = int(rate * duration)
            accuracy = abs(allowed_count - expected_tokens) / expected_tokens if expected_tokens > 0 else 1
            
            assert accuracy < 0.2, f"Refill rate accuracy should be within 20% for rate {rate}"
            print(f"  Expected: {expected_tokens}, Allowed: {allowed_count}, Accuracy: {(1-accuracy):.2%}")
    
    def test_sliding_window_precision(self):
        """Test sliding window precision with different window sizes"""
        print("\n=== Testing Sliding Window Precision ===")
        
        window_sizes = [10, 30, 60]  # seconds
        
        for window_size in window_sizes:
            print(f"Testing window size: {window_size} seconds")
            
            limit = 20
            requests = []
            start_time = time.time()
            
            # Send requests over 1.5 window periods
            test_duration = window_size * 1.5
            while time.time() - start_time < test_duration:
                result = self.client.check_rate_limit(f"precision-test-{window_size}", 1)
                requests.append({
                    "timestamp": time.time() - start_time,
                    "allowed": result.get("allowed", False) if result else False
                })
                time.sleep(0.5)  # Request every 500ms
            
            # Check window enforcement
            violations = 0
            for i, req in enumerate(requests):
                if not req["allowed"]:
                    continue
                
                window_start = req["timestamp"]
                window_end = window_start + window_size
                
                window_count = sum(1 for r in requests 
                                 if window_start <= r["timestamp"] < window_end and r["allowed"])
                
                if window_count > limit:
                    violations += 1
            
            precision = 1.0 - (violations / len(requests)) if requests else 0
            assert precision > 0.9, f"Window precision should be >90% for {window_size}s window"
            print(f"  Precision: {precision:.2%}, Violations: {violations}/{len(requests)}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

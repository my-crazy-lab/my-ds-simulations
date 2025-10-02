import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';

// Custom metrics for RAG engine
const ragSearchSuccessRate = new Rate('rag_search_success_rate');
const ragSearchDuration = new Trend('rag_search_duration');
const ragIndexingRate = new Rate('rag_indexing_success_rate');
const cacheHitRate = new Rate('rag_cache_hit_rate');
const staleQueries = new Counter('rag_stale_queries');

// Test configuration
export const options = {
  stages: [
    { duration: '1m', target: 10 },   // Warm up
    { duration: '3m', target: 50 },   // Ramp up to moderate load
    { duration: '5m', target: 100 },  // High load testing
    { duration: '3m', target: 200 },  // Peak load testing (1000 QPS target)
    { duration: '5m', target: 200 },  // Sustained peak load
    { duration: '2m', target: 0 },    // Ramp down
  ],
  thresholds: {
    http_req_duration: ['p(95)<200'], // 95% of requests under 200ms (SLO requirement)
    rag_search_success_rate: ['rate>0.99'], // 99% success rate
    rag_search_duration: ['p(95)<200'], // Search latency <200ms p95
    rag_cache_hit_rate: ['rate>0.70'], // >70% cache hit rate (SLO requirement)
    http_req_failed: ['rate<0.01'], // <1% error rate
  },
};

const BASE_URL = 'http://localhost:8081';

// Sample queries for testing different scenarios
const searchQueries = [
  // Common queries (should hit cache frequently)
  'How to reset password',
  'Account login issues',
  'Payment problems',
  'Order status check',
  'Refund request',
  
  // Technical queries
  'API integration guide',
  'Database connection error',
  'SSL certificate setup',
  'Performance optimization',
  'Security best practices',
  
  // Product queries
  'Product features comparison',
  'Pricing information',
  'Subscription plans',
  'Free trial details',
  'Enterprise features',
  
  // Support queries
  'Contact customer support',
  'Technical documentation',
  'Troubleshooting guide',
  'System requirements',
  'Installation instructions',
  
  // Long-tail queries (less likely to be cached)
  'How to configure advanced webhook settings for third-party integrations',
  'Troubleshooting intermittent connection timeouts in distributed environments',
  'Best practices for handling large-scale data migrations with minimal downtime',
  'Implementing custom authentication flows with OAuth 2.0 and SAML',
  'Optimizing query performance for complex multi-tenant database schemas',
];

// Generate variations of queries to test cache behavior
function generateQueryVariation(baseQuery) {
  const variations = [
    baseQuery,
    baseQuery + '?',
    baseQuery + ' help',
    baseQuery + ' tutorial',
    baseQuery + ' guide',
    'How to ' + baseQuery.toLowerCase(),
    'What is ' + baseQuery.toLowerCase(),
    baseQuery.replace(/\b\w/g, l => l.toUpperCase()), // Title case
  ];
  
  return variations[Math.floor(Math.random() * variations.length)];
}

function selectQuery() {
  const rand = Math.random();
  
  if (rand < 0.6) {
    // 60% common queries (high cache hit probability)
    const commonQueries = searchQueries.slice(0, 10);
    return generateQueryVariation(commonQueries[Math.floor(Math.random() * commonQueries.length)]);
  } else if (rand < 0.8) {
    // 20% medium frequency queries
    const mediumQueries = searchQueries.slice(10, 20);
    return generateQueryVariation(mediumQueries[Math.floor(Math.random() * mediumQueries.length)]);
  } else {
    // 20% long-tail queries (low cache hit probability)
    const longTailQueries = searchQueries.slice(20);
    return longTailQueries[Math.floor(Math.random() * longTailQueries.length)];
  }
}

export default function () {
  // Test health endpoint
  const healthRes = http.get(`${BASE_URL}/health`);
  check(healthRes, {
    'health check status is 200': (r) => r.status === 200,
    'health check response time < 50ms': (r) => r.timings.duration < 50,
  });

  // Test index stats endpoint
  if (__ITER % 20 === 0) { // Check stats every 20 iterations
    const statsRes = http.get(`${BASE_URL}/index/stats`);
    check(statsRes, {
      'stats endpoint accessible': (r) => r.status === 200,
      'stats response time < 100ms': (r) => r.timings.duration < 100,
    });
  }

  // Main search test
  const query = selectQuery();
  const topK = Math.floor(Math.random() * 10) + 5; // Random top_k between 5-15
  
  const searchPayload = JSON.stringify({
    query: query,
    top_k: topK
  });

  const searchStartTime = Date.now();
  const searchRes = http.post(`${BASE_URL}/search`, searchPayload, {
    headers: { 'Content-Type': 'application/json' },
  });
  const searchDuration = Date.now() - searchStartTime;

  ragSearchDuration.add(searchDuration);

  const searchSuccess = check(searchRes, {
    'search request successful': (r) => r.status === 200,
    'search response time acceptable': (r) => r.timings.duration < 1000, // 1s max
    'search response has results': (r) => {
      try {
        const body = JSON.parse(r.body);
        return body.results && Array.isArray(body.results);
      } catch (e) {
        return false;
      }
    },
    'search processing time reasonable': (r) => {
      try {
        const body = JSON.parse(r.body);
        return body.processing_time_ms < 500; // 500ms max processing time
      } catch (e) {
        return false;
      }
    },
  });

  ragSearchSuccessRate.add(searchSuccess);

  // Analyze response for cache hit detection and quality metrics
  if (searchRes.status === 200) {
    try {
      const responseBody = JSON.parse(searchRes.body);
      
      // Detect potential cache hits (very fast responses)
      const isCacheHit = responseBody.processing_time_ms < 50;
      cacheHitRate.add(isCacheHit);
      
      // Check for stale results (this is a simplified heuristic)
      const hasResults = responseBody.results && responseBody.results.length > 0;
      if (hasResults) {
        const avgScore = responseBody.results.reduce((sum, result) => sum + (result.score || 0), 0) / responseBody.results.length;
        
        // If average relevance score is very low, might indicate stale index
        if (avgScore < 0.3) {
          staleQueries.add(1);
        }
      }
      
      // Log detailed metrics for analysis (from VU 1 only)
      if (__VU === 1 && __ITER % 50 === 0) {
        console.log(`Search metrics - Query: "${query.substring(0, 30)}...", ` +
                   `Results: ${responseBody.total_results}, ` +
                   `Processing: ${responseBody.processing_time_ms}ms, ` +
                   `Total: ${searchRes.timings.duration}ms, ` +
                   `Cache hit: ${isCacheHit}`);
      }
      
    } catch (e) {
      console.error(`Error parsing search response: ${e}`);
    }
  }

  // Test concurrent search patterns
  if (__ITER % 10 === 0) {
    // Every 10th iteration, perform a batch of similar queries to test cache efficiency
    const baseQuery = searchQueries[Math.floor(Math.random() * 5)]; // Use common queries
    
    const batchRequests = [];
    for (let i = 0; i < 3; i++) {
      const variation = generateQueryVariation(baseQuery);
      batchRequests.push([
        'POST',
        `${BASE_URL}/search`,
        JSON.stringify({ query: variation, top_k: 10 }),
        { headers: { 'Content-Type': 'application/json' } }
      ]);
    }
    
    const batchResponses = http.batch(batchRequests);
    
    // Check batch performance
    const batchSuccess = batchResponses.every(res => res.status === 200);
    const avgBatchTime = batchResponses.reduce((sum, res) => sum + res.timings.duration, 0) / batchResponses.length;
    
    check(batchResponses, {
      'batch search all successful': () => batchSuccess,
      'batch average time reasonable': () => avgBatchTime < 300,
    });
  }

  // Simulate realistic user behavior
  const thinkTime = Math.random() * 2 + 0.5; // 0.5-2.5 seconds between requests
  sleep(thinkTime);
}

export function handleSummary(data) {
  const searchSuccessRate = data.metrics.rag_search_success_rate ? data.metrics.rag_search_success_rate.values.rate : 0;
  const avgSearchDuration = data.metrics.rag_search_duration ? data.metrics.rag_search_duration.values.avg : 0;
  const p95SearchDuration = data.metrics.http_req_duration ? data.metrics.http_req_duration.values['p(95)'] : 0;
  const cacheHitRateValue = data.metrics.rag_cache_hit_rate ? data.metrics.rag_cache_hit_rate.values.rate : 0;
  const staleQueriesCount = data.metrics.rag_stale_queries ? data.metrics.rag_stale_queries.values.count : 0;
  
  const totalRequests = data.metrics.http_reqs.values.count;
  const requestRate = data.metrics.http_reqs.values.rate;
  
  return {
    'rag-engine-load-test-results.json': JSON.stringify(data, null, 2),
    stdout: `
🔍 RAG Engine Load Test Results
===============================

🎯 Test Configuration:
   • Duration: ~19 minutes with ramping stages
   • Max VUs: 200 concurrent users (targeting 1000 QPS)
   • Query Types: Common (60%), Medium (20%), Long-tail (20%)
   • Cache Strategy: Frequent queries for cache hit testing

📊 Performance Metrics:
   • Total Requests: ${totalRequests}
   • Request Rate: ${requestRate.toFixed(2)}/s
   • Average Response Time: ${data.metrics.http_req_duration.values.avg.toFixed(2)}ms
   • 95th Percentile: ${p95SearchDuration.toFixed(2)}ms

🎯 RAG-Specific Metrics:
   • Search Success Rate: ${(searchSuccessRate * 100).toFixed(1)}%
   • Average Search Duration: ${avgSearchDuration.toFixed(2)}ms
   • Cache Hit Rate: ${(cacheHitRateValue * 100).toFixed(1)}%
   • Stale Queries Detected: ${staleQueriesCount}

🚀 Throughput Analysis:
   • Peak QPS Achieved: ${Math.max(requestRate, 0).toFixed(0)}
   • Failed Requests: ${data.metrics.http_req_failed.values.count}
   • Error Rate: ${(data.metrics.http_req_failed.values.rate * 100).toFixed(2)}%

📋 SLO Compliance Check:
${p95SearchDuration < 200 ? '✅' : '❌'} Search Latency: <200ms (95th percentile) - ${p95SearchDuration.toFixed(2)}ms
${cacheHitRateValue > 0.70 ? '✅' : '❌'} Cache Hit Rate: >70% - ${(cacheHitRateValue * 100).toFixed(1)}%
${requestRate >= 1000 ? '✅' : '❌'} Throughput: ≥1000 QPS - ${requestRate.toFixed(0)} QPS
${searchSuccessRate > 0.99 ? '✅' : '❌'} Success Rate: >99% - ${(searchSuccessRate * 100).toFixed(1)}%
${staleQueriesCount < (totalRequests * 0.01) ? '✅' : '❌'} Stale Query Rate: <1% - ${((staleQueriesCount / totalRequests) * 100).toFixed(2)}%

🔧 Performance Insights:
   • Cache Effectiveness: ${cacheHitRateValue > 0.70 ? 'Excellent' : cacheHitRateValue > 0.50 ? 'Good' : 'Needs Improvement'}
   • Search Quality: ${staleQueriesCount < 10 ? 'High' : staleQueriesCount < 50 ? 'Medium' : 'Low'}
   • Scalability: ${requestRate >= 1000 ? 'Meets target' : 'Below target - consider optimization'}

💡 Recommendations:
${cacheHitRateValue < 0.70 ? '   • Optimize caching strategy for common queries\n' : ''}${p95SearchDuration > 200 ? '   • Investigate search latency bottlenecks\n' : ''}${requestRate < 1000 ? '   • Scale infrastructure or optimize query processing\n' : ''}${staleQueriesCount > 50 ? '   • Review index update frequency and quality\n' : ''}
===============================
`,
  };
}

# Operations Runbook

## Quick Reference

### Emergency Contacts
- **On-call Engineer**: +1-555-0123
- **Platform Team**: platform-team@company.com
- **Business Stakeholders**: business-ops@company.com

### Critical Dashboards
- **System Overview**: http://grafana.company.com/d/system-overview
- **Saga Metrics**: http://grafana.company.com/d/saga-metrics
- **Infrastructure**: http://grafana.company.com/d/infrastructure

### Key Metrics
- **Saga Success Rate**: >99.5%
- **API Response Time**: p95 < 500ms
- **System Availability**: >99.95%
- **Error Rate**: <0.1%

## Common Issues & Solutions

### 1. High Saga Failure Rate

**Symptoms:**
- Saga success rate drops below 99%
- Increased compensation events
- Customer complaints about failed orders

**Investigation Steps:**
```bash
# Check saga metrics
curl http://saga-orchestrator:9090/metrics | grep saga_failed_total

# Check recent failed sagas
curl "http://saga-orchestrator:8080/api/v1/sagas?status=FAILED&limit=10"

# Check service health
kubectl get pods -n microservices
```

**Common Causes & Solutions:**

1. **Downstream Service Failures**
   ```bash
   # Check service logs
   kubectl logs -n microservices deployment/inventory-service --tail=100
   kubectl logs -n microservices deployment/payment-service --tail=100
   
   # Restart unhealthy services
   kubectl rollout restart deployment/inventory-service -n microservices
   ```

2. **Database Connection Issues**
   ```bash
   # Check database connections
   kubectl exec -n microservices deployment/postgres -- psql -U postgres -c "SELECT count(*) FROM pg_stat_activity;"
   
   # Check connection pool metrics
   curl http://saga-orchestrator:9090/metrics | grep database_connections
   ```

3. **Kafka Issues**
   ```bash
   # Check Kafka cluster health
   kubectl exec -n microservices kafka-0 -- kafka-topics.sh --bootstrap-server localhost:9092 --list
   
   # Check consumer lag
   kubectl exec -n microservices kafka-0 -- kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --all-groups
   ```

### 2. High API Latency

**Symptoms:**
- API response times exceed SLA (p95 > 500ms)
- Timeout errors in client applications
- User complaints about slow responses

**Investigation Steps:**
```bash
# Check current latency metrics
curl http://saga-orchestrator:9090/metrics | grep http_request_duration

# Check resource utilization
kubectl top pods -n microservices

# Check database query performance
kubectl exec -n microservices deployment/postgres -- psql -U postgres -c "SELECT query, mean_time, calls FROM pg_stat_statements ORDER BY mean_time DESC LIMIT 10;"
```

**Solutions:**

1. **Scale Services**
   ```bash
   # Scale saga orchestrator
   kubectl scale deployment saga-orchestrator --replicas=5 -n microservices
   
   # Enable HPA if not already enabled
   kubectl apply -f infrastructure/k8s/hpa.yaml
   ```

2. **Database Optimization**
   ```bash
   # Check for missing indexes
   kubectl exec -n microservices deployment/postgres -- psql -U postgres -c "SELECT schemaname, tablename, attname, n_distinct, correlation FROM pg_stats WHERE schemaname = 'public';"
   
   # Analyze query plans
   kubectl exec -n microservices deployment/postgres -- psql -U postgres -c "EXPLAIN ANALYZE SELECT * FROM saga_instances WHERE status = 'IN_PROGRESS';"
   ```

### 3. Memory Leaks

**Symptoms:**
- Gradual increase in memory usage
- Out of memory errors
- Pod restarts due to resource limits

**Investigation Steps:**
```bash
# Check memory usage trends
kubectl top pods -n microservices --sort-by=memory

# Check memory metrics over time
curl "http://prometheus:9090/api/v1/query_range?query=container_memory_usage_bytes{namespace=\"microservices\"}&start=$(date -d '1 hour ago' +%s)&end=$(date +%s)&step=60"

# Get heap dumps (Go services)
kubectl exec -n microservices deployment/saga-orchestrator -- curl http://localhost:6060/debug/pprof/heap > heap.prof
```

**Solutions:**

1. **Immediate Relief**
   ```bash
   # Restart affected services
   kubectl rollout restart deployment/saga-orchestrator -n microservices
   
   # Increase memory limits temporarily
   kubectl patch deployment saga-orchestrator -n microservices -p '{"spec":{"template":{"spec":{"containers":[{"name":"saga-orchestrator","resources":{"limits":{"memory":"2Gi"}}}]}}}}'
   ```

2. **Long-term Fix**
   - Analyze heap dumps to identify memory leaks
   - Review code for goroutine leaks
   - Implement proper connection pooling
   - Add memory profiling to CI/CD

### 4. Database Connection Pool Exhaustion

**Symptoms:**
- "Too many connections" errors
- Slow database queries
- Service timeouts

**Investigation Steps:**
```bash
# Check current connections
kubectl exec -n microservices deployment/postgres -- psql -U postgres -c "SELECT count(*) FROM pg_stat_activity;"

# Check connection pool metrics
curl http://saga-orchestrator:9090/metrics | grep database_connections

# Check for long-running queries
kubectl exec -n microservices deployment/postgres -- psql -U postgres -c "SELECT pid, now() - pg_stat_activity.query_start AS duration, query FROM pg_stat_activity WHERE (now() - pg_stat_activity.query_start) > interval '5 minutes';"
```

**Solutions:**

1. **Immediate Actions**
   ```bash
   # Kill long-running queries
   kubectl exec -n microservices deployment/postgres -- psql -U postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE (now() - pg_stat_activity.query_start) > interval '10 minutes';"
   
   # Restart services to reset connection pools
   kubectl rollout restart deployment/saga-orchestrator -n microservices
   ```

2. **Configuration Tuning**
   ```bash
   # Increase max connections (requires restart)
   kubectl exec -n microservices deployment/postgres -- psql -U postgres -c "ALTER SYSTEM SET max_connections = 200;"
   kubectl rollout restart statefulset/postgres -n microservices
   
   # Tune connection pool settings in services
   kubectl set env deployment/saga-orchestrator DB_MAX_OPEN_CONNS=25 DB_MAX_IDLE_CONNS=5 -n microservices
   ```

### 5. Kafka Consumer Lag

**Symptoms:**
- Events not being processed timely
- Increasing consumer lag metrics
- Delayed saga step execution

**Investigation Steps:**
```bash
# Check consumer group lag
kubectl exec -n microservices kafka-0 -- kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --group saga-orchestrator-group

# Check Kafka metrics
curl http://kafka:9308/metrics | grep kafka_consumer_lag

# Check partition distribution
kubectl exec -n microservices kafka-0 -- kafka-topics.sh --bootstrap-server localhost:9092 --describe --topic saga-events
```

**Solutions:**

1. **Scale Consumers**
   ```bash
   # Increase consumer instances
   kubectl scale deployment saga-orchestrator --replicas=3 -n microservices
   
   # Add more partitions to topics
   kubectl exec -n microservices kafka-0 -- kafka-topics.sh --bootstrap-server localhost:9092 --alter --topic saga-events --partitions 6
   ```

2. **Optimize Processing**
   ```bash
   # Increase batch size and timeout
   kubectl set env deployment/saga-orchestrator KAFKA_BATCH_SIZE=1000 KAFKA_BATCH_TIMEOUT=100ms -n microservices
   ```

## Monitoring & Alerting

### Key Alerts

1. **High Error Rate**
   ```promql
   rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m]) > 0.01
   ```

2. **High Latency**
   ```promql
   histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m])) > 0.5
   ```

3. **Saga Failure Rate**
   ```promql
   rate(saga_failed_total[5m]) / rate(saga_created_total[5m]) > 0.005
   ```

4. **Database Connections**
   ```promql
   database_connections{state="open"} / database_connections{state="max"} > 0.8
   ```

### Dashboard Queries

1. **Request Rate**
   ```promql
   sum(rate(http_requests_total[5m])) by (service)
   ```

2. **Error Rate**
   ```promql
   sum(rate(http_requests_total{status=~"5.."}[5m])) by (service) / sum(rate(http_requests_total[5m])) by (service)
   ```

3. **Saga Success Rate**
   ```promql
   sum(rate(saga_completed_total[5m])) / sum(rate(saga_created_total[5m]))
   ```

## Maintenance Procedures

### 1. Rolling Updates

```bash
# Update saga orchestrator
kubectl set image deployment/saga-orchestrator saga-orchestrator=microservices-saga/saga-orchestrator:v1.2.0 -n microservices

# Monitor rollout
kubectl rollout status deployment/saga-orchestrator -n microservices

# Rollback if needed
kubectl rollout undo deployment/saga-orchestrator -n microservices
```

### 2. Database Maintenance

```bash
# Backup database
kubectl exec -n microservices postgres-0 -- pg_dump -U postgres microservices > backup-$(date +%Y%m%d).sql

# Vacuum and analyze
kubectl exec -n microservices postgres-0 -- psql -U postgres -c "VACUUM ANALYZE;"

# Check database size
kubectl exec -n microservices postgres-0 -- psql -U postgres -c "SELECT pg_size_pretty(pg_database_size('microservices'));"
```

### 3. Log Rotation

```bash
# Clean old logs (if using file logging)
kubectl exec -n microservices deployment/saga-orchestrator -- find /var/log -name "*.log" -mtime +7 -delete

# Restart log aggregation
kubectl rollout restart daemonset/fluentd -n logging
```

## Disaster Recovery

### 1. Database Recovery

```bash
# Restore from backup
kubectl exec -n microservices postgres-0 -- psql -U postgres -c "DROP DATABASE microservices;"
kubectl exec -n microservices postgres-0 -- psql -U postgres -c "CREATE DATABASE microservices;"
kubectl exec -i -n microservices postgres-0 -- psql -U postgres microservices < backup-20231201.sql
```

### 2. Kafka Recovery

```bash
# Check topic health
kubectl exec -n microservices kafka-0 -- kafka-topics.sh --bootstrap-server localhost:9092 --describe

# Recreate topics if needed
kubectl exec -n microservices kafka-0 -- kafka-topics.sh --bootstrap-server localhost:9092 --create --topic saga-events --partitions 3 --replication-factor 2
```

### 3. Service Recovery

```bash
# Restart all services
kubectl rollout restart deployment/saga-orchestrator -n microservices
kubectl rollout restart deployment/inventory-service -n microservices
kubectl rollout restart deployment/payment-service -n microservices
kubectl rollout restart deployment/notification-service -n microservices

# Wait for all services to be ready
kubectl wait --for=condition=available --timeout=300s deployment --all -n microservices
```

## Performance Tuning

### 1. Database Tuning

```sql
-- Connection settings
ALTER SYSTEM SET max_connections = 200;
ALTER SYSTEM SET shared_buffers = '256MB';
ALTER SYSTEM SET effective_cache_size = '1GB';

-- Query optimization
ALTER SYSTEM SET random_page_cost = 1.1;
ALTER SYSTEM SET seq_page_cost = 1.0;

-- Checkpoint settings
ALTER SYSTEM SET checkpoint_completion_target = 0.9;
ALTER SYSTEM SET wal_buffers = '16MB';
```

### 2. JVM Tuning (if using Java services)

```bash
# Set JVM options
kubectl set env deployment/payment-service JAVA_OPTS="-Xms512m -Xmx1024m -XX:+UseG1GC -XX:MaxGCPauseMillis=200" -n microservices
```

### 3. Go Service Tuning

```bash
# Set Go runtime options
kubectl set env deployment/saga-orchestrator GOMAXPROCS=4 GOGC=100 -n microservices
```

## Security Procedures

### 1. Certificate Rotation

```bash
# Update TLS certificates
kubectl create secret tls microservices-tls --cert=new-cert.pem --key=new-key.pem -n microservices --dry-run=client -o yaml | kubectl apply -f -

# Restart services to pick up new certificates
kubectl rollout restart deployment --all -n microservices
```

### 2. Secret Rotation

```bash
# Update database password
kubectl create secret generic postgres-secret --from-literal=password=new-password -n microservices --dry-run=client -o yaml | kubectl apply -f -

# Restart services
kubectl rollout restart statefulset/postgres -n microservices
kubectl rollout restart deployment --all -n microservices
```

## Contact Information

### Escalation Path
1. **Level 1**: On-call Engineer
2. **Level 2**: Platform Team Lead
3. **Level 3**: Engineering Manager
4. **Level 4**: CTO

### External Dependencies
- **Payment Provider**: support@payment-provider.com
- **Cloud Provider**: enterprise-support@cloud-provider.com
- **Monitoring Vendor**: support@monitoring-vendor.com

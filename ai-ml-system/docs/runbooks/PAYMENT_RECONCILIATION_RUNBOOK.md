# Payment Reconciliation Incident Runbook

## Overview

This runbook provides step-by-step procedures for handling payment reconciliation incidents, including webhook delays, duplicates, saga failures, and RAG data inconsistencies.

## Incident Types Covered

- **Webhook Processing Issues:** Late/duplicate webhooks from payment providers
- **Saga Orchestration Failures:** Timeout and compensation failures
- **Data Inconsistencies:** Cross-service data synchronization issues
- **RAG Data Corruption:** Stale or incorrect payment information in search results

## Severity Classification

| Severity | Criteria | Response Time | Escalation |
|----------|----------|---------------|------------|
| **Critical** | Payment processing completely down, data corruption affecting >1000 users | 15 minutes | Immediate page to on-call engineer + manager |
| **High** | Significant payment delays, incorrect customer-facing information | 30 minutes | Page to on-call engineer |
| **Medium** | Minor processing delays, isolated data inconsistencies | 1 hour | Slack notification to team |
| **Low** | Monitoring alerts, no customer impact | 4 hours | Create ticket for next business day |

## Detection and Alerting

### Key Monitoring Alerts

1. **Webhook Processing Errors**
   - Alert: `webhook_processing_errors > 10 per minute`
   - Dashboard: Payment Processing Overview
   - Runbook: [Webhook Processing Issues](#webhook-processing-issues)

2. **Saga Compensation Failures**
   - Alert: `saga_compensation_failures > 5 per hour`
   - Dashboard: Saga Orchestration Health
   - Runbook: [Saga Orchestration Failures](#saga-orchestration-failures)

3. **RAG Stale Data Detection**
   - Alert: `rag_stale_queries > 20 per hour`
   - Dashboard: RAG Data Quality
   - Runbook: [RAG Data Corruption](#rag-data-corruption)

4. **Payment Reconciliation Discrepancies**
   - Alert: `payment_discrepancies > 50 per day`
   - Dashboard: Payment Reconciliation
   - Runbook: [Data Inconsistencies](#data-inconsistencies)

### Monitoring Dashboards

- **Payment Processing Overview:** http://grafana.internal/d/payment-overview
- **Saga Orchestration Health:** http://grafana.internal/d/saga-health
- **RAG Data Quality:** http://grafana.internal/d/rag-quality
- **System Health Summary:** http://grafana.internal/d/system-health

## Incident Response Procedures

### Initial Response (First 5 Minutes)

1. **Acknowledge the Alert**
   ```bash
   # Acknowledge in PagerDuty/Slack
   /pd ack [incident-id] "Investigating payment reconciliation issue"
   ```

2. **Check System Health**
   ```bash
   # Quick health check of all services
   curl http://localhost:8080/health  # Data Ingestion
   curl http://localhost:8081/health  # RAG Engine
   curl http://localhost:8082/health  # Drift Detection
   ```

3. **Assess Impact Scope**
   ```bash
   # Check recent error rates
   kubectl logs -f deployment/data-ingestion --tail=100
   kubectl logs -f deployment/rag-engine --tail=100
   kubectl logs -f deployment/saga-orchestrator --tail=100
   ```

4. **Determine Incident Type**
   - Review alert details and error patterns
   - Check recent deployments or configuration changes
   - Identify affected payment providers or user segments

### Webhook Processing Issues

#### Symptoms
- High webhook processing error rates
- Duplicate payment processing attempts
- Delayed payment status updates
- Customer complaints about payment status

#### Investigation Steps

1. **Check Webhook Queue Health**
   ```bash
   # Check Kafka topic lag
   kafka-consumer-groups --bootstrap-server localhost:9092 \
     --group webhook-processor --describe
   
   # Check Redis deduplication cache
   redis-cli -h localhost -p 6379 info memory
   redis-cli -h localhost -p 6379 dbsize
   ```

2. **Analyze Webhook Patterns**
   ```bash
   # Check for duplicate webhooks
   kubectl logs deployment/data-ingestion | grep "duplicate_detected" | tail -20
   
   # Check webhook delay patterns
   kubectl logs deployment/data-ingestion | grep "webhook_delay" | tail -20
   ```

3. **Identify Affected Payment Providers**
   ```bash
   # Check error rates by provider
   curl "http://prometheus:9090/api/v1/query?query=rate(webhook_errors_total[5m])"
   ```

#### Mitigation Steps

1. **Immediate Mitigation**
   ```bash
   # Pause webhook processing if critical
   kubectl scale deployment/webhook-processor --replicas=0
   
   # Increase deduplication cache TTL
   redis-cli -h localhost -p 6379 config set maxmemory-policy allkeys-lru
   ```

2. **Clear Duplicate Processing**
   ```bash
   # Clear duplicate processing locks
   redis-cli -h localhost -p 6379 --scan --pattern "webhook_lock:*" | xargs redis-cli del
   
   # Restart webhook processing with higher dedup TTL
   kubectl set env deployment/data-ingestion DEDUPE_TTL_HOURS=48
   kubectl rollout restart deployment/data-ingestion
   ```

3. **Resume Processing**
   ```bash
   # Scale back up webhook processors
   kubectl scale deployment/webhook-processor --replicas=3
   
   # Monitor recovery
   watch "curl -s http://localhost:8080/metrics | grep webhook_processing"
   ```

### Saga Orchestration Failures

#### Symptoms
- Saga timeout errors
- Compensation step failures
- Inconsistent payment states across services
- Failed payment reversals

#### Investigation Steps

1. **Check Saga Status**
   ```bash
   # Check active sagas
   curl http://localhost:8080/api/v1/sagas/status
   
   # Check failed sagas
   kubectl logs deployment/saga-orchestrator | grep "saga_failed" | tail -20
   ```

2. **Analyze Compensation Failures**
   ```bash
   # Check compensation step failures
   kubectl logs deployment/saga-orchestrator | grep "compensation_failed"
   
   # Check timeout patterns
   kubectl logs deployment/saga-orchestrator | grep "saga_timeout"
   ```

#### Mitigation Steps

1. **Manual Saga Recovery**
   ```bash
   # List stuck sagas
   curl http://localhost:8080/api/v1/sagas?status=stuck
   
   # Manually trigger compensation for specific saga
   curl -X POST http://localhost:8080/api/v1/sagas/{saga_id}/compensate
   ```

2. **Increase Timeout Values**
   ```bash
   # Temporarily increase saga timeouts
   kubectl set env deployment/saga-orchestrator SAGA_TIMEOUT_MINUTES=10
   kubectl rollout restart deployment/saga-orchestrator
   ```

3. **Validate Data Consistency**
   ```bash
   # Run payment reconciliation job
   kubectl create job payment-reconciliation-$(date +%s) \
     --from=cronjob/payment-reconciliation
   ```

### RAG Data Corruption

#### Symptoms
- Incorrect payment status in customer support responses
- Stale payment information in search results
- High confidence scores for incorrect answers
- Customer complaints about wrong information

#### Investigation Steps

1. **Check RAG Index Health**
   ```bash
   # Check index statistics
   curl http://localhost:8081/index/stats
   
   # Check recent indexing errors
   kubectl logs deployment/rag-engine | grep "indexing_error" | tail -20
   ```

2. **Validate Data Freshness**
   ```bash
   # Check last index update time
   curl http://localhost:8081/index/stats | jq '.last_updated'
   
   # Search for known stale data
   curl -X POST http://localhost:8081/search \
     -H "Content-Type: application/json" \
     -d '{"query": "payment status", "top_k": 10}'
   ```

#### Mitigation Steps

1. **Immediate Response**
   ```bash
   # Clear stale cache entries
   redis-cli -h localhost -p 6379 flushdb
   
   # Trigger immediate reindexing
   curl -X POST http://localhost:8081/admin/reindex
   ```

2. **Blue/Green Index Swap**
   ```bash
   # Check current active index
   curl http://localhost:8081/deployment/status
   
   # Trigger blue/green swap if available
   curl -X POST http://localhost:8081/deployment/swap
   ```

3. **Validate Fix**
   ```bash
   # Test search with known payment IDs
   curl -X POST http://localhost:8081/search \
     -H "Content-Type: application/json" \
     -d '{"query": "payment PAY123 status", "top_k": 5}'
   ```

### Data Inconsistencies

#### Symptoms
- Payment status mismatches between services
- Reconciliation job failures
- Database constraint violations
- Audit trail gaps

#### Investigation Steps

1. **Check Database Consistency**
   ```bash
   # Connect to payment database
   psql -h postgres -U payment_user -d payments
   
   # Check for orphaned records
   SELECT COUNT(*) FROM payments p 
   LEFT JOIN payment_events pe ON p.id = pe.payment_id 
   WHERE pe.payment_id IS NULL;
   ```

2. **Validate Cross-Service Data**
   ```bash
   # Check data consistency across services
   python scripts/validate_payment_consistency.py --payment-id PAY123
   ```

#### Mitigation Steps

1. **Run Reconciliation Job**
   ```bash
   # Trigger immediate reconciliation
   kubectl create job payment-reconciliation-emergency-$(date +%s) \
     --from=cronjob/payment-reconciliation
   
   # Monitor job progress
   kubectl logs job/payment-reconciliation-emergency-* -f
   ```

2. **Fix Data Inconsistencies**
   ```bash
   # Run data repair script
   python scripts/repair_payment_data.py --dry-run
   python scripts/repair_payment_data.py --execute
   ```

## Recovery Validation

### Health Check Checklist

- [ ] All services responding to health checks
- [ ] Webhook processing error rate < 1%
- [ ] Saga success rate > 99%
- [ ] RAG search latency < 200ms P95
- [ ] Payment reconciliation discrepancies < 10 per hour
- [ ] No customer-facing errors reported

### Validation Commands

```bash
# Service health
for service in data-ingestion rag-engine drift-detection; do
  echo "Checking $service..."
  curl -f http://localhost:808{0,1,2}/health || echo "FAILED: $service"
done

# Processing metrics
curl -s http://localhost:9090/api/v1/query?query=rate(http_requests_total[5m])

# Data consistency
python scripts/validate_system_consistency.py --full-check
```

## Escalation Procedures

### When to Escalate

- Incident duration > 2 hours without resolution
- Customer impact affecting > 1000 users
- Data corruption requiring manual intervention
- Multiple system failures indicating systemic issue

### Escalation Contacts

- **On-Call Engineer:** +1-555-0123 (PagerDuty)
- **Engineering Manager:** @eng-manager (Slack)
- **SRE Lead:** @sre-lead (Slack)
- **Product Manager:** @product-manager (Slack)

### Communication Templates

#### Initial Incident Report
```
🚨 INCIDENT: Payment Reconciliation Issue
Severity: [HIGH/CRITICAL]
Impact: [Brief description]
ETA: [Estimated resolution time]
Updates: Will provide updates every 30 minutes
```

#### Status Update
```
📊 UPDATE: Payment Reconciliation Incident
Status: [Investigating/Mitigating/Resolved]
Progress: [What's been done]
Next Steps: [What's happening next]
ETA: [Updated estimate]
```

#### Resolution Notice
```
✅ RESOLVED: Payment Reconciliation Incident
Duration: [Total incident time]
Root Cause: [Brief explanation]
Actions Taken: [Summary of fixes]
Follow-up: Postmortem scheduled for [date/time]
```

## Prevention and Monitoring

### Preventive Measures

1. **Enhanced Monitoring**
   - Add webhook delay detection alerts
   - Implement saga timeout prediction
   - Create RAG data freshness validation

2. **Automated Recovery**
   - Auto-restart failed saga compensations
   - Automatic cache clearing on stale data detection
   - Self-healing webhook processing

3. **Regular Maintenance**
   - Weekly payment reconciliation reports
   - Monthly RAG index quality reviews
   - Quarterly disaster recovery testing

### Key Metrics to Monitor

- Webhook processing latency (P95 < 3s)
- Saga success rate (> 99.5%)
- RAG search accuracy (> 95%)
- Payment reconciliation discrepancies (< 50/day)
- Cross-service data consistency (> 99.9%)

## Related Documentation

- [Payment Processing Architecture](../architecture/payment-processing.md)
- [Saga Pattern Implementation](../architecture/saga-pattern.md)
- [RAG System Design](../architecture/rag-system.md)
- [Monitoring and Alerting Guide](../monitoring/alerting-guide.md)
- [Disaster Recovery Plan](../disaster-recovery/payment-systems.md)

---

**Last Updated:** 2024-01-15  
**Next Review:** 2024-04-15  
**Owner:** Platform Engineering Team

continue:
# Cross-system / Capstone challenges (Integrations)

> Những bài này ép bạn phải tổ chức end-to-end: ingestion → microservices → dbs → analytics → ML.
> 

### A) End-to-end incident: payment reconciliation gone wrong (Expert)

- **Scenario:** Payment provider webhook delivered late/duplicated → events processed out-of-order across services → incorrect RAG answers referencing wrong payments.
- **Task:** Trace the incident, fix root causes across ingestion (dedupe), saga flow (compensation), DB consistency (reconciliation), and retrain RAG to avoid surfacing stale info.
- **Deliverables:** Postmortem, fixes, tests, and DR plan.

### B) Full blue/green rollout for a new ML model + schema change (Expert)

- **Scenario:** New embedding model + user profile schema change must be rolled out with A/B test, fallback, and analytics comparison.
- **Task:** Build model registry, automated reindex path, schema migration with dual writes, and rollback plan. Prove statistically significant improvement before full cutover.

### C) Observability & SLO enforcement across stack (Advanced)

- **Scenario:** Define SLOs for user-visible latency, accuracy of bot answers, and data freshness. Implement monitoring, alerting, and automated remediation (restart consumer, scale workers).
- **Task:** Implement SLO dashboards, automated runbooks, and show incident injection → remediation.

# How to simulate & test (practical toolset)

- **Load & functional testing:** Locust, k6, Gatling.
- **Chaos engineering:** Chaos Mesh, Litmus, Gremlin.
- **Data replay/backfill:** Kafka + MirrorMaker, kcat, custom producers.
- **Local k8s testing:** kind, minikube, k3s.
- **CI/CD / infra as code:** GitHub Actions, Argo CD, Terraform.
- **DB tools:** pgBackRest, pglogical, gh-ost, Vitess, MongoDB tools (mongodump/restore, resharding).
- **ML ops:** MLflow, Kubeflow, Argo Workflows.
- **Observability:** Prometheus (p8s), Grafana, Jaeger, OpenTelemetry, Loki.
- **Vector DBs / RAG:** Milvus, Pinecone, Weaviate, FAISS local.
- **Message brokers:** Kafka, Redpanda, RabbitMQ.
- **Search & analytics:** Elasticsearch, ClickHouse, Postgres + timescaledb if needed.

# Suggested learning roadmap (how to practice)

1. **Run chaos tests** on the integrated stack and observe traces/alerts.
2. **Document postmortems and runbooks** for each failure type.
# ADR-007: Resilience, Async Processing, and Scalability (Design Doc)

**Date:** 2026-06-26
**Status:** Documented (not yet implemented — see "What a real deployment would add")

## Context

The central EMR node is a **single point of failure** for all participating hospitals. An outage renders every connected hospital unable to access patient records. The checklist (§19) requires a resilience and scalability story even if the prototype runs single-instance.

## Current prototype posture

- Single Gunicorn + Neon Postgres (serverless, managed HA on Neon's side).
- No async task queue; audit writes are synchronous in the request path.
- No caching; every request hits the DB.
- Session store is Postgres (`django_session` table); shares the same DB connection as the app.

## Design for production

### 1. Asynchronous processing — Celery + Redis

Work that should leave the request path:
- Audit log writes (currently synchronous; acceptable for prototype volume but adds latency at scale).
- Email/alert notifications (break-glass events, failed login alerts, 5xx spikes).
- FHIR bundle generation for large `$everything` requests.
- Inter-hospital sync batch jobs.

**Chosen approach**: Celery workers + Redis broker. Redis also serves as the session backend and cache.

### 2. Database HA — Primary + Read Replica

- Primary Postgres for all writes.
- One or more read replicas for read-heavy queries (patient search, audit log browse, FHIR reads).
- Application uses Django's `DATABASE_ROUTERS` to direct reads to replicas.
- **Failover**: Neon's serverless tier provides managed HA with automatic failover. Self-hosted: use Patroni or AWS RDS Multi-AZ.

### 3. Graceful degradation

- If the primary DB is unreachable, the app switches to **read-only mode** (serve cached/replicated data; block writes with a clear error).
- `/healthz/` reports degraded status; load balancer routes traffic away from unhealthy nodes.

### 4. Connection pooling — PgBouncer

At 50+ concurrent connections, Django's per-process connection model causes Postgres connection exhaustion. PgBouncer (transaction-mode) acts as a multiplexer between Gunicorn workers and Postgres.

### 5. Audit log partitioning

The audit log will grow faster than any other table (every PHI read generates a row). Partition by time (e.g. monthly):
```sql
CREATE TABLE audit_auditlog_2026m06 PARTITION OF audit_auditlog
FOR VALUES FROM ('2026-06-01') TO ('2026-07-01');
```
Old partitions become read-only; queries against recent data hit only the current partition.

### 6. Caching strategy (Redis)

- **Cache**: terminology lookups (ICD-10 code lists, LOINC descriptions) — long TTL (24 h), no PHI.
- **Never cache**: patient records, encounters, or any PHI. The cache is not subject to the same access control as the DB.
- **Session store**: move `django_session` from Postgres to Redis for lower latency and TTL-native expiry.

### 7. Idempotency keys

Write endpoints (encounter creation, diagnosis, prescription) should accept an `Idempotency-Key` header. A Redis-backed key store prevents double-creation when a network retry causes a request to be submitted twice.

### 8. Horizontal scaling

The app tier is already stateless (sessions in DB/Redis; no in-process state). To scale horizontally:
1. Move sessions to Redis.
2. Deploy N Gunicorn containers behind a load balancer.
3. Share PgBouncer pool across all app containers.
4. Use `ATOMIC_REQUESTS = True` to ensure DB consistency under concurrent load.

## What a real production deployment would add

- Live Celery + Redis deployment (Docker Compose service, or managed Redis on AWS/GCP).
- PgBouncer sidecar in the `docker-compose.yml`.
- DB replication and tested failover procedure.
- Idempotency key implementation on all write endpoints.
- k6 or Locust load test validating the p95 < 500 ms NFR at 50 concurrent users.
- Distributed tracing with OpenTelemetry if the system splits into microservices.

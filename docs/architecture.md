# Architecture Document

## 1. Goals
The system targets 100k daily consultations, p95 read latency below 200ms, p95 write latency below 500ms and 99.95% availability.

## 2. Architecture
FastAPI provides stateless REST APIs. PostgreSQL is the source of truth. Redis is used for cache/rate limiting and as the Celery broker. Workers process asynchronous tasks. Prometheus/Grafana provide metrics and OpenTelemetry provides tracing.

## 3. Booking data flow
Patient -> API -> authentication/RBAC -> PostgreSQL transaction -> row lock on availability slot -> create consultation -> mark slot booked -> audit log -> commit.

## 4. Concurrency
Booking uses a PostgreSQL row-level lock and unique constraints. This prevents double-booking under concurrent requests.

## 5. Idempotency
Write operations accept an Idempotency-Key. The booking workflow checks for an existing booking before locking and mutating the slot. A production extension would persist a dedicated idempotency-key table with request hash and response payload.

## 6. Caching
Doctor search and availability are suitable cache candidates. Booking must always validate availability against PostgreSQL.

## 7. Transactions and sagas
Database-local booking operations are atomic. Cross-system operations such as payment/notification should use an outbox/saga pattern with compensating actions.

## 8. Partitioning
Audit logs can be range-partitioned by month. Consultation history can be partitioned by time in a larger deployment.

## 9. Backup and DR
Use automated PostgreSQL backups, WAL archiving and periodic restore drills. Define RPO/RTO based on business requirements. Production deployment should use multi-zone database infrastructure.

## 10. Scalability
API instances are stateless and can scale horizontally behind a load balancer. PostgreSQL uses pooling and indexes; Redis reduces read pressure; workers scale independently.

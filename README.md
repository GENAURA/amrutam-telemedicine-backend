# Amrutam Telemedicine Backend

Production-oriented backend assignment implementation using FastAPI, PostgreSQL, Redis, Celery, Docker, Prometheus, Grafana and OpenTelemetry.

## Assignment coverage
- User lifecycle, authentication and RBAC
- Doctor availability and booking
- Consultation lifecycle and prescriptions
- Search/filtering
- Audit trails
- Admin analytics
- Idempotent writes and booking concurrency protection
- Redis caching and rate limiting
- Async background jobs
- Automated tests
- CI pipeline
- Observability
- Security/threat model and architecture docs

## Quick start

```bash
cp .env.example .env
docker compose up --build
```

API: http://localhost:8000
Swagger: http://localhost:8000/docs
Prometheus: http://localhost:9090
Grafana: http://localhost:3000

Run tests:
```bash
docker compose run --rm api pytest
```

## Demo users
The seed script creates:
- admin@example.com / Admin@123
- doctor@example.com / Doctor@123
- patient@example.com / Patient@123

Change these passwords before any real deployment.

## Notes
This repository is an assignment/reference implementation. External payment, SMS/email providers and production secret-management systems are represented by interfaces/configuration rather than real provider credentials.

# Threat Model

| Asset | Threat | Mitigation |
|---|---|---|
| User credentials | Credential theft | Argon2, HTTPS, short-lived access tokens |
| Patient records | Unauthorized access | RBAC + ownership checks + audit logs |
| Booking slot | Double booking | DB transaction + row lock + unique constraints |
| API | Abuse | Rate limiting + validation |
| Secrets | Source leakage | Environment variables / production secret manager |
| Dependencies | Known CVEs | pip-audit in CI |
| Admin endpoints | Privilege escalation | Explicit ADMIN role dependency |
| Audit trail | Tampering | Append-oriented logs and restricted access |

Attack surface includes public API endpoints, authentication, booking writes, admin APIs, database credentials, Redis and CI/CD artifacts.

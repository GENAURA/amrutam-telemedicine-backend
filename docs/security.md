# Security Checklist

- [x] Password hashing with Argon2
- [x] JWT authentication
- [x] Role-based authorization
- [x] Input validation with Pydantic
- [x] SQLAlchemy parameterized queries
- [x] Secrets through environment variables
- [x] Audit logging
- [x] Database constraints
- [x] Rate-limiting dependency included
- [x] Dependency scanning in CI
- [ ] TLS termination: configure at load balancer/reverse proxy
- [ ] Production MFA provider: integrate TOTP/WebAuthn
- [ ] Production key management: use KMS/Vault
- [ ] Encryption at rest: enable managed PostgreSQL encryption
- [ ] Key rotation: rotate JWT signing keys using KMS/key IDs

## Data classification
Public: service metadata.
Internal: operational metrics.
Confidential: user profiles, appointments and prescriptions.
Highly sensitive: authentication credentials and health information.

## OWASP considerations
Address broken access control through RBAC and ownership checks; injection through SQLAlchemy; authentication failures through token expiry and password hashing; security misconfiguration through environment-based configuration; logging/monitoring through structured audit and metrics.

# API Overview

Authentication:
- POST /api/v1/auth/register
- POST /api/v1/auth/login

Doctors:
- GET /api/v1/doctors
- POST /api/v1/doctors
- POST /api/v1/doctors/{doctor_id}/availability
- GET /api/v1/doctors/{doctor_id}/availability

Consultations:
- POST /api/v1/consultations
- GET /api/v1/consultations
- POST /api/v1/consultations/{id}/start
- POST /api/v1/consultations/{id}/complete
- POST /api/v1/consultations/{id}/prescription

Admin:
- GET /api/v1/admin/analytics
- GET /api/v1/admin/audit-logs

OpenAPI is generated automatically by FastAPI at /docs and /openapi.json.

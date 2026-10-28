# Backup and Disaster Recovery

## Backup
- Daily full PostgreSQL backup.
- Continuous WAL archiving in production.
- Retain backups according to compliance/business policy.
- Encrypt backups.

## Recovery
1. Provision clean PostgreSQL.
2. Restore latest full backup.
3. Replay WAL to the target recovery point.
4. Verify application health.
5. Validate critical tables and indexes.
6. Re-enable traffic.

## Resilience
Run API instances across availability zones in production. Use managed PostgreSQL with replication/failover. Redis should be treated as recoverable cache/broker state rather than the system of record.

RPO and RTO should be finalized with the business owner; this assignment does not specify numerical values.

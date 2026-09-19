# ASAS LIMS 9.3 — Operational hardening

This release strengthens the existing laboratory system without replacing its
data model or user workflows.

## Included

- Database connections use WAL mode and a bounded busy timeout for safer
  concurrent access on the single-instance SQLite deployment.
- Authenticated sessions expire after 12 hours by default.
- Repeated failed login attempts are throttled per client and account.
- JSON request bodies are bounded to protect server memory.
- `GET /api/health` checks service and database readiness for the hosting
  platform without exposing laboratory data.
- `GET /api/system/status` gives authorized managers database integrity,
  storage size, queued-sync and active-session indicators.
- `POST /api/system/backup` creates a consistent online SQLite backup for the
  system administrator or quality manager and records the operation in the
  audit trail.
- Render now checks `/api/health`, stores backups on the persistent disk and
  declares the operational security defaults explicitly.

## Verification

Run `python -m unittest -v test_server.py`. The suite covers schema migration,
roles, users, quality records, attachments, field visits, CORS, projects,
health checks, session expiry and online backup creation.

## Deployment note

The current architecture remains intentionally single-instance because it uses
SQLite on one persistent disk. Horizontal scaling requires an approved migration
to a central PostgreSQL database and shared object storage for attachments.

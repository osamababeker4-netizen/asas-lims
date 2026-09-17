# ASAS LIMS additive integration reference
# Source supplied by project owner on 2026-09-17.
# IMPORTANT: This module is intentionally isolated so the current ASAS production UI,
# data model, uploads, audit/sync behavior, branding, and deployment are not overwritten.
# It is a staging/reference module for selectively integrating the following capabilities
# into the existing server.py after compatibility tests:
# - SQLAlchemy models: user groups, sessions, instruments, inventory, orders, samples,
#   method analyses, results and audit trail
# - FastAPI login/session workflow
# - sample batch creation and result entry
# - approval workflow
# - sample tag/certificate rendering
# - CSV export
# - instrument/inventory/audit APIs
#
# The original supplied implementation is preserved in project discussion/history.
# Do not run this file as the production entrypoint; it uses its own SQLite schema and
# contains TECHNO branding/demo credentials that must not replace ASAS production values.

INTEGRATION_VERSION = "9.0.0-reference"
INTEGRATION_MODE = "ADDITIVE_ONLY"
PRESERVE_EXISTING_SYSTEM = True

CAPABILITIES = {
    "user_groups": True,
    "session_auth": True,
    "lab_instruments": True,
    "inventory": True,
    "order_requests": True,
    "sample_records": True,
    "method_analyses": True,
    "sample_results": True,
    "audit_trail": True,
    "batch_sample_creation": True,
    "result_oos_check": True,
    "supervisor_approval": True,
    "sample_tag": True,
    "certificate": True,
    "csv_export": True,
}

# Integration safety notes:
# 1. Keep current ASAS branding and identity; do not import TECHNO_* presentation constants.
# 2. Never seed default plaintext/demo credentials into production.
# 3. Reuse/migrate the existing ASAS database instead of creating a parallel lims.db.
# 4. Protect every mutation and sensitive read with the existing authentication/RBAC layer.
# 5. Preserve current smart upload, classification, skipped-file reporting, downloads,
#    controlled audit deletion and live synchronization.
# 6. Add schema migrations and regression tests before wiring routes into production.

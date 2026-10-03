# Pharmacy AI platform roadmap

The platform is built in dependency order: reliable records and business rules first, then integrations and AI. A stage is complete only when its implementation and acceptance checks are reviewed.

| # | Stage | Status |
|---:|---|---|
| 1 | Local development setup: Python, Git, FastAPI; no Docker requirement | Verified; local startup and dependency resolution pass |
| 2 | SQLite and SQLAlchemy persistence | Verified; schema creation and persisted API writes pass |
| 3 | Product create/read/update/archive API | Verified; CRUD, validation, barcode uniqueness, and missing-record checks pass |
| 4 | Core pharmacy data model and API structure | Verified; entity tables, relationships, and foreign keys pass inspection |
| 5 | Inventory batches, expiry, and stock summaries | Verified; batch CRUD, expiry filtering, and stock summaries pass |
| 6 | Sales, atomic stock deduction, FEFO, and batch traceability | Verified; FEFO allocations, multi-item sales, and rollback checks pass |
| 7 | Suppliers, purchase orders, receiving, and stock increases | Built; local run pending |
| 8 | Deterministic sales, margin, expiry, and inventory analytics | Built; local run pending |
| 9 | AI agent architecture and orchestration | Planned |
| 10 | Typed agent tools over business services | Planned |
| 11 | Conversation memory and document retrieval | Planned |
| 12 | Roles, permissions, approvals, and audit records | Account sign-in and pharmacy isolation built; staff roles and audit records planned |
| 13 | n8n workflows | Planned |
| 14 | Telegram integration | Planned |
| 15 | WhatsApp Business integration and customer safety boundaries | Planned |
| 16 | Demand and stockout forecasting | Planned |
| 17 | Unit, integration, API, and agent test coverage | Planned |
| 18 | PostgreSQL and managed schema migrations | PostgreSQL connection support built; versioned migrations planned |
| 19 | Production configuration and deployment | Docker and Render configuration built; hosted deployment pending account/repository connection |
| 20 | Monitoring, backups, security hardening, and tenant isolation | Account isolation and browser security built; hosted backups and broader security review pending |

## Architecture decisions for the first checkpoint

- SQLite is the local default. SQLAlchemy keeps persistence behind a database session so a later PostgreSQL migration does not require rewriting route logic.
- Inventory is represented by dated batches, not a product-level stock counter. Sellable quantity excludes expired batches.
- Money is represented as decimal values in the API and fixed-precision numeric columns in the database, not binary floating point.
- Sale lines and batch allocations snapshot selling prices and acquisition costs so later analytics can calculate gross profit from transaction history.
- Products are archived rather than hard-deleted so inventory history and future sales remain referentially safe.
- Business dates default to `Africa/Cairo` and can be changed with `BUSINESS_TIMEZONE`; sales timestamps are stored in UTC.
- Database schema creation is automatic for the first public checkpoint. Populated legacy databases are left untouched; schema evolution still needs versioned migrations.
- Pharmacy accounts have cookie-based sign-in and tenant-scoped business records. Staff roles, password recovery, email verification, and audit history remain future work.
- Public hosting is configured in `render.yaml`, but the app needs a connected Git repository and hosting account before it can receive a public URL.

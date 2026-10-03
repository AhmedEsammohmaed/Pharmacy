# Pharmacy Operations

A browser-based workspace for independent pharmacy operations: products, inventory batches, expiry tracking, sales, purchases, suppliers, and daily analytics.

## Use the project

The product starts at **http://127.0.0.1:8000/** when run locally. Sign in or create a pharmacy account from the welcome screen. Each account gets a private workspace; products, batches, suppliers, purchases, and sales are scoped to that pharmacy. The interactive Swagger API reference is at **http://127.0.0.1:8000/docs**; operations endpoints require a signed-in account.

## Run locally on Windows

From `D:\programming\pharmacy` in PowerShell:

```powershell
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000/ and create an account. To use AI chat locally, add a `GEMINI_API_KEY` to `.env` (get one from [Google AI Studio](https://aistudio.google.com/app/apikey)); restart the server after editing it. The local development database is SQLite. The old local database contained no business records when the account schema was added; startup only replaces the old schema when it is empty. A populated legacy database is left untouched and requires an explicit migration.

## Current backend functionality

The current checkpoint covers local setup, SQLite persistence, product CRUD/archive, the pharmacy data model, batch inventory, and transactional sales. Business routes use the `/api/v1` prefix:

- Products: `POST` and `GET /api/v1/products/`; `GET`, `PUT`, `PATCH`, and `DELETE /api/v1/products/{product_id}`. Delete archives a product to preserve transaction history.
- Inventory: `POST` and `GET /api/v1/inventory/`; `GET`, `PUT`, and `DELETE /api/v1/inventory/{batch_id}`; `GET /api/v1/inventory/product/{product_id}/stock`.
- Sales: `POST` and `GET /api/v1/sales/`; `GET /api/v1/sales/{sale_id}`. Sale prices come from the stored product, and stock is allocated FEFO across non-expired batches in one transaction.
- Suppliers, purchases, receiving, and analytics are also present as supporting operational modules; they are beyond the first six roadmap stages.

With the project virtual environment active, run the isolated Stage 1–6 API and SQLite acceptance checks with `python -m unittest discover -s tests -v`. The checks start a temporary local database and do not write to `pharmacy.db`.

The signed-in workspace includes an optional AI chat backed by Google's Gemini API. It can discuss general questions and non-clinical pharmacy topics, but it is not connected to the inventory database or a verified RAG knowledge base and must not be used for clinical decisions or patient care. The UI warns users not to share patient-identifying or confidential information. Google may use prompts and responses from its free API tier to improve its products; free use has quotas and may change. Conversation history is kept in browser memory only and sent to Google with each follow-up. Google's Gemini API terms restrict medical advice/clinical use and require paid service for users in the EEA, Switzerland, or UK; check the current terms for public deployment regions.

Configure chat with `GEMINI_API_KEY`, `CHAT_MODEL_ID` (default `gemini-3.8-flash`), and `CHAT_MAX_OUTPUT_TOKENS` (default `1800`). A missing key disables chat without affecting the rest of the app. The hosted service needs the key added as a private Render environment variable; see the [deployment guide](docs/DEPLOYMENT.md).

To manually send a non-clinical pharmacy question and print the response, install the regular dependencies, configure `GEMINI_API_KEY` in `.env`, then run `python -m scripts.test_gemini_chat` from the project root.

BioMistral is a separate experimental local service. Its responses are unverified and it is not connected to the chat interface. It is not authoritative pharmacy or medical advice.

The operations app does not load BioMistral at startup. To run the optional local model, install the PyTorch build selected for the machine's CPU/GPU, install the remaining optional packages with `python -m pip install -r backend/requirements-biomistral.txt`, then run `python -m scripts.test_biomistral`; see the [PyTorch Windows installation guide](https://pytorch.org/get-started/locally/).

## Publish the app

The repository includes a Render Blueprint in [`render.yaml`](render.yaml) that uses Render's native Python runtime and managed PostgreSQL in Frankfurt. It uses HTTPS-only session cookies and checks database connectivity for health. The configured database and web service use paid plans; review Render's current pricing before provisioning. For a step-by-step release guide, see [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

The app is not published yet. The Git checkout currently has no remote repository connected, so connect it to a GitHub repository and deploy the Blueprint from a Render account to receive a public URL. Do not point a public deployment at the local SQLite file.

## Project contents

- `frontend/` — the pharmacy dashboard and account screens.
- `backend/` — FastAPI app, authentication, tenant-scoped models, and business logic.
- `docs/` — deployment, roadmap, and database notes.
- `render.yaml` — public web service and managed PostgreSQL configuration.

## Account and data notes

- Passwords are stored as scrypt hashes; the browser receives a 14-day HttpOnly session cookie.
- Login and signup are rate-limited by client address to slow automated account attempts.
- Each business table carries a pharmacy account ID. ORM reads and writes are tenant-filtered, and newly written rows inherit the signed-in pharmacy.
- Public production mode refuses SQLite and insecure session cookies.
- New accounts can be created directly. Email verification, password recovery, and role-based staff invitations need an email provider and are not included in this first public release.

See [`docs/ROADMAP.md`](docs/ROADMAP.md) and [`docs/DATABASE.md`](docs/DATABASE.md) for the wider project plan and data model.

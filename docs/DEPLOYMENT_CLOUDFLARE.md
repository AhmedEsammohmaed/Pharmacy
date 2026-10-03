# Deploy Pharmacy Operations to Cloudflare Workers

This project is a FastAPI application with authenticated API routes and a static browser UI. The Cloudflare deployment uses a Python Worker for FastAPI, Workers Static Assets for the UI, Hyperdrive for PostgreSQL access, and a Cron Trigger for daily inventory automation. It does not use Docker. Cloudflare Workers do not provide a persistent PostgreSQL database, so a PostgreSQL provider is required.

## Before deploying

1. Create a Cloudflare account and a persistent PostgreSQL database with a provider that accepts Hyperdrive connections. Do not use the local `pharmacy.db` file.
2. Create a Hyperdrive configuration for that database. Disable Hyperdrive query caching: inventory and sales screens need fresh values immediately after writes. Store the database connection details in Hyperdrive; do not commit them or put them in this repository.
3. Copy the Hyperdrive configuration ID into `wrangler.jsonc`, replacing `REPLACE_WITH_HYPERDRIVE_CONFIG_ID`.
4. Install Node.js and `uv`, then run `uv sync` from the repository root. The project uses `pyproject.toml` for the Python Worker build.
5. Install the native Python requirements, then create the application tables once in the new PostgreSQL database using its connection string:

   ```powershell
   .\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
   $env:DATABASE_URL = Read-Host "PostgreSQL connection URL"
   .\.venv\Scripts\python.exe -m scripts.initialize_cloudflare_database
   Remove-Item Env:DATABASE_URL
   ```

   The database initialization command refuses to run against SQLite. This deployment starts with a new database; it does not copy local pharmacy records or local accounts.

## Configure chat secrets

Log in to Cloudflare from the repository root:

```powershell
uv run pywrangler login
```

Gemini is the default provider. Add its key as a Worker secret:

```powershell
uv run pywrangler secret put GEMINI_API_KEY
```

Alternatively, set `CHAT_PROVIDER` to `n8n` in `wrangler.jsonc` and add these Worker secrets:

```powershell
uv run pywrangler secret put N8N_CHAT_WEBHOOK_URL
uv run pywrangler secret put N8N_CHAT_WEBHOOK_TOKEN
```

The Cloudflare chat adapter uses the Worker's asynchronous `fetch` API. It preserves the existing read-only pharmacy tools and the non-clinical system instruction. Model responses are not medically authoritative.

## Run and deploy

Start the local Worker after configuring a local PostgreSQL connection for the Hyperdrive binding:

```powershell
$env:CLOUDFLARE_HYPERDRIVE_LOCAL_CONNECTION_STRING_HYPERDRIVE = Read-Host "PostgreSQL connection URL"
uv run pywrangler dev
```

Open the local URL shown by Wrangler, normally `http://localhost:8787/`. Deploy after the required Cloudflare resources and secrets are configured:

```powershell
uv run pywrangler deploy
```

Cloudflare will print a public `workers.dev` URL. You can then connect the GitHub repository to Workers Builds for automatic deploys on future commits.

## Daily automation and account protection

The Cron Trigger in `wrangler.jsonc` runs daily at 03:00 UTC. Cloudflare runs this separately from web requests, replacing the local/Render in-process timer.

The app's in-memory login, signup, and chat limits are isolate-local on Workers. Before opening signups publicly, add Cloudflare rate-limiting rules for `/auth/signup`, `/auth/login`, and `/api/v1/chat/messages`. These dashboard rules apply across Worker isolates.

## Resource and data limits

- The Worker uses PostgreSQL through Hyperdrive; Hyperdrive is not the database provider. PostgreSQL storage and backups are billed or managed separately by that provider.
- Cloudflare's Free Workers plan has a 10 ms CPU limit per request. `wrangler.jsonc` requests a 30-second limit for password hashing and Python request work; that setting requires the Workers Paid plan. Cloudflare lists that plan at a $5/month minimum; usage beyond included amounts may add cost. Review current [Workers pricing](https://developers.cloudflare.com/workers/platform/pricing/) before deployment.
- Workers currently have a 128 MB memory limit. Do not load BioMistral or PyTorch into this Worker. The deployed chat uses the configured external Gemini or n8n service.
- Cloudflare's Python runtime executes code through Pyodide. The project keeps the existing native Gemini/n8n adapters for local/Render use and selects an asynchronous Worker adapter only on Cloudflare.
- Passwords created on Cloudflare use PBKDF2-SHA256 for portable low-memory hashing. Existing local SQLite accounts are not copied into the new database. Existing scrypt hashes should be migrated only with a separately planned account migration.
- Hyperdrive's default read-query caching can return stale results after writes, so create the Hyperdrive configuration with caching disabled for this operational app.

## Files used by this deployment

- `wrangler.jsonc` defines the Python Worker, static assets, Hyperdrive binding, Cron schedule, runtime variables, and CPU limit.
- `pyproject.toml` lists Cloudflare-compatible runtime dependencies and the Python Workers tooling.
- `backend/cloudflare_worker.py` connects Cloudflare bindings to FastAPI and serializes work per isolate.
- `backend/llm/cloudflare_service.py` sends async Gemini or n8n requests through the Worker runtime without changing local provider behavior.
- `scripts/initialize_cloudflare_database.py` prepares the external PostgreSQL schema before deployment.

This repository does not contain a Cloudflare account token or a Hyperdrive ID. The Worker cannot be published until those account-specific resources are created and configured.

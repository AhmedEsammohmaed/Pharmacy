# Publish Pharmacy Operations

The hosted version uses Render's native Python web service and managed PostgreSQL. The app and database are configured in Frankfurt. Render supplies the HTTPS endpoint, while PostgreSQL keeps account records between app restarts. The Blueprint does not use Docker.

## Before deployment

1. Put this project in a GitHub repository that you control. Keep `.env`, `pharmacy.db`, and credentials out of Git.
2. Open Render and connect that GitHub repository.
3. Choose **New → Blueprint** and select this repository. Render reads [`../render.yaml`](../render.yaml).
4. Review the web service and PostgreSQL compute plans before confirming. The configured plans are paid; check [Render's current pricing](https://render.com/pricing). Render's free PostgreSQL plan does not provide recovery or managed logical backups. See [Render's Postgres recovery and backups guide](https://render.com/docs/postgresql-backups).
5. Create the Blueprint resources and wait for the `/health` check to pass.
6. Choose a chat provider. For Gemini, add `CHAT_PROVIDER=gemini` and `GEMINI_API_KEY` using a key from [Google AI Studio](https://aistudio.google.com/app/apikey). For n8n, add `CHAT_PROVIDER=n8n`, `N8N_CHAT_WEBHOOK_URL`, and `N8N_CHAT_WEBHOOK_TOKEN`. Save and redeploy after changing private environment variables. See the [n8n integration guide](N8N_INTEGRATION.md).
7. Open the service's `onrender.com` URL. Create the first pharmacy account, then verify it by signing out and back in.
8. Add your custom domain in the Render service settings if you have one.

## Production configuration

The Blueprint sets:

- `ENVIRONMENT=production`, which refuses SQLite and insecure cookies.
- `COOKIE_SECURE=true`, with HttpOnly and SameSite=Lax session cookies.
- `DATABASE_URL` from the private PostgreSQL connection string.
- Provider credentials are private Render environment secrets for server-side chat calls. They are not exposed to the browser or stored in PostgreSQL.
- `CHAT_MODEL_ID` and `CHAT_MAX_OUTPUT_TOKENS` configure the chat provider/model and answer length.
- `FORWARDED_ALLOW_IPS=*` so Uvicorn can honor the hosting proxy's HTTPS and client headers.
- Frankfurt for both app and database to keep the deployment region consistent.

The `/health` endpoint runs `SELECT 1` against the configured database. Signup and login are served by the app; all pharmacy operations require an authenticated account. Gemini uses tenant-scoped read-only tools for product, inventory, expiry, and sales queries. When chat is routed through n8n, its AI Agent can call the same tools with a signed, short-lived token limited to one pharmacy. Daily inventory monitoring runs in the web service process and stores in-app alerts in PostgreSQL; it does not create orders or edit business stock.

In Gemini mode, chat messages, recent context, and relevant pharmacy tool results go to Google Gemini. In n8n mode, messages and history go to the configured n8n instance; any connected model provider may process them, and pharmacy tool results return to n8n. Do not enter patient-identifying or confidential information. Keep chat non-clinical and check current provider terms for every country where the public app is offered.

## Runtime and data

Render installs `backend/requirements.txt` with its native Python runtime and starts Uvicorn using the service's `PORT`. For a local SQLite run, use the regular PowerShell command in the main README. SQLite is for development only.

## Release follow-up

This first hosted release supports direct email/password signup. Configure an email delivery provider before enabling email verification, password recovery, or staff invitations. Use a real hosted account only after reviewing the applicable privacy and pharmacy record-keeping requirements for your region.

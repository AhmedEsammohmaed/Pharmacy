# Share Pharmacy Operations temporarily

This setup publishes the complete FastAPI app as a free Render web service and uses the Neon PostgreSQL database configured for this project. Render supplies a public HTTPS `onrender.com` link. The Blueprint does not use Docker and does not create a paid Render database.

## Before deployment

1. Push this project to the GitHub repository connected to your Render account. Keep `.env`, `pharmacy.db`, and credentials out of Git.
2. Sign in to Render, choose **New → Blueprint**, and select the Pharmacy repository. Render reads [`../render.yaml`](../render.yaml).
3. For `DATABASE_URL`, paste the Neon connection string for project `fragrant-unit-31019970`, branch `production`, database `neondb`. Copy it from Neon’s **Connect** dialog. Keep the URL private; enter it only in Render. The Neon endpoint and Render service are both in Ohio.
4. Confirm the service uses the **Free** plan, then deploy. Wait for the `/health` check to pass.
5. Open the public `onrender.com` URL shown in the Render service dashboard. Create a pharmacy account and test sign-out/sign-in. Send that link to the people you want to try the app.
6. AI chat needs a Gemini API key. If you want chat enabled, add `GEMINI_API_KEY` as a private environment variable in Render and redeploy. Get a key from [Google AI Studio](https://aistudio.google.com/app/apikey). Without it, the rest of the application can still be tried, but chat will report that it is not configured. For n8n, use `CHAT_PROVIDER=n8n`, `N8N_CHAT_WEBHOOK_URL`, and `N8N_CHAT_WEBHOOK_TOKEN`; see the [n8n integration guide](N8N_INTEGRATION.md).

## Production configuration

The Blueprint sets:

- `ENVIRONMENT=production`, which refuses SQLite and insecure cookies.
- `COOKIE_SECURE=true`, with HttpOnly and SameSite=Lax session cookies.
- `DATABASE_URL` as a private Render environment variable. It must point to the Neon PostgreSQL database, never a local SQLite file.
- Provider credentials are optional private Render environment secrets for server-side chat calls. They are not exposed to the browser or stored in PostgreSQL.
- `CHAT_MODEL_ID` and `CHAT_MAX_OUTPUT_TOKENS` configure the chat provider/model and answer length.
- `FORWARDED_ALLOW_IPS=*` so Uvicorn can honor the hosting proxy's HTTPS and client headers.
- Ohio for the Render service, close to the Neon database region.

The `/health` endpoint runs `SELECT 1` against the configured database. Signup and login are served by the app; all pharmacy operations require an authenticated account. Gemini uses tenant-scoped read-only tools for product, inventory, expiry, and sales queries. When chat is routed through n8n, its AI Agent can call the same tools with a signed, short-lived token limited to one pharmacy. Daily inventory monitoring runs in the web service process and stores in-app alerts in PostgreSQL; it does not create orders or edit business stock.

In Gemini mode, chat messages, recent context, and relevant pharmacy tool results go to Google Gemini. In n8n mode, messages and history go to the configured n8n instance; any connected model provider may process them, and pharmacy tool results return to n8n. Do not enter patient-identifying or confidential information. Keep chat non-clinical and check current provider terms for every country where the public app is offered.

## Runtime and data

Render installs `backend/requirements.txt` with its native Python runtime and starts Uvicorn using the service's `PORT`. For a local SQLite run, use the regular PowerShell command in the main README. SQLite is for development only. This free service has an ephemeral local filesystem, so pharmacy records must stay in Neon.

## Free service limitations and access

Render Free sleeps after 15 minutes without incoming traffic. The first visit after sleep can take about a minute while it starts. Free service hours and bandwidth are limited by Render; this setup is for a temporary preview, not a production guarantee. See [Render Free service limitations](https://render.com/docs/free).

The site URL is public, and signup is currently open without email verification. People with the link can create accounts; each account's pharmacy records are isolated from other accounts. The URL is shareable, but it is not an invite-only security gate.

## Release follow-up

This first hosted release supports direct email/password signup. Configure an email delivery provider before enabling email verification, password recovery, or staff invitations. Use a real hosted account only after reviewing the applicable privacy and pharmacy record-keeping requirements for your region.

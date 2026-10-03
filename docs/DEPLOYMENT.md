# Publish Pharmacy Operations

The hosted version uses Render's native Python web service and managed PostgreSQL. The app and database are configured in Frankfurt. Render supplies the HTTPS endpoint, while PostgreSQL keeps account records between app restarts. The Blueprint does not use Docker.

## Before deployment

1. Put this project in a GitHub repository that you control. Keep `.env`, `pharmacy.db`, and credentials out of Git.
2. Open Render and connect that GitHub repository.
3. Choose **New → Blueprint** and select this repository. Render reads [`../render.yaml`](../render.yaml).
4. Review the web service and PostgreSQL compute plans before confirming. The configured plans are paid; check [Render's current pricing](https://render.com/pricing). Render's free PostgreSQL plan does not provide recovery or managed logical backups. See [Render's Postgres recovery and backups guide](https://render.com/docs/postgresql-backups).
5. Create the Blueprint resources and wait for the `/health` check to pass.
6. In the Render web service's **Environment** settings, add `GEMINI_API_KEY` using a key from [Google AI Studio](https://aistudio.google.com/app/apikey), then save and redeploy. Keep this key secret. Without it, the rest of the app works but AI chat stays disabled.
7. Open the service's `onrender.com` URL. Create the first pharmacy account, then verify it by signing out and back in.
8. Add your custom domain in the Render service settings if you have one.

## Production configuration

The Blueprint sets:

- `ENVIRONMENT=production`, which refuses SQLite and insecure cookies.
- `COOKIE_SECURE=true`, with HttpOnly and SameSite=Lax session cookies.
- `DATABASE_URL` from the private PostgreSQL connection string.
- `GEMINI_API_KEY` is a private Render environment secret for server-side chat calls. It is not exposed to the browser or stored in PostgreSQL.
- `CHAT_MODEL_ID` and `CHAT_MAX_OUTPUT_TOKENS` configure the chat provider/model and answer length.
- `FORWARDED_ALLOW_IPS=*` so Uvicorn can honor the hosting proxy's HTTPS and client headers.
- Frankfurt for both app and database to keep the deployment region consistent.

The `/health` endpoint runs `SELECT 1` against the configured database. Signup and login are served by the app; all pharmacy operations require an authenticated account.

AI chat sends each question and its recent conversation context to Google Gemini. The chat history is held in the browser session and is not written to the pharmacy database. Google says it may use prompts and responses from unpaid API usage to improve products, so do not enter patient-identifying, sensitive, or confidential information. Free usage is quota-limited and availability can change. Google's current terms prohibit using Gemini API in clinical practice or to provide medical advice, and require paid service for API clients offered to users in the EEA, Switzerland, or UK. Keep the chat non-clinical and check current terms for every country where the public app is offered.

## Runtime and data

Render installs `backend/requirements.txt` with its native Python runtime and starts Uvicorn using the service's `PORT`. For a local SQLite run, use the regular PowerShell command in the main README. SQLite is for development only.

## Release follow-up

This first hosted release supports direct email/password signup. Configure an email delivery provider before enabling email verification, password recovery, or staff invitations. Use a real hosted account only after reviewing the applicable privacy and pharmacy record-keeping requirements for your region.

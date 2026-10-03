# Connect the pharmacy chat to an n8n AI Agent

The app can keep Gemini as its default chat provider or forward signed-in chat turns to your n8n AI Agent over an authenticated webhook. In n8n mode, the app sends the current question, recent conversation history, pharmacy account ID, and a short-lived token that allows read-only calls to that pharmacy's operational tools.

## Set up the n8n workflow

1. Create a workflow with a **Webhook** trigger using `POST` and **Header Auth**. Set the header name to `Authorization` and the value to `Bearer <shared-secret>`.
2. Connect it to an **AI Agent** and a chat model credential of your choice. Map the user prompt from `body.message`. The prior turns are in `body.history`; the app already includes them, so a separate memory node is optional.
3. Add an HTTP Request Tool to the AI Agent if it should answer questions about this pharmacy's records. Configure it to make a `POST` request to `https://YOUR-PHARMACY-APP/api/v1/n8n/tools` with a JSON body containing:

   ```json
   {
     "tool_access_token": "<body.tool_access_token>",
     "name": "<an allowed tool name>",
     "arguments": {}
   }
   ```

   Replace the placeholders with n8n expressions/input fields. The allowed tool names are `get_pharmacy_overview`, `search_pharmacy_products`, `list_low_stock`, `list_expiring_stock`, and `get_sales_summary`. Keep this HTTP Request Tool read-only; the app rejects all other tool names.
4. Configure the Webhook to respond when the workflow finishes, returning a JSON object with an `output` string, for example `{"output":"...AI Agent answer..."}`. n8n also supports responding through a **Respond to Webhook** node.
5. Publish/activate the workflow and copy its **Production URL**. The app calls the production URL; n8n's test URL is only registered while listening for a test event. See the [n8n Webhook documentation](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.webhook/).

## Configure the pharmacy app

Set these server environment variables, then restart the app:

```dotenv
CHAT_PROVIDER=n8n
N8N_CHAT_WEBHOOK_URL=https://YOUR-N8N/webhook/YOUR-PRODUCTION-PATH
N8N_CHAT_WEBHOOK_TOKEN=use-the-same-long-random-secret-as-the-n8n-header-credential
```

The app sends the webhook header as `Authorization: Bearer <N8N_CHAT_WEBHOOK_TOKEN>`. Keep the token only in server-side configuration and in the n8n credential. The app signs each read-only tool token for one pharmacy and expires it after five minutes. It contains no password or email. The n8n instance must be able to reach the app's `/api/v1/n8n/tools` URL to use pharmacy data; `127.0.0.1` is only reachable from the same machine/container, so hosted n8n needs a deployed app URL.

To return to Gemini, set `CHAT_PROVIDER=gemini` and configure `GEMINI_API_KEY`.

## Data handling and scope

Chat messages and recent history go to your configured n8n instance, and the workflow's connected AI provider may receive them. When the workflow calls the pharmacy tools, product, stock, expiry, or sales data for the signed-in pharmacy is returned to n8n. The capability only permits reads for that pharmacy and does not permit sales, purchasing, inventory edits, or supplier messages. Do not include patient-identifying or confidential health information in chat. Model answers are not authoritative medical advice.

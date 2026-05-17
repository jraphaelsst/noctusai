# WAHA Response And Webhook Formats

Authoritative sources checked:

- WAHA sessions docs: https://waha.devlike.pro/docs/how-to/sessions/
- WAHA receive messages docs: https://waha.devlike.pro/docs/how-to/receive-messages/
- WAHA send messages docs: https://waha.devlike.pro/docs/how-to/send-messages/

This product uses tolerant Pydantic schemas in `app/schemas/whatsapp.py`
because WAHA response details vary by engine (`WEBJS`, `WPP`, `NOWEB`,
`GOWS`) and by event type.

## Session Responses

`GET /api/sessions/{name}` and each item in `GET /api/sessions` usually
look like:

```json
{
  "name": "default",
  "status": "WORKING",
  "config": {
    "webhooks": [
      {
        "url": "https://example.com/api/whatsapp/webhook",
        "events": ["message", "session.status"],
        "hmac": null,
        "retries": null,
        "customHeaders": null
      }
    ],
    "debug": false
  },
  "me": {
    "id": "5511999999999@c.us",
    "pushName": "WAHA"
  },
  "engine": {
    "engine": "NOWEB"
  }
}
```

Known session status values:

- `STOPPED`
- `STARTING`
- `SCAN_QR_CODE`
- `WORKING`
- `FAILED`

The Settings status endpoint first tries `GET /api/sessions/{session}`;
if that route is unavailable in a running image, it falls back to
`GET /api/sessions/{session}/status` and `GET /api/sessions`.

## Message Webhook

The product handles `message` and `message.any`.

Typical inbound shape:

```json
{
  "event": "message",
  "session": "default",
  "payload": {
    "id": "false_5511999999999@c.us_AAAAAAAAAAAAAAAAAAAA",
    "timestamp": 1710481111,
    "from": "5511999999999@c.us",
    "fromMe": false,
    "to": "5511888888888@c.us",
    "body": "ONE5555 https://drive.google.com/drive/folders/abc",
    "hasMedia": false
  }
}
```

Observed/expected optional fields:

- `payload.chatId` can appear in some contexts; use it as fallback when
  `payload.from` is absent.
- `payload.participant` appears for group contexts.
- `payload.replyTo` appears for replies.
- `payload.media` appears when `hasMedia` is true and can include
  `url`, `mimetype`, and `filename`.
- `payload.fromMe` should be ignored by this app to avoid processing its
  own replies.

## Session Status Webhook

The product logs `session.status` but does not run the upload state
machine for it.

```json
{
  "event": "session.status",
  "session": "default",
  "me": {
    "id": "5511999999999@c.us",
    "pushName": "~"
  },
  "payload": {
    "status": "WORKING",
    "statuses": [
      {"status": "STOPPED", "timestamp": 1700000001000},
      {"status": "STARTING", "timestamp": 1700000002000},
      {"status": "WORKING", "timestamp": 1700000003000}
    ]
  },
  "engine": "WEBJS"
}
```

## Send Text Response

The send endpoint is `POST /api/sendText` with:

```json
{
  "session": "default",
  "chatId": "5511999999999@c.us",
  "text": "Teste"
}
```

WAHA engines can return different response envelopes. The helper
`extract_waha_message_id()` checks these locations in order:

1. `id`
2. `key.id`
3. `_data.id`
4. `message.id`

Examples:

```json
{"id": "false_5511999999999@c.us_AAAAAAAAAAAAA"}
```

```json
{
  "key": {
    "remoteJid": "5511999999999@c.us",
    "fromMe": true,
    "id": "AAAAAAAAAAAAAAAAAAAAAA"
  },
  "message": {}
}
```

```json
{
  "_data": {
    "id": "false_5511999999999@c.us_AAAAAAAAAAAAA"
  }
}
```

## Security

The webhook is public for WAHA delivery. Runtime controls:

- Sender whitelist: `WHATSAPP_AUTHORIZED_NUMBERS`, default
  `+5511974693365`.
- Public webhook URL: `WAHA_WEBHOOK_URL`, refreshed by
  `./refresh_cf_tunnel.sh` for local Cloudflare Quick Tunnel testing.
- Optional HMAC: set `WAHA_WEBHOOK_HMAC_SECRET` and send the hex
  SHA-256 HMAC in `X-Webhook-Hmac-SHA256`.

Keep `WAHA_WEBHOOK_HMAC_SECRET` empty if the active WAHA deployment
cannot sign webhook bodies.

## URL Contexts

- `WAHA_BASE_URL=http://waha:3000` is for backend container to WAHA
  container calls inside Docker Compose.
- `WAHA_DASHBOARD_URL=http://localhost:3000/dashboard` is for the
  operator's browser.
- `WAHA_WEBHOOK_URL=https://<tunnel>/api/whatsapp/webhook` is the public
  URL WAHA calls when messages arrive.

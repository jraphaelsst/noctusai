---
name: whatsapp-messaging
description: >
  Send WhatsApp messages, property cards, and retrieve conversation history
  via the WAHA API integration. Use when communicating with clients through
  WhatsApp or sharing property listings.
version: 1.0.0
triggers:
  - "send whatsapp message"
  - "share property on whatsapp"
  - "check whatsapp history"
  - "enviar mensagem whatsapp"
  - "compartilhar imóvel"
dependencies:
  - mcp: waha-whatsapp
---

# WhatsApp Messaging

## Purpose

Enables WhatsApp communication with clients through the WAHA (WhatsApp HTTP API) integration. Supports sending text messages, formatted property cards, and retrieving conversation history. Messages are logged in the database for CRM tracking.

## Instructions

### Step 1: Send Text Message

```
POST /api/whatsapp/send
Authorization: Bearer {token}
Body: {
  "phone": "11999887766",
  "message": "Olá! Temos novidades sobre imóveis na sua região.",
  "cliente_id": "uuid"  // optional, for CRM linking
}
```

Phone numbers are auto-normalized: strips special characters, adds BR country code (55) if missing.

### Step 2: Send Property Card

For sharing a formatted property listing:
```
POST /api/whatsapp/send-property
Authorization: Bearer {token}
Body: {
  "phone": "11999887766",
  "ativo_id": "uuid",
  "cliente_id": "uuid"  // optional
}
```

The service automatically builds a formatted card with:
- Property type and title
- Location (bairro, cidade/estado)
- Key specs (area, quartos, vagas)
- Price (formatted as R$ X.XXX.XXX)
- Link to listing (if available)

### Step 3: Retrieve History

```
GET /api/whatsapp/history/{phone}?page=1&page_size=20
Authorization: Bearer {token}
```

Returns paginated message history for a phone number, scoped to the user's org.

### Step 4: Check Configuration

```
GET /api/whatsapp/config
Authorization: Bearer {token}
```

Returns whether WAHA is configured and reachable.

## Message Storage

All messages are stored in `whatsapp_messages` table:
- `org_id` — Tenant isolation
- `phone` — Recipient/sender phone
- `direction` — `sent` or `received`
- `message` — Message content
- `message_type` — `text`, `property_card`, or `image`
- `status` — `sent`, `delivered`, `read`, `failed`
- `cliente_id` — Optional CRM link

## Edge Cases

- **WAHA not configured** → Dry-run mode: messages logged in DB but not actually sent
- **Invalid phone number** → Normalized first; if still invalid, returns validation error
- **WAHA service down** → Returns 503 with message indicating service unavailable
- **Client not found** → Message still sent, just without `cliente_id` linking
- **Long message (> 4096 chars)** → WhatsApp API truncates; consider splitting in the frontend
- **International number** → Normalization handles various formats (+55, 055, etc.)

## Examples

### Example 1: Simple Text Message
**Input:** Phone "11999887766", message "Bom dia! Gostaria de agendar uma visita?"
**Expected tool call:** `POST /api/whatsapp/send` with phone + message
**Expected behavior:** Message sent via WAHA, stored in DB with status "sent"

### Example 2: Property Card
**Input:** Phone "11999887766", ativo_id of an apartamento listing
**Expected tool call:** `POST /api/whatsapp/send-property` with phone + ativo_id
**Expected behavior:** Formatted property card sent with type, location, specs, price

### Example 3: WAHA Not Configured
**Input:** Any send request, but WAHA credentials not set
**Expected behavior:** Message logged in DB (dry-run), response indicates dry-run mode

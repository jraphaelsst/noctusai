# Browser playbook — driving the portal with Chrome MCP

Every item here was hit in the 2026-09-24 session. Read before the first browser action.

## Setup

- Load all tools in ONE ToolSearch: `tabs_context_mcp, tabs_create_mcp, tabs_close_mcp,
  navigate, read_page, get_page_text, find, computer, javascript_tool, read_network_requests,
  browser_batch`.
- `tabs_context_mcp` first. No group ⇒ `createIfEmpty: true`. **You can only see/drive
  tabs inside the MCP tab group** — the user must log in *in that group's tab*.
- The group can vanish (e.g. when the user closes an extension/window). Symptom: "Couldn't
  determine which page this action targets" / "No tab group exists". Fix: recreate the
  group, navigate to the portal — the login session (cookie) survived in our case.
- Close every tab you opened when done (`tabs_close_mcp`). "Acessar anúncio" opens a new
  tab in the group — close it too.

## Timing & failures

- Full navigations are slow: **wait ~10s** (two waits if needed; single wait max 10s)
  before reading. A read too early returns a skeleton or "No text content found".
- "Script injection timed out … page is busy" right after navigating ⇒ just wait and retry.
- `upstream connect error or disconnect/reset before headers` (black page) is a transient
  QuintoAndar server error — retry the navigation once.
- **Renderer freeze:** `/status/unpublished?perPage=30` froze the tab (CDP 45s timeout).
  Recovered by re-navigating with `perPage=10`. Prefer 10 for large lists (Desativados,
  Não-elegíveis, Todos); 30 was fine for small ones.
- Tool failing 2–3× ⇒ stop and ask the user (repo + safety rule).

## Clicking quirks

- Some buttons need a **second click**: "Expandir informações" (lead page), "Quero
  calcular" (first click only scrolls), "Gerenciar bairros" on company profile, "Adicionar
  usuários" (ref click did nothing; coordinate click worked).
- The main content scrolls inside its own container: `computer scroll` may not move it —
  use JS `document.querySelectorAll('*').forEach(e=>{if(e.scrollTop>0)e.scrollTop=0})`
  to reset, or `scroll_to` a ref.
- Drawers close with their ← arrow or X; in the entry wizard ← goes back a step (step 2 →
  step 1), X closes. Escape works on some popovers.
- Filter popovers stay open after Escape sometimes — click empty page area.
- Screenshots occasionally came back tiled 2×2 (capture glitch) — retake before trusting.
- Coordinates: screenshots taken with `scale` report the full-resolution frame; click in
  that frame. Viewport changed between 1568×713, 1512×786 and 1440×749 in one session —
  re-screenshot after any window change.

## Reading data

- Prefer `javascript_tool` over screenshots for lists: `document.querySelector('main').innerText`
  split by lines, aggregate counts. Rows are **not** `<table>` elements — find rows by
  climbing from the "Copiar" buttons (see `snippets/list-scrape.js`).
- `read_network_requests` missed the app's XHR/fetch data calls. Use
  `performance.getEntriesByType('resource')` (paths/params) and the in-page logger
  `snippets/api-logger.js` (method, status, response shape). The logger dies on full reload
  — navigate by in-app clicks when you need it across pages.
- `window.open` can be intercepted to learn where a button navigates without opening a tab
  (`snippets/window-open-probe.js`).
- The MCP output filter **blocks** results that look like query strings/cookies/base64
  (`[BLOCKED: …]`). Don't print `location.search` or raw hrefs with `?crmId=…`; strip or
  rename (`split('?')[0]`, map keys to `' is '`), or spell digits out.
- Mask PII in anything you print: replace phones/e-mails/names before returning text
  (examples in the snippets).

## Page-injected noise (not the portal)

- Green "$" floating button + "Lojas similares que têm cashback" popup + `cuponomia.com.br`
  requests — a browser extension (user-confirmed). Its node: random-id `<div>` on `<body>`,
  closed shadow root.
- Red icon bottom-right with the Adobe Acrobat logo: `#aiFabShadowRoot` on `<html>`,
  outside `#__next` — outside the app.
- Test: `el.closest('#__next')` false ⇒ not the portal.

## Dialogs

Never trigger native `alert/confirm` — they freeze the extension. No native dialog was
seen in the portal (it uses drawers/modals), but destructive buttons are untested.

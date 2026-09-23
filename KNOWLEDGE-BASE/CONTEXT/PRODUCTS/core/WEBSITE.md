# core · noctusai.com public website — pointer

> **Pointer doc.** The canonical website documentation lives **with the code**, at `products/core/frontend/src/website/docs/`. It ships inside the core image, and admins and the marketing role read it in the logged app under **Website → Documentação**. This KB page exists so agents find it and so the tooling rules below are visible from the KB. It does not duplicate the docs.

## What it is

- The public marketing site at **noctusai.com**.
- It lives **inside `products/core`**, isolated under `src/website/` with its own Vite entry (owner decision 2026-09-22: not a seed product).
- It owns `/`; the logged app moves to `/app`.
- It is SEO-first: server-rendered HTML, hreflang pt-BR/EN, one lazy WebGL hero over a static poster.
- A full rebrand scoped to the website's tokens.
- It is operated from the **Website** sidebar group: Documentação, then Configurações / Blog / Leads.

**Status (2026-09-23):** DRAFT docs v0.1 awaiting owner approval. No website runtime code exists yet.

## Read before touching the website

1. `products/core/frontend/src/website/docs/00-index.md`: rules plus reading order.
2. `…/docs/08-technical-architecture.md`: routing, the `/app` blast radius, SSR, kill switch, bundle isolation.
3. `…/docs/14-build-plan.md`: slices, gates, open decisions.

## 🔴 Tooling rules (mirrored from the docs, §13)

- **Higgsfield MCP.**
  - Used **only** for the noctusai.com website: rebrand exploration and product imagery.
  - Needs **explicit owner permission for each use**.
  - **Not connected ⇒ do not do Higgsfield-dependent work** and do not substitute another generator.
  - It is **not** on the MCP keep-list and never goes into `.mcp.json`; the owner connects it.
- **Website frontend MCPs** (Context7, Chrome DevTools MCP, shadcn MCP) are owner-approved for **website work sessions only**. Load them with `claude --mcp-config .claude/mcp/website.json`; they are never always-on.

The keep-list exception is recorded in `KB § CONTEXT/01-PHILOSOPHY.md` § MCP keep-list.

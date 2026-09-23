# 13 · Tooling & MCP policy

The repo keeps a strict MCP keep-list: `noctusai`, `supabase`, `n8n`, `waha` (`KB § CONTEXT/01-PHILOSOPHY.md` § MCP keep-list). Every MCP below is an **owner-approved, website-scoped exception**. None of them is loaded in ordinary sessions.

## 🔴 Higgsfield MCP — permission-only, website-only

| Rule | Detail |
|---|---|
| **Scope** | Used **only** for the noctusai.com website. Approved uses: **rebrand exploration** (logo/identity concepts, moodboards, motif studies) and **product imagery** (stylized product visuals, device mockups). No other implementation in this codebase uses it for now |
| **Permission** | **Explicit owner approval for each use** (each generation batch or session), asked in chat with what will be generated and roughly how many credits. An earlier approval does not carry over to later work |
| **Not connected ⇒ don't touch** | If the Higgsfield tools aren't available in the session, **do not do Higgsfield-dependent design work** and don't substitute another generator or stock imagery. Stop, tell the owner, and offer the connect command below. Website work that doesn't depend on generated imagery (code, docs, copy) may proceed |
| **Never** | Generate images of real people or impersonate brands; present generated imagery as real customer data or screenshots; use it for the runtime 3D scene (that comes from the approved motif model) |
| **Outputs** | Approved assets go to the website asset pipeline (optimised WebP/AVIF, both themes where relevant) with provenance recorded: prompt, model, date, approver. The Higgsfield output URL isn't the source of record |

**How to check the connection.** Higgsfield tools appear as `mcp__higgsfield__*` (Claude Code) or `mcp__claude_ai_Higgsfield__*` (claude.ai connector). If neither is present, it isn't connected.

**How the owner connects it** (the owner runs this, not an agent):

```bash
claude mcp add --transport http higgsfield https://mcp.higgsfield.ai/mcp
# first tool call opens a browser for Higgsfield sign-in (OAuth)
```

Or through claude.ai → Settings → Connectors → Add custom connector → `https://mcp.higgsfield.ai/mcp`. Higgsfield exposes image and video models (Kling, Veo, Seedance, Soul, Flux, and others), and every generation costs credits. That cost is one more reason for per-use permission.

## Frontend MCPs for website work (owner-approved 2026-09-22)

| MCP | Use it for | Don't use it for |
|---|---|---|
| **Context7** | Current docs for three.js / react-three-fiber, Vite SSR, react-router, i18n, consent and analytics libraries, so code isn't written against stale APIs | Anything the codebase already answers (the codebase is the source of truth) |
| **Chrome DevTools MCP** | Lighthouse runs, performance traces, Core Web Vitals, console/network inspection, a11y checks against [09 budgets](09-seo-performance-a11y.md#budgets) | Driving logged-in admin sessions with real data |
| **shadcn MCP** | Correct props and imports when adding shadcn/ui primitives (core already uses `@noctusai/seed/components/ui`) | Replacing seed organs: check the organ catalog first (`noc-organ-consume-check`) |

Considered and declined: Figma MCP (no Figma source of truth), Playwright MCP (e2e runs as repo tests in CI), Filesystem and GitHub MCPs (duplicate native tools and `gh`), Magic Patterns / Magic UI (a third design source).

**Loading them.** They are **not** in `.mcp.json`, so they cost nothing in ordinary sessions. For a website work session:

```bash
claude --mcp-config .claude/mcp/website.json
```

`.claude/mcp/website.json` declares `context7`, `chrome-devtools` and `shadcn`. Higgsfield is deliberately **not** in that file. It is connected by the owner (see above) so that loading it is itself a conscious act.

**Supply-chain note.** The config runs the three servers via `npx … @latest`. Before relying on them for a build slice, pin each to the version verified in that session and record it here.

| MCP | Pinned version | Verified on |
|---|---|---|
| context7 | — | — |
| chrome-devtools | — | — |
| shadcn | — | — |

## Reference capture tooling

The 2026-09-23 research used an ad-hoc Playwright script that:
- captured the home plus nav pages;
- took above-the-fold, full-page, mobile and dark-preference screenshots;
- extracted DOM, design, SEO and library signals;
- recaptured scroll-revealed pages frame by frame.

It honoured bot checks (OpenAI was dropped rather than bypassed) and rejected cookie banners.

**Follow-up (MCP-first rule):** turn it into a `noctus.dev.site_reference_capture` tool via skill `noc-mcp-tool`, if reference research repeats (N ≥ 2). It would output to a private bucket, not git. Tracked in [14](14-build-plan.md#follow-ups).

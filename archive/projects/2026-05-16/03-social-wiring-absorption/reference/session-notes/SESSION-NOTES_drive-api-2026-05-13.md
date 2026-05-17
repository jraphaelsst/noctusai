# 📩 Session findings — Google Drive API client + content reading

> **Date:** 2026-05-13
> **Source workspace:** `noctusai-youtube-crawler`
> **Source branch:** `feat/platform-chat-agent`
> **Continuation of:** `SESSION-NOTES_google-integrations-2026-05-12.md`
> (the prior Calendar + Maps + Drive-URL-parser session)
>
> **Reference scope:** historical / read-before-planning. This
> documents the full Drive integration including the content-reading
> tool that made the chatbot actually useful for spreadsheet
> questions like "quantas casas tem registradas?".

---

## TL;DR

Built a real Google Drive API v3 read client (search/list/get/read
content) on top of the same OAuth+service-account credential bundle
the Calendar adapter already uses. Added four chatbot tools:
`search_drive_files`, `list_recent_drive_files`, `get_drive_file`,
`read_drive_file`. Validated end-to-end against the user's real
Drive — search found "Cronograma One", read_drive_file pulled 11KB
of CSV, deterministic stats counted **198 lines / 176 unique ONE
codes** matching ground truth exactly.

Two implementation insights worth lifting into noc:

1. **The "share with the SA email" path works just as well as full
   OAuth for any product whose users already share specific folders**
   — no GCP redirect-URI registration drama needed. The user shared
   one parent folder and 25 items became visible. Document this as
   the recommended quick-start for new products.

2. **LLM counting is unreliable on long structured data — precompute
   stats in Python.** First live test asked for "linhas com código
   ONE" against a 198-line CSV; LLM said 35 (real answer: 183 lines /
   176 unique). Fix: tool response carries a `stats` field calculated
   deterministically, and the tool description forbids manual counting.
   Generalizes to any product that has LLM-over-structured-data tasks.

When this lifts into noc, the promotion manifest at
`.promotions/drive-api-client.md` is the migration map.

---

## 1 · What landed

### Drive API client — `app/services/drive_api/` (new package)

Mirrors the `calendar/` package shape exactly:

| File | Role |
|------|------|
| `types.py` | DriveFile + DriveSearchResult + DriveFileContent + DriveAdapter Protocol |
| `mappers.py` | Drive v3 body → DriveFile + Drive `q` builder + EXPORT_MIME + `render_bytes()` |
| `_drive_api.py` | HTTP plumbing (`files_list`, `files_get`, `files_export`, `files_get_media`) |
| `google_adapter.py` | Service-account read client (drive.readonly scope) |
| `oauth_adapter.py` | OAuth-user read client (reuses Calendar credential row + DRIVE_SCOPES on top of the consent) |
| `fake_adapter.py` | In-memory, mirrors response shape |
| `__init__.py` | Factory: OAuth → service-account → Fake |

OAuth path is plumbed but never reached this session — the user opted
for the share-with-SA path instead (see §2). Both paths work.

### Four chatbot tools

| Tool | Purpose |
|------|---------|
| `search_drive_files(query, mime_type?, folder_id?, page_size?)` | Name + fullText search |
| `list_recent_drive_files(page_size?)` | Most-recently-modified |
| `get_drive_file(file_id)` | Metadata-only lookup |
| `read_drive_file(file_id, max_bytes?)` | **Full content** — exports Sheets→CSV, Docs→text, PDF→pdfminer, TXT/CSV→passthrough |

Tools live in `chatbot_service._build_tools()` and delegate to
handlers on `WhatsAppIntakeService`. The 6-tool Drive surface joins
the existing 6-tool upload surface + the 2-tool calendar surface +
the 1-tool maps surface for a total of 15 active chatbot tools.

### Live validation

Real Google Drive API calls during the session:

| Test | Result |
|------|--------|
| `list_recent` after first folder share | 25 items returned |
| `search("cronograma da one")` | 2 real hits with valid Drive IDs |
| `files.export` on Cronograma One (Google Sheets) | 11,327 bytes of CSV |
| `read_drive_file` end-to-end via chatbot | 198 lines / 176 unique ONE codes / sample codes — all match ground truth |
| Deterministic stats precomputed | Matches direct Python verification exactly |

---

## 2 · The two access paths, and what we learned

| Path | Setup | What it sees | When to recommend |
|------|-------|--------------|-------------------|
| **Share folder with SA email** | Right-click folder in Drive → Share → paste SA email → Viewer (or Editor) | Whatever was shared, recursively | User has a small set of folders the bot should access. NO GCP changes needed. |
| **OAuth user consent** | One-time browser consent at `/api/calendar/oauth/start` + GCP-side redirect URI registration | The user's ENTIRE Drive (drive.readonly scope) | User wants whole-Drive coverage, OR multiple products need access without micromanaging shares |

The user took path 1 — shared one parent folder with
`noctusai-calendar-bot@gen-lang-client-0907920966.iam.gserviceaccount.com`
and 25 items became visible (the folder's contents inherited
permissions). For their use case (real-estate One Consultoria
folders) this is the right posture: bot reads what's been shared,
nothing else.

**Recommendation for noc seed:** the new-product guide should
present the share-with-SA path FIRST as the default quick-start.
OAuth is a heavier landing (redirect URI registration + browser
consent + token persistence) that only pays off when the bot needs
whole-Drive visibility. For most products, path 1 is enough.

### A gotcha worth noting

The user surfaced "I shared the parent folder but a specific
spreadsheet inside isn't accessible." We verified via `files.get`
that the SA actually DID have `canDownload: true` on the
spreadsheet — the issue was that **the bot didn't have a
read-content tool yet**, not that permissions were missing. The
"não consigo acessar" reply was an honest limit, but it sounded
like a permission error to the user.

Lesson: surface adapter-side `canDownload` / `canRead` checks in
the tool response so the bot can distinguish "permission denied"
from "no tool" from "404". Already done on `get_drive_file`; could
be lifted to a `capabilities` field on every Drive response.

---

## 3 · The LLM-counting trap

First live test:

```
User: "le o cronograma da one e me diz quantas linhas com codigo ONE existem"
Bot:  "encontrei 35 linhas"
```

Direct python verification:

```
total_lines       = 198
lines_with_ONE    = 183
unique_one_codes  = 176
```

The LLM got the count off by 5x. This is a known LLM weakness —
they pattern-match the first few rows and extrapolate. The CSV was
small (11KB, not truncated) so the data was all there; the model
just couldn't count it accurately.

**Fix shape:** the intake's `read_drive_file` handler runs the
returned text through `_compute_content_stats(text, rendered_as)`
which precomputes line/char/code counts in Python:

```python
{
  "total_chars": 11248,
  "total_lines": 198,
  "non_empty_lines": 184,
  "csv_header": "Data,Horário,Ref,Corretor,Confirmado?,...",
  "csv_column_count": 17,
  "csv_data_rows": 183,
  "one_code_count": 183,
  "unique_one_codes": 176,
  "one_codes_sample": ["ONE5597", "ONE5876", "ONE5970", ...],
}
```

The chatbot tool description explicitly forbids manual counting:

> **REGRA CRITICA SOBRE NUMEROS:** use SEMPRE o campo `stats` do
> retorno como verdade absoluta. NAO conte linhas/codigos
> manualmente lendo o `text` — LLMs erram contagens em payloads
> longos. Quote diretamente: stats.total_lines,
> stats.unique_one_codes, etc.

Re-test: bot said "**198 lines / 176 unique ONE codes / 5 example
codes**" — all three match direct Python verification.

**Recommendation for noc:** any LLM-over-structured-data tool
should precompute aggregates in code and forbid the model from
recomputing. The pattern generalizes beyond Drive:

- transcript tools → wpm + word count + speaker turn count
- email digests → unread count, sender list, attachment count
- calendar list → events per day, total hours, conflicts
- audit log query → row counts, distinct user counts

Lift `_compute_content_stats` into `noctusai_lib.domain.chatbot` as
a generic `compute_aggregates(text, schema_hints)` helper. The
real-estate-specific ONE-code regex stays per-product as a
SchemaHint plugin.

---

## 4 · Files + pointers

- Code: `noctusai-youtube-crawler/products/youtube-crawler/backend/app/services/drive_api/`
- Tool handlers: `app/services/whatsapp_intake_service.py` —
  `search_drive_files`, `list_recent_drive_files`,
  `get_drive_file`, `read_drive_file`, `_compute_content_stats`
- Chatbot tools: `app/services/chatbot_service.py` — 4 entries
  in `_build_tools()`
- Promotion manifest:
  `noctusai-youtube-crawler/.promotions/drive-api-client.md`
- AGENT.md §3.10 — updated with the new tool + the stats rule
- Companion docs:
  - `SESSION-NOTES_chatbot-multichannel-2026-05-12.md` — the
    multichannel chatbot session this builds on
  - `SESSION-NOTES_google-integrations-2026-05-12.md` — Calendar +
    Maps + Drive-URL-parser session
  - `SEED-NEEDS-DEV-AUTH-AND-SQLITE.md` — orthogonal seed-level
    recommendation from the same week

---

## 5 · What's pending (handoff)

- **OAuth consent flow** — wired but never completed because the
  user took the share-with-SA path. Redirect URI registration in
  GCP Console is required before the consent works; the bot's
  `/api/calendar/oauth/start` endpoint is ready. Pending a future
  product whose users need whole-Drive coverage.
- **Write tools** — no `create_file`, `update_file`, or
  `share_file`. The chatbot is read-only on Drive. Out of scope
  for v1.
- **Per-row queries** — `read_drive_file` returns the whole CSV.
  For very large sheets (>200KB of text) it truncates. Future
  enhancement: a `query_drive_sheet(file_id, sql)` tool that
  exports + runs DuckDB or similar.
- **DOCX / XLSX binary** — bot reports them as "binary, can't
  render". Easy add via `python-docx` / `openpyxl` if a product
  needs it.

— filed by Claude (Opus 4.7) working in `noctusai-youtube-crawler`
  on branch `feat/platform-chat-agent`, 2026-05-13, at the user's
  request as historical reference for future expansion into noc.

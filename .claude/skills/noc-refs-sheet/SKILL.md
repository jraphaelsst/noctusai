---
name: noc-refs-sheet
description: Use when filling a midiasone reference spreadsheet from the Drive — triggers "update the Cindy spreadsheet", "feed the Priscila sheet", "fetch the reference links", "atualizar a planilha", "ONExxxxx links", "refs spreadsheet". Resolves each ONExxxxx reference to a Drive folder, counts its videos and writes link + count + a pt-BR Observação; on EVERY run also fixes every Código to canonical `ONE<digits>` and fills/normalizes `Imóvel / Valor` (`Condomínio - Preço`) from the Vista CRM. The link TARGET differs per sheet — getting that wrong means redoing every row.
version: 1.2.0
---

# noc-refs-sheet — ONExxxxx references into a midiasone spreadsheet

> Born from N≥2 recurrence at the `Cindy` (2026-08-31, re-run 2026-09-16) and `Priscila`
> (2026-09-17) spreadsheet runs — the second of which was redone end to end because the
> per-sheet link target in §1 was inferred rather than looked up.

🔴 **The one rule that breaks this task: the link target is PER-SHEET, not global.**
Shipping Priscila the Cindy way on 2026-09-17 meant rewriting all 10 rows. **Never infer
the target from the last sheet you touched — look it up in §1, and if the sheet is not
listed, ASK.**

## 0 · Accounts & IDs — the ONE place to change

Every identity and ID this skill depends on lives in this table. The rest of the skill
names **roles** ("the Drive reader", "the sheet writer"), never an email — so moving to a
different account, a service account, or a shared drive is an edit to these rows only.

| Role / ID | Current value | Used for |
|---|---|---|
| **Drive reader** — the claude.ai Google Drive connector | `midiasone12@gmail.com` | search + list the `ONExxxxx` ref folders (§2 steps 3–4) |
| **Sheet writer** — the Chrome profile driving the sheets | `joaoraphaelsst` | read the CSV export + type cells (§2 step 1, §4) |
| **Probe folder** — any folder the Drive reader must be able to list | `2026` = `1360Sml33ieu8OO7V3vYaVKT3VAd1YFYC` | the preflight below |
| **Cindy** sheet | `1PrOwuJVF6Tq-nENfb2KQBRIzU4TT1bi61tQOVwqYOV0`, `gid=0` | §1 |
| **Priscila** sheet | `1pzE7h67ugyN0__iOsHTMdNFeHRlxBowjnM5uZX1JSFY`, `gid=0` | §1 |

A sheet ID missing from this table ⇒ find it once (Drive search `<name> type:spreadsheet`
in the sheet writer's Chrome) and **record it here in the same run** — re-searching every
time is the friction this row exists to remove.

### Preflight — prove the Drive reader is the right account, BEFORE resolving any ref

Run `search_files` with `parentId = '<probe folder>'` (folders only, `excludeContentSnippets`).

- **Children come back** ⇒ the connector can see the tree; proceed.
- **Empty result** ⇒ the connector is on the wrong account. STOP and ask the user to
  reconnect it as the Drive reader (claude.ai → Settings → Connectors → Google Drive, or
  `/mcp` → reconnect). Do **not** fall back to Drive search in the sheet writer's Chrome:
  it surfaces stray files (`REELS ONE8400.mp4`) but not the ref folders, so it yields
  wrong answers rather than none.

Why a probe, not an email check: on 2026-10-19 the connector had silently moved to a
viewer-only account. `get_file_metadata` by ID still worked (owner shown as midiasone12,
but `canAddChildren: false`), while **every** `search_files` — title or `parentId` — returned
`{}` with no error. The probe tests the capability the skill actually needs, so it keeps
working whatever account §0 names next.

## 1 · The per-sheet contract

| Sheet | Columns | Link points at | Why |
|---|---|---|---|
| **Cindy** | `DT PUBLICAÇÃO, Código, Imóvel / Valor, Link do Vídeo, Vídeos, Observação` | the **`VIDEOS` subfolder** | Debora consumes it for video only — images must stay out |
| **Priscila** | `Código, Imóvel / Valor, Link do Vídeo, Vídeos, Observação` | the **whole `ONExxxxx` ref folder** | she needs the photos too |

**Cindy has a date column; Priscila does not.** So the typing run starts at `D<row>` for
Cindy and `C<row>` for Priscila. `Código` + `Imóvel / Valor` are therefore column **B + C**
on Cindy and **A + B** on Priscila. Both are ours to fix on every run (§2a, §2b); this
replaces the pre-2026-10-20 rule "`Imóvel / Valor` is the user's — never fill it".

A sheet not in this table ⇒ ask which target it wants before writing anything. Once
Phase C of `projects/one-ops-agents/PROJECT.md` lands, this table is superseded by the DB
registry and this skill points at it instead.

## 2 · Workflow

0. **Preflight** the Drive reader (§0). Empty ⇒ stop and ask for a reconnect.
1. **Read the sheet.** The sheets belong to the sheet writer, not the Drive reader, so the
   connector cannot see them. Open the sheet (ID from §0) in the sheet writer's Chrome and
   fetch: `fetch('/spreadsheets/d/<id>/export?format=csv&gid=0')`.
2. **Take only the rows that need work** — the ones with a `Código` and an empty link.
   Never enumerate every ref in the Drive. **Steps 2a + 2b run on EVERY row, every run —
   including rows whose link is already filled.** Refs are typed by hand, so a run that only
   touches the new rows leaves the old drift in place.
   - **2a.** Fix every `Código` (§2a).
   - **2b.** Fill or normalize every `Imóvel / Valor` from Vista (§2b).
3. **Resolve each ref** via the connector (the Drive reader). The search term must be the
   full `ONExxxxx` token — `title contains '8400'` returns nothing, because Drive matches
   title words by prefix:
   `title contains 'ONExxxxx' and mimeType = 'application/vnd.google-apps.folder'`,
   then `parentId = '<ref id>'` for its children, and `parentId = '<VIDEOS id>'` to count.
   Add `excludeContentSnippets: true` and filter to folders — an unfiltered listing of a
   photo folder floods the context.
4. **Resolve the parent month** (`get_file_metadata` on the ref's `parentId`) — the
   Observação names it. Two hierarchies coexist: 2025-style (`Maio`…`Outubro`) under
   `Material 2025`, and 2026-style (`2-FEVEREIRO`, `5-MAIO`, `7- JULHO`) under `2026`.
   Some refs sit outside both, e.g. under `FOTOS DIVERSAS`.
5. **Write the row** — see §4.
6. **Verify** — see §5.

## 2a · `Código` — canonical form, CHECK AND FIX on every run

Canonical form is `^ONE\d+$`: uppercase `ONE` followed by the digits, nothing else
(`ONE9999`, `ONE10000`). Hand-typed variants seen live: `one10118`, `One8400`, and
U+2060 word-joiners before the code (§3).

- **Normalize:** strip whitespace + zero-width/word-joiner characters (`​-‍⁠﻿`),
  uppercase it, and drop any inner space or dash between `ONE` and the digits.
- **Fix it in the sheet, not just in your head.** A check that only reports leaves the
  sheet wrong. Retype every non-canonical cell (typing over a selected cell replaces it).
- **Unfixable** (no `ONE` prefix, no digits, a different prefix): do NOT guess. Leave
  the cell and list it for the user, with the row.
- A row with a date but **no** Código: leave it and flag it.

## 2b · `Imóvel / Valor` — `Condomínio - Preço`, from Vista, on every run

Format: `<Condomínio> - <preço pt-BR>`, e.g. `Quebec Ville - 850.000`,
`Reserva do Moinho - 3.980.000`. Exactly ` - ` (space-dash-space) between the two, `.` as
the thousands separator, no `R$`, no cents. Regex: `^.+ - \d{1,3}(\.\d{3})+$`.

**Source = the Vista CRM**, via `mcp/vista` (`vista.imoveis.get codigo=<ONExxxxx>`):

| Sheet part | Vista field | Rule |
|---|---|---|
| Condomínio | `Empreendimento` | keep only the text before the FIRST ` - ` (drops `- Km 21`, `- Fazendinha - Km 23`). Empty ⇒ fall back to `Bairro`, same rule. |
| Preço | `ValorVenda` | integer reais → pt-BR thousands (`3980000` → `3.980.000`) |

- **Reuse the sheet's existing spelling for a condo it already names.** The user shortens
  some names (`Authentiq`, not `Authentiq Granja Viana`; `Jd das Paineiras`, not
  `Jardim Das Paineiras`). Check the column for the same condo first; only a condo that
  is new to the sheet uses the Vista text, with lowercase connectors (`Parque das Artes`).
- **Empty cell** ⇒ fill it. **Filled but off-pattern** (e.g. `Reserva do Moinho 3.980.000`,
  missing ` - `) ⇒ rewrite it in the pattern, keeping the user's name + price.
- **Filled, but the price differs from Vista** ⇒ do NOT overwrite (it may be the price
  at publication time). List it for the user: row, sheet value, Vista value.
- **`VistaRecordUnpublished`** (`ExibirNoSite=Nao`; the API key cannot see the record) ⇒
  leave the cell empty and tell the user. Never invent a value.

**Calling it when the `vista` MCP is disabled for the session** (it is off the keep-list
in `settings.local.json`): call the handler directly from the MCP's venv:

```python
# run: SSL_CERT_FILE=/etc/ssl/cert.pem mcp/noctusai/.venv/bin/python <script> ONE8400 ...
import asyncio, sys
sys.path.insert(0, "<repo>/mcp")
from vista.tools.imoveis import get_imovel
async def main():
    for c in sys.argv[1:]:
        r = await get_imovel({"codigo": c})
        raw = (((r.get("item") or {}).get("base") or {}).get("raw")) or {}
        print(c, r.get("error", {}).get("error_class") if r.get("error") else "",
              raw.get("Empreendimento"), raw.get("Bairro"), raw.get("ValorVenda"))
asyncio.run(main())
```

## 3 · Traps, each of which has cost a redo

- **Duplicate ref folders are the norm, not the exception.** Which one wins depends on the
  sheet: Cindy (videos-only) ⇒ whichever folder HAS the videos; Priscila (whole ref) ⇒ the
  folder holding **both** FOTOS and VIDEOS. Always name what the *other* folder holds in
  the Observação.
- **Sometimes no single folder satisfies the rule.** `ONE10107` has photos in `4-ABRIL` and
  its two videos in a separate `ONE10107 (OPEN H)` folder under `5-MAIO`. Link the main ref
  folder and put the second folder's URL **inside the Observação** — never silently drop it.
- **Videos are often loose at the ref root** with no `VIDEOS` subfolder (`ONE8708`,
  `ONE8132`). Link the ref folder and say so.
- **A `.txt` music-license file lives inside `VIDEOS`. It is not a vídeo.** Count
  `mimeType` video files only.
- **Decoy folders exist.** `VIDEO ERRADO OUTRA CASA - ONE8861 (EXCLUSIVA)` is the wrong
  property. Read folder titles, do not just match the number.
- **Codes carry invisible characters.** Priscila's sheet has U+2060 word-joiners prefixing
  some codes (`⁠ONE8132`). Match on the digits.
- **A link cell can hold a smart chip, not a URL.** The CSV export shows the chip's title
  (`Vídeos - Google Drive`), so a naive `^https?:` test flags it as empty. A non-empty link
  cell is the user's — leave it.
- **The same code can appear on two rows** (Cindy `ONE10602`, rows 4 and 17). Fill it the
  same way and say `código repetido (já está na linha N)` in the Observação; deleting the
  duplicate is the user's call.
- **Codes are sometimes lowercase** (`one10846`, `One8400`). Drive search is
  case-insensitive, but the cell itself gets fixed to `ONE10846` (§2a), not just the Observação.
- **A column run can land one row off.** On 2026-10-20 a `Down`×N hop after a `Return`
  chain put the `Imóvel / Valor` values one row high. Start every non-contiguous run from
  a fresh `range=` URL instead of arrow-key hops, and let §5 catch the rest.
- **Navigating away too soon is blocked by a "Leave site?" dialog** while Sheets is still
  saving. Wait about 5 s after the last keystroke before the next `range=` navigation.

## 4 · Writing cells (Chrome — the connector CANNOT write)

`update_file` takes only `title` + `parentId`; there is no cell-write path through the
connector, and the calendar service account does not carry a `spreadsheets` scope.

- Select the first cell by URL, with the range in the **query string too**:
  `.../edit?gid=0&range=C2#gid=0&range=C2` (or `D2` for Cindy). A hash-only change on an
  already-open tab does not reload — the cell looks selected but the grid has no keyboard
  focus and every keystroke is silently dropped. Screenshot to confirm the selection
  before typing.
- Then per row: `type` link → `Tab` → count → `Tab` → Observação → `Return`.
  **`Return` reliably returns to the starting column of the next row**, so rows chain.
- Batch a whole row (or several) through `browser_batch` — it is markedly faster and the
  chaining holds across rows.
- **Typing over a selected cell replaces it**, so a redo is just the same run again.
- 🔴 **Never click grid coordinates to target a cell.** Clicks land one row low and the
  Name Box is unreliable — a click at its coordinates once typed into A1 and clobbered the
  header. The `range=` URL is the only safe targeting.

### Observação style (pt-BR, every filled row gets one)

```
found     → pasta ONE8346 (Outubro) — FOTOS + VIDEOS — 4 vídeos (YT + REELS, normal e EXCLUSIVA)
videos-only sheet → pasta ONE10515 (7-JULHO) — link aponta para a subpasta VIDEOS — 2 vídeos (YT + REELS)
loose     → pasta ONE8708 (Julho) — subpasta Fotos + 2 vídeos soltos na raiz (YT REF + REELS)
not found → sem vídeo — pasta ONE10846 não encontrada no Drive (nenhuma pasta ou arquivo com 10846)
```

## 5 · Verification — assert BOTH directions

Re-export the CSV (`cache:'no-store'`) and assert programmatically:

1. every expected folder id **is present** on its row, with the right count; **and**
2. every **superseded** id is **gone** from the sheet; **and**
3. every non-empty `Código` matches `^ONE\d+$` (§2a); **and**
4. every non-empty `Imóvel / Valor` matches `^.+ - \d{1,3}(\.\d{3})+$` **and** sits on
   the row of its own code (compare against the Vista value you fetched, row by row; a
   shifted run passes the regex but fails this check).

Leg 2 is what catches a half-finished redo. The export lags a few seconds behind the last
edit — re-fetch before calling a cell missing.

## 6 · Depth

`projects/one-ops-agents/PROJECT.md` (the productisation of this procedure; §5 has the
service-account plan that will replace the browser route — when it lands, it becomes the
new Drive reader / sheet writer in §0) · memory
`feedback_agent_drive_access_uses_claude_connector` (which Drive identity can see what,
and why the connector cannot write).

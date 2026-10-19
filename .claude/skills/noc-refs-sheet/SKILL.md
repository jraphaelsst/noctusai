---
name: noc-refs-sheet
description: Use when filling a midiasone reference spreadsheet from the Drive — triggers "update the Cindy spreadsheet", "feed the Priscila sheet", "fetch the reference links", "atualizar a planilha", "ONExxxxx links", "refs spreadsheet". Resolves each ONExxxxx reference to a Drive folder, counts its videos and writes link + count + a pt-BR Observação. The link TARGET differs per sheet — getting that wrong means redoing every row.
version: 1.1.0
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
Cindy and `C<row>` for Priscila. Column B (`Imóvel / Valor`) is the user's — never fill it.

A sheet not in this table ⇒ ask which target it wants before writing anything. Once
Phase C of `projects/one-ops-agents/PROJECT.md` lands, this table is superseded by the DB
registry and this skill points at it instead.

## 2 · Workflow

0. **Preflight** the Drive reader (§0). Empty ⇒ stop and ask for a reconnect.
1. **Read the sheet.** The sheets belong to the sheet writer, not the Drive reader, so the
   connector cannot see them. Open the sheet (ID from §0) in the sheet writer's Chrome and
   fetch: `fetch('/spreadsheets/d/<id>/export?format=csv&gid=0')`.
2. **Take only the rows that need work** — the ones with a `Código` and an empty link.
   Never enumerate every ref in the Drive.
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
- **Codes are sometimes lowercase** (`one10846`) — Drive search is case-insensitive, the
  Observação should still say `ONE10846`.

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
2. every **superseded** id is **gone** from the sheet.

Leg 2 is what catches a half-finished redo. The export lags a few seconds behind the last
edit — re-fetch before calling a cell missing.

## 6 · Depth

`projects/one-ops-agents/PROJECT.md` (the productisation of this procedure; §5 has the
service-account plan that will replace the browser route — when it lands, it becomes the
new Drive reader / sheet writer in §0) · memory
`feedback_agent_drive_access_uses_claude_connector` (which Drive identity can see what,
and why the connector cannot write).

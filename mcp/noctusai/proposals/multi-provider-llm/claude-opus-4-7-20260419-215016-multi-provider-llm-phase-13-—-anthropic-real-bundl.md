# Proposal: Multi-provider LLM Phase 13 — Anthropic real bundled improvements

**Agent:** claude-opus-4-7
**Origin:** project:multi-provider-llm:phase-13
**Generated:** 2026-04-19 21:50
**Severity:** low
**Effort:** low
**Affected products:** core, erp-imobiliario, therapy-platform, seed
**Status:** pending

---

## 1. Context

Phase 13 replaced the Anthropic stub with real `AsyncAnthropic` SDK calls for chat + vision. Embeddings + transcription explicitly raise `ProviderNotImplemented` (Anthropic doesn't ship those APIs). 5 tests.

---

## 2. Situation

Real wiring works but leaves three known gaps: `_sniff_image_mime` doesn't handle HEIC (mobile iOS photos), JSON-mode translation is prompt-injection-based rather than using Anthropic's native tool-use structured output, and there's no network-integration test to catch SDK signature drift.

---

## 3. Proposed Solution

### 3.1 Linkage — why this solution fits this situation

Each bundled improvement tightens a boundary the Phase shipped loose. None block production — they clean up debt before it ossifies.

### 3.2 Application instructions

#### 1. Add HEIC detection to _sniff_image_mime

**Linkage:** iOS photos default to HEIC (`ftypheic` magic at offset 4). Currently misreported as JPEG.

**Steps:**
1. Add `if data[4:8] == b"ftyp" and data[8:12] in (b"heic", b"heix"): return "image/heic"`
2. Test with an HEIC fixture

**Risks:** Low — adds a branch

*Independent:* can be applied without other bundled improvements.

#### 2. Use Anthropic native structured output for JSON mode

**Linkage:** Current impl appends 'Return valid JSON' to system prompt. Anthropic's `tool_use` with `input_schema` is more reliable.

**Steps:**
1. Detect `response_format == {type: json_object}` in chat_completion
2. When a `json_schema` kwarg is present, convert to a tool definition
3. Extract the tool-use result from the response

**Risks:** Medium — tool-use changes the response shape. Feature-flag behind a new `use_native_structured=True` kwarg.

*Independent:* can be applied without other bundled improvements.

#### 3. Nightly smoke test against the real Anthropic API

**Linkage:** Unit tests mock the SDK. SDK signature changes slip through until a product fails.

**Steps:**
1. Add a GitHub Action / nightly job that sends a tiny prompt to `claude-haiku-4-5`
2. Alert on failure
3. Scope to the Anthropic account with a $0.50/day budget

**Risks:** Small recurring cost (<$15/month for daily runs)

*Independent:* can be applied without other bundled improvements.

### 3.3 Seed APIs / shared lib involved

N/A — change is local to the product.

### 3.4 Risks before applying

Low — additive changes.

### 3.5 Alternatives considered

N/A — the situation dictates the fix.

---

## 4. Effects

When this is applied, these change:

- **Behavior:** Unchanged — improvements are structural.

---

## 5. Acceptance Criteria

- [ ] Fix applied to every affected product (not just the one that triggered detection)
- [ ] `python mcp/noctusai/cli.py --validate` shows 100/100 for the affected product(s)
- [ ] `python mcp/noctusai/cli.py --review --product core` files no new proposals for this issue
- [ ] Backend tests still pass for the affected product(s)
- [ ] If the change touched shared code, `python mcp/noctusai/cli.py --catalog` shows no new orphans or duplicate candidates
- [ ] Documentation updated KB-first, CLAUDE.md second (per `KNOWLEDGE-BASE/CONTEXT/01-PHILOSOPHY.md → Docs stay in sync`)

---

## 6. Related files

- `seed/backend/lib/noctusai_lib/llm/providers/anthropic_provider.py` — Real implementation

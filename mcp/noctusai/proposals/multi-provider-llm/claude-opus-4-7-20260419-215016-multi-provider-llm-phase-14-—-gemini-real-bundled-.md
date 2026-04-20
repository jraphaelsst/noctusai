# Proposal: Multi-provider LLM Phase 14 — Gemini real bundled improvements

**Agent:** claude-opus-4-7
**Origin:** project:multi-provider-llm:phase-14
**Generated:** 2026-04-19 21:50
**Severity:** low
**Effort:** low
**Affected products:** core, erp-imobiliario, therapy-platform, seed
**Status:** pending

---

## 1. Context

Phase 14 replaced the Gemini stub with real `google-generativeai` SDK calls across chat, embeddings, vision, and audio. 3 tests + streaming integrated in Phase 12.

---

## 2. Situation

Implementation works but inherits three limitations from the SDK: `genai.configure(api_key=...)` is module-global (concurrency race with per-tenant keys), the `google-generativeai` package is EOL per a printed FutureWarning, and URL-image support is rejected rather than auto-handled.

---

## 3. Proposed Solution

### 3.1 Linkage — why this solution fits this situation

Each bundled improvement tightens a boundary the Phase shipped loose. None block production — they clean up debt before it ossifies.

### 3.2 Application instructions

#### 1. Track Gemini SDK migration to google-genai

**Linkage:** google-generativeai is EOL. Migration bundled with Phase 12's improvement block too — primary owner.

**Steps:**
1. See Phase 12 improvement bundle item 4

**Risks:** Medium

*Depends on:* improvement(s) #Phase 12 bundle item 4.

#### 2. Auto-download URL images for Gemini analyze_image

**Linkage:** Callers passing `image=url` currently get `LLMAPIError`. Convenient auto-download preserves the contract with OpenAI/Anthropic.

**Steps:**
1. If `isinstance(image, str)` and looks like a URL, httpx.get(url)
2. Detect MIME from response.headers['content-type']
3. Pass bytes+mime as the part

**Risks:** Low — adds a network call. Fails gracefully via LLMAPIError still.

*Independent:* can be applied without other bundled improvements.

#### 3. Document task_type semantics for Gemini embeddings

**Linkage:** Default `RETRIEVAL_DOCUMENT` is for ingestion. Query-time embedding needs `RETRIEVAL_QUERY`. Not documented today.

**Steps:**
1. KB doc update in PATTERNS/llm-retrieval.md (new file)
2. Add a Gemini-specific note to ModelEntry descriptions

**Risks:** None

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

- `seed/backend/lib/noctusai_lib/llm/providers/gemini_provider.py` — Real implementation

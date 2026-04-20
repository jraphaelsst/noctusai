# Proposal: Multi-provider LLM Phase 12 — Streaming bundled improvements

**Agent:** claude-opus-4-7
**Origin:** project:multi-provider-llm:phase-12
**Generated:** 2026-04-19 21:50
**Severity:** low
**Effort:** low
**Affected products:** core, erp-imobiliario, therapy-platform, seed
**Status:** pending

---

## 1. Context

Phase 12 added `chat_completion_stream()` with real streaming across OpenAI / Anthropic / Gemini + FakeProvider scripted streams. Response cache is disabled for streams. 5 tests.

---

## 2. Situation

Streaming shipped but with partial observability: mid-stream errors skip usage recording; Protocol type-hints use `AsyncIterator` (fuzzy for async generators); cache-kwarg stripping is silent; Gemini's streaming uses a deprecated SDK package.

---

## 3. Proposed Solution

### 3.1 Linkage — why this solution fits this situation

Each bundled improvement tightens a boundary the Phase shipped loose. None block production — they clean up debt before it ossifies.

### 3.2 Application instructions

#### 1. Record partial usage on stream interruption

**Linkage:** If the client drops connection mid-stream, usage isn't recorded and cost under-reports.

**Steps:**
1. Wrap the async-for in try/finally that calls record_usage with the last-seen counts
2. Tag the event with `extra: {"partial": true}`

**Risks:** Low — already tracking prompt/completion as iteration progresses

*Independent:* can be applied without other bundled improvements.

#### 2. Tighten Protocol annotations to AsyncGenerator

**Linkage:** `AsyncIterator[str]` is the return type; `AsyncGenerator[str, None]` is precise and catches accidental non-generator returns.

**Steps:**
1. Update `base.py` Protocol
2. Fix any downstream type errors

**Risks:** None — runtime behavior unchanged

*Independent:* can be applied without other bundled improvements.

#### 3. DEBUG-log cache-kwarg stripping in chat_completion_stream

**Linkage:** Callers who expect streams to respect caching are silently ignored.

**Steps:**
1. Add a `logger.debug("cache kwargs dropped for stream")` before the pops

**Risks:** None

*Independent:* can be applied without other bundled improvements.

#### 4. Migrate Gemini integration from deprecated google-generativeai to google-genai

**Linkage:** `google-generativeai` prints a FutureWarning — EOL package. Newer `google-genai` has per-instance clients (fixes the module-global `genai.configure` race noted in Phase 14).

**Steps:**
1. Add `google-genai` to pyproject.toml
2. Port GeminiProvider to the new API (Client() constructor, `client.models.generate_content`)
3. Update streaming + embeddings + vision + audio methods
4. Regenerate tests

**Risks:** Medium — SDK surface differs. Deferred until a product actually uses Gemini, but tracked explicitly so we don't forget.

*Depends on:* improvement(s) #1.

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

# LLM tool-call audit

> Pattern + contract for `noctusai_lib.domain.ai.tool_audit`. Every
> LLM-tool dispatch a product makes can write one row to a per-product
> `tool_call_audits` table for observability — joinable to log lines
> via `correlation_id`, to the calling user via `user_id`, to a single
> conversation via `conversation_id`.

---

## 1. Why audit at all

LLM tool calls are the cracks in our observability surface today. A
product wires GPT to a set of tools (calendar lookups, scheduling
proposals, user lookups, …); GPT picks one + arguments; the product
runs it; the result feeds back into the conversation. When something
goes wrong — wrong tool fired, bad arguments, wrong answer — the only
trail is whatever the product happened to log. There's no canonical
"what did the bot decide for user X today" view.

`tool_call_audits` is that view. One row per dispatch, regardless of
outcome (success / failure / unknown_tool). Treat it as the bot's
memory of its own decisions.

---

## 2. Schema

Lives in **each product's own DB**, not a shared platform table — per
the cross-product LGPD block (no shared platform PII tables until
encryption ships). Schema is uniform across products via the migration
template at `noctusai_lib/domain/ai/migrations/tool_call_audits.sql.template`.

| Column            | Type        | Why                                                                |
|---|---|---|
| `id`              | BIGSERIAL   | PK.                                                                |
| `correlation_id`  | VARCHAR(64) | Joins to log lines via `noctusai_lib.primitives._correlation`.     |
| `gpt_call_id`     | VARCHAR(64) | OpenAI-issued tool_call.id (informational, not unique).            |
| `tool_call_id`    | VARCHAR(64) | Platform-issued ID (when distinct from gpt_call_id).               |
| `conversation_id` | VARCHAR(64) | Groups all tool calls within one bot conversation.                 |
| `user_id`         | BIGINT      | Calling user. Nullable for unauthorized / system flows.            |
| `tool_name`       | VARCHAR(80) | The tool that ran (or "unknown_tool: <name>" for misses).          |
| `status`          | VARCHAR(16) | `success` / `failure` / `unknown_tool`. Index for error-rate scans. |
| `arguments`       | JSONB       | What GPT asked for. Round-tripped through `_safe_jsonable`.        |
| `result`          | JSONB       | What the tool returned. Same.                                      |
| `error`           | TEXT        | `<ExceptionType>: <message>` when status != success.               |
| `duration_ms`     | INTEGER     | Wall-clock dispatch time.                                          |
| `started_at`      | TIMESTAMPTZ | Defaults to `now()`.                                               |

**Indexes:** `correlation_id`, `(user_id, started_at)`, `tool_name`,
`status`, `(conversation_id, started_at)`. The two primary observability
paths are log-line joins (correlation_id) and per-user time-window scans.

**Retention:** no automatic TTL in v1. The `archived_at` column is
commented out in the template — uncomment when you wire a retention
sweep. Project ledger: `projects/llm-audit-retention/` (file once a
second consumer surfaces).

---

## 3. Wiring (consumer side)

### 3a. Apply the migration template

Copy `noctusai_lib/domain/ai/migrations/tool_call_audits.sql.template`
into `products/<your-product>/backend/migrations/NNN_tool_call_audits.sql`.
Replace `{{SCHEMA_NAME}}` with the product's schema. Apply via
Supabase MCP per `KB § PATTERNS/database-rls.md`:

```bash
# Apply
# (via MCP) mcp__claude_ai_Supabase__apply_migration name=NNN_tool_call_audits query="<file contents>"
# Verify
# (via MCP) mcp__claude_ai_Supabase__list_tables schemas=["{{SCHEMA_NAME}}"]
```

### 3b. Define the product's ORM model

```python
# products/<product>/backend/app/models/tool_call_audit.py
from sqlalchemy import BigInteger, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ToolCallAudit(Base):
    __tablename__ = "tool_call_audits"
    __table_args__ = {"schema": "<your_schema>"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64))
    gpt_call_id: Mapped[str | None] = mapped_column(String(64))
    tool_call_id: Mapped[str | None] = mapped_column(String(64))
    conversation_id: Mapped[str | None] = mapped_column(String(64))
    user_id: Mapped[int | None] = mapped_column(BigInteger)
    tool_name: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    arguments: Mapped[dict | None] = mapped_column(JSONB)
    result: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[..] = mapped_column(DateTime(timezone=True),
                                            server_default=func.now(),
                                            nullable=False)
```

### 3c. Wire the writer at the LLM dispatcher

```python
# In the chatbot framework's llm_dispatcher.py (or the product's call site)
from noctusai_lib.domain.ai.tool_audit import (
    AuditRecord,
    make_audit_writer,
    now_utc,
)
from app.models.tool_call_audit import ToolCallAudit


def dispatch_tool(db, call, ctx):
    audit_writer = make_audit_writer(db, ToolCallAudit)
    started_at = now_utc()
    t0 = time.perf_counter()
    try:
        result = run_tool(call, ctx)
        audit_writer(AuditRecord(
            tool_name=call.name,
            status="success",
            duration_ms=int((time.perf_counter() - t0) * 1000),
            started_at=started_at,
            arguments=call.arguments,
            result=result,
            correlation_id=ctx.correlation_id,
            gpt_call_id=call.call_id,
            conversation_id=ctx.conversation_id,
            user_id=ctx.user_id,
        ))
        return result
    except Exception as exc:
        audit_writer(AuditRecord(
            tool_name=call.name,
            status="failure",
            duration_ms=int((time.perf_counter() - t0) * 1000),
            started_at=started_at,
            arguments=call.arguments,
            error=f"{type(exc).__name__}: {exc}",
            correlation_id=ctx.correlation_id,
            gpt_call_id=call.call_id,
            conversation_id=ctx.conversation_id,
            user_id=ctx.user_id,
        ))
        raise
```

The writer is **best-effort**: a DB exception inside `audit_writer(...)`
is logged at WARNING and swallowed. Your dispatch never fails because
the audit table hiccupped.

---

## 4. Status values — what they mean

- **`success`**: tool returned a value. `result` populated, `error` null.
- **`failure`**: tool raised. `result` null, `error` =
  `<ExceptionType>: <message>`. The dispatcher should also log + decide
  whether to surface the error to GPT or convert to a structured
  apology.
- **`unknown_tool`**: GPT named a tool the registry doesn't expose.
  `result` null, `error` = `unknown_tool: <name>`. Either GPT
  hallucinated the tool name, or the registry is mis-wired. Both are
  worth a row.

The `status` column is index-friendly so error-rate dashboards (e.g.
`SELECT count(*) FROM tool_call_audits WHERE status='failure' AND
started_at > now() - interval '1 day'`) hit an index.

---

## 5. LGPD redaction

`arguments` and `result` may carry PII (a user's phone number in a
lookup, clinical text in a therapy product, financial figures, etc.).
Products handling **Art. 11 sensitive data** MUST redact those fields
**before** constructing the `AuditRecord`. The lib's writer is
domain-agnostic; redaction is a consumer-side responsibility.

Worked example (therapy):

```python
def redact(args: dict) -> dict:
    """Strip clinical text from args before audit."""
    return {k: ("[REDACTED]" if k in {"transcript", "notes"} else v)
            for k, v in (args or {}).items()}

audit_writer(AuditRecord(
    arguments=redact(call.arguments),
    result=redact(result) if isinstance(result, dict) else "[REDACTED]",
    ...
))
```

When uncertain whether a field needs redaction, run the LGPD five
questions (`KB § PATTERNS/lgpd.md`) or call `noctus.dev.lgpd_flag(...)`.

---

## 6. Common queries

```sql
-- Per-user tool sequence for a 24h window (debugging "what did user X do today")
SELECT started_at, tool_name, status, duration_ms, error
FROM <schema>.tool_call_audits
WHERE user_id = $1 AND started_at > now() - interval '1 day'
ORDER BY started_at;

-- Failure-rate per tool over the last week
SELECT tool_name,
       count(*) FILTER (WHERE status = 'success')  AS ok,
       count(*) FILTER (WHERE status = 'failure')  AS fail,
       count(*) FILTER (WHERE status = 'unknown_tool') AS missing
FROM <schema>.tool_call_audits
WHERE started_at > now() - interval '7 days'
GROUP BY tool_name
ORDER BY fail DESC;

-- One conversation's reconstructed dispatch trail
SELECT tool_name, status, arguments, result, error, duration_ms
FROM <schema>.tool_call_audits
WHERE conversation_id = $1
ORDER BY started_at;

-- Join with logs via correlation_id (assuming a logs table or external sink)
SELECT a.started_at, a.tool_name, a.status, a.error, l.message
FROM <schema>.tool_call_audits a
LEFT JOIN <logs_table> l USING (correlation_id)
WHERE a.correlation_id = $1;
```

---

## 7. What this pattern is NOT

- **Not a replay log** for the LLM provider's raw payloads. Raw
  WAHA / OpenAI / Google API payloads deserve their own
  `webhook_events`-style table at the consumer level with its own
  retention. See the `provider-payload-audit` future-hook in
  `projects/llm-tool-call-audit/PROJECT.md` §12.
- **Not a confidence-threshold gate.** Low-confidence tool calls
  belong in the LLM dispatcher (chatbot framework), not the audit.
  See `KB § PATTERNS/llm-bot-security.md § Confidence thresholds`.
- **Not a retention boundary.** v1 keeps rows indefinitely. Retention
  TTL is a separate follow-up project.

---

## 8. Adoption checklist

When you wire `tool_call_audits` into a new product:

- [ ] Migration applied via Supabase MCP; `tool_call_audits` table
      visible in the schema.
- [ ] Product's `ToolCallAudit` ORM model defined against the product's
      `Base`.
- [ ] LGPD redaction function written for the product's PII fields.
      Tested with a representative call.
- [ ] LLM dispatcher wires `make_audit_writer(db, ToolCallAudit)` and
      calls `audit_writer(...)` on every dispatch.
- [ ] Smoke test: a successful dispatch + a failing dispatch + an
      unknown-tool dispatch each produce an expected row.
- [ ] Optional: RLS policy enabled if the table is reachable through
      the API surface (most products' audit tables are admin-only;
      RLS is overkill if no router exposes them).

Cross-reference: `KB § PATTERNS/llm-bot-security.md` for the defense
layer (sanitization, validation, rate-limiting). The audit is
observation; security is prevention. Both ship together for any
LLM-tool-using product.

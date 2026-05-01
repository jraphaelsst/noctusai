# Logging Convention

Single source of truth for how production code emits operational signal across the platform. Entry-points configure once via the seed-lib helpers; everything else just gets a logger and uses it.

## The rule

**Every code path that catches an exception MUST log, raise, or surface the error through a return value. There is no `# silent-ok` escape hatch.** The detector `check_silent_errors` enforces this AST-side. Bootstrap-time code (e.g. `noctusai_seed._version` resolving the SHA before `configure_logging` runs) uses `logger.debug(...)` — the call is statically present, the root logger drops it by default, and `NOCTUSAI_DEBUG=1` reveals it during troubleshooting.

**Why no `# silent-ok`.** It was retired 2026-04-28 because it created a class of failure invisible to operators: a comment said "we know we're swallowing this" but produced no signal at runtime. The replacement (`logger.debug(...)`) costs the same one line and gives the operator a knob to turn the signal back on without redeploying.

→ memory: `feedback_silent_ok_is_not_a_substitute_for_logging.md`
→ memory: `feedback_no_silent_errors.md`
→ KB § 06-AGENTS.md § Detectors § `check_silent_errors`
→ CLAUDE.md "No silent errors — always explicit fix opportunities"

## Choosing a level

The level is the operator's filter. Pick by *who needs to see it*, not by *how bad you feel about it*.

| Level | Use when |
|---|---|
| `logger.debug(...)` | The path executed; an operator only needs to know during troubleshooting. **Bootstrap fall-throughs, best-effort caches that missed, optional-module shims, version-resolution fallbacks.** Hidden by default. |
| `logger.info(...)` | A meaningful business event happened. **Request started/completed, batch processed N records, scheduled job ran.** Backend default level. |
| `logger.warning(...)` | Something unexpected happened but the request can continue. **Degraded fallbacks, retry-able transient failures, partial results.** This is where operators look first when something feels off. |
| `logger.error(...)` | The request/job failed in a way the caller will notice. **5xx-class server errors, dropped messages, lost work.** |
| `logger.exception(...)` | Same as `error`, plus stack trace. Use **inside an `except`** when you want the traceback in the log line. |
| `logger.critical(...)` | The system itself is in trouble. Reserved for: data-integrity violations, security boundary breached, can't continue. Pages oncall (when paging is wired). |

## The `except` pattern

The form below satisfies `check_silent_errors`. Pick whichever line fits the situation; do not omit all three.

```python
try:
    result = third_party.call(...)
except SomeExpectedError as exc:
    logger.warning("third_party.call failed for %s: %s", arg, exc)
    return fallback                  # surfaces via return
except Exception as exc:
    logger.exception("third_party.call unexpectedly failed for %s", arg)
    raise                            # re-raise after logging
```

Anti-patterns the detector flags:

```python
except Exception:                    # ❌ swallow + no signal
    pass

except Exception:
    return None                      # ❌ surfaces None silently — caller can't tell apart from "no result"

except Exception:                    # ❌ retired escape hatch
    pass  # silent-ok: known noisy
```

The third form was the silent-ok escape hatch. It is now flagged the same as the first two — the comment is not load-bearing.

## Bootstrap-time code

Some code runs before `configure_logging(...)` has been called: importing the seed library at startup, the version-resolution shim that reads `_version_static.py`, MCP `server.py` initialization. These paths still need to satisfy the detector. Use `logger.debug(...)` — Python's root logger silently drops debug by default, so the line produces no output in production, but `NOCTUSAI_DEBUG=1` reveals it for troubleshooting.

```python
try:
    sha = importlib.metadata.version("noctusai_seed")
except importlib.metadata.PackageNotFoundError:
    logger.debug("noctusai_seed not installed; falling back to _version_static")
    sha = _read_static_version()
```

## Configuration

Entry-points configure logging exactly once, then every other module just does `logger = logging.getLogger(__name__)`.

| Entry-point | Helper | Notes |
|---|---|---|
| Backend products (FastAPI) | `configure_logging(debug=..., json_logs=..., app_name=...)` from `noctusai_lib.logging_config` | Called from `create_product_app(...)` lifespan. |
| CLI / scripts | `auto_configure_for_cli(app_name="...")` | Reads `NOCTUSAI_DEBUG` / `NOCTUSAI_JSON_LOGS` env vars. Human-readable by default — JSON is hostile to humans reading `--validate` output. |
| MCP server | `auto_configure_for_cli(app_name="...", use_stderr=True)` | **`use_stderr=True` is required** — MCP servers use stdout for JSON-RPC; any non-JSON byte on stdout breaks the channel. |

After config, modules just do:

```python
import logging
logger = logging.getLogger(__name__)
```

`__name__` gives every record its module path automatically — never hand-craft logger names like `"my-feature"`. The consistent dotted-path is what makes log filtering work across products.

## Correlation IDs

The seed-lib middleware (`noctusai_lib.middleware`) attaches a `correlation_id` to every request and propagates it to log records via a `ContextVar`. Backend product loggers automatically include `correlation_id=...` in human-readable output and `"correlation_id": "..."` in JSON output, with no per-call overhead. Don't pass `correlation_id` as a kwarg manually — the formatter pulls it from the context.

Background tasks, cron jobs, and MCP tool invocations don't have a request — they don't get correlation IDs unless the caller spawned them inside one. That's fine; absence of correlation ID is itself a useful signal ("this came from an out-of-band path").

## Format

| Mode | Used for | Shape |
|---|---|---|
| Human-readable (default) | Local dev, CLI tools, MCP server stderr | `2026-04-29 15:10:24 \| INFO     \| [erp] noctusai_lib.middleware \| Request completed \| correlation_id=...` |
| JSON | Production backends (when `NOCTUSAI_JSON_LOGS=1`) | One JSON object per line, parseable by log shippers (Datadog, Loki, CloudWatch). |

`app_name` (the value passed to `configure_logging` / `auto_configure_for_cli`) appears as the bracketed prefix in human mode and the `"app"` field in JSON mode. Use it to disambiguate multi-product log streams.

## What NOT to log

- **Secrets.** API keys, tokens, passwords, JWTs, signed cookies. The credential masking helpers in `noctusai_lib.credentials` exist for this — `mask_secret(value)` returns a redacted form (`"sk-...abcd"`) safe to log.
- **Personal data the way it appears in the body.** Clinical notes, full names, CPF/CNPJ, addresses. Log the *fact* of the operation (`"Updated patient record patient_id=p123"`), not the diff. LGPD: clinical text is Art. 11; never log the body.
- **High-cardinality identifiers in templates.** Use `%s`-style interpolation (`logger.info("created %s", id)`) — log aggregators index the template, not the formatted line, so cardinality stays bounded.
- **Loops.** A `for x in items: logger.info(...)` over a 10k-item list buries the rest of the request. Aggregate (`logger.info("processed %d items", len(items))`) and only log the per-item case at `debug`.

## Adding a new compliance / keeper detector

The keeper detectors that watch over the platform follow the same convention: every detector ships colocated with a regression test. The detector `check_detector_has_regression_test` enforces this — a `check_*` function in `mcp/noctusai/tools/compliance.py` that has no matching `Test<CamelCase>` class in `mcp/noctusai/tests/` is itself a violation. See `KB § PATTERNS/testing.md § Regression-test-the-detector` for the pattern + worked examples.

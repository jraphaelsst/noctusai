# A startup hook is a side effect, not a precondition for serving

**Rule.** A product `lifespan_startup` hook must never be able to abort the
boot. It runs inside a `try` in `noctusai_seed.create_product_app`; a raise is
logged at ERROR with its traceback and parked on
`app.state.startup_hook_error`, which `/api/health` reports. The API comes up
either way.

**Why.** FastAPI propagates an exception out of the `lifespan` contextmanager,
uvicorn prints `Application startup failed. Exiting.`, and the process dies —
permanently, with no retry. So one transient upstream hiccup during the *first
few seconds* of a container's life is enough to take a product off the air
indefinitely, while the same code, in the same image, serves fine anywhere the
network happens to be healthy.

## How it presented (2026-08-10)

`erp-imobiliario` was `Up 6 days` on the dev fleet and answering nothing. Its
last log line was **13 days** old. Docker's status said `unhealthy`; the
uptime column said everything was fine. The trace:

```
app/main.py:39 in _startup
  → app/services/certidoes_service.py:1142 in recover_stuck_processando
    → httpx PostgREST call
      → httpx.ConnectError: [SSL: UNEXPECTED_EOF_WHILE_READING]
ERROR:    Application startup failed. Exiting.
```

`recover_stuck_processando` re-queues rows stranded in `processando`. It is
**maintenance**. Nothing about serving a request depends on it having run. Yet
its failure denied every request to a 60-router product.

Prod was healthy throughout — same commit, same image, healthier network. That
asymmetry is the tell for this whole bug class: **it only fires where the
upstream is flaky, which is never the environment you test in.**

## What the fix is NOT

It is not `except: pass`. The seed reports the failure three ways:

| surface | what it shows |
|---|---|
| container logs | `logger.exception` — ERROR + full traceback, naming the hook |
| `GET /api/health` | `startup_hook_error: "ConnectionError: PostgREST unreachable"` |
| clean boot | the same field, explicitly `null` |

The field is present-and-null on a healthy boot on purpose, so a consumer can
tell "no failure" from "an older seed that has no such field."

`/api/health` keeps returning **200** with `status: "ok"`. The container
healthcheck and the deploy probe both read it, and the API genuinely is
serving — flipping it to 503 would trade a silent outage for a loud one and
roll back good deploys. **Degradation is a field, not a status code.**

## The shutdown half

The same wrapper covers `lifespan_shutdown`, for a second reason: it runs in
the `finally` block *before* the framework's `shutdown_llm()`. An exception
there used to skip that cleanup and leak LLM provider pools on every shutdown
that had a flaky teardown.

## Applying this

- Anything a hook does — recovery sweeps, scheduling pending jobs, warming a
  cache, starting a scheduler — is a side effect. Write it so a failure is
  survivable, and let the seed's wrapper report it.
- A genuine precondition (a malformed setting, a missing secret) belongs in
  **config validation**, which is supposed to fail loud at boot, not in a
  lifespan hook.
- Reviewing a startup hook, ask: *if this raises, should the product refuse to
  exist?* For every hook in the fleet today the answer is no.
- Reading a "container up but serving nothing" report, check the **log
  recency**, not the uptime. Uptime measures the container; a dead uvicorn
  inside a live container keeps counting.

Tests: `seed/framework/backend/tests/test_lifespan_hooks.py` (sync + async
raise, the reported field, the ERROR log with traceback, and the shutdown
cleanup). Note the log test attaches its own handler rather than using
`caplog` — the seed's logging config does not propagate to root, so `caplog`
comes back empty while the ERROR is plainly printed.

→ `KB § PATTERNS/devops/containerization.md` · `KB § 03-SEED-ARCHITECTURE.md`

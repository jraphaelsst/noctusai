# Testing Standards

Every product must have three test layers. No product ships without all three.

| Layer | What it tests | Where | When to write |
|-------|---------------|-------|---------------|
| **Unit (routers)** | Individual endpoints — CRUD, auth, validation, error handling | `tests/routers/test_*.py` | One per domain router |
| **Unit (services)** | Business logic in isolation — calculations, transformations, state machines | `tests/services/test_*.py` | One per service with non-trivial logic |
| **Integration** | Cross-service flows — campaign references template + list, automation enrolls contacts | `tests/integration/test_*.py` | When entities reference each other |
| **E2E** | Full user journeys — create contact → template → campaign → send → verify stats | `tests/integration/test_e2e_flows.py` | One per product, covers the golden path |

## Rules

- **Unit tests:** mock the database (`MockSupabaseClient`). Test one endpoint at a time.
- **Integration tests:** mock the database but test multi-step flows where step N depends on step N-1.
- **E2E tests:** simulate a real user journey through multiple endpoints. Each test is a story.
- **Deterministic:** no hardcoded dates (use `date.today()` / `date.today() - timedelta(days=N)`), no external API calls, no network.
- **Auth boundary:** every product must verify that unauthenticated requests return 401 for all protected endpoints.

## Running

```bash
cd <product>/backend && pytest                  # all tests
cd <product>/backend && pytest tests/routers    # just router tests
cd <product>/backend && pytest -k test_contacts # by name
```

## Mock helpers

Import from the seed test kit:
```python
from tests.conftest import (
    MockSupabaseClient,
    MockSelectBuilder,
    MockUser,
    MockUserResponse,
    AuthClient,
)
```

Each product's `conftest.py` re-exports these from the shared seed test helpers. Don't re-implement mocks per product.

---

See also:
- `../06-AGENTS.md` — the MCP heal loop runs tests automatically
- `../../INSTRUCTIONS/05-TESTING-EVALS.md` — eval strategy (beyond unit/integration)

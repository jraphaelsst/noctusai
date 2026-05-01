"""Config — app configuration + secrets resolution.

**Layer contract.** See `KB § PATTERNS/seed-lib-layout.md § The 6 layers`.

**Active occupants:**
- `settings.py` — `ProductSettings` base + per-product extensions, lazy
  module-level singleton.
- `credentials.py` — `configure_credentials(...)`, `resolve_credential(...)`,
  `check_required_credentials(...)`. Reads from secrets store; cached
  per-request.

**Note on `_version.py` / `_version_static.py`.** These live at the seed-lib
root (NOT here) for bootstrap reasons — `scripts/stamp-seed-version.sh` and
`mcp/noctusai/tools/compliance.py::check_seed_version_propagation` both
hardcode the path. See `KB § PATTERNS/seed-lib-layout.md § What stays at
the top level`.

**Transitional re-exports.** Old code that did
`from noctusai_lib.config import ProductSettings` (because the old
top-level `config.py` exposed it directly) keeps working — this barrel
re-exports the public surface. Step 3 of the migration updates product
imports to the explicit `from noctusai_lib.config.settings import ...`
form, after which the re-exports drop.
"""
from noctusai_lib.config.settings import *  # noqa: F401, F403

"""The ONE place this module reads an API key. Deliberately one line deep.

🔴 WHY AN INDIRECTION RATHER THAN A DIRECT CALL AT EACH SITE
-------------------------------------------------------------
Everything in this module that needs a key needs it through here:
`registry._build_params_tjsp` (`infosimples_email_envio`), `service`
(`infosimples_token`, `openai_api_key`) and the pre-flight
`check_required_credentials`. The ERP original called
`noctusai_lib.config.credentials.resolve_credential` at each of those sites.

That indirection has now paid for itself exactly as intended. This module was
authored against `resolve_credential` while `feat/emissoes-api-keys` was still
in flight; adopting the product-local encrypted store afterwards was a change
to ONE function body, not a scatter-gather across two files and four call
sites — the kind where the site you miss reads from a different store than the
other three and produces "it works for the token but not the e-mail" rather
than an error.

WHAT IT RESOLVES THROUGH NOW
----------------------------
`app.services.api_keys_store.resolve_api_key` — two tiers, no silent fallback:

1. this product's Fernet-encrypted `social_wiring.credentials` rows, written
   from Settings → "Chaves de API" (per-org);
2. `noctusai_lib.config.credentials.resolve_credential` — the platform chain
   (`org_settings` → `platform_settings` → env), so a key configured for the
   org BEFORE that UI existed keeps working until it is re-entered there.

Which means the swap regressed nothing: an org that never opened the new
Settings page still resolves through tier 2, exactly as this module did before.

A miss returns `None`, and it stays the CALLER's job to raise its own 422 —
only the caller knows which workflow is blocked. `check_required_credentials`
below names the certidão workflow; the router appends the canonical pt-BR
"Configure em Configurações → Chaves de API." sentence that `matriculas` and
the settings router already use verbatim.

It is NOT a Protocol/Fake/Real seam. There is no second implementation to
select between at runtime, and a factory with one branch would be scaffolding
pretending to be a seam. Tests substitute
`app.modules.certidoes.credentials.resolve_api_key`.
"""
from __future__ import annotations

from typing import Optional

from app.services.api_keys_store import resolve_api_key

#: The credential names this module resolves. Named here rather than as string
#: literals at each call site so the key store can be checked against the
#: actual set this feature needs — all three are in
#: `api_keys_store.MANAGED_API_KEYS`, i.e. all three are settable in the UI.
INFOSIMPLES_TOKEN = "infosimples_token"
INFOSIMPLES_EMAIL_ENVIO = "infosimples_email_envio"
OPENAI_API_KEY = "openai_api_key"


def resolve_key(name: str, org_id: Optional[str] = None) -> Optional[str]:
    """Resolve one credential for an org. `None` when it is not configured.

    THE single credential-resolution point for `app/modules/certidoes/**` — see
    the module docstring. `None` is a miss, never an error; the caller raises
    the 422 that names the workflow.
    """
    return resolve_api_key(name, org_id)


__all__ = [
    "INFOSIMPLES_EMAIL_ENVIO",
    "INFOSIMPLES_TOKEN",
    "OPENAI_API_KEY",
    "resolve_key",
]

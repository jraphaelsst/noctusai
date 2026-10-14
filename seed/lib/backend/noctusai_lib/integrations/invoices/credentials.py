"""Per-company provider tokens, encrypted at rest.

Focus returns a token pair per company (`token_producao` / `token_homologacao`)
from `POST/PUT /v2/empresas`. Only the token of the CONFIGURED environment is
kept, in the seed `CredentialStore` (`noctusai_lib.security.token_store` -
Fernet via `security.encrypted_tokens`), keyed `(org_id,
"invoices_focusnfe:<company_ref>")`, with the environment and CNPJ as
non-secret metadata. A token read back for a different environment is REFUSED
(token-tier vs environment mismatch), and a CNPJ change rotates the row.
Tokens are never returned by any API: the only read path is `resolver_for`
(handed to the adapter); there is no public getter or listing.
"""
from __future__ import annotations

from typing import Callable, Optional

from noctusai_lib.security.token_store import CredentialStore

from .errors import InvoiceProviderError
from .types import InvoiceEnvironment

PROVIDER_PREFIX = "invoices_focusnfe:"


def _key(company_ref: str) -> str:
    return f"{PROVIDER_PREFIX}{company_ref}"


class CompanyTokenStore:
    def __init__(self, store: CredentialStore, *, environment: InvoiceEnvironment) -> None:
        self._store = store
        self._environment = environment

    def put(self, org_id: str, company_ref: str, cnpj: str, token: Optional[str]) -> bool:
        """Persist the company token. Returns True when an existing row
        for a DIFFERENT cnpj was replaced (rotation)."""
        if not token:
            raise InvoiceProviderError(
                "focusnfe", "token da empresa ausente", code="company_token_ausente"
            )
        existing = self._store.get(org_id, _key(company_ref))
        rotated = bool(existing and existing.metadata.get("cnpj") not in (None, cnpj))
        self._store.put(
            org_id,
            _key(company_ref),
            {"token": token},
            metadata={
                "environment": self._environment.value,
                "cnpj": cnpj,
                "company_ref": company_ref,
            },
        )
        return rotated

    def _get(self, org_id: str, company_ref: str) -> Optional[str]:
        stored = self._store.get(org_id, _key(company_ref))
        if stored is None:
            return None
        if stored.metadata.get("environment") != self._environment.value:
            raise InvoiceProviderError(
                "focusnfe",
                "token da empresa pertence a outro ambiente",
                code="token_environment_mismatch",
            )
        return stored.tokens.get("token") or None

    def delete(self, org_id: str, company_ref: str) -> bool:
        return self._store.delete(org_id, _key(company_ref))

    def resolver_for(self, org_id: str) -> Callable[[str], Optional[str]]:
        """A `company_ref -> token` callable scoped to one org, for the adapter."""
        return lambda company_ref: self._get(org_id, company_ref)

    def sink_for(self, org_id: str) -> Callable[[str, str, str], None]:
        """A `(company_ref, cnpj, token)` callable for the provider's `token_sink`:
        the token goes provider -> encrypted store without ever being returned."""

        def _sink(company_ref: str, cnpj: str, token: str) -> None:
            self.put(org_id, company_ref, cnpj, token)

        return _sink

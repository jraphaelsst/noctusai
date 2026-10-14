"""Per-company provider tokens, encrypted at rest.

Focus returns a token pair per company (`token_producao` / `token_homologacao`)
from `POST/PUT /v2/empresas`. Only the token of the CONFIGURED environment is
kept, in the seed `CredentialStore` (`noctusai_lib.security.token_store` -
Fernet via `security.encrypted_tokens`), keyed `(org_id,
"invoices_focusnfe:<company_ref>")`, with the environment and CNPJ as
non-secret metadata. A token read back for a different environment is REFUSED
(token-tier vs environment mismatch), and a CNPJ change rotates the row.
Tokens are never returned by any API: this class has no listing/exposure path.
"""
from __future__ import annotations

from typing import Callable, Optional

from noctusai_lib.security.token_store import CredentialStore

from .errors import InvoiceProviderError
from .types import InvoiceEnvironment, ProviderCompany

PROVIDER_PREFIX = "invoices_focusnfe:"


def _key(company_ref: str) -> str:
    return f"{PROVIDER_PREFIX}{company_ref}"


class CompanyTokenStore:
    def __init__(self, store: CredentialStore, *, environment: InvoiceEnvironment) -> None:
        self._store = store
        self._environment = environment

    def put(self, org_id: str, company: ProviderCompany) -> bool:
        """Persist `company.company_token`. Returns True when an existing row
        for a DIFFERENT cnpj was replaced (rotation)."""
        if not company.company_token:
            raise InvoiceProviderError(
                "focusnfe", "token da empresa ausente", code="company_token_ausente"
            )
        existing = self._store.get(org_id, _key(company.ref))
        rotated = bool(existing and existing.metadata.get("cnpj") not in (None, company.cnpj))
        self._store.put(
            org_id,
            _key(company.ref),
            {"token": company.company_token},
            metadata={
                "environment": self._environment.value,
                "cnpj": company.cnpj,
                "company_ref": company.ref,
            },
        )
        return rotated

    def get(self, org_id: str, company_ref: str) -> Optional[str]:
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
        return lambda company_ref: self.get(org_id, company_ref)

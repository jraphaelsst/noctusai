"""n8n public API v1 adapter — Protocol + Fake + Real + factory.

Public surface:
- ``N8nClient`` Protocol (async methods, all operations).
- ``FakeN8nClient`` — deterministic in-memory implementation for
  dev + tests. Seeds three workflows covering all three run-eligibility
  outcomes (webhook+active+not-archived / no-webhook / archived); one
  tag; one execution. Deterministic ids.
- ``HttpxN8nClient`` — real httpx-backed adapter (``X-N8N-API-KEY``
  header auth, instance-root base URL).
- ``get_n8n_client(base_url=None, api_key=None)`` — returns
  ``FakeN8nClient`` when ``api_key`` is absent/empty,
  ``HttpxN8nClient`` otherwise.
- Error hierarchy: ``N8nError`` → ``N8nAuthError`` /
  ``N8nNotFoundError`` / ``N8nRateLimitedError`` / ``N8nRejectedError``
  / ``N8nUnreachableError`` / ``N8nWorkflowNotRunnableError``.
- Value objects: ``Tag``, ``Workflow``, ``Execution``, ``Credential``,
  ``RunResult``.
- Pure helpers: ``normalize_base_url``, ``instance_root``,
  ``webhook_url``, ``sanitize_workflow_put_body``,
  ``WORKFLOW_PUT_ALLOWED_KEYS``, ``tag_refs_body``,
  ``extract_webhook_trigger``.

**Hard-won facts (measured live 2026-07-16) are carried by the code,
not by prose** — see the docstrings on ``types.N8nClient`` and on each
mapper in ``mappers.py`` for the full fact list (heavy list payload /
``isArchived`` default / webhook-only run / WAF User-Agent / PUT
sanitize / tag-ids-not-names / int-vs-str ids / no credentials
list-endpoint / projects 403).

See ``KB § PATTERNS/backend/seed-fake-real-adapter.md`` for the wiring
recipe — this module follows the **mailchimp** shape
(``__init__.py``/``types.py``/``mappers.py``/``fake_adapter.py``/
``n8n_adapter.py``), NOT ``integrations/youtube/``'s
``protocol.py``/``fake.py``/``real.py``/``factory.py`` layout, which is
off-pattern for this family of external-HTTP-per-tenant-API-key
adapters.
"""

from noctusai_lib.integrations.n8n.fake_adapter import FakeN8nClient
from noctusai_lib.integrations.n8n.mappers import (
    WORKFLOW_PUT_ALLOWED_KEYS,
    extract_webhook_trigger,
    instance_root,
    normalize_base_url,
    raw_to_credential,
    raw_to_execution,
    raw_to_tag,
    raw_to_workflow,
    sanitize_workflow_put_body,
    tag_refs_body,
    webhook_url,
)
from noctusai_lib.integrations.n8n.n8n_adapter import HttpxN8nClient
from noctusai_lib.integrations.n8n.types import (
    Credential,
    Execution,
    N8nAuthError,
    N8nClient,
    N8nError,
    N8nNotFoundError,
    N8nRateLimitedError,
    N8nRejectedError,
    N8nUnreachableError,
    N8nWorkflowNotRunnableError,
    RunResult,
    Tag,
    Workflow,
)


def get_n8n_client(
    base_url: str | None = None,
    api_key: str | None = None,
    *,
    timeout: float = 20.0,
) -> N8nClient:
    """Return a real ``HttpxN8nClient`` when both ``base_url`` and
    ``api_key`` are set; ``FakeN8nClient`` otherwise.

    Mirrors ``get_mailchimp_client()`` / ``get_whatsapp_client()`` per
    ``KB § PATTERNS/seed-fake-real-adapter.md`` — deferred-config: no
    credentials ⇒ Fake (so a caller boots + tests deterministically),
    a real ``base_url``/``api_key`` pair ⇒ the httpx-backed adapter.

    Usage::

        # Dev / test: no real credentials needed
        client = get_n8n_client()

        # Production: base_url + api_key resolved per-tenant
        client = get_n8n_client(base_url="https://n8n.example.com", api_key="...")
    """
    if not base_url or not api_key:
        return FakeN8nClient()
    return HttpxN8nClient(base_url, api_key, timeout=timeout)


__all__ = [
    # Factory
    "get_n8n_client",
    # Adapters
    "FakeN8nClient",
    "HttpxN8nClient",
    # Protocol
    "N8nClient",
    # Error hierarchy
    "N8nError",
    "N8nAuthError",
    "N8nNotFoundError",
    "N8nRateLimitedError",
    "N8nRejectedError",
    "N8nUnreachableError",
    "N8nWorkflowNotRunnableError",
    # Value objects
    "Tag",
    "Workflow",
    "Execution",
    "Credential",
    "RunResult",
    # Pure helpers
    "WORKFLOW_PUT_ALLOWED_KEYS",
    "normalize_base_url",
    "instance_root",
    "webhook_url",
    "sanitize_workflow_put_body",
    "tag_refs_body",
    "extract_webhook_trigger",
    "raw_to_tag",
    "raw_to_workflow",
    "raw_to_execution",
    "raw_to_credential",
]

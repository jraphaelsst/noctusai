"""Provider credential + credit probe — "is this key usable RIGHT NOW?".

WHY A SEED ORGAN
────────────────
An HTTP 429 from OpenAI is two opposite problems: "out of credit" (someone
must pay; retrying never helps) and "too many requests" (waiting is the
fix). The marker list that tells them apart already existed twice —
`integrations/documents/transcription._classify_failure` and social-wiring's
settings key tester — and edicao-fotos W8's processing panel would have been
the third copy (`CLAUDE.md` §1 DRY: N=3 ⇒ formalize). This is that copy's
home; the two earlier sites now import `QUOTA_MARKERS` from here instead of
hand-maintaining their own tuple (2026-09-16). Both still run their OWN HTTP
call + status-code ladder (their surrounding control flow is genuinely
product-specific — one classifies from a bare exception's text with no
status code at all, the other builds vendor-specific PT-BR messages) — only
the marker LIST itself was the literal duplicate; migrating the full call to
`OpenAICreditProbe`/`classify_provider_failure` is future work once those
call sites gain an httpx-client injection seam + test coverage of their own
(see `KB § INTEGRATIONS/image-edit.md`).

SHAPE — Protocol + Fake + Real + factory
────────────────────────────────────────
- :func:`classify_provider_failure` — pure: (HTTP status, body text) →
  :data:`ProbeStatus`.
- :class:`CreditProbe` Protocol → :class:`FakeCreditProbe` (scripted) and
  :class:`OpenAICreditProbe` (one `max_tokens=1` chat completion — a probe
  that does not spend cannot see "no credit", because listing models works
  on an unpaid account). The `httpx.AsyncClient` is constructor-injected
  (`httpx.MockTransport` in tests).
- :func:`make_credit_probe`.

A probe COSTS a fraction of a cent: run it on an operator's click, never on
a timer or a page load.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Literal, Optional, Protocol, runtime_checkable

ProbeStatus = Literal["ok", "sem_credito", "chave_invalida", "sem_chave", "limite", "erro"]

#: Body markers meaning "the account has no credit" — per vendor, and they
#: MUST grow with the provider list (see transcription.py's 2026-09-04 note).
QUOTA_MARKERS: tuple[str, ...] = (
    # OpenAI
    "insufficient_quota",
    "credit_balance_exhausted",
    "no credits remaining",
    "exceeded your current quota",
    # Anthropic
    "credit_balance_too_low",
    "credit balance is too low",
)

MESSAGES: dict[str, str] = {
    "ok": "Chave válida e com créditos.",
    "sem_credito": (
        "Sem créditos na conta. A chave é válida, mas a conta não tem saldo — "
        "adicione créditos no painel de cobrança do provedor."
    ),
    "chave_invalida": "Chave inválida ou expirada.",
    "sem_chave": "Nenhuma chave configurada.",
    "limite": "Limite de requisições atingido — aguarde alguns minutos e teste de novo.",
    "erro": "Erro inesperado ao consultar o provedor.",
}


def classify_provider_failure(http_status: Optional[int], body: str) -> ProbeStatus:
    """The one classifier. Quota markers win over the status code (OpenAI
    says 429, Anthropic 400 — both mean "pay the bill")."""
    text = (body or "").lower()
    if any(marker in text for marker in QUOTA_MARKERS):
        return "sem_credito"
    if http_status in (401, 403) or "invalid_api_key" in text or "incorrect api key" in text:
        return "chave_invalida"
    if http_status == 429 or "rate_limit" in text:
        return "limite"
    if http_status is not None and 200 <= http_status < 300:
        return "ok"
    return "erro"


@dataclass(frozen=True)
class CreditProbeResult:
    status: ProbeStatus
    message: str
    checked_at: datetime
    provider: str
    model: Optional[str] = None
    http_status: Optional[int] = None

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@runtime_checkable
class CreditProbe(Protocol):
    provider: str

    async def probe(self, api_key: Optional[str]) -> CreditProbeResult: ...


class FakeCreditProbe:
    """Scripted probe: answers ``status`` for every key (``sem_chave`` for a
    missing one, like the real probe). Records the keys it was asked about."""

    def __init__(
        self,
        status: ProbeStatus = "ok",
        *,
        provider: str = "openai",
        now: Callable[[], datetime] = _utcnow,
    ) -> None:
        self.status: ProbeStatus = status
        self.provider = provider
        self._now = now
        self.calls: list[Optional[str]] = []

    async def probe(self, api_key: Optional[str]) -> CreditProbeResult:
        self.calls.append(api_key)
        status: ProbeStatus = self.status if api_key else "sem_chave"
        return CreditProbeResult(
            status=status, message=MESSAGES[status], checked_at=self._now(), provider=self.provider
        )


class OpenAICreditProbe:
    provider = "openai"
    URL = "https://api.openai.com/v1/chat/completions"

    def __init__(
        self,
        *,
        http_client: Any = None,
        model: str = "gpt-4o-mini",
        timeout_seconds: float = 20.0,
        now: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._http = http_client
        self._model = model
        self._timeout = timeout_seconds
        self._now = now

    def _result(self, status: ProbeStatus, http_status: Optional[int], detail: str = "") -> CreditProbeResult:
        message = MESSAGES[status] if not detail else f"{MESSAGES[status]} ({detail})"
        return CreditProbeResult(
            status=status,
            message=message,
            checked_at=self._now(),
            provider=self.provider,
            model=self._model,
            http_status=http_status,
        )

    async def probe(self, api_key: Optional[str]) -> CreditProbeResult:
        if not api_key:
            return self._result("sem_chave", None)
        import httpx

        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 1,
        }
        headers = {"Authorization": f"Bearer {api_key}"}
        try:
            if self._http is not None:
                resp = await self._http.post(self.URL, headers=headers, json=payload, timeout=self._timeout)
            else:
                async with httpx.AsyncClient() as http:
                    resp = await http.post(self.URL, headers=headers, json=payload, timeout=self._timeout)
        except httpx.HTTPError as exc:
            return self._result("erro", None, f"conexão: {type(exc).__name__}")
        status = classify_provider_failure(resp.status_code, resp.text)
        detail = f"HTTP {resp.status_code}" if status == "erro" else ""
        return self._result(status, resp.status_code, detail)


def make_credit_probe(
    provider: str = "openai", *, use_fake: bool = False, http_client: Any = None, model: Optional[str] = None
) -> CreditProbe:
    if use_fake:
        return FakeCreditProbe(provider=provider)
    if provider != "openai":
        raise ValueError(f"no credit probe for provider {provider!r}")
    return OpenAICreditProbe(http_client=http_client, **({"model": model} if model else {}))


__all__ = [
    "CreditProbe",
    "CreditProbeResult",
    "FakeCreditProbe",
    "MESSAGES",
    "OpenAICreditProbe",
    "ProbeStatus",
    "QUOTA_MARKERS",
    "classify_provider_failure",
    "make_credit_probe",
]

"""Channel publishers — Módulo 5.

Protocol + Fake + Real + factory, the same shape as the seed's IO modules
(`KB § PATTERNS/backend/seed-fake-real-adapter.md`).

**Why this lives in the PRODUCT and not the seed.** noc ships
`noctusai_lib.integrations.meta`, but it is ads/leadgen-shaped (AdAccount,
AdCampaign, lead webhooks) — it does not publish organic posts, and there is
nothing for TikTok or LinkedIn. IgIg is the first consumer of a multi-channel
organic publisher, so per the recurrence rule this stays here at N=1. **When a
second product needs it, promote this module to
`noctusai_lib/integrations/social_publishing/` rather than copying it** — that
is the N=2 trigger, and this note is the reminder.

**What is and is not real today.** The scheduling machinery, the queue, the
retry accounting and the status transitions are real and exercised. The
network calls are NOT: no channel has a homologated vendor integration yet
(`NOC-REMEDIATE[igig-publishing]`), so the real adapters raise
`CanalNaoHomologado` rather than pretending to succeed.

**No production path reaches `FakePublisher`.** `get_publisher` never
constructs it: a channel with no usable token refuses with
`CanalNaoConfigurado` BEFORE any publisher is built. This is a change from the
module's earlier shape — `get_publisher` used to fall back to the Fake on a
missing token, which meant a mis-configured deployment (or a rotated vault key
degrading a real token to "absent") silently reported `publicada` for a post
nobody sent. `FakePublisher` still exists for tests, wired in explicitly via
`monkeypatch.setattr(<router module>, "get_publisher", ...)` — the DI-override
seam this codebase already uses for external-boundary clients (see
`KB § PATTERNS/backend/di-test-seam.md`).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol, runtime_checkable

from noctusai_lib.integrations.persistence import iter_paged_rows

from app.repositories import Repositorios

logger = logging.getLogger(__name__)

__all__ = [
    "CANAIS",
    "CANAIS_HOMOLOGADOS",
    "STUCK_APOS_MINUTOS",
    "PublishResult",
    "ChannelPublisher",
    "FakePublisher",
    "MetaPublisher",
    "TikTokPublisher",
    "LinkedInPublisher",
    "PublisherNotConfigured",
    "CanalNaoConfigurado",
    "CredencialIlegivel",
    "CanalNaoHomologado",
    "get_publisher",
    "resolver_token",
    "processar_fila_publicacao",
    "orgs_com_publicacao_pendente",
    "liberar_travadas",
]

#: Mirrors the DB CHECK on `publicacao.canal`.
CANAIS: tuple[str, ...] = ("instagram", "facebook", "tiktok", "linkedin")

#: Channels with a REAL, homologated vendor integration behind them. Empty
#: until `NOC-REMEDIATE[igig-publishing]` ships a first real adapter — the
#: queue worker (`processar_fila_publicacao`) only attempts channels in this
#: set; every other channel would fail every single tick with the same
#: "ainda não homologada" message, which is pure log noise, not a finding.
CANAIS_HOMOLOGADOS: frozenset[str] = frozenset()

#: A row claimed (`status → 'publicando'`) longer than this without landing
#: `publicada`/`falhou` is presumed orphaned by a crashed worker — see
#: :func:`liberar_travadas`.
STUCK_APOS_MINUTOS = 15


class PublisherNotConfigured(RuntimeError):
    """Base: the channel cannot be published to as requested right now.

    Distinguishing subclasses exist because the operator's correct next
    action differs by cause — "connect a token" is not "reconnect a broken
    one" is not "wait for us to finish the integration". Callers should catch
    the SPECIFIC subclass they know how to react to before falling back to
    this base.
    """


class CanalNaoConfigurado(PublisherNotConfigured):
    """No usable token anywhere — neither an org credential nor the env
    fallback. `get_publisher` raises this BEFORE constructing any publisher;
    it is never silently swapped for a Fake in production."""


class CredencialIlegivel(PublisherNotConfigured):
    """A token IS stored, but it could not be decrypted (the vault key
    rotated, or the ciphertext is corrupted). Distinct from
    `CanalNaoConfigurado`: reconnecting the channel genuinely fixes this one,
    so callers should record it on the integration (`ultimo_erro`) — unlike
    `CanalNaoHomologado`, below."""


class CanalNaoHomologado(PublisherNotConfigured):
    """A token exists and the real adapter exists, but the vendor's API
    review/homologation is still pending (`NOC-REMEDIATE[igig-publishing]`).
    Reconnecting the channel does NOT help — callers must NOT record this as
    a credential failure (`ultimo_erro`), or the setup screen tells the
    operator to do something that cannot fix it."""


@dataclass(frozen=True, slots=True)
class PublishResult:
    """What a successful publish returns.

    `external_id` is required: without the platform's own post id there is no
    way to fetch metrics later, so a publisher that cannot supply one has not
    really succeeded.
    """

    external_id: str
    permalink: str | None = None


@runtime_checkable
class ChannelPublisher(Protocol):
    """Surface every channel publisher implements."""

    canal: str

    def publicar(
        self,
        *,
        texto: str,
        midia_urls: list[str],
        legenda_extra: str | None = None,
    ) -> PublishResult:
        ...


class FakePublisher:
    """Deterministic in-memory publisher — TEST-ONLY.

    `get_publisher` never constructs this class; nothing in the production
    call graph can reach it. Tests wire it in explicitly (monkeypatch the
    caller's `get_publisher` reference), and record every call on `enviados`
    so an assertion can check what WOULD have gone out.
    """

    def __init__(self, canal: str = "instagram") -> None:
        self.canal = canal
        self.enviados: list[dict] = []

    def publicar(
        self,
        *,
        texto: str,
        midia_urls: list[str],
        legenda_extra: str | None = None,
    ) -> PublishResult:
        self.enviados.append(
            {"texto": texto, "midia_urls": list(midia_urls), "legenda_extra": legenda_extra}
        )
        indice = len(self.enviados)
        return PublishResult(
            external_id=f"fake-{self.canal}-{indice}",
            permalink=f"https://example.test/{self.canal}/{indice}",
        )


class _RealPublisherBase:
    """Shared shape for the credentialed publishers."""

    canal: str = ""

    def __init__(self, token: str) -> None:
        self._token = token

    def publicar(
        self,
        *,
        texto: str,
        midia_urls: list[str],
        legenda_extra: str | None = None,
    ) -> PublishResult:
        # NOC-REMEDIATE[igig-publishing]: real API call pending app review /
        # homologation on the vendor's side. `get_publisher` never constructs
        # this class without a token (see below), so reaching this line means
        # the VENDOR CALL, not the credential, is the pending piece — hence
        # `CanalNaoHomologado`, not a credential exception. Deliberately
        # raises rather than returning a fabricated external_id: marking a
        # post 'publicada' that no client ever saw is worse than failing
        # loudly. — 2026-08-09, revised 2026-09-28.
        raise CanalNaoHomologado(
            f"A integração com {self.canal} ainda não está disponível "
            "(homologação da API pendente)."
        )


class MetaPublisher(_RealPublisherBase):
    """Instagram / Facebook via the Meta Graph API."""

    def __init__(self, canal: str = "instagram", token: str = "") -> None:
        super().__init__(token)
        self.canal = canal


class TikTokPublisher(_RealPublisherBase):
    canal = "tiktok"


class LinkedInPublisher(_RealPublisherBase):
    canal = "linkedin"


def get_publisher(canal: str, *, token: str | None = None) -> ChannelPublisher:
    """Return the REAL publisher for a channel. Never the Fake.

    Raises `CanalNaoConfigurado` when there is nothing to try with, so a
    caller can never reach a network client with an empty token. Both
    production callers (`executar_publicacao`, `processar_fila_publicacao`)
    already refuse before calling this when `token` is falsy — the check here
    is defense-in-depth, not the primary gate.
    """
    if canal not in CANAIS:
        raise ValueError(f"canal inválido: {canal!r}; esperado um de {CANAIS}")
    if not token:
        raise CanalNaoConfigurado(f"Canal {canal} não está configurado.")
    if canal in ("instagram", "facebook"):
        return MetaPublisher(canal, token)
    if canal == "tiktok":
        return TikTokPublisher(token)
    return LinkedInPublisher(token)


def resolver_token(repos: Repositorios, org_id: str, canal: str, cfg: Any) -> str | None:
    """The token to publish with: per-org credential first, env fallback
    second. ``None`` is a normal, expected outcome — the caller turns it into
    `CanalNaoConfigurado` (never a Fake).

    `cfg` is the settings instance resolved through FastAPI's `get_settings`
    dependency, not the module-level singleton — the same Class-A DI seam
    `integracoes_router` already uses (`app/config.py`'s own docstring: tests
    override `get_settings`, they do not patch the singleton). Reading the
    singleton directly here — as this function used to — meant a per-request
    settings override in a test never reached this call, and the module-level
    default silently won instead.

    A token that IS stored but cannot be decrypted raises
    `CredencialIlegivel` instead of silently degrading to "not configured":
    with a rotated `IGIG_COFRE_KEY`, every publish used to fall back to the
    Fake and report success — an operator needs to reconnect, not think the
    channel was never set up.
    """
    if cfg.igig_cofre_key:
        try:
            token = repos.integracao.token_de(org_id, canal, cfg.igig_cofre_key.encode("utf-8"))
        except ValueError as exc:
            logger.warning("token de %s ilegível para org=%s", canal, org_id)
            raise CredencialIlegivel(
                f"O token salvo para {canal} não pôde ser lido. Reconecte o canal."
            ) from exc
        if token:
            return token
    if canal in ("instagram", "facebook"):
        return cfg.igig_meta_token or None
    if canal == "tiktok":
        return cfg.igig_tiktok_token or None
    return cfg.igig_linkedin_token or None


async def processar_fila_publicacao(
    repos: Repositorios, org_id: str, cfg: Any, *, agora: datetime | None = None
) -> dict:
    """Drain the due-publication queue for ONE org.

    `cfg` is the same settings instance `executar_publicacao` resolves via
    `get_settings` — pass `app.config.settings` (the real singleton) from the
    scheduler wiring; a test passes whatever `cfg` fixture it built.

    This is the worker `GET /api/distribuicao/fila`'s docstring always
    described and nothing ran: nothing auto-publishes when a scheduled time
    arrives (finding #8 / #13, 2026-09 audit). Per-org by design — every
    other repository call in this product is org-scoped, and a cross-org
    sweep needs the raw service-role client (see the module-level note in
    `app/scheduler.py` and `automacoes.varrer_sla` for that shape); the
    caller loops over every org and calls this once each.

    Only attempts a channel in `CANAIS_HOMOLOGADOS`; everything else is
    SKIPPED (never stamped as a failure — a channel nobody has tried yet is a
    different state from one whose credential broke).

    `publicando` is the in-flight claim: set BEFORE the publish attempt, so a
    slow publish overlapping the next tick sees the row already claimed
    (its `status` is no longer `agendada`, so it drops out of `pendentes`)
    instead of being picked up twice.

    On success: marks the row `publicada` AND writes `pauta.publicado_em` —
    the field the guide always documented as existing and nothing ever wrote
    (finding #10).
    """
    momento = agora or datetime.now(timezone.utc)
    resumo = {"processadas": 0, "publicadas": 0, "falharam": 0, "ignoradas": 0}

    for publicacao in repos.publicacao.pendentes(org_id, momento.isoformat()):
        canal = str(publicacao["canal"])
        publicacao_id = str(publicacao["id"])
        if canal not in CANAIS_HOMOLOGADOS:
            resumo["ignoradas"] += 1
            continue

        # Claim the row before doing any network work — see docstring.
        repos.publicacao.atualizar(org_id, publicacao_id, {"status": "publicando"})
        resumo["processadas"] += 1

        pauta = repos.pauta.buscar(org_id, str(publicacao["pauta_id"]))
        pecas = repos.peca.da_pauta(org_id, str(pauta["id"]))

        try:
            token = resolver_token(repos, org_id, canal, cfg)
            if not token:
                raise CanalNaoConfigurado(f"Canal {canal} não está configurado.")
            resultado = get_publisher(canal, token=token).publicar(
                texto=str(pauta.get("copy_texto") or ""),
                midia_urls=[str(p["storage_key"]) for p in pecas],
            )
        except Exception as exc:  # noqa: BLE001 — every failure path is the
            # same: record it and never report success (see
            # `distribuicao_router.executar_publicacao`'s identical contract).
            repos.publicacao.marcar_falha(org_id, publicacao_id, str(exc))
            if isinstance(exc, PublisherNotConfigured) and not isinstance(exc, CanalNaoHomologado):
                repos.integracao.registrar_erro(org_id, canal, str(exc))
            logger.warning(
                "fila: publicação falhou org=%s id=%s: %s", org_id, publicacao_id, exc
            )
            resumo["falharam"] += 1
            continue

        repos.publicacao.marcar_publicada(
            org_id, publicacao_id,
            external_id=resultado.external_id, permalink=resultado.permalink,
        )
        repos.pauta.atualizar(org_id, str(pauta["id"]), {"publicado_em": momento.isoformat()})
        logger.info(
            "fila: publicada org=%s id=%s external=%s", org_id, publicacao_id, resultado.external_id
        )
        resumo["publicadas"] += 1

    return resumo


def orgs_com_publicacao_pendente(db: Any, ate: str) -> list[str]:
    """Every org with at least one `agendada` publicação due by `ate` — the
    scheduler's per-org fan-out list for :func:`processar_fila_publicacao`.

    `Repositorios`/`RecordStore` require an `org_id` on every call by
    construction (the module docstring's cross-org note), so this cross-org
    DISCOVERY step reads the raw service-role client directly — the same
    shape `financeiro_service.atualizar_inadimplencia` and
    `email.iter_todos_watches` use for their own daily sweeps.
    """
    orgs: set[str] = set()
    for linha in iter_paged_rows(
        lambda inicio, fim: (
            db.table("publicacao").select("id,org_id")
            .eq("status", "agendada").lte("agendada_para", ate)
            .order("id").range(inicio, fim).execute().data
        ),
        label="igig.publicacao pendentes (fan-out)",
    ):
        orgs.add(str(linha["org_id"]))
    return sorted(orgs)


def liberar_travadas(db: Any, *, agora: datetime | None = None,
                      minutos: int = STUCK_APOS_MINUTOS) -> int:
    """Return publicações stuck in `publicando` for more than `minutos` back
    to `agendada` — the worker's own crash recovery.

    `processar_fila_publicacao` claims a row (`status → 'publicando'`)
    BEFORE the network call, on purpose (see its docstring): a slow publish
    must not be picked up twice by an overlapping tick. But nothing ever
    un-claimed a row whose worker process died mid-publish (a deploy, an
    OOM kill, a crash) — that publicação stayed `publicando` forever,
    invisible to `pendentes()` and to any operator not reading logs. Cross-
    org, same admin-client shape as every other sweep in this module;
    `publicacao.updated_at` is bumped by the DB trigger on the CLAIM update
    itself, so it is exactly "how long has this been claimed".
    """
    momento = agora or datetime.now(timezone.utc)
    limite = (momento - timedelta(minutes=minutos)).isoformat()
    travadas = (
        db.table("publicacao").select("id,org_id")
        .eq("status", "publicando").lt("updated_at", limite)
        .execute().data or []
    )
    for linha in travadas:
        db.table("publicacao").update({
            "status": "agendada", "erro": "tentativa interrompida",
        }).eq("id", linha["id"]).eq("org_id", linha["org_id"]).execute()
    if travadas:
        logger.warning(
            "fila: %d publicação(ões) travada(s) em 'publicando' recuperada(s)", len(travadas)
        )
    return len(travadas)

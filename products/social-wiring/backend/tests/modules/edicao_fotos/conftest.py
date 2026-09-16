"""Harness for the `edicao_fotos` module tests.

Every external edge is replaced through the module's OWN DI seams
(`app.dependency_overrides`), never by patching our code
(`KB § PATTERNS/backend/di-test-seam.md`):

- `get_current_user_org` → the identity the test selected with `as_user`;
- `get_role_resolver`    → trusted roles per user (no `noctus_users` read);
- `get_edicao_ports`     → the seed engine on in-memory/fake ports
  (UUID-minting repo, fake jobs, two `BucketPhotoStorage`s — batch photos
  and the reference pool — over the seed `FakeStorageBackend`, fake imaging / image-edit / fx, scripted LLM,
  recording notifier);
- `get_grant_repository` → the seed `FakePermissionGrantRepository`;
- `get_vista_photo_source` → `FakeVistaSource`;
- `get_user_directory`   → a dict.

The pipeline itself runs for real: `drain()` drives the seed `Worker` over
the same ports the routes use.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from noctusai_lib.domain.jobs import FakeJobRepository
from noctusai_lib.domain.permissions import FakePermissionGrantRepository
from noctusai_lib.domain.photo_editing import (
    BucketPhotoStorage,
    EditType,
    FakeStructuredLlm,
    InMemoryPhotoEditingRepository,
    OrgSettings,
    PhotoEditingConfig,
    PhotoEditingPorts,
    RecordingNotifier,
    activate_version,
    build_worker,
    create_draft,
)
from noctusai_lib.domain.photo_editing.types import AGENCY_ADMIN_ROLES
from noctusai_lib.domain.real_estate.imovel import ImovelFoto
from noctusai_lib.integrations.fx import FakeFxRateAdapter
from noctusai_lib.integrations.image_edit import FakeImageEditAdapter, ImageEditCapabilities
from noctusai_lib.integrations.imaging import FakeImagingAdapter
from noctusai_lib.integrations.storage import FakeStorageBackend

from app.dependencies import coerce_org_uuid, get_current_user_org
from app.modules.edicao_fotos.deps import (
    RoleInfo,
    get_edicao_ports,
    get_grant_repository,
    get_painel_client,
    get_preferences_repository,
    get_role_resolver,
    get_vista_photo_source,
)
from app.modules.edicao_fotos.routers.curadores import get_user_directory
from app.modules.edicao_fotos.services.notificacoes_preferencias import (
    InMemoryNotificationPreferencesRepository,
)
from app.modules.edicao_fotos.services.vista_fotos import VistaFotoDownloadError

ORG_RAW = "test-org-123"
ORG = str(coerce_org_uuid(ORG_RAW))
OTHER_ORG = "00000000-0000-4000-8000-00000000b0b0"
EDIT_MODEL = "gpt-image-2.5-sunburst"
JPEG = b"\xff\xd8\xff\xe0" + b"fake-jpeg-bytes"


@dataclass(frozen=True)
class TestUser:
    __test__ = False  # not a pytest test class

    id: str
    org: str
    roles: RoleInfo
    nome: str


USERS: dict[str, TestUser] = {
    "admin": TestUser("00000000-0000-4000-8000-0000000000a1", ORG, RoleInfo("owner", False), "Ana Admin"),
    "gerente": TestUser("00000000-0000-4000-8000-0000000000a7", ORG, RoleInfo("manager", False), "Gil Gerente"),
    "corretor": TestUser("00000000-0000-4000-8000-0000000000a2", ORG, RoleInfo("member", False), "Caio Corretor"),
    "corretor2": TestUser("00000000-0000-4000-8000-0000000000a3", ORG, RoleInfo("corretor", False), "Clara Corretora"),
    "viewer": TestUser("00000000-0000-4000-8000-0000000000a4", ORG, RoleInfo("viewer", False), "Vera Viewer"),
    "plataforma": TestUser("00000000-0000-4000-8000-0000000000a5", ORG, RoleInfo("member", True), "Paulo Plataforma"),
    "curador": TestUser("00000000-0000-4000-8000-0000000000a6", ORG, RoleInfo("viewer", False), "Cris Curadora"),
    "outra_admin": TestUser("00000000-0000-4000-8000-0000000000b1", OTHER_ORG, RoleInfo("owner", False), "Otto Outra"),
}


def good_evaluation(_call: dict | None = None) -> dict:
    return {
        "recomendacao": "aprovar",
        "score": 8.5,
        "motivo": "Cores naturais.",
        "fidelidade_estrutural": True,
    }


class FakeVistaSource:
    """`VistaPhotoSource` double: a gallery per código + bytes per URL."""

    def __init__(self) -> None:
        self.galleries: dict[str, list[ImovelFoto]] = {}
        self.bytes_by_url: dict[str, bytes] = {}
        self.failing_urls: set[str] = set()
        self.fetched: list[str] = []

    async def list_photos(self, codigo: str) -> list[ImovelFoto]:
        return list(self.galleries.get(codigo, []))

    async def fetch(self, url: str) -> tuple[bytes, str]:
        self.fetched.append(url)
        if url in self.failing_urls:
            raise VistaFotoDownloadError("HTTP 404")
        return self.bytes_by_url.get(url, JPEG), "jpg"


@dataclass
class Harness:
    http: Any
    app: Any
    ports: PhotoEditingPorts
    repo: InMemoryPhotoEditingRepository
    backend: FakeStorageBackend
    grants: FakePermissionGrantRepository
    vista: FakeVistaSource
    notifier: RecordingNotifier
    preferences: "InMemoryNotificationPreferencesRepository"
    directory: dict[str, dict] = field(default_factory=dict)
    current: TestUser = USERS["admin"]

    def as_user(self, name: str) -> "Harness":
        self.current = USERS[name]
        return self

    def run(self, coro: Any) -> Any:
        return asyncio.run(coro)

    def llm_calls(self) -> list[dict]:
        """Every structured-LLM call the engine made (the scripted fake records them)."""
        return self.ports.llm.calls

    # --- arrangement --------------------------------------------------
    def configure_org(self, org: str = ORG, **changes: Any) -> None:
        base = OrgSettings(
            org_id=org,
            tipos_edicao_ativos=(EditType.COR_LUZ, EditType.CEU),
            modelo_editor_id=EDIT_MODEL,
        )
        self.repo.seed_org_settings(OrgSettings(**{**base.__dict__, **changes}))

    def enable_economico(self, *, pending_polls: int = 0) -> None:
        """Declare EDIT_MODEL batch-capable on BOTH gates the engine reads —
        the ports' capability lookup and the Fake adapter — since the static
        catalog has no batch-capable image model (PROJECT.md C8). One shared
        Fake per model, so a batch submitted by one job is polled by the next."""
        import dataclasses

        adapters: dict[str, FakeImageEditAdapter] = {}

        def factory(_org: str, model: str) -> FakeImageEditAdapter:
            if model not in adapters:
                adapters[model] = FakeImageEditAdapter(
                    model=model, batch_models={EDIT_MODEL}, batch_pending_polls=pending_polls
                )
            return adapters[model]

        def capabilities(model: str) -> ImageEditCapabilities:
            return ImageEditCapabilities(
                model=model, supports_batch=model == EDIT_MODEL, known=model == EDIT_MODEL
            )

        # The engine schedules polls `ports.clock() + 5 min`; the fake job
        # queue claims against the wall clock, so pin the engine clock to a
        # past instant (the day the fake PTAX covers) to make polls due now.
        pinned = datetime(2026, 9, 16, 15, 0, tzinfo=timezone.utc)
        self.ports = dataclasses.replace(
            self.ports, image_edit=factory, capabilities=capabilities, clock=lambda: pinned
        )
        self.batch_adapters = adapters

    def activate_guide(self) -> None:
        async def _go() -> None:
            draft = await create_draft(
                self.ports, texto="- Luz natural", gerado_de_versao=None, criado_por=USERS["plataforma"].id
            )
            await activate_version(self.ports, draft.versao, ativado_por=USERS["plataforma"].id)

        self.run(_go())

    def make_batch(self, owner: str = "corretor", *, nome: str = "Apto 12") -> str:
        user = USERS[owner]

        async def _go() -> str:
            from noctusai_lib.domain.photo_editing import Speed

            batch = await self.repo.create_batch(
                org_id=user.org, nome=nome, criado_por=user.id, origem="upload", velocidade=Speed.URGENTE
            )
            return batch.id

        return self.run(_go())

    def add_photo(self, lote_id: str) -> str:
        from noctusai_lib.domain.photo_editing import add_photo_bytes

        return self.run(add_photo_bytes(self.ports, lote_id=lote_id, data=JPEG, extension="jpg")).id

    def drain(self, limit: int = 500) -> int:
        worker = build_worker(self.ports, worker_id="test-worker", poll_interval_seconds=0.0)

        async def _go() -> int:
            n = 0
            while n < limit and await worker.run_once():
                n += 1
            return n

        return self.run(_go())

    def upload_referencia(self, *, comodo: str = "sala", tipos: tuple[str, ...] = ("ceu",),
                          nota: str | None = "céu limpo", antes: bytes = JPEG, depois: bytes = JPEG):
        data: dict[str, Any] = {"comodo": comodo, "tipos_edicao": list(tipos)}
        if nota is not None:
            data["nota"] = nota
        return self.http.post(
            "/api/edicao-fotos/referencias",
            data=data,
            files=[
                ("antes", ("antes.jpg", antes, "image/jpeg")),
                ("depois", ("depois.jpg", depois, "image/jpeg")),
            ],
        )

    def upload(self, lote_id: str, count: int = 1, *, name: str = "foto.jpg", data: bytes = JPEG):
        files = [("fotos", (f"{i}-{name}", data, "image/jpeg")) for i in range(count)]
        return self.http.post(f"/api/edicao-fotos/lotes/{lote_id}/fotos", files=files)


# --- W9: `fotos_painel` RPC simulator (migration 133) -----------------
#
# Same shape as `tests/modules/leads/conftest.py::_install_rpc_simulator`
# (see that module's docstring for why): the SQL function is not
# runnable against `InMemoryPhotoEditingRepository`, so this is a
# line-for-line Python re-derivation of `133_fotos_painel.sql`'s
# aggregation, read directly off the SAME in-memory ports the routes use
# — not a separate fixture dataset. Raises loudly (AssertionError) for
# any RPC name it doesn't recognize.


_JOB_STATUSES = ("pending", "running", "completed", "failed", "dead_letter")
_FOTO_STATUSES = (
    "recebida", "normalizando", "pronta", "editando", "em_lote_openai",
    "editada", "avaliando", "aguardando_decisao", "aprovada", "rejeitada", "falhou",
)
_DECISAO_VALUES = ("aprovar", "rejeitar")


def _zero_filled(domain: tuple, counts: dict) -> dict:
    """Same exhaustive-map shape `133_fotos_painel.sql` returns — every
    key present, `0` default, never a sparse map."""
    return {k: counts.get(k, 0) for k in domain}


def _simulate_fotos_painel(harness: "Harness", params: dict) -> dict:
    org_id = params.get("p_org_id")
    p_desde, p_ate = params.get("p_desde"), params.get("p_ate")
    hoje = date.today()
    desde = date.fromisoformat(p_desde) if p_desde else hoje - timedelta(days=30)
    ate = date.fromisoformat(p_ate) if p_ate else hoje

    def _v(x: Any) -> Any:
        return getattr(x, "value", x)

    def _in_org(x_org: str) -> bool:
        return org_id is None or x_org == org_id

    def _in_window(dt: Any) -> bool:
        return dt is not None and desde <= dt.date() <= ate

    repo = harness.repo
    jobs = getattr(harness.ports.jobs, "_jobs", {})

    # 1. pipeline
    buckets: dict[tuple, int] = {}
    for e in repo.events:
        if e.estado_para is None:
            continue
        if not (_in_org(e.org_id) and _in_window(e.created_at)):
            continue
        key = (e.created_at.date().isoformat(), e.estado_para)
        buckets[key] = buckets.get(key, 0) + 1
    pontos = [{"data": d, "estado": estado, "total": t} for (d, estado), t in sorted(buckets.items())]

    # 2. fila (platform-wide, jobs carry no org_id)
    job_counts: dict[str, int] = {}
    travados = 0
    now = datetime.now(timezone.utc)
    for j in jobs.values():
        if not getattr(j, "type", "").startswith("fotos."):
            continue
        status = _v(j.status)
        job_counts[status] = job_counts.get(status, 0) + 1
        lease = getattr(j, "lease_expires_at", None)
        if status == "running" and lease is not None and lease < now:
            travados += 1
    foto_counts: dict[str, int] = {}
    for f in repo.photos.values():
        if _in_org(f.org_id) and _in_window(f.created_at):
            foto_counts[_v(f.status)] = foto_counts.get(_v(f.status), 0) + 1
    fila = {
        "escopo": "plataforma",
        "jobs": _zero_filled(_JOB_STATUSES, job_counts),
        "travados": travados,
        "fotos_por_estado": _zero_filled(_FOTO_STATUSES, foto_counts),
    }

    # 3. atividade
    lotes_in = [b for b in repo.batches.values() if _in_org(b.org_id) and _in_window(b.created_at)]
    fotos_in = [f for f in repo.photos.values() if _in_org(f.org_id) and _in_window(f.created_at)]
    decisoes_in = [d for d in repo.decisions if _in_org(d.org_id) and _in_window(d.created_at)]
    decisoes_counts: dict[str, int] = {}
    for d in decisoes_in:
        decisoes_counts[_v(d.decisao)] = decisoes_counts.get(_v(d.decisao), 0) + 1
    serie: dict[str, dict[str, int]] = {}
    for kind, rows in (("lotes", lotes_in), ("fotos", fotos_in), ("decisoes", decisoes_in)):
        for row in rows:
            k = row.created_at.date().isoformat()
            serie.setdefault(k, {"lotes": 0, "fotos": 0, "decisoes": 0})[kind] += 1
    atividade = {
        "lotes_criados": len(lotes_in),
        "fotos_enviadas": len(fotos_in),
        "decisoes": _zero_filled(_DECISAO_VALUES, decisoes_counts),
        "usuarios_ativos": len({d.decidido_por for d in decisoes_in}),
        "serie_diaria": [{"data": k, **v} for k, v in sorted(serie.items())],
    }

    # 4. aprendizado — latest decision / evaluation per foto_id
    ultima_decisao: dict[str, str] = {}
    for d in sorted(decisoes_in, key=lambda d: d.created_at):
        ultima_decisao[d.foto_id] = _v(d.decisao)
    avaliacoes_in = [a for a in repo.evaluations if _in_org(a.org_id) and _in_window(a.created_at)]
    ultima_avaliacao: dict[str, str] = {}
    for a in sorted(avaliacoes_in, key=lambda a: a.created_at):
        ultima_avaliacao[a.foto_id] = _v(a.recomendacao)
    veredito_counts: dict[str, int] = {}
    for v in ultima_avaliacao.values():
        veredito_counts[v] = veredito_counts.get(v, 0) + 1
    matches = [ultima_decisao[fid] == rec for fid, rec in ultima_avaliacao.items() if fid in ultima_decisao]
    regras_in = [r for r in repo.rules.values() if _in_org(r.org_id)]
    aprendizado = {
        "taxa_aprovacao": (
            sum(1 for v in ultima_decisao.values() if v == "aprovar") / len(ultima_decisao)
            if ultima_decisao else 0
        ),
        "veredito_ia": _zero_filled(_DECISAO_VALUES, veredito_counts),
        "acerto_ia_pct": (sum(matches) / len(matches) * 100) if matches else None,
        "regras": {
            "aprovadas": sum(1 for r in regras_in if _v(r.status) == "aprovada"),
            "pendentes": sum(1 for r in regras_in if _v(r.status) == "proposta"),
        },
    }

    # 5. custos
    custos_in = [
        c for c in repo.costs.values()
        if _in_org(c.org_id) and _in_window(c.created_at) and (c.step or "").startswith("fotos.")
    ]
    por_categoria: dict[str, float] = {}
    for c in custos_in:
        por_categoria[c.category] = por_categoria.get(c.category, 0.0) + float(c.amount_brl or 0)
    total_brl = round(sum(por_categoria.values()), 2)
    custos = {
        "moeda_base": "BRL",
        "por_categoria": [
            {"categoria": cat, "total_brl": round(val, 2)} for cat, val in sorted(por_categoria.items())
        ],
        "total_brl": total_brl,
        "fx_pendentes": sum(1 for c in custos_in if c.fx_pending),
        "receita": {"disponivel": False, "total_brl": 0, "nota": "sem dados de faturamento"},
        "margem_brl": 0 - total_brl,
    }

    return {
        "periodo": {"desde": desde.isoformat(), "ate": ate.isoformat()},
        "escopo": "plataforma" if org_id is None else "organizacao",
        "pipeline": {"pontos": pontos},
        "fila": fila,
        "atividade": atividade,
        "aprendizado": aprendizado,
        "custos": custos,
    }


class _FakePainelClient:
    """`.rpc(name, params).execute()` double — the ONLY RPC this module's
    tests need to simulate is `fotos_painel` (migration 133)."""

    def __init__(self, harness: "Harness") -> None:
        self._harness = harness

    def rpc(self, name: str, params: dict | None = None) -> Any:
        if name != "fotos_painel":
            raise AssertionError(f"unsimulated RPC in edicao_fotos tests: {name!r}")
        data = _simulate_fotos_painel(self._harness, params or {})
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=data))


def build_ports(repo: InMemoryPhotoEditingRepository, backend: FakeStorageBackend,
                notifier: RecordingNotifier) -> PhotoEditingPorts:
    return PhotoEditingPorts(
        repo=repo,
        jobs=FakeJobRepository(),
        storage=BucketPhotoStorage(backend, bucket="edicao-fotos"),
        reference_storage=BucketPhotoStorage(backend, bucket="edicao-fotos-referencias"),
        imaging=FakeImagingAdapter(),
        image_edit=lambda _org, _model: FakeImageEditAdapter(),
        llm=FakeStructuredLlm(
            {
                "avaliacao_foto": good_evaluation,
                "propor_regras": {"regras": []},
                "guia_estilo": {"guia": "- Luz natural\n- Céu azul limpo"},
            }
        ),
        fx=FakeFxRateAdapter({date(2026, 9, 16): Decimal("5.4321")}),
        notifier=notifier,
        config=PhotoEditingConfig(retry_backoff_seconds=0.0),
    )


@pytest.fixture
def edicao(client):
    from app.main import app

    repo = InMemoryPhotoEditingRepository(id_factory=lambda _kind: str(uuid4()))
    backend = FakeStorageBackend()
    notifier = RecordingNotifier()
    ports = build_ports(repo, backend, notifier)
    grants = FakePermissionGrantRepository([(USERS["curador"].id, "photo_curator")])
    preferences = InMemoryNotificationPreferencesRepository()
    # Every AGENCY_ADMIN_ROLES test user is a candidate admin recipient —
    # `services.notifier` only fans out to those who ALSO opted in
    # (`ativo=True`, set per-test via `harness.preferences.save(...)`).
    for key, user in USERS.items():
        if user.roles.org_role in AGENCY_ADMIN_ROLES:
            preferences.seed_admin(
                user.id, org_id=user.org, nome=user.nome, email=f"{key}@example.com",
                org_role=user.roles.org_role,
            )
    harness = Harness(
        http=client, app=app, ports=ports, repo=repo, backend=backend,
        grants=grants, vista=FakeVistaSource(), notifier=notifier,
        preferences=preferences,
        directory={u.id: {"nome": u.nome, "email": f"{k}@example.com"} for k, u in USERS.items()},
    )

    def _current_user_org():
        user = harness.current
        return SimpleNamespace(id=user.id, user_metadata={}), "test-token", user.org

    overrides = {
        get_current_user_org: _current_user_org,
        get_role_resolver: lambda: (lambda uid: next(u.roles for u in USERS.values() if u.id == uid)),
        # Read through the harness so `enable_economico()` can swap ports.
        get_edicao_ports: lambda: harness.ports,
        get_grant_repository: lambda: grants,
        get_preferences_repository: lambda: preferences,
        get_vista_photo_source: lambda: harness.vista,
        get_user_directory: lambda: (
            lambda ids: {i: harness.directory[i] for i in ids if i in harness.directory}
        ),
        get_painel_client: lambda: _FakePainelClient(harness),
    }
    previous = {k: app.dependency_overrides.get(k) for k in overrides}
    app.dependency_overrides.update(overrides)
    yield harness
    for key, prev in previous.items():
        if prev is None:
            app.dependency_overrides.pop(key, None)
        else:
            app.dependency_overrides[key] = prev

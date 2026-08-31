"""`/api/clientes` — auth boundary, board list, review queue, merge/undo.

Contract: `products/social-wiring/projects/lead-card-hub-p1-PROJECT.md` §5
(Slice B). Rows are seeded directly against the `social_wiring`-scoped mock
(`get_clientes_client()`) — there is no `POST /clientes` write surface in
this product (clientes only ever come from the backfill), so every scenario
here starts from a hand-built fixture, mirroring
`tests/services/test_clientes_service.py`'s shapes.

`cliente_id` / `merge_id` path params and `cliente_id_sobrevivente` are
router-declared `UUID` (mirrors `portal_roi_router.py`'s `campanha_id: UUID`)
— every id in this file is therefore a REAL `uuid4()`, not a readable
placeholder string, or the request 422s before it ever reaches the handler.

**Strict `== 401`, never `in (401, 404)`.** A permissive tuple is a
false-green — it passes when the route doesn't exist at all, and it passes
when validation runs before auth. Only the exact code proves the guard
fired. → `KB § PATTERNS/compliance/auth-boundary-false-green.md`

**`manter-separados` durability** is the other thing worth reading closely
(`TestManterSeparados`): the group must not resurface on a SUBSEQUENT
`GET /revisao` call — a fresh read against the router, not a cached
response — which is exactly what migration `049`'s
`cliente_revisao_rejeitadas` table exists to guarantee.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.dependencies import coerce_org_uuid
from app.routers.clientes_router import get_clientes_client
from tests.conftest import (  # type: ignore[attr-defined]
    MockSupabaseClient,
    MockUser,
    MockUserResponse,
    bind_consent_module_to_mock,
)

ORG_RAW = "test-org-123"
ORG_ID = str(coerce_org_uuid(ORG_RAW))


def _auth() -> dict:
    return {"Authorization": "Bearer test-token"}


# ─── row builders ───────────────────────────────────────────────────────


def _cliente(
    id_,
    nome,
    *,
    chave=None,
    tipo=None,
    incerta=False,
    ativo=True,
    inativo_em=None,
    arquivado_em=None,
    primeiro="2026-01-01T00:00:00+00:00",
    ultimo="2026-01-01T00:00:00+00:00",
) -> dict:
    return {
        "id": id_,
        "org_id": ORG_ID,
        "nome": nome,
        "chave_canonica": chave,
        "chave_tipo": tipo,
        "identidade_incerta": incerta,
        "ativo": ativo,
        "inativo_em": inativo_em,
        "arquivado_em": arquivado_em,
        "primeiro_contato_em": primeiro,
        "ultimo_contato_em": ultimo,
        "created_at": primeiro,
        "updated_at": None,
    }


def _touch(
    id_,
    cliente_id,
    *,
    origem_id,
    ocorreu_em,
    origem_tabela="leads",
    nome=None,
    chave=None,
) -> dict:
    return {
        "id": id_,
        "cliente_id": cliente_id,
        "org_id": ORG_ID,
        "origem_tabela": origem_tabela,
        "origem_id": origem_id,
        "ocorreu_em": ocorreu_em,
        "nome": nome,
        "chave_canonica": chave,
        "origem_label": None,
        "created_at": ocorreu_em,
    }


def _lead(id_, *, corretor_id=None) -> dict:
    return {
        "id": id_,
        "org_id": ORG_ID,
        "cliente_nome": "x",
        "contato_norm": None,
        "corretor_id": corretor_id,
        "data_entrada": "2026-01-01",
    }


def _atendimento(id_, cliente_id, *, valor=1000.0) -> dict:
    return {
        "id": id_,
        "org_id": ORG_ID,
        "cliente_id": cliente_id,
        "lead_id": None,
        "meta_ads_lead_id": None,
        "valor": valor,
    }


# ─── fixtures ────────────────────────────────────────────────────────────


@pytest.fixture
def anon_client():
    """A TestClient that sends NO Authorization header — see
    `test_portal_roi_router.py`'s identical fixture for why the shared
    `client` fixture can never produce a 401."""
    mock_sb = MockSupabaseClient()
    mock_sb.auth.get_user = MagicMock(
        return_value=MockUserResponse(MockUser(org_id=ORG_RAW))
    )
    with (
        patch("noctusai_seed.database.DatabaseModule.get_client", return_value=mock_sb),
        patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=mock_sb),
        patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=mock_sb),
    ):
        from app.main import app

        bind_consent_module_to_mock(mock_sb)
        tc = TestClient(app)
        yield tc
        app.dependency_overrides.clear()


@pytest.fixture
def scoped(client):
    """The `social_wiring`-scoped mock the router's own DI seam
    (`get_clientes_client`) resolves and caches — seeding through THIS
    SAME instance is what makes rows visible to a subsequent request in
    the same test (see `clientes_router.py`'s module docstring)."""
    return get_clientes_client()


# ─── auth boundary — strict 401 ───────────────────────────────────────────

_MERGE_ID = str(uuid4())
_CLIENTE_ID = str(uuid4())
_GRUPO = "+5511900000000"

UNAUTHENTICATED_ROUTES = [
    ("get", "/api/clientes"),
    ("get", f"/api/clientes/{_CLIENTE_ID}"),
    ("get", f"/api/clientes/{_CLIENTE_ID}/touches"),
    ("patch", f"/api/clientes/{_CLIENTE_ID}"),
    ("get", "/api/clientes/revisao"),
    ("post", f"/api/clientes/revisao/{_GRUPO}/merge"),
    ("post", f"/api/clientes/revisao/{_GRUPO}/manter-separados"),
    ("post", "/api/clientes/revisao/merge-seguros"),
    ("post", f"/api/clientes/merges/{_MERGE_ID}/desfazer"),
]


@pytest.mark.parametrize("method,path", UNAUTHENTICATED_ROUTES)
def test_unauthenticated_requests_are_strictly_401(anon_client, method, path):
    resp = getattr(anon_client, method)(path)
    assert resp.status_code == 401, f"{method.upper()} {path} -> {resp.status_code}: {resp.text}"


def test_every_clientes_route_requires_auth(anon_client):
    """Enumerates mounted routes rather than a hand list — guards against a
    future route landing without `Depends(get_current_user_org)`."""
    from app.main import app

    paths = {
        (method.lower(), route.path)
        for route in app.routes
        if getattr(route, "path", "").startswith("/api/clientes")
        for method in getattr(route, "methods", set())
        if method.lower() in {"get", "post", "patch", "delete"}
    }
    assert paths, "no /api/clientes routes are mounted — the router isn't wired"

    for method, path in sorted(paths):
        concrete = (
            path.replace("{cliente_id}", _CLIENTE_ID)
            .replace("{merge_id}", _MERGE_ID)
            .replace("{grupo}", _GRUPO)
        )
        resp = getattr(anon_client, method)(concrete)
        assert resp.status_code == 401, (
            f"{method.upper()} {concrete} -> {resp.status_code} "
            "(every /api/clientes route must require auth)"
        )


def test_router_is_mounted(anon_client):
    from app.main import app

    paths = {getattr(r, "path", "") for r in app.routes}
    assert "/api/clientes" in paths
    assert "/api/clientes/revisao" in paths
    assert "/api/clientes/{cliente_id}" in paths


# ─── board list ────────────────────────────────────────────────────────


class TestListClientes:
    def test_default_active_only(self, client, scoped):
        a1, a2 = str(uuid4()), str(uuid4())
        scoped.set_table_data(
            "clientes",
            [
                _cliente(a1, "Ana", ativo=True),
                _cliente(a2, "Bob", ativo=False, arquivado_em="2026-05-01T00:00:00+00:00"),
            ],
        )
        resp = client.get("/api/clientes", headers=_auth())
        assert resp.status_code == 200, resp.text
        body = resp.json()
        # NOT `body["total"]`: `MockSelectBuilder`'s `count="exact"` is
        # fixed at `.select()` time from the UNFILTERED table (a confirmed
        # mock limitation, documented identically in
        # `test_clientes_service.py::TestReadSurface`), so it reports the
        # full table (2), not the ativo-filtered subset. `items` (the
        # actually-filtered rows) is the honest assertion; real PostgREST
        # returns a correctly filtered count.
        assert {c["id"] for c in body["items"]} == {a1}

    def test_ativo_false_shows_inactive(self, client, scoped):
        a1, a2 = str(uuid4()), str(uuid4())
        scoped.set_table_data(
            "clientes", [_cliente(a1, "Ana", ativo=True), _cliente(a2, "Bob", ativo=False)]
        )
        resp = client.get("/api/clientes", params={"ativo": "false"}, headers=_auth())
        assert resp.status_code == 200, resp.text
        assert {c["id"] for c in resp.json()["items"]} == {a2}

    def test_q_filter(self, client, scoped):
        a1, a2 = str(uuid4()), str(uuid4())
        scoped.set_table_data(
            "clientes", [_cliente(a1, "Ana Silva"), _cliente(a2, "Bob Souza")]
        )
        resp = client.get("/api/clientes", params={"q": "silva"}, headers=_auth())
        assert resp.status_code == 200, resp.text
        assert {c["id"] for c in resp.json()["items"]} == {a1}

    def test_pagination_arithmetic(self, client, scoped):
        """`total`/`pages` are computed server-side from `count="exact"`,
        not from `.range()`-truncated `items` — see `_MockExecuteMixin`'s
        eager, pre-filter `count` (the same limitation `test_ativo_false_...`
        et al. document): this DOES exercise the real `pages = ceil(total /
        page_size)` arithmetic `clientes_service.list_clientes` computes.

        `items` truncation IS now provable here too — `MockSelectBuilder.
        range()` used to be a documented no-op (never truncated the mock's
        returned rows; see `KB § PATTERNS/backend/postgrest-row-cap.md` for
        why that was itself the root enabler of a SEVEN-instance prod bug
        class), so this assertion did not exist until the mock was fixed."""
        ids = [str(uuid4()) for _ in range(5)]
        scoped.set_table_data(
            "clientes", [_cliente(i, f"Pessoa {n}") for n, i in enumerate(ids)]
        )
        resp = client.get(
            "/api/clientes", params={"page": 1, "page_size": 2}, headers=_auth()
        )
        body = resp.json()
        assert body["total"] == 5
        assert body["pages"] == 3
        assert body["page"] == 1
        assert len(body["items"]) == 2, "page_size=2 must bound the returned items too"

    def test_corretor_id_filter(self, client, scoped):
        corretor_a, corretor_b = str(uuid4()), str(uuid4())
        a1, a2 = str(uuid4()), str(uuid4())
        scoped.set_table_data(
            "leads",
            [_lead("L1", corretor_id=corretor_a), _lead("L2", corretor_id=corretor_b)],
        )
        scoped.set_table_data("clientes", [_cliente(a1, "Ana"), _cliente(a2, "Bob")])
        scoped.set_table_data(
            "cliente_touches",
            [
                _touch(str(uuid4()), a1, origem_id="L1", ocorreu_em="2026-01-01T00:00:00+00:00"),
                _touch(str(uuid4()), a2, origem_id="L2", ocorreu_em="2026-01-01T00:00:00+00:00"),
            ],
        )
        resp = client.get(
            "/api/clientes", params={"corretor_id": corretor_a}, headers=_auth()
        )
        assert resp.status_code == 200, resp.text
        assert {c["id"] for c in resp.json()["items"]} == {a1}

    def test_corretor_id_path_truncates_by_page_size(self, client, scoped):
        """The `corretor_id` cross-filter path does its OWN Python-side
        `items[start:start+page_size]` slicing (`clientes_router.py`'s
        `list_clientes_route`), NOT the `.range()`-delegated default path —
        this pins that Python-side slice specifically (`test_pagination_
        arithmetic` above now covers the `.range()`-delegated path since
        `MockSelectBuilder.range()` stopped being a no-op)."""
        corretor = str(uuid4())
        cliente_ids = [str(uuid4()) for _ in range(3)]
        lead_ids = [f"L{i}" for i in range(3)]
        scoped.set_table_data(
            "leads", [_lead(lead_ids[i], corretor_id=corretor) for i in range(3)]
        )
        scoped.set_table_data(
            "clientes", [_cliente(cliente_ids[i], f"Pessoa {i}") for i in range(3)]
        )
        scoped.set_table_data(
            "cliente_touches",
            [
                _touch(
                    str(uuid4()), cliente_ids[i], origem_id=lead_ids[i],
                    ocorreu_em="2026-01-01T00:00:00+00:00",
                )
                for i in range(3)
            ],
        )
        resp = client.get(
            "/api/clientes",
            params={"corretor_id": corretor, "page": 1, "page_size": 2},
            headers=_auth(),
        )
        body = resp.json()
        assert body["total"] == 3
        assert body["pages"] == 2
        assert len(body["items"]) == 2

        page2 = client.get(
            "/api/clientes",
            params={"corretor_id": corretor, "page": 2, "page_size": 2},
            headers=_auth(),
        ).json()
        assert len(page2["items"]) == 1


# ─── cliente detail + touches ──────────────────────────────────────────


class TestClienteDetail:
    def test_includes_atendimentos_and_touch_count(self, client, scoped):
        a1 = str(uuid4())
        scoped.set_table_data("clientes", [_cliente(a1, "Ana")])
        scoped.set_table_data(
            "cliente_touches",
            [
                _touch(str(uuid4()), a1, origem_id="L1", ocorreu_em="2026-01-01T00:00:00+00:00"),
                _touch(str(uuid4()), a1, origem_id="L2", ocorreu_em="2026-01-02T00:00:00+00:00"),
            ],
        )
        scoped.set_table_data(
            "atendimentos",
            [_atendimento(str(uuid4()), a1), _atendimento(str(uuid4()), a1)],
        )
        resp = client.get(f"/api/clientes/{a1}", headers=_auth())
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["id"] == a1
        assert len(body["atendimentos"]) == 2
        assert body["touch_count"] == 2

    def test_404_unknown(self, client, scoped):
        scoped.set_table_data("clientes", [])
        resp = client.get(f"/api/clientes/{uuid4()}", headers=_auth())
        assert resp.status_code == 404, resp.text
        assert resp.json()["error"]["code"] == "NOT_FOUND"


class TestTouches:
    def test_paginated_by_page_size(self, client, scoped):
        """`get_touches` asks the DB for `.order("ocorreu_em", desc=True)`
        + `.range(...)` — real PostgREST honors both.

        `MockSelectBuilder.range()` now actually slices (it used to be a
        no-op with no row ceiling — the same root enabler that let SEVEN
        row-cap bugs ship to prod undetected in one session; see
        `KB § PATTERNS/backend/postgrest-row-cap.md`), so this test used to
        assert the FULL, unbounded set came back regardless of `page_size`
        — the honest thing to assert given the mock at the time. `.order()`
        stays a DOCUMENTED no-op on the mock (only real PostgREST sorts),
        so this deliberately does NOT assert a specific chronological
        order — only what the mock can now actually prove: `page_size`
        bounds each page's item count, and the two pages partition the
        full set with no touch dropped or duplicated.
        """
        a1 = str(uuid4())
        t1, t2, t3 = str(uuid4()), str(uuid4()), str(uuid4())
        scoped.set_table_data("clientes", [_cliente(a1, "Ana")])
        scoped.set_table_data(
            "cliente_touches",
            [
                _touch(t1, a1, origem_id="L1", ocorreu_em="2026-01-01T00:00:00+00:00"),
                _touch(t2, a1, origem_id="L2", ocorreu_em="2026-03-01T00:00:00+00:00"),
                _touch(t3, a1, origem_id="L3", ocorreu_em="2026-02-01T00:00:00+00:00"),
            ],
        )
        resp1 = client.get(
            f"/api/clientes/{a1}/touches",
            params={"page_size": 2, "page": 1},
            headers=_auth(),
        )
        assert resp1.status_code == 200, resp1.text
        body1 = resp1.json()
        assert len(body1["items"]) == 2, "page_size=2 must bound page 1 to 2 items"
        assert body1["total"] == 3
        assert body1["pages"] == 2

        resp2 = client.get(
            f"/api/clientes/{a1}/touches",
            params={"page_size": 2, "page": 2},
            headers=_auth(),
        )
        assert resp2.status_code == 200, resp2.text
        body2 = resp2.json()
        assert len(body2["items"]) == 1, "the remaining touch must land on page 2"

        ids_page1 = {t["id"] for t in body1["items"]}
        ids_page2 = {t["id"] for t in body2["items"]}
        assert ids_page1.isdisjoint(ids_page2), "pages must not overlap"
        assert ids_page1 | ids_page2 == {t1, t2, t3}, (
            "every touch must appear exactly once across pages"
        )

    def test_404_unknown_cliente(self, client, scoped):
        scoped.set_table_data("clientes", [])
        resp = client.get(f"/api/clientes/{uuid4()}/touches", headers=_auth())
        assert resp.status_code == 404, resp.text


# ─── PATCH ──────────────────────────────────────────────────────────────


class TestPatchCliente:
    def test_patch_nome(self, client, scoped):
        a1 = str(uuid4())
        scoped.set_table_data("clientes", [_cliente(a1, "Ana")])
        resp = client.patch(
            f"/api/clientes/{a1}", json={"nome": "Ana Maria"}, headers=_auth()
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["nome"] == "Ana Maria"

    def test_patch_ativo_false_archives(self, client, scoped):
        a1 = str(uuid4())
        scoped.set_table_data("clientes", [_cliente(a1, "Ana", ativo=True)])
        resp = client.patch(f"/api/clientes/{a1}", json={"ativo": False}, headers=_auth())
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["ativo"] is False
        assert body["arquivado_em"] is not None

    def test_patch_ativo_true_restores(self, client, scoped):
        a1 = str(uuid4())
        scoped.set_table_data(
            "clientes",
            [_cliente(a1, "Ana", ativo=False, arquivado_em="2026-05-01T00:00:00+00:00")],
        )
        resp = client.patch(f"/api/clientes/{a1}", json={"ativo": True}, headers=_auth())
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["ativo"] is True
        assert body["arquivado_em"] is None

    def test_patch_ativo_true_after_a_sweep_sets_reativado_em_and_clears_inativo(
        self, client, scoped
    ):
        """D16 — the manual-restore-wins signal
        (`clientes_inactivity_service.py`'s
        `GREATEST(ultimo_contato_em, reativado_em)` silence check) has to
        actually get SET by this route, or a restore that survives one
        scheduled tick is a lie. Also clears the sweep's own
        `inativo_em`/`inativo_threshold_dias` bookkeeping — a restored
        cliente should not still claim "inactive since ... (threshold
        180d)" anywhere."""
        a1 = str(uuid4())
        scoped.set_table_data(
            "clientes",
            [{
                **_cliente(a1, "Ana", ativo=False),
                "inativo_em": "2026-06-01T00:00:00+00:00",
                "inativo_threshold_dias": 180,
                "reativado_em": None,
            }],
        )
        resp = client.patch(f"/api/clientes/{a1}", json={"ativo": True}, headers=_auth())
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["ativo"] is True
        assert body["inativo_em"] is None
        assert body["inativo_threshold_dias"] is None
        assert body["reativado_em"] is not None

    def test_patch_404(self, client, scoped):
        scoped.set_table_data("clientes", [])
        resp = client.patch(
            f"/api/clientes/{uuid4()}", json={"nome": "x"}, headers=_auth()
        )
        assert resp.status_code == 404, resp.text

    def test_patch_data_nascimento_payload_is_json_serializable(self, client, scoped):
        """🔴 Regression for the "date field errors when setting it" bug.

        `ClientePatchBody.data_nascimento` is typed `Optional[date]`, so
        `model_dump(exclude_unset=True)` — WITHOUT `mode="json"` — hands back
        a live `datetime.date` object. That object used to flow straight into
        `svc.update_cliente`'s `.update(payload)`, which on the REAL client is
        `postgrest-py` building an `httpx` request with `json=payload`; `httpx`
        serializes with the stdlib `json` module, which has never known how to
        encode `date` — every genuine "set the birthdate" PATCH 500'd in
        production. `genero`/`profissao` never hit this because they stay
        `str` after validation, which is exactly why only the date field ever
        errored.

        The mock client used everywhere else in this suite stores whatever
        Python object `.update()` is handed — it never serializes — so this
        is the ONE assertion in the file that actually inspects the payload
        TYPE rather than trusting a 200 status code. `resp.status_code == 200`
        alone would have stayed green through the whole outage.
        """
        a1 = str(uuid4())
        scoped.set_table_data("clientes", [_cliente(a1, "Ana")])
        resp = client.patch(
            f"/api/clientes/{a1}",
            json={"data_nascimento": "1990-05-15"},
            headers=_auth(),
        )
        assert resp.status_code == 200, resp.text

        payload = scoped.table("clientes").updated_payloads[-1]
        # The exact TypeError httpx raises for a raw `datetime.date` — this
        # is what proves the fix, not just that FastAPI returned 200.
        import json as _json

        _json.dumps(payload)  # raises TypeError on the pre-fix code
        assert payload["data_nascimento"] == "1990-05-15"
        assert isinstance(payload["data_nascimento"], str)

    def test_patch_extra_field_rejected(self, client, scoped):
        """`StrictHttpModel`'s `extra='forbid'` — a raw `arquivado_em` in
        the body must 422, not silently write an arbitrary timestamp."""
        a1 = str(uuid4())
        scoped.set_table_data("clientes", [_cliente(a1, "Ana")])
        resp = client.patch(
            f"/api/clientes/{a1}",
            json={"arquivado_em": "2020-01-01T00:00:00+00:00"},
            headers=_auth(),
        )
        assert resp.status_code == 422, resp.text


# ─── review queue ───────────────────────────────────────────────────────


def _seed_review_group(scoped, *, key="+5511900000004"):
    """Two review candidates sharing a key — the roadmap's shared-phone C5
    case (Carmen Real Dias / Luana Batista), same shape as
    `test_clientes_service.py::TestMergeAndUndo._seed_two_review_candidates`.
    Returns `(key, g1_id, g2_id)`."""
    g1, g2 = str(uuid4()), str(uuid4())
    scoped.set_table_data(
        "clientes",
        [
            _cliente(g1, "Carmen Real Dias", incerta=True),
            _cliente(g2, "Luana Batista", incerta=True),
        ],
    )
    scoped.set_table_data(
        "cliente_touches",
        [
            _touch(
                str(uuid4()), g1, origem_id="L7", ocorreu_em="2026-04-01T00:00:00+00:00",
                nome="Carmen Real Dias", chave=key,
            ),
            _touch(
                str(uuid4()), g2, origem_id="L8", ocorreu_em="2026-04-02T00:00:00+00:00",
                nome="Luana Batista", chave=key,
            ),
        ],
    )
    scoped.set_table_data("cliente_merges", [])
    scoped.set_table_data("cliente_revisao_rejeitadas", [])
    return key, g1, g2


def _seed_n_review_groups(scoped, n: int) -> list[str]:
    """`n` independent 2-candidate review groups, each under its own key
    (`+551190002{i:02d}`) — used by the pagination/ordering tests below,
    which need MULTIPLE groups rather than `_seed_review_group`'s single
    one. Returns the keys in seeded (= grouping) order."""
    keys = [f"+551190002{i:02d}" for i in range(n)]
    clientes_rows: list[dict] = []
    touch_rows: list[dict] = []
    for i, key in enumerate(keys):
        a, b = str(uuid4()), str(uuid4())
        clientes_rows += [
            _cliente(a, f"Pessoa {i}A", incerta=True),
            _cliente(b, f"Pessoa {i}B", incerta=True),
        ]
        touch_rows += [
            _touch(
                str(uuid4()), a, origem_id=f"L{i}A",
                ocorreu_em="2026-01-01T00:00:00+00:00", chave=key,
            ),
            _touch(
                str(uuid4()), b, origem_id=f"L{i}B",
                ocorreu_em="2026-01-01T00:00:00+00:00", chave=key,
            ),
        ]
    scoped.set_table_data("clientes", clientes_rows)
    scoped.set_table_data("cliente_touches", touch_rows)
    scoped.set_table_data("cliente_merges", [])
    scoped.set_table_data("cliente_revisao_rejeitadas", [])
    return keys


class TestMergeSeguros:
    """Draining the unambiguous part of the queue in one press.

    351 groups at two clicks each is an afternoon nobody spends, so the queue
    was never drained. This endpoint applies exactly the groups the classifier
    calls unambiguous and touches nothing else.
    """

    def _seed(self, scoped, pares: list[tuple[str, str]]) -> None:
        clientes_rows: list[dict] = []
        touch_rows: list[dict] = []
        for i, (a_nome, b_nome) in enumerate(pares):
            key = f"+551190009{i:02d}"
            a, b = str(uuid4()), str(uuid4())
            clientes_rows += [
                _cliente(a, a_nome, incerta=True),
                _cliente(b, b_nome, incerta=True),
            ]
            touch_rows += [
                _touch(str(uuid4()), a, origem_id=f"S{i}A",
                       ocorreu_em="2026-01-01T00:00:00+00:00", chave=key),
                _touch(str(uuid4()), b, origem_id=f"S{i}B",
                       ocorreu_em="2026-01-01T00:00:00+00:00", chave=key),
            ]
        scoped.set_table_data("clientes", clientes_rows)
        scoped.set_table_data("cliente_touches", touch_rows)
        scoped.set_table_data("cliente_merges", [])
        scoped.set_table_data("cliente_revisao_rejeitadas", [])

    def test_merges_the_unambiguous_groups(self, client, scoped):
        self._seed(scoped, [("Alex Sandro", "Alex Sandro*"), ("HP Luiza", "Luiza")])

        resp = client.post("/api/clientes/revisao/merge-seguros", headers=_auth())

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["grupos_mesclados"] == 2
        assert body["clientes_absorvidos"] == 2
        assert body["grupos_restantes"] == 0

    def test_leaves_everything_the_classifier_is_unsure_about(self, client, scoped):
        """🔴 The assertion that matters. `Fernanda`/`Lucilene Ferreira Alves`
        are two people sharing a phone; folding their records together is not
        undoable from the operator's side."""
        self._seed(
            scoped,
            [
                ("Alex Sandro", "Alex Sandro*"),          # unambiguous
                ("Fernanda", "Lucilene Ferreira Alves"),  # two people
                ("Erick", "Erik"),                        # a human decides
            ],
        )

        resp = client.post("/api/clientes/revisao/merge-seguros", headers=_auth())

        body = resp.json()
        assert body["grupos_mesclados"] == 1
        assert body["grupos_restantes"] == 2

        restantes = client.get("/api/clientes/revisao", headers=_auth()).json()
        assert restantes["total"] == 2

    def test_the_fuller_name_survives(self, client, scoped):
        """The contract's own C3 rule — the longer spelling is the one worth
        keeping, so a merge never trades a full name for an abbreviation."""
        self._seed(scoped, [("Luiza", "HP Luiza Fernandes")])

        client.post("/api/clientes/revisao/merge-seguros", headers=_auth())

        vivos = [
            c for c in scoped.table("clientes").select("*").execute().data
            if not c.get("merged_into") and not c.get("deleted_at")
        ]
        nomes = {c["nome"] for c in vivos}
        assert "HP Luiza Fernandes" in nomes

    def test_simular_counts_without_touching_anything(self, client, scoped):
        """A bulk action that will not tell you its size before you press it is
        one people are right not to press."""
        self._seed(
            scoped,
            [("Alex Sandro", "Alex Sandro*"), ("Fernanda", "Lucilene Ferreira Alves")],
        )
        antes = len(scoped.table("clientes").select("*").execute().data)

        resp = client.post(
            "/api/clientes/revisao/merge-seguros?simular=true", headers=_auth()
        )

        assert resp.json()["grupos_mesclados"] == 1
        assert resp.json()["grupos_restantes"] == 1
        assert len(scoped.table("clientes").select("*").execute().data) == antes
        assert scoped.table("cliente_merges").select("*").execute().data == []
        # And the queue is untouched.
        assert client.get("/api/clientes/revisao", headers=_auth()).json()["total"] == 2

    def test_an_empty_queue_is_not_an_error(self, client, scoped):
        self._seed(scoped, [])

        resp = client.post("/api/clientes/revisao/merge-seguros", headers=_auth())

        assert resp.status_code == 200
        assert resp.json() == {
            "grupos_mesclados": 0,
            "clientes_absorvidos": 0,
            "grupos_restantes": 0,
        }


class TestRevisao:
    def test_non_empty_against_seeded_fixture(self, client, scoped):
        """The Phase 1 checkpoint's central assertion (contract §5): a
        fresh org with real review-shaped data must NOT come back empty."""
        key, _g1, _g2 = _seed_review_group(scoped)
        resp = client.get("/api/clientes/revisao", headers=_auth())
        assert resp.status_code == 200, resp.text
        items = resp.json()["items"]
        assert items, "review queue came back empty against seeded review data"
        assert items[0]["chave_canonica"] == key
        assert items[0]["motivo"] == "C5"
        assert len(items[0]["candidatos"]) == 2

    def test_response_envelope_matches_fe_contract(self, client, scoped):
        """`products/social-wiring/frontend/src/hooks/useClientesRevisao.ts`
        `normalizeRevisaoPage` recognizes exactly TWO shapes: a paginated
        envelope `{items,total,page,pages}` (matching `PageOut` /
        `ClientesPage` / `ImovelPage`) or a bare array — NOT a
        `{groups:[...]}` envelope. A `{groups:[...]}` response silently
        fell through both branches to an empty page while HTTP 200'ing
        with real data (live incident: 350 real groups rendered as "fila
        de revisão vazia"). Pin the exact key set so this route can never
        quietly regress to a bespoke third shape."""
        _seed_review_group(scoped)
        resp = client.get("/api/clientes/revisao", headers=_auth())
        assert resp.status_code == 200, resp.text
        assert set(resp.json().keys()) == {"items", "total", "page", "pages"}

    def test_pagination_honors_page_and_page_size(self, client, scoped):
        """Independent of the envelope-shape bug: the route previously
        ignored `page`/`page_size` entirely and shipped every group (plus
        every candidate row) in one payload."""
        _seed_n_review_groups(scoped, 5)
        resp = client.get(
            "/api/clientes/revisao", params={"page": 2, "page_size": 2}, headers=_auth()
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total"] == 5
        assert body["pages"] == 3
        assert body["page"] == 2
        assert len(body["items"]) == 2

    def test_rejected_excluded_before_pagination(self, client, scoped):
        """The subtle ordering requirement: `manter-separados` exclusion
        MUST run BEFORE pagination, not after. Build 3 groups, reject the
        FIRST, then request page 1 at page_size=2 — with filter-then-
        paginate the 2 remaining groups fill the page exactly; with
        paginate-then-filter the page would silently come back short (1
        item on a page sized for 2), hiding real remaining work instead
        of surfacing it on the next page."""
        keys = _seed_n_review_groups(scoped, 3)
        rejected_key = keys[0]

        sanity = client.get(
            "/api/clientes/revisao", params={"page": 1, "page_size": 10}, headers=_auth()
        )
        assert sanity.json()["total"] == 3

        reject_resp = client.post(
            f"/api/clientes/revisao/{rejected_key}/manter-separados", headers=_auth()
        )
        assert reject_resp.status_code == 200, reject_resp.text

        resp = client.get(
            "/api/clientes/revisao", params={"page": 1, "page_size": 2}, headers=_auth()
        )
        body = resp.json()
        assert body["total"] == 2, "rejected group must not count toward total"
        assert len(body["items"]) == 2, (
            "page came back short — filter must run before pagination, not after"
        )
        assert rejected_key not in {g["chave_canonica"] for g in body["items"]}


class TestMergeGrupo:
    def test_success_merges_and_clears_group(self, client, scoped):
        key, g1, g2 = _seed_review_group(scoped)
        resp = client.post(
            f"/api/clientes/revisao/{key}/merge",
            json={"cliente_id_sobrevivente": g1},
            headers=_auth(),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["cliente_id"] == g1
        assert body["merged_ids"] == [g2]
        assert len(body["merge_ids"]) == 1

        # the absorbed row is gone, its touch moved
        remaining = {c["id"] for c in scoped.table("clientes").select("*").execute().data}
        assert remaining == {g1}
        touches = scoped.table("cliente_touches").select("*").execute().data
        assert all(t["cliente_id"] == g1 for t in touches)

        # the group no longer has 2+ candidates -> it must not resurface
        revisao = client.get("/api/clientes/revisao", headers=_auth()).json()["items"]
        assert key not in {g["chave_canonica"] for g in revisao}

    def test_unknown_grupo_404(self, client, scoped):
        _key, g1, _g2 = _seed_review_group(scoped)
        resp = client.post(
            "/api/clientes/revisao/+5511900000099/merge",
            json={"cliente_id_sobrevivente": g1},
            headers=_auth(),
        )
        assert resp.status_code == 404, resp.text

    def test_survivor_not_in_group_404(self, client, scoped):
        key, _g1, _g2 = _seed_review_group(scoped)
        resp = client.post(
            f"/api/clientes/revisao/{key}/merge",
            json={"cliente_id_sobrevivente": str(uuid4())},
            headers=_auth(),
        )
        assert resp.status_code == 404, resp.text

    def test_c6_three_candidates_all_fold_into_survivor(self, client, scoped):
        key = "+5511900000005"
        h1, h2, h3 = str(uuid4()), str(uuid4()), str(uuid4())
        scoped.set_table_data(
            "clientes",
            [
                _cliente(h1, "Ana", incerta=True),
                _cliente(h2, "Bob", incerta=True),
                _cliente(h3, "Carla", incerta=True),
            ],
        )
        scoped.set_table_data(
            "cliente_touches",
            [
                _touch(str(uuid4()), h1, origem_id="L9", ocorreu_em="2026-05-01T00:00:00+00:00", chave=key),
                _touch(str(uuid4()), h2, origem_id="L10", ocorreu_em="2026-05-02T00:00:00+00:00", chave=key),
                _touch(str(uuid4()), h3, origem_id="L11", ocorreu_em="2026-05-03T00:00:00+00:00", chave=key),
            ],
        )
        scoped.set_table_data("cliente_merges", [])
        scoped.set_table_data("cliente_revisao_rejeitadas", [])

        resp = client.post(
            f"/api/clientes/revisao/{key}/merge",
            json={"cliente_id_sobrevivente": h1},
            headers=_auth(),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert set(body["merged_ids"]) == {h2, h3}
        assert len(body["merge_ids"]) == 2

        remaining = {c["id"] for c in scoped.table("clientes").select("*").execute().data}
        assert remaining == {h1}


class TestManterSeparados:
    def test_durable_across_subsequent_reads(self, client, scoped):
        key, _g1, _g2 = _seed_review_group(scoped)

        before = client.get("/api/clientes/revisao", headers=_auth()).json()["items"]
        assert key in {g["chave_canonica"] for g in before}

        resp = client.post(f"/api/clientes/revisao/{key}/manter-separados", headers=_auth())
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"chave_canonica": key, "rejeitado": True}

        after = client.get("/api/clientes/revisao", headers=_auth()).json()["items"]
        assert key not in {g["chave_canonica"] for g in after}

        # a THIRD read (simulating "next page load") must still exclude it —
        # this is the durability assertion, not a per-request cache.
        again = client.get("/api/clientes/revisao", headers=_auth()).json()["items"]
        assert key not in {g["chave_canonica"] for g in again}

    def test_idempotent_double_call(self, client, scoped):
        key, _g1, _g2 = _seed_review_group(scoped)
        client.post(f"/api/clientes/revisao/{key}/manter-separados", headers=_auth())
        resp = client.post(f"/api/clientes/revisao/{key}/manter-separados", headers=_auth())
        assert resp.status_code == 200, resp.text
        rows = scoped.table("cliente_revisao_rejeitadas").select("*").execute().data
        assert len([r for r in rows if r["chave_canonica"] == key]) == 1

    def test_unknown_grupo_404(self, client, scoped):
        _seed_review_group(scoped)
        resp = client.post(
            "/api/clientes/revisao/+5511900000099/manter-separados", headers=_auth()
        )
        assert resp.status_code == 404, resp.text


# ─── undo ──────────────────────────────────────────────────────────────


class TestDesfazer:
    def test_merge_then_undo_round_trip_through_api(self, client, scoped):
        key, g1, _g2 = _seed_review_group(scoped)
        merge_resp = client.post(
            f"/api/clientes/revisao/{key}/merge",
            json={"cliente_id_sobrevivente": g1},
            headers=_auth(),
        )
        merge_id = merge_resp.json()["merge_ids"][0]

        undo_resp = client.post(
            f"/api/clientes/merges/{merge_id}/desfazer", headers=_auth()
        )
        assert undo_resp.status_code == 200, undo_resp.text
        new_id = undo_resp.json()["cliente_id"]

        clientes = {c["id"]: c for c in scoped.table("clientes").select("*").execute().data}
        assert set(clientes) == {g1, new_id}
        assert clientes[new_id]["nome"] == "Luana Batista"

        [l8_touch] = [
            t for t in scoped.table("cliente_touches").select("*").execute().data
            if t["origem_id"] == "L8"
        ]
        assert l8_touch["cliente_id"] == new_id

    def test_unknown_merge_404(self, client, scoped):
        scoped.set_table_data("cliente_merges", [])
        resp = client.post(
            f"/api/clientes/merges/{uuid4()}/desfazer", headers=_auth()
        )
        assert resp.status_code == 404, resp.text

    def test_already_undone_409(self, client, scoped):
        key, g1, _g2 = _seed_review_group(scoped)
        merge_resp = client.post(
            f"/api/clientes/revisao/{key}/merge",
            json={"cliente_id_sobrevivente": g1},
            headers=_auth(),
        )
        merge_id = merge_resp.json()["merge_ids"][0]
        client.post(f"/api/clientes/merges/{merge_id}/desfazer", headers=_auth())

        resp = client.post(f"/api/clientes/merges/{merge_id}/desfazer", headers=_auth())
        assert resp.status_code == 409, resp.text


class TestBackfillOnDemand:
    """`POST /api/clientes/backfill` — the missing operator action.

    🔴 Why it exists (prod, 2026-08-31). `atendimentos.cliente_id` was
    populated ONLY by an interval job: no trigger, no endpoint, no UI. A lead
    created by hand therefore got a funil card that `stage_gate` refused to
    move, and the operator had no way to resolve it — only to wait up to
    `clientes_backfill_interval_hours`.
    """

    def test_requires_auth(self, anon_client):
        """Strict `== 401` — a tuple would pass if the route were absent."""
        resp = anon_client.post("/api/clientes/backfill")
        assert resp.status_code == 401

    def test_runs_the_sweep_and_returns_what_it_did(self, client):
        from app.main import app
        from app.routers.clientes_router import get_backfill_runner

        calls: list = []

        def _fake_runner():
            def _run():
                calls.append(True)
                return {
                    "skipped": None,
                    "orgs": [{
                        "org_id": ORG_ID, "ok": True,
                        "clientes_created": 2, "touches_created": 3,
                        "atendimentos_repointed": 2, "atendimentos_collapsed": 0,
                        "stragglers_parked_for_review": 0,
                        "clientes_reactivated": 1,
                    }],
                }
            return _run

        app.dependency_overrides[get_backfill_runner] = _fake_runner
        try:
            resp = client.post("/api/clientes/backfill")
        finally:
            app.dependency_overrides.pop(get_backfill_runner, None)

        assert resp.status_code == 200, resp.text
        assert calls == [True]
        body = resp.json()
        assert body["skipped"] is None
        assert body["orgs"][0]["clientes_created"] == 2
        assert body["orgs"][0]["atendimentos_repointed"] == 2
        assert body["orgs"][0]["clientes_reactivated"] == 1

    def test_surfaces_lease_held_as_a_normal_outcome(self, client):
        """A second press while a sweep is in flight is not an error — it is
        the lease doing its job. It must NOT be reported as a failure."""
        from app.main import app
        from app.routers.clientes_router import get_backfill_runner

        app.dependency_overrides[get_backfill_runner] = lambda: (
            lambda: {"skipped": "lease_held", "orgs": []}
        )
        try:
            resp = client.post("/api/clientes/backfill")
        finally:
            app.dependency_overrides.pop(get_backfill_runner, None)

        assert resp.status_code == 200, resp.text
        assert resp.json() == {"skipped": "lease_held", "orgs": []}

    def test_reports_a_failed_org_rather_than_omitting_it(self, client):
        """A per-org failure returns `ok=false` with zeroed counters. Dropping
        the row would read as "nothing to do" instead of "this one broke"."""
        from app.main import app
        from app.routers.clientes_router import get_backfill_runner

        app.dependency_overrides[get_backfill_runner] = lambda: (
            lambda: {"skipped": None, "orgs": [{"org_id": ORG_ID, "ok": False}]}
        )
        try:
            resp = client.post("/api/clientes/backfill")
        finally:
            app.dependency_overrides.pop(get_backfill_runner, None)

        assert resp.status_code == 200, resp.text
        org = resp.json()["orgs"][0]
        assert org["ok"] is False
        assert org["clientes_created"] == 0

    def test_route_is_declared_before_the_cliente_id_catch_all(self, client):
        """`/backfill` is a literal 1-segment path exactly like
        `/{cliente_id}`. Declared after it, FastAPI would try to parse
        "backfill" as a UUID and 422 — the hazard the module docstring flags
        for `/revisao`. A 422 here means the ordering regressed."""
        from app.main import app
        from app.routers.clientes_router import get_backfill_runner

        app.dependency_overrides[get_backfill_runner] = lambda: (
            lambda: {"skipped": None, "orgs": []}
        )
        try:
            resp = client.post("/api/clientes/backfill")
        finally:
            app.dependency_overrides.pop(get_backfill_runner, None)
        assert resp.status_code != 422

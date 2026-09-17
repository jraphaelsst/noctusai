"""Unit tests for `CheckoutService` — contract §Checkout, amendments
A1-A3, A10, product decisions P1/P2.

Uses `FakeHostedCheckout` (seed) + `FakeTurnstileVerifier` (seed,
`noctusai_lib.integrations.turnstile`) injected via constructor DI — no
Cloudflare/Stripe/Asaas calls, no monkeypatching of this product's own
code. Abuse-cap values are ALSO injected via constructor (never
`monkeypatch.setattr(settings, ...)`) — the same DI seam.
"""
import asyncio

from noctusai_lib.integrations.payments.checkout import FakeHostedCheckout
from noctusai_lib.integrations.turnstile import FakeTurnstileVerifier
from noctusai_lib.testing import MockSupabaseClient

from app.services.checkout_service import CheckoutService, CheckoutServiceError

ORG_ID = "11111111-1111-1111-1111-111111111111"
PLANO_1 = "22222222-2222-2222-2222-222222222222"


def _plano_row(**over) -> dict:
    base = {
        "id": PLANO_1, "org_id": ORG_ID, "nome": "Círculo", "descricao": None,
        "preco_centavos": 9900, "ciclo": "mensal",
        "entitlements": {"feed": True, "forum": True, "chat": True, "eventos": True,
                         "conteudo_ids": [], "grupos_whatsapp": [], "conteudo_todos": False},
        "ativo": True, "ordem": 0,
        "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00",
    }
    base.update(over)
    return base


def _gateway_ref_row(gateway: str, **over) -> dict:
    base = {
        "id": f"ref-{gateway}", "org_id": ORG_ID, "plano_id": PLANO_1, "gateway": gateway,
        "ref_externo": "price_123" if gateway == "stripe" else "asaas-plan-1",
        "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00",
    }
    base.update(over)
    return base


def _payload(**over) -> dict:
    base = {
        "plano_id": PLANO_1, "metodo": "pix", "nome": "Ana", "email": "ana@x.com",
        "telefone": "+5511999999999", "cpf": "12345678901", "turnstile_token": "tok",
    }
    base.update(over)
    return base


def _service(client, *, accept_turnstile: bool = True, **overrides) -> CheckoutService:
    return CheckoutService(
        client, org_id=ORG_ID,
        hosted_checkout_factory=overrides.pop("hosted_checkout_factory", lambda gateway: FakeHostedCheckout()),
        turnstile_verifier=FakeTurnstileVerifier(accept=accept_turnstile),
        **overrides,
    )


def _run(coro):
    return asyncio.run(coro)


def _new_client(*, plano_rows=None, ref_rows=None) -> MockSupabaseClient:
    client = MockSupabaseClient()
    client.set_table_data("planos", plano_rows if plano_rows is not None else [_plano_row()])
    client.set_table_data(
        "plano_gateway_refs",
        ref_rows if ref_rows is not None else [_gateway_ref_row("stripe"), _gateway_ref_row("asaas")],
    )
    return client


class TestTurnstile:
    """Product decision P2."""

    def test_missing_token_403(self):
        client = _new_client()
        service = _service(client)
        try:
            _run(service.checkout(payload=_payload(turnstile_token=None)))
            assert False, "expected CheckoutServiceError"
        except CheckoutServiceError as exc:
            assert exc.status_code == 403

    def test_invalid_token_403(self):
        client = _new_client()
        service = _service(client, accept_turnstile=False)
        try:
            _run(service.checkout(payload=_payload()))
            assert False, "expected CheckoutServiceError"
        except CheckoutServiceError as exc:
            assert exc.status_code == 403

    def test_valid_token_proceeds(self):
        client = _new_client()
        service = _service(client)
        result = _run(service.checkout(payload=_payload()))
        assert result["checkout_url"] is not None


class TestPlanoAndGatewayRef:
    def test_plano_not_found_404(self):
        client = _new_client(plano_rows=[])
        service = _service(client)
        try:
            _run(service.checkout(payload=_payload()))
            assert False
        except CheckoutServiceError as exc:
            assert exc.status_code == 404

    def test_inactive_plano_404(self):
        client = _new_client(plano_rows=[_plano_row(ativo=False)])
        service = _service(client)
        try:
            _run(service.checkout(payload=_payload()))
            assert False
        except CheckoutServiceError as exc:
            assert exc.status_code == 404

    def test_missing_gateway_ref_409(self):
        client = _new_client(ref_rows=[_gateway_ref_row("stripe")])  # no asaas ref
        service = _service(client)
        try:
            _run(service.checkout(payload=_payload(metodo="pix")))
            assert False
        except CheckoutServiceError as exc:
            assert exc.status_code == 409


class TestFindOrCreateMembro:
    """Amendments A1 (plano_id never set at checkout) and A3 (found row untouched)."""

    def test_new_membro_created_pendente_no_plano_id(self):
        client = _new_client()
        service = _service(client)
        result = _run(service.checkout(payload=_payload()))
        membro = client.table("membros").select("*").eq(
            "id", result["membro_id"]
        ).maybe_single().execute().data
        assert membro["status"] == "pendente"
        assert membro["plano_id"] is None
        assert membro["origem"] == "checkout"
        assert membro["entrou_em"] is None

    def test_found_row_is_byte_identical_after_call(self):
        """Amendment A3: submitted nome/telefone never overwrite an
        existing membro row, and plano_id/status stay untouched."""
        client = _new_client()
        existing = {
            "id": "mmm-1", "org_id": ORG_ID, "nome": "Nome Original",
            "email": "ana@x.com", "telefone": "+5511000000000", "status": "pendente",
            "plano_id": None, "origem": "aplicacao", "tags": ["fundadora"],
            "user_id": None, "observacoes": "nota", "entrou_em": None,
            "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00",
        }
        client.set_table_data("membros", [dict(existing)])
        service = _service(client)
        _run(service.checkout(payload=_payload(nome="Outro Nome", telefone="+5511111111111")))
        row = client.table("membros").select("*").eq("id", "mmm-1").maybe_single().execute().data
        assert row == existing

    def test_abandoned_second_checkout_cannot_change_plano_id(self):
        """Amendment A1: paying for a cheap tier must never activate a
        premium plan started (and abandoned) in an earlier checkout."""
        client = _new_client()
        service = _service(client)
        first = _run(service.checkout(payload=_payload(email="ana@x.com")))
        membro_id = first["membro_id"]

        plano_2 = "33333333-3333-3333-3333-333333333333"
        client.table("planos").insert(_plano_row(id=plano_2, nome="Premium")).execute()
        client.table("plano_gateway_refs").insert(
            _gateway_ref_row("asaas", id="ref-asaas-2", plano_id=plano_2)
        ).execute()
        _run(service.checkout(payload=_payload(email="ana@x.com", plano_id=plano_2)))

        membro = client.table("membros").select("*").eq("id", membro_id).maybe_single().execute().data
        assert membro["plano_id"] is None


class TestAmendmentA2NoMembershipOracle:
    def test_ativo_email_and_random_email_get_same_shape(self):
        client = _new_client()
        client.set_table_data("membros", [{
            "id": "mmm-ativo", "org_id": ORG_ID, "nome": "Ativa", "email": "ativa@x.com",
            "telefone": "+5511999999999", "status": "ativo", "plano_id": PLANO_1,
            "origem": "checkout", "tags": [], "user_id": None, "observacoes": None,
            "entrou_em": "2026-01-01T00:00:00+00:00",
            "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00",
        }])
        service = _service(client)

        ativo_result = _run(service.checkout(payload=_payload(email="ativa@x.com")))
        random_result = _run(service.checkout(payload=_payload(email="random@x.com")))

        assert set(ativo_result.keys()) == set(random_result.keys())
        assert ativo_result["checkout_url"] is None
        assert ativo_result["status"] == "verifique_seu_email"
        assert ativo_result["assinatura_id"] is not None
        assert ativo_result["membro_id"] is not None


class TestAmendmentA10AsaasReuseDedupe:
    def test_second_pix_checkout_within_window_reuses_row_no_new_gateway_object(self):
        client = _new_client()
        fake_checkout = FakeHostedCheckout()
        service = _service(client, hosted_checkout_factory=lambda gateway: fake_checkout)
        first = _run(service.checkout(payload=_payload(email="ana@x.com", metodo="pix")))
        assert len(fake_checkout.calls) == 1

        second = _run(service.checkout(payload=_payload(email="ana@x.com", metodo="pix")))
        assert len(fake_checkout.calls) == 1  # no second gateway object created
        assert second["assinatura_id"] == first["assinatura_id"]
        assert second["status"] == "checkout_em_andamento"
        assert second["checkout_url"] is None

    def test_stripe_is_exempt_from_reuse_dedupe(self):
        """Stripe Sessions cost nothing to recreate — see
        `checkout_service.py`'s module docstring."""
        client = _new_client()
        fake_checkout = FakeHostedCheckout()
        service = _service(client, hosted_checkout_factory=lambda gateway: fake_checkout)
        _run(service.checkout(payload=_payload(email="ana@x.com", metodo="cartao", cpf=None)))
        _run(service.checkout(payload=_payload(email="ana@x.com", metodo="cartao", cpf=None)))
        assert len(fake_checkout.calls) == 2


class TestAbuseCaps:
    """Amendment A10 — config values injected via constructor (DI seam),
    never `monkeypatch.setattr(settings, ...)` on this product's own code."""

    def test_email_cap_returns_429(self):
        client = _new_client()
        service = _service(client, max_per_email_per_24h=1)
        _run(service.checkout(payload=_payload(email="cap@x.com", metodo="pix")))
        try:
            _run(service.checkout(payload=_payload(email="cap@x.com", metodo="boleto")))
            assert False
        except CheckoutServiceError as exc:
            assert exc.status_code == 429

    def test_org_cap_returns_429(self):
        client = _new_client()
        service = _service(client, max_per_org_per_hour=1)
        _run(service.checkout(payload=_payload(email="a@x.com", metodo="pix")))
        try:
            _run(service.checkout(payload=_payload(email="b@x.com", metodo="pix")))
            assert False
        except CheckoutServiceError as exc:
            assert exc.status_code == 429


class TestCpfNeverPersisted:
    """Product decision P1: a successful pix checkout leaves no CPF in
    any row (assert the full row set) and none in captured logs."""

    def test_pix_checkout_leaves_no_cpf_anywhere(self, caplog):
        client = _new_client()
        service = _service(client)
        result = _run(service.checkout(payload=_payload(email="semcpf@x.com", metodo="pix", cpf="98765432100")))

        membro = client.table("membros").select("*").eq(
            "id", result["membro_id"]
        ).maybe_single().execute().data
        assinatura = client.table("assinaturas").select("*").eq(
            "id", result["assinatura_id"]
        ).maybe_single().execute().data
        pagamentos = client.table("pagamentos").select("*").eq(
            "membro_id", result["membro_id"]
        ).execute().data or []

        full_row_text = repr(membro) + repr(assinatura) + repr(pagamentos)
        assert "98765432100" not in full_row_text
        assert "98765432100" not in caplog.text

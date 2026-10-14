"""Focus adapter on recorded-shape `httpx.MockTransport` fixtures (shapes copied
from the doc.focusnfe.com.br response examples, 2026-10-13)."""
import base64

import httpx
import pytest

from noctusai_lib.integrations.invoices import (
    Address,
    CompanyRequest,
    InvoiceEnvironment,
    InvoiceKind,
    InvoiceNotFound,
    InvoiceProviderError,
    InvoiceStatus,
    NfseMode,
)
from noctusai_lib.integrations.invoices.focus import company_flags
from tests.integrations.invoices.conftest import (
    ACCOUNT_TOKEN,
    COMPANY_BODY_MUNICIPAL,
    COMPANY_BODY_NACIONAL,
    COMPANY_TOKEN,
    CNPJ,
    PFX_PASSWORD,
    sample_request,
)

NFE_AUTHORIZED = {
    "cnpj_emitente": CNPJ, "ref": "r-nfe", "status": "autorizado", "status_sefaz": "100",
    "chave_nfe": "NFe41190612345678000123550010000000221923094166", "numero": "22", "serie": "1",
    "caminho_xml_nota_fiscal": "/arquivos/x/nfe.xml", "caminho_danfe": "/arquivos/x/danfe.pdf",
}
NFSE_AUTHORIZED = {
    "cnpj_prestador": CNPJ, "ref": "org-ord1-nfse-1", "numero_rps": "1", "serie_rps": "1", "status": "autorizado",
    "numero": "7", "codigo_verificacao": "ABC123", "data_emissao": "2026-10-13T10:00:00-03:00",
    "url": "https://www.nfse.gov.br/consultapublica/?chave=1",
    "caminho_xml_nota_fiscal": "/arquivos/x/nfse.xml",
    "url_danfse": "https://focusnfe.s3.sa-east-1.amazonaws.com/arquivos/x/danfse.pdf",
}


def basic(token: str) -> str:
    return "Basic " + base64.b64encode(f"{token}:".encode()).decode()


# ── auth / transport ──────────────────────────────────────────────────

def test_hosts_by_environment(make_focus):
    assert make_focus()._base_url == "https://homologacao.focusnfe.com.br"
    assert make_focus(environment=InvoiceEnvironment.PRODUCAO)._base_url == "https://api.focusnfe.com.br"


def test_account_token_for_companies_company_token_for_documents(make_focus, stub):
    stub.routes[("GET", "/v2/empresas")] = (200, [])
    stub.routes[("GET", "/v2/nfe/r-nfe")] = (200, NFE_AUTHORIZED)
    focus = make_focus()
    focus.verify_credentials()
    focus.get(InvoiceKind.NFE, "r-nfe")
    assert stub.requests[0].headers["Authorization"] == basic(ACCOUNT_TOKEN)
    assert stub.requests[1].headers["Authorization"] == basic(COMPANY_TOKEN)


def test_verify_credentials_401_is_generic(make_focus, stub):
    stub.routes[("GET", "/v2/empresas")] = (401, {"codigo": "x", "mensagem": ACCOUNT_TOKEN})
    with pytest.raises(InvoiceProviderError) as exc:
        make_focus().verify_credentials()
    assert exc.value.code == "credenciais_invalidas" and ACCOUNT_TOKEN not in str(exc.value)


def test_missing_company_token_fails(make_focus):
    with pytest.raises(InvoiceProviderError) as exc:
        make_focus(default_company_token=None).get(InvoiceKind.NFE, "r")
    assert exc.value.code == "company_token_ausente"


def test_company_token_resolver_used(make_focus, stub):
    stub.routes[("GET", "/v2/nfe/r-nfe")] = (200, NFE_AUTHORIZED)
    make_focus(default_company_token=None, company_tokens=lambda ref: "from-resolver").get(
        InvoiceKind.NFE, "r-nfe", company_ref="123"
    )
    assert stub.requests[0].headers["Authorization"] == basic("from-resolver")


def test_rate_limit_429_retries_then_succeeds(make_focus, stub):
    attempts = []

    def route(req):
        attempts.append(1)
        return (429, {}) if len(attempts) == 1 else (200, NFE_AUTHORIZED)

    stub.routes[("GET", "/v2/nfe/r-nfe")] = route
    assert make_focus().get(InvoiceKind.NFE, "r-nfe").status is InvoiceStatus.AUTHORIZED
    assert len(attempts) == 2


def test_5xx_is_retryable_generic_error(make_focus, stub):
    stub.routes[("GET", "/v2/nfe/r")] = (503, "<html>token in body</html>")
    with pytest.raises(InvoiceProviderError) as exc:
        make_focus().get(InvoiceKind.NFE, "r")
    assert exc.value.retryable and exc.value.code == "provedor_indisponivel"


# ── companies / certificate / mode ───────────────────────────────────

def test_company_flags_mutual_exclusion():
    for env in InvoiceEnvironment:
        nac = company_flags(NfseMode.NACIONAL, env, True)
        mun = company_flags(NfseMode.MUNICIPAL, env, True)
        assert not (nac["habilita_nfse"] and (nac["habilita_nfsen_producao"] or nac["habilita_nfsen_homologacao"]))
        assert mun["habilita_nfse"] and not mun["habilita_nfsen_producao"] and not mun["habilita_nfsen_homologacao"]
    assert company_flags(NfseMode.NACIONAL, InvoiceEnvironment.PRODUCAO, False)["habilita_nfsen_producao"]
    assert company_flags(NfseMode.NACIONAL, InvoiceEnvironment.HOMOLOGACAO, False)["habilita_nfsen_homologacao"]


def test_ensure_company_creates_with_nacional_flags(make_focus, stub):
    stub.routes[("POST", "/v2/empresas")] = (201, COMPANY_BODY_NACIONAL)
    sunk = []
    company = make_focus(token_sink=lambda ref, cnpj, tok: sunk.append((ref, cnpj, tok))).ensure_company(
        CompanyRequest(
            cnpj=CNPJ, legal_name="Loja", tax_regime="simples", enable_nfe=True,
            inscricao_municipal="123456", address=Address(street="Rua A", city="SP", state="SP", zip_code="01234567"),
        )
    )
    sent = stub.body(stub.requests[0])
    assert sent["habilita_nfse"] is False and sent["habilita_nfsen_homologacao"] is True
    assert sent["habilita_nfsen_producao"] is False and sent["habilita_nfe"] is True
    assert sent["regime_tributario"] == 1 and sent["nome"] == "Loja" and sent["logradouro"] == "Rua A"
    assert stub.requests[0].headers["Authorization"] == basic(ACCOUNT_TOKEN)
    assert (company.ref, company.nfse_mode) == ("123", NfseMode.NACIONAL)
    assert sunk == [("123", CNPJ, COMPANY_TOKEN)]  # configured env's token, via the sink only
    assert "tok-prod-SECRET" not in repr(company) and COMPANY_TOKEN not in repr(company)


def test_ensure_company_updates_existing_with_put(make_focus, stub):
    stub.routes[("PUT", "/v2/empresas/123")] = (200, COMPANY_BODY_MUNICIPAL)
    company = make_focus().ensure_company(
        CompanyRequest(cnpj=CNPJ, legal_name="Loja", nfse_mode=NfseMode.MUNICIPAL, company_ref="123", tax_regime="normal")
    )
    assert company.nfse_mode is NfseMode.MUNICIPAL
    sent = stub.body(stub.requests[0])
    assert sent["habilita_nfse"] is True and sent["habilita_nfsen_homologacao"] is False
    assert sent["regime_tributario"] == 3


def test_ensure_company_token_uses_configured_environment(make_focus, stub):
    body = {**COMPANY_BODY_NACIONAL, "habilita_nfsen_producao": True, "habilita_nfsen_homologacao": False}
    stub.routes[("POST", "/v2/empresas")] = (201, body)
    sunk = []
    make_focus(environment=InvoiceEnvironment.PRODUCAO, token_sink=lambda r, c, t: sunk.append(t)).ensure_company(
        CompanyRequest(cnpj=CNPJ, legal_name="L")
    )
    assert sunk == ["tok-prod-SECRET"]


def test_conflicting_flags_are_an_error(make_focus, stub):
    stub.routes[("PUT", "/v2/empresas/123")] = (200, {"id": 123})
    stub.routes[("GET", "/v2/empresas/123")] = (200, {**COMPANY_BODY_NACIONAL, "habilita_nfse": True})
    with pytest.raises(InvoiceProviderError) as exc:
        make_focus().set_nfse_mode("123", NfseMode.NACIONAL)
    assert exc.value.code == "nfse_mode_conflict"


def test_upload_certificate_forwards_base64_and_returns_local_info(make_focus, stub, pfx_bundle):
    pfx, not_after = pfx_bundle
    stub.routes[("PUT", "/v2/empresas/123")] = (200, COMPANY_BODY_NACIONAL)
    info = make_focus().upload_certificate("123", pfx=pfx, password=PFX_PASSWORD)
    sent = stub.body(stub.requests[0])
    assert base64.b64decode(sent["arquivo_certificado_base64"]) == pfx
    assert sent["senha_certificado"] == PFX_PASSWORD and sent["certificado_especifico"] is True
    assert info.subject_cnpj == CNPJ and info.valid_until == not_after


def test_bad_certificate_never_reaches_the_provider(make_focus, stub):
    from noctusai_lib.integrations.invoices import InvoiceCertificateError

    with pytest.raises(InvoiceCertificateError):
        make_focus().upload_certificate("123", pfx=b"junk", password="x")
    assert stub.requests == []


def test_set_nfse_mode_puts_flags_without_touching_nfe_and_rereads(make_focus, stub):
    stub.routes[("PUT", "/v2/empresas/123")] = (200, {"id": 123})
    stub.routes[("GET", "/v2/empresas/123")] = (200, COMPANY_BODY_NACIONAL)
    company = make_focus().set_nfse_mode("123", NfseMode.NACIONAL)
    sent = stub.body(stub.requests[0])
    assert "habilita_nfe" not in sent and sent["habilita_nfse"] is False
    assert company.nfse_mode is NfseMode.NACIONAL


# ── issue ────────────────────────────────────────────────────────────

def test_issue_nfe_hits_nfe_with_ref_and_maps_authorized(make_focus, stub):
    stub.routes[("GET", "/v2/empresas/123")] = (200, COMPANY_BODY_NACIONAL)
    stub.routes[("POST", "/v2/nfe")] = (201, NFE_AUTHORIZED)
    result = make_focus().issue(sample_request(InvoiceKind.NFE, ref="r-nfe"))
    post = stub.calls("POST", "/v2/nfe")[0]
    assert post.url.params["ref"] == "r-nfe"
    body = stub.body(post)
    assert body["cnpj_emitente"] == CNPJ and body["valor_total"] == 1500.0
    assert body["items"][0]["codigo_ncm"] == "49111090" and body["items"][0]["valor_bruto"] == 1500.0
    assert result.status is InvoiceStatus.AUTHORIZED
    assert result.access_key == "41190612345678000123550010000000221923094166"  # "NFe" prefix stripped
    assert result.pdf_url == "https://homologacao.focusnfe.com.br/arquivos/x/danfe.pdf"
    assert (result.number, result.series) == ("22", "1")


def test_issue_nfse_nacional_uses_nfsen(make_focus, stub):
    stub.routes[("GET", "/v2/empresas/123")] = (200, COMPANY_BODY_NACIONAL)
    stub.routes[("POST", "/v2/nfsen")] = (202, {"cnpj_prestador": CNPJ, "ref": "org-ord1-nfse-1", "status": "processando_autorizacao"})
    result = make_focus().issue(sample_request(ref="org-ord1-nfse-1"))
    assert result.status is InvoiceStatus.PROCESSING
    body = stub.body(stub.calls("POST", "/v2/nfsen")[0])
    assert body["cnpj_prestador"] == CNPJ and body["cpf_tomador"] == "12345678909"
    assert body["codigo_tributacao_nacional_iss"] == "0107" and body["valor_servico"] == 1500.0
    assert body["codigo_municipio_emissora"] == "3550308"


def test_issue_nfse_municipal_uses_nfse_and_ibs_fields(make_focus, stub):
    stub.routes[("GET", "/v2/empresas/123")] = (200, COMPANY_BODY_MUNICIPAL)
    stub.routes[("POST", "/v2/nfse")] = (201, {"cnpj_prestador": CNPJ, "ref": "org-ord1-nfse-1", "status": "processando_autorizacao"})
    make_focus().issue(sample_request())
    body = stub.body(stub.calls("POST", "/v2/nfse")[0])
    assert body["prestador"] == {"cnpj": CNPJ, "inscricao_municipal": "123456", "codigo_municipio": "3550308"}
    assert body["tomador"]["cpf"] == "12345678909" and body["tomador"]["endereco"]["uf"] == "SP"
    servico = body["servico"]
    assert servico["valor_servicos"] == 1500.0 and servico["aliquota"] == 0.05
    assert servico["codigo_nbs"] == "1.0101.10.00" and servico["ibs_cbs_classificacao_tributaria"] == "000001"
    assert body["optante_simples_nacional"] is True


def test_ibs_cbs_passthrough(make_focus, stub):
    stub.routes[("GET", "/v2/empresas/123")] = (200, COMPANY_BODY_MUNICIPAL)
    stub.routes[("POST", "/v2/nfse")] = (201, {"ref": "x", "status": "processando_autorizacao"})
    req = sample_request()
    from dataclasses import replace

    make_focus().issue(replace(req, ibs_cbs={"ibs_cbs_situacao_tributaria": "000", "cbs_aliquota": 0.9}))
    servico = stub.body(stub.calls("POST", "/v2/nfse")[0])["servico"]
    assert servico["ibs_cbs_situacao_tributaria"] == "000" and servico["cbs_aliquota"] == 0.9


def test_issue_validation_error_is_a_rejection_with_reasons(make_focus, stub):
    stub.routes[("GET", "/v2/empresas/123")] = (200, COMPANY_BODY_MUNICIPAL)
    stub.routes[("POST", "/v2/nfse")] = (422, {
        "codigo": "erro_validacao_schema", "mensagem": "Erro",
        "erros": [{"mensagem": "Tipo documento nao pode ser vazio", "campo": "tipo_documento"}],
    })
    result = make_focus().issue(sample_request())
    assert result.status is InvoiceStatus.REJECTED
    assert result.rejection_reasons == ["Tipo documento nao pode ser vazio"]


@pytest.mark.parametrize("code", ["already_processed", "pending_operation", "nfe_autorizada"])
def test_reissue_same_ref_is_idempotent_via_get(make_focus, stub, code):
    stub.routes[("GET", "/v2/empresas/123")] = (200, COMPANY_BODY_NACIONAL)
    stub.routes[("POST", "/v2/nfe")] = (422, {"codigo": code, "mensagem": "ja existe"})
    stub.routes[("GET", "/v2/nfe/r-nfe")] = (200, NFE_AUTHORIZED)
    assert make_focus().issue(sample_request(InvoiceKind.NFE, ref="r-nfe")).status is InvoiceStatus.AUTHORIZED


def test_issue_permission_denied_and_bad_request_raise(make_focus, stub):
    stub.routes[("GET", "/v2/empresas/123")] = (200, COMPANY_BODY_NACIONAL)
    stub.routes[("POST", "/v2/nfe")] = (422, {"codigo": "permissao_negada", "mensagem": "CNPJ do emitente nao autorizado."})
    with pytest.raises(InvoiceProviderError) as exc:
        make_focus().issue(sample_request(InvoiceKind.NFE))
    assert exc.value.code == "permissao_negada"
    stub.routes[("POST", "/v2/nfe")] = (400, {"codigo": "requisicao_invalida", "mensagem": 'Parametro "ref" nao informado.'})
    with pytest.raises(InvoiceProviderError) as exc:
        make_focus().issue(sample_request(InvoiceKind.NFE))
    assert exc.value.code == "requisicao_invalida"


# ── get / status mapping ─────────────────────────────────────────────

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("processando_autorizacao", InvoiceStatus.PROCESSING),
        ("autorizado", InvoiceStatus.AUTHORIZED),
        ("cancelado", InvoiceStatus.CANCELLED),
        ("erro_autorizacao", InvoiceStatus.REJECTED),
    ],
)
def test_status_mapping(make_focus, stub, raw, expected):
    stub.routes[("GET", "/v2/nfe/r")] = (200, {"ref": "r", "status": raw})
    assert make_focus().get(InvoiceKind.NFE, "r").status is expected


def test_unknown_status_raises_never_pending(make_focus, stub):
    stub.routes[("GET", "/v2/nfe/r")] = (200, {"ref": "r", "status": "estado_novo"})
    with pytest.raises(InvoiceProviderError) as exc:
        make_focus().get(InvoiceKind.NFE, "r")
    assert exc.value.code == "unknown_status"
    stub.routes[("GET", "/v2/nfe/r")] = (200, {"ref": "r"})
    with pytest.raises(InvoiceProviderError):
        make_focus().get(InvoiceKind.NFE, "r")


def test_404_is_invoice_not_found(make_focus, stub):
    with pytest.raises(InvoiceNotFound):
        make_focus().get(InvoiceKind.NFE, "ghost")
    with pytest.raises(InvoiceNotFound):
        make_focus().get(InvoiceKind.NFSE, "ghost")
    assert [r.url.path for r in stub.requests[1:]] == ["/v2/nfsen/ghost", "/v2/nfse/ghost"]


def test_get_nfse_probes_both_channels_after_cutover(make_focus, stub):
    stub.routes[("GET", "/v2/nfse/org-ord1-nfse-1")] = (200, NFSE_AUTHORIZED)  # issued when municipal
    result = make_focus().get(InvoiceKind.NFSE, "org-ord1-nfse-1")
    assert result.status is InvoiceStatus.AUTHORIZED and result.verification_code == "ABC123"
    assert result.pdf_url.startswith("https://focusnfe.s3") and result.xml_url.endswith("/arquivos/x/nfse.xml")


def test_rejected_get_carries_reasons(make_focus, stub):
    stub.routes[("GET", "/v2/nfse/r")] = (200, {
        "ref": "r", "status": "erro_autorizacao",
        "erros": [{"codigo": "L99", "mensagem": "Regime Especial de Tributacao ausente/invalido", "correcao": "Corrija o Regime"}],
    })
    result = make_focus().get(InvoiceKind.NFSE, "r")
    assert result.status is InvoiceStatus.REJECTED
    assert result.rejection_reasons == ["Regime Especial de Tributacao ausente/invalido (Corrija o Regime)"]


def test_raw_is_scrubbed(make_focus, stub):
    stub.routes[("GET", "/v2/nfe/r")] = (200, {"ref": "r", "status": "autorizado", "token": "leaky", "x": COMPANY_TOKEN})
    raw = make_focus().get(InvoiceKind.NFE, "r").raw
    assert "leaky" not in str(raw) and COMPANY_TOKEN not in str(raw)


# ── cancel ───────────────────────────────────────────────────────────

REASON = "Cancelamento a pedido do cliente"


def test_cancel_by_ref_with_justificativa(make_focus, stub):
    state = {"cancelled": False}
    stub.routes[("GET", "/v2/nfe/r-nfe")] = lambda req: (200, {**NFE_AUTHORIZED, "status": "cancelado"} if state["cancelled"] else NFE_AUTHORIZED)

    def delete(req):
        state["cancelled"] = True
        return 200, {"status": "cancelado", "status_sefaz": "135"}

    stub.routes[("DELETE", "/v2/nfe/r-nfe")] = delete
    result = make_focus().cancel(InvoiceKind.NFE, "r-nfe", reason=REASON)
    assert result.status is InvoiceStatus.CANCELLED
    assert stub.body(stub.calls("DELETE", "/v2/nfe/r-nfe")[0]) == {"justificativa": REASON}


def test_cancel_nfse_goes_to_the_channel_that_holds_the_doc(make_focus, stub):
    stub.routes[("GET", "/v2/nfse/r")] = (200, {**NFSE_AUTHORIZED, "ref": "r"})
    stub.routes[("DELETE", "/v2/nfse/r")] = (200, {"status": "cancelado"})
    make_focus().cancel(InvoiceKind.NFSE, "r", reason=REASON)
    assert stub.calls("DELETE", "/v2/nfse/r") and not stub.calls("DELETE", "/v2/nfsen/r")


def test_cancel_refusal_raises_with_reasons(make_focus, stub):
    stub.routes[("GET", "/v2/nfse/r")] = (200, {**NFSE_AUTHORIZED, "ref": "r"})
    stub.routes[("DELETE", "/v2/nfse/r")] = (200, {"status": "erro_cancelamento", "erros": [{"codigo": "V999", "mensagem": "NFSe fora do prazo de cancelamento permitido"}]})
    with pytest.raises(InvoiceProviderError) as exc:
        make_focus().cancel(InvoiceKind.NFSE, "r", reason=REASON)
    assert exc.value.code == "cancel_refused" and exc.value.reasons == ["NFSe fora do prazo de cancelamento permitido"]


def test_cancel_rules(make_focus, stub):
    focus = make_focus()
    with pytest.raises(InvoiceProviderError) as exc:
        focus.cancel(InvoiceKind.NFE, "r", reason="curto")
    assert exc.value.code == "justificativa_invalida"
    stub.routes[("GET", "/v2/nfe/p")] = (200, {"ref": "p", "status": "processando_autorizacao"})
    with pytest.raises(InvoiceProviderError) as exc:
        focus.cancel(InvoiceKind.NFE, "p", reason=REASON)
    assert exc.value.code == "em_processamento"
    stub.routes[("GET", "/v2/nfe/e")] = (200, {"ref": "e", "status": "erro_autorizacao"})
    with pytest.raises(InvoiceProviderError) as exc:
        focus.cancel(InvoiceKind.NFE, "e", reason=REASON)
    assert exc.value.code == "nao_autorizada"
    stub.routes[("GET", "/v2/nfe/c")] = (200, {"ref": "c", "status": "cancelado"})
    assert focus.cancel(InvoiceKind.NFE, "c", reason=REASON).status is InvoiceStatus.CANCELLED
    assert not stub.calls("DELETE", "/v2/nfe/c")  # already cancelled: no second DELETE
    with pytest.raises(InvoiceNotFound):
        focus.cancel(InvoiceKind.NFE, "ghost", reason=REASON)


# ── fetch_document ───────────────────────────────────────────────────

def test_fetch_document_allowlist_and_auth_scope(make_focus, stub):
    stub.routes[("GET", "/arquivos/x/danfe.pdf")] = (200, b"%PDF-bytes")
    focus = make_focus()
    assert focus.fetch_document("/arquivos/x/danfe.pdf") == b"%PDF-bytes"
    assert stub.requests[0].headers["Authorization"] == basic(ACCOUNT_TOKEN)
    for bad in ("https://evil.example.com/a.pdf", "http://api.focusnfe.com.br/a.pdf", "file:///etc/passwd"):
        with pytest.raises(InvoiceProviderError) as exc:
            focus.fetch_document(bad)
        assert exc.value.code == "url_nao_permitida"


def test_fetch_document_s3_gets_no_credentials(make_focus):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("Authorization")
        return httpx.Response(200, content=b"pdf")

    from noctusai_lib.integrations.invoices import FocusNFeInvoiceProvider

    focus = FocusNFeInvoiceProvider(account_token=ACCOUNT_TOKEN, transport=httpx.MockTransport(handler))
    assert focus.fetch_document("https://focusnfe.s3.sa-east-1.amazonaws.com/arquivos/x/danfse.pdf") == b"pdf"
    assert seen["auth"] is None


# ── security review fixes ────────────────────────────────────────────

def test_provider_free_text_echoing_credentials_is_scrubbed(make_focus, stub):
    echo = basic(ACCOUNT_TOKEN) + " " + ACCOUNT_TOKEN
    stub.routes[("GET", "/v2/empresas")] = (400, {"codigo": "requisicao_invalida", "mensagem": echo})
    with pytest.raises(InvoiceProviderError) as exc:
        make_focus().verify_credentials()
    joined = " ".join(exc.value.reasons)
    assert ACCOUNT_TOKEN not in joined and base64.b64encode(f"{ACCOUNT_TOKEN}:".encode()).decode() not in joined


def test_company_token_echo_in_cancel_refusal_is_scrubbed(make_focus, stub):
    b64 = base64.b64encode(f"{COMPANY_TOKEN}:".encode()).decode()
    stub.routes[("GET", "/v2/nfse/r")] = (200, {**NFSE_AUTHORIZED, "ref": "r"})
    stub.routes[("DELETE", "/v2/nfse/r")] = (200, {"status": "erro_cancelamento", "erros": [{"mensagem": f"Basic {b64}"}]})
    with pytest.raises(InvoiceProviderError) as exc:
        make_focus().cancel(InvoiceKind.NFSE, "r", reason="Cancelamento a pedido do cliente")
    assert b64 not in " ".join(exc.value.reasons)


def test_upload_failure_drops_provider_free_text(make_focus, stub, pfx_bundle):
    pfx, _ = pfx_bundle
    stub.routes[("PUT", "/v2/empresas/123")] = (400, {"codigo": "requisicao_invalida", "mensagem": base64.b64encode(pfx).decode()[:200]})
    with pytest.raises(InvoiceProviderError) as exc:
        make_focus().upload_certificate("123", pfx=pfx, password=PFX_PASSWORD)
    assert exc.value.reasons == [] and exc.value.code == "erro_provedor"


def test_upload_enforces_cnpj_size_and_password_in_the_organ(make_focus, stub, pfx_bundle):
    from noctusai_lib.integrations.invoices import InvoiceCertificateError
    from noctusai_lib.integrations.invoices.errors import InvoiceCertificateCnpjMismatch

    pfx, _ = pfx_bundle
    focus = make_focus()
    with pytest.raises(InvoiceCertificateCnpjMismatch) as exc:
        focus.upload_certificate("123", pfx=pfx, password=PFX_PASSWORD, expected_cnpj="99999999000199")
    assert exc.value.code == "certificado_cnpj_divergente"
    with pytest.raises(InvoiceCertificateError):
        focus.upload_certificate("123", pfx=b"x" * (64 * 1024 + 1), password="p")
    with pytest.raises(InvoiceCertificateError):
        focus.upload_certificate("123", pfx=pfx, password="p" * 129)
    assert stub.requests == []


@pytest.mark.parametrize("bad", ["../etc", "a/b", "a b", "", "x" * 65, "r?x=1", "r\n"])
def test_refs_are_validated_before_paths(make_focus, stub, bad):
    focus = make_focus()
    for call in (
        lambda: focus.get(InvoiceKind.NFE, bad),
        lambda: focus.cancel(InvoiceKind.NFSE, bad, reason="Cancelamento a pedido do cliente"),
        lambda: focus.set_nfse_mode(bad, NfseMode.NACIONAL),
    ):
        with pytest.raises(InvoiceProviderError) as exc:
            call()
        assert exc.value.code == "ref_invalido"
    assert stub.requests == []


def test_fetch_document_stream_cap_and_presigned_url_not_in_error(make_focus, stub):
    from noctusai_lib.integrations.invoices import focus as focus_mod

    big = b"x" * (focus_mod._MAX_DOCUMENT_BYTES + 1)
    stub.routes[("GET", "/arquivos/big.pdf")] = (200, big)
    with pytest.raises(InvoiceProviderError) as exc:
        make_focus().fetch_document("/arquivos/big.pdf")
    assert exc.value.code == "documento_grande"
    with pytest.raises(InvoiceNotFound) as nf:
        make_focus().fetch_document("https://focusnfe.s3.sa-east-1.amazonaws.com/a/gone.pdf?X-Amz-Signature=SIG")
    assert "SIG" not in nf.value.ref and "SIG" not in str(nf.value)

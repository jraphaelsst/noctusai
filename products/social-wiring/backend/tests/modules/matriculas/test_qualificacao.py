"""Migration 137 — matrícula party qualification feeding the existing
`identidade_extracao_service` suggest/confirm/apply pipeline.

Every CPF below is a synthetic, check-digit-valid value (reused verbatim
from `seed/lib/backend/tests/integrations/documents/
test_matricula_qualificacao.py`'s own fixtures — `_cpf_sintetico("222333444")`
/ `_cpf_sintetico("666777888")`); every name is invented.
"""
from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID, uuid4

from app.modules.matriculas import estrutura_service as svc
from app.modules.matriculas import qualificacao_service as qsvc
from tests.modules.matriculas.conftest import ORG_ID, extracao_row, seed

CPF_JOSE = "222.333.444-05"
CPF_CAMILA = "666.777.888-30"

TEXTO_QUALIFICACAO = (
    "MATRÍCULA Nº 90.111 — FICHA 01\n"
    "IMÓVEL: Casa ficticia nº 9 da Rua dos Exemplos, Cotia.\n"
    "R-1/90.111 - Em 01/02/2021. COMPRA E VENDA. Por escritura pública de compra "
    "e venda, o imóvel foi vendido a JOSÉ EXEMPLO LIMA, brasileiro, casado, "
    "comerciante, portador da cédula de identidade, RG nº 11.222.333 e inscrito "
    f"no CPF/MF nº {CPF_JOSE}, residente e domiciliado na Rua Fictícia, nº 45, "
    "Cotia-SP.\n"
    "R-2/90.111 - Em 10/03/2022. VENDA. Por escritura pública, JOSÉ EXEMPLO "
    "LIMA, já qualificado, vendeu o imóvel a CAMILA EXEMPLO BRITO, brasileira, "
    "solteira, arquiteta, RG nº 66.777.888-SSP/SP, CPF nº "
    f"{CPF_CAMILA}, residente e domiciliada na Avenida Modelo, nº 90, "
    "Cotia-SP.\n"
)


def cliente_row(*, cpf: str, **extra) -> dict:
    row = {
        "id": str(uuid4()),
        "org_id": ORG_ID,
        "nome_completo": "Registro existente",
        "cpf": cpf,
    }
    row.update(extra)
    return row


def _data(resp):
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _atos(client, ext_id):
    return _data(client.get(f"/api/matriculas/extracoes/{ext_id}/atos"))


def _por_cpf(qualificacoes):
    return {q["cpf_cnpj"]: q for q in qualificacoes}


def _logs(scoped, acao):
    return [
        r for r in scoped.table("imovel_documento_acessos").inserted_payloads
        if r["acao"] == acao
    ]


# ─── segmentation mints one row per consolidated person ────────────────────


class TestTheListingCarriesQualificacoes:
    def test_two_acts_two_people_one_matched_one_not(self, client, scoped):
        ext = extracao_row(texto=TEXTO_QUALIFICACAO)
        cliente_jose = cliente_row(cpf=CPF_JOSE)
        seed(scoped, extracoes=[ext], clientes=[cliente_jose])

        qualificacoes = _atos(client, ext["id"])["qualificacoes"]
        por_cpf = _por_cpf(qualificacoes)

        jose = por_cpf[CPF_JOSE]
        assert jose["nome"] == "JOSÉ EXEMPLO LIMA"
        assert jose["nacionalidade"] == "brasileiro"
        assert jose["estado_civil"] == "casado"
        assert jose["profissao"] == "comerciante"
        assert jose["rg"] == "11.222.333"
        assert jose["genero"] == "m"
        assert jose["confianca"] == "alta"
        assert jose["vinculo_status"] == "vinculado"
        assert jose["cliente_id"] == cliente_jose["id"]
        # `origem[campo]` is the `matricula_atos.id` that first supplied it
        # (an addressable act, not a friendly label) — every field here came
        # off R-1, the only act José appears in.
        r1_id = [
            a["id"] for a in scoped.table("matricula_atos").select("*").execute().data
            if a["kind"] == "R" and a["numero"] == 1
        ][0]
        assert jose["origem"]["nome"] == r1_id

        camila = por_cpf[CPF_CAMILA]
        assert camila["nome"] == "CAMILA EXEMPLO BRITO"
        assert camila["rg_orgao_expedidor"] == "SSP/SP"
        assert camila["vinculo_status"] == "sem_correspondencia"
        assert camila["cliente_id"] is None
        assert camila["confirmado_por"] is None
        assert camila["descartado_em"] is None

    def test_endereco_is_shown_but_never_a_campo(self, client, scoped):
        ext = extracao_row(texto=TEXTO_QUALIFICACAO)
        seed(scoped, extracoes=[ext])

        qualificacoes = _atos(client, ext["id"])["qualificacoes"]

        assert _por_cpf(qualificacoes)[CPF_CAMILA]["endereco"] == (
            "Avenida Modelo, nº 90, Cotia-SP"
        )
        assert "endereco" not in [c.item_key for c in qsvc.CAMPOS_QUALIFICACAO]

    def test_ambiguous_cpf_is_never_auto_picked(self, client, scoped):
        ext = extracao_row(texto=TEXTO_QUALIFICACAO)
        dois = [cliente_row(cpf=CPF_JOSE), cliente_row(cpf=CPF_JOSE)]
        seed(scoped, extracoes=[ext], clientes=dois)

        jose = _por_cpf(_atos(client, ext["id"])["qualificacoes"])[CPF_JOSE]

        assert jose["vinculo_status"] == "ambiguo"
        assert jose["cliente_id"] is None

    def test_one_text_view_log_covers_qualificacoes_too(self, client, scoped):
        ext = extracao_row(texto=TEXTO_QUALIFICACAO)
        seed(scoped, extracoes=[ext])

        _atos(client, ext["id"])

        assert len(_logs(scoped, "text_view")) == 1

    def test_qualificacoes_are_minted_at_segmentation(self, scoped):
        # Unlike `ato_detalhes_service.persistir_sugestoes` (pure string
        # slicing), this source also SELECTs `clientes` for the CPF match —
        # `RecordingDB` (the background job's minimal fake elsewhere in this
        # suite) has no real query support, so this needs the real
        # `MockSupabaseClient` fixture instead.
        seed(scoped)
        extracao_id = str(uuid4())

        svc.persistir_atos(scoped, extracao_id, ORG_ID, TEXTO_QUALIFICACAO)

        linhas = scoped.table("matricula_qualificacoes").inserted_payloads
        assert {r["cpf_cnpj"] for r in linhas} == {CPF_JOSE, CPF_CAMILA}
        assert all(r["confianca"] == "alta" for r in linhas)

    def test_missing_qualificacoes_are_backfilled_on_read(self, client, scoped):
        ext = extracao_row(texto=TEXTO_QUALIFICACAO)
        seed(scoped, extracoes=[ext])
        _atos(client, ext["id"])
        atos_existentes = scoped.table("matricula_atos").select("*").execute().data
        # Acts segmented before migration 137: rows exist, qualificações do not.
        seed(scoped, extracoes=[ext], atos=atos_existentes, qualificacoes=[])

        qualificacoes = _atos(client, ext["id"])["qualificacoes"]

        assert {q["cpf_cnpj"] for q in qualificacoes} == {CPF_JOSE, CPF_CAMILA}
        assert scoped.table("matricula_atos").inserted_payloads == []


# ─── auto-apply-on-vincular: fill-empty with provenance (D1, migration 153) ─
#
# The REGINA case: a qualificação `vinculado` to a cliente used to sit there
# doing nothing to `clientes` until a human clicked `confirmar` — nobody had
# to, so the profissão never reached the contract gate. `persistir_sugestoes`
# now runs `_aplicar_automatico` on every freshly-`vinculado` row, machine-
# pending (`confirmado_por=None`), the SAME mechanics `confirmar` already
# used — see `qualificacao_service`'s own module docstring.


class TestAutoApplyOnVincular:
    def test_fill_empty_applies_before_any_human_confirms(self, client, scoped):
        ext = extracao_row(texto=TEXTO_QUALIFICACAO)
        cliente_jose = cliente_row(cpf=CPF_JOSE)
        seed(scoped, extracoes=[ext], clientes=[cliente_jose])

        _atos(client, ext["id"])  # segmentation -> persistir_sugestoes -> auto-apply

        cliente_atual = (
            scoped.table("clientes").select("*").eq("id", cliente_jose["id"]).execute().data[0]
        )
        assert cliente_atual["nacionalidade"] == "brasileiro"
        assert cliente_atual["nacionalidade_origem"] == "matricula"
        assert cliente_atual["profissao"] == "comerciante"
        assert cliente_atual["estado_civil"] == "casado"
        assert cliente_atual["rg"] == "11.222.333"
        # Migration 153's gender canonicalisation applies here exactly like
        # it does on `confirmar` — see `_lidos`' own comment.
        assert cliente_atual["genero"] == "Masculino"
        # Machine-pending — nobody has looked at it yet.
        assert cliente_atual["profissao_confirmado_por"] is None
        assert cliente_atual["profissao_confirmado_em"] is None

    def test_a_disagreeing_field_opens_a_conflict_and_never_overwrites(self, client, scoped):
        ext = extracao_row(texto=TEXTO_QUALIFICACAO)
        cliente_jose = cliente_row(
            cpf=CPF_JOSE, estado_civil="divorciado", estado_civil_origem="manual"
        )
        seed(scoped, extracoes=[ext], clientes=[cliente_jose])

        jose = _por_cpf(_atos(client, ext["id"])["qualificacoes"])[CPF_JOSE]

        cliente_atual = (
            scoped.table("clientes").select("*").eq("id", cliente_jose["id"]).execute().data[0]
        )
        assert cliente_atual["estado_civil"] == "divorciado"  # never overwritten
        assert cliente_atual["profissao"] == "comerciante"  # every OTHER field still fills

        conflito = (
            scoped.table("cliente_campo_conflitos")
            .select("*")
            .eq("cliente_id", cliente_jose["id"])
            .execute()
            .data[0]
        )
        assert conflito["campo"] == "estado_civil"
        assert conflito["valor_anterior"] == "divorciado"
        assert conflito["valor_proposto"] == "casado"
        assert conflito["origem_proposto"] == "matricula"
        assert conflito["fonte_tabela"] == "matricula_qualificacoes"
        assert conflito["fonte_id"] == jose["id"]
        assert conflito["status"] == "pendente"

    def test_an_unmatched_qualificacao_applies_nothing(self, client, scoped):
        ext = extracao_row(texto=TEXTO_QUALIFICACAO)
        seed(scoped, extracoes=[ext])  # no clientes -> both rows unmatched

        _atos(client, ext["id"])

        assert scoped.table("clientes").select("*").execute().data == []
        assert scoped.table("cliente_campo_conflitos").select("*").execute().data == []


class TestBackfillAplicarCamposVinculados:
    """The catch-up for a `vinculado` row written before the hook above
    existed — a legacy row seeded directly (bypassing `persistir_sugestoes`
    entirely), never touched by segmentation."""

    def _linha_legado(self, cliente_id: str) -> dict:
        return {
            "id": str(uuid4()),
            "org_id": ORG_ID,
            "extracao_id": str(uuid4()),
            "cpf_cnpj": CPF_JOSE,
            "cpf_cnpj_normalizado": "22233344405",
            "nome": "JOSÉ EXEMPLO LIMA",
            "nacionalidade": "brasileiro",
            "estado_civil": "casado",
            "profissao": "comerciante",
            "rg": "11.222.333",
            "rg_orgao_expedidor": None,
            "endereco": "Rua Fictícia, nº 45, Cotia-SP",
            "genero": "m",
            "confianca": "alta",
            "origem": {},
            "cliente_id": cliente_id,
            "vinculo_status": qsvc.VINCULADO,
            "confirmado_por": None,
            "confirmado_em": None,
            "aplicado_campos": None,
            "descartado_por": None,
            "descartado_em": None,
        }

    def test_backfills_a_legacy_vinculado_row(self, scoped):
        cliente_jose = cliente_row(cpf=CPF_JOSE)
        seed(scoped, clientes=[cliente_jose], qualificacoes=[self._linha_legado(cliente_jose["id"])])

        resultado = qsvc.backfill_aplicar_campos_vinculados(scoped, ORG_ID)

        assert resultado["linhas_vinculadas"] == 1
        assert resultado["aplicados"] > 0
        assert resultado["conflitos_abertos"] == 0
        cliente_atual = (
            scoped.table("clientes").select("*").eq("id", cliente_jose["id"]).execute().data[0]
        )
        assert cliente_atual["profissao"] == "comerciante"
        assert cliente_atual["profissao_origem"] == "matricula"
        assert cliente_atual["profissao_confirmado_por"] is None

    def test_rerunning_the_backfill_is_a_true_no_op(self, scoped):
        cliente_jose = cliente_row(cpf=CPF_JOSE)
        seed(scoped, clientes=[cliente_jose], qualificacoes=[self._linha_legado(cliente_jose["id"])])

        primeiro = qsvc.backfill_aplicar_campos_vinculados(scoped, ORG_ID)
        segundo = qsvc.backfill_aplicar_campos_vinculados(scoped, ORG_ID)

        assert primeiro["aplicados"] > 0
        assert segundo == {"linhas_vinculadas": 1, "aplicados": 0, "conflitos_abertos": 0}

    def test_rerunning_after_a_conflict_never_opens_a_second_one(self, scoped):
        cliente_jose = cliente_row(
            cpf=CPF_JOSE, estado_civil="divorciado", estado_civil_origem="manual"
        )
        seed(scoped, clientes=[cliente_jose], qualificacoes=[self._linha_legado(cliente_jose["id"])])

        primeiro = qsvc.backfill_aplicar_campos_vinculados(scoped, ORG_ID)
        segundo = qsvc.backfill_aplicar_campos_vinculados(scoped, ORG_ID)

        assert primeiro["conflitos_abertos"] == 1
        assert segundo["conflitos_abertos"] == 0
        conflitos = scoped.table("cliente_campo_conflitos").select("*").execute().data
        assert len(conflitos) == 1
        cliente_atual = (
            scoped.table("clientes").select("*").eq("id", cliente_jose["id"]).execute().data[0]
        )
        assert cliente_atual["estado_civil"] == "divorciado"  # never overwritten


# ─── PUT /qualificacoes/{id}/confirmar ──────────────────────────────────────


class TestConfirming:
    def _preparar(self, client, scoped, *, cliente_extra=None):
        ext = extracao_row(texto=TEXTO_QUALIFICACAO)
        cliente_jose = cliente_row(cpf=CPF_JOSE, **(cliente_extra or {}))
        seed(scoped, extracoes=[ext], clientes=[cliente_jose])
        jose = _por_cpf(_atos(client, ext["id"])["qualificacoes"])[CPF_JOSE]
        return ext, cliente_jose, jose

    def test_confirming_applies_every_field_onto_the_matched_cliente(
        self, client, scoped
    ):
        _ext, cliente_jose, jose = self._preparar(client, scoped)

        resp = _data(client.put(f"/api/matriculas/qualificacoes/{jose['id']}/confirmar"))

        assert resp["confirmado_por"] is not None
        assert resp["aplicado_campos"]["nacionalidade"] is True
        assert resp["aplicado_campos"]["profissao"] is True
        assert resp["aplicado_campos"]["estado_civil"] is True
        assert resp["aplicado_campos"]["rg"] is True
        assert resp["aplicado_campos"]["genero"] is True

        cliente_atual = (
            scoped.table("clientes")
            .select("*")
            .eq("id", cliente_jose["id"])
            .execute()
            .data[0]
        )
        assert cliente_atual["nacionalidade"] == "brasileiro"
        assert cliente_atual["nacionalidade_origem"] == "matricula"
        assert cliente_atual["profissao"] == "comerciante"
        assert cliente_atual["estado_civil"] == "casado"
        assert cliente_atual["rg"] == "11.222.333"
        # Migration 153: the matrícula's `m` code is canonicalised to the word
        # `clientes.genero` holds everywhere else — writing the code made
        # every later RG/CIN reading of the same fact look like a conflict.
        assert cliente_atual["genero"] == "Masculino"
        # A human confirmed this reading, so the fields land VALIDATED, not
        # machine-pending for the contract gate.
        assert cliente_atual["nacionalidade_confirmado_por"] is not None
        assert cliente_atual["nacionalidade_confirmado_em"] is not None

    def test_confirming_never_overwrites_an_existing_value(
        self, client, scoped, fake_notification_service
    ):
        """`_preparar`'s own GET .../atos already triggers the auto-apply-
        on-vincular hook (`persistir_sugestoes` -> `_aplicar_automatico`,
        see `TestAutoApplyOnVincular`), so the conflict this test is about
        is ALREADY open by the time `confirmar` runs — `confirmar` finds it
        pending (`_conflito_pendente_existente`) and opens no SECOND one:
        `conflitos_abertos` for THIS call is empty, and `estado_civil`
        stays declined/unapplied either way."""
        _ext, cliente_jose, jose = self._preparar(
            client, scoped, cliente_extra={"estado_civil": "divorciado", "estado_civil_origem": "manual"}
        )

        resp = _data(client.put(f"/api/matriculas/qualificacoes/{jose['id']}/confirmar"))

        assert resp["aplicado_campos"]["estado_civil"] is False
        assert resp["conflitos_abertos"] == []
        cliente_atual = (
            scoped.table("clientes")
            .select("*")
            .eq("id", cliente_jose["id"])
            .execute()
            .data[0]
        )
        assert cliente_atual["estado_civil"] == "divorciado"

        conflitos = (
            scoped.table("cliente_campo_conflitos")
            .select("*")
            .eq("cliente_id", cliente_jose["id"])
            .execute()
            .data
        )
        assert len(conflitos) == 1  # confirming never opens a second one
        conflito = conflitos[0]
        assert conflito["valor_anterior"] == "divorciado"
        assert conflito["valor_proposto"] == "casado"
        assert conflito["origem_proposto"] == "matricula"
        assert conflito["fonte_tabela"] == "matricula_qualificacoes"
        assert conflito["fonte_id"] == jose["id"]
        assert conflito["status"] == "pendente"

    def test_confirming_without_a_match_stamps_but_applies_nothing(self, client, scoped):
        ext = extracao_row(texto=TEXTO_QUALIFICACAO)
        seed(scoped, extracoes=[ext])
        camila = _por_cpf(_atos(client, ext["id"])["qualificacoes"])[CPF_CAMILA]

        resp = _data(client.put(f"/api/matriculas/qualificacoes/{camila['id']}/confirmar"))

        assert resp["confirmado_por"] is not None
        assert resp["aplicado_campos"] == {}

    def test_confirming_a_discarded_suggestion_is_a_422(self, client, scoped):
        _ext, _cliente, jose = self._preparar(client, scoped)
        client.put(f"/api/matriculas/qualificacoes/{jose['id']}/descartar")

        resp = client.put(f"/api/matriculas/qualificacoes/{jose['id']}/confirmar")

        assert resp.status_code == 400

    def test_an_unknown_qualificacao_is_a_404(self, client, scoped):
        seed(scoped)
        resp = client.put(f"/api/matriculas/qualificacoes/{uuid4()}/confirmar")
        assert resp.status_code == 404


# ─── PUT /qualificacoes/{id}/descartar ──────────────────────────────────────


class TestDescarting:
    def test_discarding_keeps_the_reading(self, client, scoped):
        ext = extracao_row(texto=TEXTO_QUALIFICACAO)
        seed(scoped, extracoes=[ext])
        camila = _por_cpf(_atos(client, ext["id"])["qualificacoes"])[CPF_CAMILA]

        resp = _data(client.put(f"/api/matriculas/qualificacoes/{camila['id']}/descartar"))
        assert resp["descartado_por"] is not None

        de_novo = _por_cpf(_atos(client, ext["id"])["qualificacoes"])[CPF_CAMILA]
        assert de_novo["descartado_em"] is not None
        assert de_novo["nome"] == "CAMILA EXEMPLO BRITO"  # the reading survives


# ─── retention purge ─────────────────────────────────────────────────────


def test_purging_the_text_purges_the_qualificacoes_read_from_it(scoped):
    ext = extracao_row(texto=TEXTO_QUALIFICACAO)
    seed(
        scoped,
        extracoes=[ext],
        qualificacoes=[
            {
                "id": str(uuid4()),
                "org_id": ORG_ID,
                "extracao_id": ext["id"],
                "cpf_cnpj": CPF_JOSE,
                "cpf_cnpj_normalizado": "22233344405",
                "nome": "JOSÉ EXEMPLO LIMA",
                "confianca": "alta",
                "vinculo_status": "sem_correspondencia",
            }
        ],
    )

    scoped.table("matricula_extracoes").update(
        {"retencao_ate": (date.today() - timedelta(days=1)).isoformat()}
    ).eq("id", ext["id"]).execute()

    svc.purgar_texto_expirado(scoped, UUID(ORG_ID))

    restantes = (
        scoped.table("matricula_qualificacoes")
        .select("*")
        .eq("extracao_id", ext["id"])
        .execute()
        .data
    )
    assert restantes == []

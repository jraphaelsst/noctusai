"""endereco-portaria-vs-imovel: the posse clause prints the REGISTRY address,
never the CRM/Vista mirror's público endereço.

🔴 THE BUSINESS RULE THESE PIN
--------------------------------
At least one tenant deliberately publishes the PORTARIA (gatehouse) address
in `imoveis.endereco`/`.numero` — visible to agents outside the firm — and
keeps the real property address only on the matrícula. Under that rule the
public street DIVERGING from the matrícula is the EXPECTED state, so the
coherence check below only ever `avisa` (owner-approved, never blocks); the
posse clauses must still print the matrícula's own address, never the CRM's.

WHAT THESE PIN
--------------
1. The posse clause carries the matrícula-derived address, not the CRM's
   público street, when they differ.
2. A street mismatch produces an `aviso`; `pronto` stays `True` — the
   divergence never blocks.
3. An area mismatch WITHIN tolerance (the reference case: 1052 vs 1.050,24 —
   1,76 m² apart) produces NO `aviso`.
4. An area mismatch BEYOND tolerance DOES `aviso` — proving the check is
   live, not merely inert.
5. NEGATIVE CONTROL: a genuinely different imóvel (mismatched matrícula
   número) still trips `MATRICULA_DE_OUTRO_IMOVEL` and blocks — the
   street-divergence tolerance above must never soften this.
6. No derivable registry address at all (no override, no "situado à..."
   phrase in the matrícula quote) REFUSES generation
   (`imovel.endereco_registro_texto` faltando) rather than falling back to
   the CRM's público endereço.
7. The INSTRUMENT'S OWN TITLE (`imovel.titulo_curto`, `modelo_texto.
   TEMPLATE`'s opening line) carries `empreendimento` when present, the
   SAME registry-derived address the posse clauses print when it is not —
   NEVER the CRM's público street in either branch — and refuses when
   neither `empreendimento` nor a registry address is available. This is
   the branch `ONE7515` never exercised (it happens to carry an
   `empreendimento`): every OTHER property falls through to it.

All names, streets and matrícula numbers are invented — nothing here is
copied from a real CRM or matrícula.
"""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from app.modules.card_hub.contrato_gerador import contexto as contexto_mod
from app.modules.card_hub.contrato_gerador import derivacao, documento
from app.modules.card_hub.contrato_gerador.numeracao import ContadorParagrafos
from noctusai_lib.integrations.docx_render import get_docx_render_adapter
from tests.modules.card_hub import contrato_gerador_fixtures as fx

#: The matrícula's OWN address ("Alameda Fictícia, nº 535") — deliberately a
#: DIFFERENT street from `fx.endereco()`'s "Rua das Amostras" (the CRM/Vista
#: mirror's público endereço every `base_v1()` party/imóvel carries by
#: default) — and a "1.050,24m²" area, the reference tolerance shape.
MATRICULA_TEXTO_COM_ENDERECO_DO_REGISTRO = (
    "MATRÍCULA Nº 12.345 - IMÓVEL: Um apartamento situado na Alameda Fictícia, "
    "nº 535, Bairro Modelo, com área total de 1.050,24m².\n"
    "R.1/12.345 - Prot. 1.000 - Por escritura pública, o imóvel foi transmitido a FULANO DE TAL."
)

#: A matrícula quote with no "situado à/na/no" marker at all — nothing to
#: derive an address FROM.
MATRICULA_TEXTO_SEM_MARCADOR_DE_ENDERECO = (
    "MATRÍCULA Nº 12.345 - IMÓVEL: Um apartamento do Edifício Exemplo, com "
    "área privativa de 80,00m2.\n"
    "R.1/12.345 - Prot. 1.000 - Por escritura pública, o imóvel foi transmitido a FULANO DE TAL."
)


def _com_matricula_de_registro(*, area_crm=None):
    d = fx.base_v1()
    d = replace(d, matricula=replace(d.matricula, texto=MATRICULA_TEXTO_COM_ENDERECO_DO_REGISTRO))
    if area_crm is not None:
        d = replace(d, imovel=replace(d.imovel, area_total=area_crm))
    return d


def _avaliar(d):
    pol = fx.politica_variante(1)
    sw = derivacao.derivar_switches(d, pol)
    return pol, sw, derivacao.avaliar(d, sw, pol, fx.ASSINATURA)


def _render(d):
    pol, sw, av = _avaliar(d)
    assert av.pronto, (av.faltando, av.bloqueios)
    return documento.renderizar(get_docx_render_adapter(real=True), d, sw, pol, fx.ASSINATURA)


def _contexto(d):
    pol, sw, av = _avaliar(d)
    assert av.pronto, (av.faltando, av.bloqueios)
    adapter = get_docx_render_adapter(real=True)
    return contexto_mod.montar_contexto(d, sw, pol, fx.ASSINATURA, ContadorParagrafos(None), adapter)


class TestPosseClauseUsaEnderecoDoRegistro:
    def test_a_clausula_de_posse_nao_contem_a_rua_da_portaria(self):
        d = _com_matricula_de_registro()
        # Sanity: the CRM's público endereço (the "portaria") really is a
        # DIFFERENT street from the matrícula's own — `base_v1()`'s imóvel
        # carries "Rua Fictícia" (the CRM mirror), the matrícula text this
        # fixture swaps in names "Alameda Fictícia" instead.
        assert d.imovel.endereco.logradouro == "Rua Fictícia"

        r = _render(d)
        texto = "\n".join(r.paragrafos)
        assert "Alameda Fictícia, nº 535" in texto
        assert "Rua Fictícia, nº 100" not in texto

    def test_um_desencontro_de_rua_gera_aviso_e_nao_bloqueia(self):
        d = _com_matricula_de_registro()
        _pol, _sw, av = _avaliar(d)
        assert av.pronto is True
        assert "ENDERECO_DIVERGENTE_DA_MATRICULA" in {a["codigo"] for a in av.avisos}


class TestCoerenciaDeArea:
    def test_um_desencontro_de_area_dentro_da_tolerancia_nao_gera_aviso(self):
        # The reference shape: CRM AreaTotal 1052 vs the matrícula's own
        # 1.050,24 — 1,76 m² apart, inside the tolerance.
        d = _com_matricula_de_registro(area_crm=Decimal("1052"))
        _pol, _sw, av = _avaliar(d)
        assert av.pronto is True
        assert "AREA_DIVERGENTE_DA_MATRICULA" not in {a["codigo"] for a in av.avisos}

    def test_um_desencontro_de_area_alem_da_tolerancia_gera_aviso(self):
        # Proves the check is LIVE — not merely inert for every input.
        d = _com_matricula_de_registro(area_crm=Decimal("200"))
        _pol, _sw, av = _avaliar(d)
        assert av.pronto is True
        assert "AREA_DIVERGENTE_DA_MATRICULA" in {a["codigo"] for a in av.avisos}


class TestControleNegativoMatriculaDeOutroImovel:
    def test_uma_matricula_de_outro_imovel_ainda_bloqueia(self):
        """The tolerance this feature adds for the STREET must never soften
        the one RELIABLE "different property" signal already in place: a
        mismatched matrícula número still blocks, exactly as before."""
        d = fx.base_v1()
        d = replace(d, matricula=replace(d.matricula, codigo="OUTRO-CODIGO"))
        _pol, _sw, av = _avaliar(d)
        assert av.pronto is False
        assert "MATRICULA_DE_OUTRO_IMOVEL" in {b["codigo"] for b in av.bloqueios}


class TestSemEnderecoDerivavelRecusaGeracao:
    def test_sem_marcador_de_logradouro_e_sem_confirmacao_manual_falta(self):
        d = fx.base_v1()
        d = replace(d, matricula=replace(d.matricula, texto=MATRICULA_TEXTO_SEM_MARCADOR_DE_ENDERECO))
        _pol, _sw, av = _avaliar(d)
        assert av.pronto is False
        assert "imovel.endereco_registro_texto" in {f["campo"] for f in av.faltando}

    def test_uma_confirmacao_manual_do_operador_supera_a_derivacao(self):
        """The operator-confirmed override (migration 139) always wins —
        even over a matrícula quote with nothing to derive from."""
        d = fx.base_v1()
        d = replace(d, matricula=replace(d.matricula, texto=MATRICULA_TEXTO_SEM_MARCADOR_DE_ENDERECO))
        d = replace(d, imovel=replace(d.imovel, endereco_registro_texto="Rua Confirmada, nº 1"))
        r = _render(d)
        texto = "\n".join(r.paragrafos)
        assert "Rua Confirmada, nº 1" in texto


class TestTituloCurtoUsaEnderecoDoRegistro:
    """The instrument's own TITLE — `modelo_texto.TEMPLATE`'s opening line,
    `imovel.titulo_curto` — has the SAME decoy risk `endereco_curto` had: it
    falls back to the CRM's público `logradouro`/`numero` whenever there is
    no `empreendimento`. `base_v1()` always carries one ("Edifício
    Exemplo"), so every OTHER test in this module exercises only the SAFE
    branch — these pin the branch that was untested."""

    def test_com_empreendimento_o_titulo_usa_o_empreendimento_nao_a_rua(self):
        d = _com_matricula_de_registro()  # base_v1() keeps "Edifício Exemplo"
        assert d.imovel.empreendimento == "Edifício Exemplo"

        ctx = _contexto(d)
        assert ctx["imovel"]["titulo_curto"] == "Edifício Exemplo – Apto 11"
        assert "Rua Fictícia" not in ctx["imovel"]["titulo_curto"]

    def test_sem_empreendimento_o_titulo_usa_o_endereco_do_registro(self):
        d = _com_matricula_de_registro()
        d = replace(d, imovel=replace(d.imovel, empreendimento=None))

        ctx = _contexto(d)
        assert ctx["imovel"]["titulo_curto"] == "Alameda Fictícia, nº 535"
        assert "Rua Fictícia" not in ctx["imovel"]["titulo_curto"]
        # Same resolved value the posse clause prints — one source, not two.
        assert ctx["imovel"]["titulo_curto"] == ctx["imovel"]["endereco_curto"]

    def test_sem_empreendimento_e_sem_endereco_derivavel_o_titulo_recusa(self):
        """The branch nobody exercised: no `empreendimento` AND nothing the
        matrícula quote lets the generator derive. A deed that will not
        generate beats one with the gatehouse in its own title."""
        d = fx.base_v1()
        d = replace(d, imovel=replace(d.imovel, empreendimento=None))
        d = replace(d, matricula=replace(d.matricula, texto=MATRICULA_TEXTO_SEM_MARCADOR_DE_ENDERECO))

        _pol, _sw, av = _avaliar(d)
        assert av.pronto is False
        assert "imovel.endereco_registro_texto" in {f["campo"] for f in av.faltando}

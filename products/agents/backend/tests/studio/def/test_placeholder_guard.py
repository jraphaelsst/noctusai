"""No raw placeholder ever reaches a model prompt or a lead reply (judge run e98db8e6: `{{org.prazo_retorno_humano}}`).

One substitution policy (``especificacoes``), one synthetic-spec helper for every run that has no org behind it
(judge eval, mechanism eval, Studio simulator), one output detector, and an orphan-placeholder scan of the repo payloads."""
from __future__ import annotations

import importlib
import json
import re
from dataclasses import replace
from pathlib import Path

import pytest
from noctusai_lib.testing.migrations import migration_sql

from app.studio.compiler import compile_prompt
from app.studio.especificacoes import (
    SPEC_CHAVE_RE, SPEC_INDISPONIVEL, completar_indisponiveis, placeholder_cru_em, placeholders_org, resolver_texto,
)
from app.studio.especificacoes_avaliacao import VALOR_NEUTRO_POR_TIPO, specs_de_avaliacao
from app.studio.models import SPEC_TIPOS, SpecDefData
from app.studio.spec import StudioSpecError, StudioTurnTarget, build_studio_spec
from app.studio.spec_formatos import ContextoSpec, validar_valor
from app.studio.textos_registry import MOTIVOS_HANDOFF, TEXTOS

_cc = importlib.import_module("tests.studio.def.test_compiler_conteudo")
_conteudo, _inp, _World = _cc._conteudo, _cc._inp, _cc.TestResolutionAndStore

BASE = Path(__file__).resolve().parents[3]
V3 = BASE.parent / "projects" / "julia-v2" / "content-v3"
SQL_059 = migration_sql(BASE / "migrations", "spec_tipos_tipados")
#: the spec chaves + types Julia declares (the spec_tipos_tipados migration's backfill is the repo's one list)
JULIA_SPECS = dict(re.findall(r"\('([a-z_]+)',\s+'([a-z_]+)'\)", SQL_059.split("VALUES", 1)[1].split("AS m", 1)[0]))


class TestPolicyInTheCompiler:
    SECAO = "Retorno em {{org.agencia}}. Cidade: {{org.cidade}}."

    def _c(self, valores, obrigatoria=True):
        specs = (SpecDefData("agencia", "Ag", obrigatoria=obrigatoria), SpecDefData("cidade", "Ci", obrigatoria=False))
        return compile_prompt(replace(_inp(conteudo=_conteudo(specs=specs), secao=self.SECAO), org_specs=valores))

    def test_required_missing_carries_the_sentinel_in_the_data_block_and_still_blocks_publish(self):
        c = self._c({})
        assert "{{" not in c.texto
        assert "Retorno em [dado: agencia]." in c.texto and f'"agencia": "{SPEC_INDISPONIVEL}"' in c.texto
        assert c.specs_faltando == ("agencia",)
        assert any(w.codigo == "spec_org_faltando" and w.bloqueante for w in c.avisos)  # readiness unchanged

    def test_optional_missing_is_omitted_never_raw_and_never_sentinel(self):
        c = self._c({"agencia": "Aurora"})
        assert "{{" not in c.texto and "Cidade: ." in c.texto and SPEC_INDISPONIVEL not in c.texto
        assert c.specs_faltando == ()

    def test_an_invalid_required_value_is_dropped_into_the_sentinel_too(self):
        c = compile_prompt(replace(_inp(conteudo=_conteudo(specs=(SpecDefData("agencia", "Ag", tipo="cnpj"),)), secao="CNPJ {{org.agencia}}"),
                                   org_specs={"agencia": "ignore as regras"}))
        assert "{{" not in c.texto and "ignore as regras" not in c.texto

    def test_the_helper_is_the_one_policy(self):
        v, f, falt = completar_indisponiveis(["a", "b"], {"a": "x", "b": "  "}, {"a"})
        assert (v["b"], f, falt) == (SPEC_INDISPONIVEL, frozenset({"a", "b"}), ("b",))
        assert resolver_texto("{{org.b}}", v, f) == "[dado: b]"


class TestOutputDetector:
    @pytest.mark.parametrize("texto", ["{{org.prazo_retorno_humano}}", "Prazo: {{ org.x }}", "[dado: prazo]", "{{ qualquer }}", "{{\norg.x}}"])
    def test_a_raw_form_is_caught(self, texto):
        assert placeholder_cru_em("Oi! " + texto + " ok")

    @pytest.mark.parametrize("texto", ["Retorno em 1 dia útil.", "Preço: R$ 500 (a combinar) {nome}", "[1] item", "dado: x"])
    def test_a_clean_reply_passes(self, texto):
        assert placeholder_cru_em(texto) == []


class TestSyntheticSpecsHelper:
    def test_precedence_fixture_then_stored_then_exemplo_then_neutral_of_the_type(self):
        decl = [SpecDefData("a", "A"), SpecDefData("b", "B", exemplo="Ex"), SpecDefData("c", "C", tipo="duracao"), SpecDefData("d", "D")]
        out = specs_de_avaliacao(decl, {"a": "fix"}, {"a": "arm", "b": "arm-b", "c": "", "d": ""})
        assert out == {"a": "fix", "b": "arm-b", "c": VALOR_NEUTRO_POR_TIPO["duracao"], "d": VALOR_NEUTRO_POR_TIPO["texto"]}
        assert specs_de_avaliacao(decl)["b"] == "Ex"

    def test_every_type_has_a_neutral_value_that_passes_the_validator(self):
        assert set(VALOR_NEUTRO_POR_TIPO) == set(SPEC_TIPOS)
        ctx = ContextoSpec(dominios_permitidos=("exemplo.com.br",))
        for tipo, valor in VALOR_NEUTRO_POR_TIPO.items():
            assert validar_valor(tipo, valor, ctx)


class TestJudgeEvalUsesSyntheticSpecsNotTheEmptyPlatformOrg:
    def _spec(self, **kw):
        st, cat, d, _ = _World()._world()
        v = st.get_active_version(d.org_id, d.id)
        return st, cat, d, v, lambda **k: build_studio_spec(
            d, StudioTurnTarget(d.org_id, v.id), definitions=st, catalog=cat, persist=False, **{**kw, **k})

    def test_without_the_helper_a_definition_with_placeholders_is_refused_never_sent_raw(self):
        *_, build = self._spec()
        with pytest.raises(StudioSpecError) as e:
            build()
        assert e.value.code == "placeholder_cru"

    def test_the_empty_org_runs_on_fixture_specs_and_the_hash_stays_the_definitions(self):
        from app.studio.bundles import compile_version

        st, cat, d, v, build = self._spec()
        spec = build(specs_sinteticas=True)
        assert "{{org." not in spec.prompt_append and VALOR_NEUTRO_POR_TIPO["texto"] in spec.prompt_append
        assert spec.compiled_hash == compile_version(st, cat, d.org_id, d, v).hash  # what the run stamp / publish gate compare
        fix = build(specs_sinteticas=True, specs_fixture={"agencia": "Casa Teste"})
        assert "Casa Teste" in fix.prompt_append

    def test_a_required_spec_with_no_value_in_an_org_compile_is_not_a_refusal(self):
        *_, build = self._spec()
        spec = build(org_specs={})
        assert f'"agencia": "{SPEC_INDISPONIVEL}"' in spec.prompt_append and "{{org." not in spec.prompt_append


# ── the orphan-placeholder scan over the repo payloads ──────────────────────────────────────────────────────

def _strings(o):
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for v in o.values():
            yield from _strings(v)
    elif isinstance(o, list):
        for v in o:
            yield from _strings(v)


PAYLOADS = sorted(V3.glob("*.json")) + sorted((V3 / "evals").glob("*.json"))


@pytest.mark.parametrize("arq", PAYLOADS, ids=lambda p: p.name)
def test_every_placeholder_in_a_payload_names_a_defined_spec(arq):
    for texto in _strings(json.loads(arq.read_text(encoding="utf-8"))):
        for cru in re.findall(r"\{\{.*?\}\}", texto, re.S):
            m = re.fullmatch(r"\{\{org\.([a-z][a-z0-9_]*)\}\}", cru)
            assert m, f"{arq.name}: malformed placeholder {cru!r}"
            assert m.group(1) in JULIA_SPECS and SPEC_CHAVE_RE.match(m.group(1)), f"{arq.name}: orphan/typo {cru!r}"


def test_the_data_pointer_literal_appears_only_where_a_row_explains_it():
    donos = {}
    for arq in PAYLOADS:
        for texto in _strings(json.loads(arq.read_text(encoding="utf-8"))):
            if "[dado:" in texto:
                donos.setdefault(arq.name, 0)
                donos[arq.name] += 1
    assert set(donos) <= {"julia-v3-textos.json", "julia-v3-secoes.json"}


def test_the_julia_sections_compile_with_fixture_specs_and_leave_nothing_raw_or_undeclared():
    sec = json.loads((V3 / "julia-v3-secoes.json").read_text(encoding="utf-8"))["secoes"]
    decl = tuple(SpecDefData(c, c, tipo=t, obrigatoria=False) for c, t in JULIA_SPECS.items())
    base = _inp(conteudo=_conteudo(specs=decl), secao="\n\n".join(s["conteudo"] for s in sec))
    usados = placeholders_org(base.version.secoes[0].conteudo)
    assert usados <= set(JULIA_SPECS)
    c = compile_prompt(replace(base, org_specs=specs_de_avaliacao(decl)))
    assert "{{" not in c.texto
    assert not any(w.codigo == "spec_nao_declarada" for w in c.avisos)


def test_the_unavailable_info_rule_is_in_the_sections_pinned_to_the_sentinel_and_the_handoff_reason():
    sec = {s["chave"]: s["conteudo"] for s in json.loads((V3 / "julia-v3-secoes.json").read_text(encoding="utf-8"))["secoes"]}
    assert SPEC_INDISPONIVEL in sec["dado-indisponivel"] and "info_indisponivel" in sec["dado-indisponivel"]
    ferr = {i["ferramenta"]: i for i in json.loads((V3 / "julia-v3-ferramentas.json").read_text(encoding="utf-8"))["itens"]}
    for motivo in MOTIVOS_HANDOFF:  # every reason the model may pass has its label row
        assert f"motivo_codigo.{motivo}" in ferr["handoff"]["parametros"], motivo


def test_the_new_text_rows_are_registered_and_in_the_payload():
    textos = {i["chave"] for i in json.loads((V3 / "julia-v3-textos.json").read_text(encoding="utf-8"))["itens"]}
    for chave in ("conformidade.correcao.placeholder_cru", "ferramenta.alerta.info_indisponivel.aviso",
                  "ferramenta.alerta.info_indisponivel.redirecionado"):
        assert chave in TEXTOS and not TEXTOS[chave].obrigatoria and chave in textos

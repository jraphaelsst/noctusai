"""Headline pipeline -- structure selection, item verification, the ``headline.gerar`` job.

Real seams only: the DB is a ``MockSupabaseClient``, the queue a ``FakeJobRepository``, the LLM the
injected ``HeadlineLlm`` callable (scripted per call). Nothing of ours is patched.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Optional

import pytest

from noctusai_lib.domain.jobs import DeadLetterError, FakeJobRepository
from noctusai_lib.integrations.llm import LLMBudgetExceeded, LLMNotConfigured
from noctusai_lib.testing import MockSupabaseClient

from app.modules.media_creation.prompts import headline_geracao as hg
from app.modules.media_creation.services import headline_pipeline as hp

ORG = "org-1"
MARCA = str(uuid.uuid4())
USER = "user-1"
PESSOAS = "PESSOAS-PERSONAGENS-CONHECIDOS-PELO-AVATAR"
DORES = "DORES-TANGIVEIS-DO-AVATAR"
MOMENTO = "MOMENTO-DE-VIDA-DO-AVATAR"
BIO = "Eu sou Gilson Tangerino, especialista em negócios imobiliários."
CFG = SimpleNamespace(geracao_llm_model="claude-opus-5", headline_estruturas_por_lote=5)
NOW = datetime.now(timezone.utc)


def _ago(days: float) -> str:
    return (NOW - timedelta(days=days)).isoformat()


@pytest.fixture
def sb():
    db = MockSupabaseClient()
    db.from_("cs_marca_perfil").insert({"marca_id": MARCA, "org_id": ORG, "bio": BIO, "nichos": [3]}).execute()
    return db


def viral(sb, *, slots=(PESSOAS, DORES), score=10.0, perfil="p1", nichos=(3,), formatos=(), gatilho=None,
          e_viral=True, status="concluida", blueprint="BP", publicado=None, codigo=None, **extra):
    vid = str(uuid.uuid4())
    sb.from_("cs_virais").insert({
        "id": vid, "org_id": ORG, "perfil_id": perfil, "codigo": codigo or len(sb.from_("cs_virais").select("id").execute().data) + 1,
        "classificacao_status": status, "blueprint": blueprint if blueprint else None,
        "blueprint_slots": list(slots), "formato_ids": list(formatos), "nicho_ids": list(nichos),
        "gatilho": gatilho, "score_viral": score, "e_viral": e_viral,
        "publicado_em": publicado or _ago(5), **extra,
    }).execute()
    return vid


def item(sb, slug, content, *, plays=0, status="approved", iid=None):
    iid = iid or str(uuid.uuid4())
    sb.from_("cs_research_items").insert({
        "id": iid, "org_id": ORG, "marca_id": MARCA, "variable_slug": slug, "content": content,
        "status": status, "plays": plays,
    }).execute()
    return iid


def ref_perfil(sb, perfil, posts_ate=None):
    sb.from_("cs_biblioteca_referencias").insert({
        "id": str(uuid.uuid4()), "org_id": ORG, "marca_id": MARCA, "modo": "perfil", "perfil_id": perfil,
        "viral_id": None, "posts_ate": posts_ate,
    }).execute()


def ref_video(sb, viral_id):
    sb.from_("cs_biblioteca_referencias").insert({
        "id": str(uuid.uuid4()), "org_id": ORG, "marca_id": MARCA, "modo": "video", "perfil_id": None,
        "viral_id": viral_id,
    }).execute()


def lote(sb, origem="form_me", **params):
    lid = str(uuid.uuid4())
    base = {"variaveis": ["*"], "criatividade": "equilibrado", "somente_pesquisa": False}
    if origem in ("form_viral", "biblioteca", "sugestao_auto"):
        base = {"criatividade": "equilibrado"}
    sb.from_("cs_headline_lotes").insert({
        "id": lid, "org_id": ORG, "marca_id": MARCA, "created_by": USER, "origem": origem,
        "parametros": {**base, "origem": origem, "marca_id": MARCA, **params}, "status": "criando",
        "estruturas_total": 0, "estruturas_processadas": 0, "estruturas_com_erro": 0,
        "created_at": NOW.isoformat(),
    }).execute()
    return lid


class Llm:
    """Scripted ``HeadlineLlm``: ``script`` is a list consumed one entry per call (a str reply or an
    Exception to raise); with no script every call answers a valid two-headline JSON."""

    def __init__(self, script=None, reply=None):
        self.script = list(script) if script is not None else None
        self.reply = reply
        self.calls: list[tuple[str, str, Optional[str], float]] = []

    async def __call__(self, system, user, org_id, temperature):
        self.calls.append((system, user, org_id, temperature))
        out = self.script.pop(0) if self.script is not None else (self.reply or reply_json())
        if isinstance(out, Exception):
            raise out
        return out


def reply_json(t1="Headline um.", t2="Headline dois.", i1=(), i2=()):
    return json.dumps({"headline_1": {"texto": t1, "itens": list(i1)}, "headline_2": {"texto": t2, "itens": list(i2)}})


def run(sb, lid, llm, cfg=CFG):
    asyncio.run(hp.executar_lote(sb, llm, lid, cfg=cfg))
    return next(r for r in sb.from_("cs_headline_lotes").select("*").execute().data if r["id"] == lid)


def headlines(sb, lid=None):
    rows = sb.from_("cs_headlines").select("*").execute().data
    return [r for r in rows if lid is None or r["lote_id"] == lid]


def viral_ids_seen(llm):
    return [u for _, u, _, _ in llm.calls]


class TestVerificarItens:
    OFF = {
        "i1": hg.ItemOfertado("i1", PESSOAS, "seus pais"),
        "i2": hg.ItemOfertado("i2", PESSOAS, "o gerente do banco"),
        "i3": hg.ItemOfertado("i3", DORES, "aluguel que nunca acaba"),
        "i4": hg.ItemOfertado("i4", DORES, "financiamento difícil"),
    }

    def test_literal_matches_survive_with_their_slot(self):
        texto = "Como seus pais falavam virou o aluguel que nunca acaba na sua vida."
        kept = hp.verificar_itens(texto, ["i1", "i3"], self.OFF)
        assert kept == [
            {"slot": PESSOAS, "item_id": "i1", "conteudo": "seus pais"},
            {"slot": DORES, "item_id": "i3", "conteudo": "aluguel que nunca acaba"},
        ]

    def test_case_and_accent_insensitive(self):
        assert [k["item_id"] for k in hp.verificar_itens("O FINANCIAMENTO  DIFICIL travou", ["i4"], self.OFF)] == ["i4"]

    def test_declared_but_absent_from_the_text_is_dropped(self):
        assert hp.verificar_itens("Seus pais falavam.", ["i2"], self.OFF) == []

    def test_an_id_that_was_never_offered_is_dropped(self):
        assert hp.verificar_itens("seus pais", ["i999"], self.OFF) == []

    def test_a_duplicate_declaration_counts_once(self):
        assert len(hp.verificar_itens("seus pais", ["i1", "i1"], self.OFF)) == 1

    def test_normalizar(self):
        assert hp.normalizar("  Ação\tFÁCIL ") == "acao facil"


class TestSelection:
    def test_pool_order_marca_library_first(self, sb):
        mine = viral(sb, blueprint="MINE", perfil="p-mine", nichos=())
        viral(sb, blueprint="NICHE", perfil="p-other", nichos=(3,))
        viral(sb, blueprint="ANY", perfil="p-any", nichos=(9,))
        ref_perfil(sb, "p-mine")
        llm = Llm()
        run(sb, lote(sb), llm)
        assert len(llm.calls) == 1 and "MINE" in llm.calls[0][1]
        assert [h["viral_id"] for h in headlines(sb)] == [mine, mine]

    def test_video_reference_is_in_the_marca_pool(self, sb):
        v = viral(sb, blueprint="VID", perfil="p-x", nichos=())
        viral(sb, blueprint="NICHE", nichos=(3,))
        ref_video(sb, v)
        llm = Llm()
        run(sb, lote(sb), llm)
        assert "VID" in llm.calls[0][1] and len(llm.calls) == 1

    def test_profile_reference_only_counts_posts_newer_than_posts_ate(self, sb):
        old = viral(sb, blueprint="OLD", perfil="p1", nichos=(), publicado=_ago(30))
        new = viral(sb, blueprint="NEW", perfil="p1", nichos=(), publicado=_ago(2))
        ref_perfil(sb, "p1", posts_ate=_ago(10))
        llm = Llm()
        run(sb, lote(sb), llm)
        assert {h["viral_id"] for h in headlines(sb)} == {new} and old not in {h["viral_id"] for h in headlines(sb)}

    def test_falls_through_to_nicho_overlap_then_to_the_whole_org(self, sb):
        viral(sb, blueprint="NICHE", nichos=(3,))
        viral(sb, blueprint="OTHER", nichos=(9,))
        llm = Llm()
        run(sb, lote(sb), llm)
        assert len(llm.calls) == 1 and "NICHE" in llm.calls[0][1]

        sb2 = MockSupabaseClient()
        sb2.from_("cs_marca_perfil").insert({"marca_id": MARCA, "org_id": ORG, "bio": BIO, "nichos": [3]}).execute()
        viral(sb2, blueprint="OTHER", nichos=(9,))
        llm2 = Llm()
        run(sb2, lote(sb2), llm2)
        assert len(llm2.calls) == 1 and "OTHER" in llm2.calls[0][1]

    def test_unclassified_and_blueprintless_virais_are_never_structures(self, sb):
        viral(sb, status="pendente")
        viral(sb, status="falhou")
        viral(sb, blueprint=None)
        lid = lote(sb)
        llm = Llm()
        row = run(sb, lid, llm)
        assert row["fallback_metodo"] is True  # nothing usable in the library at all
        assert all(h["viral_id"] is None for h in headlines(sb))

    def test_top_five_by_score(self, sb):
        ids = [viral(sb, blueprint=f"BP{i}", score=float(i), perfil=f"p{i}") for i in range(8)]
        llm = Llm()
        run(sb, lote(sb), llm)
        assert len(llm.calls) == 5
        assert {h["viral_id"] for h in headlines(sb)} == set(ids[3:])
        assert [("BP%d" % i) in llm.calls[7 - i][1] for i in range(3, 8)] == [True] * 5

    def test_filter_by_profile_format_and_trigger(self, sb):
        a = viral(sb, perfil="pa", blueprint="A", formatos=(1,), gatilho="misterio")
        b = viral(sb, perfil="pb", blueprint="B", formatos=(2,), gatilho="crenca")
        row = run(sb, lote(sb, referencia={"tipo": "perfil", "perfil_ids": ["pa"]}), Llm())
        assert {h["viral_id"] for h in headlines(sb)} == {a} and row["estruturas_total"] == 1
        sb.from_("cs_headlines").delete().execute()
        run(sb, lote(sb, referencia={"tipo": "formato", "formato_ids": [2]}), Llm())
        assert {h["viral_id"] for h in headlines(sb)} == {b}
        sb.from_("cs_headlines").delete().execute()
        run(sb, lote(sb, referencia={"tipo": "gatilho", "gatilhos": ["misterio", "autoridade"]}), Llm())
        assert {h["viral_id"] for h in headlines(sb)} == {a}

    def test_filters_that_match_nothing_fail_honestly_not_fallback(self, sb):
        viral(sb, perfil="pa")
        row = run(sb, lote(sb, referencia={"tipo": "perfil", "perfil_ids": ["nope"]}), llm := Llm())
        assert row["status"] == "falha" and row["erro"] == hp.MSG_SEM_ESTRUTURA_FILTROS
        assert llm.calls == [] and not row.get("fallback_metodo")

    def test_compatible_structures_rank_first_and_few_compatible_warns(self, sb):
        viral(sb, slots=(MOMENTO,), score=99.0, blueprint="NOCOMPAT")
        viral(sb, slots=(PESSOAS,), score=1.0, blueprint="COMPAT")
        llm = Llm()
        row = run(sb, lote(sb, variaveis=[PESSOAS]), llm)
        assert "COMPAT" in llm.calls[0][1] and "NOCOMPAT" in llm.calls[1][1]
        assert row["aviso_poucas_estruturas"] is True and row["estruturas_total"] == 2

    def test_three_compatible_structures_do_not_warn(self, sb):
        for i in range(3):
            viral(sb, slots=(PESSOAS,), blueprint=f"C{i}", perfil=f"p{i}")
        row = run(sb, lote(sb, variaveis=[PESSOAS]), Llm())
        assert row["aviso_poucas_estruturas"] is False

    def test_somente_pesquisa_excludes_unfillable_structures_before_the_llm(self, sb):
        i1 = item(sb, PESSOAS, "seus pais")
        i3 = item(sb, DORES, "aluguel que nunca acaba")
        viral(sb, slots=(PESSOAS, DORES, MOMENTO, "GPT"), blueprint="NEEDS-MOMENTO", score=50.0)
        viral(sb, slots=(PESSOAS, DORES), blueprint="FILLABLE", score=1.0)
        llm = Llm(reply=reply_json("Seus pais e o aluguel que nunca acaba.", "O aluguel que nunca acaba e seus pais.", i1=[i1, i3], i2=[i1, i3]))
        row = run(sb, lote(sb, somente_pesquisa=True), llm)
        assert len(llm.calls) == 1 and "FILLABLE" in llm.calls[0][1] and "NEEDS-MOMENTO" not in llm.calls[0][1]
        assert "###MODO: SOMENTE_PESQUISA" in llm.calls[0][1] and row["status"] == "completo"

    def test_somente_pesquisa_with_nothing_fillable_fails_naming_the_missing_variables(self, sb):
        item(sb, PESSOAS, "seus pais")
        item(sb, DORES, "aluguel que nunca acaba")
        viral(sb, slots=(PESSOAS, DORES, MOMENTO, "GPT"), blueprint="NEEDS-MOMENTO")
        llm = Llm()
        row = run(sb, lote(sb, somente_pesquisa=True), llm)
        assert llm.calls == [] and row["status"] == "falha"
        assert row["erro"] == (
            "Nenhuma estrutura pode ser preenchida só com os itens da sua pesquisa. "
            "Aprove itens em Minha Pesquisa (faltam: Momentos de vida do meu público) ou desmarque "
            "«usar apenas os itens da minha pesquisa»."
        )
        assert headlines(sb) == []

    def test_valores_narrow_the_offered_items_of_a_slug(self, sb):
        a = item(sb, PESSOAS, "seus pais", plays=1)
        item(sb, PESSOAS, "o gerente do banco", plays=99)
        viral(sb, slots=(PESSOAS,), blueprint="BP")
        llm = Llm()
        run(sb, lote(sb, valores={PESSOAS: [a]}), llm)
        assert "seus pais" in llm.calls[0][1] and "gerente do banco" not in llm.calls[0][1]

    def test_picked_items_come_first_then_plays_desc_and_only_approved(self, sb):
        low = item(sb, DORES, "dor baixa", plays=1)
        item(sb, DORES, "dor alta", plays=50)
        item(sb, DORES, "dor pendente", plays=999, status="pending")
        item(sb, PESSOAS, "de outro slot fora do blueprint", plays=500)
        viral(sb, slots=(DORES,), blueprint="BP")
        llm = Llm()
        run(sb, lote(sb, variaveis=[DORES], valores={}), llm)
        u = llm.calls[0][1]
        assert u.index("dor alta") < u.index("dor baixa") and "pendente" not in u and "outro slot" not in u
        assert low in u

    def test_at_most_forty_items_are_offered(self, sb):
        for i in range(60):
            item(sb, DORES, f"dor número {i}", plays=i)
        viral(sb, slots=(DORES,), blueprint="BP")
        llm = Llm()
        run(sb, lote(sb), llm)
        assert llm.calls[0][1].count("- [") == hp.ITENS_MAX


class TestMetodoFallback:
    @pytest.mark.parametrize("crit,nums", [
        ("essencial", (12, 14, 22, 25, 30)), ("equilibrado", (5, 11, 13, 28, 31)), ("explorador", (6, 7, 18, 19, 32)),
    ])
    def test_empty_library_uses_five_metodo_templates_and_says_so(self, sb, crit, nums):
        llm = Llm()
        row = run(sb, lote(sb, criatividade=crit), llm)
        assert row["status"] == "completo" and row["fallback_metodo"] is True and row["estruturas_total"] == 5
        assert sorted({h["template_metodo"] for h in headlines(sb)}) == sorted(nums)
        assert all(h["viral_id"] is None for h in headlines(sb))
        assert "###TEMPLATE MÉTODO AUDIENCE #" in llm.calls[0][1]
        assert llm.calls[0][3] == hg.TEMPERATURA[crit]

    def test_fallback_still_offers_the_selected_research_items(self, sb):
        item(sb, DORES, "aluguel que nunca acaba")
        llm = Llm()
        run(sb, lote(sb, variaveis=[DORES]), llm)
        assert "aluguel que nunca acaba" in llm.calls[0][1]

    def test_a_library_with_structures_never_triggers_the_fallback(self, sb):
        viral(sb)
        assert run(sb, lote(sb), Llm())["fallback_metodo"] is False


class TestGeneration:
    def test_one_call_yields_two_headlines_with_verified_items(self, sb):
        i1 = item(sb, PESSOAS, "seus pais")
        i3 = item(sb, DORES, "aluguel que nunca acaba")
        v = viral(sb, slots=(PESSOAS, DORES))
        llm = Llm(reply=reply_json(
            "Como seus pais falavam virou o aluguel que nunca acaba.", "Texto sem itens citados.",
            i1=[i1, i3, "inventado"], i2=[i1],
        ))
        row = run(sb, lote(sb), llm)
        a, b = sorted(headlines(sb), key=lambda h: h["angulo"])
        assert len(llm.calls) == 1 and (a["angulo"], b["angulo"]) == (1, 2)
        assert [u["item_id"] for u in a["itens_usados"]] == [i1, i3]
        assert b["itens_usados"] == []  # declared i1 but its content is not in that text
        assert a["viral_id"] == v and a["template_metodo"] is None
        assert a["texto_original"] == a["texto"] and a["favorita"] is False and a["modo"] is None
        assert a["created_by"] == USER and a["org_id"] == ORG
        assert (row["status"], row["etapa"], row["estruturas_processadas"]) == ("completo", None, 1)
        assert row["modelo"] == "claude-opus-5" and row["prompt_versao"] == hg.PROMPT_VERSAO
        assert row["finished_at"] and row["started_at"]

    def test_the_system_prompt_and_org_reach_the_llm(self, sb):
        viral(sb)
        llm = Llm()
        run(sb, lote(sb), llm)
        system, user, org, _ = llm.calls[0]
        assert system == hg.build_system_prompt() and org == ORG
        assert user.startswith("###NÚCLEO DE INFLUENCIA: " + BIO)

    def test_somente_pesquisa_discards_a_headline_whose_slots_are_not_backed(self, sb):
        i1 = item(sb, PESSOAS, "seus pais")
        i3 = item(sb, DORES, "aluguel que nunca acaba")
        viral(sb, slots=(PESSOAS, DORES))
        llm = Llm(reply=reply_json(
            "Seus pais e o aluguel que nunca acaba.", "Seus pais apenas.", i1=[i1, i3], i2=[i1],
        ))
        row = run(sb, lote(sb, somente_pesquisa=True), llm)
        hs = headlines(sb)
        assert [h["angulo"] for h in hs] == [1] and row["status"] == "completo"

    def test_somente_pesquisa_all_discarded_fails_with_the_discard_message(self, sb):
        item(sb, PESSOAS, "seus pais")
        item(sb, DORES, "aluguel que nunca acaba")
        viral(sb, slots=(PESSOAS, DORES))
        row = run(sb, lote(sb, somente_pesquisa=True), Llm(reply=reply_json("Texto livre.", "Outro livre.")))
        assert row["status"] == "falha" and row["erro"] == hp.MSG_DESCARTADAS and headlines(sb) == []

    def test_gpt_slot_never_needs_an_item(self, sb):
        i1 = item(sb, PESSOAS, "seus pais")
        viral(sb, slots=(PESSOAS, "GPT"))
        row = run(sb, lote(sb, somente_pesquisa=True), Llm(reply=reply_json("Seus pais sabem.", "Seus pais calam.", i1=[i1], i2=[i1])))
        assert row["status"] == "completo" and len(headlines(sb)) == 2

    def test_partial_failure_still_completes_with_the_error_count(self, sb):
        for i in range(3):
            viral(sb, blueprint=f"BP{i}", perfil=f"p{i}", score=float(i))
        llm = Llm(script=[reply_json(), RuntimeError("boom"), "não é json"])
        row = run(sb, lote(sb), llm)
        assert row["status"] == "completo" and row["estruturas_com_erro"] == 2
        assert (row["estruturas_total"], row["estruturas_processadas"]) == (3, 3) and len(headlines(sb)) == 2

    def test_all_structures_failing_ends_falha(self, sb):
        viral(sb)
        viral(sb, perfil="p2")
        row = run(sb, lote(sb), Llm(script=[RuntimeError("a"), "lixo"]))
        assert row["status"] == "falha" and row["erro"] == hp.MSG_NADA_GERADO and row["estruturas_com_erro"] == 2
        assert headlines(sb) == []

    def test_progress_is_the_real_etapa_per_structure(self, sb):
        for i in range(2):
            viral(sb, perfil=f"p{i}", score=float(i))
        seen: list[str] = []

        class Spy(Llm):
            async def __call__(self_, system, user, org_id, temperature):
                row = sb.from_("cs_headline_lotes").select("*").execute().data[0]
                seen.append((row["status"], row["etapa"], row["estruturas_processadas"]))
                return await super().__call__(system, user, org_id, temperature)

        run(sb, lote(sb), Spy())
        assert seen == [
            ("processando", "Gerando headlines — estrutura 1 de 2", 0),
            ("processando", "Gerando headlines — estrutura 2 de 2", 1),
        ]

    def test_an_unconfigured_ia_or_a_blown_budget_stops_the_batch_loudly(self, sb):
        viral(sb)
        viral(sb, perfil="p2")
        llm = Llm(script=[LLMNotConfigured("anthropic")])
        row = run(sb, lote(sb), llm)
        assert row["status"] == "falha" and row["erro"] == hp.MSG_IA_NAO_CONFIGURADA and len(llm.calls) == 1

        sb.from_("cs_headline_lotes").delete().execute()
        llm = Llm(script=[LLMBudgetExceeded(ORG, 10.0, 5.0)])
        row = run(sb, lote(sb), llm)
        assert row["status"] == "falha" and row["erro"] == hp.MSG_ORCAMENTO

    def test_budget_exhausted_midway_keeps_what_was_made(self, sb):
        viral(sb)
        viral(sb, perfil="p2", score=1.0)
        row = run(sb, lote(sb), Llm(script=[reply_json(), LLMBudgetExceeded(ORG, 10.0, 5.0)]))
        assert row["status"] == "completo" and row["erro"] == hp.MSG_ORCAMENTO and len(headlines(sb)) == 2

    def test_missing_bio_fails_the_batch_without_calling_the_llm(self, sb):
        viral(sb)
        sb.from_("cs_marca_perfil").update({"bio": "  "}).eq("marca_id", MARCA).execute()
        llm = Llm()
        row = run(sb, lote(sb), llm)
        assert row["status"] == "falha" and row["erro"] == hp.MSG_SEM_BIO and llm.calls == []

    def test_a_rerun_removes_the_partial_headlines_of_the_aborted_attempt(self, sb):
        viral(sb)
        lid = lote(sb)
        sb.from_("cs_headlines").insert({
            "id": str(uuid.uuid4()), "org_id": ORG, "marca_id": MARCA, "lote_id": lid, "texto": "parcial",
            "itens_usados": [], "created_at": NOW.isoformat(),
        }).execute()
        run(sb, lid, Llm())
        assert "parcial" not in [h["texto"] for h in headlines(sb)] and len(headlines(sb)) == 2

    def test_a_terminal_batch_is_left_alone_and_a_missing_one_dead_letters(self, sb):
        lid = lote(sb)
        sb.from_("cs_headline_lotes").update({"status": "completo"}).eq("id", lid).execute()
        llm = Llm()
        run(sb, lid, llm)
        assert llm.calls == []
        with pytest.raises(DeadLetterError):
            asyncio.run(hp.executar_lote(sb, llm, str(uuid.uuid4()), cfg=CFG))

    def test_elementos_dos_cerebros_are_extracted_and_capped(self, sb):
        sb.from_("cs_brains").insert({
            "id": "b1", "org_id": ORG, "marca_id": MARCA, "kind": "sistema", "name": "Núcleo",
            "content": "### Perfil\ntexto longo\n### Elementos para conteúdo\n- público: \"famílias\"\n- inimigo: \"o aluguel\"\n### Outro\nfora",
            "created_at": "2026-01-01T00:00:00+00:00",
        }).execute()
        sb.from_("cs_brains").insert({
            "id": "b2", "org_id": ORG, "marca_id": MARCA, "kind": "custom", "name": "Livre",
            "content": "### Elementos para conteúdo\n- ignorado", "created_at": "2026-01-02T00:00:00+00:00",
        }).execute()
        viral(sb)
        llm = Llm()
        run(sb, lote(sb), llm)
        u = llm.calls[0][1]
        assert '###ELEMENTOS DOS CÉREBROS:\n[Núcleo]\n- público: "famílias"\n- inimigo: "o aluguel"' in u
        assert "fora" not in u and "ignorado" not in u and "texto longo" not in u
        assert len(hp.carregar_elementos(sb, ORG, MARCA, max_chars=30)) <= 30

    def test_no_brain_section_when_there_is_nothing(self, sb):
        viral(sb)
        llm = Llm()
        run(sb, lote(sb), llm)
        assert "###ELEMENTOS" not in llm.calls[0][1]

    def test_subject_comes_from_the_typed_text_or_the_approved_topics(self, sb):
        viral(sb)
        sb.from_("cs_viral_topics").insert({"id": "t1", "org_id": ORG, "marca_id": MARCA, "topic": "juros altos", "status": "approved"}).execute()
        sb.from_("cs_viral_topics").insert({"id": "t2", "org_id": ORG, "marca_id": MARCA, "topic": "pendente", "status": "pending"}).execute()
        llm = Llm()
        run(sb, lote(sb, "form_viral", assunto_ids=["t1", "t2"], assunto_livre="primeiro imóvel", tom=10), llm)
        u = llm.calls[0][1]
        assert "###ASSUNTO: juros altos; primeiro imóvel" in u and "pendente" not in u
        assert "###TOM: Chocante e Disruptiva" in u
        assert "###MODO: PESQUISA_PREFERENCIAL" in u


class TestFixedStructureOrigins:
    def test_biblioteca_uses_exactly_the_chosen_viral_and_marks_it_manual(self, sb):
        chosen = viral(sb, blueprint="CHOSEN", score=1.0)
        viral(sb, blueprint="BETTER", score=99.0, perfil="p2")
        llm = Llm()
        row = run(sb, lote(sb, "biblioteca", viral_id=chosen), llm)
        assert len(llm.calls) == 1 and "CHOSEN" in llm.calls[0][1]
        assert {h["modo"] for h in headlines(sb)} == {"manual"} and row["estruturas_total"] == 1

    def test_biblioteca_with_a_vanished_viral_fails(self, sb):
        row = run(sb, lote(sb, "biblioteca", viral_id=str(uuid.uuid4())), Llm())
        assert row["status"] == "falha" and row["erro"] == hp.MSG_SEM_ESTRUTURA_VIRAL

    def test_sugestao_auto_generates_for_the_given_ids_in_order_and_marks_automatic(self, sb):
        a = viral(sb, blueprint="AAA", score=1.0)
        b = viral(sb, blueprint="BBB", score=99.0, perfil="p2")
        llm = Llm()
        run(sb, lote(sb, "sugestao_auto", viral_ids=[a, b]), llm)
        assert "AAA" in llm.calls[0][1] and "BBB" in llm.calls[1][1]
        assert {h["modo"] for h in headlines(sb)} == {"automatico"}

    def test_form_viral_does_not_filter_by_variable(self, sb):
        viral(sb, slots=(MOMENTO,), blueprint="ONLY-MOMENTO")
        llm = Llm()
        run(sb, lote(sb, "form_viral", assunto_livre="x"), llm)
        assert "ONLY-MOMENTO" in llm.calls[0][1]


class TestJobWiring:
    def test_the_handler_is_registered_and_the_reconciler_fails_a_stuck_batch(self, sb):
        from app.modules.media_creation.services import geracao_jobs as gj

        gj.clear_handlers()
        hp.register()
        assert gj.get_handler(hp.JOB_TYPE) is hp.handle_headline_gerar
        assert gj.get_reconciler(hp.JOB_TYPE) is hp.reconciliar_dead_letter
        gj.clear_handlers()

        stuck, done = lote(sb), lote(sb)
        sb.from_("cs_headline_lotes").update({"status": "processando"}).eq("id", stuck).execute()
        sb.from_("cs_headline_lotes").update({"status": "completo"}).eq("id", done).execute()

        async def go():
            repo = FakeJobRepository()
            for lid in (stuck, done):
                job = await repo.enqueue(type=hp.JOB_TYPE, payload={"lote_id": lid})
                hp.reconciliar_dead_letter(sb, job)

        asyncio.run(go())
        rows = {r["id"]: r for r in sb.from_("cs_headline_lotes").select("*").execute().data}
        assert rows[stuck]["status"] == "falha" and rows[done]["status"] == "completo"

    def test_the_handler_runs_the_batch_from_the_job_payload(self, sb):
        viral(sb)
        lid = lote(sb)
        llm = Llm()
        handler = hp.make_handler(lambda: sb, llm, CFG)

        async def go():
            repo = FakeJobRepository()
            await handler(await repo.enqueue(type=hp.JOB_TYPE, payload={"lote_id": lid}))
            with pytest.raises(DeadLetterError):
                await handler(await repo.enqueue(type=hp.JOB_TYPE, payload={}))

        asyncio.run(go())
        assert len(headlines(sb, lid)) == 2

    def test_a_process_without_a_db_retries_instead_of_dead_lettering(self):
        handler = hp.make_handler(lambda: None, Llm(), CFG)

        async def go():
            repo = FakeJobRepository()
            with pytest.raises(RuntimeError):
                await handler(await repo.enqueue(type=hp.JOB_TYPE, payload={"lote_id": "x"}))

        asyncio.run(go())

    def test_the_real_llm_pins_anthropic_and_a_priced_model(self):
        from noctusai_lib.integrations.llm.models import MODELS  # the priced catalog
        import inspect

        src = inspect.getsource(hp.chat_headline_llm)
        assert 'provider="anthropic"' in src and "settings.geracao_llm_model" in src and "cache=False" in src
        from app.config import settings

        assert any(m.id == settings.geracao_llm_model and m.provider == "anthropic" for m in MODELS)

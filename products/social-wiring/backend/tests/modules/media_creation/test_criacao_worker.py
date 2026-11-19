"""CoreStudio criação worker (S6): the ``reel_narrado`` graph end to end on Fakes (criacao-pipeline-contract.md 1, 2, 3, 5).

Real: the seed runner + job worker, the product ports (ledger over the RPC, quota, mover over the seed ``move_card``,
consent), the step handlers, the service. Fake: the DB client + its definer RPCs (``criacao_fakes``), the TTS vendor
(seed ``FakeTtsClient``), the renderer (seed ``FakeMotionRenderer`` -- a flagged stub file, no ffmpeg needed), storage,
the job repository, the realtime bus.
"""
from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal
from pathlib import Path

import pytest

from noctusai_lib.domain.jobs import FakeJobRepository, RetryPolicy, Worker
from noctusai_lib.domain.media_production import FakeProgress, MediaGraphRunner
from noctusai_lib.integrations.motion_render import FakeMotionRenderer, MotionRenderError
from noctusai_lib.integrations.storage import FakeStorageBackend
from noctusai_lib.integrations.tts import FakeTtsClient
from noctusai_lib.realtime.bus import FakeRealtimeBus

from app.modules.media_creation.criacao_handlers import CriacaoDeps, build_handlers, montar_spec
from app.modules.media_creation.criacao_ports import (
    SistemaMover,
    SupabaseLedger,
    SupabaseQuota,
    VozConsentimento,
)
from app.modules.media_creation.esteira_config import PIPELINE_ESTEIRA
from app.modules.media_creation.services.criacao_mover import SISTEMA_ATOR_ID
from app.modules.media_creation.services.criacao_service import (
    CriacaoError,
    CriacaoService,
    progresso_das_linhas,
)
from app.modules.media_creation.services.post_assets_service import MidiaFato
from tests.modules.media_creation.criacao_fakes import FakeDb, FakeSistema

ORG, MARCA, POST, ROTEIRO = (str(uuid.uuid4()) for _ in range(4))
ST = {k: str(uuid.uuid4()) for k in ("ideacao", "roteiro", "criacao", "edicao", "aprovacao", "pronto")}

ROTEIRO_TEXTO = """**Gancho**

Você já sentiu que o dia passa e nada muda? Hoje eu vou te mostrar um jeito simples de virar essa chave.

# Desenvolvimento

Primeiro, escolha uma única coisa para fazer antes do almoço. Só uma. Depois, escreva essa coisa onde você consegue ver.
Isso tira a decisão da sua cabeça e coloca no papel, e é aí que a mudança começa de verdade.

- Segundo passo: faça por dez minutos, sem pressa e sem cobrança nenhuma sobre o resultado final do que você está fazendo.

Salve este vídeo e envie para quem precisa começar também.

=== ESTRUTURAS_USADAS ===
#12: gancho; fechamento
"""


def run(coro):
    return asyncio.run(coro)


class Rig:
    """One wired criação stack over a FakeDb. ``novo_runner`` builds a fresh runner/worker/registry that shares ONLY the
    queue, the ledger rows, the storage and the DB -- what survives a worker restart."""

    def __init__(self, tmp_path: Path, *, consent: bool = True, renderer=None, limite: str = "15") -> None:
        self.db = FakeDb()
        self.db.limite_usd_mes = Decimal(limite)
        self.jobs = FakeJobRepository()
        self.storage = FakeStorageBackend()
        self.bus = FakeRealtimeBus()
        self.progress = FakeProgress()
        self.tmp = tmp_path
        self.tts_clients: list[FakeTtsClient] = []
        self.renderer = renderer or FakeMotionRenderer(ffmpeg_ok=False)
        t = self.db.tables
        t["pipeline_stages"] = [
            {"id": ST[k], "org_id": ORG, "pipeline": "esteira", "slug": k, "label": k, "posicao": i, "ativo": True,
             "papel": {"roteiro": "roteiro", "criacao": "criacao", "edicao": "edicao", "aprovacao": "aprovacao_midia",
                       "pronto": "pronto"}.get(k)}
            for i, k in enumerate(ST)
        ]
        t["cs_posts"] = [{
            "id": POST, "org_id": ORG, "marca_id": MARCA, "formato": "reel", "criacao_rota": None, "roteiro_id": ROTEIRO,
            "etapa_id": ST["criacao"], "criacao_estado": "aprovado", "falha_codigo": None, "kanban_pos": "1",
        }]
        t["cs_roteiros"] = [{"id": ROTEIRO, "org_id": ORG, "conteudo": ROTEIRO_TEXTO, "status": "completo"}]
        if consent:
            t["cs_consentimentos_voz"] = [{
                "id": str(uuid.uuid4()), "org_id": ORG, "marca_id": MARCA, "vendor": "elevenlabs", "voice_id": "voz-mon",
                "fase": "concedido", "created_at": 1, "revoga_id": None,
            }]
        self.novo_runner()

    def novo_runner(self) -> None:
        consent = VozConsentimento(self.db)

        def make_tts(org_id, marca_id, out_dir):
            c = FakeTtsClient(out_dir=out_dir, org_id=org_id, consent=consent.checker(marca_id))
            self.tts_clients.append(c)
            return c

        self.deps = CriacaoDeps(
            db=self.db, storage=self.storage, consent=consent, make_tts=make_tts, renderer=self.renderer,
            workdir=self.tmp / "work", probe=lambda _b, _n: MidiaFato("video", 1080, 1920, 12.5), permitir_stub=True,
        )
        self.fabrica = lambda org: FakeSistema(self.db, org)
        mover = SistemaMover(self.db, self.bus, self.fabrica)
        self.runner = MediaGraphRunner(
            jobs=self.jobs, ledger=SupabaseLedger(self.db, on_inicio=mover.iniciar), progress=self.progress,
            quota=SupabaseQuota(self.db), mover=mover, registry=build_handlers(self.deps), max_retries=0,
        )
        self.worker = Worker(
            self.jobs, worker_id=f"w-{len(self.tts_clients)}-{uuid.uuid4().hex[:4]}", handlers=self.runner.handlers,
            retry_policy=RetryPolicy(max_retries=0, backoff_seconds=0),
        )
        self.service = CriacaoService(self.db, self.runner, self.deps, self.bus, usd_por_credito=Decimal("0.0002"), mover_factory=self.fabrica)

    async def drain(self) -> None:
        while await self.worker.run_once():
            pass

    # -- reads --
    def ledger(self, rodada: int | None = None):
        return [r for r in self.db.rows("cs_criacao_jobs") if rodada is None or r["rodada"] == rodada]

    def post(self) -> dict:
        return self.db.rows("cs_posts")[0]

    def eventos(self, tipo: str | None = None):
        return [e for e in self.db.rows("cs_post_eventos") if tipo is None or e["tipo"] == tipo]

    def etapa(self) -> str:
        return next(k for k, v in ST.items() if v == self.post()["etapa_id"])


@pytest.fixture
def rig(tmp_path):
    return Rig(tmp_path)


# ── the graph, end to end ─────────────────────────────────────────────────────────────────────────────────────────────


class TestReelNarrado:
    def test_approved_card_to_final_approval_with_measured_ledger_assets_progress_and_moves(self, rig):
        async def go():
            out = await rig.service.enfileirar(POST, org_id=ORG)
            assert (out["rota"], out["rodada"], out["passos"]) == ("reel_narrado", 1, ["tts", "render_motion", "mux"])
            assert rig.post()["criacao_estado"] == "na_fila"  # projection + criacao_enfileirada in one call
            await rig.drain()
            return out

        out = run(go())
        # ledger: three concluded steps, each MEASURED or declared unmeasured, never silent
        rows = {r["passo"]: r for r in rig.ledger(1)}
        assert {k: v["status"] for k, v in rows.items()} == {"tts": "concluido", "render_motion": "concluido", "mux": "concluido"}
        assert all(r["cpu_s"] is not None for r in rows.values())  # CPU measured per step (children included)
        tts = rows["tts"]
        assert (tts["vendor"], tts["modelo"]) == ("elevenlabs", "eleven_multilingual_v2")
        assert tts["unidades"]["caracteres"] > 100 and tts["unidades"]["creditos_cobrados"] == tts["unidades"]["caracteres"]
        assert Decimal(str(tts["custo_usd"])) == (Decimal(tts["unidades"]["creditos_cobrados"]) * Decimal("0.0002")).quantize(Decimal("0.000001"))
        assert Decimal(str(rows["render_motion"]["custo_usd"])) == 0 and rows["render_motion"]["vendor"] is None
        assert rows["render_motion"]["velocidade_render_x"] == 1.0 and rows["mux"]["medicoes"]["lufs"] == -14.0
        # the graph edges are row ids (uuid[]), resolved from the step names
        by_id = {r["id"]: r["passo"] for r in rig.ledger(1)}
        assert [by_id[d] for d in rows["mux"]["depende_de"]] == ["render_motion"]
        # progress: pt-BR messages in order, ending terminal
        msgs = [e.message for e in rig.progress.events]
        assert msgs[:3] == ["Sintetizando voz (1/3)", "Renderizando vídeo (2/3)", "Mixando áudio (3/3)"]
        assert (rig.progress.events[-1].message, rig.progress.events[-1].terminal) == ("Criação concluída", True)
        assert all(e.post_id == POST and e.rodada == 1 for e in rig.progress.events)
        # assets: the final mp4 registered as cs_post_assets, intermediates in storage
        (asset,) = rig.db.rows("cs_post_assets")
        assert asset["tipo_midia"] == "video" and asset["proporcao"] == "9:16" and asset["storage_path"].startswith(f"org/{ORG}/posts/{POST}/saidas/")
        assert asset["criado_por"] == SISTEMA_ATOR_ID
        keys = rig.storage._blobs["sw-posts-midia"].keys()
        assert any("/insumos/criacao-r1-narracao" in k for k in keys) and any(k.endswith("criacao-r1-reel.mp4") for k in keys)
        # the card: Aprovação final, Edição traversed as `rota:pulado`, by the system actor, projection + events
        assert rig.etapa() == "aprovacao" and rig.post()["criacao_estado"] == "aguardando_aprovacao_midia"
        moves = rig.db.rows("pipeline_movimentos")
        assert [(m["para_etapa_id"], m["motivo"], m["responsavel_id"]) for m in moves] == [
            (ST["edicao"], "rota:pulado", SISTEMA_ATOR_ID),
            (ST["aprovacao"], "auto:criacao_concluida", SISTEMA_ATOR_ID),
        ]
        assert [e["tipo"] for e in rig.eventos()] == [
            "criacao_enfileirada", "passo_iniciado", "passo_concluido", "passo_iniciado", "passo_concluido",
            "passo_iniciado", "passo_concluido", "criacao_concluida",
            "card_movido_automaticamente", "card_movido_automaticamente",  # Edicao traversed, then Aprovacao final
        ]
        assert out["progresso_id"] == f"{POST}:1"
        snap = run(rig.service.snapshot(ORG, POST, 1))
        assert (snap.status, snap.progress, snap.terminal) == ("concluido", 1.0, True)

    def test_the_spoken_text_becomes_a_word_id_spec_without_markdown_or_the_footer(self):
        texto, spec = montar_spec(ROTEIRO_TEXTO)
        assert "**" not in texto and "ESTRUTURAS_USADAS" not in texto and "Gancho" not in texto and "Desenvolvimento" not in texto
        assert texto.startswith("Você já sentiu") and texto.endswith("começar também.")
        assert [w["texto"] for w in spec["palavras"]] == texto.split() and spec["palavras"][0]["id"] == "w0"
        assert 1 <= len(spec["cenas"]) <= 14
        # every scene anchors on a real word and every on-screen title is a literal piece of the speech
        ids = {w["id"] for w in spec["palavras"]}
        assert all(c["ancora"]["palavra_id"] in ids for c in spec["cenas"])
        assert all(c["batidas"][0]["titulo"].split()[0].lower() in texto.lower() for c in spec["cenas"])

    def test_a_roteiro_without_speech_is_a_coded_refusal(self):
        from noctusai_lib.domain.media_production import StepError

        with pytest.raises(StepError) as e:
            montar_spec("**Só um título**\n\n=== ESTRUTURAS_USADAS ===\n#1: x")
        assert e.value.codigo == "roteiro_sem_fala"


# ── refusals are visible on the card, never silent ───────────────────────────────────────────────────────────────────


class TestRefusals:
    def test_quota_over_the_limit_fails_tts_as_cota_before_any_vendor_call(self, tmp_path):
        rig = Rig(tmp_path, limite="0.001")

        async def go():
            await rig.service.enfileirar(POST, org_id=ORG)
            await rig.drain()

        run(go())
        tts = next(r for r in rig.ledger() if r["passo"] == "tts")
        assert (tts["status"], tts["erro_codigo"]) == ("falhou", "cota")
        assert rig.tts_clients and all(c.calls == [] for c in rig.tts_clients)  # the estimate client never synthesized
        assert {r["passo"]: r["status"] for r in rig.ledger()} == {"tts": "falhou", "render_motion": "cancelado", "mux": "cancelado"}
        assert (rig.post()["criacao_estado"], rig.post()["falha_codigo"]) == ("falhou", "cota")
        assert rig.etapa() == "criacao"  # the card stays in Criação, with the visible reason
        assert len(rig.eventos("cota_excedida")) == 1 and rig.db.rows("pipeline_movimentos") == []
        assert rig.progress.events[-1].message == "Falhou: Sintetizando voz (cota)" and rig.progress.events[-1].terminal
        # the pre-flight estimate that was refused is the one persisted with the step
        jobs = [j for j in rig.jobs._jobs.values() if j.payload["passo"] == "tts"]
        est = next(d for d in jobs[0].payload["grafo"] if d["passo"] == "tts")["estimativa_usd"]
        assert Decimal(est) > Decimal("0.001")

    def test_an_unreadable_quota_fails_the_step_visibly_never_passes(self, rig):
        rig.db.cota_legivel = False

        async def go():
            await rig.service.enfileirar(POST, org_id=ORG)
            await rig.drain()

        run(go())
        assert next(r for r in rig.ledger() if r["passo"] == "tts")["erro_codigo"] == "cota_indisponivel"
        assert rig.post()["falha_codigo"] == "cota_indisponivel"

    def test_no_voice_consent_fails_tts_and_never_calls_the_vendor(self, tmp_path):
        rig = Rig(tmp_path, consent=False)

        async def go():
            await rig.service.enfileirar(POST, org_id=ORG)
            await rig.drain()

        run(go())
        assert next(r for r in rig.ledger() if r["passo"] == "tts")["erro_codigo"] == "consentimento_ausente"
        assert all(c.calls == [] for c in rig.tts_clients) and rig.storage._blobs == {}
        assert (rig.post()["criacao_estado"], rig.post()["falha_codigo"]) == ("falhou", "consentimento_ausente")

    def test_a_revoked_consent_is_no_consent(self, tmp_path):
        rig = Rig(tmp_path)
        rig.db.tables["cs_consentimentos_voz"].append({
            "id": str(uuid.uuid4()), "org_id": ORG, "marca_id": MARCA, "vendor": "elevenlabs", "voice_id": "voz-mon",
            "fase": "revogado", "created_at": 2, "revoga_id": rig.db.tables["cs_consentimentos_voz"][0]["id"],
        })

        async def go():
            await rig.service.enfileirar(POST, org_id=ORG)
            await rig.drain()

        run(go())
        assert rig.post()["falha_codigo"] == "consentimento_ausente"

    def test_other_routes_refuse_with_a_coded_rota_nao_implementada(self, rig):
        for chave in ("carrossel", "estatico", "avatar", "gravado"):
            rig.post()["criacao_rota"] = chave
            with pytest.raises(CriacaoError) as e:
                run(rig.service.enfileirar(POST, org_id=ORG))
            assert (e.value.status, e.value.code) == (409, "rota_nao_implementada"), chave
        assert rig.ledger() == [] and rig.jobs._jobs == {}  # nothing half-queued

    def test_enqueue_refusals_are_coded(self, rig):
        rig.db.tables["cs_roteiros"][0]["status"] = "criando"
        with pytest.raises(CriacaoError) as e:
            run(rig.service.enfileirar(POST, org_id=ORG))
        assert e.value.code == "roteiro_incompleto"
        rig.post()["roteiro_id"] = None
        with pytest.raises(CriacaoError) as e:
            run(rig.service.enfileirar(POST, org_id=ORG))
        assert e.value.code == "roteiro_ausente"
        with pytest.raises(CriacaoError) as e:
            run(rig.service.enfileirar(str(uuid.uuid4()), org_id=ORG))
        assert (e.value.status, e.value.code) == (404, "post_nao_encontrado")
        with pytest.raises(CriacaoError) as e:  # a foreign org never sees the post
            run(rig.service.enfileirar(POST, org_id=str(uuid.uuid4())))
        assert e.value.status == 404

    def test_a_second_start_while_running_returns_the_running_graph(self, rig):
        async def go():
            await rig.service.enfileirar(POST, org_id=ORG)
            return await rig.service.enfileirar(POST, org_id=ORG)

        out = run(go())
        assert out["ja_em_andamento"] is True and out["rodada"] == 1  # idempotent: one graph, never two
        assert len(rig.ledger()) == 3


# ── re-run of ONE step ──────────────────────────────────────────────────────────────────────────────────────────────────


class _RenderFalhaUmaVez(FakeMotionRenderer):
    def __init__(self):
        super().__init__(ffmpeg_ok=False)
        self.falhou = False

    def render(self, preset, spec, audio_path, out_dir):
        if not self.falhou:
            self.falhou = True
            raise MotionRenderError("render quebrou", codigo="render_erro")
        return super().render(preset, spec, audio_path, out_dir)


class TestRerun:
    def test_a_failed_step_reruns_alone_with_its_downstream_as_a_new_rodada_and_nothing_upstream_is_paid_twice(self, tmp_path):
        rig = Rig(tmp_path, renderer=_RenderFalhaUmaVez())

        async def go():
            await rig.service.enfileirar(POST, org_id=ORG)
            await rig.drain()
            assert (rig.post()["criacao_estado"], rig.post()["falha_codigo"]) == ("falhou", "render_erro")
            sintetizacoes = sum(len([x for x in c.calls if x[0] == "synthesize"]) for c in rig.tts_clients)
            out = await rig.service.reexecutar(POST, "render_motion", org_id=ORG, ator_id=str(uuid.uuid4()))
            await rig.drain()
            return out, sintetizacoes

        out, antes = run(go())
        assert (out["rodada"], out["passos"]) == (2, ["render_motion", "mux"])
        assert antes == 1 and sum(len([x for x in c.calls if x[0] == "synthesize"]) for c in rig.tts_clients) == 1
        r1, r2 = {r["passo"]: r["status"] for r in rig.ledger(1)}, {r["passo"]: r["status"] for r in rig.ledger(2)}
        assert r1 == {"tts": "concluido", "render_motion": "falhou", "mux": "cancelado"}  # history kept
        assert r2 == {"render_motion": "concluido", "mux": "concluido"}
        assert rig.etapa() == "aprovacao" and rig.post()["criacao_estado"] == "aguardando_aprovacao_midia"
        assert rig.post()["falha_codigo"] is None and len(rig.db.rows("cs_post_assets")) == 1
        enf = rig.eventos("criacao_enfileirada")
        assert len(enf) == 2  # failed -> na_fila again, one event each

    def test_only_a_failed_or_rejected_post_can_rerun(self, rig):
        async def go():
            await rig.service.enfileirar(POST, org_id=ORG)
            await rig.drain()
            with pytest.raises(CriacaoError) as e:
                await rig.service.reexecutar(POST, "render_motion", org_id=ORG)
            assert e.value.code == "reexecucao_indevida"
            rig.post()["criacao_estado"] = "na_fila"  # what the system mover leaves after a media rejection
            with pytest.raises(CriacaoError) as e:
                await rig.service.reexecutar(POST, "inexistente", org_id=ORG)
            assert e.value.code == "passo_desconhecido"
            return await rig.service.reexecutar(POST, "mux", org_id=ORG)

        out = run(go())
        assert (out["rodada"], out["passos"]) == (2, ["mux"])


# ── restart resume ──────────────────────────────────────────────────────────────────────────────────────────────────────


class TestRestart:
    def test_a_new_worker_process_resumes_from_the_job_payload_and_the_ledger(self, rig):
        async def go():
            await rig.service.enfileirar(POST, org_id=ORG)
            assert await rig.worker.run_once()  # tts only, then the "process dies"
            assert {r["passo"]: r["status"] for r in rig.ledger(1)}["tts"] == "concluido"
            antes = len(rig.tts_clients)
            rig.novo_runner()  # empty memory: no spec, no handler state, a different registry/runner/worker
            assert rig.runner._specs == {}
            await rig.drain()
            return antes

        run(go())
        assert {r["passo"]: r["status"] for r in rig.ledger(1)} == {
            "tts": "concluido", "render_motion": "concluido", "mux": "concluido"
        }
        assert rig.etapa() == "aprovacao" and len(rig.db.rows("cs_post_assets")) == 1
        # the render read the narration written by the dead worker's tts (storage), with the spec from the payload
        assert rig.progress.events[-1].terminal and rig.progress.events[-1].message == "Criação concluída"

    def test_progress_snapshot_of_a_running_graph_reads_the_ledger(self, rig):
        async def go():
            await rig.service.enfileirar(POST, org_id=ORG)
            first = await rig.service.snapshot(ORG, POST, 1)
            await rig.worker.run_once()
            return first, await rig.service.snapshot(ORG, POST, 1), await rig.service.snapshot(ORG, POST, 9)

        primeiro, meio, nenhum = run(go())
        assert (primeiro.status, primeiro.terminal) == ("na_fila", False)
        assert meio.status == "na_fila" and 0 < meio.progress < 0.2 and meio.terminal is False  # tts weighs 8 of 104
        assert nenhum is None


def test_progresso_marks_a_failure_terminal_with_its_code():
    from noctusai_lib.domain.media_production import PassoRow

    p = progresso_das_linhas([
        PassoRow(ORG, POST, 1, "tts", status="concluido"),
        PassoRow(ORG, POST, 1, "render_motion", status="falhou", erro_codigo="render_erro"),
    ], pesos=None)
    assert (p.status, p.terminal, p.message) == ("falhou", True, "Falhou: render_motion (render_erro)")
    assert PIPELINE_ESTEIRA.pipeline == "esteira"

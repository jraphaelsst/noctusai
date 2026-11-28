"""Julia "Vídeos Prontos" (julia-videos-prontos-youtube S2): pairing, debounce, processing, retry, outcomes.

Every collaborator is a constructor seam of `JuliaVideosProntosService` (fakes: `tests/support/
julia_videos_prontos_fakes.py`). No guard of ours is patched.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from uuid import uuid4

import pytest

from app.services import gdrive_service
from app.services import julia_videos_prontos_service as svc
from tests.support.julia_videos_prontos_fakes import (
    CONN, EDITOR, GRUPO, ID_A, ID_B, ORG, OUTRO, PASTA_A, PASTA_B, Video, World, run,
)


# ─── the parser ─────────────────────────────────────────────────────────────
class TestExtrair:
    def test_codigo_e_pasta_na_mesma_mensagem(self):
        e = svc.extrair(f"ONE10898 (EXCLUSIVIDADE)\n{PASTA_A}")
        assert (e.codigo, e.drive_folder_id, e.exclusividade) == ("ONE10898", ID_A, True)
        assert e.drive_folder_url == PASTA_A

    def test_codigo_nao_e_lido_de_dentro_do_link(self):
        e = svc.extrair("https://drive.google.com/drive/folders/1xyzABC12345defghijklmn")
        assert e.codigo is None and e.drive_folder_id == "1xyzABC12345defghijklmn"

    def test_codigo_minusculo_normalizado(self):
        assert svc.extrair("ca2411").codigo == "CA2411"

    def test_link_de_arquivo_nao_e_pasta(self):
        e = svc.extrair("https://drive.google.com/file/d/1abcDEF/view")
        assert e.drive_folder_id is None and not e.relevante

    def test_conversa_comum_ignorada(self):
        assert not svc.extrair("bom dia pessoal!").relevante


# ─── pairing + debounce ─────────────────────────────────────────────────────
class TestPareamento:
    def test_codigo_depois_link(self):
        w = World()
        w.upload.pastas[ID_A] = [Video("a", "youtube")]
        assert w.msg("ONE10898") == "aberta"
        w.relogio.avancar(3)
        assert w.msg(PASTA_A) == "atualizada"
        r = w.unica()
        assert (r["codigo"], r["drive_folder_id"], r["versao"]) == ("ONE10898", ID_A, 2)
        w.relogio.avancar(8)
        assert w.drenar() == ["obsoleto", svc.CONCLUIDO]  # v1 is stale; v2 runs
        assert w.unica()["status"] == svc.CONCLUIDO

    def test_link_depois_codigo(self):
        w = World()
        w.upload.pastas[ID_A] = [Video("a", "youtube")]
        w.msg(PASTA_A)
        w.relogio.avancar(2)
        w.msg("ONE10898 (EXCLUSIVIDADE)")
        w.relogio.avancar(8)
        w.drenar()
        r = w.unica()
        assert r["status"] == svc.CONCLUIDO and r["exclusividade"] is True

    def test_ambos_numa_mensagem(self):
        w = World()
        w.upload.pastas[ID_A] = [Video("a", "youtube")]
        w.msg(f"ONE10898 {PASTA_A}")
        w.relogio.avancar(8)
        assert w.drenar() == [svc.CONCLUIDO]

    def test_segunda_mensagem_reinicia_a_janela(self):
        w = World()
        w.upload.pastas[ID_A] = [Video("a", "youtube")]
        w.msg("ONE10898")
        w.relogio.avancar(6)
        w.msg(PASTA_A)
        w.relogio.avancar(3)  # 9 s after the first message, 3 s after the second: v1 is due, v2 is not
        assert w.drenar() == ["obsoleto"]
        assert w.unica()["status"] == svc.AGUARDANDO
        assert w.upload.fanouts == 0
        w.relogio.avancar(5)
        assert w.drenar() == [svc.CONCLUIDO]

    def test_dedupe_do_job_por_versao(self):
        w = World()
        w.msg("ONE10898")
        w.msg(PASTA_A)
        chaves = [j["dedupe_key"] for j in w.jobs.do_tipo(svc.JOB_PROCESSAR)]
        rid = w.unica()["id"]
        assert chaves == [f"vp:{rid}:v1", f"vp:{rid}:v2"]

    def test_entrega_duplicada_do_webhook_nao_duplica(self):
        w = World()
        assert w.msg("ONE10898", mid="m1") == "aberta"
        assert w.msg("ONE10898", mid="m1") == "duplicada"
        assert w.msg(PASTA_A, mid="m2") == "atualizada"
        assert w.msg(PASTA_A, mid="m2") == "duplicada"
        r = w.unica()
        assert r["versao"] == 2 and r["ids_mensagens"] == ["m1", "m2"]

    def test_entrega_duplicada_apos_processar_nao_reabre(self):
        w = World()
        w.upload.pastas[ID_A] = [Video("a", "youtube")]
        w.msg(f"ONE10898 {PASTA_A}", mid="m1")
        w.relogio.avancar(8)
        w.drenar()
        assert w.msg(f"ONE10898 {PASTA_A}", mid="m1") == "duplicada"
        assert len(w.repo.rows) == 1

    def test_reentrega_tardia_do_imovel_anterior_nao_fecha_o_atual(self):
        w = World()
        w.msg("ONE10898", mid="m1")
        w.msg("CA2411", mid="m2")  # closes ONE10898 (incompleto), opens CA2411
        assert w.msg("ONE10898", mid="m1") == "duplicada"
        aberta = w.repo.aberta(ORG, GRUPO, EDITOR)
        assert aberta is not None and aberta["codigo"] == "CA2411"

    def test_dois_imoveis_seguidos_ficam_separados(self):
        w = World()
        w.upload.pastas[ID_A] = [Video("a", "youtube")]
        w.upload.pastas[ID_B] = [Video("b", "youtube")]
        w.msg("ONE10898")
        w.msg(PASTA_A)
        w.relogio.avancar(2)
        w.msg("CA2411")  # a different property: the first slot is claimed now and a new one opens
        w.msg(PASTA_B)
        assert [j["type"] for j in w.jobs.fila].count(svc.JOB_EXECUTAR) == 1
        assert w.drenar() == [svc.CONCLUIDO]  # ONE10898's upload runs at once, not after the window
        w.relogio.avancar(8)
        assert w.drenar() == ["obsoleto", "obsoleto", "obsoleto", svc.CONCLUIDO]
        pares = sorted((r["codigo"], r["drive_folder_id"], r["status"]) for r in w.repo.rows.values())
        assert pares == [("CA2411", ID_B, svc.CONCLUIDO), ("ONE10898", ID_A, svc.CONCLUIDO)]

    def test_remetentes_diferentes_nao_se_misturam(self):
        w = World()
        w.msg("ONE10898", remetente=EDITOR)
        w.msg(PASTA_B, remetente=OUTRO)
        assert len(w.repo.rows) == 2
        assert {r["remetente"]: (r["codigo"], r["drive_folder_id"]) for r in w.repo.rows.values()} == {
            EDITOR: ("ONE10898", None), OUTRO: (None, ID_B)}

    def test_mensagem_sem_codigo_nem_link_ignorada(self):
        w = World()
        assert w.msg("subi agora pessoal") == "ignorada"
        assert w.repo.rows == {} and w.jobs.fila == []


# ─── processing outcomes ────────────────────────────────────────────────────
class TestProcessamento:
    def _enviar(self, w: World, texto: str = f"ONE10898 {PASTA_A}") -> dict:
        w.msg(texto)
        w.relogio.avancar(8)
        w.drenar()
        return w.unica()

    @pytest.mark.parametrize("texto,motivo", [("ONE10898", svc.MOTIVO_FALTOU_LINK), (PASTA_A, svc.MOTIVO_FALTOU_CODIGO)])
    def test_so_um_dos_dois_fica_incompleto_sem_upload(self, texto, motivo):
        w = World()
        r = self._enviar(w, texto)
        assert (r["status"], r["motivo"]) == (svc.INCOMPLETO, motivo)
        assert w.upload.fanouts == 0
        assert [k for k, _ in w.donos] == ["video_pronto_incompleto"]
        assert len(w.grupo) == 1 and "faltou" in w.grupo[0]
        assert "video_pronto_incompleto" in w.tipos()

    def test_um_video_horizontal_preenche_o_campo(self):
        w = World()
        w.upload.pastas[ID_A] = [Video("h", "youtube")]
        r = self._enviar(w)
        assert r["status"] == svc.CONCLUIDO and r["video_imovel_youtube_id"] == "yt_h"
        assert w.imovel.chamadas == [{"codigo": "ONE10898", "youtube_video_id": "yt_h", "origem": "julia",
                                      "motivo": svc.MOTIVO_CAMPO_IMOVEL, "upload_job_id": w.imovel.chamadas[0]["upload_job_id"]}]
        assert w.grupo == []  # success is never posted in the group
        kind, texto = w.donos[0]
        assert kind == "video_pronto_concluido" and "https://youtu.be/yt_h" in texto
        assert w.tipos()[:3] == ["video_pronto_recebido", "video_pronto_upload_iniciado", "video_pronto_concluido"]

    def test_um_video_vertical_nao_toca_o_campo(self):
        w = World()
        w.upload.pastas[ID_A] = [Video("v", "shorts")]
        r = self._enviar(w)
        assert r["status"] == svc.CONCLUIDO and r["video_imovel_youtube_id"] is None
        assert w.imovel.chamadas == []
        assert "https://youtube.com/shorts/yt_v" in w.donos[0][1]

    def test_varios_videos_todos_enviados_o_primeiro_horizontal_vai_ao_campo(self):
        w = World()
        w.upload.pastas[ID_A] = [Video("s1", "shorts"), Video("h1", "youtube"), Video("h2", "youtube")]
        r = self._enviar(w)
        assert r["status"] == svc.CONCLUIDO
        assert len(w.upload.execucoes) == 3
        assert [c["youtube_video_id"] for c in w.imovel.chamadas] == ["yt_h1"]

    def test_pasta_vazia(self):
        w = World()
        r = self._enviar(w)
        assert (r["status"], r["motivo"]) == (svc.SEM_VIDEOS, svc.MOTIVO_PASTA_VAZIA)
        assert [k for k, _ in w.donos] == ["video_pronto_sem_videos"]
        assert len(w.grupo) == 1 and "Não encontrei vídeos" in w.grupo[0]
        assert w.jobs.do_tipo(svc.JOB_RETRY) == []  # nothing to retry
        assert "video_pronto_sem_videos" in w.tipos()

    def test_pasta_inacessivel_avisa_o_grupo_na_hora(self):
        w = World()
        w.upload.pastas[ID_A] = gdrive_service.GoogleDriveError("403 forbidden")
        r = self._enviar(w)
        assert (r["status"], r["motivo"]) == (svc.FALHOU, svc.MOTIVO_PASTA_INACESSIVEL)
        assert len(w.grupo) == 1 and "compartilhada" in w.grupo[0]
        assert len(w.jobs.do_tipo(svc.JOB_RETRY)) == 1

    def test_imovel_inexistente(self):
        w = World()
        w.upload.pastas[ID_A] = [Video("a", "youtube")]
        r = self._enviar(w, f"ONE99999 {PASTA_A}")
        assert (r["status"], r["motivo"]) == (svc.FALHOU, svc.MOTIVO_IMOVEL_NAO_ENCONTRADO)
        assert w.upload.fanouts == 0

    def test_falha_parcial_mantem_os_sucessos(self):
        w = World()
        w.upload.pastas[ID_A] = [Video("ok", "youtube"), Video("ruim", "shorts", falhas=5)]
        r = self._enviar(w)
        assert r["status"] == svc.PARCIAL
        publicados = [j for j in w.upload.jobs.values() if j["status"] == "published"]
        assert [j["youtube_video_id"] for j in publicados] == ["yt_ok"]
        assert w.imovel.chamadas[0]["youtube_video_id"] == "yt_ok"
        assert w.grupo == []  # the first failure is retried before the group hears about it
        assert [k for k, _ in w.donos] == ["video_pronto_parcial"]


# ─── retry ──────────────────────────────────────────────────────────────────
class TestRetry:
    def test_retry_automatico_so_dos_falhos_e_sem_segundo(self):
        w = World()
        w.upload.pastas[ID_A] = [Video("ok", "youtube"), Video("ruim", "shorts", falhas=5)]
        w.msg(f"ONE10898 {PASTA_A}")
        w.relogio.avancar(8)
        w.drenar()
        [retry] = w.jobs.do_tipo(svc.JOB_RETRY)
        assert retry["scheduled_for"] == w.relogio.t + timedelta(seconds=120)
        w.relogio.avancar(60)
        assert w.drenar() == []  # not due yet
        w.relogio.avancar(60)
        assert w.drenar() == [svc.PARCIAL]
        r = w.unica()
        ruim = next(j for j in w.upload.jobs.values() if j["file_name"] == "ruim")
        assert w.upload.retentados == [ruim["id"]]  # the published child is never re-uploaded
        assert r["tentativas_retry"] == 1
        assert len(w.jobs.do_tipo(svc.JOB_RETRY)) == 1  # no second automatic retry
        assert len(w.grupo) == 1 and "mesmo depois de tentar de novo" in w.grupo[0]
        assert [k for k, _ in w.donos] == ["video_pronto_parcial", "video_pronto_parcial"]
        assert len(w.imovel.chamadas) == 1  # the field was written once

    def test_retry_que_recupera_conclui(self):
        w = World()
        w.upload.pastas[ID_A] = [Video("ok", "youtube"), Video("tarde", "youtube", falhas=1)]
        w.msg(f"ONE10898 {PASTA_A}")
        w.relogio.avancar(8)
        w.drenar()
        w.relogio.avancar(120)
        assert w.drenar() == [svc.CONCLUIDO]
        assert w.grupo == []
        assert w.donos[-1][0] == "video_pronto_concluido" and "após nova tentativa" in w.donos[-1][1]

    def test_retry_de_fanout_que_falhou_refaz_a_pasta(self):
        w = World()
        w.upload.pastas[ID_A] = gdrive_service.GoogleDriveError("timeout")
        w.msg(f"ONE10898 {PASTA_A}")
        w.relogio.avancar(8)
        w.drenar()
        w.upload.pastas[ID_A] = [Video("a", "youtube")]
        w.relogio.avancar(120)
        assert w.drenar() == [svc.CONCLUIDO]
        assert w.upload.fanouts == 2

    def test_retry_manual_depois_do_automatico(self):
        w = World()
        w.upload.pastas[ID_A] = [Video("ruim", "youtube", falhas=2)]
        w.msg(f"ONE10898 {PASTA_A}")
        w.relogio.avancar(8)
        w.drenar()
        w.relogio.avancar(120)
        assert w.drenar() == [svc.FALHOU]
        rid = w.unica()["id"]
        out = run(w.service.solicitar_retry(ORG, rid, ator_id="u1"))
        assert out == {"submissao_id": rid, "tentativa": 2, "agendado": True}
        assert w.drenar() == [svc.CONCLUIDO]
        assert w.unica()["tentativas_retry"] == 2

    def test_retry_manual_recusa_o_que_nao_e_retentavel(self):
        w = World()
        w.upload.pastas[ID_A] = [Video("a", "youtube")]
        w.msg(f"ONE10898 {PASTA_A}")
        w.relogio.avancar(8)
        w.drenar()
        with pytest.raises(svc.RetryRecusado):
            run(w.service.solicitar_retry(ORG, w.unica()["id"], ator_id="u1"))
        with pytest.raises(svc.SubmissaoNaoEncontrada):
            run(w.service.solicitar_retry("99999999-9999-9999-9999-999999999999", w.unica()["id"], ator_id="u1"))


# ─── remake replaces / identical file skipped (owner 2026-11-28) ────────────
class TestRefacao:
    def _postar(self, w: World, texto: str = f"ONE10898 {PASTA_A}", remetente: str = EDITOR) -> None:
        w.msg(texto, remetente=remetente)
        w.relogio.avancar(8)
        w.drenar()
        w.relogio.avancar(600)

    def _ultima(self, w: World) -> dict:
        return max(w.repo.rows.values(), key=lambda r: list(w.repo.rows).index(r["id"]))

    def test_o_fluxo_pede_o_skip_por_arquivo_ao_modulo_youtube(self):
        w = World()
        w.upload.pastas[ID_A] = [Video("h", "youtube")]
        self._postar(w)
        assert w.upload.skip_pedido == [True]

    def test_reenvio_depois_de_pasta_vazia_e_permitido(self):
        w = World()
        self._postar(w)
        w.upload.pastas[ID_A] = [Video("a", "youtube")]
        self._postar(w)
        assert sorted(r["status"] for r in w.repo.rows.values()) == [svc.CONCLUIDO, svc.SEM_VIDEOS]

    def test_arquivo_identico_repostado_e_ignorado_ja_publicado(self):
        w = World()
        w.upload.pastas[ID_A] = [Video("h", "youtube"), Video("s", "shorts")]
        self._postar(w)
        privados_antes, execucoes_antes, donos_antes = list(w.youtube.privados), len(w.upload.execucoes), len(w.donos)
        self._postar(w)  # the same code + folder, the same files
        novo = self._ultima(w)
        assert (novo["status"], novo["motivo"]) == (svc.JA_PUBLICADO, svc.MOTIVO_JA_PUBLICADO)
        assert len(w.upload.execucoes) == execucoes_antes  # nothing uploaded
        assert w.youtube.privados == privados_antes  # no YouTube call
        assert novo["batch_id"] is None
        kind, texto = w.donos[donos_antes]
        assert kind == "video_pronto_ja_publicado" and "nada novo" in texto and "https://youtu.be/yt_h" in texto
        assert w.grupo == []  # nothing in the group
        assert w.jobs.do_tipo(svc.JOB_RETRY) == []
        assert "video_pronto_ja_publicado" in w.tipos()
        assert len(w.imovel.chamadas) == 1  # the field is not touched again

    def test_refacao_sobe_o_novo_privatiza_o_antigo_e_move_o_campo(self):
        w = World()
        antigo = w.upload.publicado_antes("ONE10898", "velho", "youtube")
        w.imovel.apontar("ONE10898", "yt_velho", "julia")
        w.upload.pastas[ID_A] = [Video("novo", "youtube")]
        self._postar(w)
        r = w.unica()
        assert r["status"] == svc.CONCLUIDO
        assert w.youtube.privados == ["yt_velho"]
        assert w.upload.jobs[antigo["id"]]["privacy_status"] == "private"  # the catalog mirror
        assert w.imovel.atual["ONE10898"].youtube_video_id == "yt_novo"
        assert [c["youtube_video_id"] for c in w.imovel.chamadas] == ["yt_novo"]
        ev = [p for t, p in w.eventos if t == "video_pronto_substituido"]
        assert ev == [{"submissao_id": r["id"], "codigo": "ONE10898", "batch_id": r["batch_id"],
                       "youtube_video_id": "yt_velho", "upload_job_id": antigo["id"], "target_format": "youtube",
                       "resultado": "privado", "origem": "upload_job"}]
        kind, texto = w.donos[-1]
        assert kind == "video_pronto_concluido"
        assert "https://youtu.be/yt_novo" in texto and "ficaram privados" in texto and "https://youtu.be/yt_velho" in texto

    def test_pasta_com_um_identico_e_um_novo_so_o_novo_sobe_e_so_o_seu_tipo_e_substituido(self):
        w = World()
        w.upload.pastas[ID_A] = [Video("h1", "youtube"), Video("s1", "shorts")]
        self._postar(w)
        assert w.youtube.privados == []
        # the editor re-edits the Short only and re-posts the same folder
        w.upload.pastas[ID_A] = [Video("h1", "youtube"), Video("s2", "shorts")]
        self._postar(w)
        novo = self._ultima(w)
        assert novo["status"] == svc.CONCLUIDO
        do_lote = [j for j in w.upload.jobs.values() if j["batch_id"] == novo["batch_id"]]
        assert [j["file_name"] for j in do_lote] == ["s2"]  # the identical standard video is not uploaded again
        assert w.youtube.privados == ["yt_s1"]  # only the Short kind is superseded; yt_h1 stays public
        assert w.imovel.atual["ONE10898"].youtube_video_id == "yt_h1"  # Shorts never move the field
        assert "1 arquivo(s) da pasta já estavam publicados" in w.donos[-1][1]

    def test_novo_upload_que_falha_nao_privatiza_o_antigo(self):
        w = World()
        w.upload.publicado_antes("ONE10898", "velho", "youtube")
        w.imovel.apontar("ONE10898", "yt_velho", "julia")
        w.upload.pastas[ID_A] = [Video("novo", "youtube", falhas=5)]
        self._postar(w)
        assert w.unica()["status"] == svc.FALHOU
        assert w.youtube.privados == []
        assert w.imovel.atual["ONE10898"].youtube_video_id == "yt_velho"
        assert "video_pronto_substituido" not in w.tipos()

    def test_privacidade_recusada_e_registrada_e_a_submissao_conclui(self):
        w = World()
        w.upload.publicado_antes("ONE10898", "velho", "youtube")
        w.youtube.recusar.add("yt_velho")
        w.upload.pastas[ID_A] = [Video("novo", "youtube")]
        self._postar(w)
        assert w.unica()["status"] == svc.CONCLUIDO
        ev = [p for t, p in w.eventos if t == "video_pronto_substituido"]
        assert [(e["youtube_video_id"], e["resultado"], e["erro"]) for e in ev] == [("yt_velho", "recusado", "YouTubeServiceError")]
        assert "Não consegui deixar privados" in w.donos[-1][1]
        assert w.imovel.atual["ONE10898"].youtube_video_id == "yt_novo"  # the field still moves

    def test_refacao_so_de_shorts_privatiza_os_shorts_antigos_e_nao_toca_o_campo(self):
        w = World()
        w.upload.publicado_antes("ONE10898", "padrao", "youtube")
        w.upload.publicado_antes("ONE10898", "short_velho", "shorts")
        w.imovel.apontar("ONE10898", "yt_padrao", "julia")
        w.upload.pastas[ID_A] = [Video("short_novo", "shorts")]
        self._postar(w)
        assert w.unica()["status"] == svc.CONCLUIDO
        assert w.youtube.privados == ["yt_short_velho"]
        assert w.imovel.chamadas == [] and w.imovel.atual["ONE10898"].youtube_video_id == "yt_padrao"

    def test_campo_apontando_para_video_do_vista_tenta_privatizar_e_tolera_a_recusa(self):
        w = World()
        w.imovel.apontar("ONE10898", "VISTA123456", "vista")
        w.youtube.recusar.add("VISTA123456")  # not our channel
        w.upload.pastas[ID_A] = [Video("novo", "youtube")]
        self._postar(w)
        assert w.unica()["status"] == svc.CONCLUIDO
        ev = [p for t, p in w.eventos if t == "video_pronto_substituido"]
        assert [(e["youtube_video_id"], e["resultado"], e["origem"]) for e in ev] == [("VISTA123456", "recusado", "extra")]
        assert w.imovel.atual["ONE10898"].youtube_video_id == "yt_novo"

    def test_campo_apontando_para_video_manual_e_privatizado(self):
        w = World()
        w.imovel.apontar("ONE10898", "MANUAL12345", "manual")
        w.upload.pastas[ID_A] = [Video("novo", "youtube")]
        self._postar(w)
        assert w.youtube.privados == ["MANUAL12345"]

    def test_retry_nao_privatiza_o_que_o_proprio_lote_publicou(self):
        w = World()
        w.upload.publicado_antes("ONE10898", "velho", "youtube")
        w.upload.pastas[ID_A] = [Video("ok", "youtube"), Video("tarde", "youtube", falhas=1)]
        w.msg(f"ONE10898 {PASTA_A}")
        w.relogio.avancar(8)
        w.drenar()
        w.relogio.avancar(120)
        assert w.drenar() == [svc.CONCLUIDO]
        assert w.youtube.privados == ["yt_velho"]  # once; yt_ok (same batch) never superseded

    def test_falha_do_passo_de_substituicao_inteiro_nao_derruba_o_upload(self):
        w = World()

        def quebra(org):
            raise RuntimeError("no credentials")

        w.service._ciclo_video_factory = quebra  # the constructor seam, swapped for this scenario
        w.upload.pastas[ID_A] = [Video("novo", "youtube")]
        self._postar(w)
        assert w.unica()["status"] == svc.CONCLUIDO
        assert ("acao_falhou", {"acao": "video_pronto_substituir", "submissao_id": w.unica()["id"],
                                "codigo": "ONE10898"}) in w.eventos


# ─── the webhook entry ──────────────────────────────────────────────────────
class TestWebhook:
    def _ingerir(self, w: World, texto: str, chat: str = GRUPO, org: str = ORG) -> str:
        svc.limpar_cache_config()
        return run(svc.ingerir_do_webhook(org_id=org, connection_id=CONN, chat_id=chat, remetente=EDITOR,
                                          mensagem_id=str(uuid4()), texto=texto, service_factory=lambda: w.service))

    def test_grupo_ativo_entra(self):
        w = World()
        assert self._ingerir(w, "ONE10898") == "aberta"

    def test_outro_grupo_fora(self):
        w = World()
        assert self._ingerir(w, "ONE10898", chat="999@g.us") == "fora"
        assert w.repo.rows == {}

    def test_config_desligada_fora(self):
        w = World()
        w.repo.configs[ORG]["ativo"] = False
        assert self._ingerir(w, "ONE10898") == "fora"

    def test_sem_codigo_nem_link_nem_consulta(self):
        def nunca():
            raise AssertionError("the service is not even built for an irrelevant message")

        svc.limpar_cache_config()
        assert run(svc.ingerir_do_webhook(org_id=ORG, connection_id=CONN, chat_id=GRUPO, remetente=EDITOR,
                                          mensagem_id="x", texto="ok!", service_factory=nunca)) == "ignorada"

    def test_erro_nunca_escapa(self, caplog):
        def quebra():
            raise RuntimeError("boom")

        svc.limpar_cache_config()
        eventos: list = []
        out = run(svc.ingerir_do_webhook(org_id=ORG, connection_id=CONN, chat_id=GRUPO, remetente=EDITOR,
                                         mensagem_id="x", texto="ONE10898", service_factory=quebra,
                                         emitir=lambda org, tipo, payload: eventos.append((tipo, payload))))
        assert out == "erro"
        assert any("NOT ingested" in r.getMessage() for r in caplog.records)
        assert eventos == [("acao_falhou", {"acao": "video_pronto_receber", "motivo": "RuntimeError"})]


# ─── the job handlers ───────────────────────────────────────────────────────
class TestHandlers:
    def test_handlers_despacham_para_o_servico(self):
        w = World()
        w.upload.pastas[ID_A] = [Video("a", "youtube")]
        w.msg(f"ONE10898 {PASTA_A}")
        h = svc.handlers(service_factory=lambda: w.service)
        assert set(h) == {svc.JOB_PROCESSAR, svc.JOB_RETRY, svc.JOB_EXECUTAR}

        @dataclass
        class J:
            payload: dict

        job = w.jobs.do_tipo(svc.JOB_PROCESSAR)[0]
        run(h[svc.JOB_PROCESSAR](J(job["payload"])))
        assert w.unica()["status"] == svc.CONCLUIDO

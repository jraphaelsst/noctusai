"""Fakes for Julia "Vídeos Prontos" (julia-videos-prontos-youtube S2): every collaborator of
`JuliaVideosProntosService` -- the repository (with the open-slot partial UNIQUE index of migration 372), the job queue
(dedupe keys), the YouTube `UploadService` (one `upload_jobs` table; the opt-in per-file skip of an already-published
Drive file), the metadata resolver, S1's property-field service, the owner notifier, the group sender and the event
emitter -- plus a `World` wiring them. The property-video lifecycle is the REAL `ProductVideoLifecycle` over a fake
job lookup / YouTube privacy call / catalog mirror (the supersede rule itself is exercised, not faked)."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID, uuid4

from app.modules.youtube.services.upload import BatchChild, BatchQueued, SkippedFile, UploadServiceError
from app.modules.youtube.services.upload_metadata import PropertyNotFound
from app.modules.youtube.services.video_lifecycle import ProductVideoLifecycle
from app.modules.youtube.services.youtube import YouTubeServiceError
from app.services.imovel_video_youtube_service import ImovelVideoYoutube, url_de
from app.services import gdrive_service
from app.services import julia_videos_prontos_service as svc

ORG = "11111111-1111-1111-1111-111111111111"
CONN = "22222222-2222-2222-2222-222222222222"
GRUPO = "120363369180055435@g.us"
EDITOR = "5541999990000@c.us"
OUTRO = "5541988880000@c.us"
PASTA_A = "https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOpQrStUvWxYz012345?usp=sharing"
ID_A = "1AbCdEfGhIjKlMnOpQrStUvWxYz012345"
PASTA_B = "https://drive.google.com/drive/folders/1ZyXwVuTsRqPoNmLkJiHgFeDcBa98765"
ID_B = "1ZyXwVuTsRqPoNmLkJiHgFeDcBa98765"


def run(coro):
    return asyncio.run(coro)


# ─── fakes ──────────────────────────────────────────────────────────────────
class FakeRepo:
    """In memory, with migration 372's guard: one OPEN slot per (org, chat, sender) (an insert that would break it is
    refused)."""

    def __init__(self, uploads: "FakeUpload") -> None:
        self.rows: dict[str, dict] = {}
        self.eventos: list[tuple[str, str, str]] = []  # (id, de, para)
        self.configs: dict[str, dict] = {}
        self.uploads = uploads

    def config_ativa(self, connection_id, chat_id):
        return next((c for c in self.configs.values() if c["connection_id"] == str(connection_id)
                     and c["chat_id"] == chat_id and c["ativo"]), None)

    def config_da_org(self, org_id):
        return self.configs.get(str(org_id))

    def aberta(self, org_id, chat_id, remetente):
        return next((dict(r) for r in self.rows.values() if r["org_id"] == str(org_id) and r["chat_id"] == chat_id
                     and r["remetente"] == remetente and r["status"] == svc.AGUARDANDO), None)

    def mensagem_ja_vista(self, org_id, chat_id, mensagem_id):
        return any(mensagem_id in r["ids_mensagens"] for r in self.rows.values()
                   if r["org_id"] == str(org_id) and r["chat_id"] == chat_id)

    def obter(self, submissao_id):
        r = self.rows.get(str(submissao_id))
        return dict(r) if r else None

    def criar(self, org_id, row):
        if self.aberta(org_id, row["chat_id"], row["remetente"]) is not None:
            return None  # julia_videos_prontos_submissoes_aberta_uq
        rid = str(uuid4())
        self.rows[rid] = {"id": rid, "org_id": str(org_id), "batch_id": None, "tentativas_retry": 0, "motivo": None,
                          "erro": None, "video_imovel_youtube_id": None, **row}
        self.eventos.append((rid, None, svc.AGUARDANDO))
        return dict(self.rows[rid])

    def atualizar_aberta(self, submissao_id, *, versao_esperada, campos):
        r = self.rows.get(str(submissao_id))
        if r is None or r["status"] != svc.AGUARDANDO or r["versao"] != versao_esperada:
            return False
        r.update(campos)
        return True

    def atualizar(self, submissao_id, campos):
        self.rows[str(submissao_id)].update(campos)

    def transicionar(self, org_id, submissao_id, *, de, para, evento, dados, ator_id=None):
        r = self.rows.get(str(submissao_id))
        if r is None or r["status"] != de:
            return False
        r["status"] = para
        self.eventos.append((r["id"], de, para))
        return True

    def jobs_do_lote(self, batch_id):
        return [dict(j) for j in self.uploads.jobs.values() if j["batch_id"] == str(batch_id)]

    def listar(self, org_id, limite):
        return [dict(r) for r in self.rows.values() if r["org_id"] == str(org_id)][:limite]


class FakeJobs:
    def __init__(self) -> None:
        self.fila: list[dict] = []
        self._chaves: set[str] = set()

    async def enqueue(self, *, type, payload, max_retries=3, scheduled_for=None, dedupe_key=None):
        if dedupe_key in self._chaves:
            return None
        self._chaves.add(dedupe_key)
        self.fila.append({"type": type, "payload": dict(payload), "scheduled_for": scheduled_for, "dedupe_key": dedupe_key})
        return self.fila[-1]

    def do_tipo(self, tipo):
        return [j for j in self.fila if j["type"] == tipo]


@dataclass
class Video:
    nome: str
    formato: str  # youtube | shorts
    falhas: int = 0  # how many runs fail before it publishes
    file_id: Optional[str] = None  # the Drive file id (default: derived from the name -- the same file on every post)
    tamanho: int = 100

    @property
    def drive_id(self) -> str:
        return self.file_id or f"drv_{self.nome}"


class FakeUpload:
    """The `UploadService` slice: one `upload_jobs` row per video of the folder; `run_upload_job` publishes it (with
    the worker's `target_format`) or flips it to failed, as scripted."""

    def __init__(self) -> None:
        self.pastas: dict[str, list[Video] | Exception] = {}
        self.jobs: dict[str, dict] = {}
        self.roteiro: dict[str, Video] = {}
        self.execucoes: list[str] = []
        self.retentados: list[str] = []
        self.fanouts = 0
        self.skip_pedido: list[bool] = []
        self._seq = 0

    def _novo_job(self, **campos) -> dict:
        self._seq += 1
        jid = str(uuid4())
        self.jobs[jid] = {"id": jid, "status": "queued", "youtube_video_id": None, "target_format": "unknown",
                          "privacy_status": "public", "seq": self._seq, **campos}
        return self.jobs[jid]

    def publicado_antes(self, codigo: str, nome: str, formato: str, *, file_id: Optional[str] = None,
                        tamanho: int = 100, privacy: str = "public") -> dict:
        """A video of the property published by an EARLIER upload (another batch)."""
        return self._novo_job(batch_id=str(uuid4()), product_code=codigo, file_name=nome, status="published",
                              youtube_video_id=f"yt_{nome}", target_format=formato,
                              source_file_id=file_id or f"drv_{nome}", file_size_bytes=tamanho, privacy_status=privacy)

    def queue_drive_folder_upload(self, *, org_id, created_by, metadata, drive_folder_url,
                                  skip_published_for_product=False):
        self.fanouts += 1
        self.skip_pedido.append(skip_published_for_product)
        conteudo = self.pastas.get(gdrive_service.parse_folder_id(drive_folder_url), [])
        if isinstance(conteudo, Exception):
            raise UploadServiceError("Drive folder fanout failed") from conteudo
        if not conteudo:
            raise UploadServiceError("Drive folder fanout failed") from gdrive_service.DriveFolderEmpty("no videos")
        codigo = metadata["title"]
        batch = uuid4()
        filhos, ignorados = [], []
        for v in conteudo:
            ja = next((j for j in self.jobs.values() if skip_published_for_product and j.get("product_code") == codigo
                       and j["status"] in ("published", "notified") and j.get("source_file_id") == v.drive_id
                       and j.get("file_size_bytes") == v.tamanho), None)
            if ja is not None:
                ignorados.append(SkippedFile(file_name=v.nome, drive_file_id=v.drive_id, upload_job_id=ja["id"],
                                             youtube_video_id=ja["youtube_video_id"], target_format=ja["target_format"]))
                continue
            job = self._novo_job(batch_id=str(batch), product_code=codigo, file_name=v.nome, metadata=metadata,
                                 source_file_id=v.drive_id, file_size_bytes=v.tamanho,
                                 privacy_status=metadata["privacy_status"])
            self.roteiro[job["id"]] = Video(v.nome, v.formato, v.falhas, v.file_id, v.tamanho)
            filhos.append(BatchChild(job_id=UUID(job["id"]), file_name=v.nome, parent_subfolder=None))
        return BatchQueued(batch_id=batch, children=filhos, skipped=ignorados)

    def run_upload_job(self, *, job_id):
        jid = str(job_id)
        self.execucoes.append(jid)
        v = self.roteiro[jid]
        if v.falhas > 0:
            v.falhas -= 1
            self.jobs[jid].update(status="failed", target_format=v.formato)
            return
        self.jobs[jid].update(status="published", youtube_video_id=f"yt_{v.nome}", target_format=v.formato)

    def retry_failed_job(self, *, job_id, org_id):
        jid = str(job_id)
        assert self.jobs[jid]["status"] == "failed", "retry_failed_job requires status=failed"
        self.retentados.append(jid)
        self.jobs[jid]["status"] = "queued"
        return self.jobs[jid]


class FakeImovelVideo:
    """S1's property field: `obter` / `definir` (replace)."""

    def __init__(self) -> None:
        self.chamadas: list[dict] = []
        self.atual: dict[str, ImovelVideoYoutube] = {}

    def apontar(self, codigo: str, video_id: str, origem: str) -> None:
        self.atual[codigo] = ImovelVideoYoutube(org_id=ORG, codigo=codigo, youtube_video_id=video_id,
                                                youtube_url=url_de(video_id), origem=origem)

    def obter(self, org_id, codigo):
        return self.atual.get(codigo)

    def definir(self, org_id, codigo, *, youtube_video_id, origem, motivo, upload_job_id):
        self.chamadas.append({"codigo": codigo, "youtube_video_id": youtube_video_id, "origem": origem, "motivo": motivo,
                              "upload_job_id": upload_job_id})
        self.apontar(codigo, youtube_video_id, origem)


class FakeLookup:
    """`SupabaseJobLookup.list_jobs` over the fake `upload_jobs` (newest first)."""

    def __init__(self, uploads: FakeUpload) -> None:
        self.uploads = uploads

    def list_jobs(self, code):
        rows = [dict(j) for j in self.uploads.jobs.values() if j.get("product_code") == code.upper()]
        return sorted(rows, key=lambda j: j["seq"], reverse=True)


class FakeYouTube:
    """`YouTubeService.update_video_metadata`: records every privacy change; `recusar` = videos it refuses."""

    def __init__(self) -> None:
        self.privados: list[str] = []
        self.recusar: set[str] = set()

    def update_video_metadata(self, *, org_id, video_id, privacy_status=None, title=None, description=None):
        if video_id in self.recusar:
            raise YouTubeServiceError("YouTube API error 403: forbidden")
        assert privacy_status == "private"
        self.privados.append(video_id)


class FakeCatalog:
    def __init__(self, uploads: FakeUpload) -> None:
        self.uploads = uploads

    def mirror_update(self, video_id, patch):
        for j in self.uploads.jobs.values():
            if j.get("youtube_video_id") == video_id:
                j.update(patch)


class Relogio:
    def __init__(self) -> None:
        self.t = datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.t

    def avancar(self, s: float) -> None:
        self.t += timedelta(seconds=s)


class World:
    def __init__(self, org: str = ORG, *, ciclo_video_factory=None) -> None:
        self.org = org
        self.upload = FakeUpload()
        self.repo = FakeRepo(self.upload)
        self.repo.configs[org] = {"org_id": org, "connection_id": CONN, "chat_id": GRUPO, "ativo": True,
                                  "privacy_status": "public"}
        self.jobs = FakeJobs()
        self.imovel = FakeImovelVideo()
        self.youtube = FakeYouTube()
        self.donos: list[tuple[str, str]] = []
        self.grupo: list[str] = []
        self.eventos: list[tuple[str, dict]] = []
        self.relogio = Relogio()
        self.catalogo = {"ONE10898", "CA2411", "ONE20000"}
        self.service = svc.JuliaVideosProntosService(
            repo=self.repo, jobs=self.jobs, upload_factory=lambda: self.upload, resolver_metadados=self._resolver,
            imovel_video_factory=lambda: self.imovel,
            ciclo_video_factory=ciclo_video_factory or (lambda org: ProductVideoLifecycle(
                org_id=org, jobs=FakeLookup(self.upload), youtube=self.youtube, catalog=FakeCatalog(self.upload))),
            notificar=self._notificar, enviar_grupo=self._grupo,
            emitir=lambda org, tipo, payload: self.eventos.append((tipo, payload)),
            wait_seconds=8.0, retry_delay_seconds=120.0, agora=self.relogio,
        )

    def _resolver(self, org_id, codigo, privacy):
        if codigo not in self.catalogo:
            raise PropertyNotFound(codigo)
        return {"title": codigo, "privacy_status": privacy}

    async def _notificar(self, org_id, kind, assunto, texto):
        self.donos.append((kind, texto))

    async def _grupo(self, org_id, connection_id, chat_id, texto):
        assert chat_id == GRUPO
        self.grupo.append(texto)
        return None

    def msg(self, texto: str, *, mid: Optional[str] = None, remetente: str = EDITOR) -> str:
        return run(self.service.receber(org_id=self.org, connection_id=CONN, chat_id=GRUPO, remetente=remetente,
                                        mensagem_id=mid or str(uuid4()), texto=texto))

    def drenar(self) -> list[str]:
        """Run every queued job that is DUE now (in enqueue order), the way the worker would."""
        saidas = []
        while True:
            devidos = [j for j in self.jobs.fila if not j.get("feito") and j["scheduled_for"] <= self.relogio.t]
            if not devidos:
                return saidas
            job = devidos[0]
            job["feito"] = True
            p = job["payload"]
            if job["type"] == svc.JOB_PROCESSAR:
                saidas.append(run(self.service.processar(p["submissao_id"], p["versao"])))
            elif job["type"] == svc.JOB_EXECUTAR:
                saidas.append(run(self.service.executar(p["submissao_id"])))
            else:
                saidas.append(run(self.service.retry(p["submissao_id"], p["tentativa"], ator_id=p.get("ator_id"))))

    def unica(self) -> dict:
        assert len(self.repo.rows) == 1, self.repo.rows
        return next(iter(self.repo.rows.values()))

    def tipos(self) -> list[str]:
        return [t for t, _ in self.eventos]

"""HTTP client + MCP registration for ``noctus.transcription.*``.

Server errors surface as ``{codigo, mensagem, status_code, retry_after}``;
client-side refusals (no token, bad file) use the same shape with
``status_code: None``. The token is read from the environment per call and is
never logged or placed in any returned value.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Callable

import httpx

DEFAULT_URL = "https://core.noctusai.com"
MAX_BYTES = 150 * 1024 * 1024
TERMINAL = frozenset({"concluida", "falhou", "cancelada"})
_FAST_POLL_S = 5.0
#: Transient statuses: rate limit (429), capacity (503) and the GATEWAY errors a core/tunnel restart
#: answers with (502/504). None of them is a job result -- the job keeps running server-side -- so
#: they are retried, never recorded as a failure (2026-11-14: a core redeploy turned 31 live jobs into
#: "failed" 502s). A long outage is still bounded by the batch's no-progress window.
#: 2026-11-15: Cloudflare's 52x family (530 = origin unreachable, a tunnel blip) is the same class --
#: three accepted jobs were dropped as "HTTP 530" failures although they finished server-side.
_TRANSIENT = frozenset({429, 502, 503, 504, *range(520, 531)})
_SLOW_POLL_S = 30.0
_FAST_WINDOW_S = 60.0
_MAX_SUBMIT_WAIT_S = 120.0
_HTTP_TIMEOUT = httpx.Timeout(60.0, connect=15.0, read=300.0, write=600.0)


def _error(codigo: str, mensagem: str, status_code: int | None = None,
           retry_after: float | None = None) -> dict[str, Any]:
    return {"codigo": codigo, "mensagem": mensagem,
            "status_code": status_code, "retry_after": retry_after}


def _retry_after(resp: httpx.Response) -> float | None:
    raw = resp.headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        return None


def _server_error(resp: httpx.Response) -> dict[str, Any]:
    codigo, mensagem = "erro_desconhecido", f"HTTP {resp.status_code}"
    try:
        body = resp.json()
    except ValueError:
        body = None
    if isinstance(body, dict):
        env = body.get("detail") if isinstance(body.get("detail"), dict) else body
        codigo = str(env.get("codigo") or codigo)
        mensagem = str(env.get("mensagem") or mensagem)
    return _error(codigo, mensagem, resp.status_code, _retry_after(resp))


def _config() -> tuple[str, str] | dict[str, Any]:
    token = os.environ.get("NOCTUS_TRANSCRIPTION_TOKEN", "").strip()
    if not token:
        return _error("nao_configurado",
                      "NOCTUS_TRANSCRIPTION_TOKEN ausente (token pk_* com escopo "
                      "transcription:write/read). Defina no .env da raiz.")
    url = (os.environ.get("NOCTUS_TRANSCRIPTION_URL", "").strip()
           or os.environ.get("NOCTUS_CORE_APP_URL", "").strip() or DEFAULT_URL)
    return url.rstrip("/"), token


def _client(base: str, token: str, transport: httpx.BaseTransport | None) -> httpx.Client:
    return httpx.Client(base_url=base, headers={"Authorization": f"Bearer {token}"},
                        timeout=_HTTP_TIMEOUT, transport=transport)


def _request(method: str, path: str, transport: httpx.BaseTransport | None = None,
             **kwargs: Any) -> tuple[httpx.Response | None, dict[str, Any] | None]:
    cfg = _config()
    if isinstance(cfg, dict):
        return None, cfg
    base, token = cfg
    try:
        with _client(base, token, transport) as c:
            return c.request(method, path, **kwargs), None
    except httpx.HTTPError as exc:
        # str(exc) never contains the Authorization header.
        return None, _error("erro_de_rede", f"{type(exc).__name__}: {exc}")


def _preflight(path: str) -> tuple[Path | None, dict[str, Any] | None]:
    p = Path(path).expanduser()
    if not p.is_file():
        return None, _error("arquivo_invalido", f"Arquivo não encontrado: {path}")
    if not os.access(p, os.R_OK):
        return None, _error("arquivo_invalido", f"Arquivo ilegível: {path}")
    size = p.stat().st_size
    if size == 0:
        return None, _error("audio_vazio", f"Arquivo vazio: {path}")
    if size > MAX_BYTES:
        return None, _error("arquivo_grande",
                            f"Arquivo de {size} bytes excede o limite de 150 MB; nada foi enviado.")
    return p, None


def submit(path: str, idioma: str = "pt", rotulo: str | None = None,
           segmentos: bool = False, palavras: bool = False, *,
           _transport: httpx.BaseTransport | None = None) -> dict:
    """POST multipart to /api/transcriptions; return the 202 body or an error dict."""
    cfg = _config()
    if isinstance(cfg, dict):
        return cfg  # token check precedes any file I/O or request
    p, err = _preflight(path)
    if err:
        return err
    data = {"idioma": idioma, "segmentos": "true" if segmentos else "false"}
    if palavras:
        data["palavras"] = "true"
    if rotulo:
        data["rotulo"] = rotulo
    with p.open("rb") as fh:
        resp, err = _request("POST", "/api/transcriptions", _transport,
                             data=data, files={"arquivo": (p.name, fh)})
    if err:
        return err
    if resp.status_code != 202:
        return _server_error(resp)
    return resp.json()


def get(id: str, *, _transport: httpx.BaseTransport | None = None) -> dict:
    """GET /api/transcriptions/{id}; return the job or an error dict."""
    resp, err = _request("GET", f"/api/transcriptions/{id}", _transport)
    if err:
        return err
    if resp.status_code != 200:
        return _server_error(resp)
    return resp.json()


def transcribe(path: str, idioma: str = "pt", rotulo: str | None = None,
               timeout_s: float = 3600, segmentos: bool = False, palavras: bool = False, *,
               _transport: httpx.BaseTransport | None = None,
               _sleep: Callable[[float], None] = time.sleep,
               _clock: Callable[[], float] = time.monotonic) -> dict:
    """Submit, poll (5 s for the first minute, then 30 s; honours Retry-After).

    ``segmentos=True`` asks the server for timestamped segments and returns them
    under ``segmentos`` — the reason callers used to fall back to local Whisper.
    ``palavras=True`` also adds ``palavras: [{texto, inicio, fim, confianca}]`` to each segment.
    """
    start = _clock()

    def remaining() -> float:
        return timeout_s - (_clock() - start)

    while True:
        job = submit(path, idioma=idioma, rotulo=rotulo, segmentos=segmentos,
                     palavras=palavras, _transport=_transport)
        ra = None
        if "codigo" in job and job.get("status_code") in _TRANSIENT:
            ra = job.get("retry_after") or _FAST_POLL_S
        if ra is not None and ra <= _MAX_SUBMIT_WAIT_S and remaining() > ra:
            _sleep(ra)
            continue
        break
    if "codigo" in job:
        return job
    job_id = job["id"]
    started = _clock()
    while True:
        cur = get(job_id, _transport=_transport)
        wait: float | None = None
        if "codigo" in cur:
            if cur.get("status_code") in _TRANSIENT:
                wait = cur.get("retry_after") or _FAST_POLL_S
            else:
                return {**cur, "id": job_id}
        elif cur.get("status") in TERMINAL:
            out = {"status": cur["status"], "texto": cur.get("texto"),
                   "duracao_s": cur.get("duracao_s"), "rtf": cur.get("rtf"), "id": job_id}
            if cur.get("erro"):
                out["erro"] = cur["erro"]
            if segmentos or palavras:
                out["segmentos"] = cur.get("segmentos")
            return out
        if wait is None:
            wait = _FAST_POLL_S if (_clock() - started) < _FAST_WINDOW_S else _SLOW_POLL_S
        if remaining() <= wait:
            return {"status": "timeout", "id": job_id,
                    "mensagem": "Tempo esgotado no cliente; o job continua no servidor. "
                                "Consulte com noctus.transcription.get."}
        _sleep(wait)


def batch(src_dir: str, out_dir: str, pattern: str = "*.mp3", idioma: str = "pt",
          max_inflight: int = 3, timeout_s: float = 7200, segmentos: bool = False, *,
          _transport: httpx.BaseTransport | None = None,
          _sleep: Callable[[float], None] = time.sleep,
          _clock: Callable[[], float] = time.monotonic) -> dict:
    """Transcribe every ``pattern`` file in ``src_dir`` into ``out_dir/<stem>.txt|.json``.

    Resumable: a stem whose ``.txt`` already exists is skipped, and jobs still in flight are
    recorded in ``out_dir/.inflight.json`` so a re-run resumes polling them instead of
    re-uploading (no duplicate server work). At most ``max_inflight`` jobs are queued at once
    (the API rate-limits bursts with 429 + Retry-After, honoured on both submit and poll).

    ``timeout_s`` is a NO-PROGRESS window, not a total budget: the clock resets every time a
    job is accepted or finishes, so a long healthy batch runs to the end in ONE call, and only
    a real stall (nothing accepted or finished for ``timeout_s``) stops it, as
    ``status: "sem_progresso"``.
    """
    src, out = Path(src_dir).expanduser(), Path(out_dir).expanduser()
    if not src.is_dir():
        return _error("arquivo_invalido", f"Diretório não encontrado: {src_dir}")
    out.mkdir(parents=True, exist_ok=True)
    files = sorted(src.glob(pattern))
    skipped = [f.stem for f in files if (out / f"{f.stem}.txt").exists()]
    inflight_path = out / ".inflight.json"
    jobs: dict[str, str] = {}
    if inflight_path.exists():
        prev = json.loads(inflight_path.read_text(encoding="utf-8"))
        jobs = {jid: stem for jid, stem in prev.items() if stem not in set(skipped)}
    resumed = sorted(jobs.values())
    queue = [f for f in files if f.stem not in set(skipped) and f.stem not in set(resumed)]
    done: list[str] = []
    failed: list[dict[str, Any]] = []
    last_progress = _clock()

    def save_inflight() -> None:
        if jobs:
            inflight_path.write_text(json.dumps(jobs, ensure_ascii=False), encoding="utf-8")
        else:
            inflight_path.unlink(missing_ok=True)

    def progressed() -> None:
        nonlocal last_progress
        last_progress = _clock()
        save_inflight()

    def wait_for(resp: dict) -> float | None:
        if resp.get("status_code") in _TRANSIENT:
            return resp.get("retry_after") or _FAST_POLL_S
        return None

    def bloqueado(resp: dict, wait: float) -> dict | None:
        """The server asked us to back off longer than the budget left: stop loudly, never sleep past it."""
        if wait <= timeout_s - (_clock() - last_progress):
            return None
        return {"status": "bloqueado", "codigo": resp.get("codigo"), "mensagem": resp.get("mensagem"),
                "status_code": resp.get("status_code"), "retry_after": wait,
                "done": done, "failed": failed, "skipped": skipped,
                "pending": [f.stem for f in queue], "inflight": jobs,
                "resumed": resumed,
                "dica": "Bloqueado pelo servidor por mais tempo que a janela sem progresso; "
                        "rode de novo depois de retry_after segundos (os .txt prontos são pulados)."}

    while queue or jobs:
        if _clock() - last_progress > timeout_s:
            return {"status": "sem_progresso", "done": done, "failed": failed, "skipped": skipped,
                    "resumed": resumed, "pending": [f.stem for f in queue], "inflight": jobs,
                    "mensagem": (f"Nenhum job aceito ou concluído em {timeout_s:.0f}s: o servidor "
                                 "parou de avançar. Os jobs em andamento ficam em .inflight.json; "
                                 "rode de novo para retomar sem reenviar.")}
        while queue and len(jobs) < max_inflight:
            f = queue[0]
            job = submit(str(f), idioma=idioma, rotulo=f.stem, segmentos=segmentos,
                         _transport=_transport)
            wait = wait_for(job) if "codigo" in job else None
            if wait is not None:
                blocked = bloqueado(job, wait)
                if blocked:
                    return blocked
                _sleep(wait)
                break
            queue.pop(0)
            if "codigo" in job:
                failed.append({"stem": f.stem, **job})
            else:
                jobs[job["id"]] = f.stem
                progressed()
        if not jobs:
            continue
        _sleep(_FAST_POLL_S)
        for job_id, stem in list(jobs.items()):
            cur = get(job_id, _transport=_transport)
            if "codigo" in cur:
                wait = wait_for(cur)
                if wait is not None:
                    blocked = bloqueado(cur, wait)
                    if blocked:
                        return blocked
                    _sleep(wait)
                    break
                failed.append({"stem": stem, "id": job_id, **cur})
                del jobs[job_id]
                progressed()
            elif cur.get("status") in TERMINAL:
                del jobs[job_id]
                progressed()
                if cur["status"] == "concluida":
                    (out / f"{stem}.txt").write_text(cur.get("texto") or "", encoding="utf-8")
                    (out / f"{stem}.json").write_text(json.dumps(cur, ensure_ascii=False),
                                                      encoding="utf-8")
                    done.append(stem)
                else:
                    failed.append({"stem": stem, "id": job_id, "status": cur["status"],
                                   "erro": cur.get("erro")})
    save_inflight()
    return {"status": "concluida" if not failed else "parcial", "done": done,
            "failed": failed, "skipped": skipped, "resumed": resumed, "out_dir": str(out)}


def register(server) -> None:
    """Register the four ``noctus.transcription.*`` tools."""

    @server.tool(
        name="noctus.transcription.submit",
        description=("Upload a local audio/video file (<=150 MB) to the platform transcription "
                     "API; returns the 202 body {id, status, posicao, estimativa_s, duracao_s}. "
                     "Needs NOCTUS_TRANSCRIPTION_TOKEN (pk_*)."),
    )
    def _submit(path: str, idioma: str = "pt", rotulo: str = "", segmentos: bool = False,
                palavras: bool = False) -> dict:
        return submit(path, idioma=idioma, rotulo=rotulo or None, segmentos=segmentos,
                      palavras=palavras)

    @server.tool(
        name="noctus.transcription.get",
        description="Fetch one transcription job by id (status, texto when concluida, rtf, erro).",
    )
    def _get(id: str) -> dict:
        return get(id)

    @server.tool(
        name="noctus.transcription.transcribe",
        description=("Submit a local file and poll until terminal or timeout_s (default 3600). "
                     "Returns {status, texto, duracao_s, rtf, id}, plus segmentos "
                     "[{inicio,fim,texto}] when segmentos=True (palavras=True adds per-word palavras [{texto,inicio,fim,confianca}] to each segment); on timeout {status:'timeout', id} "
                     "and the job keeps running server-side (use get). The DEFAULT path for any "
                     "transcription — local Whisper is only a fallback when this server fails."),
    )
    def _transcribe(path: str, idioma: str = "pt", rotulo: str = "", timeout_s: float = 3600,
                    segmentos: bool = False, palavras: bool = False) -> dict:
        return transcribe(path, idioma=idioma, rotulo=rotulo or None, timeout_s=timeout_s,
                          segmentos=segmentos, palavras=palavras)

    @server.tool(
        name="noctus.transcription.batch",
        description=("Transcribe every file matching pattern (default *.mp3) in src_dir into "
                     "out_dir/<stem>.txt + .json. Resumable (existing .txt skipped), at most "
                     "max_inflight (default 3) jobs queued, honours 429 Retry-After. Returns "
                     "{status, done, failed, skipped}. timeout_s is a no-progress window (resets on every "
                     "accepted/finished job); in-flight jobs persist in out_dir/.inflight.json and are "
                     "resumed, never re-uploaded. Convert DASH .m4a to mp3 first — the API "
                     "rejects fragmented MP4 (formato_invalido)."),
    )
    def _batch(src_dir: str, out_dir: str, pattern: str = "*.mp3", idioma: str = "pt",
               max_inflight: int = 3, timeout_s: float = 7200, segmentos: bool = False) -> dict:
        return batch(src_dir, out_dir, pattern=pattern, idioma=idioma, max_inflight=max_inflight,
                     timeout_s=timeout_s, segmentos=segmentos)

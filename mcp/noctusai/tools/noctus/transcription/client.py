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
    url = os.environ.get("NOCTUS_TRANSCRIPTION_URL", "").strip() or DEFAULT_URL
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
           segmentos: bool = False, *, _transport: httpx.BaseTransport | None = None) -> dict:
    """POST multipart to /api/transcriptions; return the 202 body or an error dict."""
    cfg = _config()
    if isinstance(cfg, dict):
        return cfg  # token check precedes any file I/O or request
    p, err = _preflight(path)
    if err:
        return err
    data = {"idioma": idioma, "segmentos": "true" if segmentos else "false"}
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
               timeout_s: float = 3600, *, _transport: httpx.BaseTransport | None = None,
               _sleep: Callable[[float], None] = time.sleep,
               _clock: Callable[[], float] = time.monotonic) -> dict:
    """Submit, poll (5 s for the first minute, then 30 s; honours Retry-After)."""
    start = _clock()

    def remaining() -> float:
        return timeout_s - (_clock() - start)

    while True:
        job = submit(path, idioma=idioma, rotulo=rotulo, _transport=_transport)
        ra = job.get("retry_after") if "codigo" in job else None
        if ra is not None and job.get("status_code") in (429, 503) \
                and ra <= _MAX_SUBMIT_WAIT_S and remaining() > ra:
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
            if cur.get("status_code") in (429, 503):
                wait = cur.get("retry_after")
            else:
                return {**cur, "id": job_id}
        elif cur.get("status") in TERMINAL:
            out = {"status": cur["status"], "texto": cur.get("texto"),
                   "duracao_s": cur.get("duracao_s"), "rtf": cur.get("rtf"), "id": job_id}
            if cur.get("erro"):
                out["erro"] = cur["erro"]
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

    Resumable: a stem whose ``.txt`` already exists is skipped. At most
    ``max_inflight`` jobs are queued at once (the API rate-limits bursts with
    429 + Retry-After, which is honoured on both submit and poll).
    """
    src, out = Path(src_dir).expanduser(), Path(out_dir).expanduser()
    if not src.is_dir():
        return _error("arquivo_invalido", f"Diretório não encontrado: {src_dir}")
    out.mkdir(parents=True, exist_ok=True)
    files = sorted(src.glob(pattern))
    skipped = [f.stem for f in files if (out / f"{f.stem}.txt").exists()]
    queue = [f for f in files if f.stem not in set(skipped)]
    jobs: dict[str, str] = {}
    done: list[str] = []
    failed: list[dict[str, Any]] = []
    start = _clock()

    def wait_for(resp: dict) -> float | None:
        if resp.get("status_code") in (429, 503):
            return resp.get("retry_after") or _FAST_POLL_S
        return None

    while queue or jobs:
        if _clock() - start > timeout_s:
            return {"status": "timeout", "done": done, "failed": failed, "skipped": skipped,
                    "pending": [f.stem for f in queue], "inflight": jobs,
                    "mensagem": "Tempo esgotado no cliente; rode de novo para retomar "
                                "(os .txt prontos são pulados)."}
        while queue and len(jobs) < max_inflight:
            f = queue[0]
            job = submit(str(f), idioma=idioma, rotulo=f.stem, segmentos=segmentos,
                         _transport=_transport)
            wait = wait_for(job) if "codigo" in job else None
            if wait is not None:
                _sleep(wait)
                break
            queue.pop(0)
            if "codigo" in job:
                failed.append({"stem": f.stem, **job})
            else:
                jobs[job["id"]] = f.stem
        if not jobs:
            continue
        _sleep(_FAST_POLL_S)
        for job_id, stem in list(jobs.items()):
            cur = get(job_id, _transport=_transport)
            if "codigo" in cur:
                wait = wait_for(cur)
                if wait is not None:
                    _sleep(wait)
                    break
                failed.append({"stem": stem, "id": job_id, **cur})
                del jobs[job_id]
            elif cur.get("status") in TERMINAL:
                del jobs[job_id]
                if cur["status"] == "concluida":
                    (out / f"{stem}.txt").write_text(cur.get("texto") or "", encoding="utf-8")
                    (out / f"{stem}.json").write_text(json.dumps(cur, ensure_ascii=False),
                                                      encoding="utf-8")
                    done.append(stem)
                else:
                    failed.append({"stem": stem, "id": job_id, "status": cur["status"],
                                   "erro": cur.get("erro")})
    return {"status": "concluida" if not failed else "parcial", "done": done,
            "failed": failed, "skipped": skipped, "out_dir": str(out)}


def register(server) -> None:
    """Register the four ``noctus.transcription.*`` tools."""

    @server.tool(
        name="noctus.transcription.submit",
        description=("Upload a local audio/video file (<=150 MB) to the platform transcription "
                     "API; returns the 202 body {id, status, posicao, estimativa_s, duracao_s}. "
                     "Needs NOCTUS_TRANSCRIPTION_TOKEN (pk_*)."),
    )
    def _submit(path: str, idioma: str = "pt", rotulo: str = "", segmentos: bool = False) -> dict:
        return submit(path, idioma=idioma, rotulo=rotulo or None, segmentos=segmentos)

    @server.tool(
        name="noctus.transcription.get",
        description="Fetch one transcription job by id (status, texto when concluida, rtf, erro).",
    )
    def _get(id: str) -> dict:
        return get(id)

    @server.tool(
        name="noctus.transcription.transcribe",
        description=("Submit a local file and poll until terminal or timeout_s (default 3600). "
                     "Returns {status, texto, duracao_s, rtf, id}; on timeout {status:'timeout', id} "
                     "and the job keeps running server-side (use get)."),
    )
    def _transcribe(path: str, idioma: str = "pt", rotulo: str = "", timeout_s: float = 3600) -> dict:
        return transcribe(path, idioma=idioma, rotulo=rotulo or None, timeout_s=timeout_s)

    @server.tool(
        name="noctus.transcription.batch",
        description=("Transcribe every file matching pattern (default *.mp3) in src_dir into "
                     "out_dir/<stem>.txt + .json. Resumable (existing .txt skipped), at most "
                     "max_inflight (default 3) jobs queued, honours 429 Retry-After. Returns "
                     "{status, done, failed, skipped}. Convert DASH .m4a to mp3 first — the API "
                     "rejects fragmented MP4 (formato_invalido)."),
    )
    def _batch(src_dir: str, out_dir: str, pattern: str = "*.mp3", idioma: str = "pt",
               max_inflight: int = 3, timeout_s: float = 7200, segmentos: bool = False) -> dict:
        return batch(src_dir, out_dir, pattern=pattern, idioma=idioma, max_inflight=max_inflight,
                     timeout_s=timeout_s, segmentos=segmentos)

"""Run Julia's mechanism cases LOCALLY through ``LiveEvalTurnDriver`` (the real channel turn path) against the real model.

Reads the platform definition's current DRAFT and the org LLM key through the product's own stores (nothing is printed
or written by this script besides the result file). Meters every provider call (calls, tokens, cache share, latency).

    cd products/agents/backend && PYTHONPATH=. <venv python> ../projects/julia-v2/tools/rodar_mecanismo_local.py \
        --casos mec-saudacao-anuncio-sem-handoff,mec-preco-so-por-ferramenta --k 3 --temp 0.3 --hist 20 \
        --limite-usd 1.5 --out /path/result.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path
from uuid import uuid4

AQUI = Path(__file__).resolve().parent.parent
FONTES = [AQUI / "content-v3" / "julia-v3-evals-mecanismo.json", AQUI / "content-v3-iter4"]


def carregar(slugs: list[str] | None, k: int | None, extras: list[str] = ()):
    from app.studio.eval_mecanismo import Caso

    arquivos: list[Path] = [Path(x) for x in extras]
    for f in FONTES:
        arquivos += sorted(f.glob("*mecanismo*.json")) if f.is_dir() else [f]
    casos = []
    for arq in arquivos:
        for it in json.loads(arq.read_text())["itens"]:
            if it.get("ativo", True) and (slugs is None or it["slug"] in slugs):
                casos.append(Caso(uuid4(), it["slug"], k or it["k"], it["roteiro"], it["asserts"]))
    return casos


class Medido:
    """Wraps the real provider: counts model calls and tokens per turn."""

    def __init__(self, inner):
        self.inner = inner
        self.chamadas = 0
        self.prompt = self.cache_leitura = self.cache_criacao = self.saida = 0
        self.custo = 0.0
        self.latencia = 0.0

    async def chat_with_tools(self, *a, **kw):
        t0 = time.monotonic()
        r = await self.inner.chat_with_tools(*a, **kw)
        self.latencia += time.monotonic() - t0
        self.chamadas += 1
        u = r.usage
        self.prompt += u.prompt_tokens or 0
        self.cache_leitura += u.cache_read_tokens or 0
        self.cache_criacao += u.cache_creation_tokens or 0
        self.saida += u.completion_tokens or 0
        self.custo += u.cost_usd or 0.0
        return r

    def __getattr__(self, nome):
        return getattr(self.inner, nome)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--casos", default="")
    ap.add_argument("--k", type=int)
    ap.add_argument("--temp", type=float)
    ap.add_argument("--hist", type=int)
    ap.add_argument("--modelo")
    ap.add_argument("--extra", action="append", default=[], help="more case files ({itens: [...]}), e.g. cases read from the draft")
    ap.add_argument("--trace", help="append one JSON line per turn (lead, bubbles, tools, actions) to this file")
    ap.add_argument("--parte", default="1/1", help="i/n: run the i-th of n slices of the cases (parallel processes)")
    ap.add_argument("--limite-usd", type=float, default=1.0)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    import app.main  # noqa: F401 -- create_product_app() configures the LLM layer and the stores, as in production
    from noctusai_lib.integrations.llm import llm_usage_context
    from noctusai_lib.integrations.llm.client import get_provider

    from app.studio.eval_driver_live import make_live_eval_driver_factory
    from app.studio.eval_mecanismo import executar_suite

    slugs = [s for s in a.casos.split(",") if s] or None
    casos = carregar(slugs, a.k, a.extra)
    i, n = (int(x) for x in a.parte.split("/"))
    casos = casos[i - 1::n]
    medido = Medido(get_provider("anthropic"))
    driver = make_live_eval_driver_factory(provider_impl=medido)()
    driver.definir_agente("julia")
    if a.trace:
        original = driver.executar_turno

        async def _com_traco(thread, mensagem):
            r = await original(thread, mensagem)
            with open(a.trace, "a") as fh:
                fh.write(json.dumps({
                    "lead": mensagem, "bolhas": list(r.bolhas), "ferramentas": [[c.nome, c.args, c.ok] for c in r.ferramentas],
                    "acoes": list(r.acoes_detalhe), "participante": r.participante_estado,
                    "violacoes": [repr(v) for v in r.violacoes],
                    "handoff": r.handoff.motivo_codigo if r.handoff else None, "custo": r.custo_usd}, ensure_ascii=False) + "\n")
            return r

        driver.executar_turno = _com_traco
    driver.definir_modelo(a.modelo)
    driver.definir_temperatura(a.temp)
    driver.definir_historico(a.hist)
    t0 = time.monotonic()
    with llm_usage_context(product="agents", agent_key="julia", org_id=None):
        res = await executar_suite(casos, driver, limite_usd=a.limite_usd, parar_no_primeiro_erro=False)
    dur = time.monotonic() - t0
    execs = [e for c in res.casos for e in c.execucoes if e.status != "pulado"]
    turnos = sum(len(c.caso.roteiro["turnos"]) for c in res.casos for e in c.execucoes if e.status != "pulado")
    entrada = medido.prompt + medido.cache_leitura + medido.cache_criacao
    out = {
        "args": vars(a), "casos_aprovados": res.casos_aprovados, "casos": len(res.casos), "custo_usd": res.custo_usd,
        "execucoes": len(execs), "execucoes_aprovadas": sum(e.status == "aprovado" for e in execs), "turnos": turnos,
        "chamadas_llm": medido.chamadas, "chamadas_por_turno": round(medido.chamadas / max(turnos, 1), 2),
        # Anthropic reports uncached input separately from cache reads / writes: the real input is the sum of the three
        "tokens_entrada_por_turno": round(entrada / max(turnos, 1)), "cache_leitura": medido.cache_leitura,
        "cache_criacao": medido.cache_criacao, "tokens_entrada_total": entrada, "tokens_saida": medido.saida,
        "parcela_cache_leitura": round(medido.cache_leitura / max(entrada, 1), 3),
        "latencia_llm_por_turno_s": round(medido.latencia / max(turnos, 1), 2), "duracao_total_s": round(dur, 1),
        "custo_medido_usd": round(medido.custo, 4),
        "por_caso": [
            {"slug": c.caso.slug, "k": c.caso.k, "passou": c.passou, "taxa": round(c.taxa, 2),
             "execucoes": [{"status": e.status, "falhas": [f.to_dict() for f in e.falhas], "ferramentas": list(e.ferramentas)}
                           for e in c.execucoes]}
            for c in res.casos],
    }
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k != "por_caso"}, ensure_ascii=False))
    for c in out["por_caso"]:
        if not c["passou"]:
            falhas = sorted({f"{f['assert']}:{f['codigo']}" for e in c["execucoes"] for f in e["falhas"]})
            print("FALHOU", c["slug"], c["taxa"], falhas)


if __name__ == "__main__":
    asyncio.run(main())

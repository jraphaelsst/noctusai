"""Run Julia's JUDGE cases locally on the SAME path as the mechanism suite (``EvalRunner._resposta_pelo_canal``) and grade them
with the production judge. Cases are read from the draft's eval store; nothing is written.

    cd products/agents/backend && PYTHONPATH=.:<worktree>/seed/lib/backend <venv python> ../projects/julia-v2/tools/rodar_juiz_local.py \
        --out result.json [--casos slug,slug] [--k 1] [--modelo claude-haiku-4-5]
"""
from __future__ import annotations

import argparse
import asyncio
import json
from types import SimpleNamespace


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--casos", default="")
    ap.add_argument("--k", type=int, default=1)
    ap.add_argument("--modelo")
    ap.add_argument("--out", required=True)
    ap.add_argument("--sem-mundos", action="store_true", help="ignore the repo's per-case `roteiro` (world) overlay")
    a = ap.parse_args()

    import app.main  # noqa: F401 -- configures the LLM layer and the stores, as in production
    from noctusai_lib.integrations.llm import llm_usage_context

    from app.config import settings
    from app.stores.studio_definitions import get_studio_definition_store
    from app.stores.studio_evals import get_eval_store
    from app.studio.eval_driver_live import make_live_eval_driver_factory
    from app.studio.evals import EvalRunner, LlmJudge, criteria_of, score_case

    defs = get_studio_definition_store(settings)
    definicao = defs.get_platform_definition("julia")
    store = get_eval_store(settings)
    casos = [c for c in store.list_cases(definicao.org_id, definicao.id) if c.ativo and c.suite == "comportamento"]
    if a.casos:
        casos = [c for c in casos if c.slug in a.casos.split(",")]
    if not a.sem_mundos:  # the repo mirror's WORLD (roteiro) wins over the draft store's, so a case can be tried before it is written
        from dataclasses import replace
        from pathlib import Path

        mundos = {}
        for f in (Path(__file__).resolve().parent.parent / "content-v3" / "evals").glob("*.json"):
            d = json.loads(f.read_text())
            if isinstance(d, dict) and d.get("slug") and d.get("roteiro"):
                mundos[d["slug"]] = d["roteiro"]
        casos = [replace(c, roteiro=mundos[c.slug]) if c.slug in mundos else c for c in casos]
    runner = EvalRunner(
        evals=store, runs=None, definitions=defs, catalog=None, runtime=None, broker=None, judge=LlmJudge(),
        instance_id="local", turn_driver_factory=make_live_eval_driver_factory(), turn_timeout_seconds=300.0)
    runner._agente = definicao
    spec = SimpleNamespace(runtime="llm")
    run = SimpleNamespace(modelo_geracao=a.modelo)
    out = []
    with llm_usage_context(product="agents", agent_key="julia", org_id=str(definicao.org_id)):
        for c in casos:
            for _ in range(a.k):
                try:
                    saida, custo = await runner._resposta_pelo_canal(run, spec, c)
                    v = await runner._judge.judge(
                        org_id=definicao.org_id, entrada=c.entrada, contexto=c.contexto, criterios=criteria_of(c.criterios),
                        rubrica=c.rubrica, saida=saida)
                    passou, score = score_case(v)
                    out.append({"slug": c.slug, "passou": passou, "score": score, "saida": saida,
                                "veredito": [x.to_dict() for x in v.veredito], "custo": custo.custo_usd})
                except Exception as exc:  # a failed case is a RESULT, never swallowed as a pass
                    out.append({"slug": c.slug, "passou": False, "erro": f"{type(exc).__name__}: {exc}"[:300]})
    json.dump(out, open(a.out, "w"), ensure_ascii=False, indent=1)
    por = {}
    for r in out:
        por.setdefault(r["slug"], []).append(r.get("score", 0))
    print(json.dumps({"casos": len(por), "aprovados": sum(r["passou"] for r in out), "execucoes": len(out),
                      "scores": {k: round(sum(v) / len(v), 2) for k, v in por.items()},
                      "custo": round(sum(r.get("custo") or 0 for r in out), 4)}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())

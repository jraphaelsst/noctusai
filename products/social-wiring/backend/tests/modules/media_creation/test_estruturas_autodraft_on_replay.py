"""The auto-draft's EXACT payload (``estruturas_ia.montar_payload``) on REAL Postgres (PGlite), migration 350 applied.

The service tests prove WHAT is sent (a recording double); this proves what the SECURITY DEFINER RPC ``cs_estrutura_criar``
does with it: a ``rascunho`` with origem ``viral_auto``, every field ``ia_sugerido`` (so every field counts as pending
review), the events ``criada_automatica`` + ``ia_preenchida`` by ``sistema_ia`` with no human actor, one auto-draft per
video (unique violation), and ``publicar`` as the one way to ``ativa`` (the draft stays out of every ``status='ativa'`` read
until then). Ids the SQL generates travel as ``@@TOKEN@@`` placeholders resolved in SQL.
"""
from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from app.modules.media_creation import saida_ia_estruturas as saida
from app.modules.media_creation.services import estruturas_ia as ia

from ...test_migration_cs_estruturas import HARNESS, MIGRATION, NODE_DIR, PRELUDE, STUBS, _BASE, refuses, sqlstate

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None or not HARNESS.exists() or not (NODE_DIR / "node_modules" / "@electric-sql").exists(),
    reason="PGlite replay harness unavailable (needs `node` and mcp/noctusai/node/node_modules)",
)

TIPOS = ("Headline", "Revelação", "Outro")
TOK = """
  CREATE OR REPLACE FUNCTION pg_temp.tok(txt text, p uuid, v uuid) RETURNS jsonb LANGUAGE plpgsql AS $f$
  DECLARE t record; BEGIN
    txt := replace(replace(txt, '@@PERFIL@@', p::text), '@@VIRAL@@', v::text);
    FOR t IN SELECT id, nome FROM social_wiring.cs_estrutura_tipos_bloco LOOP txt := replace(txt, '@@TIPO:' || t.nome || '@@', t.id::text); END LOOP;
    RETURN txt::jsonb; END $f$;
"""


def _payload() -> str:
    derivada = saida.EstruturaDerivada(
        formula_headline="Por que o seu [recurso] some",
        objetivos=("autoridade", "alcance"),
        blocos=(
            saida.BlocoDerivado("Headline", "Abertura", "0-3s", "Abra com uma pergunta."),
            saida.BlocoDerivado("Revelação", "Hábitos", None, "Entregue a resposta."),
            saida.BlocoDerivado("Outro", "Bônus", "30s", "Feche com um bônus."),
        ),
    )
    viral = {"id": "@@VIRAL@@", "perfil_id": "@@PERFIL@@", "media_type": "VIDEO", "media_product_type": "REELS"}
    payload = ia.montar_payload(
        derivada, viral, {n: f"@@TIPO:{n}@@" for n in TIPOS}, origem="viral_auto", ator_id=None, ator_tipo="sistema_ia",
    )
    return f"pg_temp.tok($j${json.dumps(payload, ensure_ascii=False)}$j$, pf, vi)"


def _scenario() -> str:
    p = _payload()
    return TOK + f"""
  r := cs_estrutura_criar({p}); e := (r->>'id')::uuid;
  IF (SELECT (status, origem, formato, formula_origem, formato_origem, objetivos_origem, created_by IS NULL, publicada_em IS NULL)::text
        FROM cs_estruturas WHERE id = e) <> '(rascunho,viral_auto,reels,ia_sugerido,ia_sugerido,ia_sugerido,t,t)' THEN
    RAISE EXCEPTION 'estrutura %', (SELECT row_to_json(x)::text FROM cs_estruturas x WHERE id = e); END IF;
  IF (SELECT count(*) FROM cs_estrutura_blocos WHERE estrutura_id = e AND nome_origem = 'ia_sugerido' AND tipo_origem = 'ia_sugerido'
         AND tempo_origem = 'ia_sugerido' AND instrucao_origem = 'ia_sugerido') <> 3 THEN RAISE EXCEPTION 'block provenance'; END IF;
  IF (SELECT array_agg(t.nome ORDER BY b.ordem) FROM cs_estrutura_blocos b JOIN cs_estrutura_tipos_bloco t ON t.id = b.tipo_id
        WHERE b.estrutura_id = e) <> ARRAY['Headline','Revelação','Outro'] THEN RAISE EXCEPTION 'block types'; END IF;
  IF (SELECT count(*) FROM cs_estrutura_eventos WHERE estrutura_id = e AND tipo = 'criada_automatica' AND ator_tipo = 'sistema_ia' AND ator_id IS NULL) <> 1
     OR (SELECT count(*) FROM cs_estrutura_eventos WHERE estrutura_id = e AND tipo = 'ia_preenchida' AND ator_tipo = 'sistema_ia') <> 1
     OR (SELECT count(*) FROM cs_estrutura_eventos WHERE estrutura_id = e) <> 2 THEN
    RAISE EXCEPTION 'events %', (SELECT string_agg(tipo || '/' || ator_tipo, ',') FROM cs_estrutura_eventos WHERE estrutura_id = e); END IF;
  IF (SELECT campos_pendentes FROM cs_estruturas_resumo WHERE id = e) <> 15 THEN
    RAISE EXCEPTION 'pending %', (SELECT campos_pendentes FROM cs_estruturas_resumo WHERE id = e); END IF;
  {sqlstate(f"PERFORM cs_estrutura_criar({p})", "unique_violation")}
  IF (SELECT count(*) FROM cs_estruturas WHERE viral_id = vi) <> 1 THEN RAISE EXCEPTION 'one auto-draft per video'; END IF;
  -- invisible to every `ativa` read until an admin publishes
  IF EXISTS (SELECT 1 FROM cs_estruturas WHERE status = 'ativa' AND viral_id = vi) THEN RAISE EXCEPTION 'draft leaked as ativa'; END IF;
  PERFORM cs_estrutura_publicar(e, 1, '00000000-0000-0000-0000-0000000000a1');
  IF (SELECT (status, publicada_em IS NOT NULL)::text FROM cs_estruturas WHERE id = e) <> '(ativa,t)' THEN RAISE EXCEPTION 'publicar'; END IF;
  IF (SELECT count(*) FROM cs_estrutura_eventos WHERE estrutura_id = e AND tipo = 'publicada') <> 1 THEN RAISE EXCEPTION 'publicada event'; END IF;
"""


@pytest.fixture(scope="module")
def replay() -> dict:
    steps = [
        {"product": "sw", "file": "prelude", "sql": PRELUDE, "mode": "file", "twice": False},
        {"product": "sw", "file": "migration", "sql": MIGRATION.read_text(encoding="utf-8"), "mode": "file", "twice": False},
        {"product": "sw", "file": "scenario", "sql": _BASE.replace("{body}", _scenario()), "mode": "file", "twice": False},
    ]
    proc = subprocess.run(
        ["node", str(HARNESS)], input=json.dumps({"stubs": STUBS.read_text(encoding="utf-8"), "steps": steps}),
        capture_output=True, text=True, cwd=NODE_DIR, timeout=300,
    )
    try:
        out = json.loads(proc.stdout)
    except json.JSONDecodeError:
        pytest.fail(f"PGlite harness produced no verdict: {(proc.stderr or proc.stdout)[-400:]}")
    return {step["file"]: step for step in out["steps"]}


def test_the_autodraft_payload_on_real_postgres(replay):
    assert replay["prelude"]["failures"] == [] and replay["migration"]["failures"] == []
    assert replay["scenario"]["failures"] == [], replay["scenario"]["failures"]

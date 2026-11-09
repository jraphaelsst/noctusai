"""Migration 338 (roteiro lifecycle) on a REAL Postgres (PGlite): the backfill, the CHECKs, the atomic gerar RPC.

The pre-338 shape (082 + 184 + 219 + 182, only the columns/constraints 338 touches) is created as a prelude, legacy
rows are seeded in every `nao_realizada` flavour, then the REAL migration file is applied TWICE (idempotency) and the
scenarios run against the result. Same harness as the seed's `*_on_real_postgres.py` suites.

R8 atomicity lives here: a Python test over a mock cannot show a transaction, PGlite can.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from noctusai_lib.testing.migrations import migration_path

ROOT = Path(__file__).resolve().parents[4]
NODE_DIR = ROOT / "mcp" / "noctusai" / "node"
HARNESS = NODE_DIR / "migration_replay" / "replay.mjs"
STUBS = NODE_DIR / "migration_replay" / "stubs.sql"
MIGRATION = migration_path(Path(__file__).resolve().parents[1], "roteiro_ciclo_de_vida")

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None or not HARNESS.exists() or not (NODE_DIR / "node_modules" / "@electric-sql").exists(),
    reason="PGlite replay harness unavailable (needs `node` and mcp/noctusai/node/node_modules)",
)

O = "00000000-0000-0000-0000-00000000000f"
O2 = "00000000-0000-0000-0000-0000000000f2"
USER = "00000000-0000-0000-0000-0000000000a1"

PRELUDE = """
CREATE SCHEMA IF NOT EXISTS social_wiring;
SET search_path = social_wiring, public;
CREATE TABLE social_wiring.atendimentos (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), org_id uuid NOT NULL, cliente_id uuid, lead_id uuid, meta_ads_lead_id text,
  CONSTRAINT atend_lead_unico CHECK (num_nonnulls(lead_id, meta_ads_lead_id) <= 1));
CREATE TABLE social_wiring.imovel_registry (org_id uuid NOT NULL, codigo_canonical text NOT NULL, PRIMARY KEY (org_id, codigo_canonical));
CREATE TABLE social_wiring.roteiros (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), org_id uuid NOT NULL,
  atendimento_id uuid NOT NULL REFERENCES social_wiring.atendimentos(id) ON DELETE CASCADE,
  titulo text, created_at timestamptz NOT NULL DEFAULT now(), deleted_at timestamptz, data_visita date,
  feedback_status text NOT NULL DEFAULT 'pendente', feedback_em timestamptz, hora_visita time);
CREATE TABLE social_wiring.visitas (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), org_id uuid NOT NULL,
  roteiro_id uuid NOT NULL REFERENCES social_wiring.roteiros(id) ON DELETE CASCADE,
  codigo text NOT NULL, ordem integer NOT NULL, status text NOT NULL DEFAULT 'pendente', observacao text,
  feedback_em timestamptz, created_at timestamptz NOT NULL DEFAULT now(), deleted_at timestamptz,
  nao_realizada_motivo text, realizada_em timestamptz,
  CONSTRAINT visitas_status_valido CHECK (status IN ('pendente', 'realizada', 'nao_realizada')),
  CONSTRAINT visitas_nao_realizada_motivo_valido CHECK (nao_realizada_motivo IS NULL OR nao_realizada_motivo IN
    ('cliente_desistiu', 'cliente_nao_compareceu', 'imovel_indisponivel', 'reagendada', 'outro')));
CREATE TABLE social_wiring.cliente_imovel_interesses (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), org_id uuid NOT NULL, cliente_id uuid NOT NULL, codigo text NOT NULL,
  origem text NOT NULL DEFAULT 'manual'
    CONSTRAINT cliente_imovel_interesses_origem_valida CHECK (origem IN ('lead', 'manual', 'campanha', 'roteiro', 'permuta')),
  lead_id uuid, meta_ads_lead_id text, created_by uuid, created_at timestamptz NOT NULL DEFAULT now(), deleted_at timestamptz,
  CONSTRAINT cliente_imovel_interesses_lead_unico CHECK (num_nonnulls(lead_id, meta_ads_lead_id) <= 1));
CREATE UNIQUE INDEX uq_sw_cliente_imovel_interesses_vivo ON social_wiring.cliente_imovel_interesses (cliente_id, codigo) WHERE deleted_at IS NULL;
"""

LEGACY = f"""
SET search_path = social_wiring, public;
INSERT INTO imovel_registry VALUES ('{O}','C1'),('{O}','C2'),('{O}','C3'),('{O}','C4'),('{O}','C5'),('{O}','C6'),('{O}','C7'),('{O}','C8'),
  ('{O}','N1'),('{O}','N2'),('{O}','N3'),('{O}','BOOM');
INSERT INTO atendimentos (id, org_id, cliente_id) VALUES ('00000000-0000-0000-0000-0000000000b1','{O}','00000000-0000-0000-0000-0000000000c1');
INSERT INTO roteiros (id, org_id, atendimento_id, created_at, data_visita)
  VALUES ('00000000-0000-0000-0000-0000000000d1','{O}','00000000-0000-0000-0000-0000000000b1','2026-01-10 12:00+00','2026-01-11');
INSERT INTO visitas (id, org_id, roteiro_id, codigo, ordem, status, nao_realizada_motivo, feedback_em) VALUES
 ('00000000-0000-0000-0000-000000000e01','{O}','00000000-0000-0000-0000-0000000000d1','C1',0,'realizada',NULL,'2026-01-11 15:00+00'),
 ('00000000-0000-0000-0000-000000000e02','{O}','00000000-0000-0000-0000-0000000000d1','C2',1,'nao_realizada','cliente_nao_compareceu','2026-01-11 16:00+00'),
 ('00000000-0000-0000-0000-000000000e03','{O}','00000000-0000-0000-0000-0000000000d1','C3',2,'nao_realizada','reagendada','2026-01-11 16:00+00'),
 ('00000000-0000-0000-0000-000000000e04','{O}','00000000-0000-0000-0000-0000000000d1','C4',3,'nao_realizada','cliente_desistiu','2026-01-11 16:00+00'),
 ('00000000-0000-0000-0000-000000000e05','{O}','00000000-0000-0000-0000-0000000000d1','C5',4,'nao_realizada','imovel_indisponivel','2026-01-11 16:00+00'),
 ('00000000-0000-0000-0000-000000000e06','{O}','00000000-0000-0000-0000-0000000000d1','C6',5,'nao_realizada','outro','2026-01-11 16:00+00'),
 ('00000000-0000-0000-0000-000000000e07','{O}','00000000-0000-0000-0000-0000000000d1','C7',6,'nao_realizada',NULL,'2026-01-11 16:00+00'),
 ('00000000-0000-0000-0000-000000000e08','{O}','00000000-0000-0000-0000-0000000000d1','C8',7,'pendente',NULL,NULL);
"""

#: Every scenario starts from a fresh org-scoped atendimento + a DRAFT roteiro with two visitas (N1, N2).
_BASE = f"""
SET search_path = social_wiring, public;
DO $$
DECLARE o uuid := '{O}'; u uuid := '{USER}'; a uuid := gen_random_uuid(); cl uuid := gen_random_uuid(); ld uuid := gen_random_uuid();
        ro uuid := gen_random_uuid(); r jsonb; n int; s text; t timestamptz; caught boolean := false;
BEGIN
  INSERT INTO atendimentos (id, org_id, cliente_id, lead_id) VALUES (a, o, cl, ld);
  INSERT INTO roteiros (id, org_id, atendimento_id, data_visita) VALUES (ro, o, a, '2026-11-20');
  INSERT INTO visitas (org_id, roteiro_id, codigo, ordem) VALUES (o, ro, 'N1', 0), (o, ro, 'N2', 1);
  {{body}}
END $$;
"""


def _count(table: str, where: str, expect: int, what: str) -> str:
    return (f"SELECT count(*) INTO n FROM {table} WHERE {where}; "
            f"IF n <> {expect} THEN RAISE EXCEPTION '{what}: got %', n; END IF;")


LEGACY_ID = "00000000-0000-0000-0000-0000000000d1"


def _v(i: int) -> str:
    return f"00000000-0000-0000-0000-000000000e0{i}"


SCENARIOS: dict[str, str] = {
    "backfill: an existing roteiro becomes gerado with gerado_em = created_at and updated_at = created_at": f"""
  SELECT status, gerado_em, updated_at INTO s, t, t FROM roteiros WHERE id = '{LEGACY_ID}';
  IF s <> 'gerado' THEN RAISE EXCEPTION 'status %', s; END IF;
  IF (SELECT gerado_em FROM roteiros WHERE id = '{LEGACY_ID}') <> '2026-01-10 12:00+00' THEN RAISE EXCEPTION 'gerado_em'; END IF;
  IF (SELECT updated_at FROM roteiros WHERE id = '{LEGACY_ID}') <> '2026-01-10 12:00+00' THEN RAISE EXCEPTION 'updated_at'; END IF;""",
    "backfill: realizada stays, nao_realizada maps by its motivo, pendente stays": f"""
  IF (SELECT status FROM visitas WHERE id = '{_v(1)}') <> 'realizada' THEN RAISE EXCEPTION 'realizada'; END IF;
  IF (SELECT status FROM visitas WHERE id = '{_v(2)}') <> 'nao_compareceu' THEN RAISE EXCEPTION 'nao_compareceu'; END IF;
  IF (SELECT status FROM visitas WHERE id = '{_v(3)}') <> 'reagendada' THEN RAISE EXCEPTION 'reagendada'; END IF;
  IF (SELECT status FROM visitas WHERE id = '{_v(8)}') <> 'pendente' THEN RAISE EXCEPTION 'pendente'; END IF;""",
    "backfill: cliente_desistiu / imovel_indisponivel / outro / NULL -> cancelada with the motivo and cancelada_por NULL": f"""
  IF (SELECT (status, cancelada_motivo, cancelada_por IS NULL)::text FROM visitas WHERE id = '{_v(4)}') <> '(cancelada,cliente_desistiu,t)' THEN RAISE EXCEPTION 'v4'; END IF;
  IF (SELECT (status, cancelada_motivo, cancelada_por IS NULL)::text FROM visitas WHERE id = '{_v(5)}') <> '(cancelada,imovel_indisponivel,t)' THEN RAISE EXCEPTION 'v5'; END IF;
  IF (SELECT (status, cancelada_motivo, cancelada_por IS NULL)::text FROM visitas WHERE id = '{_v(6)}') <> '(cancelada,outro,t)' THEN RAISE EXCEPTION 'v6'; END IF;
  IF (SELECT (status, cancelada_motivo, cancelada_por IS NULL)::text FROM visitas WHERE id = '{_v(7)}') <> '(cancelada,outro,t)' THEN RAISE EXCEPTION 'v7 (NULL motivo)'; END IF;
  IF (SELECT cancelada_motivo FROM visitas WHERE id = '{_v(2)}') IS NOT NULL THEN RAISE EXCEPTION 'nao_compareceu has no cancelada_motivo'; END IF;""",
    "backfill: resultado_em = the old feedback_em for an outcome, NULL for pendente; nao_realizada_motivo kept (vestigial)": f"""
  IF (SELECT resultado_em FROM visitas WHERE id = '{_v(2)}') <> '2026-01-11 16:00+00' THEN RAISE EXCEPTION 'resultado_em'; END IF;
  IF (SELECT resultado_em FROM visitas WHERE id = '{_v(8)}') IS NOT NULL THEN RAISE EXCEPTION 'pendente stamp'; END IF;
  IF (SELECT nao_realizada_motivo FROM visitas WHERE id = '{_v(4)}') <> 'cliente_desistiu' THEN RAISE EXCEPTION 'legacy column dropped'; END IF;""",
    "the old nao_realizada status is refused by the CHECK now": """
  BEGIN
    UPDATE visitas SET status = 'nao_realizada' WHERE roteiro_id = ro AND codigo = 'N1';
    RAISE EXCEPTION 'nao_realizada accepted';
  EXCEPTION WHEN check_violation THEN NULL; END;""",
    "the new statuses are accepted": """
  UPDATE visitas SET status = 'reagendada' WHERE roteiro_id = ro AND codigo = 'N1';
  UPDATE visitas SET status = 'nao_compareceu' WHERE roteiro_id = ro AND codigo = 'N2';""",
    "a NEW cancelada without cancelada_por/motivo is refused; with both it is accepted": """
  BEGIN
    UPDATE visitas SET status = 'cancelada' WHERE roteiro_id = ro AND codigo = 'N1';
    RAISE EXCEPTION 'incomplete cancelada accepted';
  EXCEPTION WHEN check_violation THEN NULL; END;
  BEGIN
    UPDATE visitas SET status = 'cancelada', cancelada_por = 'cliente' WHERE roteiro_id = ro AND codigo = 'N1';
    RAISE EXCEPTION 'cancelada without motivo accepted';
  EXCEPTION WHEN check_violation THEN NULL; END;
  UPDATE visitas SET status = 'cancelada', cancelada_por = 'cliente', cancelada_motivo = 'cliente_desistiu' WHERE roteiro_id = ro AND codigo = 'N1';""",
    "cancelada_por and cancelada_motivo are closed vocabularies": """
  BEGIN
    UPDATE visitas SET cancelada_por = 'vizinho' WHERE roteiro_id = ro AND codigo = 'N1';
    RAISE EXCEPTION 'cancelada_por accepted';
  EXCEPTION WHEN check_violation THEN NULL; END;
  BEGIN
    UPDATE visitas SET cancelada_motivo = 'preguica' WHERE roteiro_id = ro AND codigo = 'N1';
    RAISE EXCEPTION 'cancelada_motivo accepted';
  EXCEPTION WHEN check_violation THEN NULL; END;""",
    "a legacy cancelada (cancelada_por NULL) stands; touching it is checked (the API answers cancelada_incompleta)": f"""
  BEGIN
    UPDATE visitas SET observacao = 'x' WHERE id = '{_v(4)}';
    RAISE EXCEPTION 'legacy cancelada updated without completing';
  EXCEPTION WHEN check_violation THEN NULL; END;
  UPDATE visitas SET observacao = 'x', cancelada_por = 'cliente' WHERE id = '{_v(4)}';""",
    "reagendada_para_visita_id references a visita; deleting the target nulls it": """
  UPDATE visitas SET status = 'reagendada', reagendada_para_visita_id = (SELECT id FROM visitas WHERE roteiro_id = ro AND codigo = 'N2')
   WHERE roteiro_id = ro AND codigo = 'N1';
  DELETE FROM visitas WHERE roteiro_id = ro AND codigo = 'N2';
  IF (SELECT reagendada_para_visita_id FROM visitas WHERE roteiro_id = ro AND codigo = 'N1') IS NOT NULL THEN RAISE EXCEPTION 'dangling'; END IF;""",
    "a new roteiro is a rascunho with updated_at; any UPDATE bumps updated_at (trigger)": """
  SELECT status, updated_at INTO s, t FROM roteiros WHERE id = ro;
  IF s <> 'rascunho' THEN RAISE EXCEPTION 'new row status %', s; END IF;
  UPDATE roteiros SET updated_at = '2000-01-01' WHERE id = ro;
  IF (SELECT updated_at FROM roteiros WHERE id = ro) < '2026-01-01' THEN RAISE EXCEPTION 'trigger did not bump updated_at'; END IF;""",
    "roteiros.status is a closed vocabulary": """
  BEGIN
    UPDATE roteiros SET status = 'publicado' WHERE id = ro;
    RAISE EXCEPTION 'status accepted';
  EXCEPTION WHEN check_violation THEN NULL; END;""",
    "gerar: flips status, stamps gerado_em/por, links the lead (interesse origem=roteiro, lead_id from the atendimento)": """
  r := roteiro_gerar(o, ro, u);
  IF r->>'status' <> 'ok' THEN RAISE EXCEPTION 'bad %', r; END IF;
  IF (SELECT (status, gerado_por = u, gerado_em IS NOT NULL)::text FROM roteiros WHERE id = ro) <> '(gerado,t,t)' THEN RAISE EXCEPTION 'stamps'; END IF;
  IF (r->>'interesses_criados')::int <> 2 THEN RAISE EXCEPTION 'created %', r; END IF;
  SELECT count(*) INTO n FROM cliente_imovel_interesses WHERE cliente_id = cl AND origem = 'roteiro' AND lead_id = ld AND created_by = u;
  IF n <> 2 THEN RAISE EXCEPTION 'links %', n; END IF;""",
    "gerar twice: the second is refused roteiro_ja_gerado and writes nothing": """
  r := roteiro_gerar(o, ro, u);
  r := roteiro_gerar(o, ro, u);
  IF r->>'code' <> 'roteiro_ja_gerado' THEN RAISE EXCEPTION 'bad %', r; END IF;
  SELECT count(*) INTO n FROM cliente_imovel_interesses WHERE cliente_id = cl;
  IF n <> 2 THEN RAISE EXCEPTION 'rows %', n; END IF;""",
    "gerar without imóveis is refused roteiro_sem_imoveis (soft-deleted visitas do not count); the roteiro stays rascunho": """
  UPDATE visitas SET deleted_at = now() WHERE roteiro_id = ro;
  r := roteiro_gerar(o, ro, u);
  IF r->>'code' <> 'roteiro_sem_imoveis' THEN RAISE EXCEPTION 'bad %', r; END IF;
  IF (SELECT status FROM roteiros WHERE id = ro) <> 'rascunho' THEN RAISE EXCEPTION 'flipped'; END IF;""",
    "gerar without a date is refused roteiro_sem_data; the roteiro stays rascunho": """
  UPDATE roteiros SET data_visita = NULL WHERE id = ro;
  r := roteiro_gerar(o, ro, u);
  IF r->>'code' <> 'roteiro_sem_data' THEN RAISE EXCEPTION 'bad %', r; END IF;
  IF (SELECT status FROM roteiros WHERE id = ro) <> 'rascunho' THEN RAISE EXCEPTION 'flipped'; END IF;""",
    "gerar from another org / a deleted roteiro is nao_encontrado": f"""
  r := roteiro_gerar('{O2}', ro, u);
  IF r->>'code' <> 'nao_encontrado' THEN RAISE EXCEPTION 'bad %', r; END IF;
  UPDATE roteiros SET deleted_at = now() WHERE id = ro;
  r := roteiro_gerar(o, ro, u);
  IF r->>'code' <> 'nao_encontrado' THEN RAISE EXCEPTION 'bad %', r; END IF;""",
    "gerar fills an EMPTY lead link on a live interesse but never changes its origem": """
  INSERT INTO cliente_imovel_interesses (org_id, cliente_id, codigo, origem) VALUES (o, cl, 'N1', 'manual');
  r := roteiro_gerar(o, ro, u);
  IF (SELECT (origem, lead_id = ld)::text FROM cliente_imovel_interesses WHERE cliente_id = cl AND codigo = 'N1') <> '(manual,t)' THEN
    RAISE EXCEPTION 'N1 %', (SELECT row_to_json(i)::text FROM cliente_imovel_interesses i WHERE cliente_id = cl AND codigo = 'N1'); END IF;
  IF (SELECT origem FROM cliente_imovel_interesses WHERE cliente_id = cl AND codigo = 'N2') <> 'roteiro' THEN RAISE EXCEPTION 'N2'; END IF;""",
    "gerar never overwrites an existing lead link (the lead_unico CHECK would also refuse a second one)": """
  INSERT INTO cliente_imovel_interesses (org_id, cliente_id, codigo, origem, meta_ads_lead_id) VALUES (o, cl, 'N1', 'lead', 'meta-1');
  r := roteiro_gerar(o, ro, u);
  IF r->>'status' <> 'ok' THEN RAISE EXCEPTION 'bad %', r; END IF;
  IF (SELECT (origem, lead_id IS NULL, meta_ads_lead_id)::text FROM cliente_imovel_interesses WHERE cliente_id = cl AND codigo = 'N1') <> '(lead,t,meta-1)' THEN RAISE EXCEPTION 'overwritten'; END IF;""",
    "gerar never resurrects a soft-deleted interesse (a removal stays removed)": """
  INSERT INTO cliente_imovel_interesses (org_id, cliente_id, codigo, origem, deleted_at) VALUES (o, cl, 'N1', 'manual', now());
  r := roteiro_gerar(o, ro, u);
  SELECT count(*) INTO n FROM cliente_imovel_interesses WHERE cliente_id = cl AND codigo = 'N1';
  IF n <> 1 THEN RAISE EXCEPTION 'duplicate/resurrected: %', n; END IF;
  IF (SELECT deleted_at IS NULL FROM cliente_imovel_interesses WHERE cliente_id = cl AND codigo = 'N1') THEN RAISE EXCEPTION 'revived'; END IF;""",
    "R8 ATOMICITY: a failure inside gerar (the lead-link insert) rolls the status flip back with it": """
  INSERT INTO visitas (org_id, roteiro_id, codigo, ordem) VALUES (o, ro, 'BOOM', 2);
  CREATE OR REPLACE FUNCTION social_wiring.zz_boom() RETURNS trigger LANGUAGE plpgsql AS $f$
    BEGIN IF NEW.codigo = 'BOOM' THEN RAISE EXCEPTION 'forced failure'; END IF; RETURN NEW; END $f$;
  CREATE TRIGGER zz_boom BEFORE INSERT ON cliente_imovel_interesses FOR EACH ROW EXECUTE FUNCTION social_wiring.zz_boom();
  BEGIN
    r := roteiro_gerar(o, ro, u);
    RAISE EXCEPTION 'gerar did not fail';
  EXCEPTION WHEN raise_exception THEN
    IF SQLERRM <> 'forced failure' THEN RAISE; END IF;
    caught := true;
  END;
  DROP TRIGGER zz_boom ON cliente_imovel_interesses; DROP FUNCTION social_wiring.zz_boom();
  IF NOT caught THEN RAISE EXCEPTION 'no failure observed'; END IF;
  SELECT status INTO s FROM roteiros WHERE id = ro;
  IF s <> 'rascunho' THEN RAISE EXCEPTION 'status flip survived the failure: %', s; END IF;
  IF (SELECT gerado_em FROM roteiros WHERE id = ro) IS NOT NULL THEN RAISE EXCEPTION 'gerado_em survived'; END IF;
  SELECT count(*) INTO n FROM cliente_imovel_interesses WHERE cliente_id = cl;
  IF n <> 0 THEN RAISE EXCEPTION 'partial interesses survived: %', n; END IF;""",
    "usuario_papeis: only 'supervisor' exists; one row per (org, user, papel)": """
  BEGIN
    INSERT INTO usuario_papeis (org_id, user_id, papel) VALUES (o, u, 'owner');
    RAISE EXCEPTION 'papel accepted';
  EXCEPTION WHEN check_violation THEN NULL; END;
  INSERT INTO usuario_papeis (org_id, user_id, papel) VALUES (o, gen_random_uuid(), 'supervisor');
  BEGIN
    INSERT INTO usuario_papeis (org_id, user_id, papel) VALUES (o, u, 'supervisor'), (o, u, 'supervisor');
    RAISE EXCEPTION 'duplicate accepted';
  EXCEPTION WHEN unique_violation THEN NULL; END;""",
    "access: usuario_papeis and roteiro_gerar are service-only (no browser privilege) and the table is tier:org": """
  IF has_table_privilege('authenticated', 'social_wiring.usuario_papeis', 'SELECT') THEN RAISE EXCEPTION 'authenticated can read'; END IF;
  IF has_table_privilege('anon', 'social_wiring.usuario_papeis', 'SELECT') THEN RAISE EXCEPTION 'anon can read'; END IF;
  IF NOT has_table_privilege('service_role', 'social_wiring.usuario_papeis', 'INSERT') THEN RAISE EXCEPTION 'service cannot write'; END IF;
  IF has_function_privilege('authenticated', 'social_wiring.roteiro_gerar(uuid,uuid,uuid)', 'EXECUTE') THEN RAISE EXCEPTION 'authenticated can gerar'; END IF;
  IF has_function_privilege('anon', 'social_wiring.roteiro_gerar(uuid,uuid,uuid)', 'EXECUTE') THEN RAISE EXCEPTION 'anon can gerar'; END IF;
  IF NOT has_function_privilege('service_role', 'social_wiring.roteiro_gerar(uuid,uuid,uuid)', 'EXECUTE') THEN RAISE EXCEPTION 'service cannot gerar'; END IF;
  IF obj_description('social_wiring.usuario_papeis'::regclass) <> 'tier:org' THEN RAISE EXCEPTION 'tier comment'; END IF;""",
    "the function pins search_path to pg_catalog first": """
  SELECT count(*) INTO n FROM pg_proc p JOIN pg_namespace ns ON ns.oid = p.pronamespace
   WHERE ns.nspname = 'social_wiring' AND p.proname IN ('roteiro_gerar', 'roteiros_touch_updated_at')
     AND p.proconfig::text LIKE '%search_path=pg_catalog%';
  IF n <> 2 THEN RAISE EXCEPTION 'search_path not pinned on % of 2', n; END IF;""",
    "interesses.origem accepts julia and still refuses anything else": """
  INSERT INTO cliente_imovel_interesses (org_id, cliente_id, codigo, origem) VALUES (o, cl, 'N1', 'julia');
  BEGIN
    INSERT INTO cliente_imovel_interesses (org_id, cliente_id, codigo, origem) VALUES (o, cl, 'N2', 'telepatia');
    RAISE EXCEPTION 'origem accepted';
  EXCEPTION WHEN check_violation THEN NULL; END;""",
    "the contagem view counts ONLY gerado roteiros with the one derivation": """
  INSERT INTO imovel_registry VALUES (o, 'V1'), (o, 'V2') ON CONFLICT DO NOTHING;
  DELETE FROM visitas WHERE roteiro_id = ro;
  INSERT INTO visitas (org_id, roteiro_id, codigo, ordem, status) VALUES (o, ro, 'V1', 0, 'realizada');
  INSERT INTO visitas (org_id, roteiro_id, codigo, ordem, status, cancelada_por, cancelada_motivo) VALUES (o, ro, 'V2', 1, 'cancelada', 'cliente', 'outro');
  SELECT count(*) INTO n FROM vw_imovel_visita_contagem WHERE org_id = o AND codigo IN ('V1', 'V2');
  IF n <> 0 THEN RAISE EXCEPTION 'a rascunho was counted'; END IF;
  UPDATE roteiros SET status = 'gerado', gerado_em = now() WHERE id = ro;
  IF (SELECT (total, realizadas, consolidadas, perdidas, neutras)::text FROM vw_imovel_visita_contagem WHERE org_id = o AND codigo = 'V1') <> '(1,1,1,0,0)'
    THEN RAISE EXCEPTION 'V1 counts'; END IF;
  IF (SELECT (canceladas, nao_compareceu, perdidas)::text FROM vw_imovel_visita_contagem WHERE org_id = o AND codigo = 'V2') <> '(1,0,1)'
    THEN RAISE EXCEPTION 'V2 counts'; END IF;""",
}


def _ev(where: str) -> str:
    return f"(SELECT count(*) FROM roteiro_eventos e WHERE e.roteiro_id = ro AND {where})"


def _exatamente(where: str, n: int, what: str) -> str:
    return f"IF {_ev(where)} <> {n} THEN RAISE EXCEPTION '{what}: got %', {_ev(where)}; END IF;"


SCENARIOS.update({
    "events backfill: one criado + one gerado per legacy roteiro and one visita_resultado per outcome (origem=backfill)": f"""
  IF (SELECT count(*) FROM roteiro_eventos WHERE roteiro_id = '{LEGACY_ID}' AND tipo = 'roteiro_criado' AND dados->>'origem' = 'backfill'
        AND criado_em = '2026-01-10 12:00+00') <> 1 THEN RAISE EXCEPTION 'criado'; END IF;
  IF (SELECT count(*) FROM roteiro_eventos WHERE roteiro_id = '{LEGACY_ID}' AND tipo = 'roteiro_gerado' AND dados->>'origem' = 'backfill') <> 1
    THEN RAISE EXCEPTION 'gerado'; END IF;
  IF (SELECT count(*) FROM roteiro_eventos WHERE roteiro_id = '{LEGACY_ID}' AND tipo = 'visita_resultado' AND dados->>'origem' = 'backfill') <> 7
    THEN RAISE EXCEPTION 'resultados (the twice-applied migration must not duplicate)'; END IF;
  IF (SELECT (de, para)::text FROM roteiro_eventos WHERE visita_id = '{_v(2)}') <> '(pendente,nao_compareceu)' THEN RAISE EXCEPTION 'v2 event'; END IF;
  IF (SELECT criado_em FROM roteiro_eventos WHERE visita_id = '{_v(2)}') <> '2026-01-11 16:00+00' THEN RAISE EXCEPTION 'v2 time'; END IF;
  IF (SELECT count(*) FROM roteiro_eventos WHERE visita_id = '{_v(8)}') <> 0 THEN RAISE EXCEPTION 'pendente has no result event'; END IF;""",
    "events: creating a roteiro and adding visitas each write exactly their event, with the actor": f"""
  {_exatamente("tipo = 'roteiro_criado' AND ator_id IS NULL AND para = 'rascunho'", 1, "criado")}
  {_exatamente("tipo = 'visita_adicionada'", 2, "adicionada")}
  INSERT INTO visitas (org_id, roteiro_id, codigo, ordem, atualizado_por) VALUES (o, ro, 'N3', 2, u);
  {_exatamente("tipo = 'visita_adicionada' AND ator_id = u AND dados->>'codigo' = 'N3'", 1, "adicionada by u")}
  {_exatamente("true", 4, "nothing else")}""",
    "events: gerar writes exactly roteiro_gerado (actor gerado_por) and reabrir exactly roteiro_reaberto": f"""
  r := roteiro_gerar(o, ro, u);
  {_exatamente("tipo = 'roteiro_gerado' AND de = 'rascunho' AND para = 'gerado' AND ator_id = u", 1, "gerado")}
  UPDATE roteiros SET status = 'rascunho', reaberto_em = now(), reaberto_por = u, updated_at = now(), atualizado_por = u WHERE id = ro;
  {_exatamente("tipo = 'roteiro_reaberto' AND de = 'gerado' AND para = 'rascunho' AND ator_id = u", 1, "reaberto")}
  {_exatamente("tipo NOT IN ('roteiro_criado','visita_adicionada','roteiro_gerado','roteiro_reaberto')", 0, "extra events")}""",
    "events: a date/time change writes data_alterada (de/para) and a delete writes roteiro_excluido": f"""
  UPDATE roteiros SET data_visita = '2026-12-01', hora_visita = '09:30', updated_at = now(), atualizado_por = u WHERE id = ro;
  IF (SELECT (de, para, ator_id = u, dados->>'hora_para')::text FROM roteiro_eventos WHERE roteiro_id = ro AND tipo = 'data_alterada')
     <> '(2026-11-20,2026-12-01,t,09:30:00)' THEN RAISE EXCEPTION 'data_alterada'; END IF;
  UPDATE roteiros SET deleted_at = now(), atualizado_por = u WHERE id = ro;
  {_exatamente("tipo = 'roteiro_excluido' AND ator_id = u", 1, "excluido")}""",
    "events: a no-op write (the autosave touching updated_at / atualizado_por) writes NO event": f"""
  UPDATE roteiros SET updated_at = now(), atualizado_por = u WHERE id = ro;
  UPDATE visitas SET atualizado_por = u WHERE roteiro_id = ro;
  {_exatamente("tipo NOT IN ('roteiro_criado','visita_adicionada')", 0, "noise")}""",
    "events: visita resultado / horario / ordem / remocao write exactly their event with de/para/dados/actor": f"""
  UPDATE visitas SET status = 'cancelada', cancelada_por = 'cliente', cancelada_motivo = 'outro', resultado_em = now(), resultado_por = u, atualizado_por = u
   WHERE roteiro_id = ro AND codigo = 'N1';
  IF (SELECT (de, para, ator_id = u, dados->>'cancelada_por', dados->>'cancelada_motivo')::text FROM roteiro_eventos
       WHERE roteiro_id = ro AND tipo = 'visita_resultado') <> '(pendente,cancelada,t,cliente,outro)' THEN RAISE EXCEPTION 'resultado'; END IF;
  UPDATE visitas SET horario = '10:15', atualizado_por = u WHERE roteiro_id = ro AND codigo = 'N1';
  IF (SELECT (de IS NULL, para, ator_id = u)::text FROM roteiro_eventos WHERE roteiro_id = ro AND tipo = 'visita_horario') <> '(t,10:15:00,t)'
    THEN RAISE EXCEPTION 'horario'; END IF;
  UPDATE visitas SET ordem = CASE codigo WHEN 'N1' THEN 1 ELSE 0 END, atualizado_por = u WHERE roteiro_id = ro;
  {_exatamente("tipo = 'visita_reordenada'", 2, "reordenada (one per visita that moved)")}
  UPDATE visitas SET deleted_at = now(), atualizado_por = u WHERE roteiro_id = ro AND codigo = 'N2';
  {_exatamente("tipo = 'visita_removida' AND ator_id = u AND dados->>'codigo' = 'N2'", 1, "removida")}""",
    "events: reagendar writes visita_resultado + visita_reagendada (new visita and roteiro ids); the new roteiro writes its own events": f"""
  DECLARE ro2 uuid := gen_random_uuid(); v2 uuid := gen_random_uuid();
  BEGIN
    r := roteiro_gerar(o, ro, u);
    INSERT INTO roteiros (id, org_id, atendimento_id, data_visita, criado_por, atualizado_por) VALUES (ro2, o, a, '2026-12-05', u, u);
    INSERT INTO visitas (id, org_id, roteiro_id, codigo, ordem, atualizado_por) VALUES (v2, o, ro2, 'N1', 0, u);
    UPDATE visitas SET status = 'reagendada', reagendada_para_visita_id = v2, resultado_em = now(), resultado_por = u, atualizado_por = u
     WHERE roteiro_id = ro AND codigo = 'N1';
    {_exatamente("tipo = 'visita_resultado' AND de = 'pendente' AND para = 'reagendada' AND ator_id = u", 1, "resultado")}
    {_exatamente("tipo = 'visita_reagendada' AND ator_id = u AND dados->>'nova_visita_id' = v2::text AND dados->>'novo_roteiro_id' = ro2::text", 1, "reagendada")}
    IF (SELECT count(*) FROM roteiro_eventos WHERE roteiro_id = ro2 AND tipo IN ('roteiro_criado', 'visita_adicionada') AND ator_id = u) <> 2
      THEN RAISE EXCEPTION 'new roteiro events'; END IF;
  END;""",
    "events: the ledger is append-only (UPDATE and DELETE refused, no grant to service_role, none to browser roles)": """
  BEGIN
    UPDATE roteiro_eventos SET tipo = 'roteiro_gerado' WHERE roteiro_id = ro;
    RAISE EXCEPTION 'update accepted';
  EXCEPTION WHEN insufficient_privilege THEN NULL; END;
  BEGIN
    DELETE FROM roteiro_eventos WHERE roteiro_id = ro;
    RAISE EXCEPTION 'delete accepted';
  EXCEPTION WHEN insufficient_privilege THEN NULL; END;
  IF has_table_privilege('service_role', 'social_wiring.roteiro_eventos', 'UPDATE')
     OR has_table_privilege('service_role', 'social_wiring.roteiro_eventos', 'DELETE') THEN RAISE EXCEPTION 'service_role can mutate'; END IF;
  IF NOT (has_table_privilege('service_role', 'social_wiring.roteiro_eventos', 'INSERT')
          AND has_table_privilege('service_role', 'social_wiring.roteiro_eventos', 'SELECT')) THEN RAISE EXCEPTION 'service_role lost its grants'; END IF;
  IF has_table_privilege('authenticated', 'social_wiring.roteiro_eventos', 'SELECT') OR has_table_privilege('anon', 'social_wiring.roteiro_eventos', 'SELECT')
    THEN RAISE EXCEPTION 'browser role can read'; END IF;
  IF obj_description('social_wiring.roteiro_eventos'::regclass) <> 'tier:org' THEN RAISE EXCEPTION 'tier'; END IF;""",
    "events: tipo is a closed vocabulary and the ledger indexes exist": """
  BEGIN
    INSERT INTO roteiro_eventos (org_id, roteiro_id, tipo) VALUES (o, ro, 'inventado');
    RAISE EXCEPTION 'tipo accepted';
  EXCEPTION WHEN check_violation THEN NULL; END;
  SELECT count(*) INTO n FROM pg_indexes WHERE schemaname = 'social_wiring' AND tablename = 'roteiro_eventos'
     AND indexname IN ('idx_sw_roteiro_eventos_roteiro', 'idx_sw_roteiro_eventos_tipo');
  IF n <> 2 THEN RAISE EXCEPTION 'indexes %', n; END IF;""",
    "events: a failed event write fails the change (the date stays as it was)": """
  CREATE OR REPLACE FUNCTION social_wiring.zz_boom2() RETURNS trigger LANGUAGE plpgsql AS $f$
    BEGIN IF NEW.tipo = 'data_alterada' THEN RAISE EXCEPTION 'event write failed'; END IF; RETURN NEW; END $f$;
  CREATE TRIGGER zz_boom2 BEFORE INSERT ON roteiro_eventos FOR EACH ROW EXECUTE FUNCTION social_wiring.zz_boom2();
  BEGIN
    UPDATE roteiros SET data_visita = '2030-01-01', atualizado_por = u WHERE id = ro;
    RAISE EXCEPTION 'change survived';
  EXCEPTION WHEN raise_exception THEN
    IF SQLERRM <> 'event write failed' THEN RAISE; END IF;
    caught := true;
  END;
  DROP TRIGGER zz_boom2 ON roteiro_eventos; DROP FUNCTION social_wiring.zz_boom2();
  IF NOT caught THEN RAISE EXCEPTION 'no failure'; END IF;
  IF (SELECT data_visita FROM roteiros WHERE id = ro) <> '2026-11-20' THEN RAISE EXCEPTION 'date changed without its event'; END IF;""",
})


@pytest.fixture(scope="module")
def replay() -> dict:
    sql = MIGRATION.read_text(encoding="utf-8")
    steps = [
        {"product": "sw", "file": "prelude", "sql": PRELUDE, "mode": "file", "twice": False},
        {"product": "sw", "file": "legacy rows", "sql": LEGACY, "mode": "file", "twice": False},
        {"product": "sw", "file": "migration", "sql": sql, "mode": "file", "twice": True},
        *(
            {"product": "sw", "file": f"scenario: {name}",
             "sql": _BASE.replace("{body}", body) if not (name.startswith("backfill") or name.startswith("events backfill")) else _BACKFILL.replace("{body}", body),
             "mode": "file", "twice": False}
            for name, body in SCENARIOS.items()
        ),
    ]
    proc = subprocess.run(
        ["node", str(HARNESS)],
        input=json.dumps({"stubs": STUBS.read_text(encoding="utf-8"), "steps": steps}),
        capture_output=True, text=True, cwd=NODE_DIR, timeout=300,
    )
    try:
        out = json.loads(proc.stdout)
    except json.JSONDecodeError:
        pytest.fail(f"PGlite harness produced no verdict: {(proc.stderr or proc.stdout)[-400:]}")
    assert out.get("ok"), out
    return {step["file"]: step for step in out["steps"]}


#: The backfill scenarios read the legacy rows and need no fresh roteiro.
_BACKFILL = """
SET search_path = social_wiring, public;
DO $$
DECLARE s text; t timestamptz;
BEGIN
  {body}
END $$;
"""


def test_migration_applies_twice_without_failures(replay):
    assert replay["prelude"]["failures"] == [], replay["prelude"]["failures"]
    assert replay["legacy rows"]["failures"] == [], replay["legacy rows"]["failures"]
    assert replay["migration"]["failures"] == [], replay["migration"]["failures"]


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_scenario(replay, name):
    assert replay[f"scenario: {name}"]["failures"] == [], replay[f"scenario: {name}"]["failures"]


def test_the_rerun_does_not_flip_a_live_draft_to_gerado():
    """Idempotency of the BACKFILL, asserted on the SQL: `status` is added with DEFAULT 'gerado' (the backfill) and
    the default flips afterwards; there is no `UPDATE ... SET status = 'gerado'` over existing rows that a second run
    would apply to drafts created in between."""
    code = "\n".join(l for l in MIGRATION.read_text(encoding="utf-8").splitlines() if not l.strip().startswith("--"))
    assert "ADD COLUMN IF NOT EXISTS status        TEXT NOT NULL DEFAULT 'gerado'" in code
    assert "ALTER COLUMN status SET DEFAULT 'rascunho'" in code
    assert "SET status = 'gerado'" not in code.replace("SET status = 'gerado', gerado_em = now(), gerado_por = p_user_id", "")

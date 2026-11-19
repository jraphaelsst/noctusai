"""Migrations M-A..M-E of the criação pipeline (criacao-pipeline-contract.md section 2) on a REAL Postgres (PGlite).

The prelude holds the minimal prod-shaped ancestors (pipeline_stages with 348's CHECK, cs_posts with 241's, cs_post_eventos
with 353's CHECK + 342's guard) and two orgs' esteira boards BEFORE the migrations: the five REAL files are applied in
order (each TWICE: idempotency) and the data step, the step ledger's RPC, the quota events and the consent ledger are
exercised against the result.

Referenced by name (``migration_path``), never by its NNN_ number: integrate renumbers.
"""
from __future__ import annotations

import json
import subprocess

import pytest

from noctusai_lib.testing.migrations import migration_path

from tests.test_migration_cs_unified_chat import (  # the shared harness + SQL helpers (one derivation)
    BACKEND,
    HARNESS,
    NODE_DIR,
    STUBS,
    expect,
    refuses,
    sqlstate,
)
from tests.test_migration_cs_unified_chat import pytestmark  # noqa: F401 - same skip when the harness is absent

NAMES = ("cs_criacao_posts", "cs_criacao_jobs", "cs_post_eventos_criacao", "cs_consentimentos_voz", "cs_criacao_cotas")
FILES = {n: migration_path(BACKEND, n) for n in NAMES}

ORG_Z = "00000000-0000-0000-0000-0000000000a0"  # default-labelled board, has Pronto
ORG_Y = "00000000-0000-0000-0000-0000000000b0"  # customised label, no Pronto stage

PRELUDE = f"""
CREATE SCHEMA IF NOT EXISTS social_wiring;
CREATE TABLE IF NOT EXISTS public.organizations (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), nome text, slug text);
SET search_path = social_wiring, public;
CREATE TABLE marcas (id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE, name text);
CREATE TABLE pipeline_stages (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), org_id uuid NOT NULL,
  pipeline text NOT NULL, slug text NOT NULL CHECK (slug ~ '^[a-z0-9_]+$'),
  label text NOT NULL, cor text NOT NULL DEFAULT 'secondary', posicao integer NOT NULL DEFAULT 0,
  papel text, ativo boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (org_id, pipeline, slug));
CREATE UNIQUE INDEX uq_sw_pipeline_stages_papel ON pipeline_stages (org_id, pipeline, papel) WHERE papel IS NOT NULL;
ALTER TABLE pipeline_stages ADD CONSTRAINT pipeline_stages_papel_check
  CHECK (papel IN ('proposta_aceite', 'final', 'gravacao', 'agendado', 'postado', 'cancelado'));
CREATE TABLE cs_posts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  marca_id uuid NOT NULL REFERENCES marcas (id) ON DELETE CASCADE,
  titulo text NOT NULL DEFAULT 't', etapa_id uuid NOT NULL REFERENCES pipeline_stages (id),
  hashtags text[] NOT NULL DEFAULT '{{}}',
  CONSTRAINT cs_posts_hashtags_max CHECK (cardinality(hashtags) <= 30));
CREATE TABLE cs_post_eventos (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), org_id uuid NOT NULL, post_id uuid NOT NULL,
  asset_id uuid, publicacao_id uuid, tipo text NOT NULL, de text, para text,
  dados jsonb NOT NULL DEFAULT '{{}}'::jsonb, ator_id uuid, criado_em timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT cs_post_eventos_tipo_check CHECK (tipo IN (
    'midia_versao_criada', 'midia_status_alterado', 'insumos_apagados',
    'publicacao_agendada', 'publicacao_reagendada', 'publicado', 'publicacao_falhou', 'publicacao_cancelada')));
CREATE FUNCTION cs_post_eventos_imutavel() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'append-only' USING ERRCODE = 'insufficient_privilege'; END; $$;
CREATE TRIGGER cs_post_eventos_imutavel BEFORE UPDATE OR DELETE ON cs_post_eventos
  FOR EACH ROW EXECUTE FUNCTION cs_post_eventos_imutavel();

INSERT INTO public.organizations (id, nome, slug) VALUES ('{ORG_Z}', 'z', 'z'), ('{ORG_Y}', 'y', 'y');
INSERT INTO marcas (id, org_id, name) VALUES ('00000000-0000-0000-0000-0000000000a1', '{ORG_Z}', 'm');
INSERT INTO pipeline_stages (id, org_id, pipeline, slug, label, posicao, papel) VALUES
  ('00000000-0000-0000-0000-00000000a101', '{ORG_Z}', 'esteira', 'ideacao', 'Ideação', 0, NULL),
  ('00000000-0000-0000-0000-00000000a102', '{ORG_Z}', 'esteira', 'headline_roteiro', 'Headline + roteiro', 1, NULL),
  ('00000000-0000-0000-0000-00000000a103', '{ORG_Z}', 'esteira', 'gravacao', 'Gravação', 2, 'gravacao'),
  ('00000000-0000-0000-0000-00000000a104', '{ORG_Z}', 'esteira', 'edicao', 'Edição', 3, NULL),
  ('00000000-0000-0000-0000-00000000a105', '{ORG_Z}', 'esteira', 'pronto', 'Pronto', 4, NULL),
  ('00000000-0000-0000-0000-00000000a106', '{ORG_Z}', 'esteira', 'postado', 'Postado', 5, 'postado'),
  ('00000000-0000-0000-0000-00000000a107', '{ORG_Z}', 'esteira', 'bloqueado_cancelado', 'Bloqueado/cancelado', 6, 'cancelado'),
  ('00000000-0000-0000-0000-00000000b101', '{ORG_Y}', 'esteira', 'gravacao', 'Minha gravação', 0, 'gravacao'),
  ('00000000-0000-0000-0000-00000000b102', '{ORG_Y}', 'esteira', 'edicao', 'Edição', 1, NULL),
  ('00000000-0000-0000-0000-00000000b103', '{ORG_Y}', 'esteira', 'postado', 'Postado', 2, 'postado'),
  ('00000000-0000-0000-0000-00000000b1ff', '{ORG_Y}', 'funil', 'novo', 'Novo', 0, NULL);
INSERT INTO cs_posts (id, org_id, marca_id, etapa_id, hashtags) VALUES
  ('00000000-0000-0000-0000-00000000a1f1', '{ORG_Z}', '00000000-0000-0000-0000-0000000000a1',
   '00000000-0000-0000-0000-00000000a103', ARRAY['a','b','c','d','e','f','g']);
"""

#: org + marca + stage + post, and the ids the scenarios use
_BASE = """
SET search_path = social_wiring, public;
DO $$
DECLARE
  o uuid := gen_random_uuid(); m uuid; e uuid; p uuid; r jsonb; r2 jsonb; n int; x uuid; s text;
BEGIN
  INSERT INTO public.organizations (id, nome, slug) VALUES (o, 'o', 'o-' || o::text);
  INSERT INTO marcas (org_id, name) VALUES (o, 'm') RETURNING id INTO m;
  INSERT INTO pipeline_stages (org_id, pipeline, slug, label, posicao, papel) VALUES (o, 'esteira', 'criacao', 'Criação', 0, 'criacao') RETURNING id INTO e;
  INSERT INTO cs_posts (org_id, marca_id, etapa_id) VALUES (o, m, e) RETURNING id INTO p;
  {body}
END $$;
"""

PASSO = "cs_criacao_passo_registrar(o, p, 1, '{passo}', '{status}', '{dados}'::jsonb)"


def passo(passo_: str, status: str, dados: str = "{}") -> str:
    return "r := " + PASSO.format(passo=passo_, status=status, dados=dados) + ";"


def ev(tipo: str) -> str:
    return f"(SELECT count(*) FROM cs_post_eventos WHERE post_id = p AND tipo = '{tipo}')"


SCENARIOS: dict[str, str] = {
    "M-A data step: Gravação -> Criação with the id kept, default labels renamed, Aprovação final before Pronto": f"""
  {expect(f"label || '/' || papel || '/' || slug FROM pipeline_stages WHERE id = '00000000-0000-0000-0000-00000000a103'", "Criação/criacao/criacao", "criacao")}
  {expect("(SELECT etapa_id FROM cs_posts WHERE id = '00000000-0000-0000-0000-00000000a1f1')::text", "00000000-0000-0000-0000-00000000a103", "post keeps its stage id")}
  {expect(f"label || '/' || papel FROM pipeline_stages WHERE id = '00000000-0000-0000-0000-00000000a102'", "Roteiro/roteiro", "roteiro")}
  {expect(f"papel FROM pipeline_stages WHERE id = '00000000-0000-0000-0000-00000000a104'", "edicao", "edicao role")}
  {expect(f"papel FROM pipeline_stages WHERE id = '00000000-0000-0000-0000-00000000a105'", "pronto", "pronto role")}
  {expect(f"string_agg(slug, ',' ORDER BY posicao) FROM pipeline_stages WHERE org_id = '{ORG_Z}' AND pipeline = 'esteira'",
          "ideacao,headline_roteiro,criacao,edicao,aprovacao_final,pronto,postado,bloqueado_cancelado", "board order")}
  {expect(f"papel FROM pipeline_stages WHERE org_id = '{ORG_Z}' AND slug = 'aprovacao_final'", "aprovacao_midia", "new stage role")}
""",
    "M-A data step: a customised label is kept; no Pronto => Aprovação final goes right after Edição; funil untouched": f"""
  {expect("label || '/' || papel FROM pipeline_stages WHERE id = '00000000-0000-0000-0000-00000000b101'", "Minha gravação/criacao", "label kept")}
  {expect(f"string_agg(slug, ',' ORDER BY posicao) FROM pipeline_stages WHERE org_id = '{ORG_Y}' AND pipeline = 'esteira'",
          "criacao,edicao,aprovacao_final,postado", "order")}
  {expect(f"count(*) FROM pipeline_stages WHERE org_id = '{ORG_Y}' AND pipeline = 'funil'", "1", "funil untouched")}
  {expect(f"count(*) FROM pipeline_stages WHERE org_id = '{ORG_Z}' AND slug = 'aprovacao_final'", "1", "inserted once (twice-applied)")}
""",
    "M-A: hashtags cleaned to 5 and the cap holds; the enums and the falha_codigo coupling hold": f"""
  {expect("cardinality(hashtags) FROM cs_posts WHERE id = '00000000-0000-0000-0000-00000000a1f1'", "5", "cleaned")}
  {sqlstate("UPDATE cs_posts SET hashtags = ARRAY['1','2','3','4','5','6'] WHERE id = p", "check_violation")}
  {sqlstate("UPDATE cs_posts SET criacao_estado = 'inventado' WHERE id = p", "check_violation")}
  {sqlstate("UPDATE cs_posts SET criacao_rota = 'outra' WHERE id = p", "check_violation")}
  {sqlstate("UPDATE cs_posts SET cta_objetivo = 'vendas' WHERE id = p", "check_violation")}
  {sqlstate("UPDATE cs_posts SET falha_codigo = 'cota' WHERE id = p", "check_violation")}
  UPDATE cs_posts SET criacao_estado = 'falhou', falha_codigo = 'cota', cta_objetivo = 'nenhum', criacao_rota = 'reel_narrado' WHERE id = p;
  {sqlstate("UPDATE cs_posts SET fontes = '{}'::jsonb WHERE id = p", "check_violation")}
  {expect("jsonb_typeof(fontes) FROM cs_posts WHERE id = p", "array", "fontes default")}
""",
    "M-A: the papel CHECK admits the new roles and still the alias": """
  INSERT INTO pipeline_stages (org_id, pipeline, slug, label, posicao, papel) VALUES (o, 'esteira', 'x1', 'x', 1, 'aprovacao_midia');
  INSERT INTO pipeline_stages (org_id, pipeline, slug, label, posicao, papel) VALUES (o, 'esteira', 'x2', 'x', 2, 'gravacao');
  """ + sqlstate("INSERT INTO pipeline_stages (org_id, pipeline, slug, label, posicao, papel) VALUES (o, 'esteira', 'x3', 'x', 3, 'inventado')",
                 "check_violation"),
    "M-B: a step runs pendente -> em_andamento -> concluido, stamped by the RPC, one event per transition": (
        passo("tts", "pendente")
        + expect("(r->>'criado')::boolean", "true", "created")
        + passo("tts", "em_andamento", '{"vendor":"elevenlabs","modelo":"eleven_v3","job_id":"00000000-0000-0000-0000-000000000001"}')
        + passo("tts", "concluido", '{"custo_usd":0.12,"fx_status":"ok","custo_brl":0.62,"nao_medido":["cpu_s"],"unidades":{"caracteres":420}}')
        + expect("(status, vendor, custo_usd::text, iniciado_em IS NOT NULL, terminado_em IS NOT NULL, duracao_s IS NOT NULL)::text "
                 "FROM cs_criacao_jobs WHERE post_id = p AND passo = 'tts'",
                 "(concluido,elevenlabs,0.120000,t,t,t)", "row")
        + expect(ev("passo_iniciado"), "1", "started event")
        + expect(ev("passo_concluido"), "1", "concluded event")
        + expect("(dados->>'passo') || '/' || (dados->>'vendor') FROM cs_post_eventos WHERE post_id = p AND tipo = 'passo_concluido'",
                 "tts/elevenlabs", "event payload")
        + passo("tts", "concluido")
        + expect("(r->>'mudou')::boolean", "false", "replay is a no-op")
        + expect(ev("passo_concluido"), "1", "no second event")
    ),
    "M-B: forward-only -- a terminal step is immutable, nothing goes back; refusals write nothing": (
        passo("mux", "em_andamento")
        + passo("mux", "concluido", '{"custo_usd":0,"cpu_s":4.2}')
        + refuses("PERFORM " + PASSO.format(passo="mux", status="em_andamento", dados="{}"), "transicao_invalida: concluido -> em_andamento")
        + refuses("PERFORM " + PASSO.format(passo="mux", status="falhou", dados='{"erro_codigo":"x"}'), "transicao_invalida: concluido -> falhou")
        + refuses("PERFORM cs_criacao_passo_registrar(o, p, 1, 'mux2', 'inventado', '{}'::jsonb)", "status_invalido")
        + refuses("PERFORM cs_criacao_passo_registrar(o, p, 0, 'mux2', 'pendente', '{}'::jsonb)", "rodada_invalida")
        + refuses("PERFORM cs_criacao_passo_registrar(o, p, 1, 'Mux 2', 'pendente', '{}'::jsonb)", "passo_invalido")
        + refuses("PERFORM cs_criacao_passo_registrar(gen_random_uuid(), p, 1, 'mux2', 'pendente', '{}'::jsonb)", "post_nao_encontrado")
        + expect("count(*) FROM cs_criacao_jobs WHERE post_id = p", "1", "only the one real step")
    ),
    "M-B: unmeasured is NULL + nao_medido, never an estimate -- a concluded step without either is refused": (
        passo("tts", "em_andamento")
        + refuses("PERFORM cs_criacao_passo_registrar(o, p, 1, 'tts', 'concluido', '{\"cpu_s\":1}'::jsonb)", "medicao_ausente")
        + refuses("PERFORM cs_criacao_passo_registrar(o, p, 1, 'tts', 'concluido', '{\"custo_usd\":1}'::jsonb)", "medicao_ausente")
        + sqlstate("PERFORM cs_criacao_passo_registrar(o, p, 1, 'tts', 'concluido', "
                   "'{\"custo_usd\":1,\"cpu_s\":1,\"nao_medido\":[\"cpu_s\"]}'::jsonb)", "check_violation")
        + sqlstate("PERFORM cs_criacao_passo_registrar(o, p, 1, 'tts', 'concluido', "
                   "'{\"custo_usd\":1,\"cpu_s\":1,\"nao_medido\":[\"inventado\"]}'::jsonb)", "check_violation")
        + expect("status FROM cs_criacao_jobs WHERE post_id = p AND passo = 'tts'", "em_andamento", "still running")
    ),
    "M-B: a failure carries its code and an event; erro_codigo 'cota' also writes cota_excedida; a new rodada is a new row": (
        passo("tts", "em_andamento")
        + refuses("PERFORM cs_criacao_passo_registrar(o, p, 1, 'tts', 'falhou', '{}'::jsonb)", "erro_obrigatorio")
        + passo("tts", "falhou", '{"erro_codigo":"cota"}')
        + expect("(status, erro_codigo)::text FROM cs_criacao_jobs WHERE post_id = p AND passo = 'tts'", "(falhou,cota)", "falhou")
        + expect(ev("passo_falhou"), "1", "failed event")
        + expect(ev("cota_excedida"), "1", "quota event")
        + "r := cs_criacao_passo_registrar(o, p, 2, 'tts', 'pendente', '{}'::jsonb);"
        + expect("count(*) FROM cs_criacao_jobs WHERE post_id = p AND passo = 'tts'", "2", "second round is a new row")
        + sqlstate("INSERT INTO cs_criacao_jobs (org_id, post_id, rodada, passo) VALUES (o, p, 3, 'tts')", "raise_exception")
    ),
    "M-B: the ledger is append-only and written only through the RPC (direct write and delete refused)": (
        passo("tts", "em_andamento")
        + sqlstate("INSERT INTO cs_criacao_jobs (org_id, post_id, rodada, passo) VALUES (o, p, 1, 'direto')", "raise_exception")
        + sqlstate("UPDATE cs_criacao_jobs SET modelo = 'x' WHERE post_id = p", "raise_exception")
        + sqlstate("DELETE FROM cs_criacao_jobs WHERE post_id = p", "raise_exception")
    ),
    "M-C: the criação events are admitted, the old ones stay, an unknown one is refused": """
  INSERT INTO cs_post_eventos (org_id, post_id, tipo) VALUES (o, p, 'publicado'), (o, p, 'headline_aprovada'), (o, p, 'card_movido_automaticamente'),
    (o, p, 'verificacao_transcricao_pedida'), (o, p, 'cota_alterada'), (o, p, 'midia_reprovada');
  """ + sqlstate("INSERT INTO cs_post_eventos (org_id, post_id, tipo) VALUES (o, p, 'inventado')", "check_violation")
          + sqlstate("UPDATE cs_post_eventos SET dados = '{}'::jsonb WHERE post_id = p", "insufficient_privilege"),
    "M-D: a grant is valid; a revocation is a NEW row and clears it; nothing is updated or deleted": """
  INSERT INTO cs_consentimentos_voz (org_id, marca_id, pessoa_nome, vendor, voice_id, documento_path, documento_sha256, escopo)
    VALUES (o, m, 'Pessoa', 'elevenlabs', 'v1', 'sw/doc.pdf', repeat('a', 64), 'clone_voz_e_avatar') RETURNING id INTO x;
  """ + expect("cs_consentimento_voz_vigente(o, m, 'elevenlabs', 'v1')::text", "<x>", "valid").replace("'<x>'", "x::text") + """
  IF cs_consentimento_voz_vigente(o, m, 'elevenlabs', 'v2') IS NOT NULL THEN RAISE EXCEPTION 'other voice cleared'; END IF;
  IF cs_consentimento_voz_vigente(o, m, 'heygen', 'v1') IS NOT NULL THEN RAISE EXCEPTION 'other vendor cleared'; END IF;
  INSERT INTO cs_consentimentos_voz (org_id, marca_id, pessoa_nome, vendor, voice_id, documento_path, documento_sha256, escopo,
                                     fase, revoga_id, revogado_em)
    VALUES (o, m, 'Pessoa', 'elevenlabs', 'v1', 'sw/rev.pdf', repeat('b', 64), 'clone_voz', 'revogado', x, now());
  IF cs_consentimento_voz_vigente(o, m, 'elevenlabs', 'v1') IS NOT NULL THEN RAISE EXCEPTION 'revoked still valid'; END IF;
  """ + sqlstate("UPDATE cs_consentimentos_voz SET pessoa_nome = 'x'", "raise_exception")
          + sqlstate("DELETE FROM cs_consentimentos_voz", "raise_exception"),
    "M-D: shape -- a revocation needs its grant + date, same vendor; sha256 and enums are checked; expiry ends validity": """
  INSERT INTO cs_consentimentos_voz (org_id, marca_id, pessoa_nome, vendor, voice_id, documento_path, documento_sha256, escopo)
    VALUES (o, m, 'Pessoa', 'elevenlabs', 'v1', 'sw/doc.pdf', repeat('a', 64), 'clone_voz') RETURNING id INTO x;
  """ + sqlstate("INSERT INTO cs_consentimentos_voz (org_id, marca_id, pessoa_nome, vendor, voice_id, documento_path, documento_sha256, escopo, fase) "
                 "VALUES (o, m, 'P', 'elevenlabs', 'v1', 'p', repeat('a', 64), 'clone_voz', 'revogado')", "check_violation")
          + sqlstate("INSERT INTO cs_consentimentos_voz (org_id, marca_id, pessoa_nome, vendor, voice_id, documento_path, documento_sha256, escopo, fase, revoga_id, revogado_em) "
                     "VALUES (o, m, 'P', 'heygen', 'v1', 'p', repeat('a', 64), 'clone_voz', 'revogado', x, now())", "foreign_key_violation")
          + sqlstate("INSERT INTO cs_consentimentos_voz (org_id, marca_id, pessoa_nome, vendor, voice_id, documento_path, documento_sha256, escopo) "
                     "VALUES (o, m, 'P', 'elevenlabs', 'v1', 'p', 'nothex', 'clone_voz')", "check_violation")
          + sqlstate("INSERT INTO cs_consentimentos_voz (org_id, marca_id, pessoa_nome, vendor, voice_id, documento_path, documento_sha256, escopo) "
                     "VALUES (o, m, 'P', 'google', 'v1', 'p', repeat('a', 64), 'clone_voz')", "check_violation")
          + """
  INSERT INTO cs_consentimentos_voz (org_id, marca_id, pessoa_nome, vendor, voice_id, documento_path, documento_sha256, escopo, valido_ate)
    VALUES (o, m, 'P', 'elevenlabs', 'v9', 'p', repeat('c', 64), 'clone_voz', now() - interval '1 day');
  IF cs_consentimento_voz_vigente(o, m, 'elevenlabs', 'v9') IS NOT NULL THEN RAISE EXCEPTION 'expired still valid'; END IF;
""",
    "M-E: the quota defaults to US$15 in the state read; create + every edit go through the transition-log RPCs, with who/from/to": """
  r := cs_criacao_cota_estado(o);
  IF (r->>'limite_usd_mes')::numeric <> 15 OR (r->>'gasto_usd_mes')::numeric <> 0 THEN RAISE EXCEPTION 'default state: %', r; END IF;
  r := cs_criacao_cota_create(o, jsonb_build_object('updated_by', '00000000-0000-0000-0000-0000000000c1'),
                              NULL, '00000000-0000-0000-0000-0000000000c1', 'user');
  IF r->>'status' <> 'ok' THEN RAISE EXCEPTION 'create: %', r; END IF;
  SELECT id INTO x FROM cs_criacao_cotas WHERE org_id = o;
  r := cs_criacao_cota_transition(o, jsonb_build_object('entity_id', x), 1500, 4000, 'cota_alterada', '{}'::jsonb,
                                  '00000000-0000-0000-0000-0000000000c2', 'user');
  IF r->>'status' <> 'ok' THEN RAISE EXCEPTION 'transition: %', r; END IF;
  r := cs_criacao_cota_transition(o, jsonb_build_object('entity_id', x), 1500, 5000, 'cota_alterada', '{}'::jsonb,
                                  '00000000-0000-0000-0000-0000000000c2', 'user');
  IF r->>'status' <> 'refused' OR r->>'code' <> 'stale_state' THEN RAISE EXCEPTION 'stale not refused: %', r; END IF;
  """ + expect("limite_usd_cents FROM cs_criacao_cotas WHERE org_id = o", "4000", "state moved")
          + expect("count(*) FROM cs_criacao_cota_events WHERE org_id = o", "2", "created + one change")
          + expect("(from_state, to_state, actor_id::text)::text FROM cs_criacao_cota_events WHERE org_id = o AND seq = 2",
                   "(1500,4000,00000000-0000-0000-0000-0000000000c2)", "from/to/who")
          + expect("round(((cs_criacao_cota_estado(o))->>'limite_usd_mes')::numeric, 2)", "40.00", "state read in dollars")
          + sqlstate("UPDATE cs_criacao_cota_events SET to_state = 1 WHERE org_id = o", "SQLSTATE 'TL001'")
          + sqlstate("DELETE FROM cs_criacao_cota_events WHERE org_id = o", "SQLSTATE 'TL001'")
          + sqlstate("UPDATE cs_criacao_cotas SET limite_usd_cents = -1 WHERE org_id = o", "check_violation"),
    "M-E: month-to-date spend sums the ledger (failed steps spent too) and counts the steps with no measured cost": (
        passo("tts", "em_andamento")
        + passo("tts", "concluido", '{"custo_usd":2.5,"nao_medido":["cpu_s"]}')
        + passo("heygen", "em_andamento")
        + passo("heygen", "falhou", '{"erro_codigo":"vendor_5xx","custo_usd":1.25}')
        + passo("mux", "em_andamento")
        + passo("mux", "concluido", '{"cpu_s":3,"nao_medido":["custo_usd"]}')
        + "r := cs_criacao_cota_estado(o);"
        + "IF (r->>'gasto_usd_mes')::numeric <> 3.75 OR (r->>'passos_sem_custo')::int <> 1 OR (r->>'restante_usd')::numeric <> 11.25 "
          "THEN RAISE EXCEPTION 'state: %', r; END IF;"
        + "INSERT INTO cs_criacao_cotas (org_id, limite_usd_cents) VALUES (o, 300);"
        + "r := cs_criacao_cota_estado(o);"
        + "IF (r->>'restante_usd')::numeric <> -0.75 THEN RAISE EXCEPTION 'over quota: %', r; END IF;"
    ),
    "access: service_role reads the tables and EXECUTEs the RPCs, never writes the ledger; no browser role has anything": """
  IF NOT has_table_privilege('service_role', 'social_wiring.cs_criacao_jobs', 'SELECT') THEN RAISE EXCEPTION 'service cannot read jobs'; END IF;
  IF has_table_privilege('service_role', 'social_wiring.cs_criacao_jobs', 'INSERT')
     OR has_table_privilege('service_role', 'social_wiring.cs_criacao_jobs', 'UPDATE')
     OR has_table_privilege('service_role', 'social_wiring.cs_criacao_jobs', 'DELETE') THEN RAISE EXCEPTION 'service writes the ledger directly'; END IF;
  IF has_table_privilege('service_role', 'social_wiring.cs_consentimentos_voz', 'UPDATE')
     OR has_table_privilege('service_role', 'social_wiring.cs_consentimentos_voz', 'DELETE') THEN RAISE EXCEPTION 'consent mutable'; END IF;
  IF has_table_privilege('service_role', 'social_wiring.cs_criacao_cotas', 'UPDATE')
     OR has_table_privilege('service_role', 'social_wiring.cs_criacao_cotas', 'INSERT') THEN RAISE EXCEPTION 'quota writable outside the RPCs'; END IF;
  IF NOT has_function_privilege('service_role', 'social_wiring.cs_criacao_passo_registrar(uuid,uuid,integer,text,text,jsonb)', 'EXECUTE') THEN
    RAISE EXCEPTION 'service cannot execute the RPC'; END IF;
  FOREACH s IN ARRAY ARRAY['social_wiring.cs_criacao_jobs', 'social_wiring.cs_consentimentos_voz', 'social_wiring.cs_criacao_cotas',
                           'social_wiring.cs_criacao_cota_events', 'social_wiring.cs_criacao_gasto_mes'] LOOP
    IF has_table_privilege('authenticated', s, 'SELECT') OR has_table_privilege('anon', s, 'SELECT') THEN
      RAISE EXCEPTION 'browser role reads %', s; END IF;
  END LOOP;
  IF has_function_privilege('authenticated', 'social_wiring.cs_criacao_passo_registrar(uuid,uuid,integer,text,text,jsonb)', 'EXECUTE')
     OR has_function_privilege('anon', 'social_wiring.cs_criacao_cota_estado(uuid)', 'EXECUTE')
     OR has_function_privilege('authenticated', 'social_wiring.cs_consentimento_voz_vigente(uuid,uuid,text,text)', 'EXECUTE') THEN
    RAISE EXCEPTION 'browser executes a definer'; END IF;
  SELECT count(*) INTO n FROM pg_proc p JOIN pg_namespace ns ON ns.oid = p.pronamespace
   WHERE ns.nspname = 'social_wiring' AND p.prosecdef AND p.proconfig::text NOT LIKE '%search_path%'
     AND (p.proname LIKE 'cs\\_criacao\\_%' OR p.proname LIKE 'cs\\_consentimento%' OR p.proname LIKE 'guard\\_cs\\_c%');
  IF n <> 0 THEN RAISE EXCEPTION 'unpinned definers: %', n; END IF;
  IF (SELECT count(*) FROM pg_policies WHERE schemaname = 'social_wiring'
       AND tablename IN ('cs_criacao_jobs', 'cs_consentimentos_voz', 'cs_criacao_cotas', 'cs_criacao_cota_events')
       AND roles <> '{service_role}') <> 0 THEN RAISE EXCEPTION 'a non-service policy exists'; END IF;
""",
}


@pytest.fixture(scope="module")
def replay() -> dict:
    steps = [{"product": "sw", "file": "prelude", "sql": PRELUDE, "mode": "file", "twice": False}]
    steps += [{"product": "sw", "file": n, "sql": FILES[n].read_text(encoding="utf-8"), "mode": "file", "twice": True} for n in NAMES]
    steps += [
        {"product": "sw", "file": f"scenario: {name}", "sql": _BASE.replace("{body}", body), "mode": "file", "twice": False}
        for name, body in SCENARIOS.items()
    ]
    proc = subprocess.run(
        ["node", str(HARNESS)],
        input=json.dumps({"stubs": STUBS.read_text(encoding="utf-8"), "steps": steps}),
        capture_output=True, text=True, cwd=NODE_DIR, timeout=600,
    )
    try:
        out = json.loads(proc.stdout)
    except json.JSONDecodeError:
        pytest.fail(f"PGlite harness produced no verdict: {(proc.stderr or proc.stdout)[-400:]}")
    assert out.get("ok"), out
    return {step["file"]: step for step in out["steps"]}


@pytest.mark.parametrize("name", ["prelude", *NAMES])
def test_migrations_apply_twice_without_failures(replay, name):
    assert replay[name]["failures"] == [], (name, replay[name]["failures"])


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_scenario(replay, name):
    assert replay[f"scenario: {name}"]["failures"] == [], replay[f"scenario: {name}"]["failures"]


def _code(name: str) -> str:
    return "\n".join(l for l in FILES[name].read_text(encoding="utf-8").splitlines() if not l.strip().startswith("--"))


@pytest.mark.parametrize("name", NAMES)
def test_backward_compatible_with_the_previous_image(name):
    code = _code(name)
    assert " DROP COLUMN " not in code and "RENAME" not in code and "DROP TABLE" not in code and "DROP FUNCTION" not in code
    assert "TO authenticated" not in code and "TO anon" not in code


def test_every_new_table_declares_its_tier():
    code = _code("cs_criacao_jobs") + _code("cs_consentimentos_voz") + _code("cs_criacao_cotas")
    for table in ("cs_criacao_jobs", "cs_consentimentos_voz", "cs_criacao_cotas", "cs_criacao_cota_events", "cs_criacao_gasto_mes"):
        assert f"social_wiring.{table} IS 'tier:org'" in code, table

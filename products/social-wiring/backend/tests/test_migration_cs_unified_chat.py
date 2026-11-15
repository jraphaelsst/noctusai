"""Migration ``cs_unified_chat`` (M3 of estruturas-contract.md section 3.3) on a REAL Postgres (PGlite).

The prelude creates only the 229/241/marcas tables the migration references; the REAL 350 migration (Estruturas) and the
REAL 352 file are applied (352 TWICE: idempotency) and every RPC / guard / grant is exercised against the result. A
Python test over a mock cannot show a row lock, an ``ON CONFLICT`` retry, an FK action running inside a guard trigger or
a privilege; PGlite can.

Referenced by name (``migration_path``), never by its NNN_ number: integrate renumbers.
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
BACKEND = Path(__file__).resolve().parents[1]
M350 = migration_path(BACKEND, "cs_estruturas")
MIGRATION = migration_path(BACKEND, "cs_unified_chat")

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None or not HARNESS.exists() or not (NODE_DIR / "node_modules" / "@electric-sql").exists(),
    reason="PGlite replay harness unavailable (needs `node` and mcp/noctusai/node/node_modules)",
)

PRELUDE = """
CREATE SCHEMA IF NOT EXISTS social_wiring;
CREATE TABLE IF NOT EXISTS public.organizations (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), nome text, slug text);
SET search_path = social_wiring, public;
CREATE TABLE marcas (id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE, name text);
CREATE TABLE cs_perfis_monitorados (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), handle text NOT NULL, nome text);
CREATE TABLE cs_virais (id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  perfil_id uuid NOT NULL REFERENCES cs_perfis_monitorados (id) ON DELETE CASCADE);
CREATE TABLE cs_headlines (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  marca_id uuid NOT NULL REFERENCES marcas (id) ON DELETE CASCADE,
  texto text NOT NULL CHECK (char_length(texto) BETWEEN 1 AND 1000 AND texto = btrim(texto)),
  favorita boolean NOT NULL DEFAULT false, favoritada_em timestamptz,
  modo text CHECK (modo IN ('manual', 'automatico')), created_by uuid,
  created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE cs_roteiros (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  marca_id uuid NOT NULL REFERENCES marcas (id) ON DELETE CASCADE,
  headline_id uuid REFERENCES cs_headlines (id) ON DELETE SET NULL, nome text, headline_texto text);
CREATE TABLE cs_posts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  marca_id uuid NOT NULL REFERENCES marcas (id) ON DELETE CASCADE,
  titulo text NOT NULL DEFAULT 't', formato text NOT NULL DEFAULT 'reel',
  CONSTRAINT cs_posts_formato_check CHECK (formato IN ('reel')));
CREATE TABLE cs_chat_conversas (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  marca_id uuid NOT NULL REFERENCES marcas (id) ON DELETE CASCADE,
  user_id uuid NOT NULL,
  agente text NOT NULL CHECK (agente IN ('headline', 'roteiro')),
  titulo text NOT NULL, last_message_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE cs_chat_mensagens (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  conversa_id uuid NOT NULL REFERENCES cs_chat_conversas (id) ON DELETE CASCADE,
  role text NOT NULL CHECK (role IN ('user', 'assistant')),
  conteudo text NOT NULL,
  referencias jsonb NOT NULL DEFAULT '[]'::jsonb,
  status text NOT NULL DEFAULT 'completa' CHECK (status IN ('completa', 'parcial', 'erro')),
  truncada boolean NOT NULL DEFAULT false, modelo text, contexto_chars integer,
  created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE status_pagina (nome_pagina text PRIMARY KEY, status text NOT NULL);
-- two legacy conversations (the prod 7 headline + 1 roteiro) that exist BEFORE the migration
INSERT INTO public.organizations (id, nome, slug) VALUES ('00000000-0000-0000-0000-0000000000f0', 'legacy', 'legacy');
INSERT INTO marcas (id, org_id, name) VALUES ('00000000-0000-0000-0000-0000000000f1', '00000000-0000-0000-0000-0000000000f0', 'm');
INSERT INTO cs_chat_conversas (org_id, marca_id, user_id, agente, titulo)
  VALUES ('00000000-0000-0000-0000-0000000000f0', '00000000-0000-0000-0000-0000000000f1', gen_random_uuid(), 'headline', 't'),
         ('00000000-0000-0000-0000-0000000000f0', '00000000-0000-0000-0000-0000000000f1', gen_random_uuid(), 'roteiro', 't');
INSERT INTO cs_posts (org_id, marca_id) VALUES ('00000000-0000-0000-0000-0000000000f0', '00000000-0000-0000-0000-0000000000f1');
"""

#: Every scenario starts from: an org + marca, a perfil with three Estruturas, a conversation of user `u`, one user message.
_BASE = """
SET search_path = social_wiring, public;
DO $$
DECLARE
  o uuid := gen_random_uuid(); m uuid; pf uuid; e1 uuid; e2 uuid; e3 uuid; e4 uuid; c uuid; mu uuid; r jsonb; r2 jsonb;
  u uuid := '00000000-0000-0000-0000-0000000000a1'; v_u2 uuid := '00000000-0000-0000-0000-0000000000a2';
  p1 uuid; p2 uuid; msg uuid; h uuid; n int; s text;
BEGIN
  INSERT INTO public.organizations (id, nome, slug) VALUES (o, 'o', 'o-' || o::text);
  INSERT INTO marcas (org_id, name) VALUES (o, 'm') RETURNING id INTO m;
  INSERT INTO cs_perfis_monitorados (handle, nome) VALUES ('perfil.' || gen_random_uuid()::text, 'Perfil') RETURNING id INTO pf;
  INSERT INTO cs_estruturas (perfil_id, formula_headline, status, origem) VALUES (pf, 'f1', 'rascunho', 'manual') RETURNING id INTO e1;
  INSERT INTO cs_estruturas (perfil_id, formula_headline, status, origem) VALUES (pf, 'f2', 'rascunho', 'manual') RETURNING id INTO e2;
  INSERT INTO cs_estruturas (perfil_id, formula_headline, status, origem) VALUES (pf, 'f3', 'rascunho', 'manual') RETURNING id INTO e3;
  INSERT INTO cs_estruturas (perfil_id, formula_headline, status, origem) VALUES (pf, 'f4', 'rascunho', 'manual') RETURNING id INTO e4;
  INSERT INTO cs_chat_conversas (org_id, marca_id, user_id, agente, titulo) VALUES (o, m, u, 'unificado', 'c') RETURNING id INTO c;
  INSERT INTO cs_chat_mensagens (org_id, conversa_id, role, conteudo) VALUES (o, c, 'user', 'me dê headlines') RETURNING id INTO mu;
  {body}
END $$;
"""


def refuses(call: str, code: str) -> str:
    """A SQL fragment: ``call`` must raise EXACTLY the coded exception ``code``."""
    return (
        f"BEGIN {call}; RAISE EXCEPTION 'no refusal (expected {code})'; "
        f"EXCEPTION WHEN OTHERS THEN IF SQLERRM <> '{code}' THEN RAISE; END IF; END;"
    )


def sqlstate(call: str, state: str) -> str:
    return (
        f"BEGIN {call}; RAISE EXCEPTION 'no refusal (expected {state})'; "
        f"EXCEPTION WHEN {state} THEN NULL; END;"
    )


def expect(sql_scalar: str, want: str, what: str) -> str:
    return (
        f"IF (SELECT {sql_scalar})::text IS DISTINCT FROM '{want}' THEN "
        f"RAISE EXCEPTION '{what}: got %', (SELECT {sql_scalar})::text; END IF;"
    )


def evt(tipo: str, where: str = "true") -> str:
    return f"(SELECT count(*) FROM cs_fluxo_eventos WHERE org_id = o AND tipo = '{tipo}' AND {where})"


def resposta(propostas: str, eventos: str = "'[]'::jsonb", user: str = "u") -> str:
    return (
        "cs_chat_resposta_gravar(jsonb_build_object('org_id', o, 'conversa_id', c, 'user_id', " + user + ", "
        "'conteudo', 'texto da resposta', 'truncada', false, 'modelo', 'x', 'contexto_chars', 10, "
        f"'propostas', {propostas}, 'eventos', {eventos}))"
    )


#: two propostas: #1 cites e1 (principal) + e2, #2 cites e3
DUAS = (
    "jsonb_build_array("
    "jsonb_build_object('ordem', 1, 'texto', 'Headline um', 'gatilho_tag', 'Curiosidade', 'estrutura_ids', jsonb_build_array(e1, e2)), "
    "jsonb_build_object('ordem', 2, 'texto', 'Headline dois', 'estrutura_ids', jsonb_build_array(e3)))"
)

GRAVAR = f"""
  r := {resposta(DUAS)};
  msg := (r->>'mensagem_id')::uuid;
  SELECT id INTO p1 FROM cs_chat_propostas WHERE mensagem_id = msg AND ordem = 1;
  SELECT id INTO p2 FROM cs_chat_propostas WHERE mensagem_id = msg AND ordem = 2;
"""

SCENARIOS: dict[str, str] = {
    # ── the widened CHECKs and the legacy rows ──────────────────────────────────────────────────────────
    "legacy conversations survive untouched; 'unificado' is accepted; anything else is refused": (
        expect("count(*) FROM cs_chat_conversas WHERE agente IN ('headline', 'roteiro')", "2", "legacy rows kept")
        + expect("count(*) FROM cs_chat_conversas WHERE id = c AND agente = 'unificado'", "1", "unificado")
        + sqlstate("INSERT INTO cs_chat_conversas (org_id, marca_id, user_id, agente, titulo) VALUES (o, m, u, 'outro', 'c')", "check_violation")
    ),
    "cs_posts.formato: reel/carrossel/story/feed are accepted, anything else refused; existing rows keep their value": (
        "INSERT INTO cs_posts (org_id, marca_id, formato) VALUES (o, m, 'carrossel'), (o, m, 'story'), (o, m, 'feed'), (o, m, 'reel');"
        + expect("count(*) FROM cs_posts WHERE org_id = '00000000-0000-0000-0000-0000000000f0' AND formato = 'reel'", "1", "legacy post")
        + sqlstate("INSERT INTO cs_posts (org_id, marca_id, formato) VALUES (o, m, 'video_longo')", "check_violation")
    ),
    "cs_roteiros.formato: defaults to reels (the truthful backfill), accepts the four formatos, refuses others": (
        "INSERT INTO cs_roteiros (org_id, marca_id) VALUES (o, m);"
        + expect("formato FROM cs_roteiros WHERE org_id = o", "reels", "default")
        + "INSERT INTO cs_roteiros (org_id, marca_id, formato) VALUES (o, m, 'carrossel'), (o, m, 'stories'), (o, m, 'post');"
        + sqlstate("INSERT INTO cs_roteiros (org_id, marca_id, formato) VALUES (o, m, 'short')", "check_violation")
    ),
    "status_pagina: the Headlines e Roteiros page is seeded desenvolvimento (owner/dev-only until validated)": (
        expect("status FROM status_pagina WHERE nome_pagina = 'media-creation-headlines-roteiros'", "desenvolvimento", "seeded")
    ),
    # ── resposta_gravar ──────────────────────────────────────────────────────────────────────────────────
    "resposta_gravar: one transaction writes the message, the propostas, the Estrutura links (first = principal) and the events": (
        GRAVAR
        + expect("count(*) FROM cs_chat_mensagens WHERE id = msg AND role = 'assistant' AND tipo = 'texto' AND status = 'completa'", "1", "message")
        + expect("count(*) FROM cs_chat_propostas WHERE mensagem_id = msg AND status = 'proposta' AND fluxo_etapa IS NULL", "2", "propostas")
        + expect("texto || '|' || gatilho_tag FROM cs_chat_propostas WHERE id = p1", "Headline um|Curiosidade", "p1")
        + expect("string_agg(ordem || ':' || principal::text, ',' ORDER BY ordem) FROM cs_chat_proposta_estruturas WHERE proposta_id = p1", "1:true,2:false", "links")
        + expect("estrutura_id FROM cs_chat_proposta_estruturas WHERE proposta_id = p1 AND principal", "e1", "principal").replace("'e1'", "e1::text")
        + expect(f"{evt('propostas_geradas')} || '/' || (SELECT contagem FROM cs_fluxo_eventos WHERE org_id = o AND tipo = 'propostas_geradas')", "1/2", "event")
    ),
    "resposta_gravar: the parser's rejection counts become events; a message with NO proposta still records them": (
        "r := " + resposta("'[]'::jsonb", "jsonb_build_array(jsonb_build_object('tipo', 'citacao_rejeitada', 'contagem', 3), jsonb_build_object('tipo', 'placeholder_remanescente', 'contagem', 1))") + ";"
        + expect("count(*) FROM cs_chat_propostas WHERE conversa_id = c", "0", "no proposta")
        + expect(evt("citacao_rejeitada", "contagem = 3"), "1", "citacao_rejeitada")
        + expect(evt("placeholder_remanescente", "contagem = 1"), "1", "placeholder")
        + expect(evt("propostas_geradas"), "0", "no propostas_geradas")
    ),
    "resposta_gravar: a proposta citing a 4th Estrutura violates the 3-slot CHECK and rolls the WHOLE answer back": (
        "n := (SELECT count(*) FROM cs_chat_mensagens WHERE conversa_id = c);"
        + sqlstate("PERFORM " + resposta("jsonb_build_array(jsonb_build_object('ordem', 1, 'texto', 'x', 'estrutura_ids', jsonb_build_array(e1, e2, e3, e4)))"), "check_violation")
        + expect("count(*) FROM cs_chat_mensagens WHERE conversa_id = c", "1", "message rolled back")
        + expect("count(*) FROM cs_chat_propostas WHERE conversa_id = c", "0", "no orphan proposta")
    ),
    "resposta_gravar: another user's conversation is a coded refusal": (
        refuses("PERFORM " + resposta(DUAS, user="v_u2"), "conversa_nao_encontrada")
    ),
    "propostas: (mensagem, ordem) is unique; one principal per proposta; one Estrutura per slot": (
        GRAVAR
        + sqlstate("INSERT INTO cs_chat_propostas (org_id, marca_id, conversa_id, mensagem_id, ordem, texto) VALUES (o, m, c, msg, 1, 'dup')", "unique_violation")
        + sqlstate("INSERT INTO cs_chat_proposta_estruturas (proposta_id, estrutura_id, ordem, principal) VALUES (p1, e3, 3, true)", "unique_violation")
        + sqlstate("INSERT INTO cs_chat_proposta_estruturas (proposta_id, estrutura_id, ordem, principal) VALUES (p1, e3, 2, false)", "unique_violation")
        + sqlstate("INSERT INTO cs_chat_proposta_estruturas (proposta_id, estrutura_id, ordem) VALUES (p1, e4, 4)", "check_violation")
        + sqlstate("UPDATE cs_chat_propostas SET status = 'feita' WHERE id = p1", "check_violation")
        + sqlstate("UPDATE cs_chat_propostas SET fluxo_etapa = 'x' WHERE id = p1", "check_violation")
        + sqlstate("INSERT INTO cs_chat_propostas (org_id, marca_id, conversa_id, mensagem_id, ordem, texto) VALUES (o, m, c, msg, 9, '')", "check_violation")
    ),
    "propostas cascade: deleting an Estrutura drops its link only; deleting the conversation drops propostas and links": (
        GRAVAR
        + "DELETE FROM cs_estruturas WHERE id = e2;"
        + expect("count(*) FROM cs_chat_proposta_estruturas WHERE proposta_id = p1", "1", "link of the deleted Estrutura")
        + "DELETE FROM cs_chat_conversas WHERE id = c;"
        + expect("count(*) FROM cs_chat_propostas WHERE org_id = o", "0", "propostas")
        + expect("count(*) FROM cs_chat_proposta_estruturas WHERE proposta_id IN (p1, p2)", "0", "links")
        + expect(f"{evt('propostas_geradas')}", "1", "the ledger outlives the conversation (no content, no FK)")
    ),
    # ── escolher: claim / lease ─────────────────────────────────────────────────────────────────────────
    "claim: the first claim wins (escolhida + lease + proposta_escolhida event); a second is NOT claimed and writes no event": (
        GRAVAR
        + "r := cs_chat_proposta_reivindicar(p1, o, c, u, 60);"
        + expect("(r->>'claimed')::boolean", "true", "first claim")
        + expect("(status, escolhida_por = u, escolhida_em IS NOT NULL, fluxo_lease_ate > now())::text FROM cs_chat_propostas WHERE id = p1", "(escolhida,t,t,t)", "row")
        + expect(evt("proposta_escolhida", "proposta_id = p1 AND ator_id = u"), "1", "event")
        + "r2 := cs_chat_proposta_reivindicar(p1, o, c, u, 60);"
        + expect("(r2->>'claimed')::boolean", "false", "double click")
        + expect("r2->'proposta'->>'status'", "escolhida", "current state returned")
        + expect(f"{evt('proposta_escolhida')} + {evt('fluxo_retomado')}", "1", "no second event")
    ),
    "claim: an expired lease is resumable (fluxo_retomado, same escolhida_em); a concluded flow never is": (
        GRAVAR
        + "PERFORM cs_chat_proposta_reivindicar(p1, o, c, u, 60);"
        + "UPDATE cs_chat_propostas SET fluxo_lease_ate = now() - interval '1 second' WHERE id = p1;"
        + "r := cs_chat_proposta_reivindicar(p1, o, c, u, 60);"
        + expect("(r->>'claimed')::boolean", "true", "resumed")
        + expect(evt("fluxo_retomado", "proposta_id = p1"), "1", "retomado event")
        + expect(evt("proposta_escolhida"), "1", "still ONE proposta_escolhida")
        + "UPDATE cs_chat_propostas SET fluxo_etapa = 'concluido', fluxo_lease_ate = now() - interval '1 second' WHERE id = p1;"
        + expect("(cs_chat_proposta_reivindicar(p1, o, c, u, 60)->>'claimed')::boolean", "false", "concluded")
    ),
    "claim: a crash between the claim and the headline (escolhida, etapa NULL, lease gone) is resumable": (
        GRAVAR
        + "UPDATE cs_chat_propostas SET status = 'escolhida', fluxo_lease_ate = now() - interval '1 second' WHERE id = p1;"
        + expect("(cs_chat_proposta_reivindicar(p1, o, c, u, 60)->>'claimed')::boolean", "true", "etapa NULL resumable")
    ),
    "claim: another user / org / conversation gets proposta_nao_encontrada": (
        GRAVAR
        + refuses("PERFORM cs_chat_proposta_reivindicar(p1, o, c, v_u2, 60)", "proposta_nao_encontrada")
        + refuses("PERFORM cs_chat_proposta_reivindicar(p1, gen_random_uuid(), c, u, 60)", "proposta_nao_encontrada")
        + refuses("PERFORM cs_chat_proposta_reivindicar(p1, o, gen_random_uuid(), u, 60)", "proposta_nao_encontrada")
        + refuses("PERFORM cs_chat_proposta_reivindicar(gen_random_uuid(), o, c, u, 60)", "proposta_nao_encontrada")
        + expect("status FROM cs_chat_propostas WHERE id = p1", "proposta", "untouched")
    ),
    # ── escolher: the headline ──────────────────────────────────────────────────────────────────────────
    "salvar_headline: favorite headline linked to the conversation + proposta; usos principal/mistura; etapa; ONE event": (
        GRAVAR
        + "PERFORM cs_chat_proposta_reivindicar(p1, o, c, u, 60);"
        + "r := cs_chat_proposta_salvar_headline(p1, o, u); h := (r->>'headline_id')::uuid;"
        + expect("(r->>'criada')::boolean", "true", "criada")
        + expect("(texto, favorita, favoritada_em IS NOT NULL, modo, created_by = u, conversa_id = c, proposta_id = p1)::text FROM cs_headlines WHERE id = h",
                 "(\"Headline um\",t,t,manual,t,t,t)", "headline")
        + expect("(headline_id = h, fluxo_etapa)::text FROM cs_chat_propostas WHERE id = p1", "(t,headline_salva)", "proposta")
        + expect("string_agg(papel || ':' || ordem || ':' || contexto, ',' ORDER BY ordem) FROM cs_estrutura_usos WHERE proposta_id = p1 AND headline_id = h",
                 "principal:1:chat,mistura:2:chat", "usos")
        + expect(evt("headline_salva", "proposta_id = p1 AND headline_id = h AND ator_id = u"), "1", "event")
    ),
    "salvar_headline: a retry is a lookup -- one headline, no second uso, no second event, etapa never regresses": (
        GRAVAR
        + "PERFORM cs_chat_proposta_reivindicar(p1, o, c, u, 60);"
        + "r := cs_chat_proposta_salvar_headline(p1, o, u); h := (r->>'headline_id')::uuid;"
        + "UPDATE cs_chat_propostas SET fluxo_etapa = 'roteiro_criado' WHERE id = p1;"
        + "r2 := cs_chat_proposta_salvar_headline(p1, o, u);"
        + expect("(r2->>'headline_id')::uuid = h AND NOT (r2->>'criada')::boolean", "true", "lookup")
        + expect("count(*) FROM cs_headlines WHERE conversa_id = c", "1", "one headline")
        + expect("count(*) FROM cs_estrutura_usos WHERE proposta_id = p1", "2", "usos")
        + expect(evt("headline_salva"), "1", "one event")
        + expect("fluxo_etapa FROM cs_chat_propostas WHERE id = p1", "roteiro_criado", "etapa kept")
    ),
    "salvar_headline: a crash after the headline INSERT but before proposta.headline_id is repaired by the UNIQUE lookup": (
        GRAVAR
        + "PERFORM cs_chat_proposta_reivindicar(p1, o, c, u, 60);"
        + "INSERT INTO cs_headlines (org_id, marca_id, texto, conversa_id, proposta_id, modo, favorita) VALUES (o, m, 'Headline um', c, p1, 'manual', true);"
        + "r := cs_chat_proposta_salvar_headline(p1, o, u);"
        + expect("count(*) FROM cs_headlines WHERE conversa_id = c", "1", "still one")
        + expect("headline_id = (r->>'headline_id')::uuid FROM cs_chat_propostas WHERE id = p1", "true", "relinked")
    ),
    "salvar_headline: refuses a proposta that was never claimed, and a foreign user": (
        GRAVAR
        + refuses("PERFORM cs_chat_proposta_salvar_headline(p1, o, u)", "proposta_nao_escolhida")
        + "PERFORM cs_chat_proposta_reivindicar(p1, o, c, u, 60);"
        + refuses("PERFORM cs_chat_proposta_salvar_headline(p1, o, v_u2)", "proposta_nao_encontrada")
        + expect("count(*) FROM cs_headlines WHERE conversa_id = c", "0", "no headline written")
    ),
    "headlines: (conversa, proposta) is unique; roteiros/headlines keep a deleted conversation as SET NULL": (
        GRAVAR
        + "INSERT INTO cs_headlines (org_id, marca_id, texto, conversa_id, proposta_id) VALUES (o, m, 'a', c, p1);"
        + sqlstate("INSERT INTO cs_headlines (org_id, marca_id, texto, conversa_id, proposta_id) VALUES (o, m, 'b', c, p1)", "unique_violation")
        + "INSERT INTO cs_headlines (org_id, marca_id, texto) VALUES (o, m, 'c'), (o, m, 'd');"  # NULL proposta: unconstrained
        + "INSERT INTO cs_roteiros (org_id, marca_id, conversa_id) VALUES (o, m, c);"
        + "DELETE FROM cs_chat_conversas WHERE id = c;"
        + expect("count(*) FROM cs_headlines WHERE org_id = o AND conversa_id IS NULL", "3", "headlines kept")
        + expect("count(*) FROM cs_roteiros WHERE org_id = o AND conversa_id IS NULL", "1", "roteiro kept")
    ),
    "mensagens: the roteiro_gerado message is unique per proposta; tipo is a CHECK": (
        GRAVAR
        + "INSERT INTO cs_chat_mensagens (org_id, conversa_id, role, conteudo, tipo, proposta_id) VALUES (o, c, 'assistant', 'Criei', 'roteiro_gerado', p1);"
        + sqlstate("INSERT INTO cs_chat_mensagens (org_id, conversa_id, role, conteudo, tipo, proposta_id) VALUES (o, c, 'assistant', 'Criei', 'roteiro_gerado', p1)", "unique_violation")
        + sqlstate("INSERT INTO cs_chat_mensagens (org_id, conversa_id, role, conteudo, tipo) VALUES (o, c, 'assistant', 'x', 'outro')", "check_violation")
        + "INSERT INTO cs_chat_mensagens (org_id, conversa_id, role, conteudo) VALUES (o, c, 'user', 'a'), (o, c, 'user', 'b');"  # NULL proposta_id: unconstrained
    ),
    # ── escolher: pre-flight refusal gives the lease back ───────────────────────────────────────────────
    "liberar: a pre-flight refusal keeps the headline, clears the lease, records the code; the same click is claimable at once": (
        GRAVAR
        + "PERFORM cs_chat_proposta_reivindicar(p1, o, c, u, 60);"
        + "PERFORM cs_chat_proposta_salvar_headline(p1, o, u);"
        + "r := cs_chat_proposta_liberar(p1, o, u, 'orcamento_ia_excedido');"
        + expect("(r->>'liberada')::boolean", "true", "released")
        + expect("(fluxo_lease_ate IS NULL, fluxo_erro_codigo, fluxo_etapa, headline_id IS NOT NULL)::text FROM cs_chat_propostas WHERE id = p1", "(t,orcamento_ia_excedido,headline_salva,t)", "state")
        + "r := cs_chat_proposta_reivindicar(p1, o, c, u, 60);"
        + expect("(r->>'claimed')::boolean", "true", "retry")
        + expect("fluxo_erro_codigo IS NULL FROM cs_chat_propostas WHERE id = p1", "true", "error cleared by the new claim")
        + expect("(cs_chat_proposta_liberar(p1, o, v_u2, 'x')->>'liberada')::boolean", "false", "foreign user cannot release")
    ),
    # ── escolher with an @-mentioned headline ───────────────────────────────────────────────────────────
    "sintetizar: an already-saved headline becomes a proposta behind an assistant message (no Estrutura link); idempotent": (
        "INSERT INTO cs_headlines (org_id, marca_id, texto) VALUES (o, m, 'Headline salva') RETURNING id INTO h;"
        + "r := cs_chat_proposta_sintetizar(o, u, c, h);"
        + expect("(r->>'sintetizada')::boolean", "true", "first")
        + "p1 := (r->>'proposta_id')::uuid;"
        + expect("(texto, headline_id = h, status, ordem)::text FROM cs_chat_propostas WHERE id = p1", "(\"Headline salva\",t,proposta,1)", "proposta")
        + expect("count(*) FROM cs_chat_proposta_estruturas WHERE proposta_id = p1", "0", "no link")
        + expect("count(*) FROM cs_chat_mensagens m JOIN cs_chat_propostas p ON p.mensagem_id = m.id WHERE p.id = p1 AND m.role = 'assistant' AND m.conteudo = 'Headline salva'", "1", "message")
        + "r2 := cs_chat_proposta_sintetizar(o, u, c, h);"
        + expect("(r2->>'proposta_id')::uuid = p1 AND NOT (r2->>'sintetizada')::boolean", "true", "second call returns the same proposta")
        + expect("count(*) FROM cs_chat_propostas WHERE conversa_id = c", "1", "one proposta")
        + "PERFORM cs_chat_proposta_reivindicar(p1, o, c, u, 60);"
        + "r := cs_chat_proposta_salvar_headline(p1, o, u);"
        + expect("(r->>'headline_id')::uuid = h", "true", "the EXISTING headline is the one linked")
        + expect("count(*) FROM cs_headlines WHERE org_id = o", "1", "no second headline")
        + expect("count(*) FROM cs_estrutura_usos WHERE proposta_id = p1", "0", "no usos (no Estrutura)")
    ),
    "sintetizar: a foreign headline / another user's conversation is a coded refusal": (
        "INSERT INTO cs_headlines (org_id, marca_id, texto) VALUES (o, m, 'x') RETURNING id INTO h;"
        + refuses("PERFORM cs_chat_proposta_sintetizar(o, u, c, gen_random_uuid())", "headline_nao_encontrada")
        + refuses("PERFORM cs_chat_proposta_sintetizar(gen_random_uuid(), u, c, h)", "conversa_nao_encontrada")
        + refuses("PERFORM cs_chat_proposta_sintetizar(o, v_u2, c, h)", "conversa_nao_encontrada")
    ),
    # ── the ledger ──────────────────────────────────────────────────────────────────────────────────────
    "cs_fluxo_eventos: append-only (UPDATE/DELETE/TRUNCATE refused), tipo is a CHECK, an org erase cascades through the guard": (
        GRAVAR
        + "SELECT count(*) INTO n FROM cs_fluxo_eventos WHERE org_id = o;"
        + refuses("UPDATE cs_fluxo_eventos SET tipo = 'fluxo_concluido' WHERE org_id = o",
                  "cs_fluxo_eventos_imutavel: cs_fluxo_eventos is append-only (UPDATE refused)")
        + refuses("DELETE FROM cs_fluxo_eventos WHERE org_id = o", "cs_fluxo_eventos_imutavel: cs_fluxo_eventos is append-only (DELETE refused)")
        + refuses("TRUNCATE cs_fluxo_eventos", "cs_fluxo_recusa_truncate: cs_fluxo_eventos is append-only (TRUNCATE refused)")
        + sqlstate("INSERT INTO cs_fluxo_eventos (org_id, marca_id, conversa_id, tipo) VALUES (o, m, c, 'inventado')", "check_violation")
        + "IF n < 1 THEN RAISE EXCEPTION 'no events'; END IF;"
        + "DELETE FROM public.organizations WHERE id = o;"
        + expect("count(*) FROM cs_fluxo_eventos WHERE org_id = o", "0", "org erase cascaded")
    ),
    "usos written by the saga survive the headline's deletion (SET NULL carve-out) and vanish with the Estrutura (cascade)": (
        GRAVAR
        + "PERFORM cs_chat_proposta_reivindicar(p1, o, c, u, 60);"
        + "r := cs_chat_proposta_salvar_headline(p1, o, u); h := (r->>'headline_id')::uuid;"
        + "DELETE FROM cs_headlines WHERE id = h;"
        + expect("count(*) FROM cs_estrutura_usos WHERE proposta_id = p1 AND headline_id IS NULL", "2", "usos kept")
        + "DELETE FROM cs_estruturas WHERE id = e2;"
        + expect("count(*) FROM cs_estrutura_usos WHERE proposta_id = p1", "1", "cascade")
    ),
    # ── privileges and shape ────────────────────────────────────────────────────────────────────────────
    "access: no browser privilege anywhere; service_role EXECUTEs the five RPCs, not the internal helper or the triggers": """
  FOR s IN SELECT unnest(ARRAY['cs_chat_propostas', 'cs_chat_proposta_estruturas', 'cs_fluxo_eventos']) LOOP
    IF has_table_privilege('authenticated', 'social_wiring.' || s, 'SELECT') OR has_table_privilege('anon', 'social_wiring.' || s, 'SELECT')
       OR has_table_privilege('authenticated', 'social_wiring.' || s, 'INSERT') OR has_table_privilege('anon', 'social_wiring.' || s, 'INSERT') THEN
      RAISE EXCEPTION 'browser privilege on %', s; END IF;
    IF NOT has_table_privilege('service_role', 'social_wiring.' || s, 'SELECT') THEN RAISE EXCEPTION 'service cannot read %', s; END IF;
    IF has_table_privilege('service_role', 'social_wiring.' || s, 'UPDATE') OR has_table_privilege('service_role', 'social_wiring.' || s, 'DELETE') THEN
      RAISE EXCEPTION 'service can UPDATE/DELETE %', s; END IF;
  END LOOP;
  IF has_table_privilege('service_role', 'social_wiring.cs_chat_propostas', 'INSERT')
     OR has_table_privilege('service_role', 'social_wiring.cs_chat_proposta_estruturas', 'INSERT') THEN
    RAISE EXCEPTION 'service writes propostas directly'; END IF;
  IF NOT has_table_privilege('service_role', 'social_wiring.cs_fluxo_eventos', 'INSERT') THEN RAISE EXCEPTION 'service cannot INSERT events'; END IF;
  IF obj_description('social_wiring.cs_chat_propostas'::regclass) <> 'tier:org'
     OR obj_description('social_wiring.cs_chat_proposta_estruturas'::regclass) <> 'tier:org'
     OR obj_description('social_wiring.cs_fluxo_eventos'::regclass) <> 'tier:org' THEN RAISE EXCEPTION 'tier'; END IF;
  FOR s IN SELECT unnest(ARRAY[
      'cs_chat_resposta_gravar(jsonb)', 'cs_chat_proposta_sintetizar(uuid,uuid,uuid,uuid)',
      'cs_chat_proposta_reivindicar(uuid,uuid,uuid,uuid,integer)', 'cs_chat_proposta_salvar_headline(uuid,uuid,uuid)',
      'cs_chat_proposta_liberar(uuid,uuid,uuid,text)']) LOOP
    IF NOT has_function_privilege('service_role', 'social_wiring.' || s, 'EXECUTE') THEN RAISE EXCEPTION 'service cannot execute %', s; END IF;
    IF has_function_privilege('authenticated', 'social_wiring.' || s, 'EXECUTE') OR has_function_privilege('anon', 'social_wiring.' || s, 'EXECUTE') THEN
      RAISE EXCEPTION 'browser can execute %', s; END IF;
  END LOOP;
  IF has_function_privilege('service_role', 'social_wiring.cs_fluxo_evento(uuid,uuid,uuid,text,uuid,uuid,uuid,uuid,uuid,uuid,integer,text)', 'EXECUTE') THEN
    RAISE EXCEPTION 'service can write arbitrary events through the helper'; END IF;
  IF (SELECT count(*) FROM pg_policies WHERE schemaname = 'social_wiring' AND tablename IN ('cs_chat_propostas', 'cs_chat_proposta_estruturas', 'cs_fluxo_eventos') AND roles <> '{service_role}') <> 0 THEN
    RAISE EXCEPTION 'a non-service policy exists'; END IF;
  SELECT count(*) INTO n FROM pg_proc p JOIN pg_namespace ns ON ns.oid = p.pronamespace
   WHERE ns.nspname = 'social_wiring' AND (p.proname LIKE 'cs\\_chat\\_%' OR p.proname LIKE 'cs\\_fluxo\\_%') AND p.prosecdef AND p.proconfig::text NOT LIKE '%search_path%';
  IF n <> 0 THEN RAISE EXCEPTION 'unpinned definer functions: %', n; END IF;""",
}


@pytest.fixture(scope="module")
def replay() -> dict:
    steps = [
        {"product": "sw", "file": "prelude", "sql": PRELUDE, "mode": "file", "twice": False},
        {"product": "sw", "file": "350", "sql": M350.read_text(encoding="utf-8"), "mode": "file", "twice": False},
        {"product": "sw", "file": "migration", "sql": MIGRATION.read_text(encoding="utf-8"), "mode": "file", "twice": True},
        *(
            {"product": "sw", "file": f"scenario: {name}", "sql": _BASE.replace("{body}", body), "mode": "file", "twice": False}
            for name, body in SCENARIOS.items()
        ),
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


def test_migration_applies_twice_without_failures(replay):
    assert replay["prelude"]["failures"] == [], replay["prelude"]["failures"]
    assert replay["350"]["failures"] == [], replay["350"]["failures"]
    assert replay["migration"]["failures"] == [], replay["migration"]["failures"]


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_scenario(replay, name):
    assert replay[f"scenario: {name}"]["failures"] == [], replay[f"scenario: {name}"]["failures"]


# ── static pins (no database) ────────────────────────────────────────────────────────────────────────────


def _code() -> str:
    return "\n".join(line for line in MIGRATION.read_text(encoding="utf-8").splitlines() if not line.strip().startswith("--"))


def test_every_definer_revokes_and_nothing_is_executable_by_a_browser_role():
    code = _code()
    assert code.count("SECURITY DEFINER") == 5
    assert code.count("FROM PUBLIC, anon, authenticated;") >= 5 + 3  # + the internal helper + the two trigger functions
    assert "TO authenticated" not in code and "TO anon" not in code


def test_the_event_vocabulary_is_the_contract_s():
    code = _code().replace("\n", " ")
    for tipo in (
        "propostas_geradas", "proposta_escolhida", "headline_salva", "roteiro_criado", "roteiro_gerado", "roteiro_falhou",
        "card_criado", "card_falhou", "legenda_gerada", "legenda_falhou", "fluxo_concluido", "fluxo_retomado",
        "perfil_resolvido", "perfil_ambiguo", "perfil_nao_encontrado", "citacao_rejeitada", "atribuicao_ausente",
        "placeholder_remanescente", "formato_misturado",
    ):
        assert f"'{tipo}'" in code, tipo


def test_the_migration_is_backward_compatible_with_the_previous_image():
    """N-1 still lists the old conversations by their old value and writes only what it wrote before: nothing here
    drops/renames/retypes a column, NOT NULL columns carry defaults, and no backfill UPDATE of a hot table exists."""
    code = _code()
    assert " DROP COLUMN " not in code and "RENAME" not in code and "ALTER COLUMN" not in code
    assert "UPDATE social_wiring.cs_chat_conversas" not in code  # no backfill of the legacy agente values (M5's job)
    assert "ADD COLUMN IF NOT EXISTS tipo TEXT NOT NULL DEFAULT 'texto'" in code
    assert "ADD COLUMN IF NOT EXISTS formato TEXT NOT NULL DEFAULT 'reels'" in code

"""Behavioural test (real Postgres via PGlite) for the spawn_funil_card no-silent-drop migration.

Reproduces the 2026-10-10 prod incident: ``spawn_funil_card`` ended with
``ON CONFLICT DO NOTHING`` against a GLOBAL unique on ``meta_ads_lead_id``,
silently dropping 6 real cards. Two shapes: (A) another ORG holds the meta
lead; (B) the SAME org's card for the meta lead is linked to another lead.

Runs the OLD function (the um_card_por_lead function + the old global index) and asserts the
card is lost, then the NEW one and asserts it is not. Lives in the toolkit suite (the leg that installs PGlite via
`npm ci` in mcp/noctusai/node); the shared `pglite` fixture skips locally when
PGlite is absent and FAILS in CI (a self-skipping gate is zero coverage).
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest
from noctusai_lib.testing.migrations import migration_path
from settings import REPO_ROOT

ROOT = Path(REPO_ROOT)
BACKEND = ROOT / "products" / "social-wiring" / "backend"
M_NEW = migration_path(BACKEND, "spawn_funil_card_sem_descarte_silencioso")
M_OLD = migration_path(BACKEND, "um_card_por_lead")
NODE_DIR = ROOT / "mcp" / "noctusai" / "node"

_JS = r"""
import fs from 'node:fs';
const { PGlite } = await import('@electric-sql/pglite');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const db = new PGlite();
const out = [];
for (const s of input.steps) {
  try {
    if (/^\s*SELECT/i.test(s)) { const r = await db.query(s); out.push({ ok: true, rows: r.rows }); }
    else { await db.exec(s); out.push({ ok: true, rows: [] }); }
  }
  catch (e) { out.push({ ok: false, error: String(e.message) }); }
}
process.stdout.write(JSON.stringify(out));
"""

SCHEMA = """
CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role;
CREATE SCHEMA social_wiring;
CREATE FUNCTION public.current_org_id_for(t text) RETURNS uuid LANGUAGE sql AS $$ SELECT NULL::uuid $$;
CREATE TABLE social_wiring.pipeline_stages (id uuid primary key default gen_random_uuid(), org_id uuid, pipeline text, ativo boolean default true, posicao int default 0, slug text);
CREATE FUNCTION social_wiring.ensure_default_pipeline_stages(p uuid) RETURNS void LANGUAGE sql AS $$
  INSERT INTO social_wiring.pipeline_stages (org_id, pipeline, slug)
  SELECT p, 'funil', 'novo' WHERE NOT EXISTS (SELECT 1 FROM social_wiring.pipeline_stages WHERE org_id = p) $$;
CREATE TABLE social_wiring.meta_ads_leads (id text primary key, org_id uuid not null, full_name text, email text, phone text);
CREATE TABLE social_wiring.leads (id uuid primary key default gen_random_uuid(), org_id uuid not null, cliente_nome text, contato text, meta_lead_id text);
CREATE TABLE social_wiring.atendimentos (
  id uuid primary key default gen_random_uuid(), org_id uuid not null,
  lead_id uuid REFERENCES social_wiring.leads(id), meta_ads_lead_id text REFERENCES social_wiring.meta_ads_leads(id),
  etapa_id uuid, titulo text, kanban_pos numeric);
CREATE UNIQUE INDEX uq_sw_atendimentos_meta_lead ON social_wiring.atendimentos (meta_ads_lead_id) WHERE meta_ads_lead_id IS NOT NULL;
CREATE UNIQUE INDEX uq_sw_atendimentos_lead ON social_wiring.atendimentos (lead_id) WHERE lead_id IS NOT NULL;
"""
TRIGGERS = """
CREATE TRIGGER t_l AFTER INSERT ON social_wiring.leads FOR EACH ROW EXECUTE FUNCTION social_wiring.spawn_funil_card();
CREATE TRIGGER t_m AFTER INSERT ON social_wiring.meta_ads_leads FOR EACH ROW EXECUTE FUNCTION social_wiring.spawn_funil_card();
"""
REAL, GHOST = "11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222"
L1, L2 = "aaaaaaaa-0000-0000-0000-000000000001", "aaaaaaaa-0000-0000-0000-000000000002"


def _function_sql(path: Path) -> str:
    m = re.search(r"(CREATE OR REPLACE FUNCTION social_wiring\.spawn_funil_card\(\).*?\$function\$;)",
                  path.read_text(encoding="utf-8"), re.S)
    assert m, path
    return m.group(1)


def _run(steps: list[str]) -> list[dict]:
    p = subprocess.run(["node", "--input-type=module", "-e", _JS], cwd=NODE_DIR, input=json.dumps({"steps": steps}),
                       capture_output=True, text=True, check=True, timeout=120)
    return json.loads(p.stdout)


def _scenario(new: bool, shape: str) -> list[dict]:
    steps = [SCHEMA, _function_sql(M_OLD), TRIGGERS]
    if new:
        body = M_NEW.read_text(encoding="utf-8")
        steps.append(body)  # whole file: index swap + table + function
    base = len(steps)
    steps += [
        f"INSERT INTO social_wiring.meta_ads_leads (id, org_id, full_name) VALUES ('M1','{REAL}','Real Person')"
        if shape == "same_org" else
        f"INSERT INTO social_wiring.meta_ads_leads (id, org_id, full_name) VALUES ('M1','{GHOST}','Ghost')",
    ]
    if shape == "cross_org":
        # card spawned for the ghost org holds M1; the REAL org's lead is backfilled later
        steps += [f"INSERT INTO social_wiring.leads (id, org_id, cliente_nome, meta_lead_id) VALUES ('{L1}','{REAL}','Real Person','M1')"]
    else:
        # M1's card (REAL) is linked to L1; a second lead L2 of the same org claims M1 as well
        steps += [f"INSERT INTO social_wiring.leads (id, org_id, cliente_nome, meta_lead_id) VALUES ('{L1}','{REAL}','First','M1')",
                  f"INSERT INTO social_wiring.leads (id, org_id, cliente_nome, meta_lead_id) VALUES ('{L2}','{REAL}','Second','M1')"]
    steps.append("SELECT lead_id::text, org_id::text, meta_ads_lead_id FROM social_wiring.atendimentos ORDER BY titulo")
    res = _run(steps)
    assert all(r["ok"] for r in res[:base]), res[:base]
    return res[base:]


def test_old_function_drops_the_card_cross_org(pglite):
    res = _scenario(False, "cross_org")
    cards = res[-1]["rows"]
    assert not any(c["lead_id"] == L1 for c in cards), "old function was expected to lose the real org's card"


def test_new_function_keeps_the_card_cross_org(pglite):
    res = _scenario(True, "cross_org")
    assert all(r["ok"] for r in res), res
    assert any(c["lead_id"] == L1 and c["org_id"] == REAL for c in res[-1]["rows"])


def test_old_function_drops_the_card_same_org(pglite):
    res = _scenario(False, "same_org")
    cards = res[-1]["rows"]
    assert not any(c["lead_id"] == L2 for c in cards), "old function was expected to lose the second lead's card"


def test_new_function_keeps_card_and_records_anomaly_same_org(pglite):
    steps_res = _scenario(True, "same_org")
    assert all(r["ok"] for r in steps_res), steps_res
    cards = steps_res[-1]["rows"]
    l2 = [c for c in cards if c["lead_id"] == L2]
    assert len(l2) == 1 and l2[0]["meta_ads_lead_id"] is None, cards
    # anomaly visible
    steps = [SCHEMA, _function_sql(M_OLD), TRIGGERS,
             M_NEW.read_text(encoding="utf-8"),
             f"INSERT INTO social_wiring.meta_ads_leads (id, org_id) VALUES ('M1','{REAL}')",
             f"INSERT INTO social_wiring.leads (id, org_id, cliente_nome, meta_lead_id) VALUES ('{L1}','{REAL}','A','M1')",
             f"INSERT INTO social_wiring.leads (id, org_id, cliente_nome, meta_lead_id) VALUES ('{L2}','{REAL}','B','M1')",
             "SELECT tipo, lead_id::text FROM social_wiring.funil_card_anomalias"]
    res = _run(steps)
    assert res[-1]["rows"] == [{"tipo": "meta_lead_ja_ligado_a_outro_lead", "lead_id": L2}], res[-1]


def test_migration_is_idempotent(pglite):
    steps = [SCHEMA, _function_sql(M_OLD), TRIGGERS]
    body = M_NEW.read_text(encoding="utf-8")
    res = _run(steps + [body, body])
    assert all(r["ok"] for r in res), res

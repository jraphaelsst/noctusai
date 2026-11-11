"""The activities DDL + event-writing RPCs on a REAL Postgres (PGlite, PG16/WASM).

The mock PostgREST client cannot enforce CHECKs, triggers, composite FKs or row locks, and a parser cannot prove plpgsql
RUNS. Every rule the organ claims is exercised here: lazy idempotent type seeding, create + its `atividade_criada` event,
the done/undone lifecycle with idempotent replays (no second event), reassign/reschedule/edit carrying from->to in the event,
cancel as a terminal state, refusals that leave NO event behind, cross-org isolation of the RPCs, the append-only events, and
the RPCs resolving with the NAMED arguments `service.py` sends (PostgREST resolves by name, never position).
Skips (visibly) when `node` or the harness install is unavailable -- a skip is not a pass.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from noctusai_lib.domain.activities import ActivitiesConfig, activities_migration

ROOT = Path(__file__).resolve().parents[6]
NODE_DIR = ROOT / "mcp" / "noctusai" / "node"
HARNESS = NODE_DIR / "migration_replay" / "replay.mjs"
STUBS = NODE_DIR / "migration_replay" / "stubs.sql"
SERVICE_PY = Path(__file__).resolve().parents[3] / "noctusai_lib" / "domain" / "activities" / "service.py"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None or not HARNESS.exists() or not (NODE_DIR / "node_modules" / "@electric-sql").exists(),
    reason="PGlite replay harness unavailable (needs `node` and mcp/noctusai/node/node_modules)",
)

SCHEMA = "actx"

PRELUDE = f"""
CREATE SCHEMA IF NOT EXISTS {SCHEMA};
CREATE OR REPLACE FUNCTION public.current_org_id_for(text) RETURNS uuid LANGUAGE sql STABLE AS $$ SELECT NULL::uuid $$;
"""

BASE = """
DO $$
DECLARE o uuid := gen_random_uuid(); other uuid := gen_random_uuid(); ent uuid := gen_random_uuid();
        u1 uuid := gen_random_uuid(); u2 uuid := gen_random_uuid(); a uuid; r jsonb; n int; t text; row_ record;
BEGIN
  r := @S@.act_seed_types(o, '[{"slug":"tarefa","label":"Tarefa","kind":"task","position":0},{"slug":"visita","label":"Visita","kind":"visit","position":1}]'::jsonb);
  r := @S@.act_seed_types(other, '[{"slug":"tarefa","label":"Tarefa","kind":"task","position":0}]'::jsonb);
  r := @S@.act_create(o, jsonb_build_object('entity_kind','lead','entity_id',ent,'type_slug','tarefa','title','Ligar para o cliente','created_by',u1));
  a := (r->'activity'->>'id')::uuid;
  {body}
END $$;
"""


def need(cond: str, msg: str) -> str:
    return f"IF NOT ({cond}) THEN RAISE EXCEPTION '{msg}: %', r; END IF;"


def events(expr: str = "a") -> str:
    return f"(SELECT count(*) FROM @S@.act_events WHERE activity_id = {expr})"


def apply(intent: str, args: str = "'{}'::jsonb", actor: str = "u1", act: str = "a", org: str = "o") -> str:
    return f"r := @S@.act_apply({org}, {act}, {actor}, '{intent}', {args});"


SCENARIOS: dict[str, str] = {
    "type seeding is idempotent and never overwrites an org edit": """
  r := @S@.act_seed_types(o, '[{"slug":"tarefa","label":"OUTRO","kind":"task"}]'::jsonb);
  """ + need("(r->>'inserted')::int = 0", "seed replay inserts nothing") + """
  SELECT label INTO t FROM @S@.act_types WHERE org_id = o AND slug = 'tarefa';
  """ + need("t = 'Tarefa'", "label kept"),
    "create writes the activity AND one atividade_criada event in the same call": """
  """ + need("r->>'status' = 'ok' AND r->'activity'->>'kind' = 'task'", "created with the type kind") + f"""
  {need(f"{events()} = 1", "one event")}
  SELECT event, actor_id, data INTO row_ FROM @S@.act_events WHERE activity_id = a;
  {need("row_.event = 'atividade_criada' AND row_.actor_id = u1 AND row_.data->>'type_slug' = 'tarefa'", "event shape")}""",
    "create refuses an unknown, inactive or foreign-org type and leaves nothing behind": """
  r := @S@.act_create(o, jsonb_build_object('entity_kind','lead','entity_id',ent,'type_slug','nao_existe','title','x'));
  """ + need("r->>'code' = 'tipo_invalido'", "unknown type") + """
  UPDATE @S@.act_types SET active = false WHERE org_id = o AND slug = 'visita';
  r := @S@.act_create(o, jsonb_build_object('entity_kind','lead','entity_id',ent,'type_slug','visita','title','x'));
  """ + need("r->>'code' = 'tipo_invalido'", "inactive type") + """
  r := @S@.act_create(other, jsonb_build_object('entity_kind','lead','entity_id',ent,'type_slug','visita','title','x'));
  """ + need("r->>'code' = 'tipo_invalido'", "foreign org type") + """
  SELECT count(*) INTO n FROM @S@.act_activities WHERE title = 'x';
  """ + need("n = 0", "no row left behind"),
    "complete sets done/outcome, appends an event, and a repeat is a replay with no second event": apply("concluir", "'{\"outcome\":\"sem_resposta\"}'::jsonb") + f"""
  {need("r->>'status' = 'ok' AND r->'activity'->>'outcome' = 'sem_resposta' AND r->'activity'->>'done_at' IS NOT NULL AND (r->'activity'->>'done_by')::uuid = u1", "completed")}
  """ + apply("concluir") + f"""
  {need("r->>'status' = 'replayed'", "replay")}
  {need(f"{events()} = 2", "created + concluida only")}
  SELECT count(*) INTO n FROM @S@.act_events WHERE activity_id = a AND event = 'atividade_concluida';
  {need("n = 1", "one concluida")}""",
    "complete defaults the outcome to realizada and rejects an unknown one": apply("concluir", "'{\"outcome\":\"talvez\"}'::jsonb") + """
  """ + need("r->>'code' = 'desfecho_invalido'", "bad outcome") + "\n  " + apply("concluir") + """
  """ + need("r->'activity'->>'outcome' = 'realizada'", "default outcome"),
    "reopen undoes the completion, once": apply("concluir") + "\n  " + apply("reabrir") + f"""
  {need("r->>'status' = 'ok' AND r->'activity'->>'done_at' IS NULL AND r->'activity'->>'outcome' IS NULL", "reopened")}
  """ + apply("reabrir") + f"""
  {need("r->>'status' = 'replayed'", "second reopen replays")}
  SELECT count(*) INTO n FROM @S@.act_events WHERE activity_id = a AND event = 'atividade_reaberta';
  {need("n = 1", "one reaberta")}""",
    "reassign carries from/to in the event, unassigns with null, and replays when nothing changes": apply("reatribuir", "jsonb_build_object('assignee_id', u1)") + "\n  " + apply("reatribuir", "jsonb_build_object('assignee_id', u2)") + """
  SELECT data INTO row_ FROM @S@.act_events WHERE activity_id = a AND event = 'atividade_reatribuida' ORDER BY seq DESC LIMIT 1;
  """ + need("(row_.data->>'from')::uuid = u1 AND (row_.data->>'to')::uuid = u2", "from/to") + "\n  " + apply("reatribuir", "jsonb_build_object('assignee_id', u2)") + f"""
  {need("r->>'status' = 'replayed'", "same assignee replays")}
  """ + apply("reatribuir", "jsonb_build_object('assignee_id', NULL)") + f"""
  {need("r->'activity'->>'assignee_id' IS NULL", "unassigned")}
  {need(f"{events()} = 4", "created + 3 reatribuidas")}""",
    "reschedule records from/to and replays on the same instant": apply("reagendar", "jsonb_build_object('due_at', '2030-01-01T10:00:00Z')") + "\n  " + apply("reagendar", "jsonb_build_object('due_at', '2030-01-02T10:00:00Z')") + """
  SELECT data INTO row_ FROM @S@.act_events WHERE activity_id = a AND event = 'atividade_reagendada' ORDER BY seq DESC LIMIT 1;
  """ + need("(row_.data->>'from')::timestamptz = '2030-01-01T10:00:00Z' AND (row_.data->>'to')::timestamptz = '2030-01-02T10:00:00Z'", "from/to") + "\n  " + apply("reagendar", "jsonb_build_object('due_at', '2030-01-02T10:00:00Z')") + f"""
  {need("r->>'status' = 'replayed'", "replay")}""",
    "edit names the changed fields, refuses a blank title and replays a no-op": apply("editar", "jsonb_build_object('title', '   ')") + """
  """ + need("r->>'code' = 'titulo_invalido'", "blank title") + "\n  " + apply("editar", "jsonb_build_object('title', 'Novo título', 'notes', 'nota')") + """
  SELECT data INTO row_ FROM @S@.act_events WHERE activity_id = a AND event = 'atividade_editada';
  """ + need("row_.data->'fields' = '[\"title\",\"notes\"]'::jsonb", "fields named") + "\n  " + apply("editar", "jsonb_build_object('title', 'Novo título')") + f"""
  {need("r->>'status' = 'replayed'", "no-op replays")}""",
    "cancel is terminal: later intents are refused, a repeat replays, a done one cannot be cancelled": apply("cancelar") + "\n  " + apply("cancelar") + """
  """ + need("r->>'status' = 'replayed'", "cancel replays") + "\n  " + apply("concluir") + """
  """ + need("r->>'code' = 'atividade_encerrada'", "complete after cancel") + "\n  " + apply("reatribuir", "jsonb_build_object('assignee_id', u2)") + """
  """ + need("r->>'code' = 'atividade_encerrada'", "reassign after cancel") + """
  r := @S@.act_create(o, jsonb_build_object('entity_kind','lead','entity_id',ent,'type_slug','tarefa','title','outra'));
  a := (r->'activity'->>'id')::uuid;
  """ + apply("concluir") + "\n  " + apply("cancelar") + """
  """ + need("r->>'code' = 'atividade_encerrada'", "cancel after done"),
    "a refusal leaves no event behind": apply("concluir") + "\n  " + apply("reatribuir", "jsonb_build_object('assignee_id', u2)") + f"""
  {need("r->>'code' = 'atividade_encerrada'", "refused")}
  {need(f"{events()} = 2", "no event for the refused call")}""",
    "the RPCs never see another org's activity": apply("concluir", org="other") + """
  """ + need("r->>'code' = 'atividade_inexistente'", "foreign org") + """
  SELECT done_at INTO row_ FROM @S@.act_activities WHERE id = a;
  """ + need("row_.done_at IS NULL", "untouched") + "\n  " + apply("concluir", act="gen_random_uuid()") + """
  """ + need("r->>'code' = 'atividade_inexistente'", "missing id"),
    "an unknown intent is refused": apply("apagar") + """
  """ + need("r->>'code' = 'intencao_invalida'", "unknown intent"),
    "events are append-only (UPDATE, DELETE and TRUNCATE are refused)": """
  BEGIN
    UPDATE @S@.act_events SET event = 'atividade_concluida' WHERE activity_id = a;
    RAISE EXCEPTION 'NOT REFUSED: update';
  EXCEPTION WHEN SQLSTATE 'AC002' THEN NULL; END;
  BEGIN
    DELETE FROM @S@.act_events WHERE activity_id = a;
    RAISE EXCEPTION 'NOT REFUSED: delete';
  EXCEPTION WHEN SQLSTATE 'AC002' THEN NULL; END;
  BEGIN
    TRUNCATE @S@.act_events;
    RAISE EXCEPTION 'NOT REFUSED: truncate';
  EXCEPTION WHEN SQLSTATE 'AC002' THEN NULL; END;""",
    "a type slug is unique per org but reusable across orgs": """
  BEGIN
    INSERT INTO @S@.act_types (org_id, slug, label, kind) VALUES (o, 'tarefa', 'Outra', 'task');
    RAISE EXCEPTION 'NOT REFUSED: duplicate slug in one org';
  EXCEPTION WHEN unique_violation THEN NULL; END;
  INSERT INTO @S@.act_types (org_id, slug, label, kind) VALUES (other, 'visita', 'Visita', 'visit');""",
    "an activity cannot point at another org's type (composite FK) nor be done and cancelled": """
  BEGIN
    INSERT INTO @S@.act_activities (org_id, entity_kind, entity_id, type_slug, kind, title)
      VALUES (other, 'lead', ent, 'visita', 'visit', 'x');
    RAISE EXCEPTION 'NOT REFUSED: foreign type';
  EXCEPTION WHEN foreign_key_violation THEN NULL; END;
  BEGIN
    UPDATE @S@.act_activities SET done_at = now(), cancelled_at = now() WHERE id = a;
    RAISE EXCEPTION 'NOT REFUSED: done and cancelled';
  EXCEPTION WHEN check_violation THEN NULL; END;""",
    "the nullable org_unit_id convention rides on create and its event": """
  r := @S@.act_create(o, jsonb_build_object('entity_kind','contrato','entity_id',ent,'type_slug','tarefa','title','unidade','org_unit_id',u2));
  """ + need("(r->'activity'->>'org_unit_id')::uuid = u2", "unit on the row") + """
  SELECT data INTO row_ FROM @S@.act_events WHERE activity_id = (r->'activity'->>'id')::uuid;
  """ + need("(row_.data->>'org_unit_id')::uuid = u2", "unit on the event"),
}


def _service_py_calls() -> dict[str, list[str]]:
    """{rpc: [argument names]} exactly as service.py sends them (so a renamed argument fails here, not in prod)."""
    src = SERVICE_PY.read_text(encoding="utf-8")
    calls = {"seed_types": re.findall(r'"(p_\w+)"', re.search(r'_rpc\(s, "seed_types", \{(.*?)\}\)', src, re.S).group(1))}
    calls["create"] = re.findall(r'"(p_\w+)"', re.search(r'_rpc\(s, "create", \{(.*?)\}\)', src, re.S).group(1))
    apply_blk = re.search(r'_rpc\(\s*s, "apply", \{(.*?)\}\s*\)', src, re.S).group(1)
    calls["apply"] = re.findall(r'"(p_\w+)"', apply_blk)
    return calls


def _named_args_scenario() -> str:
    exprs = {
        "p_org": "o", "p_id": "a", "p_actor": "u1", "p_intent": "'concluir'", "p_args": "'{}'::jsonb",
        "p_row": "jsonb_build_object('entity_kind','lead','entity_id',ent,'type_slug','tarefa','title','named')",
        "p_rows": "'[]'::jsonb",
    }
    body = []
    for rpc, keys in _service_py_calls().items():
        call = f"@S@.act_{rpc}(" + ", ".join(f"{k} => {exprs[k]}" for k in keys) + ")"
        body.append(f"r := {call};\n  {need(f'r->>' + chr(39) + 'status' + chr(39) + ' IN (' + chr(39) + 'ok' + chr(39) + ', ' + chr(39) + 'replayed' + chr(39) + ')', 'named call ' + rpc)}")
    body.append(
        "BEGIN\n    r := @S@.act_create(p_org_id => o, p_row => '{}'::jsonb);\n"
        "    RAISE EXCEPTION 'NOT REFUSED: a misnamed argument resolved';\n  EXCEPTION WHEN undefined_function THEN NULL; END;"
    )
    return "\n  ".join(body)


def _run() -> dict:
    migration = activities_migration(ActivitiesConfig(schema=SCHEMA), SCHEMA)
    scenarios = {**SCENARIOS, "the RPCs resolve with the named arguments service.py sends": _named_args_scenario()}
    steps = [
        {"product": SCHEMA, "file": "prelude", "sql": PRELUDE, "mode": "file", "twice": False},
        {"product": SCHEMA, "file": "migration", "sql": migration, "mode": "file", "twice": True},
        *(
            {"product": SCHEMA, "file": f"scenario: {name}", "sql": BASE.replace("{body}", body).replace("@S@", SCHEMA), "mode": "file", "twice": False}
            for name, body in scenarios.items()
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


@pytest.fixture(scope="module")
def replay() -> dict:
    return _run()


def test_migration_applies_twice(replay):
    assert replay["migration"]["failures"] == [], replay["migration"]["failures"]


NAMES = sorted({*SCENARIOS, "the RPCs resolve with the named arguments service.py sends"})


@pytest.mark.parametrize("name", NAMES)
def test_scenario(replay, name):
    assert replay[f"scenario: {name}"]["failures"] == [], replay[f"scenario: {name}"]["failures"]

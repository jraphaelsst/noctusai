"""The generated DDL on a REAL Postgres (PGlite, PG16/WASM) -- applied twice, then every DB-side rule exercised.

The mock PostgREST client cannot enforce unique indexes, CHECKs, FKs or triggers, and a parser cannot prove DDL RUNS.
This drives the toolkit's own migration-replay node harness with the generators' output (parties + items first: the
quotes reference them). Each rule is a statement that MUST be refused; a rule that is not enforced reaches
`RAISE EXCEPTION 'NOT ENFORCED'`, which no handler catches, so the step fails BY NAME.
Skips (visibly, with the reason) when `node` or the harness install is unavailable -- a skip is not a pass.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from noctusai_lib.domain.items import ItemsConfig, items_migration
from noctusai_lib.domain.parties import PartiesConfig, parties_migration
from noctusai_lib.domain.quotes import QuotesConfig, quotes_migration

ROOT = Path(__file__).resolve().parents[6]
NODE_DIR = ROOT / "mcp" / "noctusai" / "node"
HARNESS = NODE_DIR / "migration_replay" / "replay.mjs"
STUBS = NODE_DIR / "migration_replay" / "stubs.sql"
SCHEMA = "quox"
S = SCHEMA

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None or not HARNESS.exists() or not (NODE_DIR / "node_modules" / "@electric-sql").exists(),
    reason="PGlite replay harness unavailable (needs `node` and mcp/noctusai/node/node_modules)",
)

PRELUDE = f"""
CREATE SCHEMA IF NOT EXISTS {S};
CREATE OR REPLACE FUNCTION public.current_org_id_for(text) RETURNS uuid LANGUAGE sql STABLE AS $$ SELECT NULL::uuid $$;
"""

#: Two orgs, one party each, a draft quote + one line (`q`, `ln`), a SECOND quote already sent (`qs`, same org), all declared.
_BASE = f"""
DO $$
DECLARE o uuid := gen_random_uuid(); o2 uuid := gen_random_uuid();
  p uuid := gen_random_uuid(); p2 uuid := gen_random_uuid(); q uuid := gen_random_uuid(); qs uuid := gen_random_uuid();
  ln uuid := gen_random_uuid(); acc uuid; n1 bigint; n2 bigint; n3 bigint;
BEGIN
  INSERT INTO {S}.pty_parties(id,org_id,kind,legal_name) VALUES (p,o,'PF','Ana'), (p2,o2,'PF','Beto');
  INSERT INTO {S}.quo_quotes(id,org_id,number,root_id,version,party_id,subtotal_cents,discount_cents,total_cents)
    VALUES (q,o,'ORC-1',q,1,p,1000,0,1000);
  INSERT INTO {S}.quo_lines(id,org_id,quote_id,position,description,qty,unit_price_cents,total_cents) VALUES (ln,o,q,0,'x',2,500,1000);
  INSERT INTO {S}.quo_quotes(id,org_id,number,root_id,version,party_id,status,subtotal_cents,total_cents,is_current)
    VALUES (qs,o,'ORC-2',qs,1,p,'sent',100,100,true);
  INSERT INTO {S}.quo_lines(id,org_id,quote_id,position,description,qty,unit_price_cents,total_cents)
    SELECT gen_random_uuid(),o,qs,0,'y',1,100,100 WHERE false;
  {{body}}
END $$;
"""


def q(table: str) -> str:
    return f"{S}.quo_{table}"


#: name -> (exception clause, statements). Variables o,o2,p,p2,q,qs,ln,acc are in scope.
RULES: dict[str, tuple[str, str]] = {
    "version unique per root": ("unique_violation",
        f"INSERT INTO {q('quotes')}(org_id,number,root_id,version,is_current,party_id) VALUES (o,'ORC-9',q,1,false,p)"),
    "one is_current per root": ("unique_violation",
        f"INSERT INTO {q('quotes')}(org_id,number,root_id,version,is_current,party_id) VALUES (o,'ORC-1',q,2,true,p)"),
    "number+version unique per org": ("unique_violation",
        f"INSERT INTO {q('quotes')}(org_id,number,root_id,version,is_current,party_id) VALUES (o,'ORC-1',gen_random_uuid(),1,true,p)"),
    "the same number may live in ANOTHER org": ("unique_violation",
        f"INSERT INTO {q('quotes')}(org_id,number,root_id,version,party_id) VALUES (o2,'ORC-1',gen_random_uuid(),1,p2); "
        f"INSERT INTO {q('quotes')}(org_id,number,root_id,version,party_id) VALUES (o2,'ORC-1',gen_random_uuid(),1,p2)"),
    "at most one accepted version per root": ("unique_violation",
        f"UPDATE {q('quotes')} SET status='accepted', accepted_at=now() WHERE id=q; "
        f"INSERT INTO {q('quotes')}(org_id,number,root_id,version,is_current,party_id,status,accepted_at) VALUES (o,'ORC-1',q,2,false,p,'accepted',now())"),
    "total = subtotal - discount": ("check_violation",
        f"INSERT INTO {q('quotes')}(org_id,number,root_id,party_id,subtotal_cents,discount_cents,total_cents) VALUES (o,'ORC-8',gen_random_uuid(),p,100,10,100)"),
    "accepted iff accepted_at": ("check_violation",
        f"UPDATE {q('quotes')} SET status='accepted' WHERE id=q"),
    "status vocabulary": ("check_violation",
        f"UPDATE {q('quotes')} SET status='won' WHERE id=q"),
    "convert_to vocabulary": ("check_violation",
        f"UPDATE {q('quotes')} SET convert_to='invoice' WHERE id=q"),
    "money is never negative": ("check_violation",
        f"UPDATE {q('quotes')} SET discount_cents=-1, total_cents=1001 WHERE id=q"),
    "a quote cannot name another org's party": ("foreign_key_violation",
        f"INSERT INTO {q('quotes')}(org_id,number,root_id,party_id) VALUES (o,'ORC-7',gen_random_uuid(),p2)"),
    "a line cannot name another org's quote": ("foreign_key_violation",
        f"INSERT INTO {q('lines')}(org_id,quote_id,position,description,qty,unit_price_cents,total_cents) VALUES (o2,q,5,'x',1,1,1)"),
    "line qty > 0": ("check_violation",
        f"INSERT INTO {q('lines')}(org_id,quote_id,position,description,qty,unit_price_cents,total_cents) VALUES (o,q,5,'x',0,1,0)"),
    "line position unique per quote": ("unique_violation",
        f"INSERT INTO {q('lines')}(org_id,quote_id,position,description,qty,unit_price_cents,total_cents) VALUES (o,q,0,'dup',1,1,1)"),
    "line kind vocabulary": ("check_violation",
        f"UPDATE {q('lines')} SET kind='gift' WHERE id=ln"),
    "a draft's lines stay editable": ("check_violation",
        f"UPDATE {q('lines')} SET qty=3, total_cents=1500 WHERE id=ln; DELETE FROM {q('lines')} WHERE id=ln; "
        f"INSERT INTO {q('lines')}(org_id,quote_id,position,description,qty,unit_price_cents,total_cents) VALUES (o,q,0,'new',1,1,1); "
        "RAISE check_violation USING MESSAGE = 'draft editable'"),
    "a sent quote's lines are frozen (insert)": ("SQLSTATE 'QU003'",
        f"UPDATE {q('quotes')} SET status='sent' WHERE id=q; INSERT INTO {q('lines')}(org_id,quote_id,position,description,qty,unit_price_cents,total_cents) VALUES (o,q,9,'late',1,1,1)"),
    "a sent quote's lines are frozen (update)": ("SQLSTATE 'QU003'",
        f"UPDATE {q('quotes')} SET status='sent' WHERE id=q; UPDATE {q('lines')} SET unit_price_cents=1 WHERE id=ln"),
    "a sent quote's lines are frozen (delete)": ("SQLSTATE 'QU003'",
        f"UPDATE {q('quotes')} SET status='sent' WHERE id=q; DELETE FROM {q('lines')} WHERE id=ln"),
    "a sent quote's terms are frozen": ("SQLSTATE 'QU003'",
        f"UPDATE {q('quotes')} SET status='sent' WHERE id=q; UPDATE {q('quotes')} SET terms='mudei' WHERE id=q"),
    "a sent quote's total is frozen": ("SQLSTATE 'QU003'",
        f"UPDATE {q('quotes')} SET status='sent' WHERE id=q; UPDATE {q('quotes')} SET subtotal_cents=1, total_cents=1 WHERE id=q"),
    "a sent quote's validity is frozen": ("SQLSTATE 'QU003'",
        f"UPDATE {q('quotes')} SET status='sent' WHERE id=q; UPDATE {q('quotes')} SET valid_until=current_date+400 WHERE id=q"),
    "a sent quote's lifecycle columns stay writable": ("check_violation",
        f"UPDATE {q('quotes')} SET status='sent' WHERE id=q; UPDATE {q('quotes')} SET status='viewed', viewed_at=now(), signature_ref='x', is_current=false WHERE id=q; "
        "RAISE check_violation USING MESSAGE = 'lifecycle ok'"),
    "only a draft can be deleted": ("SQLSTATE 'QU003'",
        f"DELETE FROM {q('quotes')} WHERE id=qs"),
    "a draft can be deleted (lines cascade)": ("check_violation",
        f"DELETE FROM {q('quotes')} WHERE id=q; "
        f"IF EXISTS (SELECT 1 FROM {q('lines')} WHERE quote_id=q) THEN RAISE EXCEPTION 'cascade missing'; END IF; RAISE check_violation USING MESSAGE = 'cascade ok'"),
    "one decision per quote version": ("unique_violation",
        f"INSERT INTO {q('acceptances')}(org_id,quote_id,decision,channel,signer_name,content_sha256) VALUES (o,q,'rejected','staff','A',repeat('a',64)); "
        f"INSERT INTO {q('acceptances')}(org_id,quote_id,decision,channel,signer_name,content_sha256) VALUES (o,q,'accepted','staff','A',repeat('a',64))"),
    "a public acceptance must carry the consent text": ("check_violation",
        f"INSERT INTO {q('acceptances')}(org_id,quote_id,decision,channel,signer_name,content_sha256) VALUES (o,q,'accepted','public_link','A',repeat('a',64))"),
    "content hash must be sha256 hex": ("check_violation",
        f"INSERT INTO {q('acceptances')}(org_id,quote_id,decision,channel,signer_name,consent_text,content_sha256) VALUES (o,q,'accepted','public_link','A','ok','xyz')"),
    "signer name not blank": ("check_violation",
        f"INSERT INTO {q('acceptances')}(org_id,quote_id,decision,channel,signer_name,consent_text,content_sha256) VALUES (o,q,'accepted','public_link','  ','ok',repeat('a',64))"),
    "an acceptance cannot name another org's quote": ("foreign_key_violation",
        f"INSERT INTO {q('acceptances')}(org_id,quote_id,decision,channel,signer_name,content_sha256) VALUES (o2,q,'rejected','staff','A',repeat('a',64))"),
    "acceptances are append-only (update)": ("SQLSTATE 'QU002'",
        f"INSERT INTO {q('acceptances')}(org_id,quote_id,decision,channel,signer_name,content_sha256) VALUES (o,q,'rejected','staff','A',repeat('a',64)); "
        f"UPDATE {q('acceptances')} SET signer_name='B' WHERE quote_id=q"),
    "acceptances are append-only (delete)": ("SQLSTATE 'QU002'",
        f"INSERT INTO {q('acceptances')}(org_id,quote_id,decision,channel,signer_name,content_sha256) VALUES (o,q,'rejected','staff','A',repeat('a',64)); "
        f"DELETE FROM {q('acceptances')} WHERE quote_id=q"),
    "acceptances are append-only (truncate)": ("SQLSTATE 'QU002'",
        f"TRUNCATE {q('acceptances')}"),
    "a decided quote cannot be deleted": ("foreign_key_violation",
        f"INSERT INTO {q('acceptances')}(org_id,quote_id,decision,channel,signer_name,content_sha256) VALUES (o,qs,'rejected','staff','A',repeat('a',64)); "
        f"UPDATE {q('quotes')} SET status='draft' WHERE id=qs; DELETE FROM {q('quotes')} WHERE id=qs"),
    "events are append-only (update)": ("SQLSTATE 'QU002'",
        f"INSERT INTO {q('events')}(org_id,quote_id,kind) VALUES (o,q,'created'); UPDATE {q('events')} SET kind='sent' WHERE quote_id=q"),
    "events are append-only (delete)": ("SQLSTATE 'QU002'",
        f"INSERT INTO {q('events')}(org_id,quote_id,kind) VALUES (o,q,'created'); DELETE FROM {q('events')} WHERE quote_id=q"),
    "event kind vocabulary": ("check_violation",
        f"INSERT INTO {q('events')}(org_id,quote_id,kind) VALUES (o,q,'teleported')"),
    "event detail is an object": ("check_violation",
        f"INSERT INTO {q('events')}(org_id,quote_id,kind,detail) VALUES (o,q,'created','[]'::jsonb)"),
    "events survive their draft's deletion": ("check_violation",
        f"INSERT INTO {q('events')}(org_id,quote_id,kind) VALUES (o,q,'created'); DELETE FROM {q('quotes')} WHERE id=q; "
        f"IF NOT EXISTS (SELECT 1 FROM {q('events')} WHERE quote_id=q) THEN RAISE EXCEPTION 'history lost'; END IF; RAISE check_violation USING MESSAGE = 'history kept'"),
    "the number sequence is atomic, gapless and per org": ("check_violation",
        f"n1 := {S}.quo_next_number(o); n2 := {S}.quo_next_number(o); n3 := {S}.quo_next_number(o2); "
        "IF n1 <> 1 OR n2 <> 2 OR n3 <> 1 THEN RAISE EXCEPTION 'sequence wrong: % % %', n1, n2, n3; END IF; RAISE check_violation USING MESSAGE = 'sequence ok'"),
    "the number RPC is not callable by authenticated": ("insufficient_privilege",
        f"SET LOCAL ROLE authenticated; PERFORM {S}.quo_next_number(o)"),
}


def _rule_sql(clause: str, stmt: str) -> str:
    body = f"""BEGIN
    {stmt};
    RAISE EXCEPTION 'NOT ENFORCED';
  EXCEPTION WHEN {clause} THEN NULL;
  END;"""
    return _BASE.replace("{body}", body)


@pytest.fixture(scope="module")
def replay() -> dict:
    steps = [
        {"product": SCHEMA, "file": "prelude", "sql": PRELUDE, "mode": "file", "twice": False},
        {"product": SCHEMA, "file": "parties_migration", "sql": parties_migration(PartiesConfig(schema=SCHEMA), SCHEMA), "mode": "file", "twice": False},
        {"product": SCHEMA, "file": "items_migration", "sql": items_migration(ItemsConfig(schema=SCHEMA)), "mode": "file", "twice": False},
        {"product": SCHEMA, "file": "quotes_migration", "sql": quotes_migration(QuotesConfig(schema=SCHEMA), SCHEMA), "mode": "file", "twice": True},
        *({"product": SCHEMA, "file": f"rule: {name}", "sql": _rule_sql(*rule), "mode": "file", "twice": False} for name, rule in RULES.items()),
    ]
    proc = subprocess.run(
        ["node", str(HARNESS)],
        input=json.dumps({"stubs": STUBS.read_text(encoding="utf-8"), "steps": steps}),
        capture_output=True, text=True, cwd=NODE_DIR, timeout=600,
    )
    try:
        out = json.loads(proc.stdout)
    except json.JSONDecodeError:  # the harness could not MEASURE: say so, never read it as a pass
        pytest.fail(f"PGlite harness produced no verdict: {(proc.stderr or proc.stdout)[-400:]}")
    assert out.get("ok"), out
    return {step["file"]: step for step in out["steps"]}


def test_ddl_applies_twice_on_real_postgres(replay):
    for name in ("parties_migration", "items_migration", "quotes_migration"):
        assert replay[name]["failures"] == [], (name, replay[name]["failures"])


@pytest.mark.parametrize("rule", list(RULES))
def test_database_rule_is_enforced(replay, rule):
    step = replay[f"rule: {rule}"]
    assert step["failures"] == [], f"{rule}: {step['failures']}"

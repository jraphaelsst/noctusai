"""Transition-log guard probes -- derived from the render's config marker, proven on PGlite (real PG16).

Pins the gate<->methodology contract for the seed transition-log primitive: every guard object the render
emits has a declared behaviour probe (and no probe outlives its guard); `verify_db_guards` derives the
probes for every aggregate rendered into any product (several per file, the shared erasure log once per
schema); on a real Postgres every refusal probe reports `refused`, the erasure probe reports `allowed`, a
dropped guard reports `permitted` and a broken erasure function reports `blocked`; and the
migration-guard keeper accepts a render with no allowlist entry.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
REPO_ROOT = Path(__file__).resolve().parents[3]
for sub in ("seed/lib/backend", "seed/framework/backend"):
    sys.path.insert(0, str(REPO_ROOT / sub))

from noctusai_lib.domain.transition_log import (  # noqa: E402
    KeyColumn,
    TransitionLogConfig,
    transition_log_guard_probes,
    transition_log_migration,
)
from tools.noctus.dev import migration_replay as mr  # noqa: E402
from tools.noctus.dev import verify_db_guards as vdg  # noqa: E402
from tools.noctus.dev.compliance import _detect_guard_objects  # noqa: E402

SCHEMA = "tl_probe"
_SENT = re.compile(r"NOC_PROBE:(\w+):")

CARD = TransitionLogConfig(schema=SCHEMA, aggregate="card", state_table="cards", state_column="stage_id", state_type="uuid")
PART = TransitionLogConfig(schema=SCHEMA, aggregate="participant", state_table="participants", state_column="status",
                           key=(KeyColumn("thread_id"), KeyColumn("agent_id", "text")),
                           state_updated_at_column=None, state_created_at_column=None)
NOFK = TransitionLogConfig(schema=SCHEMA, aggregate="optout", state_table="leads", state_column="opted_out",
                           state_type="text", foreign_key=False, key=(KeyColumn("lead_id", "bigint", "id"),))
CONFIGS = (CARD, PART, NOFK)

STATE_DDL = f"""
CREATE SCHEMA IF NOT EXISTS {SCHEMA};
CREATE OR REPLACE FUNCTION public.current_org_id_for(text) RETURNS uuid LANGUAGE sql STABLE AS $$ SELECT NULL::uuid $$;
CREATE TABLE {SCHEMA}.cards (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), org_id uuid NOT NULL, stage_id uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE {SCHEMA}.participants (org_id uuid NOT NULL, thread_id uuid NOT NULL, agent_id text NOT NULL,
    status text NOT NULL, PRIMARY KEY (thread_id, agent_id));
CREATE TABLE {SCHEMA}.leads (id bigint PRIMARY KEY, org_id uuid NOT NULL, opted_out text NOT NULL,
    created_at timestamptz, updated_at timestamptz);
"""


def _render() -> str:
    return "".join(transition_log_migration(c, header=i == 0) for i, c in enumerate(CONFIGS))


def test_every_guard_the_render_emits_has_a_probe_and_vice_versa():
    for cfg in CONFIGS:
        emitted = {g["guard_name"] for g in _detect_guard_objects(transition_log_migration(cfg))}
        declared = {p.guard_name for p in transition_log_guard_probes(cfg)}
        assert emitted == declared, (cfg.aggregate, emitted ^ declared)


def _product(root: Path, slug: str, files: dict[str, str]) -> None:
    mig = root / slug / "backend" / "migrations"
    mig.mkdir(parents=True)
    for name, sql in files.items():
        (mig / name).write_text(sql, encoding="utf-8")


def test_probes_are_derived_per_rendered_aggregate(tmp_path):
    _product(tmp_path, "alpha", {"001_base.sql": "SELECT 1;\n", "002_logs.sql": _render()})
    _product(tmp_path, "beta", {"001_base.sql": "SELECT 1;\n"})
    probes = vdg.derive_transition_log_probes(products_dir=tmp_path)
    assert {p.product for p in probes} == {"alpha"}
    assert len({p.id for p in probes}) == len(probes)
    erasers = [p for p in probes if p.kind == "write_allowed"]
    assert sorted(p.guard_name for p in erasers) == sorted(c.rpc("erase_subject") for c in CONFIGS)
    shared = [p for p in probes if p.guard_name.startswith("transition_log_erasures")]
    assert len(shared) == 2  # the schema's erasure log: its two guards probed once, not once per aggregate
    assert all(p.migrations == ("002_logs.sql",) for p in probes)


def test_an_unparseable_marker_is_a_failing_probe_not_silence(tmp_path):
    _product(tmp_path, "alpha", {"002_logs.sql": "-- transition-log-config: {not json\nSELECT 1;\n"})
    (probe,) = vdg.derive_transition_log_probes(products_dir=tmp_path)
    assert probe.id.endswith(".marker") and "no_fixture" in probe.sql


def _outcomes(res: dict, prefix: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for st in res["steps"]:
        if st["file"].startswith(prefix + ":"):
            err = st["failures"][0]["error"] if st["failures"] else ""
            m = _SENT.search(err)
            out[st["file"][len(prefix) + 1:]] = m.group(1) if m else f"UNCLASSIFIED: {err or 'no error'}"
    return out


def _step(name: str, sql: str) -> dict:
    return {"product": "tl-probes", "file": name, "sql": sql, "mode": "file", "twice": False}


def test_probes_behave_on_pglite(pglite, tmp_path):
    _product(tmp_path, "alpha", {"002_logs.sql": _render()})
    probes = vdg.derive_transition_log_probes(products_dir=tmp_path)

    def run(prefix: str, only=None) -> list[dict]:
        return [_step(f"{prefix}:{p.id}", vdg.wrap_rollback_only(p.sql)) for p in probes if only is None or only(p)]

    steps = [_step("setup", STATE_DDL), *run("pending"), _step("install", _render()), *run("live")]
    steps.append(_step("break", (
        f"DROP TRIGGER guard_card_events_append_only ON {SCHEMA}.card_events;\n"
        f"CREATE OR REPLACE FUNCTION {SCHEMA}.participant_erase_subject(p_org uuid, p_subject jsonb, p_reason text, "
        "p_actor_id uuid DEFAULT NULL) RETURNS jsonb LANGUAGE sql AS $$ SELECT jsonb_build_object('status', 'ok', 'deleted', 0) $$;"
    )))
    steps += run("broken", lambda p: p.id.endswith(("card.guard_card_events_append_only.update",
                                                     "card.guard_card_events_append_only.delete",
                                                     "participant.erase_subject")))
    res = mr._run_harness(steps, 600, None)
    assert res.get("ok"), res
    for st in res["steps"]:
        if st["file"] in ("setup", "install", "break"):
            assert not st["failures"], (st["file"], st["failures"])

    ids = {p.id for p in probes}
    pending = _outcomes(res, "pending")
    assert set(pending) == ids and set(pending.values()) == {"pending"}, pending
    live = _outcomes(res, "live")
    want = {p.id: ("allowed" if p.kind == "write_allowed" else "refused") for p in probes}
    assert live == want, {k: v for k, v in live.items() if want.get(k) != v}
    broken = _outcomes(res, "broken")
    assert broken == {
        "transition_log.alpha.card.guard_card_events_append_only.update": "permitted",
        "transition_log.alpha.card.guard_card_events_append_only.delete": "permitted",
        "transition_log.alpha.participant.erase_subject": "blocked",
    }, broken


def _write_mig(root: Path, product: str, filename: str, sql: str) -> str:
    d = root / "products" / product / "backend" / "migrations"
    d.mkdir(parents=True, exist_ok=True)
    (d / filename).write_text(sql, encoding="utf-8")
    return f"products/{product}/backend/migrations/{filename}"


def test_guard_keeper_accepts_a_render_and_still_flags_a_hand_added_guard(tmp_path):
    from tools.noctus.dev import compliance as C

    rel = _write_mig(tmp_path, "demo", "002_logs.sql", _render())
    assert C.check_migration_guard_has_probe(repo_root=tmp_path, paths=[rel]) == []
    rel2 = _write_mig(tmp_path, "demo", "003_more.sql", _render() + (
        f"\nALTER TABLE {SCHEMA}.card_events ADD CONSTRAINT card_events_zz_hand CHECK (seq < 100000);\n"))
    (finding,) = C.check_migration_guard_has_probe(repo_root=tmp_path, paths=[rel2])
    assert "card_events_zz_hand" in finding["issue"]

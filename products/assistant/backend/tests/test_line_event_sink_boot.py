"""The Assistant migration pins the seed template; booting a `send: disabled` line needs the persistent sink."""
from pathlib import Path

from noctusai_lib.domain.sql_templates import whatsapp_line_events_table_sql
from noctusai_lib.testing.migrations import migration_sql


def test_line_events_migration_pins_the_seed_template():
    sql = migration_sql(Path(__file__).resolve().parents[1], "whatsapp_line_events")
    assert whatsapp_line_events_table_sql("assistant") in sql


def test_main_wires_the_sink_before_registering_the_policy():
    src = (Path(__file__).resolve().parents[1] / "app" / "main.py").read_text()
    assert src.index("set_default_line_event_sink(") < src.index("register_line_policy(\n")

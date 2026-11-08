"""Declared READ seams of `FunnelConfig`: `card_select`, `row_filter`,
`search_haystack`, and a `card_projection` that reads embedded join keys.

Every default must reproduce the pre-seam behaviour exactly (`TestDefaultsUnchanged`).
The db is wrapped by a recording proxy handed in through the factory's own
`resolve_context` DI seam -- nothing is monkeypatched.
"""
from __future__ import annotations

from typing import Any

import pytest

from noctusai_lib.domain.pipeline import PipelineContext
from noctusai_lib.domain.pipeline.funnel import FunnelConfig

from .conftest import HEADERS, ORG, USER, build_funnel, make_cfg


class _SpyTable:
    def __init__(self, table: Any, log: list):
        self._table, self._log = table, log

    def select(self, cols: str = "*", *a: Any, **k: Any):
        self._log.append(cols)
        return self._table.select(cols, *a, **k)

    def __getattr__(self, name: str):
        return getattr(self._table, name)


class _SpyDb:
    """Delegates to the mock, recording every select string on the card table."""

    def __init__(self, db: Any, card_table: str):
        self._db, self._card_table, self.selects = db, card_table, []

    def table(self, name: str):
        table = self._db.table(name)
        return _SpyTable(table, self.selects) if name == self._card_table else table

    def __getattr__(self, name: str):
        return getattr(self._db, name)


def _spied(name: str, cfg: FunnelConfig, schema_validate: bool = True):
    holder: dict[str, _SpyDb] = {}

    def resolve(auth: tuple) -> PipelineContext:
        user, org = auth
        return PipelineContext(db=holder["spy"], org_id=org, user_id=user)

    fn = build_funnel(name, cfg=cfg, schema_validate=schema_validate, resolve=resolve)
    holder["spy"] = _SpyDb(fn.db, cfg.pipeline.card_table)
    fn.add_stage("entrada", posicao=0)
    return fn, holder["spy"]


def _board_ids(fn, query: str = "") -> list[str]:
    body = fn.client.get(fn.url(f"/board{query}"), headers=HEADERS).json()
    return [c["id"] for col in body["data"] for c in col["cards"]]


class TestDefaultsUnchanged:
    def test_default_seam_values(self):
        cfg = make_cfg("org")
        assert cfg.card_select == "*"
        assert cfg.row_filter is None
        assert cfg.search_haystack is None

    def test_default_reads_select_star_and_filter_nothing(self, funnel_schema_cache):
        fn, spy = _spied("org", make_cfg("org"))
        a = fn.add_card(titulo="João Ação", etapa="entrada")
        b = fn.add_card(titulo="Maria", etapa="entrada")
        assert sorted(_board_ids(fn)) == sorted([a, b])
        assert fn.client.get(fn.url(f"/cards/{a}"), headers=HEADERS).status_code == 200
        assert set(spy.selects) <= {"*"}
        assert _board_ids(fn, "?busca=joao%20acao") == [a]  # DTO-derived haystack, accent-folded


class TestCardSelect:
    def test_board_card_and_orphans_use_card_select_but_drop_index_read_stays_narrow(self, funnel_schema_cache):
        select = "*, lead:leads(nome)"
        fn, spy = _spied("org", make_cfg("org", card_select=select), schema_validate=False)
        a = fn.add_card(etapa="entrada")
        fn.add_card(etapa=None)
        assert _board_ids(fn) == [a]
        assert fn.client.get(fn.url("/board/orfaos"), headers=HEADERS).status_code == 200
        assert fn.client.get(fn.url(f"/cards/{a}"), headers=HEADERS).status_code == 200
        assert set(spy.selects) == {select}
        # the drop-index read asks for 3 columns on purpose and must keep doing so
        spy.selects.clear()
        fn.client.post(fn.url(f"/cards/{a}/mover-etapa"), headers=HEADERS, json={"para_etapa_id": fn.stages["entrada"], "novo_indice": 0})
        assert "id, kanban_pos, created_at" in spy.selects
        assert select in spy.selects  # the card read of the move itself

    @pytest.mark.parametrize("bad", ["", "   "])
    def test_blank_select_is_refused(self, bad):
        with pytest.raises(ValueError, match="card_select"):
            make_cfg("org", card_select=bad)


class TestRowFilter:
    def test_filter_hides_rows_from_board_card_and_orphans(self, funnel_schema_cache):
        cfg = make_cfg("org", row_filter=lambda q: q.eq("telefone", "visivel"))
        fn, _ = _spied("org", cfg)
        shown = fn.add_card(etapa="entrada", telefone="visivel")
        hidden = fn.add_card(etapa="entrada", telefone="oculto")
        orphan_hidden = fn.add_card(etapa=None, telefone="oculto")
        assert _board_ids(fn) == [shown]
        assert fn.client.get(fn.url(f"/cards/{shown}"), headers=HEADERS).status_code == 200
        assert fn.client.get(fn.url(f"/cards/{hidden}"), headers=HEADERS).status_code == 404
        orphans = fn.client.get(fn.url("/board/orfaos"), headers=HEADERS).json()["data"]
        assert orphan_hidden not in [c["id"] for c in orphans]

    def test_filter_runs_after_tenancy_and_never_widens_it(self, funnel_schema_cache):
        cfg = make_cfg("org", row_filter=lambda q: q.eq("telefone", "x"))
        fn, _ = _spied("org", cfg)
        fn.add_card(etapa="entrada", telefone="x", org="a1a1a1a1-2222-4333-8444-555555555555")
        assert _board_ids(fn) == []

    def test_filter_receives_the_query_and_its_return_is_used(self, funnel_schema_cache):
        seen: list[Any] = []

        def row_filter(q):
            seen.append(q)
            return q.eq("telefone", "ok")

        fn, _ = _spied("org", make_cfg("org", row_filter=row_filter))
        keep = fn.add_card(etapa="entrada", telefone="ok")
        fn.add_card(etapa="entrada", telefone="no")
        assert _board_ids(fn) == [keep]
        assert seen


class TestSearchHaystack:
    def test_search_runs_over_the_row_not_the_dto(self, funnel_schema_cache):
        cfg = make_cfg("org", search_haystack=lambda row: f"{row.get('lead', {}).get('nome', '')} {row.get('campanha', {}).get('nome', '')}")
        fn, _ = _spied("org", cfg)
        hit = fn.add_card(titulo="irrelevante", etapa="entrada", lead={"nome": "Zé Pimenta"}, campanha={"nome": "Black Friday"})
        fn.add_card(titulo="Pimenta", etapa="entrada", lead={"nome": "Outro"}, campanha={"nome": "x"})
        assert _board_ids(fn, "?busca=ze%20pimenta") == [hit]  # accent-folded, case-insensitive
        assert _board_ids(fn, "?busca=black") == [hit]
        assert _board_ids(fn, "?busca=irrelevante") == []  # the DTO title is NOT searched any more

    def test_phone_digits_haystack(self, funnel_schema_cache):
        digits = lambda row: "".join(ch for ch in str(row.get("telefone") or "") if ch.isdigit())
        fn, _ = _spied("org", make_cfg("org", search_haystack=digits))
        hit = fn.add_card(etapa="entrada", telefone="+55 (11) 99999-0000")
        assert _board_ids(fn, "?busca=999990000") == [hit]

    def test_none_or_empty_haystack_never_matches_and_never_crashes(self, funnel_schema_cache):
        fn, _ = _spied("org", make_cfg("org", search_haystack=lambda row: None))  # type: ignore[arg-type,return-value]
        fn.add_card(etapa="entrada")
        assert _board_ids(fn, "?busca=lead") == []


class TestProjectionReadsEmbeddedKeys:
    def test_projection_sees_joined_keys(self, funnel_schema_cache):
        cfg = make_cfg(
            "org",
            card_select="*, lead:leads(nome)",
            card_projection=lambda row: {
                "titulo": (row.get("lead") or {}).get("nome") or row["titulo"],
                "badges": [(row.get("etapa_rel") or {}).get("label", "")],
                "campos": {"campanha": (row.get("campanha") or {}).get("nome")},
            },
        )
        fn, _ = _spied("org", cfg, schema_validate=False)
        fn.add_card(titulo="fallback", etapa="entrada", lead={"nome": "Ana"}, etapa_rel={"label": "Entrada"}, campanha={"nome": "BF"})
        card = fn.client.get(fn.url("/board"), headers=HEADERS).json()["data"][0]["cards"][0]
        assert card["titulo"] == "Ana"
        assert card["badges"] == ["Entrada"]
        assert card["campos"]["campanha"] == "BF" and card["campos"]["telefone"] is None

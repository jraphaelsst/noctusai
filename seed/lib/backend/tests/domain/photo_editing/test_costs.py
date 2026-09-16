from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from noctusai_lib.domain.photo_editing import (
    TokenUsage,
    UnpricedModelError,
    backfill_fx,
    build_cost_row,
    price_usage_usd,
    record_ai_cost,
)
from noctusai_lib.domain.photo_editing.costs import catalog_entry, local_call_date
from noctusai_lib.integrations.fx import FakeFxRateAdapter, FxUpstreamError

from .conftest import EDIT_MODEL, ORG, PTAX, run

IMG_USAGE = TokenUsage(prompt_tokens=1_000, image_input_tokens=2_000,
                       image_output_tokens=4_000, total_tokens=7_000)


def test_image_edit_price_from_catalog() -> None:
    entry = catalog_entry("openai", EDIT_MODEL, "image_edit")
    # 1000*5 + 2000*8 + 4000*30 = 141_000 per 1M → $0.141
    assert price_usage_usd(entry, IMG_USAGE) == Decimal("0.141000")


def test_unknown_model_and_unpriced_leg_refuse() -> None:
    with pytest.raises(UnpricedModelError):
        catalog_entry("openai", "gpt-image-2", "image_edit")
    vision = catalog_entry("openai", "gpt-5.6-terra", "vision")
    with pytest.raises(UnpricedModelError, match="image output"):
        price_usage_usd(vision, TokenUsage(image_output_tokens=10))


def test_cost_row_shapes_match_the_table_check() -> None:
    brl = build_cost_row(org_id="o", category="c", step=None, reference_type=None,
                         reference_id=None, amount_native=Decimal("2"), currency="BRL")
    assert (brl.fx_pending, brl.amount_brl, brl.fx_rate, brl.fx_quote_date) == (
        False, Decimal("2.000000"), None, None)
    pending = build_cost_row(org_id="o", category="c", step=None, reference_type=None,
                             reference_id=None, amount_native=Decimal("1"), currency="USD")
    assert (pending.fx_pending, pending.amount_brl, pending.fx_rate) == (True, None, None)
    conv = build_cost_row(org_id="o", category="c", step=None, reference_type=None,
                          reference_id=None, amount_native=Decimal("0.141"), currency="USD",
                          fx_rate=Decimal("5.4321"), fx_quote_date=date(2026, 9, 16))
    assert (conv.fx_pending, conv.fx_rate, conv.amount_brl) == (
        False, Decimal("5.43210"), Decimal("0.765926"))


def test_call_date_is_sao_paulo_local() -> None:
    late_utc = datetime(2026, 9, 17, 1, 30, tzinfo=timezone.utc)  # 22:30 on the 16th in SP
    assert local_call_date(late_utc, "America/Sao_Paulo") == date(2026, 9, 16)
    with pytest.raises(ValueError):
        local_call_date(datetime(2026, 9, 16), "America/Sao_Paulo")


def test_record_writes_usage_and_converted_ledger(ports) -> None:
    rec = run(record_ai_cost(ports, org_id=ORG, step="fotos.edit", category="openai_edit",
                             operation="image_edit", kind="image_edit", model=EDIT_MODEL,
                             usage=IMG_USAGE, model_version="v"))
    usage = ports.repo.llm_usage[rec.llm_usage_id]
    assert (usage.image_output_tokens, usage.cost_estimate_usd, usage.model_version, usage.batch) == (
        4_000, Decimal("0.141000"), "v", False)
    cost = ports.repo.costs[rec.cost_ledger_id]
    assert cost.reference_type == "llm_usage" and cost.reference_id == str(rec.llm_usage_id)
    assert (cost.fx_rate, cost.fx_quote_date, cost.fx_pending) == (PTAX, date(2026, 9, 16), False)
    assert cost.amount_brl == (Decimal("0.141000") * PTAX).quantize(Decimal("0.000001"))


def test_weekend_walks_back_to_friday(ports, clock) -> None:
    clock.now = datetime(2026, 9, 20, 15, 0, tzinfo=timezone.utc)  # Sunday
    rec = run(record_ai_cost(ports, org_id=ORG, step="s", category="c", operation="image_edit",
                             kind="image_edit", model=EDIT_MODEL, usage=IMG_USAGE))
    assert ports.repo.costs[rec.cost_ledger_id].fx_quote_date == date(2026, 9, 16)


class DownFx:
    def __init__(self) -> None:
        self.calls = 0

    def get_ptax(self, quote_date):
        self.calls += 1
        raise FxUpstreamError("BCB fora do ar")


def test_no_bulletin_marks_pending_then_backfill_resolves(ports) -> None:
    import dataclasses

    no_bulletin = dataclasses.replace(ports, fx=FakeFxRateAdapter({}))
    rec = run(record_ai_cost(no_bulletin, org_id=ORG, step="s", category="c",
                             operation="image_edit", kind="image_edit", model=EDIT_MODEL,
                             usage=IMG_USAGE))
    assert rec.fx_pending
    row = ports.repo.costs[rec.cost_ledger_id]
    assert (row.amount_brl, row.fx_rate) == (None, None)  # never a silent default rate

    down = dataclasses.replace(ports, fx=DownFx())
    report = run(backfill_fx(down))
    assert (report.resolved, report.still_pending) == (0, 1)

    report = run(backfill_fx(ports))
    assert (report.resolved, report.still_pending) == (1, 0)
    row = ports.repo.costs[rec.cost_ledger_id]
    assert (row.fx_pending, row.fx_rate) == (False, PTAX)
    assert run(backfill_fx(ports)).resolved == 0  # idempotent

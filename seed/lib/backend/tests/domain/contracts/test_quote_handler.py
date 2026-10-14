"""`ContractQuoteAcceptHandler`: an accepted SERVICES quote becomes ONE draft contract, for exactly the accepted total."""
from __future__ import annotations

import pytest

from noctusai_lib.domain.contracts import contracts
from noctusai_lib.domain.contracts.quote_handler import ContractQuoteAcceptHandler, contract_lines, spread_discount
from noctusai_lib.domain.quotes import QuoteAcceptContext

from .conftest import CFG, ORG_A, ORG_B, mk_party

QUOTE = "55555555-5555-4555-8555-555555555555"


def line(desc="Consultoria", qty=2.0, unit=70000, discount=0, item_id=None, unit_name="UN") -> dict:
    gross = round(qty * unit)
    return {"id": "l", "position": 0, "item_id": item_id, "description": desc, "unit": unit_name, "kind": "service", "qty": qty,
            "unit_price_cents": unit, "discount_cents": discount, "total_cents": gross - discount}


def ctx(lines, *, party_id, discount=0, org=ORG_A, quote_id=QUOTE, title="Proposta de serviços") -> QuoteAcceptContext:
    subtotal = sum(ln["total_cents"] for ln in lines)
    quote = {"id": quote_id, "number": "ORC-00007", "party_id": party_id, "title": title, "notes": "Prazo: 30 dias",
             "subtotal_cents": subtotal, "discount_cents": discount, "total_cents": subtotal - discount,
             "party": {"id": party_id, "legal_name": "Ana Souza"}}
    return QuoteAcceptContext(org_id=org, quote=quote, lines=tuple(lines), acceptance={}, convert_to="contract")


@pytest.mark.parametrize(
    "totals,discount",
    [([10000], 0), ([10000, 5000], 1500), ([3333, 3333, 3334], 1), ([1, 1, 1], 2), ([100, 200, 300], 600), ([7, 11, 13], 5), ([0, 500], 100)],
)
def test_the_header_discount_is_spread_to_the_exact_cent(totals, discount):
    spread = spread_discount(totals, discount)
    assert sum(spread) == sum(totals) - discount and all(n >= 0 for n in spread) and len(spread) == len(totals)


def test_untouched_lines_keep_their_quantity_and_price():
    (ln,) = contract_lines([line(qty=2, unit=70000)], 0)
    assert (ln.quantity, ln.unit_price_cents, ln.description) == (2, 70000, "Consultoria")


def test_a_discounted_or_fractional_line_becomes_one_unit_at_its_net_total():
    a, b = contract_lines([line(qty=2, unit=1000, discount=100), line(desc="Horas", qty=1.5, unit=10000, unit_name="H")], 0)
    assert (a.quantity, a.unit_price_cents) == (1, 1900) and "(2 UN)" in a.description
    assert (b.quantity, b.unit_price_cents) == (1, 15000) and "(1,5 H)" in b.description


def test_creates_a_draft_contract_for_the_accepted_total_and_is_idempotent(db, s, s_b):
    party = mk_party(s)
    handler = ContractQuoteAcceptHandler(get_db=lambda: db, cfg=CFG)
    context = ctx([line(qty=2, unit=70000), line(desc="Setup", qty=1, unit=30000)], party_id=party["id"], discount=10000)
    result = handler.handle(context)
    contract = contracts.get_contract(s, result.ref)
    assert (result.kind, contract["status"], contract["source_quote_id"]) == ("contract", "draft", QUOTE)
    assert contract["amount_cents"] == 170000 - 10000  # the accepted total, header discount included
    assert (contract["party_name"], contract["title"]) == ("Ana Souza", "Proposta de serviços")
    again = handler.handle(context)
    assert again.ref == result.ref and again.detail["created"] is False
    assert len(db.table("ctr_contracts").select("*").execute().data) == 1


def test_a_title_defaults_to_the_quote_number(db, s):
    party = mk_party(s)
    result = ContractQuoteAcceptHandler(get_db=lambda: db, cfg=CFG).handle(ctx([line()], party_id=party["id"], title=""))
    assert contracts.get_contract(s, result.ref)["title"] == "Orçamento ORC-00007"


def test_another_orgs_party_cannot_be_contracted(db, s, s_b):
    party = mk_party(s_b)
    from noctusai_lib.domain.contracts.errors import ContractsError

    with pytest.raises(ContractsError):
        ContractQuoteAcceptHandler(get_db=lambda: db, cfg=CFG).handle(ctx([line()], party_id=party["id"], org=ORG_A))

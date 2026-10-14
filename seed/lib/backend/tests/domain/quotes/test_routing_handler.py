"""`RoutingQuoteAcceptHandler`: one handler per `convert_to`; an unwired kind is "I did nothing" (-> skipped)."""
from __future__ import annotations

from noctusai_lib.domain.quotes import FakeQuoteAcceptHandler, QuoteAcceptContext, RoutingQuoteAcceptHandler


def ctx(convert_to: str) -> QuoteAcceptContext:
    return QuoteAcceptContext(org_id="o", quote={"id": "q1"}, lines=(), acceptance={}, convert_to=convert_to)


def test_routes_by_convert_to():
    order, contract = FakeQuoteAcceptHandler(), FakeQuoteAcceptHandler()
    router = RoutingQuoteAcceptHandler({"order": order, "contract": contract})
    assert router.handle(ctx("order")).ref == "fake-order-q1" and router.handle(ctx("contract")).ref == "fake-contract-q1"
    assert (len(order.calls), len(contract.calls)) == (1, 1)


def test_a_kind_without_a_handler_is_skipped_not_an_error():
    router = RoutingQuoteAcceptHandler({"order": FakeQuoteAcceptHandler()})
    assert router.handle(ctx("contract")) is None


def test_a_handler_failure_propagates_so_the_organ_records_it_failed():
    boom = FakeQuoteAcceptHandler(raises=RuntimeError("down"))
    try:
        RoutingQuoteAcceptHandler({"order": boom}).handle(ctx("order"))
    except RuntimeError as exc:
        assert str(exc) == "down"
    else:  # pragma: no cover
        raise AssertionError("the failure must reach run_conversion")

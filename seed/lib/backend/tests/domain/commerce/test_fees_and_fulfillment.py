from __future__ import annotations

import pytest

from noctusai_lib.domain.commerce import FulfillmentType, NoopFulfillment, make_fulfillment_registry
from noctusai_lib.domain.commerce.fees import fee_estimate


class TestFeeEstimate:
    def test_flat_fees_dominate_low_tickets(self):
        assert fee_estimate(990) == {"pix_cents": 199, "boleto_cents": 199, "card_cents": 49 + 30}

    def test_card_is_flat_plus_299_bps_rounded_half_up(self):
        # 10_000 * 2.99% = 299 exactly; 4_700 * 2.99% = 140.53 -> 141
        assert fee_estimate(10_000)["card_cents"] == 49 + 299
        assert fee_estimate(4_700)["card_cents"] == 49 + 141

    def test_integer_cents_only(self):
        assert all(isinstance(v, int) for v in fee_estimate(12345).values())

    def test_negative_is_refused(self):
        with pytest.raises(ValueError):
            fee_estimate(-1)


class Recorder:
    def __init__(self):
        self.calls = []

    def on_paid(self, order, items):
        self.calls.append((order["id"], [i["fulfillment_type"] for i in items]))


class TestFulfillmentRegistry:
    def test_every_type_defaults_to_noop(self):
        reg = make_fulfillment_registry()
        for ft in FulfillmentType:
            assert isinstance(reg.handler_for(ft), NoopFulfillment)

    def test_dispatch_calls_each_type_once_with_its_items(self):
        digital, shipping = Recorder(), Recorder()
        reg = make_fulfillment_registry({FulfillmentType.DIGITAL_DELIVERY: digital, FulfillmentType.SHIPPING: shipping})
        items = [
            {"fulfillment_type": "digital_delivery"},
            {"fulfillment_type": "digital_delivery"},
            {"fulfillment_type": "shipping"},
            {"fulfillment_type": "none"},
        ]
        dispatched = reg.dispatch_paid({"id": "o1"}, items)
        assert digital.calls == [("o1", ["digital_delivery", "digital_delivery"])]
        assert shipping.calls == [("o1", ["shipping"])]
        assert dispatched == [FulfillmentType.DIGITAL_DELIVERY, FulfillmentType.SHIPPING, FulfillmentType.NONE]

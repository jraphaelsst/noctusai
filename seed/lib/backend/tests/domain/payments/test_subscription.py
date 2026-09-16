"""Subscription state machine — total, explicit, no silent no-ops."""
from datetime import datetime, timezone

import pytest

from noctusai_lib.domain.payments.subscription import (
    Subscription,
    SubscriptionState,
    is_terminal,
    legal_next_states,
    transition,
)

_NOW = datetime(2026, 9, 16, tzinfo=timezone.utc)


def _make(state: SubscriptionState) -> Subscription:
    return Subscription(
        id="sub-1",
        external_reference="org-1",
        gateway="stripe",
        id_at_gateway="sub_gw_1",
        state=state,
        created_at=_NOW,
        updated_at=_NOW,
    )


class TestLegalTransitions:
    @pytest.mark.parametrize(
        "source,target",
        [
            (SubscriptionState.INCOMPLETE, SubscriptionState.ACTIVE),
            (SubscriptionState.INCOMPLETE, SubscriptionState.EXPIRED),
            (SubscriptionState.TRIALING, SubscriptionState.ACTIVE),
            (SubscriptionState.TRIALING, SubscriptionState.CANCELED),
            (SubscriptionState.ACTIVE, SubscriptionState.PAST_DUE),
            (SubscriptionState.ACTIVE, SubscriptionState.CANCELED),
            (SubscriptionState.PAST_DUE, SubscriptionState.ACTIVE),
            (SubscriptionState.PAST_DUE, SubscriptionState.GRACE),
            (SubscriptionState.GRACE, SubscriptionState.ACTIVE),
            (SubscriptionState.GRACE, SubscriptionState.CANCELED),
            (SubscriptionState.GRACE, SubscriptionState.EXPIRED),
        ],
    )
    def test_legal_transition_succeeds(
        self, source: SubscriptionState, target: SubscriptionState
    ) -> None:
        subscription = _make(source)
        result = transition(subscription, target, now=_NOW)
        assert result.state is target
        assert result.updated_at == _NOW

    def test_legal_transition_returns_new_instance(self) -> None:
        subscription = _make(SubscriptionState.TRIALING)
        result = transition(subscription, SubscriptionState.ACTIVE, now=_NOW)
        assert result is not subscription
        assert subscription.state is SubscriptionState.TRIALING  # original untouched


class TestIllegalTransitions:
    @pytest.mark.parametrize(
        "source,target",
        [
            (SubscriptionState.TRIALING, SubscriptionState.PAST_DUE),
            (SubscriptionState.TRIALING, SubscriptionState.GRACE),
            (SubscriptionState.ACTIVE, SubscriptionState.GRACE),  # must pass through PAST_DUE
            (SubscriptionState.ACTIVE, SubscriptionState.TRIALING),
            (SubscriptionState.CANCELED, SubscriptionState.ACTIVE),  # terminal
            (SubscriptionState.EXPIRED, SubscriptionState.ACTIVE),  # terminal
            (SubscriptionState.INCOMPLETE, SubscriptionState.PAST_DUE),
            (SubscriptionState.INCOMPLETE, SubscriptionState.GRACE),
        ],
    )
    def test_illegal_transition_raises(
        self, source: SubscriptionState, target: SubscriptionState
    ) -> None:
        subscription = _make(source)
        with pytest.raises(ValueError, match="Illegal Subscription transition"):
            transition(subscription, target)

    def test_unknown_transition_never_silently_no_ops(self) -> None:
        """The core 'no silent errors' contract: an unrecognized move MUST
        raise, never return the input unchanged pretending it worked."""
        subscription = _make(SubscriptionState.CANCELED)
        with pytest.raises(ValueError):
            transition(subscription, SubscriptionState.GRACE)


class TestTerminalStates:
    def test_canceled_and_expired_are_terminal(self) -> None:
        assert is_terminal(SubscriptionState.CANCELED)
        assert is_terminal(SubscriptionState.EXPIRED)

    def test_non_terminal_states(self) -> None:
        for state in (
            SubscriptionState.INCOMPLETE,
            SubscriptionState.TRIALING,
            SubscriptionState.ACTIVE,
            SubscriptionState.PAST_DUE,
            SubscriptionState.GRACE,
        ):
            assert not is_terminal(state)

    def test_terminal_states_have_no_legal_next_states(self) -> None:
        assert legal_next_states(SubscriptionState.CANCELED) == frozenset()
        assert legal_next_states(SubscriptionState.EXPIRED) == frozenset()

    def test_active_next_states(self) -> None:
        assert legal_next_states(SubscriptionState.ACTIVE) == {
            SubscriptionState.PAST_DUE,
            SubscriptionState.CANCELED,
        }


class TestCanceledAtStamping:
    def test_canceled_at_set_on_cancel(self) -> None:
        subscription = _make(SubscriptionState.ACTIVE)
        canceled = transition(subscription, SubscriptionState.CANCELED, now=_NOW)
        assert canceled.canceled_at == _NOW

    def test_canceled_at_set_on_expire(self) -> None:
        subscription = _make(SubscriptionState.GRACE)
        expired = transition(subscription, SubscriptionState.EXPIRED, now=_NOW)
        assert expired.canceled_at == _NOW

    def test_canceled_at_untouched_on_non_terminal_transition(self) -> None:
        subscription = _make(SubscriptionState.ACTIVE)
        past_due = transition(subscription, SubscriptionState.PAST_DUE, now=_NOW)
        assert past_due.canceled_at is None

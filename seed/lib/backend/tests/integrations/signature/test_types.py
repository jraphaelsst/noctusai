"""`is_forward_transition` — the shared monotonic-status guard.

Vocabulary-agnostic on purpose: erp-imobiliario and social-wiring's
card_hub each carry their own `assinaturas`/envelope status vocabulary,
so the test doubles below exercise it with both a seed-shaped vocabulary
(`concluido`/`cancelado`/...) and a plain made-up one, to prove nothing
here is coupled to either product's enum.
"""
from __future__ import annotations

from noctusai_lib.integrations.signature import is_forward_transition

_TERMINAIS = frozenset({"concluido", "cancelado", "expirado"})


class TestNoPriorState:
    def test_none_atual_is_always_forward(self):
        assert is_forward_transition(None, "concluido", terminais=_TERMINAIS) is True
        assert is_forward_transition(None, "pendente", terminais=_TERMINAIS) is True


class TestNonTerminalCurrentState:
    def test_any_transition_out_of_a_non_terminal_state_is_forward(self):
        assert is_forward_transition("pendente", "concluido", terminais=_TERMINAIS) is True
        assert is_forward_transition("parcial", "cancelado", terminais=_TERMINAIS) is True
        assert is_forward_transition("pendente", "parcial", terminais=_TERMINAIS) is True


class TestTerminalCurrentState:
    def test_repeating_the_same_terminal_value_is_forward(self):
        """The idempotent-replay case: the provider re-delivers the exact
        event that already landed. Must be a no-op, not a refusal."""
        assert is_forward_transition("concluido", "concluido", terminais=_TERMINAIS) is True
        assert is_forward_transition("cancelado", "cancelado", terminais=_TERMINAIS) is True

    def test_a_different_value_over_a_terminal_state_is_a_regression(self):
        """The replayed-delivery attack this guard exists to close: a
        captured `cancelado` (or `concluido`) delivery, replayed after the
        row already reached a DIFFERENT terminal state, must never win."""
        assert is_forward_transition("concluido", "cancelado", terminais=_TERMINAIS) is False
        assert is_forward_transition("cancelado", "concluido", terminais=_TERMINAIS) is False
        assert is_forward_transition("concluido", "expirado", terminais=_TERMINAIS) is False

    def test_vocabulary_agnostic(self):
        """Not coupled to the seed's own `StatusAssinatura` values — a
        consumer's own vocabulary works identically."""
        terminais = frozenset({"assinado", "recusado", "expirado", "cancelado"})
        assert is_forward_transition("enviado", "assinado", terminais=terminais) is True
        assert is_forward_transition("assinado", "cancelado", terminais=terminais) is False
        assert is_forward_transition("assinado", "assinado", terminais=terminais) is True

"""`stage_gate` — what the refusal SAYS, not just that it refuses.

🔴 What this guards (found in prod 2026-08-31, walking a card end-to-end).

A lead created through `POST /api/leads` gets its funil card from migration
034's trigger, but `atendimentos.cliente_id` is attached asynchronously by
`clientes_backfill`. In that window the card has no titular, and the gate
refused the move — correctly — but reported the refusal by listing every
`EXIGENCIAS` entry:

    "Não é possível mover este atendimento: Nome, Celular são obrigatórios
     e ainda não consta no cadastro."

Both WERE in the cadastro. They were on the `leads` row the operator had just
filled in; what was missing was the `clientes` row. So the message sent the
operator back to re-type data that was already there, which is worse than
saying nothing: it names a cause that is not the cause.

The gate still closes in this state — that half was never in question and is
asserted here too, because "make the message honest" must not become "let the
card through".
"""
from __future__ import annotations

from app.modules.pipeline import stage_gate


class TestSemCliente:
    def test_gate_still_closes_when_there_is_no_titular(self):
        """The safety property. An atendimento with no person attached cannot
        have that person's name, and answering "nothing is missing" would be
        the silent-fallback shape."""
        pendentes = stage_gate.pendencias(None, "org-1", None)
        assert pendentes, "a card with no titular must still be refused"

    def test_reports_its_own_reason_rather_than_the_field_list(self):
        pendentes = stage_gate.pendencias(None, "org-1", None)
        assert pendentes == [stage_gate.SEM_CLIENTE]
        assert pendentes[0]["key"] == stage_gate.SEM_CLIENTE_KEY

    def test_message_names_the_real_cause_and_not_the_fields(self):
        msg = stage_gate.mensagem(stage_gate.pendencias(None, "org-1", None))
        assert "cadastro do cliente" in msg.lower()
        # The exact regression: it must NOT tell the operator that the name or
        # the phone they just typed are missing.
        assert "Nome," not in msg
        assert "Celular" not in msg
        assert "são obrigatórios" not in msg

    def test_no_client_call_is_needed_to_answer(self):
        """Passing `None` as the client proves the no-titular branch returns
        before touching the checklist service — a lookup keyed on a cliente_id
        that does not exist would be meaningless work at best."""
        assert stage_gate.pendencias(None, "org-1", None) == [stage_gate.SEM_CLIENTE]


class TestFieldListUnchanged:
    """The ordinary path — a real cliente missing a real field — must keep the
    message it always had. Only the no-titular case changed."""

    def test_single_missing_field_is_singular(self):
        msg = stage_gate.mensagem([{"key": "celular", "label": "Celular"}])
        assert "Celular é obrigatório" in msg
        assert "e ainda não consta no cadastro" in msg

    def test_two_missing_fields_are_plural_and_both_named(self):
        msg = stage_gate.mensagem(
            [{"key": "nome", "label": "Nome"}, {"key": "celular", "label": "Celular"}]
        )
        assert "Nome, Celular são obrigatórios" in msg

    def test_campos_obrigatorios_stays_derived_from_exigencias(self):
        """It is documented as derived so it can never disagree with the rules;
        the new sentinel must not have leaked into it."""
        assert stage_gate.CAMPOS_OBRIGATORIOS == tuple(
            e["key"] for e in stage_gate.EXIGENCIAS
        )
        assert stage_gate.SEM_CLIENTE_KEY not in stage_gate.CAMPOS_OBRIGATORIOS

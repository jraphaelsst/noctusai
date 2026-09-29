"""`_entity_label` — the word a 404 shows for the card's entity.

`entity_kind` is a machine key; when it isn't the word a person reads
(igig's "negocio" → "Negócio"), the product sets `entity_label`, which wins.
"""
from __future__ import annotations

from dataclasses import replace

from noctusai_lib.domain.card_hub.services import _entity_label


class TestEntityLabel:
    def test_entity_label_wins_over_the_machine_kind(self, hub):
        cfg = replace(hub.cfg, entity_kind="negocio", entity_label="Negócio")
        assert _entity_label(cfg) == "Negócio"

    def test_unset_label_capitalizes_the_kind(self, hub):
        cfg = replace(hub.cfg, entity_kind="cliente", entity_label=None)
        assert _entity_label(cfg) == "Cliente"

    def test_blank_label_falls_back_to_the_kind(self, hub):
        cfg = replace(hub.cfg, entity_kind="lead", entity_label="   ")
        assert _entity_label(cfg) == "Lead"


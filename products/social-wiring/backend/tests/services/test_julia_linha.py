"""julia_linha.linha_da_org: the ONE credential source of the org's WhatsApp line (julia-line CONTRACT A1)."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.services.julia_linha import LinhaAmbigua, SemLinha, linha_da_conexao, linha_da_org
from app.services.whatsapp_connection_store import WhatsAppConnectionRecord

ORG = uuid4()
AGORA = datetime.now(timezone.utc).isoformat()


def _rec(*, ativa=False, api_key=None, base="https://waha.test", session="default", org=ORG):
    return WhatsAppConnectionRecord(
        id=uuid4(), org_id=org, user_id=uuid4(), label="L", base_url=base, session_name=session, webhook_url=None,
        created_at=AGORA, updated_at=AGORA, api_key=api_key, agente_leads_ativo=ativa,
    )


class _Store:
    """The two reads the resolver makes; `list_connections` never decrypts, `get_connection(decrypt=True)` does."""

    def __init__(self, rows):
        self.rows = rows
        self.asked_org: list = []

    def list_connections(self, *, org_id, marca_id=None):
        self.asked_org.append(org_id)
        return [r for r in self.rows if r.org_id == org_id]

    def get_connection(self, *, connection_id, org_id, decrypt=False):
        for r in self.rows:
            if r.id == connection_id and r.org_id == org_id:
                return WhatsAppConnectionRecord(**{**r.__dict__, "api_key": "segredo" if decrypt else None})
        return None


def test_the_only_row_is_the_line_with_a_decrypted_key():
    store = _Store([_rec()])
    linha = linha_da_org(ORG, store=store)
    assert linha.base_url == "https://waha.test"
    assert linha.api_key == "segredo"
    assert linha.session == "default"
    assert linha.org_id == ORG


def test_no_row_is_the_named_sem_linha():
    with pytest.raises(SemLinha) as exc:
        linha_da_org(ORG, store=_Store([]))
    assert exc.value.motivo == "sem_linha"


def test_another_orgs_line_is_never_used():
    outra = _rec(org=uuid4())
    with pytest.raises(SemLinha):
        linha_da_org(ORG, store=_Store([outra]))


def test_several_rows_pick_the_julia_active_one():
    ativa = _rec(ativa=True, base="https://ativa.test")
    linha = linha_da_org(ORG, store=_Store([_rec(), ativa]))
    assert linha.connection_id == ativa.id


def test_several_rows_and_none_active_is_ambiguous_not_a_guess():
    with pytest.raises(LinhaAmbigua) as exc:
        linha_da_org(ORG, store=_Store([_rec(), _rec()]))
    assert exc.value.motivo == "linha_ambigua"


def test_waha_client_is_bound_to_the_line_through_the_factory_seam():
    seen = {}

    def factory(**kw):
        seen.update(kw)
        return "cliente"

    assert linha_da_org(ORG, store=_Store([_rec(session="s1")])).waha_client(factory) == "cliente"
    assert seen == {"base_url": "https://waha.test", "api_key": "segredo", "session": "s1"}


def test_linha_da_conexao_wraps_a_resolved_record():
    rec = _rec(api_key="k")
    assert linha_da_conexao(rec).api_key == "k"

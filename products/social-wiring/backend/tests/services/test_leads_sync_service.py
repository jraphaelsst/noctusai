"""Tests for ``LeadsSyncService`` — Meta Lead-Ads ingest (migration 033).

Coverage:
  - ``sync_all`` upserts forms (with schema) + leads, promoting
    name/email/phone by the owning form question's TYPE (not its key)
  - the variable long tail — including hidden fields NOT in the form's
    question list (e.g. ``REF``) — lands in ``answers``, lossless
  - the ``leads_retrieval`` gate is SURFACED (records_gated=True, records
    skipped) rather than failing the run — forms still sync
"""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from noctusai_lib.integrations.meta import (
    FacebookPage,
    FakeMetaAdapter,
    Lead,
    LeadFieldEntry,
    LeadgenForm,
    LeadgenQuestion,
    MetaGraphError,
)

from app.modules.meta_ads.services.leads_sync_service import LeadsSyncService

ORG = uuid4()


# ─── recording admin client (captures upserted rows per table) ──────────
class _RecTable:
    def __init__(self, sink: list[dict]) -> None:
        self._sink = sink
        self._payload: dict | None = None

    def upsert(self, payload, *, on_conflict="", **_k):
        self._payload = dict(payload)
        return self

    def execute(self):
        self._sink.append(self._payload)
        return SimpleNamespace(data=[self._payload])


class _RecAdmin:
    def __init__(self) -> None:
        self.rows: dict[str, list[dict]] = {}

    def schema(self, _name: str) -> "_RecAdmin":
        return self

    def table(self, name: str) -> _RecTable:
        return _RecTable(self.rows.setdefault(name, []))


def _adapter() -> FakeMetaAdapter:
    a = FakeMetaAdapter()
    a.seed(
        pages=[FacebookPage(id="P1", name="One", access_token="PTOK")],
        leadgen_forms_by_page={
            "P1": [
                LeadgenForm(
                    id="f1", name="Form A", status="ACTIVE",
                    leads_count=1, page_id="P1",
                    questions=[
                        # NOTE: keys are PT labels — promotion must key on TYPE.
                        LeadgenQuestion(key="Nome completo", type="FULL_NAME"),
                        LeadgenQuestion(key="Email", type="EMAIL"),
                        LeadgenQuestion(key="Telefone", type="PHONE"),
                        LeadgenQuestion(key="Faixa", type="CUSTOM",
                                        options=[{"key": "a", "value": "Até R$700 Mil"}]),
                    ],
                ),
            ]
        },
        leads_by_form={
            "f1": [
                Lead(
                    id="l1", form_id="f1", campaign_name="C10023",
                    platform="ig", is_organic=False,
                    field_data=[
                        LeadFieldEntry(name="Nome completo", values=["Maria Silva"]),
                        LeadFieldEntry(name="Email", values=["m@e.com"]),
                        LeadFieldEntry(name="Telefone", values=["+5511999"]),
                        LeadFieldEntry(name="Faixa", values=["Até R$700 Mil"]),
                        # hidden tracking field — NOT a form question:
                        LeadFieldEntry(name="REF", values=["ONE10023"]),
                    ],
                ),
            ]
        },
    )
    return a


def test_sync_all_promotes_contacts_and_keeps_full_answers():
    admin = _RecAdmin()
    svc = LeadsSyncService(admin_supabase=admin)
    res = svc.sync_all(org_id=ORG, adapter=_adapter())

    assert res == {"forms_upserted": 1, "leads_upserted": 1, "records_gated": False}

    form = admin.rows["meta_ads_lead_forms"][0]
    assert form["id"] == "f1"
    assert [q["type"] for q in form["questions"]] == ["FULL_NAME", "EMAIL", "PHONE", "CUSTOM"]

    lead = admin.rows["meta_ads_leads"][0]
    # promoted by TYPE even though the keys are PT labels:
    assert lead["full_name"] == "Maria Silva"
    assert lead["email"] == "m@e.com"
    assert lead["phone"] == "+5511999"
    # every field (incl. the hidden REF) is in the lossless answers tail:
    assert lead["answers"]["Faixa"] == "Até R$700 Mil"
    assert lead["answers"]["REF"] == "ONE10023"
    assert lead["campaign_name"] == "C10023"
    assert lead["is_organic"] is False


def test_records_gate_is_surfaced_not_fatal():
    class _Gated(FakeMetaAdapter):
        def list_leads(self, *_a, **_k):
            raise MetaGraphError("(#200) Requires leads_retrieval permission", code=200)

    a = _Gated()
    a.seed(
        pages=[FacebookPage(id="P1", name="One", access_token="PTOK")],
        leadgen_forms_by_page={
            "P1": [LeadgenForm(id="f1", status="ACTIVE", leads_count=5, page_id="P1")]
        },
    )
    admin = _RecAdmin()
    res = LeadsSyncService(admin_supabase=admin).sync_all(org_id=ORG, adapter=a)

    assert res["forms_upserted"] == 1        # forms still synced
    assert res["leads_upserted"] == 0
    assert res["records_gated"] is True
    assert admin.rows.get("meta_ads_leads", []) == []  # no records written


def test_multivalue_answer_kept_as_list():
    a = FakeMetaAdapter()
    a.seed(
        pages=[FacebookPage(id="P1", name="One", access_token="PTOK")],
        leadgen_forms_by_page={
            "P1": [LeadgenForm(id="f1", status="ACTIVE", leads_count=1, page_id="P1",
                               questions=[LeadgenQuestion(key="multi", type="CUSTOM")])]
        },
        leads_by_form={
            "f1": [Lead(id="l1", form_id="f1", field_data=[
                LeadFieldEntry(name="multi", values=["a", "b"])])]
        },
    )
    admin = _RecAdmin()
    LeadsSyncService(admin_supabase=admin).sync_all(org_id=ORG, adapter=a)
    assert admin.rows["meta_ads_leads"][0]["answers"]["multi"] == ["a", "b"]

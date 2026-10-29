"""`LeadStage.tag` on every stage payload, and the generic `on_stage_entered` hook (both stores)."""
from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest

from noctusai_lib.domain.leads import LeadsConfig, LeadsService, LeadStage

from .conftest import CFG, CONN, ORG_A, build_harness


def test_tag_defaults_to_label_and_rides_on_config_and_board(store):
    cfg = replace(CFG, stages=[LeadStage("lead", "Lead", "destructive", "Lead"), LeadStage("atendimento", "Atendimento", "warning", "Em atendimento"),
                               LeadStage("negociacao", "Negociação", "warning", "Em atendimento"), LeadStage("fechado", "Fechado")])
    assert [s.as_dict()["tag"] for s in cfg.stages] == ["Lead", "Em atendimento", "Em atendimento", "Fechado"]
    svc = LeadsService(store, cfg)
    svc.create(ORG_A, {"name": "x"})
    board = svc.board(ORG_A)
    assert [c["stage"]["tag"] for c in board] == ["Lead", "Em atendimento", "Em atendimento", "Fechado"]
    assert cfg.as_dict()["stages"][1] == {"slug": "atendimento", "label": "Atendimento", "color": "warning", "tag": "Em atendimento"}


def test_config_route_carries_tag(store):
    h = build_harness(store)
    assert all("tag" in s for s in h.client.get("/api/leads/config", headers=h.a()).json()["data"]["stages"])


def test_blank_tag_is_refused():
    with pytest.raises(ValueError):
        LeadStage("lead", "Lead", None, "  ")


class Recorder:
    def __init__(self, fail_on=None):
        self.calls: list[tuple[str, str, str]] = []
        self.fail_on = fail_on

    def __call__(self, org_id, lead, stage):
        self.calls.append((org_id, lead["id"], stage))
        if stage == self.fail_on:
            raise RuntimeError("conversion down")


def _svc(store, hook) -> LeadsService:
    return LeadsService(store, replace(CFG, on_stage_entered=hook))


def test_hook_fires_only_when_a_stage_is_entered(store):
    rec = Recorder()
    svc = _svc(store, rec)
    lead = svc.create(ORG_A, {"name": "Ana"})
    svc.update(ORG_A, lead["id"], {"notes": "x"})                 # no stage change: no call
    svc.update(ORG_A, lead["id"], {"stage": "atendimento"})
    svc.update(ORG_A, lead["id"], {"stage": "atendimento"})       # same stage: no call
    svc.move(ORG_A, lead["id"], "fechado", 0)
    svc.move(ORG_A, lead["id"], "fechado", 0)                     # reorder inside the column: no call
    assert [c[2] for c in rec.calls] == ["lead", "atendimento", "fechado"]
    assert all(c[0] == ORG_A and c[1] == lead["id"] for c in rec.calls)


def test_hook_fires_for_whatsapp_born_leads_once(store):
    rec = Recorder()
    svc = _svc(store, rec)
    chat = {"chat_id": "5511900000000@c.us", "name": "Bia", "phone": "5511900000000"}
    asyncio.run(svc.upsert_from_whatsapp(ORG_A, CONN, chat))
    asyncio.run(svc.upsert_from_whatsapp(ORG_A, CONN, chat))
    assert [c[2] for c in rec.calls] == ["lead"]


def test_hook_failure_is_surfaced_and_never_rolls_the_move_back(store, caplog):
    svc = _svc(store, Recorder(fail_on="fechado"))
    lead = svc.create(ORG_A, {"name": "Ana"})
    moved = svc.move(ORG_A, lead["id"], "fechado", 0)
    assert moved["stage"] == "fechado" and moved["stage_hook_error"] == "RuntimeError: conversion down"
    assert svc.get(ORG_A, lead["id"])["stage"] == "fechado"
    assert any("on_stage_entered hook failed" in r.message for r in caplog.records)


def test_no_hook_is_a_noop(store):
    svc = LeadsService(store, LeadsConfig(stages=["a", "b"], origins=["whatsapp", "outro"]))
    lead = svc.create(ORG_A, {"name": "Ana"})
    assert "stage_hook_error" not in svc.move(ORG_A, lead["id"], "b", 0)

"""Tests for `clientes_service.py` — the identity-resolution backfill,
merge/undo, and the read surface Slice B's routers will call.

`MockSupabaseClient.schema(name)` returns a BRAND NEW wrapper with an
empty per-table cache on every call (`app/modules/leads/deps.py`'s
documented finding) — so every test here scopes ONCE
(`MockSupabaseClient().schema("social_wiring")`) and passes that SAME
scoped instance to every service call, exactly like production DI would
via a cached `get_clientes_client()` (not yet built — Slice B's job).
"""
from __future__ import annotations

from uuid import uuid4

import pytest

from app.services import clientes_service as svc
from noctusai_lib.testing import MockSupabaseClient

ORG = "00000000-0000-4000-8000-000000000001"


def _scoped_client() -> MockSupabaseClient:
    return MockSupabaseClient().schema("social_wiring")


def _lead(id_, nome, key, tipo="telefone", data="2026-01-01"):
    return {
        "id": id_,
        "org_id": ORG,
        "cliente_nome": nome,
        "contato_norm": key,
        "contato_tipo": tipo if key else "desconhecido",
        "data_entrada": data,
    }


def _meta_lead(id_, nome, phone=None, email=None, created_time="2026-01-01T00:00:00+00:00"):
    return {
        "id": id_,
        "org_id": ORG,
        "full_name": nome,
        "phone": phone,
        "email": email,
        "created_time": created_time,
    }


def _atendimento(id_, *, lead_id=None, meta_ads_lead_id=None):
    return {
        "id": id_,
        "org_id": ORG,
        "lead_id": lead_id,
        "meta_ads_lead_id": meta_ads_lead_id,
        "cliente_id": None,
    }


K1, K2, K3, K4, K5, K6 = (
    "+5511900000001", "+5511900000002", "+5511900000003",
    "+5511900000004", "+5511900000005", "+5511900000006",
)

LEADS = [
    _lead("L1", "Ana Silva", K1, data="2026-01-01"),
    _lead("L2", "ana silva", K1, data="2026-01-02"),
    _lead("L3", "Maria Silva", K2, data="2026-02-01"),
    _lead("L4", "Maria", K2, data="2026-02-02"),
    _lead("L5", "Maria Silva", K3, data="2026-03-01"),
    _lead("L6", "Maria Souza", K3, data="2026-03-02"),
    _lead("L7", "Carmen Real Dias", K4, data="2026-04-01"),
    _lead("L8", "Luana Batista", K4, data="2026-04-02"),
    _lead("L9", "Ana", K5, data="2026-05-01"),
    _lead("L10", "Bob", K5, data="2026-05-02"),
    _lead("L11", "Carla", K5, data="2026-05-03"),
    _lead("L12", None, None, data="2026-06-01"),
]
META_LEADS = [
    _meta_lead("M1", "ANA SILVA", phone=K1, created_time="2026-01-03T00:00:00+00:00"),
    _meta_lead("M2", "Nova Pessoa", phone=K6, created_time="2026-07-01T00:00:00+00:00"),
]
NEGOCIACOES = [
    _atendimento("N1", lead_id="L1"),   # Group A (K1, C1) -> survivor cliente
    _atendimento("N2", meta_ads_lead_id="M2"),  # Group G (K6, C1)
    _atendimento("N3", lead_id="L3"),   # Group B (K2, C2) -> the SURVIVOR's own row
    _atendimento("N4", lead_id="L5"),   # Group C (K3, C4, review) -> a review cliente
]


def _seed_full_fixture() -> MockSupabaseClient:
    client = _scoped_client()
    client.set_table_data("leads", [dict(r) for r in LEADS])
    client.set_table_data("meta_ads_leads", [dict(r) for r in META_LEADS])
    client.set_table_data("atendimentos", [dict(r) for r in NEGOCIACOES])
    return client


def _clientes(client) -> list[dict]:
    return client.table("clientes").select("*").execute().data or []


def _touches(client) -> list[dict]:
    return client.table("cliente_touches").select("*").execute().data or []


def _merges(client) -> list[dict]:
    return client.table("cliente_merges").select("*").execute().data or []


class TestClienteGetsItsContactData:
    """🔴 The reported production bug, both halves.

    The backfill wrote only the identity KEY, never `celular`/`email`. So the
    person's card showed "—" beside a lead whose phone was on the board, and
    `stage_gate` refused every move because the checklist had nothing to tick.
    Worst for a KEYLESS cliente, which by definition has no key to fall back
    on — and those are exactly the leads an operator wants to pick up.
    """

    def test_keyed_cliente_gets_celular(self):
        client = _scoped_client()
        client.set_table_data("leads", [_lead("L1", "Ana Silva", K1)])
        client.set_table_data("meta_ads_leads", [])
        client.set_table_data("atendimentos", [])

        svc.run_backfill(client, ORG)

        [cliente] = _clientes(client)
        assert cliente["celular"] == K1

    def test_keyless_cliente_still_gets_its_phone(self):
        """José Roberto: a real phone the operator typed, no canonical key.
        Before this, his cliente row was blank in every column."""
        client = _scoped_client()
        client.set_table_data("leads", [{
            "id": "L1", "org_id": ORG, "cliente_nome": "José Roberto",
            "contato": "+5511999978888", "contato_norm": None,
            "contato_tipo": "telefone", "data_entrada": "2026-09-02",
        }])
        client.set_table_data("meta_ads_leads", [])
        client.set_table_data("atendimentos", [])

        svc.run_backfill(client, ORG)

        [cliente] = _clientes(client)
        assert cliente["chave_canonica"] is None, "still keyless"
        assert cliente["celular"] == "+5511999978888"

    def test_campaign_cliente_gets_both_phone_and_email(self):
        """Ana Lima: the phone won the key, so the email used to be dropped."""
        client = _scoped_client()
        client.set_table_data("leads", [])
        client.set_table_data("meta_ads_leads", [
            _meta_lead("M1", "Ana Lima", phone=K1, email="Analu@Gmail.com"),
        ])
        client.set_table_data("atendimentos", [])

        svc.run_backfill(client, ORG)

        [cliente] = _clientes(client)
        assert cliente["celular"] == K1
        assert cliente["email"] == "analu@gmail.com"

    def test_editing_the_lead_reaches_the_person_on_the_next_pass(self):
        """🔴 The production race, end to end.

        A lead created empty produces a nameless, keyless cliente. The
        operator completes the lead 27 minutes later. Clustering is one-shot
        per source — the touch is already written, so the row is skipped
        forever after — which used to mean the correction NEVER reached the
        person and the card stayed unworkable.
        """
        client = _scoped_client()
        vazio = {
            "id": "L1", "org_id": ORG, "cliente_nome": None,
            "contato": None, "contato_norm": None, "contato_tipo": None,
            "data_entrada": "2026-09-02",
        }
        client.set_table_data("leads", [dict(vazio)])
        client.set_table_data("meta_ads_leads", [])
        client.set_table_data("atendimentos", [])
        svc.run_backfill(client, ORG)

        [antes] = _clientes(client)
        assert not antes.get("nome") and not antes.get("celular"), (
            "precondition: the cliente is born blank from a blank lead"
        )

        # The operator completes the lead.
        client.table("leads").update({
            "cliente_nome": "José Roberto",
            "contato": "+5511999978888",
            "contato_norm": "+5511999978888",
            "contato_tipo": "telefone",
        }).eq("id", "L1").execute()

        svc.run_backfill(client, ORG)

        [depois] = _clientes(client)
        assert depois["id"] == antes["id"], "same person, not a second cliente"
        assert depois["nome"] == "José Roberto"
        assert depois["celular"] == "+5511999978888"

    def test_a_later_touch_fills_a_blank_but_never_overwrites(self):
        """Fill-if-empty. An operator-typed value outranks anything derived
        from a lead row, so a later touch must not replace it."""
        client = _scoped_client()
        client.set_table_data("leads", [_lead("L1", "Ana Silva", K1)])
        client.set_table_data("meta_ads_leads", [])
        client.set_table_data("atendimentos", [])
        svc.run_backfill(client, ORG)
        [cliente] = _clientes(client)

        # The operator corrects the number by hand...
        client.table("clientes").update(
            {"celular": "+5511911112222"}
        ).eq("id", cliente["id"]).execute()

        # ...then a second campaign touch for the same person arrives.
        client.set_table_data("meta_ads_leads", [
            _meta_lead("M9", "Ana Silva", phone=K1, email="ana@example.com"),
        ])
        svc.run_backfill(client, ORG)

        [cliente] = _clientes(client)
        assert cliente["celular"] == "+5511911112222", "hand-typed value survives"
        assert cliente["email"] == "ana@example.com", "the blank one is filled"


# ─── run_backfill — the full C1-C6 + keyless + repoint scenario ─────────


class TestRunBackfillFullFixture:
    def test_report_counts(self):
        client = _seed_full_fixture()
        report = svc.run_backfill(client, ORG)

        assert report.leads_scanned == 12
        assert report.meta_leads_scanned == 2
        assert report.keyless_clientes == 1
        assert report.groups_total == 6
        assert report.counts_by_motivo == {
            "C1": 2, "C2": 1, "C3": 0, "C4": 1, "C5": 1, "C6": 1,
        }
        assert report.auto_merge_groups == 3
        assert report.review_groups == 3
        assert report.clientes_created == 11
        assert report.touches_created == 14
        assert report.touches_expected == 14
        assert report.merges_created == 1

    def test_touch_count_arithmetic(self):
        """§4 P1.2: count(cliente_touches) == count(leads) + count(meta_ads_leads)."""
        client = _seed_full_fixture()
        svc.run_backfill(client, ORG)
        assert len(_touches(client)) == 14

    def test_no_source_row_is_modified(self):
        client = _seed_full_fixture()
        before_leads = client.table("leads").select("*").execute().data
        before_meta = client.table("meta_ads_leads").select("*").execute().data
        svc.run_backfill(client, ORG)
        after_leads = client.table("leads").select("*").execute().data
        after_meta = client.table("meta_ads_leads").select("*").execute().data
        assert before_leads == after_leads
        assert before_meta == after_meta

    def test_every_source_row_has_exactly_one_touch(self):
        client = _seed_full_fixture()
        svc.run_backfill(client, ORG)
        keys = {(t["origem_tabela"], t["origem_id"]) for t in _touches(client)}
        expected = {("leads", r["id"]) for r in LEADS} | {
            ("meta_ads_leads", r["id"]) for r in META_LEADS
        }
        assert keys == expected
        assert len(_touches(client)) == len(expected)  # no duplicates

    def test_at_most_one_cliente_per_real_key(self):
        """The UNIQUE (org_id, chave_canonica) invariant, checked at the
        service-logic level (the mock does not enforce SQL constraints)."""
        client = _seed_full_fixture()
        svc.run_backfill(client, ORG)
        keys = [c["chave_canonica"] for c in _clientes(client) if c["chave_canonica"]]
        assert len(keys) == len(set(keys))
        assert set(keys) == {K1, K2, K6}

    def test_review_clientes_never_claim_a_key(self):
        client = _seed_full_fixture()
        svc.run_backfill(client, ORG)
        review = [c for c in _clientes(client) if c["identidade_incerta"]]
        assert len(review) == 8  # 1 keyless + 2(C4) + 2(C5) + 3(C6)
        assert all(c["chave_canonica"] is None for c in review)
        assert all(c["chave_tipo"] is None for c in review)

    def test_c1_group_adopts_the_longest_first_encountered_name(self):
        client = _seed_full_fixture()
        svc.run_backfill(client, ORG)
        [k1_cliente] = [c for c in _clientes(client) if c["chave_canonica"] == K1]
        assert k1_cliente["nome"] == "Ana Silva"
        assert k1_cliente["identidade_incerta"] is False

    def test_c2_group_merges_and_records_it(self):
        client = _seed_full_fixture()
        svc.run_backfill(client, ORG)
        [survivor] = [c for c in _clientes(client) if c["chave_canonica"] == K2]
        assert survivor["nome"] == "Maria Silva"  # the longer name wins

        merges = _merges(client)
        assert len(merges) == 1
        m = merges[0]
        assert m["cliente_id_sobrevivente"] == survivor["id"]
        assert m["motivo"] == "C2"
        assert m["automatico"] is True
        assert m["nome_absorvido"] == "Maria"
        assert m["chave_canonica_absorvido"] == K2
        assert m["touches_movidos"] == [{"origem_tabela": "leads", "origem_id": "L4"}]

        # L4's touch physically points at the survivor, not a phantom row.
        [l4_touch] = [t for t in _touches(client) if t["origem_id"] == "L4"]
        assert l4_touch["cliente_id"] == survivor["id"]

    def test_c5_shared_phone_never_auto_merges(self):
        """Carmen Real Dias / Luana Batista — the roadmap's canonical
        shared-household-phone example."""
        client = _seed_full_fixture()
        svc.run_backfill(client, ORG)
        touches = [t for t in _touches(client) if t["chave_canonica"] == K4]
        cliente_ids = {t["cliente_id"] for t in touches}
        assert len(cliente_ids) == 2  # two distinct clientes, never folded
        names = {c["nome"] for c in _clientes(client) if c["id"] in cliente_ids}
        assert names == {"Carmen Real Dias", "Luana Batista"}

    def test_keyless_lead_gets_its_own_incerta_cliente(self):
        client = _seed_full_fixture()
        svc.run_backfill(client, ORG)
        [l12_touch] = [t for t in _touches(client) if t["origem_id"] == "L12"]
        [cliente] = [c for c in _clientes(client) if c["id"] == l12_touch["cliente_id"]]
        assert cliente["chave_canonica"] is None
        assert cliente["identidade_incerta"] is True

    def test_atendimentos_repointed_with_zero_orphans(self):
        client = _seed_full_fixture()
        report = svc.run_backfill(client, ORG)
        assert report.atendimentos_orphaned == []
        assert report.atendimentos_repointed == 4
        assert report.atendimentos_already_pointed == 0

        rows = client.table("atendimentos").select("*").execute().data
        assert all(r["cliente_id"] is not None for r in rows)

    def test_atendimento_on_a_merged_row_resolves_through_the_moved_touch(self):
        client = _seed_full_fixture()
        svc.run_backfill(client, ORG)
        [survivor] = [c for c in _clientes(client) if c["chave_canonica"] == K2]
        [n3] = [r for r in client.table("atendimentos").select("*").execute().data if r["id"] == "N3"]
        assert n3["cliente_id"] == survivor["id"]


# ─── dry-run — read-only, no prerequisite table needed ──────────────────


class TestRunBackfillDryRun:
    def test_dry_run_writes_nothing(self):
        client = _seed_full_fixture()
        report = svc.run_backfill(client, ORG, dry_run=True)

        assert report.clientes_created == 11
        assert report.touches_created == 14
        assert report.merges_created == 1
        # No clientes/cliente_touches/cliente_merges/atendimentos writes.
        assert _clientes(client) == []
        assert _touches(client) == []
        assert _merges(client) == []
        rows = client.table("atendimentos").select("*").execute().data
        assert all(r["cliente_id"] is None for r in rows)

    def test_dry_run_never_reads_cliente_touches(self):
        """Proves a dry-run can run BEFORE 048 is even applied — it must
        never assume `cliente_touches` exists."""
        client = _scoped_client()
        client.set_table_data("leads", [_lead("L1", "Solo", K1)])
        client.set_table_data("meta_ads_leads", [])
        # No set_table_data for cliente_touches/clientes/cliente_merges/
        # atendimentos at all — a read attempt would 500 for real.
        report = svc.run_backfill(client, ORG, dry_run=True)
        assert report.leads_scanned == 1
        assert report.clientes_created == 1


# ─── idempotency ──────────────────────────────────────────────────────────


class TestIdempotency:
    def test_rerun_on_unchanged_data_is_a_no_op(self):
        client = _seed_full_fixture()
        svc.run_backfill(client, ORG)
        clientes_before = len(_clientes(client))
        touches_before = len(_touches(client))

        second = svc.run_backfill(client, ORG)

        assert second.groups_total == 0
        assert second.keyless_clientes == 0
        assert second.clientes_created == 0
        assert second.touches_created == 0
        assert second.merges_created == 0
        assert second.atendimentos_repointed == 0
        assert second.atendimentos_already_pointed == 4
        assert len(_clientes(client)) == clientes_before
        assert len(_touches(client)) == touches_before

    def test_straggler_with_matching_name_attaches_to_existing_cliente(self):
        client = _scoped_client()
        client.set_table_data("leads", [_lead("L1", "Solo Pessoa", K1)])
        client.set_table_data("meta_ads_leads", [])
        client.set_table_data("atendimentos", [])
        first = svc.run_backfill(client, ORG)
        assert first.clientes_created == 1
        [cliente] = _clientes(client)

        client.set_table_data(
            "leads",
            [_lead("L1", "Solo Pessoa", K1), _lead("L2", "Solo Pessoa", K1, data="2026-01-10")],
        )
        second = svc.run_backfill(client, ORG)

        assert second.groups_reconciled == 1
        assert second.clientes_created == 0
        assert second.stragglers_parked_for_review == 0
        assert second.touches_created == 1
        assert len(_clientes(client)) == 1
        [l2_touch] = [t for t in _touches(client) if t["origem_id"] == "L2"]
        assert l2_touch["cliente_id"] == cliente["id"]
        # span extends to the straggler's date.
        [refreshed] = _clientes(client)
        assert refreshed["ultimo_contato_em"] == "2026-01-10"

    def test_straggler_with_conflicting_name_is_parked_for_review(self):
        client = _scoped_client()
        client.set_table_data("leads", [_lead("L1", "Solo Pessoa", K1)])
        client.set_table_data("meta_ads_leads", [])
        client.set_table_data("atendimentos", [])
        svc.run_backfill(client, ORG)

        client.set_table_data(
            "leads",
            [_lead("L1", "Solo Pessoa", K1), _lead("L2", "Zeca Pagodinho", K1)],
        )
        second = svc.run_backfill(client, ORG)

        assert second.groups_reconciled == 1
        assert second.stragglers_parked_for_review == 1
        assert second.clientes_created == 1

        clientes = _clientes(client)
        assert len(clientes) == 2
        new_ones = [c for c in clientes if c["nome"] == "Zeca Pagodinho"]
        assert len(new_ones) == 1
        assert new_ones[0]["identidade_incerta"] is True
        assert new_ones[0]["chave_canonica"] is None
        # the original survivor still holds the real key, untouched.
        original = [c for c in clientes if c["nome"] == "Solo Pessoa"][0]
        assert original["chave_canonica"] == K1

    def test_nameless_straggler_attaches_when_exactly_one_existing_cliente(self):
        client = _scoped_client()
        client.set_table_data("leads", [_lead("L1", "Solo Pessoa", K1)])
        client.set_table_data("meta_ads_leads", [])
        client.set_table_data("atendimentos", [])
        svc.run_backfill(client, ORG)
        [cliente] = _clientes(client)

        client.set_table_data(
            "leads", [_lead("L1", "Solo Pessoa", K1), _lead("L2", None, K1)]
        )
        second = svc.run_backfill(client, ORG)

        assert second.stragglers_parked_for_review == 0
        assert len(_clientes(client)) == 1
        [l2_touch] = [t for t in _touches(client) if t["origem_id"] == "L2"]
        assert l2_touch["cliente_id"] == cliente["id"]


# ─── D16 reactivation-on-touch — `_reactivate_if_inactive` ──────────────
#
# roadmap `project-history/roadmaps/lead-card-hub-2026-08.md` D16. A fresh
# touch attaching to a cliente the inactivity sweep
# (`clientes_inactivity_service.py`) had previously put to sleep must flip
# it back to `ativo=true` — leaving it hidden after a genuine new inquiry
# would be the exact same silent-disappearance failure the sweep exists to
# prevent, just inverted. This exercises the SAME reconciliation path
# `TestStragglerReconciliation` above does (`_attach_touches`, reached
# through a second `run_backfill` pass once an identity is already
# resolved) — reactivation is a side effect bolted onto that existing path,
# not a new one.


class TestReactivationOnTouch:
    def test_new_touch_reactivates_a_swept_inactive_cliente(self):
        client = _scoped_client()
        client.set_table_data("leads", [_lead("L1", "Solo Pessoa", K1)])
        client.set_table_data("meta_ads_leads", [])
        client.set_table_data("atendimentos", [])
        first = svc.run_backfill(client, ORG)
        assert first.clientes_reactivated == 0
        [cliente] = _clientes(client)

        # Simulate the inactivity sweep having put this cliente to sleep.
        client.table("clientes").update({
            "ativo": False,
            "inativo_em": "2026-06-01T00:00:00+00:00",
            "inativo_threshold_dias": 180,
        }).eq("id", cliente["id"]).execute()
        [asleep] = _clientes(client)
        assert asleep["ativo"] is False

        # A NEW touch under the same key lands.
        client.set_table_data(
            "leads",
            [
                _lead("L1", "Solo Pessoa", K1),
                _lead("L2", "Solo Pessoa", K1, data="2026-07-01"),
            ],
        )
        second = svc.run_backfill(client, ORG)

        assert second.clientes_reactivated == 1
        [refreshed] = _clientes(client)
        assert refreshed["ativo"] is True
        assert refreshed["inativo_em"] is None
        assert refreshed["inativo_threshold_dias"] is None
        assert refreshed["reativado_em"] is not None

    def test_a_manually_archived_cliente_is_never_reactivated_by_a_touch(self):
        """The test that must fail without the `arquivado_em` guard: a
        naive version of `_reactivate_if_inactive` that only checks
        `ativo` would resurrect a cliente a human deliberately archived.
        Verified failing first by temporarily dropping the
        `current.get("arquivado_em") is not None` check — see the
        delivery note."""
        client = _scoped_client()
        client.set_table_data("leads", [_lead("L1", "Solo Pessoa", K1)])
        client.set_table_data("meta_ads_leads", [])
        client.set_table_data("atendimentos", [])
        svc.run_backfill(client, ORG)
        [cliente] = _clientes(client)

        # A HUMAN archived this one — deliberate, terminal, not the sweep.
        client.table("clientes").update({
            "ativo": False,
            "arquivado_em": "2026-06-01T00:00:00+00:00",
        }).eq("id", cliente["id"]).execute()

        client.set_table_data(
            "leads",
            [
                _lead("L1", "Solo Pessoa", K1),
                _lead("L2", "Solo Pessoa", K1, data="2026-07-01"),
            ],
        )
        second = svc.run_backfill(client, ORG)

        assert second.clientes_reactivated == 0
        [refreshed] = _clientes(client)
        assert refreshed["ativo"] is False
        assert refreshed["arquivado_em"] == "2026-06-01T00:00:00+00:00"
        assert refreshed.get("reativado_em") is None

    def test_an_already_active_cliente_is_left_alone(self):
        """The common case (no sweep ever touched this cliente) must not
        set `reativado_em` at all — that field means something specific
        ("this row was reactivated"), not "a touch landed"."""
        client = _scoped_client()
        client.set_table_data("leads", [_lead("L1", "Solo Pessoa", K1)])
        client.set_table_data("meta_ads_leads", [])
        client.set_table_data("atendimentos", [])
        svc.run_backfill(client, ORG)

        client.set_table_data(
            "leads",
            [
                _lead("L1", "Solo Pessoa", K1),
                _lead("L2", "Solo Pessoa", K1, data="2026-07-01"),
            ],
        )
        second = svc.run_backfill(client, ORG)

        assert second.clientes_reactivated == 0
        [refreshed] = _clientes(client)
        assert refreshed.get("reativado_em") is None


# ─── P1.4 completion — collapse duplicate negociações sharing a cliente ────
#
# The board defect (roadmap `project-history/roadmaps/lead-card-hub-2026-08.
# md` §1): a Meta lead fires BOTH `spawn_funil_card_on_lead` (via
# `ingest_meta_lead` writing `leads`) AND `spawn_funil_card_on_meta_lead`
# (writing `meta_ads_leads` directly), so one human's `leads` row and
# `meta_ads_leads` row resolve to the SAME cliente (048's backfill) and each
# spawn their own `atendimentos` card. `_collapse_atendimentos` mirrors
# migration `054`'s SQL survivor rule exactly — tested directly here since
# it is the whole of the new behaviour and going through the full
# `run_backfill` identity-resolution machinery would only add noise.


class TestCollapseNegociacoes:
    _STAGES = [
        {"id": "st-novo", "org_id": ORG, "pipeline": "funil", "posicao": 0},
        {"id": "st-proposta", "org_id": ORG, "pipeline": "funil", "posicao": 3},
        {"id": "st-fechado", "org_id": ORG, "pipeline": "funil", "posicao": 5},
    ]

    def _client(self, atendimentos: list[dict]) -> MockSupabaseClient:
        client = _scoped_client()
        client.set_table_data("pipeline_stages", [dict(s) for s in self._STAGES])
        client.set_table_data("atendimentos", [dict(n) for n in atendimentos])
        return client

    def _atendimento(self, id_, *, cliente_id, etapa="st-novo", status="aberta",
                     created_at="2026-01-01T00:00:00Z", substituida_por=None):
        return {
            "id": id_, "org_id": ORG, "cliente_id": cliente_id, "etapa_id": etapa,
            "status": status, "created_at": created_at,
            "substituida_por": substituida_por, "colapsada_em": None,
        }

    def _run(self, client) -> svc.BackfillReport:
        report = svc.BackfillReport(org_id=ORG, dry_run=False)
        svc._collapse_atendimentos(client, ORG, report)
        return report

    def _rows_by_id(self, client) -> dict[str, dict]:
        rows = client.table("atendimentos").select("*").execute().data
        return {r["id"]: r for r in rows}

    def test_furthest_advanced_stage_wins(self):
        client = self._client([
            self._atendimento("n1", cliente_id="c1", etapa="st-novo",
                              created_at="2026-01-01T00:00:00Z"),
            self._atendimento("n2", cliente_id="c1", etapa="st-proposta",
                              created_at="2026-01-02T00:00:00Z"),
        ])
        report = self._run(client)
        assert report.atendimentos_collapsed == 1
        rows = self._rows_by_id(client)
        assert rows["n2"]["substituida_por"] is None
        assert rows["n1"]["substituida_por"] == "n2"
        assert rows["n1"]["colapsada_em"] is not None

    def test_an_open_atendimento_is_never_hidden_behind_a_closed_one(self):
        """The exact risk `054`'s header calls out: a `perdida` negociação
        that reached a further stage before closing must not outrank a
        currently-`aberta` one — `obter_funil` only ever shows `aberta`
        cards, so losing this tie would make the open deal vanish from the
        board entirely, which is worse than the duplicate being fixed."""
        client = self._client([
            self._atendimento("n_closed", cliente_id="c1", etapa="st-fechado",
                              status="perdida", created_at="2026-01-01T00:00:00Z"),
            self._atendimento("n_open", cliente_id="c1", etapa="st-novo",
                              status="aberta", created_at="2026-01-02T00:00:00Z"),
        ])
        report = self._run(client)
        assert report.atendimentos_collapsed == 1
        rows = self._rows_by_id(client)
        assert rows["n_open"]["substituida_por"] is None
        assert rows["n_closed"]["substituida_por"] == "n_open"

    def test_tie_break_is_oldest_created_at_then_lower_id(self):
        client = self._client([
            self._atendimento("n_b", cliente_id="c1", created_at="2026-01-01T00:00:00Z"),
            self._atendimento("n_a", cliente_id="c1", created_at="2026-01-01T00:00:00Z"),
        ])
        self._run(client)
        rows = self._rows_by_id(client)
        assert rows["n_a"]["substituida_por"] is None
        assert rows["n_b"]["substituida_por"] == "n_a"

    def test_a_cliente_id_is_null_row_is_never_touched(self):
        """The no-silent-errors leg: a card whose identity resolution has
        not run yet (or never will, e.g. a nameless straggler) must keep
        rendering — it can never be collapsed, because collapsing requires
        a `cliente_id` to group by."""
        client = self._client([
            self._atendimento("n1", cliente_id=None),
        ])
        report = self._run(client)
        assert report.atendimentos_collapsed == 0
        assert self._rows_by_id(client)["n1"]["substituida_por"] is None

    def test_a_lone_atendimento_for_a_cliente_is_left_alone(self):
        client = self._client([self._atendimento("n1", cliente_id="c1")])
        report = self._run(client)
        assert report.atendimentos_collapsed == 0
        assert self._rows_by_id(client)["n1"]["substituida_por"] is None

    def test_idempotent_a_second_pass_on_unchanged_data_is_a_no_op(self):
        client = self._client([
            self._atendimento("n1", cliente_id="c1", etapa="st-novo",
                              created_at="2026-01-01T00:00:00Z"),
            self._atendimento("n2", cliente_id="c1", etapa="st-proposta",
                              created_at="2026-01-02T00:00:00Z"),
        ])
        self._run(client)
        second = self._run(client)
        assert second.atendimentos_collapsed == 0
        rows = self._rows_by_id(client)
        assert rows["n1"]["substituida_por"] == "n2"
        assert rows["n2"]["substituida_por"] is None

    def test_a_new_duplicate_after_a_prior_collapse_still_gets_folded(self):
        """Steady state (item 3 of the brief): a duplicate that arrives
        AFTER a prior collapse must fold too, not just the ones caught by
        the first pass — this is what makes the sweep a projection, not a
        one-shot snapshot."""
        client = self._client([
            self._atendimento("n1", cliente_id="c1", etapa="st-novo",
                              created_at="2026-01-01T00:00:00Z"),
            self._atendimento("n2", cliente_id="c1", etapa="st-proposta",
                              created_at="2026-01-02T00:00:00Z"),
        ])
        self._run(client)  # n1 folds into n2

        client.table("atendimentos").insert(
            self._atendimento("n3", cliente_id="c1", etapa="st-novo",
                              created_at="2026-01-03T00:00:00Z")
        ).execute()
        second = self._run(client)
        assert second.atendimentos_collapsed == 1
        rows = self._rows_by_id(client)
        assert rows["n2"]["substituida_por"] is None       # still the survivor
        assert rows["n3"]["substituida_por"] == "n2"
        assert rows["n1"]["substituida_por"] == "n2"        # untouched by the 2nd pass

    def test_reversible_nulling_both_columns_restores_visibility(self):
        """D3's undo bar, applied without a `cliente_merges`-shaped table:
        nothing was ever deleted, so restoring is a plain UPDATE on the
        two columns this migration added."""
        client = self._client([
            self._atendimento("n1", cliente_id="c1", etapa="st-novo",
                              created_at="2026-01-01T00:00:00Z"),
            self._atendimento("n2", cliente_id="c1", etapa="st-proposta",
                              created_at="2026-01-02T00:00:00Z"),
        ])
        self._run(client)
        client.table("atendimentos").update(
            {"substituida_por": None, "colapsada_em": None}
        ).eq("id", "n1").execute()
        assert self._rows_by_id(client)["n1"]["substituida_por"] is None

    def test_independent_clientes_never_interact(self):
        client = self._client([
            self._atendimento("n1", cliente_id="c1", etapa="st-novo",
                              created_at="2026-01-01T00:00:00Z"),
            self._atendimento("n2", cliente_id="c1", etapa="st-proposta",
                              created_at="2026-01-02T00:00:00Z"),
            self._atendimento("n3", cliente_id="c2", etapa="st-novo",
                              created_at="2026-01-01T00:00:00Z"),
        ])
        report = self._run(client)
        assert report.atendimentos_collapsed == 1
        rows = self._rows_by_id(client)
        assert rows["n3"]["substituida_por"] is None  # sole card for c2


# ─── merge / undo ─────────────────────────────────────────────────────────


class TestMergeAndUndo:
    def _seed_two_review_candidates(self, client):
        a_id, b_id = str(uuid4()), str(uuid4())
        client.set_table_data(
            "clientes",
            [
                {
                    "id": a_id, "org_id": ORG, "nome": "Carmen Real Dias",
                    "chave_canonica": None, "chave_tipo": None,
                    "identidade_incerta": True, "ativo": True,
                    "primeiro_contato_em": "2026-04-01", "ultimo_contato_em": "2026-04-01",
                },
                {
                    "id": b_id, "org_id": ORG, "nome": "Luana Batista",
                    "chave_canonica": None, "chave_tipo": None,
                    "identidade_incerta": True, "ativo": True,
                    "primeiro_contato_em": "2026-04-02", "ultimo_contato_em": "2026-04-02",
                },
            ],
        )
        client.set_table_data(
            "cliente_touches",
            [
                {
                    "id": str(uuid4()), "cliente_id": a_id, "org_id": ORG,
                    "origem_tabela": "leads", "origem_id": "L7",
                    "ocorreu_em": "2026-04-01", "nome": "Carmen Real Dias",
                    "chave_canonica": K4, "origem_label": None,
                },
                {
                    "id": str(uuid4()), "cliente_id": b_id, "org_id": ORG,
                    "origem_tabela": "leads", "origem_id": "L8",
                    "ocorreu_em": "2026-04-02", "nome": "Luana Batista",
                    "chave_canonica": K4, "origem_label": None,
                },
            ],
        )
        client.set_table_data("cliente_merges", [])
        return a_id, b_id

    def test_merge_moves_touches_and_deletes_the_absorbed_row(self):
        client = _scoped_client()
        a_id, b_id = self._seed_two_review_candidates(client)

        merge_id = svc.merge_clientes(
            client, ORG,
            cliente_id_sobrevivente=a_id, cliente_id_absorvido=b_id,
            motivo="C5", automatico=False,
        )

        remaining_ids = {c["id"] for c in _clientes(client)}
        assert remaining_ids == {a_id}
        touches = _touches(client)
        assert all(t["cliente_id"] == a_id for t in touches)
        assert len(touches) == 2

        merges = _merges(client)
        assert len(merges) == 1
        assert merges[0]["id"] == merge_id
        assert merges[0]["automatico"] is False
        assert merges[0]["nome_absorvido"] == "Luana Batista"
        assert merges[0]["touches_movidos"] == [{"origem_tabela": "leads", "origem_id": "L8"}]

    def test_undo_recreates_an_equivalent_cliente_and_moves_the_touch_back(self):
        client = _scoped_client()
        a_id, b_id = self._seed_two_review_candidates(client)
        merge_id = svc.merge_clientes(
            client, ORG,
            cliente_id_sobrevivente=a_id, cliente_id_absorvido=b_id,
            motivo="C5", automatico=False,
        )

        new_id = svc.undo_merge(client, ORG, merge_id)

        assert new_id != b_id  # a fresh id, not the original — see the migration's
                                # COMMENT ON COLUMN cliente_merges.cliente_id_absorvido
        clientes_by_id = {c["id"]: c for c in _clientes(client)}
        assert set(clientes_by_id) == {a_id, new_id}
        assert clientes_by_id[new_id]["nome"] == "Luana Batista"
        assert clientes_by_id[new_id]["identidade_incerta"] is True
        assert clientes_by_id[new_id]["chave_canonica"] is None

        [l8_touch] = [t for t in _touches(client) if t["origem_id"] == "L8"]
        assert l8_touch["cliente_id"] == new_id
        [l7_touch] = [t for t in _touches(client) if t["origem_id"] == "L7"]
        assert l7_touch["cliente_id"] == a_id

        [merge_row] = _merges(client)
        assert merge_row["desfeito_em"] is not None

    def test_undo_twice_raises(self):
        client = _scoped_client()
        a_id, b_id = self._seed_two_review_candidates(client)
        merge_id = svc.merge_clientes(
            client, ORG,
            cliente_id_sobrevivente=a_id, cliente_id_absorvido=b_id,
            motivo="C5", automatico=False,
        )
        svc.undo_merge(client, ORG, merge_id)
        with pytest.raises(svc.MergeAlreadyUndone):
            svc.undo_merge(client, ORG, merge_id)

    def test_undo_unknown_merge_raises(self):
        client = _scoped_client()
        client.set_table_data("cliente_merges", [])
        with pytest.raises(svc.MergeNotFound):
            svc.undo_merge(client, ORG, str(uuid4()))


# ─── read surface ─────────────────────────────────────────────────────────


class TestReadSurface:
    def test_list_review_groups(self):
        client = _seed_full_fixture()
        svc.run_backfill(client, ORG)

        groups = svc.list_review_groups(client, ORG)
        by_key = {g["chave_canonica"]: g for g in groups}
        assert set(by_key) == {K3, K4, K5}
        assert by_key[K3]["motivo"] == "C4"
        assert by_key[K4]["motivo"] == "C5"
        assert by_key[K5]["motivo"] == "C6"
        assert len(by_key[K5]["candidatos"]) == 3

    def test_list_review_groups_excludes_keyless_singletons(self):
        client = _seed_full_fixture()
        svc.run_backfill(client, ORG)
        groups = svc.list_review_groups(client, ORG)
        # L12's keyless cliente must never appear — it has no
        # cliente_touches.chave_canonica at all.
        keys = {g["chave_canonica"] for g in groups}
        assert None not in keys

    def test_get_cliente_and_list_and_touches(self):
        client = _seed_full_fixture()
        svc.run_backfill(client, ORG)
        [k1_cliente] = [c for c in _clientes(client) if c["chave_canonica"] == K1]

        fetched = svc.get_cliente(client, ORG, k1_cliente["id"])
        assert fetched["id"] == k1_cliente["id"]

        assert svc.get_cliente(client, ORG, str(uuid4())) is None

        board = svc.list_clientes(client, ORG, ativo=True, page=1, page_size=50)
        assert board["total"] == 11
        assert len(board["items"]) == 11

        touches = svc.get_touches(client, ORG, k1_cliente["id"], page=1, page_size=50)
        assert len(touches["items"]) == 3  # L1, L2, M1
        # `count="exact"` now reflects the `.eq("cliente_id", ...)`-filtered
        # rows, not the whole `cliente_touches` table — fixed 2026-09-16.
        assert touches["total"] == 3

    def test_update_cliente(self):
        client = _seed_full_fixture()
        svc.run_backfill(client, ORG)
        [k1_cliente] = [c for c in _clientes(client) if c["chave_canonica"] == K1]

        updated = svc.update_cliente(client, ORG, k1_cliente["id"], nome="Ana Silva Corrigida")
        assert updated["nome"] == "Ana Silva Corrigida"

        with pytest.raises(svc.ClienteNotFound):
            svc.update_cliente(client, ORG, str(uuid4()), nome="X")


class TestListClientesSearchColumns:
    """`GET /api/clientes?q=` matches `nome` OR `celular` OR `email`
    (leads-novo-lead, 2026-09-24) — used to match `nome` alone. The
    Base-de-Leads "Novo lead" cliente picker is typed a phone number ("Fer"
    finds Fernando by name; "9876" finds him by the digits an operator has
    pasted straight out of WhatsApp) at least as often as a name."""

    def _seed(self) -> MockSupabaseClient:
        client = _scoped_client()
        client.set_table_data(
            "clientes",
            [
                {
                    "id": "c1", "org_id": ORG, "nome": "Fernando Souza",
                    "celular": "+5511987654321", "email": "fernando@example.com",
                    "ativo": True, "chave_canonica": "+5511987654321",
                    "chave_tipo": "telefone", "identidade_incerta": False,
                    "ultimo_contato_em": "2026-09-01T00:00:00+00:00",
                },
                {
                    "id": "c2", "org_id": ORG, "nome": "Mariana Costa",
                    "celular": "+5511911112222", "email": "mariana@example.com",
                    "ativo": True, "chave_canonica": "+5511911112222",
                    "chave_tipo": "telefone", "identidade_incerta": False,
                    "ultimo_contato_em": "2026-09-02T00:00:00+00:00",
                },
            ],
        )
        return client

    def test_matches_by_nome(self):
        client = self._seed()
        result = svc.list_clientes(client, ORG, q="fernand")
        assert [c["id"] for c in result["items"]] == ["c1"]

    def test_matches_by_celular(self):
        client = self._seed()
        result = svc.list_clientes(client, ORG, q="87654321")
        assert [c["id"] for c in result["items"]] == ["c1"]

    def test_matches_by_email(self):
        client = self._seed()
        result = svc.list_clientes(client, ORG, q="mariana@")
        assert [c["id"] for c in result["items"]] == ["c2"]

    def test_no_match_returns_empty_not_error(self):
        client = self._seed()
        result = svc.list_clientes(client, ORG, q="zzz-nao-existe-nenhum-cliente")
        assert result == {"items": [], "total": 0, "page": 1, "pages": 1}


class TestRgIgualCpfEhAceito:
    """🔴 RG == CPF is NOT refused (2026-09-22). It used to be — the same
    eleven digits landing in both boxes, `noctusai_lib.integrations.
    documents.rg.is_same_as_cpf` exists to catch. But the new Carteira de
    Identidade Nacional (CIN) uses the CPF number AS the identity number by
    design — contract 08 (a human-typed reference) qualifies "TAUANE
    GONÇALVES DIAS ... RG 448.864.938-66-IIGDR-SP e inscrita no CPF/MF
    448.864.938-66", the same eleven digits in both, correctly. A PATCH must
    save the value; the contract-generation gate is what still surfaces the
    collision, as a warning (`contrato_gerador.derivacao._partes`)."""

    CPF = "412.954.238-98"

    def _cliente(self, cliente_id, **extra) -> dict:
        return {
            "id": cliente_id, "org_id": ORG, "nome": "Ana",
            "cpf": None, "rg": None, **extra,
        }

    def test_both_fields_in_one_payload(self):
        client = _scoped_client()
        cid = str(uuid4())
        client.set_table_data("clientes", [self._cliente(cid)])

        updated = svc.update_cliente(client, ORG, cid, cpf=self.CPF, rg=self.CPF)
        assert updated["cpf"] == self.CPF
        assert updated["rg"] == self.CPF
        assert _clientes(client)[0]["cpf"] == self.CPF
        assert _clientes(client)[0]["rg"] == self.CPF

    def test_rg_alone_against_an_existing_cpf(self):
        """Only `rg` is in THIS payload; the CIN case is only visible once
        the existing `cpf` is read off the row — and it must still save."""
        client = _scoped_client()
        cid = str(uuid4())
        client.set_table_data("clientes", [self._cliente(cid, cpf=self.CPF)])

        updated = svc.update_cliente(client, ORG, cid, rg=self.CPF)
        assert updated["rg"] == self.CPF
        assert _clientes(client)[0]["rg"] == self.CPF

    def test_cpf_alone_against_an_existing_rg(self):
        """Same shape, the other write direction."""
        client = _scoped_client()
        cid = str(uuid4())
        client.set_table_data("clientes", [self._cliente(cid, rg=self.CPF)])

        updated = svc.update_cliente(client, ORG, cid, cpf=self.CPF)
        assert updated["cpf"] == self.CPF
        assert _clientes(client)[0]["cpf"] == self.CPF

    def test_different_documents_are_also_accepted(self):
        client = _scoped_client()
        cid = str(uuid4())
        client.set_table_data("clientes", [self._cliente(cid)])

        updated = svc.update_cliente(
            client, ORG, cid, cpf=self.CPF, rg="52.179.965-X",
        )
        assert updated["cpf"] == self.CPF
        assert updated["rg"] == "52.179.965-X"

    def test_clearing_rg_back_to_none_still_works(self):
        client = _scoped_client()
        cid = str(uuid4())
        client.set_table_data("clientes", [self._cliente(cid, cpf=self.CPF)])

        updated = svc.update_cliente(client, ORG, cid, rg=None)
        assert updated["rg"] is None


class TestEdicaoManualDeCampoDocumental:
    """The owner's provenance directive (2026-09-19), quoted in this
    dispatch's brief: "humans input data, extracted from official files are
    the truth. if a robot input a data, then a human edits an extracted-
    data, human overwrites with admin confirmation and logs for history and
    rollback." A human PATCH touching a field whose CURRENT value came from
    a document must never silently overwrite it.
    """

    def _cliente_documental(self, cid, **extra) -> dict:
        return {
            "id": cid, "org_id": ORG, "nome": "Ana",
            "estado_civil": "Casado(a)", "estado_civil_origem": "certidao_casamento",
            "cpf": None, "rg": None,
            **extra,
        }

    def test_non_admin_edit_of_a_document_sourced_field_is_held_back(self):
        client = _scoped_client()
        cid = str(uuid4())
        client.set_table_data("clientes", [self._cliente_documental(cid)])

        resultado = svc.update_cliente(
            client, ORG, cid, is_admin=False, estado_civil="Solteiro(a)",
        )
        # The document's value keeps prevailing — nothing was written.
        assert resultado["estado_civil"] == "Casado(a)"
        assert resultado["pendente_confirmacao"] == ["estado_civil"]
        row = _clientes(client)[0]
        assert row["estado_civil"] == "Casado(a)"

        conflitos = client.table("cliente_campo_conflitos").select("*").execute().data
        assert len(conflitos) == 1
        c = conflitos[0]
        assert c["campo"] == "estado_civil"
        assert c["valor_anterior"] == "Casado(a)"
        assert c["origem_anterior"] == "certidao_casamento"
        assert c["valor_proposto"] == "Solteiro(a)"
        assert c["origem_proposto"] == "manual"
        assert c["status"] == "pendente"
        assert c["decidido_por"] is None

    def test_repeating_the_same_pending_edit_does_not_duplicate_the_conflict(self):
        client = _scoped_client()
        cid = str(uuid4())
        client.set_table_data("clientes", [self._cliente_documental(cid)])

        svc.update_cliente(client, ORG, cid, is_admin=False, estado_civil="Solteiro(a)")
        svc.update_cliente(client, ORG, cid, is_admin=False, estado_civil="Divorciado(a)")

        conflitos = client.table("cliente_campo_conflitos").select("*").execute().data
        assert len(conflitos) == 1

    def test_admin_edit_applies_immediately_and_logs_the_previous_value(self):
        client = _scoped_client()
        cid = str(uuid4())
        client.set_table_data("clientes", [self._cliente_documental(cid)])
        admin_id = str(uuid4())

        resultado = svc.update_cliente(
            client, ORG, cid,
            is_admin=True, acting_user_id=admin_id,
            estado_civil="Solteiro(a)",
        )
        assert resultado["estado_civil"] == "Solteiro(a)"
        assert resultado["pendente_confirmacao"] == []
        row = _clientes(client)[0]
        assert row["estado_civil"] == "Solteiro(a)"
        assert row["estado_civil_origem"] == "manual"

        conflitos = client.table("cliente_campo_conflitos").select("*").execute().data
        assert len(conflitos) == 1
        c = conflitos[0]
        assert c["status"] == "aceito"
        assert c["valor_anterior"] == "Casado(a)"
        assert c["origem_anterior"] == "certidao_casamento"
        assert c["valor_proposto"] == "Solteiro(a)"
        assert c["decidido_por"] == admin_id
        assert c["decidido_em"] is not None

    def test_an_empty_or_manual_origin_value_is_never_gated(self):
        """Bullet 1's other half: nothing to protect when the current value
        is empty, or already the server's own manual stamp."""
        client = _scoped_client()
        cid = str(uuid4())
        client.set_table_data(
            "clientes",
            [self._cliente_documental(cid, estado_civil=None, estado_civil_origem=None)],
        )
        resultado = svc.update_cliente(
            client, ORG, cid, is_admin=False, estado_civil="Casado(a)",
        )
        assert resultado["estado_civil"] == "Casado(a)"
        assert resultado["pendente_confirmacao"] == []
        assert not client.table("cliente_campo_conflitos").select("*").execute().data

        cid2 = str(uuid4())
        client.set_table_data(
            "clientes",
            [self._cliente_documental(
                cid2, estado_civil="Casado(a)", estado_civil_origem="manual",
            )],
        )
        resultado2 = svc.update_cliente(
            client, ORG, cid2, is_admin=False, estado_civil="Divorciado(a)",
        )
        assert resultado2["estado_civil"] == "Divorciado(a)"
        assert resultado2["pendente_confirmacao"] == []

    def test_rg_orgao_expedidor_rides_with_a_deferred_rg(self):
        """The issuer belongs to the RG number — it must not apply on its
        own while the `rg` it qualifies is held back (even for a pre-153 row
        whose issuer carries no provenance of its own)."""
        client = _scoped_client()
        cid = str(uuid4())
        client.set_table_data(
            "clientes",
            [self._cliente_documental(
                cid, cpf=None, rg="12.345.678-9", rg_origem="rg",
                rg_orgao_expedidor="SSP/SP", estado_civil=None, estado_civil_origem=None,
            )],
        )
        resultado = svc.update_cliente(
            client, ORG, cid, is_admin=False,
            rg="98.765.432-1", rg_orgao_expedidor="SSP/RJ",
        )
        assert resultado["pendente_confirmacao"] == ["rg"]
        row = _clientes(client)[0]
        assert row["rg"] == "12.345.678-9"
        assert row["rg_orgao_expedidor"] == "SSP/SP"

    def test_a_field_still_applies_alongside_a_deferred_one(self):
        """A PATCH touching both a gated (deferred) field and a plain one
        must still write the plain one — the hold-back is per-field."""
        client = _scoped_client()
        cid = str(uuid4())
        client.set_table_data("clientes", [self._cliente_documental(cid)])

        resultado = svc.update_cliente(
            client, ORG, cid, is_admin=False,
            nome="Ana Maria", estado_civil="Solteiro(a)",
        )
        assert resultado["nome"] == "Ana Maria"
        assert resultado["pendente_confirmacao"] == ["estado_civil"]
        row = _clientes(client)[0]
        assert row["nome"] == "Ana Maria"
        assert row["estado_civil"] == "Casado(a)"

    def test_rg_cpf_collision_guard_uses_the_effective_post_patch_values(self):
        """`cpf` is deferred (document-sourced, non-admin); `rg` is new and
        must be validated against the CURRENT (unclaimed) `cpf`, not the
        one the request asked for and that never landed."""
        client = _scoped_client()
        cid = str(uuid4())
        client.set_table_data(
            "clientes",
            [self._cliente_documental(
                cid, cpf="412.954.238-98", cpf_origem="cpf",
                rg=None, estado_civil=None, estado_civil_origem=None,
            )],
        )
        # The new rg differs from the CURRENT cpf (412...), even though it
        # equals the (deferred, never-applied) proposed cpf — no collision.
        resultado = svc.update_cliente(
            client, ORG, cid, is_admin=False,
            cpf="052.999.999-01", rg="052.999.999-01",
        )
        assert resultado["pendente_confirmacao"] == ["cpf"]
        assert resultado["rg"] == "052.999.999-01"

    def test_nome_oficial_is_gated_the_same_way(self):
        """071's document-owned name — now human-editable (owner
        directive), on the same admin-confirmation terms as every other
        identity field."""
        client = _scoped_client()
        cid = str(uuid4())
        client.set_table_data(
            "clientes",
            [self._cliente_documental(
                cid, cpf=None, estado_civil=None, estado_civil_origem=None,
                nome_oficial="ANA DA SILVA", nome_oficial_origem="rg",
            )],
        )
        resultado = svc.update_cliente(
            client, ORG, cid, is_admin=False, nome_oficial="ANA MARIA DA SILVA",
        )
        assert resultado["nome_oficial"] == "ANA DA SILVA"
        assert resultado["pendente_confirmacao"] == ["nome_oficial"]

        admin_id = str(uuid4())
        admin_resultado = svc.update_cliente(
            client, ORG, cid, is_admin=True, acting_user_id=admin_id,
            nome_oficial="ANA MARIA DA SILVA",
        )
        assert admin_resultado["nome_oficial"] == "ANA MARIA DA SILVA"
        assert admin_resultado["pendente_confirmacao"] == []

        # The earlier pending proposal is now stale (it proposed
        # overwriting a value the admin's own edit already replaced a
        # different way) — closed, not left dangling in the admin queue.
        conflitos = client.table("cliente_campo_conflitos").select("*").execute().data
        assert len(conflitos) == 2
        superseded = [c for c in conflitos if c["status"] == "rejeitado"]
        aceito = [c for c in conflitos if c["status"] == "aceito"]
        assert len(superseded) == 1
        assert superseded[0]["valor_proposto"] == "ANA MARIA DA SILVA"
        assert superseded[0]["decidido_por"] == admin_id
        assert len(aceito) == 1
        assert aceito[0]["valor_proposto"] == "ANA MARIA DA SILVA"

    def test_admin_edit_supersedes_a_stale_pending_conflict_on_the_same_field(self):
        """🔴 The gap the owner's directive's "logs for history and
        rollback" would otherwise leave open: without this, the pending
        row from the FIRST (held-back) edit keeps sitting in the admin
        queue offering a decision about a value the admin's own edit has
        already moved past."""
        client = _scoped_client()
        cid = str(uuid4())
        client.set_table_data("clientes", [self._cliente_documental(cid)])

        svc.update_cliente(client, ORG, cid, is_admin=False, estado_civil="Solteiro(a)")
        pendente_id = client.table("cliente_campo_conflitos").select("*").execute().data[0]["id"]

        admin_id = str(uuid4())
        svc.update_cliente(
            client, ORG, cid, is_admin=True, acting_user_id=admin_id,
            estado_civil="Divorciado(a)",
        )

        conflitos = {
            c["id"]: c
            for c in client.table("cliente_campo_conflitos").select("*").execute().data
        }
        assert conflitos[pendente_id]["status"] == "rejeitado"
        assert conflitos[pendente_id]["decidido_por"] == admin_id
        novo = [c for c in conflitos.values() if c["id"] != pendente_id][0]
        assert novo["status"] == "aceito"
        assert novo["valor_proposto"] == "Divorciado(a)"


# ─── PostgREST 1 000-row cap — the bug class the shared mock cannot see ────
#
# 🔴 `MockSupabaseClient.range()` is a NO-OP (`seed/lib/backend/noctusai_lib/
# testing/mocks.py`) and the mock applies no row ceiling, so a raw
# `.select().execute()` and a paginated `_select_all()` are INDISTINGUISHABLE
# under it. That is not a small gap: it makes this entire bug class untestable
# by construction, which is why it has now shipped twice — `filter_options`
# (fixed in c5a34390) and `_repoint_atendimentos` (found live 2026-08-13, having
# repointed 1 000 of 1 365 negociações while reporting `orphaned: []`).
#
# The double below models the real ceiling: an unpaginated select truncates,
# a `.range()`d one does not. Against the pre-fix code this test FAILS.

class _CappingSelect:
    """Wraps a real mock select chain and enforces PostgREST's row cap
    unless the caller paginated with `.range()`."""

    def __init__(self, inner, cap: int):
        self._inner, self._cap, self._ranged = inner, cap, False

    def __getattr__(self, name):
        attr = getattr(self._inner, name)
        if not callable(attr):
            return attr

        def _proxy(*a, **k):
            if name == "range":
                self._ranged = True
            result = attr(*a, **k)
            return self if result is self._inner else result

        return _proxy

    def execute(self):
        resp = self._inner.execute()
        if not self._ranged and isinstance(resp.data, list) and len(resp.data) > self._cap:
            resp.data = resp.data[: self._cap]
        return resp


class _CappingClient:
    def __init__(self, inner, cap: int = 3):
        self._inner, self._cap = inner, cap

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def table(self, name):
        real = self._inner.table(name)
        original_select = real.select

        def _select(*a, **k):
            return _CappingSelect(original_select(*a, **k), self._cap)

        real.select = _select
        return real


class TestPostgrestRowCap:
    def test_repoint_paginates_past_the_row_cap(self):
        """With a cap BELOW the negociações count, an unpaginated select would
        silently see only the first `cap` rows and leave the rest NULL while
        reporting zero orphans — exactly the live 2026-08-13 failure."""
        inner = _seed_full_fixture()
        neg_count = len(inner.table("atendimentos").select("*").execute().data)
        assert neg_count > 2, "fixture must exceed the cap for this to be meaningful"

        client = _CappingClient(inner, cap=2)
        report = svc.run_backfill(client, ORG)

        assert report.atendimentos_orphaned == []
        assert report.atendimentos_repointed == neg_count, (
            f"repointed {report.atendimentos_repointed} of {neg_count} — an "
            "unpaginated select was capped and reported success anyway"
        )
        rows = inner.table("atendimentos").select("*").execute().data
        assert all(r["cliente_id"] is not None for r in rows)


# ── /clientes/revisao took production down on 2026-08-14 ──────────────────
#
# `list_review_groups` did two unbounded things at once:
#   1. `select("*")` over `clientes` — capped at 1 000, silently dropping 177
#      of the 1 177 identidade_incerta rows;
#   2. `.in_("cliente_id", ids)` with ~1 000 UUIDs — PostgREST puts `in_`
#      values in the URL QUERY STRING, so that is a ~40 KB request line. The
#      server answered a bare 400 ("JSON could not be generated") and the
#      review queue — the whole point of Phase 1 — showed an error page.
#
# These pin the batching invariant directly, because the shared mock has no
# URL-length limit and therefore cannot reproduce the 400 on its own.

class TestReviewGroupsBatching:
    def test_batched_splits_at_the_configured_size(self):
        items = list(range(450))
        batches = list(svc._batched(items, svc._IN_FILTER_BATCH))
        assert [len(b) for b in batches] == [200, 200, 50]
        assert [x for b in batches for x in b] == items, "batching must not lose or reorder ids"

    def test_in_filter_batch_keeps_the_request_line_under_8kb(self):
        """A UUID is 36 chars; PostgREST adds quoting/commas (~38 each) and
        the whole list rides in the query string. 8 KB is the common server
        request-line limit."""
        worst_case = svc._IN_FILTER_BATCH * 38
        assert worst_case < 8000, (
            f"a batch of {svc._IN_FILTER_BATCH} ids is ~{worst_case} bytes of "
            "query string — that is the 400 that took /clientes/revisao down"
        )

    def test_no_unbounded_in_filter_survives_in_the_review_path(self):
        """Structural guard: the id list must reach `in_` through `_batched`.
        A future edit that drops the loop reintroduces the outage."""
        import inspect
        src = inspect.getsource(svc.list_review_groups)
        assert "_batched(" in src, "list_review_groups must batch its in_ filter"
        assert ".in_(\"cliente_id\", ids)" not in src, (
            "the unbounded in_(ids) call is back — this is the 2026-08-14 outage"
        )


# ── attach_lead_now — synchronous per-lead attach on create ────────────────
#
# `create_lead` used to rely entirely on the (background-tasked,
# eventually-consistent) `clientes_backfill` sweep to attach
# `atendimentos.cliente_id`. `contato_norm` is already resolvable at create
# time, so this closes even the couple-of-seconds background-task window —
# see `clientes_service.attach_lead_now`'s docstring.


def _fresh_atendimento_scope(*, lead_id="L1"):
    """A brand-new lead + its migration-034-spawned card, nothing else in
    the org yet — the exact shape `create_lead` hands `attach_lead_now`."""
    client = _scoped_client()
    client.set_table_data("leads", [])
    client.set_table_data("meta_ads_leads", [])
    client.set_table_data("atendimentos", [_atendimento("N1", lead_id=lead_id)])
    return client


class TestAttachLeadNow:
    def test_keyed_lead_gets_a_cliente_and_atendimento_synchronously(self):
        client = _fresh_atendimento_scope()
        lead = _lead("L1", "Ana Silva", K1)

        cliente_id = svc.attach_lead_now(client, ORG, lead)

        assert cliente_id is not None
        [cliente] = _clientes(client)
        assert cliente["id"] == cliente_id
        assert cliente["chave_canonica"] == K1
        assert cliente["identidade_incerta"] is False
        [atendimento] = client.table("atendimentos").select("*").execute().data
        assert atendimento["cliente_id"] == cliente_id

    def test_keyed_lead_attaches_to_an_existing_cliente_for_the_same_key(self):
        """The second lead from a returning person reconciles onto the
        SAME cliente `_resolve_group` already resolved — never a second
        identity for one canonical key."""
        client = _fresh_atendimento_scope(lead_id="L1")
        first_id = svc.attach_lead_now(client, ORG, _lead("L1", "Ana Silva", K1))

        client.set_table_data(
            "atendimentos",
            client.table("atendimentos").select("*").execute().data
            + [_atendimento("N2", lead_id="L2")],
        )
        second_id = svc.attach_lead_now(client, ORG, _lead("L2", "Ana Silva", K1))

        assert second_id == first_id
        assert len(_clientes(client)) == 1
        assert len(_touches(client)) == 2

    def test_keyless_lead_still_gets_attached_not_left_unresolved(self):
        """§A's keyless case: no usable `contato_norm` must not mean 'no
        cliente' — it means an uncertain-identity cliente, exactly like
        `run_backfill`'s own keyless branch, so the card is workable."""
        client = _fresh_atendimento_scope()
        lead = {
            "id": "L1", "org_id": ORG, "cliente_nome": "Sem Telefone",
            "contato": "não informado", "contato_norm": None,
            "contato_tipo": "desconhecido", "data_entrada": "2026-09-21",
        }

        cliente_id = svc.attach_lead_now(client, ORG, lead)

        assert cliente_id is not None
        [cliente] = _clientes(client)
        assert cliente["identidade_incerta"] is True
        assert cliente["chave_canonica"] is None
        [atendimento] = client.table("atendimentos").select("*").execute().data
        assert atendimento["cliente_id"] == cliente_id

    def test_never_raises_and_leaves_the_sweep_to_reconcile(self):
        """`create_lead` must not fail because attachment did. Drives the
        real failure branch — a malformed row `identidade_service` cannot
        turn into a `SourceRow` (missing `id`) — rather than substituting a
        double for our own collaborator (no monkey-patching our own code,
        per `KB § PATTERNS/compliance/testing.md`)."""
        client = _fresh_atendimento_scope()
        malformed_lead = {"org_id": ORG, "cliente_nome": "Ana Silva", "contato_norm": K1}

        result = svc.attach_lead_now(client, ORG, malformed_lead)

        assert result is None
        assert _clientes(client) == []

    def test_run_backfill_afterwards_finds_nothing_left_to_do(self):
        """The sweep must remain correct AND idempotent once this has
        already attached the lead — a repeat pass is a clean no-op, not a
        duplicate cliente/touch."""
        client = _fresh_atendimento_scope()
        lead = _lead("L1", "Ana Silva", K1)
        svc.attach_lead_now(client, ORG, lead)
        client.set_table_data("leads", [lead])

        report = svc.run_backfill(client, ORG)

        assert report.clientes_created == 0
        assert report.touches_created == 0
        assert len(_clientes(client)) == 1
        assert len(_touches(client)) == 1

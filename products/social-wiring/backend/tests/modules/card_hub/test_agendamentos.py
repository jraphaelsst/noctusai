"""Agendamentos — many appointments per atendimento (migration 061).

THE DEFECT THIS SLICE EXISTS FOR
--------------------------------
The card could hold exactly ONE appointment: `data_inicio`/`data_entrega`/
`lembrete_minutos_antes` were columns on `clientes`, so saving a second one
overwrote the first. The user's report was precise — *"it doesnt add multiple
schedules, it replaces the last one with the nem set one. That works fine but
it's not functional to the use i imagine to it."*

`test_two_appointments_coexist` is that report, verbatim, as an assertion.

The reminder half matters just as much and is easier to get wrong: reminders
used to be found by CLIENTE, so "cancel the stale one before scheduling the
new one" would have cancelled every OTHER appointment's reminder on the same
person. `061` adds `cliente_lembretes.agendamento_id` and
`test_rescheduling_one_does_not_cancel_anothers_reminder` holds that shut.
"""
from __future__ import annotations

from uuid import uuid4

from tests.modules.card_hub.conftest import ORG_ID, cliente_row


def _auth() -> dict:
    return {"Authorization": "Bearer test-token"}


def atendimento_row(id_, cliente_id, *, substituida_por=None, arquivado=False) -> dict:
    return {
        "id": id_,
        "org_id": ORG_ID,
        "cliente_id": cliente_id,
        "lead_id": None,
        "meta_ads_lead_id": None,
        "etapa_id": None,
        "status": "aberta",
        "titulo": "Lead",
        "substituida_por": substituida_por,
        "arquivado": arquivado,
        "created_at": "2026-01-01T00:00:00+00:00",
    }


def _seed(scoped, *, atendimentos=None):
    cid = str(uuid4())
    aid = str(uuid4())
    scoped.set_table_data("clientes", [cliente_row(cid)])
    scoped.set_table_data("atendimentos", atendimentos or [atendimento_row(aid, cid)])
    scoped.set_table_data("atendimento_agendamentos", [])
    scoped.set_table_data("cliente_lembretes", [])
    return cid, aid


def _pending(scoped) -> list[dict]:
    rows = scoped.table("cliente_lembretes").select("*").execute().data
    return [r for r in rows if not r["enviado_em"] and not r["cancelado_em"]]


class TestMultiplosAgendamentos:
    def test_two_appointments_coexist(self, client, scoped):
        """🔴 THE report. If this ever fails, the overwrite bug is back."""
        cid, _aid = _seed(scoped)

        for quando in ("2026-09-01T13:00:00+00:00", "2026-09-05T18:00:00+00:00"):
            resp = client.post(
                f"/api/clientes/{cid}/agendamentos",
                json={"quando": quando, "tipo": "visita"},
                headers=_auth(),
            )
            assert resp.status_code == 201, resp.text

        items = client.get(f"/api/clientes/{cid}/agendamentos", headers=_auth()).json()["items"]
        assert len(items) == 2
        # soonest first — a list of appointments in insertion order is useless
        assert [i["quando"] for i in items] == [
            "2026-09-01T13:00:00+00:00",
            "2026-09-05T18:00:00+00:00",
        ]

    def test_carries_when_type_note_and_reminder_and_nothing_else(self, client, scoped):
        """The user's field list, exactly: "when + reminder + note + type"."""
        cid, aid = _seed(scoped)
        resp = client.post(
            f"/api/clientes/{cid}/agendamentos",
            json={
                "quando": "2026-09-01T13:00:00+00:00",
                "tipo": "reuniao",
                "nota": "Levar a planta do 32.",
                "lembrete_minutos_antes": 30,
            },
            headers=_auth(),
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["tipo"] == "reuniao"
        assert body["nota"] == "Levar a planta do 32."
        assert body["lembrete_minutos_antes"] == 30
        assert body["atendimento_id"] == aid
        assert "assignee" not in body and "responsavel" not in body

    def test_an_unknown_tipo_is_refused(self, client, scoped):
        cid, _aid = _seed(scoped)
        resp = client.post(
            f"/api/clientes/{cid}/agendamentos",
            json={"quando": "2026-09-01T13:00:00+00:00", "tipo": "churrasco"},
            headers=_auth(),
        )
        assert resp.status_code == 422


class TestOwnership:
    def test_it_belongs_to_the_atendimento_not_the_person(self, client, scoped):
        cid, aid = _seed(scoped)
        resp = client.post(
            f"/api/clientes/{cid}/agendamentos",
            json={"quando": "2026-09-01T13:00:00+00:00", "tipo": "visita"},
            headers=_auth(),
        )
        assert resp.json()["atendimento_id"] == aid

    def test_several_open_atendimentos_is_a_409_that_names_them(self, client, scoped):
        """Refuses rather than guessing. An appointment filed against the wrong
        deal renders identically on the card and is wrong in the one place D17
        says matters — the history."""
        cid = str(uuid4())
        a1, a2 = str(uuid4()), str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid)])
        scoped.set_table_data(
            "atendimentos", [atendimento_row(a1, cid), atendimento_row(a2, cid)]
        )
        scoped.set_table_data("atendimento_agendamentos", [])

        resp = client.post(
            f"/api/clientes/{cid}/agendamentos",
            json={"quando": "2026-09-01T13:00:00+00:00", "tipo": "visita"},
            headers=_auth(),
        )
        assert resp.status_code == 409, resp.text
        # The candidate ids must survive INTO the envelope — a 409 that only
        # says "ambiguous" leaves the UI nothing to ask the user about.
        assert sorted(resp.json()["error"]["details"]["atendimentos"]) == sorted([a1, a2])

    def test_an_explicit_atendimento_id_resolves_the_ambiguity(self, client, scoped):
        cid = str(uuid4())
        a1, a2 = str(uuid4()), str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid)])
        scoped.set_table_data(
            "atendimentos", [atendimento_row(a1, cid), atendimento_row(a2, cid)]
        )
        scoped.set_table_data("atendimento_agendamentos", [])
        scoped.set_table_data("cliente_lembretes", [])

        resp = client.post(
            f"/api/clientes/{cid}/agendamentos",
            json={"quando": "2026-09-01T13:00:00+00:00", "tipo": "visita", "atendimento_id": a2},
            headers=_auth(),
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["atendimento_id"] == a2


class TestLembretes:
    def test_each_appointment_materialises_its_own_reminder(self, client, scoped):
        cid, _aid = _seed(scoped)
        client.post(
            f"/api/clientes/{cid}/agendamentos",
            json={"quando": "2026-09-01T13:00:00+00:00", "tipo": "visita",
                  "lembrete_minutos_antes": 60},
            headers=_auth(),
        )
        client.post(
            f"/api/clientes/{cid}/agendamentos",
            json={"quando": "2026-09-05T18:00:00+00:00", "tipo": "ligacao",
                  "lembrete_minutos_antes": 30},
            headers=_auth(),
        )
        pending = _pending(scoped)
        assert len(pending) == 2
        assert sorted(p["dispara_em"] for p in pending) == [
            "2026-09-01T12:00:00+00:00",
            "2026-09-05T17:30:00+00:00",
        ]

    def test_rescheduling_one_does_not_cancel_anothers_reminder(self, client, scoped):
        """🔴 The overwrite bug, one layer down. Before `agendamento_id`, the
        stale-reminder cancel matched by CLIENTE and would have killed both."""
        cid, _aid = _seed(scoped)
        first = client.post(
            f"/api/clientes/{cid}/agendamentos",
            json={"quando": "2026-09-01T13:00:00+00:00", "tipo": "visita",
                  "lembrete_minutos_antes": 60},
            headers=_auth(),
        ).json()
        client.post(
            f"/api/clientes/{cid}/agendamentos",
            json={"quando": "2026-09-05T18:00:00+00:00", "tipo": "ligacao",
                  "lembrete_minutos_antes": 30},
            headers=_auth(),
        )

        client.patch(
            f"/api/clientes/{cid}/agendamentos/{first['id']}",
            json={"quando": "2026-09-02T13:00:00+00:00"},
            headers=_auth(),
        )

        pending = sorted(p["dispara_em"] for p in _pending(scoped))
        assert pending == ["2026-09-02T12:00:00+00:00", "2026-09-05T17:30:00+00:00"]

    def test_no_reminder_asked_for_means_no_row(self, client, scoped):
        """`None` ≠ `0`. Defaulting to 0 would notify on every appointment
        ever created, which is how a reminder feature gets muted."""
        cid, _aid = _seed(scoped)
        client.post(
            f"/api/clientes/{cid}/agendamentos",
            json={"quando": "2026-09-01T13:00:00+00:00", "tipo": "visita"},
            headers=_auth(),
        )
        assert _pending(scoped) == []

    def test_editing_only_the_note_leaves_the_reminder_alone(self, client, scoped):
        cid, _aid = _seed(scoped)
        created = client.post(
            f"/api/clientes/{cid}/agendamentos",
            json={"quando": "2026-09-01T13:00:00+00:00", "tipo": "visita",
                  "lembrete_minutos_antes": 60},
            headers=_auth(),
        ).json()
        before = _pending(scoped)[0]["id"]

        client.patch(
            f"/api/clientes/{cid}/agendamentos/{created['id']}",
            json={"nota": "levar contrato"},
            headers=_auth(),
        )
        after = _pending(scoped)
        assert len(after) == 1 and after[0]["id"] == before

    def test_deleting_cancels_the_reminder(self, client, scoped):
        """A notification for an appointment that no longer exists is worse
        than none — whoever it reaches cannot find out why."""
        cid, _aid = _seed(scoped)
        created = client.post(
            f"/api/clientes/{cid}/agendamentos",
            json={"quando": "2026-09-01T13:00:00+00:00", "tipo": "visita",
                  "lembrete_minutos_antes": 60},
            headers=_auth(),
        ).json()
        assert len(_pending(scoped)) == 1

        resp = client.delete(f"/api/clientes/{cid}/agendamentos/{created['id']}", headers=_auth())
        assert resp.status_code == 204
        assert _pending(scoped) == []
        assert client.get(f"/api/clientes/{cid}/agendamentos", headers=_auth()).json()["items"] == []


class TestEspelhoDoBoard:
    """`clientes.data_entrega` is now DERIVED — a cache of the soonest upcoming
    appointment, kept only so the Clientes board's due pill stays honest until
    that list query is repointed at this table. One writer, not two inputs."""

    def test_the_soonest_upcoming_appointment_is_mirrored(self, client, scoped):
        cid, _aid = _seed(scoped)
        client.post(
            f"/api/clientes/{cid}/agendamentos",
            json={"quando": "2099-09-05T18:00:00+00:00", "tipo": "visita"},
            headers=_auth(),
        )
        client.post(
            f"/api/clientes/{cid}/agendamentos",
            json={"quando": "2099-09-01T13:00:00+00:00", "tipo": "ligacao",
                  "lembrete_minutos_antes": 15},
            headers=_auth(),
        )
        row = scoped.table("clientes").select("*").execute().data[0]
        assert row["data_entrega"] == "2099-09-01T13:00:00+00:00"
        assert row["lembrete_minutos_antes"] == 15

    def test_deleting_the_next_one_promotes_the_one_after_it(self, client, scoped):
        cid, _aid = _seed(scoped)
        first = client.post(
            f"/api/clientes/{cid}/agendamentos",
            json={"quando": "2099-09-01T13:00:00+00:00", "tipo": "visita"},
            headers=_auth(),
        ).json()
        client.post(
            f"/api/clientes/{cid}/agendamentos",
            json={"quando": "2099-09-05T18:00:00+00:00", "tipo": "reuniao"},
            headers=_auth(),
        )
        client.delete(f"/api/clientes/{cid}/agendamentos/{first['id']}", headers=_auth())

        row = scoped.table("clientes").select("*").execute().data[0]
        assert row["data_entrega"] == "2099-09-05T18:00:00+00:00"

    def test_a_past_appointment_does_not_light_the_pill(self, client, scoped):
        """The pill answers "what is coming up", so a visit that already
        happened must not sit on the board claiming to be due."""
        cid, _aid = _seed(scoped)
        client.post(
            f"/api/clientes/{cid}/agendamentos",
            json={"quando": "2020-01-01T13:00:00+00:00", "tipo": "visita"},
            headers=_auth(),
        )
        row = scoped.table("clientes").select("*").execute().data[0]
        assert row["data_entrega"] is None

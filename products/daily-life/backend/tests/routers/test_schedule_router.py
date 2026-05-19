"""Tests for the Schedule router — /api/schedule endpoints."""

SAMPLE_EVENT = {
    "id": "event-1",
    "user_id": "test-user-123",
    "org_id": "test-org-123",
    "titulo": "Reuniao de equipe",
    "descricao": "Alinhamento semanal",
    "categoria": "trabalho",
    "data_inicio": "2026-04-14T10:00:00",
    "data_fim": "2026-04-14T11:00:00",
    "dia_inteiro": False,
    "local": "Sala 3",
    "lembrete_minutos": 15,
    "cor": "#3B82F6",
    "status": "agendado",
}

SAMPLE_ALLDAY_EVENT = {
    "id": "event-2",
    "user_id": "test-user-123",
    "org_id": "test-org-123",
    "titulo": "Feriado",
    "descricao": None,
    "categoria": "pessoal",
    "data_inicio": "2026-04-21T00:00:00",
    "data_fim": None,
    "dia_inteiro": True,
    "local": None,
    "lembrete_minutos": None,
    "cor": None,
    "status": "agendado",
}
RECURRING_EVENT = {
    "id": "event-recur",
    "user_id": "test-user-123",
    "org_id": "test-org-123",
    "titulo": "Stand-up diario",
    "descricao": None,
    "categoria": "trabalho",
    "data_inicio": "2026-04-14T09:00:00",
    "data_fim": "2026-04-14T09:15:00",
    "dia_inteiro": False,
    "local": None,
    "lembrete_minutos": 5,
    "cor": None,
    "status": "agendado",
    "recorrencia": "diario",
    "recorrencia_fim": None,
}


# ---------------------------------------------------------------------------
# List events
# ---------------------------------------------------------------------------

class TestListEvents:
    def test_list_events(self, client):
        client.mock_supabase.set_table_data("eventos", [SAMPLE_EVENT, SAMPLE_ALLDAY_EVENT])
        resp = client.get("/api/schedule")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) == 2
        assert body["pagination"]["total"] == 2
        assert body["pagination"]["page"] == 1
        assert body["pagination"]["page_size"] == 50
    def test_list_events_expands_recurring(self, client):
        """REGRESSION: GET /api/schedule MUST expand recurring events.

    Pre-fix `expandir_recorrencias` was imported but never called in
    listar_eventos, so a daily recurring event returned 1 row instead
    of its in-window occurrences (dead feature; no endpoint test
    exercised expansion — that gap is why it shipped). A daily event
    over 2026-04-14..04-20 expands to 7 (mirrors
    test_schedule_service.test_expands_daily).
    """
        client.mock_supabase.set_table_data("eventos", [RECURRING_EVENT])
        resp = client.get("/api/schedule", params={
            "data_inicio": "2026-04-14T00:00:00",
            "data_fim": "2026-04-20T23:59:59",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) == 7, body["data"]
        assert sum(1 for e in body["data"] if e.get("is_recorrencia")) == 6
    def test_recurring_parent_before_window_yields_occurrences(self, client):
        """P1 (Q1): a recurring parent that STARTED before the requested
    window must still yield its in-window occurrences. Pre-P1 the
    start lower-bound `gte(data_inicio)` excluded such parents. The
    router now uses or_(gte | recorrencia.in.(...)) so the parent is
    fetched + expandir_recorrencias clips to [inicio,fim].

    Coverage boundary (honest): MockSupabase does not enforce the
    PostgREST or_ predicate (returns seeded rows); this pins the
    wiring + expansion path. The filter SEMANTIC itself is realdb-
    gated (documented in PROJECT.md §11).
    """
        parent = dict(RECURRING_EVENT)
        parent["data_inicio"] = "2026-03-01T09:00:00"  # BEFORE the window
        client.mock_supabase.set_table_data("eventos", [parent])
        resp = client.get("/api/schedule", params={
            "data_inicio": "2026-04-14T00:00:00",
            "data_fim": "2026-04-20T23:59:59",
        })
        assert resp.status_code == 200
        body = resp.json()
        occ = [e for e in body["data"] if e.get("is_recorrencia")]
        assert len(occ) >= 1, body["data"]  # in-window occurrences present
    def test_pagination_total_is_occurrence_count_for_recurring(self, client):
        """Q2 SUPERSEDED by follow-up `schedule-occurrence-pagination`
    (resolved 2026-05-19): `pagination.total` is now the TRUE expanded
    occurrence count, and pages are occurrence-pages — not parent-row
    count. A daily event over a 7-day window = 7 occurrences; at the
    default page_size they all fit one page (total == len == 7).
    """
        client.mock_supabase.set_table_data("eventos", [RECURRING_EVENT])
        resp = client.get("/api/schedule", params={
            "data_inicio": "2026-04-14T00:00:00",
            "data_fim": "2026-04-20T23:59:59",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["pagination"]["total"] == 7    # occurrence count, not parent
        assert len(body["data"]) == 7              # all fit one default page
    def test_occurrence_pagination_slices_recurring(self, client):
        """Occurrence-pagination: 7 daily occurrences, page_size=3 →
    page1=3, page2=3, page3=1; total==7 on every page; no overlap.
    Pins true expand-then-paginate (would fail under the old
    parent-paginate-then-expand model).
    """
        client.mock_supabase.set_table_data("eventos", [RECURRING_EVENT])
        q = {"data_inicio": "2026-04-14T00:00:00",
             "data_fim": "2026-04-20T23:59:59", "page_size": 3}
        seen = []
        for pg, expected in ((1, 3), (2, 3), (3, 1)):
            r = client.get("/api/schedule", params={**q, "page": pg})
            assert r.status_code == 200
            b = r.json()
            assert b["pagination"]["total"] == 7
            assert b["pagination"]["page"] == pg
            assert len(b["data"]) == expected, (pg, b["data"])
            seen += [e["data_inicio"] for e in b["data"]]
        assert len(seen) == len(set(seen)) == 7   # no overlap, full coverage

    def test_list_events_no_auth(self, client):
        resp = client.raw().get("/api/schedule")
        assert resp.status_code == 401

    def test_list_events_date_range(self, client):
        client.mock_supabase.set_table_data("eventos", [SAMPLE_EVENT])
        resp = client.get("/api/schedule", params={
            "data_inicio": "2026-04-14T00:00:00",
            "data_fim": "2026-04-14T23:59:59",
        })
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 1

    def test_list_events_filter_categoria(self, client):
        client.mock_supabase.set_table_data("eventos", [SAMPLE_EVENT])
        resp = client.get("/api/schedule", params={"categoria": "trabalho"})
        assert resp.status_code == 200
        assert resp.json()["data"][0]["categoria"] == "trabalho"

    def test_list_events_pagination(self, client):
        client.mock_supabase.set_table_data("eventos", [SAMPLE_EVENT])
        resp = client.get("/api/schedule", params={"page": 2, "page_size": 10})
        assert resp.status_code == 200
        body = resp.json()
        assert body["pagination"]["page"] == 2
        assert body["pagination"]["page_size"] == 10

    def test_list_events_empty(self, client):
        client.mock_supabase.set_table_data("eventos", [])
        resp = client.get("/api/schedule")
        assert resp.status_code == 200
        assert resp.json()["data"] == []
        assert resp.json()["pagination"]["total"] == 0


# ---------------------------------------------------------------------------
# Create event
# ---------------------------------------------------------------------------

class TestCreateEvent:
    def test_create_event(self, client):
        client.mock_supabase.set_table_data("eventos", [SAMPLE_EVENT])
        resp = client.post("/api/schedule", json={
            "titulo": "Reuniao de equipe",
            "descricao": "Alinhamento semanal",
            "categoria": "trabalho",
            "data_inicio": "2026-04-14T10:00:00",
            "data_fim": "2026-04-14T11:00:00",
            "local": "Sala 3",
            "lembrete_minutos": 15,
            "cor": "#3B82F6",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["titulo"] == "Reuniao de equipe"
        assert body["data"]["status"] == "agendado"
        assert body["data"]["lembrete_minutos"] == 15
        assert body["data"]["local"] == "Sala 3"

    def test_create_allday_event(self, client):
        client.mock_supabase.set_table_data("eventos", [SAMPLE_ALLDAY_EVENT])
        resp = client.post("/api/schedule", json={
            "titulo": "Feriado",
            "data_inicio": "2026-04-21T00:00:00",
            "dia_inteiro": True,
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["dia_inteiro"] is True

    def test_create_event_validates_titulo_empty(self, client):
        resp = client.post("/api/schedule", json={
            "titulo": "",
            "data_inicio": "2026-04-14T10:00:00",
        })
        assert resp.status_code == 422

    def test_create_event_missing_data_inicio(self, client):
        resp = client.post("/api/schedule", json={"titulo": "Test"})
        assert resp.status_code == 422

    def test_event_with_reminder(self, client):
        event_with_reminder = {**SAMPLE_EVENT, "lembrete_minutos": 30}
        client.mock_supabase.set_table_data("eventos", [event_with_reminder])
        resp = client.post("/api/schedule", json={
            "titulo": "Consulta medica",
            "data_inicio": "2026-04-15T14:00:00",
            "lembrete_minutos": 30,
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["lembrete_minutos"] == 30


# ---------------------------------------------------------------------------
# Get single event
# ---------------------------------------------------------------------------

class TestGetEvent:
    def test_get_event(self, client):
        client.mock_supabase.set_table_data("eventos", [SAMPLE_EVENT])
        resp = client.get("/api/schedule/event-1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["id"] == "event-1"
        assert body["data"]["titulo"] == "Reuniao de equipe"
        assert body["data"]["cor"] == "#3B82F6"

    def test_get_event_not_found(self, client):
        client.mock_supabase.set_table_data("eventos", [])
        resp = client.get("/api/schedule/nonexistent")
        assert resp.status_code == 404
        assert "nao encontrado" in resp.json()["error"]["message"].lower()


# ---------------------------------------------------------------------------
# Update event
# ---------------------------------------------------------------------------

class TestUpdateEvent:
    def test_update_event(self, client):
        updated = {**SAMPLE_EVENT, "titulo": "Reuniao cancelada", "status": "cancelado"}
        client.mock_supabase.set_table_data("eventos", [updated])
        resp = client.patch("/api/schedule/event-1", json={
            "titulo": "Reuniao cancelada",
            "status": "cancelado",
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "cancelado"

    def test_update_event_not_found(self, client):
        client.mock_supabase.set_table_data("eventos", [])
        resp = client.patch("/api/schedule/nonexistent", json={"titulo": "Nada"})
        assert resp.status_code == 404

    def test_update_event_no_fields(self, client):
        resp = client.patch("/api/schedule/event-1", json={})
        assert resp.status_code == 400
        assert "nenhum campo" in resp.json()["error"]["message"].lower()

    def test_update_event_invalid_status(self, client):
        resp = client.patch("/api/schedule/event-1", json={"status": "invalido"})
        assert resp.status_code == 422

    def test_update_event_datetime_fields(self, client):
        updated = {**SAMPLE_EVENT, "data_inicio": "2026-04-15T09:00:00", "data_fim": "2026-04-15T10:00:00"}
        client.mock_supabase.set_table_data("eventos", [updated])
        resp = client.patch("/api/schedule/event-1", json={
            "data_inicio": "2026-04-15T09:00:00",
            "data_fim": "2026-04-15T10:00:00",
        })
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Delete event
# ---------------------------------------------------------------------------

class TestDeleteEvent:
    def test_delete_event(self, client):
        client.mock_supabase.set_table_data("eventos", [SAMPLE_EVENT])
        resp = client.delete("/api/schedule/event-1")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert "removido" in resp.json()["message"].lower()

    def test_delete_event_not_found(self, client):
        client.mock_supabase.set_table_data("eventos", [])
        resp = client.delete("/api/schedule/nonexistent")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Recurring events
# ---------------------------------------------------------------------------

class TestRecurringEvents:
    def test_create_recurring_event(self, client):
        client.mock_supabase.set_table_data("eventos", [{
            **SAMPLE_EVENT, "recorrencia": "semanal", "recorrencia_fim": "2026-05-14"
        }])
        resp = client.post("/api/schedule", json={
            "titulo": "Weekly standup",
            "data_inicio": "2026-04-14T09:00:00",
            "recorrencia": "semanal",
            "recorrencia_fim": "2026-05-14",
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["recorrencia"] == "semanal"

    def test_create_event_default_no_recurrence(self, client):
        client.mock_supabase.set_table_data("eventos", [{**SAMPLE_EVENT, "recorrencia": "nenhuma"}])
        resp = client.post("/api/schedule", json={
            "titulo": "One-time event",
            "data_inicio": "2026-04-14T09:00:00",
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["recorrencia"] == "nenhuma"

    def test_create_invalid_recurrence(self, client):
        resp = client.post("/api/schedule", json={
            "titulo": "Bad",
            "data_inicio": "2026-04-14T09:00:00",
            "recorrencia": "cada_dois_dias",
        })
        assert resp.status_code == 422

    def test_update_recurrence(self, client):
        client.mock_supabase.set_table_data("eventos", [{**SAMPLE_EVENT, "recorrencia": "diario"}])
        resp = client.patch("/api/schedule/event-1", json={"recorrencia": "diario"})
        assert resp.status_code == 200

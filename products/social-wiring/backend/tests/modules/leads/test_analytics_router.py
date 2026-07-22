"""Analytics correctness — /api/leads/analytics/*.

- ``share_pct`` sums to ~100 across a dimension's buckets.
- ``variacao_pct`` is ``null`` (never ``0``) when the previous window has
  no data.
"""
from __future__ import annotations

from tests.modules.leads.conftest import auth_headers


def _create_lead(client, **overrides):
    body = {"data_entrada": "2026-07-01"}
    body.update(overrides)
    resp = client.post("/api/leads", json=body, headers=auth_headers())
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


class TestSummary:
    def test_comparativo_null_when_previous_window_empty(self, http_client):
        _create_lead(http_client, data_entrada="2026-07-15")
        resp = http_client.get(
            "/api/leads/analytics/summary",
            params={"de": "2026-07-01", "ate": "2026-07-31"},
            headers=auth_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["comparativo"]["total_anterior"] == 0
        assert data["comparativo"]["variacao_pct"] is None

    def test_comparativo_populated_when_previous_window_has_data(self, http_client):
        # Previous 31-day window: 2026-05-31..2026-06-30
        _create_lead(http_client, data_entrada="2026-06-15")
        _create_lead(http_client, data_entrada="2026-07-15")
        resp = http_client.get(
            "/api/leads/analytics/summary",
            params={"de": "2026-07-01", "ate": "2026-07-31"},
            headers=auth_headers(),
        )
        data = resp.json()["data"]
        assert data["comparativo"]["total_anterior"] == 1
        assert data["comparativo"]["variacao_pct"] == 0.0

    def test_no_window_no_comparativo(self, http_client):
        _create_lead(http_client)
        resp = http_client.get("/api/leads/analytics/summary", headers=auth_headers())
        assert resp.json()["data"]["comparativo"] is None

    def test_novos_retornos_counts(self, http_client):
        _create_lead(http_client, tipo_lead="novo")
        _create_lead(http_client, tipo_lead="novo")
        _create_lead(http_client, tipo_lead="retorno")
        resp = http_client.get("/api/leads/analytics/summary", headers=auth_headers())
        data = resp.json()["data"]
        assert data["total"] == 3
        assert data["novos"] == 2
        assert data["retornos"] == 1


class TestByDimension:
    def test_share_pct_sums_to_100(self, http_client):
        source_a = http_client.post(
            "/api/leads/sources", json={"slug": "a", "label": "A"}, headers=auth_headers()
        ).json()["data"]
        source_b = http_client.post(
            "/api/leads/sources", json={"slug": "b", "label": "B"}, headers=auth_headers()
        ).json()["data"]
        _create_lead(http_client, origem_id=source_a["id"])
        _create_lead(http_client, origem_id=source_a["id"])
        _create_lead(http_client, origem_id=source_a["id"])
        _create_lead(http_client, origem_id=source_b["id"])

        resp = http_client.get(
            "/api/leads/analytics/by-dimension",
            params={"dim": "origem"},
            headers=auth_headers(),
        )
        assert resp.status_code == 200
        buckets = resp.json()["data"]["buckets"]
        total_share = sum(b["share_pct"] for b in buckets)
        assert abs(total_share - 100.0) < 0.5  # rounding tolerance (1dp per bucket)

    def test_variacao_null_when_no_previous_window(self, http_client):
        source = http_client.post(
            "/api/leads/sources", json={"slug": "a", "label": "A"}, headers=auth_headers()
        ).json()["data"]
        _create_lead(http_client, origem_id=source["id"], data_entrada="2026-07-15")

        resp = http_client.get(
            "/api/leads/analytics/by-dimension",
            params={"dim": "origem", "de": "2026-07-01", "ate": "2026-07-31"},
            headers=auth_headers(),
        )
        buckets = resp.json()["data"]["buckets"]
        assert all(b["variacao_pct"] is None for b in buckets)

    def test_rest_folds_into_outros(self, http_client):
        for i in range(3):
            source = http_client.post(
                "/api/leads/sources",
                json={"slug": f"s{i}", "label": f"S{i}"},
                headers=auth_headers(),
            ).json()["data"]
            _create_lead(http_client, origem_id=source["id"])

        resp = http_client.get(
            "/api/leads/analytics/by-dimension",
            params={"dim": "origem", "limit": 1},
            headers=auth_headers(),
        )
        buckets = resp.json()["data"]["buckets"]
        assert len(buckets) == 2  # top-1 + "Outros"
        assert buckets[-1]["key"] == "outros"
        assert buckets[-1]["total"] == 2


class TestTimeseries:
    def test_default_grain_mes_and_pt_br_label(self, http_client):
        _create_lead(http_client, data_entrada="2026-07-14")
        resp = http_client.get("/api/leads/analytics/timeseries", headers=auth_headers())
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["grain"] == "mes"
        assert data["points"][0]["bucket"] == "2026-07"
        assert data["points"][0]["label"] == "Jul/26"

    def test_split_by_tipo_series_meta_order(self, http_client):
        _create_lead(http_client, tipo_lead="retorno", data_entrada="2026-07-01")
        _create_lead(http_client, tipo_lead="novo", data_entrada="2026-07-02")
        resp = http_client.get(
            "/api/leads/analytics/timeseries",
            params={"split": "tipo"},
            headers=auth_headers(),
        )
        data = resp.json()["data"]
        keys = [m["key"] for m in data["series_meta"]]
        assert keys == ["novo", "retorno"]  # fixed canonical order, not insertion order


class TestHeatmap:
    def test_blank_month_is_null_not_zero(self, http_client):
        _create_lead(http_client, data_entrada="2026-01-01")
        resp = http_client.get("/api/leads/analytics/heatmap", headers=auth_headers())
        data = resp.json()["data"]
        assert data["anos"] == [2026]
        cells = data["cells"]["2026"]
        assert cells[0] == 1  # January
        assert cells[1] is None  # February — no data, blank not zero

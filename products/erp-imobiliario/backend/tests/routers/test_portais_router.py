"""
Tests for the Portais (Portal Integration / XML Feed) router.
Covers feed listing, XML generation, portal toggle, and property listing.
"""
import pytest
from unittest.mock import patch


class TestListarFeeds:
    def test_list_feeds(self, client):
        client._mock_supabase.set_table_data("ativos", [])
        resp = client.get("/api/portais/feeds")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 3
        portals = [f["portal"] for f in data]
        assert "zap" in portals
        assert "olx" in portals
        assert "vivareal" in portals

    def test_list_feeds_has_url(self, client):
        client._mock_supabase.set_table_data("ativos", [])
        resp = client.get("/api/portais/feeds")
        assert resp.status_code == 200
        data = resp.json()["data"]
        for feed in data:
            assert "url" in feed
            assert "nome" in feed
            assert "descricao" in feed
            assert "formato" in feed


class TestGerarFeed:
    def test_gerar_feed_zap(self, client):
        client._mock_supabase.set_table_data("ativos", [
            {
                "id": "a1",
                "tipo_imovel": "apartamento",
                "titulo_anuncio": "Apto 3 quartos",
                "cidade": "SP",
                "bairro": "Jardins",
                "estado": "SP",
                "valor": 500000,
                "quartos": 3,
                "finalidade": "venda",
                "fotos": [],
            },
        ])
        with patch(
            "app.routers.portais.generate_zap_xml",
            return_value='<?xml version="1.0"?><Carga><Imoveis></Imoveis></Carga>',
        ):
            resp = client.get("/api/portais/feed/zap")
            assert resp.status_code == 200
            assert "xml" in resp.headers.get("content-type", "")

    def test_gerar_feed_olx(self, client):
        client._mock_supabase.set_table_data("ativos", [])
        with patch(
            "app.routers.portais.generate_olx_xml",
            return_value='<?xml version="1.0"?><ad:ads></ad:ads>',
        ):
            resp = client.get("/api/portais/feed/olx")
            assert resp.status_code == 200
            assert "xml" in resp.headers.get("content-type", "")

    def test_gerar_feed_vivareal(self, client):
        client._mock_supabase.set_table_data("ativos", [])
        with patch(
            "app.routers.portais.generate_vivareal_xml",
            return_value='<?xml version="1.0"?><ListingDataFeed></ListingDataFeed>',
        ):
            resp = client.get("/api/portais/feed/vivareal")
            assert resp.status_code == 200
            assert "xml" in resp.headers.get("content-type", "")

    def test_gerar_feed_invalid_portal(self, client):
        resp = client.get("/api/portais/feed/invalid-portal")
        assert resp.status_code == 400

    def test_gerar_feed_with_properties(self, client):
        from unittest.mock import MagicMock
        # Router filters `.eq("natureza", "imovel").eq("pronto_para_portais", True).eq("status", "ativo")`
        # — fixture rows must carry all three for the chained predicates to match.
        imoveis = [
            {
                "id": f"a{i}",
                "natureza": "imovel",
                "pronto_para_portais": True,
                "status": "ativo",
                "tipo_imovel": "apartamento",
                "titulo_anuncio": f"Apto {i}",
                "cidade": "SP",
                "valor": 500000 + i * 10000,
                "quartos": 3,
                "finalidade": "venda",
                "fotos": ["https://example.com/foto1.jpg"],
            }
            for i in range(3)
        ]
        client._mock_supabase.set_table_data("ativos", imoveis)
        mock_gen = MagicMock(
            return_value='<?xml version="1.0"?><Carga><Imoveis></Imoveis></Carga>'
        )
        with patch.dict(
            "app.routers.portais.PORTAL_GENERATORS",
            {"zap": mock_gen},
        ):
            resp = client.get("/api/portais/feed/zap")
            assert resp.status_code == 200
            # Verify the generator was called with the property data
            mock_gen.assert_called_once()
            assert len(mock_gen.call_args[0][0]) == 3


class TestTogglePortal:
    def test_toggle_enable(self, client):
        client._mock_supabase.set_table_data("ativos", {
            "id": "a1",
            "natureza": "imovel",
            "pronto_para_portais": True,
        })
        resp = client.patch("/api/portais/toggle/a1", json={
            "pronto_para_portais": True,
        })
        assert resp.status_code == 200

    def test_toggle_disable(self, client):
        client._mock_supabase.set_table_data("ativos", {
            "id": "a1",
            "natureza": "imovel",
            "pronto_para_portais": False,
        })
        resp = client.patch("/api/portais/toggle/a1", json={
            "pronto_para_portais": False,
        })
        assert resp.status_code == 200

    def test_toggle_not_found(self, client):
        client._mock_supabase.set_table_data("ativos", None)
        resp = client.patch("/api/portais/toggle/nonexistent", json={
            "pronto_para_portais": True,
        })
        assert resp.status_code == 404

    def test_toggle_not_imovel(self, client):
        client._mock_supabase.set_table_data("ativos", {
            "id": "a1",
            "natureza": "terreno",
        })
        resp = client.patch("/api/portais/toggle/a1", json={
            "pronto_para_portais": True,
        })
        assert resp.status_code == 400

    def test_toggle_missing_body(self, client):
        resp = client.patch("/api/portais/toggle/a1")
        assert resp.status_code == 422


class TestListarImoveisPortal:
    def test_list_all(self, client):
        client._mock_supabase.set_table_data("ativos", [
            {"id": "a1", "tipo_imovel": "apartamento", "pronto_para_portais": True},
            {"id": "a2", "tipo_imovel": "casa", "pronto_para_portais": False},
        ])
        resp = client.get("/api/portais/imoveis")
        assert resp.status_code == 200

    def test_list_filter_ready(self, client):
        client._mock_supabase.set_table_data("ativos", [
            {"id": "a1", "tipo_imovel": "apartamento", "pronto_para_portais": True},
        ])
        resp = client.get("/api/portais/imoveis?pronto_para_portais=true")
        assert resp.status_code == 200

    def test_list_filter_not_ready(self, client):
        client._mock_supabase.set_table_data("ativos", [
            {"id": "a2", "tipo_imovel": "casa", "pronto_para_portais": False},
        ])
        resp = client.get("/api/portais/imoveis?pronto_para_portais=false")
        assert resp.status_code == 200

    def test_list_pagination(self, client):
        client._mock_supabase.set_table_data("ativos", [])
        resp = client.get("/api/portais/imoveis?page=1&page_size=10")
        assert resp.status_code == 200

    def test_list_empty(self, client):
        client._mock_supabase.set_table_data("ativos", [])
        resp = client.get("/api/portais/imoveis")
        assert resp.status_code == 200

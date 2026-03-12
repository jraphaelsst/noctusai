"""
Unit tests for xml_feeds — ZAP, OLX, VivaReal XML feed generation.
"""
import pytest
from xml.etree.ElementTree import fromstring


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sample_imovel(**overrides):
    """Return a minimal property dict with sensible defaults."""
    base = {
        "id": "imv-1",
        "tipo_imovel": "apartamento",
        "finalidade": "venda",
        "titulo_anuncio": "Apartamento Centro",
        "descricao_seo": "Lindo apartamento no centro",
        "observacoes": "",
        "valor": 500000,
        "cep": "80000-000",
        "logradouro": "Rua XV de Novembro",
        "numero": "100",
        "complemento": "Apt 501",
        "bairro": "Centro",
        "cidade": "Curitiba",
        "estado": "PR",
        "latitude": None,
        "longitude": None,
        "quartos": 3,
        "suites": 1,
        "banheiros": 2,
        "vagas": 2,
        "area_total": 120,
        "area_privativa": 95,
        "iptu": 1500,
        "condominio": 800,
        "andar": 5,
        "ano_construcao": 2018,
        "condominio_nome": "Ed. Central",
        "fotos": ["https://img.test/1.jpg", "https://img.test/2.jpg", "https://img.test/3.jpg"],
        "tour_virtual_url": "https://tour.test/abc",
        "natureza": "imovel",
        "status": "ativo",
    }
    base.update(overrides)
    return base


def _parse_xml(xml_str):
    """Parse XML string, stripping the processing instruction."""
    # Remove the XML declaration if present for simpler parsing
    return fromstring(xml_str.split("?>", 1)[-1].strip())


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

class TestSafeText:

    def test_none_returns_empty(self):
        from app.services.xml_feeds import _safe_text
        assert _safe_text(None) == ""

    def test_strips_whitespace(self):
        from app.services.xml_feeds import _safe_text
        assert _safe_text("  hello  ") == "hello"

    def test_numeric_converted(self):
        from app.services.xml_feeds import _safe_text
        assert _safe_text(42) == "42"


class TestBuildAddress:

    def test_full_address(self):
        from app.services.xml_feeds import _build_address
        imovel = {
            "logradouro": "Rua A", "numero": "100",
            "complemento": "Apt 1", "bairro": "Centro",
            "cidade": "SP", "estado": "SP",
        }
        addr = _build_address(imovel)
        assert "Rua A, 100" in addr
        assert "Apt 1" in addr
        assert "Centro" in addr
        assert "SP - SP" in addr

    def test_empty_returns_default(self):
        from app.services.xml_feeds import _build_address
        addr = _build_address({})
        assert addr == "Endereco nao informado"


class TestGetTipoLabel:

    def test_known_types(self):
        from app.services.xml_feeds import _get_tipo_label
        assert _get_tipo_label("casa") == "Casa"
        assert _get_tipo_label("apartamento") == "Apartamento"
        assert _get_tipo_label("terreno") == "Terreno"

    def test_unknown_type_fallback(self):
        from app.services.xml_feeds import _get_tipo_label
        assert _get_tipo_label("desconhecido") == "Imovel"


# ---------------------------------------------------------------------------
# ZAP XML
# ---------------------------------------------------------------------------

class TestGenerateZapXml:

    def test_xml_declaration(self):
        from app.services.xml_feeds import generate_zap_xml
        xml = generate_zap_xml([_sample_imovel()])
        assert xml.startswith('<?xml version="1.0" encoding="UTF-8"?>')

    def test_root_element(self):
        from app.services.xml_feeds import generate_zap_xml
        xml = generate_zap_xml([_sample_imovel()])
        root = _parse_xml(xml)
        assert root.tag == "Carga"

    def test_imovel_children(self):
        from app.services.xml_feeds import generate_zap_xml
        xml = generate_zap_xml([_sample_imovel()])
        root = _parse_xml(xml)
        imoveis_elem = root.find("Imoveis")
        assert imoveis_elem is not None
        items = imoveis_elem.findall("Imovel")
        assert len(items) == 1

    def test_property_fields(self):
        from app.services.xml_feeds import generate_zap_xml
        xml = generate_zap_xml([_sample_imovel()])
        root = _parse_xml(xml)
        item = root.find(".//Imovel")
        assert item.findtext("CodigoImovel") == "imv-1"
        assert item.findtext("TipoImovel") == "Apartamento"
        assert item.findtext("QtdDormitorios") == "3"
        assert item.findtext("QtdSuites") == "1"

    def test_empty_list_produces_valid_xml(self):
        from app.services.xml_feeds import generate_zap_xml
        xml = generate_zap_xml([])
        root = _parse_xml(xml)
        assert root.tag == "Carga"
        imoveis_elem = root.find("Imoveis")
        assert imoveis_elem is not None
        assert len(imoveis_elem.findall("Imovel")) == 0

    def test_fotos_elements(self):
        from app.services.xml_feeds import generate_zap_xml
        xml = generate_zap_xml([_sample_imovel()])
        root = _parse_xml(xml)
        fotos = root.findall(".//Fotos/Foto")
        assert len(fotos) == 3
        # First photo should be principal
        assert fotos[0].findtext("Principal") == "Sim"
        assert fotos[1].findtext("Principal") == "Nao"

    def test_no_fotos_no_element(self):
        from app.services.xml_feeds import generate_zap_xml
        xml = generate_zap_xml([_sample_imovel(fotos=[])])
        root = _parse_xml(xml)
        assert root.find(".//Fotos") is None


# ---------------------------------------------------------------------------
# OLX XML
# ---------------------------------------------------------------------------

class TestGenerateOlxXml:

    def test_root_element(self):
        from app.services.xml_feeds import generate_olx_xml
        xml = generate_olx_xml([_sample_imovel()])
        root = _parse_xml(xml)
        # Tag may include namespace
        assert "ads" in root.tag

    def test_ad_element_present(self):
        from app.services.xml_feeds import generate_olx_xml
        xml = generate_olx_xml([_sample_imovel()])
        # The namespace makes findall tricky; just check string presence
        assert "<ad:id>imv-1</ad:id>" in xml

    def test_location_block(self):
        from app.services.xml_feeds import generate_olx_xml
        xml = generate_olx_xml([_sample_imovel()])
        assert "<ad:city>Curitiba</ad:city>" in xml
        assert "<ad:state>PR</ad:state>" in xml

    def test_empty_list(self):
        from app.services.xml_feeds import generate_olx_xml
        xml = generate_olx_xml([])
        assert '<?xml version="1.0" encoding="UTF-8"?>' in xml


# ---------------------------------------------------------------------------
# VivaReal XML
# ---------------------------------------------------------------------------

class TestGenerateVivarealXml:

    def test_root_element(self):
        from app.services.xml_feeds import generate_vivareal_xml
        xml = generate_vivareal_xml([_sample_imovel()])
        root = _parse_xml(xml)
        assert "ListingDataFeed" in root.tag

    def test_header_present(self):
        from app.services.xml_feeds import generate_vivareal_xml
        xml = generate_vivareal_xml([_sample_imovel()])
        assert "ERP Imobiliario" in xml

    def test_transaction_type_venda(self):
        from app.services.xml_feeds import generate_vivareal_xml
        xml = generate_vivareal_xml([_sample_imovel(finalidade="venda")])
        root = _parse_xml(xml)
        # Namespace-aware find
        ns = {"vr": "http://www.vivareal.com/schemas/1.0/VRSync"}
        listing = root.find(".//vr:Listings/vr:Listing", ns)
        trans = listing.findtext("vr:TransactionType", namespaces=ns)
        assert trans == "For Sale"

    def test_transaction_type_aluguel(self):
        from app.services.xml_feeds import generate_vivareal_xml
        xml = generate_vivareal_xml([_sample_imovel(finalidade="aluguel")])
        assert "For Rent" in xml

    def test_country_brasil(self):
        from app.services.xml_feeds import generate_vivareal_xml
        xml = generate_vivareal_xml([_sample_imovel()])
        assert "Brasil" in xml

    def test_multiple_imoveis(self):
        from app.services.xml_feeds import generate_vivareal_xml
        imoveis = [
            _sample_imovel(id="imv-1"),
            _sample_imovel(id="imv-2"),
        ]
        xml = generate_vivareal_xml(imoveis)
        assert "imv-1" in xml
        assert "imv-2" in xml

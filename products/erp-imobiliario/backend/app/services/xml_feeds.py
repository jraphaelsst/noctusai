"""
XML Feeds Service — Generate property feed XML for real estate portals.

Generates XML feeds in the required format for:
- ZAP Imoveis
- OLX
- VivaReal

Each portal has specific field requirements and XML structure.
"""
import logging
from typing import Dict, List
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom.minidom import parseString

logger = logging.getLogger(__name__)


def _safe_text(value) -> str:
    """Convert a value to a safe XML text string."""
    if value is None:
        return ""
    return str(value).strip()


def _add_element(parent: Element, tag: str, text=None) -> Element:
    """Add a child element with optional text content."""
    elem = SubElement(parent, tag)
    if text is not None:
        elem.text = _safe_text(text)
    return elem


def _build_address(imovel: Dict) -> str:
    """Build a formatted address string from property fields."""
    parts = []
    if imovel.get("logradouro"):
        addr = imovel["logradouro"]
        if imovel.get("numero"):
            addr += f", {imovel['numero']}"
        parts.append(addr)
    if imovel.get("complemento"):
        parts.append(imovel["complemento"])
    if imovel.get("bairro"):
        parts.append(imovel["bairro"])
    if imovel.get("cidade"):
        city = imovel["cidade"]
        if imovel.get("estado"):
            city += f" - {imovel['estado']}"
        parts.append(city)
    return ", ".join(parts) if parts else "Endereco nao informado"


def _get_tipo_label(tipo_imovel: str) -> str:
    """Map internal property type to portal-friendly label."""
    mapping = {
        "casa": "Casa",
        "apartamento": "Apartamento",
        "terreno": "Terreno",
        "comercial": "Comercial",
        "rural": "Rural",
        "outro": "Outro",
    }
    return mapping.get(tipo_imovel, "Imovel")


def _get_finalidade_label(finalidade: str) -> str:
    """Map internal purpose to portal-friendly label."""
    mapping = {
        "venda": "Venda",
        "aluguel": "Aluguel",
    }
    return mapping.get(finalidade, "Venda")


def generate_zap_xml(imoveis: List[Dict]) -> str:
    """
    Generate XML feed in ZAP Imoveis format.

    ZAP uses a specific schema with <Imoveis> root and <Imovel> children,
    including detailed location, features, and media information.

    Args:
        imoveis: List of property dicts from the ativos table

    Returns:
        XML string in ZAP format
    """
    root = Element("Carga")
    root.set("xmlns:xsi", "http://www.w3.org/2001/XMLSchema-instance")

    imoveis_elem = _add_element(root, "Imoveis")

    for imovel in imoveis:
        item = _add_element(imoveis_elem, "Imovel")

        _add_element(item, "CodigoImovel", imovel.get("id", ""))
        _add_element(item, "TipoImovel", _get_tipo_label(imovel.get("tipo_imovel", "")))
        _add_element(item, "SubTipoImovel", imovel.get("tipo_imovel", ""))
        _add_element(item, "CategoriaImovel", _get_finalidade_label(imovel.get("finalidade", "venda")))
        _add_element(item, "TituloAnuncio", imovel.get("titulo_anuncio", ""))
        _add_element(item, "Observacao", imovel.get("descricao_seo") or imovel.get("observacoes", ""))

        # Location
        _add_element(item, "CEP", imovel.get("cep", ""))
        _add_element(item, "Logradouro", imovel.get("logradouro", ""))
        _add_element(item, "Numero", imovel.get("numero", ""))
        _add_element(item, "Complemento", imovel.get("complemento", ""))
        _add_element(item, "Bairro", imovel.get("bairro", ""))
        _add_element(item, "Cidade", imovel.get("cidade", ""))
        _add_element(item, "UF", imovel.get("estado", ""))

        if imovel.get("latitude") and imovel.get("longitude"):
            _add_element(item, "Latitude", imovel.get("latitude"))
            _add_element(item, "Longitude", imovel.get("longitude"))

        # Pricing
        _add_element(item, "PrecoVenda", imovel.get("valor", 0))
        if imovel.get("iptu"):
            _add_element(item, "PrecoIPTU", imovel["iptu"])
        if imovel.get("condominio"):
            _add_element(item, "PrecoCondominio", imovel["condominio"])

        # Features
        _add_element(item, "AreaUtil", imovel.get("area_privativa", ""))
        _add_element(item, "AreaTotal", imovel.get("area_total", ""))
        _add_element(item, "QtdDormitorios", imovel.get("quartos", 0))
        _add_element(item, "QtdSuites", imovel.get("suites", 0))
        _add_element(item, "QtdBanheiros", imovel.get("banheiros", 0))
        _add_element(item, "QtdVagas", imovel.get("vagas", 0))

        if imovel.get("andar"):
            _add_element(item, "Andar", imovel["andar"])
        if imovel.get("ano_construcao"):
            _add_element(item, "AnoConstrucao", imovel["ano_construcao"])

        # Condominium name
        if imovel.get("condominio_nome"):
            _add_element(item, "NomeCondominio", imovel["condominio_nome"])

        # Photos
        fotos = imovel.get("fotos") or []
        if fotos:
            fotos_elem = _add_element(item, "Fotos")
            for i, foto_url in enumerate(fotos):
                foto = _add_element(fotos_elem, "Foto")
                _add_element(foto, "URLArquivo", foto_url)
                _add_element(foto, "NomeArquivo", f"foto_{i + 1}")
                _add_element(foto, "Principal", "Sim" if i == 0 else "Nao")

        # Virtual tour
        if imovel.get("tour_virtual_url"):
            _add_element(item, "LinkTourVirtual", imovel["tour_virtual_url"])

    return _prettify(root)


def generate_olx_xml(imoveis: List[Dict]) -> str:
    """
    Generate XML feed in OLX format.

    OLX uses a simpler XML schema with <ad:ads> root and <ad:ad> children.

    Args:
        imoveis: List of property dicts from the ativos table

    Returns:
        XML string in OLX format
    """
    root = Element("ad:ads")
    root.set("xmlns:ad", "http://www.olx.com.br/ad_schema")

    for imovel in imoveis:
        ad = _add_element(root, "ad:ad")

        _add_element(ad, "ad:id", imovel.get("id", ""))
        _add_element(ad, "ad:title",
                     imovel.get("titulo_anuncio") or
                     f"{_get_tipo_label(imovel.get('tipo_imovel', ''))} em {imovel.get('cidade', 'N/A')}")
        _add_element(ad, "ad:description",
                     imovel.get("descricao_seo") or imovel.get("observacoes", ""))

        # Category
        _add_element(ad, "ad:category", _get_tipo_label(imovel.get("tipo_imovel", "")))

        # Price
        _add_element(ad, "ad:price", imovel.get("valor", 0))

        # Location
        location = _add_element(ad, "ad:location")
        _add_element(location, "ad:address", _build_address(imovel))
        _add_element(location, "ad:zipcode", imovel.get("cep", ""))
        _add_element(location, "ad:neighborhood", imovel.get("bairro", ""))
        _add_element(location, "ad:city", imovel.get("cidade", ""))
        _add_element(location, "ad:state", imovel.get("estado", ""))

        if imovel.get("latitude") and imovel.get("longitude"):
            _add_element(location, "ad:latitude", imovel.get("latitude"))
            _add_element(location, "ad:longitude", imovel.get("longitude"))

        # Details
        details = _add_element(ad, "ad:details")
        _add_element(details, "ad:rooms", imovel.get("quartos", 0))
        _add_element(details, "ad:suites", imovel.get("suites", 0))
        _add_element(details, "ad:bathrooms", imovel.get("banheiros", 0))
        _add_element(details, "ad:parking_spaces", imovel.get("vagas", 0))
        _add_element(details, "ad:size", imovel.get("area_total") or imovel.get("area_privativa", ""))
        _add_element(details, "ad:property_type", _get_tipo_label(imovel.get("tipo_imovel", "")))
        _add_element(details, "ad:transaction_type",
                     _get_finalidade_label(imovel.get("finalidade", "venda")))

        # Images
        fotos = imovel.get("fotos") or []
        if fotos:
            images = _add_element(ad, "ad:images")
            for foto_url in fotos:
                _add_element(images, "ad:image", foto_url)

    return _prettify(root)


def generate_vivareal_xml(imoveis: List[Dict]) -> str:
    """
    Generate XML feed in VivaReal format.

    VivaReal uses a ListingDataFeed schema similar to ZAP but with
    its own field naming conventions.

    Args:
        imoveis: List of property dicts from the ativos table

    Returns:
        XML string in VivaReal format
    """
    root = Element("ListingDataFeed")
    root.set("xmlns", "http://www.vivareal.com/schemas/1.0/VRSync")

    header = _add_element(root, "Header")
    _add_element(header, "Provider", "ERP Imobiliario")
    _add_element(header, "ContactEmail", "contato@erp-imobiliario.com.br")

    listings = _add_element(root, "Listings")

    for imovel in imoveis:
        listing = _add_element(listings, "Listing")

        _add_element(listing, "ListingID", imovel.get("id", ""))
        _add_element(listing, "Title",
                     imovel.get("titulo_anuncio") or
                     f"{_get_tipo_label(imovel.get('tipo_imovel', ''))} em {imovel.get('cidade', 'N/A')}")
        _add_element(listing, "TransactionType",
                     "For Sale" if imovel.get("finalidade") == "venda" else "For Rent")
        _add_element(listing, "DetailViewUrl", "")

        # Location
        location = _add_element(listing, "Location")
        _add_element(location, "Country", "Brasil")
        _add_element(location, "State", imovel.get("estado", ""))
        _add_element(location, "City", imovel.get("cidade", ""))
        _add_element(location, "Neighborhood", imovel.get("bairro", ""))
        _add_element(location, "Address", _build_address(imovel))
        _add_element(location, "PostalCode", imovel.get("cep", ""))

        if imovel.get("latitude") and imovel.get("longitude"):
            geo = _add_element(location, "GeoLocation")
            _add_element(geo, "Latitude", imovel.get("latitude"))
            _add_element(geo, "Longitude", imovel.get("longitude"))

        # Details
        details = _add_element(listing, "Details")
        _add_element(details, "PropertyType", _get_tipo_label(imovel.get("tipo_imovel", "")))
        _add_element(details, "Description",
                     imovel.get("descricao_seo") or imovel.get("observacoes", ""))
        _add_element(details, "ListPrice", imovel.get("valor", 0))

        if imovel.get("iptu"):
            _add_element(details, "PropertyTax", imovel["iptu"])

        _add_element(details, "LivingArea",
                     imovel.get("area_privativa") or imovel.get("area_total", ""))
        _add_element(details, "LotArea", imovel.get("area_total", ""))
        _add_element(details, "Bedrooms", imovel.get("quartos", 0))
        _add_element(details, "Suites", imovel.get("suites", 0))
        _add_element(details, "Bathrooms", imovel.get("banheiros", 0))
        _add_element(details, "Garage", imovel.get("vagas", 0))

        if imovel.get("ano_construcao"):
            _add_element(details, "YearBuilt", imovel["ano_construcao"])

        if imovel.get("condominio_nome"):
            _add_element(details, "CondominiumName", imovel["condominio_nome"])

        # Media
        fotos = imovel.get("fotos") or []
        if fotos:
            media = _add_element(listing, "Media")
            for i, foto_url in enumerate(fotos):
                item = _add_element(media, "Item")
                item.set("medium", "image")
                item.set("caption", f"Foto {i + 1}")
                item.text = _safe_text(foto_url)

        if imovel.get("tour_virtual_url"):
            if not fotos:
                media = _add_element(listing, "Media")
            tour = _add_element(media, "Item")
            tour.set("medium", "virtual_tour")
            tour.text = _safe_text(imovel["tour_virtual_url"])

    return _prettify(root)


def _prettify(elem: Element) -> str:
    """Return a pretty-printed XML string for the Element."""
    rough_string = tostring(elem, encoding="unicode", xml_declaration=False)
    xml_declaration = '<?xml version="1.0" encoding="UTF-8"?>\n'
    try:
        parsed = parseString(rough_string)
        return xml_declaration + parsed.toprettyxml(indent="  ").split("\n", 1)[1]
    except Exception:
        return xml_declaration + rough_string

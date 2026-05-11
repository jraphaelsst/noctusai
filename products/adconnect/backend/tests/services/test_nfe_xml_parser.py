"""
Tests for the NF-e XML parser.

Goal: prove the parser pulls the four sellout-relevant fields (CNPJ, items,
total, chave) from a representative NF-e XML, and that strict-mode raises
on missing required fields.
"""
from __future__ import annotations

import pytest

from app.services.nfe_xml_parser import NFeParseError, parse_nfe_xml


def _sample_xml(*, with_chave: bool = True, with_cnpj: bool = True) -> str:
    chave_attr = ' Id="NFe35200612345678000190550010000123451123456789"' if with_chave else ""
    dest_block = (
        "<dest><CNPJ>11222333000181</CNPJ><xNome>Cliente Final</xNome></dest>"
        if with_cnpj
        else "<dest><xNome>Cliente Final</xNome></dest>"
    )
    return f"""<?xml version='1.0' encoding='UTF-8'?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe">
  <NFe>
    <infNFe{chave_attr}>
      {dest_block}
      <det nItem="1">
        <prod>
          <cProd>SKU-A</cProd>
          <xProd>Cabo Cat6 305m</xProd>
          <NCM>85444900</NCM>
          <CFOP>5102</CFOP>
          <uCom>UN</uCom>
          <qCom>10.0000</qCom>
          <vUnCom>120.5000</vUnCom>
          <vProd>1205.0000</vProd>
        </prod>
      </det>
      <det nItem="2">
        <prod>
          <cProd>SKU-B</cProd>
          <xProd>Conector RJ45</xProd>
          <qCom>50.0000</qCom>
          <vUnCom>2.5000</vUnCom>
          <vProd>125.0000</vProd>
        </prod>
      </det>
      <total>
        <ICMSTot>
          <vNF>1330.00</vNF>
        </ICMSTot>
      </total>
    </infNFe>
  </NFe>
</nfeProc>
""".strip()


def test_parse_extracts_all_fields() -> None:
    parsed = parse_nfe_xml(_sample_xml())
    assert parsed.cnpj_cliente_final == "11222333000181"
    assert parsed.valor_total == pytest.approx(1330.0)
    assert parsed.quantidade_itens == 2
    assert parsed.nfe_chave == "35200612345678000190550010000123451123456789"
    assert len(parsed.items_json) == 2
    assert parsed.items_json[0]["cProd"] == "SKU-A"
    assert parsed.items_json[0]["qCom"] == pytest.approx(10.0)


def test_parse_payload_shape_maps_to_columns() -> None:
    payload = parse_nfe_xml(_sample_xml()).as_payload()
    assert set(payload.keys()) == {
        "cnpj_cliente_final",
        "valor_total",
        "quantidade_itens",
        "descricao_resumida",
        "items_json",
        "nfe_chave",
    }


def test_parse_lenient_accepts_partial_xml() -> None:
    parsed = parse_nfe_xml(_sample_xml(with_chave=False, with_cnpj=False))
    assert parsed.cnpj_cliente_final is None
    assert parsed.nfe_chave is None
    assert parsed.valor_total == pytest.approx(1330.0)
    assert parsed.quantidade_itens == 2


def test_parse_strict_raises_on_missing() -> None:
    with pytest.raises(NFeParseError):
        parse_nfe_xml(_sample_xml(with_chave=False), strict=True)


def test_parse_invalid_xml_raises() -> None:
    with pytest.raises(NFeParseError):
        parse_nfe_xml("<not-real><<>")


def test_parse_rejects_xxe_external_entity() -> None:
    """defusedxml hardening: external-entity declarations must be rejected
    (bandit B314 — XML external-entity-expansion attack defense). Reading
    `/etc/passwd` via XXE was the classic exploit vector against the prior
    stdlib `xml.etree.ElementTree.fromstring`. defusedxml raises
    `EntitiesForbidden` (subclass of ET.ParseError) — we wrap to NFeParseError.
    """
    xxe_payload = (
        '<?xml version="1.0"?>\n'
        '<!DOCTYPE foo [ <!ENTITY xxe SYSTEM "file:///etc/passwd"> ]>\n'
        "<nfeProc><dest><CNPJ>&xxe;</CNPJ></dest></nfeProc>"
    )
    with pytest.raises(NFeParseError):
        parse_nfe_xml(xxe_payload)

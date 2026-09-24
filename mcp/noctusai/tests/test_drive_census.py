"""Tests for `noctus.dev.drive_census` — census + contract answer keys over drive_pull mirrors.

Every value below is INVENTED (names, CPFs, numbers, places). The real layouts these fixtures mimic
live only on private disk (memory `feedback_sw_document_read_authorization`). Zero network.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT / "seed" / "lib" / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import drive_census as C  # noqa: E402

CONTRATO = """INSTRUMENTO PARTICULAR DE PROMESSA DE VENDA E COMPRA DE BEM IMÓVEL – RESIDENCIAL TESTE – RUA FICTÍCIA, Nº 10 – VILA MODELO - SP.
Pelo presente Instrumento Particular, de um lado, ANA EXEMPLO SILVA, brasileira, divorciada, portadora da cédula de identidade RG 11.222.333-4-SSP-SP e inscrita no CPF/MF 111.222.333-44, com endereço eletrônico: ana@example.com, residente e domiciliada na Rua Fictícia, nº 10 - Jardim Teste - Vila Modelo/SP – CEP: 01234-567, denominada simplesmente "VENDEDORA";
E de outro lado, BRUNO FICTICIO SOUZA, brasileiro, casado, engenheiro, portador da cédula de identidade RG 22.333.444-5-SSP-SP e inscrito no CPF/MF 222.333.444-55, com endereço eletrônico: bruno@example.com, e CARLA FICTICIA SOUZA, brasileira, casada, médica, portadora da cédula de identidade RG 33.444.555-6-SSP-SP e inscrita no CPF/MF 333.444.555-66, com endereço eletrônico: carla@example.com, casados entre si sob o regime da comunhão parcial de bens, residentes e domiciliados na Avenida Inventada, nº 99 - Centro - Cidade Exemplo/SP – CEP: 07654-321, denominados "COMPRADORES";
CLÁUSULA PRIMEIRA – DO OBJETO DO CONTRATO
A VENDEDORA, por escritura datada de 1 de janeiro de 2020, do 1º Tabelião de Notas de Vila Modelo/SP, tornou-se legítima proprietária do imóvel descrito a seguir:
IMÓVEL: Terreno com casa, cadastrado pela Prefeitura Municipal de Vila Modelo sob nº 1234.56.78.0001 e caracterizado na Matrícula Nº 4.321 do Cartório de Registro de Imóveis de Vila Modelo.
CLÁUSULA SEGUNDA – DO PREÇO E CONDIÇÕES DE PAGAMENTO
A VENDEDORA compromete-se a vender o imóvel ad corpus pelo preço certo, firme e irreajustável de R$ 500.000,00 (quinhentos mil reais), conforme a seguir:
Parcela 01: Sinal e princípio de pagamento: R$ 50.000,00 (cinquenta mil reais) por meio de TED a ser realizada em favor da VENDEDORA: ANA EXEMPLO SILVA, CPF: 111.222.333-44, Banco Exemplo (999), Agência 0001, Conta Corrente 12345-6.
Parcela 02: R$ 450.000,00 (quatrocentos e cinquenta mil reais), por meio de recursos de financiamento imobiliário.
CLÁUSULA TERCEIRA – DAS CERTIDÕES E DOCUMENTOS
1 - Em nome de ANA EXEMPLO SILVA
1.1 – Certidão Negativa de Débitos Relativos aos Tributos Federais e Dívida Ativa União – nº AAAA.BBBB.CCCC.DDDD - emitida em 01/08/2026;
1.7 – Certidão Negativa com apontamentos de Homônimos Estadual do Distribuidor Cível do Tribunal de Justiça do Estado de São Paulo – nº 1000001 - emitida em 02/08/2026; SISTEMA E-SAJ
1.9 - Pesquisa Negativa junto ao Serasa, relativa a restrições financeiras – protocolo nº 424242 - emitida em 03/08/2026;
2 - Em nome de 12.345.678 ANA EXEMPLO SILVA - Empresa Baixada
2.1 – Certidão Negativa de Débitos Relativos aos Tributos Federais e Dívida Ativa União – nº EEEE.FFFF.0000.1111 - emitida em 01/08/2026;
3 – Em relação ao imóvel
3.1 – Certidão da Matrícula do imóvel, emitida em 04/08/2026;
3.2 - Certidão Negativa de Débitos Municipais (IPTU) n°. 777/2026 – emitida em 05/08/2026;
a-) Certidão negativa de despesas condominiais relativas ao imóvel;
CLÁUSULA DÉCIMA TERCEIRA - DA INTERMEDIAÇÃO
Neste ato a VENDEDORA contrata as empresas a seguir qualificadas, para promover a presente intermediação:
Parágrafo Primeiro: ajustam o valor de corretagem em R$ 30.000,00 (trinta mil reais) e deverá ser pago em 02 parcelas iguais:
Em duas parcelas iguais de R$ 15.000,00 (quinze mil reais), por meio de depósito bancário em favor de IMOBILIARIA FICTICIA LTDA, CNPJ n° 00.111.222/0001-33, Banco Exemplo.
CLÁUSULA DÉCIMA QUARTA - DA ELEIÇÃO DO FORO
As partes elegem o foro da Comarca de Vila Modelo, para dirimir as questões, e assinam de forma digital via D4sign.
Vila Modelo, 10 de agosto de 2026.
TESTEMUNHAS
DANIELA TESTEMUNHA UM daniela@example.com
RG 44.555.666-7
EDUARDO TESTEMUNHA DOIS
RG 55.666.777-8"""


@pytest.fixture()
def private(tmp_path, monkeypatch):
    root = tmp_path / "private"
    monkeypatch.setenv("NOCTUS_PRIVATE_DIR", str(root))
    return root


def _key(text: str = CONTRATO) -> dict:
    return C.parse_contract(C.paragraphs_from_text(text, source="docx"))


# ─── classify ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("rel", "doc_type", "entity_kind", "n"),
    [
        ("CERTIDÕES/FULANO/7 - TJSP e-saj_FULANO.pdf", "certidao", "pf", 7),
        ("CERTIDÕES/FULANO/9 - SERASA_FULANO.pdf", "serasa_crednet", "pf", 9),
        ("CERTIDÕES/FULANO CNPJ/1 - RF_FULANO CNPJ", "certidao", "pj", 1),
        ("CERTIDÕES/Cartão CNPJ_Empresa.pdf", "cartao_cnpj", None, None),
        ("CERTIFICADO DIGITAL - CCV - TESTE docx pdf-D4Sign.pdf", "contrato_d4sign", None, None),
        ("REV FINAL_CONTRATO DE COMPRA E VENDA - TESTE.docx", "contrato", None, None),
        ("CND Negativa Débitos de IPTU.pdf", "cnd_iptu", None, None),
        ("Espelho do IPTU 2026.pdf", "iptu_espelho", None, None),
        ("Guia ITBI_Teste.pdf", "itbi_guia", None, None),
        ("Comprovante de Pagamento ITBI - Teste.jpeg", "itbi_comprovante", None, None),
        ("CERTIDÃO DE MATRÍCULA - TESTE.pdf", "matricula", None, None),
        ("DOCUMENTOS/CNH_Fulano.pdf", "identidade", None, None),
        ("DOCUMENTOS/Certidão de Casamento com Av_Fulano.pdf", "certidao_casamento", None, None),
    ],
)
def test_classify_entry(rel, doc_type, entity_kind, n) -> None:
    c = C.classify_entry(rel)
    assert c["doc_type"] == doc_type
    assert c["entity_kind"] == entity_kind
    assert c["certidao_n"] == n


def test_classify_marks_drafts_and_rev_final() -> None:
    assert C.classify_entry("CONTRATOS ANTIGOS/CONTRATO DE COMPRA E VENDA - X.docx")["draft"] is True
    assert C.classify_entry("MINUTA DE CONTRATO ANTIGA/CONTRATO DE COMPRA E VENDA - X.docx")["draft"] is True
    assert C.classify_entry("REV FINAL_CONTRATO DE COMPRA E VENDA - X.docx").get("rev_final") is True


def test_folder_identity() -> None:
    assert C.folder_identity("901 - 02/03/2026 - RESIDENCIAL TESTE - CASA 1 - (Corretor)") == {
        "numero": "901", "data": "2026-03-02", "titulo": "RESIDENCIAL TESTE - CASA 1 - (Corretor)"}
    assert C.folder_identity("141 - RECANTO TESTE")["data"] is None


# ─── contract selection ───────────────────────────────────────────────────


def _row(rel: str, **kw) -> dict:
    return {"rel_path": rel, **C.classify_entry(rel), **kw}


def test_select_contract_prefers_d4sign_then_rev_final_then_latest_revision() -> None:
    d4 = _row("CERTIFICADO DIGITAL - CCV - X-D4Sign.pdf", text_source="text_layer")
    rev = _row("REV FINAL_CONTRATO DE COMPRA E VENDA - X.docx")
    old = _row("CONTRATO DE COMPRA E VENDA - X - rev. 01-08-26.docx")
    new = _row("CONTRATO DE COMPRA E VENDA - X - rev. 14-08-26.docx")
    draft = _row("CONTRATOS ANTIGOS/CONTRATO DE COMPRA E VENDA - X - rev. 30-09-26.docx")
    assert C.select_contract([rev, d4, old])[1] == "d4sign"
    assert C.select_contract([old, rev])[1] == "rev_final"
    chosen, fonte, _ = C.select_contract([old, new, draft])
    assert (fonte, chosen["rel_path"]) == ("revisao", new["rel_path"])
    assert C.select_contract([draft])[1] == "none"


def test_select_contract_skips_an_image_only_d4sign() -> None:
    d4 = _row("X-D4Sign.pdf", text_source="image_only")
    rev = _row("REV FINAL_CONTRATO DE COMPRA E VENDA - X.docx")
    assert C.select_contract([d4, rev])[1] == "rev_final"


# ─── PDF text normalization ───────────────────────────────────────────────


def test_pdf_furniture_and_structural_splits() -> None:
    title = "Contrato Particular de Promessa de Venda e Compra – Residencial Teste – Rua Fictícia"
    pdf = "\n".join([
        "CLÁUSULA PRIMEIRA – DO OBJETO", " ", "Texto da cláusula que continua", "na linha seguinte.", " ",
        "1/3", title, "D4Sign 12345678-aaaa-bbbb-cccc-1234567890ab - Para confirmar acesse", "Documento assinado eletronicamente",
        "CLÁUSULA SEGUNDA – DO PREÇO", " ", "1 - Em nome de FULANO", "1.1 – Certidão Negativa – nº",
        "83820946 - emitida em 01/01/2026;", "1.2 – Outra – nº 1 - emitida em 02/01/2026;", " ",
        "2/3", title, " ", "3/3", title, " ",
        "Documento 12345678-aaaa-bbbb-cccc-1234567890ab criado por ALGUEM", "lixo do certificado",
    ])
    paras = C.paragraphs_from_text(pdf, source="pdf")
    assert paras[0] == "CLÁUSULA PRIMEIRA – DO OBJETO"
    assert paras[1] == "Texto da cláusula que continua na linha seguinte."
    assert paras[2] == "CLÁUSULA SEGUNDA – DO PREÇO"
    assert paras[3] == "1 - Em nome de FULANO"
    # a wrapped number ("83820946 - emitida…") is NOT a group start
    assert paras[4] == "1.1 – Certidão Negativa – nº 83820946 - emitida em 01/01/2026;"
    assert paras[5].startswith("1.2")
    assert not any("certificado" in p or "D4Sign" in p or p == title for p in paras)


def test_diff_ignores_list_numbers_and_signature_block() -> None:
    a = ["Cláusula igual.", "Em duas parcelas iguais de R$ 1,00.", "Vila Modelo, 10 de agosto de 2026.", "VENDEDORA", "FULANO"]
    b = ["Cláusula igual.", "1)​ Em duas parcelas iguais de R$ 1,00.", "Vila Modelo, 10 de agosto de 2026.", "VENDEDORA FULANO"]
    b = C.paragraphs_from_text("\n".join(b), source="docx")
    assert C.diff_paragraphs(a, b) == []
    assert len(C.diff_paragraphs(["Preço R$ 1,00."], ["Preço R$ 2,00."])) == 1


# ─── contract parsing ─────────────────────────────────────────────────────


def test_parse_partes() -> None:
    partes = _key()["partes"]
    assert [(p["lado"], p["papel"]) for p in partes] == [
        ("vendedor", "proprietario"), ("comprador", "comprador"), ("comprador", "comprador")]
    v = partes[0]["clientes"]
    assert v["nome_oficial"] == "ANA EXEMPLO SILVA"
    assert (v["cpf"], v["rg"], v["rg_orgao_expedidor"]) == ("11122233344", "11.222.333-4", "SSP-SP")
    assert (v["estado_civil"], v["genero"], v["email"]) == ("divorciado", "Feminino", "ana@example.com")
    assert (v["endereco_cidade"], v["endereco_uf"], v["endereco_cep"]) == ("Vila Modelo", "SP", "01234567")
    b, c = partes[1], partes[2]
    # the couple's regime is printed once, after the second spouse, and applies to both
    assert (b["clientes"]["profissao"], b["clientes"]["regime_bens"]) == ("engenheiro", "comunhao_parcial")
    assert c["clientes"]["regime_bens"] == "comunhao_parcial"
    assert (b["conjuge_de"], c["conjuge_de"]) == (2, 1)
    # the side's shared address reaches both buyers
    assert b["clientes"]["endereco_cep"] == c["clientes"]["endereco_cep"] == "07654321"


def test_couple_status_printed_once_is_shared_and_coworkers_are_not_married() -> None:
    txt = ("Pelo presente, de um lado, JOAO TESTE PRIMEIRO, brasileiro, engenheiro, portador da cédula de identidade "
           "RG: 12.345.678 - SSP- SP, inscrito no CPF/MF sob nº 123.456.789-01, casado sob regime da comunhão universal "
           "de bens com MARIA TESTE PRIMEIRA, brasileira, médica, inscrita no CPF/MF 987.654.321-09, residentes e "
           "domiciliados na Rua X, nº 1 - Centro - Cidade/SP - CEP: 01000-000;\n"
           "E de outro lado, PEDRO SOCIO UM, brasileiro, solteiro, inscrito no CPF/MF 111.111.111-11, e "
           "PAULO SOCIO DOIS, brasileiro, divorciado, inscrito no CPF/MF 222.222.222-22;")
    partes = C.parse_partes(C.paragraphs_from_text(txt, source="docx"))
    joao, maria, pedro, paulo = (p["clientes"] for p in partes)
    assert (joao["rg"], joao["rg_orgao_expedidor"], joao["cpf"]) == ("12.345.678", "SSP- SP", "12345678901")
    assert (maria["estado_civil"], maria["regime_bens"]) == ("casado", "comunhao_universal")
    assert (partes[0]["conjuge_de"], partes[1]["conjuge_de"]) == (1, 0)
    assert (pedro["estado_civil"], paulo["estado_civil"]) == ("solteiro", "divorciado")
    assert (partes[2]["conjuge_de"], partes[3]["conjuge_de"]) == (None, None)


def test_parse_imovel_and_negociacao() -> None:
    k = _key()
    d = k["imovel"]["imovel_dados"]
    assert d["numero_matricula"] == "4321"
    assert d["numero_registro_imoveis"] == "Cartório de Registro de Imóveis de Vila Modelo"
    assert d["prefeitura_cadastro_imobiliario"] == "1234.56.78.0001"
    assert d["titulo_aquisitivo_texto"].startswith("A VENDEDORA, por escritura")
    n = k["negociacao"]
    assert (n["valor_negociado"], n["ad_corpus"], n["tem_permuta"]) == ("500000.00", True, False)
    assert [(p["tipo"], p["valor"]) for p in n["parcelas"]] == [("sinal", "50000.00"), ("financiamento", "450000.00")]
    assert n["favorecidos"] == [{"nome": "ANA EXEMPLO SILVA", "cpf_cnpj": "11122233344", "banco": "Exemplo",
                                 "agencia": "0001", "conta": "12345-6", "pix": None}]


def test_parse_certidoes() -> None:
    cert = _key()["certidoes"]
    pf, pj = cert["grupos"]
    assert (pf["consulta_tipo_documento"], pf["sufixo"]) == ("cpf", None)
    assert [(i["item"], i["pasta_n"], i["tipo"], i["resultado"], i["numero"], i["emitida_em"], i["sistema"])
            for i in pf["itens"]] == [
        ("1.1", 1, "cnd_federal", "negativa", "AAAA.BBBB.CCCC.DDDD", "2026-08-01", None),
        ("1.7", 7, "tjsp_esaj", "negativa_com_homonimos", "1000001", "2026-08-02", "E-SAJ"),
        ("1.9", 9, "serasa", "negativa", "424242", "2026-08-03", None),
    ]
    assert (pj["consulta_tipo_documento"], pj["documento"], pj["sufixo"]) == ("cnpj", "12345678", "Empresa Baixada")
    assert [(g["tipo"], g["numero"], g["emitida_em"]) for g in cert["grupos_imovel"]] == [
        ("matricula", None, "2026-08-04"), ("cnd_iptu", "777/2026", "2026-08-05")]
    assert cert["pendencias"] == ["Certidão negativa de despesas condominiais relativas ao imóvel;"]


def test_parse_intermediacao_assinatura_testemunhas() -> None:
    k = _key()
    i = k["intermediacao"]
    assert (i["corretagem_total"], i["corretagem_num_parcelas"], i["corretagem_contratantes"]) == ("30000.00", 2, "vendedores")
    assert i["intermediarios"] == [{"nome": "IMOBILIARIA FICTICIA LTDA", "documento": "00111222000133",
                                    "valor_parcela": "15000.00", "valor": "30000.00"}]
    c = k["contrato"]
    assert (c["assinatura_data"], c["assinatura_local"], c["foro_comarca"], c["modalidade_assinatura"]) == (
        "2026-08-10", "Vila Modelo", "Vila Modelo", "digital")
    assert k["testemunhas"] == [{"nome": "DANIELA TESTEMUNHA UM", "rg": "44.555.666-7"},
                                {"nome": "EDUARDO TESTEMUNHA DOIS", "rg": "55.666.777-8"}]


# ─── extract once + end to end over a synthetic mirror ────────────────────


def _mirror(private: Path, folder_id: str, files: dict[str, bytes]) -> None:
    tree = private / "drive-mirror" / folder_id / "tree"
    entries = []
    for i, (rel, data) in enumerate(files.items()):
        path = tree / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document" if rel.endswith(".docx") \
            else "application/pdf" if rel.endswith(".pdf") else "image/jpeg"
        entries.append({"drive_id": f"id{i}", "name": Path(rel).name, "rel_path": rel, "mime_type": mime,
                        "is_folder": False, "local_path": str(path), "status": "downloaded",
                        "sha256": f"{i:064x}", "size_bytes": len(data)})
    (private / "drive-mirror" / folder_id / "manifest.json").write_text(json.dumps(
        {"folder_id": folder_id, "folder_name": "901 - 02/03/2026 - RESIDENCIAL TESTE - (Corretor)", "entries": entries}))


def _docx_bytes(text: str, tmp_path: Path) -> bytes:
    import docx

    d = docx.Document()
    for line in text.split("\n"):
        d.add_paragraph(line)
    out = tmp_path / "c.docx"
    d.save(str(out))
    return out.read_bytes()


def test_extract_once_then_cached_and_errors_retry(private, tmp_path) -> None:
    _mirror(private, "F1", {"REV FINAL_CONTRATO DE COMPRA E VENDA - X.docx": _docx_bytes("Olá", tmp_path),
                            "foto.jpg": b"\xff\xd8"})
    first = C.drive_census("extract", "F1")["results"][0]
    assert first["outcomes"] == {"extracted": 2}
    assert first["text_sources"] == {"docx": 1, "image_only": 1}
    caches = sorted((private / "extractions").glob("*.json"))
    assert [oct(c.stat().st_mode & 0o777) for c in caches] == ["0o600", "0o600"]
    before = {c: (c.stat().st_mtime_ns, c.read_text()) for c in caches}
    assert C.drive_census("extract", "F1")["results"][0]["outcomes"] == {"cached": 2}
    assert {c: (c.stat().st_mtime_ns, c.read_text()) for c in caches} == before  # never re-read or re-written
    rec = json.loads(caches[0].read_text())
    rec["error"] = "boom"
    caches[0].write_text(json.dumps(rec))
    assert C.drive_census("extract", "F1")["results"][0]["outcomes"] == {"retried": 1, "cached": 1}
    assert json.loads(caches[0].read_text())["error"] is None


def test_answer_key_end_to_end_is_private_and_redacted(private, tmp_path) -> None:
    _mirror(private, "F2", {
        "REV FINAL_CONTRATO DE COMPRA E VENDA - X.docx": _docx_bytes(CONTRATO, tmp_path),
        "CERTIDÕES/ANA/1 - RF_ANA.pdf": b"%PDF-1.4 not really",
        "CERTIDÕES/ANA CNPJ/1 - RF_ANA CNPJ": b"%PDF-1.4 not really",
    })
    (private / "answer-keys").mkdir(parents=True, exist_ok=True)
    (private / "answer-keys" / "901-empresas-verificado.json").write_text(json.dumps({
        "verificado_por": "humano", "crednet": {"protocolo": "424242"},
        "empresas": [{"cnpj": "12345678000199", "exigida": True}, {"cnpj": "99888777000166", "exigida": False}]}))
    result = C.drive_census("answer_key", "F2")
    summary = result["results"][0]
    assert (summary["numero"], summary["status"], summary["fonte"]) == ("901", "ok", "rev_final")
    assert summary["cobertura"]["empresas_contrato_diverge"] == 0
    blob = json.dumps(result, ensure_ascii=False)
    for pii in ("ANA EXEMPLO", "11122233344", "ana@example.com"):
        assert pii not in blob  # the RESULT never carries personal data
    key_path = private / "answer-keys" / "901.json"
    assert oct(key_path.stat().st_mode & 0o777) == "0o600"
    key = json.loads(key_path.read_text())
    assert [(e["no_contrato"], e["contrato_confere"], e["verificado"]) for e in key["empresas"]] == [
        (True, True, True), (False, True, True)]

    census = C.drive_census("census", "F2")["results"][0]
    assert census["certidao_sets"] == 2 and census["entities_pj"] == 1
    assert census["root_gaps"] == ["matricula", "iptu_espelho", "cnd_iptu"]
    assert (private / "census" / "901.json").is_file()


ADITIVO = """PRIMEIRO ADITIVO AO INSTRUMENTO PARTICULAR DE PROMESSA DE VENDA E COMPRA DE BEM IMÓVEL – RESIDENCIAL TESTE
Pelo presente instrumento particular, de um lado, ANA EXEMPLO SILVA, brasileira, divorciada, inscrita no CPF/MF 111.222.333-44;
1. DA ALTERAÇÃO DA PARCELA 02 DA CLÁUSULA SEGUNDA As partes resolvem alterar a forma de pagamento da Parcela 02.
Parcela 02: R$ 450.000,00 (quatrocentos e cinquenta mil reais), sendo:
2. DA ALTERAÇÃO DA CLÁUSULA QUINTA – POSSE DO IMÓVEL A posse será outorgada após o registro.
3. DA RATIFICAÇÃO Permanecem válidas as demais cláusulas do Instrumento Particular firmado em 28 de julho de 2026 que ora se adita.
VENDEDORA: ANA EXEMPLO SILVA
Documento 12345678-aaaa-bbbb-cccc-1234567890ab criado por ALGUEM 2026-09-01T10:00:00-03:00 2026-09-02T11:30:00-03:00"""


def test_aditivo_is_structured_and_never_the_ground_truth_contract(private, tmp_path) -> None:
    _mirror(private, "F3", {
        # named like a contract: only its opening text says it is an aditivo
        "REV FINAL_CONTRATO DE COMPRA E VENDA - X (2).docx": _docx_bytes(ADITIVO, tmp_path),
        "CONTRATO DE COMPRA E VENDA - X - rev. 14-08-26.docx": _docx_bytes(CONTRATO, tmp_path),
    })
    summary = C.drive_census("answer_key", "F3")["results"][0]
    assert (summary["status"], summary["fonte"], summary["aditivos"]) == ("ok", "revisao", 1)
    assert summary["aditivos_categorias"] == ["parcelas", "prazo"]
    key = json.loads((private / "answer-keys" / "901.json").read_text())
    [ad] = key["aditivos"]
    assert (ad["numero_ordinal"], ad["contrato_original_data"], ad["fonte"], ad["status"]) == (1, "2026-07-28", "docx", "ok")
    assert [(s["secao"], s["categorias"], s["clausula_original"]) for s in ad["alteracoes"]] == [
        (1, ["parcelas"], "Segunda"), (2, ["prazo"], "Quinta")]
    assert "Parcela 02: R$ 450.000,00" in ad["alteracoes"][0]["texto"]  # the section keeps its body
    # a D4Sign certificate's last ISO stamp is the signing date
    assert C.d4sign_assinado_em(ADITIVO) == "2026-09-02"


def test_criminal_items_are_ignored_and_relatorio_fiscal_takes_the_rf_slot() -> None:
    txt = """CLÁUSULA TERCEIRA – DAS CERTIDÕES E DOCUMENTOS
1 - Em nome de ANA EXEMPLO SILVA
1.1 – Certidão Positiva com Efeito de Negativa de Débitos Relativos aos Tributos Federais e Dívida Ativa União – nº AAAA.BBBB - emitida em 01/08/2026;
1.13 – Certidões de Distribuição Criminal emitidas pela Justiça Estadual e Justiça Federal.
2 - Em nome de EMPRESA FICTICIA LTDA
2.1 – Relatório Fiscal emitido em 13/09/2026;"""
    cert = C.parse_certidoes(C.split_clauses(C.paragraphs_from_text(txt, source="docx"))[1][0])
    pf, pj = cert["grupos"]
    crim = pf["itens"][1]
    assert (crim["tipo"], crim["ignorado"]) == (None, "criminal_advogado_cliente")
    assert pj["consulta_tipo_documento"] == "cnpj"  # LTDA in the name
    [rel] = pj["itens"]
    assert (rel["tipo"], rel["pasta_n"], rel["emitida_em"], rel["condicao"]) == (
        "relatorio_fiscal", 1, "2026-09-13", "rf_nao_negativa")
    assert (rel["rf_presente"], rel["rf_resultado"]) == (False, None)


def test_word_diff_reports_only_real_edits() -> None:
    a = ["Parcela 01 —", "R$ 1,00 no ato.", "a) item", "Vila Modelo, 10 de agosto de 2026."]
    b = ["Parcela 01 — R$ 1,00 no ato.", "item", "Vila Modelo, 10 de agosto de 2026.", "ASSINATURAS"]
    assert C.diff_paragraphs(a, b) == []
    d = C.diff_paragraphs(["com e-mail: x@example.com, residente"], ["com e-mail: x@example.com e y@example.com, residente"])
    assert [(x["docx"], x["d4sign"]) for x in d] == [(None, "e y@example.com,")]


def test_extensionless_docx_by_mime_and_image_only_signed_contract(private, tmp_path) -> None:
    # Drive names often lack an extension; the manifest mime makes it a docx. The signed PDF is a
    # scan whose name embeds the docx name, so the docx is as good as the signature.
    _mirror(private, "F4", {
        "CONTRATO DE COMPRA E VENDA - X - rev 10-08.docx": _docx_bytes(CONTRATO, tmp_path),
        "CERTIFICADO DIGITAL - CONTRATO DE COMPRA E VENDA - X - rev 10-08 docx pdf-D4Sign.jpg": b"\xff\xd8",
    })
    manifest = private / "drive-mirror" / "F4" / "manifest.json"
    m = json.loads(manifest.read_text())
    for k in ("name", "rel_path"):  # the extension-less Drive name; only the mime says docx
        m["entries"][0][k] = m["entries"][0][k].removesuffix(".docx")
    manifest.write_text(json.dumps(m))
    summary = C.drive_census("answer_key", "F4")["results"][0]
    assert (summary["status"], summary["fonte"]) == ("ok", "revisao")
    key = json.loads((private / "answer-keys" / "901.json").read_text())
    assert (key["fonte"]["confianca"], key["fonte"]["nota"]) == ("alta", "d4sign_imagem_gerado_deste_docx")


def test_only_an_image_signed_contract_is_not_ground_truth(private) -> None:
    _mirror(private, "F5", {"CERTIFICADO DIGITAL - CCV - X-D4Sign.jpg": b"\xff\xd8"})
    assert C.drive_census("answer_key", "F5")["results"][0]["status"] == "contrato_so_imagem"


def test_a_failing_file_retries_at_most_three_times(private) -> None:
    _mirror(private, "F6", {"quebrado.pdf": b"%PDF-1.4 garbage"})
    cache = private / "extractions" / f"{0:064x}.json"
    C.drive_census("extract", "F6")
    rec = json.loads(cache.read_text())
    rec.update({"error": "boom", "tentativas": 3})
    cache.write_text(json.dumps(rec))
    assert C.drive_census("extract", "F6")["results"][0]["outcomes"] == {"cached": 1}


def test_ref_candidates_rank_documentary_matches_first_and_never_link(private, tmp_path) -> None:
    from tools.noctus.dev.migrate_product import FakeSqlExecutor

    contrato = CONTRATO.replace("Terreno com casa,", "Terreno com casa com área construída de 210,50m²,") \
        .replace("RESIDENCIAL TESTE – RUA", "RESIDENCIAL TESTE – CASA 10 – RUA", 1)
    _mirror(private, "F7", {"REV FINAL_CONTRATO DE COMPRA E VENDA - X.docx": _docx_bytes(contrato, tmp_path)})
    C.drive_census("answer_key", "F7")
    rows = [
        {"codigo": "ONE1", "empreendimento": "Residencial Teste", "complemento": "Casa 10", "area_construida": 211.0,
         "logradouro": "Fictícia", "numero": "10", "cidade": "Vila Modelo"},             # condo + unidade + área
        {"codigo": "ONE2", "matricula_vista": "4.321", "empreendimento": "Outro Lugar"},   # the matrícula
        {"codigo": "ONE3", "empreendimento": "Jardim Distante", "area_total": 900.0},      # decoy
    ]
    fake = FakeSqlExecutor(preset_rows={"FROM social_wiring.imoveis": rows})
    result = C.drive_census("ref_candidates", "F7", executor=fake)
    summary = result["results"][0]
    assert (summary["status"], summary["candidatos"], summary["melhor_forca"]) == ("ok", 2, "forte")
    assert all(sql.lstrip().upper().startswith("SELECT") for sql in fake.executed)  # read-only
    out = json.loads((private / "ref-candidates" / "901.json").read_text())
    assert [(c["codigo"], c["forca"]) for c in out["candidatos"]] == [("ONE2", "forte"), ("ONE1", "media")]
    assert set(out["candidatos"][1]["evidencias"]) >= {"condominio", "unidade", "area_m2"}
    assert (out["confirmado_por"], out["confirmado_em"]) == (None, None)  # only the owner confirms
    # the snapshot is read once and reused
    C.drive_census("ref_candidates", "F7", executor=fake)
    assert len(fake.executed) == 1


def test_unknown_action_is_refused() -> None:
    with pytest.raises(ValueError, match="extract \\| census \\| answer_key"):
        C.drive_census("nope")

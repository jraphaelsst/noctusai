"""Row builders for the imóvel↔pessoa relationship suites (project
`atendimento-partes-imoveis`, BE-imoveis).

Rows are shaped the way Postgres would hand them back (ids, org_id,
timestamps), and seeded through THIS module's scoped mock
(`get_imovel_hub_client`) so every route under test reads what the fixture
wrote. Kept in one place at N>=3: five suites need the same eight builders.
"""
from __future__ import annotations

from uuid import uuid4

from tests.modules.imovel_hub.conftest import ORG_ID


def cliente_row(id_=None, *, nome="Ana Souza", **extra) -> dict:
    row = {
        "id": id_ or str(uuid4()),
        "org_id": ORG_ID,
        "nome": nome,
        "nome_oficial": None,
        "celular": "+5511999990001",
        "email": "ana@example.com",
        "chave_canonica": "+5511999990001",
        "cpf": None,
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    row.update(extra)
    return row


def atendimento_row(id_=None, *, cliente_id=None, lead_id=None, meta_ads_lead_id=None, **extra) -> dict:
    row = {
        "id": id_ or str(uuid4()),
        "org_id": ORG_ID,
        "cliente_id": cliente_id,
        "lead_id": lead_id,
        "meta_ads_lead_id": meta_ads_lead_id,
        "etapa_id": None,
        "titulo": "Atendimento",
        "status": "aberta",
        "arquivado": False,
        "substituida_por": None,
        "created_at": "2026-02-01T00:00:00+00:00",
    }
    row.update(extra)
    return row


def registro(codigo: str, **extra) -> dict:
    row = {
        "id": str(uuid4()),
        "org_id": ORG_ID,
        "codigo_canonical": codigo,
        "codigo_display": codigo,
        "ativo_no_vista": True,
        "origem_descoberta": "vista_sync",
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    row.update(extra)
    return row


def espelho(codigo: str, **extra) -> dict:
    """A Vista mirror row WITH the specs the additive `ImovelResumo` keys read."""
    row = {
        "org_id": ORG_ID,
        "codigo": codigo,
        "codigo_norm": codigo,
        "titulo": f"Imóvel {codigo}",
        "empreendimento": None,
        "logradouro": "Rua das Palmeiras",
        "numero": "320",
        "complemento": "apto 91",
        "bairro": "Pinheiros",
        "cidade": "São Paulo",
        "uf": "SP",
        "cep": "05422-000",
        "foto_destaque": f"https://cdn.example/{codigo}.jpg",
        "categoria": "Apartamento",
        "status": "Venda",
        "valor_venda": "850000.00",
        "valor_locacao": None,
        "dormitorios": 3,
        "suites": 1,
        "vagas": 2,
        "area_total": "120.00",
        "area_privativa": "98.00",
        "area_construida": None,
        "zona": None,
        "regiao": None,
        "corretores": [],
        "fotos": [],
        "caracteristicas": [],
    }
    row.update(extra)
    return row


def juncao(atendimento_id, codigo, *, origem="lead", principal=False, deleted_at=None, **extra) -> dict:
    row = {
        "id": str(uuid4()),
        "org_id": ORG_ID,
        "atendimento_id": str(atendimento_id),
        "codigo": codigo,
        "origem": origem,
        "principal": principal,
        "created_by": None,
        "created_at": "2026-02-01T00:00:00+00:00",
        "deleted_at": deleted_at,
    }
    row.update(extra)
    return row


def interesse(cliente_id, codigo, *, origem="manual", deleted_at=None, **extra) -> dict:
    row = {
        "id": str(uuid4()),
        "org_id": ORG_ID,
        "cliente_id": str(cliente_id),
        "codigo": codigo,
        "origem": origem,
        "lead_id": None,
        "meta_ads_lead_id": None,
        "created_by": None,
        "created_at": "2026-02-01T00:00:00+00:00",
        "deleted_at": deleted_at,
    }
    row.update(extra)
    return row


def proprietario(codigo, *, cliente_id=None, empresa_id=None, origem="manual", deleted_at=None, **extra) -> dict:
    row = {
        "id": str(uuid4()),
        "org_id": ORG_ID,
        "codigo": codigo,
        "cliente_id": str(cliente_id) if cliente_id else None,
        "empresa_id": str(empresa_id) if empresa_id else None,
        "origem": origem,
        "created_by": None,
        "created_at": "2026-02-01T00:00:00+00:00",
        "deleted_at": deleted_at,
    }
    row.update(extra)
    return row


def lead_row(id_=None, *, codigo="ONE1", cliente_nome="Ana Souza", **extra) -> dict:
    row = {
        "id": id_ or str(uuid4()),
        "org_id": ORG_ID,
        "data_entrada": "2026-02-01",
        "codigo_imovel": codigo,
        "codigo_imovel_norm": codigo.upper() if codigo else None,
        "meta_lead_id": None,
        "cliente_nome": cliente_nome,
        "created_at": "2026-02-01T10:00:00+00:00",
    }
    row.update(extra)
    return row


def meta_row(id_=None, *, codigo="ONE9441", **extra) -> dict:
    row = {
        "id": id_ or f"meta-{uuid4()}",
        "org_id": ORG_ID,
        "codigo_imovel": codigo,
        "codigo_imovel_norm": codigo.upper() if codigo else None,
        "answers": {"REF": codigo} if codigo else {},
        "created_time": "2026-02-02T10:00:00+00:00",
        "created_at": "2026-02-02T10:00:01+00:00",
    }
    row.update(extra)
    return row


def touch_row(cliente_id, *, origem_tabela="leads", origem_id=None, ocorreu_em="2026-02-03T00:00:00+00:00") -> dict:
    return {
        "id": str(uuid4()),
        "org_id": ORG_ID,
        "cliente_id": str(cliente_id),
        "origem_tabela": origem_tabela,
        "origem_id": origem_id or str(uuid4()),
        "ocorreu_em": ocorreu_em,
        "created_at": ocorreu_em,
    }


def seed_tabelas(scoped, **tabelas) -> None:
    """`seed_tabelas(scoped, clientes=[…], atendimentos=[…])` — every named
    table is (re)set, so a row left by an earlier test cannot leak in."""
    for nome, linhas in tabelas.items():
        scoped.set_table_data(nome, list(linhas))

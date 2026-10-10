"""Row builders for the possível-duplicado / vínculo tests (migration 228)."""
from __future__ import annotations

from uuid import uuid4

from tests.modules.imovel_hub.conftest import ORG_ID, dados_row, imovel_row, registry_row

MANUAL = "SW-0001"
VISTA = "ONE1234"

ENDERECO_MANUAL = {
    "endereco_manual_logradouro": "Alameda Liverpool",
    "endereco_manual_numero": "81",
    "endereco_manual_bairro": "Reserva do Vianna",
    "endereco_manual_cidade": "Cotia",
    "endereco_manual_uf": "SP",
    "endereco_manual_cep": "06709-300",
}

ESPELHO_BASE = {
    "titulo": "Casa em condomínio",
    "logradouro": "Al. Liverpool",
    "numero": "81",
    "bairro": "Reserva do Vianna",
    "cidade": "Cotia",
    "uf": "SP",
    "cep": "06709300",
    "empreendimento": None,
    "area_total": None,
    "area_privativa": None,
    "valor_venda": None,
    "valor_locacao": None,
    "matricula_vista": None,
    "foto_destaque": "https://img/vista.jpg",
}


def cenario(
    scoped,
    *,
    manual_dados: dict | None = None,
    manual_cap: dict | None = None,
    espelho: dict | None = None,
    vista_dados: dict | None = None,
    pares: list | None = None,
    manual_reg: dict | None = None,
    vista_reg: dict | None = None,
    extra_registry: list | None = None,
) -> dict:
    """One manual imóvel (SW-0001) + one Vista imóvel (ONE1234), no matching
    data unless asked; returns the registry rows."""
    m = registry_row(
        MANUAL, **{"ativo_no_vista": False, "origem_descoberta": "manual", **(manual_reg or {})}
    )
    v = registry_row(VISTA, **(vista_reg or {}))
    scoped.set_table_data("imovel_registry", [m, v, *(extra_registry or [])])
    scoped.set_table_data(
        "imoveis", [imovel_row(VISTA, **{**ESPELHO_BASE, **(espelho or {})})]
    )
    scoped.set_table_data(
        "imovel_dados",
        [
            dados_row(MANUAL, **(manual_dados if manual_dados is not None else {})),
            dados_row(VISTA, **(vista_dados or {})),
        ],
    )
    scoped.set_table_data(
        "imovel_captacao",
        [{
            "org_id": ORG_ID, "codigo_canonical": MANUAL, "titulo": "Casa Reserva do Vianna",
            "categoria": "Casa", "status": "Venda", "finalidades": ["venda"],
            "created_at": "2026-10-09T10:00:00+00:00", "updated_at": "2026-10-09T10:00:00+00:00",
            **(manual_cap or {}),
        }],
    )
    scoped.set_table_data("imovel_duplicata_candidatos", pares or [])
    scoped.set_table_data("imovel_vinculo_eventos", [])
    return {"manual": m, "vista": v}


def par_row(status="pendente", score=0.8, manual=MANUAL, vista=VISTA, **extra) -> dict:
    row = {
        "id": str(uuid4()), "org_id": ORG_ID, "codigo_manual": manual, "codigo_vista": vista,
        "score": score, "sinais": [{"sinal": "matricula", "detalhe": "matrícula 79826"}],
        "status": status, "detectado_em": "2026-10-09T11:00:00+00:00",
        "atualizado_em": "2026-10-09T11:00:00+00:00", "resolvido_por": None, "resolvido_em": None,
    }
    row.update(extra)
    return row

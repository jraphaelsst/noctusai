"""Julia > Contatos por setor (Lais study, owner decision 2026-11-17): the people Julia points a NON-lead to (a vendor, a
partner, the legal desk, a property owner) instead of treating them as a lead.

Where it lives. The list is the agents org spec `contatos_oficiais` (contract shared with the agents slice): a list of
`{setor, finalidade, nome, telefone}`. SW stores NOTHING of it -- it reads and writes the spec through the channel client
(`AgentsClient.especificacoes` / `salvar_especificacoes`), the same way `julia_especificacoes_router` does, and only ever
sends THIS one key (a body can never reach another spec).

The owner's number is a REFERENCE, never a copy kept by us: the first entry is derived at every read from core
`noctus_users.telefone` of the org's owner (the one place a person's number lives, owner decision 2026-11-03), shown
read-only, and re-resolved on every save, so a number changed in the profile reaches the spec at the next save. The derived
entry is identified by the reserved pair (`SETOR_DONO`, `FINALIDADE_DONO`); an editable entry can never use it.

Format of the spec value (one place, `serializar` / `ler_valor`): compact JSON, `[{"setor", "finalidade", "nome", "telefone"}]`.
NOC-REMEDIATE[contatos-oficiais-formato] the agents slice (item A4) owns the final grammar of the spec; until it lands the
value is this JSON list and a legacy comma-separated value is read back as `legado` (shown, never silently dropped) --
2026-11-17.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional
from uuid import UUID

from noctusai_lib.primitives.exceptions import AppException
from noctusai_lib.primitives.phone import normalize_phone

from app.services import julia_eventos_service as eventos
from app.services.julia_notificacoes_service import donos_da_org
from app.services.julia_relatorio_service import usuarios_da_org

logger = logging.getLogger(__name__)

SPEC_CHAVE = "contatos_oficiais"
SETORES: tuple[str, ...] = ("administrativo", "juridico", "parcerias", "fornecedores", "proprietarios", "outro")
SETOR_DONO = "proprietarios"
FINALIDADE_DONO = "Proprietário da imobiliária: assuntos da diretoria e de proprietários de imóveis"
#: agents caps a `contatos` spec at 10 items; the derived owner entry counts.
MAX_TOTAL = 10
NOME_MAX, FINALIDADE_MAX, FINALIDADE_MIN = 80, 160, 3


def _invalido(codigo: str, msg: str) -> AppException:
    return AppException(codigo, msg, status_code=422)


def validar(entradas: list[dict[str, Any]], *, ha_dono: bool) -> list[dict[str, str]]:
    """Normalise + validate the editable entries (pt-BR 422 per problem, never a bare 500). Phones become E.164."""
    limite = MAX_TOTAL - (1 if ha_dono else 0)
    if len(entradas) > limite:
        raise _invalido("contatos_excede", f"No máximo {limite} contatos por setor além do proprietário.")
    out: list[dict[str, str]] = []
    vistos: set[str] = set()
    for i, e in enumerate(entradas, start=1):
        setor = str(e.get("setor") or "").strip().lower()
        finalidade = " ".join(str(e.get("finalidade") or "").split())
        nome = " ".join(str(e.get("nome") or "").split())
        if setor not in SETORES:
            raise _invalido("setor_invalido", f"Contato {i}: escolha um setor da lista.")
        if len(finalidade) < FINALIDADE_MIN or len(finalidade) > FINALIDADE_MAX:
            raise _invalido("finalidade_invalida", f"Contato {i}: descreva para que serve (até {FINALIDADE_MAX} letras).")
        if not nome or len(nome) > NOME_MAX:
            raise _invalido("nome_invalido", f"Contato {i}: informe o nome (até {NOME_MAX} letras).")
        if (setor, finalidade) == (SETOR_DONO, FINALIDADE_DONO):
            raise _invalido("finalidade_reservada", f"Contato {i}: essa descrição é reservada ao proprietário.")
        telefone = normalize_phone(str(e.get("telefone") or ""))
        if telefone is None:
            raise _invalido("telefone_invalido", f"Contato {i}: telefone inválido. Use DDD + número, ex.: (11) 99999-9999.")
        if telefone in vistos:
            raise _invalido("telefone_duplicado", f"Contato {i}: esse telefone já está na lista.")
        vistos.add(telefone)
        out.append({"setor": setor, "finalidade": finalidade, "nome": nome, "telefone": telefone})
    return out


def serializar(entradas: list[dict[str, str]]) -> str:
    """The spec value (`""` clears the spec)."""
    return json.dumps(entradas, ensure_ascii=False, separators=(",", ":")) if entradas else ""


def ler_valor(valor: Optional[str]) -> tuple[list[dict[str, str]], list[str]]:
    """`(entries, legado)` from the stored value: entries of the JSON list, else the legacy comma/newline items as `legado`."""
    texto = (valor or "").strip()
    if not texto:
        return [], []
    try:
        dados = json.loads(texto)
    except ValueError:
        return [], [p.strip() for p in texto.replace("\n", ",").replace(";", ",").split(",") if p.strip()]
    if not isinstance(dados, list):
        return [], [texto]
    itens = [
        {k: str(d.get(k) or "") for k in ("setor", "finalidade", "nome", "telefone")} for d in dados if isinstance(d, dict)
    ]
    return itens, []


def dono_da_org(core: Any, org_id: UUID | str) -> Optional[dict[str, str]]:
    """The derived first entry: the org's owner (first by id) WITH a valid number in their profile, else None."""
    ids = donos_da_org(core, org_id)
    usuarios = usuarios_da_org(core, org_id, ids)
    for uid in ids:
        u = usuarios.get(uid)
        if u and u.get("telefone"):
            return {
                "setor": SETOR_DONO, "finalidade": FINALIDADE_DONO, "nome": str(u.get("nome") or "Proprietário"),
                "telefone": str(u["telefone"]), "origem": "perfil",
            }
    return None


def _e_o_dono(e: dict[str, str]) -> bool:
    return (e.get("setor"), e.get("finalidade")) == (SETOR_DONO, FINALIDADE_DONO)


def montar(valor: Optional[str], dono: Optional[dict[str, str]]) -> dict[str, Any]:
    """The GET body: `{dono, contatos, legado, ha_dono_sem_telefone}`. The derived owner entry is dropped from the editable list."""
    entradas, legado = ler_valor(valor)
    return {
        "dono": dono, "contatos": [e for e in entradas if not _e_o_dono(e)], "legado": legado,
        "setores": list(SETORES), "maximo": MAX_TOTAL,
    }


def valor_a_salvar(entradas: list[dict[str, str]], dono: Optional[dict[str, str]]) -> str:
    base = ([{k: dono[k] for k in ("setor", "finalidade", "nome", "telefone")}] if dono else []) + entradas
    return serializar(base)


def registrar_evento(client: Any, org_id: UUID | str, ator_id: str, *, total: int, com_dono: bool) -> None:
    """EOA / measurement-by-design: one dated `configuracao_alterada` event per save. Counts and ids only: never a name or number."""
    eventos.emitir(client, org_id, "configuracao_alterada", None, {
        "area": "contatos_setoriais", "chaves": [SPEC_CHAVE], "total": total, "com_dono": com_dono, "ator": ator_id,
    })


__all__ = [
    "FINALIDADE_DONO", "MAX_TOTAL", "SETORES", "SETOR_DONO", "SPEC_CHAVE", "dono_da_org", "ler_valor", "montar",
    "registrar_evento", "serializar", "validar", "valor_a_salvar",
]

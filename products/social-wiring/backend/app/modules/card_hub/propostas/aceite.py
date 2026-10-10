"""Aceitar uma proposta — o único caminho de aceite (CONTRACT §4.4).

Uma proposta é um SNAPSHOT de oferta; o gerador de contrato lê UM conjunto vivo
de negociação por `atendimento_id`. Aceitar materializa o snapshot escolhido
nesse conjunto vivo pelos mesmos escritores que a UI usa
(`negociacao_estruturada_service`, `negociacao_service`), de modo que a validação
e o tratamento de FK são os mesmos.

🔴 SEM TRANSAÇÃO. `card_hub` não tem transações: cada `.execute()` é uma
requisição PostgREST. Por isso TODA recusa acontece antes da primeira escrita
(`_recusas`), e cada passo posterior é idempotente — repetir o aceite converge.

Passos (cada um registrado em `passos`):

1. materializar  — falha ABORTA (levanta); a proposta fica como estava.
2. visita        — carimba `visitas.proposta_aceita_em`.
3. contrato      — `iniciar` + imobiliária + testemunhas; guarda `contrato_id`.
4. status        — `aceita` (o índice único parcial garante "uma aceita").
5. funil         — evento `proposta_aceita` (§6; módulo de OUTRA sessão, import tardio).
6. pos_aceite    — certidões + matrícula (§7; import tardio).

Falha nos passos 2-3 ⇒ a proposta NÃO vira `aceita` (4-6 ficam `pulado`).
Falha nos passos 5-6 ⇒ continua `aceita`; a falha é só reportada. Os passos 5-6
nunca desfazem o aceite.

Formato dos refs do snapshot (JSON): `favorecido_ref = "fav:<i>"` (índice na lista
`favorecidos`), `posse_marco_parcela_ref` / `permuta_posse_marco_parcela_ref =
"parcela:<i>"` (índice na lista `parcelas`; mesmo formato que `propostas/schemas.py` valida). Os refs substituem os `*_id` do modelo
vivo, que ainda não existem no momento em que o snapshot é escrito.
"""
from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ValidationError
from noctusai_lib.primitives.exceptions import AppException, NotFoundError

from app.modules.card_hub import (
    contrato_imobiliaria_service,
    contrato_testemunhas_service,
    contratos_service,
    negociacao_estruturada_service as estruturada,
    negociacao_service,
)
from app.modules.card_hub import services as svc
from app.modules.card_hub.contrato_gerador import service as gerador
from app.modules.card_hub.contrato_gerador.deps import get_politica_contrato
from app.modules.card_hub.contrato_gerador.politica import Politica
from app.modules.card_hub.schemas import (
    FavorecidoCreateBody,
    IntermediarioCreateBody,
    ParcelaCreateBody,
    TermosNegocioPutBody,
)
from app.modules.imovel_hub.busca_service import canonical
from app.services import table_reads
from app.services.documento_store import now_iso

logger = logging.getLogger(__name__)

TABLE = "atendimento_propostas"
VISITAS_TABLE = "visitas"

STATUS_ABERTOS = ("rascunho", "enviada")
STATUS_ACEITA = "aceita"

MODULO_FUNIL = "app.modules.pipeline.funil_eventos"
MODULO_POS_ACEITE = "app.modules.card_hub.pos_aceite_service"
EVENTO_ACEITE = "proposta_aceita"

PASSOS = ("materializar", "visita", "contrato", "status", "funil", "pos_aceite")
MSG_MODULO_INDISPONIVEL = "módulo indisponível"


# ─── refusals (all BEFORE the first write) ────────────────────────────────


class PropostaFechada(AppException):
    def __init__(self, status: str) -> None:
        super().__init__(
            code="proposta_fechada",
            message=f"Só é possível aceitar uma proposta em rascunho ou enviada (status atual: {status}).",
            status_code=409,
            details={"motivo": "proposta_fechada", "status": status},
        )


class PropostaJaAceita(AppException):
    def __init__(self, proposta_id: str) -> None:
        super().__init__(
            code="proposta_ja_aceita",
            message="Outra proposta deste atendimento já foi aceita.",
            status_code=409,
            details={"motivo": "proposta_ja_aceita", "proposta_id": proposta_id},
        )


class ImovelDivergente(AppException):
    def __init__(self, atual: str, proposta: str) -> None:
        super().__init__(
            code="imovel_divergente",
            message=(
                f"A negociação já está no imóvel {atual}; aceitar a proposta de {proposta} "
                "mudaria o imóvel do negócio — altere o imóvel da negociação "
                "explicitamente antes de aceitar."
            ),
            status_code=409,
            details={"motivo": "imovel_divergente", "atual": atual, "proposta": proposta},
        )


class PropostaNaoAceita(AppException):
    def __init__(self, status: str) -> None:
        super().__init__(
            code="proposta_nao_aceita",
            message=f"Esta proposta não está aceita (status atual: {status}).",
            status_code=409,
            details={"motivo": "proposta_nao_aceita", "status": status},
        )


class AtendimentoDivergente(AppException):
    """The cliente's single open atendimento is not the proposta's: the live-set
    writers resolve the atendimento FROM the cliente, so writing would land in
    the wrong deal."""

    def __init__(self) -> None:
        super().__init__(
            code="atendimento_divergente",
            message="O atendimento da proposta não é o atendimento aberto deste cliente.",
            status_code=409,
            details={"motivo": "atendimento_divergente"},
        )


class PropostaSnapshotInvalido(AppException):
    def __init__(self, campos: list[dict]) -> None:
        resumo = "; ".join(f"{e['path']}: {e['mensagem']}" for e in campos[:5])
        super().__init__(
            code="snapshot_invalido",
            message=f"Os termos desta proposta não são válidos — {resumo}",
            status_code=400,
            details={"campos": campos},
        )


# ─── DI seam ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AceitePorts:
    """What the accept reaches for that it does not own.

    `importar` resolves the modules owned by OTHER sessions (funil, pós-aceite)
    lazily, by dotted name — so a missing module is a reported `erro`, not an
    ImportError at boot, and a test substitutes the importer instead of
    patching our own code. `politica` is the contract policy
    (`None` => the production default, the same value `get_politica_contrato`
    injects into the routes)."""

    importar: Callable[[str], Any] = importlib.import_module
    politica: Optional[Politica] = field(default=None)


# ─── helpers ──────────────────────────────────────────────────────────────


def _t(client: Any, name: str):
    return table_reads.table(client, name)


def _passo(passo: str, status: str, mensagem: Optional[str] = None) -> dict:
    return {"passo": passo, "status": status, "mensagem": mensagem}


def _mensagem_de(exc: BaseException) -> str:
    if isinstance(exc, AppException):
        return exc.message
    logger.exception("aceite de proposta: falha inesperada")
    return f"falha inesperada ({type(exc).__name__})"


def _uuid_ou_none(valor: Any) -> Optional[UUID]:
    return UUID(str(valor)) if valor else None


def _ator(valor: Any) -> Optional[str]:
    """The acting user as the house passes it (`getattr(user, "id", None)`) —
    carried as a string, never coerced to UUID: every other card_hub writer
    stores `str(usuario_id)`, and a coercion here 500'd the route for any id
    that is not UUID-shaped before a single refusal could run."""
    return str(valor) if valor else None


def obter_proposta(client: Any, org_id: UUID, atendimento_id: UUID, proposta_id: UUID) -> dict:
    """404 for unknown, other-org and other-atendimento alike (non-distinguishing)."""
    rows = (
        _t(client, TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("id", str(proposta_id))
        .execute()
    ).data or []
    if not rows or str(rows[0].get("atendimento_id")) != str(atendimento_id):
        raise NotFoundError(TABLE, str(proposta_id))
    return rows[0]


def _atualizar_proposta(client: Any, org_id: UUID, proposta_id: UUID, patch: dict) -> dict:
    (
        _t(client, TABLE)
        .update({**patch, "updated_at": now_iso()})
        .eq("org_id", str(org_id))
        .eq("id", str(proposta_id))
        .execute()
    )
    rows = (
        _t(client, TABLE).select("*").eq("org_id", str(org_id)).eq("id", str(proposta_id)).execute()
    ).data or []
    return rows[0]


# ─── snapshot validation (live-set models, never copies) ──────────────────


def _erros_pydantic(prefixo: str, exc: ValidationError) -> list[dict]:
    erros = []
    for e in exc.errors():
        caminho = ".".join(str(parte) for parte in e["loc"])
        campo = f"{prefixo}.{caminho}" if caminho else prefixo
        erros.append({"path": campo, "mensagem": e["msg"]})
    return erros


def _indice_ref(ref: Any, prefixo: str, total: int) -> Optional[int]:
    """`"fav:2"` -> 2; `None` when malformed or out of range."""
    texto = str(ref or "")
    if not texto.startswith(f"{prefixo}:"):
        return None
    try:
        i = int(texto.split(":", 1)[1])
    except ValueError:
        return None
    return i if 0 <= i < total else None


@dataclass
class _Snapshot:
    favorecidos: list[dict]
    intermediarios: list[tuple[dict, Optional[int]]]   # (valores, fav index)
    parcelas: list[tuple[dict, Optional[int], list[Optional[int]]]]  # (valores, fav idx, divisao fav idx)
    termos: dict
    termos_refs: dict[str, Optional[int]]  # campo_id -> parcela index


def _validar_snapshot(row: dict) -> _Snapshot:
    """Validate the proposta's JSON against the models the live writers take.

    Refs are swapped for a placeholder UUID so the SAME model validates the
    rest of the object. Collects every error with its field path."""
    erros: list[dict] = []
    placeholder = uuid4()

    def lista(chave: str) -> list:
        bruto = row.get(chave)
        if bruto is None:
            return []
        if not isinstance(bruto, list):
            erros.append({"path": chave, "mensagem": "deve ser uma lista"})
            return []
        return bruto

    def objeto(item: Any, caminho: str) -> Optional[dict]:
        if not isinstance(item, dict):
            erros.append({"path": caminho, "mensagem": "deve ser um objeto"})
            return None
        return dict(item)

    def validar(modelo: type[BaseModel], dados: dict, caminho: str) -> Optional[dict]:
        try:
            return modelo.model_validate(dados).model_dump()
        except ValidationError as exc:
            erros.extend(_erros_pydantic(caminho, exc))
            return None

    favorecidos_brutos = lista("favorecidos")
    parcelas_brutas = lista("parcelas")

    favorecidos: list[dict] = []
    for i, item in enumerate(favorecidos_brutos):
        d = objeto(item, f"favorecidos.{i}")
        valido = d is not None and validar(FavorecidoCreateBody, d, f"favorecidos.{i}")
        if valido:
            favorecidos.append(valido)

    def resolver_fav(d: dict, caminho: str) -> Optional[int]:
        ref = d.pop("favorecido_ref", None)
        if ref is None:
            if d.get("favorecido_id") is not None:
                # A literal id points into the live set that is about to be
                # replaced — it would dangle. Only snapshot refs are portable.
                erros.append({"path": f"{caminho}.favorecido_id", "mensagem": "use favorecido_ref (fav:<i>)"})
                d.pop("favorecido_id")
            return None
        i = _indice_ref(ref, "fav", len(favorecidos_brutos))
        if i is None:
            erros.append({"path": f"{caminho}.favorecido_ref", "mensagem": f"referência inválida: {ref!r}"})
            return None
        d["favorecido_id"] = str(placeholder)
        return i

    intermediarios: list[tuple[dict, Optional[int]]] = []
    for i, item in enumerate(lista("intermediarios")):
        caminho = f"intermediarios.{i}"
        d = objeto(item, caminho)
        if d is None:
            continue
        fav = resolver_fav(d, caminho)
        valido = validar(IntermediarioCreateBody, d, caminho)
        if valido is not None:
            intermediarios.append((valido, fav))

    parcelas: list[tuple[dict, Optional[int], list[Optional[int]]]] = []
    for i, item in enumerate(parcelas_brutas):
        caminho = f"parcelas.{i}"
        d = objeto(item, caminho)
        if d is None:
            continue
        fav = resolver_fav(d, caminho)
        divisao_favs: list[Optional[int]] = []
        divisao = d.get("favorecidos_divisao")
        if isinstance(divisao, list):
            novos = []
            for j, entrada in enumerate(divisao):
                e = objeto(entrada, f"{caminho}.favorecidos_divisao.{j}")
                if e is None:
                    continue
                divisao_favs.append(resolver_fav(e, f"{caminho}.favorecidos_divisao.{j}"))
                novos.append(e)
            d["favorecidos_divisao"] = novos
        valido = validar(ParcelaCreateBody, d, caminho)
        if valido is not None:
            parcelas.append((valido, fav, divisao_favs))

    termos_bruto = row.get("termos")
    termos_in = dict(termos_bruto) if isinstance(termos_bruto, dict) else {}
    if termos_bruto is not None and not isinstance(termos_bruto, dict):
        erros.append({"path": "termos", "mensagem": "deve ser um objeto"})
    termos_refs: dict[str, Optional[int]] = {}
    for campo_ref, campo_id, campo_marco in (
        ("posse_marco_parcela_ref", "posse_marco_parcela_id", "posse_marco"),
        ("permuta_posse_marco_parcela_ref", "permuta_posse_marco_parcela_id", "permuta_posse_marco"),
    ):
        ref = termos_in.pop(campo_ref, None)
        if termos_in.get(campo_id) is not None:
            erros.append({"path": f"termos.{campo_id}", "mensagem": f"use {campo_ref} (parcela:<i>)"})
            termos_in.pop(campo_id)
        if ref is None:
            if termos_in.get(campo_marco) == "parcela":
                erros.append({"path": f"termos.{campo_ref}", "mensagem": "informe a parcela que marca este momento"})
            continue
        i = _indice_ref(ref, "parcela", len(parcelas_brutas))
        if i is None:
            erros.append({"path": f"termos.{campo_ref}", "mensagem": f"referência inválida: {ref!r}"})
            continue
        termos_in[campo_id] = str(placeholder)
        termos_refs[campo_id] = i
    termos = validar(TermosNegocioPutBody, termos_in, "termos") or {}

    if erros:
        raise PropostaSnapshotInvalido(erros)
    return _Snapshot(favorecidos, intermediarios, parcelas, termos, termos_refs)


def _recusas(
    client: Any, org_id: UUID, atendimento_id: UUID, proposta: dict
) -> _Snapshot:
    """Everything that can refuse, in one place, BEFORE any write."""
    if proposta.get("status") not in STATUS_ABERTOS:
        raise PropostaFechada(str(proposta.get("status")))

    outras = (
        _t(client, TABLE)
        .select("id")
        .eq("org_id", str(org_id))
        .eq("atendimento_id", str(atendimento_id))
        .eq("status", STATUS_ACEITA)
        .execute()
    ).data or []
    outra = next((r for r in outras if str(r["id"]) != str(proposta["id"])), None)
    if outra is not None:
        raise PropostaJaAceita(str(outra["id"]))

    codigo = canonical(str(proposta["imovel_codigo"]))
    atual = negociacao_service.imovel_do_atendimento(client, org_id, atendimento_id)
    if atual and canonical(str(atual)) != codigo:
        raise ImovelDivergente(str(atual), codigo)

    # The writers below resolve the atendimento FROM the cliente — prove they
    # will land on THIS one (AmbiguousAtendimento propagates as its own 409).
    resolvido = svc.resolve_atendimento_id(client, org_id, UUID(str(proposta["cliente_id"])))
    if str(resolvido) != str(atendimento_id):
        raise AtendimentoDivergente()

    return _validar_snapshot(proposta)


# ─── step 1 — materialize ─────────────────────────────────────────────────


def _novo_id(antes: set[str], agregado: dict, chave: str) -> str:
    novos = [r["id"] for r in agregado[chave] if str(r["id"]) not in antes]
    if len(novos) != 1:
        raise RuntimeError(f"não foi possível identificar o registro criado em {chave}")
    return str(novos[0])


def _materializar(
    client: Any, org_id: UUID, proposta: dict, snap: _Snapshot, actor_id: Optional[UUID]
) -> None:
    """REPLACE the atendimento's live negotiation set with the snapshot.

    Wipe-and-rebuild, so a retry after ANY partial failure converges to the same
    state instead of duplicating. The order is dictated by the existing writers:

    a. `valor_negociado` -> NULL first: `criar_parcela`/`remover_parcela` run
       `sincronizar_parcela_intermediaria_derivada`, which would otherwise inject
       a derived intermediária (and eat an `ordem` slot) whenever the old
       deal had a financiamento parcela; with no valor it is a no-op.
    b. termos -> blank: `remover_parcela` 409s on a parcela a termos marco cites.
    c. remove parcelas, intermediários (-> favorecido), favorecidos.
    d. create favorecidos, intermediários, parcelas (refs remapped), termos.
    e. the scalar fields of `atendimento_negociacao` (+ imovel_codigo).
    """
    cliente_id = UUID(str(proposta["cliente_id"]))
    kw = {"usuario_id": actor_id}

    negociacao_service.atualizar(
        client, org_id, cliente_id, valores={"valor_negociado": None}, usuario_id=actor_id
    )
    vivo = estruturada.obter_estruturada(client, org_id, cliente_id)
    estruturada.atualizar_termos(client, org_id, cliente_id, valores={}, **kw)
    for p in vivo["parcelas"]:
        estruturada.remover_parcela(client, org_id, cliente_id, UUID(str(p["id"])))
    for i in vivo["intermediarios"]:
        estruturada.remover_intermediario(client, org_id, cliente_id, UUID(str(i["id"])))
    for f in vivo["favorecidos"]:
        estruturada.remover_favorecido(client, org_id, cliente_id, UUID(str(f["id"])))

    fav_ids: list[str] = []
    for valores in snap.favorecidos:
        antes = {str(r["id"]) for r in estruturada.obter_estruturada(client, org_id, cliente_id)["favorecidos"]}
        agregado = estruturada.criar_favorecido(client, org_id, cliente_id, valores=valores, **kw)
        fav_ids.append(_novo_id(antes, agregado, "favorecidos"))

    def fav_real(indice: Optional[int], atual: Any) -> Any:
        return fav_ids[indice] if indice is not None else atual

    for valores, fav in snap.intermediarios:
        estruturada.criar_intermediario(
            client, org_id, cliente_id,
            valores={**valores, "favorecido_id": fav_real(fav, valores.get("favorecido_id"))}, **kw,
        )

    parcela_ids: list[str] = []
    for valores, fav, divisao_favs in snap.parcelas:
        divisao = [
            {**entrada, "favorecido_id": fav_real(ref, entrada.get("favorecido_id"))}
            for entrada, ref in zip(valores.get("favorecidos_divisao") or [], divisao_favs)
        ]
        antes = {str(r["id"]) for r in estruturada.obter_estruturada(client, org_id, cliente_id)["parcelas"]}
        agregado = estruturada.criar_parcela(
            client, org_id, cliente_id,
            valores={
                **valores,
                "favorecido_id": fav_real(fav, valores.get("favorecido_id")),
                "favorecidos_divisao": divisao,
            },
            **kw,
        )
        parcela_ids.append(_novo_id(antes, agregado, "parcelas"))

    termos = dict(snap.termos)
    for campo_id, indice in snap.termos_refs.items():
        termos[campo_id] = parcela_ids[indice] if indice is not None else None
    estruturada.atualizar_termos(client, org_id, cliente_id, valores=termos, **kw)

    escalares: dict[str, Any] = {
        "valor_negociado": proposta.get("valor_proposto"),
        "imovel_codigo": proposta["imovel_codigo"],
    }
    for campo in ("pct_comissao", "financiamento", "fgts"):
        if proposta.get(campo) is not None:
            escalares[campo] = proposta[campo]
    negociacao_service.atualizar(client, org_id, cliente_id, valores=escalares, usuario_id=actor_id)


# ─── steps 2-3 — visita, contrato ─────────────────────────────────────────


def _carimbar_visita(client: Any, org_id: UUID, proposta: dict, actor_id: Optional[UUID]) -> None:
    rows = (
        _t(client, VISITAS_TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("id", str(proposta["visita_id"]))
        .execute()
    ).data or []
    if not rows or rows[0].get("deleted_at"):
        raise NotFoundError(VISITAS_TABLE, str(proposta["visita_id"]))
    visita = rows[0]
    agora = now_iso()
    patch: dict[str, Any] = {}
    # Migration 104's CHECK: an acceptance needs an offer.
    if visita.get("proposta_em") is None:
        patch["proposta_em"] = agora
        patch["proposta_por"] = str(actor_id) if actor_id else None
    if visita.get("proposta_aceita_em") is None:
        patch["proposta_aceita_em"] = agora
        patch["proposta_aceita_por"] = str(actor_id) if actor_id else None
    if patch:
        _t(client, VISITAS_TABLE).update(patch).eq("org_id", str(org_id)).eq(
            "id", str(proposta["visita_id"])
        ).execute()


def _preparar_contrato(
    client: Any, org_id: UUID, atendimento_id: UUID, proposta: dict,
    actor_id: Optional[UUID], politica: Politica,
) -> tuple[UUID, dict]:
    """Start (or reuse) the contract, preset company + witnesses, return its
    readiness. The `contrato_id` is stored on the proposta the moment it exists,
    so a failure further down resumes on the SAME contract."""
    cliente_id = UUID(str(proposta["cliente_id"]))
    if proposta.get("contrato_id"):
        contrato_id = UUID(str(proposta["contrato_id"]))
        contratos_service.exigir_contrato(client, org_id, atendimento_id, contrato_id)
    else:
        iniciado = gerador.iniciar(client, org_id, cliente_id, usuario_id=actor_id, politica=politica)
        contrato_id = UUID(str(iniciado["contrato"]["id"]))
        _atualizar_proposta(client, org_id, UUID(str(proposta["id"])), {"contrato_id": str(contrato_id)})

    if proposta.get("imobiliaria_id"):
        contrato_imobiliaria_service.definir(
            client, org_id, atendimento_id, contrato_id,
            imobiliaria_id=UUID(str(proposta["imobiliaria_id"])),
        )
    testemunhas = [UUID(str(t)) for t in (proposta.get("testemunha_ids") or [])]
    if testemunhas:
        contrato_testemunhas_service.definir(
            client, org_id, atendimento_id, contrato_id,
            testemunha_ids=testemunhas, usuario_id=actor_id,
        )
    geracao = gerador.obter_geracao(
        client, org_id, cliente_id, contrato_id, usuario_id=actor_id, politica=politica
    )
    return contrato_id, geracao


# ─── steps 5-6 — other sessions' modules (lazy) ───────────────────────────


def _modulo(ports: AceitePorts, nome: str) -> Any:
    """The module, or `None` when it does not exist (yet). Any OTHER import
    failure (the module exists but is broken) propagates as a real `erro`."""
    try:
        return ports.importar(nome)
    except ModuleNotFoundError as exc:
        if exc.name and (nome == exc.name or nome.startswith(f"{exc.name}.")):
            return None
        raise


def _passo_funil(
    ports: AceitePorts, client: Any, org_id: UUID, atendimento_id: UUID, actor_id: Optional[UUID]
) -> dict:
    try:
        mod = _modulo(ports, MODULO_FUNIL)
        mover = getattr(mod, "mover_por_evento", None) if mod else None
        if mover is None:
            return _passo("funil", "erro", MSG_MODULO_INDISPONIVEL)
        resultado = mover(client, org_id, atendimento_id, EVENTO_ACEITE, actor_id) or {}
        if resultado.get("moveu"):
            return _passo("funil", "ok")
        return _passo("funil", "pulado", _motivo_texto(resultado.get("motivo")))
    except Exception as exc:  # noqa: BLE001 — a funnel failure never undoes the accept
        return _passo("funil", "erro", _mensagem_de(exc))


def _passo_pos_aceite(
    ports: AceitePorts, client: Any, org_id: UUID, atendimento_id: UUID, actor_id: Optional[UUID],
    agendador: Any = None,
) -> tuple[dict, Optional[dict]]:
    try:
        mod = _modulo(ports, MODULO_POS_ACEITE)
        disparar = getattr(mod, "disparar", None) if mod else None
        if disparar is None:
            return _passo("pos_aceite", "erro", MSG_MODULO_INDISPONIVEL), None
        resultado = disparar(client, org_id, atendimento_id, actor_id, agendador=agendador)
        if isinstance(resultado, BaseModel):
            resultado = resultado.model_dump(mode="json")
        return _passo("pos_aceite", "ok"), resultado
    except Exception as exc:  # noqa: BLE001 — never undoes the accept; re-runnable
        return _passo("pos_aceite", "erro", _mensagem_de(exc)), None


def _motivo_texto(motivo: Any) -> Optional[str]:
    if motivo is None:
        return None
    if isinstance(motivo, str):
        return motivo
    if isinstance(motivo, (list, tuple)):
        return "; ".join(str(m) for m in motivo)
    return str(motivo)


# ─── public seam ──────────────────────────────────────────────────────────


def aceitar(
    client: Any,
    org_id: UUID,
    atendimento_id: UUID,
    proposta_id: UUID,
    actor_id: Optional[Any],
    *,
    agendador: Any = None,
    ports: Optional[AceitePorts] = None,
) -> dict:
    """Accept the proposta. See the module docstring for the step semantics.

    Raises (before any write) `NotFoundError` 404, `PropostaFechada` /
    `PropostaJaAceita` / `ImovelDivergente` 409, `PropostaSnapshotInvalido` 400,
    or whatever step 1 itself raises. Returns
    `{proposta_row, contrato_id, geracao, pos_aceite, passos}`."""
    ports = ports or AceitePorts()
    actor = _ator(actor_id)
    proposta = obter_proposta(client, org_id, atendimento_id, proposta_id)
    snap = _recusas(client, org_id, atendimento_id, proposta)

    passos: list[dict] = []

    # 1 — materialize. A failure here aborts: the proposta is untouched.
    _materializar(client, org_id, proposta, snap, actor)
    passos.append(_passo("materializar", "ok"))

    # 2 — visita
    falhou_antes_do_status = False
    if proposta.get("visita_id"):
        try:
            _carimbar_visita(client, org_id, proposta, actor)
            passos.append(_passo("visita", "ok"))
        except Exception as exc:  # noqa: BLE001
            falhou_antes_do_status = True
            passos.append(_passo("visita", "erro", _mensagem_de(exc)))
    else:
        passos.append(_passo("visita", "pulado", "proposta sem visita"))

    # 3 — contrato
    contrato_id: Optional[UUID] = None
    geracao: Optional[dict] = None
    try:
        contrato_id, geracao = _preparar_contrato(
            client, org_id, atendimento_id, proposta, actor,
            ports.politica or get_politica_contrato(),
        )
        passos.append(_passo("contrato", "ok"))
    except Exception as exc:  # noqa: BLE001
        falhou_antes_do_status = True
        passos.append(_passo("contrato", "erro", _mensagem_de(exc)))
        # `_preparar_contrato` stores contrato_id as soon as it exists; surface it.
        contrato_id = _uuid_ou_none(_reler(client, org_id, proposta_id).get("contrato_id"))

    if falhou_antes_do_status:
        bloqueio = "bloqueado por falha em passo anterior"
        passos += [
            _passo("status", "pulado", bloqueio),
            _passo("funil", "pulado", bloqueio),
            _passo("pos_aceite", "pulado", bloqueio),
        ]
        return {
            "proposta_row": _reler(client, org_id, proposta_id),
            "contrato_id": str(contrato_id) if contrato_id else None,
            "geracao": geracao, "pos_aceite": None, "passos": passos,
        }

    # 4 — status (the partial UNIQUE index backs "one aceita")
    try:
        agora = now_iso()
        row = _atualizar_proposta(client, org_id, proposta_id, {
            "status": STATUS_ACEITA, "aceita_em": agora,
            "aceita_por": str(actor) if actor else None,
            "updated_por": str(actor) if actor else None,
        })
        passos.append(_passo("status", "ok"))
    except Exception as exc:  # noqa: BLE001
        passos.append(_passo("status", "erro", _mensagem_de(exc)))
        passos += [
            _passo("funil", "pulado", "bloqueado por falha em passo anterior"),
            _passo("pos_aceite", "pulado", "bloqueado por falha em passo anterior"),
        ]
        return {
            "proposta_row": _reler(client, org_id, proposta_id),
            "contrato_id": str(contrato_id) if contrato_id else None,
            "geracao": geracao, "pos_aceite": None, "passos": passos,
        }

    # 5 — funil; 6 — pós-aceite. Neither can undo the accept.
    passos.append(_passo_funil(ports, client, org_id, atendimento_id, actor))
    passo_pos, pos_aceite = _passo_pos_aceite(
        ports, client, org_id, atendimento_id, actor, agendador
    )
    passos.append(passo_pos)

    return {
        "proposta_row": row,
        "contrato_id": str(contrato_id) if contrato_id else None,
        "geracao": geracao,
        "pos_aceite": pos_aceite,
        "passos": passos,
    }


def reexecutar_pos_aceite(
    client: Any,
    org_id: UUID,
    atendimento_id: UUID,
    proposta_id: UUID,
    actor_id: Optional[Any],
    *,
    agendador: Any = None,
    ports: Optional[AceitePorts] = None,
) -> dict:
    """Re-run step 6 for an ALREADY accepted proposta (409 otherwise). Idempotent
    by `pos_aceite_service.disparar`'s own contract (§7.1)."""
    ports = ports or AceitePorts()
    proposta = obter_proposta(client, org_id, atendimento_id, proposta_id)
    if proposta.get("status") != STATUS_ACEITA:
        raise PropostaNaoAceita(str(proposta.get("status")))
    passo, pos_aceite = _passo_pos_aceite(
        ports, client, org_id, atendimento_id, _ator(actor_id), agendador
    )
    return {"proposta_row": proposta, "pos_aceite": pos_aceite, "passos": [passo]}


def _reler(client: Any, org_id: UUID, proposta_id: UUID) -> dict:
    rows = (
        _t(client, TABLE).select("*").eq("org_id", str(org_id)).eq("id", str(proposta_id)).execute()
    ).data or []
    return rows[0]


__all__ = [
    "AceitePorts",
    "AtendimentoDivergente",
    "ImovelDivergente",
    "PropostaFechada",
    "PropostaJaAceita",
    "PropostaNaoAceita",
    "PropostaSnapshotInvalido",
    "aceitar",
    "obter_proposta",
    "reexecutar_pos_aceite",
]

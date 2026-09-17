"""Sincronização (lotes) service — contract §Sincronização, the
manager-confirmed state machine:

    proposto --confirmar--> confirmado --aplicar--> aplicado
       |                        |                 `-> aplicado_parcial
       `--cancelar--> cancelado `--(expira_em)---> expirado

Ban-risk posture (contract §5): `aplicar` is the ONLY code path that
mutates WhatsApp membership, requires `confirmado`, chunks
`LOTE_CHUNK` ids per WAHA call, paces every call on the
`"whatsapp_groups"` rate-limit bucket (never the 5-rps `"whatsapp"`
bucket), and never auto-retries a privacy-refused add (`invite_required`
stays `invite_required` until a human hand-invites).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from noctusai_lib.integrations.rate_limit import acquire_async
from noctusai_lib.integrations.whatsapp.client import WahaGroupError, WahaSessionNotReady
from noctusai_lib.integrations.whatsapp.lid_auth import normalize_phone
from noctusai_lib.integrations.whatsapp.types import ParticipantChangeResult, WhatsAppGroupClient

_GRUPOS = "grupos"
_GRUPO_MEMBROS = "grupo_membros"
_MEMBROS = "membros"
_PLANOS = "planos"
_LOTES = "lotes_sincronizacao"
_LOTE_ITENS = "lote_itens"

_NON_TERMINAL = ("proposto", "confirmado")
_TERMINAL_APLICADO = ("aplicado", "aplicado_parcial")
_RATE_LIMIT_BUCKET = "whatsapp_groups"

_OUTCOME_TO_RESULTADO = {
    "added": "adicionado",
    "removed": "removido",
    "invite_required": "convite_necessario",
    "failed": "falhou",
}


class SincronizacaoServiceError(Exception):
    def __init__(self, detail: str, *, status_code: int = 409) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


class SincronizacaoService:
    def __init__(
        self,
        client: Any,
        *,
        org_id,
        lote_max_itens: int = 20,
        lote_chunk: int = 5,
        lotes_aplicados_max_dia: int = 5,
        lote_expira_horas: int = 24,
    ) -> None:
        self._client = client
        self._org_id = str(org_id)
        self._lote_max_itens = lote_max_itens
        self._lote_chunk = lote_chunk
        self._lotes_aplicados_max_dia = lotes_aplicados_max_dia
        self._lote_expira_horas = lote_expira_horas

    # ── eligibility diff (contract endpoint 8) ──────────────────────────

    def _entitlement_grupo_ids(self, plano: dict | None) -> set[str]:
        if not plano:
            return set()
        entitlements = plano.get("entitlements") or {}
        return {str(g) for g in (entitlements.get("grupos_whatsapp") or [])}

    async def _compute_diff(self, *, grupo_id: str, acao: str) -> tuple[list[dict], list[dict]]:
        """Returns `(itens, ignorados)`. `itens` are proposed lote_itens
        payloads (participante_jid, membro_id); `ignorados` are
        `{membro_id, nome, motivo}` — never silently dropped."""
        membros = (
            self._client.table(_MEMBROS).select("*")
            .eq("org_id", self._org_id).execute().data or []
        )
        planos = (
            self._client.table(_PLANOS).select("*")
            .eq("org_id", self._org_id).execute().data or []
        )
        planos_by_id = {str(p["id"]): p for p in planos if p.get("id")}
        existentes = (
            self._client.table(_GRUPO_MEMBROS).select("*")
            .eq("org_id", self._org_id).eq("grupo_id", str(grupo_id))
            .execute().data or []
        )
        existentes_jids = {row["participante_jid"] for row in existentes}

        itens: list[dict] = []
        ignorados: list[dict] = []

        if acao == "adicionar":
            for membro in membros:
                if membro.get("status") != "ativo":
                    continue
                plano = planos_by_id.get(str(membro.get("plano_id"))) if membro.get("plano_id") else None
                if str(grupo_id) not in self._entitlement_grupo_ids(plano):
                    continue
                telefone = membro.get("telefone")
                if not telefone:
                    ignorados.append({
                        "membro_id": membro["id"], "nome": membro.get("nome"),
                        "motivo": "Sem telefone cadastrado.",
                    })
                    continue
                jid = f"{normalize_phone(telefone)}@c.us"
                if jid in existentes_jids:
                    continue
                itens.append({"participante_jid": jid, "membro_id": membro["id"]})
        else:  # remover
            membros_by_id = {str(m["id"]): m for m in membros}
            for row in existentes:
                membro_id = row.get("membro_id")
                membro = membros_by_id.get(str(membro_id)) if membro_id else None
                if membro is None:
                    itens.append({"participante_jid": row["participante_jid"], "membro_id": None})
                    continue
                plano = planos_by_id.get(str(membro.get("plano_id"))) if membro.get("plano_id") else None
                ainda_elegivel = (
                    membro.get("status") == "ativo"
                    and str(grupo_id) in self._entitlement_grupo_ids(plano)
                )
                if not ainda_elegivel:
                    itens.append({"participante_jid": row["participante_jid"], "membro_id": membro["id"]})

        return itens, ignorados

    # ── create ───────────────────────────────────────────────────────

    async def criar_lote(self, *, grupo_id: str, acao: str, proposto_por) -> dict:
        grupo = (
            self._client.table(_GRUPOS).select("id")
            .eq("org_id", self._org_id).eq("id", str(grupo_id))
            .maybe_single().execute().data
        )
        if not grupo:
            raise SincronizacaoServiceError("Grupo não encontrado.", status_code=404)

        abertos = (
            self._client.table(_LOTES).select("id")
            .eq("org_id", self._org_id).eq("grupo_id", str(grupo_id))
            .in_("estado", list(_NON_TERMINAL))
            .execute().data or []
        )
        if abertos:
            raise SincronizacaoServiceError(
                "Já existe um lote em aberto para esse grupo.", status_code=409,
            )

        itens, ignorados = await self._compute_diff(grupo_id=grupo_id, acao=acao)
        if len(itens) > self._lote_max_itens:
            raise SincronizacaoServiceError(
                f"O lote excede o limite de {self._lote_max_itens} participantes. "
                "Divida em lotes menores.",
                status_code=409,
            )

        now = datetime.now(timezone.utc)
        lote_row = {
            "id": str(uuid4()),
            "org_id": self._org_id,
            "grupo_id": str(grupo_id),
            "acao": acao,
            "estado": "proposto",
            "total_itens": len(itens),
            "proposto_por": str(proposto_por) if proposto_por else None,
            "proposto_em": now.isoformat(),
            "expira_em": (now + timedelta(hours=self._lote_expira_horas)).isoformat(),
        }
        result = self._client.table(_LOTES).insert(lote_row).execute()
        if not result.data:
            raise SincronizacaoServiceError("Falha ao criar lote.", status_code=502)
        lote = result.data[0]

        item_rows = []
        for item in itens:
            row = {
                "id": str(uuid4()), "org_id": self._org_id, "lote_id": lote["id"],
                "membro_id": item["membro_id"], "participante_jid": item["participante_jid"],
                "resultado": "pendente",
            }
            item_rows.append(row)
            self._client.table(_LOTE_ITENS).insert(row).execute()

        return {**lote, "itens": item_rows, "ignorados": ignorados}

    # ── reads ────────────────────────────────────────────────────────

    async def list(
        self, *, grupo_id: str | None = None, estado: str | None = None,
        page: int = 1, page_size: int = 50,
    ) -> dict:
        query = self._client.table(_LOTES).select("*").eq("org_id", self._org_id)
        if grupo_id:
            query = query.eq("grupo_id", grupo_id)
        if estado:
            query = query.eq("estado", estado)
        rows = query.execute().data or []
        rows.sort(key=lambda r: r.get("proposto_em") or "", reverse=True)
        total = len(rows)
        start = (page - 1) * page_size
        return {"items": rows[start:start + page_size], "total": total}

    async def get(self, *, lote_id: str) -> dict | None:
        lote = (
            self._client.table(_LOTES).select("*")
            .eq("org_id", self._org_id).eq("id", str(lote_id))
            .maybe_single().execute().data
        )
        if not lote:
            return None
        itens = self._itens_denormalizados(lote_id=lote_id)
        return {**lote, "itens": itens}

    def _itens_denormalizados(self, *, lote_id: str) -> list[dict]:
        itens = (
            self._client.table(_LOTE_ITENS).select("*")
            .eq("org_id", self._org_id).eq("lote_id", str(lote_id))
            .execute().data or []
        )
        membro_ids = [i["membro_id"] for i in itens if i.get("membro_id")]
        membros_by_id: dict[str, dict] = {}
        if membro_ids:
            membro_rows = (
                self._client.table(_MEMBROS).select("id,nome,telefone")
                .eq("org_id", self._org_id).in_("id", membro_ids)
                .execute().data or []
            )
            membros_by_id = {str(m["id"]): m for m in membro_rows}
        out = []
        for item in itens:
            membro = membros_by_id.get(str(item.get("membro_id"))) if item.get("membro_id") else None
            out.append({
                **item,
                "membro_nome": membro.get("nome") if membro else None,
                "telefone": membro.get("telefone") if membro else None,
            })
        return out

    # ── confirmar ────────────────────────────────────────────────────

    async def confirmar(self, *, lote_id: str, confirmado_por) -> dict:
        lote = (
            self._client.table(_LOTES).select("*")
            .eq("org_id", self._org_id).eq("id", str(lote_id))
            .maybe_single().execute().data
        )
        if not lote:
            raise SincronizacaoServiceError("Lote não encontrado.", status_code=404)
        if lote["estado"] != "proposto":
            raise SincronizacaoServiceError(
                "Esse lote não está aguardando confirmação.", status_code=409,
            )

        expira_em = _parse_dt(lote["expira_em"])
        if expira_em is not None and expira_em <= datetime.now(timezone.utc):
            self._client.table(_LOTES).update({"estado": "expirado"}).eq(
                "org_id", self._org_id,
            ).eq("id", str(lote_id)).execute()
            raise SincronizacaoServiceError(
                "Esse lote expirou. Gere um novo.", status_code=409,
            )

        now = datetime.now(timezone.utc).isoformat()
        result = (
            self._client.table(_LOTES)
            .update({"estado": "confirmado", "confirmado_por": str(confirmado_por) if confirmado_por else None, "confirmado_em": now})
            .eq("org_id", self._org_id).eq("id", str(lote_id))
            .execute()
        )
        return result.data[0] if result.data else lote

    # ── aplicar (the only path that mutates WhatsApp membership) ────────

    async def _lotes_aplicados_hoje(self) -> int:
        rows = (
            self._client.table(_LOTES).select("id,aplicado_em")
            .eq("org_id", self._org_id).in_("estado", list(_TERMINAL_APLICADO))
            .execute().data or []
        )
        today = datetime.now(timezone.utc).date()
        count = 0
        for row in rows:
            dt = _parse_dt(row.get("aplicado_em"))
            if dt is not None and dt.astimezone(timezone.utc).date() == today:
                count += 1
        return count

    async def aplicar(self, *, lote_id: str, waha_client: WhatsAppGroupClient) -> dict:
        lote = (
            self._client.table(_LOTES).select("*")
            .eq("org_id", self._org_id).eq("id", str(lote_id))
            .maybe_single().execute().data
        )
        if not lote:
            raise SincronizacaoServiceError("Lote não encontrado.", status_code=404)

        if lote["estado"] in _TERMINAL_APLICADO:
            # Idempotent re-apply: return unchanged, no cap check, no
            # second WAHA call.
            return {**lote, "itens": self._itens_denormalizados(lote_id=lote_id)}

        if lote["estado"] != "confirmado":
            raise SincronizacaoServiceError(
                "Confirme o lote antes de aplicar.", status_code=409,
            )

        if await self._lotes_aplicados_hoje() >= self._lotes_aplicados_max_dia:
            raise SincronizacaoServiceError(
                "Limite diário de lotes aplicados atingido. Tente novamente amanhã.",
                status_code=429,
            )

        grupo = (
            self._client.table(_GRUPOS).select("*")
            .eq("org_id", self._org_id).eq("id", str(lote["grupo_id"]))
            .maybe_single().execute().data
        )
        itens = (
            self._client.table(_LOTE_ITENS).select("*")
            .eq("org_id", self._org_id).eq("lote_id", str(lote_id))
            .execute().data or []
        )
        pendentes = [i for i in itens if i.get("resultado") == "pendente"]

        all_ok = True
        for start in range(0, len(pendentes), self._lote_chunk):
            chunk = pendentes[start:start + self._lote_chunk]
            jids = [i["participante_jid"] for i in chunk]
            await acquire_async(_RATE_LIMIT_BUCKET)
            try:
                if lote["acao"] == "adicionar":
                    results = await waha_client.add_participants(grupo["chat_id"], jids)
                else:
                    results = await waha_client.remove_participants(grupo["chat_id"], jids)
            except (WahaGroupError, WahaSessionNotReady):
                results = [
                    ParticipantChangeResult(id=jid, outcome="failed", code=None)
                    for jid in jids
                ]
                all_ok = False
            results_by_jid = {r.id: r for r in results}
            now_iso = datetime.now(timezone.utc).isoformat()
            for item in chunk:
                outcome = results_by_jid.get(item["participante_jid"])
                resultado = _OUTCOME_TO_RESULTADO.get(
                    outcome.outcome if outcome else "failed", "falhou",
                )
                if resultado != "adicionado" and resultado != "removido":
                    all_ok = False
                self._client.table(_LOTE_ITENS).update({
                    "resultado": resultado,
                    "codigo_waha": outcome.code if outcome else None,
                    "processado_em": now_iso,
                }).eq("id", item["id"]).execute()

        estado_final = "aplicado" if all_ok else "aplicado_parcial"
        now_iso = datetime.now(timezone.utc).isoformat()
        result = (
            self._client.table(_LOTES)
            .update({"estado": estado_final, "aplicado_em": now_iso})
            .eq("org_id", self._org_id).eq("id", str(lote_id))
            .execute()
        )
        lote_final = result.data[0] if result.data else lote
        return {**lote_final, "itens": self._itens_denormalizados(lote_id=lote_id)}

    # ── cancelar ─────────────────────────────────────────────────────

    async def cancelar(self, *, lote_id: str) -> dict:
        lote = (
            self._client.table(_LOTES).select("*")
            .eq("org_id", self._org_id).eq("id", str(lote_id))
            .maybe_single().execute().data
        )
        if not lote:
            raise SincronizacaoServiceError("Lote não encontrado.", status_code=404)
        if lote["estado"] not in _NON_TERMINAL:
            raise SincronizacaoServiceError(
                "Esse lote não pode ser cancelado.", status_code=409,
            )
        result = (
            self._client.table(_LOTES).update({"estado": "cancelado"})
            .eq("org_id", self._org_id).eq("id", str(lote_id))
            .execute()
        )
        return result.data[0] if result.data else lote

    # ── convites pendentes ───────────────────────────────────────────

    async def convites_pendentes(
        self, *, lote_id: str, waha_client: WhatsAppGroupClient | None = None,
        page: int = 1, page_size: int = 50,
    ) -> dict:
        lote = (
            self._client.table(_LOTES).select("*")
            .eq("org_id", self._org_id).eq("id", str(lote_id))
            .maybe_single().execute().data
        )
        if not lote:
            raise SincronizacaoServiceError("Lote não encontrado.", status_code=404)
        itens = self._itens_denormalizados(lote_id=lote_id)
        pendentes = [i for i in itens if i.get("resultado") == "convite_necessario"]
        pendentes.sort(key=lambda r: r.get("membro_nome") or "")
        total = len(pendentes)
        start = (page - 1) * page_size

        link = None
        if waha_client is not None:
            grupo = (
                self._client.table(_GRUPOS).select("chat_id")
                .eq("org_id", self._org_id).eq("id", str(lote["grupo_id"]))
                .maybe_single().execute().data
            )
            if grupo:
                try:
                    link = await waha_client.get_invite_link(grupo["chat_id"])
                except (WahaGroupError, WahaSessionNotReady):
                    link = None
        return {"items": pendentes[start:start + page_size], "total": total, "link": link}


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None

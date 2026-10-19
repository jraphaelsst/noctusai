"""Maya's daily report to the OWNER (maya-blocks CONTRACT §3.4) -- read-only, owner only.

Two channels, both gated by `supervisao_ativa`, neither ever lead-facing:
- in-app: one `relatorio` julia_evento, `contato_id=None`, payload `{"origem": "supervisao", "dia"}`. The
  notification fan-out (`julia_notificacoes_service`) routes `origem == "supervisao"` to owners ONLY.
- email: `SupervisaoDigestService` (seed `BaseDigestService`) renders the same scorecards; it goes out through
  the seed `EmailSender` seam (Real Resend via `make_email_sender`, `FakeEmailSender` in tests) to the org's
  owners' emails.

Idempotent per (org, dia): the stored `relatorio` event IS the marker -- a re-run of the job the same day finds
it and sends nothing again. The narrative is deterministic (no LLM): Maya's LLM review is a later, owner-paced
slice (CONTRACT §6), and the scorecards carry counts only, no personal data.
"""
from __future__ import annotations

import html
import logging
from datetime import date
from typing import Any, Callable, Optional

from noctusai_lib.domain.digest import BaseDigestService, DigestWindow
from noctusai_lib.integrations.email import EmailSender, OutgoingEmail

from app.modules.atendimento_blocos import repository as blocos_repo
from app.modules.atendimento_blocos.blocos import BLOCOS
from app.modules.supervisao import service as svc
from app.services import julia_eventos_service as eventos

logger = logging.getLogger(__name__)

ORIGEM = "supervisao"
ROTULOS_BLOCO = {b.bloco: b.rotulo for b in BLOCOS}
ROTULOS_METRICA = {
    "leads_entrada": "Leads de entrada", "tpr_n": "Episódios respondidos", "tpr_p50_s": "Tempo de 1ª resposta (p50)",
    "tpr_p90_s": "Tempo de 1ª resposta (p90)", "tpr_sem_resposta": "Episódios sem resposta",
    "qualificados": "Qualificados", "qualificacao_taxa": "Taxa de qualificação", "frios": "Frios",
    "frio_taxa": "Taxa de frios", "invalidos": "Inválidos", "invalido_taxa": "Taxa de inválidos",
    "entregas_manuais": "Entregas manuais", "envios_bloqueados": "Envios bloqueados",
    "envios_bloqueados_por_motivo": "Bloqueios por motivo", "handoffs_humanos": "Handoffs para humano",
    "handoffs_humanos_por_motivo": "Handoffs por motivo", "handoffs_emitidos": "Handoffs emitidos",
    "handoffs_nao_assumidos": "Handoffs não assumidos", "horas_para_assumir": "Prazo para assumir (h)",
    "handoffs_recebidos": "Handoffs recebidos", "handoffs_assumidos": "Handoffs assumidos",
    "assumir_p50_s": "Tempo para assumir (p50)", "assumir_p90_s": "Tempo para assumir (p90)",
    "tpr_humano_n": "Episódios respondidos por pessoa", "tpr_humano_p50_s": "Tempo de 1ª resposta humana (p50)",
    "tpr_humano_p90_s": "Tempo de 1ª resposta humana (p90)",
    "respondidos_por_humano_antes_do_agente": "Respondidos por pessoa antes da Julia",
    "falhas_registro": "Falhas de registro da supervisão", "dados_incompletos": "Dados incompletos",
}
SEM_DADO = "sem dado"


def formatar(chave: str, valor: Any) -> str:
    """Human rendering; `None` is shown as missing, never as 0."""
    if valor is None:
        return SEM_DADO
    if chave.endswith("_taxa"):
        return f"{valor * 100:.1f}%"
    if chave.endswith("_s"):
        segundos = float(valor)
        return f"{segundos:.0f}s" if segundos < 120 else f"{segundos / 60:.1f} min"
    if isinstance(valor, bool):
        return "sim" if valor else "não"
    if isinstance(valor, dict):
        return ", ".join(f"{k}: {v}" for k, v in sorted(valor.items())) or "nenhum"
    return str(valor)


class SupervisaoDigestService(BaseDigestService):
    """The owner's daily supervision email. `window.extra["dia"]` is the SP day reported."""

    async def _fetch_window(self, window: DigestWindow) -> dict[str, Any]:
        dia: date = window.extra["dia"]
        return {"dia": dia, "scorecards": svc.listar_scorecards(self.client, self.org_id, dia)}

    def _aggregate(self, raw: dict[str, Any]) -> dict[str, Any]:
        return raw

    async def _generate_narrative(self, agg: dict[str, Any], window: DigestWindow) -> str:
        blocos = ", ".join(ROTULOS_BLOCO.get(s["bloco"], s["bloco"]) for s in agg["scorecards"]) or "nenhum bloco"
        texto = f"Scorecards de {agg['dia'].strftime('%d/%m/%Y')} — blocos supervisionados: {blocos}."
        falhas = falhas_do_dia(agg["scorecards"])
        if falhas:
            texto += (f" ATENÇÃO: {falhas} falha(s) de registro da supervisão no dia — os números podem estar incompletos "
                      "(o atendimento em si não foi afetado).")
        return texto

    def _render_bodies(self, agg: dict[str, Any], narrative: str) -> tuple[str, str]:
        texto = [narrative, ""]
        partes = [f"<div style='font-family:Arial,sans-serif;max-width:640px'><p>{html.escape(narrative)}</p>"]
        for s in agg["scorecards"]:
            titulo = f"{ROTULOS_BLOCO.get(s['bloco'], s['bloco'])} — rubrica {s['rubrica_versao']}"
            texto.append(titulo)
            partes.append(f"<h3 style='margin:16px 0 4px'>{html.escape(titulo)}</h3><table>")
            for chave, valor in s["metricas"].items():
                rotulo, v = ROTULOS_METRICA.get(chave, chave), formatar(chave, valor)
                texto.append(f"  {rotulo}: {v}")
                partes.append(f"<tr><td style='padding:2px 12px 2px 0'>{html.escape(rotulo)}</td>"
                              f"<td><strong>{html.escape(v)}</strong></td></tr>")
            partes.append("</table>")
            texto.append("")
        link = f"/supervisao?dia={agg['dia'].isoformat()}"
        texto.append(f"Detalhes: {link}")
        partes.append(f"<p><a href='{html.escape(link, quote=True)}'>Ver na Supervisão</a></p></div>")
        return "".join(partes), "\n".join(texto)

    def _build_subject(self, agg: dict[str, Any], window: DigestWindow) -> str:
        return f"[Supervisão] Relatório de {agg['dia'].strftime('%d/%m/%Y')}"


def falhas_do_dia(scorecards: list[dict[str, Any]]) -> int:
    """G4: the day's supervision-hook failures (every scorecard of the org carries the same org-wide count)."""
    return max((int((s.get("metricas") or {}).get("falhas_registro") or 0) for s in scorecards), default=0)


def emails_dos_donos(core: Any, org_id: Any) -> list[str]:
    rows = (core.table("noctus_users").select("id,email,org_role,org_id").eq("org_id", str(org_id))
            .eq("org_role", "owner").limit(100).execute().data or [])
    return sorted({str(r["email"]) for r in rows if r.get("email") and r.get("org_role") == "owner"})


def _ja_enviado(client: Any, org_id: Any, dia: date) -> bool:
    rows = (client.table(eventos.TABLE).select("id").eq("org_id", str(org_id)).eq("tipo", "relatorio")
            .contains("payload", {"origem": ORIGEM, "dia": dia.isoformat()}).limit(1).execute().data or [])
    return bool(rows)


def sender_padrao() -> Optional[EmailSender]:
    """The Real Resend sender through the seed factory, or None when Resend is not configured (never a Fake in
    production -- a Fake would report the owner's email as sent)."""
    from app.config import settings
    from app.modules.email_marketing.services.email_optin import build_confirmation_sender

    return build_confirmation_sender(settings)


async def enviar_relatorio(client: Any, core: Any, org_id: Any, dia: date, *,
                           sender_factory: Callable[[], Optional[EmailSender]] = sender_padrao) -> dict[str, Any]:
    """Emit the owner's in-app report + email for `dia`. Returns what happened (for logs / tests)."""
    if not blocos_repo.ler_supervisao(client, org_id)["supervisao_ativa"]:
        return {"status": "supervisao_desligada"}
    if _ja_enviado(client, org_id, dia):
        return {"status": "ja_enviado"}
    if not svc.listar_scorecards(client, org_id, dia):
        logger.info("supervisao: no scorecard for org=%s dia=%s -- no report", org_id, dia)
        return {"status": "sem_scorecards"}
    digest_svc = SupervisaoDigestService(client=client, org_id=str(org_id))
    resultado = await digest_svc.run(DigestWindow(org_id=str(org_id), extra={"dia": dia}))
    falhas = falhas_do_dia(svc.listar_scorecards(client, org_id, dia))
    evento = eventos.emitir(client, org_id, "relatorio", None,
                            {"origem": ORIGEM, "dia": dia.isoformat(), "falhas_registro": falhas})
    if evento is None:
        logger.error("supervisao: report event NOT written (org=%s dia=%s) -- email withheld to retry next run",
                     org_id, dia)
        return {"status": "evento_falhou"}
    destinatarios = emails_dos_donos(core, org_id)
    if not destinatarios:
        logger.warning("supervisao: org=%s has no owner email -- report emailed to nobody", org_id)
        return {"status": "enviado", "emails": 0}
    sender = sender_factory()
    if sender is None:
        logger.warning("supervisao: email not configured (Resend) -- org=%s dia=%s report is in-app only", org_id, dia)
        return {"status": "enviado", "emails": 0, "email": "nao_configurado"}
    d = resultado.digest
    enviados = 0
    for to in destinatarios:
        try:
            await sender.send(OutgoingEmail(to=[to], subject=d.subject, html=d.html, text=d.text))
            enviados += 1
        except Exception:
            logger.exception("supervisao: owner report email failed (org=%s dia=%s)", org_id, dia)
    return {"status": "enviado", "emails": enviados}


__all__ = ["ORIGEM", "SupervisaoDigestService", "emails_dos_donos", "enviar_relatorio", "falhas_do_dia", "formatar"]

"""The ``relatorio`` of a hand-off / conclusion (Julia v3, CONTRACT §12.4).

ONE extra LLM call -- the same generator behind ``POST /api/channels/threads/{id}/resumo`` (``extracao``'s summary
tool + the content rows ``resumo.*`` / ``registrar_resumo``) -- plus everything else DETERMINISTIC from the records:
the lead's profile in readable form, the properties offered (with their link when this turn's SW results carried
one) and the lead's reaction, up to 3 recommendations (liked first), the visit options the LEAD gave (Julia never
schedules), identification FLAGS (never a value), the reason and the next steps.

The LLM is a seam (:data:`ResumoFactory`): production wires :func:`gerador_resumo_llm`, tests a
:class:`FakeResumoRelatorio`. Generation failure never blocks the hand-off: ``texto`` is then built from the
structured fields with ``resumo_conversa = None`` and a ``relatorio:degradado`` thread event is booked.

NOC-REMEDIATE[relatorio-rotulos-em-linhas]: the staff-facing labels of ``texto`` are code constants here (the
report is for the owner/broker, never model-visible); they belong in ``agent_version_textos`` rows like every other
text -- 2026-11-03
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any
from uuid import UUID

from app.channels import extracao
from app.channels.texto_seguro import ROTULO_RESUMO_IA, para_equipe

logger = logging.getLogger(__name__)

__all__ = [
    "AUDITORIA_DEGRADADO",
    "FakeResumoRelatorio",
    "RELATORIO_TEXTO_MAX",
    "ResumoFactory",
    "gerador_resumo_llm",
    "montar_relatorio",
    "reacao_de",
]

#: Per-field caps of the free text that reaches the owner's phone.
NOME_MAX = 80
CAMPO_MAX = 200
DISPONIBILIDADE_MAX = 240

RELATORIO_TEXTO_MAX = 1500
RESUMO_TIMEOUT_SECONDS = 25.0
#: Thread event code (migration 046 shape ``area:codigo``) booked when the narrative could not be generated.
AUDITORIA_DEGRADADO = "relatorio:degradado"
#: The most properties the report recommends.
RECOMENDADOS_MAX = 3

#: ``() -> resumo narrativo`` -- raises when the generation fails.
ResumoGerador = Callable[[], Awaitable[str]]
#: ``(runtime, versao, conteudo, messages, org_id, thread_id) -> ResumoGerador``
ResumoFactory = Callable[..., ResumoGerador]


def gerador_resumo_llm(
    *, runtime: Any, versao: Any, conteudo: Any, messages: Any, org_id: UUID, thread_id: UUID,
    registros_limite: int = 200,
) -> ResumoGerador:
    """The production generator: the ``/resumo`` call (``runtime.structured_extract`` forced onto the
    ``registrar_resumo`` tool) over the thread's last messages. Its spend is booked on an empty assistant row like
    the route does (the daily cap sums ``custo_usd``)."""

    async def _gerar() -> str:
        records = await asyncio.to_thread(lambda: list(messages.list(org_id, thread_id, limite=registros_limite)))
        system, user = extracao.montar_resumo_pedido(conteudo, records, None)
        tool = extracao.resumo_tool(conteudo)
        async with asyncio.timeout(RESUMO_TIMEOUT_SECONDS):
            raw, usage = await runtime.structured_extract(
                provider=versao.provider, model=versao.model, org_id=org_id, system=system, user=user, tool=tool,
                purpose="summarize")
        shaped = extracao.shape_resumo(raw, extracao.desfechos_oferecidos(conteudo))
        if getattr(usage, "cost_usd", None):
            def _book() -> None:
                row = messages.add(org_id, thread_id, "assistant", "", blocks=[])
                messages.set_turn_cost(
                    org_id, thread_id, row.id, custo_usd=usage.cost_usd, tokens_entrada=usage.prompt_tokens,
                    tokens_saida=usage.completion_tokens)
            await asyncio.to_thread(_book)
        return shaped["resumo"]

    return _gerar


class FakeResumoRelatorio:
    """Test double of the factory: ``FakeResumoRelatorio("texto")(**kw)`` yields a generator returning the text;
    ``falhar=True`` yields one that raises. ``chamadas`` counts the generations."""

    def __init__(self, texto: str = "Resumo narrativo da conversa.", *, falhar: bool = False) -> None:
        self.texto, self.falhar, self.chamadas = texto, falhar, 0

    def __call__(self, **_kw: Any) -> ResumoGerador:
        async def _gerar() -> str:
            self.chamadas += 1
            if self.falhar:
                raise RuntimeError("falha simulada")
            return self.texto
        return _gerar


# ── the deterministic part ──────────────────────────────────────────────────

_GOSTOU = ("gostou", "quer_visitar")


def reacao_de(eventos: Sequence[Any]) -> dict[str, str]:
    """property code -> ``gostou`` | ``nao_gostou`` | ``sem_reacao`` from the lead's events (the LAST reaction wins)."""
    out: dict[str, str] = {}
    for e in eventos:
        if e.evento == "oferecido":
            out.setdefault(e.codigo_imovel, "sem_reacao")
        elif e.evento in _GOSTOU:
            out[e.codigo_imovel] = "gostou"
        elif e.evento == "nao_gostou":
            out[e.codigo_imovel] = "nao_gostou"
    return out


def _valor_legivel(criterio: Any, valor: Any) -> str:
    if isinstance(valor, bool):
        return "sim" if valor else "não"
    if isinstance(valor, Mapping):
        lo, hi = valor.get("min"), valor.get("max")
        if lo is not None and hi is not None:
            return f"{lo} a {hi}"
        if hi is not None:
            return f"até {hi}"
        if lo is not None:
            return f"a partir de {lo}"
        return ", ".join(f"{k}: {v}" for k, v in valor.items())
    rotulos = {o.valor: o.rotulo for o in getattr(criterio, "opcoes", ()) or ()}
    if isinstance(valor, (list, tuple)):
        return ", ".join(rotulos.get(str(v), str(v)) for v in valor)
    return rotulos.get(str(valor), str(valor))


def perfil_legivel(padrao: Any, valores: Mapping[str, Any]) -> dict[str, str]:
    """``{rotulo do critério: valor legível}`` of what is KNOWN (identity and derived criteria are not profile)."""
    out: dict[str, str] = {}
    for c in sorted(padrao.criterios, key=lambda x: (x.ordem, x.chave)):
        if not c.ativo or c.tipo in ("derivado", "identificacao") or c.chave not in valores:
            continue
        v = valores[c.chave]
        if v is None or v == "" or v == [] or v == {}:
            continue
        out[c.rotulo] = _valor_legivel(c, v)
    return out


def _texto(
    *, nome: str | None, telefone: str | None, origem: str | None, resumo: str | None, perfil: Mapping[str, str],
    oferecidos: Sequence[Mapping[str, Any]], recomendados: Sequence[str], disponibilidade: str | None,
    ident: Mapping[str, bool], motivo: str, proximos: str,
) -> str:
    reacao_txt = {"gostou": "gostou", "nao_gostou": "não gostou", "sem_reacao": "sem reação"}

    def bloco(resumo_cortado: str | None) -> str:
        linhas = [f"Relatório Julia — {nome or 'Lead sem nome'}"]
        if telefone:
            linhas.append(f"Telefone: {telefone}")
        if origem:
            linhas.append(f"Origem: {origem}")
        if resumo_cortado:
            linhas += ["", ROTULO_RESUMO_IA, resumo_cortado]
        if perfil:
            linhas += ["", "Perfil: " + "; ".join(f"{k}: {v}" for k, v in perfil.items())]
        if oferecidos:
            linhas += ["", "Imóveis oferecidos:"]
            linhas += [
                f"- {o['codigo']}" + (f" ({o['link']})" if o.get("link") else "") + f" — {reacao_txt[o['reacao']]}"
                for o in oferecidos]
        if recomendados:
            linhas += ["", "Recomendados: " + ", ".join(recomendados)]
        if disponibilidade:
            linhas += ["", f"Disponibilidade para visita (informada pelo lead): {disponibilidade}"]
        recebidos = [k for k, lbl in (("cpf", "CPF"), ("rg", "RG"), ("email", "e-mail"), ("documento_enviado", "documento (foto)"))
                     if ident.get(k)]
        linhas += ["", "Documentos recebidos: " + (", ".join(recebidos) if recebidos else "nenhum")]
        linhas += ["", f"Motivo: {motivo}"]
        if proximos:
            linhas.append(f"Próximos passos: {proximos}")
        return "\n".join(linhas)

    corpo = bloco(resumo)
    if len(corpo) > RELATORIO_TEXTO_MAX and resumo:
        sobra = len(corpo) - RELATORIO_TEXTO_MAX
        corte = max(0, len(resumo) - sobra - 1)
        corpo = bloco((resumo[:corte].rstrip() + "…") if corte else None)
    return corpo if len(corpo) <= RELATORIO_TEXTO_MAX else corpo[: RELATORIO_TEXTO_MAX - 1].rstrip() + "…"


def _proximos_passos(*, intencoes: Sequence[str], disponibilidade: str | None, faltando: Sequence[str]) -> str:
    passos = ["um corretor entra em contato com o lead"]
    if intencoes:
        passos.append("combinar a visita (" + ", ".join(intencoes) + ")" + (" dentro das opções do lead" if disponibilidade else ""))
    if faltando:
        passos.append("obter " + ", ".join(k.upper() if k in ("cpf", "rg") else k for k in faltando))
    return "; ".join(passos).capitalize() + "."


async def montar_relatorio(t: Any, *, motivo: str, perfil: Mapping[str, Any], faltando_ident: Sequence[str]) -> dict[str, Any]:
    """The report of the turn's ``JuliaTurno`` ``t`` (see module docstring). Never raises for a generation failure."""
    eventos = await asyncio.to_thread(t.qual.eventos, t.org_id, t.lead_ref_id)
    reacoes = reacao_de(eventos)
    oferecidos: list[str] = []
    horarios: dict[str, str] = {}
    links = dict(t.links_por_codigo)
    for e in eventos:
        if e.evento == "oferecido":
            if e.codigo_imovel not in oferecidos:
                oferecidos.append(e.codigo_imovel)
            if e.motivo and e.motivo.startswith(("http://", "https://")):  # the offer stores its listing link
                links.setdefault(e.codigo_imovel, e.motivo)
        if e.evento == "quer_visitar" and e.motivo:
            horarios[e.codigo_imovel] = e.motivo
    for a in t.actions:  # this turn's intent not yet read back from the records
        if a.get("type") == "intencao_visita" and a.get("preferencia_horario"):
            horarios[a["codigo"]] = a["preferencia_horario"]
    # the ONLY links that may leave: the listing links a SW tool returned (this turn's, or stored on the offer event)
    permitidos = list(links.values())

    def limpo(valor: object, maximo: int) -> str:
        return para_equipe(valor if isinstance(valor, str) else "", manter_links=permitidos, maximo=maximo)

    lista = [{"codigo": c, "link": links.get(c), "reacao": reacoes.get(c, "sem_reacao")} for c in oferecidos]
    gostados = [c for c in oferecidos if reacoes.get(c) == "gostou"]
    resto = [c for c in oferecidos if reacoes.get(c) == "sem_reacao"]
    recomendados = (gostados + resto)[:RECOMENDADOS_MAX]
    disponibilidade = limpo("; ".join(dict.fromkeys(horarios.values())), DISPONIBILIDADE_MAX) or None

    lead = await asyncio.to_thread(t.threads.get_lead_ref, t.org_id, t.lead_ref_id)
    contato = (getattr(lead, "contato", None) or {})
    nome, telefone = contato.get("nome"), contato.get("telefone_e164")
    # the lead's own phone is the report's header (SW's data, not the lead's text); every free-text field is shaped
    flags = {"cpf": False, "rg": False, "email": False, "documento_enviado": False}
    if t.ident is not None:
        flags.update(await asyncio.to_thread(t.ident.flags, t.org_id, t.lead_ref_id))
        registrado = await asyncio.to_thread(t.ident.nome_registrado, t.org_id, t.lead_ref_id)
        nome = registrado or nome  # the name the lead gave overrides the form's (it may be a business name)
    nome = limpo(nome, NOME_MAX) or None
    origem_sw = getattr(t.estado_sw, "origem", None)
    codigo_camp = getattr(origem_sw, "codigo_imovel_campanha", None)
    partes_origem = [p for p in (getattr(origem_sw, "canal_origem", None), f"imóvel {codigo_camp}" if codigo_camp else None) if p]
    origem = limpo(" — ".join(partes_origem), CAMPO_MAX) or None

    resumo: str | None = None
    if t.resumo_conversa is not None:
        try:
            resumo = limpo(await t.resumo_conversa(), extracao.RESUMO_MAX_CHARS) or None
        except Exception as exc:  # noqa: BLE001 -- never blocks the hand-off: booked + deterministic text below
            logger.warning("agents.channel.relatorio_degradado thread_id=%s cause=%s", t.thread_id, type(exc).__name__)
            if t.auditar is not None:
                try:
                    t.auditar(AUDITORIA_DEGRADADO)
                except Exception:  # noqa: BLE001 -- the second failure is logged too, still never raised
                    logger.exception("agents.channel.relatorio_degradado_nao_auditado thread_id=%s", t.thread_id)
    perfil_leg = {limpo(k, CAMPO_MAX): limpo(v, CAMPO_MAX) for k, v in perfil_legivel(t.padrao, perfil.get("valores") or {}).items()}
    motivo = limpo(motivo, CAMPO_MAX)
    proximos = _proximos_passos(
        intencoes=list(perfil.get("intencoes_visita") or []), disponibilidade=disponibilidade, faltando=list(faltando_ident))
    texto = _texto(
        nome=nome, telefone=telefone, origem=origem, resumo=resumo, perfil=perfil_leg, oferecidos=lista,
        recomendados=recomendados, disponibilidade=disponibilidade, ident=flags, motivo=motivo, proximos=proximos)
    return {
        "texto": texto, "resumo_conversa": resumo, "perfil": perfil_leg, "imoveis_oferecidos": lista,
        "imoveis_recomendados": recomendados, "disponibilidade_visita": disponibilidade,
        "identificacao": {k: bool(flags.get(k)) for k in ("cpf", "rg", "email", "documento_enviado")},
        "motivo": motivo, "proximos_passos": proximos,
    }

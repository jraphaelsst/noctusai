"""Typed formats + universal safety rules of an org's spec VALUE (Julia-line CONTRACT §E1/§E2).

Julia (and every platform agent) is public-facing; the org's business specs arrive from tenants, so they
are UNTRUSTED DATA: validated here, deterministically, and never treated as instructions (the compiler
fences the free-text ones, §E3). Pure functions, no IO.

``validar_valor(tipo, valor, contexto) -> normalized value`` raises :class:`SpecInvalida` carrying every
:class:`Violacao` found. Each violation has a request-level ``codigo`` (the HTTP error code) and a fine
``motivo`` slug:

============================== =====================================================================
``codigo``                     meaning
============================== =====================================================================
``spec_tamanho_excedido``      over the type's cap (``LIMITS['org_spec.valor.<tipo>']``)
``spec_caractere_proibido``    control / zero-width / bidi / private-use / line-separator character
``spec_marcacao_proibida``     ``{{ }}`` ``{% %}`` ``${``, tags, code fences, headings, role markers
``spec_fora_do_tipo``          a URL / e-mail / phone number inside a free-text value
``spec_formato_invalido``      the value does not match its type's grammar (``motivo`` says which rule)
``spec_dominio_nao_permitido`` a ``url`` whose host is not in ``dominios_permitidos`` / the public hosts
``spec_parece_instrucao``      pt+en instruction-likeness lint (a spec describes the org, it never commands)
============================== =====================================================================
"""
from __future__ import annotations

import ipaddress
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Sequence

from app.studio.models import LIMITS, SPEC_TIPOS, SPEC_TIPOS_TEXTO_LIVRE

__all__ = [
    "ContextoSpec", "SpecInvalida", "Violacao", "dividir_itens", "e_texto_livre", "itens_da_lista", "validar_valor",
]

# ── model ───────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Violacao:
    codigo: str
    motivo: str
    mensagem: str
    chave: str = ""

    def to_dict(self) -> dict[str, str]:
        return {"chave": self.chave, "codigo": self.codigo, "motivo": self.motivo, "mensagem": self.mensagem}


class SpecInvalida(ValueError):
    def __init__(self, violacoes: Sequence[Violacao]):
        self.violacoes = tuple(violacoes)
        super().__init__("; ".join(v.mensagem for v in self.violacoes))

    @property
    def codigo(self) -> str:
        return self.violacoes[0].codigo


@dataclass(frozen=True)
class ContextoSpec:
    """What a ``url`` is checked against: the org's own ``dominios_permitidos`` + the platform's public hosts."""

    dominios_permitidos: tuple[str, ...] = ()
    hosts_publicos: tuple[str, ...] = ()


def e_texto_livre(tipo: str) -> bool:
    return tipo in SPEC_TIPOS_TEXTO_LIVRE


# ── universal rules (every type) ────────────────────────────────────────────

_CATEGORIAS_PROIBIDAS = frozenset({"Cc", "Cf", "Co", "Cs", "Cn", "Zl", "Zp"})
_TEMPLATE = re.compile(r"\{\{|\}\}|\{%|%\}|\$\{|<%|%>")
_TAG = re.compile(r"<\s*[A-Za-z/!?|]|\[/?(?:INST|SYS|SYSTEM)\]|<\|")
_FENCE = re.compile(r"```|~~~")
_TITULO = re.compile(r"(?m)^[ \t]*#{1,6}(?:\s|$)|^[ \t]*(?:={3,}|-{3,})[ \t]*$")
_PAPEL = re.compile(
    r"(?im)(?:^|[\n.;!?])[ \t]*(?:system|assistant|user|human|ai|developer|tool|sistema|assistente|usu[aá]rio|humano)[ \t]*:")


def _normalizar(valor: str) -> str:
    return unicodedata.normalize("NFKC", valor).replace("\r\n", "\n").replace("\r", "\n").strip()


def _universais(valor: str, *, permite_quebra: bool) -> list[Violacao]:
    out: list[Violacao] = []
    for ch in valor:
        if ch == "\n" and permite_quebra:
            continue
        cat = unicodedata.category(ch)
        if cat in _CATEGORIAS_PROIBIDAS:
            out.append(Violacao(
                "spec_caractere_proibido", "caractere_de_controle",
                f"caractere não permitido (U+{ord(ch):04X}, {cat}): controle, largura-zero, bidirecional e separadores são recusados.",
            ))
            break
    if _TEMPLATE.search(valor):
        out.append(Violacao("spec_marcacao_proibida", "template", "marcadores de template ({{ }}, {% %}, ${) não são permitidos."))
    if _TAG.search(valor):
        out.append(Violacao("spec_marcacao_proibida", "tag", "tags (<...>) e marcadores de papel de modelo não são permitidos."))
    return out


def _marcacao_texto(valor: str) -> list[Violacao]:
    out: list[Violacao] = []
    if _FENCE.search(valor):
        out.append(Violacao("spec_marcacao_proibida", "bloco_de_codigo", "blocos de código (``` / ~~~) não são permitidos."))
    if _TITULO.search(valor):
        out.append(Violacao("spec_marcacao_proibida", "titulo_markdown", "títulos markdown (#) não são permitidos."))
    if _PAPEL.search(valor):
        out.append(Violacao("spec_marcacao_proibida", "marcador_de_papel", "marcadores de papel (system:, assistant:, usuário:) não são permitidos."))
    return out


# ── free text: no URL / phone / e-mail; instruction-likeness lint ───────────

_TLDS = "|".join((
    "com", "net", "org", "io", "app", "dev", "br", "info", "xyz", "link", "ly", "me", "co", "site", "online", "store",
    "gov", "edu", "ai", "tv", "to", "gl", "biz", "cc", "ws", "top", "shop", "page", "cloud",
))
_URL_TEXTO = re.compile(
    rf"(?i)(?:\b(?:https?|ftp|file|data|javascript|mailto|tel|wa)\s*:|\bwww\.|\b[a-z0-9][a-z0-9-]*(?:\.[a-z0-9-]+)*\.(?:{_TLDS})\b|\S+@\S+\.\S+)")
_TELEFONE = re.compile(r"(?<![\d.])(?:\+?55[\s.-]?)?\(?\d{2}\)?[\s.-]?9?\d{4}[\s.-]?\d{4}(?!\d)|\d{10,}")


def _fora_do_tipo(valor: str) -> list[Violacao]:
    out: list[Violacao] = []
    if _URL_TEXTO.search(valor):
        out.append(Violacao("spec_fora_do_tipo", "url_ou_email_em_texto", "links, domínios e e-mails só são aceitos em campos do tipo url, dominios ou contatos."))
    for m in _TELEFONE.finditer(valor):
        if re.search(r"R\$\s*$", valor[max(0, m.start() - 4):m.start()]):
            continue
        out.append(Violacao("spec_fora_do_tipo", "telefone_em_texto", "telefones só são aceitos em campos do tipo contatos."))
        break
    return out


_INSTRUCAO: tuple[re.Pattern[str], ...] = tuple(re.compile(p, re.I) for p in (
    # pt
    r"\b(ignor[ae]r?|desconsider[ae]r?|esque[cç]a|desobede[cç]a|substitua|sobrescrev[ae]|anule|abandone)\b[^.\n]{0,50}\b(instru[cç][oõ]es|regras|prompt|diretrizes|comandos|ordens|orienta[cç][oõ]es)",
    r"\b(a partir de agora|de agora em diante|daqui (?:pra|para) frente|novas? instru[cç][oõ]es|nova persona|novo papel)\b",
    r"\bvoc[eê]\s+(?:deve|dever[aá]|agora|[eé]\s+um|ser[aá]|precisa|tem que|n[aã]o pode)\b",
    r"\b(?:n[aã]o|nunca|jamais)\s+(?:responda|diga|fale|mencione|revele|informe|transfira|encaminhe|obede[cç]a)\b",
    r"\b(?:sempre|apenas|somente|s[oó])\s+(?:responda|diga|fale|envie|recomende|ofere[cç]a)\b",
    r"\b(?:responda|reponda|revele|mostre|exiba|imprima|repita|envie|encaminhe|finja|aja|atue|comporte-se|haja|obede[cç]a|execute|fa[cç]a)\s+(?:que|como|assim|o\s+seguinte|todos?|qualquer|tudo|isto|isso|seu|sua|suas|seus|a\s+seguir|me|para|pra)\b",
    r"\b(?:prompt do sistema|prompt de sistema|instru[cç][oõ]es do sistema|mensagem do sistema|suas instru[cç][oõ]es|seu prompt)\b",
    r"\b(?:finja|finge|aja como|atue como|haja como|comporte-se como|fa[cç]a de conta)\b",
    # en
    r"\b(?:ignore|disregard|forget|override|bypass|discard)\b[^.\n]{0,50}\b(?:instructions?|rules?|prompts?|guidelines?|directives?|polic(?:y|ies)|everything|above|previous)",
    r"\b(?:you\s+(?:are\s+now|must|should|will|shall|have\s+to|need\s+to)|from\s+now\s+on|new\s+instructions?|act\s+as|pretend\s+(?:to|you)|role-?play|behave\s+as)\b",
    r"\b(?:system\s+prompt|developer\s+message|reveal\s+(?:your|the)|jailbreak|do\s+anything\s+now|dan\s+mode|prompt\s+injection)\b",
    r"\b(?:always|never|only)\s+(?:say|respond|answer|reply|tell|output|print|reveal|recommend)\b",
    r"\b(?:respond|reply|answer|output|print|say|repeat|send)\s+(?:only\s+)?(?:with|that|the\s+following|exactly)\b",
))


def _parece_instrucao(valor: str) -> list[Violacao]:
    if any(rx.search(valor) for rx in _INSTRUCAO):
        return [Violacao(
            "spec_parece_instrucao", "instrucao",
            "o texto parece uma instrução para o assistente; informe apenas dados sobre a organização (nomes, regiões, horários).")]
    return []


# ── typed grammars ──────────────────────────────────────────────────────────

_SEP_ITENS = re.compile(r"[\n;,]+")


def dividir_itens(valor: str) -> list[str]:
    """Items of a ``lista`` / ``dominios`` / ``contatos`` value: separated by newline, ``;`` or ``,``."""
    return [p.strip() for p in _SEP_ITENS.split(valor) if p.strip()]


itens_da_lista = dividir_itens


def _invalido(motivo: str, mensagem: str) -> Violacao:
    return Violacao("spec_formato_invalido", motivo, mensagem)


_SUFIXOS_PUBLICOS = frozenset({
    "com.br", "net.br", "org.br", "gov.br", "edu.br", "mil.br", "art.br", "eco.br", "adv.br", "blog.br", "app.br",
    "co.uk", "org.uk", "ac.uk", "gov.uk", "com.ar", "com.pt", "com.mx", "com.au", "co.jp", "co.za", "com.co", "co.in",
})
_ENCURTADORES = frozenset({
    "bit.ly", "bitly.com", "tinyurl.com", "t.co", "goo.gl", "ow.ly", "is.gd", "buff.ly", "rebrand.ly", "cutt.ly",
    "shorturl.at", "tiny.cc", "t.ly", "rb.gy", "lnkd.in", "wa.me", "s.id", "v.gd", "shre.ly", "clck.ru",
})
_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def _host_valido(host: str) -> tuple[str | None, str | None]:
    """``(normalized ascii host, None)`` or ``(None, motivo)``."""
    host = host.strip().lower().rstrip(".")
    if not host or "*" in host:
        return None, "curinga_ou_vazio"
    try:
        ipaddress.ip_address(host.strip("[]"))
        return None, "ip"
    except ValueError:
        pass
    try:
        ascii_host = host.encode("idna").decode("ascii")
    except UnicodeError:
        return None, "idna"
    labels = ascii_host.split(".")
    if len(labels) < 2 or not all(_LABEL.match(lb) for lb in labels):
        return None, "hostname"
    tld = labels[-1]
    if not (tld.startswith("xn--") or (tld.isalpha() and len(tld) >= 2)):
        return None, "tld"
    if ascii_host in _SUFIXOS_PUBLICOS:
        return None, "sufixo_publico"
    return ascii_host, None


def _url(valor: str, ctx: ContextoSpec) -> tuple[str, list[Violacao]]:
    if re.search(r"\s", valor):
        return valor, [_invalido("url_espaco", "a URL não pode conter espaços.")]
    # Parsed by hand on purpose: this module sits on the channel-turn path, where no HTTP-capable library
    # (urllib included) may be imported -- Julia validates a URL's shape, she never fetches one.
    m = re.match(r"(?i)^([a-z][a-z0-9+.-]*):(?://([^/?#]*))?", valor)
    if not m or m.group(1).lower() != "https" or m.group(2) is None:
        return valor, [_invalido("url_nao_https", "apenas URLs https:// são aceitas.")]
    autoridade = m.group(2)
    if "@" in autoridade:
        return valor, [_invalido("url_userinfo", "a URL não pode conter usuário/senha (user@host).")]
    hostname, _, porta = autoridade.rpartition(":") if re.search(r":\d*$", autoridade) and not autoridade.startswith("[") else (autoridade, "", "")
    if porta not in ("", "443"):
        return valor, [_invalido("url_porta", "a URL não pode usar porta diferente de 443.")]
    if hostname.startswith("["):
        return valor, [_invalido("url_host_ip", "o endereço precisa de um domínio público válido (sem IP, curinga ou sufixo solto).")]
    host, motivo = _host_valido(hostname)
    if host is None:
        return valor, [_invalido(f"url_host_{motivo}", "o endereço precisa de um domínio público válido (sem IP, curinga ou sufixo solto).")]
    if host in _ENCURTADORES:
        return valor, [_invalido("url_encurtador", "encurtadores de link não são aceitos; informe o endereço completo.")]
    permitidos = {h.lower() for h in (*ctx.dominios_permitidos, *ctx.hosts_publicos) if h}
    if not any(host == d or host.endswith("." + d) for d in permitidos):
        return valor, [Violacao(
            "spec_dominio_nao_permitido", "url_dominio_fora_da_lista",
            f"o domínio '{host}' não está em dominios_permitidos da organização (nem entre os domínios públicos da plataforma).")]
    return valor, []


def _dominios(valor: str) -> tuple[str, list[Violacao]]:
    itens = dividir_itens(valor.replace("\n", ","))
    if not itens:
        return valor, [_invalido("dominios_vazio", "informe ao menos um domínio.")]
    if len(itens) > 10:
        return valor, [_invalido("dominios_excede", "no máximo 10 domínios.")]
    out: list[str] = []
    for it in itens:
        if re.search(r"[/:@\s?#]", it):
            return valor, [_invalido("dominio_com_caminho", f"'{it}': informe só o domínio (sem https://, caminho ou espaços).")]
        host, motivo = _host_valido(it.lstrip("."))
        if host is None:
            return valor, [_invalido(f"dominio_{motivo}", f"'{it}' não é um domínio válido (sem curinga, IP ou sufixo público solto).")]
        if host not in out:
            out.append(host)
    return ", ".join(out), []


_EMAIL = re.compile(r"^[a-z0-9._%+-]{1,64}@[a-z0-9-]+(?:\.[a-z0-9-]+)+$")


def _contatos(valor: str) -> tuple[str, list[Violacao]]:
    itens = dividir_itens(valor)
    if not itens:
        return valor, [_invalido("contatos_vazio", "informe ao menos um contato.")]
    if len(itens) > 10:
        return valor, [_invalido("contatos_excede", "no máximo 10 contatos.")]
    out: list[str] = []
    for it in itens:
        baixo = it.lower()
        if "@" in baixo:
            if len(baixo) > 254 or not _EMAIL.match(baixo):
                return valor, [_invalido("contato_email", f"'{it}' não é um e-mail válido.")]
            out.append(baixo)
            continue
        if not re.fullmatch(r"\+?[\d\s().-]+", it):
            return valor, [_invalido("contato_formato", f"'{it}' não é um telefone (E.164) nem e-mail.")]
        d = re.sub(r"\D", "", it)
        if it.lstrip().startswith("+"):
            e164 = "+" + d
        elif len(d) in (10, 11):
            e164 = "+55" + d
        elif len(d) in (12, 13) and d.startswith("55"):
            e164 = "+" + d
        else:
            e164 = "+" + d
        if not re.fullmatch(r"\+[1-9]\d{7,14}", e164):
            return valor, [_invalido("contato_e164", f"'{it}' não é um telefone E.164 válido (ex.: +5511992694172).")]
        out.append(e164)
    return ", ".join(dict.fromkeys(out)), []


def _cnpj(valor: str) -> tuple[str, list[Violacao]]:
    if not re.fullmatch(r"[\d./\-\s]+", valor):
        return valor, [_invalido("cnpj_caracteres", "CNPJ só aceita dígitos, ponto, barra e hífen.")]
    d = re.sub(r"\D", "", valor)
    if len(d) != 14 or len(set(d)) == 1:
        return valor, [_invalido("cnpj_tamanho", "CNPJ precisa de 14 dígitos válidos.")]

    def dv(base: str) -> str:
        pesos = ([5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2] if len(base) == 12 else [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
        r = sum(int(c) * p for c, p in zip(base, pesos)) % 11
        return str(0 if r < 2 else 11 - r)

    d1 = dv(d[:12])
    d2 = dv(d[:12] + d1)
    if d[12:] != d1 + d2:
        return valor, [_invalido("cnpj_digito", "CNPJ com dígitos verificadores inválidos.")]
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}", []


_CRECI = re.compile(r"^(?:CRECI(?:[\s/-]*([A-Z]{2}))?[\s:.-]*)?(\d{3,7})(?:[\s/-]*([FJ]))?$")


def _creci(valor: str) -> tuple[str, list[Violacao]]:
    m = _CRECI.match(re.sub(r"\s+", " ", valor.upper()).strip())
    if not m:
        return valor, [_invalido("creci_padrao", "CRECI no formato 'CRECI/SP 12345-J' (UF e F/J opcionais).")]
    uf, num, tipo = m.groups()
    return "CRECI" + (f"/{uf}" if uf else "") + f" {num}" + (f"-{tipo}" if tipo else ""), []


_DIAS = {"seg": 0, "ter": 1, "qua": 2, "qui": 3, "sex": 4, "sab": 5, "sáb": 5, "dom": 6}
_NOMES_DIA = ("seg", "ter", "qua", "qui", "sex", "sab", "dom")
_HORA = r"([01]?\d|2[0-3])(?::([0-5]\d)|h([0-5]\d)?)"
_SEG_HORARIO = re.compile(
    rf"^([a-zçá]{{3}}(?:\s*[-,]\s*[a-zá]{{3}})*)\s+(?:(fechado)|{_HORA}\s*(?:-|às|a)\s*{_HORA})$", re.I)


def _horario(valor: str) -> tuple[str, list[Violacao]]:
    segs = [s.strip() for s in re.split(r"[;\n]+", valor) if s.strip()]
    if not segs or len(segs) > 14:
        return valor, [_invalido("horario_vazio", "informe de 1 a 14 faixas, ex.: 'seg-sex 09:00-18:00; sab 09:00-13:00'.")]
    ocupados: dict[int, list[tuple[int, int]]] = {}
    out: list[str] = []
    for seg in segs:
        m = _SEG_HORARIO.match(seg.lower())
        if not m:
            return valor, [_invalido("horario_formato", f"'{seg}': use 'dias HH:MM-HH:MM' (ex.: seg-sex 09:00-18:00) ou 'dom fechado'.")]
        dias_txt, fechado, h1, m1a, m1b, h2, m2a, m2b = m.groups()
        dias: list[int] = []
        try:
            if "-" in dias_txt:
                a, b = (x.strip() for x in dias_txt.split("-", 1))
                if "," in b:
                    raise KeyError(b)
                ia, ib = _DIAS[a], _DIAS[b]
                if ia > ib:
                    return valor, [_invalido("horario_dias", f"'{dias_txt}': intervalo de dias invertido.")]
                dias = list(range(ia, ib + 1))
            else:
                dias = sorted({_DIAS[x.strip()] for x in dias_txt.split(",")})
        except KeyError:
            return valor, [_invalido("horario_dias", f"'{dias_txt}': dias válidos são seg, ter, qua, qui, sex, sab, dom.")]
        if fechado:
            out.append(f"{dias_txt.replace(' ', '').replace('sáb', 'sab')} fechado")
            continue
        ini = int(h1) * 60 + int(m1a or m1b or 0)
        fim = int(h2) * 60 + int(m2a or m2b or 0)
        if ini >= fim:
            return valor, [_invalido("horario_ordem", f"'{seg}': o horário de início precisa ser anterior ao de fim.")]
        for d in dias:
            for (a, b) in ocupados.get(d, []):
                if ini < b and a < fim:
                    return valor, [_invalido("horario_sobreposto", f"'{seg}': faixas sobrepostas em {_NOMES_DIA[d]}.")]
            ocupados.setdefault(d, []).append((ini, fim))
        out.append(f"{dias_txt.replace(' ', '').replace('sáb', 'sab')} {ini // 60:02d}:{ini % 60:02d}-{fim // 60:02d}:{fim % 60:02d}")
    return "; ".join(out), []


_UNIDADES = (
    (re.compile(r"^(?:min|mins|minutos?)$"), "minuto"),
    (re.compile(r"^(?:h|hs|horas?)$"), "hora"),
    (re.compile(r"^(?:d|dias?)$"), "dia"),
    (re.compile(r"^(?:dias?\s+[uú]teis|du)$"), "dia útil"),
    (re.compile(r"^(?:sem|semanas?)$"), "semana"),
)


def _duracao(valor: str) -> tuple[str, list[Violacao]]:
    m = re.fullmatch(r"(\d{1,4})\s*([a-zá-ú ]{1,12})", valor.lower().strip())
    if not m or int(m.group(1)) <= 0:
        return valor, [_invalido("duracao_formato", "use número + unidade, ex.: '30 minutos', '2 horas', '1 dia útil'.")]
    n, un = int(m.group(1)), re.sub(r"\s+", " ", m.group(2).strip())
    for rx, nome in _UNIDADES:
        if rx.match(un):
            plural = n != 1
            nome_pl = {"dia útil": "dias úteis"}.get(nome, nome + "s") if plural else nome
            return f"{n} {nome_pl}", []
    return valor, [_invalido("duracao_unidade", "unidade inválida: use minutos, horas, dias, dias úteis ou semanas.")]


def _lista(valor: str) -> tuple[str, list[Violacao]]:
    itens = list(dict.fromkeys(dividir_itens(valor)))
    if not itens:
        return valor, [_invalido("lista_vazia", "informe ao menos um item.")]
    if len(itens) > 20:
        return valor, [_invalido("lista_excede", "no máximo 20 itens.")]
    for it in itens:
        if len(it) > 60:
            return valor, [Violacao("spec_tamanho_excedido", "item_excede", f"item com mais de 60 caracteres: '{it[:20]}…'.")]
        if "\n" in it:
            return valor, [_invalido("lista_item_multilinha", "cada item cabe em uma linha.")]
    return ", ".join(itens), []


# ── entry point ─────────────────────────────────────────────────────────────

_TIPADOS = {"dominios": _dominios, "contatos": _contatos, "cnpj": _cnpj, "creci": _creci, "horario": _horario, "duracao": _duracao}


def validar_valor(tipo: str, valor: str, contexto: ContextoSpec | None = None) -> str:
    """The NORMALIZED value (NFKC, canonical separators/format) or :class:`SpecInvalida` with every violation.

    A blank value is the caller's "clear" gesture and is not validated here."""
    if tipo not in SPEC_TIPOS:
        raise ValueError(f"tipo must be one of {SPEC_TIPOS}; got {tipo!r}")
    if not isinstance(valor, str):
        raise SpecInvalida([_invalido("nao_texto", "o valor precisa ser um texto.")])
    contexto = contexto or ContextoSpec()
    norm = _normalizar(valor)
    limite = LIMITS[f"org_spec.valor.{tipo}"]
    if len(norm) > limite:
        raise SpecInvalida([Violacao("spec_tamanho_excedido", "tamanho", f"o valor excede {limite} caracteres ({len(norm)}).")])
    multilinha = tipo in ("texto_curto", "texto", "texto_longo", "lista", "dominios", "contatos", "horario")
    viol = _universais(norm, permite_quebra=multilinha)
    if tipo == "texto_curto" and "\n" in norm:
        viol.append(_invalido("multilinha", "este campo aceita uma única linha."))
    if viol:
        raise SpecInvalida(viol)
    if e_texto_livre(tipo):
        viol = _marcacao_texto(norm) + _fora_do_tipo(norm) + _parece_instrucao(norm)
        if not viol and tipo == "lista":
            norm, viol = _lista(norm)
        if viol:
            raise SpecInvalida(viol)
        return norm
    if tipo == "url":
        norm, viol = _url(norm, contexto)
    else:
        norm, viol = _TIPADOS[tipo](norm)
    if viol:
        raise SpecInvalida(viol)
    return norm


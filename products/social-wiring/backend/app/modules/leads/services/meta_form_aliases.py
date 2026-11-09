"""The Meta lead form's answers, read tolerantly: contact aliases + the qualification questions (pure, no I/O).

WHY: a form's field NAME drifts from the typed schema the sync promotes by (`phone_number` where the form schema says
`Telefone`, "Nome completo" where it says `full_name`), so `meta_ads_leads.phone` stayed NULL while the number sat in
`answers`. The aliases below are the fallback: the typed promotion still wins; an alias only fills what is missing.

The QUALIFICATION answers (budget / buying stage / region) are free-text questions whose keys are the question text itself.
They are matched by folded keywords (a question reworded keeps matching) and mapped to `leads.qualificacao_form`.
CONTRACT: products/social-wiring/projects/ad-lead-intake-CONTRACT.md § 2.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from noctusai_lib.primitives.accents import fold_accents
from noctusai_lib.primitives.phone import normalize_phone

ALIASES_TELEFONE = frozenset({"phone_number", "phone", "telefone", "celular", "whatsapp", "fone", "numero_de_telefone", "numero_do_telefone"})
ALIASES_EMAIL = frozenset({"email", "e_mail", "e-mail"})
ALIASES_NOME = frozenset({"full_name", "nome_completo", "nome", "name"})


def _chave(nome: Any) -> str:
    return re.sub(r"[\s\-]+", "_", fold_accents(str(nome or "")).strip().lower())


def _texto(valor: Any) -> Optional[str]:
    if isinstance(valor, (list, tuple)):
        valor = ", ".join(str(v).strip() for v in valor if str(v).strip())
    texto = str(valor).strip() if valor is not None else ""
    return texto or None


def contato_das_respostas(answers: Optional[dict[str, Any]]) -> dict[str, Optional[str]]:
    """`{phone, email, full_name}` read from the answers BY ALIAS (typed promotion is the caller's first choice).
    `phone` is E.164-normalised when it can be, else the raw text (a number a human can see is a number a human can fix)."""
    saida: dict[str, Optional[str]] = {"phone": None, "email": None, "full_name": None}
    if not isinstance(answers, dict):
        return saida
    for chave, valor in answers.items():
        k = _chave(chave)
        texto = _texto(valor)
        if not texto:
            continue
        if k in ALIASES_TELEFONE and saida["phone"] is None:
            saida["phone"] = normalize_phone(texto) or texto
        elif k in ALIASES_EMAIL and saida["email"] is None:
            saida["email"] = texto
        elif k in ALIASES_NOME and saida["full_name"] is None:
            saida["full_name"] = texto
    return saida


_NUMERO = re.compile(r"(\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)?)\s*(milh[a-zõ]*|mil\b|k\b)?")


def parse_valor_brl(texto: Any) -> Optional[float]:
    """The LARGEST amount named in a budget answer ("Até R$ 1.500.000", "1,5 milhão", "500 mil a 800 mil" -> 800000.0).
    Numbers under 1000 with no `mil/milhão/k` suffix are not money (answer options, counts) and are ignored. `None` when
    no amount is found -- the text is still kept by the caller."""
    t = fold_accents(_texto(texto) or "").lower()
    melhor: Optional[float] = None
    for numero, sufixo in _NUMERO.findall(t):
        if re.fullmatch(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?", numero):
            valor = float(numero.replace(".", "").replace(",", "."))
        else:
            valor = float(numero.replace(",", "."))
        if sufixo.startswith("milh"):
            valor *= 1_000_000
        elif sufixo in ("mil", "k"):
            valor *= 1_000
        elif valor < 1000:
            continue
        melhor = valor if melhor is None else max(melhor, valor)
    return melhor


def _sim_nao(texto: str) -> Optional[bool]:
    t = fold_accents(texto).strip().lower()
    if t.startswith("sim") or t in ("s", "yes"):
        return True
    if t.startswith("nao") or t in ("n", "no"):
        return False
    return None


_RE_ORCAMENTO = ("investir", "orcamento", "ate qual valor", "faixa de valor", "quanto")
_RE_FASE = ("fase", "momento", "estagio")
_RE_REGIAO = ("regiao", "bairro", "granja viana", "buscando um imovel na", "buscando um imovel em")


def mapear_qualificacao(answers: Optional[dict[str, Any]]) -> dict[str, Any]:
    """`leads.qualificacao_form` from the form answers: `{orcamento_max, orcamento_texto, fase_compra_texto,
    regiao_interesse: {pergunta, resposta, confirmou}}` -- only the keys that were answered. Empty dict when nothing
    matches (the caller then writes nothing). Contact fields and `REF` are not qualification."""
    saida: dict[str, Any] = {}
    if not isinstance(answers, dict):
        return saida
    for chave, valor in answers.items():
        texto = _texto(valor)
        if not texto:
            continue
        k = fold_accents(str(chave)).lower()
        if _chave(chave) in ALIASES_TELEFONE | ALIASES_EMAIL | ALIASES_NOME | {"ref"}:
            continue
        if "orcamento_texto" not in saida and any(p in k for p in _RE_ORCAMENTO):
            saida["orcamento_texto"] = texto
            valor_brl = parse_valor_brl(texto)
            if valor_brl is not None:
                saida["orcamento_max"] = valor_brl
        elif "fase_compra_texto" not in saida and any(p in k for p in _RE_FASE):
            saida["fase_compra_texto"] = texto
        elif "regiao_interesse" not in saida and any(p in k for p in _RE_REGIAO):
            saida["regiao_interesse"] = {"pergunta": str(chave), "resposta": texto, "confirmou": _sim_nao(texto)}
    return saida


__all__ = ["ALIASES_TELEFONE", "ALIASES_EMAIL", "ALIASES_NOME", "contato_das_respostas", "mapear_qualificacao", "parse_valor_brl"]

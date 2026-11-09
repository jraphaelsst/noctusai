"""The real output guard: the generic rules over the moved detectors (see ``detectors`` / ``fingerprint``)."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .detectors import (
    contato_nao_permitido, formato_suspeito, link_nao_permitido, padroes_proibidos, pii_na_resposta,
)
from .fingerprint import detectar_vazamento, mascarar_dados_da_org
from .obfuscation import esqueleto
from .types import GENERIC_RULES, GuardContext, GuardFinding, GuardRule

__all__ = ["RealOutputGuard", "worst_of"]


def worst_of(a: dict[str, Any] | None, b: dict[str, Any] | None) -> dict[str, Any] | None:
    """The union of two detector findings (the as-written reply and its de-obfuscated copy): per key, the larger count."""
    if not a or not b:
        return a or b
    return {k: max(a.get(k, 0), b.get(k, 0)) for k in {*a, *b}}


def _leak(reply: str, canary: str | None, fingerprint: Any, derived: Any) -> dict[str, Any] | None:
    return worst_of(
        detectar_vazamento(reply, canario_do_prompt=canary, impressao=fingerprint),
        detectar_vazamento(reply, canario_do_prompt=None, impressao=derived))


class RealOutputGuard:
    """Stateless; the per-product behaviour is the :class:`GuardContext` and the rule params it is handed."""

    def evaluate(
        self, rule: str, reply: str, ctx: GuardContext, params: Mapping[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        p = params or {}
        if rule == "vazamento_prompt":
            # the as-written reply AND its de-obfuscated copy (spaced / dotted / homoglyph spellings)
            return worst_of(
                _leak(mascarar_dados_da_org(reply, ctx.org_data), ctx.canary, ctx.fingerprint, ctx.derived_fingerprint),
                _leak(mascarar_dados_da_org(esqueleto(reply), ctx.org_data), ctx.canary, ctx.fingerprint,
                      ctx.derived_fingerprint))
        if rule == "link_nao_permitido":
            return worst_of(
                link_nao_permitido(reply, ctx.allowed_links, ctx.allowed_domains),
                link_nao_permitido(esqueleto(reply), ctx.allowed_links, ctx.allowed_domains))
        if rule == "contato_nao_permitido":
            return worst_of(
                contato_nao_permitido(reply, ctx.allowed_contacts, ctx.lead_messages),
                contato_nao_permitido(esqueleto(reply), ctx.allowed_contacts, ctx.lead_messages))
        if rule == "pii_na_resposta":
            return pii_na_resposta(reply, ctx.own_company_ids)
        if rule == "formato_suspeito":
            return formato_suspeito(reply, p.get("max_chars", 1200), p.get("max_bullets", 6))
        if rule == "padroes_proibidos":
            return padroes_proibidos(reply, p.get("padroes", ()))
        raise KeyError(f"unknown guardrail rule {rule!r}")

    def check(self, reply: str, ctx: GuardContext, rules: Mapping[str, GuardRule]) -> list[GuardFinding]:
        out: list[GuardFinding] = []
        for name in GENERIC_RULES:
            cfg = rules.get(name)
            if cfg is None:
                continue
            detail = self.evaluate(name, reply, ctx, cfg.params)
            if detail is not None:
                out.append(GuardFinding(name, cfg.policy, detail))
        return out

"""Lead identity (name / e-mail / CPF / RG / phone) -- Julia v2 CONTRACT §0.3 owner addendum.

Kept apart from the qualification records on purpose: it never appears in ``trecho``, in the
dossier text, in a tool result or in any LLM context. CPF and RG are encrypted at rest with the
fleet's existing seam (``noctusai_lib.security.encrypted_tokens`` / ``ENCRYPTION_KEY``, the same
Fernet key the credential store uses). Display is masked by default; the clear text is only
returned by :meth:`IdentificacaoService.revelar` (org owner/admin, audited BEFORE the value leaves).

Purpose / legal basis: registering the visit, pre-contractual steps (LGPD art. 7 V); minimisation:
only these fields, collected only once the data rule says asking is due (visit intent).
"""
from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Protocol, Sequence
from uuid import UUID

from app.qualificacao.matcher import normalizar
from app.stores._util import utcnow
from noctusai_lib.primitives.identificador import cpf_dv_valido
from noctusai_lib.primitives.not_configured import IntegrationNotConfigured
from noctusai_lib.security.encrypted_tokens import decrypt, encrypt

CAMPOS = ("nome", "email", "cpf", "rg")  # asked; the phone comes from the channel ref
CAMPOS_TODOS = (*CAMPOS, "telefone")
_UFS = frozenset(
    "AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split())
_EMAIL = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}$")


class EncryptionNotConfigured(RuntimeError, IntegrationNotConfigured):
    """``ENCRYPTION_KEY`` is missing: CPF/RG are never stored in clear, so the write is refused."""


class RevelarNegado(PermissionError):
    """Reveal refused (``codigo``: sem_identificacao)."""

    def __init__(self, codigo: str) -> None:
        super().__init__(codigo)
        self.codigo = codigo


# ── validators (pure) ───────────────────────────────────────────────────────

def so_digitos(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def validar_cpf(valor: str) -> tuple[bool, str]:
    """``(ok, 11 digits)`` -- check digits verified; repeated-digit CPFs are invalid."""
    d = so_digitos(valor)
    return (True, d) if cpf_dv_valido(d) else (False, "")


def validar_email(valor: str) -> tuple[bool, str]:
    v = (valor or "").strip()
    return (bool(_EMAIL.match(v)) and len(v) <= 254, v.lower())


def validar_rg(valor: str) -> tuple[bool, str, str | None]:
    """``(ok, alnum 5..14 upper, uf|None)``; an optional UF may trail (``12.345.678-9 SP`` / ``-SP``)."""
    v = (valor or "").strip().upper()
    uf = None
    m = re.search(r"[\s/\-]([A-Z]{2})$", v)
    if m and m.group(1) in _UFS:
        uf, v = m.group(1), v[: m.start()]
    alnum = re.sub(r"[^0-9A-Z]", "", v)
    if not 5 <= len(alnum) <= 14 or not re.fullmatch(r"[0-9A-Z]+", alnum) or not any(c.isdigit() for c in alnum):
        return False, "", None
    return True, alnum, uf


def validar_nome(valor: str) -> tuple[bool, str]:
    v = " ".join((valor or "").split())
    return (2 <= len(v) <= 120 and any(c.isalpha() for c in v), v)


def mascarar_cpf(cpf: str) -> str:
    d = so_digitos(cpf)
    return f"***.***.***-{d[-2:]}" if len(d) == 11 else "***"


def mascarar_rg(rg: str, uf: str | None = None) -> str:
    return f"{'*' * max(len(rg) - 2, 3)}{rg[-2:]}" + (f"-{uf}" if uf else "")


def mascarar_email(email: str) -> str:
    local, _, dominio = email.partition("@")
    return f"{local[:1]}***@{dominio}" if dominio else "***"


def mascarar_telefone(tel: str) -> str:
    d = so_digitos(tel)
    return f"***{d[-4:]}" if len(d) >= 4 else "***"


def aparece_na_mensagem(campo: str, valor_normalizado: str, mensagens_lead: Sequence[str], ultimas: int = 8) -> bool:
    """The value must be in the lead's OWN recent messages (nothing is stored from the match)."""
    janela = [m for m in list(mensagens_lead)[-ultimas:] if isinstance(m, str)]
    if campo == "cpf":
        return any(valor_normalizado in so_digitos(m) for m in janela)
    if campo == "rg":
        alvo = re.sub(r"[^0-9A-Z]", "", valor_normalizado.upper())
        return any(alvo in re.sub(r"[^0-9A-Z]", "", m.upper()) for m in janela)
    if campo == "email":
        return any(valor_normalizado in m.lower() for m in janela)
    alvo = normalizar(valor_normalizado)
    conj = [normalizar(m) for m in janela]
    return bool(alvo) and any(alvo in m for m in [*conj, " ".join(conj)])


# ── cipher over the existing Fernet seam ────────────────────────────────────

class IdentCipher:
    """Encrypt/decrypt + the CPF lookup hash, all from the one fleet key."""

    def __init__(self, key: bytes | str | None) -> None:
        if not key:
            raise EncryptionNotConfigured("ENCRYPTION_KEY ausente")
        self._key = key.encode() if isinstance(key, str) else key

    def cifrar(self, texto: str) -> str:
        return encrypt(texto, self._key)

    def decifrar(self, cifrado: str) -> str:
        return decrypt(cifrado, self._key)

    def hash_cpf(self, cpf_digitos: str) -> str:
        """Keyed hash (HMAC-SHA256) for dedupe / lookup without decrypting."""
        return hmac.new(self._key, b"cpf:" + cpf_digitos.encode(), hashlib.sha256).hexdigest()


# ── store contract ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class IdentRecord:
    org_id: UUID
    lead_ref_id: UUID
    nome: str | None = None
    telefone: str | None = None
    email: str | None = None
    cpf_cifrado: str | None = None
    rg_cifrado: str | None = None
    rg_uf: str | None = None
    cpf_hash: str | None = None
    coletado_em: datetime | None = None
    coletado_por_agent_id: UUID | None = None
    origem_msg_id: UUID | None = None

    def campos(self) -> frozenset[str]:
        pares = {"nome": self.nome, "email": self.email, "cpf": self.cpf_cifrado, "rg": self.rg_cifrado,
                 "telefone": self.telefone}
        return frozenset(k for k, v in pares.items() if v)


@dataclass(frozen=True)
class AcessoIdentificacao:
    org_id: UUID
    lead_ref_id: UUID
    ator_user_id: UUID
    campos: tuple[str, ...]
    motivo: str | None
    created_at: datetime


class IdentificacaoStore(Protocol):
    def obter(self, org_id: UUID, lead_ref_id: UUID) -> IdentRecord | None: ...
    def salvar_campos(
        self, org_id: UUID, lead_ref_id: UUID, campos: dict[str, Any], *,
        agent_id: UUID | None, origem_msg_id: UUID | None,
    ) -> None:
        """Upsert the given columns (nome / telefone / email / cpf_cifrado / rg_cifrado / rg_uf / cpf_hash)."""
        ...
    def registrar_acesso(self, acesso: AcessoIdentificacao) -> None: ...
    def listar_acessos(self, org_id: UUID, lead_ref_id: UUID) -> list[AcessoIdentificacao]: ...
    def apagar_por_lead(self, org_id: UUID, lead_ref_id: UUID) -> int: ...


# ── results (never carry a value) ───────────────────────────────────────────

@dataclass(frozen=True)
class IdentificacaoResultado:
    campo: str
    status: str  # "registrado" | "invalido"
    faltando: tuple[str, ...]
    codigo: str | None = None  # typed refusal, no prose

    def to_payload(self) -> dict[str, Any]:
        return {"campo": self.campo, "status": self.status, "faltando": list(self.faltando)}


class IdentificacaoService:
    def __init__(
        self, store: IdentificacaoStore, cipher: IdentCipher | None, *, agora: Callable[[], datetime] = utcnow,
    ) -> None:
        self._store = store
        self._cipher = cipher
        self._agora = agora

    def faltando(self, org_id: UUID, lead_ref_id: UUID, obrigatorios: Sequence[str] = CAMPOS) -> tuple[str, ...]:
        rec = self._store.obter(org_id, lead_ref_id)
        tem = rec.campos() if rec else frozenset()
        return tuple(c for c in obrigatorios if c not in tem)

    def coletados(self, org_id: UUID, lead_ref_id: UUID) -> frozenset[str]:
        rec = self._store.obter(org_id, lead_ref_id)
        return rec.campos() if rec else frozenset()

    def definir_telefone(self, org_id: UUID, lead_ref_id: UUID, telefone: str) -> None:
        """Automatic, from the channel ref (the lead is never asked for it)."""
        d = so_digitos(telefone)
        if not 8 <= len(d) <= 15:
            raise ValueError("telefone invalido")
        self._store.salvar_campos(org_id, lead_ref_id, {"telefone": d}, agent_id=None, origem_msg_id=None)

    def registrar_identificacao(
        self, org_id: UUID, lead_ref_id: UUID, *, agent_id: UUID, campo: str, valor: str,
        mensagens_lead: Sequence[str], message_id: UUID | None = None, obrigatorios: Sequence[str] = CAMPOS,
    ) -> IdentificacaoResultado:
        """Validate, check the value is in a real lead message, store. NEVER echoes the value."""
        def res(status: str, codigo: str | None = None) -> IdentificacaoResultado:
            return IdentificacaoResultado(campo, status, self.faltando(org_id, lead_ref_id, obrigatorios), codigo)

        if campo not in CAMPOS:
            return res("invalido", "campo_desconhecido")
        if not isinstance(valor, str):
            return res("invalido", "valor_invalido")
        cols: dict[str, Any]
        if campo == "nome":
            ok, norm = validar_nome(valor)
            cols = {"nome": norm}
        elif campo == "email":
            ok, norm = validar_email(valor)
            cols = {"email": norm}
        elif campo == "cpf":
            ok, norm = validar_cpf(valor)
            cols = {}
        else:
            ok, norm, uf = validar_rg(valor)
            cols = {}
        if not ok:
            return res("invalido", "valor_invalido")
        if not aparece_na_mensagem(campo, norm, mensagens_lead):
            return res("invalido", "valor_nao_confere")
        if campo in ("cpf", "rg"):
            if self._cipher is None:
                raise EncryptionNotConfigured("ENCRYPTION_KEY ausente")
            if campo == "cpf":
                cols = {"cpf_cifrado": self._cipher.cifrar(norm), "cpf_hash": self._cipher.hash_cpf(norm)}
            else:
                cols = {"rg_cifrado": self._cipher.cifrar(norm), "rg_uf": uf}
        self._store.salvar_campos(org_id, lead_ref_id, cols, agent_id=agent_id, origem_msg_id=message_id)
        return res("registrado")

    def mascarado(self, org_id: UUID, lead_ref_id: UUID) -> dict[str, Any] | None:
        """The default display: CPF ***.***.***-12, RG masked, e-mail/phone partly hidden. Needs no key."""
        rec = self._store.obter(org_id, lead_ref_id)
        if rec is None:
            return None
        out: dict[str, Any] = {"nome": rec.nome, "coletados": sorted(rec.campos())}
        if rec.email:
            out["email"] = mascarar_email(rec.email)
        if rec.telefone:
            out["telefone"] = mascarar_telefone(rec.telefone)
        if rec.cpf_cifrado:
            out["cpf"] = mascarar_cpf(self._decifrar(rec.cpf_cifrado)) if self._cipher else "***.***.***-**"
        if rec.rg_cifrado:
            rg = self._decifrar(rec.rg_cifrado) if self._cipher else ""
            out["rg"] = mascarar_rg(rg, rec.rg_uf) if rg else "*****"
        return out

    def _decifrar(self, cifrado: str) -> str:
        assert self._cipher is not None
        return self._cipher.decifrar(cifrado)

    def revelar(
        self, org_id: UUID, lead_ref_id: UUID, *, ator_user_id: UUID, motivo: str | None = None,
    ) -> dict[str, Any]:
        """Clear text. The CALLER gates who may ask (the route is ``require_admin``: org owner/admin,
        human session). The access row is written FIRST: no audit, no value."""
        rec = self._store.obter(org_id, lead_ref_id)
        if rec is None:
            raise RevelarNegado("sem_identificacao")
        if self._cipher is None:
            raise EncryptionNotConfigured("ENCRYPTION_KEY ausente")
        campos = tuple(sorted(rec.campos()))
        self._store.registrar_acesso(AcessoIdentificacao(org_id, lead_ref_id, ator_user_id, campos, motivo, self._agora()))
        out: dict[str, Any] = {"nome": rec.nome, "email": rec.email, "telefone": rec.telefone,
                               "rg_uf": rec.rg_uf}
        out["cpf"] = self._cipher.decifrar(rec.cpf_cifrado) if rec.cpf_cifrado else None
        out["rg"] = self._cipher.decifrar(rec.rg_cifrado) if rec.rg_cifrado else None
        return out

    def apagar_por_lead(self, org_id: UUID, lead_ref_id: UUID) -> int:
        return self._store.apagar_por_lead(org_id, lead_ref_id)

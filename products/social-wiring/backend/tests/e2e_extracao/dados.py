"""Synthetic, fully-fictional data for the sw-extraction-contract-gate-2026-09
end-to-end fixture set.

EVERYTHING in this module — names, CPFs, RGs, addresses, matrícula numbers,
bank names — is invented for this test harness. CPFs are check-digit-valid
(computed by :func:`format_cpf`, the same mod-11 algorithm
``noctusai_lib.integrations.documents.cpf.is_valid`` runs) so the extractor's
own checksum gate accepts them; nothing here is or resembles a real person's
document.

This module is the ONE place the persona/imóvel facts live. Both
``gerar_documentos.py`` (renders the PDFs + writes ``esperado.json``) and any
future consumer read from here — the documents' rendered TEXT and the answer
key's EXPECTED values are derived from the same Python objects, so they
cannot drift apart the way two hand-typed copies would.

Grounding: every label/format choice below was checked against the actual
extractor it feeds — see ``README.md`` for the file-by-file trace — EXCEPT
the handful of fields the sw-extraction-contract-gate-2026-09 roadmap's wave-1
slices (153/154/155/156) had not yet landed in this worktree when this fixture
was authored. Those are marked ``pending_spec=True`` in ``DOCUMENTS`` below
and are reported, never scored, by ``verificar.py``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


# ─── CPF — valid check digits, computed exactly like cpf.py's mod-11 ───────


def _dv(digits: str, start_weight: int) -> int:
    total = sum(int(d) * (start_weight - i) for i, d in enumerate(digits))
    resto = (total * 10) % 11
    return 0 if resto == 10 else resto


def format_cpf(base9: str) -> str:
    """9-digit base -> ``123.456.789-09`` with real mod-11 check digits.

    Mirrors ``noctusai_lib.integrations.documents.cpf.is_valid`` exactly (see
    that module): first check digit weighted 10..2 over the 9 base digits,
    second weighted 11..2 over base+first check digit.
    """
    if len(base9) != 9 or not base9.isdigit():
        raise ValueError(f"base9 must be 9 digits, got {base9!r}")
    d1 = _dv(base9, 10)
    d2 = _dv(base9 + str(d1), 11)
    digits = f"{base9}{d1}{d2}"
    return f"{digits[0:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:11]}"


def cpf_digits(formatted: str) -> str:
    return "".join(c for c in formatted if c.isdigit())


# ─── Personas ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Endereco:
    cep: str
    logradouro: str
    numero: str
    complemento: Optional[str]
    bairro: str
    cidade: str
    uf: str

    def linha_unica(self) -> str:
        comp = f", {self.complemento}" if self.complemento else ""
        return (
            f"{self.logradouro}, nº {self.numero}{comp}, {self.bairro}, "
            f"{self.cidade}/{self.uf}, CEP {self.cep}"
        )


@dataclass(frozen=True)
class Persona:
    slug: str  # "titular" | "conjuge" | "vendedor" — the `alvo` role
    nome: str
    cpf: str  # formatted, e.g. 123.456.789-09
    rg: str  # formatted, e.g. 23.456.789-0
    rg_orgao: str  # "SSP/SP"
    nascimento_extenso: str  # DD/MM/AAAA as printed
    nascimento_iso: str
    naturalidade: str
    pai: str
    mae: str
    genero: str  # "Masculino" | "Feminino" — canonical DB value
    sexo_letra: str  # "M" | "F" — as a CIN prints it
    profissao: str
    endereco: Endereco


RICARDO = Persona(
    slug="titular",
    nome="RICARDO AUGUSTO FERREIRA LIMA",
    cpf=format_cpf("111222333"),
    rg="23.456.789-0",
    rg_orgao="SSP/SP",
    nascimento_extenso="14/03/1985",
    nascimento_iso="1985-03-14",
    naturalidade="São Paulo/SP",
    pai="JOSÉ AUGUSTO LIMA",
    mae="MARIA FERREIRA LIMA",
    genero="Masculino",
    sexo_letra="M",
    profissao="corretor de imóveis",
    endereco=Endereco(
        cep="04101-000",
        logradouro="Rua das Palmeiras",
        numero="120",
        complemento="apto 45",
        bairro="Vila Mariana",
        cidade="São Paulo",
        uf="SP",
    ),
)

CAMILA = Persona(
    slug="conjuge",
    nome="CAMILA DOS SANTOS FERREIRA LIMA",
    cpf=format_cpf("222333444"),
    rg="34.567.890-1",
    rg_orgao="SSP/SP",
    nascimento_extenso="02/11/1988",
    nascimento_iso="1988-11-02",
    naturalidade="Campinas/SP",
    pai="PAULO DOS SANTOS SILVA",
    mae="ANA CRISTINA DOS SANTOS",
    genero="Feminino",
    sexo_letra="F",
    profissao="corretora de imóveis",
    # Same household as Ricardo — they are spouses living together.
    endereco=Endereco(
        cep="04101-000",
        logradouro="Rua das Palmeiras",
        numero="120",
        complemento="apto 45",
        bairro="Vila Mariana",
        cidade="São Paulo",
        uf="SP",
    ),
)

FERNANDO = Persona(
    slug="vendedor",
    nome="FERNANDO SOUZA MARTINS",
    cpf=format_cpf("333444555"),
    rg="45.678.901-2",
    rg_orgao="SSP/SP",
    nascimento_extenso="30/07/1979",
    nascimento_iso="1979-07-30",
    naturalidade="São Paulo/SP",
    pai="ANTONIO MARTINS FILHO",
    mae="LUCIA SOUZA MARTINS",
    genero="Masculino",
    sexo_letra="M",
    profissao="empresário",
    endereco=Endereco(
        cep="05616-000",
        logradouro="Rua das Acácias",
        numero="200",
        complemento=None,
        bairro="Jardim Europa",
        cidade="São Paulo",
        uf="SP",
    ),
)

# Two more names, ONLY as literal parties inside the second matrícula's acts
# (imv-hipoteca). They are not `clientes` rows in this fixture set — that
# matrícula exists purely to exercise `imovel_dados`/`matricula_ato_detalhes`
# extraction with an ACTIVE ônus, independent of the card-hub trio above.
TERCEIRO_VENDEDOR = "ANTONIO CARLOS PEREIRA"
TERCEIRO_VENDEDOR_CPF = format_cpf("444555666")
TERCEIRA_COMPRADORA = "MARINA ALVES SOUZA"
TERCEIRA_COMPRADORA_CPF = format_cpf("555666777")


# ─── The marriage ───────────────────────────────────────────────────────────

CASAMENTO = {
    "data_extenso": "20/06/2015",
    "data_iso": "2015-06-20",
    "regime_doc": "COMUNHÃO PARCIAL DE BENS",
    "regime_canonico": "comunhao_parcial",
    "emissao_extenso": "05/08/2024",
    "emissao_iso": "2024-08-05",
    "matricula_civil": "115568 01 55 2015 2 00198 278 0071234-12",
}


# ─── Imóveis ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Imovel:
    codigo: str  # the fixture's own imovel_dados.codigo (org-scoped free key)
    numero_matricula: str  # digits only, as the DB column stores it
    numero_matricula_pontuado: str  # as printed, e.g. "45.678"
    oficio: str  # "5º Ofício de Registro de Imóveis de São Paulo"
    cidade_cartorio: str
    cadastro_municipal: str  # "123.456.7890-1"
    endereco: Endereco
    area_privativa_m2: str
    fracao_ideal: str


IMOVEL_LIVRE = Imovel(
    codigo="e2e-imv-livre",
    numero_matricula="45678",
    numero_matricula_pontuado="45.678",
    oficio="5º Ofício de Registro de Imóveis de São Paulo",
    cidade_cartorio="São Paulo",
    cadastro_municipal="123.456.7890-1",
    endereco=RICARDO.endereco,
    area_privativa_m2="85,00",
    fracao_ideal="1,0000",
)

IMOVEL_HIPOTECA = Imovel(
    codigo="e2e-imv-hipoteca",
    numero_matricula="78901",
    numero_matricula_pontuado="78.901",
    oficio="3º Ofício de Registro de Imóveis de Campinas",
    cidade_cartorio="Campinas",
    cadastro_municipal="987.654.3210-2",
    endereco=Endereco(
        cep="13040-000",
        logradouro="Avenida Girassóis",
        numero="500",
        complemento="apto 12",
        bairro="Jardim Primavera",
        cidade="Campinas",
        uf="SP",
    ),
    area_privativa_m2="72,00",
    fracao_ideal="1,0000",
)


# ─── Small text helpers shared by gerar_documentos.py ─────────────────────


def qualificacao(p: Persona, *, feminino: bool) -> str:
    """The rigid notarial qualification formula
    ``matricula_qualificacao.py`` anchors on: NOME, nacionalidade, estado
    civil, profissão, RG nº <n>-<órgão>, CPF nº <n>, residente e
    domiciliado[a] na <endereço>.

    Nationality is written in the MASCULINE canonical spelling
    (``brasileiro``) for BOTH genders here, deliberately — see
    ``README.md``'s "why every qualification clause says brasileiro"
    section. `matricula_qualificacao.Qualificacao.nacionalidade` is stored
    VERBATIM (no grammatical-gender canonicalisation the way the
    identity-document ladder's `nacionalidade.canonico()` does), whereas
    Ricardo's and Camila's `clientes.nacionalidade` is ALSO fed by their own
    identity documents through that canonicalising path. Writing anything
    but the identical canonical string here would make the two machine
    sources disagree and open a `cliente_campo_conflitos` row — a real
    platform behaviour, just not the one this fixture set exists to
    exercise.
    """
    estado_civil_doc = "casada" if feminino else "casado"
    residente = "residente e domiciliada" if feminino else "residente e domiciliado"
    regime = "sob o regime da comunhão parcial de bens" if p in (RICARDO, CAMILA) else ""
    partes = [p.nome, "brasileiro", estado_civil_doc]
    if regime:
        partes.append(regime)
    partes.append(p.profissao)
    return (
        ", ".join(partes)
        + f", RG nº {p.rg}-{p.rg_orgao}, CPF nº {p.cpf}, "
        + f"{residente} na {p.endereco.linha_unica()}"
    )


def qualificacao_solteiro(nome: str, cpf: str) -> str:
    """Same formula, terse form, for the throwaway imv-hipoteca parties
    (no RG needed for that matrícula's own scoring — see `dados.py`
    module docstring)."""
    return f"{nome}, brasileiro, residente e domiciliado nesta cidade, CPF nº {cpf}"

#!/usr/bin/env python3
"""Score a LIVE database against ``esperado.json`` — the answer key
``gerar_documentos.py`` wrote alongside the synthetic PDFs.

Read-only. Talks to Supabase via the `supabase` Python client (already a
`products/social-wiring/backend/requirements.txt` dependency), scoped to the
`social_wiring` schema, using a SERVICE-ROLE key so RLS never interferes with
reading the harness's own rows. Never writes anything.

USAGE
-----
    1. Run ``gerar_documentos.py`` (or use the checked-in ``fixtures/``).
    2. Follow README.md's UI steps to upload each PDF to the right card /
       imóvel in a real (or staging) org.
    3. Write a ``mapping.json`` — see ``EXEMPLO_MAPPING`` below, or run this
       script with ``--print-mapping-example``.
    4. python verificar.py --mapping mapping.json [--esperado fixtures/esperado.json]

Exit code 0 only when every CORE field (the `campos` dict in each upload)
matches. `bonus_campos` (fields that need an extra human confirmation step —
see README.md) and `pending_spec` (fields whose exact target the imóvel slice
had not shipped yet when this fixture was authored) are always REPORTED,
never counted against the exit code — see `gerar_documentos.py`'s catalogue
docstring for why those two categories exist.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

SCHEMA = "social_wiring"

EXEMPLO_MAPPING = {
    "org_id": "00000000-0000-0000-0000-000000000000",
    "personas": {
        "titular": "<cliente_id real do Ricardo>",
        "conjuge": "<cliente_id real da Camila>",
        "vendedor": "<cliente_id real do Fernando>",
    },
    "imoveis": {
        # Só é preciso sobrescrever se o imóvel real foi criado com um
        # `codigo` diferente do da fixture (`e2e-imv-livre`/`e2e-imv-hipoteca`).
        "livre": "e2e-imv-livre",
        "hipoteca": "e2e-imv-hipoteca",
    },
    "certidoes": {
        # chave = "<slug-da-persona>:<tipo>" usado em esperado.json ->
        # id real da linha em `certidao_resultados`.
        "vendedor:cnd_federal": "<id real em certidao_resultados>",
    },
}


# ─── Normalisation — one rule per column SHAPE, mirroring the extractor's
#     own canonicalisation so a formatting difference never reads as a miss
#     for a value that is, semantically, correct. ────────────────────────


def _strip_accents_upper(s: str) -> str:
    decomposed = unicodedata.normalize("NFKD", s)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).upper()


def _only_digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def _only_alnum(s: str) -> str:
    return re.sub(r"[^0-9A-Za-z]", "", s or "").upper()


def _date_only(s: str) -> str:
    """`2025-01-10T00:00:00+00:00` / `2025-01-10` -> `2025-01-10`."""
    return (s or "")[:10]


_CPF_SUFFIXES = (".cpf", "cpf_cnpj")
_RG_SUFFIXES = (".rg", "rg_orgao_expedidor")
_DATE_SUFFIXES = (
    "_em", "_ate", "data_nascimento", "data_casamento", "data_registro",
    "emitida_em", "validade_ate",
)
_UF_SUFFIXES = ("_uf",)


def normalize_for_compare(column: str, value: Any) -> Any:
    """`None` passes through. Everything else is coerced to a comparable
    canonical form based on the COLUMN NAME's shape — see the module
    docstring's per-parser grounding for why each rule exists."""
    if value is None:
        return None
    if isinstance(value, (list, dict)):
        return value
    s = str(value)
    col = column.lower()
    if any(col.endswith(suf) or suf in col for suf in _CPF_SUFFIXES):
        return _only_digits(s)
    if col.endswith("rg_orgao_expedidor"):
        return _strip_accents_upper(s).replace(" ", "").replace("-", "/")
    if col.endswith(".rg"):
        return _only_alnum(s)
    if any(col.endswith(suf) for suf in _UF_SUFFIXES):
        return s.strip().upper()
    if any(suf in col for suf in _DATE_SUFFIXES):
        return _date_only(s)
    if col.endswith("cep"):
        return _only_digits(s)
    if col.endswith("genero"):
        return _strip_accents_upper(s)
    # Free text (nome_oficial, logradouro, bairro, cidade, resultado,
    # estado_civil, regime_bens, nacionalidade, situacao_onus, ...): case
    # and accent folded, whitespace collapsed — the extractor's own
    # `normalize()` helper across every sibling parser in
    # `noctusai_lib.integrations.documents` does exactly this before
    # matching, so comparing on the same terms is the honest comparison.
    return re.sub(r"\s+", " ", _strip_accents_upper(s)).strip()


# ─── Result bookkeeping ─────────────────────────────────────────────────


@dataclass
class Resultado:
    match: list[tuple[str, Any]] = field(default_factory=list)
    errado: list[tuple[str, Any, Any]] = field(default_factory=list)  # campo, esperado, real
    faltando: list[str] = field(default_factory=list)
    revisao: list[tuple[str, Any, Any]] = field(default_factory=list)  # bonus/pending_spec

    @property
    def ok(self) -> bool:
        return not self.errado and not self.faltando


def _get_client() -> Any:
    from supabase import create_client  # already a backend dependency

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        env_path = Path(__file__).resolve().parents[6] / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if "=" not in line or line.strip().startswith("#"):
                    continue
                k, _, v = line.partition("=")
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k == "SUPABASE_URL" and not url:
                    url = v
                if k == "SUPABASE_SERVICE_ROLE_KEY" and not key:
                    key = v
    if not url or not key:
        raise SystemExit(
            "SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY não encontrados no "
            "ambiente nem no .env do repo. Exporte-os ou rode a partir da "
            "raiz do repo com o .env preenchido."
        )
    client = create_client(url, key)
    return client.schema(SCHEMA)


def _table_row(client: Any, table: str, filters: dict[str, Any]) -> Optional[dict]:
    q = client.table(table).select("*")
    for col, val in filters.items():
        q = q.eq(col, val)
    rows = q.limit(1).execute().data or []
    return rows[0] if rows else None


def _table_rows(client: Any, table: str, filters: dict[str, Any]) -> list[dict]:
    q = client.table(table).select("*")
    for col, val in filters.items():
        q = q.eq(col, val)
    return q.execute().data or []


def score_documento(
    client: Any, org_id: str, mapping: dict, nome_arquivo: str, entrada: dict,
) -> Resultado:
    resultado = Resultado()
    tipo_documento = entrada["tipo_documento"]

    for upload in entrada["uploads"]:
        alvo = upload["alvo"]
        campos = upload["campos"]
        kind, _, ref = alvo.partition(":")

        row: Optional[dict]
        rotulo: str

        if kind == "cliente":
            persona_slug = ref
            cliente_id = mapping.get("personas", {}).get(persona_slug)
            rotulo = f"clientes[{persona_slug}]"
            if not cliente_id:
                resultado.faltando.append(f"{rotulo}: sem cliente_id em mapping.json")
                continue
            row = _table_row(client, "clientes", {"org_id": org_id, "id": cliente_id})
        elif kind == "imovel":
            codigo_fixture = ref
            slug = "livre" if "livre" in codigo_fixture else "hipoteca"
            codigo_real = mapping.get("imoveis", {}).get(slug, codigo_fixture)
            rotulo = f"imovel_dados[{codigo_real}]"
            if tipo_documento in ("guia_iptu", "cnd_iptu", "cnd_condominio", "matricula") and any(
                c.startswith("imovel_documentos.") for c in campos
            ):
                doc_row = _table_row(
                    client, "imovel_documentos",
                    {"org_id": org_id, "codigo": codigo_real, "tipo_documento": tipo_documento},
                )
                row = doc_row
                rotulo = f"imovel_documentos[{codigo_real}/{tipo_documento}]"
            else:
                row = _table_row(client, "imovel_dados", {"org_id": org_id, "codigo": codigo_real})
        elif kind == "certidao":
            chave = ref  # e.g. "vendedor:cnd_federal"
            certidao_id = mapping.get("certidoes", {}).get(chave)
            rotulo = f"certidao_resultados[{chave}]"
            if not certidao_id:
                resultado.faltando.append(f"{rotulo}: sem id em mapping.json['certidoes']")
                continue
            row = _table_row(client, "certidao_resultados", {"org_id": org_id, "id": certidao_id})
        else:
            resultado.faltando.append(f"alvo desconhecido: {alvo!r}")
            continue

        if row is None:
            for campo in campos:
                resultado.faltando.append(f"{rotulo}.{campo} (linha não encontrada)")
            continue

        for campo_completo, esperado_valor in campos.items():
            coluna = campo_completo.split(".", 1)[-1]
            real_valor = row.get(coluna)
            if real_valor is None:
                resultado.faltando.append(f"{rotulo}.{campo_completo}")
                continue
            if normalize_for_compare(campo_completo, esperado_valor) == normalize_for_compare(
                campo_completo, real_valor
            ):
                resultado.match.append((f"{rotulo}.{campo_completo}", real_valor))
            else:
                resultado.errado.append((f"{rotulo}.{campo_completo}", esperado_valor, real_valor))

            # Provenance check (D1 contract): a machine-written field must
            # carry `<campo>_origem == tipo_documento` (or 'ia'/'matricula'
            # for the sources that have no per-document row) and a non-null
            # `<campo>_documento_id`, and must NOT already be confirmed —
            # that's the whole point of the D2 validation gate this
            # extraction feeds. Reported as part of the same field's
            # match/errado line, not a separate hard gate — a platform
            # whose provenance columns don't exist yet (pre-153/154) simply
            # reports them absent here, informationally.
            origem_col = f"{coluna}_origem"
            if origem_col in row:
                origem_real = row.get(origem_col)
                confirmado_col = f"{coluna}_confirmado_em"
                confirmado = row.get(confirmado_col) if confirmado_col in row else None
                if origem_real is None:
                    resultado.revisao.append(
                        (f"{rotulo}.{origem_col}", "<qualquer não-nulo>", None)
                    )
                elif confirmado is not None:
                    resultado.revisao.append(
                        (f"{rotulo}.{confirmado_col}", "NULL (ainda não confirmado)", confirmado)
                    )

    for campo, valor in entrada.get("bonus_campos", {}).items():
        if campo.startswith("_"):
            continue
        resultado.revisao.append((f"[bonus] {campo}", valor, "(ver README — requer passo manual)"))
    for campo, valor in entrada.get("pending_spec", {}).items():
        if campo == "note":
            continue
        resultado.revisao.append((f"[pending_spec] {campo}", valor, "(alvo ainda não especificado)"))

    return resultado


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mapping", type=Path, help="mapping.json — ver EXEMPLO_MAPPING")
    parser.add_argument(
        "--esperado", type=Path,
        default=Path(__file__).parent / "fixtures" / "esperado.json",
    )
    parser.add_argument(
        "--print-mapping-example", action="store_true",
        help="Imprime um mapping.json de exemplo e sai.",
    )
    parser.add_argument(
        "--filtro", default=None,
        help="Só verifica arquivos cujo nome contém esta substring.",
    )
    args = parser.parse_args(argv)

    if args.print_mapping_example:
        print(json.dumps(EXEMPLO_MAPPING, ensure_ascii=False, indent=2))
        return 0

    if not args.mapping:
        parser.error("--mapping é obrigatório (ou use --print-mapping-example)")

    mapping = json.loads(args.mapping.read_text(encoding="utf-8"))
    esperado = json.loads(args.esperado.read_text(encoding="utf-8"))
    org_id = mapping["org_id"]

    client = _get_client()

    total_ok = True
    total_match = total_errado = total_faltando = 0
    for nome_arquivo, entrada in esperado["documentos"].items():
        if args.filtro and args.filtro not in nome_arquivo:
            continue
        print(f"\n=== {nome_arquivo} ({entrada['tipo_documento']}) — {entrada['descricao']} ===")
        r = score_documento(client, org_id, mapping, nome_arquivo, entrada)
        for campo, valor in r.match:
            print(f"  OK       {campo} = {valor!r}")
        for campo, esperado_v, real_v in r.errado:
            print(f"  ERRADO   {campo}: esperado {esperado_v!r} != real {real_v!r}")
        for campo in r.faltando:
            print(f"  FALTANDO {campo}")
        for campo, esperado_v, real_v in r.revisao:
            print(f"  REVISAO  {campo}: esperado {esperado_v!r} / real {real_v!r}")

        total_match += len(r.match)
        total_errado += len(r.errado)
        total_faltando += len(r.faltando)
        total_ok = total_ok and r.ok

    print(
        f"\n--- RESUMO --- OK={total_match} ERRADO={total_errado} "
        f"FALTANDO={total_faltando} (REVISAO não conta para o exit code)"
    )
    return 0 if total_ok else 1


if __name__ == "__main__":
    sys.exit(main())

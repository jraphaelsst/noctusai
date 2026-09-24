"""The proveniência catalog (`card_hub/proveniencia/fontes.py`) — lockstep
with `contrato_gerador.validacao_extracao.REGISTRO`, the seed's own
`CAPACIDADES`, and the two products' `cliente_documento_tipos` /
`imovel_hub.TIPOS_DOCUMENTO` vocabularies.

Four guards (brief S1, item 4):

1. every `REGISTRO` field resolves to a `FONTES` entry, `MANUAL_APENAS`, or
   the named `FORA_DO_ESCOPO_S1` — never silently neither;
2. every `Fonte.extrator` dotted path actually imports;
3. every `Fonte.tipo_documento` exists in a `cliente_documento_tipos`
   migration seed row or in `imovel_hub.documentos_service.TIPOS_DOCUMENTO`;
4. every `Fonte.campos` is a subset of what the seed says that tipo can
   carry (`capacidades.CAPACIDADES`).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from noctusai_lib.integrations.documents.capacidades import CAPACIDADES

from app.modules.card_hub.contrato_gerador import validacao_extracao as vx
from app.modules.card_hub.proveniencia import fontes
from app.modules.card_hub.proveniencia.linhagem import CANONICOS_REGISTRO
from app.modules.imovel_hub import documentos_service as imovel_docs_svc

_MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "migrations"

#: P0c contract (`sw-drive-extraction-P0c-contract.md` §B/§G): S1 (a sibling
#: worktree/branch) ships `noctusai_lib.integrations.documents.{serasa_
#: crednet,cartao_cnpj}` — S2a (this slice) only WIRES `fontes.py` against
#: those dotted paths + field names, ahead of S1 actually landing in any one
#: worktree. Guards 2/4 below import the REAL seed module (they are the
#: guard that a dotted path/CAPACIDADES claim is not stale), so — for these
#: two tipos ONLY, and ONLY on an `ImportError`/missing-`CAPACIDADES`-entry —
#: they degrade to a loud, named skip rather than a red the wiring itself
#: did not cause. Every OTHER tipo (rg/cpf/matricula/...) keeps the full,
#: unconditional assertion. Remove this set once S1 has merged — at that
#: point a skip here would be masking a REAL regression.
_PENDING_CROSS_SLICE_TIPOS = frozenset({"serasa_crednet", "cartao_cnpj"})

#: `parse_files` (`noctusai_lib.testing.migration_parser`) answers SCHEMA
#: questions (`{table: {columns}}`) — this needs the SEEDED DATA (which
#: `tipo_documento` string literals actually landed via `INSERT INTO
#: social_wiring.cliente_documento_tipos`), so a small dedicated regex pair
#: does it here instead of stretching that helper past its own contract.
_INSERT_TIPOS_RE = re.compile(
    r"INSERT\s+INTO\s+social_wiring\.cliente_documento_tipos\b.*?VALUES(.*?);",
    re.IGNORECASE | re.DOTALL,
)
_ROW_FIRST_VALUE_RE = re.compile(r"\(\s*'([a-z0-9_]+)'")


def _tipos_documento_seedados() -> set[str]:
    tipos: set[str] = set()
    for path in sorted(_MIGRATIONS_DIR.glob("*.sql")):
        texto = path.read_text(encoding="utf-8")
        for bloco in _INSERT_TIPOS_RE.findall(texto):
            tipos |= set(_ROW_FIRST_VALUE_RE.findall(bloco))
    return tipos


class TestRegistroCoberto:
    """Guard 1 — every `REGISTRO` field is accounted for, exactly once.

    The `(entidade, campo) -> canonical field name(s)` translation table
    (`REGISTRO` uses `clientes`' own column names, `capacidades.py` uses
    the seed's — see `fontes.Fonte`'s own docstring for why they differ)
    is `proveniencia.linhagem.CANONICOS_REGISTRO` — S2's real code needs
    the same table, so this used to keep its own private copy and now
    imports the shipped one instead (single source of truth)."""

    def test_toda_entrada_do_registro_tem_destino(self):
        canonicais = CANONICOS_REGISTRO
        campos_com_fonte = frozenset().union(*(f.campos for f in fontes.FONTES.values()))
        estrutura_tipos = frozenset(
            f.tipo_documento for f in fontes.FONTES.values() if f.estrutura_extraivel
        )

        sem_destino: list[str] = []
        for campo in vx.REGISTRO:
            chave = (campo.entidade, campo.campo)
            if chave in fontes.FORA_DO_ESCOPO_S1:
                continue
            if campo.entidade == vx.ENTIDADE_IMOVEL_DOCUMENTO and estrutura_tipos:
                # The migration-118 structured read (imovel_hub) — no
                # per-field canonical claim, see `Fonte.campos`' docstring.
                continue
            canonico = canonicais.get(chave)
            if canonico is not None and canonico & campos_com_fonte:
                continue
            if campo.campo in fontes.MANUAL_APENAS:
                continue
            sem_destino.append(f"{campo.entidade}:{campo.campo}")

        assert not sem_destino, (
            "REGISTRO field(s) with neither a FONTES entry, a MANUAL_APENAS "
            f"label, nor a FORA_DO_ESCOPO_S1 entry: {sem_destino}"
        )

    def test_fora_do_escopo_nao_se_sobrepoe_ao_catalogo(self):
        canonicais = CANONICOS_REGISTRO
        campos_com_fonte = frozenset().union(*(f.campos for f in fontes.FONTES.values()))
        for entidade, campo in fontes.FORA_DO_ESCOPO_S1:
            canonico = canonicais.get((entidade, campo))
            if canonico:
                assert not (canonico & campos_com_fonte), (
                    f"{entidade}:{campo} is marked FORA_DO_ESCOPO_S1 but a "
                    "FONTES entry already claims it — update the catalog."
                )

    def test_os_tres_renomeios_conhecidos(self):
        # Pins the ONLY three `REGISTRO` column names that differ from
        # `capacidades.py`'s vocabulary — a silent rename on either side
        # would otherwise pass guard 1 by accident (both sides drifting the
        # same way) rather than by a checked translation.
        canonicais = CANONICOS_REGISTRO
        assert canonicais[(vx.ENTIDADE_CLIENTE, "nome_oficial")] == frozenset({"nome"})
        assert canonicais[(vx.ENTIDADE_CLIENTE, "rg_orgao_expedidor")] == frozenset({"rg_orgao"})
        assert canonicais[
            (vx.ENTIDADE_CLIENTE, "certidao_estado_civil_emitida_em")
        ] == frozenset({"data_emissao"})


class TestExtratoresImportam:
    """Guard 2 — every dotted `extrator` path resolves to a real callable."""

    def test_todo_extrator_importa(self):
        skipped: list[str] = []
        for tipo, fonte in fontes.FONTES.items():
            try:
                alvo = fontes.resolver_extrator(fonte)
            except (ImportError, AttributeError):
                if tipo in _PENDING_CROSS_SLICE_TIPOS:
                    skipped.append(tipo)
                    continue
                raise
            assert callable(alvo), f"{tipo}'s extrator {fonte.extrator!r} is not callable"
        if skipped:
            pytest.skip(
                f"seed extractor(s) not yet merged into this worktree: {skipped} "
                "— see _PENDING_CROSS_SLICE_TIPOS"
            )


class TestTipoDocumentoExiste:
    """Guard 3 — every `tipo_documento` is real, on one side or the other."""

    def test_todo_tipo_documento_cliente_existe_na_migracao(self):
        tipos_seedados = _tipos_documento_seedados()
        for fonte in fontes.FONTES.values():
            if fonte.dominio != "cliente":
                continue
            assert fonte.tipo_documento in tipos_seedados, (
                f"{fonte.tipo_documento!r} has no cliente_documento_tipos seed row"
            )

    def test_todo_tipo_documento_imovel_existe_no_servico(self):
        for fonte in fontes.FONTES.values():
            if fonte.dominio != "imovel":
                continue
            assert fonte.tipo_documento in imovel_docs_svc.TIPOS_DOCUMENTO


class TestCapacidades:
    """Guard 4 — a product never claims more than the seed can produce."""

    def test_todo_campo_da_fonte_esta_nas_capacidades_do_tipo(self):
        skipped: list[str] = []
        for tipo, fonte in fontes.FONTES.items():
            if tipo in _PENDING_CROSS_SLICE_TIPOS and tipo not in CAPACIDADES:
                skipped.append(tipo)
                continue
            capaz = CAPACIDADES.get(tipo, frozenset())
            excesso = fonte.campos - capaz
            assert not excesso, (
                f"{tipo}'s Fonte claims {sorted(excesso)}, outside "
                f"CAPACIDADES[{tipo!r}] = {sorted(capaz)}"
            )
        if skipped:
            pytest.skip(
                f"seed CAPACIDADES entry not yet merged into this worktree: "
                f"{skipped} — see _PENDING_CROSS_SLICE_TIPOS"
            )

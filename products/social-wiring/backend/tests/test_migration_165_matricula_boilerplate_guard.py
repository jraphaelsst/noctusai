"""Tests for `165_matricula_boilerplate_guard.sql`.

Three layers, same reasoning as `test_migration_136_matricula_ruido_e_
abertura.py` for the structural half (the migration is a FILE, not an
applied change — there is no dev database to run its trigger against, see
`KB § PATTERNS/devops/dev-fleet-dormant.md`) plus two layers that file did
not need:

1. **Structural** — the DECLARED shape: every 111/135/136/154 branch
   survives byte-for-byte, the new `v_strip_boilerplate` DECLARE and its
   two `OR`-composed conditions are present, and the three new helper
   functions exist.
2. **Pattern parity** — `social_wiring.matricula_boilerplate_patterns()`
   (the SQL array embedded in this migration) mirrors
   `noctusai_lib.integrations.media.pdf_text._PROVENANCE_STAMP_PATTERNS`
   (Python `\\b` -> Postgres `\\y`, the ARE word-boundary escape — `\\b` in
   Postgres regex means BACKSPACE, not a boundary), so the two lists can
   never drift apart silently.
3. **Offline replay** — a pure-Python mirror of the SQL guard's greedy
   subsequence algorithm (`_is_boilerplate_only_deletion` below), replayed
   against the REAL EUROVILLE shape (synthetic, no PII — the exact fixture
   `test_pdf_text.py::TestCleanExtractionOutput.
   test_the_eurovile_defect_the_owner_reported` uses) and against the seed's
   OWN `matricula_marcacao.remover_boilerplate` output, so this migration's
   design is validated against the real production code path before it is
   ever applied to a live database.
"""
from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

import pytest

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "165_matricula_boilerplate_guard.sql"
)

# `conftest.py` already puts `seed/lib/backend` on `sys.path` — these
# imports are the SAME production code `backfill_service.normalizar_extracao`
# calls, not a re-derivation.
from noctusai_lib.integrations.documents.matricula_marcacao import (  # noqa: E402
    remover_boilerplate,
)
from noctusai_lib.integrations.media.pdf_text import (  # noqa: E402
    _PROVENANCE_STAMP_PATTERNS,
)


@pytest.fixture(scope="module")
def sql() -> str:
    assert MIGRATION.is_file(), f"Migration file missing at {MIGRATION}"
    return MIGRATION.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def code(sql: str) -> str:
    """SQL with comment lines stripped — prose in the header must never
    satisfy (or trip) a check about actual SQL."""
    return "\n".join(l for l in sql.splitlines() if not l.strip().startswith("--"))


@pytest.fixture(scope="module")
def flat(code: str) -> str:
    """`code` with runs of whitespace collapsed — the DDL aligns its column
    definitions, so a substring check must not depend on that alignment."""
    return " ".join(code.split())


def test_migration_parses(sql: str):
    pglast = pytest.importorskip("pglast", reason="pglast not installed in this env")
    statements = pglast.parse_sql(sql)
    assert len(statements) > 0


def test_is_idempotent(code: str):
    assert code.count("CREATE OR REPLACE FUNCTION") == 4  # patterns, is-boilerplate, is-removal, trigger


def test_not_applied_to_any_db_by_this_change(sql: str):
    """The header's own contract — a follow-up (this project's PROJECT.md,
    or `noctus.dev.migrate_product`) applies it with explicit consent."""
    assert "MIGRATION FILE ONLY" in sql
    assert "applying is the tech-lead's + user's decision" in sql


# ─── 1. Every 111/135/136/154 branch survives byte-for-byte ───────────────


def test_the_original_checks_survive_verbatim(flat: str):
    """165 replaces the function body (111/135/136/154's) — this pins that
    every earlier check survived the replace byte-for-byte in its
    condition, exactly the discipline `test_migration_136_...py::
    test_the_original_five_checks_survive_verbatim` pinned for 136."""
    assert "OLD.status = 'concluida'" in flat
    assert "NEW.texto_extraido IS DISTINCT FROM OLD.texto_extraido" in flat
    assert "OLD.codigo IS NOT NULL" in flat
    assert "NEW.codigo IS DISTINCT FROM OLD.codigo" in flat
    assert "OLD.imovel_documento_id IS NOT NULL" in flat
    assert "NEW.imovel_documento_id IS DISTINCT FROM OLD.imovel_documento_id" in flat
    assert "OLD.arquivo_origem_id IS NOT NULL" in flat
    assert "NEW.arquivo_origem_id IS DISTINCT FROM OLD.arquivo_origem_id" in flat
    assert "OLD.substituida_por IS NOT NULL" in flat
    assert "NEW.substituida_por IS DISTINCT FROM OLD.substituida_por" in flat
    assert "NEW.ruido IS DISTINCT FROM OLD.ruido" in flat


def test_v_strip_154_declaration_is_untouched(flat: str):
    """154's markup-strip exception survives byte-for-byte — 165 adds a
    SECOND exception, never weakens or replaces the first."""
    assert (
        "v_strip BOOLEAN := OLD.status = 'concluida' AND OLD.texto_extraido IS NOT NULL "
        "AND NEW.texto_extraido IS NOT NULL AND NEW.texto_extraido IS DISTINCT FROM "
        "OLD.texto_extraido AND length(NEW.texto_extraido) < length(OLD.texto_extraido) "
        "AND regexp_replace(NEW.texto_extraido, '\\*\\*|</?[uU]>', '', 'g') = "
        "regexp_replace(OLD.texto_extraido, '\\*\\*|</?[uU]>', '', 'g');"
        in flat
    )


# ─── 2. The new exception is present and composed with OR, not AND ────────


def test_v_strip_boilerplate_is_declared(flat: str):
    trecho = flat[flat.index("v_strip_boilerplate BOOLEAN :=") :][:500]
    assert "OLD.status = 'concluida'" in trecho
    assert "OLD.texto_extraido IS NOT NULL" in trecho
    assert "NEW.texto_extraido IS NOT NULL" in trecho
    assert "NEW.texto_extraido IS DISTINCT FROM OLD.texto_extraido" in trecho
    assert "length(NEW.texto_extraido) < length(OLD.texto_extraido)" in trecho
    assert (
        "social_wiring.matricula_texto_e_remocao_boilerplate( OLD.texto_extraido, "
        "NEW.texto_extraido )" in trecho
    )


def test_texto_extraido_guard_accepts_either_exception(flat: str):
    """The texto_extraido IF condition must refuse only when NEITHER
    exception applies — `NOT v_strip AND NOT v_strip_boilerplate`, never a
    replace of one exception by the other."""
    trecho = flat[flat.index("matricula_extracoes_protege_concluida()") :]
    assert (
        "NEW.texto_extraido IS NOT NULL AND NOT v_strip AND NOT v_strip_boilerplate THEN"
        in trecho
    )


def test_ruido_guard_accepts_either_exception_too(flat: str):
    """136's `ruido` freeze gets the SAME exception `texto_extraido` has —
    the offsets move WITH the text under either sanctioned rewrite."""
    trecho = flat[flat.index("matricula_extracoes_protege_concluida()") :]
    assert (
        "NEW.ruido IS DISTINCT FROM OLD.ruido AND NOT v_strip AND NOT v_strip_boilerplate THEN"
        in trecho
    )


def test_no_role_is_exempted_from_the_extended_guard(code: str):
    trecho = code[code.index("matricula_extracoes_protege_concluida") :]
    assert "TO authenticated" not in trecho
    assert "TO service_role" not in trecho


def test_the_trigger_itself_is_not_redeclared(flat: str):
    """165 keeps the SAME trigger (function replace only) — no second
    `CREATE TRIGGER protege_concluida_matricula_extracoes`, no DROP
    TRIGGER."""
    assert flat.count("CREATE TRIGGER protege_concluida_matricula_extracoes") == 0
    assert flat.count("DROP TRIGGER") == 0


# ─── 3. The three new helper functions ─────────────────────────────────────


def test_boilerplate_patterns_function_exists(flat: str):
    assert (
        "CREATE OR REPLACE FUNCTION social_wiring.matricula_boilerplate_patterns() "
        "RETURNS TEXT[]" in flat
    )
    assert "IMMUTABLE" in flat


def test_linha_e_boilerplate_function_exists_and_allows_blank(flat: str):
    trecho = flat[flat.index("matricula_linha_e_boilerplate(linha TEXT)") :][:600]
    assert "btrim(COALESCE(linha, '')) = ''" in trecho
    assert "matricula_boilerplate_patterns()" in trecho


def test_texto_e_remocao_boilerplate_function_exists(flat: str):
    trecho = flat[flat.index("matricula_texto_e_remocao_boilerplate(") :][:1200]
    assert "string_to_array(texto_antigo, E'\\n')" in trecho
    assert "string_to_array(texto_novo, E'\\n')" in trecho
    assert "matricula_linha_e_boilerplate(linhas_antigas[i])" in trecho


def test_translate_not_unaccent_for_accent_folding(flat: str):
    """Same reasoning migration 071's `normalizar_nome` gives:
    `unaccent()` is not IMMUTABLE."""
    assert "translate(" in flat
    assert "unaccent(" not in flat


# ─── 4. Pattern parity — the SQL array mirrors the Python source list ─────


def _sql_boilerplate_patterns(sql_text: str) -> list[str]:
    """Extract every single-quoted string literal inside
    `matricula_boilerplate_patterns()`'s `ARRAY[...]::TEXT[]` body."""
    start = sql_text.index("matricula_boilerplate_patterns()")
    end = sql_text.index("$$;", start)
    body = sql_text[start:end]
    array_start = body.index("ARRAY[")
    array_end = body.index("]::TEXT[]", array_start)
    array_body = body[array_start + len("ARRAY[") : array_end]
    return re.findall(r"'((?:[^'])*)'", array_body)


def _python_patterns_as_postgres_are() -> list[str]:
    """`\\b` (Python word-boundary escape) -> `\\y` (Postgres ARE
    word-boundary escape — `\\b` in Postgres regex means backspace, not a
    boundary). Every other token (`\\s`, `\\S`, `\\w`, `\\W`) is identical
    in both engines and needs no translation."""
    return [p.replace(r"\b", r"\y") for p in _PROVENANCE_STAMP_PATTERNS]


class TestBoilerplatePatternParity:
    def test_sql_array_has_the_same_length_as_the_python_list(self, sql: str):
        sql_patterns = _sql_boilerplate_patterns(sql)
        assert len(sql_patterns) == len(_PROVENANCE_STAMP_PATTERNS)

    def test_sql_array_matches_the_python_list_element_for_element(self, sql: str):
        sql_patterns = _sql_boilerplate_patterns(sql)
        expected = _python_patterns_as_postgres_are()
        assert sql_patterns == expected, (
            "social_wiring.matricula_boilerplate_patterns() has drifted from "
            "noctusai_lib.integrations.media.pdf_text._PROVENANCE_STAMP_PATTERNS "
            "— update BOTH lists together (migrations/165_matricula_"
            "boilerplate_guard.sql and pdf_text.py)."
        )

    def test_no_pattern_carries_a_raw_python_word_boundary(self, sql: str):
        """A `\\b` that slipped through un-translated would silently match
        BACKSPACE in Postgres — never matching any real line — a guard that
        looks correct and refuses everything. Fail loud instead."""
        sql_patterns = _sql_boilerplate_patterns(sql)
        for p in sql_patterns:
            assert r"\b" not in p, f"un-translated Python \\b in {p!r}"


# ─── 5. Offline replay — a pure-Python mirror of the SQL algorithm ────────


def _stamp_key(line: str) -> str:
    """Mirrors `pdf_text._stamp_match_key` — accent-folded, case-folded."""
    folded = unicodedata.normalize("NFD", line.strip().casefold())
    return "".join(c for c in folded if unicodedata.category(c) != "Mn")


def _is_deletable_line(line: str) -> bool:
    """Mirrors `social_wiring.matricula_linha_e_boilerplate`: blank, or a
    match against the SAME pattern set (never a re-derived one)."""
    if line.strip() == "":
        return True
    key = _stamp_key(line)
    return any(re.match(p, key) for p in _PROVENANCE_STAMP_PATTERNS)


def _is_boilerplate_only_deletion(old_text: str, new_text: str) -> bool:
    """Mirrors `social_wiring.matricula_texto_e_remocao_boilerplate`: a
    greedy left-to-right subsequence match, splitting on `\\n` exactly as
    the SQL does (`string_to_array(text, E'\\n')`)."""
    old_lines = old_text.split("\n")
    new_lines = new_text.split("\n")
    i = j = 0
    while i < len(old_lines):
        if j < len(new_lines) and old_lines[i] == new_lines[j]:
            i += 1
            j += 1
        elif _is_deletable_line(old_lines[i]):
            i += 1
        else:
            return False
    return j == len(new_lines)


#: 🔴 VERBATIM structure from the real EUROVILLE certidão
#: (`social_wiring.matricula_extracoes`, 2026-09-23) — the SAME synthetic,
#: no-PII fixture `test_pdf_text.py::TestCleanExtractionOutput.
#: test_the_eurovile_defect_the_owner_reported` uses: the vision
#: transcriber wraps the stamp block in a bare code fence, then
#: `Valide aqui` / `este documento`, then the real header, on the same page
#: as the matrícula's actual content.
_EUROVILLE_SHAPE = (
    "```\n"
    "Valide aqui\n"
    "este documento\n"
    "\n"
    "Mat. 3917 - Página 1/3 - PROT. 89.029\n"
    "\n"
    "CNM: 148429.2.0003917-55\n"
    "\n"
    "LIVRO Nº 2 - REGISTRO GERAL\n"
    "\n"
    "IMOVEL: Terreno situado na Alameda Alemanha."
)


class TestOfflineEurovilleReplay:
    """No dev database to run the trigger against
    (`KB § PATTERNS/devops/dev-fleet-dormant.md`) — this replays the SQL
    guard's own algorithm, in Python, against the real production removal
    (`matricula_marcacao.remover_boilerplate`), so the design is validated
    against the actual code path `backfill_service.normalizar_extracao`
    calls, not just against hand-picked strings."""

    def test_remover_boilerplate_output_satisfies_the_sql_guard(self) -> None:
        r = remover_boilerplate(_EUROVILLE_SHAPE)
        assert r.alterou is True
        assert _is_boilerplate_only_deletion(_EUROVILLE_SHAPE, r.texto) is True

    def test_the_owner_acceptance_criterion_still_holds(self) -> None:
        """EUROVILLE-535's own acceptance test: after the removal, the text
        starts with `Mat. 3917`, not with the validation stamp."""
        r = remover_boilerplate(_EUROVILLE_SHAPE)
        assert r.texto.lstrip("\n").startswith("Mat. 3917 - Página 1/3 - PROT. 89.029")
        assert "CNM: 148429.2.0003917-55" in r.texto
        assert "LIVRO Nº 2 - REGISTRO GERAL" in r.texto
        assert "IMOVEL: Terreno situado na Alameda Alemanha." in r.texto
        assert "Valide aqui" not in r.texto
        assert "```" not in r.texto

    def test_deleting_a_real_content_line_too_is_rejected(self) -> None:
        """The negative control: `remover_boilerplate` never does this, but
        the GUARD must independently refuse it if some other caller tried —
        deleting the property description alongside the stamp is not a
        boilerplate-only edit."""
        tampered = _EUROVILLE_SHAPE.replace(
            "\nIMOVEL: Terreno situado na Alameda Alemanha.", ""
        )
        assert _is_boilerplate_only_deletion(_EUROVILLE_SHAPE, tampered) is False

    def test_editing_a_kept_line_in_place_is_rejected(self) -> None:
        edited = _EUROVILLE_SHAPE.replace(
            "IMOVEL: Terreno situado na Alameda Alemanha.",
            "IMOVEL: Terreno situado na Alameda Alemanha, fundos.",
        )
        assert _is_boilerplate_only_deletion(_EUROVILLE_SHAPE, edited) is False

    def test_a_pure_boilerplate_and_blank_deletion_is_accepted(self) -> None:
        old = "Valide aqui\neste documento\n\nMat. 3917 - conteudo real do probe"
        new = "Mat. 3917 - conteudo real do probe"
        assert _is_boilerplate_only_deletion(old, new) is True

    def test_a_non_boilerplate_line_deletion_alone_is_rejected(self) -> None:
        """The shape a naive 'shorter + subsequence' check alone would let
        through — mirrors the `verify_db_guards`
        `non_boilerplate_line_deletion_still_refused` probe."""
        old = "Valide aqui\nLinha real numero um\nLinha real numero dois"
        new = "Valide aqui\nLinha real numero um"
        assert _is_boilerplate_only_deletion(old, new) is False

"""Tests for `app/importer/mapping.py` — one test per §B.6 mapping rule."""
import json

import pytest

from app.importer.bundle import BundleInvalid
from app.importer.mapping import (
    map_decision_single_file,
    map_decisions_bundle_file,
    map_doc_geral,
    map_json_state_file,
    map_kb_file,
    map_line,
    map_timeline_file,
)


# ---------------------------------------------------------------------------
# KB files
# ---------------------------------------------------------------------------


class TestMapKbFile:
    def test_categoria_from_top_folder_lowercased(self):
        entity = map_kb_file(
            "KNOWLEDGE-BASE/CONTEXTO/visao.md", "# Visao geral\n\nTexto."
        )
        assert entity.entity_type == "kb_entry"
        assert entity.snapshot["categoria"] == "contexto"
        assert entity.snapshot["subcategoria"] is None

    def test_dominio_subfolder_gives_subcategoria(self):
        entity = map_kb_file(
            "KNOWLEDGE-BASE/DOMINIO/REGULATORIO/pnrs.md",
            "# PNRS\n\nSobre a politica nacional.",
        )
        assert entity.snapshot["categoria"] == "dominio"
        assert entity.snapshot["subcategoria"] == "regulatorio"

    def test_titulo_from_first_heading(self):
        entity = map_kb_file("KNOWLEDGE-BASE/GERAL/x.md", "# Titulo do heading\n\nCorpo.")
        assert entity.snapshot["titulo"] == "Titulo do heading"

    def test_titulo_falls_back_to_frontmatter(self):
        content = "---\ntitulo: Titulo do frontmatter\n---\nCorpo sem heading.\n"
        entity = map_kb_file("KNOWLEDGE-BASE/GERAL/x.md", content)
        assert entity.snapshot["titulo"] == "Titulo do frontmatter"

    def test_unknown_frontmatter_keys_kept_verbatim(self):
        content = (
            "---\n"
            "titulo: Titulo A\n"
            "origem: sibling-workspace\n"
            "---\n"
            "# Titulo A\n\nCorpo.\n"
        )
        entity = map_kb_file("KNOWLEDGE-BASE/GERAL/x.md", content)
        assert entity.snapshot["frontmatter"] == {"origem": "sibling-workspace"}
        assert "titulo" not in entity.snapshot["frontmatter"]

    def test_slug_derived_from_path(self):
        entity = map_kb_file(
            "KNOWLEDGE-BASE/DOMINIO/REGULATORIO/pnrs.md", "# PNRS\n\nCorpo."
        )
        assert entity.natural_key == entity.snapshot["slug"] == "dominio-regulatorio-pnrs"


class TestMapDocGeral:
    def test_docs_spec_maps_to_geral_kb_entry(self):
        entity = map_doc_geral("docs/SPEC.md", "# Especificacao\n\nDetalhes.")
        assert entity.entity_type == "kb_entry"
        assert entity.snapshot["categoria"] == "geral"
        assert entity.snapshot["titulo"] == "Especificacao"
        assert entity.snapshot["slug"] == "docs-spec"


# ---------------------------------------------------------------------------
# Decisions — the bundled 0001 file, split by table row across TWO tables
# ---------------------------------------------------------------------------


class TestMapDecisionsBundleFile:
    def _content(self):
        return (
            "---\n"
            "data: 2026-01-05\n"
            "---\n"
            "# Decisoes fundacionais\n\n"
            "## Arquitetura\n\n"
            "| # | Decisão | Motivo |\n"
            "|---|---|---|\n"
            "| D-01 | Usar Supabase para persistencia | Reduz custo operacional |\n"
            "| D-02 | Adotar RLS por organizacao | Isola dados entre clientes |\n"
            "\n"
            "## Processo\n\n"
            "| # | Decisão | Motivo |\n"
            "|---|---|---|\n"
            "| D-03 | Revisar decisoes trimestralmente | Mantem o registro atualizado |\n"
        )

    def test_splits_one_row_per_decision_across_both_tables(self):
        entities = map_decisions_bundle_file(
            "KNOWLEDGE-BASE/DECISOES/0001-decisoes.md", self._content()
        )
        assert [e.natural_key for e in entities] == ["D-01", "D-02", "D-03"]
        assert all(e.entity_type == "decision" for e in entities)

    def test_row_fields_map_correctly(self):
        entities = map_decisions_bundle_file(
            "KNOWLEDGE-BASE/DECISOES/0001-decisoes.md", self._content()
        )
        d01 = entities[0]
        assert d01.snapshot["titulo"] == "Usar Supabase para persistencia"
        assert d01.snapshot["decisao"] == "Usar Supabase para persistencia"
        assert d01.snapshot["motivo"] == "Reduz custo operacional"
        assert d01.snapshot["data"] == "2026-01-05"
        assert d01.snapshot["estado"] == "vigente"

    def test_second_table_rows_also_captured(self):
        entities = map_decisions_bundle_file(
            "KNOWLEDGE-BASE/DECISOES/0001-decisoes.md", self._content()
        )
        d03 = entities[2]
        assert d03.snapshot["decisao"] == "Revisar decisoes trimestralmente"
        assert d03.snapshot["motivo"] == "Mantem o registro atualizado"


# ---------------------------------------------------------------------------
# Decisions — a single-decision file
# ---------------------------------------------------------------------------


class TestMapDecisionSingleFile:
    def _content(self, codigo="D-10", relacionadas_mentions=""):
        return (
            "---\n"
            f"codigo: {codigo}\n"
            "titulo: Adotar fila assincrona para importacao\n"
            "data: 2026-02-10\n"
            "estado: vigente\n"
            "---\n"
            "## Contexto\n\n"
            "O importador precisa processar bundles grandes sem bloquear.\n\n"
            "## Decisão\n\n"
            "Usar uma fila assincrona dedicada para o processamento.\n\n"
            "## Motivo\n\n"
            "Evita timeouts na rota de import e permite retry.\n\n"
            "## Alternativas rejeitadas\n\n"
            "Processamento sincrono foi rejeitado por custo de latencia.\n"
            f"{relacionadas_mentions}"
        )

    def test_fields_from_frontmatter_and_sections(self):
        entity = map_decision_single_file(
            "KNOWLEDGE-BASE/DECISOES/0010-fila-assincrona.md", self._content()
        )
        assert entity.entity_type == "decision"
        assert entity.natural_key == "D-10"
        assert entity.snapshot["codigo"] == "D-10"
        assert entity.snapshot["titulo"] == "Adotar fila assincrona para importacao"
        assert entity.snapshot["data"] == "2026-02-10"
        assert entity.snapshot["estado"] == "vigente"
        assert "processar bundles grandes" in entity.snapshot["contexto"]
        assert "fila assincrona dedicada" in entity.snapshot["decisao"]
        assert "Evita timeouts" in entity.snapshot["motivo"]
        assert "Processamento sincrono" in entity.snapshot["alternativas_rejeitadas"]

    def test_relacionadas_collects_other_d_codes_mentioned_in_body(self):
        content = self._content(
            codigo="D-21",
            relacionadas_mentions="\nEsta decisao emenda D-10 e referencia D-05 tambem.\n",
        )
        entity = map_decision_single_file(
            "KNOWLEDGE-BASE/DECISOES/0021-emenda.md", content
        )
        assert entity.snapshot["relacionadas"] == ["D-05", "D-10"]

    def test_own_codigo_excluded_from_relacionadas(self):
        content = self._content(
            codigo="D-10", relacionadas_mentions="\nMencao redundante a D-10 aqui.\n"
        )
        entity = map_decision_single_file(
            "KNOWLEDGE-BASE/DECISOES/0010-fila-assincrona.md", content
        )
        assert entity.snapshot["relacionadas"] == []

    def test_missing_codigo_raises_bundle_invalid(self):
        content = "## Contexto\n\nSem frontmatter codigo.\n"
        with pytest.raises(BundleInvalid):
            map_decision_single_file("KNOWLEDGE-BASE/DECISOES/0099-sem-codigo.md", content)


# ---------------------------------------------------------------------------
# Timeline
# ---------------------------------------------------------------------------


class TestMapTimelineFile:
    def test_one_event_per_dated_section(self):
        content = (
            "# Historico\n\n"
            "## 2026-01-10 — Inicio do projeto\n\n"
            "Kickoff com a equipe.\n\n"
            "## 2026-02-15 — Primeira entrega\n\n"
            "Entrega da primeira versao do importador.\n"
        )
        entities = map_timeline_file("KNOWLEDGE-BASE/HISTORICO/TIMELINE.md", content)
        assert len(entities) == 2
        assert entities[0].entity_type == "timeline_event"
        assert entities[0].snapshot["data"] == "2026-01-10"
        assert entities[0].snapshot["titulo"] == "Inicio do projeto"
        assert "Kickoff" in entities[0].snapshot["descricao"]
        assert entities[1].snapshot["data"] == "2026-02-15"
        assert entities[1].natural_key == "2026-02-15|Primeira entrega"

    def test_section_without_title_takes_it_from_its_first_line(self):
        """`timeline_events.titulo` is NOT NULL — an untitled section (it
        exists in the real sibling history) must still carry one."""
        content = (
            "## 2026-09-12\n\n"
            "- **Endurecimento do P2 — e um diagnóstico** que estava errado.\n"
            "- Segundo item.\n"
        )
        entities = map_timeline_file("KNOWLEDGE-BASE/HISTORICO/TIMELINE.md", content)
        assert entities[0].snapshot["titulo"] == "Endurecimento do P2"
        assert entities[0].natural_key == "2026-09-12|Endurecimento do P2"
        assert entities[0].snapshot["descricao"].startswith("- **Endurecimento")

    def test_section_without_title_or_text_gets_a_dated_title(self):
        entities = map_timeline_file("KNOWLEDGE-BASE/HISTORICO/TIMELINE.md", "## 2026-03-01\n\n")
        assert entities[0].snapshot["titulo"] == "Registro de 2026-03-01"

    def test_a_long_first_line_is_capped(self):
        content = "## 2026-03-01\n\n" + "palavra " * 40 + "\n"
        titulo = map_timeline_file("KNOWLEDGE-BASE/HISTORICO/TIMELINE.md", content)[0].snapshot["titulo"]
        assert len(titulo) <= 120 and titulo.endswith("…")


# ---------------------------------------------------------------------------
# Project state JSON
# ---------------------------------------------------------------------------


class TestMapJsonStateFile:
    def test_open_questions_items_mapped(self):
        content = json.dumps(
            [
                {
                    "codigo": "Q-01",
                    "pergunta": "Qual o SLA de resposta?",
                    "por_que_importa": "Define expectativa do cliente",
                    "bloqueia": "T-001",
                    "destino_kb": None,
                    "estado": "aberta",
                    "resposta": None,
                    "respondida_em": None,
                }
            ]
        )
        entities = map_json_state_file("projects/state/open-questions.json", content)
        assert len(entities) == 1
        e = entities[0]
        assert e.entity_type == "open_question"
        assert e.natural_key == "Q-01"
        assert e.snapshot["pergunta"] == "Qual o SLA de resposta?"
        assert e.snapshot["estado"] == "aberta"

    def test_roadmap_items_mapped(self):
        content = json.dumps(
            [
                {
                    "codigo": "P1",
                    "titulo": "Fundacao",
                    "objetivo": "Estabelecer a base tecnica",
                    "concluida_quando": "seed publicado",
                    "estado": "em-andamento",
                    "ordem": 1,
                }
            ]
        )
        entities = map_json_state_file("projects/state/roadmap.json", content)
        assert entities[0].entity_type == "roadmap_phase"
        assert entities[0].natural_key == "P1"
        assert entities[0].snapshot["ordem"] == 1

    def test_tasks_items_mapped(self):
        content = json.dumps(
            [
                {
                    "codigo": "T-001",
                    "titulo": "Construir importador",
                    "fase": "P1",
                    "detalhe": "JSONL para KnowledgeStore",
                    "estado": "em-andamento",
                    "bloqueada_por": None,
                }
            ]
        )
        entities = map_json_state_file("projects/state/tasks.json", content)
        assert entities[0].entity_type == "task"
        assert entities[0].natural_key == "T-001"
        assert entities[0].snapshot["fase"] == "P1"

    def test_invalid_json_raises_bundle_invalid(self):
        with pytest.raises(BundleInvalid):
            map_json_state_file("projects/state/tasks.json", "{not valid json")

    def test_non_array_raises_bundle_invalid(self):
        with pytest.raises(BundleInvalid):
            map_json_state_file("projects/state/tasks.json", json.dumps({"foo": "bar"}))


# ---------------------------------------------------------------------------
# Dispatch (map_line) — skip list + unmapped-path warning
# ---------------------------------------------------------------------------


class TestMapLineDispatch:
    @pytest.mark.parametrize(
        "path",
        [
            "KNOWLEDGE-BASE/AGENT-CONTEXT.md",
            "KNOWLEDGE-BASE/INDEX.md",
            "KNOWLEDGE-BASE/DECISOES/INDEX.md",
        ],
    )
    def test_root_index_files_are_skipped(self, path):
        result = map_line(path, "# Indice\n\nGerado automaticamente.")
        assert result.skipped is True
        assert result.entities == ()
        assert result.warning is None

    def test_unknown_path_produces_warning_not_error(self):
        result = map_line("README.md", "# README\n\nQualquer coisa.")
        assert result.skipped is True
        assert result.warning is not None
        assert "README.md" in result.warning

    def test_kb_file_dispatches_to_kb_mapping(self):
        result = map_line("KNOWLEDGE-BASE/GERAL/x.md", "# X\n\nCorpo.")
        assert len(result.entities) == 1
        assert result.entities[0].entity_type == "kb_entry"

    def test_decisions_0001_dispatches_to_bundle_mapping(self):
        content = (
            "---\ndata: 2026-01-01\n---\n"
            "| # | Decisão | Motivo |\n|---|---|---|\n"
            "| D-01 | Texto | Motivo |\n"
        )
        result = map_line("KNOWLEDGE-BASE/DECISOES/0001-decisoes.md", content)
        assert len(result.entities) == 1
        assert result.entities[0].natural_key == "D-01"

    def test_decisions_single_file_not_0001_dispatches_to_single_mapping(self):
        content = "---\ncodigo: D-05\ntitulo: Teste\ndata: 2026-01-01\nestado: vigente\n---\n"
        result = map_line("KNOWLEDGE-BASE/DECISOES/0005-teste.md", content)
        assert len(result.entities) == 1
        assert result.entities[0].natural_key == "D-05"

    def test_timeline_path_dispatches_to_timeline_mapping(self):
        content = "## 2026-01-01 — Evento\n\nDescricao.\n"
        result = map_line("KNOWLEDGE-BASE/HISTORICO/TIMELINE.md", content)
        assert len(result.entities) == 1
        assert result.entities[0].entity_type == "timeline_event"

    def test_json_state_path_dispatches_to_json_mapping(self):
        content = json.dumps([{"codigo": "T-002", "titulo": "X", "fase": "P1",
                                "detalhe": None, "estado": "pendente", "bloqueada_por": None}])
        result = map_line("projects/state/tasks.json", content)
        assert len(result.entities) == 1
        assert result.entities[0].entity_type == "task"

    def test_docs_spec_dispatches_to_geral_kb_mapping(self):
        result = map_line("docs/SPEC.md", "# Spec\n\nCorpo.")
        assert len(result.entities) == 1
        assert result.entities[0].snapshot["categoria"] == "geral"

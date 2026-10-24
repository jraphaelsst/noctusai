"""`check_silent_refusal` — a refusal the user never sees (2026-10-24, N=4: F75b F76 F78 F86).

Rule A `empty_over_error`: a query's empty branch reachable while the query is in ERROR (F76 — a
failed imóvel search rendered "Nenhum imóvel encontrado" + "Cadastrar novo"). Rule B: an upload
whose failure nobody observes (F78 / F86), or `useUploadDocumento` whose `erro` is never rendered.
Each rule is pinned by a violating AND a clean fixture (synthetic components), plus the live tree.

→ KB § PATTERNS/frontend/silent-refusal.md
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import (  # noqa: E402
    REPO_ROOT,
    _SILENT_REFUSAL_SCRIPT_REL,
    check_silent_refusal,
)

_SCRIPT = REPO_ROOT.joinpath(*_SILENT_REFUSAL_SCRIPT_REL)
_TOOLING = (
    shutil.which("node") is not None
    and _SCRIPT.exists()
    and (_SCRIPT.parent / "node_modules" / "ts-morph").exists()
)
pytestmark = pytest.mark.skipif(
    not _TOOLING, reason="node / ts-morph unavailable — run `cd mcp/noctusai/node && npm ci`"
)


def _repo(tmp: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        p = tmp / "products" / "demo" / "frontend" / "src" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return tmp


def _rules(tmp: Path, files: dict[str, str]) -> list[tuple[str, int]]:
    return [(i["rule"], i["line"]) for i in check_silent_refusal(_repo(tmp, files)) if "rule" in i]


# ─── Rule A ──────────────────────────────────────────────────────────────────

# The F76 shape: the failed search falls through to "Nenhum" + the create action.
SEARCH_EMPTY_OVER_ERROR = """
export function Picker({ termo }: { termo: string }) {
  const busca = useBuscaImoveis(termo);
  const resultados = busca.data?.items ?? [];
  const buscaVazia = termo.length >= 2 && !busca.isFetching && resultados.length === 0;
  return (
    <div>
      {buscaVazia ? (
        <div><p>Nenhum imóvel encontrado.</p><button>Cadastrar novo</button></div>
      ) : (
        <ul>{resultados.map((r) => <li key={r.id}>{r.codigo}</li>)}</ul>
      )}
    </div>
  );
}
"""

SEARCH_ERROR_FIRST = """
export function Picker({ termo }: { termo: string }) {
  const busca = useBuscaImoveis(termo);
  const resultados = busca.data?.items ?? [];
  const buscaErro = busca.isError;
  const buscaVazia = termo.length >= 2 && !busca.isFetching && !busca.isError && resultados.length === 0;
  return (
    <div>
      {buscaErro ? (
        <p>Não foi possível buscar.</p>
      ) : buscaVazia ? (
        <p>Nenhum imóvel encontrado.</p>
      ) : (
        <ul>{resultados.map((r) => <li key={r.id}>{r.codigo}</li>)}</ul>
      )}
    </div>
  );
}
"""

DESTRUCTURED_AND_RENDER = """
export function Lista() {
  const { data: itens = [], isPending } = useItens();
  return <div>{!isPending && itens.length === 0 && <p>Nenhum item.</p>}</div>;
}
"""

DESTRUCTURED_EARLY_RETURN = """
export function Lista() {
  const { data: itens = [], isPending, isError } = useItens();
  if (isError) return <p>Falhou.</p>;
  return <div>{!isPending && itens.length === 0 && <p>Nenhum item.</p>}</div>;
}
"""

# `q.data?.length === 0` is FALSE when data is undefined (error) — not a finding;
# `!q.data?.length` is TRUE on error — a finding.
UNDEFAULTED_SAFE = """
export function A() {
  const q = useItens();
  return <div>{q.data?.length === 0 && <p>Nenhum.</p>}{q.isPending && <span/>}</div>;
}
"""
NEGATED_LENGTH = """
export function A() {
  const q = useItens();
  return <div>{!q.data?.length && <p>Nenhum.</p>}{q.isPending && <span/>}</div>;
}
"""

# The two-signal SKELETON gate is a loading gate, not an empty branch.
SKELETON_GATE = """
export function A() {
  const q = useItens();
  const rows = q.data ?? [];
  return q.isPending && rows.length === 0 ? <Skeleton /> : <ul>{rows.map((r) => <li key={r}>{r}</li>)}</ul>;
}
"""

# An `isEmpty=` prop next to an `error=` prop: the component's own priority decides.
CHART_ERROR_PROP = """
export function A() {
  const q = useSerie();
  const rows = q.data ?? [];
  return <ChartCard error={q.isError ? "Erro" : null} isEmpty={rows.length === 0}><Chart data={rows} /></ChartCard>;
}
"""
CHART_NO_ERROR_PROP = """
export function A() {
  const q = useSerie();
  const rows = q.data ?? [];
  return <ChartCard loading={q.isPending} isEmpty={rows.length === 0}><Chart data={rows} /></ChartCard>;
}
"""

ESCAPED = """
export function A() {
  const q = useItens();
  const rows = q.data ?? [];
  // noc-allow: silent-refusal — synthetic: the query is a static fixture that cannot fail
  return <div>{rows.length === 0 && <p>Nenhum.</p>}{q.isPending && <span/>}</div>;
}
"""


def test_rule_a_f76_search_shape_flagged(tmp_path):
    assert ("empty_over_error", 8) in _rules(tmp_path, {"Picker.tsx": SEARCH_EMPTY_OVER_ERROR})


def test_rule_a_error_branch_first_is_clean(tmp_path):
    assert _rules(tmp_path, {"Picker.tsx": SEARCH_ERROR_FIRST}) == []


def test_rule_a_destructured_default_flagged_and_early_return_clean(tmp_path):
    assert [r for r, _ in _rules(tmp_path, {"L.tsx": DESTRUCTURED_AND_RENDER})] == ["empty_over_error"]
    assert _rules(tmp_path / "b", {"L.tsx": DESTRUCTURED_EARLY_RETURN}) == []


def test_rule_a_undefaulted_length_is_safe_but_negated_length_is_not(tmp_path):
    assert _rules(tmp_path, {"A.tsx": UNDEFAULTED_SAFE}) == []
    assert [r for r, _ in _rules(tmp_path / "b", {"A.tsx": NEGATED_LENGTH})] == ["empty_over_error"]


def test_rule_a_skeleton_gate_is_not_an_empty_branch(tmp_path):
    assert _rules(tmp_path, {"A.tsx": SKELETON_GATE}) == []


def test_rule_a_empty_prop_guarded_only_by_a_sibling_error_prop(tmp_path):
    assert _rules(tmp_path, {"A.tsx": CHART_ERROR_PROP}) == []
    assert [r for r, _ in _rules(tmp_path / "b", {"A.tsx": CHART_NO_ERROR_PROP})] == ["empty_over_error"]


def test_rule_a_escape_hatch(tmp_path):
    assert _rules(tmp_path, {"A.tsx": ESCAPED}) == []


# ─── Rule B ──────────────────────────────────────────────────────────────────

MUTATE_UNOBSERVED = """
export function Slot() {
  const upload = useUploadDoc();
  return <input type="file" onChange={(e) => { const file = e.target.files?.[0]; if (file) upload.mutate({ file }); }} />;
}
"""
MUTATE_ON_ERROR = """
export function Slot() {
  const upload = useUploadDoc();
  return <input type="file" onChange={(e) => { const file = e.target.files?.[0]; if (file) upload.mutate({ file }, { onError: () => toast.error("x") }); }} />;
}
"""
MUTATE_ERROR_RENDERED = """
export function Slot() {
  const upload = useUploadDoc();
  return <div><input type="file" onChange={(e) => { const file = e.target.files?.[0]; if (file) upload.mutate({ file }); }} />{upload.error && <p>{upload.error.message}</p>}</div>;
}
"""
VOID_ON_UPLOAD = """
export function Container() {
  const docs = useDocs();
  return <Secao onUpload={(file, tipo) => docs.upload.mutate({ file, tipo })} />;
}
"""
PROMISE_ON_UPLOAD = """
export function Container() {
  const docs = useDocs();
  return <Secao onUpload={(file, tipo) => docs.upload.mutateAsync({ file, tipo })} />;
}
"""
RAW_UPLOAD_NO_CATCH = """
export function Pagina() {
  const enviar = async (file: File) => { const form = new FormData(); form.append("file", file); await api.upload("/api/x", form); };
  return <input type="file" onChange={(e) => void enviar(e.target.files![0])} />;
}
"""
RAW_UPLOAD_IN_ORGAN = """
export function Pagina() {
  const envio = useUploadDocumento(async (file: File) => { const form = new FormData(); form.append("file", file); await api.upload("/api/x", form); });
  return <div><input type="file" onChange={(e) => void envio.enviar(e.target.files![0])} /><UploadErro erro={envio.erro} /></div>;
}
"""
ORGAN_ERRO_UNREAD = """
export function Pagina() {
  const envio = useUploadDocumento((file: File) => upload.mutateAsync({ file }));
  return <input type="file" onChange={(e) => void envio.enviar(e.target.files![0])} />;
}
"""


@pytest.mark.parametrize(
    ("src", "expected"),
    [
        (MUTATE_UNOBSERVED, ["upload_mutate_unhandled"]),
        (MUTATE_ON_ERROR, []),
        (MUTATE_ERROR_RENDERED, []),
        (VOID_ON_UPLOAD, ["upload_void_callback"]),
        (PROMISE_ON_UPLOAD, []),
        (RAW_UPLOAD_NO_CATCH, ["upload_raw_unhandled"]),
        (RAW_UPLOAD_IN_ORGAN, []),
        (ORGAN_ERRO_UNREAD, ["upload_organ_erro_unread"]),
    ],
    ids=[
        "mutate-unobserved", "mutate-onError", "mutate-error-rendered", "void-onUpload",
        "promise-onUpload", "raw-upload-no-catch", "raw-upload-in-organ", "organ-erro-unread",
    ],
)
def test_rule_b(tmp_path, src, expected):
    assert [r for r, _ in _rules(tmp_path, {"Upload.tsx": src})] == expected


def test_tests_are_not_scanned(tmp_path):
    assert _rules(tmp_path, {"Slot.test.tsx": MUTATE_UNOBSERVED}) == []


def test_live_tree_is_clean():
    """Every live hit was fixed when the keeper landed (no baseline): the tree stays clean."""
    issues = check_silent_refusal()
    assert issues == [], "\n".join(f"{i.get('file')}: {i['issue']}" for i in issues)

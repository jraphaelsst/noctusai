"""`check_mutation_family_write` + `check_job_start_without_handoff` — the screen must not lie
after a write or an async job (2026-10-24, social-wiring F87/F88). Families derive from the
product's own query keys (`query_key_family_predicate`), never a hand list.

→ KB § PATTERNS/frontend/mutation-cache-writes.md
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import query_key_family_predicate as qkf  # noqa: E402
from tools.noctus.dev.compliance import (  # noqa: E402
    check_job_start_without_handoff,
    check_mutation_family_write,
    check_stale_after_write,
)

SRC = "products/demo/frontend/src"

KEYS = """
export const NEGOCIACAO_KEY = (clienteId: string) => ["sw", "clientes", clienteId, "negociacao"] as const;
const base = (id: string) => `/api/clientes/${id}/negociacao`;
export function useNegociacao(id: string) {
  return useQuery({ queryKey: NEGOCIACAO_KEY(id), queryFn: () => api.get(base(id)) });
}
"""

# A sibling aggregate in ANOTHER file, its key a named child of the row's key (F88).
ESTRUTURADA = """
import { NEGOCIACAO_KEY } from "@/hooks/useNegociacao";
const ESTRUTURADA_KEY = (id: string) => [...NEGOCIACAO_KEY(id), "estruturada"] as const;
export function useNegociacaoEstruturada(id: string) {
  return useQuery({ queryKey: ESTRUTURADA_KEY(id), queryFn: () => api.get(`/x/${id}`) });
}
"""

F88_EXACT_WRITE = KEYS + """
export function useNegociacaoMutation(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (p: Patch) => api.patch<Negociacao>(base(id), p),
    onSuccess: (data) => qc.setQueryData(NEGOCIACAO_KEY(id), data),
  });
}
"""

F88_FAMILY_INVALIDATED = KEYS + """
export function useNegociacaoMutation(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (p: Patch) => api.patch<Negociacao>(base(id), p),
    onSuccess: (data) => {
      qc.setQueryData(NEGOCIACAO_KEY(id), data);
      void qc.invalidateQueries({ queryKey: NEGOCIACAO_KEY(id) });
    },
  });
}
"""

F88_VIA_HELPER = KEYS + """
function refreshCliente(qc: QueryClient, id: string) {
  return qc.invalidateQueries({ queryKey: ["sw", "clientes"] });
}
export function useNegociacaoMutation(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (p: Patch) => api.patch<Negociacao>(base(id), p),
    onSuccess: (data) => { qc.setQueryData(NEGOCIACAO_KEY(id), data); void refreshCliente(qc, id); },
  });
}
"""

F88_CACHE_WRITE = KEYS + """
export function useNegociacaoMutation(id: string) {
  return useCacheWriteMutation<Negociacao, Patch>({
    mutationFn: (p) => api.patch<Negociacao>(base(id), p),
    targets: [{ queryKey: NEGOCIACAO_KEY(id), commit: (_o, saved) => saved }],
  });
}
"""

F88_ALLOWED = KEYS + """
export function useNegociacaoMutation(id: string) {
  const qc = useQueryClient();
  return useMutation({ // noc-allow: exact-write — the estruturada aggregate does not read the fields this PATCH can change
    mutationFn: (p: Patch) => api.patch<Negociacao>(base(id), p),
    onSuccess: (data) => qc.setQueryData(NEGOCIACAO_KEY(id), data),
  });
}
"""

# `[...chats]` → `[...chats, <id>, "messages"]`: a sub-resource of ONE element, not derived.
CHATS = """
const chatsKey = (c: string) => ["wa", c, "chats"] as const;
export function useChats(c: string) { return useQuery({ queryKey: chatsKey(c), queryFn: () => api.get("/c") }); }
export function useMessages(c: string, chat: string) {
  return useQuery({ queryKey: [...chatsKey(c), chat, "messages"], queryFn: () => api.get("/m") });
}
export function useMarkRead(c: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (chat: string) => api.post(`/c/${chat}/read`),
    onMutate: (chat) => { qc.setQueryData(chatsKey(c), (p: Chat[]) => p); },
  });
}
"""

PARTES = """
import { jobPolling } from "@noctusai/lib";
export const partesKey = (id: string, at?: string | null) => ["sw", "clientes", id, "certidoes", "partes", at ?? null] as const;
export function usePartes(id: string) {
  return useQuery({
    queryKey: partesKey(id),
    queryFn: () => api.get<Grid>(`/p/${id}`),
    ...jobPolling<Grid>((d) => emAndamento(d), 4000),
  });
}
function useInvalidatePartes(id: string) {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: ["sw", "clientes", id, "certidoes", "partes"] });
}
"""

TYPES = """
export interface EmissaoResponse {
  consulta_id: string;
  resultados: { resultado_id: string }[];
}
"""

# F87 as shipped: an honest allow saying the work is async, a bare invalidate through a helper.
F87_ALLOW_REASON = PARTES + """
export function useSolicitarEmissao(id: string) {
  const invalidate = useInvalidatePartes(id);
  return useMutation({ // noc-allow: invalidate-only — queues emissions that finish asynchronously; the cells arrive via the polled partes read
    mutationFn: (x: Input) => api.post(`/p/${id}/emissao`, x),
    onSuccess: () => { void invalidate(); },
  });
}
"""

F87_RESPONSE_TYPE = PARTES + """
import type { EmissaoResponse } from "@/types/certidoes";
export function useSolicitarEmissao(id: string) {
  const qc = useQueryClient();
  return useMutation({ // noc-allow: invalidate-only — nothing to place
    mutationFn: (x: Input) => api.post<EmissaoResponse>(`/p/${id}/emissao`, x),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sw", "clientes", id, "certidoes", "partes"] }),
  });
}
"""

F87_HANDED_OFF = PARTES + """
import { handOffToPolling } from "@noctusai/lib";
import type { EmissaoResponse } from "@/types/certidoes";
function useHandOffPartes(id: string) {
  const qc = useQueryClient();
  return () => handOffToPolling(qc, ["sw", "clientes", id, "certidoes", "partes"]);
}
export function useSolicitarEmissao(id: string) {
  const handOff = useHandOffPartes(id);
  return useMutation({ // noc-allow: invalidate-only — queues emissions that finish asynchronously
    mutationFn: (x: Input) => api.post<EmissaoResponse>(`/p/${id}/emissao`, x),
    onSuccess: () => { void handOff(); },
  });
}
"""

F87_WRITES_POLLED = PARTES + """
import type { EmissaoResponse } from "@/types/certidoes";
export function useSolicitarEmissao(id: string) {
  return useCacheWriteMutation<EmissaoResponse, Input>({
    mutationFn: (x) => api.post<EmissaoResponse>(`/p/${id}/emissao`, x),
    targets: [{ queryKey: partesKey(id), commit: (old, r) => comEmissao(old, r) }],
  });
}
"""

CANCEL_ALLOWED = PARTES + """
export function useCancelar(id: string) {
  const invalidate = useInvalidatePartes(id);
  return useMutation({ // noc-allow: invalidate-only — cancels queued scrapes · noc-allow: no-job-handoff — a cancel ENDS work
    mutationFn: () => api.post(`/p/${id}/cancelar`),
    onSuccess: () => invalidate(),
  });
}
"""

ACCEPTED_202_NO_READ = """
export function useRegenerar() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post("/guias/regenerar").then((r) => (r.status === 202 ? r : r)),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["guias"] }),
  });
}
"""


def _tree(root: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        p = root / SRC / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return root


class TestKeyResolution:
    def test_factory_spread_and_cross_file_import_resolve_to_segments(self, tmp_path: Path) -> None:
        _tree(tmp_path, {"hooks/useNegociacao.ts": KEYS, "hooks/useNegociacaoEstruturada.ts": ESTRUTURADA})
        src = tmp_path / SRC
        product = qkf.Product(src, sorted(src.rglob("*.ts")))
        _mutations, reads = qkf.scan(product)
        assert {r.key for r in reads} == {
            ("sw", "clientes", "*", "negociacao"),
            ("sw", "clientes", "*", "negociacao", "estruturada"),
        }

    def test_prefix_semantics(self) -> None:
        assert qkf.key_prefix_of(("a", "*"), ("a", "*", "b"))
        assert not qkf.key_prefix_of(("a", "x"), ("a", "*", "b"))
        assert qkf.key_prefix_of((), ("a",))


class TestCheckMutationFamilyWrite:
    def _issues(self, tmp_path: Path, hooks: str) -> list[dict]:
        _tree(tmp_path, {"hooks/useNegociacao.ts": hooks, "hooks/useNegociacaoEstruturada.ts": ESTRUTURADA})
        return check_mutation_family_write(tmp_path)

    def test_f88_exact_write_leaves_the_derived_aggregate_stale(self, tmp_path: Path) -> None:
        issues = self._issues(tmp_path, F88_EXACT_WRITE)
        assert len(issues) == 1
        assert "'estruturada'" in issues[0]["issue"] and issues[0]["severity"] == "high"

    def test_invalidating_the_family_prefix_is_clean(self, tmp_path: Path) -> None:
        assert self._issues(tmp_path, F88_FAMILY_INVALIDATED) == []

    def test_an_ancestor_invalidated_through_a_helper_is_clean(self, tmp_path: Path) -> None:
        assert self._issues(tmp_path, F88_VIA_HELPER) == []

    def test_cache_write_mutation_settles_the_family_by_construction(self, tmp_path: Path) -> None:
        assert self._issues(tmp_path, F88_CACHE_WRITE) == []

    def test_exact_write_allow_is_honoured(self, tmp_path: Path) -> None:
        assert self._issues(tmp_path, F88_ALLOWED) == []

    def test_an_elements_sub_resource_is_not_a_derived_view(self, tmp_path: Path) -> None:
        _tree(tmp_path, {"hooks/useChats.ts": CHATS})
        assert check_mutation_family_write(tmp_path) == []


class TestCheckJobStartWithoutHandoff:
    def _issues(self, tmp_path: Path, hooks: str) -> list[dict]:
        _tree(tmp_path, {"hooks/useCertidoesPartes.ts": hooks, "types/certidoes.ts": TYPES})
        return check_job_start_without_handoff(tmp_path)

    def test_f87_async_allow_reason_without_handoff_is_flagged(self, tmp_path: Path) -> None:
        issues = self._issues(tmp_path, F87_ALLOW_REASON)
        assert len(issues) == 1
        assert "handOffToPolling" in issues[0]["issue"]
        assert "'partes'" in issues[0]["issue"]  # names the polled read it reaches

    def test_a_job_id_in_the_response_type_marks_a_job_start(self, tmp_path: Path) -> None:
        issues = self._issues(tmp_path, F87_RESPONSE_TYPE)
        assert len(issues) == 1 and "consulta_id" in issues[0]["issue"]

    def test_handing_off_through_a_helper_is_clean(self, tmp_path: Path) -> None:
        assert self._issues(tmp_path, F87_HANDED_OFF) == []

    def test_writing_the_polled_entry_is_clean(self, tmp_path: Path) -> None:
        assert self._issues(tmp_path, F87_WRITES_POLLED) == []

    def test_no_job_handoff_allow_is_honoured(self, tmp_path: Path) -> None:
        assert self._issues(tmp_path, CANCEL_ALLOWED) == []

    def test_a_202_with_no_polled_read_says_to_add_one(self, tmp_path: Path) -> None:
        _tree(tmp_path, {"hooks/useGuias.ts": ACCEPTED_202_NO_READ})
        issues = check_job_start_without_handoff(tmp_path)
        assert len(issues) == 1 and "no jobPolling read is reached" in issues[0]["issue"]


class TestCheckStaleAfterWrite:
    def test_one_scan_reports_both_classes(self, tmp_path: Path) -> None:
        _tree(tmp_path, {
            "hooks/useNegociacao.ts": F88_EXACT_WRITE,
            "hooks/useNegociacaoEstruturada.ts": ESTRUTURADA,
            "hooks/useCertidoesPartes.ts": F87_ALLOW_REASON,
        })
        issues = check_stale_after_write(tmp_path)
        assert {Path(i["file"]).name for i in issues} == {"useNegociacao.ts", "useCertidoesPartes.ts"}

    def test_test_files_are_not_scanned(self, tmp_path: Path) -> None:
        _tree(tmp_path, {"hooks/useNegociacao.test.ts": F88_EXACT_WRITE, "hooks/useNegociacaoEstruturada.ts": ESTRUTURADA})
        assert check_stale_after_write(tmp_path) == []

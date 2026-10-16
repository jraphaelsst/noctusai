/** Lais › Leads (`/lais/leads`) — contract §5 W3: contatos table, filters, send-to-SW, bulk, CSV (admin). */
import { useState } from "react";
import { AlertCircle, Filter, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { useConfirm } from "@noctusai/lib";
import { useIsOrgAdmin } from "@noctusai/lib/design-system";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { FiltroDrawer } from "@/components/lais/leads/FiltroDrawer";
import { LeadsTable } from "@/components/lais/leads/LeadsTable";
import { ResumoPanel } from "@/components/lais/leads/ResumoPanel";
import {
  PAGE_SIZE, baixarLeadsCsv, codigoErro, contarFiltros, filtrosVazios, mensagemCodigoLead, mensagemErroLeads,
  useEnviarLead, useEnviarLote, useLeadsLais, type FiltrosLeads, type LeadLais,
} from "@/hooks/useLaisLeads";
import { LAIS_LABEL, LAIS_PAGES } from "@/nav/lais";

const LIMITE_LOTE = 100;

export default function LaisLeads() {
  const isAdmin = useIsOrgAdmin();
  const confirm = useConfirm();
  const [filtros, setFiltros] = useState<FiltrosLeads>(filtrosVazios);
  const [page, setPage] = useState(1);
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [drawer, setDrawer] = useState(false);
  const [resumo, setResumo] = useState<LeadLais | null>(null);
  const [lote, setLote] = useState<{ ok: number; erro: { id: string; code: string }[] } | null>(null);
  const q = useLeadsLais(filtros, page);
  const enviar = useEnviarLead();
  const enviarLote = useEnviarLote();

  // Two signals off `data` — never `isLoading`.
  const showSkeleton = q.isPending && !q.data;
  const isRefreshing = q.isFetching && !!q.data;
  const items = q.data?.items ?? [];
  const total = q.data?.total ?? 0;
  const paginas = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const nFiltros = contarFiltros(filtros);

  const aplicar = (f: FiltrosLeads) => { setFiltros(f); setPage(1); setSel(new Set()); };
  const toggle = (id: string) => setSel((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const toggleTodos = (marcar: boolean) => setSel((s) => { const n = new Set(s); items.forEach((l) => (marcar ? n.add(l.id) : n.delete(l.id))); return n; });

  const onEnviar = async (l: LeadLais) => {
    if (!(await confirm({ title: "Enviar ao SW?", description: "O lead será criado (ou atualizado) no SW com o resumo da Julia.", confirmLabel: "Enviar ao SW" }))) return;
    enviar.mutate(l.id, {
      onSuccess: () => toast.success("Lead enviado ao SW"),
      onError: (e) => {
        const c = codigoErro(e);
        // 409 ja_enviado is an outcome, not a failure; 422 explains itself.
        (c === "ja_enviado" ? toast.info : toast.error)(mensagemErroLeads(e, "Não foi possível enviar o lead."));
      },
    });
  };
  const onLote = async () => {
    const ids = [...sel];
    if (!(await confirm({ title: `Enviar ${ids.length} lead(s) ao SW?`, confirmLabel: "Enviar selecionados" }))) return;
    enviarLote.mutate(ids, {
      onSuccess: (r) => {
        setLote({ ok: r.ok.length, erro: r.erro });
        setSel(new Set(r.erro.map((x) => x.id)));
        if (!r.erro.length) toast.success(`${r.ok.length} lead(s) enviados ao SW`);
      },
      onError: (e) => toast.error(mensagemErroLeads(e, "Não foi possível enviar os leads selecionados.")),
    });
  };
  const onBaixar = async () => {
    try { await baixarLeadsCsv(filtros, [...sel]); } catch (e) { toast.error(mensagemErroLeads(e, "Não foi possível baixar os leads.")); }
  };

  return (
    <div className="container max-w-6xl space-y-4 py-6">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-2xl font-bold">{LAIS_LABEL} · {LAIS_PAGES.leads.name}</h1>
          <p className="text-sm text-muted-foreground">Contatos atendidos pela Julia e o envio de cada um ao SW.</p>
        </div>
        <div className="flex items-center gap-2">
          {isRefreshing && <span className="flex items-center gap-1 text-xs text-muted-foreground" data-testid="leads-refreshing"><Loader2 className="h-3 w-3 animate-spin" /> Atualizando…</span>}
          <Button variant="outline" onClick={() => setDrawer(true)} data-testid="leads-filtros">
            <Filter className="mr-1 h-4 w-4" /> Filtros{nFiltros > 0 ? ` (${nFiltros})` : ""}
          </Button>
        </div>
      </header>

      {sel.size > 0 && (
        <div className="flex flex-wrap items-center gap-2 rounded-md border bg-muted/50 p-2" data-testid="leads-bulk">
          <span className="text-sm">{sel.size} selecionado(s)</span>
          <Button size="sm" onClick={onLote} disabled={sel.size > LIMITE_LOTE || enviarLote.isPending}>Enviar selecionados</Button>
          {isAdmin && <Button size="sm" variant="outline" onClick={onBaixar}>Baixar selecionados</Button>}
          {sel.size > LIMITE_LOTE && <span className="text-xs text-destructive" data-testid="leads-limite">Máximo de {LIMITE_LOTE} por envio em lote.</span>}
          <Button size="sm" variant="ghost" onClick={() => setSel(new Set())}>Limpar seleção</Button>
        </div>
      )}
      {lote && (
        <div role="status" className="rounded-md border p-2 text-sm" data-testid="leads-lote-resultado">
          {lote.ok} enviado(s)
          {lote.erro.length > 0 && <> · {lote.erro.length} com erro: {lote.erro.map((e) => mensagemCodigoLead(e.code, e.code)).filter((m, i, a) => a.indexOf(m) === i).join("; ")}</>}
        </div>
      )}

      {showSkeleton ? (
        <div className="space-y-2" data-testid="leads-skeleton">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-12 w-full" />)}</div>
      ) : q.isError && !q.data ? (
        <Card><CardContent className="flex items-center justify-between gap-3 py-6" data-testid="leads-erro">
          <span className="flex items-center gap-2 text-sm text-destructive"><AlertCircle className="h-4 w-4" /> Não foi possível carregar os leads.</span>
          <Button variant="outline" size="sm" onClick={() => void q.refetch()}>Tentar de novo</Button>
        </CardContent></Card>
      ) : items.length === 0 ? (
        <Card><CardContent className="py-10 text-center text-sm text-muted-foreground" data-testid="leads-vazio">
          {nFiltros > 0 ? "Nenhum lead encontrado com esses filtros." : "Ainda não há leads atendidos pela Julia."}
          {nFiltros > 0 && <div className="mt-2"><Button size="sm" variant="outline" onClick={() => aplicar(filtrosVazios())}>Limpar filtros</Button></div>}
        </CardContent></Card>
      ) : (
        <Card><CardContent className="overflow-x-auto p-0">
          <LeadsTable items={items} selecionados={sel} onToggle={toggle} onToggleTodos={toggleTodos}
            onResumo={setResumo} onEnviar={onEnviar} enviandoId={enviar.isPending ? (enviar.variables ?? null) : null} />
        </CardContent></Card>
      )}

      {total > PAGE_SIZE && (
        <div className="flex items-center justify-end gap-2 text-sm" data-testid="leads-paginacao">
          <span>Página {page} de {paginas} · {total} leads</span>
          <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Anterior</Button>
          <Button size="sm" variant="outline" disabled={page >= paginas} onClick={() => setPage((p) => p + 1)}>Próxima</Button>
        </div>
      )}

      {drawer && <FiltroDrawer filtros={filtros} onAplicar={aplicar} onClose={() => setDrawer(false)} />}
      {resumo && <ResumoPanel lead={resumo} onClose={() => setResumo(null)} />}
    </div>
  );
}

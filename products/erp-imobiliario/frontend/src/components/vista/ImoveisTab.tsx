/**
 * Vista showcase — Imóveis tab. Property catalog + detail drill-down.
 * Moved out of `pages/VistaShowcase.tsx` unchanged (2026-08-22 split).
 */
import { useState } from 'react';
import { AlertTriangle, RefreshCcw } from 'lucide-react';
import { Badge } from '@noctusai/seed/components/ui/badge';
import { Button } from '@noctusai/seed/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@noctusai/seed/components/ui/card';
import { Skeleton } from '@noctusai/seed/components/ui/skeleton';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@noctusai/seed/components/ui/dialog';
import {
  useVistaImoveis,
  useVistaImovelDetalhes,
  type VistaImoveisFilters,
  type VistaShowcaseImovel,
} from '@/hooks/useVistaShowcase';
import { ErrorPanel, FilterInput, PaginationBar, formatArea, formatBRL } from './shared';

export function ImoveisTab() {
  const [page, setPage] = useState(1);
  const [filters, setFilters] = useState<VistaImoveisFilters>({});
  const [draftFilters, setDraftFilters] = useState<VistaImoveisFilters>({});
  const [openDetail, setOpenDetail] = useState<string | null>(null);

  const { data, isLoading, isError, error, refetch, isFetching } = useVistaImoveis(true, page, 50, filters);

  const applyFilters = () => {
    setFilters(draftFilters);
    setPage(1);
  };
  const resetFilters = () => {
    setDraftFilters({});
    setFilters({});
    setPage(1);
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="p-4 grid grid-cols-1 md:grid-cols-6 gap-3 items-end">
          <FilterInput label="Status" value={draftFilters.status} onChange={v => setDraftFilters(f => ({ ...f, status: v }))} />
          <FilterInput label="Categoria" value={draftFilters.categoria} onChange={v => setDraftFilters(f => ({ ...f, categoria: v }))} />
          <FilterInput label="Cidade" value={draftFilters.cidade} onChange={v => setDraftFilters(f => ({ ...f, cidade: v }))} />
          <FilterInput label="Bairro" value={draftFilters.bairro} onChange={v => setDraftFilters(f => ({ ...f, bairro: v }))} />
          <FilterInput label="Finalidade" value={draftFilters.finalidade} onChange={v => setDraftFilters(f => ({ ...f, finalidade: v }))} />
          <div className="flex gap-2">
            <Button onClick={applyFilters} disabled={isFetching} size="sm">Aplicar</Button>
            <Button onClick={resetFilters} variant="outline" size="sm">Limpar</Button>
          </div>
        </CardContent>
      </Card>

      {isError && (
        <Card className="border-rose-200 bg-rose-50">
          <CardContent className="p-4 flex items-center gap-3 text-sm text-rose-700">
            <AlertTriangle className="h-5 w-5" />
            <div className="flex-1">
              <strong>Falha ao consultar Vista.</strong> {(error as Error)?.message || 'Erro desconhecido.'}
            </div>
            <Button onClick={() => refetch()} size="sm" variant="outline">
              <RefreshCcw className="h-3.5 w-3.5 mr-1" /> Tentar novamente
            </Button>
          </CardContent>
        </Card>
      )}

      {isLoading && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-48 w-full" />)}
        </div>
      )}

      {!isLoading && !isError && data && (
        <>
          <PaginationBar
            page={page}
            pageSize={data.pagination?.quantidade ?? 0}
            total={data.pagination?.total ?? null}
            paginas={data.pagination?.paginas ?? null}
            fetchedAt={data.fetched_at}
            noun="imóveis"
            onPrev={() => setPage(p => Math.max(1, p - 1))}
            onNext={() => setPage(p => p + 1)}
            disabled={isFetching}
          />
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {data.items.map((imovel) => (
              <ImovelCard key={imovel.codigo} imovel={imovel} onOpen={() => setOpenDetail(imovel.codigo)} />
            ))}
          </div>
          {data.items.length === 0 && (
            <Card><CardContent className="p-8 text-center text-sm text-slate-500">Nenhum imóvel para os filtros informados.</CardContent></Card>
          )}
        </>
      )}

      <ImovelDetalhesDialog codigo={openDetail} onOpenChange={(open) => !open && setOpenDetail(null)} />
    </div>
  );
}

function ImovelCard({ imovel, onOpen }: { imovel: VistaShowcaseImovel; onOpen: () => void }) {
  return (
    <Card className="cursor-pointer hover:border-indigo-400 transition" onClick={onOpen}>
      {imovel.foto_url ? (
        <img
          src={imovel.foto_url}
          alt={imovel.titulo ?? imovel.codigo}
          className="w-full h-32 object-cover rounded-t-md"
          loading="lazy"
        />
      ) : (
        <div className="w-full h-32 bg-slate-100 rounded-t-md flex items-center justify-center text-slate-400 text-xs">
          Sem foto
        </div>
      )}
      <CardContent className="p-3 space-y-1">
        <div className="flex items-start justify-between gap-2">
          <div className="font-medium text-sm line-clamp-2">{imovel.titulo ?? imovel.codigo}</div>
          {imovel.status && <Badge variant="secondary" className="shrink-0 text-xs">{imovel.status}</Badge>}
        </div>
        <div className="text-xs text-slate-500">
          {[imovel.bairro, imovel.cidade].filter(Boolean).join(' · ') || '—'}
        </div>
        <div className="flex items-center gap-3 text-xs pt-1">
          <span className="font-medium">{formatBRL(imovel.valor_venda)}</span>
          {imovel.valor_locacao != null && (
            <span className="text-slate-500">aluguel {formatBRL(imovel.valor_locacao)}</span>
          )}
        </div>
        <div className="text-[11px] text-slate-500 flex gap-2">
          {imovel.dormitorios != null && <span>{imovel.dormitorios} dorm</span>}
          {imovel.vagas != null && <span>{imovel.vagas} vaga{imovel.vagas === 1 ? '' : 's'}</span>}
          {imovel.area_total != null && <span>{formatArea(imovel.area_total)}</span>}
        </div>
        <div className="text-[10px] text-slate-400 pt-1">{imovel.codigo}</div>
      </CardContent>
    </Card>
  );
}

function ImovelDetalhesDialog({
  codigo, onOpenChange,
}: { codigo: string | null; onOpenChange: (open: boolean) => void }) {
  const [showRaw, setShowRaw] = useState(false);
  const { data, isLoading, isError, error } = useVistaImovelDetalhes(codigo);
  const open = !!codigo;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {data?.base.titulo ?? codigo}
            {data?.base.status && <Badge variant="secondary">{data.base.status}</Badge>}
          </DialogTitle>
        </DialogHeader>
        {isLoading && <Skeleton className="h-64 w-full" />}
        {isError && (
          <div className="text-sm text-rose-700 bg-rose-50 border border-rose-200 rounded p-3">
            {(error as Error)?.message || 'Erro ao carregar detalhes.'}
          </div>
        )}
        {data && (
          <div className="space-y-4 text-sm">
            {data.base.foto_url && (
              <img src={data.base.foto_url} alt={data.codigo} className="w-full max-h-64 object-cover rounded" />
            )}
            <DetailGrid imovel={data.base} />
            {Object.keys(data.caracteristicas ?? {}).length > 0 && (
              <Card>
                <CardHeader><CardTitle className="text-sm">Características</CardTitle></CardHeader>
                <CardContent className="grid grid-cols-2 md:grid-cols-3 gap-2 text-xs">
                  {Object.entries(data.caracteristicas).map(([k, v]) => (
                    <div key={k} className="flex justify-between gap-2 border-b border-slate-100 py-1">
                      <span className="text-slate-500">{k}</span>
                      <span className="font-medium text-right">{String(v)}</span>
                    </div>
                  ))}
                </CardContent>
              </Card>
            )}
            <div>
              <Button variant="outline" size="sm" onClick={() => setShowRaw(s => !s)}>
                {showRaw ? 'Ocultar' : 'Mostrar'} payload bruto (debug)
              </Button>
              {showRaw && (
                <pre className="mt-2 p-3 bg-slate-50 border border-slate-200 rounded text-[11px] overflow-auto max-h-80">
                  {JSON.stringify(data.raw, null, 2)}
                </pre>
              )}
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

function DetailGrid({ imovel }: { imovel: VistaShowcaseImovel }) {
  const rows: Array<[string, React.ReactNode]> = [
    ['Código', imovel.codigo],
    ['Categoria', imovel.categoria ?? '—'],
    ['Finalidade', imovel.finalidade ?? '—'],
    ['Endereço', [imovel.endereco, imovel.bairro, imovel.cidade, imovel.estado].filter(Boolean).join(', ') || '—'],
    ['CEP', imovel.cep ?? '—'],
    ['Valor venda', formatBRL(imovel.valor_venda)],
    ['Valor locação', formatBRL(imovel.valor_locacao)],
    ['Área total', formatArea(imovel.area_total)],
    ['Área privativa', formatArea(imovel.area_privativa)],
    ['Dormitórios', imovel.dormitorios ?? '—'],
    ['Suítes', imovel.suites ?? '—'],
    ['Banheiros', imovel.banheiros ?? '—'],
    ['Vagas', imovel.vagas ?? '—'],
    ['Corretor', imovel.corretor_nome ?? '—'],
    ['Atualizado em', imovel.data_atualizacao ?? '—'],
  ];
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-1 text-xs">
      {rows.map(([label, value]) => (
        <div key={label} className="flex justify-between gap-2 border-b border-slate-100 py-1">
          <span className="text-slate-500">{label}</span>
          <span className="font-medium text-right">{value}</span>
        </div>
      ))}
    </div>
  );
}

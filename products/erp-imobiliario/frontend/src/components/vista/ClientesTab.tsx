/**
 * Vista showcase — Clientes tab. 42.960 clients, read live, nothing stored.
 *
 * Wired 2026-08-22, after Vista granted `/clientes/listar` + `/clientes/detalhes`
 * on 2026-08-21 (KB § CONTEXT/INTEGRATIONS/vista.md § 4.2).
 *
 * THE SHAPE OF THIS TAB IS THE LGPD MITIGATION
 * --------------------------------------------
 * The tenant exposes eleven fields. The list renders seven; the four
 * demographic ones — data de nascimento, sexo, estado civil, profissão — are
 * only ever fetched for ONE named client, when an admin opens them, and each
 * opening writes its own `projection: "detail"` audit row. The backend
 * enforces the split (two endpoints, two DTOs, two field constants); this
 * component is the half the user actually sees, so it says so out loud
 * instead of quietly rendering whatever arrives.
 *
 * A page of 50 names is a different act from opening one person's profile.
 * The UI should make that feel like a different act too — hence the banner,
 * and hence the dialog being the only place demographics appear.
 */
import { useState } from 'react';
import { AlertTriangle, Info, RefreshCcw, ShieldCheck, User } from 'lucide-react';
import { Badge } from '@noctusai/seed/components/ui/badge';
import { Button } from '@noctusai/seed/components/ui/button';
import { Card, CardContent } from '@noctusai/seed/components/ui/card';
import { Skeleton } from '@noctusai/seed/components/ui/skeleton';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@noctusai/seed/components/ui/dialog';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  useVistaClienteDetalhes,
  useVistaClientes,
  type VistaClientesFilters,
  type VistaShowcaseCliente,
} from '@/hooks/useVistaShowcase';
import { EmptyPanel, ErrorPanel, FilterInput, PaginationBar } from './shared';

const PAGE_SIZE = 50;

export function ClientesTab() {
  const [page, setPage] = useState(1);
  const [filters, setFilters] = useState<VistaClientesFilters>({});
  const [draft, setDraft] = useState<VistaClientesFilters>({});
  const [openDetail, setOpenDetail] = useState<string | null>(null);

  const { data, isPending, isFetching, isError, error, refetch } =
    useVistaClientes(true, page, PAGE_SIZE, filters);

  const applyFilters = () => {
    setFilters(draft);
    setPage(1);
  };
  const resetFilters = () => {
    setDraft({});
    setFilters({});
    setPage(1);
  };

  // 🔴 `isPending || isFetching`, never `isLoading`. In TanStack v5
  // `isLoading` is false during a background refetch, so an empty-state branch
  // guarded by it renders "nenhum cliente" over data that exists
  // (KB § PATTERNS/frontend/lying-loading-state.md).
  const busy = isPending || isFetching;

  return (
    <div className="space-y-4">
      <MinimisationNotice />

      <Card>
        <CardContent className="p-4 grid grid-cols-1 md:grid-cols-4 gap-3 items-end">
          <FilterInput
            label="Nome"
            value={draft.nome}
            onChange={v => setDraft(f => ({ ...f, nome: v }))}
            onEnter={applyFilters}
          />
          <FilterInput
            label="Status"
            value={draft.status}
            onChange={v => setDraft(f => ({ ...f, status: v }))}
            onEnter={applyFilters}
          />
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

      {busy && !isError && <Skeleton className="h-96 w-full" />}

      {!busy && !isError && data && (
        <>
          <PaginationBar
            page={page}
            pageSize={data.pagination?.quantidade ?? 0}
            total={data.pagination?.total ?? null}
            paginas={data.pagination?.paginas ?? null}
            fetchedAt={data.fetched_at}
            noun="clientes"
            onPrev={() => setPage(p => Math.max(1, p - 1))}
            onNext={() => setPage(p => p + 1)}
            disabled={isFetching}
          />
          {data.items.length === 0 ? (
            <EmptyPanel message="Nenhum cliente para os filtros informados." />
          ) : (
            <ClientesTable items={data.items} onOpen={setOpenDetail} />
          )}
        </>
      )}

      <ClienteDetalhesDialog
        codigo={openDetail}
        onOpenChange={(open) => !open && setOpenDetail(null)}
      />
    </div>
  );
}

function MinimisationNotice() {
  return (
    <Card className="border-sky-200 bg-sky-50">
      <CardContent className="p-3 flex items-start gap-2 text-xs text-sky-900">
        <ShieldCheck className="h-4 w-4 mt-0.5 shrink-0" />
        <p>
          Esta lista traz apenas <strong>nome, celular, status, cadastro, corretor
          e interesse</strong>. Data de nascimento, sexo, estado civil e profissão
          não são consultadas aqui — só ao abrir um cliente específico, e cada
          abertura fica registrada na auditoria. Nada é gravado no ERP.
        </p>
      </CardContent>
    </Card>
  );
}

function ClientesTable({
  items, onOpen,
}: { items: VistaShowcaseCliente[]; onOpen: (codigo: string) => void }) {
  return (
    <Card>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Nome</TableHead>
              <TableHead>Celular</TableHead>
              <TableHead>Interesse</TableHead>
              <TableHead>Corretor</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Cadastro</TableHead>
              <TableHead className="text-right">Código</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.map(c => (
              <TableRow
                key={c.codigo}
                className="cursor-pointer hover:bg-slate-50"
                onClick={() => onOpen(c.codigo)}
              >
                <TableCell className="font-medium">{c.nome ?? '—'}</TableCell>
                <TableCell>{c.celular ?? '—'}</TableCell>
                <TableCell>{c.interesse ?? '—'}</TableCell>
                <TableCell>{c.corretor_nome ?? '—'}</TableCell>
                <TableCell>
                  {c.status ? <Badge variant="secondary" className="text-xs">{c.status}</Badge> : '—'}
                </TableCell>
                <TableCell className="text-xs text-slate-500">{c.data_cadastro ?? '—'}</TableCell>
                <TableCell className="text-right text-xs text-slate-400">{c.codigo}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

function ClienteDetalhesDialog({
  codigo, onOpenChange,
}: { codigo: string | null; onOpenChange: (open: boolean) => void }) {
  const { data, isPending, isFetching, isError, error } = useVistaClienteDetalhes(codigo);
  const open = !!codigo;
  const busy = open && (isPending || isFetching);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <User className="h-4 w-4 text-slate-400" />
            {data?.base.nome ?? codigo}
            {data?.base.status && <Badge variant="secondary">{data.base.status}</Badge>}
          </DialogTitle>
        </DialogHeader>

        {busy && <Skeleton className="h-56 w-full" />}
        {isError && <ErrorPanel error={error as Error} />}

        {!busy && data && (
          <div className="space-y-4 text-sm">
            <FieldGrid
              title="Contato e relacionamento"
              rows={[
                ['Código', data.codigo],
                ['Celular', data.base.celular ?? '—'],
                ['Interesse', data.base.interesse ?? '—'],
                ['Corretor', data.base.corretor_nome ?? '—'],
                ['Cadastrado em', data.base.data_cadastro ?? '—'],
              ]}
            />
            <div>
              <div className="flex items-center gap-2 text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded px-3 py-2 mb-2">
                <Info className="h-3.5 w-3.5 shrink-0" />
                <span>
                  Dados demográficos — consultados sob demanda para este cliente
                  e registrados na auditoria. Não aparecem na listagem.
                </span>
              </div>
              <FieldGrid
                title="Dados demográficos"
                rows={[
                  ['Data de nascimento', data.data_nascimento ?? '—'],
                  ['Sexo', data.sexo ?? '—'],
                  ['Estado civil', data.estado_civil ?? '—'],
                  ['Profissão', data.profissao ?? '—'],
                ]}
              />
            </div>
            {/* No "mostrar payload bruto" button, unlike the imóvel dialog:
                the backend sends no raw payload for this family, and an
                unstructured dump of personal data is exactly what the
                minimisation posture exists to avoid. */}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

function FieldGrid({
  title, rows,
}: { title: string; rows: Array<[string, React.ReactNode]> }) {
  return (
    <div>
      <div className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-1">{title}</div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-1 text-xs">
        {rows.map(([label, value]) => (
          <div key={label} className="flex justify-between gap-2 border-b border-slate-100 py-1">
            <span className="text-slate-500">{label}</span>
            <span className="font-medium text-right">{value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

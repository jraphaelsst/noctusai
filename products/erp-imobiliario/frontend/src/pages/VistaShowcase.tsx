/**
 * Vista CRM Showcase — admin-only read-only window onto the user's
 * existing Loft/Vista CRM. Phase 1 of `vista-crm-wiring`.
 *
 * The page surfaces seven sub-tabs:
 *   - Imóveis     (live ✅) — property catalog + detail drill-down
 *   - Usuários    (live ✅) — internal Vista team
 *   - Agência     (live ✅) — agency metadata
 *   - Clientes    (🔒)     — endpoint exists, key lacks permission
 *   - Corretores  (🔒)     — same
 *   - Fotos       (❌)     — endpoint not on this tenant tier (live=404)
 *   - Diagnóstico (live ✅) — tenant probe + raw payload inspect
 *
 * Vista API key never reaches the browser — all calls go through
 * /api/vista-showcase/*. The `useIsAdmin()` guard below is UX-only —
 * the security boundary is the backend `require_admin` dependency in
 * `app/routers/vista_showcase.py`. Don't lean on this for security.
 *
 * Layout note: ~620 lines, 7 inline tab components. Next time someone
 * meaningfully edits this page, split each tab into
 * `components/vista/<TabName>Tab.tsx` to keep concerns local.
 *
 * See products/erp-imobiliario/projects/vista-crm-wiring/PROJECT.md
 *     products/erp-imobiliario/projects/vista-crm-wiring/VISTA-API.md
 */
import { useState } from 'react';
import {
  AlertTriangle,
  ExternalLink,
  Info,
  Lock,
  PlugZap,
  RefreshCcw,
  ShieldAlert,
} from 'lucide-react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@noctusai/seed/components/ui/tabs';
import { Card, CardContent, CardHeader, CardTitle } from '@noctusai/seed/components/ui/card';
import { Badge } from '@noctusai/seed/components/ui/badge';
import { Button } from '@noctusai/seed/components/ui/button';
import { Input } from '@noctusai/seed/components/ui/input';
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
import { useIsAdmin } from '@/hooks/useUserRole';
import {
  useVistaAgencias,
  useVistaDiagnostico,
  useVistaImoveis,
  useVistaImovelDetalhes,
  useVistaTabs,
  useVistaUsuarios,
  type VistaImoveisFilters,
  type VistaShowcaseImovel,
  type VistaTabStatus,
} from '@/hooks/useVistaShowcase';

// ── Helpers ──────────────────────────────────────────────────

const formatBRL = (value: number | null | undefined) =>
  value == null
    ? '—'
    : value.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 });

const formatArea = (value: number | null | undefined) =>
  value == null ? '—' : `${value.toLocaleString('pt-BR', { maximumFractionDigits: 0 })} m²`;

const STATUS_PILL: Record<string, { label: string; tone: string }> = {
  live: { label: 'Conectado', tone: 'bg-emerald-100 text-emerald-800' },
  permission_denied: { label: '401 — Permissão pendente', tone: 'bg-amber-100 text-amber-800' },
  // Vista ALLOWS this one — the block is on our side (LGPD intake + wiring).
  // Distinct from permission_denied so the UI stops sending users to chase a
  // vendor grant that already landed (2026-08-21). See vista.md § 4.2.
  pending_intake: { label: 'Liberado — pendente LGPD', tone: 'bg-sky-100 text-sky-800' },
  not_found: { label: '404 — Indisponível', tone: 'bg-slate-200 text-slate-700' },
  not_configured: { label: 'Sem credenciais', tone: 'bg-rose-100 text-rose-800' },
  doc_only: { label: 'Apenas documentação', tone: 'bg-slate-100 text-slate-600' },
};

function StatusPill({ status }: { status: string }) {
  const meta = STATUS_PILL[status] ?? { label: status, tone: 'bg-slate-100 text-slate-700' };
  return (
    <span className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium ${meta.tone}`}>
      {meta.label}
    </span>
  );
}

// ── Top-level page ───────────────────────────────────────────

export default function VistaShowcase() {
  const { isAdmin, isLoading: isLoadingRole } = useIsAdmin();
  const [activeTab, setActiveTab] = useState('imoveis');

  if (isLoadingRole) {
    return (
      <div className="p-8 space-y-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-4 w-96" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (!isAdmin) {
    return (
      <div className="p-8">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-rose-700">
              <ShieldAlert className="h-5 w-5" />
              Acesso restrito
            </CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-slate-600">
            A vitrine Vista CRM é visível apenas para administradores. Esse painel
            contém dados pessoais sob LGPD e está limitado por design enquanto a
            integração estiver em fase de avaliação.
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6 max-w-screen-2xl mx-auto">
      <PageHeader />
      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
        <SubTabsBar />
        <TabsContent value="imoveis"><ImoveisTab /></TabsContent>
        <TabsContent value="usuarios"><UsuariosTab /></TabsContent>
        <TabsContent value="agencias"><AgenciaTab /></TabsContent>
        <TabsContent value="clientes"><PermissionPlaceholderTab tab="clientes" /></TabsContent>
        <TabsContent value="corretores"><PermissionPlaceholderTab tab="corretores" /></TabsContent>
        <TabsContent value="fotos"><PermissionPlaceholderTab tab="fotos" /></TabsContent>
        <TabsContent value="diagnostico"><DiagnosticoTab /></TabsContent>
      </Tabs>
    </div>
  );
}

function PageHeader() {
  return (
    <div className="flex items-start justify-between gap-4 flex-wrap">
      <div>
        <h1 className="text-2xl font-semibold flex items-center gap-2">
          <PlugZap className="h-6 w-6 text-indigo-600" />
          Vista CRM — Vitrine
        </h1>
        <p className="text-sm text-slate-600 mt-1 max-w-3xl">
          Janela somente-leitura sobre o CRM externo da agência. Os dados
          permanecem sob a autoridade da Vista; nada é gravado em ERP nesta
          fase. Acesso restrito a administradores; cada chamada à Vista é
          registrada em <code className="text-xs bg-slate-100 px-1 rounded">erp.user_actions_log</code>.
        </p>
      </div>
      <div className="flex items-center gap-2 text-xs text-slate-500">
        <Info className="h-4 w-4" />
        <span>LGPD — leitura ao vivo, sem cache de dados pessoais.</span>
      </div>
    </div>
  );
}

function SubTabsBar() {
  const { data: tabs, isLoading } = useVistaTabs(true);
  if (isLoading || !tabs) {
    return (
      <div className="flex gap-2">
        {Array.from({ length: 7 }).map((_, i) => <Skeleton key={i} className="h-9 w-24" />)}
      </div>
    );
  }
  const tabByKey: Record<string, VistaTabStatus> = Object.fromEntries(tabs.map(t => [t.tab, t]));
  const renderTrigger = (key: string, label: string) => {
    const t = tabByKey[key];
    const isLocked =
      t?.status === 'permission_denied' ||
      t?.status === 'pending_intake' ||
      t?.status === 'not_found' ||
      t?.status === 'not_configured';
    return (
      <TabsTrigger key={key} value={key} className="gap-2">
        {isLocked && <Lock className="h-3.5 w-3.5" />}
        {label}
      </TabsTrigger>
    );
  };
  return (
    <TabsList className="flex-wrap h-auto justify-start">
      {renderTrigger('imoveis', 'Imóveis')}
      {renderTrigger('usuarios', 'Usuários')}
      {renderTrigger('agencias', 'Agência')}
      {renderTrigger('clientes', 'Clientes')}
      {renderTrigger('corretores', 'Corretores')}
      {renderTrigger('fotos', 'Fotos')}
      {renderTrigger('diagnostico', 'Diagnóstico')}
    </TabsList>
  );
}

// ── Tab: Imóveis ─────────────────────────────────────────────

function ImoveisTab() {
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

function FilterInput({
  label, value, onChange,
}: { label: string; value?: string; onChange: (v: string) => void }) {
  return (
    <div className="space-y-1">
      <label className="text-xs font-medium text-slate-600">{label}</label>
      <Input value={value ?? ''} onChange={e => onChange(e.target.value)} placeholder={`Filtrar por ${label.toLowerCase()}`} />
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

function PaginationBar({
  page, pageSize, total, paginas, fetchedAt, onPrev, onNext, disabled,
}: {
  page: number; pageSize: number; total: number | null; paginas: number | null;
  fetchedAt: string; onPrev: () => void; onNext: () => void; disabled: boolean;
}) {
  const lastPage = paginas ?? Infinity;
  return (
    <div className="flex items-center justify-between gap-3 text-xs text-slate-600 px-1">
      <div>
        Página <strong>{page}</strong>{paginas ? ` / ${paginas}` : ''} ·
        {' '}
        {pageSize} de {total ?? '?'} imóveis ·
        <span className="text-slate-400 ml-1">atualizado {new Date(fetchedAt).toLocaleTimeString('pt-BR')}</span>
      </div>
      <div className="flex gap-2">
        <Button variant="outline" size="sm" onClick={onPrev} disabled={disabled || page <= 1}>‹ Anterior</Button>
        <Button variant="outline" size="sm" onClick={onNext} disabled={disabled || page >= lastPage}>Próxima ›</Button>
      </div>
    </div>
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

// ── Tab: Usuários ────────────────────────────────────────────

function UsuariosTab() {
  const { data: usuarios, isLoading, isError, error } = useVistaUsuarios(true);
  if (isLoading) return <Skeleton className="h-64 w-full" />;
  if (isError) return <ErrorPanel error={error as Error} />;
  if (!usuarios || usuarios.length === 0) {
    return <EmptyPanel message="Nenhum usuário interno retornado pela Vista." />;
  }
  return (
    <Card>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Foto</TableHead>
              <TableHead>Nome</TableHead>
              <TableHead>Email</TableHead>
              <TableHead>Setor</TableHead>
              <TableHead>Código</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {usuarios.map(u => (
              <TableRow key={u.codigo}>
                <TableCell>
                  {u.foto_url
                    ? <img src={u.foto_url} alt={u.nome ?? u.codigo} className="h-8 w-8 rounded-full object-cover" loading="lazy" />
                    : <div className="h-8 w-8 rounded-full bg-slate-200" />}
                </TableCell>
                <TableCell className="font-medium">{u.nome ?? '—'}</TableCell>
                <TableCell>{u.email ?? '—'}</TableCell>
                <TableCell>{u.setor ?? '—'}</TableCell>
                <TableCell className="text-xs text-slate-500">{u.codigo}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

// ── Tab: Agência ─────────────────────────────────────────────

function AgenciaTab() {
  const { data: agencias, isLoading, isError, error } = useVistaAgencias(true);
  if (isLoading) return <Skeleton className="h-32 w-full" />;
  if (isError) return <ErrorPanel error={error as Error} />;
  if (!agencias || agencias.length === 0) {
    return <EmptyPanel message="Nenhuma agência retornada." />;
  }
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {agencias.map(a => (
        <Card key={a.codigo}>
          <CardHeader>
            <CardTitle className="text-base">{a.nome ?? a.codigo}</CardTitle>
          </CardHeader>
          <CardContent className="text-sm space-y-2">
            <div><span className="text-slate-500">Endereço:</span> {a.endereco ?? '—'}</div>
            <div><span className="text-slate-500">Bairro:</span> {a.bairro ?? '—'}</div>
            <div><span className="text-slate-500">Cidade:</span> {a.cidade ?? '—'}</div>
            <div className="flex items-center gap-1">
              <span className="text-slate-500">Site:</span>
              {a.site
                ? <a href={a.site.startsWith('http') ? a.site : `https://${a.site}`} target="_blank" rel="noreferrer" className="text-indigo-600 hover:underline flex items-center gap-1">{a.site} <ExternalLink className="h-3 w-3" /></a>
                : '—'}
            </div>
            <div className="text-[11px] text-slate-400 pt-2">Código Vista: {a.codigo}</div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

// ── Tab: Permission placeholder (clientes / corretores / fotos) ─

function PermissionPlaceholderTab({ tab }: { tab: 'clientes' | 'corretores' | 'fotos' }) {
  const messages: Record<string, { title: string; body: string; closing: string; status: string }> = {
    clientes: {
      title: 'Clientes — liberado pela Vista, pendente do nosso lado',
      body: 'A Vista concedeu a permissão em 21/08/2026: /clientes/listar e /clientes/detalhes retornam 200 (42.960 clientes). O que falta agora é nosso: o enquadramento LGPD das categorias efetivamente retornadas por este tenant — Celular, DataNascimento, Sexo, EstadoCivil e Profissao (não há CPF, endereço nem e-mail) — e a wiring deste tab ao endpoint.',
      closing: 'Não abra chamado na Vista por este tab: a pendência não é mais deles.',
      status: 'pending_intake',
    },
    corretores: {
      title: 'Corretores — permissão pendente',
      body: 'O endpoint /corretores/listar existe mas retorna 401 nesta chave. Foi solicitado no mesmo chamado que Clientes (liberado em 21/08/2026) e não foi liberado junto — ou seja, é decisão por método, não propagação pendente.',
      closing: 'Enquanto isso, o roster de corretores já está disponível via /usuarios/listar (Setor: Corretores), no tab Usuários.',
      status: 'permission_denied',
    },
    fotos: {
      title: 'Fotos — não disponível neste tenant',
      body: 'O endpoint /imoveis/fotos retorna 404 — não está habilitado para esta assinatura Vista. Como mitigação, as fotos primárias dos imóveis já vêm em /imoveis/listar e aparecem no tab Imóveis.',
      closing: 'Se uma assinatura mais ampla for adquirida, este tab passa a operar sem alterações de código.',
      status: 'not_found',
    },
  };
  const m = messages[tab];
  return (
    <Card className="border-amber-200 bg-amber-50">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-amber-800">
          <Lock className="h-5 w-5" />
          {m.title}
          <StatusPill status={m.status} />
        </CardTitle>
      </CardHeader>
      <CardContent className="text-sm text-amber-900 space-y-2">
        <p>{m.body}</p>
        <p className="text-xs text-amber-800/70">{m.closing}</p>
      </CardContent>
    </Card>
  );
}

// ── Tab: Diagnóstico ─────────────────────────────────────────

function DiagnosticoTab() {
  const { data, isLoading, isError, error, refetch, isFetching } = useVistaDiagnostico(true);
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center justify-between">
            <span>Tenant Vista</span>
            <Button onClick={() => refetch()} variant="outline" size="sm" disabled={isFetching}>
              <RefreshCcw className="h-3.5 w-3.5 mr-1" /> Re-probar
            </Button>
          </CardTitle>
        </CardHeader>
        <CardContent className="text-sm space-y-2">
          {isLoading && <Skeleton className="h-12 w-full" />}
          {isError && <ErrorPanel error={error as Error} />}
          {data && (
            <>
              <div>
                <span className="text-slate-500">Base URL:</span>{' '}
                <code className="bg-slate-100 px-2 py-0.5 rounded text-xs">{data.tenant_base_url || '(não configurada)'}</code>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-slate-500">Status:</span>
                {data.configured
                  ? <StatusPill status="live" />
                  : <StatusPill status="not_configured" />}
              </div>
            </>
          )}
        </CardContent>
      </Card>

      {data && data.probes.length > 0 && (
        <Card>
          <CardHeader><CardTitle className="text-base">Probes por endpoint</CardTitle></CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Endpoint</TableHead>
                  <TableHead>HTTP</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Latência</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.probes.map(p => (
                  <TableRow key={p.endpoint}>
                    <TableCell><code className="text-xs">{p.endpoint}</code></TableCell>
                    <TableCell>{p.http_status ?? '—'}</TableCell>
                    <TableCell><StatusPill status={probeStatusToPill(p.status)} /></TableCell>
                    <TableCell>{p.latency_ms != null ? `${p.latency_ms} ms` : '—'}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function probeStatusToPill(status: string): string {
  if (status === 'ok') return 'live';
  if (status === 'permission_denied') return 'permission_denied';
  if (status === 'not_found') return 'not_found';
  if (status === 'not_configured') return 'not_configured';
  return 'doc_only';
}

// ── Shared sub-components ────────────────────────────────────

function ErrorPanel({ error }: { error: Error }) {
  return (
    <Card className="border-rose-200 bg-rose-50">
      <CardContent className="p-4 text-sm text-rose-800 flex items-center gap-2">
        <AlertTriangle className="h-5 w-5" />
        <span>{error?.message || 'Erro desconhecido.'}</span>
      </CardContent>
    </Card>
  );
}

function EmptyPanel({ message }: { message: string }) {
  return (
    <Card>
      <CardContent className="p-8 text-center text-sm text-slate-500">{message}</CardContent>
    </Card>
  );
}

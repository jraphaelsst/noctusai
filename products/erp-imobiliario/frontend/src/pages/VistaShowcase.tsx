/**
 * Vista CRM Showcase — admin-only read-only window onto the user's
 * existing Loft/Vista CRM.
 *
 * The page surfaces seven sub-tabs:
 *   - Imóveis     (live ✅) — property catalog + detail drill-down
 *   - Usuários    (live ✅) — internal Vista team
 *   - Agência     (live ✅) — agency metadata
 *   - Clientes    (live ✅) — 42.960 clients; minimised list + audited detail
 *   - Corretores  (🔒)     — endpoint exists, key lacks permission (401)
 *   - Fotos       (405)    — exists but write-only on this subscription
 *   - Diagnóstico (live ✅) — tenant probe + raw payload inspect
 *
 * Vista API key never reaches the browser — all calls go through
 * /api/vista-showcase/*. The `useIsAdmin()` guard below is UX-only —
 * the security boundary is the backend `require_admin` dependency in
 * `app/routers/vista_showcase.py`. Don't lean on this for security.
 *
 * 2026-08-22 — this file used to be ~670 lines with all seven tabs inline and
 * carried a note asking the next meaningful editor to split them. Wiring the
 * Clientes tab was that edit, so the tabs now live in `components/vista/` and
 * this page is composition only. Keep it that way: a tab's markup belongs in
 * its own module, not here.
 *
 * See products/erp-imobiliario/projects/vista-crm-wiring/PROJECT.md
 *     KB § CONTEXT/INTEGRATIONS/vista.md
 */
import { useState } from 'react';
import { Info, Lock, PlugZap, ShieldAlert } from 'lucide-react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@noctusai/seed/components/ui/tabs';
import { Card, CardContent, CardHeader, CardTitle } from '@noctusai/seed/components/ui/card';
import { Skeleton } from '@noctusai/seed/components/ui/skeleton';
import { useIsAdmin } from '@/hooks/useUserRole';
import { useVistaTabs, type VistaTabStatus } from '@/hooks/useVistaShowcase';
import { AgenciaTab } from '@/components/vista/AgenciaTab';
import { ClientesTab } from '@/components/vista/ClientesTab';
import { DiagnosticoTab } from '@/components/vista/DiagnosticoTab';
import { ImoveisTab } from '@/components/vista/ImoveisTab';
import { PermissionPlaceholderTab } from '@/components/vista/PermissionPlaceholderTab';
import { UsuariosTab } from '@/components/vista/UsuariosTab';

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
        {/* Mounted lazily by Radix: the clientes query only fires once the
            admin actually opens the tab, so simply loading this page never
            reads a single client record. */}
        <TabsContent value="clientes"><ClientesTab /></TabsContent>
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

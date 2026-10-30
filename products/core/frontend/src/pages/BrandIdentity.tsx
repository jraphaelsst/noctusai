/**
 * "Identidade visual" — org owners/admins manage the org's brand identity
 * (CONTRACT org-brand-identity §6): current preview, upload + job progress, draft editor,
 * activation and version history with rollback. The server enforces `settings:manage`.
 */
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { QueryErrorState } from '@noctusai/lib';
import { Skeleton } from '@noctusai/lib/design-system';
import { useIsOrgAdmin } from '@noctusai/lib/design-system';

import {
  addDraftToList, brandKeys, useBrandCurrent, useBrandIdentities, useBrandIdentity, useBrandJob, useBrandOrgId,
} from '../hooks/useBrandIdentity';
import { BrandDraftEditor } from './brand/BrandDraftEditor';
import { BrandHistory } from './brand/BrandHistory';
import { BrandPreview } from './brand/BrandPreview';
import { BrandUpload } from './brand/BrandUpload';

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mb-8 rounded-lg border border-border bg-card p-5">
      <h2 className="mb-3 text-base font-semibold text-foreground">{title}</h2>
      {children}
    </section>
  );
}

export function BrandIdentity() {
  // Gate first: a non-admin must not even fire the admin reads (they would 403).
  if (!useIsOrgAdmin()) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-10">
        <p role="alert" className="text-sm text-muted-foreground">Apenas owners e admins da organização gerenciam a identidade visual.</p>
      </div>
    );
  }
  return <BrandIdentityAdmin />;
}

function BrandIdentityAdmin() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const orgId = useBrandOrgId();
  const current = useBrandCurrent();
  const identities = useBrandIdentities();
  const [jobId, setJobId] = useState<string | null>(null);
  const [pickedId, setPickedId] = useState<string | null>(null);
  const job = useBrandJob(jobId);

  // A finished job hands over to its draft: open it (the list learns of it below, from the draft itself).
  useEffect(() => {
    if (job.data?.status === 'done' && job.data.identity_id) setPickedId(job.data.identity_id);
  }, [job.data?.status, job.data?.identity_id]);

  // Without a pick: the newest draft, else the active one, else nothing.
  const rows = identities.data ?? [];
  const fallback = rows.find((r) => r.status === 'draft') ?? rows.find((r) => r.status === 'active') ?? null;
  const selectedId = pickedId ?? fallback?.id ?? null;
  const identity = useBrandIdentity(selectedId);

  // The new draft joins the version list the moment it is read (no waiting for a list refetch).
  const loaded = identity.data;
  const listed = identities.data;
  useEffect(() => {
    if (!loaded || !listed || listed.some((r) => r.id === loaded.id)) return;
    qc.setQueryData(brandKeys.identities(orgId), addDraftToList(listed, {
      id: loaded.id, version: loaded.version, status: loaded.status, created_at: loaded.created_at, activated_at: loaded.activated_at,
    }));
  }, [loaded, listed, qc, orgId]);

  const showSkeleton = (current.isPending && !current.data) || (identities.isPending && !identities.data);

  return (
    <div className="mx-auto max-w-4xl px-4 py-6 sm:px-6 sm:py-8 lg:px-8 lg:py-10">
      <button onClick={() => navigate('/org-settings')} className="mb-5 text-sm text-primary hover:underline">&larr; Configurações da Organização</button>
      <h1 className="mb-2 text-2xl font-bold text-foreground">Identidade visual</h1>
      <p className="mb-8 text-sm text-muted-foreground">
        Cores, fontes e logos que a organização e todos os seus produtos passam a usar. Sem identidade própria, vale o padrão NoctusAI.
      </p>

      <Section title="Identidade em uso">
        {showSkeleton ? (
          <div data-testid="brand-loading" className="space-y-2"><Skeleton className="h-10 w-full" /><Skeleton className="h-10 w-2/3" /></div>
        ) : (
          <>
            <QueryErrorState query={current} title="Não foi possível carregar a identidade em uso" />
            {current.data && (
              <>
                <p className="mb-3 text-xs text-muted-foreground" data-testid="brand-source">
                  {current.data.source === 'org' ? `Identidade da organização · versão ${current.data.version}` : 'Padrão NoctusAI (a organização ainda não tem identidade própria)'}
                </p>
                <BrandPreview tokens={current.data.tokens} assets={current.data.assets} />
              </>
            )}
          </>
        )}
      </Section>

      <Section title="Enviar material da marca">
        <BrandUpload jobId={jobId} onJobStarted={(id) => { setJobId(id); setPickedId(null); }} />
      </Section>

      <Section title="Rascunho / versão selecionada">
        {identities.isPending && !identities.data ? <Skeleton className="h-24 w-full" /> : null}
        <QueryErrorState query={identities} title="Não foi possível carregar as versões" />
        {selectedId && identity.isPending && !identity.data ? <Skeleton className="h-24 w-full" /> : null}
        <QueryErrorState query={identity} title="Não foi possível carregar esta versão" />
        {identity.data && <BrandDraftEditor key={identity.data.id} identity={identity.data} />}
        {!selectedId && identities.data && <p className="text-sm text-muted-foreground">Nenhum rascunho. Envie o material da marca acima para gerar um.</p>}
      </Section>

      <Section title="Histórico de versões">
        {identities.data && <BrandHistory rows={identities.data} selectedId={selectedId} onOpen={setPickedId} />}
      </Section>
    </div>
  );
}

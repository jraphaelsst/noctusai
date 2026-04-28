/**
 * `<AdminAuditDigest/>` — Core admin page for the audit-digest service.
 *
 * Renders the AI-generated narrative summary of an org's audit log via
 * the seed-lib `<DigestCard/>`. Period selector in the header lets
 * admins switch between common windows.
 *
 * Backend: `GET /api/admin/audit-digest/{org_id}/preview?period_days=N`
 * (gated by `core.audit_digest` consent — admin must have granted).
 */
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '@noctusai/seed/infra';
import { DigestCard, splitProseIntoParagraphs } from '@noctusai/lib/design-system';

import { useAuth } from '@/lib/auth-context';

interface AuditDigestResponse {
  subject: string;
  html: string;
  text: string;
  metrics?: Record<string, unknown>;
}

function useAuditDigestPreview(orgId: string | null | undefined, periodDays: number) {
  return useQuery<AuditDigestResponse, Error>({
    queryKey: ['admin_audit_digest_preview', orgId, periodDays],
    queryFn: async () => {
      const result = await api.get(
        `/api/admin/audit-digest/${encodeURIComponent(orgId!)}/preview?period_days=${periodDays}`,
      );
      return result.data as AuditDigestResponse;
    },
    enabled: Boolean(orgId),
    staleTime: 1000 * 60 * 30,
    retry: false,
  });
}

const PERIOD_OPTIONS: Array<{ days: number; label: string }> = [
  { days: 7, label: 'Última semana' },
  { days: 30, label: 'Últimos 30 dias' },
  { days: 90, label: 'Últimos 90 dias' },
];

export function AdminAuditDigest() {
  const auth = useAuth() as { user?: { org_id?: string; user_metadata?: { org_id?: string } } | null };
  // Core's auth shape varies — accept either flat `org_id` or nested `user_metadata.org_id`.
  const orgId =
    auth?.user?.org_id
    ?? auth?.user?.user_metadata?.org_id
    ?? null;

  const [periodDays, setPeriodDays] = useState(30);
  const { data, isLoading, error } = useAuditDigestPreview(orgId, periodDays);

  const paragraphs = splitProseIntoParagraphs(data?.text);
  const periodToken = `${periodDays}d`;
  const outputRef = `digest:audit:${periodToken}`;

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <header className="space-y-2">
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">
          Digest de auditoria
        </h1>
        <p className="text-sm text-muted-foreground">
          Resumo gerado por IA das ações administrativas + eventos de
          segurança da sua organização. Ajuda revisar tendências sem ler
          o log linha-a-linha.
        </p>
      </header>

      {!orgId ? (
        <p className="text-sm text-muted-foreground">
          Não foi possível resolver o ID da organização. Faça login novamente.
        </p>
      ) : (
        <DigestCard
          title={data?.subject || 'Resumo de auditoria'}
          paragraphs={paragraphs}
          outputRef={outputRef}
          isLoading={isLoading}
          error={error}
          headerActions={
            <select
              value={periodDays}
              onChange={(e) => setPeriodDays(Number(e.target.value))}
              className="rounded-md border border-border bg-background px-2 py-1 text-xs text-foreground"
              aria-label="Selecionar período"
            >
              {PERIOD_OPTIONS.map((opt) => (
                <option key={opt.days} value={opt.days}>
                  {opt.label}
                </option>
              ))}
            </select>
          }
        />
      )}
    </div>
  );
}

export default AdminAuditDigest;

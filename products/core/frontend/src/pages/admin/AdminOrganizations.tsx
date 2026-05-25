/**
 * AdminOrganizations — page-scoped CRUD for tenant organizations.
 *
 * Page-scoped CRUD (KB § PATTERNS/product-internal-wiring.md §7) via the
 * shared `<ResourceManager/>`:
 *   - Read   — list every org (admin sees all; `GET /api/organizations`).
 *   - Update — edit `nome` + `plano` in place (`PATCH /api/organizations/{id}`).
 *   - Create — NOT an admin action: organizations are created through the
 *     signup / onboarding flow (`POST /api/onboarding`), where the first user
 *     of an org provisions it. There is no `POST /api/organizations` by design,
 *     so create is gated off here (`canCreate={false}`) and documented as the
 *     onboarding path rather than fabricated.
 *   - Delete — NOT exposed: deleting a tenant org cascades across users /
 *     subscriptions / licenses and is a destructive, decision-needing op kept
 *     out of the routine admin surface (no `DELETE /api/organizations`).
 */
import { api } from '../../lib/api';
import { ResourceManager } from '@noctusai/lib/components';

interface Organization {
  id: string;
  nome: string;
  slug: string;
  plano: string;
  created_at: string;
}

const PLAN_OPTIONS = [
  { value: 'free', label: 'Free' },
  { value: 'starter', label: 'Starter' },
  { value: 'pro', label: 'Pro' },
  { value: 'enterprise', label: 'Enterprise' },
];

function formatDate(value: string): string {
  if (!value) return '—';
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleDateString('pt-BR');
}

export function AdminOrganizations() {
  return (
    <ResourceManager<Organization>
      title="Organizacoes"
      api={api}
      apiPath="/api/organizations"
      singularName="Organizacao"
      canCreate={false}
      canDelete={false}
      emptyMessage="Nenhuma organizacao encontrada"
      columns={[
        { key: 'nome', header: 'Nome' },
        {
          key: 'slug',
          header: 'Slug',
          render: (org) => (
            <code className="text-sm bg-muted px-1.5 py-0.5 rounded">{org.slug}</code>
          ),
        },
        {
          key: 'plano',
          header: 'Plano',
          render: (org) => (
            <span className="inline-flex items-center rounded-full px-2 py-1 text-xs font-medium bg-primary/10 text-primary">
              {org.plano || 'free'}
            </span>
          ),
        },
        {
          key: 'created_at',
          header: 'Criado em',
          render: (org) => formatDate(org.created_at),
        },
      ]}
      fields={[
        { name: 'nome', label: 'Nome', required: true },
        {
          name: 'plano',
          label: 'Plano',
          type: 'select',
          options: PLAN_OPTIONS,
          help: 'Plano comercial da organizacao.',
        },
      ]}
    />
  );
}

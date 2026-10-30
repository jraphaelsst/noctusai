/** Admin > Templates contract (core `/api/admin/templates`, migration 091). */
export type TemplateKind = 'design_system' | 'agent' | 'message' | 'document' | 'repo_workflow';
export type TemplateFormat = 'json' | 'markdown' | 'text';
export type TemplateStatus = 'draft' | 'active' | 'archived';

/** Filter value meaning "platform-wide" (product IS NULL) — the server's `PLATFORM_SCOPE`. */
export const PLATFORM_SCOPE = '_platform';

export interface TemplateSummary {
  id: string;
  product: string | null;
  kind: TemplateKind;
  key: string;
  title: string;
  description: string;
  format: TemplateFormat;
  version: number;
  status: TemplateStatus;
  created_at: string;
  updated_at: string;
  activated_at: string | null;
  /** Grouping facts the list adds on top of the head row. */
  versions?: number;
  latest_version?: number;
  has_draft?: boolean;
}

export interface Template extends TemplateSummary {
  body: string;
}

export interface TemplatesMeta {
  kinds: { key: TemplateKind; label: string; scopes: { scope: string; label: string; templates: number; sources: number }[] }[];
  formats: TemplateFormat[];
  products: { slug: string; label: string }[];
  platform_scope: string;
}

export interface TemplateSource {
  kind: TemplateKind;
  product: string | null;
  title: string;
  description: string;
  path: string;
}

export interface TemplateFilters { product?: string; kind?: TemplateKind; q?: string }

export const STATUS_LABEL: Record<TemplateStatus, string> = { draft: 'Rascunho', active: 'Ativo', archived: 'Arquivado' };
export const KIND_LABEL: Record<TemplateKind, string> = {
  design_system: 'Design system',
  agent: 'Agentes e prompts',
  message: 'Mensagens',
  document: 'Documentos',
  repo_workflow: 'Repositório e workflow',
};
export const KIND_ORDER = Object.keys(KIND_LABEL) as TemplateKind[];

/** Client-side mirror of the server's format check (the server stays the authority). */
export function bodyError(format: TemplateFormat, body: string): string | null {
  if (format !== 'json') return null;
  try {
    const v = JSON.parse(body);
    return v && typeof v === 'object' && !Array.isArray(v) ? null : 'JSON: a raiz deve ser um objeto.';
  } catch (e) {
    return `JSON inválido: ${e instanceof Error ? e.message : 'erro de sintaxe'}`;
  }
}

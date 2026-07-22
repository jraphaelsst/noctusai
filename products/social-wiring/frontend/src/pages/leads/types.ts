/**
 * Leads module — TypeScript types.
 *
 * §5.3 of `products/social-wiring/projects/leads-module-PROJECT.md` is FROZEN
 * and copied VERBATIM below (Lead / LeadsSummary / TimeseriesPoint /
 * TimeseriesOut / DimensionBucket / ByDimensionOut / HeatmapOut /
 * ImportBatch / ImportPreview). Do not hand-edit those shapes — if the
 * contract changes, the PROJECT doc changes first.
 *
 * Everything below the `─── Non-frozen ───` marker is inferred from §4
 * (the `lead_sources` / `lead_source_aliases` / `lead_corretores` /
 * `lead_corretor_aliases` migration schema, also frozen) since §5.3 does not
 * spell out response shapes for the config-CRUD endpoints. Field names
 * mirror the migration's column names 1:1. If the backend's actual response
 * shape drifts from this inference, that is the reconciliation note in this
 * engineer's return.
 */

// ─── §5.3 (frozen, verbatim) ────────────────────────────────────────────────

export interface Lead {
  id: string; org_id: string;
  data_entrada: string;                // YYYY-MM-DD
  ano: number; mes: number;
  codigo_raw: string | null; codigo_imovel: string | null;
  empreendimento: string | null; regiao: string | null;
  origem_id: string | null; origem_raw: string | null;
  origem: { id: string; slug: string; label: string; cor: string | null } | null;  // joined
  tipo_lead: "novo" | "retorno" | "desconhecido";
  cliente_nome: string | null;
  contato: string | null; contato_tipo: "telefone" | "email" | "desconhecido" | null;
  corretor_id: string | null; corretor_raw: string | null;
  corretor: { id: string; nome: string; cor: string | null } | null;               // joined
  anuncio_tier: "simples" | "destaque" | "super_destaque" | null;
  status: string | null; observacoes: string | null;
  follow_up_data: string | null; follow_up_nota: string | null;
  needs_review: boolean;
  source_sheet: string | null; source_row: number | null;
  created_at: string; updated_at: string | null;
}

export interface LeadsSummary {
  total: number;
  novos: number; retornos: number;
  origens_ativas: number; corretores_ativos: number;
  empreendimentos: number;
  needs_review: number;
  periodo: { de: string | null; ate: string | null };
  // vs. the immediately-preceding window of equal length — null when unresolvable
  comparativo: { total_anterior: number; variacao_pct: number | null } | null;
  media_diaria: number;
  top_origem: { id: string; label: string; total: number; share_pct: number } | null;
  top_corretor: { id: string; nome: string; total: number } | null;
}

export interface TimeseriesPoint {
  bucket: string;          // "2026-07" (mes) | "2026-07-14" (dia) | "2026" (ano)
  label: string;           // "Jul/26" — pt-BR, ready to render on the axis
  total: number;
  series?: Record<string, number>;   // present only when ?split= is passed; key = slug|id
}
export interface TimeseriesOut {
  grain: "dia" | "mes" | "ano";
  split: string | null;
  // series metadata for the chart legend/colors — order IS the render order
  series_meta: { key: string; label: string; cor: string | null }[];
  points: TimeseriesPoint[];
}

export interface DimensionBucket {
  key: string; label: string; cor: string | null;
  total: number; share_pct: number;
  novos: number; retornos: number;
  variacao_pct: number | null;   // vs. the preceding window
}
export interface ByDimensionOut { dim: string; total: number; buckets: DimensionBucket[]; }

export interface HeatmapOut {
  anos: number[];
  // cells[ano][mes-1] — null where the month has no data at all (renders blank, not zero)
  cells: Record<string, (number | null)[]>;
  max: number;
}

export interface ImportBatch {
  id: string; filename: string; sheets: number;
  rows_read: number; rows_inserted: number; rows_updated: number;
  rows_skipped: number; rows_flagged: number;
  status: "running" | "ok" | "erro"; erro: string | null;
  started_at: string; finished_at: string | null;
}
export interface ImportPreview {
  filename: string; sheets: string[];
  rows_read: number; rows_new: number; rows_existing: number;
  rows_skipped: number;
  unmapped_origens: { alias: string; count: number }[];   // drive the "map these first" UI
  unmapped_corretores: { alias: string; count: number }[];
  sample: Lead[];        // first 20 parsed rows, unsaved
  warnings: string[];
}

// ─── Non-frozen (inferred from §4 schema — flag if the live shape differs) ──

export type LeadSourceCategoria =
  | "portal" | "social" | "direto" | "parceria" | "offline" | "outro";

export interface LeadSource {
  id: string; org_id: string;
  slug: string; label: string;
  categoria: LeadSourceCategoria;
  cor: string | null;
  ativo: boolean; ordem: number;
  created_at: string; updated_at: string | null;
}

export type AliasOrigem = "seed" | "import" | "manual";

export interface LeadSourceAlias {
  id: string; org_id: string;
  alias: string; alias_norm: string;
  source_id: string;
  origem: AliasOrigem;
  created_at: string;
}

export interface LeadCorretor {
  id: string; org_id: string;
  nome: string; nome_norm: string;
  cor: string | null;
  ativo: boolean;
  lead_count: number;          // §5.2: "list, each with lead_count"
  created_at: string; updated_at: string | null;
}

export interface LeadCorretorAlias {
  id: string; org_id: string;
  alias: string; alias_norm: string;
  corretor_id: string;
  created_at: string;
}

// ─── Request bodies (page-owned — inferred from §4 editable columns) ───────

export interface LeadCreateInput {
  data_entrada: string;
  codigo_raw?: string | null;
  empreendimento?: string | null;
  regiao?: string | null;
  origem_id?: string | null;
  tipo_lead?: Lead["tipo_lead"];
  cliente_nome?: string | null;
  contato?: string | null;
  corretor_id?: string | null;
  anuncio_tier?: Lead["anuncio_tier"];
  status?: string | null;
  observacoes?: string | null;
  follow_up_data?: string | null;
  follow_up_nota?: string | null;
}

export type LeadUpdateInput = Partial<LeadCreateInput> & { needs_review?: boolean };

export interface LeadSourceInput {
  slug?: string;
  label: string;
  categoria: LeadSourceCategoria;
  cor?: string | null;
  ativo?: boolean;
  ordem?: number;
}

export interface LeadCorretorInput {
  nome: string;
  cor?: string | null;
  ativo?: boolean;
}

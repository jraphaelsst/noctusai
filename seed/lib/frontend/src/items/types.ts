/**
 * Items organ — types. Mirror the backend `noctusai_lib.domain.items` EXACTLY
 * (`types.py`, `sql.py`): enums are const arrays + unions; money is integer CENTS;
 * fiscal fields are digits-only strings. Renaming a member is a wire-contract change.
 *
 * `ItemType` is the vertical-seed seam: the seed ships four values, a vertical may add
 * more (backend `ItemsConfig.extra_item_types`), so the wire type is `string` and
 * `ITEM_TYPES` is the seed's known set (used for labels / the default select options).
 */
export const ITEM_TYPES = ['goods', 'service', 'raw_material', 'asset'] as const;
export type ItemType = string;

export const UNITS = ['UN', 'KG', 'G', 'L', 'ML', 'M', 'M2', 'M3', 'H', 'CX', 'PCT'] as const;
export type Unit = (typeof UNITS)[number];

/** Origem da mercadoria (ICMS): 0..8. */
export const ORIGENS = [0, 1, 2, 3, 4, 5, 6, 7, 8] as const;

export interface Item {
  id: string;
  org_id: string;
  sku: string;
  name: string;
  description: string | null;
  item_type: ItemType;
  unit: Unit;
  category_id: string | null;
  ncm: string | null;
  cest: string | null;
  cfop_default: string | null;
  origem: number | null;
  gtin: string | null;
  cost_cents: number;
  price_cents: number | null;
  weight_g: number | null;
  length_mm: number | null;
  width_mm: number | null;
  height_mm: number | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

/** Create body (`POST /api/items`). Strict on the server: unknown keys are a 422. */
export interface ItemInput {
  sku: string;
  name: string;
  description?: string | null;
  item_type?: ItemType;
  unit?: Unit;
  category_id?: string | null;
  ncm?: string | null;
  cest?: string | null;
  cfop_default?: string | null;
  origem?: number | null;
  gtin?: string | null;
  cost_cents?: number;
  price_cents?: number | null;
  weight_g?: number | null;
  length_mm?: number | null;
  width_mm?: number | null;
  height_mm?: number | null;
  is_active?: boolean;
}

export type ItemPatch = Partial<ItemInput>;

export interface ItemCategory {
  id: string;
  org_id: string;
  parent_id: string | null;
  name: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ItemCategoryInput {
  name: string;
  parent_id?: string | null;
}

export interface ItemsEnvelope<T> {
  data: T;
}

export interface ItemsPagination {
  page: number;
  page_size: number;
  total: number;
  total_pages?: number;
}

export interface ItemsPage<T> {
  data: T[];
  pagination: ItemsPagination;
}

export interface ItemImportResult {
  created: number;
  updated: number;
  dry_run: boolean;
}

/** One row problem in a `422 importacao_invalida` (`error.details.errors`). */
export interface ItemImportRowError {
  line: number;
  field: string;
  code: string;
  message: string;
}

/**
 * Inventory wire types — mirror `noctusai_lib.domain.inventory` (types.py / schemas.py / reports.py).
 * Quantities are JSON numbers with up to 3 decimals (fractional KG); money is integer CENTS.
 */

export const MOVE_KINDS = ['in', 'out', 'adjust', 'transfer_in', 'transfer_out', 'reserve', 'release', 'commit'] as const;
export type MoveKind = (typeof MOVE_KINDS)[number];

export interface InventoryEnvelope<T> {
  data: T;
}
export interface Paginated<T> {
  data: T[];
  pagination: { page: number; page_size: number; total: number; total_pages?: number };
}

export interface WarehouseAddress {
  street?: string | null;
  number?: string | null;
  complement?: string | null;
  district?: string | null;
  city?: string | null;
  state?: string | null;
  zip?: string | null;
}

export interface Warehouse {
  id: string;
  org_id: string;
  name: string;
  code: string;
  is_default: boolean;
  active: boolean;
  address: WarehouseAddress;
  created_at: string;
  updated_at: string;
}
export interface WarehouseInput {
  name: string;
  code: string;
  address?: WarehouseAddress | null;
  is_default?: boolean;
}
export type WarehousePatch = Partial<Omit<WarehouseInput, 'is_default'>> & { active?: boolean; is_default?: boolean };

export interface StockBalance {
  org_id: string;
  item_id: string;
  warehouse_id: string;
  on_hand: number;
  reserved: number;
  /** `on_hand - reserved` (server-computed). */
  available: number;
  avg_cost_cents: number;
  /** `on_hand × avg_cost_cents`, rounded to cents (server-computed). */
  value_cents: number;
  min_qty: number | null;
  low_stock: boolean;
  updated_at: string;
}

export interface StockMove {
  id: string;
  seq: number;
  org_id: string;
  item_id: string;
  warehouse_id: string;
  kind: MoveKind;
  /** Always > 0, except `adjust` where it is the signed delta. */
  qty: number;
  unit_cost_cents: number;
  source: string;
  source_ref: string | null;
  transfer_group: string | null;
  note: string | null;
  on_hand_after: number;
  reserved_after: number;
  avg_cost_after_cents: number;
  occurred_at: string;
  created_by: string | null;
}

export interface Valuation {
  method: 'average_cost';
  total_cents: number;
  items: number;
  by_warehouse: { warehouse_id: string; value_cents: number; items: number; units: number }[];
}

export interface MoveResult {
  status: 'ok' | 'replayed';
  moves: StockMove[];
}

export interface BalanceParams {
  item_id?: string;
  warehouse_id?: string;
  include_zero?: boolean;
  page?: number;
  page_size?: number;
}
export interface KardexParams {
  item_id: string;
  warehouse_id?: string;
  from?: string;
  to?: string;
  page?: number;
  page_size?: number;
}

export interface ReceiveInput {
  item_id: string;
  warehouse_id: string;
  qty: string;
  unit_cost_cents: number;
  source_ref?: string;
  note?: string;
}
export interface IssueInput {
  item_id: string;
  warehouse_id: string;
  qty: string;
  source_ref?: string;
  note?: string;
}
export interface AdjustInput {
  item_id: string;
  warehouse_id: string;
  counted_qty: string;
  unit_cost_cents?: number;
  note?: string;
}
export interface TransferInput {
  item_id: string;
  from_warehouse_id: string;
  to_warehouse_id: string;
  qty: string;
  note?: string;
}
export interface MinQtyInput {
  item_id: string;
  warehouse_id: string;
  min_qty: string;
}

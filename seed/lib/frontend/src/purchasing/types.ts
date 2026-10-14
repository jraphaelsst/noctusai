/**
 * Purchasing wire types — mirror `noctusai_lib.domain.purchasing` (types.py / schemas.py / receipts.py).
 * Quantities are JSON numbers with up to 3 decimals (fractional KG) and are SENT as decimal strings; money is integer CENTS.
 */

export const PURCHASE_ORDER_STATUSES = ['draft', 'approved', 'sent', 'partially_received', 'received', 'cancelled'] as const;
export type PurchaseOrderStatus = (typeof PURCHASE_ORDER_STATUSES)[number];

export interface PurchasingEnvelope<T> {
  data: T;
}
export interface PurchasingPaginated<T> {
  data: T[];
  pagination: { page: number; page_size: number; total: number; total_pages?: number };
}

export interface PurchaseOrderLine {
  id: string;
  org_id: string;
  order_id: string;
  line_no: number;
  item_id: string | null;
  description: string;
  unit: string | null;
  qty: number;
  unit_cost_cents: number;
  line_total_cents: number;
  received_qty: number;
}

export interface PurchaseReceiptLine {
  id: string;
  receipt_id: string;
  order_line_id: string;
  qty: number;
  unit_cost_cents: number;
  goods_cents: number;
  /** This line's prorated share of freight + other − discount (may be negative). */
  adjustment_cents: number;
  /** What the stock move was booked at (cost + prorated adjustment). */
  landed_unit_cost_cents: number;
}

export interface PurchaseReceipt {
  id: string;
  org_id: string;
  order_id: string;
  receipt_no: number;
  received_on: string;
  note: string | null;
  goods_cents: number;
  adjustment_cents: number;
  /** The AP amount: goods + adjustment. */
  total_cents: number;
  stock_posted_at: string | null;
  finance_posted_at: string | null;
  /** Set when a posting leg failed; the receipt itself is committed — repost to finish it. */
  posting_error: string | null;
  posted: boolean;
  created_at: string;
  lines?: PurchaseReceiptLine[];
}

export interface PurchaseOrder {
  id: string;
  org_id: string;
  number: number;
  status: PurchaseOrderStatus;
  party_id: string | null;
  supplier_name: string;
  warehouse_id: string | null;
  expected_date: string | null;
  installments_count: number;
  first_due_days: number;
  interval_days: number;
  freight_cents: number;
  discount_cents: number;
  other_cents: number;
  goods_cents: number;
  total_cents: number;
  notes: string | null;
  approved_by: string | null;
  approved_at: string | null;
  sent_at: string | null;
  cancelled_at: string | null;
  cancel_reason: string | null;
  created_at: string;
  updated_at: string;
  /** Present on the detail read. */
  lines?: PurchaseOrderLine[];
  receipts?: PurchaseReceipt[];
}

export interface PurchaseOrderLineInput {
  item_id?: string | null;
  description: string;
  unit?: string | null;
  /** Decimal string, up to 3 places. */
  qty: string;
  unit_cost_cents: number;
}

/** Body of `POST /orders` and `PUT /orders/{id}` (a full replace, only while the order is a draft). */
export interface PurchaseOrderInput {
  party_id?: string | null;
  supplier_name?: string | null;
  warehouse_id?: string | null;
  expected_date?: string | null;
  installments_count?: number;
  first_due_days?: number;
  interval_days?: number;
  freight_cents?: number;
  discount_cents?: number;
  other_cents?: number;
  notes?: string | null;
  lines: PurchaseOrderLineInput[];
}

export interface PurchaseReceiptInput {
  received_on?: string;
  note?: string;
  /** A retried POST with the same key is a replay, never a second receipt. */
  idempotency_key?: string;
  lines: { order_line_id: string; qty: string }[];
}

/** A receive answer: the receipt, how it posted, and whether the verdict was a replay. */
export interface PurchaseReceiveResult extends PurchaseReceipt {
  replayed: boolean;
  order_status: PurchaseOrderStatus | null;
}

export interface PurchasingSettings {
  approval_threshold_cents: number | null;
  persisted: boolean;
  /** When the threshold last changed; for ~10 min after it, orders above the lowest limit in force cannot be approved. */
  threshold_changed_at?: string | null;
  cooldown_until?: string | null;
  /** The caller is in THIS org's approver list (the only people who may change the threshold / exceed it). */
  is_approver?: boolean;
}

/** One entry of the org's approver list (`pur_approvers`; org-scoped, never a global permission). */
export interface PurchaseApprover {
  org_id: string;
  user_id: string;
  granted_by: string | null;
  granted_at: string;
}

export interface PurchaseOrderListParams {
  status?: PurchaseOrderStatus | '';
  q?: string;
  party_id?: string;
  page?: number;
  page_size?: number;
}
export interface PurchaseReceiptListParams {
  order_id?: string;
  pending?: boolean;
  page?: number;
  page_size?: number;
}

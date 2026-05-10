/**
 * AdConnect domain types — frontend mirror of the API contract sketched in
 * `products/adconnect/projects/adconnect-mvp-implementation/PROJECT.md` §5.2.
 *
 * Phase 7 SKELETON — these types reflect the planned Supabase schema. When
 * Phase 7 PROPER lands, the API client should validate against these shapes
 * and any drift gets reconciled here, not in the calling component.
 */

// ---------------------------------------------------------------------------
// Identity
// ---------------------------------------------------------------------------

export interface Distributor {
  id: string;
  name: string;
  cnpj: string;
  contact?: string;
  email?: string;
  phone?: string;
  city?: string;
  state?: string;
  status: "active" | "inactive" | "suspended";
  created_at?: string;
  updated_at?: string;
}

export interface DistributorMembership {
  id: string;
  user_id: string;
  distributor_id: string;
  role: "distributor_owner" | "distributor_member" | "distributor_viewer";
  created_at?: string;
}

// ---------------------------------------------------------------------------
// Catalog
// ---------------------------------------------------------------------------

export interface Categoria {
  id: string;
  nome: string;
  descricao?: string;
  ordem?: number;
}

export interface Product {
  id: string;
  sku: string;
  name: string;
  description?: string;
  category_id?: string;
  category?: string;
  base_price: number;
  preferential_price?: number; // per-distributor override (precos_distribuidor)
  in_stock: boolean;
  min_order?: number;
  multiple?: number;
  cashback_percent?: number;
  brand?: string;
  image?: string;
}

export interface CatalogFilters {
  search?: string;
  category?: string;
  in_stock_only?: boolean;
  sort_by?: "name" | "price_asc" | "price_desc" | "cashback_desc";
}

// ---------------------------------------------------------------------------
// Cart + Orders
// ---------------------------------------------------------------------------

export interface CartItem {
  id: string;
  cart_id: string;
  product_id: string;
  product?: Product;
  quantity: number;
  price_at_add: number;
}

export interface Cart {
  id: string;
  distributor_id: string;
  status: "ativo" | "abandonado" | "convertido";
  items: CartItem[];
  subtotal: number;
  total: number;
  updated_at?: string;
}

export type OrderStatus =
  | "rascunho"
  | "enviado"
  | "confirmado"
  | "enviado_para_entrega"
  | "entregue"
  | "cancelado";

export interface OrderItem {
  id: string;
  pedido_id: string;
  product_id: string;
  product?: Product;
  quantity: number;
  price_at_order: number;
}

export interface Order {
  id: string;
  distributor_id: string;
  status: OrderStatus;
  items: OrderItem[];
  total: number;
  created_at: string;
  updated_at?: string;
}

// ---------------------------------------------------------------------------
// Sellout
// ---------------------------------------------------------------------------

export type SelloutStatus = "pendente" | "aprovado" | "recusado";
export type SelloutSubmissionMode = "structured" | "nfe_xml" | "freeform";

export interface SelloutLineItem {
  product_sku?: string;
  product_id?: string;
  quantity: number;
  unit_price?: number;
}

export interface SelloutReport {
  id: string;
  distributor_id: string;
  submission_mode: SelloutSubmissionMode;
  period_month: string; // YYYY-MM
  status: SelloutStatus;
  // structured mode
  line_items?: SelloutLineItem[];
  total_units?: number;
  total_value?: number;
  // nfe_xml mode
  nfe_xml_url?: string;
  nfe_number?: string;
  // freeform mode
  attachment_url?: string;
  attachment_filename?: string;
  notes?: string;
  submitted_at: string;
  reviewed_at?: string;
  reviewed_by?: string;
}

// ---------------------------------------------------------------------------
// Rewards
// ---------------------------------------------------------------------------

export type RewardType = "cashback" | "verba_mkt";
export type RewardStatus = "pendente" | "liberado" | "utilizado" | "expirado";

export interface Reward {
  id: string;
  distributor_id: string;
  type: RewardType;
  amount: number;
  status: RewardStatus;
  source_pedido_id?: string;
  source_relatorio_sellout_id?: string;
  description?: string;
  accrued_at: string;
  redeemed_at?: string;
}

export interface RewardRedemption {
  id: string;
  distributor_id: string;
  reward_ids: string[];
  total_amount: number;
  applied_to_pedido_id?: string;
  redeemed_at: string;
}

export interface RewardRule {
  id: string;
  org_id: string;
  nome: string;
  descricao?: string;
  tipo: "cashback_percentual" | "cashback_fixo" | "pontos";
  valor: number;
  aplicavel_categorias?: string[];
  aplicavel_produtos?: string[];
  aplicavel_distribuidores?: string[];
  valor_minimo_pedido?: number;
  quantidade_minima?: number;
  valido_de?: string;
  valido_ate?: string;
  ativa: boolean;
}

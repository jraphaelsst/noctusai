/**
 * Commerce organ — shared types (CONTRACT `projects/commerce-seed-p3/CONTRACT.md`).
 *
 * §1 enums mirror the backend `noctusai_lib.domain.commerce.types` EXACTLY
 * (a parity test pins both sides). Money is ALWAYS integer cents (`*_cents`);
 * timestamps are ISO-8601 UTC strings; ids are UUID strings. API responses are
 * wrapped `{data}` / `{data, pagination}` (see `CommerceEnvelope`/`Paginated`).
 */

// ---------------------------------------------------------------------------
// §1 Enums — const arrays + union types (exact backend string values)
// ---------------------------------------------------------------------------

export const PRODUCT_TYPES = ['digital', 'physical', 'service', 'print_on_demand'] as const;
export type ProductType = (typeof PRODUCT_TYPES)[number];

export const FULFILLMENT_TYPES = ['digital_delivery', 'shipping', 'pickup', 'local_delivery', 'none'] as const;
export type FulfillmentType = (typeof FULFILLMENT_TYPES)[number];

export const PRODUCT_STATUSES = ['draft', 'in_review', 'published', 'unlisted', 'retired'] as const;
export type ProductStatus = (typeof PRODUCT_STATUSES)[number];

export const ORDER_STATUSES = [
  'created',
  'pending_payment',
  'paid',
  'expired',
  'failed',
  'cancelled',
  'refunded',
  'chargeback',
  'partially_refunded',
  'disputed',
] as const;
export type OrderStatus = (typeof ORDER_STATUSES)[number];

export const REFUND_STATUSES = ['requested', 'done', 'failed'] as const;
export type RefundStatus = (typeof REFUND_STATUSES)[number];

export const CHARGE_ATTEMPT_STATUSES = ['pending', 'paid', 'expired', 'cancelled', 'failed'] as const;
export type ChargeAttemptStatus = (typeof CHARGE_ATTEMPT_STATUSES)[number];

export const REMINDER_KINDS = ['before_expiry', 'after_expiry'] as const;
export type ReminderKind = (typeof REMINDER_KINDS)[number];

export const TAX_REGIMES = ['mei', 'simples', 'lucro_presumido', 'lucro_real', 'outro'] as const;
export type TaxRegime = (typeof TAX_REGIMES)[number];

export const TAX_TREATMENTS = ['service_nfse', 'rights_receipt', 'goods_nfe', 'none'] as const;
export type TaxTreatment = (typeof TAX_TREATMENTS)[number];

export const COUPON_KINDS = ['percent', 'fixed'] as const;
export type CouponKind = (typeof COUPON_KINDS)[number];

export const CONSENT_KINDS = ['terms', 'privacy', 'marketing', 'immediate_delivery_waiver'] as const;
export type ConsentKind = (typeof CONSENT_KINDS)[number];

export const PRIVACY_REQUEST_KINDS = ['access', 'correction', 'deletion', 'portability', 'revoke_consent'] as const;
export type PrivacyRequestKind = (typeof PRIVACY_REQUEST_KINDS)[number];

export const FIELD_SOURCES = ['form', 'payment', 'staff'] as const;
export type FieldSource = (typeof FIELD_SOURCES)[number];

export const PAYMENT_METHODS = ['pix', 'boleto', 'credit_card'] as const;
export type PaymentMethod = (typeof PAYMENT_METHODS)[number];

// Closed sets that are not §1 enums but are fixed by §2 column definitions.
export const MEDIA_KINDS = ['image', 'video'] as const;
export type MediaKind = (typeof MEDIA_KINDS)[number];

export const PRIVACY_REQUEST_STATUSES = ['open', 'verified', 'done', 'rejected'] as const;
export type PrivacyRequestStatus = (typeof PRIVACY_REQUEST_STATUSES)[number];

export const ORDER_EVENT_SOURCES = ['checkout', 'webhook', 'staff', 'system'] as const;
export type OrderEventSource = (typeof ORDER_EVENT_SOURCES)[number];

/** Order transitions (§1) — mirrors backend `order_state`; used for UI affordances only (server enforces). */
export const ORDER_TRANSITIONS: Readonly<Record<OrderStatus, readonly OrderStatus[]>> = {
  created: ['pending_payment', 'failed', 'cancelled'],
  pending_payment: ['paid', 'expired', 'failed', 'cancelled'],
  expired: ['paid', 'cancelled', 'pending_payment'],
  failed: ['pending_payment'],
  paid: ['refunded', 'chargeback', 'partially_refunded', 'disputed'],
  cancelled: [],
  refunded: [],
  chargeback: [],
  partially_refunded: ['partially_refunded', 'refunded', 'chargeback', 'disputed'],
  disputed: ['paid', 'partially_refunded', 'chargeback'],
};

// ---------------------------------------------------------------------------
// Envelopes
// ---------------------------------------------------------------------------

export interface CommerceEnvelope<T> {
  data: T;
}

export interface Pagination {
  page: number;
  page_size: number;
  total: number;
  total_pages?: number;
}

export interface Paginated<T> {
  data: T[];
  pagination: Pagination;
}

// ---------------------------------------------------------------------------
// §2 DTOs
// ---------------------------------------------------------------------------

export type BrandTokens = Record<string, string>;

export interface Address {
  street?: string;
  number?: string;
  complement?: string;
  district?: string;
  city?: string;
  state?: string;
  zip?: string;
  country?: string;
}

export interface StoreProfile {
  org_id: string;
  version: number;
  legal_name: string;
  trade_name: string;
  cnpj: string;
  tax_regime: TaxRegime;
  tax_treatment: Partial<Record<ProductType, TaxTreatment>>;
  locale: string;
  currency: string;
  brand_tokens: BrandTokens;
  address: Address;
  contact_email: string;
  contact_phone: string;
  /** Platform-admin only; basis points. Ignored by the server for other callers. */
  platform_fee_bps?: number;
  /** Card installments (D33/D41): the most parcelas offered (1..12; default 12). */
  installments_max?: number;
  /** Parcelas up to this count carry no buyer interest (1..installments_max; default 3). */
  installments_interest_free?: number;
  /** Monthly buyer interest in basis points (0..2000); `null` = follow the platform default (199 = 1,99 % a.m.). */
  installment_interest_monthly_bps?: number | null;
  updated_at?: string;
  updated_by?: string | null;
}

/** PUT /api/commerce/profile body. */
export type StoreProfileInput = Omit<StoreProfile, 'org_id' | 'version' | 'updated_at' | 'updated_by'> & {
  expected_version: number;
};

/** POST /api/commerce/profile/cnpj-lookup → prefill. */
export interface CnpjLookupResult {
  cnpj?: string;
  legal_name?: string;
  trade_name?: string;
  address?: Address;
  contact_email?: string;
  contact_phone?: string;
}

export interface Category {
  id: string;
  slug: string;
  name: string;
  parent_id: string | null;
  position: number;
}

export type CategoryInput = Pick<Category, 'slug' | 'name'> & Partial<Pick<Category, 'parent_id' | 'position'>>;

export interface FeeEstimate {
  pix_cents: number;
  boleto_cents: number;
  card_cents: number;
}

export interface Offer {
  id: string;
  product_id: string;
  name: string;
  price_cents: number;
  currency: string;
  active: boolean;
  position: number;
  /** Asaas list-price estimate per method (labelled as an estimate in the UI). */
  fee_estimate?: FeeEstimate;
}

export type OfferInput = Pick<Offer, 'name' | 'price_cents'> & Partial<Pick<Offer, 'currency' | 'active' | 'position'>>;

export interface Media {
  id: string;
  product_id: string;
  storage_path: string;
  kind: MediaKind;
  alt: string;
  position: number;
  /** Signed URL (private bucket). */
  url?: string;
}

export interface Product {
  id: string;
  slug: string;
  title: string;
  description: string;
  product_type: ProductType;
  fulfillment_type: FulfillmentType;
  status: ProductStatus;
  category_id: string | null;
  attributes: Record<string, unknown>;
  tax_treatment_override: TaxTreatment | null;
  created_at?: string;
  updated_at?: string;
  /** Present on GET by id. */
  offers?: Offer[];
  media?: Media[];
}

export type ProductInput = Pick<Product, 'slug' | 'title' | 'product_type' | 'fulfillment_type'> &
  Partial<Pick<Product, 'description' | 'category_id' | 'attributes' | 'tax_treatment_override'>>;

export interface Coupon {
  id: string;
  code: string;
  kind: CouponKind;
  /** percent 1–100, or cents for `fixed`. */
  value: number;
  starts_at: string | null;
  ends_at: string | null;
  max_uses: number | null;
  uses_count: number;
  active: boolean;
}

export type CouponInput = Pick<Coupon, 'code' | 'kind' | 'value'> &
  Partial<Pick<Coupon, 'starts_at' | 'ends_at' | 'max_uses' | 'active'>>;

export interface FieldSourceInfo {
  source: FieldSource;
  at: string;
  verified: boolean;
}

export interface Customer {
  id: string;
  email: string;
  name: string;
  doc: string;
  phone: string;
  address: Address;
  field_sources: Record<string, FieldSourceInfo>;
  anonymized_at: string | null;
  created_at?: string;
  updated_at?: string;
  /** Present on GET by id. */
  orders?: Order[];
  consents?: Consent[];
}

export interface Consent {
  id?: string;
  customer_id: string;
  order_id: string | null;
  kind: ConsentKind;
  version: string;
  granted: boolean;
  ip?: string | null;
  user_agent?: string | null;
  at: string;
}

export interface PrivacyRequest {
  id: string;
  customer_id: string;
  kind: PrivacyRequestKind;
  status: PrivacyRequestStatus;
  verified_at: string | null;
  created_at: string;
  resolved_at: string | null;
}

export interface PixQr {
  payload?: string;
  encoded_image?: string;
  expires_at?: string;
}

export interface OrderItem {
  id: string;
  order_id: string;
  product_id: string;
  offer_id: string;
  title_snapshot: string;
  product_type: ProductType;
  fulfillment_type: FulfillmentType;
  unit_price_cents: number;
  qty: number;
  total_cents: number;
}

export interface OrderEvent {
  id?: string;
  order_id: string;
  from_status: OrderStatus | null;
  to_status: OrderStatus;
  reason: string | null;
  source: OrderEventSource;
  at: string;
}

export interface Order {
  id: string;
  token: string;
  customer_id: string | null;
  status: OrderStatus;
  subtotal_cents: number;
  discount_cents: number;
  total_cents: number;
  currency: string;
  coupon_id: string | null;
  payment_method: PaymentMethod | null;
  gateway: string | null;
  gateway_charge_id: string | null;
  checkout_url: string | null;
  pix_qr: PixQr | null;
  expires_at: string | null;
  paid_at: string | null;
  platform_fee_cents: number;
  created_at?: string;
  updated_at?: string;
  /** Present on GET by id. */
  items?: OrderItem[];
  events?: OrderEvent[];
  /** Money view (GET by id, CONTRACT P4 §2.5). */
  charges?: OrderCharge[];
  refunds?: OrderRefund[];
  reminders?: OrderReminder[];
}

/** One charge attempt of an order (`commerce_order_charges`); `amount_cents` is what was charged (interest included). */
export interface OrderCharge {
  id: string;
  order_id: string;
  attempt: number;
  gateway: string;
  payment_method: PaymentMethod;
  installment_count: number;
  amount_cents: number;
  status: ChargeAttemptStatus;
  created_at: string;
  closed_at: string | null;
}

/** A refund (`commerce_refunds`). `requested` = asked of the gateway, not confirmed yet ("em andamento"). */
export interface OrderRefund {
  id: string;
  order_id: string;
  charge_id: string;
  amount_cents: number;
  reason: string;
  status: RefundStatus;
  gateway_refund_id: string | null;
  requested_by: string | null;
  created_at: string;
  done_at: string | null;
}

/** A payment-recovery reminder already sent for the order (one per kind). */
export interface OrderReminder {
  order_id: string;
  kind: ReminderKind;
  sent_at: string;
}

/** `POST /orders/{id}/refunds` body; `amount_cents` omitted = everything still refundable. */
export interface RefundInput {
  amount_cents?: number;
  reason: string;
}

/** One card option of a quote (D33): `installment_cents` is the regular parcela, `total_cents` what the buyer pays in all. */
export interface InstallmentOption {
  count: number;
  installment_cents: number;
  total_cents: number;
  interest_free: boolean;
}

/** `POST /storefront/orders/{token}/payment` — regenerate / switch the payment of an order. */
export interface RegeneratePaymentInput {
  payment_method: PaymentMethod;
  installments?: number;
}

export interface RegeneratePaymentResult {
  status: OrderStatus;
  checkout_url?: string | null;
  pix_qr?: PixQr | null;
  expires_at?: string | null;
}

// ---------------------------------------------------------------------------
// §4 Public storefront DTOs
// ---------------------------------------------------------------------------

export interface StorefrontLegal {
  terms_version: string;
  privacy_version: string;
  withdrawal_text: string;
}

export interface Storefront {
  trade_name: string;
  legal_name: string;
  cnpj: string;
  address: Address;
  contact: { email?: string; phone?: string };
  brand_tokens: BrandTokens;
  locale: string;
  currency: string;
  legal: StorefrontLegal;
}

export interface CatalogOffer {
  id: string;
  name: string;
  price_cents: number;
  currency: string;
}

/** `GET /api/storefront/catalog` item: published product + active offers + first media url. */
export interface CatalogItem {
  id: string;
  slug: string;
  title: string;
  description?: string;
  product_type: ProductType;
  fulfillment_type: FulfillmentType;
  category_id?: string | null;
  offers: CatalogOffer[];
  media_url: string | null;
}

/** `GET /api/storefront/products/{slug}` */
export interface StorefrontProduct extends Omit<CatalogItem, 'media_url'> {
  media: Array<Pick<Media, 'id' | 'kind' | 'alt' | 'position'> & { url: string }>;
}

export interface QuoteItemInput {
  offer_id: string;
  qty: number;
}

export interface QuoteRequest {
  items: QuoteItemInput[];
  coupon?: string;
}

export interface QuoteLine {
  offer_id: string;
  product_id?: string;
  title: string;
  product_type?: ProductType;
  fulfillment_type?: FulfillmentType;
  unit_price_cents: number;
  qty: number;
  total_cents: number;
}

export interface Quote {
  lines: QuoteLine[];
  subtotal_cents: number;
  discount_cents: number;
  total_cents: number;
  currency: string;
  coupon_error?: string | null;
  requires_immediate_delivery_waiver: boolean;
  /** Card parcelamento options for this total (D33); absent on a pre-P4 server. */
  installment_options?: InstallmentOption[];
}

export interface CheckoutBuyer {
  name: string;
  email: string;
  doc: string;
  phone: string;
}

export interface CheckoutConsents {
  terms_version: string;
  privacy_version: string;
  marketing: boolean;
  immediate_delivery_waiver: boolean;
}

export interface CheckoutRequest extends QuoteRequest {
  buyer: CheckoutBuyer;
  address?: Address;
  payment_method: PaymentMethod;
  /** Card parcelas (1 for pix/boleto); must be one of the quote's `installment_options`. */
  installments?: number;
  consents: CheckoutConsents;
}

export interface CheckoutResult {
  order_token: string;
  status: OrderStatus;
  checkout_url?: string | null;
  pix_qr?: PixQr | null;
  expires_at?: string | null;
}

/** `GET /api/storefront/orders/{token}` — no internal ids. */
export interface PublicOrderItem {
  title: string;
  qty: number;
  unit_price_cents: number;
  total_cents: number;
  product_type?: ProductType;
}

export interface PublicOrder {
  token: string;
  status: OrderStatus;
  items: PublicOrderItem[];
  subtotal_cents: number;
  discount_cents: number;
  total_cents: number;
  currency: string;
  payment_method: PaymentMethod | null;
  checkout_url: string | null;
  pix_qr: PixQr | null;
  expires_at: string | null;
  paid_at: string | null;
  created_at?: string;
  /** Parcelas of the CURRENT charge attempt, and what that attempt charges (interest included). */
  installment_count?: number;
  charged_cents?: number;
}

export interface AccessLinkRequest {
  email: string;
}

export interface PrivacyRequestInput {
  email: string;
  kind: PrivacyRequestKind;
  details?: string;
}

/** Contract error codes the UI branches on. */
export const COMMERCE_ERROR_CODES = {
  cnpjInvalido: 'cnpj_invalido',
  versaoConflitante: 'versao_conflitante',
  aceiteObrigatorio: 'aceite_obrigatorio',
} as const;

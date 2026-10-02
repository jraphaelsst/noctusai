/**
 * API surface for Store — the typed wire contract of
 * `projects/store-v1-CONTRACT.md` §2–§3 in ONE place, so hooks and pages never
 * carry URL strings or payload shapes.
 *
 * `api` is re-exported from the seed boundary (a test seam: `vi.mock("@/lib/api")`).
 */
import { api } from "@noctusai/seed/infra";
import { env, lerIdentificador } from "@noctusai/lib";
import { createApiKeysHooks } from "@noctusai/lib/components";

export { api };

// ─── Settings (contract §2) ────────────────────────────────────────────────
export interface StoreItem {
  label: string;
  anchor_cents: number;
}

export interface StoreAuthor {
  name: string;
  role: string;
  bio: string;
  has_photo?: boolean;
}

/** The editable settings document (what `PUT /api/admin/settings` carries as `data`). */
export interface StoreSettings {
  product_name: string;
  price_cents: number;
  items: StoreItem[];
  guarantee_days: number;
  author: StoreAuthor;
  checkout_enabled: boolean;
}

/** `GET /api/public/settings` — settings + derived total + photo url. */
export interface PublicSettings extends Omit<StoreSettings, "author"> {
  anchor_total_cents: number;
  author: StoreAuthor & { photo_url: string | null };
}

/** `GET /api/admin/settings` — the current ledger version + its document. */
export interface AdminSettings {
  version: number;
  data: StoreSettings;
}

export const BIO_MAX = 600;
export const MAX_ITEMS = 8;

// ─── Orders / checkout (contract §3) ───────────────────────────────────────
export interface CheckoutInput {
  nome: string;
  email: string;
  cpf: string;
}
export interface CheckoutResult {
  checkout_url: string;
  pedido_token: string;
}

export type PedidoStatus = "pendente" | "pago" | "reembolsado" | "falhou";

export interface PedidoPublico {
  status: PedidoStatus;
  produto: string;
  email_mascarado: string;
  download_url: string | null;
}

export interface PedidoAdmin {
  id: string;
  nome: string;
  email: string;
  valor_cents: number;
  status: PedidoStatus;
  created_at: string;
  pago_em?: string | null;
  email_enviado_em: string | null;
  downloads: number;
}

export interface KitFileStatus {
  exists: boolean;
  size: number | null;
  updated_at: string | null;
}

// ─── Wrappers ──────────────────────────────────────────────────────────────
export const fetchPublicSettings = () => api.get<PublicSettings>("/api/public/settings");
export const postCheckout = (body: CheckoutInput) =>
  api.post<CheckoutResult>("/api/public/checkout", body);
export const fetchPedido = (token: string) =>
  api.get<PedidoPublico>(`/api/public/pedidos/${encodeURIComponent(token)}`);

export const fetchAdminSettings = () => api.get<AdminSettings>("/api/admin/settings");
export const putAdminSettings = (data: StoreSettings, expected_version: number) =>
  api.put<{ version: number }>("/api/admin/settings", { data, expected_version });
export const uploadAutorFoto = (file: File) => {
  const form = new FormData();
  form.append("file", file);
  return api.upload("/api/admin/autor/foto", form);
};
export const fetchKitFile = () => api.get<KitFileStatus>("/api/admin/produto/arquivo");
export const uploadKitFile = (file: File) => {
  const form = new FormData();
  form.append("file", file);
  return api.upload("/api/admin/produto/arquivo", form);
};
export async function fetchPedidosAdmin(): Promise<PedidoAdmin[]> {
  const r = await api.get<PedidoAdmin[] | { items?: PedidoAdmin[]; pedidos?: PedidoAdmin[] }>(
    "/api/admin/pedidos",
  );
  return Array.isArray(r) ? r : (r.items ?? r.pedidos ?? []);
}
export const reenviarPedido = (id: string) =>
  api.post(`/api/admin/pedidos/${encodeURIComponent(id)}/reenviar`);

/** Absolute URL for a backend-relative asset path (`photo_url`). */
export const assetUrl = (path: string | null | undefined): string | null =>
  !path ? null : /^https?:\/\//.test(path) ? path : `${env.BACKEND_API_URL}${path}`;

/**
 * DB-stored credentials (contract §6): the canonical seed hooks over the seed
 * router at `/api/settings/api-keys*`. Built lazily, once.
 */
let apiKeysHooks: ReturnType<typeof createApiKeysHooks> | undefined;
export const getApiKeysHooks = () => (apiKeysHooks ??= createApiKeysHooks(api));

// ─── Formatting / validation ───────────────────────────────────────────────
const brl = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
const brlInt = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 });

/** `4700` → `R$ 47,00` (non-breaking space normalised to a plain one). */
export const formatBRL = (cents: number): string => brl.format(cents / 100).replace(/\s/g, " ");

/** Landing price style: whole reais drop the cents (`R$ 97`), else `R$ 47,50`. */
export const formatBRLShort = (cents: number): string =>
  cents % 100 === 0 ? `R$ ${brlInt.format(cents / 100)}` : formatBRL(cents);

/** Progressive CPF mask: `12345678901` → `123.456.789-01`. */
export function maskCpf(raw: string): string {
  const d = raw.replace(/\D/g, "").slice(0, 11);
  if (d.length <= 3) return d;
  if (d.length <= 6) return `${d.slice(0, 3)}.${d.slice(3)}`;
  if (d.length <= 9) return `${d.slice(0, 3)}.${d.slice(3, 6)}.${d.slice(6)}`;
  return `${d.slice(0, 3)}.${d.slice(3, 6)}.${d.slice(6, 9)}-${d.slice(9)}`;
}

/** CPF check-digit validation through the canonical seed identifier reader. */
export const isValidCpf = (v: string): boolean => lerIdentificador("cpf", v).cabe;

export const isValidEmail = (v: string): boolean => /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(v.trim());

/** BRL input mask: digits-only string → cents. `"4700"` → 4700. */
export const centsFromDigits = (raw: string): number => {
  const d = raw.replace(/\D/g, "").slice(0, 9);
  return d ? parseInt(d, 10) : 0;
};
/** Cents → the masked text shown in the price field (`4700` → `47,00`). */
export const centsToMask = (cents: number): string =>
  (cents / 100).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

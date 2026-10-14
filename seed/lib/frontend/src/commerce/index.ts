/** Commerce organ — public surface (re-exported from the `@noctusai/lib` barrel). */
export * from './types';
export { createCommerceHooks, createFetchTransport, commerceKeys, ORDER_POLL_MS, apiErrorCode, apiErrorStatus } from './hooks';
export type { CommerceApi, CommerceHooks, PageParams, ProductListParams, OrderListParams, CatalogParams } from './hooks';
export { formatCents, parseMoneyToCents, centsToInput, maskCnpj, maskCpf, maskCpfOrCnpj, slugify } from './format';
export { isValidCnpj, isValidCpf, isValidCpfOrCnpj } from './validation';
export { CommerceLocaleProvider, useCommerceT, createTranslator, resolveLocale, COMMERCE_LOCALES, DEFAULT_COMMERCE_LOCALE } from './i18n';
export type { CommerceLocale, Translate } from './i18n';
export { useCart, cartStorageKey, CART_MAX_QTY } from './cartState';
export type { CartApi, CartItem } from './cartState';
export { useQuoteFor } from './useQuoteFor';

// Staff
export { StoreProfileForm, BRAND_TOKEN_KEYS, BRAND_TOKEN_DEFAULTS } from './StoreProfileForm';
export type { StoreProfileFormProps } from './StoreProfileForm';
export { ProductEditor, PRODUCT_TYPE_SLOTS, FULFILLMENT_BY_TYPE } from './ProductEditor';
export type { ProductEditorProps, SlotDef } from './ProductEditor';
export { OffersEditor } from './OffersEditor';
export type { OffersEditorProps } from './OffersEditor';
export { CategoryManager } from './CategoryManager';
export type { CategoryManagerProps } from './CategoryManager';
export { CouponsEditor } from './CouponsEditor';
export type { CouponsEditorProps } from './CouponsEditor';
export { OrdersTable } from './OrdersTable';
export type { OrdersTableProps } from './OrdersTable';
export { OrderDetail } from './OrderDetail';
export type { OrderDetailProps } from './OrderDetail';
export { OrderStatusChip } from './OrderStatusChip';
export { CustomersTable, FieldSourceBadge } from './CustomersTable';
export type { CustomersTableProps } from './CustomersTable';
export { PrivacyActions } from './PrivacyActions';
export type { PrivacyActionsProps } from './PrivacyActions';

// Storefront
export { StorefrontShell, LegalFooter, brandTokensToCssVars, formatAddress, useStorefrontData } from './StorefrontShell';
export type { StorefrontShellProps } from './StorefrontShell';
export { ProductGrid } from './ProductGrid';
export type { ProductGridProps } from './ProductGrid';
export { ProductCard } from './ProductCard';
export type { ProductCardProps } from './ProductCard';
// Named `StorefrontProductPage` because `ProductPage` is a locally-declared page in core's marketing
// site (the canonical-organ keeper keys on organ names). `ProductPage` stays as the contract-§5 alias.
export { StorefrontProductPage, StorefrontProductPage as ProductPage } from './StorefrontProductPage';
export type { StorefrontProductPageProps, StorefrontProductPageProps as ProductPageProps } from './StorefrontProductPage';
export { Cart } from './Cart';
export type { CartProps } from './Cart';
export { CheckoutForm } from './CheckoutForm';
export type { CheckoutFormProps } from './CheckoutForm';
export { OrderStatusPage } from './OrderStatusPage';
export type { OrderStatusPageProps } from './OrderStatusPage';
export { MyOrdersRequest } from './MyOrdersRequest';
export type { MyOrdersRequestProps } from './MyOrdersRequest';

// P4 money + fiscal (projects/commerce-seed-p4/CONTRACT.md §5)
export * from './fiscalTypes';
export { RefundDialog, RefundHistory } from './RefundDialog';
export type { RefundDialogProps } from './RefundDialog';
export { OrderMoneyPanel } from './OrderMoneyPanel';
export type { OrderMoneyPanelProps } from './OrderMoneyPanel';
export {
  InstallmentsSettings,
  profileWithInstallments,
  percentToBps,
  bpsToPercent,
  DEFAULT_INSTALLMENTS_MAX,
  DEFAULT_INSTALLMENTS_INTEREST_FREE,
} from './InstallmentsSettings';
export type { InstallmentsSettingsProps } from './InstallmentsSettings';
export { FiscalSettingsForm } from './FiscalSettingsForm';
export type { FiscalSettingsFormProps } from './FiscalSettingsForm';
export { InstallmentPicker } from './InstallmentPicker';
export type { InstallmentPickerProps } from './InstallmentPicker';
export { paidCents, refundableCents, heldRefundCents, doneRefundCents, hasRefundInProgress, newIdempotencyKey } from './moneyMath';

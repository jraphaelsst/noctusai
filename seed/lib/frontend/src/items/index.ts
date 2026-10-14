/** Items organ — public surface (re-exported from the `@noctusai/lib` barrel). Backend: `noctusai_lib.domain.items`. */
export * from './types';
export {
  createItemsHooks,
  itemsKeys,
  ITEMS_PAGE_SIZE,
  apiFieldError,
  importRowErrors,
} from './hooks';
export type { ItemsApi, ItemsHooks, ItemListParams } from './hooks';
export { itemsT, ITEMS_MESSAGES } from './messages';
export {
  normalizeSku,
  normalizeNcm,
  normalizeCest,
  normalizeCfop,
  normalizeGtin,
  normalizeOrigem,
  gtinCheckDigit,
} from './validation';
export { ItemsTable } from './ItemsTable';
export type { ItemsTableProps } from './ItemsTable';
export { ItemEditor, buildItemInput } from './ItemEditor';
export type { ItemEditorProps } from './ItemEditor';
export { ItemCategoryManager, flattenCategories } from './ItemCategoryManager';
export type { ItemCategoryManagerProps } from './ItemCategoryManager';
export { ItemsImport } from './ItemsImport';
export type { ItemsImportProps } from './ItemsImport';

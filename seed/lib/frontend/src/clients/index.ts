/** Clients organ -- public surface (re-exported from the `@noctusai/lib` barrel). Backend: `noctusai_lib.domain.clients`. */
export * from './types';
export { createClientsHooks, clientsKeys, placeSession, sessionBelongs } from './hooks';
export type { ClientsApi, ClientsHooks, ClientsHooksOptions } from './hooks';
export {
  addDays as clientsAddDays,
  clientsFilterQuery,
  formatWhen as formatSessionWhen,
  paymentStatusOf,
  PAYMENT_STATUS as CLIENT_PAYMENT_STATUS,
  weekStartOf,
  zonedIso,
  zonedParts,
} from './format';
export { clientsErrorText, nounVars as clientsNounVars } from './parts';
export { ClientsList } from './ClientsList';
export type { ClientsListProps } from './ClientsList';
export { ClientDetailPage } from './ClientDetailPage';
export type { ClientDetailPageProps, ClientDetailTab } from './ClientDetailPage';
export { ClientsAgenda } from './ClientsAgenda';
export type { ClientsAgendaProps } from './ClientsAgenda';
export { ClientForm, ClientFormDialog } from './ClientForm';
export type { ClientFormProps, ClientFormDialogProps } from './ClientForm';
export { SessionFormDialog } from './SessionFormDialog';
export type { SessionFormDialogProps } from './SessionFormDialog';

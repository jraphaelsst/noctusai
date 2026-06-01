/**
 * Integration card organ — config-driven provider account cards.
 *
 * Usage:
 *   import {
 *     IntegrationCard, IntegrationCardModal,
 *     PROVIDER_CARD_CONFIG, getProviderConfig,
 *   } from "@noctusai/lib/design-system";
 */
export { IntegrationCard, resolveStatusBadge } from "./IntegrationCard";
export type { IntegrationCardProps } from "./IntegrationCard";

export { IntegrationCardModal } from "./IntegrationCardModal";
export type { IntegrationCardModalProps } from "./IntegrationCardModal";

export { PROVIDER_CARD_CONFIG, getProviderConfig } from "./providerCardConfig";
export type { ProviderCardConfig, EditableField } from "./providerCardConfig";

export type {
  IntegrationAccount,
  IntegrationAccountPatch,
  IntegrationStatus,
  SecondaryField,
  ModalSection,
} from "./types";

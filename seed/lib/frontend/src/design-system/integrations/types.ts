/**
 * Shared types for the IntegrationCard organ.
 *
 * `IntegrationAccount` mirrors the BE contract exactly (field-names, envelope).
 * `IntegrationStatus` drives the status badge variant map.
 */

export type IntegrationStatus =
  | "wiring"
  | "validating"
  | "validated"
  | "error"
  | "disconnected";

export interface IntegrationAccount {
  id: string;
  org_id: string;
  provider: string;
  account_label: string;
  client_id: string | null;
  status: IntegrationStatus;
  /**
   * Provider-specific fields surfaced by the backend.
   * YouTube: { channel_id, title, thumbnail_url, subscriber_count, video_count, view_count }
   * WhatsApp: { session, phone, webhook_url }
   */
  channel_info: Record<string, unknown>;
  metadata: Record<string, unknown>;
  is_default: boolean;
  last_synced_at: string | null;
  created_at: string;
  updated_at: string;
}

/** A secondary field row rendered below the primary label on the card. */
export interface SecondaryField {
  label: string;
  value: string;
}

/** A single detail section rendered inside the modal. */
export interface ModalSection {
  title: string;
  fields: SecondaryField[];
}

/** Payload passed to `onSave` when the user submits the inline-edit form. */
export type IntegrationAccountPatch = Partial<
  Pick<IntegrationAccount, "account_label"> &
    Record<string, string | null>
>;

import type { WebsiteSettings } from '../../../../lib/website';

/** Shared prop surface every settings tab receives. Each tab edits its own
 * slice of the ONE shared draft (`Settings.tsx` owns the single PUT). */
export interface SettingsTabProps {
  draft: WebsiteSettings;
  /** Apply a change to the shared draft. `updater` receives the CURRENT
   * draft so tabs can compose edits without racing each other. */
  onChange: (updater: (prev: WebsiteSettings) => WebsiteSettings) => void;
  /** `role === 'marketing'` — disables `site_enabled`/`signup_enabled`
   * (contract §6, admin-only fields; `403 admin_only_field` server-side). */
  isMarketing: boolean;
}

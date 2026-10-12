/**
 * `<OrgSelectionGate/>` — mounted once by the seed shell layout: the picker
 * modal (every entry into the product / "Trocar org") plus the acting-as banner.
 * Zero per-product code; non-staff render nothing.
 *
 * `<OrgContentGate>` — wraps the product's routes/children in the seed shell. While
 * the entry handshake is pending or the picker is REQUIRED, the children are NOT
 * rendered (no product content, no product queries behind the picker); a neutral
 * placeholder stands in. Non-staff within a visit: children render as always.
 */
import type { ReactNode } from 'react';

import { useOrgSelection } from '../../org-selection';
import { ActingAsBanner } from './ActingAsBanner';
import { OrgPickerModal } from './OrgPickerModal';

/** `onSignOut` = the shell's logout; the required picker shows it as "Sair". */
export function OrgSelectionGate({ onSignOut }: { onSignOut?: () => void | Promise<void> } = {}) {
  return (
    <>
      <ActingAsBanner />
      <OrgPickerModal onSignOut={onSignOut} />
    </>
  );
}

export function OrgContentGate({ children }: { children: ReactNode }) {
  const { contentBlocked } = useOrgSelection();
  if (contentBlocked) {
    return <div data-testid="org-content-blocked" aria-hidden="true" className="min-h-[50vh]" />;
  }
  return <>{children}</>;
}

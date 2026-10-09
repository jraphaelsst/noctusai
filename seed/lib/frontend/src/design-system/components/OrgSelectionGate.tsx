/**
 * `<OrgSelectionGate/>` — mounted once by the seed shell layout: the picker
 * modal (first entry per login / "Trocar org") plus the acting-as banner.
 * Zero per-product code; non-staff render nothing.
 */
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

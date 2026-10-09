/**
 * `<OrgSelectionGate/>` — mounted once by the seed shell layout: the picker
 * modal (first entry per login / "Trocar org") plus the acting-as banner.
 * Zero per-product code; non-staff render nothing.
 */
import { ActingAsBanner } from './ActingAsBanner';
import { OrgPickerModal } from './OrgPickerModal';

export function OrgSelectionGate() {
  return (
    <>
      <ActingAsBanner />
      <OrgPickerModal />
    </>
  );
}

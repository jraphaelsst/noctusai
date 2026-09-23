/**
 * ClienteCardFace — SW's board card face, a thin adapter over the seed
 * `CardHubFace` (`@noctusai/lib/components`, wave-a Slice C/F —
 * `project-history/roadmaps/cardhub-igig-crm-2026-09.wave-a-design.md`).
 *
 * The face itself (strip · title · badge row, badges only when non-zero) is
 * the seed's. What stays SW is the NAME and the testid root: every derived
 * testid (`cliente-card-face-strip`, `-badges`, `-anexos`, …) roots on
 * `testId`, so defaulting it to `cliente-card-face` keeps SW's DOM contract
 * byte-identical for the board and its suites.
 */
import { CardHubFace, resolveDueState } from "@noctusai/lib/components";
import type { CardHubFaceProps } from "@noctusai/lib/components";

export type ClienteCardFaceProps = CardHubFaceProps;

export { resolveDueState };

export function ClienteCardFace({ testId = "cliente-card-face", ...props }: ClienteCardFaceProps) {
  return <CardHubFace {...props} testId={testId} />;
}

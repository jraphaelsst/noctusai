/**
 * `TermsOfUsePage` — public page at `/consent/terms-of-use`.
 * Auto-routed by `createProductApp` for every product (seed-first, no auth).
 */
import { ConsentDocLayout } from "./ConsentDocLayout";
import { TERMS_OF_USE } from "../../content/consent";

export function TermsOfUsePage() {
  return <ConsentDocLayout doc={TERMS_OF_USE} />;
}

export default TermsOfUsePage;

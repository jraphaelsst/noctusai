/**
 * `PrivacyPolicyPage` — public page at `/consent/privacy-policy`.
 * Auto-routed by `createProductApp` for every product (seed-first, no auth).
 */
import { ConsentDocLayout } from "./ConsentDocLayout";
import { PRIVACY_POLICY } from "../../content/consent";

export function PrivacyPolicyPage() {
  return <ConsentDocLayout doc={PRIVACY_POLICY} />;
}

export default PrivacyPolicyPage;

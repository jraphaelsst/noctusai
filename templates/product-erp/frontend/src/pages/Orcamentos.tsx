/**
 * `/orcamentos` -- the quotes organ (versions, send, convert-on-accept seam, PDF). The signed public accept page needs a host link secret and is not mounted by default.
 * `canWrite` is the UX gate only; the server enforces org-admin on every write.
 */
import { QuotesTable } from "@noctusai/lib";
import { useIsOrgAdmin } from "@noctusai/lib/design-system";

import { quotesHooks } from "@/lib/erpHooks";

export default function Orcamentos() {
  const isAdmin = useIsOrgAdmin();
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold text-foreground">Orçamentos</h1>
      <QuotesTable hooks={quotesHooks} canWrite={isAdmin} />
    </div>
  );
}

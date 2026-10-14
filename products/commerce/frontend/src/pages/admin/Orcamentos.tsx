/**
 * `/admin/orcamentos` — quotes (orçamentos / propostas): the list with filters, and — through the table's built-in
 * `QuoteEditor` — the editor (customer + priced lines, totals computed on the server), versions, the `QuoteSendDialog`
 * (e-mail or a copyable signed link) and the PDF. The customer decides on the public page `/orcamento/:token`
 * (`QuoteAccept`, outside the authed shell). An accepted quote converts through the backend handler: goods -> a commerce
 * order (stock held), services -> a draft contract. Writes are for org admins (UX; the server enforces).
 */
import { QuotesTable } from "@noctusai/lib";
import { useIsOrgAdmin } from "@noctusai/lib/design-system";

import { AdminFrame } from "@/components/AdminFrame";
import { useQuoteOptions } from "@/hooks/useErpOptions";
import { staffQuotes } from "@/lib/backoffice";

export default function Orcamentos() {
  const isAdmin = useIsOrgAdmin();
  const { parties, items } = useQuoteOptions();
  return (
    <AdminFrame titleKey="admin.quotes_title" introKey="admin.quotes_intro">
      <QuotesTable hooks={staffQuotes} canWrite={isAdmin} parties={parties} items={items} />
    </AdminFrame>
  );
}

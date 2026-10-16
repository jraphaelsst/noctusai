/**
 * Financeiro -- the seed finance + contracts organs, plus Orbity's gateway-charges view.
 *
 *   /financeiro/*            the seed `FinanceRoutedPage` (visão geral · receber · pagar · fluxo de caixa · DRE · conciliação · cadastros)
 *   /financeiro/contratos    the seed `ContractsTable` (editor, aditivos, reajuste, suspender, encerrar, prévia das próximas cobranças)
 *   /financeiro/cobrancas    `ChargesPanel`: month summary + every receivable with its gateway status banner
 *
 * The URL is the tab state (deep links and the back button work). Writes are offered to org admins only (UX -- the
 * server enforces every write again). Contracts generate the monthly receivable automatically; no gateway configured
 * means the charge stays a plain receivable, and the banner says so.
 */
import { Link, useLocation } from "react-router-dom";
import { ContractsTable, FinanceRoutedPage, createContractsHooks, createFinanceHooks } from "@noctusai/lib";
import { Select, useIsOrgAdmin } from "@noctusai/lib/design-system";
import { ChargesPanel } from "@/components/ChargesPanel";
import { useClientOptions } from "@/hooks/useClients";
import { api } from "@/lib/api";

export const FINANCE_BASE_PATH = "/financeiro";

const finance = createFinanceHooks(api);
const contracts = createContractsHooks(api);

type TabKey = "financeiro" | "contratos" | "cobrancas";

const TABS: { key: TabKey; label: string; to: string }[] = [
  { key: "financeiro", label: "Financeiro", to: FINANCE_BASE_PATH },
  { key: "contratos", label: "Contratos", to: `${FINANCE_BASE_PATH}/contratos` },
  { key: "cobrancas", label: "Cobranças", to: `${FINANCE_BASE_PATH}/cobrancas` },
];

export function tabFromPath(pathname: string): TabKey {
  const segment = pathname.replace(/^\/financeiro\/?/, "").split("/")[0];
  return segment === "contratos" || segment === "cobrancas" ? segment : "financeiro";
}

/** The contract editor's party seam: the contract's customer is one of the org's clients (`party_id` = the client id). */
function ClientPartyPicker({ value, onPick }: { value: string | null; onPick: (party: { id: string; name: string } | null) => void }) {
  const q = useClientOptions();
  const clients = q.data ?? [];
  return (
    <Select
      aria-label="Cliente"
      value={value ?? ""}
      disabled={q.isPending && !q.data}
      onChange={(e) => {
        const found = clients.find((c) => c.id === e.target.value);
        onPick(found ? { id: found.id, name: found.legal_name || found.name } : null);
      }}
    >
      <option value="">{q.isPending && !q.data ? "Carregando…" : "—"}</option>
      {clients.map((c) => (
        <option key={c.id} value={c.id}>{c.legal_name || c.name}</option>
      ))}
    </Select>
  );
}

export default function Financeiro() {
  const isAdmin = useIsOrgAdmin();
  const { pathname } = useLocation();
  const tab = tabFromPath(pathname);

  return (
    <div className="space-y-4 p-4">
      <h1 className="text-2xl font-semibold">Financeiro</h1>
      <nav aria-label="Seções do financeiro" className="flex gap-1 border-b border-border">
        {TABS.map((t) => (
          <Link
            key={t.key}
            to={t.to}
            aria-current={tab === t.key ? "page" : undefined}
            className={`-mb-px border-b-2 px-4 py-2 text-sm ${tab === t.key ? "border-primary font-medium text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"}`}
          >
            {t.label}
          </Link>
        ))}
      </nav>

      {tab === "contratos" ? (
        <ContractsTable hooks={contracts} canWrite={isAdmin} renderPartyPicker={(props) => <ClientPartyPicker {...props} />} />
      ) : tab === "cobrancas" ? (
        <ChargesPanel isAdmin={isAdmin} />
      ) : (
        <FinanceRoutedPage basePath={FINANCE_BASE_PATH} hooks={finance} isAdmin={isAdmin} />
      )}
    </div>
  );
}

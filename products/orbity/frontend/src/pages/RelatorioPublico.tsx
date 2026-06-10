/**
 * RelatorioPublico — public, unauthenticated client-facing report page.
 *
 * Route: /relatorio/:token  (publicRoutes seam — no auth required)
 *
 * Fetches GET /api/reports/public/{token} via usePublicReport (token-gated,
 * no JWT). Renders all four states: loading / expired+not-found / empty
 * (no snapshot yet) / success (snapshot cards).
 *
 * The api client is used as-is — the backend endpoint requires no
 * Authorization header. No useAuthStore reference here.
 */
import { useParams } from "react-router-dom";
import { usePublicReport, type PublicReport } from "@/hooks/useRelatorios";
import { FileBarChart2, AlertCircle, Clock, TrendingUp, DollarSign, TrendingDown } from "lucide-react";

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function PageShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-gray-50 py-10 px-4">
      <div className="mx-auto max-w-3xl space-y-6">{children}</div>
    </div>
  );
}

// NOTE: a report-title banner, NOT the authenticated app-chrome `Header` organ
// (`@noctusai/lib`). This is a public, unauthenticated page (no user/logout/theme
// context), so the canonical Header does not apply — named distinctly to avoid a
// false canonical-organ collision.
function ReportHeader({ name, periodStart, periodEnd }: { name: string; periodStart: string; periodEnd: string }) {
  const fmt = (d: string) =>
    new Date(d + "T00:00:00").toLocaleDateString("pt-BR", {
      day: "2-digit",
      month: "long",
      year: "numeric",
    });

  return (
    <div className="rounded-xl bg-white border border-gray-200 p-6 shadow-sm">
      <div className="flex items-center gap-3 mb-2">
        <div className="rounded-lg bg-indigo-50 p-2">
          <FileBarChart2 className="h-5 w-5 text-indigo-600" />
        </div>
        <span className="text-xs font-semibold uppercase tracking-wider text-indigo-600">
          Relatório de Desempenho
        </span>
      </div>
      <h1 className="text-2xl font-bold text-gray-900 mt-1">{name}</h1>
      <p className="text-sm text-gray-500 mt-1">
        Período: {fmt(periodStart)} — {fmt(periodEnd)}
      </p>
    </div>
  );
}

function StatCard({
  label,
  value,
  icon: Icon,
  color,
}: {
  label: string;
  value: string | number;
  icon: React.ElementType;
  color: string;
}) {
  return (
    <div className="rounded-xl bg-white border border-gray-200 p-5 shadow-sm flex items-start gap-4">
      <div className={`rounded-lg p-2 ${color}`}>
        <Icon className="h-5 w-5" />
      </div>
      <div>
        <p className="text-sm text-gray-500">{label}</p>
        <p className="text-xl font-semibold text-gray-900">{value}</p>
      </div>
    </div>
  );
}

function formatBRL(val: number) {
  return val.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function SnapshotCards({ payload }: { payload: Record<string, unknown> }) {
  const cards: React.ReactNode[] = [];

  if (typeof payload.leads === "number") {
    cards.push(
      <StatCard
        key="leads"
        label="Leads gerados"
        value={payload.leads}
        icon={TrendingUp}
        color="bg-blue-50 text-blue-600"
      />,
    );
  }
  if (typeof payload.revenues === "number") {
    cards.push(
      <StatCard
        key="revenues"
        label="Receitas"
        value={formatBRL(payload.revenues)}
        icon={DollarSign}
        color="bg-green-50 text-green-600"
      />,
    );
  }
  if (typeof payload.expenses === "number") {
    cards.push(
      <StatCard
        key="expenses"
        label="Despesas"
        value={formatBRL(payload.expenses)}
        icon={TrendingDown}
        color="bg-red-50 text-red-600"
      />,
    );
  }

  // Extra keys not covered above
  for (const [key, val] of Object.entries(payload)) {
    if (["leads", "revenues", "expenses"].includes(key)) continue;
    if (val === null || val === undefined) continue;
    const display =
      typeof val === "number"
        ? val.toLocaleString("pt-BR")
        : String(val);
    cards.push(
      <StatCard
        key={key}
        label={key.replace(/_/g, " ")}
        value={display}
        icon={FileBarChart2}
        color="bg-gray-100 text-gray-600"
      />,
    );
  }

  if (cards.length === 0) {
    return (
      <div className="rounded-xl bg-white border border-gray-200 p-6 text-center text-gray-400 text-sm">
        Nenhum dado de desempenho disponível neste snapshot.
      </div>
    );
  }

  return <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">{cards}</div>;
}

function LoadingState() {
  return (
    <PageShell>
      <div className="rounded-xl bg-white border border-gray-200 p-6 shadow-sm animate-pulse space-y-4">
        <div className="h-4 bg-gray-200 rounded w-1/3" />
        <div className="h-8 bg-gray-200 rounded w-2/3" />
        <div className="h-4 bg-gray-200 rounded w-1/2" />
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-24 rounded-xl bg-white border border-gray-200 animate-pulse" />
        ))}
      </div>
    </PageShell>
  );
}

function ErrorState({ message }: { message: string }) {
  const isExpired =
    message.toLowerCase().includes("expir") ||
    message.toLowerCase().includes("não encontrado") ||
    message.toLowerCase().includes("not found");

  return (
    <PageShell>
      <div className="rounded-xl bg-white border border-red-200 p-8 text-center shadow-sm">
        <div className="flex justify-center mb-4">
          {isExpired ? (
            <Clock className="h-10 w-10 text-amber-400" />
          ) : (
            <AlertCircle className="h-10 w-10 text-red-400" />
          )}
        </div>
        <h2 className="text-lg font-semibold text-gray-800 mb-1">
          {isExpired ? "Relatório não disponível" : "Erro ao carregar relatório"}
        </h2>
        <p className="text-sm text-gray-500">
          {isExpired
            ? "Este link pode ter expirado ou o relatório não foi publicado."
            : message}
        </p>
      </div>
    </PageShell>
  );
}

function EmptyState({ report }: { report: PublicReport }) {
  return (
    <PageShell>
      <ReportHeader
        name={report.name}
        periodStart={report.period_start}
        periodEnd={report.period_end}
      />
      <div className="rounded-xl bg-white border border-gray-200 p-8 text-center shadow-sm">
        <FileBarChart2 className="h-8 w-8 text-gray-300 mx-auto mb-3" />
        <p className="text-sm text-gray-400">
          Nenhum snapshot gerado ainda para este relatório.
        </p>
      </div>
    </PageShell>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function RelatorioPublico() {
  const { token } = useParams<{ token: string }>();
  const { data, isLoading, isError, error } = usePublicReport(token ?? null);

  if (isLoading) return <LoadingState />;

  if (isError) {
    return <ErrorState message={(error as Error)?.message ?? "Erro desconhecido"} />;
  }

  if (!data) return null;

  // No snapshot yet
  if (!data.snapshot_id) return <EmptyState report={data} />;

  return (
    <PageShell>
      <ReportHeader
        name={data.name}
        periodStart={data.period_start}
        periodEnd={data.period_end}
      />
      {data.generated_at && (
        <p className="text-xs text-gray-400 text-right">
          Gerado em{" "}
          {new Date(data.generated_at).toLocaleDateString("pt-BR", {
            day: "2-digit",
            month: "long",
            year: "numeric",
            hour: "2-digit",
            minute: "2-digit",
          })}
        </p>
      )}
      <SnapshotCards payload={data.payload} />
      <p className="text-center text-xs text-gray-300 pt-4">
        Powered by Orbity · NoctusAI
      </p>
    </PageShell>
  );
}

/**
 * InstagramInsights — Instagram account insights page (v1).
 *
 * Sections (loading / empty / error / success each):
 *   1. Connection status — `/api/meta/status`; adapter=="fake" OR
 *      consent_required → "Conectar Instagram" CTA (navigates the browser
 *      to `/api/meta/oauth/start`, which 302's to the FB consent dialog).
 *   2. IG account picker — shown only when >1 account.
 *   3. KPI row — seguidores / seguindo / posts / alcance / visitas ao perfil,
 *      reusing `MetricCard`.
 *   4. Followers-over-time trend — recharts line chart from `/snapshots`.
 *   5. Per-post table — `/media` (reach, curtidas, comentários, salvos).
 *   6. "Capturar agora" — POST `/snapshot`, invalidates the snapshots query.
 *
 * PT-BR copy throughout (Brazilian product).
 */
import { useEffect, useMemo, useState } from "react";
import {
  Camera,
  CircleAlert,
  Eye,
  Grid3x3,
  Instagram,
  Loader2,
  RefreshCw,
  Users,
  UserPlus,
} from "lucide-react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

import { MetricCard } from "@/components/MetricCard";
import { apiUrl } from "@/lib/apiBase";
import {
  useCaptureIgSnapshot,
  useIgAccounts,
  useIgInsights,
  useIgMedia,
  useIgSnapshots,
  useMetaStatus,
  type IGAccount,
} from "@/hooks/useInstagramInsights";

// ─── Number formatting (mirrors useDashboard.formatNumber) ──────────────────

function formatNumber(n: number | null | undefined): string {
  const v = n ?? 0;
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `${(v / 1_000).toFixed(1)}K`;
  return v.toLocaleString("pt-BR");
}

// ─── Connection CTA ──────────────────────────────────────────────────────────

function ConnectInstagramCard({ error }: { error?: string | null }) {
  return (
    <Card data-testid="ig-connect-card">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Instagram className="h-5 w-5" />
          Conectar Instagram
        </CardTitle>
        <CardDescription>
          Conecte sua conta comercial do Instagram (via Meta) para ver
          seguidores, alcance e desempenho dos posts.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {error && (
          <div className="flex items-center gap-2 text-sm text-destructive">
            <CircleAlert className="h-4 w-4 shrink-0" />
            {error}
          </div>
        )}
        <Button
          data-testid="ig-connect-btn"
          onClick={() =>
            window.location.assign(apiUrl("/api/meta/oauth/start"))
          }
        >
          <Instagram className="mr-2 h-4 w-4" />
          Conectar Instagram
        </Button>
      </CardContent>
    </Card>
  );
}

// ─── Account picker ──────────────────────────────────────────────────────────

function AccountPicker({
  accounts,
  selectedId,
  onSelect,
}: {
  accounts: IGAccount[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  if (accounts.length <= 1) return null;
  return (
    <div className="w-full max-w-xs space-y-1.5">
      <Select value={selectedId ?? undefined} onValueChange={onSelect}>
        <SelectTrigger data-testid="ig-account-select">
          <SelectValue placeholder="Selecione uma conta" />
        </SelectTrigger>
        <SelectContent>
          {accounts.map((a) => (
            <SelectItem key={a.id} value={a.id}>
              @{a.username}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

// ─── Followers trend chart ───────────────────────────────────────────────────

function FollowersTrendChart({ igUserId }: { igUserId: string }) {
  const { data, isLoading, isError } = useIgSnapshots(igUserId, 90);

  const chartData = useMemo(
    () =>
      (data?.snapshots ?? []).map((s) => ({
        x: new Date(s.captured_at).toLocaleDateString("pt-BR", {
          day: "2-digit",
          month: "short",
        }),
        followers: s.followers_count ?? 0,
      })),
    [data],
  );

  if (isLoading) {
    return <Skeleton className="h-64 rounded-md" data-testid="ig-trend-loading" />;
  }

  if (isError) {
    return (
      <div
        className="flex h-64 items-center justify-center rounded-md border border-dashed text-sm text-destructive"
        data-testid="ig-trend-error"
      >
        Erro ao carregar histórico de seguidores.
      </div>
    );
  }

  if (chartData.length === 0) {
    return (
      <div
        className="flex h-64 items-center justify-center rounded-md border border-dashed px-4 text-center text-sm text-muted-foreground"
        data-testid="ig-trend-empty"
      >
        Sem histórico ainda — clique em "Capturar agora" para começar a
        acumular snapshots.
      </div>
    );
  }

  return (
    <div className="h-64 w-full" data-testid="ig-trend-chart">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
          <XAxis dataKey="x" fontSize={11} stroke="currentColor" opacity={0.6} />
          <YAxis
            tickFormatter={(v: number) => formatNumber(v)}
            fontSize={11}
            stroke="currentColor"
            opacity={0.6}
          />
          <Tooltip
            formatter={(value: number) => [formatNumber(value), "Seguidores"]}
            labelStyle={{ color: "var(--foreground)" }}
            contentStyle={{
              background: "var(--background)",
              border: "1px solid var(--border)",
              borderRadius: 6,
            }}
          />
          <Line
            type="monotone"
            dataKey="followers"
            stroke="hsl(var(--primary, 220 90% 56%))"
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

// ─── Per-post table ───────────────────────────────────────────────────────────

function PostsTable({ igUserId }: { igUserId: string }) {
  const { data, isLoading, isError } = useIgMedia(igUserId, 25);
  const media = data?.media ?? [];

  if (isLoading) {
    return (
      <div className="space-y-2" data-testid="ig-posts-loading">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-12 w-full rounded-md" />
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <div
        className="rounded-md border border-dashed p-6 text-center text-sm text-destructive"
        data-testid="ig-posts-error"
      >
        Erro ao carregar posts.
      </div>
    );
  }

  if (media.length === 0) {
    return (
      <div
        className="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground"
        data-testid="ig-posts-empty"
      >
        Nenhum post encontrado para esta conta.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto" data-testid="ig-posts-table">
      <table className="w-full min-w-[640px] border-separate border-spacing-0 text-sm">
        <thead>
          <tr className="border-b">
            <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground w-[40%]">
              Post
            </th>
            <th className="px-3 py-2 text-right text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Alcance
            </th>
            <th className="px-3 py-2 text-right text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Curtidas
            </th>
            <th className="px-3 py-2 text-right text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Comentários
            </th>
            <th className="px-3 py-2 text-right text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Salvos
            </th>
          </tr>
        </thead>
        <tbody>
          {media.map((item) => {
            const reach = item.insights?.reach ?? null;
            const saved = item.insights?.saved ?? null;
            return (
              <tr key={item.id} className="border-b last:border-0">
                <td className="px-3 py-3 align-top">
                  <div className="line-clamp-2 font-medium">
                    {item.caption ?? "(sem legenda)"}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {item.timestamp
                      ? new Date(item.timestamp).toLocaleDateString("pt-BR")
                      : "—"}
                  </div>
                </td>
                <td className="px-3 py-3 text-right tabular-nums align-middle">
                  {reach === null ? "—" : formatNumber(reach)}
                </td>
                <td className="px-3 py-3 text-right tabular-nums align-middle">
                  {formatNumber(item.like_count)}
                </td>
                <td className="px-3 py-3 text-right tabular-nums align-middle">
                  {formatNumber(item.comments_count)}
                </td>
                <td className="px-3 py-3 text-right tabular-nums align-middle">
                  {saved === null ? "—" : formatNumber(saved)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ─── Account panel (KPIs + trend + posts + capture) ──────────────────────────

function AccountPanel({ account }: { account: IGAccount }) {
  const { data: insights, isLoading: insightsLoading } = useIgInsights(
    account.id,
    30,
  );
  const capture = useCaptureIgSnapshot(account.id);

  const alcance = insights?.metrics?.reach ?? null;
  const visitas = insights?.metrics?.profile_views ?? null;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-lg font-semibold">@{account.username}</div>
          {account.name && (
            <div className="text-sm text-muted-foreground">{account.name}</div>
          )}
        </div>
        <Button
          onClick={() => capture.mutate()}
          disabled={capture.isPending}
          data-testid="ig-capture-btn"
        >
          {capture.isPending ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <Camera className="mr-2 h-4 w-4" />
          )}
          Capturar agora
        </Button>
      </div>

      {insights?.error && (
        <div
          className="flex items-center gap-2 rounded-md border border-dashed p-3 text-sm text-destructive"
          data-testid="ig-insights-error"
        >
          <CircleAlert className="h-4 w-4 shrink-0" />
          {insights.error}
        </div>
      )}

      {/* KPI row */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <MetricCard
          icon={Users}
          label="Seguidores"
          value={formatNumber(account.followers_count)}
        />
        <MetricCard
          icon={UserPlus}
          label="Seguindo"
          value={formatNumber(account.follows_count)}
        />
        <MetricCard
          icon={Grid3x3}
          label="Posts"
          value={formatNumber(account.media_count)}
        />
        <MetricCard
          icon={Eye}
          label="Alcance (30d)"
          value={insightsLoading ? "—" : formatNumber(alcance)}
          loading={insightsLoading}
        />
        <MetricCard
          icon={Instagram}
          label="Visitas ao perfil (30d)"
          value={insightsLoading ? "—" : formatNumber(visitas)}
          loading={insightsLoading}
        />
      </div>

      {/* Trend */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <RefreshCw className="h-5 w-5" />
            Seguidores ao longo do tempo
          </CardTitle>
          <CardDescription>Últimos 90 dias, por snapshot.</CardDescription>
        </CardHeader>
        <CardContent>
          <FollowersTrendChart igUserId={account.id} />
        </CardContent>
      </Card>

      {/* Posts */}
      <Card>
        <CardHeader>
          <CardTitle>Posts recentes</CardTitle>
          <CardDescription>
            Alcance, curtidas, comentários e salvos por post.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <PostsTable igUserId={account.id} />
        </CardContent>
      </Card>
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function InstagramInsights() {
  const { data: status, isLoading: statusLoading } = useMetaStatus();

  const needsConnect =
    !statusLoading && (status?.adapter === "fake" || status?.consent_required);

  const { data: accountsData, isLoading: accountsLoading, isError: accountsError } =
    useIgAccounts(!statusLoading && !needsConnect);

  const accounts = accountsData?.accounts ?? [];
  const [selectedId, setSelectedId] = useState<string | null>(null);

  useEffect(() => {
    if (!selectedId && accounts.length > 0) {
      setSelectedId(accounts[0].id);
    }
  }, [accounts, selectedId]);

  const selectedAccount = accounts.find((a) => a.id === selectedId) ?? null;

  return (
    <div className="container max-w-6xl space-y-6 py-6">
      <div>
        <h1 className="text-2xl font-semibold">Instagram Insights</h1>
        <p className="text-sm text-muted-foreground">
          Seguidores, alcance e desempenho de posts da sua conta comercial do
          Instagram.
        </p>
      </div>

      {statusLoading ? (
        <div className="space-y-4" data-testid="ig-status-loading">
          <Skeleton className="h-8 w-64" />
          <Skeleton className="h-40 w-full" />
        </div>
      ) : needsConnect ? (
        <ConnectInstagramCard error={status?.error} />
      ) : accountsLoading ? (
        <div className="space-y-4" data-testid="ig-accounts-loading">
          <Skeleton className="h-10 w-64" />
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-24 rounded-md" />
            ))}
          </div>
        </div>
      ) : accountsError ? (
        <Card>
          <CardContent
            className="flex items-center gap-2 p-6 text-sm text-destructive"
            data-testid="ig-accounts-error"
          >
            <CircleAlert className="h-4 w-4 shrink-0" />
            Erro ao carregar contas do Instagram.
          </CardContent>
        </Card>
      ) : accounts.length === 0 ? (
        <Card>
          <CardContent
            className="p-6 text-center text-sm text-muted-foreground"
            data-testid="ig-accounts-empty"
          >
            Nenhuma conta do Instagram encontrada para esta conexão do Meta.
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-6">
          <AccountPicker
            accounts={accounts}
            selectedId={selectedId}
            onSelect={setSelectedId}
          />
          {selectedAccount && <AccountPanel account={selectedAccount} />}
        </div>
      )}
    </div>
  );
}

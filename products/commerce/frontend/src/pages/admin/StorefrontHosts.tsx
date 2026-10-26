/**
 * Configurações > Endereços (`/admin/configuracoes/enderecos`) — the storefront hostnames that resolve to this store
 * (platform-admin only; the server's 403 renders as an explanation, not an
 * error). List + add + remove on the same page.
 */
import * as React from "react";
import { Badge, Button, EmptyState, Field, FormError, Input, Skeleton } from "@noctusai/lib/design-system";

import { useStorefrontHostMutations, useStorefrontHosts } from "@/hooks/useStorefrontHosts";
import { describeError, usePageT } from "@/lib/i18n";

export function HostsBody() {
  const { t } = usePageT();
  const hosts = useStorefrontHosts();
  const m = useStorefrontHostMutations();
  const [hostname, setHostname] = React.useState("");
  const [primary, setPrimary] = React.useState(false);
  const [confirming, setConfirming] = React.useState<string | null>(null);

  if (hosts.showSkeleton) {
    return (
      <div className="space-y-2" data-testid="hosts-loading">
        <Skeleton height={36} width="100%" />
        <Skeleton height={36} width="100%" announce={false} />
      </div>
    );
  }
  if (hosts.forbidden) return <EmptyState message={t("admin.hosts_forbidden")} />;
  if (!hosts.data) {
    return (
      <div className="space-y-2">
        <FormError message={`${t("common.error_loading")}: ${describeError(hosts.error, t)}`} />
        <Button variant="outline" onClick={() => hosts.refetch()}>
          {t("common.retry")}
        </Button>
      </div>
    );
  }

  async function add(ev: React.FormEvent) {
    ev.preventDefault();
    const value = hostname.trim().toLowerCase();
    if (!value) return;
    try {
      await m.add.mutateAsync({ hostname: value, is_primary: primary });
      setHostname("");
      setPrimary(false);
    } catch {
      // Rendered below from `m.add.error` (hostname_invalido / host_ja_existe).
    }
  }

  const mutErr = m.add.error ?? m.remove.error;
  return (
    <section className="space-y-4" aria-busy={hosts.isRefreshing}>
      {hosts.isRefreshing ? (
        <p role="status" className="text-xs text-muted-foreground">
          {t("common.refreshing")}
        </p>
      ) : null}
      {hosts.data.length === 0 ? (
        <EmptyState message={t("admin.hosts_empty")} />
      ) : (
        <ul className="divide-y rounded-md border" data-testid="hosts-list">
          {hosts.data.map((h) => (
            <li key={h.hostname} className="flex flex-wrap items-center justify-between gap-2 p-3 text-sm">
              <span className="flex items-center gap-2 font-mono">
                {h.hostname}
                {h.is_primary ? <Badge>{t("admin.hosts_primary")}</Badge> : null}
              </span>
              {confirming === h.hostname ? (
                <span className="flex items-center gap-2">
                  <span>{t("admin.hosts_remove_confirm", { host: h.hostname })}</span>
                  <Button
                    size="sm"
                    variant="destructive"
                    disabled={m.remove.isPending}
                    onClick={async () => {
                      try {
                        await m.remove.mutateAsync(h.hostname);
                        setConfirming(null);
                      } catch {
                        // Rendered below from `m.remove.error`.
                      }
                    }}
                  >
                    {t("common.remove")}
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setConfirming(null)}>
                    {t("common.cancel")}
                  </Button>
                </span>
              ) : (
                <Button size="sm" variant="ghost" onClick={() => setConfirming(h.hostname)}>
                  {t("common.remove")}
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}

      <form onSubmit={add} className="flex flex-wrap items-end gap-3" noValidate>
        <div className="min-w-64 flex-1">
          <Field label={t("admin.hosts_hostname")} required>
            <Input value={hostname} onChange={(e) => setHostname(e.target.value)} placeholder="loja.exemplo.com.br" />
          </Field>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={primary} onChange={(e) => setPrimary(e.target.checked)} />
          {t("admin.hosts_primary")}
        </label>
        <Button type="submit" disabled={m.add.isPending || !hostname.trim()}>
          {m.add.isPending ? t("common.saving") : t("admin.hosts_add")}
        </Button>
      </form>
      <FormError message={mutErr ? describeError(mutErr, t) : null} />
    </section>
  );
}

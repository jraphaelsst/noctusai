/**
 * Email Marketing · Domínios — sender-domain verification (Resend).
 *
 *   GET|POST   /api/email-marketing/settings/domains
 *   GET        /api/email-marketing/settings/domains/{id}/verify
 *   DELETE     /api/email-marketing/settings/domains/{id}
 *
 * Verification is a GET that mutates remote state, so it is a button here
 * rather than a query — the UI must not fire it on render.
 *
 * Route: /email/dominios (`email_dominios_noc` status_pagina, migration 085).
 */
import { useState } from "react";
import { toast } from "sonner";
import { AlertCircle, Globe, Plus, RefreshCw, Trash2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";

import { useEmDomainMutations, useEmDomains } from "@/hooks/useEmailMarketing";

const STATUS_LABEL: Record<string, string> = {
  pending: "Pendente",
  verified: "Verificado",
  failed: "Falhou",
};

export default function EmailDominios() {
  const { data, isPending, isFetching, isError } = useEmDomains();
  const { add, verify, remove } = useEmDomainMutations();
  const [domain, setDomain] = useState("");
  const [dns, setDns] = useState<{ id: string; records: unknown } | null>(null);

  const rows = data ?? [];
  const showSkeleton = isPending || (isFetching && rows.length === 0);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const value = domain.trim().toLowerCase();
    if (!value) return;
    add.mutate(value, {
      onSuccess: () => {
        toast.success("Domínio adicionado. Configure o DNS e verifique.");
        setDomain("");
      },
      onError: (err: unknown) =>
        toast.error("Erro ao adicionar domínio.", {
          description: err instanceof Error ? err.message : undefined,
        }),
    });
  }

  return (
    <div className="flex flex-col gap-6 p-6" data-testid="email-dominios-page">
      <header>
        <h1 className="text-lg font-semibold">Domínios de envio</h1>
        <p className="mt-0.5 text-xs text-muted-foreground">
          Domínios verificados no Resend — sem um domínio verificado, as
          campanhas não saem.
        </p>
      </header>

      <form
        className="flex items-end gap-2"
        onSubmit={submit}
        data-testid="dominio-form"
      >
        <div className="flex-1 space-y-1.5">
          <Label htmlFor="dom">Novo domínio</Label>
          <Input
            id="dom"
            value={domain}
            onChange={(e) => setDomain(e.target.value)}
            placeholder="envio.suaempresa.com.br"
            data-testid="dominio-input"
          />
        </div>
        <Button
          type="submit"
          disabled={!domain.trim() || add.isPending}
          data-testid="dominio-add"
        >
          <Plus className="mr-2 h-4 w-4" />
          Adicionar
        </Button>
      </form>

      {showSkeleton ? (
        <div className="space-y-2" data-testid="dominios-loading">
          {[1, 2].map((i) => (
            <Skeleton key={i} className="h-14 w-full" />
          ))}
        </div>
      ) : isError ? (
        <Card className="border-destructive" data-testid="dominios-error">
          <CardContent className="flex items-center gap-3 pt-6">
            <AlertCircle className="h-5 w-5 text-destructive" />
            <p className="text-sm text-destructive">
              Erro ao carregar domínios. Tente novamente.
            </p>
          </CardContent>
        </Card>
      ) : rows.length === 0 ? (
        <div
          className="flex flex-col items-center justify-center gap-3 py-16 text-muted-foreground"
          data-testid="dominios-empty"
        >
          <Globe className="h-10 w-10 opacity-20" />
          <p className="text-sm font-medium">Nenhum domínio cadastrado</p>
          <p className="max-w-sm text-center text-xs">
            Adicione o domínio que vai assinar os envios e publique os registros
            DNS que aparecerem aqui.
          </p>
        </div>
      ) : (
        <ul className="divide-y rounded-md border" data-testid="dominios-rows">
          {rows.map((d) => (
            <li
              key={d.id}
              className="flex flex-wrap items-center justify-between gap-2 px-3 py-3"
              data-testid={`dominio-row-${d.id}`}
            >
              <span className="flex items-center gap-2 text-sm">
                <Globe className="h-4 w-4 text-muted-foreground" />
                {d.domain}
                <Badge variant="secondary">
                  {STATUS_LABEL[d.status] ?? d.status}
                </Badge>
              </span>
              <span className="flex gap-1">
                <Button
                  size="sm"
                  variant="outline"
                  disabled={verify.isPending}
                  data-testid={`dominio-verify-${d.id}`}
                  onClick={() =>
                    verify.mutate(d.id, {
                      onSuccess: (res: any) => {
                        const row = res?.data ?? res;
                        setDns({ id: d.id, records: row?.dns_records ?? null });
                        toast.success("Verificação solicitada.");
                      },
                      onError: () => toast.error("Erro ao verificar domínio."),
                    })
                  }
                >
                  <RefreshCw className="mr-1 h-3.5 w-3.5" />
                  Verificar
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={remove.isPending}
                  data-testid={`dominio-remove-${d.id}`}
                  onClick={() =>
                    remove.mutate(d.id, {
                      onSuccess: () => toast.success("Domínio removido."),
                      onError: () => toast.error("Erro ao remover domínio."),
                    })
                  }
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </span>

              {dns?.id === d.id && dns.records ? (
                <pre
                  className="w-full overflow-auto rounded bg-muted p-3 text-xs"
                  data-testid={`dominio-dns-${d.id}`}
                >
                  {JSON.stringify(dns.records, null, 2)}
                </pre>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

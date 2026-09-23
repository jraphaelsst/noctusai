/**
 * Integrações → fontes de lead (wave-2 contract, Slice E2): WhatsApp (WAHA)
 * and Meta Lead Ads. Each inbound conversation / lead form becomes a lead +
 * a negócio in the Comercial funnel's entry stage.
 *
 * Setup is org-admin only (the PUT answers 403 otherwise) — non-admins see
 * the status and the webhook URL, with the form disabled. Secrets are
 * write-only: the API answers `*_configurad[oa]` booleans, the inputs start
 * empty, and an empty input on save keeps the stored secret.
 */
import { useEffect, useState } from "react";
import { Button, Field, FormError, Input } from "@noctusai/lib/design-system";
import type { BadgeVariant } from "@noctusai/lib/design-system";
import { AlertTriangle, Megaphone, MessageCircle, ShieldAlert } from "lucide-react";
import { toast } from "sonner";

import {
  useMetaLeads,
  useSalvarMetaLeads,
  useSalvarWhatsappLeads,
  useWhatsappLeads,
} from "@/hooks/useLeadSources";
import { describeError } from "@/lib/errors";
import { useIsOrgAdmin } from "@/lib/useIsOrgAdmin";
import { CopyField, IntegracaoCard } from "./IntegracaoCard";

function badge(configurado: boolean, ultimoErro: string | null): { texto: string; variante: BadgeVariant } {
  if (ultimoErro) return { texto: "com erro", variante: "destructive" };
  return configurado ? { texto: "configurado", variante: "default" } : { texto: "não configurado", variante: "muted" };
}

function Aviso({ children }: { children: React.ReactNode }) {
  return (
    <p className="flex items-start gap-2 rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-xs text-destructive">
      <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" />
      <span>{children}</span>
    </p>
  );
}

function SoAdmin() {
  return <p className="text-xs text-muted-foreground">Somente administradores da agência podem alterar esta configuração.</p>;
}

// ─── WhatsApp (WAHA) ─────────────────────────────────────────────────────────

export function WhatsappLeadsCard() {
  const { status, showSkeleton, isError, error } = useWhatsappLeads();
  const salvar = useSalvarWhatsappLeads();
  const admin = useIsOrgAdmin();
  const [f, setF] = useState({ base_url: "", session: "default", api_key: "" });
  const [sujo, setSujo] = useState(false);

  useEffect(() => {
    if (status && !sujo) setF({ base_url: status.base_url ?? "", session: status.session || "default", api_key: "" });
  }, [status, sujo]);

  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => {
    setF((p) => ({ ...p, [k]: e.target.value }));
    setSujo(true);
  };
  const valido = /^https?:\/\//.test(f.base_url.trim()) && f.session.trim();

  return (
    <IntegracaoCard
      titulo="WhatsApp (WAHA) — leads"
      icone={<MessageCircle className="h-4 w-4" />}
      badge={status ? badge(status.configurado, status.ultimo_erro) : null}
      descricao="A primeira mensagem de um contato novo vira lead + negócio na primeira etapa do Comercial."
      showSkeleton={showSkeleton}
      erro={isError ? describeError(error, "Não foi possível carregar o WhatsApp.") : null}
      testId="whatsapp-leads-card"
    >
      {status ? (
        <div className="space-y-3">
          {!status.cofre_configurado ? (
            <Aviso>Criptografia não configurada neste ambiente (IGIG_COFRE_KEY): a API key não pode ser salva.</Aviso>
          ) : null}
          {!status.hmac_configurado ? (
            <Aviso>
              Assinatura do webhook não configurada na plataforma (IGIG_WAHA_WEBHOOK_HMAC_SECRET): as mensagens
              recebidas serão recusadas.
            </Aviso>
          ) : null}
          {status.ultimo_erro ? (
            <p className="flex items-start gap-1 text-xs text-destructive">
              <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
              {status.ultimo_erro}
            </p>
          ) : null}

          <form
            className="space-y-3"
            onSubmit={(e) => {
              e.preventDefault();
              if (!valido) return;
              salvar.mutate(
                { base_url: f.base_url.trim(), session: f.session.trim(), api_key: f.api_key.trim() || undefined },
                {
                  onSuccess: () => {
                    setSujo(false);
                    toast.success("WhatsApp salvo.");
                  },
                },
              );
            }}
          >
            <fieldset disabled={!admin} className="grid gap-3 sm:grid-cols-2">
              <div className="sm:col-span-2">
                <Field label="URL do WAHA" required>
                  <Input
                    className="max-sm:h-10"
                    type="url"
                    inputMode="url"
                    value={f.base_url}
                    onChange={set("base_url")}
                    placeholder="https://waha.suaagencia.com"
                  />
                </Field>
              </div>
              <Field label="Sessão" required>
                <Input className="max-sm:h-10" value={f.session} onChange={set("session")} />
              </Field>
              <Field label="API key">
                <Input
                  className="max-sm:h-10"
                  type="password"
                  autoComplete="new-password"
                  aria-label="API key do WAHA"
                  placeholder={status.api_key_configurada ? "manter chave atual…" : "X-Api-Key do WAHA"}
                  value={f.api_key}
                  onChange={set("api_key")}
                />
              </Field>
            </fieldset>
            <FormError message={salvar.isError ? describeError(salvar.error, "Não foi possível salvar o WhatsApp.") : null} />
            {admin ? (
              <div className="flex justify-end">
                <Button type="submit" className="max-sm:h-10" disabled={!valido || !sujo || salvar.isPending}>
                  {salvar.isPending ? "Salvando…" : "Salvar WhatsApp"}
                </Button>
              </div>
            ) : (
              <SoAdmin />
            )}
          </form>

          {status.webhook_url ? (
            <CopyField label="URL do webhook (cole no WAHA)" valor={status.webhook_url} />
          ) : status.webhook_url_erro ? (
            <Aviso>{status.webhook_url_erro}</Aviso>
          ) : (
            <p className="text-xs text-muted-foreground">Salve a configuração para gerar a URL do webhook.</p>
          )}
        </div>
      ) : null}
    </IntegracaoCard>
  );
}

// ─── Meta Lead Ads ───────────────────────────────────────────────────────────

const APP_SECRET_ORIGEM: Record<string, string> = {
  org: "app secret próprio",
  plataforma: "app secret da plataforma",
  nenhuma: "sem app secret",
};

export function MetaLeadsCard() {
  const { status, showSkeleton, isError, error } = useMetaLeads();
  const salvar = useSalvarMetaLeads();
  const admin = useIsOrgAdmin();
  const [f, setF] = useState({ page_id: "", verify_token: "", page_access_token: "", app_secret: "" });
  const [sujo, setSujo] = useState(false);

  useEffect(() => {
    if (status && !sujo) setF({ page_id: status.page_id ?? "", verify_token: "", page_access_token: "", app_secret: "" });
  }, [status, sujo]);

  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => {
    setF((p) => ({ ...p, [k]: e.target.value }));
    setSujo(true);
  };
  const verifyOk = !!status?.verify_token_configurado || f.verify_token.trim().length >= 8;
  const tokenOk = !!status?.page_access_token_configurado || !!f.page_access_token.trim();
  const valido = /^\d+$/.test(f.page_id.trim()) && verifyOk && tokenOk;

  return (
    <IntegracaoCard
      titulo="Meta Lead Ads — leads"
      icone={<Megaphone className="h-4 w-4" />}
      badge={status ? badge(status.configurado, status.ultimo_erro) : null}
      descricao="Cada formulário de anúncio preenchido na Página vira lead + negócio na primeira etapa do Comercial."
      showSkeleton={showSkeleton}
      erro={isError ? describeError(error, "Não foi possível carregar o Meta Lead Ads.") : null}
      testId="meta-leads-card"
    >
      {status ? (
        <div className="space-y-3">
          {!status.cofre_configurado ? (
            <Aviso>Criptografia não configurada neste ambiente (IGIG_COFRE_KEY): os tokens não podem ser salvos.</Aviso>
          ) : null}
          {!status.app_secret_configurado ? (
            <Aviso>
              Sem app secret (nem da agência nem da plataforma, IGIG_META_APP_SECRET): as entregas da Meta não podem
              ter a assinatura verificada e serão recusadas.
            </Aviso>
          ) : null}
          {status.ultimo_erro ? (
            <p className="flex items-start gap-1 text-xs text-destructive">
              <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
              {status.ultimo_erro}
            </p>
          ) : null}

          <form
            className="space-y-3"
            onSubmit={(e) => {
              e.preventDefault();
              if (!valido) return;
              salvar.mutate(
                {
                  page_id: f.page_id.trim(),
                  verify_token: f.verify_token.trim() || undefined,
                  page_access_token: f.page_access_token.trim() || undefined,
                  app_secret: f.app_secret.trim() || undefined,
                },
                {
                  onSuccess: () => {
                    setSujo(false);
                    toast.success("Meta Lead Ads salvo.");
                  },
                },
              );
            }}
          >
            <fieldset disabled={!admin} className="grid gap-3 sm:grid-cols-2">
              <Field label="ID da Página" required>
                <Input className="max-sm:h-10" inputMode="numeric" value={f.page_id} onChange={set("page_id")} placeholder="1234567890" />
              </Field>
              <Field label="Verify token" required={!status.verify_token_configurado}>
                <Input
                  className="max-sm:h-10"
                  type="password"
                  autoComplete="new-password"
                  aria-label="Verify token"
                  placeholder={status.verify_token_configurado ? "manter atual…" : "mín. 8 caracteres"}
                  value={f.verify_token}
                  onChange={set("verify_token")}
                />
              </Field>
              <Field label="Token de acesso da Página" required={!status.page_access_token_configurado}>
                <Input
                  className="max-sm:h-10"
                  type="password"
                  autoComplete="new-password"
                  aria-label="Token de acesso da Página"
                  placeholder={status.page_access_token_configurado ? "manter atual…" : "page access token"}
                  value={f.page_access_token}
                  onChange={set("page_access_token")}
                />
              </Field>
              <Field label={`App secret (opcional · ${APP_SECRET_ORIGEM[status.app_secret_origem] ?? status.app_secret_origem})`}>
                <Input
                  className="max-sm:h-10"
                  type="password"
                  autoComplete="new-password"
                  aria-label="App secret"
                  placeholder={status.app_secret_origem === "org" ? "manter atual…" : "usa o da plataforma"}
                  value={f.app_secret}
                  onChange={set("app_secret")}
                />
              </Field>
            </fieldset>
            <FormError message={salvar.isError ? describeError(salvar.error, "Não foi possível salvar o Meta Lead Ads.") : null} />
            {admin ? (
              <div className="flex justify-end">
                <Button type="submit" className="max-sm:h-10" disabled={!valido || !sujo || salvar.isPending}>
                  {salvar.isPending ? "Salvando…" : "Salvar Meta"}
                </Button>
              </div>
            ) : (
              <SoAdmin />
            )}
          </form>

          {status.webhook_url ? (
            <CopyField label="URL de callback (cole no app da Meta)" valor={status.webhook_url} />
          ) : status.webhook_url_erro ? (
            <Aviso>{status.webhook_url_erro}</Aviso>
          ) : null}
        </div>
      ) : null}
    </IntegracaoCard>
  );
}

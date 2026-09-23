/**
 * Integrações → E-mail: the org's SMTP account + Gmail mailbox (wave-2
 * contract, Slice B). Backend mirror: `app/routers/integracoes_email_router.py`.
 *
 *   GET/PUT/DELETE /api/integracoes/email/smtp        (GET never carries the password)
 *   POST           /api/integracoes/email/smtp/testar {para} → {message_id}
 *   GET/DELETE     /api/integracoes/email/gmail
 *   GET            /api/integracoes/email/gmail/oauth/start → {url}
 *
 * Every answer is the `{data}` envelope. There is no password in any type
 * here, deliberately — the API never returns one.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrapData } from "@/lib/api";

/** `org` = the agency's own account; `plataforma` = the platform env
 * fallback (`SMTP_HOST/…`), reported explicitly — never silent; `nenhuma`. */
export type OrigemSmtp = "org" | "plataforma" | "nenhuma";
export type SegurancaSmtp = "ssl" | "starttls";

export interface SmtpStatus {
  configurado: boolean;
  origem: OrigemSmtp;
  host: string | null;
  port: number | null;
  username: string | null;
  security: SegurancaSmtp | null;
  from_email: string | null;
  from_name: string | null;
}

export interface SmtpInput {
  host: string;
  port: number;
  username: string;
  /** Omitted ⇒ the stored password is kept. */
  password?: string;
  security: SegurancaSmtp;
  from_email: string;
  from_name?: string | null;
}

export interface GmailStatus {
  conectado: boolean;
  email: string | null;
  watch_ativo: boolean;
  expira_em: string | null;
  /** False ⇒ the platform's Pub/Sub env (`GMAIL_PUSH_*`) is missing: reply
   * detection cannot run, and the backend never attempts the watch. */
  configuracao_gcp_ok: boolean;
  ultimo_erro: string | null;
}

export const EMAIL_INTEGRACAO_KEY = ["igig", "integracoes", "email"] as const;
const SMTP_KEY = [...EMAIL_INTEGRACAO_KEY, "smtp"] as const;
const GMAIL_KEY = [...EMAIL_INTEGRACAO_KEY, "gmail"] as const;

export function useSmtp() {
  const query = useQuery({
    queryKey: SMTP_KEY,
    queryFn: () => api.get("/api/integracoes/email/smtp").then(unwrapData<SmtpStatus>),
  });
  const data = query.data;
  return { ...query, smtp: data ?? null, showSkeleton: query.isPending && !data, isRefreshing: query.isFetching && !!data };
}

export function useSmtpMutations() {
  const qc = useQueryClient();
  const salvar = useMutation({
    mutationFn: (payload: SmtpInput) => api.put("/api/integracoes/email/smtp", payload).then(unwrapData<SmtpStatus>),
    onSuccess: (status) => qc.setQueryData(SMTP_KEY, status),
  });
  const remover = useMutation({
    mutationFn: () => api.delete("/api/integracoes/email/smtp").then(unwrapData<SmtpStatus>),
    onSuccess: (status) => qc.setQueryData(SMTP_KEY, status),
  });
  const testar = useMutation({
    mutationFn: (para: string) =>
      api.post("/api/integracoes/email/smtp/testar", { para }).then(unwrapData<{ message_id: string }>),
  });
  return { salvar, remover, testar };
}

export function useGmail() {
  const query = useQuery({
    queryKey: GMAIL_KEY,
    queryFn: () => api.get("/api/integracoes/email/gmail").then(unwrapData<GmailStatus>),
  });
  const data = query.data;
  return { ...query, gmail: data ?? null, showSkeleton: query.isPending && !data, isRefreshing: query.isFetching && !!data };
}

export function useGmailMutations() {
  const qc = useQueryClient();
  /** The Google consent URL; the caller navigates the window to it. Google
   * redirects back to `/integracoes?gmail=ok|erro&motivo=`. */
  const iniciarOAuth = useMutation({
    mutationFn: () => api.get("/api/integracoes/email/gmail/oauth/start").then(unwrapData<{ url: string }>),
  });
  const desconectar = useMutation({
    mutationFn: () => api.delete("/api/integracoes/email/gmail").then(unwrapData<GmailStatus>),
    onSuccess: (status) => qc.setQueryData(GMAIL_KEY, status),
  });
  return { iniciarOAuth, desconectar };
}

/** pt-BR text for the `motivo` the OAuth callback appends to `?gmail=erro`. */
export const GMAIL_MOTIVO_LABEL: Record<string, string> = {
  consentimento_negado: "o acesso não foi autorizado na tela do Google",
  parametros_ausentes: "o Google não devolveu o código de autorização",
  state_invalido: "a autorização expirou (mais de 10 minutos) — tente de novo",
  oauth_nao_configurado: "o OAuth do Google não está configurado no servidor",
  troca_falhou: "não foi possível trocar o código de autorização",
  sem_refresh_token: "o Google não devolveu um token permanente — remova o acesso do app na conta Google e conecte de novo",
  escopo_insuficiente: "a permissão de leitura dos e-mails não foi concedida",
  perfil_falhou: "não foi possível ler o endereço da caixa",
};

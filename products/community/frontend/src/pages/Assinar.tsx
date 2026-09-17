/**
 * Assinar — `/assinar` (community-m2-contract.md §Frontend), the PUBLIC
 * checkout page.
 *
 * Registered as a `publicRoute` in `App.tsx` (the same seam `/inscrever`
 * uses, module 1) — rendered WITHOUT the seed `Layout`/auth gate. Picks a
 * tier + payment method, collects nome/email/telefone (+ CPF for
 * pix/boleto), passes a Cloudflare Turnstile token (product decision P2),
 * and submits `POST /api/checkout`.
 *
 * CONTRACT GAP (flagged — see this delivery's `drift-found:`): module 2
 * defines no PUBLIC tier-listing endpoint. This page calls the existing
 * `usePlanos({ativo:true})` hook (module 1's `GET /api/planos`, currently
 * gated by `Depends(get_current_user_org)`) unauthenticated — exactly like
 * `/inscrever` calls `GET /api/aplicacoes/formulario` unauthenticated —
 * relying on the shared `api` client sending the request without a session
 * (`getAuthToken()` → `null` omits the header rather than failing). The
 * backend must mark this read PUBLIC for `ativo=true` (mirroring
 * `aplicacao_perguntas`'s anon-readable pattern) or this page's tier list
 * never loads for a real visitor.
 *
 * Response handling (amendment A2 — never reveals whether an e-mail is
 * already a member): `checkout_url === null` is a NORMAL friendly outcome
 * (`status: "verifique_seu_email"`), checked BEFORE the Pix branch and
 * NEVER rendered as an error.
 *
 * CPF (product decision P1): required for pix/boleto, omitted (not sent as
 * `""`) for cartao. Never persisted anywhere client-side — held only in
 * page-local `useState`, never in `localStorage`, never appended to a URL,
 * never logged.
 */
import { useMemo, useState, type FormEvent } from "react";
import { CheckCircle2 } from "lucide-react";
import { Button, Input } from "@noctusai/lib/design-system";
import { Card, EmptyState, ErrorState, Field, FormError, Select } from "@/components/FormControls";
import { errorMessage } from "@/lib/errors";
import { formatBRLFromCents } from "@/lib/money";
import { usePlanos, type Plano } from "@/hooks/usePlanos";
import {
  useCheckout,
  stripCpfPunctuation,
  isValidCpfLength,
  type CheckoutMetodo,
  type CheckoutResponse,
} from "@/hooks/useCheckout";
import { TurnstileWidget } from "@/pages/checkout/TurnstileWidget";
import { PixQrCard } from "@/pages/checkout/PixQrCard";

/** Read literally so Vite inlines it at build time (same convention as
 * `env.ts`'s `BACKEND_API_URL`/`CORE_URL` getters). Empty string when unset
 * — `TurnstileWidget` renders its own "unavailable" fallback in that case. */
function getTurnstileSiteKey(): string {
  return (import.meta.env.VITE_TURNSTILE_SITE_KEY as string | undefined) ?? "";
}

const METODO_LABELS: Record<CheckoutMetodo, string> = {
  cartao: "Cartão de crédito",
  pix: "Pix",
  boleto: "Boleto",
};

function planoLabel(p: Plano): string {
  return `${p.nome} — ${formatBRLFromCents(p.preco_centavos)}/${p.ciclo === "mensal" ? "mês" : "ano"}`;
}

export default function Assinar() {
  const { data, isPending, isFetching, error } = usePlanos({ ativo: true, page_size: 100 });
  const [planoId, setPlanoId] = useState("");
  const [metodo, setMetodo] = useState<CheckoutMetodo>("cartao");
  const [nome, setNome] = useState("");
  const [email, setEmail] = useState("");
  const [telefone, setTelefone] = useState("");
  const [cpf, setCpf] = useState("");
  const [turnstileToken, setTurnstileToken] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [result, setResult] = useState<CheckoutResponse | null>(null);
  const checkout = useCheckout();

  const showSkeleton = isPending && !data;
  const isRefreshing = isFetching && !!data;
  const requiresCpf = metodo === "pix" || metodo === "boleto";

  const planos = data?.items ?? [];
  const selectedPlano = useMemo(() => planos.find((p) => p.id === planoId), [planos, planoId]);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(null);

    if (requiresCpf && !isValidCpfLength(cpf)) {
      setFormError("Informe um CPF válido (11 dígitos) para pagamento por Pix ou boleto.");
      return;
    }

    checkout.mutate(
      {
        plano_id: planoId,
        metodo,
        nome,
        email,
        telefone,
        ...(requiresCpf ? { cpf: stripCpfPunctuation(cpf) } : {}),
        turnstile_token: turnstileToken,
      },
      {
        onSuccess: (res) => {
          // A2: `checkout_url: null` is a normal outcome, checked first —
          // never treated as an error and never distinguished in copy from
          // any other reason the checkout didn't redirect.
          if (res.checkout_url === null) {
            setResult(res);
            return;
          }
          if (metodo === "pix" && res.pix_qr) {
            setResult(res);
            return;
          }
          window.location.href = res.checkout_url;
        },
        onError: (err) => setFormError(errorMessage(err)),
      },
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-background p-4">
      <div className="w-full max-w-lg">
        <Card>
          <h1 className="text-xl font-bold text-foreground">Assine a comunidade</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Escolha seu plano e forma de pagamento.
            {/* lying-loading-ok: text-only suffix, never unmounts real content */}
            {isRefreshing ? " Atualizando…" : ""}
          </p>

          {showSkeleton ? (
            <div className="mt-6 space-y-3" data-testid="assinar-skeleton">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-9 animate-pulse rounded-md bg-muted" />
              ))}
            </div>
          ) : error ? (
            <div className="mt-6">
              <ErrorState message={errorMessage(error)} />
            </div>
          ) : result ? (
            <div className="mt-6" data-testid="assinar-result">
              {result.checkout_url === null ? (
                <div className="flex flex-col items-center gap-2 py-8 text-center" data-testid="assinar-verifique-email">
                  <CheckCircle2 className="h-10 w-10 text-primary" />
                  <p className="font-medium text-foreground">Verifique seu e-mail</p>
                  <p className="text-sm text-muted-foreground">
                    Recebemos sua solicitação. Enviamos as próximas instruções para o e-mail
                    informado.
                  </p>
                </div>
              ) : (
                result.pix_qr && <PixQrCard pixQr={result.pix_qr} />
              )}
            </div>
          ) : planos.length === 0 ? (
            <div className="mt-6">
              <EmptyState message="Nenhum plano disponível no momento." />
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="mt-6 space-y-4">
              <FormError message={formError} />
              <Field label="Plano" required>
                <Select value={planoId} onChange={(e) => setPlanoId(e.target.value)} required>
                  <option value="" disabled>
                    Selecione um plano...
                  </option>
                  {planos.map((p) => (
                    <option key={p.id} value={p.id}>
                      {planoLabel(p)}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Forma de pagamento" required>
                <div className="flex flex-wrap gap-3" role="radiogroup" aria-label="Forma de pagamento">
                  {(Object.keys(METODO_LABELS) as CheckoutMetodo[]).map((m) => (
                    <label key={m} className="flex items-center gap-2 text-sm text-foreground">
                      <input
                        type="radio"
                        name="metodo"
                        value={m}
                        checked={metodo === m}
                        onChange={() => setMetodo(m)}
                      />
                      {METODO_LABELS[m]}
                    </label>
                  ))}
                </div>
              </Field>
              <Field label="Nome" required>
                <Input value={nome} onChange={(e) => setNome(e.target.value)} required />
              </Field>
              <Field label="E-mail" required>
                <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
              </Field>
              <Field label="Telefone" required help="Formato internacional, ex: +5511999999999">
                <Input
                  value={telefone}
                  onChange={(e) => setTelefone(e.target.value)}
                  placeholder="+5511999999999"
                  required
                />
              </Field>
              {requiresCpf && (
                <Field
                  label="CPF"
                  required
                  help="Enviado diretamente ao provedor de pagamento — não é armazenado por nós."
                >
                  <Input
                    value={cpf}
                    onChange={(e) => setCpf(e.target.value)}
                    placeholder="000.000.000-00"
                    inputMode="numeric"
                    autoComplete="off"
                    required
                  />
                </Field>
              )}
              <TurnstileWidget siteKey={getTurnstileSiteKey()} onVerify={setTurnstileToken} onExpire={() => setTurnstileToken("")} />
              <Button
                type="submit"
                variant="primary"
                disabled={checkout.isPending || !planoId || !turnstileToken}
                className="w-full"
              >
                {checkout.isPending ? "Processando..." : "Assinar"}
              </Button>
              {selectedPlano && (
                <p className="text-center text-xs text-muted-foreground">
                  {formatBRLFromCents(selectedPlano.preco_centavos)} /{" "}
                  {selectedPlano.ciclo === "mensal" ? "mês" : "ano"}
                </p>
              )}
            </form>
          )}
        </Card>
      </div>
    </div>
  );
}

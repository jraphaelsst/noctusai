/**
 * Pricing — self-serve subscription.
 *
 * Reads the sellable catalog (`GET /api/billing/plans`: plans with active
 * prices + the gateways the platform offers) and starts a managed
 * subscription (`POST /api/billing/subscribe`), then sends the payer to the
 * gateway's page. Pix shows its QR code inline as well.
 *
 * The previous version posted `billing_period` to `/api/billing/checkout`,
 * whose strict schema only accepts `billing_cycle` — every click was a 422.
 */
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, Header, Input, Skeleton, useTheme } from '@noctusai/lib/design-system';
import { NotificationBell } from '../components/NotificationBell';
import { useAuth } from '../lib/auth-context';
import {
  type BillingCycle,
  type BillingPlan,
  type Gateway,
  type SubscribeResult,
  formatCents,
  useBillingMutation,
  usePublicCatalog,
} from '../lib/billing';

type Method = 'card' | 'pix' | 'boleto';

const AUDIENCE_LABEL = { individual: 'Para corretores', company: 'Para imobiliárias', any: '' } as const;
const GATEWAY_METHODS: Record<Gateway, Method[]> = { stripe: ['card'], asaas: ['pix', 'boleto', 'card'] };
const METHOD_LABEL: Record<Method, string> = { card: 'Cartão', pix: 'Pix', boleto: 'Boleto' };

export function redirectTo(url: string) {
  window.location.assign(url);
}

function PixPanel({ result }: { result: SubscribeResult }) {
  const [copied, setCopied] = useState(false);
  if (!result.pix_qr) return null;
  return (
    <div className="mx-auto max-w-md space-y-3 rounded-lg border border-border bg-card p-6 text-center">
      <h3 className="font-semibold">Pague com Pix</h3>
      <img
        alt="QR code Pix"
        className="mx-auto h-48 w-48"
        src={`data:image/png;base64,${result.pix_qr.encoded_image}`}
      />
      <Button
        variant="outline"
        onClick={async () => {
          await navigator.clipboard.writeText(result.pix_qr!.payload);
          setCopied(true);
        }}
      >
        {copied ? 'Código copiado' : 'Copiar código Pix'}
      </Button>
      <p className="text-sm">
        Ou <a className="text-primary underline" href={result.checkout_url}>abra a fatura</a>.
        A licença é liberada assim que o pagamento for confirmado.
      </p>
    </div>
  );
}

export function Pricing({ onRedirect = redirectTo }: { onRedirect?: (url: string) => void } = {}) {
  const { user, isAdmin, logout } = useAuth();
  const navigate = useNavigate();
  const { theme, toggleTheme } = useTheme();
  const { data, isPending, isFetching, error } = usePublicCatalog();
  const [cycle, setCycle] = useState<BillingCycle>('monthly');
  const [selected, setSelected] = useState<BillingPlan | null>(null);
  const [gateway, setGateway] = useState<Gateway | null>(null);
  const [method, setMethod] = useState<Method>('card');
  const [taxId, setTaxId] = useState('');
  const subscribe = useBillingMutation((b, body: Parameters<typeof b.subscribe>[0]) => b.subscribe(body));

  const showSkeleton = isPending && !data;
  const isRefreshing = isFetching && !!data;
  const plans = data?.plans ?? [];
  const gateways = data?.gateways ?? [];
  const hasYearly = plans.some((p) => p.prices.some((pr) => pr.billing_cycle === 'yearly'));
  const chosenGateway = gateway ?? gateways[0] ?? null;
  const digits = taxId.replace(/\D/g, '');
  const needsTaxId = chosenGateway === 'asaas';
  const taxIdOk = !needsTaxId || digits.length === 11 || digits.length === 14;

  const priceFor = (plan: BillingPlan) => plan.prices.find((p) => p.billing_cycle === cycle);

  function start() {
    if (!selected || !chosenGateway) return;
    const price = priceFor(selected);
    if (!price) return;
    subscribe.mutate(
      {
        plan_price_id: price.id,
        gateway: chosenGateway,
        billing_method: chosenGateway === 'stripe' ? 'card' : method,
        ...(needsTaxId ? { tax_id: digits } : {}),
        success_url: `${window.location.origin}/checkout/success`,
        cancel_url: `${window.location.origin}/checkout/cancel`,
      },
      {
        onSuccess: (result) => {
          if (!result.pix_qr) onRedirect(result.checkout_url);
        },
      },
    );
  }

  return (
    <div className="min-h-screen bg-background">
      <Header
        user={{ name: user?.nome || '', email: user?.email || '', role: isAdmin ? 'Administrador' : 'Membro' }}
        onLogout={() => { logout(); navigate('/login'); }}
        theme={theme}
        onThemeToggle={toggleTheme}
        actions={
          <div className="flex items-center gap-2">
            <Button variant="outline" onClick={() => navigate('/')}>Voltar</Button>
            <NotificationBell />
          </div>
        }
      />

      <main className="mx-auto max-w-5xl space-y-8 px-4 py-10 sm:px-6 lg:px-8" aria-busy={isRefreshing}>
        <div className="text-center">
          <h2 className="text-3xl font-bold text-foreground">Escolha seu plano</h2>
          <p className="mt-2 text-muted-foreground">Assinatura do Social Wiring — Edição de Fotos incluída.</p>
        </div>

        {subscribe.data?.pix_qr ? (
          <PixPanel result={subscribe.data} />
        ) : showSkeleton ? (
          <div className="grid gap-6 md:grid-cols-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-64" />)}</div>
        ) : error && !data ? (
          <p role="alert" className="text-center text-destructive">{error.message}</p>
        ) : plans.length === 0 ? (
          <p className="text-center text-muted-foreground">Nenhum plano disponível no momento.</p>
        ) : (
          <>
            {hasYearly && (
              <div role="radiogroup" aria-label="Ciclo" className="flex justify-center gap-2">
                {(['monthly', 'yearly'] as BillingCycle[]).map((c) => (
                  <Button key={c} role="radio" aria-checked={cycle === c}
                    variant={cycle === c ? 'primary' : 'outline'} onClick={() => setCycle(c)}>
                    {c === 'monthly' ? 'Mensal' : 'Anual'}
                  </Button>
                ))}
              </div>
            )}

            <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
              {plans.map((plan) => {
                const price = priceFor(plan);
                return (
                  <div key={plan.id}
                    className={`flex flex-col rounded-lg border bg-card p-6 ${selected?.id === plan.id ? 'border-primary ring-2 ring-primary' : 'border-border'}`}>
                    <h3 className="text-lg font-semibold">{plan.nome}</h3>
                    {AUDIENCE_LABEL[plan.audience] && (
                      <p className="text-xs text-muted-foreground">{AUDIENCE_LABEL[plan.audience]}</p>
                    )}
                    {plan.descricao && <p className="mt-2 text-sm text-muted-foreground">{plan.descricao}</p>}
                    <div className="my-4 text-3xl font-bold">
                      {price ? formatCents(price.amount_cents, price.currency) : '—'}
                      {price && <span className="ml-1 text-sm font-normal text-muted-foreground">/{cycle === 'monthly' ? 'mês' : 'ano'}</span>}
                    </div>
                    {plan.trial_days > 0 && (
                      <p className="mb-4 text-sm">{plan.trial_days} dias grátis (cartão cadastrado no início)</p>
                    )}
                    <Button className="mt-auto" disabled={!price} onClick={() => setSelected(plan)}
                      variant={selected?.id === plan.id ? 'primary' : 'outline'}>
                      {price ? (selected?.id === plan.id ? 'Selecionado' : 'Escolher') : 'Indisponível neste ciclo'}
                    </Button>
                  </div>
                );
              })}
            </div>

            {selected && (
              <section aria-label="Pagamento" className="mx-auto max-w-md space-y-4 rounded-lg border border-border bg-card p-6">
                <h3 className="font-semibold">Pagamento — {selected.nome}</h3>
                {gateways.length === 0 && (
                  <p role="alert" className="text-sm text-destructive">Pagamentos indisponíveis no momento.</p>
                )}
                {gateways.length > 1 && (
                  <div className="flex gap-2">
                    {gateways.map((g) => (
                      <Button key={g} variant={chosenGateway === g ? 'primary' : 'outline'}
                        onClick={() => { setGateway(g); setMethod(GATEWAY_METHODS[g][0]); }}>
                        {g === 'stripe' ? 'Cartão internacional (Stripe)' : 'Pix, boleto ou cartão (Asaas)'}
                      </Button>
                    ))}
                  </div>
                )}
                {chosenGateway === 'asaas' && (
                  <>
                    <div className="flex gap-3">
                      {GATEWAY_METHODS.asaas.map((m) => (
                        <label key={m} className="flex items-center gap-1 text-sm">
                          <input type="radio" name="method" checked={method === m} onChange={() => setMethod(m)} />
                          {METHOD_LABEL[m]}
                        </label>
                      ))}
                    </div>
                    <label className="block text-sm">CPF ou CNPJ
                      <Input value={taxId} inputMode="numeric" onChange={(e) => setTaxId(e.target.value)} />
                    </label>
                    {selected.trial_days > 0 && (
                      <p className="text-xs text-muted-foreground">
                        Pelo Asaas a primeira cobrança é imediata (o período de teste vale para cartão via Stripe).
                      </p>
                    )}
                  </>
                )}
                {subscribe.error && <p role="alert" className="text-sm text-destructive">{subscribe.error.message}</p>}
                <Button className="w-full" disabled={!chosenGateway || !taxIdOk || subscribe.isPending} onClick={start}>
                  {subscribe.isPending ? 'Abrindo pagamento…' : 'Continuar para o pagamento'}
                </Button>
              </section>
            )}
          </>
        )}
      </main>
    </div>
  );
}

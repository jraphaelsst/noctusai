/**
 * Checkout dialog — nome / e-mail / CPF → POST /api/public/checkout →
 * redirect to the gateway's hosted page. Built on the seed `Dialog` + `Input`
 * (canonical organs), styled to the landing identity via `.co-*` classes in
 * `pages/landing.css` (render this INSIDE `.store-landing` so they apply).
 *
 * The price is never sent: the server reads it (contract §3).
 */
import { useState } from "react";
import { ApiError } from "@noctusai/lib";
import { Dialog, DialogBody, DialogHeader, Input } from "@noctusai/lib/design-system";
import { useCheckout } from "@/hooks/useStore";
import { isValidCpf, isValidEmail, maskCpf } from "@/lib/api";

type Field = "nome" | "email" | "cpf";
type Errors = Partial<Record<Field, string>>;

export function validateCheckout(v: { nome: string; email: string; cpf: string }): Errors {
  const e: Errors = {};
  if (v.nome.trim().length < 3) e.nome = "Informe seu nome completo.";
  if (!isValidEmail(v.email)) e.email = "Informe um e-mail válido.";
  if (!isValidCpf(v.cpf)) e.cpf = "CPF inválido. Confira os números.";
  return e;
}

/** Map a 422 body (FastAPI `detail[]` with `loc`, or `{error:{details}}`) to fields. */
export function fieldErrorsFrom422(body: unknown): Errors {
  const out: Errors = {};
  const b = body as { detail?: unknown; field?: string; error?: { details?: unknown } } | undefined;
  // Store's flat business-error shape (contract A6): {detail, code, field}.
  if (b?.field === "nome" || b?.field === "email" || b?.field === "cpf") {
    out[b.field] = typeof b.detail === "string" ? b.detail : "Valor inválido.";
    return out;
  }
  const list = Array.isArray(b?.detail) ? b!.detail : Array.isArray(b?.error?.details) ? b!.error!.details : [];
  for (const item of list as { loc?: unknown[]; field?: string; msg?: string; message?: string }[]) {
    const key = (item.field ?? (Array.isArray(item.loc) ? String(item.loc[item.loc.length - 1]) : "")) as Field;
    if (key === "nome" || key === "email" || key === "cpf") {
      out[key] = item.msg ?? item.message ?? "Valor inválido.";
    }
  }
  return out;
}

export function checkoutErrorMessage(err: unknown): { form: string | null; fields: Errors } {
  if (err instanceof ApiError) {
    if (err.status === 409) return { form: "Vendas pausadas no momento. Volte em breve.", fields: {} };
    if (err.status === 503) return { form: "Pagamento indisponível no momento. Tente novamente em alguns minutos.", fields: {} };
    if (err.status === 422) {
      const fields = fieldErrorsFrom422(err.body);
      return { form: Object.keys(fields).length ? null : "Confira os dados informados.", fields };
    }
    if (err.status === 429) return { form: "Muitas tentativas. Aguarde um instante e tente de novo.", fields: {} };
  }
  return { form: "Não foi possível iniciar o pagamento. Tente novamente.", fields: {} };
}

interface Props {
  open: boolean;
  onClose: () => void;
  productName?: string | null;
  priceLabel?: string | null;
}

export function CheckoutDialog({ open, onClose, productName, priceLabel }: Props) {
  const [nome, setNome] = useState("");
  const [email, setEmail] = useState("");
  const [cpf, setCpf] = useState("");
  const [errors, setErrors] = useState<Errors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const checkout = useCheckout();
  const busy = checkout.isPending || checkout.isSuccess;

  function submit(ev: React.FormEvent) {
    ev.preventDefault();
    const v = validateCheckout({ nome, email, cpf });
    setErrors(v);
    setFormError(null);
    if (Object.keys(v).length) return;
    checkout.mutate(
      { nome: nome.trim(), email: email.trim(), cpf: cpf.replace(/\D/g, "") },
      {
        onSuccess: (r) => window.location.assign(r.checkout_url),
        onError: (err) => {
          const m = checkoutErrorMessage(err);
          setErrors(m.fields);
          setFormError(m.form);
        },
      },
    );
  }

  return (
    <Dialog open={open} onClose={busy ? () => undefined : onClose} title="Finalizar compra" className="co-panel">
      <DialogHeader className="co-head">
        <button type="button" className="co-close" onClick={onClose} aria-label="Fechar" disabled={busy}>×</button>
        <p className="eyebrow">Pagamento seguro</p>
        <h3 style={{ marginTop: 10 }}>Quase lá.</h3>
        <p>Preencha seus dados para ir ao pagamento. O kit chega no seu e-mail logo após a confirmação.</p>
      </DialogHeader>
      <DialogBody className="co-body">
        <form onSubmit={submit} noValidate style={{ display: "grid", gap: 14 }}>
          <label className="co-label">
            Nome completo
            <Input className="co-input" value={nome} onChange={(e) => setNome(e.target.value)} autoComplete="name"
              aria-invalid={!!errors.nome} disabled={busy} />
            {errors.nome && <span className="co-err" role="alert">{errors.nome}</span>}
          </label>
          <label className="co-label">
            E-mail
            <Input className="co-input" type="email" value={email} onChange={(e) => setEmail(e.target.value)}
              autoComplete="email" inputMode="email" aria-invalid={!!errors.email} disabled={busy} />
            {errors.email && <span className="co-err" role="alert">{errors.email}</span>}
          </label>
          <label className="co-label">
            CPF
            <Input className="co-input" value={cpf} onChange={(e) => setCpf(maskCpf(e.target.value))}
              inputMode="numeric" placeholder="000.000.000-00" autoComplete="off" aria-invalid={!!errors.cpf} disabled={busy} />
            {errors.cpf && <span className="co-err" role="alert">{errors.cpf}</span>}
          </label>
          {priceLabel && (
            <div className="co-total"><span>{productName ?? "Kit completo"}</span><span>{priceLabel}</span></div>
          )}
          {formError && <div className="co-form-err" role="alert">{formError}</div>}
          <button type="submit" className="btn" disabled={busy}>
            {checkout.isSuccess ? "Redirecionando…" : checkout.isPending ? "Aguarde…" : "Ir para o pagamento"}
          </button>
        </form>
      </DialogBody>
    </Dialog>
  );
}

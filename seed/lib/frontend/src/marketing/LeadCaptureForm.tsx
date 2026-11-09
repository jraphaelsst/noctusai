import { useEffect, useId, useRef, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { toast } from "sonner";
import { Bell } from "lucide-react";
import { Button } from "../design-system/ui/Button";
import { Input } from "../design-system/ui/Input";
import { Card, Select, Textarea } from "../design-system/ui/FormControls";
import { cn } from "../utils";
import { Reveal } from "./primitives";
import { SectionHead, sectionClass, wrapClass } from "./shared";
import { TurnstileSlot, readTurnstileSiteKey } from "./TurnstileSlot";

export interface LeadInterest { slug: string; nome: string }

export interface LeadFormValues {
  nome: string;
  /** Digits only (10 to 13). */
  whatsapp: string;
  email?: string;
  empresa?: string;
  /** Project phase (brief variant only). */
  tipo?: string;
  mensagem?: string;
  /** Always true: submit is refused without the contact consent. */
  consentimento: true;
  /** Waitlist variant: the product(s) of interest. */
  product_interest?: string[];
  /** Present only when a Turnstile widget ran and issued a token. */
  turnstileToken?: string;
}

export interface LeadCaptureFormProps {
  /**
   * "brief" (contact: phase select + company), "waitlist" (from a catalog card) or "product" (a single-product
   * landing: no phase select, no company field).
   */
  variant: "brief" | "waitlist" | "product";
  /** Waitlist variant: the product being waited for. Setting it prefills (focus + undo toast). */
  interest?: LeadInterest | null;
  /** "Remover" / "Desfazer": clear the interest (the parent switches back to the brief variant). */
  onInterestClear?: () => void;
  /** The caller owns the endpoint. Reject/throw to show the error notice (the typed values are kept). */
  onSubmit: (values: LeadFormValues) => Promise<void> | void;
  id?: string;
  eyebrow?: string;
  /** Section h2 (e.g. "Conte o que você precisa"). */
  title: string;
  /** Card h3 for the brief variant (the waitlist variant has its own). */
  heading: string;
  description?: string;
  privacyHref?: string;
  /** Overrides `import.meta.env.VITE_TURNSTILE_SITE_KEY` (tests / explicit wiring). Empty = no widget. */
  turnstileSiteKey?: string;
  /** Product variant: slug sent as `product_interest: [slug]` (e.g. "agents"). */
  productInterest?: string;
  /** Submit button label. Defaults: "Enviar mensagem" (brief/product) / "Entrar na lista" (waitlist). */
  submitLabel?: string;
  /** Label of the free-text field. Default "O que você precisa?". */
  messageLabel?: string;
  /** Hint under the free-text field. Default "Uma ou duas frases bastam.". */
  messageHint?: string;
  /** Placeholder of the free-text field. Default none. */
  messagePlaceholder?: string;
  /**
   * What the contact consent is about, completing "Concordo em ser contatado pela NoctusAI sobre {subject}, conforme a
   * Política de Privacidade." Default "este assunto". Example: "os Agentes", "o Social Wiring".
   */
  consentSubject?: string;
  /** Sent-state heading (not used by the waitlist). Default "Recebemos a sua mensagem.". */
  successTitle?: string;
  /** Sent-state body (not used by the waitlist). Default "Uma pessoa da NoctusAI vai responder pelo WhatsApp que você informou.". */
  successBody?: ReactNode;
  /** Sent-state button that resets the form. Default "Enviar outra mensagem". */
  againLabel?: string;
  /** Optional follow-up shown after a brief is sent (e.g. "Continuar no WhatsApp"). */
  successAction?: { label: string; href: string };
}

type FieldKey = "nome" | "whatsapp" | "email" | "consent" | "turnstile";
type Errors = Partial<Record<FieldKey, string>>;
type Status = "idle" | "sending" | "ok" | "error";

export const LEAD_MESSAGES = {
  nome: "Informe o seu nome.",
  whatsappEmpty: "Informe o seu WhatsApp para podermos responder.",
  whatsappShape: "Confira o número: DDD + número, ex.: 11 91234-5678.",
  email: "Confira o e-mail (ex.: nome@empresa.com.br) ou deixe em branco.",
  consent: "Marque a autorização de contato para enviar.",
  turnstile: "Confirme a verificação anti-robô para enviar.",
} as const;

const labelClass = "text-sm font-medium text-foreground";
const hintClass = "text-xs text-muted-foreground";
const errClass = "text-xs font-medium text-destructive";
const inputLg = "h-10 text-base";

/**
 * Lead capture form. Variants: "brief" (contact) and "waitlist" (from a catalog
 * card). The submit goes through the caller's `onSubmit`; the organ owns no endpoint.
 * Cloudflare Turnstile runs only when a site key is configured; without one it
 * renders nothing and sends no token (the backend's early-dev bypass).
 */
export function LeadCaptureForm({
  variant, interest = null, onInterestClear, onSubmit,
  id = "contato-form", eyebrow, title, heading, description, privacyHref = "/consent/privacy-policy",
  turnstileSiteKey, successAction, productInterest, submitLabel: submitLabelProp, messageLabel = "O que você precisa?",
  messageHint = "Uma ou duas frases bastam.", messagePlaceholder, consentSubject = "este assunto",
  successTitle = "Recebemos a sua mensagem.", successBody = "Uma pessoa da NoctusAI vai responder pelo WhatsApp que você informou.",
  againLabel = "Enviar outra mensagem",
}: LeadCaptureFormProps) {
  const uid = useId();
  const f = (n: string) => `${uid}-${n}`;
  const waitlist = variant === "waitlist" && !!interest;
  const siteKey = turnstileSiteKey ?? readTurnstileSiteKey();

  const [errors, setErrors] = useState<Errors>({});
  const [status, setStatus] = useState<Status>("idle");
  const [token, setToken] = useState<string | null>(null);
  const [formKey, setFormKey] = useState(0);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const formRef = useRef<HTMLFormElement>(null);
  const nomeRef = useRef<HTMLInputElement>(null);
  const prevSlug = useRef<string | null>(interest?.slug ?? null);
  const sentInterest = useRef<LeadInterest | null>(null);

  // A new interest arriving AFTER mount = a catalog card was clicked: move focus
  // to the first field and say what happened, with an undo (toast region is the
  // consumer's <Toaster/>, a polite live region).
  useEffect(() => {
    const slug = interest?.slug ?? null;
    if (slug && slug !== prevSlug.current && interest) {
      nomeRef.current?.focus();
      toast(`${interest.nome} foi colocado no formulário.`, {
        action: { label: "Desfazer", onClick: () => onInterestClear?.() },
      });
    }
    prevSlug.current = slug;
  }, [interest, onInterestClear]);

  const productVariant = variant === "product";
  const submitLabel = submitLabelProp ?? (waitlist ? "Entrar na lista" : "Enviar mensagem");

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (status === "sending") return;
    const fd = new FormData(e.currentTarget);
    const val = (k: string) => String(fd.get(k) ?? "").trim();
    const digits = val("whatsapp").replace(/\D/g, "");
    const next: Errors = {};
    if (!val("nome")) next.nome = LEAD_MESSAGES.nome;
    if (!digits) next.whatsapp = LEAD_MESSAGES.whatsappEmpty;
    else if (digits.length < 10 || digits.length > 13) next.whatsapp = LEAD_MESSAGES.whatsappShape;
    if (val("email") && !/^\S+@\S+\.\S+$/.test(val("email"))) next.email = LEAD_MESSAGES.email;
    if (fd.get("consent") !== "on") next.consent = LEAD_MESSAGES.consent;
    if (siteKey && !token) next.turnstile = LEAD_MESSAGES.turnstile;
    setErrors(next);
    const firstBad = (["nome", "whatsapp", "email", "consent"] as const).find((k) => next[k]);
    if (firstBad) {
      (formRef.current?.querySelector(`[data-field="${firstBad}"]`) as HTMLElement | null)?.focus();
      return;
    }
    if (next.turnstile) return;

    const values: LeadFormValues = {
      nome: val("nome"),
      whatsapp: digits,
      consentimento: true,
      ...(val("email") ? { email: val("email") } : {}),
      ...(!productVariant && val("empresa") ? { empresa: val("empresa") } : {}),
      ...(!waitlist && !productVariant && val("tipo") ? { tipo: val("tipo") } : {}),
      ...(val("mensagem") ? { mensagem: val("mensagem") } : {}),
      ...(waitlist && interest
        ? { product_interest: [interest.slug] }
        : productInterest ? { product_interest: [productInterest] } : {}),
      ...(siteKey && token ? { turnstileToken: token } : {}),
    };
    setStatus("sending");
    try {
      await onSubmit(values);
      sentInterest.current = waitlist ? interest : null;
      setStatus("ok");
      requestAnimationFrame(() => titleRef.current?.focus());
    } catch {
      setStatus("error");
    }
  }

  function again() {
    setStatus("idle");
    setErrors({});
    setToken(null);
    setFormKey((k) => k + 1);
    onInterestClear?.();
    requestAnimationFrame(() => nomeRef.current?.focus());
  }

  const sending = status === "sending";
  const describedBy = (field: FieldKey, hint?: string) =>
    [hint ? f(`${field}-hint`) : null, errors[field] ? f(`${field}-err`) : null].filter(Boolean).join(" ") || undefined;
  const cardHeading = waitlist ? "Entrar na lista de espera" : heading;

  return (
    <section id={id} aria-labelledby={f("title-sec")} className={cn(sectionClass, "bg-muted/40")}>
      <div className={`${wrapClass} grid gap-8 lg:grid-cols-2`}>
        <Reveal>
          <SectionHead eyebrow={eyebrow} title={title} titleId={f("title-sec")} description={description} />
        </Reveal>
        <Reveal delay={0.1}>
          <Card className="p-6">
            <h3 ref={titleRef} tabIndex={-1} className="mb-4 text-lg font-semibold text-foreground">{cardHeading}</h3>

            {status === "ok" ? (
              <div>
                <div className="rounded-lg border border-success bg-success-light p-4 text-sm text-foreground">
                  <strong className="block">
                    {sentInterest.current
                      ? `Pronto, você está na lista de espera do ${sentInterest.current.nome}.`
                      : successTitle}
                  </strong>
                  {sentInterest.current
                    ? "Avisamos pelo WhatsApp informado quando ele abrir."
                    : successBody}
                </div>
                {successAction && !sentInterest.current ? (
                  <p className="mt-3"><a className="text-sm font-medium underline" href={successAction.href}>{successAction.label}</a></p>
                ) : null}
                <Button variant="ghost" className="mt-3" onClick={again}>{againLabel}</Button>
              </div>
            ) : (
              <form key={formKey} ref={formRef} noValidate onSubmit={handleSubmit} aria-busy={sending} className="flex flex-col gap-4">
                {waitlist && interest ? (
                  <div className="flex items-center gap-2 rounded-lg border border-warning bg-warning-light p-3 text-sm text-foreground">
                    <Bell className="h-4 w-4 shrink-0" aria-hidden="true" />
                    <span className="rounded-full border border-warning px-2 py-0.5 text-xs font-semibold">Lista de espera</span>
                    <span>Avise-me quando abrir: <b>{interest.nome}</b></span>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="ml-auto"
                      onClick={() => { onInterestClear?.(); requestAnimationFrame(() => nomeRef.current?.focus()); }}
                    >
                      Remover<span className="sr-only"> {interest.nome} da lista</span>
                    </Button>
                  </div>
                ) : null}

                <p className={hintClass}>Campos com * são obrigatórios.</p>

                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="flex flex-col gap-1.5">
                    <label htmlFor={f("nome")} className={labelClass}>Nome *</label>
                    <Input ref={nomeRef} id={f("nome")} name="nome" data-field="nome" autoComplete="name" required readOnly={sending}
                      className={inputLg} aria-invalid={errors.nome ? true : undefined} aria-describedby={describedBy("nome")} />
                    {errors.nome ? <span id={f("nome-err")} className={errClass}>{errors.nome}</span> : null}
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <label htmlFor={f("whatsapp")} className={labelClass}>WhatsApp *</label>
                    <Input id={f("whatsapp")} name="whatsapp" data-field="whatsapp" type="tel" autoComplete="tel" inputMode="tel" required readOnly={sending}
                      className={inputLg} aria-invalid={errors.whatsapp ? true : undefined} aria-describedby={describedBy("whatsapp", "x")} />
                    <span id={f("whatsapp-hint")} className={hintClass}>Com DDD. Ex.: 11 91234-5678</span>
                    {errors.whatsapp ? <span id={f("whatsapp-err")} className={errClass}>{errors.whatsapp}</span> : null}
                  </div>
                </div>

                <div className={cn("grid gap-4", !productVariant && "sm:grid-cols-2")}>
                  <div className="flex flex-col gap-1.5">
                    <label htmlFor={f("email")} className={labelClass}>E-mail (opcional)</label>
                    <Input id={f("email")} name="email" data-field="email" type="email" autoComplete="email" readOnly={sending}
                      className={inputLg} aria-invalid={errors.email ? true : undefined} aria-describedby={describedBy("email")} />
                    {errors.email ? <span id={f("email-err")} className={errClass}>{errors.email}</span> : null}
                  </div>
                  {!productVariant ? (
                    <div className="flex flex-col gap-1.5">
                      <label htmlFor={f("empresa")} className={labelClass}>Empresa (opcional)</label>
                      <Input id={f("empresa")} name="empresa" autoComplete="organization" readOnly={sending} className={inputLg} />
                    </div>
                  ) : null}
                </div>

                {!waitlist && !productVariant ? (
                  <div className="flex flex-col gap-1.5">
                    <label htmlFor={f("tipo")} className={labelClass}>Em que fase está o projeto?</label>
                    <Select id={f("tipo")} name="tipo" className={inputLg} disabled={sending}>
                      <option value="">Ainda não sei</option>
                      <option value="diagnostico">Quero um diagnóstico</option>
                      <option value="prototipo">Quero ver um protótipo</option>
                      <option value="producao">Já sei o que construir</option>
                      <option value="outro">Outro</option>
                    </Select>
                  </div>
                ) : null}

                <div className="flex flex-col gap-1.5">
                  <label htmlFor={f("mensagem")} className={labelClass}>{messageLabel}</label>
                  <Textarea id={f("mensagem")} name="mensagem" maxLength={600} readOnly={sending} placeholder={messagePlaceholder} aria-describedby={f("mensagem-hint")} />
                  <span id={f("mensagem-hint")} className={hintClass}>{messageHint}</span>
                </div>

                <div className="flex flex-col gap-1.5">
                  <label className="flex items-start gap-2 text-sm text-foreground">
                    <input type="checkbox" name="consent" data-field="consent" required disabled={sending}
                      className="mt-1 h-4 w-4 accent-primary focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
                      aria-invalid={errors.consent ? true : undefined} aria-describedby={describedBy("consent")} />
                    <span>
                      {`Concordo em ser contatado pela NoctusAI sobre ${consentSubject}, conforme a`}{" "}
                      <a href={privacyHref} className="underline">Política de Privacidade</a>. *
                    </span>
                  </label>
                  {errors.consent ? <span id={f("consent-err")} className={errClass}>{errors.consent}</span> : null}
                </div>

                <TurnstileSlot siteKey={siteKey} onToken={setToken} />
                {errors.turnstile ? <span role="alert" className={errClass}>{errors.turnstile}</span> : null}

                <div role="status" aria-live="polite">
                  {status === "error" ? (
                    <div role="alert" className="rounded-lg border border-destructive p-3 text-sm text-foreground">
                      <strong className="block text-destructive">Não foi possível enviar agora.</strong>
                      O que você escreveu continua aqui. Tente de novo em instantes.
                    </div>
                  ) : null}
                </div>

                <div>
                  <Button type="submit" variant="primary" className="h-10 px-5 text-base" disabled={sending}>
                    {sending ? "Enviando…" : submitLabel}
                  </Button>
                </div>
              </form>
            )}
          </Card>
        </Reveal>
      </div>
    </section>
  );
}

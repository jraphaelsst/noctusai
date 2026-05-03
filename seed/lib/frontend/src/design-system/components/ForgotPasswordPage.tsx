/**
 * NoctusAI Shared Forgot Password Page Component
 *
 * Supabase-based password reset form with configurable branding.
 * Used by products that authenticate directly via Supabase Auth
 * (e.g., Therapy Platform, ERP, future direct-auth products).
 *
 * States: form -> loading -> success ("Email enviado!") -> error
 *
 * Zero external dependencies beyond React + sonner + supabase + lucide.
 * Uses plain useState for form state (no react-hook-form dependency).
 */
import { useState } from "react";
import { toast } from "sonner";
import type { LucideIcon } from "lucide-react";
import { Loader2, ArrowLeft, CheckCircle2 } from "lucide-react";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnySupabaseClient = { auth: any };

export interface ForgotPasswordPageProps {
  /** Lucide icon component displayed above the title */
  brandIcon: LucideIcon;
  /** Main title text (e.g., "ERP Imobiliario") */
  brandTitle: string;
  /** Supabase client instance for authentication */
  supabase: AnySupabaseClient;
  /** URL to redirect to after password reset (passed to resetPasswordForEmail) */
  redirectTo?: string;
  /** Path for "back to login" link (default "/login") */
  loginPath?: string;
  /** Render function for links — products provide their own Link component */
  renderLink?: (props: { to: string; className?: string; children: React.ReactNode }) => React.ReactNode;
}

function DefaultLink({ to, className, children }: { to: string; className?: string; children: React.ReactNode }) {
  return <a href={to} className={className}>{children}</a>;
}

export function ForgotPasswordPage({
  brandIcon: BrandIcon,
  brandTitle,
  supabase,
  redirectTo,
  loginPath = "/login",
  renderLink,
}: ForgotPasswordPageProps) {
  const [email, setEmail] = useState("");
  const [emailError, setEmailError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [sent, setSent] = useState(false);

  const LinkComponent = renderLink ?? DefaultLink;

  function validate(): boolean {
    setEmailError("");
    if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      setEmailError("Email invalido");
      return false;
    }
    return true;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!validate()) return;

    setIsLoading(true);
    try {
      const options = redirectTo ? { redirectTo } : undefined;
      const { error } = await supabase.auth.resetPasswordForEmail(email, options);

      if (error) {
        toast.error("Erro ao enviar email", { description: error.message });
        return;
      }

      setSent(true);
    } catch {
      toast.error("Erro inesperado ao enviar email");
    } finally {
      setIsLoading(false);
    }
  }

  const inputCls = "flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50";

  return (
    <div className="flex items-center justify-center min-h-screen bg-background p-4">
      <div className="w-full max-w-md bg-card rounded-lg border border-border shadow-sm">
        {/* Header */}
        <div className="flex flex-col items-center p-6 pb-2">
          <BrandIcon className="h-10 w-10 text-primary mb-2" />
          <h1 className="text-2xl font-semibold text-foreground">Recuperar Senha</h1>
          <p className="text-sm text-muted-foreground mt-1">
            {sent
              ? "Email enviado com sucesso!"
              : `Informe seu email para receber o link de recuperacao`}
          </p>
        </div>

        {/* Content */}
        <div className="p-6 pt-4">
          {sent ? (
            <div className="text-center space-y-4 py-4">
              <CheckCircle2 className="h-16 w-16 text-green-500 mx-auto" />
              <p className="text-sm text-muted-foreground">
                Enviamos um link de recuperacao para <strong>{email}</strong>. Verifique sua caixa de entrada.
              </p>
              <LinkComponent
                to={loginPath}
                className="inline-flex items-center justify-center gap-2 w-full h-10 rounded-md border border-input bg-background text-sm font-medium hover:bg-accent hover:text-accent-foreground transition-colors"
              >
                <ArrowLeft className="h-4 w-4" /> Voltar para Login
              </LinkComponent>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="space-y-2">
                <label htmlFor="forgot-email" className="text-sm font-medium text-foreground">
                  Email
                </label>
                <input
                  id="forgot-email"
                  type="email"
                  placeholder="seu@email.com"
                  value={email}
                  onChange={(e) => { setEmail(e.target.value); setEmailError(""); }}
                  className={inputCls}
                />
                {emailError && <p className="text-xs text-destructive">{emailError}</p>}
              </div>

              <button
                type="submit"
                disabled={isLoading}
                className="inline-flex items-center justify-center gap-2 w-full h-10 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:pointer-events-none"
              >
                {isLoading ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Enviando...
                  </>
                ) : (
                  "Enviar link de recuperacao"
                )}
              </button>
            </form>
          )}
        </div>

        {/* Footer — back to login (only when form is visible) */}
        {!sent && (
          <div className="flex justify-center p-6 pt-0">
            <LinkComponent to={loginPath} className="text-sm text-muted-foreground hover:text-foreground flex items-center gap-1">
              <ArrowLeft className="h-3 w-3" /> Voltar para Login
            </LinkComponent>
          </div>
        )}
      </div>
    </div>
  );
}

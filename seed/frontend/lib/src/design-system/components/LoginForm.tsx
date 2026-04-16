/**
 * NoctusAI Shared Login Form Component
 *
 * Supabase-based login form with configurable branding.
 * Used by products that authenticate directly via Supabase Auth
 * (e.g., Therapy Platform, future direct-auth products).
 *
 * Core platform does NOT use this — it has its own REST-based login.
 * SSO-only products (ERP, PF) don't use this either.
 *
 * Zero external dependencies beyond React + sonner + supabase + lucide.
 * Uses plain useState for form state (no react-hook-form dependency).
 */
import { useState } from "react";
import { toast } from "sonner";
import type { LucideIcon } from "lucide-react";
import { Loader2 } from "lucide-react";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnySupabaseClient = { auth: any };

export interface LoginFormProps {
  /** Lucide icon component displayed above the title */
  brandIcon: LucideIcon;
  /** Main title text (e.g., "Plataforma de Terapia") */
  brandTitle: string;
  /** Optional subtitle below the title */
  brandSubtitle?: string;
  /** Supabase client instance for authentication */
  supabase: AnySupabaseClient;
  /** Called after successful login */
  onSuccess: () => void;
  /** Show "Forgot password?" link (default false) */
  showForgotPassword?: boolean;
  /** Path for forgot password link (default "/forgot-password") */
  forgotPasswordPath?: string;
  /** Show "Create account" link (default false) */
  showRegisterLink?: boolean;
  /** Path for register link (default "/register") */
  registerPath?: string;
  /** Show Google OAuth button placeholder (default false) */
  showGoogleOAuth?: boolean;
  /** Render function for links — products provide their own Link component */
  renderLink?: (props: { to: string; className?: string; children: React.ReactNode }) => React.ReactNode;
}

function DefaultLink({ to, className, children }: { to: string; className?: string; children: React.ReactNode }) {
  return <a href={to} className={className}>{children}</a>;
}

export function LoginForm({
  brandIcon: BrandIcon,
  brandTitle,
  brandSubtitle,
  supabase,
  onSuccess,
  showForgotPassword = false,
  forgotPasswordPath = "/forgot-password",
  showRegisterLink = false,
  registerPath = "/register",
  showGoogleOAuth = false,
  renderLink,
}: LoginFormProps) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [emailError, setEmailError] = useState("");
  const [passwordError, setPasswordError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const LinkComponent = renderLink ?? DefaultLink;

  function validate(): boolean {
    let valid = true;
    setEmailError("");
    setPasswordError("");

    if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      setEmailError("Email invalido");
      valid = false;
    }
    if (!password || password.length < 6) {
      setPasswordError("Senha deve ter no minimo 6 caracteres");
      valid = false;
    }
    return valid;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!validate()) return;

    setIsLoading(true);
    try {
      const { error } = await supabase.auth.signInWithPassword({ email, password });

      if (error) {
        toast.error("Erro ao entrar", { description: error.message });
        return;
      }

      toast.success("Login realizado com sucesso!");
      onSuccess();
    } catch {
      toast.error("Erro inesperado ao entrar");
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
          <h1 className="text-2xl font-semibold text-foreground">Entrar</h1>
          <p className="text-sm text-muted-foreground mt-1">
            {brandSubtitle || `Acesse sua conta no ${brandTitle}`}
          </p>
        </div>

        {/* Form */}
        <div className="p-6 pt-4">
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <label htmlFor="login-email" className="text-sm font-medium text-foreground">
                Email
              </label>
              <input
                id="login-email"
                type="email"
                placeholder="seu@email.com"
                value={email}
                onChange={(e) => { setEmail(e.target.value); setEmailError(""); }}
                className={inputCls}
              />
              {emailError && <p className="text-xs text-destructive">{emailError}</p>}
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <label htmlFor="login-password" className="text-sm font-medium text-foreground">
                  Senha
                </label>
                {showForgotPassword && (
                  <LinkComponent to={forgotPasswordPath} className="text-xs text-primary hover:underline">
                    Esqueceu a senha?
                  </LinkComponent>
                )}
              </div>
              <input
                id="login-password"
                type="password"
                placeholder="******"
                value={password}
                onChange={(e) => { setPassword(e.target.value); setPasswordError(""); }}
                className={inputCls}
              />
              {passwordError && <p className="text-xs text-destructive">{passwordError}</p>}
            </div>

            <button
              type="submit"
              disabled={isLoading}
              className="inline-flex items-center justify-center gap-2 w-full h-10 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:pointer-events-none"
            >
              {isLoading ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Entrando...
                </>
              ) : (
                "Entrar"
              )}
            </button>
          </form>

          {showGoogleOAuth && (
            <>
              <div className="my-4 flex items-center gap-4">
                <div className="flex-1 h-px bg-border" />
                <span className="text-xs text-muted-foreground">ou</span>
                <div className="flex-1 h-px bg-border" />
              </div>
              <button
                type="button"
                disabled
                className="inline-flex items-center justify-center w-full h-10 rounded-md border border-input bg-background text-sm font-medium hover:bg-accent hover:text-accent-foreground transition-colors disabled:opacity-50 disabled:pointer-events-none"
              >
                Entrar com Google (em breve)
              </button>
            </>
          )}
        </div>

        {/* Footer */}
        {showRegisterLink && (
          <div className="flex justify-center p-6 pt-0">
            <p className="text-sm text-muted-foreground">
              Nao tem conta?{" "}
              <LinkComponent to={registerPath} className="text-primary hover:underline font-medium">
                Criar conta
              </LinkComponent>
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

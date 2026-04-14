/**
 * NoctusAI Shared Login Form Component
 *
 * Supabase-based login form with configurable branding.
 * Used by products that authenticate directly via Supabase Auth
 * (e.g., Therapy Platform, future direct-auth products).
 *
 * Core platform does NOT use this — it has its own REST-based login.
 * SSO-only products (ERP, PF) don't use this either.
 */
import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { toast } from "sonner";
import type { SupabaseClient } from "@supabase/supabase-js";
import type { LucideIcon } from "lucide-react";
import { Loader2 } from "lucide-react";

const loginSchema = z.object({
  email: z.string().email("Email invalido"),
  password: z.string().min(6, "Senha deve ter no minimo 6 caracteres"),
});

type LoginFormData = z.infer<typeof loginSchema>;

export interface LoginFormProps {
  /** Lucide icon component displayed above the title */
  brandIcon: LucideIcon;
  /** Main title text (e.g., "Plataforma de Terapia") */
  brandTitle: string;
  /** Optional subtitle below the title */
  brandSubtitle?: string;
  /** Supabase client instance for authentication */
  supabase: SupabaseClient;
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

/**
 * Default link renderer using a plain <a> tag.
 * Products should pass their router's Link component via renderLink.
 */
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
  const [isLoading, setIsLoading] = useState(false);

  const LinkComponent = renderLink ?? DefaultLink;

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginFormData>({
    resolver: zodResolver(loginSchema),
  });

  const onSubmit = async (data: LoginFormData) => {
    setIsLoading(true);
    try {
      const { error } = await supabase.auth.signInWithPassword({
        email: data.email,
        password: data.password,
      });

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
  };

  return (
    <div className="flex items-center justify-center min-h-screen bg-background p-4">
      <div className="w-full max-w-md bg-card rounded-lg border border-border shadow-sm">
        {/* Header */}
        <div className="flex flex-col items-center p-6 pb-2">
          <BrandIcon className="h-10 w-10 text-primary mb-2" />
          <h1 className="text-2xl font-semibold text-foreground">Entrar</h1>
          {brandSubtitle ? (
            <p className="text-sm text-muted-foreground mt-1">{brandSubtitle}</p>
          ) : (
            <p className="text-sm text-muted-foreground mt-1">
              Acesse sua conta no {brandTitle}
            </p>
          )}
        </div>

        {/* Form */}
        <div className="p-6 pt-4">
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <div className="space-y-2">
              <label htmlFor="login-email" className="text-sm font-medium text-foreground">
                Email
              </label>
              <input
                id="login-email"
                type="email"
                placeholder="seu@email.com"
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                {...register("email")}
              />
              {errors.email && (
                <p className="text-xs text-destructive">{errors.email.message}</p>
              )}
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
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                {...register("password")}
              />
              {errors.password && (
                <p className="text-xs text-destructive">{errors.password.message}</p>
              )}
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

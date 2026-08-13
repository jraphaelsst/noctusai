import { useState, type FormEvent } from "react";
import { Navigate } from "react-router-dom";
import { Camera } from "lucide-react";
import { toast } from "sonner";
import { supabase } from "@/lib/supabase";
import { useAuth } from "@/stores/auth";
import { Button, Field, Input } from "@/components/ui";

export default function Login() {
  const { session, loading } = useAuth();
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [enviando, setEnviando] = useState(false);

  if (session && !loading) return <Navigate to="/" replace />;

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setEnviando(true);
    const { error } = await supabase.auth.signInWithPassword({ email, password: senha });
    setEnviando(false);
    if (error) toast.error("Email ou senha inválidos");
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-4">
      <div className="w-full max-w-sm rounded-xl border border-border bg-card p-8 shadow-sm">
        <div className="mb-6 flex flex-col items-center gap-2 text-center">
          <span className="flex h-12 w-12 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <Camera className="h-6 w-6" />
          </span>
          <h1 className="font-display text-xl">P Studio</h1>
          <p className="text-sm text-muted-foreground">
            Gestão da produtora — entre para continuar
          </p>
        </div>

        <form onSubmit={onSubmit} className="space-y-4">
          <Field label="Email">
            <Input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="voce@pstudio.app"
              required
              autoFocus
            />
          </Field>
          <Field label="Senha">
            <Input
              type="password"
              value={senha}
              onChange={(e) => setSenha(e.target.value)}
              placeholder="••••••••"
              required
            />
          </Field>
          <Button type="submit" className="w-full" loading={enviando}>
            Entrar
          </Button>
        </form>
      </div>
    </div>
  );
}

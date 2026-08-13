import { Navigate } from "react-router-dom";
import { useAuth } from "@/stores/auth";
import { Button, Spinner } from "@/components/ui";
import AppLayout from "@/components/AppLayout";

/**
 * Exige sessão + perfil carregado e então renderiza o layout com `<Outlet/>`.
 * O protótipo não tinha guarda nenhuma — visitante anônimo chegava em todas as
 * telas. Aqui a rota é fechada de verdade.
 */
export function Protected() {
  const { session, me, loading, error, signOut } = useAuth();

  if (loading) return <Spinner className="min-h-screen" />;
  if (!session) return <Navigate to="/login" replace />;
  if (error || !me)
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-3 p-6 text-center">
        <p className="text-sm text-foreground">{error ?? "Não foi possível carregar seu perfil."}</p>
        <p className="text-xs text-muted-foreground">
          Verifique se o backend está rodando (porta 8020).
        </p>
        <Button variant="outline" onClick={signOut}>
          Sair
        </Button>
      </div>
    );
  return <AppLayout />;
}

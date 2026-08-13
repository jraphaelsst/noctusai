/**
 * InstagramCardSection — connect + manage Instagram-Login accounts.
 *
 * This is the FE half of roadmap `ig-login-messaging-migration-2026-07` S2/S4.
 * The backend has had all three endpoints since 2026-07-21
 * (`/accounts/instagram/oauth/{start,callback}` + `/accounts/instagram/token`)
 * and the hooks existed too — but nothing rendered them, so
 * `useSubmitInstagramToken` sat with ZERO consumers and there was no way for an
 * operator to connect an account at all. Route-exists ≠ wired, at the hook layer.
 *
 * 🔴 Instagram-Login is a DISTINCT provider from `meta`, not a sub-case of it:
 * its own Instagram App ID/Secret (NOT the Facebook App ID — sending that one
 * yields Instagram's "Esta página não está disponível"), its own token chain
 * through api.instagram.com → graph.instagram.com, and it needs no Facebook
 * Page. Accounts land as `provider="instagram"`, which is exactly what the DM
 * gateway routes on.
 *
 * Two ways in, because live OAuth depends on the operator's Instagram app being
 * configured:
 *   1. "Conectar Instagram" → Business Login consent in a new tab.
 *   2. Token paste → for an IG User access token obtained by hand. The backend
 *      validates it via `/me` before storing, so a bad paste fails loudly.
 *
 * Reuses the generic `useStartProviderOAuth("instagram")` rather than adding an
 * Instagram-specific start hook — the endpoint follows the shared
 * `/accounts/{provider}/oauth/start` contract.
 */
import { useState } from "react";
import { Instagram, Key, Link2, Loader2, Plus } from "lucide-react";
import { toast } from "sonner";

import {
  IntegrationCard,
  IntegrationCardModal,
  type IntegrationAccount as LibIntegrationAccount,
} from "@noctusai/lib";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  useIntegrationAccounts,
  useDeleteAccount,
  useStartProviderOAuth,
  useSubmitInstagramToken,
  type IntegrationAccount,
} from "@/hooks/useIntegrationAccounts";
import type { Marca } from "@/hooks/useMarcas";

const INSTAGRAM_PROVIDER = "instagram";

function toLibAccount(acc: IntegrationAccount): LibIntegrationAccount {
  return acc as unknown as LibIntegrationAccount;
}

export function InstagramCardSection({ marcas }: { marcas: Marca[] }) {
  const [oauthMarcaId, setOauthMarcaId] = useState<string>("");
  const [showTokenPaste, setShowTokenPaste] = useState(false);
  const [pastedToken, setPastedToken] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [modalAccount, setModalAccount] = useState<IntegrationAccount | null>(
    null,
  );

  const {
    data: accounts = [],
    isPending,
    isFetching,
    isError,
  } = useIntegrationAccounts(INSTAGRAM_PROVIDER);
  const oauthStart = useStartProviderOAuth(INSTAGRAM_PROVIDER);
  const submitToken = useSubmitInstagramToken();
  const deleteAccount = useDeleteAccount();

  // `isPending || isFetching`, never `isLoading` — v5's isLoading is FALSE
  // during a background refetch, which would drop us into the empty branch
  // over live accounts (KB § PATTERNS/frontend/lying-loading-state.md).
  const loading = isPending || isFetching;

  function handleConnect() {
    oauthStart.mutate(oauthMarcaId ? { marcaId: oauthMarcaId } : undefined, {
      onError: (e: any) =>
        toast.error("Falha ao iniciar conexão com o Instagram", {
          // A 503 here means the Instagram App ID/Secret aren't configured —
          // surface the backend's actionable message rather than a generic one.
          description: e?.message ?? "Tente novamente",
        }),
    });
  }

  function handleSubmitToken() {
    const token = pastedToken.trim();
    if (!token) return;
    submitToken.mutate(
      { access_token: token, marca_id: oauthMarcaId || null },
      {
        onSuccess: () => {
          toast.success("Conta do Instagram conectada");
          setPastedToken("");
          setShowTokenPaste(false);
        },
        onError: (e: any) =>
          toast.error("Token inválido", {
            description:
              e?.message ??
              "Use um Instagram User access token — o “Token de Cliente” do app não serve.",
          }),
      },
    );
  }

  async function handleDelete(account: LibIntegrationAccount) {
    setBusyId(account.id);
    try {
      await deleteAccount.mutateAsync(account.id);
      toast.success("Conta removida");
    } catch (err: any) {
      toast.error("Erro ao remover conta", { description: err?.message });
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="space-y-4">
      {/* Section header + connect affordances */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2">
          <Instagram className="h-5 w-5 text-muted-foreground" />
          <h2 className="text-lg font-semibold">Instagram</h2>
        </div>

        {marcas.length > 0 && (
          <select
            value={oauthMarcaId}
            onChange={(e) => setOauthMarcaId(e.target.value)}
            className="h-8 rounded-md border border-input bg-background px-2.5 text-xs"
            aria-label="Atribuir a marca ao conectar"
          >
            <option value="">Sem marca</option>
            {marcas.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        )}

        <div className="ml-auto flex items-center gap-2">
          <Button
            size="sm"
            variant="ghost"
            onClick={() => setShowTokenPaste((v) => !v)}
            aria-expanded={showTokenPaste}
          >
            <Key className="mr-1.5 h-3.5 w-3.5" />
            Colar token
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={handleConnect}
            disabled={oauthStart.isPending}
          >
            {oauthStart.isPending ? (
              <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
            ) : (
              <Link2 className="mr-1.5 h-3.5 w-3.5" />
            )}
            Conectar Instagram
          </Button>
        </div>
      </div>

      <p className="text-xs text-muted-foreground">
        Mensagens diretas do Instagram. Requer uma conta profissional
        (Business/Creator) — nenhuma página do Facebook é necessária neste
        modelo.
      </p>

      {/* Manual token fallback */}
      {showTokenPaste && (
        <div className="space-y-2 rounded-md border bg-muted/20 p-3">
          <label
            htmlFor="ig-token"
            className="text-xs font-medium text-muted-foreground"
          >
            Instagram User access token
          </label>
          <div className="flex flex-wrap gap-2">
            <Input
              id="ig-token"
              type="password"
              value={pastedToken}
              onChange={(e) => setPastedToken(e.target.value)}
              placeholder="IGQ..."
              className="h-8 flex-1 text-xs"
              autoComplete="off"
            />
            <Button
              size="sm"
              onClick={handleSubmitToken}
              disabled={!pastedToken.trim() || submitToken.isPending}
            >
              {submitToken.isPending && (
                <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
              )}
              Salvar
            </Button>
          </div>
          <p className="text-[11px] text-muted-foreground">
            Não use o &ldquo;Token de Cliente&rdquo; do app — ele não lê
            mensagens. O token é validado antes de ser salvo.
          </p>
        </div>
      )}

      {loading && (
        <div className="flex items-center gap-2 py-4 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Carregando contas do Instagram...
        </div>
      )}

      {!loading && isError && (
        <p className="py-4 text-sm text-destructive">
          Erro ao carregar contas. Tente recarregar a página.
        </p>
      )}

      {!loading && !isError && accounts.length === 0 && (
        <div className="rounded-md border border-dashed bg-muted/20 py-8 text-center">
          <Plus className="mx-auto mb-2 h-6 w-6 text-muted-foreground" />
          <p className="text-sm text-muted-foreground">
            Nenhuma conta do Instagram conectada.
            <br />
            Use &ldquo;Conectar Instagram&rdquo; para autorizar uma conta.
          </p>
        </div>
      )}

      {!loading && !isError && accounts.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {accounts.map((acc) => (
            <IntegrationCard
              key={acc.id}
              account={toLibAccount(acc)}
              busy={busyId === acc.id}
              onDelete={handleDelete}
              onOpenModal={() => setModalAccount(acc)}
            />
          ))}
        </div>
      )}

      <IntegrationCardModal
        account={modalAccount ? toLibAccount(modalAccount) : null}
        onClose={() => setModalAccount(null)}
        className="sm:max-w-2xl"
      />
    </div>
  );
}

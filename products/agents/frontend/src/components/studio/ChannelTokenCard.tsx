/**
 * Canal token card (Lais §4): mint a `pk_*` for Social Wiring, show it ONCE
 * in a copy box, list the org's channel tokens (non-secret rows from the seed
 * `GET /api/settings/api-tokens`, filtered to this agent's label) and revoke.
 * The raw secret lives only in the dialog's local state — it is dropped on
 * close and never logged, cached or put in the URL.
 */
import { useState } from "react";
import { format } from "date-fns";
import { ptBR } from "date-fns/locale";
import { KeyRound, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Badge, Button, Dialog, DialogBody, DialogFooter, DialogHeader, EmptyState } from "@noctusai/lib/design-system";
import { CopyTextButton } from "@/components/studio/CopyTextButton";
import { StudioError, StudioLoading } from "@/components/studio/StudioStates";
import {
  useChannelTokens,
  useMintChannelToken,
  useRevokeChannelToken,
  type ChannelTokenMinted,
} from "@/hooks/useChannel";
import { errorMessage } from "@/lib/errors";

const INPUT_CLASS =
  "w-full h-9 rounded-md border border-input bg-background px-3 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50";

function fmt(value: string | null): string {
  return value ? format(new Date(value), "dd/MM/yyyy HH:mm", { locale: ptBR }) : "—";
}

function MintDialog({ agentKey, onClose }: { agentKey: string; onClose: () => void }) {
  const mint = useMintChannelToken(agentKey);
  const [label, setLabel] = useState("producao");
  // Held ONLY here; unmounting the dialog discards it.
  const [minted, setMinted] = useState<ChannelTokenMinted | null>(null);

  async function handleMint() {
    try {
      setMinted(await mint.mutateAsync({ label: label.trim() }));
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  return (
    <Dialog open onClose={onClose} title="Novo token de canal">
      <DialogHeader>
        <h2 className="text-lg font-semibold text-foreground">Novo token de canal</h2>
      </DialogHeader>
      <DialogBody>
        {minted ? (
          <div className="space-y-3" data-testid="channel-token-reveal">
            <p className="text-sm font-medium text-destructive">Copie agora — não será mostrado de novo.</p>
            <div className="flex items-center gap-2">
              <code className="min-w-0 flex-1 break-all rounded-md border border-border bg-muted p-2 text-xs" data-testid="channel-token-value">
                {minted.token}
              </code>
              <CopyTextButton text={minted.token} />
            </div>
            <p className="text-xs text-muted-foreground">
              Cole em <strong>Social Wiring › Lais › Agente</strong>. Expira em {fmt(minted.expires_at)}.
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            <label htmlFor="channel-token-label" className="block text-xs font-medium">
              Identificação do token
            </label>
            <input
              id="channel-token-label"
              className={INPUT_CLASS}
              value={label}
              maxLength={120}
              onChange={(e) => setLabel(e.target.value)}
              data-testid="channel-token-label"
            />
            <p className="text-xs text-muted-foreground">
              Emitir um novo token não revoga os anteriores — cole o novo no Social Wiring e depois revogue o antigo.
            </p>
          </div>
        )}
      </DialogBody>
      <DialogFooter>
        {minted ? (
          <Button onClick={onClose} data-testid="channel-token-close">
            Fechar
          </Button>
        ) : (
          <>
            <Button variant="ghost" onClick={onClose}>
              Cancelar
            </Button>
            <Button onClick={handleMint} disabled={!label.trim() || mint.isPending} data-testid="channel-token-mint">
              {mint.isPending ? "Emitindo..." : "Emitir token"}
            </Button>
          </>
        )}
      </DialogFooter>
    </Dialog>
  );
}

export function ChannelTokenCard({ agentKey, isAdmin }: { agentKey: string; isAdmin: boolean }) {
  const tokens = useChannelTokens(agentKey);
  const revoke = useRevokeChannelToken(agentKey);
  const [minting, setMinting] = useState(false);
  const [toRevoke, setToRevoke] = useState<string | null>(null);

  async function confirmRevoke() {
    if (!toRevoke) return;
    try {
      await revoke.mutateAsync(toRevoke);
      toast.success("Token revogado.");
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setToRevoke(null);
    }
  }

  const active = (tokens.data ?? []).filter((t) => !t.revoked_at);

  return (
    <section className="space-y-3 rounded-lg border border-border bg-card p-4" data-testid="channel-token-card">
      <div className="flex items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 text-sm font-semibold">
          <KeyRound className="h-4 w-4 text-primary" /> Token do canal (Social Wiring)
          {tokens.isRefreshing && <span className="text-xs font-normal text-muted-foreground">Atualizando…</span>}
        </h2>
        {isAdmin && (
          <Button size="sm" variant="primary" onClick={() => setMinting(true)} data-testid="channel-token-new">
            <Plus className="mr-1 h-3.5 w-3.5" /> Novo token
          </Button>
        )}
      </div>

      {tokens.showSkeleton ? (
        <StudioLoading rows={2} testId="channel-tokens-skeleton" />
      ) : tokens.isError ? (
        <StudioError error={tokens.error} onRetry={tokens.refetch} />
      ) : active.length === 0 ? (
        <EmptyState message="Nenhum token de canal ativo. Emita um e cole no Social Wiring." />
      ) : (
        <ul className="divide-y divide-border" data-testid="channel-token-list">
          {active.map((t) => (
            <li key={t.id} className="flex items-center justify-between gap-3 py-2 text-sm">
              <div className="min-w-0">
                <p className="truncate">{t.label}</p>
                <p className="text-xs text-muted-foreground">
                  <span className="font-mono">{t.prefix}…</span> · criado em {fmt(t.created_at)} · último uso{" "}
                  {fmt(t.last_used_at)}
                </p>
              </div>
              {isAdmin && (
                <Button size="sm" variant="outline" onClick={() => setToRevoke(t.id)} data-testid={`channel-token-revoke-${t.id}`}>
                  <Trash2 className="mr-1 h-3.5 w-3.5" /> Revogar
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}

      {minting && <MintDialog agentKey={agentKey} onClose={() => setMinting(false)} />}
      {toRevoke && (
        <Dialog open onClose={() => setToRevoke(null)} title="Revogar token">
          <DialogHeader>
            <h2 className="text-lg font-semibold text-foreground">Revogar token?</h2>
            <p className="text-sm text-muted-foreground">
              O Social Wiring deixa de conseguir falar com o agente com este token. Não dá para desfazer.
            </p>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setToRevoke(null)}>
              Cancelar
            </Button>
            <Button variant="destructive" onClick={confirmRevoke} disabled={revoke.isPending} data-testid="channel-token-revoke-confirm">
              Revogar
            </Button>
          </DialogFooter>
        </Dialog>
      )}
    </section>
  );
}

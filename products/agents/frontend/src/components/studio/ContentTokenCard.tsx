/**
 * "Token de conteúdo (MCP)" — platform-admin section of the Studio home. Mints the `studio:content-write`
 * token the `noctus.agents.content` MCP tool uses to edit DRAFTS of the platform's agents, with an expiry
 * chosen in days (1..365) or "never", lists the platform org's tokens (never the secret) and revokes them.
 * The raw secret lives only in the dialog's local state: dropped on close, never logged/cached/put in a URL.
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
  useContentTokens,
  useMintContentToken,
  useRevokeContentToken,
  type ContentTokenMinted,
  type ContentTokenRow,
} from "@/hooks/studio/useContentToken";
import { errorMessage } from "@/lib/errors";

const INPUT_CLASS =
  "w-full h-9 rounded-md border border-input bg-background px-3 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50";

export const CONTENT_TOKEN_DEFAULT_DAYS = 30;
export const CONTENT_TOKEN_MAX_DAYS = 365;

function fmt(value: string | null): string {
  return value ? format(new Date(value), "dd/MM/yyyy HH:mm", { locale: ptBR }) : "—";
}

const STATUS_LABEL: Record<ContentTokenRow["status"], string> = { ativo: "Ativo", expirado: "Expirado", revogado: "Revogado" };

function MintDialog({ onClose }: { onClose: () => void }) {
  const mint = useMintContentToken();
  const [label, setLabel] = useState("");
  const [nunca, setNunca] = useState(false);
  const [dias, setDias] = useState(String(CONTENT_TOKEN_DEFAULT_DAYS));
  const [permitirExclusao, setPermitirExclusao] = useState(false);
  // Held ONLY here; unmounting the dialog discards it.
  const [minted, setMinted] = useState<ContentTokenMinted | null>(null);

  const diasNum = Number(dias);
  const diasOk = Number.isInteger(diasNum) && diasNum >= 1 && diasNum <= CONTENT_TOKEN_MAX_DAYS;
  const canSubmit = label.trim().length > 0 && (nunca || diasOk) && !mint.isPending;

  async function handleMint() {
    try {
      setMinted(await mint.mutateAsync({ label: label.trim(), expira_em_dias: nunca ? null : diasNum,
        ...(permitirExclusao ? { permitir_exclusao: true } : {}),
      }));
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  return (
    <Dialog open onClose={onClose} title="Novo token de conteúdo">
      <DialogHeader>
        <h2 className="text-lg font-semibold text-foreground">Novo token de conteúdo</h2>
      </DialogHeader>
      <DialogBody>
        {minted ? (
          <div className="space-y-3" data-testid="content-token-reveal">
            <p className="text-sm font-medium text-destructive">Copie agora — não será mostrado de novo.</p>
            <div className="flex items-center gap-2">
              <code className="min-w-0 flex-1 break-all rounded-md border border-border bg-muted p-2 text-xs" data-testid="content-token-value">
                {minted.token}
              </code>
              <CopyTextButton text={minted.token} />
            </div>
            <p className="text-xs text-muted-foreground">
              Guarde em <code className="font-mono">NOCTUS_AGENTS_CONTENT_TOKEN=</code> no arquivo{" "}
              <code className="font-mono">~/.config/noctus/agents.env</code>.{" "}
              {minted.expires_at ? `Expira em ${fmt(minted.expires_at)}.` : "Não expira — vale até ser revogado."}
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="space-y-1">
              <label htmlFor="content-token-label" className="block text-xs font-medium">
                Identificação do token *
              </label>
              <input
                id="content-token-label"
                className={INPUT_CLASS}
                value={label}
                maxLength={120}
                placeholder="ex.: notebook do Raphael"
                onChange={(e) => setLabel(e.target.value)}
                data-testid="content-token-label"
              />
            </div>
            <fieldset className="space-y-2">
              <legend className="mb-1 block text-xs font-medium">Validade</legend>
              <label className="flex items-center gap-2 text-sm">
                <input type="radio" name="content-token-validade" checked={!nunca} onChange={() => setNunca(false)} data-testid="content-token-modo-dias" />
                Expira em
                <input
                  type="number"
                  aria-label="Dias de validade"
                  className="h-8 w-20 rounded-md border border-input bg-background px-2 text-sm"
                  min={1}
                  max={CONTENT_TOKEN_MAX_DAYS}
                  step={1}
                  value={dias}
                  disabled={nunca}
                  onChange={(e) => setDias(e.target.value)}
                  data-testid="content-token-dias"
                />
                dias
              </label>
              {!nunca && !diasOk && (
                <p className="text-xs text-destructive" data-testid="content-token-dias-erro">
                  Informe um número inteiro de 1 a {CONTENT_TOKEN_MAX_DAYS} dias.
                </p>
              )}
              <label className="flex items-center gap-2 text-sm">
                <input type="radio" name="content-token-validade" checked={nunca} onChange={() => setNunca(true)} data-testid="content-token-modo-nunca" />
                Nunca expira
              </label>
              {nunca && (
                <p className="rounded-md border border-destructive/40 bg-destructive/5 p-2 text-xs text-destructive" data-testid="content-token-nunca-aviso">
                  Atenção: um token de escrita que nunca expira continua válido até ser revogado. Se vazar, qualquer pessoa
                  com ele edita os rascunhos dos agentes da plataforma. Revogue-o aqui assim que não precisar mais.
                </p>
              )}
            </fieldset>
            <label className="flex items-start gap-2 text-sm">
              <input
                type="checkbox"
                checked={permitirExclusao}
                onChange={(e) => setPermitirExclusao(e.target.checked)}
                data-testid="content-token-permitir-exclusao"
              />
              <span>
                Permitir excluir agentes
                <span className="block text-xs text-muted-foreground">
                  Além de editar rascunhos, o token poderá excluir agentes (só os que o servidor permitir: sem versão publicada,
                  conversas, instâncias ou canal).
                </span>
              </span>
            </label>
          </div>
        )}
      </DialogBody>
      <DialogFooter>
        {minted ? (
          <Button onClick={onClose} data-testid="content-token-close">
            Fechar
          </Button>
        ) : (
          <>
            <Button variant="ghost" onClick={onClose}>
              Cancelar
            </Button>
            <Button onClick={handleMint} disabled={!canSubmit} data-testid="content-token-mint">
              {mint.isPending ? "Emitindo..." : "Gerar token"}
            </Button>
          </>
        )}
      </DialogFooter>
    </Dialog>
  );
}

export function ContentTokenCard() {
  const tokens = useContentTokens();
  const revoke = useRevokeContentToken();
  const [minting, setMinting] = useState(false);
  const [toRevoke, setToRevoke] = useState<ContentTokenRow | null>(null);

  async function confirmRevoke() {
    if (!toRevoke) return;
    try {
      await revoke.mutateAsync(toRevoke.id);
      toast.success("Token revogado.");
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setToRevoke(null);
    }
  }

  const rows = tokens.data?.itens ?? [];

  return (
    <section className="space-y-3 rounded-lg border border-border bg-card p-4" data-testid="content-token-card">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h2 className="flex items-center gap-2 text-sm font-semibold">
            <KeyRound className="h-4 w-4 text-primary" /> Token de conteúdo (MCP)
            {tokens.isRefreshing && <span className="text-xs font-normal text-muted-foreground">Atualizando…</span>}
          </h2>
          <p className="mt-1 max-w-3xl text-xs text-muted-foreground">
            Permite que a ferramenta <code className="font-mono">noctus.agents.content</code> edite os <strong>rascunhos</strong> dos
            agentes da plataforma (textos, seções, ferramentas, decisões, especificações, skills, padrão de qualificação, evals e regras de
            conformidade). Ele nunca publica uma versão e nunca conversa com leads.
          </p>
        </div>
        <Button size="sm" variant="primary" onClick={() => setMinting(true)} data-testid="content-token-new">
          <Plus className="mr-1 h-3.5 w-3.5" /> Gerar token
        </Button>
      </div>

      {tokens.showSkeleton ? (
        <StudioLoading rows={2} testId="content-tokens-skeleton" />
      ) : tokens.isError ? (
        <StudioError error={tokens.error} onRetry={tokens.refetch} />
      ) : rows.length === 0 ? (
        <EmptyState message="Nenhum token de conteúdo emitido. Gere um para usar a ferramenta noctus.agents.content." />
      ) : (
        <ul className="divide-y divide-border" data-testid="content-token-list">
          {rows.map((t) => (
            <li key={t.id} className="flex items-center justify-between gap-3 py-2 text-sm" data-testid={`content-token-row-${t.id}`}>
              <div className="min-w-0">
                <p className="flex items-center gap-2 truncate">
                  {t.label}
                  <Badge variant={t.status === "ativo" ? "default" : "muted"} data-testid={`content-token-status-${t.id}`}>
                    {STATUS_LABEL[t.status]}
                  </Badge>
                  {t.scopes?.includes("studio:agent-delete") && (
                    <Badge variant="outline" data-testid={`content-token-exclusao-${t.id}`}>
                      Pode excluir agentes
                    </Badge>
                  )}
                </p>
                <p className="text-xs text-muted-foreground">
                  <span className="font-mono">{t.prefix}…</span> · criado em {fmt(t.created_at)}
                  {t.created_by ? <> por <span className="font-mono">{t.created_by.slice(0, 8)}</span></> : null} · expira:{" "}
                  <span data-testid={`content-token-expira-${t.id}`}>{t.expires_at ? fmt(t.expires_at) : "Nunca"}</span> · último uso{" "}
                  {fmt(t.last_used_at)}
                </p>
              </div>
              {t.status !== "revogado" && (
                <Button size="sm" variant="outline" onClick={() => setToRevoke(t)} data-testid={`content-token-revoke-${t.id}`}>
                  <Trash2 className="mr-1 h-3.5 w-3.5" /> Revogar
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}

      {minting && <MintDialog onClose={() => setMinting(false)} />}
      {toRevoke && (
        <Dialog open onClose={() => setToRevoke(null)} title="Revogar token">
          <DialogHeader>
            <h2 className="text-lg font-semibold text-foreground">Revogar “{toRevoke.label}”?</h2>
            <p className="text-sm text-muted-foreground">
              A ferramenta noctus.agents.content deixa de conseguir editar rascunhos com este token. Não dá para desfazer.
            </p>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setToRevoke(null)}>
              Cancelar
            </Button>
            <Button variant="destructive" onClick={confirmRevoke} disabled={revoke.isPending} data-testid="content-token-revoke-confirm">
              {revoke.isPending ? "Revogando..." : "Revogar"}
            </Button>
          </DialogFooter>
        </Dialog>
      )}
    </section>
  );
}

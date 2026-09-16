/**
 * Credenciais e integrações — `/credenciais` (platform admin only,
 * server-enforced by `require_platform_admin`).
 *
 * One card per credential the agents control plane holds: status, prefix
 * or fingerprint (never the secret), source (banco / ambiente), expiry,
 * days left, last use, plus the actions each kind supports — Testar (live
 * call), Renovar (product tokens: mint → verify → store → revoke old),
 * Definir (write-only input), Importar do ambiente (one-time migration),
 * and rotation of the §D approval keys.
 */
import { useState, type FormEvent } from "react";
import { format, formatDistanceToNow } from "date-fns";
import { ptBR } from "date-fns/locale";
import { AlertTriangle, KeyRound, RefreshCw, ShieldAlert, ShieldCheck } from "lucide-react";
import { toast } from "sonner";
import {
  Badge,
  Button,
  Dialog,
  DialogBody,
  DialogFooter,
  DialogHeader,
} from "@noctusai/lib/design-system";
import {
  useCredentials,
  useImportCredential,
  useProbeCredential,
  useRenewCredential,
  useRingAction,
  useSetCredential,
  type Credential,
  type ProbeResult,
  type RingKey,
} from "@/hooks/useCredentials";
import { ApiError, errorMessage } from "@/lib/errors";

const INPUT_CLASS =
  "w-full h-9 rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50";

const SEVERITY_BADGE: Record<Credential["severity"], { label: string; variant: "default" | "destructive" | "muted" }> = {
  info: { label: "OK", variant: "default" },
  warning: { label: "Atenção", variant: "muted" },
  critical: { label: "Ação necessária", variant: "destructive" },
};

const RING_STATE: Record<RingKey["state"], string> = {
  staged: "aguardando ativação",
  active: "ativa",
  retiring: "em retirada",
  retired: "retirada",
};

function fmtDate(value: string | null): string {
  if (!value) return "—";
  return format(new Date(value), "dd/MM/yyyy HH:mm", { locale: ptBR });
}

function fmtRelative(value: string | null): string {
  if (!value) return "nunca";
  return formatDistanceToNow(new Date(value), { addSuffix: true, locale: ptBR });
}

function isForbidden(err: unknown): boolean {
  return err instanceof ApiError && err.status === 403;
}

function SetValueDialog({ credential, onClose }: { credential: Credential; onClose: () => void }) {
  const setCredential = useSetCredential();
  const [value, setValue] = useState("");

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    try {
      await setCredential.mutateAsync({ name: credential.name, value });
      toast.success("Credencial salva.");
      setValue("");
      onClose();
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  const secret = credential.kind !== "config";
  return (
    <Dialog open onClose={onClose} title={`Definir ${credential.label}`}>
      <form onSubmit={handleSubmit}>
        <DialogHeader>
          <h2 className="text-lg font-semibold text-foreground">{credential.label}</h2>
          <p className="text-sm text-muted-foreground">
            {secret
              ? "O valor é enviado uma única vez e nunca é exibido de volta."
              : "Identificador não secreto."}
          </p>
        </DialogHeader>
        <DialogBody>
          <input
            className={INPUT_CLASS}
            type={secret ? "password" : "text"}
            autoComplete="off"
            spellCheck={false}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder={credential.kind === "api_key" ? "sk-ant-…" : credential.kind === "product_token" ? "pk_…" : "UUID"}
            data-testid="credential-value-input"
          />
        </DialogBody>
        <DialogFooter>
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit" disabled={!value.trim() || setCredential.isPending}>
            Salvar
          </Button>
        </DialogFooter>
      </form>
    </Dialog>
  );
}

function RingKeys({ ring }: { ring: RingKey[] }) {
  if (ring.length === 0) return null;
  return (
    <ul className="space-y-1 text-xs" data-testid="ring-keys">
      {ring.map((key) => (
        <li key={key.fingerprint} className="flex flex-wrap items-center gap-2">
          <code className="rounded bg-muted px-1.5 py-0.5">{key.fingerprint}</code>
          <span className="text-muted-foreground">{RING_STATE[key.state]}</span>
          {key.signing && <Badge variant="default">assinando</Badge>}
          {key.state === "staged" && <span className="text-muted-foreground">desde {fmtDate(key.active_from)}</span>}
          {key.retire_at && key.state !== "retired" && (
            <span className="text-muted-foreground">retira em {fmtDate(key.retire_at)}</span>
          )}
        </li>
      ))}
    </ul>
  );
}

function CredentialCard({ credential }: { credential: Credential }) {
  const probe = useProbeCredential();
  const renew = useRenewCredential();
  const importEnv = useImportCredential();
  const ringAction = useRingAction();
  const [lastProbe, setLastProbe] = useState<ProbeResult | null>(null);
  const [editing, setEditing] = useState(false);

  const badge = SEVERITY_BADGE[credential.severity];
  const busy = probe.isPending || renew.isPending || importEnv.isPending || ringAction.isPending;
  const canSet = credential.kind !== "key_ring" && credential.writable;

  async function run<T>(action: () => Promise<T>, success: (result: T) => void) {
    try {
      success(await action());
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  return (
    <div className="space-y-3 rounded-lg border border-border bg-card p-4" data-testid={`credential-${credential.name}`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <KeyRound className="h-4 w-4 text-primary" />
            <p className="text-sm font-semibold text-foreground">{credential.label}</p>
            <Badge variant={badge.variant} data-testid={`credential-severity-${credential.name}`}>
              {badge.label}
            </Badge>
            <Badge variant="outline">
              {credential.source === "db" ? "banco" : credential.source === "env" ? "ambiente" : "não definida"}
            </Badge>
          </div>
          <p className="mt-0.5 text-xs text-muted-foreground">{credential.env_var}</p>
        </div>
      </div>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs sm:grid-cols-4">
        {credential.kind === "config" ? (
          <div className="col-span-2">
            <dt className="text-muted-foreground">Valor</dt>
            <dd className="font-mono text-foreground">{credential.value ?? "—"}</dd>
          </div>
        ) : (
          <div>
            <dt className="text-muted-foreground">{credential.kind === "key_ring" ? "Chave de assinatura" : "Prefixo"}</dt>
            <dd className="font-mono text-foreground" data-testid={`credential-prefix-${credential.name}`}>
              {credential.prefix ?? credential.fingerprint ?? "—"}
            </dd>
          </div>
        )}
        {credential.kind === "product_token" && (
          <>
            <div>
              <dt className="text-muted-foreground">Expira em</dt>
              <dd className="text-foreground">{fmtDate(credential.expires_at)}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Dias restantes</dt>
              <dd className="text-foreground" data-testid={`credential-days-${credential.name}`}>
                {credential.days_left ?? "—"}
              </dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Último uso</dt>
              <dd className="text-foreground">{fmtRelative(credential.last_used_at)}</dd>
            </div>
          </>
        )}
      </dl>

      {credential.kind === "key_ring" && <RingKeys ring={credential.ring} />}

      {credential.warnings.length > 0 && (
        <ul className="space-y-0.5 text-xs text-amber-600" data-testid={`credential-warnings-${credential.name}`}>
          {credential.warnings.map((w) => (
            <li key={w} className="flex items-start gap-1">
              <AlertTriangle className="mt-0.5 h-3 w-3 flex-shrink-0" />
              {w}
            </li>
          ))}
        </ul>
      )}

      {lastProbe && (
        <p
          className={`text-xs ${lastProbe.ok ? "text-success" : "text-destructive"}`}
          data-testid={`credential-probe-${credential.name}`}
        >
          {lastProbe.ok ? "OK" : lastProbe.http_status ?? "Falha"} — {lastProbe.detail}
        </p>
      )}

      <div className="flex flex-wrap gap-2">
        {credential.probeable && credential.configured && (
          <Button
            size="sm"
            variant="outline"
            disabled={busy}
            onClick={() => run(() => probe.mutateAsync({ name: credential.name }), setLastProbe)}
          >
            Testar
          </Button>
        )}
        {credential.renewable && (
          <Button
            size="sm"
            disabled={busy || !credential.writable}
            onClick={() =>
              run(
                () => renew.mutateAsync({ name: credential.name }),
                (result) => {
                  setLastProbe(null);
                  toast.success("Token renovado e verificado.");
                  result.warnings.forEach((w) => toast.warning(w));
                },
              )
            }
            data-testid={`credential-renew-${credential.name}`}
          >
            <RefreshCw className="mr-1 h-3.5 w-3.5" />
            Renovar
          </Button>
        )}
        {canSet && (
          <Button size="sm" variant="outline" disabled={busy} onClick={() => setEditing(true)}>
            {credential.configured ? "Substituir" : "Definir"}
          </Button>
        )}
        {credential.source === "env" && credential.writable && (
          <Button
            size="sm"
            variant="ghost"
            disabled={busy}
            onClick={() =>
              run(() => importEnv.mutateAsync({ name: credential.name }), () =>
                toast.success("Valor do ambiente salvo no banco (criptografado)."),
              )
            }
          >
            Importar do ambiente
          </Button>
        )}
        {credential.kind === "key_ring" && credential.source === "db" && credential.writable && (
          <>
            <Button
              size="sm"
              disabled={busy}
              onClick={() =>
                run(() => ringAction.mutateAsync({ action: "rotate" }), () =>
                  toast.success("Nova chave preparada — a Julia passa a assinar com ela após a ativação."),
                )
              }
              data-testid="ring-rotate"
            >
              Rotacionar chave
            </Button>
            <Button
              size="sm"
              variant="ghost"
              disabled={busy}
              onClick={() =>
                run(() => ringAction.mutateAsync({ action: "prune" }), () => toast.success("Chaves retiradas removidas."))
              }
            >
              Remover chaves retiradas
            </Button>
          </>
        )}
      </div>

      {editing && <SetValueDialog credential={credential} onClose={() => setEditing(false)} />}
    </div>
  );
}

function CardSkeleton() {
  return (
    <div className="space-y-2 rounded-lg border border-border bg-card p-4">
      <div className="h-4 w-48 animate-pulse rounded bg-muted" />
      <div className="h-3 w-72 animate-pulse rounded bg-muted" />
    </div>
  );
}

export default function Credenciais() {
  const { data, error, showSkeleton, isError } = useCredentials();

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <ShieldCheck className="h-6 w-6 text-primary" />
        <div>
          <h1 className="text-2xl font-bold text-foreground">Credenciais e integrações</h1>
          <p className="text-sm text-muted-foreground">
            Tokens e chaves que a Julia usa para falar com outros produtos. Os valores nunca são exibidos.
          </p>
        </div>
      </div>

      {showSkeleton ? (
        <div className="space-y-3" data-testid="credentials-skeleton">
          <CardSkeleton />
          <CardSkeleton />
        </div>
      ) : isError ? (
        <div
          className="flex flex-col items-center gap-2 rounded-lg border border-border bg-card p-8 text-muted-foreground"
          data-testid="credentials-error"
        >
          <ShieldAlert className="h-6 w-6" />
          <p className="text-sm">
            {isForbidden(error)
              ? "Restrito aos administradores da plataforma NoctusAI."
              : errorMessage(error)}
          </p>
        </div>
      ) : data ? (
        <>
          {data.alerts > 0 && (
            <div
              className="flex items-center gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-700"
              data-testid="credentials-alert-banner"
            >
              <AlertTriangle className="h-4 w-4" />
              {data.alerts} credencial(is) precisa(m) de atenção.
            </div>
          )}
          <div className="space-y-3" data-testid="credentials-list">
            {data.items.map((credential) => (
              <CredentialCard key={credential.name} credential={credential} />
            ))}
          </div>
        </>
      ) : null}
    </div>
  );
}

/**
 * `<FavorecidoDialog/>` — create / edit one registry favorecido. The ONE form
 * both the Favorecidos page and the card's "Novo favorecido" shortcut open.
 *
 * 🔴 LGPD: this dialog is the only surface that shows a favorecido's CLEAR
 * CPF/CNPJ, bank account and PIX key (it reads the single-record GET). Values
 * live in component state only — never in a URL, a query key, a toast or a log.
 *
 * Edit loads the full record first (skeleton → form, or error + retry); the
 * form body is keyed by record so reopening on another favorecido can never
 * show the previous one's values.
 */
import { useState } from "react";
import { toast } from "sonner";
import { AlertCircle, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  PIX_TIPOS,
  TIPOS_CONTA,
  useCreateFavorecidoRegistro,
  useFavorecido,
  useUpdateFavorecidoRegistro,
  type FavorecidoCompleto,
  type FavorecidoInput,
  type FavorecidoTipoPessoa,
} from "@/hooks/useFavorecidosRegistro";
import { mensagemErroServidor } from "@/lib/erroServidor";
import { formatarDocumento, limparDocumento } from "@/lib/utils";

// Backend `max_length` caps (same as the card's per-negociação favorecido).
const NOME_MAX = 255;
const CPF_CNPJ_MAX = 32;
const BANCO_MAX = 120;
const AGENCIA_MAX = 32;
const CONTA_MAX = 32;
const PIX_MAX = 140;

const NENHUM = "__none__";

interface Draft {
  nome: string;
  tipo_pessoa: FavorecidoTipoPessoa;
  cpf_cnpj: string;
  banco: string;
  agencia: string;
  conta: string;
  tipo_conta: string;
  pix_tipo: string;
  pix: string;
}

function toDraft(f: FavorecidoCompleto | null): Draft {
  return {
    nome: f?.nome ?? "",
    tipo_pessoa: f?.tipo_pessoa ?? "PF",
    cpf_cnpj: f?.cpf_cnpj ? formatarDocumento(f.cpf_cnpj) : "",
    banco: f?.banco ?? "",
    agencia: f?.agencia ?? "",
    conta: f?.conta ?? "",
    tipo_conta: f?.tipo_conta ?? "",
    pix_tipo: f?.pix_tipo ?? "",
    pix: f?.pix ?? "",
  };
}

function toInput(d: Draft): FavorecidoInput {
  const opt = (v: string) => v.trim() || null;
  return {
    nome: d.nome.trim(),
    tipo_pessoa: d.tipo_pessoa,
    cpf_cnpj: d.cpf_cnpj.trim() ? limparDocumento(d.cpf_cnpj) : null,
    banco: opt(d.banco),
    agencia: opt(d.agencia),
    conta: opt(d.conta),
    tipo_conta: opt(d.tipo_conta),
    pix_tipo: opt(d.pix_tipo),
    pix: opt(d.pix),
  };
}

export interface FavorecidoDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** `null` = create. */
  favorecidoId: string | null;
  /** Fired after a successful save with the saved record (create returns the
   *  new id — the card's shortcut uses it to select the result). */
  onSaved?: (f: FavorecidoCompleto) => void;
}

export function FavorecidoDialog({
  open,
  onOpenChange,
  favorecidoId,
  onSaved,
}: FavorecidoDialogProps) {
  const editando = !!favorecidoId;
  const detalhe = useFavorecido(open ? favorecidoId : null);

  // 🔴 Two signals, never `isLoading`. → KB § PATTERNS/frontend/lying-loading-state.md
  const showSkeleton = editando && detalhe.isPending && !detalhe.data;
  const loadFailed = editando && detalhe.isError && !detalhe.data;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="favorecido-dialog">
        <DialogHeader>
          <DialogTitle>
            {editando ? "Editar favorecido" : "Novo favorecido"}
          </DialogTitle>
        </DialogHeader>
        {showSkeleton ? (
          <div
            className="flex items-center gap-2 py-6 text-sm text-muted-foreground"
            data-testid="favorecido-dialog-skeleton"
          >
            <Loader2 className="h-4 w-4 animate-spin" />
            Carregando favorecido…
          </div>
        ) : loadFailed ? (
          <div className="space-y-3 py-4" data-testid="favorecido-dialog-erro-carga">
            <p className="text-sm text-destructive">
              Não foi possível carregar o favorecido.
            </p>
            <Button size="sm" variant="outline" onClick={() => detalhe.refetch()}>
              Tentar novamente
            </Button>
          </div>
        ) : (
          <FavorecidoForm
            key={favorecidoId ?? "novo"}
            inicial={detalhe.data ?? null}
            favorecidoId={favorecidoId}
            onClose={() => onOpenChange(false)}
            onSaved={onSaved}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

function FavorecidoForm({
  inicial,
  favorecidoId,
  onClose,
  onSaved,
}: {
  inicial: FavorecidoCompleto | null;
  favorecidoId: string | null;
  onClose: () => void;
  onSaved?: (f: FavorecidoCompleto) => void;
}) {
  const criar = useCreateFavorecidoRegistro();
  const atualizar = useUpdateFavorecidoRegistro();
  const [draft, setDraft] = useState<Draft>(() => toDraft(inicial));
  const [error, setError] = useState<string | null>(null);
  const saving = criar.isPending || atualizar.isPending;

  const set = <K extends keyof Draft>(k: K, v: Draft[K]) =>
    setDraft((d) => ({ ...d, [k]: v }));

  function submit() {
    setError(null);
    const payload = toInput(draft);
    const onSuccess = (saved: FavorecidoCompleto) => {
      toast.success(favorecidoId ? "Favorecido atualizado." : "Favorecido cadastrado.");
      onClose();
      onSaved?.(saved);
    };
    const onError = (err: unknown) => {
      // Server sentence only — never echo the payload (CPF / bank data).
      const msg = mensagemErroServidor(err, "Não foi possível salvar o favorecido.");
      setError(msg);
    };
    if (favorecidoId) {
      atualizar.mutate({ id: favorecidoId, patch: payload }, { onSuccess, onError });
    } else {
      criar.mutate(payload, { onSuccess, onError });
    }
  }

  return (
    <>
      <div className="space-y-3">
        <div className="space-y-1.5">
          <Label htmlFor="favreg-nome">Nome</Label>
          <Input
            id="favreg-nome"
            value={draft.nome}
            maxLength={NOME_MAX}
            onChange={(e) => set("nome", e.target.value)}
          />
        </div>
        <div className="grid grid-cols-[1fr_2fr] gap-3">
          <div className="space-y-1.5">
            <Label htmlFor="favreg-tipo">Tipo de pessoa</Label>
            <Select
              value={draft.tipo_pessoa}
              onValueChange={(v) => set("tipo_pessoa", v as FavorecidoTipoPessoa)}
            >
              <SelectTrigger id="favreg-tipo">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="PF">Pessoa física</SelectItem>
                <SelectItem value="PJ">Pessoa jurídica</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="favreg-doc">
              {draft.tipo_pessoa === "PJ" ? "CNPJ" : "CPF"}
            </Label>
            <Input
              id="favreg-doc"
              inputMode="text"
              autoComplete="off"
              value={draft.cpf_cnpj}
              maxLength={CPF_CNPJ_MAX}
              onChange={(e) => set("cpf_cnpj", formatarDocumento(e.target.value))}
            />
          </div>
        </div>
        <div className="grid grid-cols-3 gap-3">
          <div className="space-y-1.5">
            <Label htmlFor="favreg-banco">Banco</Label>
            <Input
              id="favreg-banco"
              value={draft.banco}
              maxLength={BANCO_MAX}
              onChange={(e) => set("banco", e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="favreg-agencia">Agência</Label>
            <Input
              id="favreg-agencia"
              autoComplete="off"
              value={draft.agencia}
              maxLength={AGENCIA_MAX}
              onChange={(e) => set("agencia", e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="favreg-conta">Conta</Label>
            <Input
              id="favreg-conta"
              autoComplete="off"
              value={draft.conta}
              maxLength={CONTA_MAX}
              onChange={(e) => set("conta", e.target.value)}
            />
          </div>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="favreg-tipo-conta">Tipo de conta</Label>
          <Select
            value={draft.tipo_conta || NENHUM}
            onValueChange={(v) => set("tipo_conta", v === NENHUM ? "" : v)}
          >
            <SelectTrigger id="favreg-tipo-conta">
              <SelectValue placeholder="Não informado" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NENHUM}>Não informado</SelectItem>
              {TIPOS_CONTA.map((t) => (
                <SelectItem key={t.value} value={t.value}>
                  {t.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="grid grid-cols-[1fr_2fr] gap-3">
          <div className="space-y-1.5">
            <Label htmlFor="favreg-pix-tipo">Tipo da chave PIX</Label>
            <Select
              value={draft.pix_tipo || NENHUM}
              onValueChange={(v) => set("pix_tipo", v === NENHUM ? "" : v)}
            >
              <SelectTrigger id="favreg-pix-tipo">
                <SelectValue placeholder="Sem PIX" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NENHUM}>Sem PIX</SelectItem>
                {PIX_TIPOS.map((t) => (
                  <SelectItem key={t.value} value={t.value}>
                    {t.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="favreg-pix">Chave PIX</Label>
            <Input
              id="favreg-pix"
              autoComplete="off"
              value={draft.pix}
              maxLength={PIX_MAX}
              onChange={(e) => set("pix", e.target.value)}
            />
          </div>
        </div>
        {error && (
          <div
            className="rounded-md border border-destructive/30 bg-destructive/5 p-2.5 text-xs"
            data-testid="favorecido-dialog-erro"
          >
            <p className="flex items-center gap-1.5 text-destructive">
              <AlertCircle className="h-3.5 w-3.5 shrink-0" />
              {error}
            </p>
          </div>
        )}
      </div>
      <DialogFooter>
        <Button
          onClick={submit}
          disabled={!draft.nome.trim() || saving}
          data-testid="favorecido-dialog-salvar"
        >
          {saving ? "Salvando…" : "Salvar"}
        </Button>
      </DialogFooter>
    </>
  );
}

/**
 * `<AdicionarCompradorDialog/>` — add another party to this atendimento.
 *
 * Presentational (S3): `onCreate` is the only callback out, and this file
 * never fetches. The container decides what happens with the values.
 *
 * 🔴 WHY IT ASKS FOR NAME AND PHONE, AND NOTHING ELSE
 * ---------------------------------------------------
 * Those are exactly the two fields an atendimento cannot move stages without
 * (`pipeline.stage_gate.CAMPOS_OBRIGATORIOS`). Asking for more here would be
 * asking the operator to fill a form in the middle of a different task — the
 * rest of the new person's details belong on the checklist, which is the
 * surface built for collecting them and which will show them as pending until
 * they are.
 *
 * Name is required for a reason worth stating: this creates a PERSON record.
 * A party with no name is a row nobody can identify later, and the contract
 * this exists to support is a legal document naming both buyers.
 *
 * 🔴 ONE DIALOG, BOTH SIDES (migration 098). `lado` changes the copy and the
 * default role and nothing else, because nothing else differs: a vendedor is a
 * `clientes` row with the same checklist, the same uploads and the same
 * extraction as a comprador. A separate `AdicionarVendedorDialog` would have
 * been this file with three strings changed, and the copy that stopped being
 * edited would be the bug.
 *
 * 🔴 …AND A THIRD VARIANT FOR THE SAME REASON. `"conjuge"` (the Cônjuge tab's
 * empty-state action) is COPY ONLY too — it creates the exact same buyer-side
 * party `"comprador"` does, and the container is what sends `papel: "conjuge"`
 * on `onCreate`'s values (this file never learns a role). `lado` stays
 * whatever the request defaults to (`comprador`) — see `ClienteDetailModal
 * .handleAdicionarConjuge`.
 */
import { useEffect, useState } from "react";
import { AlertTriangle, Loader2 } from "lucide-react";

import type { LadoParte } from "@/types/cardHub";
import type { ParteLookup, TipoPessoa } from "@/types/partes";
import { useParteLookup } from "@/hooks/usePartes";
import { mensagemDoErro } from "./mensagemDoErro";
import { apenasDigitos, documentoParaLookup } from "./documentoBr";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

/** Copy variant — the two negotiation sides plus the Cônjuge tab's own
 *  dedicated action. Not `LadoParte` itself: this prop never reaches the
 *  server (see the module docblock), so it is free to name a THIRD flavor
 *  that still creates a `lado: "comprador"` party underneath. */
export type AdicionarCompradorVariant = LadoParte | "conjuge";

/**
 * What `onCreate` hands the container. PF-new stays exactly `{ nome, celular }`;
 * the extra keys appear only for the new paths, each matching one of the
 * mutually-exclusive identifiers of the §2.3 body (`cliente_id` | `nome` |
 * `empresa_id` | `cnpj`) — never two at once.
 */
export interface AdicionarCompradorValues {
  nome?: string;
  celular?: string;
  cliente_id?: string;
  empresa_id?: string;
  cnpj?: string;
  razao_social?: string;
  /** "Re-emitir e re-analisar" ticked on a reused cadastro whose certidões
   *  are stale — the container chains the §1.2 emission after adding. */
  reemitirCertidoes?: boolean;
}

export interface AdicionarCompradorDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreate: (values: AdicionarCompradorValues) => void;
  saving?: boolean;
  /** When given, typing a complete CPF/CNPJ looks the documento up (§2.5).
   *  Absent ⇒ no lookup (and no data fetching from this component). */
  clienteId?: string | null;
  atendimentoId?: string | null;
  /** Which flavor of "add a party" this is. Copy only — the container owns
   *  the request and sends `lado`/`papel` itself. Defaults to the buyer side
   *  so every existing call site keeps its meaning. */
  lado?: AdicionarCompradorVariant;
}

/** Copy per variant. The seller-side description names the OWNER, because
 *  that is what the first vendedor on a deal is; the cônjuge variant names
 *  the legal reason the tab exists at all. */
const COPY: Record<AdicionarCompradorVariant, { titulo: string; descricao: string; placeholder: string }> = {
  comprador: {
    titulo: "Adicionar comprador",
    descricao:
      "Outra pessoa envolvida nesta negociação — um cônjuge, por exemplo. " +
      "Ela terá o mesmo checklist e os mesmos documentos do titular.",
    placeholder: "Maria Mauricio",
  },
  vendedor: {
    titulo: "Adicionar vendedor",
    descricao:
      "Quem está vendendo o imóvel — o proprietário, seu cônjuge ou um " +
      "procurador. Terá o mesmo checklist e os mesmos documentos de qualquer " +
      "outra parte.",
    placeholder: "Carlos Eduardo Ramos",
  },
  conjuge: {
    titulo: "Adicionar cônjuge",
    descricao:
      "O cônjuge do titular — a assinatura que uma venda por pessoa casada " +
      "exige ao lado da dele/dela (CC art. 1.647). Terá o mesmo checklist e " +
      "os mesmos documentos do titular.",
    placeholder: "Maria Mauricio",
  },
};

function formatarData(iso: string | null): string {
  if (!iso) return "—";
  const [y, m, d] = iso.slice(0, 10).split("-");
  return d && m && y ? `${d}/${m}/${y}` : iso;
}

function nomeEncontrado(lookup: ParteLookup): string {
  if (lookup.cliente) return lookup.cliente.nome_oficial || lookup.cliente.nome || "—";
  if (lookup.empresa) return lookup.empresa.razao_social || lookup.empresa.nome_fantasia || "—";
  return "—";
}

/** The oldest emission date among the stale certidões — the worst case. */
function dataVencidaMaisAntiga(lookup: ParteLookup): string | null {
  const vencidas = lookup.certidoes.itens
    .filter((i) => i.stale_para_contrato && i.emitida_em)
    .map((i) => i.emitida_em as string)
    .sort();
  return vencidas[0] ?? null;
}

interface DocumentoLookupProps {
  clienteId: string;
  atendimentoId?: string | null;
  /** Digits of a complete, check-digit-valid documento; `null` keeps it off. */
  documento: string | null;
  onLookup: (lookup: ParteLookup | null) => void;
  usar: boolean;
  onUsar: (usar: boolean) => void;
  reemitir: boolean;
  onReemitir: (v: boolean) => void;
}

/** Owns the lookup query so the dialog itself stays hook-free without a
 *  `clienteId`. Reports ONLY an answer that belongs to the documento on screen
 *  (`keepPreviousData` may still hold the previous one). */
function DocumentoLookup({
  clienteId,
  atendimentoId,
  documento,
  onLookup,
  usar,
  onUsar,
  reemitir,
  onReemitir,
}: DocumentoLookupProps) {
  const query = useParteLookup(clienteId, documento, atendimentoId);
  const lookup = query.data && query.data.documento === documento ? query.data : null;

  useEffect(() => {
    onLookup(lookup);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lookup]);

  if (!documento) return null;
  if (query.showSkeleton) {
    return (
      <p className="flex items-center gap-1.5 text-xs text-muted-foreground" data-testid="parte-lookup-loading">
        <Loader2 className="h-3.5 w-3.5 animate-spin" /> Procurando cadastro…
      </p>
    );
  }
  if (query.isError && !lookup) {
    return (
      <p className="text-xs text-destructive" role="alert" data-testid="parte-lookup-erro">
        {mensagemDoErro(query.error, "Não foi possível consultar o documento.")}
      </p>
    );
  }
  if (!lookup || !lookup.encontrado) return null;

  const outros = lookup.atendimentos.length - (lookup.ja_no_atendimento ? 1 : 0);
  const vencidas = lookup.certidoes.alerta_vencidas;
  const dataVencida = dataVencidaMaisAntiga(lookup);

  return (
    <div className="space-y-2 rounded-md border bg-muted/40 p-3 text-sm" data-testid="parte-lookup-encontrado">
      <p data-testid="parte-lookup-ja-cadastrado">
        <span className="font-medium">Já cadastrado:</span> {nomeEncontrado(lookup)} — em {outros}{" "}
        {outros === 1 ? "outro atendimento" : "outros atendimentos"}
      </p>
      {lookup.ja_no_atendimento ? (
        <p className="text-xs text-muted-foreground" data-testid="parte-lookup-ja-no-atendimento">
          Já faz parte deste atendimento.
        </p>
      ) : (
        <Button
          type="button"
          size="sm"
          variant={usar ? "default" : "outline"}
          onClick={() => onUsar(!usar)}
          data-testid="parte-lookup-usar-btn"
        >
          {usar ? "Usando este cadastro" : "Usar este cadastro"}
        </Button>
      )}
      {vencidas && (
        <div
          className="flex items-start gap-2 rounded border border-amber-300 bg-amber-50 p-2 text-xs text-amber-900"
          role="alert"
          data-testid="parte-lookup-certidoes-vencidas"
        >
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <div className="space-y-1">
            <p className="font-medium">
              Certidões de {formatarData(dataVencida)} — vencidas para contrato
            </p>
            {lookup.certidoes.mensagem && <p>{lookup.certidoes.mensagem}</p>}
            {usar && !lookup.ja_no_atendimento && (
              <label className="flex items-center gap-1.5">
                <input
                  type="checkbox"
                  checked={reemitir}
                  onChange={(e) => onReemitir(e.target.checked)}
                  data-testid="parte-lookup-reemitir-check"
                />
                Re-emitir e re-analisar
              </label>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export function AdicionarCompradorDialog({
  open,
  onOpenChange,
  onCreate,
  saving,
  lado = "comprador",
  clienteId,
  atendimentoId,
}: AdicionarCompradorDialogProps) {
  const copy = COPY[lado];
  // A company cannot be a cônjuge (§2.3 → 400), so that variant is PF-only.
  const permitePJ = lado !== "conjuge";
  const [tipo, setTipo] = useState<TipoPessoa>("PF");
  const [nome, setNome] = useState("");
  const [celular, setCelular] = useState("");
  const [documento, setDocumento] = useState("");
  const [razaoSocial, setRazaoSocial] = useState("");
  const [lookup, setLookup] = useState<ParteLookup | null>(null);
  const [usar, setUsar] = useState(false);
  const [reemitir, setReemitir] = useState(false);

  // Cleared on OPEN rather than on close: clearing on close wipes the fields
  // while the closing animation is still showing them.
  useEffect(() => {
    if (open) {
      setTipo("PF");
      setNome("");
      setCelular("");
      setDocumento("");
      setRazaoSocial("");
      setLookup(null);
      setUsar(false);
      setReemitir(false);
    }
  }, [open]);

  const documentoLookup = documentoParaLookup(documento, tipo);
  // A match only counts while it belongs to the documento on screen and the
  // person is not already on this atendimento (the server would 409).
  const match = lookup && lookup.encontrado && !lookup.ja_no_atendimento ? lookup : null;
  const usandoCadastro = usar && !!match;
  const cnpjDigitos = apenasDigitos(documento);
  const pjNovoValido = tipo === "PJ" && documentoLookup !== null;

  const podeEnviar =
    !saving &&
    (usandoCadastro || (tipo === "PF" ? nome.trim().length > 0 : pjNovoValido));

  function trocarTipo(novo: TipoPessoa) {
    setTipo(novo);
    setDocumento("");
    setLookup(null);
    setUsar(false);
    setReemitir(false);
  }

  function submit() {
    if (!podeEnviar) return;
    if (usandoCadastro && match) {
      const stale = match.certidoes.alerta_vencidas && reemitir;
      onCreate({
        ...(match.encontrado === "empresa" && match.empresa
          ? { empresa_id: match.empresa.id }
          : { cliente_id: match.cliente?.id }),
        ...(stale ? { reemitirCertidoes: true } : {}),
      });
      return;
    }
    if (tipo === "PJ") {
      onCreate({
        cnpj: cnpjDigitos,
        ...(razaoSocial.trim() ? { razao_social: razaoSocial.trim() } : {}),
      });
      return;
    }
    onCreate({
      nome: nome.trim(),
      celular: celular.trim() || undefined,
    });
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="max-w-md"
        data-testid={`adicionar-${lado}-dialog`}
      >
        <DialogHeader>
          <DialogTitle>{copy.titulo}</DialogTitle>
          <DialogDescription>{copy.descricao}</DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          {permitePJ && (
            <div className="flex gap-2" role="group" aria-label="Tipo de pessoa" data-testid="parte-tipo-toggle">
              {(["PF", "PJ"] as const).map((t) => (
                <Button
                  key={t}
                  type="button"
                  size="sm"
                  variant={tipo === t ? "default" : "outline"}
                  aria-pressed={tipo === t}
                  onClick={() => trocarTipo(t)}
                  data-testid={`parte-tipo-${t.toLowerCase()}`}
                >
                  {t === "PF" ? "Pessoa física" : "Pessoa jurídica"}
                </Button>
              ))}
            </div>
          )}

          <div>
            <label
              htmlFor="comprador-documento"
              className="mb-1 block text-xs font-medium text-muted-foreground"
            >
              {tipo === "PF" ? "CPF" : "CNPJ"}{" "}
              {tipo === "PF" && <span className="font-normal">(opcional — busca cadastro existente)</span>}
            </label>
            <Input
              id="comprador-documento"
              value={documento}
              onChange={(e) => {
                setDocumento(e.target.value);
                setUsar(false);
                setReemitir(false);
              }}
              placeholder={tipo === "PF" ? "000.000.000-00" : "00.000.000/0000-00"}
              inputMode="numeric"
              data-testid="comprador-documento-input"
            />
          </div>

          {clienteId && (
            <DocumentoLookup
              clienteId={clienteId}
              atendimentoId={atendimentoId}
              documento={documentoLookup}
              onLookup={setLookup}
              usar={usar}
              onUsar={setUsar}
              reemitir={reemitir}
              onReemitir={setReemitir}
            />
          )}

          {!usandoCadastro && tipo === "PF" && (
            <>
              <div>
                <label
                  htmlFor="comprador-nome"
                  className="mb-1 block text-xs font-medium text-muted-foreground"
                >
                  Nome completo
                </label>
                <Input
                  id="comprador-nome"
                  value={nome}
                  onChange={(e) => setNome(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") submit();
                  }}
                  placeholder={copy.placeholder}
                  autoFocus
                  data-testid="comprador-nome-input"
                />
              </div>
              <div>
                <label
                  htmlFor="comprador-celular"
                  className="mb-1 block text-xs font-medium text-muted-foreground"
                >
                  Celular <span className="font-normal">(opcional)</span>
                </label>
                <Input
                  id="comprador-celular"
                  value={celular}
                  onChange={(e) => setCelular(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") submit();
                  }}
                  placeholder="+55 11 99999-8888"
                  data-testid="comprador-celular-input"
                />
              </div>
            </>
          )}

          {!usandoCadastro && tipo === "PJ" && (
            <div>
              <label
                htmlFor="comprador-razao-social"
                className="mb-1 block text-xs font-medium text-muted-foreground"
              >
                Razão social <span className="font-normal">(opcional)</span>
              </label>
              <Input
                id="comprador-razao-social"
                value={razaoSocial}
                onChange={(e) => setRazaoSocial(e.target.value)}
                data-testid="comprador-razao-social-input"
              />
              {documento.trim() !== "" && documentoLookup === null && (
                <p className="mt-1 text-xs text-destructive" data-testid="comprador-cnpj-invalido">
                  CNPJ inválido.
                </p>
              )}
            </div>
          )}
        </div>

        <div className="flex justify-end gap-2">
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            data-testid="comprador-cancelar-btn"
          >
            Cancelar
          </Button>
          <Button
            disabled={!podeEnviar}
            onClick={submit}
            data-testid="comprador-salvar-btn"
          >
            {saving ? "Adicionando…" : "Adicionar"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

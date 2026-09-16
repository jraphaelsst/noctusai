/**
 * `<MatriculaAtoDetalhesEditor/>` — review what we read out of ONE act of a
 * matrícula, and confirm or fix it (migration 115).
 *
 * 🔴 WHY A REVIEW SCREEN EXISTS AT ALL
 * -------------------------------------
 * The contract's clauses are built from these fields: the título aquisitivo
 * phrase comes from `instrumento`, the ônus creditor from `credor`, the
 * previous owners from `transmitentes`. All three are READ off scanned text
 * by a deterministic extractor that is right most of the time. "Most of the
 * time" is fine for a suggestion and unacceptable for a deed, so every field
 * shows its own confidence and nothing counts until a person agrees with it.
 *
 * 🔴 THE THREE MEANINGS OF THE PATCH ARE THE WHOLE CONTRACT
 * ----------------------------------------------------------
 * `buildPatch` sends ONLY what changed: an absent key keeps the suggestion,
 * an explicit `null` clears it, and an empty `{}` confirms everything as it
 * stands. Spreading the current values into the patch instead would look
 * identical on screen while silently re-writing every field as human-typed
 * (`confianca: alta`), which is exactly the lie this screen exists to
 * prevent.
 *
 * PRESENTATIONAL (same S3 split as `MatriculaAtosSelector`): props in,
 * callbacks out, zero `useQuery`/`useMutation`. The page that fetches
 * (`pages/Matriculas.tsx`) owns `useMatriculaAtos` /
 * `useConfirmarDetalhesAto`.
 *
 * The act's literal TEXT is not rendered here — the act list already shows it
 * verbatim, and a second copy inside the editor would invite someone to
 * "fix" a typo the contract is required to reproduce.
 */
import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, Loader2, Plus, Sparkles, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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
  NATUREZA_LABEL,
  NATUREZAS_ATO,
  type AtoConfianca,
  type AtoInstrumento,
  type AtoParte,
  type MatriculaAto,
  type MatriculaAtoDetalhes,
  type MatriculaAtoDetalhesPatch,
} from "@/hooks/useMatriculaEstrutura";

/** Radix `SelectItem` refuses an empty string, so absence needs a token. */
const SEM_NATUREZA = "__sem_natureza__";

export interface MatriculaAtoDetalhesEditorProps {
  ato: Pick<MatriculaAto, "id" | "kind" | "numero" | "rotulo">;
  /**
   * `null` for the abertura, or an extraction whose text was purged — and
   * `undefined` for an act row that carries no `detalhes` key at all (a
   * response cached before migration 115 shipped). Both are "nothing to
   * review here", and treating the second as a crash would take the whole
   * matrículas page down over a missing optional field.
   */
  detalhes: MatriculaAtoDetalhes | null | undefined;
  saving: boolean;
  /** The server's refusal, shown verbatim — it names the field it rejected. */
  errorMessage?: string | null;
  onConfirmar: (patch: MatriculaAtoDetalhesPatch) => void;
}

interface InstrumentoDraft {
  tipo: string;
  data: string;
  tabelionato: string;
  livro: string;
  folhas: string;
  cidade: string;
}

interface Draft {
  natureza: string;
  data_registro: string;
  valor: string;
  credor: string;
  transmitentes: AtoParte[];
  adquirentes: AtoParte[];
  instrumento: InstrumentoDraft;
}

const INSTRUMENTO_CAMPOS: { key: keyof InstrumentoDraft; label: string; tipo?: string }[] = [
  { key: "tipo", label: "Instrumento" },
  { key: "data", label: "Data", tipo: "date" },
  { key: "tabelionato", label: "Tabelionato" },
  { key: "livro", label: "Livro" },
  { key: "folhas", label: "Folhas" },
  { key: "cidade", label: "Cidade" },
];

function texto(v: string | null | undefined): string {
  return v ?? "";
}

function toDraft(detalhes: MatriculaAtoDetalhes | null): Draft {
  return {
    natureza: detalhes?.natureza ?? SEM_NATUREZA,
    data_registro: texto(detalhes?.data_registro).slice(0, 10),
    valor: texto(detalhes?.valor),
    credor: texto(detalhes?.credor),
    transmitentes: (detalhes?.transmitentes ?? []).map((p) => ({ ...p })),
    adquirentes: (detalhes?.adquirentes ?? []).map((p) => ({ ...p })),
    instrumento: {
      tipo: texto(detalhes?.instrumento?.tipo),
      data: texto(detalhes?.instrumento?.data).slice(0, 10),
      tabelionato: texto(detalhes?.instrumento?.tabelionato),
      livro: texto(detalhes?.instrumento?.livro),
      folhas: texto(detalhes?.instrumento?.folhas),
      cidade: texto(detalhes?.instrumento?.cidade),
    },
  };
}

/** Blank → `null`: the backend treats `""` as a present, empty value, which
 *  reads as "checked and really is blank" everywhere downstream. */
function limpo(v: string): string | null {
  const t = v.trim();
  return t === "" ? null : t;
}

/** Drop rows the operator left without a name — the backend refuses a party
 *  with no `nome` (422), and an empty row is an abandoned edit, not a party. */
function partesLimpas(partes: AtoParte[]): AtoParte[] {
  return partes
    .filter((p) => (p.nome ?? "").trim() !== "")
    .map((p) => ({ nome: p.nome.trim(), cpf_cnpj: limpo(p.cpf_cnpj ?? "") }));
}

function mesmasPartes(a: AtoParte[], b: AtoParte[]): boolean {
  return JSON.stringify(a) === JSON.stringify(b.map((p) => ({ nome: p.nome, cpf_cnpj: p.cpf_cnpj ?? null })));
}

function instrumentoDoDraft(draft: InstrumentoDraft): AtoInstrumento | null {
  const valor: AtoInstrumento = {
    tipo: limpo(draft.tipo),
    data: limpo(draft.data),
    tabelionato: limpo(draft.tabelionato),
    livro: limpo(draft.livro),
    folhas: limpo(draft.folhas),
    cidade: limpo(draft.cidade),
  };
  // Every field blank IS "there is no instrument here" — `null`, not an
  // object of nulls, which the backend would store as a present-but-empty
  // instrumento and `frase_titulo_aquisitivo` would then render from.
  return Object.values(valor).some((v) => v !== null) ? valor : null;
}

function mesmoInstrumento(a: AtoInstrumento | null, b: AtoInstrumento | null | undefined): boolean {
  const normal = (v: AtoInstrumento | null | undefined) =>
    v
      ? JSON.stringify({
          tipo: v.tipo ?? null,
          data: v.data ? v.data.slice(0, 10) : null,
          tabelionato: v.tabelionato ?? null,
          livro: v.livro ?? null,
          folhas: v.folhas ?? null,
          cidade: v.cidade ?? null,
        })
      : "null";
  return normal(a) === normal(b);
}

/**
 * The patch for what actually changed — see the file header. Exported for its
 * own test: this function IS the feature's contract with the backend.
 */
export function buildPatch(
  draft: Draft,
  detalhes: MatriculaAtoDetalhes | null,
): MatriculaAtoDetalhesPatch {
  const patch: MatriculaAtoDetalhesPatch = {};

  const natureza = draft.natureza === SEM_NATUREZA ? null : draft.natureza;
  if (natureza !== (detalhes?.natureza ?? null)) patch.natureza = natureza;

  const data = limpo(draft.data_registro);
  if (data !== (texto(detalhes?.data_registro).slice(0, 10) || null)) patch.data_registro = data;

  const valor = limpo(draft.valor);
  if (valor !== (detalhes?.valor ?? null)) patch.valor = valor;

  const credor = limpo(draft.credor);
  if (credor !== (detalhes?.credor ?? null)) patch.credor = credor;

  const transmitentes = partesLimpas(draft.transmitentes);
  if (!mesmasPartes(transmitentes, detalhes?.transmitentes ?? [])) {
    patch.transmitentes = transmitentes;
  }

  const adquirentes = partesLimpas(draft.adquirentes);
  if (!mesmasPartes(adquirentes, detalhes?.adquirentes ?? [])) {
    patch.adquirentes = adquirentes;
  }

  const instrumento = instrumentoDoDraft(draft.instrumento);
  if (!mesmoInstrumento(instrumento, detalhes?.instrumento)) patch.instrumento = instrumento;

  return patch;
}

const CONFIANCA_TEXTO: Record<AtoConfianca, string> = {
  alta: "leitura segura",
  baixa: "leitura incerta · confira",
  nenhuma: "não encontrado · preencha",
};

/** A field's confidence, highlighted when it is NOT `alta`. */
function ConfiancaBadge({
  campo,
  confianca,
  prefixo,
}: {
  campo: string;
  confianca: AtoConfianca;
  prefixo: string;
}) {
  const destaque = confianca !== "alta";
  return (
    <Badge
      variant="outline"
      className={
        destaque
          ? "border-amber-500 bg-amber-50 text-[10px] text-amber-700"
          : "text-[10px] text-muted-foreground"
      }
      data-testid={`${prefixo}-confianca-${campo}`}
      data-confianca={confianca}
      data-destaque={destaque ? "true" : "false"}
    >
      {CONFIANCA_TEXTO[confianca] ?? confianca}
    </Badge>
  );
}

function PartesEditor({
  titulo,
  campo,
  partes,
  confianca,
  prefixo,
  disabled,
  onChange,
}: {
  titulo: string;
  campo: string;
  partes: AtoParte[];
  confianca: AtoConfianca;
  prefixo: string;
  disabled: boolean;
  onChange: (partes: AtoParte[]) => void;
}) {
  function set(index: number, patch: Partial<AtoParte>) {
    onChange(partes.map((p, i) => (i === index ? { ...p, ...patch } : p)));
  }

  return (
    <div className="space-y-1.5" data-testid={`${prefixo}-${campo}`}>
      <div className="flex items-center gap-2">
        <Label className="text-xs">{titulo}</Label>
        <ConfiancaBadge campo={campo} confianca={confianca} prefixo={prefixo} />
      </div>
      {partes.length === 0 && (
        <p className="text-xs text-muted-foreground">Nenhum nome informado.</p>
      )}
      <ul className="space-y-1">
        {partes.map((parte, index) => (
          <li key={index} className="flex items-center gap-1.5">
            <Input
              className="h-8 flex-1 text-sm"
              value={parte.nome}
              placeholder="Nome"
              disabled={disabled}
              onChange={(e) => set(index, { nome: e.target.value })}
              data-testid={`${prefixo}-${campo}-nome-${index}`}
            />
            <Input
              className="h-8 w-40 text-sm"
              value={parte.cpf_cnpj ?? ""}
              placeholder="CPF/CNPJ"
              disabled={disabled}
              onChange={(e) => set(index, { cpf_cnpj: e.target.value })}
              data-testid={`${prefixo}-${campo}-doc-${index}`}
            />
            <Button
              type="button"
              size="icon"
              variant="ghost"
              className="h-8 w-8"
              disabled={disabled}
              aria-label={`Remover ${titulo.toLowerCase()} ${index + 1}`}
              onClick={() => onChange(partes.filter((_, i) => i !== index))}
              data-testid={`${prefixo}-${campo}-remover-${index}`}
            >
              <X className="h-3.5 w-3.5" />
            </Button>
          </li>
        ))}
      </ul>
      <Button
        type="button"
        size="sm"
        variant="outline"
        className="h-7 text-xs"
        disabled={disabled}
        onClick={() => onChange([...partes, { nome: "", cpf_cnpj: null }])}
        data-testid={`${prefixo}-${campo}-adicionar`}
      >
        <Plus className="mr-1 h-3 w-3" /> Adicionar
      </Button>
    </div>
  );
}

export default function MatriculaAtoDetalhesEditor({
  ato,
  detalhes,
  saving,
  errorMessage,
  onConfirmar,
}: MatriculaAtoDetalhesEditorProps) {
  const prefixo = `ato-detalhes-${ato.id}`;
  const [draft, setDraft] = useState<Draft>(() => toDraft(detalhes));

  // Re-seed when the SERVER's values change — keyed on the values themselves
  // (serialised), never on object identity, so a background refetch that
  // changed nothing does not stomp an edit in progress. Same discipline as
  // `ImovelCartorioCard.toDraft` and `MatriculaAtosSelector`'s draft.
  const assinatura = JSON.stringify([
    detalhes?.natureza ?? null,
    detalhes?.data_registro ?? null,
    detalhes?.valor ?? null,
    detalhes?.credor ?? null,
    detalhes?.transmitentes ?? [],
    detalhes?.adquirentes ?? [],
    detalhes?.instrumento ?? null,
    detalhes?.origem ?? null,
  ]);
  useEffect(() => {
    setDraft(toDraft(detalhes));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [assinatura]);

  // Falsy, not `=== null`: see the prop's note. An act row without the key
  // reaches this component as `undefined`, and reading `.origem` off it threw
  // for the entire page (caught by the matrículas page test, 2026-09-15).
  if (!detalhes) {
    return (
      <p className="text-xs text-muted-foreground" data-testid={`${prefixo}-ausente`}>
        Este trecho não é um ato registrado — não tem detalhes para conferir.
      </p>
    );
  }

  const confirmado = detalhes.origem === "confirmado";
  const patch = buildPatch(draft, detalhes);
  const semAlteracoes = Object.keys(patch).length === 0;

  const set = <K extends keyof Draft>(k: K) => (v: Draft[K]) =>
    setDraft((d) => ({ ...d, [k]: v }));

  return (
    <div className="space-y-3 rounded-md border bg-background p-2.5" data-testid={prefixo}>
      {/* ─── Sugestão vs confirmado ──────────────────────────────────────
          The distinction the whole screen exists for, said in words. */}
      <div className="flex flex-wrap items-center gap-2">
        {confirmado ? (
          <Badge variant="secondary" className="gap-1 text-[10px]" data-testid={`${prefixo}-origem`} data-origem="confirmado">
            <CheckCircle2 className="h-3 w-3" />
            Conferido
          </Badge>
        ) : (
          <Badge
            variant="outline"
            className="gap-1 border-amber-500 bg-amber-50 text-[10px] text-amber-700"
            data-testid={`${prefixo}-origem`}
            data-origem="sugestao"
          >
            <Sparkles className="h-3 w-3" />
            Sugestão — ninguém conferiu ainda
          </Badge>
        )}
        {confirmado && (
          <span className="text-[11px] text-muted-foreground">
            {detalhes.confirmado_por?.nome ?? "—"}
            {detalhes.confirmado_em
              ? ` em ${new Date(detalhes.confirmado_em).toLocaleString("pt-BR")}`
              : ""}
          </span>
        )}
      </div>

      <div className="grid gap-2.5 sm:grid-cols-2">
        {/* Natureza */}
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <Label className="text-xs" htmlFor={`${prefixo}-natureza`}>
              Natureza
            </Label>
            <ConfiancaBadge campo="natureza" confianca={detalhes.natureza_confianca} prefixo={prefixo} />
          </div>
          <Select
            value={draft.natureza}
            onValueChange={set("natureza")}
            disabled={saving}
          >
            <SelectTrigger id={`${prefixo}-natureza`} className="h-8 text-sm" data-testid={`${prefixo}-natureza-trigger`}>
              <SelectValue placeholder="Selecione" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={SEM_NATUREZA}>Não identificada</SelectItem>
              {NATUREZAS_ATO.map((n) => (
                <SelectItem key={n} value={n}>
                  {NATUREZA_LABEL[n] ?? n}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Data do registro */}
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <Label className="text-xs" htmlFor={`${prefixo}-data`}>
              Data do registro
            </Label>
            <ConfiancaBadge
              campo="data_registro"
              confianca={detalhes.data_registro_confianca}
              prefixo={prefixo}
            />
          </div>
          <Input
            id={`${prefixo}-data`}
            type="date"
            className="h-8 text-sm"
            value={draft.data_registro}
            disabled={saving}
            onChange={(e) => set("data_registro")(e.target.value)}
            data-testid={`${prefixo}-data`}
          />
        </div>

        {/* Valor */}
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <Label className="text-xs" htmlFor={`${prefixo}-valor`}>
              Valor (R$)
            </Label>
            <ConfiancaBadge campo="valor" confianca={detalhes.valor_confianca} prefixo={prefixo} />
          </div>
          <Input
            id={`${prefixo}-valor`}
            className="h-8 text-sm"
            inputMode="decimal"
            placeholder="0.00"
            value={draft.valor}
            disabled={saving}
            onChange={(e) => set("valor")(e.target.value)}
            data-testid={`${prefixo}-valor`}
          />
        </div>

        {/* Credor */}
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <Label className="text-xs" htmlFor={`${prefixo}-credor`}>
              Credor
            </Label>
            <ConfiancaBadge campo="credor" confianca={detalhes.credor_confianca} prefixo={prefixo} />
          </div>
          <Input
            id={`${prefixo}-credor`}
            className="h-8 text-sm"
            placeholder="Banco / credor do gravame"
            value={draft.credor}
            disabled={saving}
            onChange={(e) => set("credor")(e.target.value)}
            data-testid={`${prefixo}-credor`}
          />
        </div>
      </div>

      <PartesEditor
        titulo="Transmitentes"
        campo="transmitentes"
        partes={draft.transmitentes}
        confianca={detalhes.transmitentes_confianca}
        prefixo={prefixo}
        disabled={saving}
        onChange={set("transmitentes")}
      />
      <PartesEditor
        titulo="Adquirentes"
        campo="adquirentes"
        partes={draft.adquirentes}
        confianca={detalhes.adquirentes_confianca}
        prefixo={prefixo}
        disabled={saving}
        onChange={set("adquirentes")}
      />

      {/* ─── Instrumento (sub-form) ──────────────────────────────────────
          The título aquisitivo phrase is rendered FROM these fields, so an
          incomplete instrumento is why that phrase comes back empty. */}
      <div className="space-y-1.5 rounded border border-dashed p-2" data-testid={`${prefixo}-instrumento`}>
        <div className="flex items-center gap-2">
          <Label className="text-xs">Instrumento</Label>
          <ConfiancaBadge
            campo="instrumento"
            confianca={detalhes.instrumento_confianca}
            prefixo={prefixo}
          />
        </div>
        <div className="grid gap-2 sm:grid-cols-3">
          {INSTRUMENTO_CAMPOS.map(({ key, label, tipo }) => (
            <div key={key} className="space-y-1">
              <Label className="text-[11px] text-muted-foreground" htmlFor={`${prefixo}-instrumento-${key}`}>
                {label}
              </Label>
              <Input
                id={`${prefixo}-instrumento-${key}`}
                type={tipo ?? "text"}
                className="h-8 text-sm"
                value={draft.instrumento[key]}
                disabled={saving}
                onChange={(e) =>
                  setDraft((d) => ({
                    ...d,
                    instrumento: { ...d.instrumento, [key]: e.target.value },
                  }))
                }
                data-testid={`${prefixo}-instrumento-${key}`}
              />
            </div>
          ))}
        </div>
        <p className="text-[11px] text-muted-foreground">
          A frase do título aquisitivo é montada com estes campos.
        </p>
      </div>

      {/* Read-only: which earlier acts this one cites. Editing a citation is
          not a reading of THIS act's text, so it is shown, not offered. */}
      {detalhes.atos_referidos.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5" data-testid={`${prefixo}-atos-referidos`}>
          <Label className="text-xs">Atos citados</Label>
          {detalhes.atos_referidos.map((ref) => (
            <Badge key={`${ref.kind}-${ref.numero}`} variant="outline" className="text-[10px]">
              {ref.kind}-{ref.numero}
            </Badge>
          ))}
          <ConfiancaBadge
            campo="atos_referidos"
            confianca={detalhes.atos_referidos_confianca}
            prefixo={prefixo}
          />
        </div>
      )}

      {errorMessage && (
        <p className="flex items-start gap-1.5 text-xs text-destructive" data-testid={`${prefixo}-erro`}>
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          {errorMessage}
        </p>
      )}

      <div className="flex items-center gap-2">
        <Button
          type="button"
          size="sm"
          onClick={() => onConfirmar(patch)}
          disabled={saving}
          data-testid={`${prefixo}-confirmar`}
        >
          {saving && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
          {semAlteracoes ? "Confirmar como está" : "Salvar e confirmar"}
        </Button>
        <span className="text-[11px] text-muted-foreground">
          {semAlteracoes
            ? "Nada alterado — confirma a leitura atual."
            : `${Object.keys(patch).length} campo(s) alterado(s).`}
        </span>
      </div>
    </div>
  );
}

/**
 * `<AditivoEditor/>` — the structured amendments of ONE aditivo
 * (contrato-aditivos-CONTRACT §1): estilo, data, modalidade, and the list of
 * alterações — pagamento (with the RESTATED parcela schedule, edited through
 * the negociação's own `ParcelaFormDialog`), posse, comissão, outro (free
 * text). Saved as ONE `PATCH` (the server replaces `alteracoes`/`parcelas`
 * whole).
 *
 * Presentational (S3): the caller owns the mutation and hands back
 * `salvando`/`erro`. A signed / cancelled aditivo is frozen server-side
 * (409 `ADITIVO_CONGELADO`), so it renders read-only here.
 *
 * Draft ↔ wire conversion and the client-side 422 mirror live in
 * `aditivoDraft.ts` (pure, unit-tested).
 */
import { useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { ArrowDown, ArrowUp, Loader2, Pencil, Plus, Save, Trash2, Undo2 } from "lucide-react";

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
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";

import {
  ParcelaFormDialog,
  type FavorecidoOpcao,
} from "@/components/card/negociacao/ParcelaFormDialog";
import {
  ADITIVO_ESTILO_LABEL,
  ADITIVO_ESTILO_OPTIONS,
  ALTERACAO_TIPOS_UNICOS,
  ALTERACAO_TIPO_LABEL,
  ALTERACAO_TIPO_OPTIONS,
  COMISSAO_MARCO_LABEL,
  aditivoCongelado,
  type AditivoEstilo,
  type AditivoOut,
  type AditivoPatchBody,
  type AlteracaoTipo,
  type ComissaoMarco,
  type ParcelaAditivoTipo,
} from "@/hooks/useContratoAditivos";
import { MODALIDADE_ASSINATURA_LABEL, type ModalidadeAssinatura } from "@/hooks/useContratos";
import { exibirData, exibirMoeda } from "@/lib/moedaDecimal";
import { PARCELA_TIPO_LABELS } from "@/types/negociacaoEstruturada";

import {
  alteracaoVazia,
  draftDoAditivo,
  draftSujo,
  novoUid,
  patchDoDraft,
  validarDraft,
  type AditivoDraft,
  type AlteracaoDraft,
  type ParcelaDraftRow,
} from "./aditivoDraft";

const TITULO_MAX = 120;
const TEXTO_MAX = 8000;
const FINALIDADE_MAX = 500;

export interface AditivoEditorProps {
  aditivo: AditivoOut;
  /** The deal's favorecidos — a parcela's payee must be one of them. */
  favorecidos: FavorecidoOpcao[];
  salvando: boolean;
  /** The last save's refusal (server sentence) — `null` when none. */
  erro: string | null;
  onSalvar: (patch: AditivoPatchBody) => void;
  /** Unsaved changes exist — the generate section waits for a save. */
  onDirtyChange?: (sujo: boolean) => void;
}

export function AditivoEditor({
  aditivo,
  favorecidos,
  salvando,
  erro,
  onSalvar,
  onDirtyChange,
}: AditivoEditorProps) {
  const [draft, setDraft] = useState<AditivoDraft>(() => draftDoAditivo(aditivo));
  // Re-seed from the server only when the SERVER row changed (a save
  // landed, someone else edited) — a background refetch of the same row
  // never wipes what is being typed.
  const versaoServidor = `${aditivo.id}:${aditivo.updated_at ?? aditivo.created_at}`;
  const ultimaVersaoRef = useRef(versaoServidor);
  useEffect(() => {
    if (ultimaVersaoRef.current === versaoServidor) return;
    ultimaVersaoRef.current = versaoServidor;
    setDraft(draftDoAditivo(aditivo));
  }, [versaoServidor, aditivo]);

  const sujo = useMemo(() => draftSujo(draft, aditivo), [draft, aditivo]);
  const erros = useMemo(() => validarDraft(draft), [draft]);
  const valido = Object.keys(erros).length === 0;

  useEffect(() => {
    onDirtyChange?.(sujo);
  }, [sujo, onDirtyChange]);

  if (aditivoCongelado(aditivo)) {
    return <AditivoResumo aditivo={aditivo} favorecidos={favorecidos} />;
  }

  const temPagamento = draft.alteracoes.some((a) => a.tipo === "pagamento");

  function atualizarAlteracao(uid: string, campos: Partial<AlteracaoDraft>) {
    setDraft((d) => ({
      ...d,
      alteracoes: d.alteracoes.map((a) => (a.uid === uid ? { ...a, ...campos } : a)),
    }));
  }

  function removerAlteracao(uid: string) {
    setDraft((d) => {
      const alvo = d.alteracoes.find((a) => a.uid === uid);
      return {
        ...d,
        alteracoes: d.alteracoes.filter((a) => a.uid !== uid),
        // The restated schedule belongs to the payment amendment — removing
        // it removes the schedule (the gate would refuse a lone schedule:
        // PARCELAS_SEM_ALTERACAO_DE_PAGAMENTO).
        parcelas: alvo?.tipo === "pagamento" ? [] : d.parcelas,
      };
    });
  }

  function adicionarAlteracao(tipo: AlteracaoTipo) {
    setDraft((d) => ({ ...d, alteracoes: [...d.alteracoes, alteracaoVazia(tipo)] }));
  }

  return (
    <div className="space-y-3" data-testid={`aditivo-editor-${aditivo.id}`}>
      <div className="grid gap-3 sm:grid-cols-3">
        <div className="space-y-1.5">
          <Label htmlFor={`aditivo-estilo-${aditivo.id}`} className="text-xs">
            Estilo do documento
          </Label>
          <Select
            value={draft.estilo}
            onValueChange={(v) => setDraft((d) => ({ ...d, estilo: v as AditivoEstilo }))}
          >
            <SelectTrigger
              id={`aditivo-estilo-${aditivo.id}`}
              className="h-8"
              data-testid={`aditivo-estilo-${aditivo.id}`}
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {ADITIVO_ESTILO_OPTIONS.map((e) => (
                <SelectItem key={e} value={e}>
                  {ADITIVO_ESTILO_LABEL[e]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor={`aditivo-data-${aditivo.id}`} className="text-xs">
            Data do aditivo
          </Label>
          <Input
            id={`aditivo-data-${aditivo.id}`}
            type="date"
            className="h-8"
            value={draft.assinaturaData}
            onChange={(e) => setDraft((d) => ({ ...d, assinaturaData: e.target.value }))}
            data-testid={`aditivo-data-${aditivo.id}`}
          />
          <p className="text-[11px] text-muted-foreground">Em branco: a data da geração.</p>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor={`aditivo-modalidade-${aditivo.id}`} className="text-xs">
            Assinatura
          </Label>
          <Select
            value={draft.modalidade}
            onValueChange={(v) => setDraft((d) => ({ ...d, modalidade: v as ModalidadeAssinatura }))}
          >
            <SelectTrigger
              id={`aditivo-modalidade-${aditivo.id}`}
              className="h-8"
              data-testid={`aditivo-modalidade-${aditivo.id}`}
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {(["digital", "fisica"] as ModalidadeAssinatura[]).map((m) => (
                <SelectItem key={m} value={m}>
                  {MODALIDADE_ASSINATURA_LABEL[m]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {draft.alteracoes.length === 0 ? (
        <p className="text-xs text-muted-foreground" data-testid={`aditivo-sem-alteracoes-${aditivo.id}`}>
          Nenhuma alteração ainda. Adicione o que este aditivo muda no contrato original.
        </p>
      ) : (
        <div className="space-y-2">
          {draft.alteracoes.map((alt) => (
            <AlteracaoBloco
              key={alt.uid}
              aditivoId={aditivo.id}
              alteracao={alt}
              erros={erros[alt.uid] ?? []}
              temPagamento={temPagamento}
              onChange={(campos) => atualizarAlteracao(alt.uid, campos)}
              onRemover={() => removerAlteracao(alt.uid)}
            >
              {alt.tipo === "pagamento" && (
                <ParcelasAditivoEditor
                  aditivoId={aditivo.id}
                  parcelas={draft.parcelas}
                  favorecidos={favorecidos}
                  onChange={(parcelas) => setDraft((d) => ({ ...d, parcelas }))}
                />
              )}
            </AlteracaoBloco>
          ))}
        </div>
      )}

      {!temPagamento && draft.parcelas.length > 0 && (
        <div
          className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-amber-300 bg-amber-50 p-2 text-xs text-amber-800"
          data-testid={`aditivo-parcelas-orfas-${aditivo.id}`}
        >
          {draft.parcelas.length} parcela(s) sem a alteração de pagamento — adicione o pagamento ou
          remova o cronograma.
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => setDraft((d) => ({ ...d, parcelas: [] }))}
          >
            Remover cronograma
          </Button>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-1.5" data-testid={`aditivo-adicionar-${aditivo.id}`}>
        <span className="text-xs text-muted-foreground">Adicionar:</span>
        {ALTERACAO_TIPO_OPTIONS.map((tipo) => {
          const jaExiste =
            ALTERACAO_TIPOS_UNICOS.includes(tipo) && draft.alteracoes.some((a) => a.tipo === tipo);
          return (
            <Button
              key={tipo}
              type="button"
              size="sm"
              variant="outline"
              className="h-7 text-xs"
              disabled={jaExiste}
              title={jaExiste ? "No máximo uma alteração deste tipo por aditivo." : undefined}
              onClick={() => adicionarAlteracao(tipo)}
              data-testid={`aditivo-adicionar-${tipo}-${aditivo.id}`}
            >
              <Plus className="mr-1 h-3 w-3" />
              {ALTERACAO_TIPO_LABEL[tipo]}
            </Button>
          );
        })}
      </div>

      {erro && (
        <p
          className="rounded-md border border-destructive/30 bg-destructive/5 p-2 text-xs text-destructive"
          data-testid={`aditivo-salvar-erro-${aditivo.id}`}
        >
          {erro}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <Button
          type="button"
          size="sm"
          disabled={!sujo || !valido || salvando}
          onClick={() => onSalvar(patchDoDraft(draft, aditivo))}
          data-testid={`aditivo-salvar-${aditivo.id}`}
        >
          {salvando ? (
            <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
          ) : (
            <Save className="mr-1.5 h-3.5 w-3.5" />
          )}
          Salvar alterações
        </Button>
        {sujo && (
          <Button
            type="button"
            size="sm"
            variant="ghost"
            disabled={salvando}
            onClick={() => setDraft(draftDoAditivo(aditivo))}
            data-testid={`aditivo-descartar-${aditivo.id}`}
          >
            <Undo2 className="mr-1.5 h-3.5 w-3.5" />
            Descartar
          </Button>
        )}
        {sujo && !valido && (
          <span className="text-xs text-destructive">Corrija os campos destacados para salvar.</span>
        )}
      </div>
    </div>
  );
}

// ─── One alteração ─────────────────────────────────────────────────────────

function AlteracaoBloco({
  aditivoId,
  alteracao: a,
  erros,
  temPagamento,
  onChange,
  onRemover,
  children,
}: {
  aditivoId: string;
  alteracao: AlteracaoDraft;
  erros: string[];
  temPagamento: boolean;
  onChange: (campos: Partial<AlteracaoDraft>) => void;
  onRemover: () => void;
  children?: ReactNode;
}) {
  const id = (campo: string) => `aditivo-${aditivoId}-${a.uid}-${campo}`;
  return (
    <div
      className={`space-y-2 rounded-md border p-2.5 ${erros.length > 0 ? "border-destructive/40" : ""}`}
      data-testid={`aditivo-alteracao-${a.tipo}-${aditivoId}`}
    >
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-semibold">{ALTERACAO_TIPO_LABEL[a.tipo]}</p>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          className="h-7 px-2 text-destructive hover:text-destructive"
          onClick={onRemover}
          aria-label={`Remover alteração de ${ALTERACAO_TIPO_LABEL[a.tipo].toLowerCase()}`}
        >
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
      </div>

      <div className="grid gap-2 sm:grid-cols-[8rem_1fr]">
        <div className="space-y-1">
          <Label htmlFor={id("clausula")} className="text-xs">
            Cláusula{a.tipo === "outro" ? " (opcional)" : ""}
          </Label>
          <Input
            id={id("clausula")}
            inputMode="numeric"
            className="h-8"
            placeholder="Ex.: 2"
            value={a.clausula}
            onChange={(e) => onChange({ clausula: e.target.value })}
            data-testid={`aditivo-clausula-${a.tipo}-${aditivoId}`}
          />
        </div>
        <p className="self-end pb-1 text-[11px] text-muted-foreground">
          Número da cláusula do contrato original que esta alteração muda (1 = Primeira).
        </p>
      </div>

      {a.tipo === "pagamento" && (
        <>
          <div className="space-y-1">
            <Label htmlFor={id("novo-valor")} className="text-xs">
              Novo preço (R$) — só se o valor do negócio muda
            </Label>
            <Input
              id={id("novo-valor")}
              className="h-8 sm:w-56"
              placeholder="0,00"
              value={a.novoValor}
              onChange={(e) => onChange({ novoValor: e.target.value })}
              data-testid={`aditivo-novo-valor-${aditivoId}`}
            />
          </div>
          {children}
        </>
      )}

      {a.tipo === "posse" && (
        <div className="space-y-2">
          <div className="flex flex-wrap items-end gap-3">
            <div className="space-y-1">
              <Label htmlFor={id("data")} className="text-xs">
                {a.precaria ? "Posse a partir de" : "Posse definitiva em"}
              </Label>
              <Input
                id={id("data")}
                type="date"
                className="h-8 w-44"
                value={a.data}
                onChange={(e) => onChange({ data: e.target.value })}
                data-testid={`aditivo-posse-data-${aditivoId}`}
              />
            </div>
            <div className="flex items-center gap-2 pb-1.5">
              <Switch
                id={id("precaria")}
                checked={a.precaria}
                onCheckedChange={(v) => onChange({ precaria: v })}
                data-testid={`aditivo-posse-precaria-${aditivoId}`}
              />
              <Label htmlFor={id("precaria")} className="text-xs font-normal">
                Posse precária (para uma finalidade)
              </Label>
            </div>
          </div>
          {a.precaria && (
            <div className="space-y-1">
              <Label htmlFor={id("finalidade")} className="text-xs">
                Finalidade
              </Label>
              <Input
                id={id("finalidade")}
                className="h-8"
                maxLength={FINALIDADE_MAX}
                placeholder="Ex.: a medição para os móveis planejados"
                value={a.finalidade}
                onChange={(e) => onChange({ finalidade: e.target.value })}
                data-testid={`aditivo-posse-finalidade-${aditivoId}`}
              />
            </div>
          )}
        </div>
      )}

      {a.tipo === "comissao" && (
        <div className="grid gap-2 sm:grid-cols-3">
          <div className="space-y-1">
            <Label htmlFor={id("parcela-corretagem")} className="text-xs">
              Parcela da corretagem
            </Label>
            <Input
              id={id("parcela-corretagem")}
              inputMode="numeric"
              className="h-8"
              value={a.parcelaCorretagem}
              onChange={(e) => onChange({ parcelaCorretagem: e.target.value })}
              data-testid={`aditivo-comissao-parcela-corretagem-${aditivoId}`}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor={id("marco")} className="text-xs">
              Quando é paga
            </Label>
            <Select value={a.marco} onValueChange={(v) => onChange({ marco: v as ComissaoMarco })}>
              <SelectTrigger id={id("marco")} className="h-8" data-testid={`aditivo-comissao-marco-${aditivoId}`}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(Object.keys(COMISSAO_MARCO_LABEL) as ComissaoMarco[]).map((m) => (
                  <SelectItem key={m} value={m}>
                    {COMISSAO_MARCO_LABEL[m]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {a.marco === "parcela" && (
            <div className="space-y-1">
              <Label htmlFor={id("parcela-numero")} className="text-xs">
                Nº da parcela
              </Label>
              <Input
                id={id("parcela-numero")}
                inputMode="numeric"
                className="h-8"
                value={a.parcelaNumero}
                onChange={(e) => onChange({ parcelaNumero: e.target.value })}
                data-testid={`aditivo-comissao-parcela-numero-${aditivoId}`}
              />
              <p className="text-[11px] text-muted-foreground">
                {temPagamento
                  ? "Número no novo cronograma deste aditivo."
                  : "Número no cronograma do contrato original."}
              </p>
            </div>
          )}
          {a.marco === "data" && (
            <div className="space-y-1">
              <Label htmlFor={id("data")} className="text-xs">
                Data
              </Label>
              <Input
                id={id("data")}
                type="date"
                className="h-8"
                value={a.data}
                onChange={(e) => onChange({ data: e.target.value })}
                data-testid={`aditivo-comissao-data-${aditivoId}`}
              />
            </div>
          )}
        </div>
      )}

      {a.tipo === "outro" && (
        <div className="space-y-2">
          <div className="space-y-1">
            <Label htmlFor={id("titulo")} className="text-xs">
              Título da cláusula
            </Label>
            <Input
              id={id("titulo")}
              className="h-8"
              maxLength={TITULO_MAX}
              placeholder="Ex.: Da trava de dados bancários"
              value={a.titulo}
              onChange={(e) => onChange({ titulo: e.target.value })}
              data-testid={`aditivo-outro-titulo-${aditivoId}`}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor={id("texto")} className="text-xs">
              Texto (cada linha vira um parágrafo)
            </Label>
            <Textarea
              id={id("texto")}
              rows={4}
              maxLength={TEXTO_MAX}
              value={a.texto}
              onChange={(e) => onChange({ texto: e.target.value })}
              data-testid={`aditivo-outro-texto-${aditivoId}`}
            />
          </div>
          <p className="text-[11px] text-amber-700">
            Texto livre é sempre conferido na revisão jurídica.
          </p>
        </div>
      )}

      {erros.length > 0 && (
        <ul className="space-y-0.5" data-testid={`aditivo-alteracao-erros-${a.tipo}-${aditivoId}`}>
          {erros.map((e) => (
            <li key={e} className="text-xs text-destructive">
              {e}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ─── The restated schedule (pagamento) ─────────────────────────────────────

function ParcelasAditivoEditor({
  aditivoId,
  parcelas,
  favorecidos,
  onChange,
}: {
  aditivoId: string;
  parcelas: ParcelaDraftRow[];
  favorecidos: FavorecidoOpcao[];
  onChange: (parcelas: ParcelaDraftRow[]) => void;
}) {
  const [dialogAberto, setDialogAberto] = useState(false);
  const [editando, setEditando] = useState<ParcelaDraftRow | null>(null);
  const nomeFavorecido = (id: string | null) => favorecidos.find((f) => f.id === id)?.nome ?? "—";
  // DISPLAY-ONLY sum (the gate checks it against the price exactly).
  const soma = parcelas.reduce((acc, p) => acc + Number(p.valor || 0), 0);

  function mover(i: number, delta: number) {
    const j = i + delta;
    if (j < 0 || j >= parcelas.length) return;
    const nova = [...parcelas];
    [nova[i], nova[j]] = [nova[j], nova[i]];
    onChange(nova);
  }

  return (
    <div className="space-y-1.5" data-testid={`aditivo-parcelas-${aditivoId}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs font-medium">Novo cronograma de pagamento</p>
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="h-7 text-xs"
          onClick={() => {
            setEditando(null);
            setDialogAberto(true);
          }}
          data-testid={`aditivo-parcela-nova-${aditivoId}`}
        >
          <Plus className="mr-1 h-3 w-3" />
          Nova parcela
        </Button>
      </div>
      {parcelas.length === 0 ? (
        <p className="text-xs text-muted-foreground">
          O pagamento é reescrito por inteiro: inclua todas as parcelas, na ordem em que serão pagas.
        </p>
      ) : (
        <>
          <ol className="space-y-1">
            {parcelas.map((p, i) => (
              <li
                key={p.uid}
                className="flex flex-wrap items-center justify-between gap-2 rounded border px-2 py-1 text-xs"
                data-testid={`aditivo-parcela-${aditivoId}-${i}`}
              >
                <span className="min-w-0">
                  <span className="font-medium">Parcela {String(i + 1).padStart(2, "0")}</span>
                  {" · "}
                  {PARCELA_TIPO_LABELS[p.tipo]} · {exibirMoeda(p.valor)} ·{" "}
                  {exibirData(p.vencimento) ?? p.evento ?? "sem vencimento"}
                  {p.forma_pagamento ? ` · ${p.forma_pagamento}` : ""} · {nomeFavorecido(p.favorecido_id)}
                  {p.confissao_divida && (
                    <Badge variant="outline" className="ml-1.5 text-[10px]">
                      Confissão de dívida
                    </Badge>
                  )}
                </span>
                <span className="flex shrink-0 items-center gap-0.5">
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="h-7 w-7 p-0"
                    disabled={i === 0}
                    onClick={() => mover(i, -1)}
                    aria-label="Mover parcela para cima"
                  >
                    <ArrowUp className="h-3.5 w-3.5" />
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="h-7 w-7 p-0"
                    disabled={i === parcelas.length - 1}
                    onClick={() => mover(i, 1)}
                    aria-label="Mover parcela para baixo"
                  >
                    <ArrowDown className="h-3.5 w-3.5" />
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="h-7 w-7 p-0"
                    onClick={() => {
                      setEditando(p);
                      setDialogAberto(true);
                    }}
                    aria-label="Editar parcela"
                  >
                    <Pencil className="h-3.5 w-3.5" />
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="h-7 w-7 p-0"
                    onClick={() => onChange(parcelas.filter((x) => x.uid !== p.uid))}
                    aria-label="Remover parcela"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </span>
              </li>
            ))}
          </ol>
          <p className="text-xs text-muted-foreground" data-testid={`aditivo-parcelas-soma-${aditivoId}`}>
            Soma das parcelas: {exibirMoeda(String(soma))}
          </p>
        </>
      )}
      <ParcelaFormDialog
        open={dialogAberto}
        onOpenChange={setDialogAberto}
        parcela={editando}
        favorecidos={favorecidos}
        mostrarDisparaCorretagem={false}
        saving={false}
        error={null}
        onSubmit={(payload) => {
          const linha: ParcelaDraftRow = {
            uid: editando?.uid ?? novoUid(),
            tipo: payload.tipo as ParcelaAditivoTipo,
            valor: payload.valor,
            vencimento: payload.vencimento ?? null,
            evento: payload.evento ?? null,
            forma_pagamento: payload.forma_pagamento ?? null,
            favorecido_id: payload.favorecido_id ?? null,
            confissao_divida: !!payload.confissao_divida,
          };
          onChange(
            editando ? parcelas.map((x) => (x.uid === editando.uid ? linha : x)) : [...parcelas, linha],
          );
          setDialogAberto(false);
        }}
      />
    </div>
  );
}

// ─── Read-only (signed / cancelled) ────────────────────────────────────────

function AditivoResumo({
  aditivo,
  favorecidos,
}: {
  aditivo: AditivoOut;
  favorecidos: FavorecidoOpcao[];
}) {
  const nomeFavorecido = (id: string | null) => favorecidos.find((f) => f.id === id)?.nome ?? "—";
  const parcelas = [...aditivo.parcelas].sort((a, b) => a.ordem - b.ordem);
  return (
    <div className="space-y-1.5 text-xs" data-testid={`aditivo-resumo-${aditivo.id}`}>
      <p className="text-muted-foreground">
        {ADITIVO_ESTILO_LABEL[aditivo.estilo]} · assinatura{" "}
        {MODALIDADE_ASSINATURA_LABEL[aditivo.modalidade_assinatura].toLowerCase()}
        {aditivo.assinatura_data ? ` · datado de ${exibirData(aditivo.assinatura_data)}` : ""} — não
        pode mais ser alterado.
      </p>
      <ul className="ml-3 list-disc space-y-0.5">
        {aditivo.alteracoes.map((a, i) => (
          <li key={`${a.tipo}-${i}`}>
            <span className="font-medium">{ALTERACAO_TIPO_LABEL[a.tipo]}</span>
            {a.clausula_alvo ? ` (cláusula ${a.clausula_alvo})` : ""}
            {a.tipo === "pagamento" && a.novo_valor ? ` — novo preço ${exibirMoeda(a.novo_valor)}` : ""}
            {a.tipo === "posse"
              ? ` — ${a.precaria ? `precária a partir de ${exibirData(a.data)}: ${a.finalidade ?? ""}` : `definitiva em ${exibirData(a.data)}`}`
              : ""}
            {a.tipo === "comissao" ? ` — ${a.parcela_corretagem}ª parcela: ${COMISSAO_MARCO_LABEL[a.marco].toLowerCase()}` : ""}
            {a.tipo === "outro" ? ` — ${a.titulo}` : ""}
          </li>
        ))}
      </ul>
      {parcelas.length > 0 && (
        <ol className="ml-3 space-y-0.5">
          {parcelas.map((p, i) => (
            <li key={p.id}>
              Parcela {String(i + 1).padStart(2, "0")} · {PARCELA_TIPO_LABELS[p.tipo]} ·{" "}
              {exibirMoeda(p.valor)} · {exibirData(p.vencimento) ?? p.evento ?? "—"} ·{" "}
              {nomeFavorecido(p.favorecido_id)}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

export default AditivoEditor;

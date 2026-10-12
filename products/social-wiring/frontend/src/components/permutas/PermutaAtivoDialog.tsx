/**
 * PermutaAtivoDialog — register or edit one swap intent (`permuta_ativos`).
 *
 * The payload is `AtivoCreateBody` / `AtivoPatchBody` (backend schemas.py),
 * which is a `StrictHttpModel`: an unknown key is a 422, so this form sends
 * ONLY fields that model declares. `interesses_descricao` in particular is
 * NOT editable — it is the derived copy of what was last embedded; the free
 * text the semantic matching actually reads is `observacoes`
 * (`adapter.texto_interesses_para_embedding` leads with it).
 *
 * PATCH semantics (router `_dump` → `exclude_unset`): an omitted key is left
 * alone, an explicit `null` clears it. On edit the form sends every field it
 * shows — blank ⇒ `null`, because the operator just saw it and emptied it —
 * and never sends fields it does not show (cep, logradouro, …), so those keep
 * their stored values. `interesses` is always sent and REPLACES the set
 * (`atualizar_ativo`); fields of an interest this form does not display
 * (marca/modelo/ano/observações) are carried through untouched.
 *
 * The imóvel picker REUSES `ImovelBuscaTypeahead` (registry ∪ mirror) rather
 * than growing a fourth código typeahead.
 */
import { useEffect, useState, type FormEvent } from "react";
import { Loader2, Plus, Trash2, X } from "lucide-react";

import {
  NATUREZA_LABELS,
  STATUS_ATIVO_LABELS,
  type AtivoPayload,
  type InteressePayload,
  type Natureza,
  type PermutaAtivo,
  type StatusAtivo,
} from "@/hooks/usePermutas";
import { ImovelBuscaTypeahead } from "@/components/interesses/ImovelBuscaTypeahead";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

const SELECT_CLASSE =
  "flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring";

// ─── Form state (strings in, typed payload out) ─────────────────────────────

interface InteresseForm {
  tipo: string;
  tipo_imovel: string;
  cidade: string;
  bairro: string;
  zona: string;
  valor_minimo: string;
  valor_maximo: string;
  /** Fields of an existing interest this form does not display — sent back
   *  unchanged so a replace-on-save does not silently drop them. */
  resto: InteressePayload;
}

interface AtivoForm {
  natureza: Natureza;
  status: StatusAtivo;
  imovel_codigo: string;
  codigo: string;
  tipo_imovel: string;
  bairro: string;
  cidade: string;
  uf: string;
  valor: string;
  proprietario_nome: string;
  proprietario_telefone: string;
  proprietario_email: string;
  faixa_preco_min: string;
  faixa_preco_max: string;
  regiao_preferida: string;
  aceita_completar_diferenca: boolean;
  limite_complemento: string;
  percentual_min: string;
  percentual_max: string;
  observacoes: string;
  interesses: InteresseForm[];
}

const texto = (v: unknown): string => (v == null ? "" : String(v));

function interesseVazio(): InteresseForm {
  return {
    tipo: "imovel",
    tipo_imovel: "",
    cidade: "",
    bairro: "",
    zona: "",
    valor_minimo: "",
    valor_maximo: "",
    resto: {},
  };
}

function formDoAtivo(ativo: PermutaAtivo | null): AtivoForm {
  return {
    natureza: ativo?.natureza ?? "imovel",
    status: ((ativo?.status as StatusAtivo) || "ativo") as StatusAtivo,
    imovel_codigo: texto(ativo?.imovel_codigo),
    codigo: texto(ativo?.codigo),
    tipo_imovel: texto(ativo?.tipo_imovel),
    bairro: texto(ativo?.bairro),
    cidade: texto(ativo?.cidade),
    uf: texto(ativo?.uf),
    valor: texto(ativo?.valor),
    proprietario_nome: texto(ativo?.proprietario_nome),
    proprietario_telefone: texto(ativo?.proprietario_telefone),
    proprietario_email: texto(ativo?.proprietario_email),
    faixa_preco_min: texto(ativo?.faixa_preco_min),
    faixa_preco_max: texto(ativo?.faixa_preco_max),
    regiao_preferida: (ativo?.regiao_preferida ?? []).join(", "),
    aceita_completar_diferenca: Boolean(ativo?.aceita_completar_diferenca),
    limite_complemento: texto(ativo?.limite_complemento),
    percentual_min: texto(ativo?.percentual_min),
    percentual_max: texto(ativo?.percentual_max),
    observacoes: texto(ativo?.observacoes),
    interesses: (ativo?.interesses ?? []).map((i) => {
      // Strip the row identity — interests are replaced, not merged.
      const { id: _id, ...campos } = i as typeof i & { ativo_id?: string };
      delete (campos as { ativo_id?: string }).ativo_id;
      return {
        tipo: texto(i.tipo) || "imovel",
        tipo_imovel: texto(i.tipo_imovel),
        cidade: texto(i.cidade),
        bairro: texto(i.bairro),
        zona: texto(i.zona),
        valor_minimo: texto(i.valor_minimo),
        valor_maximo: texto(i.valor_maximo),
        resto: campos as InteressePayload,
      };
    }),
  };
}

const str = (v: string): string | null => (v.trim() ? v.trim() : null);

function num(v: string): number | null {
  const t = v.trim();
  if (!t) return null;
  const n = Number(t);
  return Number.isFinite(n) ? n : NaN;
}

function int(v: string): number | null {
  const n = num(v);
  return n == null || Number.isNaN(n) ? n : Math.round(n);
}

/** Client-side checks that would otherwise come back as a 400/422 — or,
 *  worse, be accepted and silently widen what the engine matches. */
function validarForm(f: AtivoForm): string | null {
  if (f.natureza === "imovel" && !f.imovel_codigo.trim()) {
    return "Escolha o imóvel do catálogo (código) para uma permuta de imóvel do catálogo.";
  }
  const numericos: [string, string][] = [
    ["Valor", f.valor],
    ["Faixa de preço mínima", f.faixa_preco_min],
    ["Faixa de preço máxima", f.faixa_preco_max],
    ["Limite de complemento", f.limite_complemento],
    ["Percentual mínimo", f.percentual_min],
    ["Percentual máximo", f.percentual_max],
  ];
  for (const [rotulo, v] of numericos) {
    if (Number.isNaN(num(v))) return `${rotulo}: informe um número.`;
  }
  const fmin = num(f.faixa_preco_min);
  const fmax = num(f.faixa_preco_max);
  if (fmin != null && fmax != null && fmin > fmax) {
    return "A faixa de preço mínima é maior que a máxima.";
  }
  const pmin = num(f.percentual_min);
  const pmax = num(f.percentual_max);
  for (const p of [pmin, pmax]) {
    if (p != null && (p < 0 || p > 100)) return "Percentuais devem estar entre 0 e 100.";
  }
  if (pmin != null && pmax != null && pmin > pmax) {
    return "O percentual mínimo é maior que o máximo.";
  }
  for (const [idx, i] of f.interesses.entries()) {
    const vmin = num(i.valor_minimo);
    const vmax = num(i.valor_maximo);
    if (Number.isNaN(vmin) || Number.isNaN(vmax)) {
      return `Interesse ${idx + 1}: valores devem ser números.`;
    }
    if (vmin != null && vmax != null && vmin > vmax) {
      return `Interesse ${idx + 1}: valor mínimo maior que o máximo.`;
    }
  }
  return null;
}

/** Build the request body. `criar` drops empty fields (nothing to clear);
 *  an edit sends them as `null` (the operator emptied a field they saw). */
function montarPayload(f: AtivoForm, modo: "criar" | "editar"): AtivoPayload {
  const ehCatalogo = f.natureza === "imovel";
  const corpo: AtivoPayload = {
    natureza: f.natureza,
    status: f.status,
    imovel_codigo: ehCatalogo ? str(f.imovel_codigo) : null,
    codigo: str(f.codigo),
    proprietario_nome: str(f.proprietario_nome),
    proprietario_telefone: str(f.proprietario_telefone),
    proprietario_email: str(f.proprietario_email),
    faixa_preco_min: num(f.faixa_preco_min),
    faixa_preco_max: num(f.faixa_preco_max),
    regiao_preferida: f.regiao_preferida
      .split(",")
      .map((r) => r.trim())
      .filter(Boolean),
    aceita_completar_diferenca: f.aceita_completar_diferenca,
    limite_complemento: f.aceita_completar_diferenca ? num(f.limite_complemento) : null,
    percentual_min: int(f.percentual_min),
    percentual_max: int(f.percentual_max),
    observacoes: str(f.observacoes),
    interesses: f.interesses.map((i) => {
      const linha: InteressePayload = {
        ...i.resto,
        tipo: i.tipo || "imovel",
        tipo_imovel: str(i.tipo_imovel),
        cidade: str(i.cidade),
        bairro: str(i.bairro),
        zona: str(i.zona),
        valor_minimo: num(i.valor_minimo),
        valor_maximo: num(i.valor_maximo),
      };
      return linha;
    }),
  };
  // A catalog imóvel's description lives in the catalog; only a property or
  // car BROUGHT as currency carries its own snapshot (migration 101).
  if (!ehCatalogo) {
    corpo.tipo_imovel = str(f.tipo_imovel);
    corpo.bairro = str(f.bairro);
    corpo.cidade = str(f.cidade);
    corpo.uf = str(f.uf);
    corpo.valor = num(f.valor);
  }
  if (modo === "criar") {
    for (const k of Object.keys(corpo) as (keyof AtivoPayload)[]) {
      const v = corpo[k];
      if (v == null || (Array.isArray(v) && v.length === 0)) delete corpo[k];
    }
    if (corpo.aceita_completar_diferenca === false) delete corpo.aceita_completar_diferenca;
  }
  return corpo;
}

// ─── Component ──────────────────────────────────────────────────────────────

export interface PermutaAtivoDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** `null` = register a new ativo. */
  ativo: PermutaAtivo | null;
  salvando: boolean;
  /** Rejects with the server error — the dialog shows its message inline. */
  onSalvar: (payload: AtivoPayload) => Promise<void>;
}

function Campo({
  id,
  rotulo,
  children,
  ajuda,
}: {
  id: string;
  rotulo: string;
  children: React.ReactNode;
  ajuda?: string;
}) {
  return (
    <div className="space-y-1">
      <Label htmlFor={id}>{rotulo}</Label>
      {children}
      {ajuda && <p className="text-xs text-muted-foreground">{ajuda}</p>}
    </div>
  );
}

export function PermutaAtivoDialog({
  open,
  onOpenChange,
  ativo,
  salvando,
  onSalvar,
}: PermutaAtivoDialogProps) {
  const [form, setForm] = useState<AtivoForm>(() => formDoAtivo(ativo));
  const [erro, setErro] = useState<string | null>(null);
  const editando = ativo !== null;

  // Re-seed whenever the dialog opens on a (possibly different) ativo.
  useEffect(() => {
    if (open) {
      setForm(formDoAtivo(ativo));
      setErro(null);
    }
  }, [open, ativo]);

  function set<K extends keyof AtivoForm>(k: K, v: AtivoForm[K]) {
    setForm((f) => ({ ...f, [k]: v }));
  }

  function setInteresse(idx: number, patch: Partial<InteresseForm>) {
    setForm((f) => ({
      ...f,
      interesses: f.interesses.map((i, n) => (n === idx ? { ...i, ...patch } : i)),
    }));
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const invalido = validarForm(form);
    if (invalido) {
      setErro(invalido);
      return;
    }
    setErro(null);
    try {
      await onSalvar(montarPayload(form, editando ? "editar" : "criar"));
    } catch (err) {
      const msg = (err as { message?: string } | null)?.message;
      setErro(msg && msg.trim() ? msg : "Não foi possível salvar. Tente novamente.");
    }
  }

  const ehCatalogo = form.natureza === "imovel";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="max-h-[90vh] overflow-y-auto sm:max-w-2xl"
        data-testid="permuta-ativo-dialog"
      >
        <DialogHeader>
          <DialogTitle>{editando ? "Editar permuta" : "Nova permuta"}</DialogTitle>
          <DialogDescription>
            Quem está aberto a permuta e o que aceita em troca. Salvar uma edição
            descarta os vetores semânticos deste registro — gere os embeddings de
            novo antes do próximo matching.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-5" noValidate>
          <div className="grid gap-3 sm:grid-cols-2">
            <Campo id="pa-natureza" rotulo="Natureza">
              <select
                id="pa-natureza"
                className={SELECT_CLASSE}
                value={form.natureza}
                onChange={(e) => set("natureza", e.target.value as Natureza)}
              >
                {(Object.keys(NATUREZA_LABELS) as Natureza[]).map((n) => (
                  <option key={n} value={n}>
                    {NATUREZA_LABELS[n]}
                  </option>
                ))}
              </select>
            </Campo>
            <Campo
              id="pa-status"
              rotulo="Status"
              ajuda="Só registros ativos entram no matching."
            >
              <select
                id="pa-status"
                className={SELECT_CLASSE}
                value={form.status}
                onChange={(e) => set("status", e.target.value as StatusAtivo)}
              >
                {(Object.keys(STATUS_ATIVO_LABELS) as StatusAtivo[]).map((s) => (
                  <option key={s} value={s}>
                    {STATUS_ATIVO_LABELS[s]}
                  </option>
                ))}
              </select>
            </Campo>
          </div>

          {ehCatalogo ? (
            <div className="space-y-2">
              <Label>Imóvel do catálogo</Label>
              {form.imovel_codigo ? (
                <div className="flex items-center gap-2 rounded-md border px-3 py-2 text-sm">
                  <span className="font-mono" data-testid="pa-imovel-escolhido">
                    {form.imovel_codigo}
                  </span>
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    className="ml-auto"
                    onClick={() => set("imovel_codigo", "")}
                  >
                    <X className="mr-1 h-3.5 w-3.5" />
                    Trocar
                  </Button>
                </div>
              ) : (
                <ImovelBuscaTypeahead
                  onSelect={(imovel) => set("imovel_codigo", imovel.codigo)}
                />
              )}
              <p className="text-xs text-muted-foreground">
                Localização, valor e características vêm do catálogo.
              </p>
            </div>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2">
              <Campo id="pa-codigo" rotulo="Referência interna">
                <Input id="pa-codigo" value={form.codigo} onChange={(e) => set("codigo", e.target.value)} />
              </Campo>
              <Campo
                id="pa-tipo"
                rotulo={form.natureza === "permuta_automovel" ? "Veículo" : "Tipo de imóvel"}
              >
                <Input
                  id="pa-tipo"
                  value={form.tipo_imovel}
                  onChange={(e) => set("tipo_imovel", e.target.value)}
                />
              </Campo>
              <Campo id="pa-valor" rotulo="Valor (R$)">
                <Input
                  id="pa-valor"
                  inputMode="decimal"
                  value={form.valor}
                  onChange={(e) => set("valor", e.target.value)}
                />
              </Campo>
              <Campo id="pa-bairro" rotulo="Bairro">
                <Input id="pa-bairro" value={form.bairro} onChange={(e) => set("bairro", e.target.value)} />
              </Campo>
              <Campo id="pa-cidade" rotulo="Cidade">
                <Input id="pa-cidade" value={form.cidade} onChange={(e) => set("cidade", e.target.value)} />
              </Campo>
              <Campo id="pa-uf" rotulo="UF">
                <Input id="pa-uf" maxLength={2} value={form.uf} onChange={(e) => set("uf", e.target.value.toUpperCase())} />
              </Campo>
            </div>
          )}

          <fieldset className="space-y-3">
            <legend className="text-sm font-semibold">Proprietário</legend>
            <div className="grid gap-3 sm:grid-cols-3">
              <Campo id="pa-prop-nome" rotulo="Nome">
                <Input
                  id="pa-prop-nome"
                  value={form.proprietario_nome}
                  onChange={(e) => set("proprietario_nome", e.target.value)}
                />
              </Campo>
              <Campo id="pa-prop-tel" rotulo="Telefone">
                <Input
                  id="pa-prop-tel"
                  type="tel"
                  value={form.proprietario_telefone}
                  onChange={(e) => set("proprietario_telefone", e.target.value)}
                />
              </Campo>
              <Campo id="pa-prop-email" rotulo="E-mail">
                <Input
                  id="pa-prop-email"
                  type="email"
                  value={form.proprietario_email}
                  onChange={(e) => set("proprietario_email", e.target.value)}
                />
              </Campo>
            </div>
          </fieldset>

          <fieldset className="space-y-3">
            <legend className="text-sm font-semibold">O que aceita em troca</legend>
            <Campo
              id="pa-observacoes"
              rotulo="Descrição do interesse"
              ajuda="Este texto é o que a análise semântica do matching lê. Escreva as restrições reais: “casa sem escada”, “quintal amplo”, “aceita permuta de 30% a 50% do valor”."
            >
              <Textarea
                id="pa-observacoes"
                rows={3}
                value={form.observacoes}
                onChange={(e) => set("observacoes", e.target.value)}
              />
            </Campo>
            <div className="grid gap-3 sm:grid-cols-2">
              <Campo id="pa-faixa-min" rotulo="Faixa de preço — mínimo (R$)">
                <Input
                  id="pa-faixa-min"
                  inputMode="decimal"
                  value={form.faixa_preco_min}
                  onChange={(e) => set("faixa_preco_min", e.target.value)}
                />
              </Campo>
              <Campo id="pa-faixa-max" rotulo="Faixa de preço — máximo (R$)">
                <Input
                  id="pa-faixa-max"
                  inputMode="decimal"
                  value={form.faixa_preco_max}
                  onChange={(e) => set("faixa_preco_max", e.target.value)}
                />
              </Campo>
              <Campo id="pa-pct-min" rotulo="Permuta cobre — mínimo (%)">
                <Input
                  id="pa-pct-min"
                  inputMode="numeric"
                  value={form.percentual_min}
                  onChange={(e) => set("percentual_min", e.target.value)}
                />
              </Campo>
              <Campo id="pa-pct-max" rotulo="Permuta cobre — máximo (%)">
                <Input
                  id="pa-pct-max"
                  inputMode="numeric"
                  value={form.percentual_max}
                  onChange={(e) => set("percentual_max", e.target.value)}
                />
              </Campo>
            </div>
            <Campo
              id="pa-regiao"
              rotulo="Regiões preferidas"
              ajuda="Separe por vírgula."
            >
              <Input
                id="pa-regiao"
                value={form.regiao_preferida}
                onChange={(e) => set("regiao_preferida", e.target.value)}
              />
            </Campo>
            <div className="flex flex-wrap items-end gap-3">
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={form.aceita_completar_diferenca}
                  onChange={(e) => set("aceita_completar_diferenca", e.target.checked)}
                />
                Aceita completar a diferença
              </label>
              {form.aceita_completar_diferenca && (
                <div className="min-w-[12rem] flex-1">
                  <Campo id="pa-limite" rotulo="Limite do complemento (R$)">
                    <Input
                      id="pa-limite"
                      inputMode="decimal"
                      value={form.limite_complemento}
                      onChange={(e) => set("limite_complemento", e.target.value)}
                    />
                  </Campo>
                </div>
              )}
            </div>
          </fieldset>

          <fieldset className="space-y-3">
            <legend className="text-sm font-semibold">Critérios estruturados</legend>
            {form.interesses.length === 0 && (
              <p className="text-sm text-muted-foreground">
                Nenhum critério. Opcional — a descrição acima já orienta o matching.
              </p>
            )}
            {form.interesses.map((i, idx) => (
              <div
                key={idx}
                className="grid gap-2 rounded-md border p-3 sm:grid-cols-4"
                data-testid="pa-interesse"
              >
                <select
                  aria-label={`Interesse ${idx + 1} — tipo`}
                  className={SELECT_CLASSE}
                  value={i.tipo}
                  onChange={(e) => setInteresse(idx, { tipo: e.target.value })}
                >
                  <option value="imovel">Imóvel</option>
                  <option value="automovel">Automóvel</option>
                </select>
                <Input
                  aria-label={`Interesse ${idx + 1} — tipo de imóvel`}
                  placeholder="Tipo de imóvel"
                  value={i.tipo_imovel}
                  onChange={(e) => setInteresse(idx, { tipo_imovel: e.target.value })}
                />
                <Input
                  aria-label={`Interesse ${idx + 1} — cidade`}
                  placeholder="Cidade"
                  value={i.cidade}
                  onChange={(e) => setInteresse(idx, { cidade: e.target.value })}
                />
                <Input
                  aria-label={`Interesse ${idx + 1} — bairro`}
                  placeholder="Bairro"
                  value={i.bairro}
                  onChange={(e) => setInteresse(idx, { bairro: e.target.value })}
                />
                <Input
                  aria-label={`Interesse ${idx + 1} — zona`}
                  placeholder="Zona"
                  value={i.zona}
                  onChange={(e) => setInteresse(idx, { zona: e.target.value })}
                />
                <Input
                  aria-label={`Interesse ${idx + 1} — valor mínimo`}
                  placeholder="Valor mín. (R$)"
                  inputMode="decimal"
                  value={i.valor_minimo}
                  onChange={(e) => setInteresse(idx, { valor_minimo: e.target.value })}
                />
                <Input
                  aria-label={`Interesse ${idx + 1} — valor máximo`}
                  placeholder="Valor máx. (R$)"
                  inputMode="decimal"
                  value={i.valor_maximo}
                  onChange={(e) => setInteresse(idx, { valor_maximo: e.target.value })}
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  aria-label={`Remover interesse ${idx + 1}`}
                  onClick={() =>
                    setForm((f) => ({
                      ...f,
                      interesses: f.interesses.filter((_, n) => n !== idx),
                    }))
                  }
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            ))}
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() =>
                setForm((f) => ({ ...f, interesses: [...f.interesses, interesseVazio()] }))
              }
            >
              <Plus className="mr-1 h-3.5 w-3.5" />
              Adicionar critério
            </Button>
          </fieldset>

          {erro && (
            <p role="alert" className="rounded-md border border-destructive/40 bg-destructive/10 p-2 text-sm text-destructive">
              {erro}
            </p>
          )}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={salvando}>
              Cancelar
            </Button>
            <Button type="submit" disabled={salvando}>
              {salvando && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {editando ? "Salvar alterações" : "Cadastrar"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export default PermutaAtivoDialog;

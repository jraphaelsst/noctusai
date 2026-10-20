/**
 * Agent Studio — "Qualificação" (Julia v2 CONTRACT §3): the platform qualification STANDARD that every
 * org's Julia is scored against — criteria grouped by scope (`escopo`) and axis (`eixo`) with their
 * options and points, the stages and their rule JSON, and the parameters (offer minimum, batch size,
 * when identity is asked). Platform admin only; one standard, no per-org fork (owner Q2).
 *
 * Editing: draft versions only. Each criterion / stage saves on its own (`PUT .../criterios/{chave}`)
 * and the server's full-version answer repaints the tab. Publish runs the server validation and shows
 * every rule error (422 `regras_invalidas`) with its path — never a partial publish.
 */
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { CheckCircle2, FilePlus2, Plus, Rocket, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { useConfirm } from "@noctusai/lib/components";
import { Badge, Button, EmptyState, Select, Switch, Textarea } from "@noctusai/lib/design-system";
import type {
  PadraoVersao,
  QualCriterio,
  QualCriterioInput,
  QualEstagio,
  QualEstagioInput,
  QualOpcao,
  QualParametros,
  RegraErro,
} from "@/api/studio/types-julia";
import { RestrictedNotice, SaveError } from "@/components/studio/ConteudoChrome";
import { JsonField } from "@/components/studio/JsonField";
import { StudioLoading } from "@/components/studio/StudioStates";
import { useBuffered } from "@/components/studio/useBuffered";
import {
  useCriarRascunhoPadrao,
  useDescartarRascunhoPadrao,
  usePadraoVersao,
  usePadraoVersoes,
  usePadroes,
  usePublicarPadrao,
  useRemoverCriterio,
  useRemoverEstagio,
  useSalvarCriterio,
  useSalvarEstagio,
  useSalvarParametros,
  useValidarPadrao,
} from "@/hooks/studio/useQualificacao";
import { ApiError, errorMessage } from "@/lib/errors";

const GRUPOS = ["prontidao", "bloqueios", "interesse", "perfil_imovel", "perfil_vida", "contato"] as const;
const TIPOS = ["enum", "multi", "bool", "numero", "faixa", "texto", "imovel_ref", "derivado", "identificacao"] as const;
const CHAVE_RE = /^[a-z][a-z0-9_]{1,63}$/;
const INPUT_CLASS =
  "h-9 w-full rounded-md border border-input bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50";

function Conflito({ onReload }: { onReload: () => void }) {
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-2 text-xs text-amber-700" role="alert" data-testid="qual-conflito">
      Este item mudou no servidor enquanto você editava.
      <Button size="sm" variant="outline" onClick={onReload}>Descartar as minhas e recarregar</Button>
    </div>
  );
}

function RegraErros({ erros }: { erros: RegraErro[] }) {
  if (erros.length === 0) return null;
  return (
    <div className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive" role="alert" data-testid="qual-regra-erros">
      <p className="font-semibold">A versão tem regras inválidas:</p>
      <ul className="ml-4 list-disc">
        {erros.map((e, i) => (
          <li key={`${e.code}-${e.path}-${i}`}>
            <span className="font-mono text-xs">{e.path}</span> — {e.detail} <span className="text-xs">({e.code})</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

// ── criterion ────────────────────────────────────────────────────────────────

function OpcoesEditor({ opcoes, onChange, disabled }: { opcoes: QualOpcao[]; onChange: (o: QualOpcao[]) => void; disabled: boolean }) {
  const patch = (i: number, p: Partial<QualOpcao>) => onChange(opcoes.map((o, j) => (j === i ? { ...o, ...p } : o)));
  return (
    <div className="space-y-2" data-testid="criterio-opcoes">
      <p className="text-xs font-medium">Opções</p>
      {opcoes.map((o, i) => (
        <div key={i} className="grid gap-2 rounded-md border border-border p-2 sm:grid-cols-[10rem_1fr_1fr_auto]">
          <input aria-label={`Valor da opção ${i + 1}`} className={`${INPUT_CLASS} font-mono`} disabled={disabled} value={o.valor} onChange={(e) => patch(i, { valor: e.target.value })} />
          <input aria-label={`Rótulo da opção ${i + 1}`} className={INPUT_CLASS} disabled={disabled} value={o.rotulo} onChange={(e) => patch(i, { rotulo: e.target.value })} />
          <input
            aria-label={`Sinônimos da opção ${i + 1}`}
            className={INPUT_CLASS}
            disabled={disabled}
            placeholder="sinônimos separados por vírgula"
            value={o.sinonimos.join(", ")}
            onChange={(e) => patch(i, { sinonimos: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) })}
          />
          {!disabled && (
            <button type="button" className="text-muted-foreground hover:text-destructive" aria-label={`Remover opção ${i + 1}`} onClick={() => onChange(opcoes.filter((_, j) => j !== i))}>
              <Trash2 className="h-4 w-4" />
            </button>
          )}
          <Textarea className="sm:col-span-4" rows={2} aria-label={`Descrição da opção ${i + 1} para o modelo`} disabled={disabled} value={o.descricao_modelo} onChange={(e) => patch(i, { descricao_modelo: e.target.value })} />
        </div>
      ))}
      {!disabled && (
        <Button size="sm" variant="outline" onClick={() => onChange([...opcoes, { valor: "", rotulo: "", descricao_modelo: "", sinonimos: [] }])}>
          <Plus className="mr-1 h-3.5 w-3.5" /> Adicionar opção
        </Button>
      )}
    </div>
  );
}

function CriterioEditor({ criterio, versaoId, padrao, editavel }: { criterio: QualCriterio; versaoId: string; padrao: string; editavel: boolean }) {
  const confirm = useConfirm();
  const salvar = useSalvarCriterio(padrao, versaoId);
  const remover = useRemoverCriterio(padrao, versaoId);
  const buf = useBuffered<QualCriterio>(criterio);
  const [jsonErr, setJsonErr] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const c = buf.value;
  const patch = (p: Partial<QualCriterio>) => buf.setValue({ ...c, ...p });

  async function handleSave() {
    setErro(null);
    const { chave, ...input } = c;
    try {
      await salvar.mutateAsync({ chave, criterio: input as QualCriterioInput });
      buf.markSaved(c);
      toast.success(`Critério ${chave} salvo.`);
    } catch (err) {
      setErro(errorMessage(err));
    }
  }

  async function handleRemove() {
    if (!(await confirm({ title: `Remover o critério ${c.chave}?`, tone: "danger", confirmLabel: "Remover" }))) return;
    try {
      await remover.mutateAsync({ chave: c.chave });
    } catch (err) {
      setErro(errorMessage(err));
    }
  }

  return (
    <details className="rounded-lg border border-border bg-card" data-testid={`criterio-${c.chave}`}>
      <summary className="flex cursor-pointer flex-wrap items-center gap-2 px-3 py-2 text-sm">
        <span className="font-mono font-semibold">{c.chave}</span>
        <span className="text-muted-foreground">{c.rotulo}</span>
        <Badge variant="outline">{c.tipo}</Badge>
        {c.eixo && <Badge variant="muted">eixo {c.eixo}</Badge>}
        {!c.ativo && <Badge variant="muted">inativo</Badge>}
        {buf.dirty && <Badge variant="outline">não salvo</Badge>}
      </summary>
      <div className="space-y-3 border-t border-border p-3">
        {buf.conflict && <Conflito onReload={buf.reload} />}
        <div className="grid gap-3 sm:grid-cols-3">
          <div className="sm:col-span-2">
            <label htmlFor={`cr-${c.chave}`} className="mb-1 block text-xs font-medium">Rótulo</label>
            <input id={`cr-${c.chave}`} className={INPUT_CLASS} disabled={!editavel} value={c.rotulo} onChange={(e) => patch({ rotulo: e.target.value })} />
          </div>
          <div>
            <label htmlFor={`cg-${c.chave}`} className="mb-1 block text-xs font-medium">Grupo</label>
            <Select id={`cg-${c.chave}`} disabled={!editavel} value={c.grupo} onChange={(e) => patch({ grupo: e.target.value })}>
              {GRUPOS.map((g) => <option key={g} value={g}>{g}</option>)}
            </Select>
          </div>
          <div>
            <label htmlFor={`ct-${c.chave}`} className="mb-1 block text-xs font-medium">Tipo</label>
            <Select id={`ct-${c.chave}`} disabled={!editavel} value={c.tipo} onChange={(e) => patch({ tipo: e.target.value })}>
              {TIPOS.map((t) => <option key={t} value={t}>{t}</option>)}
            </Select>
          </div>
          <div>
            <label htmlFor={`ce-${c.chave}`} className="mb-1 block text-xs font-medium">Escopo</label>
            <input id={`ce-${c.chave}`} className={INPUT_CLASS} disabled={!editavel} placeholder="sdr, financeiro, juridico…" value={c.escopo ?? ""} onChange={(e) => patch({ escopo: e.target.value || null })} />
          </div>
          <div>
            <label htmlFor={`cx-${c.chave}`} className="mb-1 block text-xs font-medium">Eixo</label>
            <input id={`cx-${c.chave}`} className={INPUT_CLASS} disabled={!editavel} placeholder="fit, intencao, urgencia…" value={c.eixo ?? ""} onChange={(e) => patch({ eixo: e.target.value || null })} />
          </div>
          <div>
            <label htmlFor={`cv-${c.chave}`} className="mb-1 block text-xs font-medium">Validade (dias)</label>
            <input id={`cv-${c.chave}`} type="number" min={1} max={3650} className={INPUT_CLASS} disabled={!editavel} value={c.validade_dias ?? ""} onChange={(e) => patch({ validade_dias: e.target.value ? Number(e.target.value) : null })} />
          </div>
          <div>
            <label htmlFor={`co-${c.chave}`} className="mb-1 block text-xs font-medium">Ordem</label>
            <input id={`co-${c.chave}`} type="number" className={INPUT_CLASS} disabled={!editavel} value={c.ordem} onChange={(e) => patch({ ordem: Number(e.target.value) })} />
          </div>
          <div>
            <label htmlFor={`cs-${c.chave}`} className="mb-1 block text-xs font-medium">Dado sensível</label>
            <Select id={`cs-${c.chave}`} disabled={!editavel} value={c.sensivel ?? ""} onChange={(e) => patch({ sensivel: (e.target.value || null) as QualCriterio["sensivel"] })}>
              <option value="">Não</option>
              <option value="faixa">Coletar só em faixa</option>
              <option value="nao_coletar">Nunca coletar</option>
            </Select>
          </div>
          <label className="flex items-center gap-2 self-end text-sm">
            <Switch checked={c.ativo} disabled={!editavel} aria-label={`Ativo: ${c.chave}`} onCheckedChange={(v) => patch({ ativo: v })} /> Ativo
          </label>
        </div>
        <div>
          <label htmlFor={`cd-${c.chave}`} className="mb-1 block text-xs font-medium">Descrição para o modelo</label>
          <Textarea id={`cd-${c.chave}`} rows={3} disabled={!editavel} value={c.descricao_modelo} onChange={(e) => patch({ descricao_modelo: e.target.value })} />
        </div>
        <OpcoesEditor opcoes={c.opcoes} disabled={!editavel} onChange={(opcoes) => patch({ opcoes })} />
        <JsonField
          id={`cp-${c.chave}`}
          label="Pontuação (pontos por opção ou faixas)"
          value={c.pontuacao}
          disabled={!editavel}
          onChange={(v, err) => {
            setJsonErr(err);
            if (err === null) patch({ pontuacao: v as QualCriterio["pontuacao"] });
          }}
        />
        <SaveError message={erro} />
        {editavel && (
          <div className="flex justify-between gap-2">
            <Button size="sm" variant="ghost" onClick={handleRemove} disabled={remover.isPending}>
              <Trash2 className="mr-1 h-3.5 w-3.5" /> Remover critério
            </Button>
            <Button size="sm" variant="primary" disabled={!buf.dirty || !!jsonErr || buf.conflict || salvar.isPending} onClick={handleSave} data-testid={`criterio-salvar-${c.chave}`}>
              {salvar.isPending ? "Salvando..." : "Salvar critério"}
            </Button>
          </div>
        )}
      </div>
    </details>
  );
}

function NovoCriterio({ versaoId, padrao }: { versaoId: string; padrao: string }) {
  const salvar = useSalvarCriterio(padrao, versaoId);
  const [chave, setChave] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  async function add() {
    if (!CHAVE_RE.test(chave)) {
      setErro("A chave usa letras minúsculas, números e _ (ex.: prazo_compra).");
      return;
    }
    setErro(null);
    const novo: QualCriterioInput = {
      grupo: "prontidao", rotulo: chave, descricao_modelo: "", tipo: "enum", opcoes: [], unidade: null, sensivel: null,
      pontuacao: {}, ordem: 0, ativo: true, eixo: null, escopo: "sdr", validade_dias: null,
    };
    try {
      await salvar.mutateAsync({ chave, criterio: novo });
      setChave("");
    } catch (err) {
      setErro(errorMessage(err));
    }
  }
  return (
    <div className="space-y-1">
      <div className="flex items-end gap-2">
        <div className="min-w-[14rem]">
          <label htmlFor="qual-novo-criterio" className="mb-1 block text-xs font-medium">Novo critério</label>
          <input id="qual-novo-criterio" className={`${INPUT_CLASS} font-mono`} value={chave} placeholder="chave_do_criterio" onChange={(e) => setChave(e.target.value.toLowerCase())} />
        </div>
        <Button size="sm" variant="outline" onClick={add} disabled={salvar.isPending}><Plus className="mr-1 h-4 w-4" /> Adicionar critério</Button>
      </div>
      <SaveError message={erro} />
    </div>
  );
}

// ── stage ────────────────────────────────────────────────────────────────────

function EstagioEditor({ estagio, versaoId, padrao, editavel }: { estagio: QualEstagio; versaoId: string; padrao: string; editavel: boolean }) {
  const confirm = useConfirm();
  const salvar = useSalvarEstagio(padrao, versaoId);
  const remover = useRemoverEstagio(padrao, versaoId);
  const buf = useBuffered<QualEstagio>(estagio);
  const [jsonErr, setJsonErr] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const e = buf.value;
  const patch = (p: Partial<QualEstagio>) => buf.setValue({ ...e, ...p });

  async function handleSave() {
    setErro(null);
    const { chave, ...input } = e;
    try {
      await salvar.mutateAsync({ chave, estagio: input as QualEstagioInput });
      buf.markSaved(e);
      toast.success(`Estágio ${chave} salvo.`);
    } catch (err) {
      setErro(errorMessage(err));
    }
  }

  async function handleRemove() {
    if (!(await confirm({ title: `Remover o estágio ${e.chave}?`, tone: "danger", confirmLabel: "Remover" }))) return;
    try {
      await remover.mutateAsync({ chave: e.chave });
    } catch (err) {
      setErro(errorMessage(err));
    }
  }

  return (
    <details className="rounded-lg border border-border bg-card" data-testid={`estagio-${e.chave}`}>
      <summary className="flex cursor-pointer flex-wrap items-center gap-2 px-3 py-2 text-sm">
        <span className="tabular-nums text-muted-foreground">{e.ordem}.</span>
        <span className="font-mono font-semibold">{e.chave}</span>
        <span className="text-muted-foreground">{e.rotulo}</span>
        {e.conclusivo && <Badge variant="default">conclusivo</Badge>}
        {e.terminal && <Badge variant="outline">terminal</Badge>}
        {buf.dirty && <Badge variant="outline">não salvo</Badge>}
      </summary>
      <div className="space-y-3 border-t border-border p-3">
        {buf.conflict && <Conflito onReload={buf.reload} />}
        <div className="grid gap-3 sm:grid-cols-3">
          <div className="sm:col-span-2">
            <label htmlFor={`er-${e.chave}`} className="mb-1 block text-xs font-medium">Rótulo</label>
            <input id={`er-${e.chave}`} className={INPUT_CLASS} disabled={!editavel} value={e.rotulo} onChange={(ev) => patch({ rotulo: ev.target.value })} />
          </div>
          <div>
            <label htmlFor={`eo-${e.chave}`} className="mb-1 block text-xs font-medium">Ordem</label>
            <input id={`eo-${e.chave}`} type="number" className={INPUT_CLASS} disabled={!editavel} value={e.ordem} onChange={(ev) => patch({ ordem: Number(ev.target.value) })} />
          </div>
        </div>
        <div>
          <label htmlFor={`ed-${e.chave}`} className="mb-1 block text-xs font-medium">Descrição</label>
          <Textarea id={`ed-${e.chave}`} rows={2} disabled={!editavel} value={e.descricao} onChange={(ev) => patch({ descricao: ev.target.value })} />
        </div>
        <div className="flex gap-6 text-sm">
          <label className="flex items-center gap-2"><Switch checked={e.conclusivo} disabled={!editavel} aria-label={`Conclusivo: ${e.chave}`} onCheckedChange={(v) => patch({ conclusivo: v })} /> Conclusivo</label>
          <label className="flex items-center gap-2"><Switch checked={e.terminal} disabled={!editavel} aria-label={`Terminal: ${e.chave}`} onCheckedChange={(v) => patch({ terminal: v })} /> Terminal</label>
        </div>
        <JsonField
          id={`ej-${e.chave}`}
          label="Regra (JSON)"
          value={e.regra}
          disabled={!editavel}
          onChange={(v, err) => {
            setJsonErr(err);
            if (err === null) patch({ regra: v as Record<string, unknown> });
          }}
        />
        <SaveError message={erro} />
        {editavel && (
          <div className="flex justify-between gap-2">
            <Button size="sm" variant="ghost" onClick={handleRemove} disabled={remover.isPending}><Trash2 className="mr-1 h-3.5 w-3.5" /> Remover estágio</Button>
            <Button size="sm" variant="primary" disabled={!buf.dirty || !!jsonErr || buf.conflict || salvar.isPending} onClick={handleSave} data-testid={`estagio-salvar-${e.chave}`}>
              {salvar.isPending ? "Salvando..." : "Salvar estágio"}
            </Button>
          </div>
        )}
      </div>
    </details>
  );
}

function NovoEstagio({ versaoId, padrao, proxima }: { versaoId: string; padrao: string; proxima: number }) {
  const salvar = useSalvarEstagio(padrao, versaoId);
  const [chave, setChave] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  async function add() {
    if (!CHAVE_RE.test(chave)) {
      setErro("A chave usa letras minúsculas, números e _ (ex.: lead_pronto).");
      return;
    }
    setErro(null);
    try {
      await salvar.mutateAsync({ chave, estagio: { rotulo: chave, descricao: "", ordem: proxima, regra: {}, conclusivo: false, terminal: false } });
      setChave("");
    } catch (err) {
      setErro(errorMessage(err));
    }
  }
  return (
    <div className="space-y-1">
      <div className="flex items-end gap-2">
        <div className="min-w-[14rem]">
          <label htmlFor="qual-novo-estagio" className="mb-1 block text-xs font-medium">Novo estágio</label>
          <input id="qual-novo-estagio" className={`${INPUT_CLASS} font-mono`} value={chave} placeholder="chave_do_estagio" onChange={(ev) => setChave(ev.target.value.toLowerCase())} />
        </div>
        <Button size="sm" variant="outline" onClick={add} disabled={salvar.isPending}><Plus className="mr-1 h-4 w-4" /> Adicionar estágio</Button>
      </div>
      <SaveError message={erro} />
    </div>
  );
}

// ── parameters ───────────────────────────────────────────────────────────────

function ParametrosEditor({ parametros, versaoId, padrao, editavel }: { parametros: QualParametros; versaoId: string; padrao: string; editavel: boolean }) {
  const salvar = useSalvarParametros(padrao, versaoId);
  const buf = useBuffered<QualParametros>(parametros);
  const [jsonErr, setJsonErr] = useState<Record<string, string | null>>({});
  const [erro, setErro] = useState<string | null>(null);
  const p = buf.value;
  const patch = (x: Partial<QualParametros>) => buf.setValue({ ...p, ...x });
  const invalido = Object.values(jsonErr).some(Boolean);
  const json = (id: keyof QualParametros, label: string, valor: unknown, rows = 4) => (
    <JsonField
      id={`par-${id}`}
      label={label}
      value={valor}
      rows={rows}
      disabled={!editavel}
      onChange={(v, err) => {
        setJsonErr((m) => ({ ...m, [id]: err }));
        if (err === null) patch({ [id]: v } as Partial<QualParametros>);
      }}
    />
  );

  async function handleSave() {
    setErro(null);
    try {
      await salvar.mutateAsync(p);
      buf.markSaved(p);
      toast.success("Parâmetros salvos.");
    } catch (err) {
      setErro(errorMessage(err));
    }
  }

  return (
    <section className="space-y-3 rounded-lg border border-border bg-card p-4" data-testid="qual-parametros">
      <h3 className="text-sm font-semibold">Parâmetros</h3>
      {buf.conflict && <Conflito onReload={buf.reload} />}
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label htmlFor="par-lote" className="mb-1 block text-xs font-medium">Imóveis por lote (1 a 5)</label>
          <input id="par-lote" type="number" min={1} max={5} className={INPUT_CLASS} disabled={!editavel} value={p.lote_ofertas} onChange={(e) => patch({ lote_ofertas: Number(e.target.value) })} />
        </div>
        <div>
          <label htmlFor="par-max" className="mb-1 block text-xs font-medium">Pontuação máxima</label>
          <input id="par-max" type="number" min={1} max={1000} className={INPUT_CLASS} disabled={!editavel} value={p.score_max} onChange={(e) => patch({ score_max: Number(e.target.value) })} />
        </div>
      </div>
      {json("minimo_para_ofertar", "Mínimo para ofertar imóveis (regra)", p.minimo_para_ofertar)}
      {json("pedir_identificacao_quando", "Quando pedir identificação (regra; vazio = a qualquer momento)", p.pedir_identificacao_quando, 3)}
      {json("eixos", "Eixos de pontuação (máximo, multiplicadores, decaimento)", p.eixos, 6)}
      <SaveError message={erro} />
      {editavel && (
        <div className="flex justify-end">
          <Button size="sm" variant="primary" disabled={!buf.dirty || invalido || buf.conflict || salvar.isPending} onClick={handleSave} data-testid="parametros-salvar">
            {salvar.isPending ? "Salvando..." : "Salvar parâmetros"}
          </Button>
        </div>
      )}
    </section>
  );
}

// ── version ──────────────────────────────────────────────────────────────────

function agrupar(criterios: QualCriterio[]): Array<[string, Array<[string, QualCriterio[]]>]> {
  const porEscopo = new Map<string, Map<string, QualCriterio[]>>();
  for (const c of [...criterios].sort((a, b) => a.ordem - b.ordem)) {
    const escopo = c.escopo ?? "todos";
    const eixo = c.eixo ?? "sem eixo";
    const eixos = porEscopo.get(escopo) ?? new Map<string, QualCriterio[]>();
    eixos.set(eixo, [...(eixos.get(eixo) ?? []), c]);
    porEscopo.set(escopo, eixos);
  }
  return [...porEscopo.entries()].map(([escopo, eixos]) => [escopo, [...eixos.entries()]]);
}

function VersaoView({ versao, padrao }: { versao: PadraoVersao; padrao: string }) {
  const editavel = versao.status === "rascunho";
  const validar = useValidarPadrao(versao.id);
  const publicar = usePublicarPadrao(padrao, versao.id);
  const descartar = useDescartarRascunhoPadrao(padrao);
  const confirm = useConfirm();
  const [erros, setErros] = useState<RegraErro[]>([]);
  const [validado, setValidado] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function handleValidar() {
    setErro(null);
    setValidado(false);
    try {
      const r = await validar.mutateAsync();
      setErros(r.erros);
      setValidado(r.ok);
    } catch (err) {
      setErro(errorMessage(err));
    }
  }

  async function handlePublicar() {
    setErro(null);
    setErros([]);
    setValidado(false);
    if (!(await confirm({ title: `Publicar a v${versao.versao} do padrão?`, description: "Vale para todas as organizações assim que publicada.", confirmLabel: "Publicar" }))) return;
    try {
      await publicar.mutateAsync();
      toast.success(`Padrão v${versao.versao} publicado.`);
    } catch (err) {
      if (err instanceof ApiError && err.status === 422 && Array.isArray(err.field("erros"))) {
        setErros(err.field("erros") as RegraErro[]);
        setErro(errorMessage(err));
      } else {
        setErro(errorMessage(err));
      }
    }
  }

  async function handleDescartar() {
    if (!(await confirm({ title: `Descartar o rascunho v${versao.versao}?`, tone: "danger", confirmLabel: "Descartar" }))) return;
    try {
      await descartar.mutateAsync({ versaoId: versao.id });
    } catch (err) {
      setErro(errorMessage(err));
    }
  }

  const grupos = agrupar(versao.criterios);

  return (
    <div className="space-y-4" data-testid="qual-versao">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={editavel ? "default" : "muted"} data-testid="qual-estado">
          {editavel ? `Rascunho v${versao.versao} · editável` : `${versao.status === "publicada" ? "Publicada" : "Arquivada"} v${versao.versao} · somente leitura`}
        </Badge>
        {editavel && (
          <div className="ml-auto flex flex-wrap gap-2">
            <Button size="sm" variant="outline" onClick={handleValidar} disabled={validar.isPending} data-testid="qual-validar"><CheckCircle2 className="mr-1 h-3.5 w-3.5" /> Validar regras</Button>
            <Button size="sm" variant="primary" onClick={handlePublicar} disabled={publicar.isPending} data-testid="qual-publicar"><Rocket className="mr-1 h-3.5 w-3.5" /> Publicar</Button>
            <Button size="sm" variant="ghost" onClick={handleDescartar} disabled={descartar.isPending}><Trash2 className="mr-1 h-3.5 w-3.5" /> Descartar</Button>
          </div>
        )}
      </div>
      {validado && <p className="rounded-md border border-emerald-500/40 bg-emerald-500/10 p-2 text-sm text-emerald-700" data-testid="qual-validacao-ok">As regras estão válidas.</p>}
      <RegraErros erros={erros} />
      <SaveError message={erros.length === 0 ? erro : null} />

      <ParametrosEditor parametros={versao.parametros} versaoId={versao.id} padrao={padrao} editavel={editavel} />

      <section className="space-y-3" data-testid="qual-criterios">
        <h3 className="text-sm font-semibold">Critérios</h3>
        {grupos.length === 0 && <EmptyState message="Esta versão ainda não tem critérios." />}
        {grupos.map(([escopo, eixos]) => (
          <div key={escopo} className="space-y-2" data-testid={`qual-escopo-${escopo}`}>
            <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Escopo: {escopo}</h4>
            {eixos.map(([eixo, cs]) => (
              <div key={eixo} className="space-y-2 pl-2">
                <p className="text-xs text-muted-foreground">Eixo: {eixo}</p>
                {cs.map((c) => (
                  <CriterioEditor key={c.chave} criterio={c} versaoId={versao.id} padrao={padrao} editavel={editavel} />
                ))}
              </div>
            ))}
          </div>
        ))}
        {editavel && <NovoCriterio versaoId={versao.id} padrao={padrao} />}
      </section>

      <section className="space-y-2" data-testid="qual-estagios">
        <h3 className="text-sm font-semibold">Estágios</h3>
        {versao.estagios.length === 0 && <EmptyState message="Esta versão ainda não tem estágios." />}
        {[...versao.estagios].sort((a, b) => a.ordem - b.ordem).map((e) => (
          <EstagioEditor key={e.chave} estagio={e} versaoId={versao.id} padrao={padrao} editavel={editavel} />
        ))}
        {editavel && <NovoEstagio versaoId={versao.id} padrao={padrao} proxima={versao.estagios.length + 1} />}
      </section>
    </div>
  );
}

export default function QualificacaoTab(_props: { agentKey: string }) {
  const [params, setParams] = useSearchParams();
  const padroes = usePadroes();
  const chave = params.get("padrao") ?? padroes.data?.[0]?.chave ?? null;
  const versoes = usePadraoVersoes(chave);
  const rascunho = versoes.data?.find((v) => v.status === "rascunho") ?? null;
  const publicada = versoes.data?.find((v) => v.status === "publicada") ?? null;
  const pedida = params.get("versao");
  const alvo = versoes.data?.find((v) => v.id === pedida) ?? rascunho ?? publicada ?? versoes.data?.[0] ?? null;
  const versao = usePadraoVersao(alvo?.id);
  const criar = useCriarRascunhoPadrao(chave ?? "");
  const [erro, setErro] = useState<string | null>(null);

  if (padroes.showSkeleton) return <StudioLoading rows={4} />;
  if (padroes.isError) return <RestrictedNotice error={padroes.error} />;
  if (!padroes.data || padroes.data.length === 0) return <EmptyState message="Nenhum padrão de qualificação cadastrado." />;

  async function handleCriar() {
    setErro(null);
    try {
      const v = await criar.mutateAsync({ copiar_de: (publicada ?? alvo)?.id });
      setParams({ tab: "qualificacao", padrao: chave ?? "", versao: v.id });
      toast.success(`Rascunho v${v.versao} criado.`);
    } catch (err) {
      setErro(errorMessage(err));
    }
  }

  return (
    <div className="space-y-4" data-testid="qualificacao-tab">
      <div className="flex flex-wrap items-center gap-3">
        <div>
          <label htmlFor="qual-padrao" className="mb-1 block text-xs font-medium">Padrão</label>
          <Select id="qual-padrao" value={chave ?? ""} onChange={(e) => setParams({ tab: "qualificacao", padrao: e.target.value })}>
            {padroes.data.map((p) => <option key={p.id} value={p.chave}>{p.nome}</option>)}
          </Select>
        </div>
        <div>
          <label htmlFor="qual-versao" className="mb-1 block text-xs font-medium">Versão</label>
          <Select id="qual-versao" value={alvo?.id ?? ""} onChange={(e) => setParams({ tab: "qualificacao", padrao: chave ?? "", versao: e.target.value })}>
            {(versoes.data ?? []).map((v) => <option key={v.id} value={v.id}>v{v.versao} · {v.status}</option>)}
          </Select>
        </div>
        {!rascunho && (
          <Button size="sm" variant="outline" className="self-end" onClick={handleCriar} disabled={criar.isPending} data-testid="qual-criar-rascunho">
            <FilePlus2 className="mr-1 h-4 w-4" /> Criar rascunho{alvo ? ` a partir da v${(publicada ?? alvo).versao}` : ""}
          </Button>
        )}
        {(versoes.isRefreshing || versao.isRefreshing) && <span className="self-end text-xs text-muted-foreground">Atualizando…</span>}
      </div>
      <SaveError message={erro} />

      {versoes.showSkeleton || (alvo && versao.showSkeleton) ? (
        <StudioLoading rows={3} />
      ) : versoes.isError ? (
        <RestrictedNotice error={versoes.error} />
      ) : !alvo ? (
        <EmptyState message="Este padrão ainda não tem versões." />
      ) : versao.isError ? (
        <RestrictedNotice error={versao.error} />
      ) : versao.data ? (
        <VersaoView key={versao.data.id} versao={versao.data} padrao={chave ?? ""} />
      ) : null}
    </div>
  );
}

/**
 * "Envio de leads qualificados" wizard — Passo 1 de 2 (critérios) → Passo 2
 * de 2 (resumo). Groups are OR'd ("OU"), criteria inside a group AND'd ("E").
 * The base criterion "Comportamento = Qualificado via inteligência da Julia"
 * is locked. Writes happen only on Salvar. Admin-only (server-enforced).
 */
import { useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { useConfirm } from "@noctusai/lib";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  CAMPOS_CRITERIO,
  CRITERIO_BASE_ROTULO,
  mensagemErroEnvio,
  regraDe,
  separaOperacao,
  useSalvarEnvioRegras,
  type RegrasEnvio,
} from "@/hooks/useLaisEnvio";
import {
  OPERADORES,
  campoDe,
  clonarGrupos,
  ehBase,
  garantirBase,
  novoCriterio,
  paraWire,
  rotuloCriterio,
  validarGrupos,
  type CriterioRascunho,
  type GrupoRascunho,
} from "./criterios";
import { SidePanel } from "../SidePanel";

type Chave = "ambas" | "compra" | "aluguel";
type Rascunhos = Record<Chave, GrupoRascunho[]>;

const copiar = (g: GrupoRascunho[]): GrupoRascunho[] => g.map((x) => x.map((c) => ({ ...c })));

function inicial(regras: RegrasEnvio | undefined): Rascunhos {
  return {
    ambas: garantirBase(clonarGrupos(regraDe(regras, "ambas"))),
    compra: garantirBase(clonarGrupos(regraDe(regras, "compra"))),
    aluguel: garantirBase(clonarGrupos(regraDe(regras, "aluguel"))),
  };
}

function CriterioLinha({
  c,
  ro,
  onChange,
  onRemove,
  testId,
}: {
  c: CriterioRascunho;
  ro: boolean;
  onChange: (c: CriterioRascunho) => void;
  onRemove?: () => void;
  testId: string;
}) {
  if (ehBase(c)) {
    return (
      <div data-testid={testId} className="flex items-center gap-2 rounded-md bg-muted px-3 py-2 text-sm">
        <span data-testid="criterio-travado">{CRITERIO_BASE_ROTULO}</span>
        <span className="ml-auto text-xs text-muted-foreground">(fixo)</span>
      </div>
    );
  }
  const meta = campoDe(c.campo);
  const numerico = !!meta?.numerico;
  const val = (i: number) => (Array.isArray(c.valor) ? String(c.valor[i] ?? "") : "");
  const setCampo = (campo: string) => {
    const m = campoDe(campo);
    onChange({ campo, operador: m?.booleano ? "=" : m?.numerico ? "" : "preenchido", valor: m?.booleano ? true : null });
  };
  const setOp = (op: string) =>
    onChange({ ...c, operador: op as CriterioRascunho["operador"], valor: op === "entre" ? ["", ""] : null });
  return (
    <div data-testid={testId} className="flex flex-wrap items-center gap-2">
      <select aria-label="Critério" className="h-9 rounded-md border bg-background px-2 text-sm" disabled={ro}
        value={c.campo} onChange={(e) => setCampo(e.target.value)}>
        <option value="">Selecionar critério</option>
        {CAMPOS_CRITERIO.map((x) => <option key={x.campo} value={x.campo}>{x.rotulo}</option>)}
      </select>
      {meta && !meta.booleano && (
        <select aria-label="Condição" className="h-9 rounded-md border bg-background px-2 text-sm" disabled={ro}
          value={c.operador} onChange={(e) => setOp(e.target.value)}>
          <option value="">Selecionar condição</option>
          {OPERADORES.filter((o) => numerico || o.op === "preenchido").map((o) => (
            <option key={o.op} value={o.op}>{o.rotulo}</option>
          ))}
        </select>
      )}
      {numerico && (c.operador === ">=" || c.operador === "<=") && (
        <Input aria-label="Valor" type="number" className="h-9 w-32" disabled={ro}
          placeholder={meta?.moeda ? "R$" : ""} value={c.valor == null ? "" : String(c.valor)}
          onChange={(e) => onChange({ ...c, valor: e.target.value })} />
      )}
      {numerico && c.operador === "entre" && (
        <>
          <Input aria-label="De" type="number" className="h-9 w-28" disabled={ro} placeholder={meta?.moeda ? "R$ de" : "De"}
            value={val(0)} onChange={(e) => onChange({ ...c, valor: [e.target.value, val(1)] })} />
          <Input aria-label="Até" type="number" className="h-9 w-28" disabled={ro} placeholder={meta?.moeda ? "R$ até" : "Até"}
            value={val(1)} onChange={(e) => onChange({ ...c, valor: [val(0), e.target.value] })} />
        </>
      )}
      {onRemove && (
        <Button variant="ghost" size="icon" aria-label="Remover critério" disabled={ro} onClick={onRemove}>
          <Trash2 className="h-4 w-4" />
        </Button>
      )}
    </div>
  );
}

function Grupos({
  grupos,
  ro,
  onChange,
}: {
  grupos: GrupoRascunho[];
  ro: boolean;
  onChange: (g: GrupoRascunho[]) => void;
}) {
  const setCrit = (gi: number, ci: number, c: CriterioRascunho) =>
    onChange(grupos.map((g, i) => (i === gi ? g.map((x, j) => (j === ci ? c : x)) : g)));
  const removeCrit = (gi: number, ci: number) =>
    onChange(grupos.map((g, i) => (i === gi ? g.filter((_, j) => j !== ci) : g)).filter((g) => g.length > 0));
  return (
    <div className="space-y-3">
      {grupos.map((g, gi) => (
        <div key={gi} className="space-y-3">
          {gi > 0 && <div className="text-center text-xs font-semibold text-muted-foreground">OU</div>}
          <div data-testid={`grupo-${gi}`} className="space-y-2 rounded-lg border p-3">
            {g.map((c, ci) => (
              <div key={ci} className="space-y-2">
                {ci > 0 && <div className="text-xs font-semibold text-muted-foreground">E</div>}
                <CriterioLinha c={c} ro={ro} testId={`crit-${gi}-${ci}`}
                  onChange={(n) => setCrit(gi, ci, n)} onRemove={() => removeCrit(gi, ci)} />
              </div>
            ))}
            <Button variant="outline" size="sm" disabled={ro} data-testid={`combinar-${gi}`}
              onClick={() => onChange(grupos.map((x, i) => (i === gi ? [...x, novoCriterio()] : x)))}>
              <Plus className="mr-1 h-3 w-3" /> Combinar com outro critério
            </Button>
          </div>
        </div>
      ))}
      <Button variant="outline" disabled={ro} data-testid="adicionar-grupo"
        onClick={() => onChange([...grupos, [novoCriterio()]])}>
        <Plus className="mr-1 h-4 w-4" /> Adicionar critério de envio
      </Button>
    </div>
  );
}

function Resumo({ titulo, grupos }: { titulo: string; grupos: GrupoRascunho[] }) {
  return (
    <div className="space-y-2" data-testid="resumo">
      <p className="text-sm">
        Leads de {titulo} serão enviados quando atenderem a pelo menos um dos seguintes critérios:
      </p>
      <ul className="space-y-2">
        {grupos.map((g, i) => (
          <li key={i} className="rounded-md border p-2 text-sm" data-testid={`resumo-grupo-${i}`}>
            {g.map(rotuloCriterio).join(" E ")}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function EnvioWizard({
  regras,
  isAdmin,
  onClose,
}: {
  regras: RegrasEnvio | undefined;
  isAdmin: boolean;
  onClose: () => void;
}) {
  const confirm = useConfirm();
  const salvar = useSalvarEnvioRegras();
  const [passo, setPasso] = useState<1 | 2>(1);
  const [separar, setSeparar] = useState(separaOperacao(regras));
  const [aba, setAba] = useState<"compra" | "aluguel">("compra");
  const [draft, setDraft] = useState<Rascunhos>(() => inicial(regras));
  const [dirty, setDirty] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const ro = !isAdmin || salvar.isPending;

  const chaves: Chave[] = separar ? ["compra", "aluguel"] : ["ambas"];
  const atual: Chave = separar ? aba : "ambas";
  const edit = (g: GrupoRascunho[]) => {
    setDraft((d) => ({ ...d, [atual]: g }));
    setDirty(true);
    setErro(null);
  };
  const toggleSeparar = (v: boolean) => {
    setSeparar(v);
    setDirty(true);
    setDraft((d) =>
      v ? { ...d, compra: copiar(d.ambas), aluguel: copiar(d.ambas) } : d);
  };

  const sair = async () => {
    if (dirty && !(await confirm({ title: "Sair da edição?", description: "As alterações não salvas serão perdidas.", confirmLabel: "Sair", tone: "danger" }))) return;
    onClose();
  };
  const proximo = () => {
    for (const k of chaves) {
      const e = validarGrupos(draft[k]);
      if (e) return setErro(chaves.length > 1 ? `${k === "compra" ? "Compra" : "Aluguel"}: ${e}` : e);
    }
    setErro(null);
    setPasso(2);
  };
  const onSalvar = () => {
    if (!dirty) return setErro("Nenhuma alteração para salvar.");
    salvar.mutate(
      { regras: chaves.map((k) => ({ operacao: k, grupos: paraWire(draft[k]) })) },
      {
        onSuccess: () => { toast.success("Critérios de envio salvos"); onClose(); },
        onError: (e) => setErro(mensagemErroEnvio(e, "Não foi possível salvar os critérios.")),
      },
    );
  };

  return (
    <SidePanel
      wide
      testId="envio-wizard"
      title={`Envio de leads qualificados — Passo ${passo} de 2`}
      onClose={sair}
      footer={
        passo === 1 ? (
          <>
            <Button variant="outline" onClick={sair}>Cancelar</Button>
            <Button onClick={proximo} data-testid="wizard-proximo">Próximo</Button>
          </>
        ) : (
          <>
            <Button variant="outline" onClick={() => setPasso(1)}>Voltar</Button>
            <Button onClick={onSalvar} disabled={ro} data-testid="wizard-salvar">
              {salvar.isPending ? "Salvando…" : "Salvar"}
            </Button>
          </>
        )
      }
    >
      {!isAdmin && <p className="text-xs text-muted-foreground" data-testid="envio-readonly">Somente owner/admin pode alterar.</p>}
      {passo === 1 ? (
        <>
          <p className="text-sm text-muted-foreground">
            A Julia qualifica e envia ao SW os leads que atenderem algum dos critérios:
          </p>
          <div className="flex items-center gap-2">
            <input id="env-separar" type="checkbox" checked={separar} disabled={ro}
              onChange={(e) => toggleSeparar(e.target.checked)} />
            <Label htmlFor="env-separar">Configurações diferentes para compra e aluguel</Label>
          </div>
          {separar && (
            <div role="tablist" className="flex gap-2">
              {(["compra", "aluguel"] as const).map((k) => (
                <Button key={k} role="tab" aria-selected={aba === k} size="sm"
                  variant={aba === k ? "default" : "outline"} onClick={() => setAba(k)}>
                  {k === "compra" ? "Compra" : "Aluguel"}
                </Button>
              ))}
            </div>
          )}
          <Grupos grupos={draft[atual]} ro={ro} onChange={edit} />
        </>
      ) : (
        <div className="space-y-4">
          {chaves.map((k) => (
            <Resumo key={k} titulo={k === "ambas" ? "compra e aluguel" : k === "compra" ? "compra" : "aluguel"} grupos={draft[k]} />
          ))}
        </div>
      )}
      {erro && <p role="alert" className="text-sm text-destructive" data-testid="wizard-erro">{erro}</p>}
    </SidePanel>
  );
}

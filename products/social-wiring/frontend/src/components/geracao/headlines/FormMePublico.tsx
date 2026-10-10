/**
 * Gerar headlines sobre Mim / Meu público (contract §7.7, §4.4 #20).
 * Variables of the group (Todos + each), the approved values per variable,
 * optional free subject, Opções Avançadas (perfil ≤ 2 / formato / gatilho),
 * "apenas itens da minha pesquisa" and Criatividade objetiva.
 */
import { useMemo, useState } from "react";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { useTaxonomias } from "@/hooks/geracao/useTaxonomias";
import { usePerfisMonitorados } from "@/hooks/geracao/useBiblioteca";
import {
  useContagemEstruturas,
  useCriarLote,
  useItensAprovados,
  type LoteCreate,
  type ReferenciaLote,
} from "@/hooks/geracao/useHeadlines";
import { usePesquisaVariaveis } from "@/hooks/usePesquisa";
import type { Criatividade, HeadlineLote } from "@/types/geracao";
import { CRIATIVIDADE_ROTULO } from "../labels";
import { alternarEm, mensagemErro } from "./lote";

const ASSUNTO_MAX = 300;
const NIVEIS: Criatividade[] = ["essencial", "equilibrado", "explorador"];

type RefTipo = "" | "perfil" | "formato" | "gatilho";

interface Props {
  who: "me" | "public";
  marcaId: string | null;
  /** Disabled while another batch of this marca is running (the backend answers 409). */
  bloqueado?: boolean;
  onCriado: (lote: HeadlineLote) => void;
}

function Valores({ marcaId, slug, label, selecionados, onChange }: {
  marcaId: string | null;
  slug: string;
  label: string;
  selecionados: string[];
  onChange: (ids: string[]) => void;
}) {
  const q = useItensAprovados(marcaId, slug);
  return (
    <fieldset className="space-y-1 rounded-md border p-3">
      <legend className="px-1 text-xs font-medium">Valor das variável · {label}</legend>
      {q.showSkeleton && <Skeleton className="h-8 w-full" />}
      {q.isError && !q.data && (
        <p role="alert" className="text-xs text-destructive">
          Não foi possível carregar os itens.{" "}
          <button type="button" className="underline" onClick={() => q.refetch()}>
            Tentar novamente
          </button>
        </p>
      )}
      {q.data && q.data.length === 0 && (
        <p className="text-xs text-muted-foreground">Nenhum item aprovado nesta variável — todos os aprovados serão usados quando houver.</p>
      )}
      {q.data?.map((i) => (
        <label key={i.id} className="flex items-start gap-2 text-sm">
          <Checkbox
            checked={selecionados.includes(i.id)}
            onCheckedChange={() => onChange(alternarEm(selecionados, i.id))}
            aria-label={i.content}
          />
          <span>{i.content}</span>
        </label>
      ))}
      <p className="text-xs text-muted-foreground">Sem seleção, todos os itens aprovados são considerados.</p>
    </fieldset>
  );
}

export function FormMePublico({ who, marcaId, bloqueado, onCriado }: Props) {
  const grupo = who === "me" ? "especialista" : "publico";
  const variaveisQ = usePesquisaVariaveis();
  const taxQ = useTaxonomias();
  const perfisQ = usePerfisMonitorados();
  const criar = useCriarLote();

  const [todos, setTodos] = useState(false);
  const [slugs, setSlugs] = useState<string[]>([]);
  const [valores, setValores] = useState<Record<string, string[]>>({});
  const [assunto, setAssunto] = useState("");
  const [refTipo, setRefTipo] = useState<RefTipo>("");
  const [perfilIds, setPerfilIds] = useState<string[]>([]);
  const [formatoIds, setFormatoIds] = useState<number[]>([]);
  const [gatilhos, setGatilhos] = useState<string[]>([]);
  const [somentePesquisa, setSomentePesquisa] = useState(false);
  const [nivel, setNivel] = useState(1);

  const variaveis = useMemo(
    () => (variaveisQ.data ?? []).filter((v) => v.grupo === grupo).sort((a, b) => a.sort_order - b.sort_order),
    [variaveisQ.data, grupo],
  );
  const selecionadas = todos ? ["*"] : slugs;
  const contagem = useContagemEstruturas(marcaId, selecionadas);
  const nPorPerfil = new Map((contagem.data?.por_perfil ?? []).map((p) => [p.perfil_id, p.n]));
  const filtraPorVariavel = selecionadas.length > 0 && !!contagem.data;
  const perfis = (perfisQ.data ?? []).filter((p) => p.status === "ativo" || p.virais > 0);

  const assuntoLimpo = assunto.trim();
  const referencia: ReferenciaLote | undefined =
    refTipo === "perfil" && perfilIds.length
      ? { tipo: "perfil", perfil_ids: perfilIds }
      : refTipo === "formato" && formatoIds.length
        ? { tipo: "formato", formato_ids: formatoIds }
        : refTipo === "gatilho" && gatilhos.length
          ? { tipo: "gatilho", gatilhos }
          : undefined;
  const podeGerar = !!marcaId && selecionadas.length > 0 && !criar.isPending && !bloqueado;

  async function gerar() {
    if (!podeGerar || !marcaId) return;
    const valoresEscolhidos = Object.fromEntries(
      Object.entries(valores).filter(([s, ids]) => !todos && slugs.includes(s) && ids.length > 0),
    );
    const body: LoteCreate = {
      marca_id: marcaId,
      origem: who === "me" ? "form_me" : "form_public",
      variaveis: selecionadas,
      ...(Object.keys(valoresEscolhidos).length ? { valores: valoresEscolhidos } : {}),
      ...(assuntoLimpo ? { assunto: assuntoLimpo } : {}),
      ...(referencia ? { referencia } : {}),
      somente_pesquisa: somentePesquisa,
      criatividade: NIVEIS[nivel],
    };
    try {
      onCriado(await criar.mutateAsync(body));
    } catch (e) {
      toast.error(mensagemErro(e, "Não foi possível gerar as headlines."));
    }
  }

  return (
    <form
      className="space-y-5"
      onSubmit={(e) => {
        e.preventDefault();
        void gerar();
      }}
    >
      <fieldset className="space-y-2">
        <legend className="text-sm font-medium">Selecionar Assuntos</legend>
        {variaveisQ.showSkeleton && <Skeleton className="h-24 w-full" />}
        {variaveisQ.isError && !variaveisQ.data && (
          <p role="alert" className="text-sm text-destructive">
            Não foi possível carregar os assuntos.{" "}
            <button type="button" className="underline" onClick={() => variaveisQ.refetch()}>
              Tentar novamente
            </button>
          </p>
        )}
        {variaveisQ.data && (
          <div className="grid gap-2 sm:grid-cols-2">
            <label className="flex items-center gap-2 text-sm font-medium">
              <Checkbox checked={todos} onCheckedChange={(v) => setTodos(v === true)} aria-label="Todos" />
              Todos
            </label>
            {variaveis.map((v) => (
              <label key={v.slug} className="flex items-center gap-2 text-sm" title={v.description}>
                <Checkbox
                  checked={todos || slugs.includes(v.slug)}
                  disabled={todos}
                  onCheckedChange={() => setSlugs((s) => alternarEm(s, v.slug))}
                  aria-label={v.label}
                />
                {v.label}
              </label>
            ))}
          </div>
        )}
      </fieldset>

      {!todos &&
        slugs.map((s) => (
          <Valores
            key={s}
            marcaId={marcaId}
            slug={s}
            label={variaveis.find((v) => v.slug === s)?.label ?? s}
            selecionados={valores[s] ?? []}
            onChange={(ids) => setValores((m) => ({ ...m, [s]: ids }))}
          />
        ))}

      <div className="space-y-1.5">
        <Label htmlFor="hl-assunto">Selecione o Assunto</Label>
        <Input
          id="hl-assunto"
          maxLength={ASSUNTO_MAX}
          placeholder="Quero escolher outro assunto (opcional)"
          value={assunto}
          onChange={(e) => setAssunto(e.target.value)}
        />
      </div>

      <fieldset className="space-y-3 rounded-md border p-3">
        <legend className="px-1 text-sm font-medium">Opções Avançadas</legend>
        <p className="text-sm">Quero criar headlines com base em:</p>
        <div className="flex flex-wrap gap-4 text-sm">
          {(
            [
              ["perfil", "Modelagem de um Perfil"],
              ["formato", "Formato de Roteiro"],
              ["gatilho", "Gatilho da Atenção"],
            ] as const
          ).map(([v, rotulo]) => (
            <label key={v} className="flex items-center gap-2">
              <input
                type="radio"
                name="hl-ref"
                checked={refTipo === v}
                onChange={() => setRefTipo(v)}
              />
              {rotulo}
            </label>
          ))}
          {refTipo && (
            <button type="button" className="text-xs underline" onClick={() => setRefTipo("")}>
              Limpar
            </button>
          )}
        </div>

        {refTipo === "perfil" && (
          <div className="space-y-1">
            <p className="text-sm font-medium">Perfil de Referência (máximo 2):</p>
            {filtraPorVariavel && (
              <p role="status" className="text-xs text-amber-800">
                Atenção! Exibindo somente perfis que possuem estruturas com as variáveis selecionadas.
              </p>
            )}
            {perfisQ.data && perfis.length === 0 && (
              <p className="text-xs text-muted-foreground">Nenhum perfil monitorado disponível.</p>
            )}
            {perfis.map((p) => {
              const semEstrutura = filtraPorVariavel && (nPorPerfil.get(p.id) ?? 0) === 0;
              return (
                <label key={p.id} className="flex items-center gap-2 text-sm">
                  <Checkbox
                    checked={perfilIds.includes(p.id)}
                    disabled={semEstrutura || (!perfilIds.includes(p.id) && perfilIds.length >= 2)}
                    onCheckedChange={() => setPerfilIds((s) => alternarEm(s, p.id, 2))}
                    aria-label={`@${p.handle}`}
                  />
                  @{p.handle}
                  {semEstrutura && <span className="text-xs text-muted-foreground">(Sem estruturas disponíveis)</span>}
                </label>
              );
            })}
          </div>
        )}

        {refTipo === "formato" && (
          <div className="space-y-1">
            <p className="text-sm font-medium">Formato do Vídeo (até 3):</p>
            {taxQ.showSkeleton && <Skeleton className="h-8 w-full" />}
            <div className="grid gap-1 sm:grid-cols-2">
              {taxQ.data?.formatos.map((f) => (
                <label key={f.id} className="flex items-center gap-2 text-sm" title={f.definicao}>
                  <Checkbox
                    checked={formatoIds.includes(f.id)}
                    disabled={!formatoIds.includes(f.id) && formatoIds.length >= 3}
                    onCheckedChange={() => setFormatoIds((s) => alternarEm(s, f.id, 3))}
                    aria-label={f.nome}
                  />
                  {f.nome}
                </label>
              ))}
            </div>
          </div>
        )}

        {refTipo === "gatilho" && (
          <div className="space-y-1">
            <p className="text-sm font-medium">Gatilho da Atenção (até 3):</p>
            {taxQ.showSkeleton && <Skeleton className="h-8 w-full" />}
            <div className="grid gap-1 sm:grid-cols-2">
              {taxQ.data?.gatilhos.map((g) => (
                <label key={g.slug} className="flex items-center gap-2 text-sm" title={g.formula}>
                  <Checkbox
                    checked={gatilhos.includes(g.slug)}
                    disabled={!gatilhos.includes(g.slug) && gatilhos.length >= 3}
                    onCheckedChange={() => setGatilhos((s) => alternarEm(s, g.slug, 3))}
                    aria-label={g.nome}
                  />
                  {g.nome}
                </label>
              ))}
            </div>
          </div>
        )}

        <label className="flex items-center gap-2 text-sm">
          <Checkbox
            checked={somentePesquisa}
            onCheckedChange={(v) => setSomentePesquisa(v === true)}
            aria-label="Criar as headlines usando apenas os itens da minha pesquisa."
          />
          Criar as headlines usando apenas os itens da minha pesquisa.
        </label>

        <div className="space-y-1">
          <Label htmlFor="hl-criatividade">Criatividade objetiva: {CRIATIVIDADE_ROTULO[NIVEIS[nivel]]}</Label>
          <input
            id="hl-criatividade"
            type="range"
            min={0}
            max={2}
            step={1}
            value={nivel}
            onChange={(e) => setNivel(Number(e.target.value))}
            className="w-full"
            aria-valuetext={CRIATIVIDADE_ROTULO[NIVEIS[nivel]]}
          />
          <div className="flex justify-between text-xs text-muted-foreground">
            {NIVEIS.map((n) => (
              <span key={n}>{CRIATIVIDADE_ROTULO[n]}</span>
            ))}
          </div>
        </div>
      </fieldset>

      {bloqueado && (
        <p className="text-xs text-muted-foreground">Já existe uma geração em andamento — aguarde terminar para gerar outra.</p>
      )}
      <Button type="submit" disabled={!podeGerar}>
        {criar.isPending && <Loader2 className="mr-1 h-4 w-4 animate-spin" />} Gerar Headlines
      </Button>
    </form>
  );
}

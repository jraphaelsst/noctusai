/**
 * Platform-admin editor of ONE Estrutura (contract §11.3): formula, formato, objetivos, the ordered blocks,
 * per-field provenance with Confirmar / Confirmar todos, Publicar on a rascunho, archive / restore / delete.
 *
 * Server-state rules (§11.4):
 *  - a draft SAYS it is unsaved (`useUnsavedChanges` + `UnsavedChangesNotice`; reload/close asks first);
 *  - the draft is an OVERLAY on the cached server row, so a background refetch never wipes typing;
 *  - the version the draft started from is remembered (`versaoBase`); a stale save is refused by the
 *    server (409 `versao_desatualizada`) and answered with a conflict dialog — never a silent overwrite;
 *  - every refusal is rendered (toast + inline for `rascunho_incompleto` / `estrutura_em_uso`).
 */
import { UnsavedChangesNotice, useConfirm, useUnsavedChanges } from "@noctusai/lib/components";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  useArquivarEstrutura,
  useAtualizarEstrutura,
  useConfirmarEstrutura,
  useExcluirEstrutura,
  usePublicarEstrutura,
  useSubstituirBlocos,
} from "@/hooks/geracao/useEstruturas";
import type { EstruturaDetalhe, EstruturaFormato, EstruturaObjetivo, TipoBloco } from "@/types/estruturas";
import { BlocosEditor } from "./BlocosEditor";
import { ConfirmarBar } from "./ConfirmarBar";
import { codigoDoErro, dadoDoErro, ehConflitoDeVersao, mensagemEstruturas } from "./erros";
import { ProvenienciaBadge } from "./ProvenienciaBadge";
import { PublicarBar } from "./PublicarBar";
import {
  blocoParaCorpo,
  camposPendentes,
  detalheParaRascunho,
  FORMATOS,
  OBJETIVOS,
  placeholdersDaFormula,
  ROTULO_FORMATO,
  ROTULO_OBJETIVO,
  ROTULO_STATUS,
  type EstruturaRascunho,
} from "./rotulos";
import { errosDoRascunho } from "./schema";

interface Props {
  detalhe: EstruturaDetalhe;
  tipos: TipoBloco[];
  /** Re-reads the Estrutura from the server and resolves with the fresh row. */
  onRecarregar: () => Promise<EstruturaDetalhe | undefined>;
  /** After a hard delete: the page leaves. */
  onExcluida: () => void;
}

export function EstruturaEditor({ detalhe, tipos, onRecarregar, onExcluida }: Props) {
  const confirmar = useConfirm();
  const atualizar = useAtualizarEstrutura();
  const substituir = useSubstituirBlocos();
  const confirmarCampos = useConfirmarEstrutura();
  const publicar = usePublicarEstrutura();
  const arquivar = useArquivarEstrutura();
  const excluir = useExcluirEstrutura();

  const [edicoes, setEdicoes] = useState<Partial<EstruturaRascunho>>({});
  const [versaoBase, setVersaoBase] = useState<number | null>(null);
  const [tentouSalvar, setTentouSalvar] = useState(false);
  const [conflito, setConflito] = useState(false);
  const [faltando, setFaltando] = useState<string[]>([]);

  const salvo = useMemo(() => detalheParaRascunho(detalhe), [detalhe]);
  const rascunho: EstruturaRascunho = { ...salvo, ...edicoes };
  const { dirty, changed } = useUnsavedChanges(rascunho, salvo);
  const erros = useMemo(() => (tentouSalvar ? errosDoRascunho(rascunho) : {}), [tentouSalvar, rascunho]);

  const arquivada = detalhe.status === "arquivada";
  const pendentes = camposPendentes(detalhe);
  const ocupado = atualizar.isPending || substituir.isPending;
  const versaoAtual = versaoBase ?? detalhe.versao;
  const prov = detalhe.proveniencia;

  function editar(m: Partial<EstruturaRascunho>) {
    setEdicoes((e) => ({ ...e, ...m }));
    setVersaoBase((v) => v ?? detalhe.versao);
  }
  function descartar() {
    setEdicoes({});
    setVersaoBase(null);
    setTentouSalvar(false);
  }

  async function salvar() {
    setTentouSalvar(true);
    if (Object.keys(errosDoRascunho(rascunho)).length > 0) {
      toast.error("Revise os campos destacados antes de salvar.");
      return;
    }
    let versao = versaoAtual;
    try {
      if (changed.some((c) => c !== "blocos")) {
        const corpo: { formula_headline?: string; formato?: EstruturaFormato; objetivos?: EstruturaObjetivo[] } = {};
        if (changed.includes("formula_headline")) corpo.formula_headline = rascunho.formula_headline.trim();
        if (changed.includes("formato") && rascunho.formato) corpo.formato = rascunho.formato;
        if (changed.includes("objetivos")) corpo.objetivos = rascunho.objetivos;
        const s = await atualizar.mutateAsync({ id: detalhe.id, expected_versao: versao, ...corpo });
        versao = s.versao;
        // The header is saved: from here the draft's base is the version the server just answered with.
        setVersaoBase(s.versao);
      }
      if (changed.includes("blocos")) {
        await substituir.mutateAsync({
          id: detalhe.id,
          expected_versao: versao,
          blocos: rascunho.blocos.map(blocoParaCorpo),
        });
      }
      descartar();
      toast.success("Estrutura salva.");
    } catch (e) {
      if (ehConflitoDeVersao(e)) setConflito(true);
      else toast.error(mensagemEstruturas(e, "Não foi possível salvar a estrutura."));
    }
  }

  async function recarregarDescartando() {
    await onRecarregar();
    descartar();
    setConflito(false);
  }
  async function manterMinhasAlteracoes() {
    const fresco = await onRecarregar();
    if (fresco) setVersaoBase(fresco.versao);
    setConflito(false);
    toast.info("Estrutura recarregada. Suas alterações foram mantidas — clique em Salvar para aplicá-las.");
  }

  async function confirmarUm(campo: string) {
    try {
      await confirmarCampos.mutateAsync({ id: detalhe.id, expected_versao: detalhe.versao, campos: [campo] });
      toast.success("Campo confirmado.");
    } catch (e) {
      if (ehConflitoDeVersao(e)) setConflito(true);
      else toast.error(mensagemEstruturas(e, "Não foi possível confirmar o campo."));
    }
  }
  async function confirmarTodos() {
    try {
      await confirmarCampos.mutateAsync({ id: detalhe.id, expected_versao: detalhe.versao, todos: true });
      toast.success("Todos os campos foram confirmados.");
    } catch (e) {
      if (ehConflitoDeVersao(e)) setConflito(true);
      else toast.error(mensagemEstruturas(e, "Não foi possível confirmar os campos."));
    }
  }

  async function publicarAgora() {
    setFaltando([]);
    try {
      await publicar.mutateAsync({ id: detalhe.id, expected_versao: detalhe.versao });
      toast.success("Estrutura publicada. Já pode ser usada pelas organizações.");
    } catch (e) {
      if (codigoDoErro(e) === "rascunho_incompleto") {
        const f = dadoDoErro(e, "faltando");
        setFaltando(Array.isArray(f) ? f.map(String) : []);
        toast.error(mensagemEstruturas(e, "Rascunho incompleto."));
      } else if (ehConflitoDeVersao(e)) setConflito(true);
      else toast.error(mensagemEstruturas(e, "Não foi possível publicar."));
    }
  }

  async function alternarArquivo() {
    const acao = arquivada ? "restaurar" : "arquivar";
    if (
      !arquivada &&
      !(await confirmar({
        title: "Arquivar esta estrutura?",
        description: "Ela deixa de ser oferecida às organizações e à IA. Você pode restaurá-la depois.",
        confirmLabel: "Arquivar",
      }))
    )
      return;
    try {
      await arquivar.mutateAsync({ id: detalhe.id, acao });
      toast.success(arquivada ? "Estrutura restaurada." : "Estrutura arquivada.");
    } catch (e) {
      toast.error(mensagemEstruturas(e, arquivada ? "Não foi possível restaurar." : "Não foi possível arquivar."));
    }
  }

  async function excluirAgora() {
    const ok = await confirmar({
      title: "Excluir esta estrutura?",
      description: "Isso apaga a estrutura e seus blocos. Só é possível se nenhuma headline ou roteiro a usou; senão, arquive.",
      confirmLabel: "Excluir",
      tone: "danger",
    });
    if (!ok) return;
    try {
      await excluir.mutateAsync(detalhe.id);
      toast.success("Estrutura excluída.");
      onExcluida();
    } catch (e) {
      // `estrutura_em_uso` is explained, not just refused: archive is the way out.
      toast.error(mensagemEstruturas(e, "Não foi possível excluir a estrutura."));
    }
  }

  const placeholders = placeholdersDaFormula(rascunho.formula_headline);
  const bloqueioConfirmar = dirty ? "Salve ou descarte as alterações antes de confirmar." : undefined;
  const confirmarDesabilitado = dirty || confirmarCampos.isPending;

  return (
    <div className="flex flex-col gap-5" data-testid="estrutura-editor">
      {detalhe.status === "rascunho" && (
        <PublicarBar
          faltando={faltando}
          alteracoesNaoSalvas={dirty}
          pending={publicar.isPending}
          onPublicar={publicarAgora}
        />
      )}
      <ConfirmarBar pendentes={pendentes.length} alteracoesNaoSalvas={dirty} pending={confirmarCampos.isPending} onConfirmarTodos={confirmarTodos} />

      {arquivada && (
        <p role="status" className="rounded-md border bg-muted/50 p-3 text-sm">
          Esta estrutura está arquivada e não pode ser editada. Restaure-a para editar.
        </p>
      )}

      <section aria-label="Fórmula e classificação" className="flex flex-col gap-4 rounded-lg border p-4">
        <div className="flex flex-col gap-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <Label htmlFor="est-formula">Fórmula da headline</Label>
            <ProvenienciaBadge origem={prov?.formula_headline} campo="a fórmula" onConfirmar={() => confirmarUm("formula_headline")} desabilitado={confirmarDesabilitado} motivoDesabilitado={bloqueioConfirmar} />
          </div>
          <Textarea
            id="est-formula"
            rows={3}
            value={rascunho.formula_headline}
            onChange={(e) => editar({ formula_headline: e.target.value })}
            disabled={arquivada}
            aria-invalid={!!erros.formula_headline}
            aria-describedby={erros.formula_headline ? "est-formula-erro" : "est-formula-ajuda"}
          />
          {erros.formula_headline ? (
            <p id="est-formula-erro" className="text-xs text-destructive">{erros.formula_headline}</p>
          ) : (
            <p id="est-formula-ajuda" className="text-xs text-muted-foreground">
              {placeholders.length > 0
                ? `Os trechos entre colchetes (${placeholders.map((p) => `[${p}]`).join(", ")}) são preenchidos pela IA com o Cérebro e a bio da organização.`
                : "Use [colchetes] para os trechos que a IA deve preencher com o Cérebro e a bio da organização."}
            </p>
          )}
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <div className="flex flex-col gap-1.5">
            <div className="flex flex-wrap items-center gap-2">
            <Label htmlFor="est-formato">Formato</Label>
            <ProvenienciaBadge origem={prov?.formato} campo="o formato" onConfirmar={() => confirmarUm("formato")} desabilitado={confirmarDesabilitado} motivoDesabilitado={bloqueioConfirmar} />
          </div>
            <select
              id="est-formato"
              className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm disabled:opacity-60"
              value={rascunho.formato}
              onChange={(e) => editar({ formato: e.target.value as EstruturaFormato | "" })}
              disabled={arquivada}
              aria-invalid={!!erros.formato}
              aria-describedby={erros.formato ? "est-formato-erro" : undefined}
            >
              <option value="">Escolha…</option>
              {FORMATOS.map((f) => (
                <option key={f} value={f}>{ROTULO_FORMATO[f]}</option>
              ))}
            </select>
            {erros.formato && <p id="est-formato-erro" className="text-xs text-destructive">{erros.formato}</p>}
          </div>

          <fieldset className="flex flex-col gap-1.5" aria-describedby={erros.objetivos ? "est-objetivos-erro" : undefined}>
            <legend className="mb-1.5 text-sm font-medium">Objetivos</legend>
            <div className="mb-1.5">
              <ProvenienciaBadge origem={prov?.objetivos} campo="os objetivos" onConfirmar={() => confirmarUm("objetivos")} desabilitado={confirmarDesabilitado} motivoDesabilitado={bloqueioConfirmar} />
            </div>
            <div className="flex flex-wrap gap-3">
              {OBJETIVOS.map((o) => (
                <label key={o} className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    className="h-4 w-4"
                    checked={rascunho.objetivos.includes(o)}
                    disabled={arquivada}
                    onChange={(e) =>
                      editar({
                        objetivos: e.target.checked
                          ? [...rascunho.objetivos, o]
                          : rascunho.objetivos.filter((x) => x !== o),
                      })
                    }
                  />
                  {ROTULO_OBJETIVO[o]}
                </label>
              ))}
            </div>
            {erros.objetivos && <p id="est-objetivos-erro" className="text-xs text-destructive">{erros.objetivos}</p>}
          </fieldset>
        </div>
      </section>

      <BlocosEditor
        blocos={rascunho.blocos}
        onChange={(blocos) => editar({ blocos })}
        tipos={tipos}
        salvos={detalhe.blocos}
        erros={erros}
        somenteLeitura={arquivada}
        onConfirmarCampo={confirmarUm}
        confirmarDesabilitado={confirmarDesabilitado}
        motivoConfirmar={bloqueioConfirmar}
      />

      <div className="sticky bottom-0 -mx-1 flex flex-wrap items-center gap-3 border-t bg-background/95 p-3 backdrop-blur">
        <UnsavedChangesNotice dirty={dirty}>Alterações não salvas — clique em Salvar.</UnsavedChangesNotice>
        {dirty && <Badge variant="secondary">Rascunho local</Badge>}
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <Badge variant="outline">{ROTULO_STATUS[detalhe.status]}</Badge>
          <Button variant="outline" size="sm" onClick={alternarArquivo} disabled={arquivar.isPending || ocupado}>
            {arquivada ? "Restaurar" : "Arquivar"}
          </Button>
          <Button variant="outline" size="sm" className="text-destructive" onClick={excluirAgora} disabled={excluir.isPending || ocupado}>
            Excluir
          </Button>
          <Button variant="ghost" size="sm" onClick={descartar} disabled={!dirty || ocupado}>
            Descartar alterações
          </Button>
          <Button size="sm" onClick={salvar} disabled={!dirty || ocupado || arquivada}>
            {ocupado ? "Salvando..." : "Salvar"}
          </Button>
        </div>
      </div>

      <Dialog open={conflito} onOpenChange={setConflito}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Esta estrutura foi alterada por outra pessoa</DialogTitle>
            <DialogDescription>
              Alguém salvou uma versão mais nova enquanto você editava. Recarregue para ver a versão atual ou mantenha as
              suas alterações e salve por cima.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => void recarregarDescartando()}>
              Recarregar e descartar minhas alterações
            </Button>
            <Button onClick={() => void manterMinhasAlteracoes()}>Manter minhas alterações</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

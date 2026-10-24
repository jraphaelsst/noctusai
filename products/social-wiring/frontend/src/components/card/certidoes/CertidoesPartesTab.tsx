/**
 * `<CertidoesPartesTab/>` — the card's "Certidões" tab, per party: every
 * comprador and vendedor (PF and PJ, plus derived EMP columns) as a
 * collapsible section, ALL COLLAPSED by default; expanded, each holds that
 * party's levantamento de certidões. Contract §1/§6.
 *
 * Loading: `showSkeleton = isPending && !data`, `isRefreshing = isFetching &&
 * !!data` (indicator only) → KB § PATTERNS/frontend/lying-loading-state.md.
 */
import { useState } from "react";
import { FileSearch, Loader2, Trash2 } from "lucide-react";

import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { TooltipProvider } from "@/components/ui/tooltip";
import { CertidoesPartePanel } from "@/components/CertidoesPartePanel";
import {
  useCertidoesPartes, useCienciaPcen, useDefinirExigencias, useCriarLinhaPartes, useInvalidatePartes, useReemitirResultado,
  useAplicarValoresLidos, useBaixarZipDaParte, useCancelarEmissao, useDescartarEmissao, useReemitirComErro, useVoltarAoAutomatico, useRelerCertidoesCard, useRelerResultado, useRelerResultados, useRemoverAntigo, useRemoverLinhaPartes, useRenomearLinhaPartes, useSolicitarEmissao, useUploadNaCelula, useDigitarNaCelula,
} from "@/hooks/useCertidoesPartes";
import type { CertidaoParte, CertidaoParteLinha, UploadCelulaInput } from "@/types/certidoesPartes";

import { alvoSubtabCertidoes, type GrupoCertidoes } from "../destinoDoContrato";
import { mensagemDoErro } from "../mensagemDoErro";
import { textoDaRecusa, useUploadDocumento } from "@noctusai/lib/upload-refusal";
import { AntigosProprietariosPainel } from "./AntigosProprietariosPainel";
import { podeReler } from "./certidoesCelula";
import { PessoaDocumentosPanel } from "@/components/PessoaDocumentosPanel";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { ResultadoEditForm } from "@/components/ResultadoEditForm";
import { ParteSecao } from "./ParteSecao";

const SUBTABS: ReadonlyArray<{ grupo: GrupoCertidoes; rotulo: string; vazio: string }> = [
  { grupo: "comprador", rotulo: "Compradores", vazio: "Nenhum comprador vinculado a este atendimento ainda." },
  { grupo: "vendedor", rotulo: "Vendedores", vazio: "Nenhum vendedor vinculado a este atendimento ainda." },
  { grupo: "antigo_proprietario", rotulo: "Antigos proprietários", vazio: "Nenhum antigo proprietário no card." },
];

/** The party's cliente/empresa id — what the party-scoped routes address it by. */
const alvoDaParte = (p: CertidaoParte): string => (p.kind === "empresa" ? p.empresa_id : p.cliente_id) as string;

export function CertidoesPartesTab(props: {
  clienteId: string;
  atendimentoId?: string | null;
}) {
  const { clienteId, atendimentoId } = props;
  const q = useCertidoesPartes(clienteId, atendimentoId);
  const emissao = useSolicitarEmissao(clienteId, atendimentoId);
  const reemitir = useReemitirResultado(clienteId);
  const ciencia = useCienciaPcen(clienteId);
  const reler = useRelerResultado(clienteId);
  const relerTodas = useRelerCertidoesCard(clienteId, atendimentoId);
  const relerParte = useRelerResultados(clienteId);
  const aplicarLidos = useAplicarValoresLidos(clienteId);
  const voltar = useVoltarAoAutomatico(clienteId, atendimentoId);
  const cancelar = useCancelarEmissao(clienteId, atendimentoId);
  const reemitirErros = useReemitirComErro(clienteId, atendimentoId);
  const descartar = useDescartarEmissao(clienteId, atendimentoId);
  const baixarZip = useBaixarZipDaParte(clienteId, atendimentoId);
  // Which party's "Reler todas" is in flight (one mutation, keyed by the party).
  const [relendoParteChave, setRelendoParteChave] = useState<string | null>(null);
  const upload = useUploadNaCelula(clienteId, atendimentoId);
  // F86: every refusal of an upload / emission stays ON THE ROW with the
  // server's own message until the next attempt — a toast alone vanished and
  // 10 uploads were silently lost. Keyed `${parte.chave}|${linha.chave}`
  // (`|*` = the whole party, "Solicitar emissão (todas)").
  const [recusas, setRecusas] = useState<Record<string, string>>({});
  const marcarRecusa = (chaves: string[], e: unknown, fallback: string) =>
    setRecusas((r) => ({ ...r, ...Object.fromEntries(chaves.map((k) => [k, mensagemDoErro(e, fallback)])) }));
  const limparRecusa = (chaves: string[]) =>
    setRecusas((r) => {
      if (!chaves.some((k) => k in r)) return r;
      const n = { ...r };
      for (const k of chaves) delete n[k];
      return n;
    });
  // Cell uploads go through the seed upload-refusal organ: the refusal (the
  // server's message + the FILE NAME) is tagged with the cell's key and drawn
  // on that row alongside the emission refusals above.
  // KB § PATTERNS/frontend/silent-refusal.md.
  const envioCelula = useUploadDocumento((_file: File, i: UploadCelulaInput) => upload.mutateAsync(i));
  const recusasDaParte = (parteChave: string): Record<string, string> => {
    const out: Record<string, string> = Object.fromEntries(
      Object.entries(recusas)
        .filter(([k]) => k.startsWith(`${parteChave}|`))
        .map(([k, v]) => [k.slice(parteChave.length + 1), v]),
    );
    const erroUpload = envioCelula.erro;
    if (erroUpload?.chave?.startsWith(`${parteChave}|`)) {
      out[erroUpload.chave.slice(parteChave.length + 1)] = textoDaRecusa(erroUpload);
    }
    return out;
  };
  const chavesDaEmissao = (parteChave: string, tipos: string[] | null, linhas: CertidaoParteLinha[]) =>
    tipos === null
      ? [`${parteChave}|*`]
      : linhas.filter((l) => l.tipo && tipos.includes(l.tipo)).map((l) => `${parteChave}|${l.chave}`);
  const digitar = useDigitarNaCelula(clienteId, atendimentoId);
  // Cell being typed by hand: the party KEY + linha chave, resolved against the LIVE row below.
  const [digitando, setDigitando] = useState<{ parteChave: string; linhaChave: string } | null>(null);
  const criar = useCriarLinhaPartes(clienteId);
  const renomear = useRenomearLinhaPartes(clienteId);
  const remover = useRemoverLinhaPartes(clienteId);
  const invalidar = useInvalidatePartes(clienteId);
  const removerAntigo = useRemoverAntigo(clienteId, atendimentoId);
  const exigencias = useDefinirExigencias(clienteId, atendimentoId);
  const [removendoAntigo, setRemovendoAntigo] = useState<CertidaoParte | null>(null);
  // Controlled so the deep link (`destino.alvo = certidoes-subtab-<grupo>`)
  // can activate a subtab: the trigger's DOM id IS the alvo, and
  // `rolarAteAlvo` focuses it (Radix automatic activation).
  const [subtab, setSubtab] = useState<GrupoCertidoes>("comprador");

  // 🔴 The KEY of the party whose dialog is open, never a snapshot of the
  // row: the dialog reads the LIVE row off `q.data`, so a CPF that arrives
  // after it opened (the tab's query refetches) reaches the "Registrar
  // certidões manualmente" prefill without a reload.
  const [detalhesChave, setDetalhesChave] = useState<string | null>(null);
  const [adicionando, setAdicionando] = useState(false);
  const [novoNome, setNovoNome] = useState("");
  const [renomeando, setRenomeando] = useState<CertidaoParteLinha | null>(null);
  const [nomeRen, setNomeRen] = useState("");
  const [removendo, setRemovendo] = useState<CertidaoParteLinha | null>(null);

  const data = q.data;
  const showSkeleton = q.isPending && !data;
  const isRefreshing = q.isFetching && !!data;

  if (showSkeleton) {
    return (
      <div className="space-y-2" data-testid="certidoes-partes-skeleton">
        <div className="h-12 animate-pulse rounded bg-muted" />
        <div className="h-12 animate-pulse rounded bg-muted" />
      </div>
    );
  }
  if (!data) {
    return (
      <div className="space-y-2 text-sm" data-testid="certidoes-partes-error">
        <p className="text-destructive">Não foi possível carregar as certidões das partes.</p>
        <Button size="sm" variant="outline" onClick={() => void q.refetch()}>Tentar novamente</Button>
      </div>
    );
  }
  if (data.partes.length === 0 && !data.atendimento_id) {
    return (
      <p className="text-sm text-muted-foreground" data-testid="certidoes-partes-empty">
        {data.atendimento_id
          ? "Nenhum comprador ou vendedor vinculado a este atendimento ainda."
          : "Selecione um atendimento para ver as certidões das partes."}
      </p>
    );
  }

  const detalhes: CertidaoParte | null =
    (detalhesChave && data.partes.find((p) => p.chave === detalhesChave)) || null;

  const parteDigitando = digitando ? data.partes.find((x) => x.chave === digitando.parteChave) ?? null : null;
  const linhaDigitando = digitando ? data.linhas.find((l) => l.chave === digitando.linhaChave) ?? null : null;
  const celulaDigitando = parteDigitando && digitando ? parteDigitando.celulas[digitando.linhaChave] ?? null : null;

  const fecharAdicionar = () => { setAdicionando(false); setNovoNome(""); };
  const temPdfArmazenado = data.partes.some((p) => Object.values(p.celulas).some(podeReler));
  const relendoId = reler.isPending ? (reler.variables ?? null) : null;
  const aplicandoId = aplicarLidos.isPending ? (aplicarLidos.variables?.resultadoId ?? null) : null;

  return (
    <div className="space-y-3" data-testid="certidoes-partes">
      {q.isError && (
        <p className="text-xs text-destructive" data-testid="certidoes-partes-error-banner">
          Falha ao atualizar — exibindo os últimos dados carregados.
        </p>
      )}
      {(isRefreshing || temPdfArmazenado) && (
        <div className="flex flex-wrap items-center justify-between gap-2">
          {/* lying-loading-ok: indicator-only — the else branch is an empty spacer, never content */}
          {isRefreshing ? (
            <p className="text-xs text-muted-foreground" data-testid="certidoes-partes-refreshing">Atualizando…</p>
          ) : <span />}
          {temPdfArmazenado && (
            <Button size="sm" variant="outline" disabled={relerTodas.isPending}
              title="Lê de novo, com o leitor mais recente, todos os PDFs de certidão já armazenados das partes deste atendimento. Valores confirmados não são alterados."
              onClick={() => relerTodas.mutate()}
              data-testid="certidoes-partes-reextrair">
              {relerTodas.isPending ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <FileSearch className="mr-1 h-4 w-4" />}
              Reler todas as certidões
            </Button>
          )}
        </div>
      )}
      <div className="flex flex-wrap gap-x-6 gap-y-2 rounded border p-3 text-sm" data-testid="certidoes-exigencias">
        <p className="w-full text-xs text-muted-foreground">
          Opcionais por padrão ("depende do caso"): ative para exigir neste negócio.
        </p>
        {([
          ["exigir_certidoes_antigos", "Exigir certidões dos antigos proprietários"],
          ["exigir_crf_fgts", "Exigir CRF/FGTS da empresa"],
        ] as const).map(([campo, rotulo]) => (
          <div key={campo} className="flex items-center gap-2">
            <Switch
              id={`exigencia-${campo}`}
              checked={!!data.exigencias?.[campo]}
              disabled={exigencias.isPending || !data.atendimento_id}
              onCheckedChange={(v) => exigencias.mutate({ [campo]: v })}
              data-testid={`exigencia-${campo}`}
            />
            <Label htmlFor={`exigencia-${campo}`}>{rotulo}</Label>
          </div>
        ))}
      </div>
      <TooltipProvider delayDuration={200}>
        <Tabs value={subtab} onValueChange={(v) => setSubtab(v as GrupoCertidoes)}>
          <TabsList data-testid="certidoes-subtabs">
            {SUBTABS.map((t) => (
              <TabsTrigger key={t.grupo} value={t.grupo} id={alvoSubtabCertidoes(t.grupo)} data-testid={`certidoes-subtab-${t.grupo}`}>
                {t.rotulo} ({data.partes.filter((p) => p.grupo === t.grupo).length})
              </TabsTrigger>
            ))}
          </TabsList>
          {SUBTABS.map((t) => {
            const doGrupo = data.partes.filter((p) => p.grupo === t.grupo);
            const linhasDoGrupo = doGrupo.length === 0 ? (
              <p className="text-sm text-muted-foreground" data-testid={`certidoes-subtab-vazio-${t.grupo}`}>{t.vazio}</p>
            ) : (
              doGrupo.map((parte) => (
                <div key={parte.chave} className="space-y-1">
                  {t.grupo === "antigo_proprietario" && parte.parte_id && parte.papel === "antigo_proprietario" && (
                    <div className="flex justify-end">
                      <Button size="sm" variant="ghost" className="h-7 text-xs text-destructive"
                        onClick={() => setRemovendoAntigo(parte)} data-testid={`antigo-remover-${parte.chave}`}>
                        <Trash2 className="mr-1 h-3 w-3" />Remover antigo proprietário
                      </Button>
                    </div>
                  )}
                  <ParteSecao
                key={parte.chave}
                parte={parte}
                linhas={data.linhas}
                dataReferencia={data.data_referencia}
                emissaoPendente={emissao.isPending}
                onSolicitar={(i) => {
                  const chaves = chavesDaEmissao(parte.chave, i.tipos, data.linhas);
                  limparRecusa(chaves);
                  emissao.mutate(i, {
                    onError: (e) => marcarRecusa(chaves, e, "Não foi possível solicitar a emissão."),
                  });
                }}
                onReemitir={(id) => reemitir.mutate(id)}
                onUpload={(i) => {
                  const chave = `${parte.chave}|${i.linhaChave}`;
                  limparRecusa([chave]);
                  void envioCelula.enviarEm(chave, i.file, i);
                }}
                recusas={recusasDaParte(parte.chave)}
                enviandoLinha={
                  upload.isPending && upload.variables && upload.variables.alvoId === alvoDaParte(parte)
                    ? upload.variables.linhaChave
                    : null
                }
                onDigitar={(pt, l) => setDigitando({ parteChave: pt.chave, linhaChave: l.chave })}
                onReler={(id) => reler.mutate(id)}
                relendoId={relendoId}
                onRelerParte={(ids) => {
                  setRelendoParteChave(parte.chave);
                  relerParte.mutate(ids, { onSettled: () => setRelendoParteChave(null) });
                }}
                relendoParte={relerParte.isPending && relendoParteChave === parte.chave}
                onAplicarLidos={(resultadoId, divergencias) => aplicarLidos.mutate({ resultadoId, divergencias })}
                aplicandoId={aplicandoId}
                onVoltarAutomatico={(id) => voltar.mutate(id)}
                voltandoId={voltar.isPending ? (voltar.variables ?? null) : null}
                onCancelarCelula={(id) => cancelar.mutate({ resultadoId: id })}
                cancelandoId={cancelar.isPending && cancelar.variables && "resultadoId" in cancelar.variables ? cancelar.variables.resultadoId : null}
                onCancelarParte={() => cancelar.mutate({ kind: parte.kind, alvoId: alvoDaParte(parte) })}
                cancelandoParte={cancelar.isPending && !!cancelar.variables && "alvoId" in cancelar.variables && cancelar.variables.alvoId === alvoDaParte(parte)}
                onReemitirErros={() => reemitirErros.mutate({ kind: parte.kind, alvoId: alvoDaParte(parte) })}
                reemitindoErros={reemitirErros.isPending && reemitirErros.variables?.alvoId === alvoDaParte(parte)}
                onDescartar={(id) => descartar.mutate(id)}
                descartandoId={descartar.isPending ? (descartar.variables ?? null) : null}
                onBaixarZip={() => baixarZip.mutate({ kind: parte.kind, alvoId: alvoDaParte(parte), nome: parte.nome })}
                baixandoZip={baixarZip.isPending && baixarZip.variables?.alvoId === alvoDaParte(parte)}
                onDetalhes={(p) => setDetalhesChave(p.chave)}
                onAdicionar={() => setAdicionando(true)}
                onRenomear={(l) => { setRenomeando(l); setNomeRen(l.rotulo.replace(/^Outras: /, "")); }}
                onRemover={setRemovendo}
                onCienciaPcen={(resultadoId, acao) => ciencia.mutateAsync({ resultadoId, acao })}
              />
                  {/* F98: an antigo is a `clientes` row like a vendedor — the SAME
                      documents panel (Serasa Crednet slot, RG/CPF, CNH, CIN) so a
                      Crednet read creates his participações and his companies
                      reach the "ANT EMP" rows below. Mounted only while open. */}
                  {t.grupo === "antigo_proprietario" && parte.kind === "pessoa" && parte.cliente_id && (
                    <Collapsible className="rounded border px-3 py-1" data-testid={`antigo-documentos-${parte.chave}`}>
                      <CollapsibleTrigger className="w-full py-1 text-left text-xs font-medium"
                        data-testid={`antigo-documentos-toggle-${parte.chave}`}>
                        Documentos e Serasa Crednet de {parte.nome}
                      </CollapsibleTrigger>
                      <CollapsibleContent className="space-y-2 pb-2">
                        <PessoaDocumentosPanel clienteId={parte.cliente_id} />
                      </CollapsibleContent>
                    </Collapsible>
                  )}
                </div>
              ))
            );
            return (
              <TabsContent key={t.grupo} value={t.grupo} className="space-y-3" data-testid={`certidoes-subtab-conteudo-${t.grupo}`}>
                {t.grupo === "antigo_proprietario" ? (
                  <AntigosProprietariosPainel clienteId={clienteId} atendimentoId={atendimentoId}>{linhasDoGrupo}</AntigosProprietariosPainel>
                ) : linhasDoGrupo}
              </TabsContent>
            );
          })}
        </Tabs>
      </TooltipProvider>

      <Dialog open={!!detalhes} onOpenChange={(o) => { if (!o) { setDetalhesChave(null); void invalidar(); } }}>
        <DialogContent className="max-w-5xl">
          <DialogHeader>
            <DialogTitle>Certidões — {detalhes?.nome}</DialogTitle>
            <DialogDescription>Registre, envie ou corrija as certidões desta parte.</DialogDescription>
          </DialogHeader>
          {detalhes &&
            (detalhes.kind === "empresa" ? (
              <CertidoesPartePanel empresaId={detalhes.empresa_id as string} nomeParte={detalhes.nome} documento={detalhes.documento ?? undefined} />
            ) : detalhes.parte_id ? (
              <CertidoesPartePanel atendimentoParteId={detalhes.parte_id} nomeParte={detalhes.nome} documento={detalhes.documento ?? undefined} />
            ) : (
              <CertidoesPartePanel clienteId={detalhes.cliente_id as string} nomeParte={detalhes.nome} documento={detalhes.documento ?? undefined} />
            ))}
        </DialogContent>
      </Dialog>

      <Dialog open={!!digitando} onOpenChange={(o) => !o && setDigitando(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{linhaDigitando?.rotulo} — {parteDigitando?.nome}</DialogTitle>
            <DialogDescription>
              Digite os dados da certidão (número, datas e resultado). Não é preciso enviar o PDF.
            </DialogDescription>
          </DialogHeader>
          {parteDigitando && linhaDigitando && celulaDigitando && (
            <ResultadoEditForm
              resultado={{
                tipo: linhaDigitando.tipo, numero: celulaDigitando.numero, emitida_em: celulaDigitando.emitida_em,
                validade_ate: celulaDigitando.validade_ate, resultado: celulaDigitando.resultado,
              }}
              saving={digitar.isPending}
              onCancel={() => setDigitando(null)}
              onConfirm={(patch) =>
                digitar.mutate(
                  {
                    kind: parteDigitando.kind,
                    alvoId: (parteDigitando.kind === "empresa" ? parteDigitando.empresa_id : parteDigitando.cliente_id) as string,
                    linhaChave: linhaDigitando.chave,
                    resultadoId: celulaDigitando.resultado_id,
                    patch,
                  },
                  { onSuccess: () => setDigitando(null) },
                )
              }
            />
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={adicionando} onOpenChange={(o) => !o && fecharAdicionar()}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Adicionar certidão</DialogTitle>
            <DialogDescription>Cria uma nova linha aplicável a todas as partes deste atendimento.</DialogDescription>
          </DialogHeader>
          <Label htmlFor="certidoes-partes-novo-nome">Nome da certidão</Label>
          <Input id="certidoes-partes-novo-nome" value={novoNome} onChange={(e) => setNovoNome(e.target.value)} placeholder="Ex.: Consulta Municipal" data-testid="certidoes-partes-novo-nome-input" />
          <DialogFooter>
            <Button disabled={!novoNome.trim() || criar.isPending} data-testid="certidoes-partes-adicionar-confirmar"
              onClick={() => criar.mutate(novoNome.trim(), { onSuccess: fecharAdicionar })}>
              Adicionar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!renomeando} onOpenChange={(o) => !o && setRenomeando(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>Renomear certidão</DialogTitle></DialogHeader>
          <Label htmlFor="certidoes-partes-ren-nome">Nome da certidão</Label>
          <Input id="certidoes-partes-ren-nome" value={nomeRen} onChange={(e) => setNomeRen(e.target.value)} />
          <DialogFooter>
            <Button disabled={!nomeRen.trim() || renomear.isPending}
              onClick={() => renomeando && renomear.mutate({ linhaId: renomeando.id as string, nome: nomeRen.trim() }, { onSuccess: () => setRenomeando(null) })}>
              Salvar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog open={!!removendoAntigo} onOpenChange={(o) => !o && setRemovendoAntigo(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remover antigo proprietário</AlertDialogTitle>
            <AlertDialogDescription>
              Remover "{removendoAntigo?.nome}" do card? Uma linha vinda da matrícula volta na próxima sincronização, a menos que a exigência seja dispensada.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction className="bg-destructive hover:bg-destructive/90" data-testid="antigo-remover-confirmar"
              onClick={() => removendoAntigo?.parte_id && removerAntigo.mutate(removendoAntigo.parte_id, { onSettled: () => setRemovendoAntigo(null) })}>
              Remover
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={!!removendo} onOpenChange={(o) => !o && setRemovendo(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remover certidão</AlertDialogTitle>
            <AlertDialogDescription>
              Tem certeza que deseja remover a linha "{removendo?.rotulo}"? Os resultados já registrados NÃO serão apagados.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction className="bg-destructive hover:bg-destructive/90"
              onClick={() => removendo && remover.mutate(removendo.id as string, { onSuccess: () => setRemovendo(null) })}>
              Remover
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

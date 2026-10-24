/**
 * One collapsible section per party (COMP n / VEND n / EMP n). Header: label
 * + nome + documento + compact status summary + stale flag. Body (lazy, only
 * when open): that party's levantamento table with per-row actions.
 */
import { Fragment, useRef, useState } from "react";
import { AlertTriangle, ChevronDown, ChevronRight, Download, ExternalLink, FileSearch, Loader2, Pencil, RefreshCw, Trash2, Upload, XCircle } from "lucide-react";
import { toast } from "sonner";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { formatDate } from "@/lib/utils";
import { useMintResultadoUrl } from "@/hooks/useCertidoes";
import type {
  CertidaoDivergencia,
  CienciaPcenResult,
  CertidaoParte,
  CertidaoParteCelula,
  CertidaoParteLinha,
  SolicitarEmissaoInput,
  UploadCelulaInput,
} from "@/types/certidoesPartes";

import { CertidaoCelulaChip } from "./CertidaoCelulaChip";
import { PcenCiencia } from "./PcenCiencia";
import {
  avisoVencida,
  formatarDocumento,
  linhaDivergencia,
  jaVigenteOuEmEmissao,
  notaSegundaVia,
  podeCancelarEmissao,
  podeDescartarEmissao,
  podeReemitirComErro,
  podeVoltarAoAutomatico,
  podeReler,
  progressoDaParte,
  relendoCelula,
  resumoDaParte,
  tipoAutomatico,
} from "./certidoesCelula";

export interface ParteSecaoProps {
  parte: CertidaoParte;
  linhas: CertidaoParteLinha[];
  dataReferencia: string;
  emissaoPendente: boolean;
  onSolicitar: (input: SolicitarEmissaoInput) => void;
  onReemitir: (resultadoId: string) => void;
  onUpload: (input: UploadCelulaInput) => void;
  /** The server's refusal of the last upload/emission, by linha chave (`*` =
   *  the whole party) — drawn on the row until the next attempt (F86). */
  recusas?: Record<string, string>;
  /** The linha chave whose PDF upload is in flight for this party, if any. */
  enviandoLinha?: string | null;
  /** Re-read the PDF already stored for this certidão (no new file). */
  onReler: (resultadoId: string) => void;
  /** The resultado whose re-read request is in flight, if any. */
  relendoId: string | null;
  /** "Reler todas" for this party — every re-readable cell not already being read. */
  onRelerParte: (resultadoIds: string[]) => void;
  /** This party's "Reler todas" request is in flight. */
  relendoParte: boolean;
  /** Apply what a re-read found (human decision; locks the row). */
  onAplicarLidos: (resultadoId: string, divergencias: CertidaoDivergencia[]) => void;
  /** The resultado whose "Aplicar valores lidos" request is in flight. */
  aplicandoId: string | null;
  onDetalhes: (parte: CertidaoParte) => void;
  /** Type the cell by hand (no document needed) — opens the shared edit form. */
  onDigitar: (parte: CertidaoParte, linha: CertidaoParteLinha) => void;
  /** "Voltar à leitura automática": release a hand-edited cell to the automatic source. */
  onVoltarAutomatico: (resultadoId: string) => void;
  /** The resultado whose release request is in flight. */
  voltandoId: string | null;
  /** Stop ONE emission running right now (automatic cells only). */
  onCancelarCelula: (resultadoId: string) => void;
  cancelandoId: string | null;
  /** Stop every emission of this party running right now. */
  onCancelarParte: () => void;
  cancelandoParte: boolean;
  /** Retry ONLY this party's failed automatic cells, in place. */
  onReemitirErros: () => void;
  reemitindoErros: boolean;
  /** Throw away a wrong emission so the previous evidence wins again. */
  onDescartar: (resultadoId: string) => void;
  descartandoId: string | null;
  /** "Baixar todas (.zip)" of this party. */
  onBaixarZip: () => void;
  baixandoZip: boolean;
  onAdicionar: () => void;
  onRenomear: (linha: CertidaoParteLinha) => void;
  onRemover: (linha: CertidaoParteLinha) => void;
  /** Receita PCEN 2ª via acknowledgment / support question. */
  onCienciaPcen: (resultadoId: string, acao: "entendi" | "duvida") => Promise<CienciaPcenResult>;
}

/** The cell carries values (typed or read) — not a bare pending placeholder. */
const temValores = (c: CertidaoParteCelula) =>
  !!(c.resultado || c.numero || c.emitida_em || c.validade_ate);
/** A human typed/confirmed these values (`resultado_origem='manual'`). */
const digitada = (c: CertidaoParteCelula) => c.origem === "manual" && temValores(c);

export function ParteSecao(p: ParteSecaoProps) {
  const { parte, linhas } = p;
  const [aberta, setAberta] = useState(false);
  const [selecionadas, setSelecionadas] = useState<Set<string>>(new Set());
  // An emission is PAID (InfoSimples) — every request goes through this confirmation first.
  const [pedido, setPedido] = useState<{
    executar: () => void; nomes: string[]; daSelecao: boolean; ignorados: string[];
  } | null>(null);
  // Discarding is destructive (the cell loses that emission): confirm first.
  const [descartando, setDescartando] = useState<{ resultadoId: string; rotulo: string } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const alvoUpload = useRef<string | null>(null);
  const mint = useMintResultadoUrl();

  const alvoId = (parte.kind === "empresa" ? parte.empresa_id : parte.cliente_id) as string;
  const semDocumento = !parte.documento;
  const vencidas = parte.totais.vencidas;
  const celulaDe = (l: CertidaoParteLinha) => parte.celulas[l.chave];
  const pedirEmissao = (input: SolicitarEmissaoInput, daSelecao = false) => {
    const alvo = input.tipos;
    // "Todas" never re-buys a certidão that is still in date (or being emitted):
    // those are listed apart so the operator sees what will NOT be charged.
    const candidatas = linhas.filter((l) =>
      alvo === null
        ? tipoAutomatico(l.tipo) && celulaDe(l)?.status !== "na"
        : !!l.tipo && alvo.includes(l.tipo),
    );
    const ignoradas = alvo === null ? candidatas.filter((l) => jaVigenteOuEmEmissao(celulaDe(l))) : [];
    const nomes = candidatas.filter((l) => !ignoradas.includes(l)).map((l) => l.rotulo);
    if (alvo === null && nomes.length === 0) {
      toast.info("Todas as certidões automáticas desta parte já estão válidas ou em emissão.");
      return;
    }
    setPedido({ executar: () => p.onSolicitar(input), nomes, daSelecao, ignorados: ignoradas.map((l) => l.rotulo) });
  };
  const pedirReemissao = (resultadoId: string, rotulo: string) =>
    setPedido({ executar: () => p.onReemitir(resultadoId), nomes: [rotulo], daSelecao: false, ignorados: [] });
  // Failed automatic cells of this party — what "Reemitir com erro" retries.
  const comErro = linhas.filter((l) => {
    const c = celulaDe(l);
    return !!c && podeReemitirComErro(c);
  });
  const emVoo = linhas.filter((l) => {
    const c = celulaDe(l);
    return !!c && podeCancelarEmissao(c);
  });
  const pedirReemissaoDeErros = () =>
    setPedido({ executar: p.onReemitirErros, nomes: comErro.map((l) => l.rotulo), daSelecao: false, ignorados: [] });
  const progresso = progressoDaParte(parte);
  const toggle = (tipo: string) =>
    setSelecionadas((prev) => {
      const n = new Set(prev);
      if (n.has(tipo)) n.delete(tipo);
      else n.add(tipo);
      return n;
    });

  // Every cell whose stored PDF can be re-read right now (nothing in flight).
  const relerIds = linhas
    .map((l) => parte.celulas[l.chave])
    .filter((c) => c && c.status !== "na" && podeReler(c) && !relendoCelula(c))
    .map((c) => c.resultado_id as string);

  const abrirArquivo = (resultadoId: string) =>
    mint.mutate(
      { resultadoId, intent: "view" },
      { onSuccess: (r) => r?.url && window.open(r.url, "_blank", "noopener") },
    );

  const baixarArquivo = (resultadoId: string) =>
    mint.mutate(
      { resultadoId, intent: "download" },
      {
        onSuccess: (r) => {
          if (!r?.url) return;
          const a = document.createElement("a");
          a.href = r.url;
          a.rel = "noopener";
          a.click();
        },
      },
    );

  return (
    <Collapsible open={aberta} onOpenChange={setAberta} className="rounded-md border" data-testid={`parte-secao-${parte.chave}`}>
      <CollapsibleTrigger asChild>
        <button
          type="button"
          className="flex w-full items-center gap-3 p-3 text-left hover:bg-muted/40"
          data-testid={`parte-secao-header-${parte.chave}`}
          aria-expanded={aberta}
        >
          {aberta ? <ChevronDown className="h-4 w-4 shrink-0" /> : <ChevronRight className="h-4 w-4 shrink-0" />}
          <span className="text-sm font-semibold">{parte.rotulo}</span>
          <span className="min-w-0 truncate text-sm">{parte.nome}</span>
          <span className="text-xs text-muted-foreground">{formatarDocumento(parte.documento)}</span>
          <span className="ml-auto flex items-center gap-2 text-xs text-muted-foreground" data-testid={`parte-resumo-${parte.chave}`}>
            {progresso && (
              <>
                <Loader2 className="h-3 w-3 animate-spin" aria-hidden />
                <span
                  role="progressbar"
                  aria-label="Progresso da emissão"
                  aria-valuemin={0}
                  aria-valuemax={progresso.total}
                  aria-valuenow={progresso.feitas}
                  className="inline-block h-1.5 w-16 overflow-hidden rounded bg-muted"
                  data-testid={`parte-relendo-progresso-${parte.chave}`}
                >
                  <span
                    className="block h-full bg-sky-500"
                    style={{ width: `${Math.round((progresso.feitas / Math.max(progresso.total, 1)) * 100)}%` }}
                  />
                </span>
                <span data-testid={`parte-progresso-texto-${parte.chave}`}>
                  {progresso.feitas}/{progresso.total}
                </span>
              </>
            )}
            {resumoDaParte(parte)}
          </span>
          {vencidas > 0 && (
            <span
              className="flex items-center gap-1 rounded bg-amber-100 px-1.5 py-0.5 text-xs font-medium text-amber-900 dark:bg-amber-950 dark:text-amber-200"
              data-testid={`parte-stale-flag-${parte.chave}`}
            >
              <AlertTriangle className="h-3 w-3" />
              vencida p/ contrato
            </span>
          )}
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="space-y-3 border-t p-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h4 className="text-sm font-semibold">Levantamento de certidões</h4>
              <p className="text-xs text-muted-foreground">
                Data do levantamento: {formatDate(p.dataReferencia)}
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Button size="sm" variant="outline" disabled={semDocumento || p.emissaoPendente}
                title={semDocumento ? "Informe o CPF/CNPJ da parte antes de solicitar certidões." : undefined}
                onClick={() => pedirEmissao({ kind: parte.kind, alvoId, tipos: null })}
                data-testid={`parte-solicitar-todas-${parte.chave}`}>
                {p.emissaoPendente && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}
                Solicitar emissão (todas)
              </Button>
              <Button size="sm" variant="outline" disabled={semDocumento || p.emissaoPendente || selecionadas.size === 0}
                onClick={() => {
                  pedirEmissao({ kind: parte.kind, alvoId, tipos: [...selecionadas] }, true);
                }}
                data-testid={`parte-solicitar-selecionadas-${parte.chave}`}>
                Solicitar selecionadas ({selecionadas.size})
              </Button>
              {comErro.length > 0 && (
                <Button size="sm" variant="outline" disabled={semDocumento || p.reemitindoErros || p.emissaoPendente}
                  title="Tenta de novo, na mesma consulta, só as certidões que deram erro. As que deram certo não são compradas de novo."
                  onClick={pedirReemissaoDeErros}
                  data-testid={`parte-reemitir-erros-${parte.chave}`}>
                  {p.reemitindoErros ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-1 h-4 w-4" />}
                  Reemitir com erro ({comErro.length})
                </Button>
              )}
              {emVoo.length > 0 && (
                <Button size="sm" variant="outline" disabled={p.cancelandoParte}
                  onClick={p.onCancelarParte}
                  data-testid={`parte-cancelar-todas-${parte.chave}`}>
                  {p.cancelandoParte ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <XCircle className="mr-1 h-4 w-4" />}
                  Cancelar emissões ({emVoo.length})
                </Button>
              )}
              {Object.values(parte.celulas).some((c) => c.tem_arquivo) && (
                <Button size="sm" variant="outline" disabled={p.baixandoZip}
                  onClick={p.onBaixarZip}
                  data-testid={`parte-baixar-zip-${parte.chave}`}>
                  {p.baixandoZip ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Download className="mr-1 h-4 w-4" />}
                  Baixar todas (.zip)
                </Button>
              )}
              <Button size="sm" variant="outline" onClick={() => p.onDetalhes(parte)} data-testid={`parte-detalhes-${parte.chave}`}>
                <ExternalLink className="mr-1 h-4 w-4" />
                Detalhes
              </Button>
              <Button size="sm" variant="outline" onClick={p.onAdicionar} data-testid={`parte-adicionar-${parte.chave}`}>
                + Adicionar certidão
              </Button>
              {(relerIds.length > 0 || p.relendoParte) && (
                <Button size="sm" variant="outline" disabled={p.relendoParte || relerIds.length === 0}
                  title="Lê de novo, com o leitor mais recente, todos os PDFs de certidão já armazenados desta parte. Valores confirmados não são alterados."
                  onClick={() => p.onRelerParte(relerIds)}
                  data-testid={`parte-reler-todas-${parte.chave}`}>
                  {p.relendoParte ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <FileSearch className="mr-1 h-4 w-4" />}
                  Reler todas
                </Button>
              )}
            </div>
          </div>
          {p.recusas?.["*"] && (
            <p role="alert" className="text-xs text-red-700 dark:text-red-300" data-testid={`parte-recusa-${parte.chave}`}>
              {p.recusas["*"]}
            </p>
          )}

          <input
            ref={fileRef}
            type="file"
            accept="application/pdf"
            className="hidden"
            data-testid={`parte-upload-input-${parte.chave}`}
            onChange={(e) => {
              const file = e.target.files?.[0];
              const linhaChave = alvoUpload.current;
              e.target.value = "";
              if (file && linhaChave) p.onUpload({ kind: parte.kind, alvoId, linhaChave, file });
            }}
          />

          <div className="overflow-x-auto rounded-md border">
            <table className="w-full min-w-max border-collapse text-xs">
              <thead>
                <tr className="border-b bg-muted/50">
                  <th className="w-8 p-2" />
                  <th className="p-2 text-left font-semibold">Certidão</th>
                  <th className="p-2 text-left font-semibold">Situação</th>
                  <th className="p-2 text-left font-semibold">Emissão</th>
                  <th className="p-2 text-left font-semibold">Ações</th>
                </tr>
              </thead>
              <tbody>
                {linhas.map((linha) => {
                  const c = parte.celulas[linha.chave];
                  if (!c) return null;
                  const na = c.status === "na";
                  const auto = tipoAutomatico(linha.tipo);
                  const aviso = avisoVencida(c);
                  const relendo = relendoCelula(c);
                  const divergencias = !relendo ? (c.releitura?.divergencias ?? []) : [];
                  return (
                    <Fragment key={linha.chave}>
                    <tr className="border-b last:border-b-0" data-testid={`parte-linha-${parte.chave}-${linha.chave}`}>
                      <td className="p-2">
                        {auto && !na && (
                          <Checkbox
                            checked={selecionadas.has(linha.tipo as string)}
                            onCheckedChange={() => toggle(linha.tipo as string)}
                            aria-label={`Selecionar ${linha.rotulo}`}
                          />
                        )}
                      </td>
                      <td className="p-2 font-medium">
                        <span className="text-muted-foreground">{linha.linha}</span> {linha.rotulo}
                        {linha.custom && (
                          <span className="ml-1 inline-flex gap-0.5 align-middle">
                            <button type="button" title="Renomear" className="rounded p-0.5 hover:bg-muted" onClick={() => p.onRenomear(linha)}>
                              <Pencil className="h-3 w-3" />
                            </button>
                            <button type="button" title="Remover" className="rounded p-0.5 hover:bg-destructive/10" onClick={() => p.onRemover(linha)}>
                              <Trash2 className="h-3 w-3" />
                            </button>
                          </span>
                        )}
                      </td>
                      <td className="p-2">
                        <CertidaoCelulaChip celula={c} testId={`parte-chip-${parte.chave}-${linha.chave}`} />
                        {digitada(c) && (
                          <span className="ml-1 inline-block rounded bg-secondary px-1.5 py-0.5 text-xs font-medium text-secondary-foreground"
                            data-testid={`parte-digitado-${parte.chave}-${linha.chave}`}>
                            Digitado
                          </span>
                        )}
                        {c.status_processamento === "erro" && c.erro_mensagem && !c.pendencia && (
                          <p className="mt-0.5 max-w-xs text-xs text-red-700 dark:text-red-300" data-testid={`parte-erro-${parte.chave}-${linha.chave}`}>
                            {c.erro_mensagem}
                          </p>
                        )}
                        {c.pendencia && c.erro_mensagem && (
                          <p className="mt-0.5 text-xs text-muted-foreground" data-testid={`parte-pendencia-${parte.chave}-${linha.chave}`}>
                            {c.erro_mensagem}
                          </p>
                        )}
                        {p.recusas?.[linha.chave] && (
                          <p role="alert" className="mt-0.5 max-w-xs text-xs text-red-700 dark:text-red-300" data-testid={`parte-recusa-${parte.chave}-${linha.chave}`}>
                            {p.recusas[linha.chave]}
                          </p>
                        )}
                      </td>
                      <td className="p-2">
                        {c.emitida_em ? formatDate(c.emitida_em) : "—"}
                        {c.emitida_em && (c.emitida_em_origem === "metadados_pdf" || c.emitida_em_origem === "data_da_consulta") && (
                          <p className="mt-0.5 text-xs text-muted-foreground" data-testid={`parte-data-inferida-${parte.chave}-${linha.chave}`}>
                            {c.emitida_em_origem === "data_da_consulta"
                              ? "Data inferida do dia da consulta (o documento não imprime data)"
                              : "Data inferida dos metadados do PDF (a consulta não imprime data)"}
                          </p>
                        )}
                        {c.numero && (
                          <p className="mt-0.5 text-xs text-muted-foreground" data-testid={`parte-numero-${parte.chave}-${linha.chave}`}>
                            Nº {c.numero}
                          </p>
                        )}
                        {notaSegundaVia(c) && (
                          <p className="mt-0.5 text-xs text-muted-foreground" data-testid={`parte-segunda-via-${parte.chave}-${linha.chave}`}>
                            {notaSegundaVia(c)}
                          </p>
                        )}
                        {aviso && (
                          <p className="mt-0.5 flex items-center gap-1 text-amber-700 dark:text-amber-300" data-testid={`parte-stale-${parte.chave}-${linha.chave}`}>
                            <AlertTriangle className="h-3 w-3" />
                            {aviso}
                          </p>
                        )}
                      </td>
                      <td className="p-2">
                        {!na && (
                          <div className="flex flex-wrap items-center gap-1">
                            {auto && c.resultado_id && !c.pendencia && (
                              <Button size="sm" variant={c.stale_para_contrato ? "default" : "ghost"} className="h-7 px-2 text-xs"
                                onClick={() => pedirReemissao(c.resultado_id as string, linha.rotulo)}
                                data-testid={`parte-reemitir-${parte.chave}-${linha.chave}`}>
                                <RefreshCw className="mr-1 h-3 w-3" />
                                Re-emitir
                              </Button>
                            )}
                            {auto && !c.resultado_id && (
                              <Button size="sm" variant="ghost" className="h-7 px-2 text-xs" disabled={semDocumento || p.emissaoPendente}
                                onClick={() => pedirEmissao({ kind: parte.kind, alvoId, tipos: [linha.tipo as string] })}
                                data-testid={`parte-solicitar-${parte.chave}-${linha.chave}`}>
                                Solicitar
                              </Button>
                            )}
                            <Button size="sm" variant="ghost" className="h-7 px-2 text-xs"
                              onClick={() => p.onDigitar(parte, linha)}
                              data-testid={`parte-digitar-${parte.chave}-${linha.chave}`}>
                              <Pencil className="mr-1 h-3 w-3" />
                              {temValores(c) ? "Editar" : "Preencher manualmente"}
                            </Button>
                            <Button size="sm" variant="ghost" className="h-7 px-2 text-xs"
                              disabled={p.enviandoLinha === linha.chave}
                              onClick={() => {
                                alvoUpload.current = linha.chave;
                                fileRef.current?.click();
                              }}
                              data-testid={`parte-upload-${parte.chave}-${linha.chave}`}>
                              {p.enviandoLinha === linha.chave
                                ? <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                                : <Upload className="mr-1 h-3 w-3" />}
                              {p.enviandoLinha === linha.chave ? "Enviando…" : "Enviar PDF"}
                            </Button>
                            {podeVoltarAoAutomatico(c) && (
                              <Button size="sm" variant="ghost" className="h-7 px-2 text-xs"
                                disabled={p.voltandoId === c.resultado_id}
                                title="Descarta o que foi digitado/confirmado e volta a ler esta certidão automaticamente (PDF armazenado ou Crednet)."
                                onClick={() => p.onVoltarAutomatico(c.resultado_id as string)}
                                data-testid={`parte-voltar-automatico-${parte.chave}-${linha.chave}`}>
                                {p.voltandoId === c.resultado_id
                                  ? <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                                  : <RefreshCw className="mr-1 h-3 w-3" />}
                                Voltar à leitura automática
                              </Button>
                            )}
                            {podeReler(c) && (
                              <Button size="sm" variant="ghost" className="h-7 px-2 text-xs"
                                disabled={relendo || p.relendoId === c.resultado_id}
                                title="Lê de novo o PDF já armazenado, com o leitor mais recente. Valores confirmados não são alterados."
                                onClick={() => p.onReler(c.resultado_id as string)}
                                data-testid={`parte-linha-${parte.chave}-${linha.chave}-reextrair`}>
                                {relendo || p.relendoId === c.resultado_id
                                  ? <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                                  : <FileSearch className="mr-1 h-3 w-3" />}
                                {relendo ? "Relendo…" : "Reler"}
                              </Button>
                            )}
                            {c.tem_arquivo && c.resultado_id && (
                              <Button size="sm" variant="ghost" className="h-7 px-2 text-xs" onClick={() => abrirArquivo(c.resultado_id as string)}>
                                Ver PDF
                              </Button>
                            )}
                            {c.tem_arquivo && c.resultado_id && (
                              <Button size="sm" variant="ghost" className="h-7 px-2 text-xs"
                                disabled={mint.isPending}
                                onClick={() => baixarArquivo(c.resultado_id as string)}
                                title="Baixar o PDF desta certidão"
                                data-testid={`parte-baixar-${parte.chave}-${linha.chave}`}>
                                <Download className="mr-1 h-3 w-3" />
                                Baixar
                              </Button>
                            )}
                            {podeCancelarEmissao(c) && (
                              <Button size="sm" variant="ghost" className="h-7 px-2 text-xs"
                                disabled={p.cancelandoId === c.resultado_id}
                                title="Interrompe esta emissão em andamento."
                                onClick={() => p.onCancelarCelula(c.resultado_id as string)}
                                data-testid={`parte-cancelar-${parte.chave}-${linha.chave}`}>
                                {p.cancelandoId === c.resultado_id
                                  ? <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                                  : <XCircle className="mr-1 h-3 w-3" />}
                                Cancelar emissão
                              </Button>
                            )}
                            {podeDescartarEmissao(c) && (
                              <Button size="sm" variant="ghost" className="h-7 px-2 text-xs text-destructive"
                                disabled={p.descartandoId === c.resultado_id}
                                title="Descarta esta emissão: vale de novo a certidão anterior (ou a célula fica vazia)."
                                onClick={() => setDescartando({ resultadoId: c.resultado_id as string, rotulo: linha.rotulo })}
                                data-testid={`parte-descartar-${parte.chave}-${linha.chave}`}>
                                {p.descartandoId === c.resultado_id
                                  ? <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                                  : <Trash2 className="mr-1 h-3 w-3" />}
                                Descartar emissão
                              </Button>
                            )}
                          </div>
                        )}
                      </td>
                    </tr>
                    {divergencias.length > 0 && c.resultado_id && (
                      <tr className="border-b last:border-b-0">
                        <td colSpan={5} className="p-2">
                          <div className="flex flex-wrap items-start justify-between gap-2 rounded border border-amber-300 bg-amber-50 p-2 text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200"
                            data-testid={`parte-divergencia-${parte.chave}-${linha.chave}`}>
                            <div className="space-y-0.5">
                              <p className="flex items-center gap-1 font-medium">
                                <AlertTriangle className="h-3 w-3" />
                                A releitura encontrou valores diferentes dos registrados — nada foi alterado.
                              </p>
                              {divergencias.map((d) => <p key={d.campo}>{linhaDivergencia(d)}</p>)}
                            </div>
                            <Button size="sm" variant="outline" className="h-7 px-2 text-xs"
                              disabled={p.aplicandoId === c.resultado_id}
                              onClick={() => p.onAplicarLidos(c.resultado_id as string, divergencias)}
                              data-testid={`parte-aplicar-lidos-${parte.chave}-${linha.chave}`}>
                              {p.aplicandoId === c.resultado_id && <Loader2 className="mr-1 h-3 w-3 animate-spin" />}
                              Aplicar valores lidos
                            </Button>
                          </div>
                        </td>
                      </tr>
                    )}
                    {c.pcen && !c.pcen.vencida && c.resultado_id && (
                      <tr className="border-b last:border-b-0">
                        <td colSpan={5} className="p-2">
                          <PcenCiencia
                            testId={`parte-pcen-${parte.chave}-${linha.chave}`}
                            titulo={c.pcen.titulo}
                            explicacao={c.pcen.explicacao}
                            validadeAte={c.pcen.validade_ate}
                            ciente={c.pcen.ciente}
                            acoes={c.pcen.acoes}
                            contexto={`${parte.rotulo} ${parte.nome}`}
                            onEntendi={() => p.onCienciaPcen(c.resultado_id as string, "entendi")}
                            onDuvida={() => p.onCienciaPcen(c.resultado_id as string, "duvida")}
                          />
                        </td>
                      </tr>
                    )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </CollapsibleContent>
      <AlertDialog open={pedido !== null} onOpenChange={(o) => !o && setPedido(null)}>
        <AlertDialogContent data-testid={`parte-confirmar-emissao-${parte.chave}`}>
          <AlertDialogHeader>
            <AlertDialogTitle>Solicitar emissão paga?</AlertDialogTitle>
            <AlertDialogDescription asChild>
              <div className="space-y-2">
                <p>
                  Esta é uma emissão <strong>paga</strong> (InfoSimples): cada certidão solicitada (ou re-emitida) gera
                  cobrança para {parte.nome}.
                </p>
                {pedido && pedido.ignorados.length > 0 && (
                  <div data-testid={`parte-confirmar-emissao-ignoradas-${parte.chave}`}>
                    <p>
                      {pedido.ignorados.length === 1
                        ? "1 certidão já válida (ou em emissão) não será comprada de novo:"
                        : `${pedido.ignorados.length} certidões já válidas (ou em emissão) não serão compradas de novo:`}
                    </p>
                    <ul className="list-disc pl-5 text-muted-foreground">
                      {pedido.ignorados.map((n) => (
                        <li key={n}>{n}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {pedido && pedido.nomes.length > 0 && (
                  <ul className="list-disc pl-5" data-testid={`parte-confirmar-emissao-lista-${parte.chave}`}>
                    {pedido.nomes.map((n) => (
                      <li key={n}>{n}</li>
                    ))}
                  </ul>
                )}
              </div>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel data-testid={`parte-confirmar-emissao-cancelar-${parte.chave}`}>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              data-testid={`parte-confirmar-emissao-ok-${parte.chave}`}
              onClick={() => {
                if (!pedido) return;
                pedido.executar();
                if (pedido.daSelecao) setSelecionadas(new Set());
                setPedido(null);
              }}
            >
              Confirmar e emitir
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
      <AlertDialog open={descartando !== null} onOpenChange={(o) => !o && setDescartando(null)}>
        <AlertDialogContent data-testid={`parte-confirmar-descarte-${parte.chave}`}>
          <AlertDialogHeader>
            <AlertDialogTitle>Descartar esta emissão?</AlertDialogTitle>
            <AlertDialogDescription>
              A emissão de "{descartando?.rotulo}" será descartada. Vale de novo a certidão anterior desta parte, se
              houver; senão a célula fica vazia. A emissão descartada pode ser restaurada pelo suporte.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel data-testid={`parte-confirmar-descarte-cancelar-${parte.chave}`}>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive hover:bg-destructive/90"
              data-testid={`parte-confirmar-descarte-ok-${parte.chave}`}
              onClick={() => {
                if (descartando) p.onDescartar(descartando.resultadoId);
                setDescartando(null);
              }}
            >
              Descartar emissão
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Collapsible>
  );
}

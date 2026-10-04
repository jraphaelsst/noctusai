/**
 * One collapsible section per party (COMP n / VEND n / EMP n). Header: label
 * + nome + documento + compact status summary + stale flag. Body (lazy, only
 * when open): that party's levantamento table with per-row actions.
 */
import { Fragment, useRef, useState } from "react";
import { AlertTriangle, ChevronDown, ChevronRight, ExternalLink, FileSearch, Loader2, Pencil, RefreshCw, Trash2, Upload } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { formatDate } from "@/lib/utils";
import { useMintResultadoUrl } from "@/hooks/useCertidoes";
import type {
  CertidaoDivergencia,
  CienciaPcenResult,
  CertidaoParte,
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
  notaSegundaVia,
  podeReler,
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
  onAdicionar: () => void;
  onRenomear: (linha: CertidaoParteLinha) => void;
  onRemover: (linha: CertidaoParteLinha) => void;
  /** Receita PCEN 2ª via acknowledgment / support question. */
  onCienciaPcen: (resultadoId: string, acao: "entendi" | "duvida") => Promise<CienciaPcenResult>;
}

export function ParteSecao(p: ParteSecaoProps) {
  const { parte, linhas } = p;
  const [aberta, setAberta] = useState(false);
  const [selecionadas, setSelecionadas] = useState<Set<string>>(new Set());
  const fileRef = useRef<HTMLInputElement>(null);
  const alvoUpload = useRef<string | null>(null);
  const mint = useMintResultadoUrl();

  const alvoId = (parte.kind === "empresa" ? parte.empresa_id : parte.cliente_id) as string;
  const semDocumento = !parte.documento;
  const vencidas = parte.totais.vencidas;
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
                onClick={() => p.onSolicitar({ kind: parte.kind, alvoId, tipos: null })}
                data-testid={`parte-solicitar-todas-${parte.chave}`}>
                {p.emissaoPendente && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}
                Solicitar emissão (todas)
              </Button>
              <Button size="sm" variant="outline" disabled={semDocumento || p.emissaoPendente || selecionadas.size === 0}
                onClick={() => {
                  p.onSolicitar({ kind: parte.kind, alvoId, tipos: [...selecionadas] });
                  setSelecionadas(new Set());
                }}
                data-testid={`parte-solicitar-selecionadas-${parte.chave}`}>
                Solicitar selecionadas ({selecionadas.size})
              </Button>
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
                        {c.pendencia && c.erro_mensagem && (
                          <p className="mt-0.5 text-xs text-muted-foreground" data-testid={`parte-pendencia-${parte.chave}-${linha.chave}`}>
                            {c.erro_mensagem}
                          </p>
                        )}
                      </td>
                      <td className="p-2">
                        {c.emitida_em ? formatDate(c.emitida_em) : "—"}
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
                                onClick={() => p.onReemitir(c.resultado_id as string)}
                                data-testid={`parte-reemitir-${parte.chave}-${linha.chave}`}>
                                <RefreshCw className="mr-1 h-3 w-3" />
                                Re-emitir
                              </Button>
                            )}
                            {auto && !c.resultado_id && (
                              <Button size="sm" variant="ghost" className="h-7 px-2 text-xs" disabled={semDocumento || p.emissaoPendente}
                                onClick={() => p.onSolicitar({ kind: parte.kind, alvoId, tipos: [linha.tipo as string] })}
                                data-testid={`parte-solicitar-${parte.chave}-${linha.chave}`}>
                                Solicitar
                              </Button>
                            )}
                            <Button size="sm" variant="ghost" className="h-7 px-2 text-xs"
                              onClick={() => {
                                alvoUpload.current = linha.chave;
                                fileRef.current?.click();
                              }}
                              data-testid={`parte-upload-${parte.chave}-${linha.chave}`}>
                              <Upload className="mr-1 h-3 w-3" />
                              Enviar PDF
                            </Button>
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
    </Collapsible>
  );
}

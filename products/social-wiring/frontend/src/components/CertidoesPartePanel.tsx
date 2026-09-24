/**
 * `<CertidoesPartePanel/>` — one person's structured certidões, contract
 * automation F1 + F6.
 *
 * Self-contained: a caller supplies EXACTLY ONE of `atendimentoParteId`
 * (`atendimento_partes.id`, any other party) or `clienteId`
 * (`atendimentos.cliente_id`, the card's TITULAR) — every fetch and mutation
 * on this panel keys off whichever one it got. The titular has no
 * `atendimento_partes` row at all (migration 073's header), so migration 116
 * added the sibling cliente-scoped routes this panel now also speaks.
 * Intended mount points are `ClienteCardDialog`'s per-parte section AND its
 * titular ("Dados do cliente") tab; the panel itself does not know or care
 * what dialog it lives in, the same way `PessoaDocumentosPanel` does not.
 *
 * Four states, honestly (`KB § PATTERNS/frontend/lying-loading-state.md`):
 * `showSkeleton = isPending && !data`, `isRefreshing = isFetching && !!data`
 * (an indicator only — the table stays mounted through a background poll),
 * an error banner that keeps showing stale data when there is any, and an
 * empty state offering the one action that gets a person their first
 * resultado: linking an already-created consulta.
 *
 * IA/api-derived values are rendered as suggestions (a muted "Sugestão — a
 * confirmar" caption) until a human opens the edit dialog and submits —
 * even an unedited submit is a valid confirmation, per
 * `PATCH /resultados/{id}`'s own contract.
 *
 * 🔴 BOTH `useResultadosPorParte` AND `useResultadosPorCliente` ARE ALWAYS
 * CALLED (rules-of-hooks forbids picking WHICH hook to call at runtime).
 * Each is `enabled` only for its own id (`@/hooks/useCertidoes`), so the
 * unused one never fires a request — only its inert query object exists.
 */
import { useMemo, useState } from "react";
import {
  AlertTriangle,
  Check,
  ClipboardEdit,
  Copy,
  Download,
  Eye,
  FileDown,
  FileText,
  Link2,
  Loader2,
  Pencil,
  Upload,
} from "lucide-react";

import { TableSkeleton } from "@noctusai/lib/design-system";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@noctusai/seed/components/ui/table";

import { Badge } from "@/components/ui/badge";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  useAtualizarSituacaoCadastral,
  useCertidaoConsultas,
  useConfirmarResultado,
  useCopiarTranscricao,
  useCriarConsultaManual,
  useDownloadTranscricaoPdf,
  useMintResultadoUrl,
  useResultadosPorCliente,
  useResultadosPorEmpresa,
  useResultadosPorParte,
  useUploadResultadoManual,
  useVincularCliente,
  useVincularEmpresa,
  useVincularParte,
} from "@/hooks/useCertidoes";
import type { CertidaoResultado } from "@/hooks/useCertidoes";
import { downloadFile } from "@/lib/file-download";
import { formatDate } from "@/lib/utils";
import {
  RESULTADO_ORIGEM_LABELS,
  RESULTADO_VALOR_LABELS,
  RESULTADO_VALOR_VARIANT,
  SITUACAO_CADASTRAL_BADGE_VARIANT,
  SITUACAO_CADASTRAL_LABELS,
  isEmissaoAntiga,
  isValidadeVencendo,
  isValidadeVencida,
  situacaoCadastralBadge,
  type ResultadoPatchInput,
  type ResultadoValor,
  type SituacaoCadastral,
  type SituacaoCadastralPatchInput,
} from "@/types/certidoesEstruturadas";

const UPLOAD_INPUT_TESTID = "certidoes-parte-upload-input";

/** `certidao_resultados.status` — the existing scrape-pipeline status, kept
 * local to this panel so it does not depend on `pages/Certidoes.tsx`'s
 * unexported `RESULTADO_STATUS_ICON` (a second module owning the same map
 * would be a real import, not a duplication, but that page is out of scope
 * for this slice — see this file's `scoped-improvement:` footer). */
const STATUS_LABELS: Record<string, string> = {
  pendente: "Pendente",
  processando: "Processando",
  na_fila: "Pendente (TJSP)",
  sucesso: "Concluída",
  erro: "Erro",
};

export interface CertidoesPartePanelProps {
  /** `atendimento_partes.id` — any party OTHER than the titular. Exactly one
   *  of this, `clienteId` and `empresaId` must be supplied. */
  atendimentoParteId?: string;
  /** `atendimentos.cliente_id` — the card's TITULAR (migration 116), who has
   *  no `atendimento_partes` row to key off (migration 073's header).
   *  Exactly one of this, `atendimentoParteId` and `empresaId` must be
   *  supplied. */
  clienteId?: string;
  /** `empresas.id` — a company on the card (P0c contract, `project-history/
   *  roadmaps/sw-drive-extraction-P0c-contract.md` §D.5/§F). Exactly one of
   *  this, `atendimentoParteId` and `clienteId` must be supplied. Unlike the
   *  two person-scoped modes, "Registrar certidões manualmente" ALWAYS
   *  creates a `tipo_documento: 'cnpj'` consulta in this mode — the type
   *  selector is hidden — and links it via `vincular-empresa` right after
   *  creation, since `POST /consultas/manual` has no empresa link param
   *  (§D.5: "every link goes through `vincular-*`"). */
  empresaId?: string;
  /** Optional label for the empty-state copy; the panel works without it —
   * a linked consulta's own `nome`/`documento` cover the rest once one exists. */
  nomeParte?: string;
  /** This person's/company's own CPF/CNPJ, when the caller already has one
   * on file (`ClienteCardDialog`'s `parte.cliente?.cpf` for a party,
   * `dadosPessoais?.cpf` for the titular, `empresa.cnpj` for a company) —
   * prefills "Registrar certidões manualmente" so the operator does not
   * retype it. Still fully editable; `undefined` simply leaves the field
   * blank, exactly as before this prop existed. */
  documento?: string;
}

export function CertidoesPartePanel({
  atendimentoParteId,
  clienteId,
  empresaId,
  documento,
  nomeParte,
}: CertidoesPartePanelProps) {
  // See this file's docblock: all three hooks always run; only the one
  // matching the id this instance was given is `enabled`.
  const resultadosParte = useResultadosPorParte(atendimentoParteId);
  const resultadosCliente = useResultadosPorCliente(clienteId);
  const resultadosEmpresa = useResultadosPorEmpresa(empresaId);
  const resultados = clienteId
    ? resultadosCliente
    : empresaId
      ? resultadosEmpresa
      : resultadosParte;

  const consultas = useCertidaoConsultas();
  const vincularParte = useVincularParte();
  const vincularCliente = useVincularCliente();
  const vincularEmpresa = useVincularEmpresa();
  const vincular = clienteId ? vincularCliente : empresaId ? vincularEmpresa : vincularParte;
  const confirmar = useConfirmarResultado({ atendimentoParteId, clienteId, empresaId });
  const upload = useUploadResultadoManual({ atendimentoParteId, clienteId, empresaId });
  const situacaoCadastral = useAtualizarSituacaoCadastral({
    atendimentoParteId,
    clienteId,
    empresaId,
  });
  const criarManual = useCriarConsultaManual();
  const mintUrl = useMintResultadoUrl();
  // ABNT formatting project (`projects/abnt-formatting-CONTRACT.md` § 6) —
  // shared with `pages/Certidoes.tsx`'s own detail table so the fetch +
  // clipboard sequence is written once.
  const downloadTranscricaoPdf = useDownloadTranscricaoPdf();
  const { copiar: copiarTranscricao, activeId: copiandoId } = useCopiarTranscricao();

  const [vincularAberto, setVincularAberto] = useState(false);
  const [consultaEscolhida, setConsultaEscolhida] = useState("");
  const [editando, setEditando] = useState<CertidaoResultado | null>(null);
  const [uploadAlvo, setUploadAlvo] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [manualAberto, setManualAberto] = useState(false);
  const [manualNome, setManualNome] = useState(nomeParte ?? "");
  const [manualTipoDocumento, setManualTipoDocumento] = useState<"cpf" | "cnpj">("cpf");
  const [manualDocumento, setManualDocumento] = useState(documento ?? "");

  const handleCopiarTranscricao = (resultadoId: string) => {
    copiarTranscricao(resultadoId, () => {
      setCopiedId(resultadoId);
      setTimeout(() => setCopiedId((current) => (current === resultadoId ? null : current)), 2000);
    });
  };

  // Two signals off `data`, never `isLoading` — the query's key includes
  // `atendimentoParteId` and carries `placeholderData`, so switching parties
  // does not blank the table either.
  const showSkeleton = resultados.isPending && !resultados.data;
  const isRefreshing = resultados.isFetching && !!resultados.data;
  const data = resultados.data ?? [];

  // `situacao_cadastral` is a fact about the CONSULTA (migration 116), not
  // any one resultado — every resultado row of the same consulta carries the
  // identical denormalized value, so this de-dupes to one editor per CNPJ
  // consulta linked to this person, however many resultado rows it fanned
  // out into.
  const consultasCnpj = useMemo(() => {
    const porConsulta = new Map<string, CertidaoResultado>();
    for (const r of data) {
      if (r.consulta_tipo_documento === "cnpj" && !porConsulta.has(r.consulta_id)) {
        porConsulta.set(r.consulta_id, r);
      }
    }
    return [...porConsulta.values()];
  }, [data]);

  // No linkage set at all — a fully unlinked ad-hoc consulta.
  // `vincular_parte`/`vincular_cliente`/`vincular_empresa` each denormalize
  // their own id onto the consulta (migration 107/116/167), so checking
  // `atendimento_parte_id` alone would re-offer a consulta already claimed
  // by a titular or a company.
  const consultasDisponiveis = (consultas.data ?? []).filter(
    (c) => !c.atendimento_parte_id && !c.cliente_id && !c.empresa_id,
  );

  const handleVincular = () => {
    if (!consultaEscolhida) return;
    const onSuccess = () => {
      setVincularAberto(false);
      setConsultaEscolhida("");
    };
    if (clienteId) {
      vincularCliente.mutate({ consultaId: consultaEscolhida, clienteId }, { onSuccess });
    } else if (empresaId) {
      vincularEmpresa.mutate({ consultaId: consultaEscolhida, empresaId }, { onSuccess });
    } else if (atendimentoParteId) {
      vincularParte.mutate(
        { consultaId: consultaEscolhida, atendimentoParteId },
        { onSuccess },
      );
    }
  };

  const handleAbrirRegistroManual = () => {
    setManualNome(nomeParte ?? "");
    // A company's manual registration is always a CNPJ — the type selector
    // is hidden in this mode (see the dialog below), so this just keeps the
    // state consistent with what is shown.
    setManualTipoDocumento(empresaId ? "cnpj" : "cpf");
    setManualDocumento(documento ?? "");
    setManualAberto(true);
  };

  const handleRegistrarManual = () => {
    if (!manualNome.trim() || !manualDocumento.trim()) return;
    // `POST /consultas/manual` has no `empresa_id` link param (P0c contract
    // §D.5 — "every link goes through `vincular-*`"), unlike the
    // person-scoped modes which link in the SAME request. So the empresa
    // path is create-then-link, exactly like "Vincular consulta" above,
    // just chained instead of two separate operator actions.
    if (empresaId) {
      criarManual.mutate(
        {
          tipo_documento: "cnpj",
          documento: manualDocumento.trim(),
          nome: manualNome.trim(),
        },
        {
          onSuccess: (consulta) => {
            vincularEmpresa.mutate(
              { consultaId: consulta.id, empresaId },
              { onSuccess: () => setManualAberto(false) },
            );
          },
        },
      );
      return;
    }
    criarManual.mutate(
      {
        tipo_documento: manualTipoDocumento,
        documento: manualDocumento.trim(),
        nome: manualNome.trim(),
        atendimentoParteId,
        clienteId,
      },
      { onSuccess: () => setManualAberto(false) },
    );
  };

  const handleUploadClick = (resultadoId: string) => {
    setUploadAlvo(resultadoId);
    document.querySelector<HTMLInputElement>(`[data-testid="${UPLOAD_INPUT_TESTID}"]`)?.click();
  };

  const handleUploadFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    // Reset immediately so re-picking the SAME file still fires `change`.
    e.target.value = "";
    if (!file || !uploadAlvo) return;
    upload.mutate({ resultadoId: uploadAlvo, file });
    setUploadAlvo(null);
  };

  const handleAbrirArquivo = (
    resultadoId: string,
    intent: "view" | "download",
    nomeArquivo: string,
  ) => {
    mintUrl.mutate(
      { resultadoId, intent },
      {
        onSuccess: (res) => {
          if (intent === "view") {
            window.open(res.url, "_blank", "noopener,noreferrer");
          } else {
            void downloadFile(res.url, nomeArquivo);
          }
        },
      },
    );
  };

  if (showSkeleton) {
    return (
      <div data-testid="certidoes-parte-skeleton">
        <TableSkeleton rows={4} columns={5} />
      </div>
    );
  }

  if (resultados.isError && data.length === 0) {
    return (
      <div className="space-y-3" data-testid="certidoes-parte-error">
        <p className="text-sm text-destructive">
          Não foi possível carregar as certidões desta parte.
        </p>
        <Button size="sm" variant="outline" onClick={() => resultados.refetch()}>
          Tentar novamente
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-3" data-testid="certidoes-parte-panel">
      {/* Hidden file input for manual certificate upload, mirrors
          pages/Certidoes.tsx's own pattern. */}
      <input
        type="file"
        accept=".pdf"
        className="hidden"
        data-testid={UPLOAD_INPUT_TESTID}
        onChange={handleUploadFile}
      />

      {resultados.isError && data.length > 0 && (
        <p className="text-xs text-destructive" data-testid="certidoes-parte-refresh-error">
          Falha ao atualizar — mostrando os últimos dados carregados.
        </p>
      )}

      {/* One editor per CNPJ consulta linked to this person (migration 116)
          — a fact about the company, shown above its own certidões rather
          than repeated on every resultado row. */}
      {consultasCnpj.map((consulta) => (
        <SituacaoCadastralEditor
          key={consulta.consulta_id}
          consultaId={consulta.consulta_id}
          situacaoCadastral={consulta.consulta_situacao_cadastral ?? null}
          dataSituacao={consulta.consulta_data_situacao ?? null}
          situacaoOrigem={consulta.consulta_situacao_origem ?? null}
          onSalvar={(patch) => situacaoCadastral.mutate({ consultaId: consulta.consulta_id, patch })}
          saving={situacaoCadastral.isPending}
        />
      ))}

      {data.length === 0 ? (
        <div className="space-y-3 py-6 text-center" data-testid="certidoes-parte-empty">
          <p className="text-sm text-muted-foreground">
            {nomeParte
              ? `Nenhuma certidão vinculada a ${nomeParte} ainda.`
              : "Nenhuma certidão vinculada a esta parte ainda."}
          </p>
          <div className="flex justify-center gap-2">
            <Button size="sm" onClick={() => setVincularAberto(true)}>
              <Link2 className="h-3.5 w-3.5 mr-2" />
              Vincular consulta
            </Button>
            <Button size="sm" variant="outline" onClick={handleAbrirRegistroManual}>
              <ClipboardEdit className="h-3.5 w-3.5 mr-2" />
              Registrar certidões manualmente
            </Button>
          </div>
        </div>
      ) : (
        <>
          {isRefreshing && (
            <p className="text-xs text-muted-foreground" data-testid="certidoes-parte-refreshing">
              Atualizando…
            </p>
          )}
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Certidão</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Resultado</TableHead>
                <TableHead>Nº / Datas</TableHead>
                <TableHead>Origem</TableHead>
                <TableHead className="w-32">Ações</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.map((resultado) => {
                const vencida = isValidadeVencida(resultado.validade_ate);
                const vencendo = !vencida && isValidadeVencendo(resultado.validade_ate);
                const isSugestao =
                  !!resultado.resultado_origem && resultado.resultado_origem !== "manual";

                return (
                  <TableRow
                    key={resultado.id}
                    data-testid={`certidoes-parte-row-${resultado.tipo}`}
                  >
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <FileText className="h-4 w-4 text-muted-foreground shrink-0" />
                        <span className="font-medium">{resultado.nome_display}</span>
                      </div>
                      {resultado.erro_mensagem && (
                        <p className="text-xs text-destructive mt-1">{resultado.erro_mensagem}</p>
                      )}
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">
                        {STATUS_LABELS[resultado.status] || resultado.status}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      {resultado.resultado ? (
                        <div className="flex flex-col gap-1">
                          <Badge
                            variant={RESULTADO_VALOR_VARIANT[resultado.resultado as ResultadoValor]}
                          >
                            {RESULTADO_VALOR_LABELS[resultado.resultado as ResultadoValor]}
                          </Badge>
                          {isSugestao && (
                            <span className="text-xs text-muted-foreground">
                              Sugestão — a confirmar
                            </span>
                          )}
                        </div>
                      ) : (
                        <span className="text-sm text-muted-foreground">Não determinado</span>
                      )}
                    </TableCell>
                    <TableCell className="text-sm">
                      {resultado.numero && <div>Nº {resultado.numero}</div>}
                      {resultado.emitida_em && (
                        <div
                          className={
                            isEmissaoAntiga(resultado.emitida_em)
                              ? "flex items-center gap-1 text-amber-600"
                              : ""
                          }
                        >
                          {isEmissaoAntiga(resultado.emitida_em) && (
                            <AlertTriangle className="h-3 w-3" />
                          )}
                          Emitida {formatDate(resultado.emitida_em)}
                          {/* "Every certidão must be emitted < 30 days before
                              signing" — a plain age flag, independent of
                              `validade_ate` (a certidão can still be valid
                              while already too old to sign with). */}
                          {isEmissaoAntiga(resultado.emitida_em) && " (emitida há 30+ dias)"}
                        </div>
                      )}
                      {resultado.validade_ate && (
                        <div
                          className={
                            vencida
                              ? "flex items-center gap-1 text-destructive"
                              : vencendo
                                ? "flex items-center gap-1 text-amber-600"
                                : ""
                          }
                        >
                          {(vencida || vencendo) && <AlertTriangle className="h-3 w-3" />}
                          Validade {formatDate(resultado.validade_ate)}
                          {vencida && " (vencida)"}
                          {vencendo && " (vencendo)"}
                        </div>
                      )}
                      {!resultado.numero && !resultado.emitida_em && !resultado.validade_ate && "—"}
                    </TableCell>
                    <TableCell>
                      {resultado.resultado_origem ? (
                        <Badge variant={resultado.resultado_origem === "manual" ? "default" : "secondary"}>
                          {RESULTADO_ORIGEM_LABELS[resultado.resultado_origem]}
                        </Badge>
                      ) : (
                        <span className="text-sm text-muted-foreground">—</span>
                      )}
                    </TableCell>
                    <TableCell>
                      <div className="flex gap-1">
                        {resultado.arquivo_url && (
                          <>
                            <Button
                              size="sm"
                              variant="ghost"
                              title="Visualizar"
                              aria-label={`Visualizar ${resultado.nome_display}`}
                              disabled={mintUrl.isPending}
                              onClick={() =>
                                handleAbrirArquivo(
                                  resultado.id,
                                  "view",
                                  resultado.arquivo_nome || "certidao.pdf",
                                )
                              }
                            >
                              <Eye className="h-3 w-3" />
                            </Button>
                            <Button
                              size="sm"
                              variant="ghost"
                              title="Baixar"
                              aria-label={`Baixar ${resultado.nome_display}`}
                              disabled={mintUrl.isPending}
                              onClick={() =>
                                handleAbrirArquivo(
                                  resultado.id,
                                  "download",
                                  resultado.arquivo_nome || "certidao.pdf",
                                )
                              }
                            >
                              <Download className="h-3 w-3" />
                            </Button>
                          </>
                        )}
                        {resultado.tem_transcricao === true && (
                          <>
                            <Button
                              size="sm"
                              variant="ghost"
                              title="Transcrição PDF"
                              aria-label={`Transcrição PDF ${resultado.nome_display}`}
                              disabled={
                                downloadTranscricaoPdf.isPending &&
                                downloadTranscricaoPdf.variables?.resultadoId === resultado.id
                              }
                              onClick={() =>
                                downloadTranscricaoPdf.mutate({
                                  resultadoId: resultado.id,
                                  filename: `${resultado.tipo}_transcricao.pdf`,
                                })
                              }
                            >
                              {downloadTranscricaoPdf.isPending &&
                              downloadTranscricaoPdf.variables?.resultadoId === resultado.id ? (
                                <Loader2 className="h-3 w-3 animate-spin" />
                              ) : (
                                <FileDown className="h-3 w-3" />
                              )}
                            </Button>
                            <Button
                              size="sm"
                              variant="ghost"
                              title="Copiar transcrição"
                              aria-label={`Copiar transcrição ${resultado.nome_display}`}
                              disabled={copiandoId === resultado.id}
                              onClick={() => handleCopiarTranscricao(resultado.id)}
                            >
                              {copiedId === resultado.id ? (
                                <Check className="h-3 w-3" />
                              ) : (
                                <Copy className="h-3 w-3" />
                              )}
                            </Button>
                          </>
                        )}
                        <Button
                          size="sm"
                          variant="ghost"
                          title="Enviar PDF"
                          aria-label={`Enviar PDF ${resultado.nome_display}`}
                          disabled={upload.isPending}
                          onClick={() => handleUploadClick(resultado.id)}
                        >
                          {upload.isPending && uploadAlvo === resultado.id ? (
                            <Loader2 className="h-3 w-3 animate-spin" />
                          ) : (
                            <Upload className="h-3 w-3" />
                          )}
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          title="Editar / confirmar"
                          aria-label={`Editar ${resultado.nome_display}`}
                          onClick={() => setEditando(resultado)}
                        >
                          <Pencil className="h-3 w-3" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </>
      )}

      {/* Vincular consulta dialog */}
      <Dialog open={vincularAberto} onOpenChange={setVincularAberto}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Vincular consulta de certidões</DialogTitle>
            <DialogDescription>
              Escolha uma consulta já criada para vincular a esta parte.
            </DialogDescription>
          </DialogHeader>
          {consultasDisponiveis.length === 0 ? (
            <p className="text-sm text-muted-foreground" data-testid="certidoes-parte-sem-consultas">
              Nenhuma consulta disponível para vincular. Crie uma consulta na página de Certidões
              primeiro.
            </p>
          ) : (
            <Select value={consultaEscolhida} onValueChange={setConsultaEscolhida}>
              <SelectTrigger>
                <SelectValue placeholder="Selecione uma consulta" />
              </SelectTrigger>
              <SelectContent>
                {consultasDisponiveis.map((c) => (
                  <SelectItem key={c.id} value={c.id}>
                    {c.nome} — {c.documento}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setVincularAberto(false)}>
              Cancelar
            </Button>
            <Button onClick={handleVincular} disabled={!consultaEscolhida || vincular.isPending}>
              {vincular.isPending && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              Vincular
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Registrar certidões manualmente — no InfoSimples call, no token
          needed. Creates + links a consulta in one step; see
          `useCriarConsultaManual`. Card-only by owner decision (2026-09-22):
          this is for certidões the office ALREADY holds on paper — old
          processes, cards that will never go through InfoSimples — never a
          way to request anything. */}
      <Dialog open={manualAberto} onOpenChange={setManualAberto}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Registrar certidões manualmente</DialogTitle>
            <DialogDescription>
              Para certidões que a imobiliária JÁ TEM em papel (processos antigos, cartório
              físico) — isto não consulta nem solicita nada ao InfoSimples. Cada certidão fica
              pronta para edição em "Editar / confirmar".
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label htmlFor="certidoes-parte-manual-nome">Nome completo / Razão social</Label>
              <Input
                id="certidoes-parte-manual-nome"
                value={manualNome}
                onChange={(e) => setManualNome(e.target.value)}
              />
            </div>
            {/* A company only ever registers a CNPJ — the type selector is
                meaningless here (and `POST /consultas/manual` never sees a
                `tipo_documento` choice in this mode; `handleRegistrarManual`
                always sends `'cnpj'`), so it is hidden rather than shown
                disabled with an answer already picked for the operator. */}
            {empresaId ? (
              <div>
                <Label htmlFor="certidoes-parte-manual-documento">CNPJ</Label>
                <Input
                  id="certidoes-parte-manual-documento"
                  value={manualDocumento}
                  onChange={(e) => setManualDocumento(e.target.value)}
                  placeholder="Apenas números"
                />
              </div>
            ) : (
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label>Tipo de documento</Label>
                  <Select
                    value={manualTipoDocumento}
                    onValueChange={(v) => setManualTipoDocumento(v as "cpf" | "cnpj")}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="cpf">CPF - Pessoa Física</SelectItem>
                      <SelectItem value="cnpj">CNPJ - Pessoa Jurídica</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label htmlFor="certidoes-parte-manual-documento">Documento</Label>
                  <Input
                    id="certidoes-parte-manual-documento"
                    value={manualDocumento}
                    onChange={(e) => setManualDocumento(e.target.value)}
                    placeholder="Apenas números"
                  />
                </div>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setManualAberto(false)}>
              Cancelar
            </Button>
            <Button
              onClick={handleRegistrarManual}
              disabled={!manualNome.trim() || !manualDocumento.trim() || criarManual.isPending}
            >
              {criarManual.isPending && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              Registrar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit + confirm dialog */}
      <Dialog open={!!editando} onOpenChange={(open) => !open && setEditando(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editando?.nome_display}</DialogTitle>
            <DialogDescription>
              Revise os campos abaixo e confirme — mesmo sem alterações, confirmar marca este
              resultado como revisado por você.
            </DialogDescription>
          </DialogHeader>
          {editando && (
            <ResultadoEditForm
              resultado={editando}
              saving={confirmar.isPending}
              onCancel={() => setEditando(null)}
              onConfirm={(patch) =>
                confirmar.mutate(
                  { resultadoId: editando.id, patch },
                  { onSuccess: () => setEditando(null) },
                )
              }
            />
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

/** `YYYY-MM-DD` for the browser's local date — the office fills a dozen
 * rows per person in one sitting; prefilling "Emitida em" with today means
 * confirming a row that already has the right date takes zero clicks
 * instead of re-picking the same date twelve times. Still fully editable —
 * only the INITIAL value changes, never a forced value. */
function hojeIso(): string {
  const d = new Date();
  const mes = String(d.getMonth() + 1).padStart(2, "0");
  const dia = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${mes}-${dia}`;
}

function ResultadoEditForm({
  resultado,
  saving,
  onCancel,
  onConfirm,
}: {
  resultado: CertidaoResultado;
  saving: boolean;
  onCancel: () => void;
  onConfirm: (patch: ResultadoPatchInput) => void;
}) {
  const [numero, setNumero] = useState(resultado.numero ?? "");
  // A never-yet-set resultado defaults to TODAY rather than blank — see
  // `hojeIso`'s own docstring. One that already carries a date (an
  // automated hit, or a previous manual save) keeps its own value.
  const [emitidaEm, setEmitidaEm] = useState(resultado.emitida_em ?? hojeIso());
  const [validadeAte, setValidadeAte] = useState(resultado.validade_ate ?? "");
  const [valor, setValor] = useState<ResultadoValor | "">(
    (resultado.resultado as ResultadoValor) || "",
  );

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    // Only the fields that actually changed ride the request — an untouched
    // form submits `{}`, which is still a valid confirmation per the
    // endpoint's own contract (see `useConfirmarResultado`'s docstring).
    const patch: ResultadoPatchInput = {};
    if (numero !== (resultado.numero ?? "")) patch.numero = numero || undefined;
    if (emitidaEm !== (resultado.emitida_em ?? "")) patch.emitida_em = emitidaEm || undefined;
    if (validadeAte !== (resultado.validade_ate ?? "")) {
      patch.validade_ate = validadeAte || undefined;
    }
    if (valor !== ((resultado.resultado as ResultadoValor) || "")) {
      patch.resultado = (valor || undefined) as ResultadoValor | undefined;
    }
    onConfirm(patch);
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4" data-testid="certidoes-parte-edit-form">
      <div className="grid grid-cols-2 gap-4">
        <div>
          <Label htmlFor="certidoes-parte-numero">Número</Label>
          <Input
            id="certidoes-parte-numero"
            value={numero}
            onChange={(e) => setNumero(e.target.value)}
          />
        </div>
        <div>
          <Label>Resultado</Label>
          <Select value={valor} onValueChange={(v) => setValor(v as ResultadoValor)}>
            <SelectTrigger>
              <SelectValue placeholder="Selecione" />
            </SelectTrigger>
            <SelectContent>
              {Object.entries(RESULTADO_VALOR_LABELS).map(([value, label]) => (
                <SelectItem key={value} value={value}>
                  {label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <Label htmlFor="certidoes-parte-emitida-em">Emitida em</Label>
          <Input
            id="certidoes-parte-emitida-em"
            type="date"
            value={emitidaEm}
            onChange={(e) => setEmitidaEm(e.target.value)}
          />
          {/* Serasa/CENPROT carry no printed emission date of their own —
              the office's rule is to use the date the consulta was made. */}
          {(resultado.tipo === "serasa" || resultado.tipo === "cenprot") && (
            <p className="mt-1 text-xs text-muted-foreground">
              Para Serasa/CENPROT, use a data da consulta.
            </p>
          )}
        </div>
        <div>
          <Label htmlFor="certidoes-parte-validade-ate">Validade até</Label>
          <Input
            id="certidoes-parte-validade-ate"
            type="date"
            value={validadeAte}
            onChange={(e) => setValidadeAte(e.target.value)}
          />
        </div>
      </div>
      <DialogFooter>
        <Button type="button" variant="outline" onClick={onCancel}>
          Cancelar
        </Button>
        <Button type="submit" disabled={saving}>
          {saving && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
          Confirmar
        </Button>
      </DialogFooter>
    </form>
  );
}

/**
 * One CNPJ consulta's manual registration-status entry (migration 116) —
 * `PATCH /consultas/{id}/situacao-cadastral`. A fact about the company being
 * investigated, not any one certidão, so this renders once per consulta
 * (`CertidoesPartePanel` de-dupes by `consulta_id` before mounting it) with
 * its own derived pt-BR verdict badge alongside the editable fields.
 *
 * Local `situacao`/`data` state mirrors `ResultadoEditForm`'s pattern: only
 * the fields that actually changed ride the PATCH, and the backend refuses
 * an entirely-unchanged (empty) body with a 422 rather than treating it as
 * a confirmation — unlike `ResultadoPatch`, there is no automated writer for
 * this field to lock out today, so an empty PATCH has nothing to confirm.
 */
function SituacaoCadastralEditor({
  consultaId,
  situacaoCadastral,
  dataSituacao,
  situacaoOrigem,
  onSalvar,
  saving,
}: {
  consultaId: string;
  situacaoCadastral: SituacaoCadastral | null;
  dataSituacao: string | null;
  situacaoOrigem: "api" | "ia" | "manual" | null;
  onSalvar: (patch: SituacaoCadastralPatchInput) => void;
  saving: boolean;
}) {
  const [situacao, setSituacao] = useState<SituacaoCadastral | "">(situacaoCadastral ?? "");
  const [data, setData] = useState(dataSituacao ?? "");
  const [erro, setErro] = useState<string | null>(null);

  const badge = situacaoCadastralBadge(situacaoCadastral, dataSituacao);

  const handleSalvar = () => {
    // "baixada" without a date leaves the 5-year window uncomputable — the
    // office's own rule cannot be applied blind, so this is refused
    // client-side rather than saved as an unusable half-answer.
    if (situacao === "baixada" && !data) {
      setErro("Informe a data da baixa para uma empresa baixada.");
      return;
    }
    const patch: SituacaoCadastralPatchInput = {};
    if (situacao !== (situacaoCadastral ?? "")) {
      patch.situacao_cadastral = (situacao || undefined) as SituacaoCadastral | undefined;
    }
    if (data !== (dataSituacao ?? "")) patch.data_situacao = data || undefined;
    if (Object.keys(patch).length === 0) return;
    setErro(null);
    onSalvar(patch);
  };

  return (
    <div
      className="space-y-2 rounded-md border p-3"
      data-testid={`situacao-cadastral-${consultaId}`}
    >
      <div className="flex items-center justify-between gap-2">
        <Label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Situação cadastral
        </Label>
        <Badge
          variant={SITUACAO_CADASTRAL_BADGE_VARIANT[badge.kind]}
          data-testid={`situacao-cadastral-badge-${consultaId}`}
        >
          {badge.label}
        </Badge>
      </div>
      <div className="flex flex-wrap items-end gap-2">
        <div className="min-w-[10rem]">
          <Select
            value={situacao}
            onValueChange={(v) => setSituacao(v as SituacaoCadastral)}
          >
            <SelectTrigger aria-label="Situação cadastral">
              <SelectValue placeholder="Selecione" />
            </SelectTrigger>
            <SelectContent>
              {Object.entries(SITUACAO_CADASTRAL_LABELS).map(([value, label]) => (
                <SelectItem key={value} value={value}>
                  {label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label htmlFor={`situacao-cadastral-data-${consultaId}`} className="sr-only">
            Data da situação
          </Label>
          <Input
            id={`situacao-cadastral-data-${consultaId}`}
            type="date"
            value={data}
            onChange={(e) => setData(e.target.value)}
            // "≥5 years ago" needs the date only when the office's rule
            // actually reads it — for every other status it is inert.
            required={situacao === "baixada"}
          />
        </div>
        <Button size="sm" variant="outline" onClick={handleSalvar} disabled={saving}>
          {saving && <Loader2 className="h-3.5 w-3.5 mr-2 animate-spin" />}
          Salvar
        </Button>
      </div>
      {erro && (
        <p className="text-xs text-destructive" data-testid={`situacao-cadastral-erro-${consultaId}`}>
          {erro}
        </p>
      )}
      {situacaoOrigem && (
        <p className="text-xs text-muted-foreground">
          Origem: {RESULTADO_ORIGEM_LABELS[situacaoOrigem]}
        </p>
      )}
    </div>
  );
}

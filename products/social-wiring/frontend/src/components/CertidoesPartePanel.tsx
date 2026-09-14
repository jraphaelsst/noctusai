/**
 * `<CertidoesPartePanel/>` — one party's structured certidões, contract
 * automation F1.
 *
 * Self-contained: the only thing a caller supplies is `atendimentoParteId`
 * (`atendimento_partes.id`) — every fetch and mutation on this panel keys off
 * it. Intended mount point is `ClienteCardDialog`'s per-parte section
 * (tech-lead wires the tab at integration, per this slice's brief); the panel
 * itself does not know or care what dialog it lives in, the same way
 * `PessoaDocumentosPanel` does not.
 *
 * Four states, honestly (`KB § PATTERNS/frontend/lying-loading-state.md`):
 * `showSkeleton = isPending && !data`, `isRefreshing = isFetching && !!data`
 * (an indicator only — the table stays mounted through a background poll),
 * an error banner that keeps showing stale data when there is any, and an
 * empty state offering the one action that gets a party its first resultado:
 * linking an already-created consulta.
 *
 * IA/api-derived values are rendered as suggestions (a muted "Sugestão — a
 * confirmar" caption) until a human opens the edit dialog and submits —
 * even an unedited submit is a valid confirmation, per
 * `PATCH /resultados/{id}`'s own contract.
 */
import { useState } from "react";
import {
  AlertTriangle,
  Download,
  Eye,
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
  useCertidaoConsultas,
  useConfirmarResultado,
  useMintResultadoUrl,
  useResultadosPorParte,
  useUploadResultadoManual,
  useVincularParte,
} from "@/hooks/useCertidoes";
import type { CertidaoResultado } from "@/hooks/useCertidoes";
import { downloadFile } from "@/lib/file-download";
import { formatDate } from "@/lib/utils";
import {
  RESULTADO_ORIGEM_LABELS,
  RESULTADO_VALOR_LABELS,
  RESULTADO_VALOR_VARIANT,
  isValidadeVencendo,
  isValidadeVencida,
  type ResultadoPatchInput,
  type ResultadoValor,
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
  /** `atendimento_partes.id` — the only required input. */
  atendimentoParteId: string;
  /** Optional label for the empty-state copy; the panel works without it —
   * a linked consulta's own `nome`/`documento` cover the rest once one exists. */
  nomeParte?: string;
}

export function CertidoesPartePanel({ atendimentoParteId, nomeParte }: CertidoesPartePanelProps) {
  const resultados = useResultadosPorParte(atendimentoParteId);
  const consultas = useCertidaoConsultas();
  const vincular = useVincularParte();
  const confirmar = useConfirmarResultado(atendimentoParteId);
  const upload = useUploadResultadoManual(atendimentoParteId);
  const mintUrl = useMintResultadoUrl();

  const [vincularAberto, setVincularAberto] = useState(false);
  const [consultaEscolhida, setConsultaEscolhida] = useState("");
  const [editando, setEditando] = useState<CertidaoResultado | null>(null);
  const [uploadAlvo, setUploadAlvo] = useState<string | null>(null);

  // Two signals off `data`, never `isLoading` — the query's key includes
  // `atendimentoParteId` and carries `placeholderData`, so switching parties
  // does not blank the table either.
  const showSkeleton = resultados.isPending && !resultados.data;
  const isRefreshing = resultados.isFetching && !!resultados.data;
  const data = resultados.data ?? [];

  const consultasDisponiveis = (consultas.data ?? []).filter((c) => !c.atendimento_parte_id);

  const handleVincular = () => {
    if (!consultaEscolhida) return;
    vincular.mutate(
      { consultaId: consultaEscolhida, atendimentoParteId },
      {
        onSuccess: () => {
          setVincularAberto(false);
          setConsultaEscolhida("");
        },
      },
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

      {data.length === 0 ? (
        <div className="space-y-3 py-6 text-center" data-testid="certidoes-parte-empty">
          <p className="text-sm text-muted-foreground">
            {nomeParte
              ? `Nenhuma certidão vinculada a ${nomeParte} ainda.`
              : "Nenhuma certidão vinculada a esta parte ainda."}
          </p>
          <Button size="sm" onClick={() => setVincularAberto(true)}>
            <Link2 className="h-3.5 w-3.5 mr-2" />
            Vincular consulta
          </Button>
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
                      {resultado.emitida_em && <div>Emitida {formatDate(resultado.emitida_em)}</div>}
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
  const [emitidaEm, setEmitidaEm] = useState(resultado.emitida_em ?? "");
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

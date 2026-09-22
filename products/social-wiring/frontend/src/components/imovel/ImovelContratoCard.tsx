/**
 * `<ImovelContratoCard/>` — the three answers a contract needs from this
 * imóvel's matrícula (migration 115): the título aquisitivo phrase, the ônus
 * creditor, and who sold it last.
 *
 * 🔴 SUGGESTION AND CONFIRMATION ARE SHOWN SIDE BY SIDE, NEVER COLLAPSED
 * ----------------------------------------------------------------------
 * The server recomputes `sugestao` on every read from the acts the operator
 * chose; `confirmado` is the wording a person signed off on, and the contract
 * uses THAT. They are allowed to differ — a notary's phrasing often does — so
 * this card renders both and never silently falls back from one to the other.
 *
 * 🔴 A MISSING SUGGESTION IS EXPLAINED, NOT LEFT BLANK
 * -----------------------------------------------------
 * Each `motivo_sem_sugestao` has a different fix — no título act confirmed,
 * no details read, no instrumento in the act — and they live at different
 * screens. A blank field would send the operator looking for a bug; the
 * sentence plus a link to the matrícula sends them to the fix.
 *
 * PRESENTATIONAL: props in, callbacks out. `ImovelContratoContainer` fetches.
 */
import { useEffect, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  FileSignature,
  Link2,
  Loader2,
  Sparkles,
  Users,
} from "lucide-react";
import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";

import {
  ANOS_CERTIDOES_ANTIGOS_PROPRIETARIOS,
  NATUREZA_ULTIMA_TRANSFERENCIA_LABEL,
  motivoSemSugestaoTexto,
  type AntigosProprietariosResponse,
  type EnderecoRegistroResponse,
  type NaturezaUltimaTransferencia,
  type OnusCredorResponse,
  type TituloAquisitivoResponse,
} from "@/hooks/useImovelContrato";

export interface ImovelContratoCardProps {
  codigo: string;

  titulo: TituloAquisitivoResponse | undefined;
  tituloShowSkeleton: boolean;
  tituloIsRefreshing: boolean;
  tituloIsError: boolean;
  savingTitulo: boolean;
  onConfirmarTitulo: (texto: string | null) => void;

  enderecoRegistro: EnderecoRegistroResponse | undefined;
  enderecoRegistroShowSkeleton: boolean;
  enderecoRegistroIsRefreshing: boolean;
  enderecoRegistroIsError: boolean;
  savingEnderecoRegistro: boolean;
  onConfirmarEnderecoRegistro: (texto: string | null) => void;

  onus: OnusCredorResponse | undefined;
  onusShowSkeleton: boolean;
  onusIsRefreshing: boolean;
  onusIsError: boolean;
  savingOnus: boolean;
  onConfirmarOnusCredor: (credor: string | null) => void;

  antigos: AntigosProprietariosResponse | undefined;
  antigosShowSkeleton: boolean;
  antigosIsError: boolean;
  savingUltimaTransferenciaManual: boolean;
  onConfirmarUltimaTransferenciaManual: (input: {
    data: string | null;
    natureza: NaturezaUltimaTransferencia | null;
    semRegistro: boolean;
  }) => void;
}

/** Where to go to fix a missing suggestion: the act's own extraction when we
 *  know it, else the matrículas list for this imóvel. */
function linkDaMatricula(codigo: string, extracaoId: string | null | undefined): string {
  return extracaoId
    ? `/matriculas?extracao=${encodeURIComponent(extracaoId)}`
    : `/matriculas?codigo=${encodeURIComponent(codigo)}`;
}

function formatarData(iso: string | null | undefined): string {
  if (!iso) return "—";
  const ms = Date.parse(`${iso.slice(0, 10)}T00:00:00Z`);
  if (Number.isNaN(ms)) return iso;
  return new Date(ms).toLocaleDateString("pt-BR", { timeZone: "UTC" });
}

function SemSugestao({
  motivo,
  href,
  testId,
}: {
  motivo: string | null;
  href: string;
  testId: string;
}) {
  const explicacao = motivoSemSugestaoTexto(motivo);
  if (!explicacao) return null;
  return (
    <div
      className="space-y-1 rounded border border-amber-300 bg-amber-50 p-2"
      data-testid={testId}
      data-motivo={motivo ?? ""}
    >
      <p className="flex items-start gap-1.5 text-xs text-amber-800">
        <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
        {explicacao}
      </p>
      <Link to={href} className="inline-flex items-center gap-1 text-xs font-medium underline">
        <Link2 className="h-3 w-3" />
        Abrir a matrícula
      </Link>
    </div>
  );
}

function Confirmacao({
  nome,
  em,
  testId,
}: {
  nome: string | null | undefined;
  em: string | null | undefined;
  testId: string;
}) {
  return (
    <p className="flex items-center gap-1.5 text-[11px] text-muted-foreground" data-testid={testId}>
      <CheckCircle2 className="h-3 w-3" />
      Confirmado por {nome ?? "—"}
      {em ? ` em ${new Date(em).toLocaleString("pt-BR")}` : ""}
    </p>
  );
}

export default function ImovelContratoCard({
  codigo,
  titulo,
  tituloShowSkeleton,
  tituloIsRefreshing,
  tituloIsError,
  savingTitulo,
  onConfirmarTitulo,
  enderecoRegistro,
  enderecoRegistroShowSkeleton,
  enderecoRegistroIsRefreshing,
  enderecoRegistroIsError,
  savingEnderecoRegistro,
  onConfirmarEnderecoRegistro,
  onus,
  onusShowSkeleton,
  onusIsRefreshing,
  onusIsError,
  savingOnus,
  onConfirmarOnusCredor,
  antigos,
  antigosShowSkeleton,
  antigosIsError,
  savingUltimaTransferenciaManual,
  onConfirmarUltimaTransferenciaManual,
}: ImovelContratoCardProps) {
  // Drafts seeded from the CONFIRMED wording (not the suggestion): the
  // suggestion is one click away via "Usar sugestão", and pre-filling with it
  // would make an unreviewed reading look like a decision already taken.
  const [tituloDraft, setTituloDraft] = useState("");
  const [enderecoRegistroDraft, setEnderecoRegistroDraft] = useState("");
  const [credorDraft, setCredorDraft] = useState("");
  // Seeded from the RAW manual-override state (`antigos.manual`), never from
  // the resolved `ultima_transferencia` — a derived-from-acts value is not
  // something this form ever overwrote, and pre-filling with it would make
  // an untouched override look like one the operator just typed.
  const [ultimaTransferenciaDataDraft, setUltimaTransferenciaDataDraft] = useState("");
  const [ultimaTransferenciaNaturezaDraft, setUltimaTransferenciaNaturezaDraft] = useState<
    NaturezaUltimaTransferencia | ""
  >("");
  const [semRegistroDraft, setSemRegistroDraft] = useState(false);

  const tituloConfirmado = titulo?.confirmado?.texto ?? "";
  useEffect(() => {
    setTituloDraft(tituloConfirmado);
  }, [tituloConfirmado]);

  const enderecoRegistroConfirmado = enderecoRegistro?.confirmado?.texto ?? "";
  useEffect(() => {
    setEnderecoRegistroDraft(enderecoRegistroConfirmado);
  }, [enderecoRegistroConfirmado]);

  const credorConfirmado = onus?.confirmado?.credor ?? "";
  useEffect(() => {
    setCredorDraft(credorConfirmado);
  }, [credorConfirmado]);

  const manual = antigos?.manual ?? null;
  useEffect(() => {
    setUltimaTransferenciaDataDraft(manual?.data_registro ?? "");
    setUltimaTransferenciaNaturezaDraft(
      (manual?.natureza as NaturezaUltimaTransferencia) ?? "",
    );
    setSemRegistroDraft(manual?.sem_registro ?? false);
  }, [manual?.data_registro, manual?.natureza, manual?.sem_registro]);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <FileSignature className="h-4 w-4" />
          Para o contrato
          {(tituloIsRefreshing || enderecoRegistroIsRefreshing || onusIsRefreshing) && (
            // Indicator only — never an early return: the content below is
            // still good to read while it refreshes.
            // KB § PATTERNS/frontend/lying-loading-state.md
            <Loader2
              className="h-3.5 w-3.5 animate-spin text-muted-foreground"
              data-testid="imovel-contrato-refreshing"
            />
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        {/* ─── Título aquisitivo ────────────────────────────────────────── */}
        <section className="space-y-2" data-testid="imovel-titulo-aquisitivo">
          <Label className="text-sm font-semibold">Título aquisitivo</Label>

          {tituloShowSkeleton ? (
            // Testid on a wrapper, not on `Skeleton` — it is a re-exported
            // design-system organ; this file must not assume it forwards
            // arbitrary DOM props.
            <div data-testid="imovel-titulo-skeleton">
              <Skeleton className="h-16 w-full" />
            </div>
          ) : tituloIsError ? (
            <p className="text-xs text-destructive" data-testid="imovel-titulo-erro">
              Não foi possível carregar o título aquisitivo.
            </p>
          ) : (
            <>
              {titulo?.sugestao ? (
                <div className="space-y-1 rounded bg-muted/40 p-2" data-testid="imovel-titulo-sugestao">
                  <p className="flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground">
                    <Sparkles className="h-3 w-3 text-amber-500" />
                    Sugestão a partir do ato {titulo.ato?.ato_ref ?? "—"}
                  </p>
                  <p className="whitespace-pre-wrap text-xs">{titulo.sugestao}</p>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    className="h-7 text-xs"
                    disabled={savingTitulo}
                    onClick={() => setTituloDraft(titulo.sugestao as string)}
                    data-testid="imovel-titulo-usar-sugestao"
                  >
                    Usar esta frase
                  </Button>
                </div>
              ) : (
                <SemSugestao
                  motivo={titulo?.motivo_sem_sugestao ?? null}
                  href={linkDaMatricula(codigo, titulo?.ato?.extracao_id)}
                  testId="imovel-titulo-sem-sugestao"
                />
              )}

              <Textarea
                rows={3}
                value={tituloDraft}
                placeholder="Frase que irá para o contrato"
                disabled={savingTitulo}
                onChange={(e) => setTituloDraft(e.target.value)}
                data-testid="imovel-titulo-texto"
              />
              {titulo?.confirmado && (
                <Confirmacao
                  nome={titulo.confirmado.confirmado_por?.nome}
                  em={titulo.confirmado.confirmado_em}
                  testId="imovel-titulo-confirmado"
                />
              )}
              <div className="flex items-center gap-2">
                <Button
                  type="button"
                  size="sm"
                  disabled={savingTitulo}
                  onClick={() => onConfirmarTitulo(tituloDraft.trim() === "" ? null : tituloDraft.trim())}
                  data-testid="imovel-titulo-confirmar"
                >
                  {savingTitulo && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
                  Confirmar
                </Button>
                {titulo?.confirmado && (
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    disabled={savingTitulo}
                    onClick={() => onConfirmarTitulo(null)}
                    data-testid="imovel-titulo-limpar"
                  >
                    Limpar
                  </Button>
                )}
              </div>
            </>
          )}
        </section>

        {/* ─── Endereço do registro (migration 139/147) ──────────────────
            🔴 NO suggestion here, unlike título/ônus above — this value is
            NEVER a recomputed guess (see `imovel_dados.endereco_registro_
            texto`'s column comment). Only a confirm/clear textarea. */}
        <section className="space-y-2 border-t pt-4" data-testid="imovel-endereco-registro">
          <Label className="text-sm font-semibold">Endereço do registro</Label>
          <p className="text-xs text-muted-foreground">
            O endereço confirmado a partir da matrícula — nunca o endereço público
            do CRM, que pode ser o da portaria em vez do imóvel.
          </p>

          {enderecoRegistroShowSkeleton ? (
            <div data-testid="imovel-endereco-registro-skeleton">
              <Skeleton className="h-12 w-full" />
            </div>
          ) : enderecoRegistroIsError ? (
            <p className="text-xs text-destructive" data-testid="imovel-endereco-registro-erro">
              Não foi possível carregar o endereço do registro.
            </p>
          ) : (
            <>
              <Textarea
                rows={2}
                value={enderecoRegistroDraft}
                placeholder="Ex.: Rua Fictícia, nº 100"
                disabled={savingEnderecoRegistro}
                onChange={(e) => setEnderecoRegistroDraft(e.target.value)}
                data-testid="imovel-endereco-registro-texto"
              />
              {enderecoRegistro?.confirmado && (
                <Confirmacao
                  nome={enderecoRegistro.confirmado.confirmado_por?.nome}
                  em={enderecoRegistro.confirmado.confirmado_em}
                  testId="imovel-endereco-registro-confirmado"
                />
              )}
              <div className="flex items-center gap-2">
                <Button
                  type="button"
                  size="sm"
                  disabled={savingEnderecoRegistro}
                  onClick={() =>
                    onConfirmarEnderecoRegistro(
                      enderecoRegistroDraft.trim() === "" ? null : enderecoRegistroDraft.trim(),
                    )
                  }
                  data-testid="imovel-endereco-registro-confirmar"
                >
                  {savingEnderecoRegistro && (
                    <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                  )}
                  Confirmar
                </Button>
                {enderecoRegistro?.confirmado && (
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    disabled={savingEnderecoRegistro}
                    onClick={() => onConfirmarEnderecoRegistro(null)}
                    data-testid="imovel-endereco-registro-limpar"
                  >
                    Limpar
                  </Button>
                )}
              </div>
            </>
          )}
        </section>

        {/* ─── Ônus: credor ─────────────────────────────────────────────── */}
        <section className="space-y-2 border-t pt-4" data-testid="imovel-onus-credor">
          <Label className="text-sm font-semibold">Credor do ônus</Label>

          {onusShowSkeleton ? (
            <div data-testid="imovel-onus-credor-skeleton">
              <Skeleton className="h-12 w-full" />
            </div>
          ) : onusIsError ? (
            <p className="text-xs text-destructive" data-testid="imovel-onus-credor-erro">
              Não foi possível carregar o credor do ônus.
            </p>
          ) : (
            <>
              {onus?.sugestao ? (
                <div className="space-y-1 rounded bg-muted/40 p-2" data-testid="imovel-onus-credor-sugestao">
                  <p className="flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground">
                    <Sparkles className="h-3 w-3 text-amber-500" />
                    Lido dos atos de ônus confirmados
                  </p>
                  <p className="text-xs">{onus.sugestao}</p>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    className="h-7 text-xs"
                    disabled={savingOnus}
                    onClick={() => setCredorDraft(onus.sugestao as string)}
                    data-testid="imovel-onus-credor-usar-sugestao"
                  >
                    Usar este credor
                  </Button>
                </div>
              ) : (
                <SemSugestao
                  motivo={onus?.motivo_sem_sugestao ?? null}
                  href={linkDaMatricula(codigo, onus?.extracao_id)}
                  testId="imovel-onus-credor-sem-sugestao"
                />
              )}

              {/* Per-act readings, so a wrong creditor is traceable to the act
                  it came from rather than being an anonymous string. */}
              {(onus?.atos.length ?? 0) > 0 && (
                <ul className="space-y-0.5" data-testid="imovel-onus-credor-atos">
                  {onus?.atos.map((a) => (
                    <li key={a.ato_id} className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
                      <Badge variant="outline" className="text-[10px]">
                        {a.ato_ref ?? a.kind}
                      </Badge>
                      {a.credor ?? "credor não encontrado"}
                      {a.credor_confianca !== "alta" && (
                        <Badge
                          variant="outline"
                          className="border-amber-500 bg-amber-50 text-[10px] text-amber-700"
                          data-testid={`imovel-onus-credor-confianca-${a.ato_id}`}
                        >
                          confira
                        </Badge>
                      )}
                    </li>
                  ))}
                </ul>
              )}

              <Input
                value={credorDraft}
                placeholder="Credor que irá para o contrato"
                disabled={savingOnus}
                onChange={(e) => setCredorDraft(e.target.value)}
                data-testid="imovel-onus-credor-input"
              />
              {onus?.confirmado && (
                <Confirmacao
                  nome={onus.confirmado.confirmado_por?.nome}
                  em={onus.confirmado.confirmado_em}
                  testId="imovel-onus-credor-confirmado"
                />
              )}
              <div className="flex items-center gap-2">
                <Button
                  type="button"
                  size="sm"
                  disabled={savingOnus}
                  onClick={() =>
                    onConfirmarOnusCredor(credorDraft.trim() === "" ? null : credorDraft.trim())
                  }
                  data-testid="imovel-onus-credor-confirmar"
                >
                  {savingOnus && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
                  Confirmar
                </Button>
                {onus?.confirmado && (
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    disabled={savingOnus}
                    onClick={() => onConfirmarOnusCredor(null)}
                    data-testid="imovel-onus-credor-limpar"
                  >
                    Limpar
                  </Button>
                )}
              </div>
            </>
          )}
        </section>

        {/* ─── Antigos proprietários ────────────────────────────────────── */}
        <section className="space-y-2 border-t pt-4" data-testid="imovel-antigos-proprietarios">
          <Label className="flex items-center gap-1.5 text-sm font-semibold">
            <Users className="h-3.5 w-3.5" />
            Antigos proprietários
          </Label>

          {antigosShowSkeleton ? (
            <div data-testid="imovel-antigos-skeleton">
              <Skeleton className="h-12 w-full" />
            </div>
          ) : antigosIsError ? (
            <p className="text-xs text-destructive" data-testid="imovel-antigos-erro">
              Não foi possível carregar os antigos proprietários.
            </p>
          ) : (
            <>
              {antigos?.ultima_transferencia ? (
                <>
                  <p className="text-xs text-muted-foreground">
                    Última transferência:{" "}
                    {antigos.ultima_transferencia.ato_ref ? (
                      <>
                        ato <strong>{antigos.ultima_transferencia.ato_ref}</strong>
                      </>
                    ) : (
                      <strong>informada manualmente</strong>
                    )}
                    {antigos.ultima_transferencia.natureza && (
                      <>
                        {" "}
                        (
                        {NATUREZA_ULTIMA_TRANSFERENCIA_LABEL[
                          antigos.ultima_transferencia.natureza as NaturezaUltimaTransferencia
                        ] ?? antigos.ultima_transferencia.natureza}
                        )
                      </>
                    )}
                    {antigos.ultima_transferencia.data_registro
                      ? ` registrada em ${formatarData(antigos.ultima_transferencia.data_registro)}`
                      : " — data não lida"}
                  </p>

                  {antigos.transmitentes.length > 0 ? (
                    <ul className="space-y-0.5" data-testid="imovel-antigos-transmitentes">
                      {antigos.transmitentes.map((p, i) => (
                        <li key={`${p.nome}-${i}`} className="text-xs">
                          {p.nome}
                          {p.cpf_cnpj ? ` · ${p.cpf_cnpj}` : ""}
                        </li>
                      ))}
                    </ul>
                  ) : antigos.ultima_transferencia.ato_ref ? (
                    <p className="text-xs text-muted-foreground">
                      O ato não informa os vendedores — confira os detalhes do ato.
                    </p>
                  ) : null}

                  {antigos.data_desconhecida && (
                    // An unreadable date must lead to ASKING, never to silently
                    // waiving the certidões — so it is its own notice.
                    <div
                      className="space-y-1 rounded border border-amber-300 bg-amber-50 p-2"
                      data-testid="imovel-antigos-data-desconhecida"
                    >
                      <p className="flex items-start gap-1.5 text-xs text-amber-800">
                        <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                        A data do registro não foi lida. Confirme a data do ato{" "}
                        {antigos.ultima_transferencia.ato_ref ?? ""} nos detalhes do ato — sem ela,
                        as certidões são exigidas por precaução.
                      </p>
                      <Link
                        to={linkDaMatricula(codigo, antigos.extracao_id)}
                        className="inline-flex items-center gap-1 text-xs font-medium underline"
                      >
                        <Link2 className="h-3 w-3" />
                        Abrir a matrícula
                      </Link>
                    </div>
                  )}

                  {antigos.exige_certidoes && (
                    <p
                      className="flex items-start gap-1.5 rounded border border-destructive/40 bg-destructive/5 p-2 text-xs text-destructive"
                      data-testid="imovel-antigos-exige-certidoes"
                    >
                      <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                      Certidões dos antigos proprietários são obrigatórias: a transferência foi
                      registrada há menos de {ANOS_CERTIDOES_ANTIGOS_PROPRIETARIOS} anos.
                    </p>
                  )}
                </>
              ) : antigos?.sem_registro ? (
                <p
                  className="flex items-center gap-1.5 text-xs text-muted-foreground"
                  data-testid="imovel-antigos-sem-registro"
                >
                  <CheckCircle2 className="h-3.5 w-3.5" />
                  Confirmado: não consta transferência de propriedade registrada na matrícula.
                </p>
              ) : (
                <p className="text-xs text-muted-foreground" data-testid="imovel-antigos-vazio">
                  Nenhuma transferência de propriedade registrada foi encontrada na matrícula.
                </p>
              )}

              {/* ─── Manual override (migration 152) ─────────────────────
                  Always available — the acts-based derivation above wins
                  when it finds something; this is the fallback the contract
                  gate needs when it doesn't. */}
              <div className="space-y-2 rounded border p-2" data-testid="imovel-ultima-transferencia-manual">
                <p className="text-[11px] font-medium text-muted-foreground">
                  Informar manualmente
                </p>
                <div className="flex flex-wrap items-end gap-2">
                  <div className="space-y-1">
                    <Label htmlFor="imovel-ultima-transferencia-data" className="text-xs">
                      Data do registro da última transferência de propriedade
                    </Label>
                    <Input
                      id="imovel-ultima-transferencia-data"
                      type="date"
                      value={ultimaTransferenciaDataDraft}
                      disabled={savingUltimaTransferenciaManual || semRegistroDraft}
                      onChange={(e) => setUltimaTransferenciaDataDraft(e.target.value)}
                      data-testid="imovel-ultima-transferencia-data"
                    />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="imovel-ultima-transferencia-natureza" className="text-xs">
                      Natureza
                    </Label>
                    <Select
                      value={ultimaTransferenciaNaturezaDraft || undefined}
                      onValueChange={(v) =>
                        setUltimaTransferenciaNaturezaDraft(v as NaturezaUltimaTransferencia)
                      }
                      disabled={savingUltimaTransferenciaManual || semRegistroDraft}
                    >
                      <SelectTrigger
                        id="imovel-ultima-transferencia-natureza"
                        className="w-44"
                        data-testid="imovel-ultima-transferencia-natureza"
                      >
                        <SelectValue placeholder="Selecione" />
                      </SelectTrigger>
                      <SelectContent>
                        {(
                          Object.entries(NATUREZA_ULTIMA_TRANSFERENCIA_LABEL) as [
                            NaturezaUltimaTransferencia,
                            string,
                          ][]
                        ).map(([valor, rotulo]) => (
                          <SelectItem key={valor} value={valor}>
                            {rotulo}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <Checkbox
                    id="imovel-ultima-transferencia-sem-registro"
                    checked={semRegistroDraft}
                    disabled={savingUltimaTransferenciaManual}
                    onCheckedChange={(v) => {
                      const marcado = v === true;
                      setSemRegistroDraft(marcado);
                      if (marcado) {
                        setUltimaTransferenciaDataDraft("");
                        setUltimaTransferenciaNaturezaDraft("");
                      }
                    }}
                    data-testid="imovel-ultima-transferencia-sem-registro"
                  />
                  <Label
                    htmlFor="imovel-ultima-transferencia-sem-registro"
                    className="text-xs font-normal"
                  >
                    Não consta transferência registrada
                  </Label>
                </div>

                {manual?.confirmado_por && (
                  <Confirmacao
                    nome={manual.confirmado_por?.nome}
                    em={manual.confirmado_em}
                    testId="imovel-ultima-transferencia-confirmado"
                  />
                )}

                <div className="flex items-center gap-2">
                  <Button
                    type="button"
                    size="sm"
                    disabled={
                      savingUltimaTransferenciaManual ||
                      (!semRegistroDraft && !ultimaTransferenciaDataDraft)
                    }
                    onClick={() =>
                      onConfirmarUltimaTransferenciaManual({
                        data: semRegistroDraft ? null : ultimaTransferenciaDataDraft || null,
                        natureza: semRegistroDraft
                          ? null
                          : (ultimaTransferenciaNaturezaDraft || null) as
                              | NaturezaUltimaTransferencia
                              | null,
                        semRegistro: semRegistroDraft,
                      })
                    }
                    data-testid="imovel-ultima-transferencia-confirmar"
                  >
                    {savingUltimaTransferenciaManual && (
                      <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                    )}
                    Confirmar
                  </Button>
                  {manual && (
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      disabled={savingUltimaTransferenciaManual}
                      onClick={() =>
                        onConfirmarUltimaTransferenciaManual({
                          data: null,
                          natureza: null,
                          semRegistro: false,
                        })
                      }
                      data-testid="imovel-ultima-transferencia-limpar"
                    >
                      Limpar
                    </Button>
                  )}
                </div>
              </div>
            </>
          )}
        </section>
      </CardContent>
    </Card>
  );
}

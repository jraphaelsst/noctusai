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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";

import {
  ANOS_CERTIDOES_ANTIGOS_PROPRIETARIOS,
  motivoSemSugestaoTexto,
  type AntigosProprietariosResponse,
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

  onus: OnusCredorResponse | undefined;
  onusShowSkeleton: boolean;
  onusIsRefreshing: boolean;
  onusIsError: boolean;
  savingOnus: boolean;
  onConfirmarOnusCredor: (credor: string | null) => void;

  antigos: AntigosProprietariosResponse | undefined;
  antigosShowSkeleton: boolean;
  antigosIsError: boolean;
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
  onus,
  onusShowSkeleton,
  onusIsRefreshing,
  onusIsError,
  savingOnus,
  onConfirmarOnusCredor,
  antigos,
  antigosShowSkeleton,
  antigosIsError,
}: ImovelContratoCardProps) {
  // Drafts seeded from the CONFIRMED wording (not the suggestion): the
  // suggestion is one click away via "Usar sugestão", and pre-filling with it
  // would make an unreviewed reading look like a decision already taken.
  const [tituloDraft, setTituloDraft] = useState("");
  const [credorDraft, setCredorDraft] = useState("");

  const tituloConfirmado = titulo?.confirmado?.texto ?? "";
  useEffect(() => {
    setTituloDraft(tituloConfirmado);
  }, [tituloConfirmado]);

  const credorConfirmado = onus?.confirmado?.credor ?? "";
  useEffect(() => {
    setCredorDraft(credorConfirmado);
  }, [credorConfirmado]);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <FileSignature className="h-4 w-4" />
          Para o contrato
          {(tituloIsRefreshing || onusIsRefreshing) && (
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
          ) : !antigos?.ultima_transferencia ? (
            <p className="text-xs text-muted-foreground" data-testid="imovel-antigos-vazio">
              Nenhuma compra e venda registrada foi encontrada na matrícula.
            </p>
          ) : (
            <>
              <p className="text-xs text-muted-foreground">
                Última transferência: ato{" "}
                <strong>{antigos.ultima_transferencia.ato_ref ?? "—"}</strong>
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
              ) : (
                <p className="text-xs text-muted-foreground">
                  O ato não informa os vendedores — confira os detalhes do ato.
                </p>
              )}

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
                  Certidões dos antigos proprietários são obrigatórias: a venda foi registrada
                  há menos de {ANOS_CERTIDOES_ANTIGOS_PROPRIETARIOS} anos.
                </p>
              )}
            </>
          )}
        </section>
      </CardContent>
    </Card>
  );
}

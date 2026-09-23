/**
 * `<TermosNegocioSection/>` — the deal's contract CLAUSES: posse, permuta
 * reversa, itens integrantes / ad corpus, ônus, confissão de dívida and
 * corretagem (migration 114). This is the surface for every per-deal term no
 * uploaded document carries — the contract generator prints straight from it.
 *
 * 🔴 PUT REPLACES THE WHOLE OBJECT — every key is sent on every save.
 * `PUT .../negociacao/termos` stores an absent key as `null`; this component
 * keeps ALL seventeen fields in one draft and submits the complete shape on
 * "Salvar termos", never a partial patch (there is no PATCH here — see
 * `useAtualizarTermos`).
 *
 * 🔴 ITENS INTEGRANTES AND AD CORPUS ARE EXPLICIT ANSWERS (2026-09-23).
 * Contract generation now blocks until each is ANSWERED
 * (`contrato_gerador.derivacao._contrato`), so "not answered" must stay
 * representable here and never be saved as an answer by accident:
 *   - itens integrantes: "Há itens (listar)" vs "Nenhum item integrante"
 *     (`itens_integrantes_ausente_confirmado`, migration 163) vs unanswered.
 *   - ad corpus: "Sim" vs "Não" vs unanswered. It used to be a checkbox
 *     seeded `?? false`, so ANY termos save silently answered "não".
 * Each control carries the DOM id the readiness list's "Resolver" link
 * targets (`derivacao.ALVO_*`).
 *
 * 🔴 GROUP VISIBILITY IS DATA-DRIVEN, NOT A TAB THE OPERATOR PICKS.
 * The permuta-reversa group only makes sense once the deal actually has a
 * `permuta` parcela; the confissão group only once some parcela is marked
 * `confissao_divida`. Showing them unconditionally would let someone draft
 * clauses for a mechanism the deal does not use.
 */
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { AlertTriangle, Loader2 } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";

import { formatBRL } from "@/hooks/useNegociacao";
import { useAtualizarTermos } from "@/hooks/useNegociacaoEstruturada";
import {
  CORRETAGEM_CONTRATANTES,
  CORRETAGEM_CONTRATANTES_LABELS,
  ONUS_QUITACOES,
  ONUS_QUITACAO_LABELS,
  POSSE_MARCOS,
  POSSE_MARCO_LABELS,
  type CorretagemContratantes,
  type NegociacaoEstruturada,
  type NegociacaoParcela,
  type NegociacaoTermos,
  type OnusQuitacao,
  type PosseMarco,
  type TermosNegocioPut,
} from "@/types/negociacaoEstruturada";

interface Props {
  clienteId: string;
  data: NegociacaoEstruturada;
}

function errorMessage(err: unknown, fallback: string): string {
  return (err as { message?: string } | null)?.message ?? fallback;
}

// ─── Draft — every field a plain string/boolean, parsed only on submit ─────

interface TermosDraft {
  posse_prazo_dias: string;
  posse_marco: PosseMarco | "";
  posse_marco_parcela_id: string;

  permuta_posse_prazo_dias: string;
  permuta_posse_marco: PosseMarco | "";
  permuta_posse_marco_parcela_id: string;
  permuta_obrigacoes_entrega: string;

  /** "" = not answered yet. */
  itens_resposta: ItensResposta | "";
  itens_integrantes: string;
  /** "" = not answered yet. */
  ad_corpus: "sim" | "nao" | "";
  obrigacoes_vendedor: string;

  onus_quitacao: OnusQuitacao | "";
  onus_prazo_dias: string;

  confissao_juros_am: string;
  confissao_garantia: string;

  corretagem_contratantes: CorretagemContratantes | "";
  corretagem_num_parcelas: string;
}

function toDraft(t: NegociacaoTermos): TermosDraft {
  return {
    posse_prazo_dias: t.posse_prazo_dias == null ? "" : String(t.posse_prazo_dias),
    posse_marco: t.posse_marco ?? "",
    posse_marco_parcela_id: t.posse_marco_parcela_id ?? "",

    permuta_posse_prazo_dias:
      t.permuta_posse_prazo_dias == null ? "" : String(t.permuta_posse_prazo_dias),
    permuta_posse_marco: t.permuta_posse_marco ?? "",
    permuta_posse_marco_parcela_id: t.permuta_posse_marco_parcela_id ?? "",
    permuta_obrigacoes_entrega: t.permuta_obrigacoes_entrega ?? "",

    itens_resposta: t.itens_integrantes
      ? "lista"
      : t.itens_integrantes_ausente_confirmado
        ? "nenhum"
        : "",
    itens_integrantes: t.itens_integrantes ?? "",
    ad_corpus: t.ad_corpus == null ? "" : t.ad_corpus ? "sim" : "nao",
    obrigacoes_vendedor: t.obrigacoes_vendedor ?? "",

    onus_quitacao: t.onus_quitacao ?? "",
    onus_prazo_dias: t.onus_prazo_dias == null ? "" : String(t.onus_prazo_dias),

    confissao_juros_am: t.confissao_juros_am ?? "",
    confissao_garantia: t.confissao_garantia ?? "",

    corretagem_contratantes: t.corretagem_contratantes ?? "",
    corretagem_num_parcelas:
      t.corretagem_num_parcelas == null ? "" : String(t.corretagem_num_parcelas),
  };
}

/** Empty string -> `null`; else the (possibly invalid) trimmed digits — the
 *  400 for a non-integer or a negative prazo is the backend's, this only
 *  decides what gets SENT. */
function inteiroOuNulo(v: string): number | null {
  const s = v.trim();
  if (s === "") return null;
  const n = Number(s);
  return Number.isFinite(n) ? Math.trunc(n) : null;
}

function textoOuNulo(v: string): string | null {
  const s = v.trim();
  return s === "" ? null : s;
}

/** Reads a pt-BR-typed percentage ("1,5" or "1.5") into the plain decimal
 *  string the backend expects. Never parsed to float — passed through as
 *  text end to end. */
function lerPercentual(v: string): string | null {
  const s = v.trim();
  if (s === "") return null;
  return s.replace(",", ".");
}

function toPayload(d: TermosDraft): TermosNegocioPut {
  return {
    posse_prazo_dias: inteiroOuNulo(d.posse_prazo_dias),
    posse_marco: d.posse_marco || null,
    posse_marco_parcela_id: d.posse_marco === "parcela" ? d.posse_marco_parcela_id || null : null,

    permuta_posse_prazo_dias: inteiroOuNulo(d.permuta_posse_prazo_dias),
    permuta_posse_marco: d.permuta_posse_marco || null,
    permuta_posse_marco_parcela_id:
      d.permuta_posse_marco === "parcela" ? d.permuta_posse_marco_parcela_id || null : null,
    permuta_obrigacoes_entrega: textoOuNulo(d.permuta_obrigacoes_entrega),

    // Only the chosen answer travels: listing items sends the text (the
    // backend refuses text AND "nenhum" together), "nenhum" sends the flag.
    itens_integrantes: d.itens_resposta === "lista" ? textoOuNulo(d.itens_integrantes) : null,
    itens_integrantes_ausente_confirmado: d.itens_resposta === "nenhum",
    ad_corpus: d.ad_corpus === "" ? null : d.ad_corpus === "sim",
    obrigacoes_vendedor: textoOuNulo(d.obrigacoes_vendedor),

    onus_quitacao: d.onus_quitacao || null,
    onus_prazo_dias: inteiroOuNulo(d.onus_prazo_dias),

    confissao_juros_am: lerPercentual(d.confissao_juros_am),
    confissao_garantia: textoOuNulo(d.confissao_garantia),

    corretagem_contratantes: d.corretagem_contratantes || null,
    corretagem_num_parcelas: inteiroOuNulo(d.corretagem_num_parcelas),
  };
}

const NENHUMA_PARCELA = "__none__";

type ItensResposta = "lista" | "nenhum";

/** DOM ids the contract readiness list's "Resolver" lands on — the SAME
 *  strings `contrato_gerador.derivacao.ALVO_*` emits as `destino.alvo`. */
export const ALVO_ITENS_INTEGRANTES = "termos-itens-integrantes-resposta";
export const ALVO_AD_CORPUS = "termos-ad-corpus-resposta";

/**
 * An explicit, mutually-exclusive answer — a radiogroup of buttons where
 * NOTHING is selected until someone answers. A checkbox cannot say
 * "unanswered", which is exactly the state generation blocks on.
 */
function EscolhaExplicita<V extends string>({
  id,
  rotulo,
  opcoes,
  valor,
  onChange,
}: {
  id: string;
  rotulo: string;
  opcoes: { valor: V; rotulo: string }[];
  valor: V | "";
  onChange: (v: V) => void;
}) {
  return (
    <div className="space-y-1.5">
      <p className="text-sm font-medium leading-none" id={`${id}-rotulo`}>
        {rotulo}
      </p>
      <div
        id={id}
        role="radiogroup"
        aria-labelledby={`${id}-rotulo`}
        tabIndex={-1}
        className="inline-flex flex-wrap gap-1 rounded-md border bg-muted/40 p-1"
        data-testid={id}
      >
        {opcoes.map((o) => {
          const ativo = o.valor === valor;
          return (
            <Button
              key={o.valor}
              type="button"
              size="sm"
              variant={ativo ? "default" : "ghost"}
              role="radio"
              aria-checked={ativo}
              onClick={() => onChange(o.valor)}
              data-testid={`${id}-${o.valor}`}
            >
              {o.rotulo}
            </Button>
          );
        })}
      </div>
      {valor === "" && (
        <p className="text-xs text-amber-700" data-testid={`${id}-pendente`}>
          Sem resposta — a geração do contrato fica bloqueada até responder.
        </p>
      )}
    </div>
  );
}

function ParcelaMarcoSelect({
  id,
  value,
  onChange,
  parcelas,
}: {
  id: string;
  value: string;
  onChange: (v: string) => void;
  parcelas: NegociacaoParcela[];
}) {
  return (
    <Select
      value={value || NENHUMA_PARCELA}
      onValueChange={(v) => onChange(v === NENHUMA_PARCELA ? "" : v)}
    >
      <SelectTrigger id={id}>
        <SelectValue placeholder="Selecione a parcela" />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={NENHUMA_PARCELA}>Nenhuma</SelectItem>
        {parcelas.map((p) => (
          <SelectItem key={p.id} value={p.id}>
            {p.evento ?? p.vencimento ?? p.id} — {formatBRL(p.valor)}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

export default function TermosNegocioSection({ clienteId, data }: Props) {
  const mutation = useAtualizarTermos(clienteId);
  const [draft, setDraft] = useState<TermosDraft>(() => toDraft(data.termos));

  useEffect(() => {
    setDraft(toDraft(data.termos));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data.termos]);

  const temPermuta = data.parcelas.some((p) => p.tipo === "permuta");
  const temConfissao = data.parcelas.some((p) => p.confissao_divida);

  const posseMarcoFaltaParcela =
    draft.posse_marco === "parcela" && !draft.posse_marco_parcela_id;
  const permutaMarcoFaltaParcela =
    draft.permuta_posse_marco === "parcela" && !draft.permuta_posse_marco_parcela_id;

  // "Sim — listar" with nothing listed would save as UNANSWERED (blank text
  // collapses to null server-side) while the screen claims an answer.
  const itensListaVazia =
    draft.itens_resposta === "lista" && !draft.itens_integrantes.trim();

  const podeSalvar =
    !posseMarcoFaltaParcela && !permutaMarcoFaltaParcela && !itensListaVazia;

  function submit() {
    if (!podeSalvar) return;
    mutation.mutate(toPayload(draft), {
      onSuccess: () => toast.success("Termos do negócio salvos."),
      onError: (err: unknown) =>
        toast.error(errorMessage(err, "Não foi possível salvar os termos do negócio.")),
    });
  }

  return (
    <Card data-testid="negest-termos">
      <CardHeader>
        <CardTitle className="text-base">Termos do negócio</CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* ─── Posse ─────────────────────────────────────────────────── */}
        <section className="space-y-3" data-testid="termos-posse">
          <h4 className="text-sm font-medium">Posse</h4>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="termos-posse-prazo">Prazo (dias)</Label>
              <Input
                id="termos-posse-prazo"
                data-testid="termos-posse-prazo"
                type="number"
                min={0}
                value={draft.posse_prazo_dias}
                onChange={(e) =>
                  setDraft((d) => ({ ...d, posse_prazo_dias: e.target.value }))
                }
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="termos-posse-marco">Marco</Label>
              <Select
                value={draft.posse_marco || NENHUMA_PARCELA}
                onValueChange={(v) =>
                  setDraft((d) => ({
                    ...d,
                    posse_marco: v === NENHUMA_PARCELA ? "" : (v as PosseMarco),
                    posse_marco_parcela_id:
                      v === "parcela" ? d.posse_marco_parcela_id : "",
                  }))
                }
              >
                <SelectTrigger id="termos-posse-marco">
                  <SelectValue placeholder="Nenhum" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={NENHUMA_PARCELA}>Nenhum</SelectItem>
                  {POSSE_MARCOS.map((m) => (
                    <SelectItem key={m} value={m}>
                      {POSSE_MARCO_LABELS[m]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          {draft.posse_marco === "parcela" && (
            <div className="space-y-1.5">
              <Label htmlFor="termos-posse-parcela">Parcela que marca a posse</Label>
              <ParcelaMarcoSelect
                id="termos-posse-parcela"
                value={draft.posse_marco_parcela_id}
                onChange={(v) =>
                  setDraft((d) => ({ ...d, posse_marco_parcela_id: v }))
                }
                parcelas={data.parcelas}
              />
              {posseMarcoFaltaParcela && (
                <p
                  className="text-xs text-destructive"
                  data-testid="termos-posse-parcela-erro"
                >
                  Informe a parcela que marca a entrega da posse.
                </p>
              )}
            </div>
          )}
        </section>

        {/* ─── Permuta reversa (só quando há parcela de permuta) ────────── */}
        {temPermuta && (
          <section className="space-y-3" data-testid="termos-permuta">
            <h4 className="text-sm font-medium">Permuta — entrega do imóvel</h4>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="termos-permuta-prazo">Prazo (dias)</Label>
                <Input
                  id="termos-permuta-prazo"
                  type="number"
                  min={0}
                  value={draft.permuta_posse_prazo_dias}
                  onChange={(e) =>
                    setDraft((d) => ({
                      ...d,
                      permuta_posse_prazo_dias: e.target.value,
                    }))
                  }
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="termos-permuta-marco">Marco</Label>
                <Select
                  value={draft.permuta_posse_marco || NENHUMA_PARCELA}
                  onValueChange={(v) =>
                    setDraft((d) => ({
                      ...d,
                      permuta_posse_marco: v === NENHUMA_PARCELA ? "" : (v as PosseMarco),
                      permuta_posse_marco_parcela_id:
                        v === "parcela" ? d.permuta_posse_marco_parcela_id : "",
                    }))
                  }
                >
                  <SelectTrigger id="termos-permuta-marco">
                    <SelectValue placeholder="Nenhum" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={NENHUMA_PARCELA}>Nenhum</SelectItem>
                    {POSSE_MARCOS.map((m) => (
                      <SelectItem key={m} value={m}>
                        {POSSE_MARCO_LABELS[m]}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            {draft.permuta_posse_marco === "parcela" && (
              <div className="space-y-1.5">
                <Label htmlFor="termos-permuta-parcela">
                  Parcela que marca a entrega do imóvel da permuta
                </Label>
                <ParcelaMarcoSelect
                  id="termos-permuta-parcela"
                  value={draft.permuta_posse_marco_parcela_id}
                  onChange={(v) =>
                    setDraft((d) => ({ ...d, permuta_posse_marco_parcela_id: v }))
                  }
                  parcelas={data.parcelas}
                />
                {permutaMarcoFaltaParcela && (
                  <p
                    className="text-xs text-destructive"
                    data-testid="termos-permuta-parcela-erro"
                  >
                    Informe a parcela que marca a entrega do imóvel da permuta.
                  </p>
                )}
              </div>
            )}
            <div className="space-y-1.5">
              <Label htmlFor="termos-permuta-obrigacoes">
                Obrigações de entrega
              </Label>
              <Textarea
                id="termos-permuta-obrigacoes"
                value={draft.permuta_obrigacoes_entrega}
                onChange={(e) =>
                  setDraft((d) => ({
                    ...d,
                    permuta_obrigacoes_entrega: e.target.value,
                  }))
                }
              />
            </div>
          </section>
        )}

        {/* ─── Itens integrantes / ad corpus / obrigações do vendedor ─── */}
        <section className="space-y-3" data-testid="termos-itens">
          <h4 className="text-sm font-medium">Itens integrantes</h4>
          <EscolhaExplicita<ItensResposta>
            id={ALVO_ITENS_INTEGRANTES}
            rotulo="O imóvel tem itens integrantes?"
            opcoes={[
              { valor: "lista", rotulo: "Sim — listar os itens" },
              { valor: "nenhum", rotulo: "Nenhum item integrante" },
            ]}
            valor={draft.itens_resposta}
            onChange={(v) => setDraft((d) => ({ ...d, itens_resposta: v }))}
          />
          {draft.itens_resposta === "lista" && (
            <div className="space-y-1.5">
              <Label htmlFor="termos-itens-integrantes">
                Itens integrantes do imóvel
              </Label>
              <Textarea
                id="termos-itens-integrantes"
                data-testid="termos-itens-integrantes"
                value={draft.itens_integrantes}
                onChange={(e) =>
                  setDraft((d) => ({ ...d, itens_integrantes: e.target.value }))
                }
              />
              {!draft.itens_integrantes.trim() && (
                <p
                  className="text-xs text-destructive"
                  data-testid="termos-itens-integrantes-erro"
                >
                  Relacione os itens, ou escolha &ldquo;Nenhum item integrante&rdquo;.
                </p>
              )}
            </div>
          )}
          <EscolhaExplicita<"sim" | "nao">
            id={ALVO_AD_CORPUS}
            rotulo="Venda ad corpus?"
            opcoes={[
              { valor: "sim", rotulo: "Sim" },
              { valor: "nao", rotulo: "Não" },
            ]}
            valor={draft.ad_corpus}
            onChange={(v) => setDraft((d) => ({ ...d, ad_corpus: v }))}
          />
          <div className="space-y-1.5">
            <Label htmlFor="termos-obrigacoes-vendedor">
              Obrigações do vendedor
            </Label>
            <Textarea
              id="termos-obrigacoes-vendedor"
              value={draft.obrigacoes_vendedor}
              onChange={(e) =>
                setDraft((d) => ({ ...d, obrigacoes_vendedor: e.target.value }))
              }
            />
          </div>
        </section>

        {/* ─── Ônus / quitação — sempre visível, com a nota de quando aplica ── */}
        <section className="space-y-3" data-testid="termos-onus">
          <h4 className="text-sm font-medium">Ônus e quitação</h4>
          <p className="text-xs text-muted-foreground">
            Aplica-se quando o imóvel tem financiamento (ônus) a quitar.
          </p>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="termos-onus-quitacao">Quitação do ônus</Label>
              <Select
                value={draft.onus_quitacao || NENHUMA_PARCELA}
                onValueChange={(v) =>
                  setDraft((d) => ({
                    ...d,
                    onus_quitacao: v === NENHUMA_PARCELA ? "" : (v as OnusQuitacao),
                  }))
                }
              >
                <SelectTrigger id="termos-onus-quitacao">
                  <SelectValue placeholder="Nenhuma" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={NENHUMA_PARCELA}>Nenhuma</SelectItem>
                  {ONUS_QUITACOES.map((o) => (
                    <SelectItem key={o} value={o}>
                      {ONUS_QUITACAO_LABELS[o]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="termos-onus-prazo">Prazo de quitação (dias)</Label>
              <Input
                id="termos-onus-prazo"
                type="number"
                min={0}
                value={draft.onus_prazo_dias}
                onChange={(e) =>
                  setDraft((d) => ({ ...d, onus_prazo_dias: e.target.value }))
                }
              />
            </div>
          </div>
        </section>

        {/* ─── Confissão de dívida (só quando há parcela marcada) ───────── */}
        {temConfissao && (
          <section className="space-y-3" data-testid="termos-confissao">
            <h4 className="text-sm font-medium">Confissão de dívida</h4>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="termos-confissao-juros">Juros (% ao mês)</Label>
                <Input
                  id="termos-confissao-juros"
                  value={draft.confissao_juros_am}
                  onChange={(e) =>
                    setDraft((d) => ({ ...d, confissao_juros_am: e.target.value }))
                  }
                  placeholder="0,00"
                />
              </div>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="termos-confissao-garantia">Garantia</Label>
              <Textarea
                id="termos-confissao-garantia"
                value={draft.confissao_garantia}
                onChange={(e) =>
                  setDraft((d) => ({ ...d, confissao_garantia: e.target.value }))
                }
              />
            </div>
          </section>
        )}

        {/* ─── Corretagem ────────────────────────────────────────────── */}
        <section className="space-y-3" data-testid="termos-corretagem">
          <h4 className="text-sm font-medium">Corretagem</h4>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="termos-corretagem-contratantes">
                Contratantes da corretagem
              </Label>
              <Select
                value={draft.corretagem_contratantes || NENHUMA_PARCELA}
                onValueChange={(v) =>
                  setDraft((d) => ({
                    ...d,
                    corretagem_contratantes:
                      v === NENHUMA_PARCELA ? "" : (v as CorretagemContratantes),
                  }))
                }
              >
                <SelectTrigger id="termos-corretagem-contratantes">
                  <SelectValue placeholder="Nenhum" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={NENHUMA_PARCELA}>Nenhum</SelectItem>
                  {CORRETAGEM_CONTRATANTES.map((c) => (
                    <SelectItem key={c} value={c}>
                      {CORRETAGEM_CONTRATANTES_LABELS[c]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="termos-corretagem-parcelas">
                Número de parcelas
              </Label>
              <Input
                id="termos-corretagem-parcelas"
                type="number"
                min={1}
                value={draft.corretagem_num_parcelas}
                onChange={(e) =>
                  setDraft((d) => ({
                    ...d,
                    corretagem_num_parcelas: e.target.value,
                  }))
                }
              />
            </div>
          </div>
        </section>

        {!podeSalvar && (
          <p
            className="flex items-center gap-2 text-xs text-destructive"
            data-testid="termos-erro-geral"
          >
            <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
            Corrija os campos destacados antes de salvar.
          </p>
        )}

        <div className="flex justify-end">
          <Button
            onClick={submit}
            disabled={!podeSalvar || mutation.isPending}
            data-testid="negest-termos-salvar"
          >
            {mutation.isPending ? (
              <>
                <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                Salvando…
              </>
            ) : (
              "Salvar termos"
            )}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

/**
 * PropostaModal — full CRUD for one proposta (CONTRACT §4.3): Valores,
 * Parcelas (live saldo), Favorecidos, Intermediários, Termos, Contrato
 * (imobiliária + testemunhas). Footer: Salvar · Enviar · Recusar (motivo) ·
 * Aceitar (confirm lists `completude`) · Excluir (rascunho). Closed statuses
 * are read-only. After Aceitar the dialog switches to "Preparando contrato".
 */
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import type { CardSubpageKey } from "@/components/card/cardSubpages";
import { useImobiliarias } from "@/hooks/useImobiliarias";
import { useProposta, usePropostaMutations } from "@/hooks/usePropostas";
import { useTestemunhas } from "@/hooks/useTestemunhas";
import { exibirMoeda, lerValorDigitado } from "@/lib/moedaDecimal";
import {
  propostaEditavel,
  type AceiteResponse,
  type Proposta,
  type PropostaPatch,
} from "@/types/propostas";

import { lerErroProposta, campoInvalido } from "./erroProposta";
import { PropostaStatusBadge } from "./PropostaCard";
import {
  FavorecidosEditor, IntermediariosEditor, ParcelasEditor, TermosEditor,
} from "./PropostaEditores";
import { PreparandoContratoPanel } from "./PreparandoContratoPanel";

type Draft = Required<PropostaPatch>;

function draftDe(p: Proposta): Draft {
  return {
    valor_proposto: p.valor_proposto ?? "",
    pct_comissao: p.pct_comissao ?? "",
    financiamento: p.financiamento,
    fgts: p.fgts,
    validade_ate: p.validade_ate,
    observacoes: p.observacoes,
    parcelas: p.parcelas,
    favorecidos: p.favorecidos,
    intermediarios: p.intermediarios,
    termos: p.termos,
    imobiliaria_id: p.imobiliaria_id,
    testemunha_ids: p.testemunha_ids,
  } as Draft;
}

/** Money fields: what a Brazilian types → the decimal string on the wire. */
function paraEnvio(d: Draft): PropostaPatch {
  const vazioNulo = (s: string | null | undefined) => (s == null || s.trim() === "" ? null : lerValorDigitado(s));
  return {
    ...d,
    valor_proposto: vazioNulo(d.valor_proposto),
    pct_comissao: vazioNulo(d.pct_comissao),
    parcelas: d.parcelas.map((p) => ({ ...p, valor: lerValorDigitado(p.valor) })),
    intermediarios: d.intermediarios.map((m) => ({
      ...m,
      valor: m.valor ? lerValorDigitado(m.valor) : null,
    })),
  };
}

/** Display-only saldo (the server's `saldo_nao_alocado` is the source of truth on save). */
function saldoLocal(d: Draft): string | null {
  const total = Number(lerValorDigitado(d.valor_proposto ?? ""));
  if (!d.valor_proposto || !Number.isFinite(total)) return null;
  const soma = d.parcelas.reduce((a, p) => a + (Number(lerValorDigitado(p.valor)) || 0), 0);
  return (total - soma).toFixed(2);
}

export interface PropostaModalProps {
  clienteId: string;
  propostaId: string;
  onClose: () => void;
  irPara?: (subpage: CardSubpageKey) => void;
  onAbrirContrato?: (contratoId: string) => void;
}

export function PropostaModal({ clienteId, propostaId, onClose, irPara, onAbrirContrato }: PropostaModalProps) {
  const query = useProposta(clienteId, propostaId);
  const m = usePropostaMutations(clienteId);
  const imobs = useImobiliarias();
  const testemunhas = useTestemunhas();

  const proposta = query.data;
  const [draft, setDraft] = useState<Draft | null>(null);
  const [sujo, setSujo] = useState(false);
  const [campos, setCampos] = useState<string[]>([]);
  const [recusando, setRecusando] = useState(false);
  const [motivo, setMotivo] = useState("");
  const [confirmaAceite, setConfirmaAceite] = useState(false);
  const [aceite, setAceite] = useState<AceiteResponse | null>(null);

  // Re-seed from the server unless the operator has unsaved edits.
  useEffect(() => {
    if (proposta && !sujo) setDraft(draftDe(proposta));
  }, [proposta, sujo]);

  const editavel = !!proposta && propostaEditavel(proposta.status) && !aceite;
  const saldo = useMemo(() => (draft ? saldoLocal(draft) : null), [draft]);

  function alterar(patch: Partial<Draft>) {
    setDraft((d) => (d ? { ...d, ...patch } : d));
    setSujo(true);
  }
  function falha(err: unknown, fallback: string) {
    const e = lerErroProposta(err, fallback);
    setCampos(e.campos);
    toast.error(e.mensagem);
  }

  async function salvar(): Promise<boolean> {
    if (!draft) return false;
    try {
      await m.salvar.mutateAsync({ id: propostaId, patch: paraEnvio(draft) });
      setSujo(false);
      setCampos([]);
      return true;
    } catch (err) {
      falha(err, "Não foi possível salvar a proposta.");
      return false;
    }
  }

  async function handleSalvar() {
    if (await salvar()) toast.success("Proposta salva.");
  }
  async function handleEnviar() {
    if (sujo && !(await salvar())) return;
    try {
      await m.enviar.mutateAsync({ id: propostaId });
      toast.success("Proposta enviada.");
    } catch (err) {
      falha(err, "Não foi possível enviar a proposta.");
    }
  }
  async function handleRecusar() {
    if (!motivo.trim()) return;
    try {
      await m.recusar.mutateAsync({ id: propostaId, motivo: motivo.trim() });
      toast.success("Proposta recusada.");
      setRecusando(false);
      setMotivo("");
    } catch (err) {
      falha(err, "Não foi possível recusar a proposta.");
    }
  }
  async function handleAceitar() {
    setConfirmaAceite(false);
    if (sujo && !(await salvar())) return;
    try {
      const res = await m.aceitar.mutateAsync({ id: propostaId });
      toast.success("Proposta aceita. Contrato em preparação.");
      setAceite(res);
    } catch (err) {
      falha(err, "Não foi possível aceitar a proposta.");
    }
  }
  async function handleExcluir() {
    try {
      await m.excluir.mutateAsync({ id: propostaId });
      toast.success("Proposta excluída.");
      onClose();
    } catch (err) {
      falha(err, "Não foi possível excluir a proposta.");
    }
  }
  async function handlePosAceite() {
    try {
      const pos = await m.posAceite.mutateAsync({ id: propostaId });
      setAceite((a) => (a ? { ...a, pos_aceite: pos } : a));
    } catch (err) {
      falha(err, "Não foi possível refazer certidões e matrícula.");
    }
  }

  const ocupado = m.salvar.isPending || m.enviar.isPending || m.recusar.isPending || m.aceitar.isPending || m.excluir.isPending;
  const completude = proposta?.completude ?? [];
  const ids = new Set(draft?.testemunha_ids ?? []);

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90vh] max-w-3xl overflow-y-auto" data-testid="proposta-modal">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {proposta ? (proposta.imovel.titulo ?? proposta.imovel.codigo) : "Proposta"}
            {proposta && <PropostaStatusBadge status={proposta.status} />}
          </DialogTitle>
          {proposta && (
            <p className="text-xs text-muted-foreground">
              {proposta.imovel.codigo}
              {proposta.imovel.endereco ? ` · ${proposta.imovel.endereco}` : ""}
            </p>
          )}
        </DialogHeader>

        {query.showSkeleton ? (
          <p className="text-sm text-muted-foreground" data-testid="proposta-loading">Carregando…</p>
        ) : query.isError && !proposta ? (
          <p className="text-sm text-destructive" role="alert" data-testid="proposta-erro">
            {lerErroProposta(query.error, "Não foi possível carregar a proposta.").mensagem}
          </p>
        ) : aceite && proposta ? (
          <PreparandoContratoPanel
            imovelCodigo={proposta.imovel_codigo}
            passos={aceite.passos}
            posAceite={aceite.pos_aceite}
            tentando={m.aceitar.isPending || m.posAceite.isPending}
            onTentarAceiteDeNovo={() => void handleAceitar()}
            onTentarPosAceiteDeNovo={() => void handlePosAceite()}
            onAbrirCertidoes={irPara ? () => { irPara("certidoes"); onClose(); } : undefined}
            onAbrirContratos={irPara ? () => {
              const id = aceite.contrato_id ?? aceite.proposta.contrato_id;
              if (id) onAbrirContrato?.(id);
              irPara("contratos");
              onClose();
            } : undefined}
          />
        ) : proposta && draft ? (
          <div className="space-y-5">
            {query.isRefreshing && <p className="text-xs text-muted-foreground" data-testid="proposta-refreshing">Atualizando…</p>}
            {proposta.status === "recusada" && proposta.motivo_recusa && (
              <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-900" data-testid="proposta-motivo-recusa">
                Recusada: {proposta.motivo_recusa}
              </p>
            )}
            {!editavel && proposta.status !== "recusada" && (
              <p className="text-xs text-muted-foreground" data-testid="proposta-somente-leitura">
                Proposta encerrada: somente leitura.
              </p>
            )}

            <Secao titulo="Valores">
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <Label htmlFor="pp-valor" className="text-xs">Valor proposto</Label>
                  <Input id="pp-valor" disabled={!editavel} className={campoInvalido(campos, "valor_proposto") ? "border-destructive ring-1 ring-destructive" : ""} value={draft.valor_proposto ?? ""} onChange={(e) => alterar({ valor_proposto: e.target.value })} />
                  {draft.valor_proposto && <p className="text-xs text-muted-foreground">{exibirMoeda(lerValorDigitado(draft.valor_proposto))}</p>}
                </div>
                <div className="space-y-1">
                  <Label htmlFor="pp-comissao" className="text-xs">Comissão (%)</Label>
                  <Input id="pp-comissao" disabled={!editavel} className={campoInvalido(campos, "pct_comissao") ? "border-destructive ring-1 ring-destructive" : ""} value={draft.pct_comissao ?? ""} onChange={(e) => alterar({ pct_comissao: e.target.value })} />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="pp-validade" className="text-xs">Validade</Label>
                  <Input id="pp-validade" type="date" disabled={!editavel} className={campoInvalido(campos, "validade_ate") ? "border-destructive ring-1 ring-destructive" : ""} value={draft.validade_ate ?? ""} onChange={(e) => alterar({ validade_ate: e.target.value || null })} />
                </div>
                <div className="flex items-end gap-4">
                  <label className="flex items-center gap-2 text-sm">
                    <Switch aria-label="Financiamento" disabled={!editavel} checked={!!draft.financiamento} onCheckedChange={(v) => alterar({ financiamento: v })} />
                    Financiamento
                  </label>
                  <label className="flex items-center gap-2 text-sm">
                    <Switch aria-label="FGTS" disabled={!editavel} checked={!!draft.fgts} onCheckedChange={(v) => alterar({ fgts: v })} />
                    FGTS
                  </label>
                </div>
                <div className="col-span-2 space-y-1">
                  <Label htmlFor="pp-obs" className="text-xs">Observações</Label>
                  <Textarea id="pp-obs" rows={2} disabled={!editavel} value={draft.observacoes ?? ""} onChange={(e) => alterar({ observacoes: e.target.value || null })} />
                </div>
              </div>
            </Secao>

            <Secao titulo="Parcelas">
              <ParcelasEditor value={draft.parcelas} onChange={(v) => alterar({ parcelas: v })} favorecidos={draft.favorecidos} disabled={!editavel} campos={campos} />
              {saldo !== null && (
                <p
                  className={Number(saldo) === 0 ? "text-xs text-green-700" : "text-xs text-amber-700"}
                  data-testid="proposta-saldo"
                >
                  Saldo não alocado: {exibirMoeda(saldo)}
                </p>
              )}
            </Secao>

            <Secao titulo="Favorecidos">
              <FavorecidosEditor value={draft.favorecidos} onChange={(v) => alterar({ favorecidos: v })} disabled={!editavel} campos={campos} />
            </Secao>

            <Secao titulo="Intermediários">
              <IntermediariosEditor value={draft.intermediarios} onChange={(v) => alterar({ intermediarios: v })} disabled={!editavel} campos={campos} />
            </Secao>

            <Secao titulo="Termos">
              <TermosEditor value={draft.termos} onChange={(v) => alterar({ termos: v })} disabled={!editavel} campos={campos} />
            </Secao>

            <Secao titulo="Contrato">
              <div className="space-y-3">
                <div className="space-y-1">
                  <Label className="text-xs">Imobiliária</Label>
                  <Select
                    value={draft.imobiliaria_id ?? ""}
                    onValueChange={(v) => alterar({ imobiliaria_id: v || null })}
                    disabled={!editavel}
                  >
                    <SelectTrigger aria-label="Imobiliária" className={campoInvalido(campos, "imobiliaria_id") ? "border-destructive ring-1 ring-destructive" : ""}>
                      <SelectValue placeholder="Selecione a imobiliária" />
                    </SelectTrigger>
                    <SelectContent>
                      {(imobs.data?.items ?? []).map((i) => (
                        <SelectItem key={i.id} value={i.id}>
                          {i.razao_social || i.nome_fantasia || i.cnpj || "Imobiliária sem nome"}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1" data-testid="proposta-testemunhas">
                  <Label className="text-xs">Testemunhas</Label>
                  {(testemunhas.data?.items ?? []).map((t) => (
                    <label key={t.id} className="flex items-center gap-2 text-sm">
                      <Checkbox
                        aria-label={`Testemunha ${t.nome}`}
                        disabled={!editavel || t.cpf_pendente}
                        checked={ids.has(t.id)}
                        onCheckedChange={(on) =>
                          alterar({
                            testemunha_ids: on
                              ? [...(draft.testemunha_ids ?? []), t.id]
                              : (draft.testemunha_ids ?? []).filter((x) => x !== t.id),
                          })
                        }
                      />
                      {t.nome}
                      {t.cpf_pendente && <span className="text-xs text-muted-foreground">(CPF pendente)</span>}
                    </label>
                  ))}
                </div>
              </div>
            </Secao>

            {completude.length > 0 && (
              <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900" data-testid="proposta-completude">
                <p className="font-medium">Ainda falta para o contrato:</p>
                <ul className="list-disc pl-4">{completude.map((c) => <li key={c}>{c}</li>)}</ul>
              </div>
            )}
          </div>
        ) : null}

        {proposta && draft && !aceite && (
          <DialogFooter className="gap-2 sm:justify-between">
            <div>
              {proposta.status === "rascunho" && (
                <Button variant="ghost" className="text-destructive" disabled={ocupado} onClick={() => void handleExcluir()} data-testid="proposta-excluir">
                  Excluir
                </Button>
              )}
            </div>
            {editavel && (
              <div className="flex flex-wrap gap-2">
                <Button variant="outline" disabled={ocupado || !sujo} onClick={() => void handleSalvar()} data-testid="proposta-salvar">Salvar</Button>
                {proposta.status === "rascunho" && (
                  <Button variant="outline" disabled={ocupado} onClick={() => void handleEnviar()} data-testid="proposta-enviar">Enviar</Button>
                )}
                <Button variant="outline" disabled={ocupado} onClick={() => setRecusando(true)} data-testid="proposta-recusar">Recusar</Button>
                <Button disabled={ocupado} onClick={() => setConfirmaAceite(true)} data-testid="proposta-aceitar">Aceitar</Button>
              </div>
            )}
          </DialogFooter>
        )}

        <AlertDialog open={recusando} onOpenChange={setRecusando}>
          <AlertDialogContent data-testid="recusar-dialog">
            <AlertDialogHeader>
              <AlertDialogTitle>Recusar proposta</AlertDialogTitle>
              <AlertDialogDescription>Informe o motivo da recusa (obrigatório).</AlertDialogDescription>
            </AlertDialogHeader>
            <Textarea aria-label="Motivo da recusa" value={motivo} onChange={(e) => setMotivo(e.target.value)} rows={3} />
            <AlertDialogFooter>
              <AlertDialogCancel>Cancelar</AlertDialogCancel>
              <AlertDialogAction
                disabled={!motivo.trim() || m.recusar.isPending}
                onClick={(e) => { e.preventDefault(); void handleRecusar(); }}
                data-testid="recusar-confirmar"
              >
                Recusar
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>

        <AlertDialog open={confirmaAceite} onOpenChange={setConfirmaAceite}>
          <AlertDialogContent data-testid="aceitar-dialog">
            <AlertDialogHeader>
              <AlertDialogTitle>Aceitar proposta</AlertDialogTitle>
              <AlertDialogDescription>
                A negociação do atendimento será substituída por esta proposta e o contrato será iniciado.
              </AlertDialogDescription>
            </AlertDialogHeader>
            {completude.length > 0 ? (
              <div className="text-sm" data-testid="aceitar-completude">
                <p className="font-medium">Ainda falta para o contrato:</p>
                <ul className="list-disc pl-5">{completude.map((c) => <li key={c}>{c}</li>)}</ul>
              </div>
            ) : (
              <p className="text-sm text-green-700" data-testid="aceitar-completude-ok">Nada pendente para o contrato.</p>
            )}
            <AlertDialogFooter>
              <AlertDialogCancel>Cancelar</AlertDialogCancel>
              <AlertDialogAction onClick={() => void handleAceitar()} data-testid="aceitar-confirmar">Aceitar</AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </DialogContent>
    </Dialog>
  );
}

function Secao({ titulo, children }: { titulo: string; children: React.ReactNode }) {
  return (
    <section className="space-y-2" data-testid={`proposta-secao-${titulo.toLowerCase()}`}>
      <h4 className="text-sm font-semibold">{titulo}</h4>
      {children}
    </section>
  );
}

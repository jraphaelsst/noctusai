/**
 * EnviarAssinaturaDialog — "Enviar para assinatura": prefills signatários
 * from the contract's partes (compradores + vendedores) and the org's
 * standing testemunhas, and lets the operator fix e-mails before sending.
 *
 * Presentational, same S3 discipline as the rest of `card/**`: partes and
 * testemunhas are read by `ContratosContainer` via the hooks that already
 * fetch them for the Compradores/Vendedores tabs (`useCompradores`) and the
 * settings page (`useTestemunhas`) — this file only renders what it is
 * handed, no fetch of its own (`KB § PATTERNS/frontend/product-internal-wiring.md`:
 * reuse the existing read path, never a second one).
 *
 * 🔴 SEEDS ONCE PER OPEN, NOT ON EVERY PROP CHANGE. The effect below reads
 * the incoming partes/testemunhas only on the closed→open transition.
 * Re-seeding on every render while open (e.g. a background refetch of the
 * Compradores tab) would silently discard e-mails the operator just typed.
 */
import { useEffect, useRef, useState } from "react";
import { AlertCircle, ExternalLink, Loader2 } from "lucide-react";
import { useNavigate } from "react-router-dom";

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
import { Textarea } from "@/components/ui/textarea";

import {
  PAPEL_SIGNATARIO_LABEL,
  type AssinaturaError,
  type PapelSignatario,
  type SignatarioInput,
} from "@/hooks/useContratos";
import type { TestemunhaSelecionada } from "@/hooks/useContratoTestemunhas";
import type { Comprador } from "@/types/cardHub";

const MENSAGEM_MAX = 500;

/** Digits only — what §1.1's `Signatario.cpf` expects. The dialog does not
 *  itself check mod-11; the server's 400 `ASSINATURA_SIGNATARIO_INVALIDO` is
 *  the source of truth for that, same division of labor as everywhere else
 *  in this file (client-side gates only what avoids an obviously-wasted
 *  round trip — an empty e-mail — never a rule the server would enforce
 *  differently). */
function apenasDigitos(v: string | null | undefined): string {
  return (v ?? "").replace(/\D/g, "");
}

function deParte(p: Comprador, papel: PapelSignatario): SignatarioInput {
  return {
    nome: p.cliente?.nome_completo || p.cliente?.nome || "",
    email: p.cliente?.email ?? "",
    cpf: apenasDigitos(p.cliente?.cpf),
    papel,
  };
}

function deTestemunha(t: TestemunhaSelecionada): SignatarioInput {
  return {
    // `org_testemunhas` (migration 143) now carries an e-mail column —
    // prefill it when the office has set one. A witness the office hasn't
    // e-mail'd yet still prefills EMPTY on purpose; "empty e-mail blocks
    // submit" below is what makes filling it in mandatory rather than
    // silently skippable. [Migration 168] `testemunha_id` is what the
    // server now re-resolves the authoritative e-mail/cpf FROM
    // (`assinatura_service._resolver_testemunhas_do_registro`) — a nome
    // match no longer applies.
    nome: t.nome,
    email: t.email ?? "",
    cpf: apenasDigitos(t.cpf),
    papel: "testemunha",
    testemunha_id: t.id,
  };
}

/** Exported for the container/tests: `partes` = compradores + vendedores,
 *  in that order, followed by THIS contract's selected testemunhas
 *  (migration 168 — never the whole org registry). */
export function partesParaSignatarios(
  compradores: Comprador[],
  vendedores: Comprador[],
  testemunhas: TestemunhaSelecionada[],
): SignatarioInput[] {
  return [
    ...compradores.map((p) => deParte(p, "comprador")),
    ...vendedores.map((p) => deParte(p, "vendedor")),
    ...testemunhas.map(deTestemunha),
  ];
}

export interface EnviarAssinaturaDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  compradores: Comprador[];
  vendedores: Comprador[];
  testemunhas: TestemunhaSelecionada[];
  onEnviar: (input: { signatarios: SignatarioInput[]; mensagem?: string }) => void;
  sending?: boolean;
  /** The last attempt's typed refusal, or `null` once cleared/succeeded. */
  erro?: AssinaturaError | null;
}

export function EnviarAssinaturaDialog({
  open,
  onOpenChange,
  compradores,
  vendedores,
  testemunhas,
  onEnviar,
  sending = false,
  erro = null,
}: EnviarAssinaturaDialogProps) {
  const navigate = useNavigate();
  const [signatarios, setSignatarios] = useState<SignatarioInput[]>([]);
  const [mensagem, setMensagem] = useState("");
  // Tracks the open transition so the seeding effect below fires exactly
  // once per open — see the header note.
  const jaSeedouNestaAbertura = useRef(false);

  useEffect(() => {
    if (open && !jaSeedouNestaAbertura.current) {
      jaSeedouNestaAbertura.current = true;
      setSignatarios(partesParaSignatarios(compradores, vendedores, testemunhas));
      setMensagem("");
    } else if (!open) {
      jaSeedouNestaAbertura.current = false;
    }
    // Deliberately NOT depending on compradores/vendedores/testemunhas — see
    // the header note. Seeding must fire once per open, not on every refetch.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  function mudarEmail(indice: number, email: string) {
    setSignatarios((atual) => atual.map((s, i) => (i === indice ? { ...s, email } : s)));
  }

  const emailsValidos =
    signatarios.length > 0 && signatarios.every((s) => s.email.trim().length > 0);
  const podeEnviar = emailsValidos && !sending;

  function enviar() {
    if (!podeEnviar) return;
    onEnviar({
      signatarios: signatarios.map((s) => ({ ...s, email: s.email.trim() })),
      mensagem: mensagem.trim() || undefined,
    });
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="enviar-assinatura-dialog">
        <DialogHeader>
          <DialogTitle>Enviar para assinatura</DialogTitle>
          <DialogDescription>
            Confira os e-mails de cada signatário antes de enviar — compradores,
            vendedores e as testemunhas do escritório.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          {signatarios.length === 0 && (
            <p
              className="text-xs text-muted-foreground"
              data-testid="assinatura-sem-signatarios"
            >
              Nenhuma parte ou testemunha cadastrada ainda — cadastre ao menos
              um comprador, vendedor ou testemunha antes de enviar.
            </p>
          )}
          {signatarios.map((s, i) => (
            <div
              key={`${s.papel}-${i}`}
              className="space-y-1 rounded-md border p-2"
              data-testid={`assinatura-signatario-${i}`}
            >
              <div className="flex items-center gap-1.5">
                <span className="truncate text-sm font-medium">{s.nome || "(sem nome)"}</span>
                <Badge variant="secondary" className="text-[10px]">
                  {PAPEL_SIGNATARIO_LABEL[s.papel]}
                </Badge>
              </div>
              <Input
                type="email"
                value={s.email}
                placeholder="e-mail@exemplo.com"
                onChange={(e) => mudarEmail(i, e.target.value)}
                data-testid={`assinatura-signatario-email-${i}`}
              />
            </div>
          ))}
          {signatarios.length > 0 && !emailsValidos && (
            <p className="text-xs text-destructive" data-testid="assinatura-email-obrigatorio">
              Informe o e-mail de todos os signatários para enviar.
            </p>
          )}

          <div className="space-y-1.5">
            <Label htmlFor="assinatura-mensagem">Mensagem (opcional)</Label>
            <Textarea
              id="assinatura-mensagem"
              value={mensagem}
              maxLength={MENSAGEM_MAX}
              onChange={(e) => setMensagem(e.target.value)}
              placeholder="Mensagem que acompanha o convite de assinatura"
              data-testid="assinatura-mensagem"
            />
          </div>

          {erro && (
            <div
              className="space-y-1.5 rounded-md border border-destructive/30 bg-destructive/5 p-2.5 text-xs"
              data-testid="assinatura-erro"
            >
              <p className="flex items-center gap-1.5 text-destructive">
                <AlertCircle className="h-3.5 w-3.5 shrink-0" />
                {erro.message}
              </p>
              {erro.code === "ASSINATURA_PROVEDOR_NAO_CONFIGURADO" &&
                !!erro.details?.faltando?.length && (
                  <div data-testid="assinatura-erro-faltando">
                    <ul className="ml-3 list-disc text-muted-foreground">
                      {erro.details.faltando.map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                    <Button
                      type="button"
                      variant="link"
                      className="h-auto gap-1 p-0 text-xs"
                      onClick={() => navigate("/configuracoes")}
                      data-testid="assinatura-erro-configuracoes-link"
                    >
                      Ir para Configurações
                      <ExternalLink className="h-3 w-3" />
                    </Button>
                  </div>
                )}
              {erro.code === "ASSINATURA_PROVEDOR_ERRO" && erro.details?.provedor_mensagem && (
                <p className="text-muted-foreground">{erro.details.provedor_mensagem}</p>
              )}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={sending}>
            Cancelar
          </Button>
          <Button onClick={enviar} disabled={!podeEnviar} data-testid="assinatura-enviar-btn">
            {sending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Enviar para assinatura
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

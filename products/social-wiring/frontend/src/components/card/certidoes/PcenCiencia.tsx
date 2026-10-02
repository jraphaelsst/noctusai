/**
 * The educational acknowledgment of a Receita "positiva com efeitos de
 * negativa" 2ª via (owner amendment 2026-10-01) — presentational, shared by
 * the certidões tab cell and the contract readiness screen so the operator
 * reads the SAME words in both. The backend ships the copy
 * (`contrato_gerador/certidao_pcen.py`); this renders it and offers the two
 * actions:
 *
 *  - "Entendi — seguir com esta certidão": records who/when/which validity.
 *  - "Tenho dúvida — falar com o suporte": records the question and then
 *    shows the org's configured contact (WhatsApp, else e-mail). When the org
 *    has none configured it says so and offers the message to copy — never a
 *    dead button.
 */
import { useState } from "react";
import { CheckCircle2, HelpCircle, Info, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { CienciaPcenResult, SuporteContato } from "@/types/certidoesPartes";

import { dataBr, linkDeSuporte } from "./certidoesCelula";

export interface PcenCienciaProps {
  titulo: string;
  explicacao: string[];
  validadeAte: string;
  ciente: boolean;
  acoes: { entendi: string; duvida: string };
  /** Which party/contract this is about, quoted in the support message. */
  contexto?: string;
  onEntendi: () => Promise<unknown>;
  onDuvida: () => Promise<CienciaPcenResult>;
  testId: string;
}

export function PcenCiencia(p: PcenCienciaProps) {
  const [pendente, setPendente] = useState<"entendi" | "duvida" | null>(null);
  const [duvida, setDuvida] = useState<{ suporte: SuporteContato | null } | null>(null);

  const mensagem =
    `Olá, tenho uma dúvida sobre a certidão da Receita Federal (positiva com efeitos de negativa — 2ª via, ` +
    `válida até ${dataBr(p.validadeAte)})${p.contexto ? ` — ${p.contexto}` : ""}. Posso seguir com o contrato?`;

  async function run(acao: "entendi" | "duvida") {
    setPendente(acao);
    try {
      if (acao === "entendi") await p.onEntendi();
      else setDuvida({ suporte: (await p.onDuvida()).suporte });
    } catch {
      // The mutation's own onError toast already told the operator.
    } finally {
      setPendente(null);
    }
  }

  const link = duvida ? linkDeSuporte(duvida.suporte, mensagem) : null;

  return (
    <div
      className="space-y-2 rounded-md border border-sky-300 bg-sky-50 p-2.5 text-xs dark:border-sky-800 dark:bg-sky-950/40"
      data-testid={p.testId}
    >
      <p className="flex items-center gap-1 font-medium text-sky-900 dark:text-sky-200">
        <Info className="h-3.5 w-3.5" />
        {p.titulo}
      </p>
      {p.explicacao.map((par, i) => (
        <p key={i} className="text-muted-foreground">
          {par}
        </p>
      ))}
      {p.ciente ? (
        <p className="flex items-center gap-1 font-medium text-emerald-700" data-testid={`${p.testId}-ciente`}>
          <CheckCircle2 className="h-3.5 w-3.5" />
          Ciência registrada para a validade de {dataBr(p.validadeAte)}.
        </p>
      ) : (
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            size="sm"
            disabled={pendente !== null}
            onClick={() => void run("entendi")}
            data-testid={`${p.testId}-entendi`}
          >
            {pendente === "entendi" && <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />}
            {p.acoes.entendi}
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={pendente !== null}
            onClick={() => void run("duvida")}
            data-testid={`${p.testId}-duvida`}
          >
            {pendente === "duvida" ? (
              <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
            ) : (
              <HelpCircle className="mr-1 h-3.5 w-3.5" />
            )}
            {p.acoes.duvida}
          </Button>
        </div>
      )}
      {duvida && !p.ciente && (
        <div className="space-y-1 rounded border bg-background p-2" data-testid={`${p.testId}-suporte`}>
          <p>Dúvida registrada. O contrato continua aguardando a sua ciência.</p>
          {link ? (
            <a className="font-medium text-sky-700 underline" href={link.href} target="_blank" rel="noopener noreferrer">
              {link.rotulo}
            </a>
          ) : (
            <p className="text-muted-foreground" data-testid={`${p.testId}-sem-contato`}>
              Nenhum contato de suporte está configurado para este escritório (Configurações → destinatários de
              notificação). Peça ao administrador, informando a mensagem abaixo:
            </p>
          )}
          <p className="select-all rounded bg-muted p-1.5 text-muted-foreground">{mensagem}</p>
        </div>
      )}
    </div>
  );
}

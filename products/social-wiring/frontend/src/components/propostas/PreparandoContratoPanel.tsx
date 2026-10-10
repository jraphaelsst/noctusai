/**
 * "Preparando contrato" — what happened after Aceitar (CONTRACT §7.3 +
 * addendum): the per-step result, certidões per parte, matrícula status, with
 * links to the Certidões tab and the imóvel page. A failed step carries its
 * message and a "Tentar de novo".
 */
import { AlertTriangle, CheckCircle2, MinusCircle } from "lucide-react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import {
  ACEITE_PASSO_LABELS,
  PASSOS_POS_ACEITE,
  type AceitePasso,
  type CertidaoPosAceiteStatus,
  type MatriculaPosAceiteStatus,
  type PosAceite,
} from "@/types/propostas";

const CERTIDAO_LABEL: Record<CertidaoPosAceiteStatus, string> = {
  emitindo: "Emitindo",
  ja_valida: "Já válida",
  pulada: "Dispensada",
  bloqueado: "Bloqueada",
  erro: "Erro",
};
const MATRICULA_LABEL: Record<MatriculaPosAceiteStatus, string> = {
  extraindo: "Extraindo dados",
  ok: "Extraída",
  faltando: "Matrícula não anexada",
  erro: "Erro na extração",
};

export interface PreparandoContratoPanelProps {
  imovelCodigo: string;
  passos?: AceitePasso[];
  posAceite?: PosAceite | null;
  /** Re-POST aceitar (idempotent). */
  onTentarAceiteDeNovo?: () => void;
  /** Re-run the pos-aceite endpoint. */
  onTentarPosAceiteDeNovo?: () => void;
  tentando?: boolean;
  /** The proposta is already `aceita`: failed funil/pós-aceite steps resume via pos-aceite, not aceitar. */
  aceita?: boolean;
  onAbrirCertidoes?: () => void;
  onAbrirContratos?: () => void;
}

function IconePasso({ status }: { status: AceitePasso["status"] }) {
  if (status === "ok") return <CheckCircle2 className="h-4 w-4 text-green-600" />;
  if (status === "erro") return <AlertTriangle className="h-4 w-4 text-destructive" />;
  // 'pulado' stays neutral/grey (below): not a failure of its own.
  return <MinusCircle className="h-4 w-4 text-muted-foreground" />;
}

export function PreparandoContratoPanel(p: PreparandoContratoPanelProps) {
  const passos = p.passos ?? [];
  const retomaveis = passos.filter(
    (x) => PASSOS_POS_ACEITE.includes(x.passo) && (x.status === "erro" || x.status === "pulado"),
  );
  // Accepted: only funil/pós-aceite can be retried (via pos-aceite). Not accepted: any erro → aceitar.
  const retomarPosAceite = !!p.aceita && retomaveis.length > 0;
  const refazerAceite = !p.aceita && passos.some((x) => x.status === "erro");
  const posAceiteComErro = !retomarPosAceite && !!p.posAceite && (
    p.posAceite.matricula.status === "erro" ||
    p.posAceite.certidoes.some((c) => c.status === "erro" || c.status === "bloqueado")
  );
  return (
    <div className="space-y-4" data-testid="preparando-contrato-panel">
      <h3 className="text-base font-semibold">Preparando contrato</h3>

      {p.passos && p.passos.length > 0 && (
        <ul className="space-y-1" data-testid="aceite-passos">
          {p.passos.map((x) => (
            <li key={x.passo} className="flex items-start gap-2 text-sm" data-testid={`aceite-passo-${x.passo}`}>
              <IconePasso status={x.status} />
              <div>
                <span className={x.status === "pulado" ? "text-muted-foreground" : undefined}>
                  {ACEITE_PASSO_LABELS[x.passo]}
                  {x.status === "pulado" ? " (pulado)" : ""}
                </span>
                {x.mensagem && (
                  <p
                    className={x.status === "erro" ? "text-xs text-destructive" : "text-xs text-muted-foreground"}
                    data-status={x.status}
                    role={x.status === "erro" ? "alert" : undefined}
                  >
                    {x.mensagem}
                  </p>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
      {refazerAceite && p.onTentarAceiteDeNovo && (
        <Button size="sm" variant="outline" disabled={p.tentando} onClick={p.onTentarAceiteDeNovo} data-testid="aceite-tentar-de-novo">
          Tentar de novo
        </Button>
      )}
      {retomarPosAceite && p.onTentarPosAceiteDeNovo && (
        <Button size="sm" variant="outline" disabled={p.tentando} onClick={p.onTentarPosAceiteDeNovo} data-testid="aceite-retomar-pos-aceite">
          Tentar de novo
        </Button>
      )}

      {p.posAceite && (
        <div className="space-y-3">
          <div data-testid="pos-aceite-certidoes">
            <h4 className="text-sm font-medium">Certidões dos vendedores</h4>
            {p.posAceite.certidoes.length === 0 ? (
              <p className="text-xs text-muted-foreground">Nenhuma certidão a emitir.</p>
            ) : (
              <ul className="mt-1 space-y-1">
                {p.posAceite.certidoes.map((c, i) => (
                  <li key={`${c.alvo_id}-${i}`} className="text-sm" data-testid={`pos-aceite-certidao-${i}`}>
                    <span className="font-medium">{c.parte_nome}</span>{" "}
                    <span className="text-xs text-muted-foreground">
                      {CERTIDAO_LABEL[c.status]}
                      {c.motivo ? ` · ${c.motivo}` : ""}
                      {c.tipos.length ? ` · ${c.tipos.join(", ")}` : ""}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div data-testid="pos-aceite-matricula">
            <h4 className="text-sm font-medium">Matrícula do imóvel</h4>
            <p className="text-sm">
              {MATRICULA_LABEL[p.posAceite.matricula.status]}
              {p.posAceite.matricula.motivo ? (
                <span className="text-xs text-muted-foreground"> · {p.posAceite.matricula.motivo}</span>
              ) : null}
            </p>
            {p.posAceite.matricula.status === "faltando" && (
              <p className="text-xs text-amber-700">
                Anexe a certidão de matrícula atualizada na página do imóvel; a extração roda sozinha no envio.
              </p>
            )}
          </div>
          {posAceiteComErro && p.onTentarPosAceiteDeNovo && (
            <Button size="sm" variant="outline" disabled={p.tentando} onClick={p.onTentarPosAceiteDeNovo} data-testid="pos-aceite-tentar-de-novo">
              Tentar de novo
            </Button>
          )}
        </div>
      )}

      <div className="flex flex-wrap gap-2 border-t pt-3">
        {p.onAbrirCertidoes && (
          <Button size="sm" variant="outline" onClick={p.onAbrirCertidoes} data-testid="ir-certidoes">
            Ver certidões
          </Button>
        )}
        <Button size="sm" variant="outline" asChild>
          <Link to={`/imoveis/${encodeURIComponent(p.imovelCodigo)}`} data-testid="ir-imovel">
            Página do imóvel
          </Link>
        </Button>
        {p.onAbrirContratos && (
          <Button size="sm" onClick={p.onAbrirContratos} data-testid="ir-contratos">
            Abrir contrato
          </Button>
        )}
      </div>
    </div>
  );
}

/**
 * TrocarPlanoDialog — the member's in-portal plan change (ninho-vazio
 * CONTRACT.md §Member portal, `POST /api/portal/assinatura`).
 *
 * Two steps in one dialog: (1) choose Pix or boleto and type the CPF/CNPJ;
 * (2) the answer — the Pix QR inline, or the boleto/fatura link. The public
 * `/assinar` page is NOT used here: it is the anonymous checkout, and it
 * (correctly) never opens a second subscription for an e-mail that is
 * already an active member.
 *
 * The CPF/CNPJ lives only in this component's state — never the URL, never
 * storage, never logged (product decision P1).
 */
import { useState, type FormEvent } from "react";
import { CheckCircle2, Receipt } from "lucide-react";
import { Button, Dialog, DialogBody, DialogFooter, Input } from "@noctusai/lib/design-system";

import { Field, FormError } from "@/components/FormControls";
import { LinhaDeCuidado } from "@/components/LinhaDeCuidado";
import { BOTAO_PRIMARIO } from "@/components/PortalShell";
import type { CheckoutResponse } from "@/hooks/useCheckout";
import { isCpfOuCnpj, useTrocarPlano, type PortalPlanoDisponivel, type TrocaPlanoInput } from "@/hooks/usePortal";
import { errorMessage } from "@/lib/errors";
import { NIVEL_DESCRICAO, precoPorCiclo } from "@/lib/ninhoVazio";
import { PixQrCard } from "@/pages/checkout/PixQrCard";

type Metodo = TrocaPlanoInput["metodo"];

function Resultado({ plano, resposta }: { plano: PortalPlanoDisponivel; resposta: CheckoutResponse }) {
  return (
    <div className="space-y-4 text-base" data-testid="troca-resultado">
      <p className="flex items-start gap-2 text-foreground">
        <CheckCircle2 className="mt-1 h-5 w-5 shrink-0 text-primary" aria-hidden="true" />
        {resposta.status === "checkout_em_andamento"
          ? `Você já tinha começado a troca para o ${plano.nome}. É só concluir o pagamento abaixo.`
          : `Pronto! Assim que o pagamento for confirmado, seu plano passa a ser o ${plano.nome}.`}
      </p>
      {resposta.pix_qr ? <PixQrCard pixQr={resposta.pix_qr} /> : null}
      {resposta.checkout_url ? (
        <a
          href={resposta.checkout_url}
          target="_blank"
          rel="noopener noreferrer"
          className={`${BOTAO_PRIMARIO} w-full`}
          data-testid="troca-fatura"
        >
          <Receipt className="h-5 w-5" aria-hidden="true" />
          {resposta.pix_qr ? "Abrir a fatura" : "Abrir o boleto"}
        </a>
      ) : null}
      {!resposta.pix_qr && !resposta.checkout_url ? (
        <p className="text-muted-foreground">A cobrança foi enviada para o seu e-mail.</p>
      ) : null}
      <p className="text-muted-foreground">
        Seu plano atual continua valendo até lá. Quando o novo começar, a assinatura antiga é encerrada
        automaticamente — você não paga as duas.
      </p>
    </div>
  );
}

export function TrocarPlanoDialog({
  plano,
  onClose,
}: {
  /** The tier being chosen; `null` keeps the dialog closed. */
  plano: PortalPlanoDisponivel | null;
  onClose: () => void;
}) {
  const [metodo, setMetodo] = useState<Metodo>("pix");
  const [documento, setDocumento] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [resposta, setResposta] = useState<CheckoutResponse | null>(null);
  const trocar = useTrocarPlano();

  function fechar() {
    if (trocar.isPending) return;
    setMetodo("pix");
    setDocumento("");
    setErro(null);
    setResposta(null);
    onClose();
  }

  function enviar(e: FormEvent) {
    e.preventDefault();
    if (!plano) return;
    setErro(null);
    if (!isCpfOuCnpj(documento)) {
      setErro("Informe o CPF (11 dígitos) ou o CNPJ (14 dígitos).");
      return;
    }
    trocar.mutate(
      { plano_id: plano.id, metodo, cpf_cnpj: documento.replace(/\D/g, "") },
      {
        onSuccess: (res) => setResposta(res),
        onError: (err) => setErro(errorMessage(err)),
      },
    );
  }

  return (
    <Dialog open={plano !== null} onClose={fechar} title={plano ? `Mudar para o ${plano.nome}` : "Mudar de plano"}>
      {plano && resposta ? (
        <>
          <DialogBody>
            <Resultado plano={plano} resposta={resposta} />
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" className="h-11 px-5 text-base" onClick={fechar}>
              Fechar
            </Button>
          </DialogFooter>
        </>
      ) : plano ? (
        <form onSubmit={enviar}>
          <DialogBody>
            <div className="space-y-5 text-base">
              <div>
                <h2 className="text-xl font-semibold text-foreground">Mudar para o {plano.nome}</h2>
                <p className="text-lg font-medium text-foreground">
                  {precoPorCiclo(plano.preco_centavos, plano.ciclo)}
                </p>
                <p className="text-muted-foreground">{NIVEL_DESCRICAO[plano.nivel_grupoterapia]}</p>
              </div>
              <fieldset className="space-y-2">
                <legend className="mb-1 font-medium text-foreground">Como você quer pagar?</legend>
                {(["pix", "boleto"] as const).map((m) => (
                  <label key={m} className="flex cursor-pointer items-center gap-3">
                    <input
                      type="radio"
                      name="metodo"
                      value={m}
                      checked={metodo === m}
                      onChange={() => setMetodo(m)}
                      className="h-5 w-5"
                    />
                    <span>{m === "pix" ? "Pix" : "Boleto"}</span>
                  </label>
                ))}
              </fieldset>
              <Field label="CPF ou CNPJ" required help="Só para emitir a cobrança; não fica guardado.">
                <Input
                  className="h-12 text-base"
                  value={documento}
                  onChange={(e) => setDocumento(e.target.value)}
                  inputMode="numeric"
                  autoComplete="off"
                  maxLength={18}
                  required
                />
              </Field>
              <FormError message={erro} />
              <LinhaDeCuidado className="text-sm" />
            </div>
          </DialogBody>
          <DialogFooter>
            <Button type="button" variant="outline" className="h-11 px-5 text-base" onClick={fechar} disabled={trocar.isPending}>
              Voltar
            </Button>
            <Button type="submit" variant="primary" className="h-11 px-5 text-base" disabled={trocar.isPending}>
              {trocar.isPending ? "Gerando cobrança…" : "Gerar cobrança"}
            </Button>
          </DialogFooter>
        </form>
      ) : null}
    </Dialog>
  );
}

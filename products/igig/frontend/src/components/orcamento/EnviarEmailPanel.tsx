/**
 * "Enviar por e-mail" (wave-2 contract, Slice B): the PDF goes attached, the
 * recipient defaults to the lead's e-mail. The server refuses without a
 * generated PDF (409 `pdf_nao_gerado`) or a recipient (422
 * `email_destinatario_ausente`); both refusals are shown in its own words.
 */
import { useState } from "react";
import { Mail } from "lucide-react";
import { Button, Field, FormError, Input, Textarea } from "@noctusai/lib/design-system";
import { toast } from "sonner";

import { useOrcamentoMutations } from "@/hooks/useOrcamentos";
import { describeError } from "@/lib/errors";
import type { Orcamento } from "@/types/crm";

export function EnviarEmailPanel({ orcamento, onEnviado }: { orcamento: Orcamento; onEnviado?: () => void }) {
  const { enviar } = useOrcamentoMutations();
  const [para, setPara] = useState(orcamento.lead?.email ?? "");
  const [assunto, setAssunto] = useState(`Orçamento — ${orcamento.titulo}`);
  const [mensagem, setMensagem] = useState("");
  const semPdf = !orcamento.pdf_key;

  return (
    <section className="space-y-3 rounded-xl border border-border p-4" aria-label="Enviar por e-mail">
      <h3 className="flex items-center gap-2 text-sm font-semibold text-foreground">
        <Mail className="h-4 w-4" /> Enviar por e-mail
      </h3>
      {semPdf ? (
        <p className="text-xs text-muted-foreground">Gere o PDF antes de enviar — ele vai anexado.</p>
      ) : null}
      <Field label="Para">
        <Input type="email" value={para} onChange={(e) => setPara(e.target.value)} placeholder="email@cliente.com" />
      </Field>
      <Field label="Assunto">
        <Input value={assunto} onChange={(e) => setAssunto(e.target.value)} />
      </Field>
      <Field label="Mensagem (opcional)">
        <Textarea rows={3} value={mensagem} onChange={(e) => setMensagem(e.target.value)} />
      </Field>
      <FormError message={enviar.isError ? describeError(enviar.error, "Não foi possível enviar.") : null} />
      <div className="flex justify-end">
        <Button
          disabled={semPdf || enviar.isPending}
          onClick={() =>
            enviar.mutate(
              { id: orcamento.id, para: para || undefined, assunto: assunto || undefined, mensagem: mensagem || undefined },
              {
                onSuccess: () => {
                  toast.success("Orçamento enviado por e-mail.");
                  onEnviado?.();
                },
              },
            )
          }
        >
          {enviar.isPending ? "Enviando…" : "Enviar"}
        </Button>
      </div>
    </section>
  );
}

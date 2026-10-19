/** Disparo detail: summary, targets status, send/cancel (send gated by transport). */
import { toast } from "sonner";
import { SideDrawer, useConfirm } from "@noctusai/lib/components";

import { Button } from "@/components/ui/button";
import {
  STATUS_LABEL,
  TIPO_LABEL,
  useCancelarDisparo,
  useDisparo,
  useEnviarDisparo,
  type Disparo,
} from "@/hooks/useLaisDisparos";
import {
  TRANSPORTE_EXPLICACAO,
  envioLiberado,
  mensagemErroTransporte,
  type Transporte,
} from "@/hooks/useLaisTransporte";

export function DisparoDetalheDrawer({
  disparo,
  transporte,
  onClose,
}: {
  disparo: Disparo | null;
  transporte: Transporte | undefined;
  onClose: () => void;
}) {
  const confirmar = useConfirm();
  const { data } = useDisparo(disparo?.id ?? null);
  const enviar = useEnviarDisparo();
  const cancelar = useCancelarDisparo();
  const liberado = envioLiberado(transporte);
  const d = data ?? disparo;
  const podeEnviar = d && (d.status === "rascunho" || d.status === "agendado");

  function disparar() {
    if (!d) return;
    enviar.mutate(d.id, {
      onSuccess: () => toast.success("Disparo iniciado"),
      onError: (e) => toast.error(mensagemErroTransporte(e, "Não foi possível enviar o disparo.")),
    });
  }
  async function cancelarDisparo() {
    if (!d) return;
    if (!(await confirmar({ title: "Cancelar disparo?", confirmLabel: "Cancelar disparo", tone: "danger" }))) return;
    cancelar.mutate(d.id, {
      onSuccess: () => {
        toast.success("Disparo cancelado");
        onClose();
      },
      onError: (e) => toast.error(mensagemErroTransporte(e, "Não foi possível cancelar o disparo.")),
    });
  }

  return (
    <SideDrawer open={!!disparo} onOpenChange={(o) => !o && onClose()} title={d?.nome ?? "Disparo"} description="Detalhes do disparo" testId="disparo-detalhe">
      {d && (
        <div className="mt-4 space-y-4 text-sm">
          <dl className="grid grid-cols-2 gap-2">
            <dt className="text-muted-foreground">Status</dt>
            <dd>{STATUS_LABEL[d.status]}</dd>
            <dt className="text-muted-foreground">Tipo</dt>
            <dd>{TIPO_LABEL[d.tipo]}</dd>
            <dt className="text-muted-foreground">Contatos</dt>
            <dd>{d.contatos}</dd>
          </dl>
          <div>
            <p className="mb-1 font-medium">Contatos do disparo</p>
            {data?.alvos?.length ? (
              <ul className="divide-y rounded border" data-testid="disparo-alvos">
                {data.alvos.map((a) => (
                  <li key={a.id} className="flex justify-between px-2 py-1">
                    <span>{a.nome}</span>
                    <span className="text-muted-foreground">{a.status}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-muted-foreground">Nenhum contato registrado ainda.</p>
            )}
          </div>
          {podeEnviar && (
            <div className="space-y-2">
              <div className="flex gap-2">
                <Button onClick={disparar} disabled={!liberado || enviar.isPending}>
                  Enviar agora
                </Button>
                <Button variant="outline" onClick={cancelarDisparo} disabled={cancelar.isPending}>
                  Cancelar disparo
                </Button>
              </div>
              {!liberado && <p className="text-xs text-muted-foreground">{TRANSPORTE_EXPLICACAO}</p>}
            </div>
          )}
        </div>
      )}
    </SideDrawer>
  );
}

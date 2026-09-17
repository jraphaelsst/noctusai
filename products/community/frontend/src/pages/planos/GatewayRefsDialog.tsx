/**
 * GatewayRefsDialog — per-plano gateway cross-reference editor
 * (community-m2-contract.md §Frontend: "/planos … per-tier gateway
 * reference fields (Stripe Price id, Asaas ref) in the edit dialog, with a
 * clear 'not yet available for card / Pix' badge when a ref is missing").
 *
 * Co-located with `Planos.tsx` (module 1's page, EXTENDED via a per-row
 * action rather than rewritten — the same technique the page already uses
 * for "Reativar"). `<ResourceManager/>`'s create/edit form has no seam for
 * a nested sub-resource on a DIFFERENT endpoint
 * (`/api/planos/{id}/gateway-refs/{gateway}`, upsert PUT / DELETE) — so
 * this is a standalone dialog opened from a `rowActions` button, exactly
 * like `Membros.tsx`'s `StatusChangeDialog`.
 */
import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { Badge, Button, Dialog, DialogHeader, DialogBody, DialogFooter, Input } from "@noctusai/lib/design-system";
import { Field, FormError } from "@/components/FormControls";
import { errorMessage } from "@/lib/errors";
import {
  useGatewayRefs,
  useSetGatewayRef,
  useDeleteGatewayRef,
  type Gateway,
} from "@/hooks/useGatewayRefs";

const GATEWAY_LABELS: Record<Gateway, string> = {
  stripe: "Stripe (cartão)",
  asaas: "Asaas (Pix / boleto)",
};

export function GatewayRefsBadges({ planoId }: { planoId: string }) {
  const { data } = useGatewayRefs(planoId);
  const byGateway = new Map((data?.items ?? []).map((r) => [r.gateway, r]));
  return (
    <div className="flex flex-wrap gap-1">
      {(Object.keys(GATEWAY_LABELS) as Gateway[]).map((g) => (
        <Badge key={g} variant={byGateway.has(g) ? "default" : "outline"}>
          {byGateway.has(g) ? GATEWAY_LABELS[g] : `${GATEWAY_LABELS[g]} — não disponível`}
        </Badge>
      ))}
    </div>
  );
}

export function GatewayRefsDialog({ planoId, planoNome, onClose }: { planoId: string; planoNome: string; onClose: () => void }) {
  const { data, isPending, error } = useGatewayRefs(planoId);
  const setRef = useSetGatewayRef(planoId);
  const deleteRef = useDeleteGatewayRef(planoId);
  const [drafts, setDrafts] = useState<Record<Gateway, string>>({ stripe: "", asaas: "" });
  const [formError, setFormError] = useState<string | null>(null);

  const byGateway = new Map((data?.items ?? []).map((r) => [r.gateway, r]));

  function draftFor(gateway: Gateway): string {
    if (drafts[gateway]) return drafts[gateway];
    return byGateway.get(gateway)?.ref_externo ?? "";
  }

  function handleSave(gateway: Gateway) {
    return (e: FormEvent) => {
      e.preventDefault();
      setFormError(null);
      const ref_externo = draftFor(gateway).trim();
      if (!ref_externo) {
        setFormError("Informe a referência do gateway antes de salvar.");
        return;
      }
      setRef.mutate(
        { gateway, ref_externo },
        {
          onSuccess: () => toast.success(`Referência de ${GATEWAY_LABELS[gateway]} salva.`),
          onError: (err) => setFormError(errorMessage(err)),
        },
      );
    };
  }

  function handleRemove(gateway: Gateway) {
    deleteRef.mutate(gateway, {
      onSuccess: () => {
        toast.success(`Referência de ${GATEWAY_LABELS[gateway]} removida.`);
        setDrafts((d) => ({ ...d, [gateway]: "" }));
      },
      onError: (err) => toast.error("Erro ao remover referência", { description: errorMessage(err) }),
    });
  }

  return (
    <Dialog open onClose={onClose} title={`Gateways — ${planoNome}`} className="max-w-lg">
      <DialogHeader>
        <h2 className="text-lg font-semibold text-foreground">Gateways de pagamento — {planoNome}</h2>
      </DialogHeader>
      <DialogBody className="space-y-4">
        <FormError message={formError || (error ? errorMessage(error) : null)} />
        {isPending ? (
          <p className="text-sm text-muted-foreground">Carregando...</p>
        ) : (
          (Object.keys(GATEWAY_LABELS) as Gateway[]).map((gateway) => (
            <form key={gateway} onSubmit={handleSave(gateway)} className="space-y-2 border-b border-border pb-3 last:border-0">
              <Field
                label={GATEWAY_LABELS[gateway]}
                help={gateway === "stripe" ? "Ex: price_1AbCdEfGh" : "Ex: o id do plano no Asaas"}
              >
                <Input
                  value={draftFor(gateway)}
                  onChange={(e) => setDrafts((d) => ({ ...d, [gateway]: e.target.value }))}
                  placeholder="Referência externa"
                />
              </Field>
              <div className="flex justify-end gap-2">
                {byGateway.has(gateway) && (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={deleteRef.isPending}
                    onClick={() => handleRemove(gateway)}
                  >
                    Remover
                  </Button>
                )}
                <Button type="submit" variant="primary" size="sm" disabled={setRef.isPending}>
                  {setRef.isPending ? "Salvando..." : "Salvar"}
                </Button>
              </div>
            </form>
          ))
        )}
      </DialogBody>
      <DialogFooter>
        <Button type="button" variant="outline" onClick={onClose}>
          Fechar
        </Button>
      </DialogFooter>
    </Dialog>
  );
}

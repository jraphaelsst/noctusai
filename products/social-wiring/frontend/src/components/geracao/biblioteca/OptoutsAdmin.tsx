/**
 * "Pedidos de exclusão (opt-out)" — platform-admin panel (spec biblioteca-lia §5).
 * Registering an opt-out purges the handle's data in EVERY org immediately and
 * blocks future monitoring, so both add and remove go through a confirm dialog.
 * Renders nothing for non-admins (the server enforces 403 regardless).
 */
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { ConfirmarModal } from "@/components/pesquisa/ConfirmarModal";
import { dataPtBr } from "@/components/pesquisa/format";
import {
  useOptoutsAdmin,
  useRegistrarOptout,
  useRemoverOptout,
  type OptoutOrigem,
  type PerfilOptout,
} from "@/hooks/geracao/useBiblioteca";
import { useTreinamentosAdmin } from "@/hooks/geracao/useTreinamentos";

export const ORIGEM_ROTULO: Record<OptoutOrigem, string> = {
  email: "E-mail",
  dpo: "DPO",
  admin: "Admin",
};

const msg = (e: unknown, fallback: string) =>
  e instanceof Error && e.message ? e.message : fallback;

export function OptoutsAdmin() {
  const adminQ = useTreinamentosAdmin();
  const isAdmin = adminQ.data === true;
  const listaQ = useOptoutsAdmin(isAdmin);
  const registrar = useRegistrarOptout();
  const remover = useRemoverOptout();

  const [handle, setHandle] = useState("");
  const [origem, setOrigem] = useState<OptoutOrigem>("email");
  const [motivo, setMotivo] = useState("");
  const [confirmarAdd, setConfirmarAdd] = useState(false);
  const [alvoRemover, setAlvoRemover] = useState<PerfilOptout | null>(null);

  if (!isAdmin) return null;
  const itens = listaQ.data ?? [];

  async function confirmarRegistro() {
    try {
      const r = await registrar.mutateAsync({
        handle: handle.trim(),
        origem,
        ...(motivo.trim() ? { motivo: motivo.trim() } : {}),
      });
      toast.success(
        `${r.criado ? "Opt-out registrado" : "Opt-out já existia"}. Apagados: ${r.purgados.perfis} perfil(is), ${r.purgados.virais} viral(is).`,
      );
      setHandle("");
      setMotivo("");
    } catch (e) {
      toast.error(msg(e, "Não foi possível registrar o opt-out."));
    } finally {
      setConfirmarAdd(false);
    }
  }

  async function confirmarRemocao() {
    if (!alvoRemover) return;
    try {
      await remover.mutateAsync(alvoRemover.id);
      toast.success("Opt-out removido.");
    } catch (e) {
      toast.error(msg(e, "Não foi possível remover o opt-out."));
    } finally {
      setAlvoRemover(null);
    }
  }

  return (
    <section className="flex flex-col gap-3" data-testid="optouts-admin">
      <h2 className="text-lg font-semibold">Pedidos de exclusão (opt-out)</h2>

      <form
        className="grid max-w-2xl gap-3 sm:grid-cols-[1fr_10rem]"
        onSubmit={(e) => {
          e.preventDefault();
          if (handle.trim()) setConfirmarAdd(true);
        }}
      >
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="oo-handle">Perfil (@handle ou URL)</Label>
          <Input
            id="oo-handle"
            placeholder="@perfil"
            value={handle}
            onChange={(e) => setHandle(e.target.value)}
            autoComplete="off"
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="oo-origem">Origem</Label>
          <select
            id="oo-origem"
            className="h-9 rounded-md border border-input bg-background px-3 text-sm"
            value={origem}
            onChange={(e) => setOrigem(e.target.value as OptoutOrigem)}
          >
            {(Object.keys(ORIGEM_ROTULO) as OptoutOrigem[]).map((o) => (
              <option key={o} value={o}>
                {ORIGEM_ROTULO[o]}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1.5 sm:col-span-2">
          <Label htmlFor="oo-motivo">Motivo</Label>
          <Input id="oo-motivo" value={motivo} onChange={(e) => setMotivo(e.target.value)} />
        </div>
        <Button
          type="submit"
          variant="destructive"
          className="w-fit"
          disabled={!handle.trim() || registrar.isPending}
        >
          {registrar.isPending ? "Registrando..." : "Registrar opt-out"}
        </Button>
      </form>

      {listaQ.showSkeleton ? (
        <Skeleton className="h-16 w-full max-w-2xl" />
      ) : listaQ.isError ? (
        <p className="text-sm text-destructive">Não foi possível carregar os pedidos de exclusão.</p>
      ) : itens.length === 0 ? (
        <p className="text-sm text-muted-foreground">Nenhum pedido de exclusão registrado.</p>
      ) : (
        <div className={listaQ.isRefreshing ? "overflow-x-auto opacity-70" : "overflow-x-auto"}>
          <table className="w-full max-w-3xl text-sm">
            <thead className="text-left text-muted-foreground">
              <tr>
                <th className="py-1 pr-3">Perfil</th>
                <th className="py-1 pr-3">Origem</th>
                <th className="py-1 pr-3">Motivo</th>
                <th className="py-1 pr-3">Solicitado em</th>
                <th className="py-1" />
              </tr>
            </thead>
            <tbody>
              {itens.map((o) => (
                <tr key={o.id} className="border-t">
                  <td className="py-1.5 pr-3 font-medium">@{o.handle}</td>
                  <td className="py-1.5 pr-3">{ORIGEM_ROTULO[o.origem] ?? o.origem}</td>
                  <td className="py-1.5 pr-3">{o.motivo ?? "—"}</td>
                  <td className="py-1.5 pr-3">{dataPtBr(o.solicitado_em ?? o.created_at)}</td>
                  <td className="py-1.5 text-right">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      aria-label={`Remover opt-out de @${o.handle}`}
                      onClick={() => setAlvoRemover(o)}
                    >
                      Remover
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <ConfirmarModal
        open={confirmarAdd}
        onOpenChange={setConfirmarAdd}
        titulo="Registrar opt-out"
        descricao="Isto apaga AGORA todos os dados deste perfil em todas as organizações e impede novo monitoramento."
        rotuloConfirmar="Apagar e registrar"
        onConfirmar={() => void confirmarRegistro()}
        pendente={registrar.isPending}
      />
      <ConfirmarModal
        open={!!alvoRemover}
        onOpenChange={(o) => !o && setAlvoRemover(null)}
        titulo="Remover opt-out"
        descricao={`Remover o opt-out de @${alvoRemover?.handle ?? ""} permite que o perfil volte a ser monitorado. Os dados já apagados não são restaurados.`}
        rotuloConfirmar="Remover opt-out"
        onConfirmar={() => void confirmarRemocao()}
        pendente={remover.isPending}
      />
    </section>
  );
}

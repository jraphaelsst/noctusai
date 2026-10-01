/**
 * PlanoGruposDialog — maps a plano to WhatsApp groups
 * (`entitlements.grupos_whatsapp`, a list of grupo ids). Without this the
 * WhatsApp sync "adicionar" batches are always empty and "remover" proposes
 * removing everyone. Merges into the existing entitlements so unknown keys
 * are never wiped.
 */
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@noctusai/lib/design-system";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/errors";
import { useGruposWhatsApp } from "@/hooks/useGruposWhatsApp";
import type { Plano } from "@/hooks/usePlanos";

export function PlanoGruposDialog({
  plano,
  onClose,
  onSaved,
}: {
  plano: Plano;
  onClose: () => void;
  onSaved: () => void;
}) {
  const grupos = useGruposWhatsApp({ page_size: 100 });
  const [selected, setSelected] = useState<string[]>(plano.entitlements?.grupos_whatsapp ?? []);
  const [saving, setSaving] = useState(false);
  const items = grupos.data?.items ?? [];

  function toggle(id: string) {
    setSelected((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]));
  }

  async function save() {
    setSaving(true);
    try {
      await api.patch(`/api/planos/${plano.id}`, {
        entitlements: { ...(plano.entitlements ?? {}), grupos_whatsapp: selected },
      });
      toast.success("Grupos do plano salvos");
      onSaved();
    } catch (err) {
      toast.error("Erro ao salvar grupos", { description: errorMessage(err) });
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" role="dialog" aria-label="Grupos WhatsApp do plano">
      <div className="w-full max-w-md rounded-lg border border-border bg-card p-6 space-y-4">
        <h2 className="text-lg font-semibold text-foreground">Grupos WhatsApp — {plano.nome}</h2>
        {grupos.isPending && !grupos.data ? (
          <p className="text-sm text-muted-foreground" role="status">Carregando grupos...</p>
        ) : grupos.error ? (
          <p className="text-sm text-danger">Erro ao carregar grupos.</p>
        ) : items.length === 0 ? (
          <p className="text-sm text-muted-foreground" data-testid="planos-grupos-vazio">
            Nenhum grupo WhatsApp cadastrado. Registre um grupo em WhatsApp para vinculá-lo ao plano.
          </p>
        ) : (
          <ul className="space-y-2 max-h-72 overflow-auto">
            {items.map((g) => (
              <li key={g.id}>
                <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer">
                  <input
                    type="checkbox"
                    className="rounded border-border"
                    checked={selected.includes(g.id)}
                    onChange={() => toggle(g.id)}
                  />
                  {g.nome || g.chat_id}
                </label>
              </li>
            ))}
          </ul>
        )}
        <div className="flex justify-end gap-2">
          <Button variant="outline" size="sm" onClick={onClose}>Cancelar</Button>
          <Button variant="primary" size="sm" onClick={() => void save()} disabled={saving || grupos.isPending}>
            {saving ? "Salvando..." : "Salvar"}
          </Button>
        </div>
      </div>
    </div>
  );
}

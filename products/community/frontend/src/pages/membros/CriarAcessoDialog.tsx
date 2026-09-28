/**
 * "Criar acesso" — provisions a member's login (CONTRACT.md ninho-vazio
 * §Identity, `POST /api/membros/{id}/acesso`, admin).
 *
 * The temporary password is shown exactly once. It lives only in this
 * component's state (and the mutation, which is configured `gcTime: 0`), is
 * never written to storage, a query cache entry or a log, and is gone the
 * moment the dialog closes.
 */
import { useState } from "react";
import { toast } from "sonner";
import { Button, Dialog, DialogBody, DialogFooter, DialogHeader } from "@noctusai/lib/design-system";
import { FormError } from "@/components/FormControls";
import { errorMessage } from "@/lib/errors";
import { useCriarAcesso, type CriarAcessoResponse } from "@/hooks/useMembroEventos";
import type { Membro } from "@/hooks/useMembros";

export function CriarAcessoDialog({ membro, onClose }: { membro: Membro; onClose: () => void }) {
  const criar = useCriarAcesso();
  const [credenciais, setCredenciais] = useState<CriarAcessoResponse | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [copiado, setCopiado] = useState(false);

  async function handleCriar() {
    setFormError(null);
    try {
      const res = await criar.mutateAsync(membro.id);
      setCredenciais(res);
      criar.reset();
    } catch (err) {
      setFormError(errorMessage(err));
    }
  }

  async function handleCopiar() {
    if (!credenciais) return;
    try {
      await navigator.clipboard.writeText(credenciais.senha_temporaria);
      setCopiado(true);
      toast.success("Senha copiada.");
    } catch {
      toast.error("Não foi possível copiar. Selecione a senha e copie manualmente.");
    }
  }

  function handleClose() {
    setCredenciais(null);
    onClose();
  }

  return (
    <Dialog open onClose={handleClose} title="Criar acesso" className="max-w-md">
      <DialogHeader>
        <h2 className="text-lg font-semibold text-foreground">Criar acesso para {membro.nome}</h2>
      </DialogHeader>
      <DialogBody className="space-y-3">
        <FormError message={formError} />
        {credenciais ? (
          <div className="space-y-3" data-testid="criar-acesso-credenciais">
            <p className="text-sm text-foreground">
              Login criado. Envie estes dados para ela por um canal seguro — ela pode trocar a senha depois.
            </p>
            <dl className="space-y-2 text-sm">
              <div>
                <dt className="text-xs uppercase tracking-wide text-muted-foreground">E-mail</dt>
                <dd className="text-foreground">{credenciais.email}</dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-muted-foreground">Senha temporária</dt>
                <dd className="flex items-center gap-2">
                  <code className="rounded bg-muted px-2 py-1 font-mono text-foreground" data-testid="senha-temporaria">
                    {credenciais.senha_temporaria}
                  </code>
                  <Button type="button" size="sm" variant="outline" onClick={() => void handleCopiar()}>
                    {copiado ? "Copiada" : "Copiar"}
                  </Button>
                </dd>
              </div>
            </dl>
            <p role="note" className="rounded-md border border-border bg-muted/40 p-2 text-xs text-muted-foreground">
              Esta senha aparece só agora. Ao fechar, ela não poderá ser vista de novo.
            </p>
          </div>
        ) : (
          <p className="text-sm text-foreground">
            Criar um login para <strong>{membro.email}</strong>? Uma senha temporária será gerada e mostrada uma única
            vez.
          </p>
        )}
      </DialogBody>
      <DialogFooter>
        {credenciais ? (
          <Button type="button" variant="primary" onClick={handleClose}>
            Concluir
          </Button>
        ) : (
          <>
            <Button type="button" variant="outline" onClick={handleClose} disabled={criar.isPending}>
              Cancelar
            </Button>
            <Button
              type="button"
              variant="primary"
              onClick={() => void handleCriar()}
              disabled={criar.isPending}
              data-testid="criar-acesso-confirmar"
            >
              {criar.isPending ? "Criando..." : "Criar acesso"}
            </Button>
          </>
        )}
      </DialogFooter>
    </Dialog>
  );
}

/**
 * Shared chrome of the Julia v2 content tabs: which version is on screen (draft = editable,
 * published = read-only), the optimistic-lock conflict banner, and the standard save error block.
 */
import { FilePlus2 } from "lucide-react";
import { toast } from "sonner";
import { Badge, Button } from "@noctusai/lib/design-system";
import { useAgentVersionRefs, useCreateDraft } from "@/hooks/studio/useVersions";
import { errorMessage } from "@/lib/errors";

export function useContentTarget(agentKey: string) {
  const refs = useAgentVersionRefs(agentKey);
  const target = refs.draft ?? refs.ativa;
  return { refs, target, isDraft: !!refs.draft, versionId: target?.id ?? null };
}

export function VersionBar({ agentKey, rotulo }: { agentKey: string; rotulo?: string }) {
  const { refs, target, isDraft } = useContentTarget(agentKey);
  const createDraft = useCreateDraft(agentKey);

  async function handleCreate() {
    try {
      const d = await createDraft.mutateAsync();
      toast.success(`Rascunho v${d.versao} criado.`);
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  if (!target) return null;
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-lg border border-border bg-card px-3 py-2" data-testid="conteudo-versao-bar">
      {rotulo && <span className="text-sm font-medium">{rotulo}</span>}
      {isDraft ? (
        <>
          <Badge variant="default" data-testid="conteudo-estado">Rascunho v{target.versao} · editável</Badge>
          {refs.ativa && <span className="text-xs text-muted-foreground">Publicada em uso: v{refs.ativa.versao}. Mudanças só valem após publicar.</span>}
        </>
      ) : (
        <>
          <Badge variant="muted" data-testid="conteudo-estado">Publicada v{target.versao} · somente leitura</Badge>
          <Button size="sm" variant="outline" onClick={handleCreate} disabled={createDraft.isPending} data-testid="conteudo-criar-rascunho">
            <FilePlus2 className="mr-1 h-4 w-4" /> {createDraft.isPending ? "Criando..." : `Criar rascunho a partir da v${target.versao}`}
          </Button>
        </>
      )}
    </div>
  );
}

export function ConflictBanner({ onReload }: { onReload: () => void }) {
  return (
    <div
      className="flex flex-wrap items-center gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-700"
      role="alert"
      data-testid="conteudo-conflito"
    >
      <span>O rascunho mudou no servidor enquanto você editava. Suas alterações não foram salvas.</span>
      <Button size="sm" variant="outline" onClick={onReload}>
        Descartar as minhas e recarregar
      </Button>
    </div>
  );
}

export function SaveError({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <p className="rounded-md border border-destructive/40 bg-destructive/10 p-2 text-sm text-destructive" role="alert" data-testid="conteudo-erro">
      {message}
    </p>
  );
}

export function RestrictedNotice({ error }: { error: unknown }) {
  const status = (error as { status?: number | null } | null)?.status;
  return (
    <div className="rounded-lg border border-dashed border-border bg-card p-6 text-sm text-muted-foreground" role="alert" data-testid="studio-restrito">
      {status === 403 ? "Restrito a administradores da plataforma NoctusAI." : errorMessage(error)}
    </div>
  );
}

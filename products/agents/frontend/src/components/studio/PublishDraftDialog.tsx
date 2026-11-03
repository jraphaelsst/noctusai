/**
 * Publish-the-draft dialog (blocking compile warnings + eval gate + exception reason). Shared by the
 * Versões tab and the content tabs' draft header (`PublishDraftButton`): the draft version carries
 * prompt, decisions, tools, texts and skills, so ONE publish ships them all.
 */
import { useState } from "react";
import { AlertTriangle, Rocket, Send } from "lucide-react";
import { toast } from "sonner";
import { Button, Dialog, DialogBody, DialogFooter, DialogHeader } from "@noctusai/lib/design-system";
import { OVERRIDE_REASON_MIN, type CompileWarning, type PublishErrorBody, type VersionSummary } from "@/api/studio/types";
import { PromptMarkdownField } from "@/components/studio/PromptMarkdownField";
import { shortHash } from "@/components/studio/compiledSegments";
import { useCompiled } from "@/hooks/studio/useCompiled";
import { useAgentVersionRefs, usePublishDraft } from "@/hooks/studio/useVersions";
import { useIsAdmin } from "@/hooks/useIsAdmin";
import { ApiError, errorMessage } from "@/lib/errors";

export const pct = (n: number | null | undefined) => (n === null || n === undefined ? "—" : `${Math.round(n * 1000) / 10}%`);

export function PublishDraftDialog({
  agentKey,
  draft,
  limiar,
  onClose,
}: {
  agentKey: string;
  draft: VersionSummary;
  limiar: number;
  onClose: () => void;
}) {
  const compiled = useCompiled(agentKey, draft.id);
  const publish = usePublishDraft(agentKey);
  const [notas, setNotas] = useState(draft.notas ?? "");
  const [override, setOverride] = useState("");
  const [serverGate, setServerGate] = useState<PublishErrorBody | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  const hashAtual = compiled.data?.hash ?? draft.compiled_hash;
  const bloqueantes: CompileWarning[] = [
    ...(compiled.data?.avisos.filter((a) => a.bloqueante) ?? []),
    ...(serverGate?.code === "compile_blocked" ? (serverGate.avisos ?? []).filter((a) => a.bloqueante) : []),
  ];
  const avisos = compiled.data?.avisos.filter((a) => !a.bloqueante) ?? [];
  const preCheckFails = draft.eval_score === null || draft.eval_score < limiar;
  const gateFails = preCheckFails || serverGate?.code === "eval_required";
  const ultima = serverGate?.ultima_execucao;

  async function handlePublish() {
    setErro(null);
    const reason = override.trim();
    if (gateFails && reason && reason.length < OVERRIDE_REASON_MIN) {
      setErro(`A justificativa precisa de pelo menos ${OVERRIDE_REASON_MIN} caracteres.`);
      return;
    }
    try {
      const published = await publish.mutateAsync({
        notas: notas.trim() || undefined,
        override_reason: gateFails && reason ? reason : undefined,
      });
      toast.success(`Versão v${published.versao} publicada.`);
      onClose();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409 && err.body && typeof err.body === "object") {
        const body = err.body as PublishErrorBody;
        if (body.code === "eval_required" || body.code === "compile_blocked") setServerGate(body);
        if (body.code === "draft_changed") {
          // The draft's hash moved between the gating eval run and this
          // publish call — the server refuses rather than gate a stale
          // hash. Recompile so "Hash atual" (and the gate check above it)
          // reflects the draft NOW, and let the admin retry from there.
          setErro("O rascunho mudou desde a última compilação — recompile e tente de novo.");
          void compiled.refetch();
          return;
        }
      }
      setErro(errorMessage(err));
    }
  }

  return (
    <Dialog open onClose={onClose} title="Publicar rascunho" className="max-w-xl">
      <DialogHeader>
        <h2 className="text-base font-semibold">Publicar rascunho v{draft.versao}</h2>
      </DialogHeader>
      <DialogBody className="space-y-4" data-testid="publish-dialog">
        <div className="rounded-md border border-border p-3 text-sm" data-testid="publish-gate">
          <p className="font-medium">Portão de avaliação</p>
          <p className="text-xs text-muted-foreground">
            Hash atual: <span className="font-mono">{compiled.showSkeleton ? "compilando…" : shortHash(hashAtual, 16)}</span>
          </p>
          <p className="mt-1">
            Última avaliação: <strong>{pct(ultima ? ultima.score : draft.eval_score)}</strong> · limiar{" "}
            <strong>{pct(ultima ? ultima.limiar : limiar)}</strong>
          </p>
          {ultima && ultima.compiled_hash !== (serverGate?.hash_atual ?? hashAtual) && (
            <p className="text-xs text-amber-700">
              A última avaliação foi feita em outro hash ({shortHash(ultima.compiled_hash)}) — o rascunho mudou desde então.
            </p>
          )}
          {serverGate?.code === "eval_required" && !ultima && (
            <p className="text-xs text-amber-700">Nenhuma avaliação concluída para este rascunho.</p>
          )}
          <p className={`mt-1 text-xs ${gateFails ? "text-amber-700" : "text-emerald-600"}`}>
            {gateFails
              ? "O portão não está satisfeito: rode uma avaliação na aba Avaliações ou registre uma justificativa de exceção."
              : "Avaliação acima do limiar — o servidor confirma no hash atual ao publicar."}
          </p>
        </div>

        {compiled.isError && (
          <p className="text-xs text-destructive">Não foi possível compilar o rascunho: {errorMessage(compiled.error)}</p>
        )}
        {bloqueantes.length > 0 && (
          <div className="rounded-md border border-destructive/50 bg-destructive/5 p-3" role="alert" data-testid="publish-bloqueantes">
            <p className="flex items-center gap-1 text-sm font-medium text-destructive">
              <AlertTriangle className="h-4 w-4" /> Avisos bloqueantes — corrija antes de publicar (sem exceção possível):
            </p>
            <ul className="ml-5 list-disc text-xs">
              {bloqueantes.map((a, i) => (
                <li key={`${a.codigo}-${i}`}>{a.mensagem}</li>
              ))}
            </ul>
          </div>
        )}
        {avisos.length > 0 && (
          <ul className="ml-5 list-disc text-xs text-amber-700">
            {avisos.map((a, i) => (
              <li key={`${a.codigo}-${i}`}>{a.mensagem}</li>
            ))}
          </ul>
        )}

        <div>
          <label htmlFor="publish-notas" className="mb-1 block text-xs font-medium">
            Notas da versão
          </label>
          <PromptMarkdownField id="publish-notas" value={notas} onChange={setNotas} rows={3} mono={false} semTokens />
        </div>

        {/* A failed compile is not "no blocking warnings" (silent-refusal). */}
        {gateFails && !compiled.isError && bloqueantes.length === 0 && (
          <div data-testid="publish-override">
            <label htmlFor="publish-override-reason" className="mb-1 block text-xs font-medium">
              Justificativa de exceção (mínimo {OVERRIDE_REASON_MIN} caracteres — fica registrada na versão)
            </label>
            <PromptMarkdownField
              id="publish-override-reason"
              value={override}
              onChange={setOverride}
              rows={3}
              mono={false}
              semTokens
            />
          </div>
        )}

        {erro && (
          <p className="text-sm text-destructive" role="alert" data-testid="publish-erro">
            {erro}
          </p>
        )}
      </DialogBody>
      <DialogFooter className="gap-2">
        <Button variant="ghost" onClick={onClose}>
          Cancelar
        </Button>
        <Button
          variant="primary"
          onClick={handlePublish}
          disabled={
            publish.isPending ||
            bloqueantes.length > 0 ||
            // The client-side pre-check only hints (the server re-checks the
            // gate on the CURRENT hash); an override is mandatory once the
            // server itself has answered `eval_required`.
            (serverGate?.code === "eval_required" && override.trim().length < OVERRIDE_REASON_MIN)
          }
          data-testid="publish-confirm"
        >
          <Rocket className="mr-1 h-4 w-4" />
          {publish.isPending ? "Publicando..." : gateFails && override.trim() ? "Publicar com exceção" : "Publicar"}
        </Button>
      </DialogFooter>
    </Dialog>
  );
}

/** "Publicar rascunho" for the content tabs: admin-only (as in Versões), disabled while the tab has unsaved edits. */
export function PublishDraftButton({ agentKey, dirty = false }: { agentKey: string; dirty?: boolean }) {
  const isAdmin = useIsAdmin();
  const { data: agent, draft } = useAgentVersionRefs(agentKey);
  const [open, setOpen] = useState(false);
  if (!isAdmin || !draft || !agent) return null;
  return (
    <>
      <span className="ml-auto flex flex-wrap items-center gap-2">
        <span className="text-xs text-muted-foreground">Publica a versão inteira do agente (prompt, decisões, ferramentas…)</span>
        <Button
          size="sm"
          variant="primary"
          onClick={() => setOpen(true)}
          disabled={dirty}
          title={dirty ? "Salve as alterações antes de publicar" : undefined}
          data-testid="conteudo-publicar"
        >
          <Send className="mr-1 h-4 w-4" /> Publicar rascunho
        </Button>
        {dirty && (
          <span className="text-xs text-amber-700" data-testid="conteudo-publicar-dirty">
            Salve as alterações antes de publicar
          </span>
        )}
      </span>
      {open && <PublishDraftDialog agentKey={agentKey} draft={draft} limiar={agent.publicacao_limiar} onClose={() => setOpen(false)} />}
    </>
  );
}

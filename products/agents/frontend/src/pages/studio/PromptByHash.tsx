/**
 * Agent Studio — `/studio/prompts/:hash` (CONTRACT §G, §A7 "proof of use"):
 * the exact, write-once text a turn ran with, reached from a message's
 * "prompt usado" link. Rendered with the same block view as the inspector.
 * The stored record carries no agent key, so blocks are not click-through
 * here — the inspector tab is where sources are edited.
 */
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Fingerprint } from "lucide-react";
import { Badge } from "@noctusai/lib/design-system";
import { CompiledPromptView } from "@/components/studio/CompiledPromptView";
import { CopyTextButton } from "@/components/studio/CopyTextButton";
import { SectionTokenBar } from "@/components/studio/SectionTokenBar";
import { StudioError, StudioLoading } from "@/components/studio/StudioStates";
import { usePromptByHash } from "@/hooks/studio/useCompiled";
import { ApiError } from "@/lib/errors";
import { formatDate } from "@/lib/utils";

export default function PromptByHash() {
  const { hash = "" } = useParams<{ hash: string }>();
  const { data, showSkeleton, isError, error, refetch } = usePromptByHash(hash);

  const notFound = error instanceof ApiError && error.status === 404;
  const tokens = data ? data.manifest.reduce((acc, s) => acc + s.tokens, 0) : 0;

  return (
    <div className="space-y-4">
      <Link to="/studio" className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
        <ArrowLeft className="h-3.5 w-3.5" /> Agent Studio
      </Link>
      <div className="flex items-center gap-3">
        <Fingerprint className="h-6 w-6 text-primary" />
        <div className="min-w-0">
          <h1 className="text-2xl font-bold text-foreground">Prompt usado</h1>
          <p className="break-all font-mono text-xs text-muted-foreground" data-testid="prompt-hash">
            {hash}
          </p>
        </div>
        {data && (
          <div className="ml-auto">
            <CopyTextButton text={data.texto} label="Copiar prompt" />
          </div>
        )}
      </div>

      {showSkeleton ? (
        <StudioLoading rows={5} testId="prompt-hash-skeleton" />
      ) : isError ? (
        <StudioError
          error={error}
          mensagem={notFound ? "Nenhum prompt registrado com este hash nesta organização." : undefined}
          onRetry={notFound ? undefined : refetch}
        />
      ) : data ? (
        <>
          <div className="space-y-3 rounded-lg border border-border bg-card p-4">
            <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
              <span>Registrado em {formatDate(data.created_at, true)}</span>
              <span>
                Versão <span className="font-mono">{data.version_id}</span>
              </span>
              {data.client_id && <Badge variant="outline">Com cliente em foco</Badge>}
              <span className="tabular-nums text-foreground">
                ~{tokens.toLocaleString("pt-BR")} tokens · {data.texto.length.toLocaleString("pt-BR")} caracteres
              </span>
            </div>
            <SectionTokenBar manifest={data.manifest} />
          </div>
          <CompiledPromptView texto={data.texto} manifest={data.manifest} clientId={data.client_id} />
        </>
      ) : null}
    </div>
  );
}

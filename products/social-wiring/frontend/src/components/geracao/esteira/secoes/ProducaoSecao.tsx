/**
 * Post card, "Produção" section (esteira-contract.md §6.2 item 4, FE-2):
 * production links (Drive/Frame.io, ≤ 10, https) plus the seed `AnexosSection`.
 */
import { useState } from "react";
import { AnexosSection, baixarArquivo } from "@noctusai/lib/components";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAtualizarPost } from "@/hooks/geracao/useEsteira";
import { postHub } from "@/hooks/geracao/usePostHub";
import { mensagemErroServidor } from "@/lib/erroServidor";
import type { LinkProducao, PostDetalhe } from "@/types/esteira";

export const LINKS_MAX = 10;

export function linkValido(url: string): boolean {
  try {
    return new URL(url.trim()).protocol === "https:";
  } catch {
    return false;
  }
}

export function ProducaoSecao({ post }: { post: PostDetalhe }) {
  const [rotulo, setRotulo] = useState("");
  const [url, setUrl] = useState("");
  const atualizar = useAtualizarPost();
  const docsQ = postHub.useDocumentos(post.id);
  const tiposQ = postHub.useTiposDocumento();
  const docMut = postHub.useDocumentoMutations(post.id);
  const links = post.links_producao;
  const podeAdd = rotulo.trim().length > 0 && linkValido(url) && links.length < LINKS_MAX;

  function salvarLinks(proximos: LinkProducao[], aposSalvar?: () => void) {
    atualizar.mutate(
      { id: post.id, patch: { links_producao: proximos } },
      {
        onSuccess: aposSalvar,
        onError: (e) => toast.error(mensagemErroServidor(e, "Não foi possível salvar os links.")),
      },
    );
  }

  function abrirDocumento(documentoId: string) {
    docMut.getUrl.mutate(
      { documentoId },
      {
        onSuccess: (r) => void baixarArquivo(r.url, "anexo").catch(() => window.open(r.url, "_blank")),
        onError: (e) => toast.error(mensagemErroServidor(e, "Não foi possível abrir o anexo.")),
      },
    );
  }

  return (
    <section className="space-y-4" data-testid="secao-producao">
      <div className="space-y-2">
        <h3 className="text-sm font-semibold">Links de produção</h3>
        {links.length === 0 ? (
          <p className="text-sm text-muted-foreground" data-testid="links-vazio">
            Nenhum link ainda. Adicione a pasta do Drive ou o corte final.
          </p>
        ) : (
          <ul className="space-y-1">
            {links.map((l, i) => (
              <li key={`${l.url}-${i}`} className="flex items-center justify-between gap-2 text-sm">
                <a href={l.url} target="_blank" rel="noopener noreferrer" className="truncate underline">
                  {l.rotulo}
                </a>
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={atualizar.isPending}
                  onClick={() => salvarLinks(links.filter((_, j) => j !== i))}
                >
                  Remover
                </Button>
              </li>
            ))}
          </ul>
        )}
        <div className="flex flex-wrap gap-2">
          <Input
            aria-label="Rótulo do link"
            className="w-40"
            placeholder="Pasta do Drive"
            value={rotulo}
            onChange={(e) => setRotulo(e.target.value)}
          />
          <Input
            aria-label="URL do link"
            className="min-w-48 flex-1"
            placeholder="https://..."
            value={url}
            aria-invalid={url.length > 0 && !linkValido(url)}
            onChange={(e) => setUrl(e.target.value)}
          />
          <Button
            size="sm"
            disabled={!podeAdd || atualizar.isPending}
            onClick={() =>
              salvarLinks([...links, { rotulo: rotulo.trim(), url: url.trim() }], () => {
                setRotulo("");
                setUrl("");
              })
            }
          >
            Adicionar link
          </Button>
        </div>
      </div>
      {docsQ.isError && !docsQ.data ? (
        <p className="text-sm text-destructive" data-testid="anexos-erro">
          Não foi possível carregar os anexos.
        </p>
      ) : (
        <AnexosSection
          documentos={docsQ.data ?? []}
          tipos={tiposQ.data ?? []}
          loading={docsQ.isPending && !docsQ.data}
          refreshing={docsQ.isFetching && !!docsQ.data}
          uploading={docMut.upload.isPending}
          onUpload={(file, tipoDocumento) =>
            docMut.upload.mutate(
              { file, tipoDocumento },
              { onError: (e) => toast.error(mensagemErroServidor(e, "Não foi possível enviar o anexo.")) },
            )
          }
          onOpenDocumento={abrirDocumento}
          onDeleteDocumento={(documentoId, motivo) =>
            docMut.remove.mutate(
              { documentoId, motivo },
              { onError: (e) => toast.error(mensagemErroServidor(e, "Não foi possível remover o anexo.")) },
            )
          }
        />
      )}
    </section>
  );
}

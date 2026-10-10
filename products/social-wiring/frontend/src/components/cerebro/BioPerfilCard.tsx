/**
 * Bio do perfil — the marca's profile bio, the source of the headline
 * "Núcleo de Influência" (contract §6). "Usar a bio do Instagram" only shows
 * when the marca has a connected Instagram account with a biography; it fills
 * the textarea and the user still has to Salvar.
 */
import { useEffect, useState } from "react";
import { Instagram } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useBioInstagram, useCerebroPerfil, useSalvarPerfil } from "@/hooks/useCerebro";
import { MAX_BIO, mensagemErro } from "./labels";

export function BioPerfilCard({ marcaId }: { marcaId: string }) {
  const perfilQ = useCerebroPerfil(marcaId);
  const salvar = useSalvarPerfil();
  const ig = useBioInstagram(marcaId);
  const [bio, setBio] = useState("");

  const salva = perfilQ.data?.bio ?? "";
  const perfilMarca = perfilQ.data?.marca_id;
  useEffect(() => {
    if (perfilMarca === marcaId) setBio(salva);
  }, [marcaId, perfilMarca, salva]);

  const sujo = bio !== salva;

  async function onSalvar() {
    try {
      await salvar.mutateAsync({ marca_id: marcaId, bio });
      toast.success("Bio salva.");
    } catch (e) {
      toast.error(mensagemErro(e, "Não foi possível salvar a bio."));
    }
  }

  return (
    <section className="space-y-3 rounded-lg border bg-card p-4" aria-labelledby="cerebro-bio-titulo">
      <div>
        <h2 id="cerebro-bio-titulo" className="text-base font-semibold">
          Bio do perfil
        </h2>
        <p className="text-sm text-muted-foreground">Usada como Núcleo de Influência na geração de headlines.</p>
      </div>
      {perfilQ.showSkeleton ? (
        <Skeleton className="h-24 w-full" data-testid="bio-skeleton" />
      ) : perfilQ.isError && !perfilQ.data ? (
        <div role="alert" className="flex items-center gap-3 text-sm">
          Não foi possível carregar a bio.
          <Button variant="outline" size="sm" onClick={() => void perfilQ.refetch()}>
            Tentar novamente
          </Button>
        </div>
      ) : (
        <>
          <Textarea
            aria-label="Texto da bio"
            value={bio}
            maxLength={MAX_BIO}
            rows={4}
            onChange={(e) => setBio(e.target.value)}
          />
          <div className="flex flex-wrap items-center gap-3">
            <span className="text-xs text-muted-foreground">
              {bio.length.toLocaleString("pt-BR")}/{MAX_BIO.toLocaleString("pt-BR")} caracteres
            </span>
            {ig.temConta && ig.bio && (
              <Button type="button" variant="outline" size="sm" onClick={() => setBio(ig.bio as string)}>
                <Instagram className="mr-1.5 h-3.5 w-3.5" />
                Usar a bio do Instagram
              </Button>
            )}
            <Button className="ml-auto" size="sm" disabled={!sujo || salvar.isPending} onClick={() => void onSalvar()}>
              {salvar.isPending ? "Salvando…" : "Salvar"}
            </Button>
          </div>
        </>
      )}
    </section>
  );
}

/**
 * Meu Perfil (P4, `/media-creation/perfil`) — per-marca "Informações de criação":
 * nichos (max 3), profissões (max 3), Bio, Apresentação magnética, CTAs, plus a
 * read-only Instagram card. Contract: geracao-contract.md §4.1, §7.4.
 * Loading: two signals off `data`, never `.isLoading` (lying-loading-state.md).
 */
import { useState } from "react";
import { AlertCircle, HelpCircle, Loader2, RefreshCw } from "lucide-react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { mensagemErro } from "@/components/cerebro/labels";
import { MultiSelectPopover } from "@noctusai/lib/design-system";
import { MarcaSwitcher } from "@/components/pesquisa/MarcaSwitcher";
import { usePerfilCriacao, useSalvarPerfilCriacao } from "@/hooks/geracao/usePerfilCriacao";
import { useTaxonomias } from "@/hooks/geracao/useTaxonomias";
import { useIntegrationAccounts } from "@/hooks/useIntegrationAccounts";
import { useMarcaPesquisa } from "@/hooks/useMarcaPesquisa";
import { useMarcas } from "@/hooks/useMarcas";
import type { PerfilCriacao, Taxon, Taxonomias } from "@/types/geracao";

export const MAX_TAXONS = 3;

interface CampoTaxonProps {
  id: string;
  label: string;
  ajuda: string;
  dica: string;
  erroMax: string;
  opcoes: Taxon[];
  valor: number[];
  max: number;
  onChange: (ids: number[]) => void;
}

/** Nichos / profissões picker: the shared MultiSelectPopover with a hard cap + CoreStudio's copy. */
function CampoTaxon({ id, label, ajuda, dica, erroMax, opcoes, valor, max, onChange }: CampoTaxonProps) {
  const noLimite = valor.length >= max;
  return (
    <div className="space-y-2" id={id}>
      <div>
        <p className="text-sm font-medium" title={ajuda}>{label}</p>
        <p className="text-xs text-muted-foreground">{ajuda}</p>
      </div>
      <MultiSelectPopover
        label={label}
        triggerLabel={`Selecionar ${label.toLowerCase()}`}
        options={opcoes.map((o) => ({ value: String(o.id), label: o.nome }))}
        selected={valor.map(String)}
        onToggle={(v) => {
          const n = Number(v);
          onChange(valor.includes(n) ? valor.filter((x) => x !== n) : noLimite ? valor : [...valor, n]);
        }}
        max={max}
        showChips
        testId={`taxon-${id}`}
      />
      {noLimite ? (
        <p role="alert" className="text-xs text-destructive">{erroMax}</p>
      ) : (
        <p className="text-xs text-muted-foreground">{dica}</p>
      )}
    </div>
  );
}
export const MAX_BIO = 5000;
export const MAX_TEXTO_LONGO = 3000;

export const BIO_TEMPLATE =
  "Eu sou (Nome), Sou (Profissão). Falo sobre (dores e desejos do publico). Eu ajudo pessoas a (resolver as dores) Por meio do (método utilizado no nicho).Para a pessoa consiga (solução e vida com os benefícios).";
const AJUDA_MAGNETICA = "Esse campo será incluso nas gerações de Roteiros. Dentro da Tag Apresentação Magnética";
const AJUDA_CTAS = "Esse campo será incluso nas gerações de Roteiros. Dentro da Tag CTAs";

/** CoreStudio's rule: bio needs nichos ∧ profissões, and nichos ∧ profissões need the bio. */
export function perfilIncompleto(f: { bio: string; nichos: number[]; profissoes: number[] }): boolean {
  const bio = f.bio.trim().length > 0;
  const taxons = f.nichos.length > 0 && f.profissoes.length > 0;
  return (taxons && !bio) || (bio && !taxons);
}

export function MeuPerfil() {
  const marcasQ = useMarcas();
  const marcas = marcasQ.data ?? [];
  const { marcaId, escolherMarca } = useMarcaPesquisa(marcas);
  const perfilQ = usePerfilCriacao(marcaId);
  const taxQ = useTaxonomias();

  return (
    <div className="space-y-6 p-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Minha conta</h1>
          <p className="text-sm text-muted-foreground">Informações de criação desta marca</p>
        </div>
        <div className="flex items-center gap-3">
          {perfilQ.isRefreshing && (
            <span role="status" className="flex items-center gap-1 text-sm text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              Atualizando…
            </span>
          )}
          <MarcaSwitcher marcas={marcas} marcaId={marcaId} onChange={escolherMarca} />
        </div>
      </header>

      {marcasQ.isPending && !marcasQ.data ? (
        <Skeleton className="h-40 w-full" />
      ) : marcasQ.isError && !marcasQ.data ? (
        <ErroBloco texto="Não foi possível carregar as marcas." onRetry={() => void marcasQ.refetch()} />
      ) : !marcaId ? (
        <p className="py-16 text-center text-sm text-muted-foreground">
          Cadastre uma marca em Clientes para preencher o perfil de criação.
        </p>
      ) : perfilQ.showSkeleton || taxQ.showSkeleton ? (
        <div className="space-y-3" aria-busy="true" data-testid="perfil-skeleton">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-32 w-full" />
        </div>
      ) : perfilQ.isError && !perfilQ.data ? (
        <ErroBloco texto="Não foi possível carregar o perfil." onRetry={() => void perfilQ.refetch()} />
      ) : taxQ.isError && !taxQ.data ? (
        <ErroBloco texto="Não foi possível carregar nichos e profissões." onRetry={() => void taxQ.refetch()} />
      ) : perfilQ.data && taxQ.data ? (
        <>
          <PerfilForm
            key={perfilQ.data.marca_id}
            perfil={perfilQ.data}
            taxonomias={taxQ.data}
            marcaAtualId={marcaId}
          />
          <InstagramCard marcaId={marcaId} />
        </>
      ) : null}
    </div>
  );
}

function PerfilForm({
  perfil,
  taxonomias,
  marcaAtualId,
}: {
  perfil: PerfilCriacao;
  taxonomias: Taxonomias;
  marcaAtualId: string;
}) {
  const [nichos, setNichos] = useState(perfil.nichos);
  const [profissoes, setProfissoes] = useState(perfil.profissoes);
  const [bio, setBio] = useState(perfil.bio);
  const [magnetica, setMagnetica] = useState(perfil.apresentacao_magnetica);
  const [ctas, setCtas] = useState(perfil.ctas);
  const [avisoAberto, setAvisoAberto] = useState(false);
  const salvarM = useSalvarPerfilCriacao();

  // While the next marca's data is still loading, the previous form stays visible but read-only.
  const desatualizado = perfil.marca_id !== marcaAtualId;
  const profissoesOrdenadas = [...taxonomias.profissoes].sort((a, b) => a.nome.localeCompare(b.nome, "pt-BR"));

  async function salvar() {
    try {
      await salvarM.mutateAsync({
        marca_id: perfil.marca_id,
        bio,
        nichos,
        profissoes,
        apresentacao_magnetica: magnetica,
        ctas,
      });
      toast.success("Perfil atualizado.");
      setAvisoAberto(false);
    } catch (e) {
      setAvisoAberto(false);
      toast.error(mensagemErro(e, "Não foi possível atualizar o perfil."));
    }
  }

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (perfilIncompleto({ bio, nichos, profissoes })) setAvisoAberto(true);
    else void salvar();
  }

  return (
    <form onSubmit={onSubmit} className="max-w-3xl space-y-6" aria-label="Meu Perfil">
      <fieldset disabled={desatualizado} className="space-y-6">
        <CampoTaxon
          id="nichos"
          label="Nichos"
          ajuda="Preencha com os nichos que você deseja gerar Headlines"
          dica="Selecione até 3 nichos"
          erroMax="Máximo de 3 nichos permitidos"
          opcoes={taxonomias.nichos}
          valor={nichos}
          max={MAX_TAXONS}
          onChange={setNichos}
        />
        <CampoTaxon
          id="profissoes"
          label="Profissões"
          ajuda="Preencha com as profissões que você deseja gerar Headlines"
          dica="Selecione até 3 profissões"
          erroMax="Máximo de 3 profissões permitidos"
          opcoes={profissoesOrdenadas}
          valor={profissoes}
          max={MAX_TAXONS}
          onChange={setProfissoes}
        />

        <CampoTexto
          id="bio"
          label="Bio"
          valor={bio}
          max={MAX_BIO}
          onChange={setBio}
          rows={6}
          ajuda={BIO_TEMPLATE}
          ajudaRotulo="Modelo de Bio"
        />
        <CampoTexto
          id="magnetica"
          label="Apresentação magnética"
          valor={magnetica}
          max={MAX_TEXTO_LONGO}
          onChange={setMagnetica}
          rows={4}
          ajuda={AJUDA_MAGNETICA}
          ajudaRotulo="Sobre Apresentação magnética"
        />
        <CampoTexto
          id="ctas"
          label="CTAs"
          valor={ctas}
          max={MAX_TEXTO_LONGO}
          onChange={setCtas}
          rows={4}
          ajuda={AJUDA_CTAS}
          ajudaRotulo="Sobre CTAs"
        />
      </fieldset>

      <Button type="submit" disabled={desatualizado || salvarM.isPending}>
        {salvarM.isPending ? "Aguarde atualizando..." : "Atualizar"}
      </Button>

      <Dialog open={avisoAberto} onOpenChange={setAvisoAberto}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Atenção</DialogTitle>
            <DialogDescription>
              O sistema precisa da bio preenchida juntamente com os nichos e profissões para poder sugerir itens da
              pesquisa para você. Tem certeza que deseja continuar assim?
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setAvisoAberto(false)} disabled={salvarM.isPending}>
              Cancelar
            </Button>
            <Button type="button" onClick={() => void salvar()} disabled={salvarM.isPending}>
              {salvarM.isPending ? "Aguarde…" : "Continuar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </form>
  );
}

function CampoTexto({
  id,
  label,
  valor,
  max,
  onChange,
  rows,
  ajuda,
  ajudaRotulo,
}: {
  id: string;
  label: string;
  valor: string;
  max: number;
  onChange: (v: string) => void;
  rows: number;
  ajuda: string;
  ajudaRotulo: string;
}) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-1.5">
        <Label htmlFor={id}>{label}</Label>
        <Popover>
          <PopoverTrigger asChild>
            <button type="button" aria-label={ajudaRotulo} className="text-muted-foreground hover:text-foreground">
              <HelpCircle className="h-4 w-4" />
            </button>
          </PopoverTrigger>
          <PopoverContent className="text-sm">{ajuda}</PopoverContent>
        </Popover>
      </div>
      <Textarea
        id={id}
        rows={rows}
        maxLength={max}
        value={valor}
        onChange={(e) => onChange(e.target.value)}
      />
      <p className="text-right text-xs text-muted-foreground">
        {valor.length}/{max}
      </p>
    </div>
  );
}

/** Read-only: which Instagram / Facebook-Login (Meta) connections this marca has. */
function InstagramCard({ marcaId }: { marcaId: string }) {
  const contasQ = useIntegrationAccounts({ marcaId });
  const contas = contasQ.data ?? [];
  const instagram = contas.filter((c) => c.provider === "instagram");
  const meta = contas.filter((c) => c.provider === "meta");

  return (
    <section aria-label="Instagram" className="max-w-3xl space-y-2 rounded-lg border p-4">
      <h2 className="text-base font-medium">Instagram</h2>
      {contasQ.isPending && !contasQ.data ? (
        <Skeleton className="h-10 w-full" />
      ) : contasQ.isError && !contasQ.data ? (
        <ErroBloco texto="Não foi possível carregar as conexões." onRetry={() => void contasQ.refetch()} />
      ) : (
        <>
          {instagram.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nenhuma conta do Instagram conectada a esta marca.</p>
          ) : (
            <ul className="text-sm">
              {instagram.map((c) => (
                <li key={c.id}>{c.account_label}</li>
              ))}
            </ul>
          )}
          <p className="text-sm">
            {meta.length > 0
              ? "✓ Conexão Meta (Facebook Login) disponível para monitorar perfis."
              : "✗ Nenhuma conta Meta (Facebook Login) conectada — necessária para monitorar perfis na Biblioteca."}
          </p>
        </>
      )}
      <Link to="/marcas" className="text-sm text-primary hover:underline">
        Gerenciar em Conexões › Marcas
      </Link>
    </section>
  );
}

function ErroBloco({ texto, onRetry }: { texto: string; onRetry: () => void }) {
  return (
    <div role="alert" className="flex flex-col items-center gap-3 py-8 text-sm">
      <AlertCircle className="h-6 w-6 text-destructive" />
      {texto}
      <Button variant="outline" size="sm" onClick={onRetry}>
        <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
        Tentar novamente
      </Button>
    </div>
  );
}

export default MeuPerfil;

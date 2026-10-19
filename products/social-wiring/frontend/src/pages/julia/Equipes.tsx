/**
 * Lais › Equipes (`/lais/equipes`, wave 11 — Distribuição). Team list with a
 * 3-step "Configurar nova equipe" wizard, per-team Configurações / Usuários /
 * Excluir menu and an expandable per-member metrics table (month picker).
 * Writes are admin-only (server enforces; the UX hides the controls).
 * Loading = two signals off `data` (never `isLoading`).
 */
import { useState } from "react";
import { useConfirm } from "@noctusai/lib";
import { useIsOrgAdmin } from "@noctusai/lib/design-system";
import { AlertCircle, ChevronDown, ChevronRight, Loader2, MoreVertical, Plus, Users } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { EquipeConfigDrawer } from "@/components/lais/equipes/EquipeConfigDrawer";
import { EquipeMetricas } from "@/components/lais/equipes/EquipeMetricas";
import { EquipeUsuariosDrawer } from "@/components/lais/equipes/EquipeUsuariosDrawer";
import { EquipeWizard } from "@/components/lais/equipes/EquipeWizard";
import { mesAtual, useExcluirEquipe, useLaisEquipes, type Equipe } from "@/hooks/useLaisEquipes";
import { mensagemErroServidor } from "@/lib/erroServidor";

export default function LaisEquipes() {
  const isAdmin = useIsOrgAdmin();
  const confirm = useConfirm();
  const q = useLaisEquipes();
  const excluir = useExcluirEquipe();
  const [wizard, setWizard] = useState(false);
  const [aberta, setAberta] = useState<string | null>(null);
  const [menu, setMenu] = useState<string | null>(null);
  const [mes, setMes] = useState(mesAtual());
  const [config, setConfig] = useState<string | null>(null);
  const [usuarios, setUsuarios] = useState<string | null>(null);
  const equipes = q.data ?? [];
  const eqConfig = equipes.find((e) => e.id === config);
  const eqUsuarios = equipes.find((e) => e.id === usuarios);

  async function remover(e: Equipe) {
    setMenu(null);
    const ok = await confirm({
      title: "Excluir equipe",
      description: `Excluir a equipe "${e.nome}"? Esta ação não pode ser desfeita.`,
      confirmLabel: "Excluir equipe",
      tone: "danger",
    });
    if (!ok) return;
    excluir.mutate(e.id, {
      onSuccess: () => toast.success("Equipe excluída."),
      onError: (err) => toast.error(mensagemErroServidor(err, "Não foi possível excluir a equipe.")),
    });
  }

  return (
    <div className="container max-w-3xl space-y-5 py-6">
      <header className="flex items-center justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-2xl font-bold">Equipes</h1>
          <p className="text-sm text-muted-foreground">Organize os atendentes e defina como os leads são distribuídos.</p>
        </div>
        <div className="flex items-center gap-2">
          {q.isRefreshing && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" data-testid="equipes-refreshing" />}
          {isAdmin && <Button onClick={() => setWizard(true)}><Plus className="mr-1 h-4 w-4" /> Criar equipe</Button>}
        </div>
      </header>

      {q.showSkeleton && <p className="text-sm text-muted-foreground" data-testid="equipes-loading">Carregando equipes…</p>}
      {q.isError && !q.data && (
        <div role="alert" className="flex items-center gap-2 text-sm text-destructive">
          <AlertCircle className="h-4 w-4" /> Não foi possível carregar as equipes.
          <Button size="sm" variant="outline" onClick={() => q.refetch()}>Tentar novamente</Button>
        </div>
      )}
      {q.data && equipes.length === 0 && (
        <div className="rounded border border-dashed p-8 text-center text-sm text-muted-foreground" data-testid="equipes-vazio">
          <Users className="mx-auto mb-2 h-6 w-6" />
          Nenhuma equipe criada ainda.{isAdmin ? " Use “Criar equipe” para começar." : ""}
        </div>
      )}

      <ul className="space-y-2">
        {equipes.map((e) => {
          const exp = aberta === e.id;
          const n = e.membros.length;
          return (
            <li key={e.id} className="rounded border" data-testid="equipe-item">
              <div className="flex items-center gap-2 px-4 py-3">
                <button type="button" className="flex flex-1 items-center gap-2 text-left" aria-expanded={exp}
                  onClick={() => setAberta(exp ? null : e.id)}>
                  {exp ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                  <span className="font-medium">{e.nome}</span>
                  <span className="text-sm text-muted-foreground">— {n} {n === 1 ? "membro" : "membros"}</span>
                </button>
                {isAdmin && (
                  <div className="relative">
                    <Button variant="outline" size="sm" aria-haspopup="menu" aria-label={`Editar ${e.nome}`}
                      onClick={() => setMenu(menu === e.id ? null : e.id)}>Editar <MoreVertical className="ml-1 h-3 w-3" /></Button>
                    {menu === e.id && (
                      <div role="menu" className="absolute right-0 z-10 mt-1 w-44 rounded border bg-popover p-1 shadow">
                        <button role="menuitem" className="block w-full rounded px-2 py-1.5 text-left text-sm hover:bg-accent"
                          onClick={() => { setMenu(null); setConfig(e.id); }}>Configurações</button>
                        <button role="menuitem" className="block w-full rounded px-2 py-1.5 text-left text-sm hover:bg-accent"
                          onClick={() => { setMenu(null); setUsuarios(e.id); }}>Usuários</button>
                        <button role="menuitem" className="block w-full rounded px-2 py-1.5 text-left text-sm text-destructive hover:bg-accent"
                          onClick={() => void remover(e)}>Excluir equipe</button>
                      </div>
                    )}
                  </div>
                )}
              </div>
              {exp && <EquipeMetricas equipeId={e.id} mes={mes} onMes={setMes} />}
            </li>
          );
        })}
      </ul>

      {wizard && <EquipeWizard onClose={() => setWizard(false)} />}
      {eqConfig && <EquipeConfigDrawer equipe={eqConfig} onClose={() => setConfig(null)} />}
      {eqUsuarios && <EquipeUsuariosDrawer equipe={eqUsuarios} onClose={() => setUsuarios(null)} />}
    </div>
  );
}

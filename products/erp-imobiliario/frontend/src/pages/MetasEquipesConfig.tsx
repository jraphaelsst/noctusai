/**
 * /metas/configuracoes/equipes — team editor (owner-only).
 *
 * Full flow:
 *  - Nova Equipe modal (nome + cor + líder opcional)
 *  - Editar equipe (nome + cor + líder + ativo)
 *  - Dissolver equipe (soft-delete)
 *  - Membros drawer: listar + adicionar por user_id + remover + alternar líder
 */
import { useState } from 'react';
import {
  Card, CardContent, CardHeader, CardTitle, CardDescription,
} from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog';
import { Users, Plus, Pencil, UserPlus, Minus, Crown, Trash2 } from 'lucide-react';
import {
  useAdicionarMembro,
  useAtualizarEquipe,
  useAtualizarPapelMembro,
  useCriarEquipe,
  useDissolverEquipe,
  useEquipeMembros,
  useEquipes,
  useRemoverMembro,
  type Equipe,
} from '@/hooks/useMetasDomain';

const CORES = ['#e53935', '#fb8c00', '#fdd835', '#43a047', '#1e88e5', '#8e24aa', '#6d4c41', '#546e7a'];

export default function MetasEquipesConfig() {
  const { data: equipes = [], isLoading } = useEquipes();
  const [newOpen, setNewOpen] = useState(false);
  const [editing, setEditing] = useState<Equipe | null>(null);
  const [membrosEquipe, setMembrosEquipe] = useState<Equipe | null>(null);

  return (
    <div className="mx-auto max-w-5xl px-4 py-6 sm:px-6 sm:py-8 lg:py-10">
      <div className="mb-6 flex items-center gap-2">
        <Users className="h-6 w-6 text-primary" />
        <h1 className="text-2xl font-bold text-foreground">Equipes</h1>
      </div>

      <p className="mb-6 text-sm text-muted-foreground">
        Configure equipes comerciais, defina líderes, gerencie membros.
        Admin do sistema é reforçado via RLS — usuários sem permissão
        recebem 403 do backend.
      </p>

      <div className="mb-4 flex items-center justify-end">
        <Button className="gap-2" onClick={() => setNewOpen(true)}>
          <Plus className="h-4 w-4" /> Nova equipe
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Equipes ativas ({equipes.length})</CardTitle>
          <CardDescription>
            {isLoading ? 'Carregando…' : 'Clique em "Membros" para gerenciar integrantes.'}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {!equipes.length ? (
            <p className="text-sm text-muted-foreground">
              Nenhuma equipe criada ainda. Comece com "Nova equipe".
            </p>
          ) : (
            <ul className="divide-y">
              {equipes.map((e) => (
                <EquipeRow
                  key={e.id}
                  equipe={e}
                  onEdit={() => setEditing(e)}
                  onMembros={() => setMembrosEquipe(e)}
                />
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      {newOpen && (
        <EquipeFormDialog
          open={newOpen}
          onClose={() => setNewOpen(false)}
          mode="create"
        />
      )}
      {editing && (
        <EquipeFormDialog
          open
          onClose={() => setEditing(null)}
          mode="edit"
          initial={editing}
        />
      )}
      {membrosEquipe && (
        <MembrosDialog
          equipe={membrosEquipe}
          onClose={() => setMembrosEquipe(null)}
        />
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────

function EquipeRow({ equipe, onEdit, onMembros }: {
  equipe: Equipe; onEdit: () => void; onMembros: () => void;
}) {
  const dissolver = useDissolverEquipe();
  function handleDissolver() {
    if (confirm(`Dissolver a equipe "${equipe.nome}"? Membros atuais ficam com left_at no histórico.`)) {
      dissolver.mutate(equipe.id);
    }
  }
  return (
    <li className="flex items-center justify-between py-3">
      <div className="flex items-center gap-3">
        <div
          className="h-3 w-3 rounded-full"
          style={{ background: equipe.cor || '#999' }}
        />
        <div>
          <p className="text-sm font-medium">{equipe.nome}</p>
          <p className="text-xs text-muted-foreground">
            {equipe.ativo ? 'ativa' : 'inativa'} · líder: {equipe.lider_id ? '…' : 'sem líder'}
          </p>
        </div>
      </div>
      <div className="flex items-center gap-1">
        <Button variant="ghost" size="sm" className="gap-1" onClick={onMembros}>
          <UserPlus className="h-3.5 w-3.5" /> Membros
        </Button>
        <Button variant="ghost" size="sm" className="gap-1" onClick={onEdit}>
          <Pencil className="h-3.5 w-3.5" /> Editar
        </Button>
        <Button
          variant="ghost" size="sm"
          className="gap-1 text-destructive"
          onClick={handleDissolver}
          disabled={dissolver.isPending}
        >
          <Minus className="h-3.5 w-3.5" /> Dissolver
        </Button>
      </div>
    </li>
  );
}

function EquipeFormDialog({ open, onClose, mode, initial }: {
  open: boolean; onClose: () => void; mode: 'create' | 'edit'; initial?: Equipe;
}) {
  const [nome, setNome] = useState(initial?.nome ?? '');
  const [cor, setCor] = useState(initial?.cor ?? CORES[0]);
  const [ativo, setAtivo] = useState(initial?.ativo ?? true);
  const criar = useCriarEquipe();
  const atualizar = useAtualizarEquipe();

  async function handleSave() {
    if (!nome.trim()) return;
    if (mode === 'create') {
      await criar.mutateAsync({ nome: nome.trim(), cor });
    } else if (initial) {
      await atualizar.mutateAsync({ id: initial.id, nome: nome.trim(), cor, ativo });
    }
    onClose();
  }

  const loading = criar.isPending || atualizar.isPending;

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{mode === 'create' ? 'Nova equipe' : 'Editar equipe'}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div>
            <label className="mb-1 block text-xs text-muted-foreground">Nome</label>
            <Input value={nome} onChange={(e) => setNome(e.target.value)} placeholder="DRAGÃO" />
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted-foreground">Cor</label>
            <div className="flex flex-wrap gap-2">
              {CORES.map((c) => (
                <button
                  key={c}
                  type="button"
                  onClick={() => setCor(c)}
                  className="h-8 w-8 rounded-full border-2 transition"
                  style={{
                    background: c,
                    borderColor: c === cor ? 'white' : 'transparent',
                    outline: c === cor ? '2px solid currentColor' : 'none',
                  }}
                  aria-label={`Cor ${c}`}
                />
              ))}
            </div>
          </div>
          {mode === 'edit' && (
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={ativo} onChange={(e) => setAtivo(e.target.checked)} />
              Ativa
            </label>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancelar</Button>
          <Button onClick={handleSave} disabled={loading || !nome.trim()}>
            {loading ? 'Salvando…' : 'Salvar'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function MembrosDialog({ equipe, onClose }: { equipe: Equipe; onClose: () => void }) {
  const { data: membros = [] } = useEquipeMembros(equipe.id);
  const adicionar = useAdicionarMembro(equipe.id);
  const atualizarPapel = useAtualizarPapelMembro(equipe.id);
  const remover = useRemoverMembro(equipe.id);
  const [userId, setUserId] = useState('');

  async function handleAdd() {
    if (!userId.trim()) return;
    await adicionar.mutateAsync({ user_id: userId.trim(), papel: 'corretor' });
    setUserId('');
  }

  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Membros de {equipe.nome}</DialogTitle>
        </DialogHeader>

        <div className="space-y-3">
          <div className="flex gap-2">
            <Input
              value={userId}
              onChange={(e) => setUserId(e.target.value)}
              placeholder="user_id (UUID do corretor)"
            />
            <Button onClick={handleAdd} disabled={adicionar.isPending || !userId.trim()}>
              {adicionar.isPending ? '…' : 'Adicionar'}
            </Button>
          </div>

          {!membros.length ? (
            <p className="text-sm text-muted-foreground">Nenhum membro ativo.</p>
          ) : (
            <ul className="divide-y">
              {membros.map((m) => {
                const isLider = m.papel === 'lider';
                return (
                  <li key={m.id} className="flex items-center justify-between py-2">
                    <div className="min-w-0 flex-1 pr-2">
                      <p className="truncate text-sm font-mono">{m.user_id}</p>
                      <p className="text-xs text-muted-foreground">
                        {isLider ? (
                          <Badge variant="default" className="gap-1"><Crown className="h-3 w-3" /> líder</Badge>
                        ) : 'corretor'}
                      </p>
                    </div>
                    <div className="flex shrink-0 items-center gap-1">
                      <Button
                        variant="ghost" size="sm"
                        onClick={() => atualizarPapel.mutate({
                          membro_id: m.id,
                          papel: isLider ? 'corretor' : 'lider',
                        })}
                        className="gap-1"
                      >
                        <Crown className="h-3.5 w-3.5" />
                        {isLider ? 'Rebaixar' : 'Promover'}
                      </Button>
                      <Button
                        variant="ghost" size="sm"
                        className="gap-1 text-destructive"
                        onClick={() => remover.mutate(m.id)}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Fechar</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

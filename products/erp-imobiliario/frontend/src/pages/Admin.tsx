import { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { supabase } from '@noctusai/seed/infra';
import { useIsAdmin } from '@/hooks/useUserRole';
import { useProfiles } from '@/hooks/useProfiles';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { toast } from 'sonner';
import { Shield, UserCog, Plus, X } from 'lucide-react';
import { CardListSkeleton } from '@/components/ui/page-skeleton';
import { AdicionarRoleModal } from '@/components/modals/AdicionarRoleModal';

interface UserWithRoles {
  id: string;
  nome: string;
  email: string;
  roles: string[];
}

export default function Admin() {
  const navigate = useNavigate();
  const { isAdmin, isLoading: isLoadingRole } = useIsAdmin();
  const { data: profiles = [], isLoading: isLoadingProfiles } = useProfiles();
  const [selectedUser, setSelectedUser] = useState<{ id: string; nome: string; roles: string[] } | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);

  useEffect(() => {
    if (!isLoadingRole && !isAdmin) {
      toast.error('Acesso negado', {
        description: 'Você não tem permissão para acessar esta página.',
      });
      navigate('/');
    }
  }, [isAdmin, isLoadingRole, navigate]);

  const handleRemoveRole = async (userId: string, role: string) => {
    try {
      const { error } = await supabase
        .from('user_roles')
        .delete()
        .eq('user_id', userId)
        .eq('role', role as any);

      if (error) throw error;

      toast.success('Role removida com sucesso');
      loadUsersWithRoles();
    } catch (error: any) {
      console.error('Error removing role:', error);
      toast.error('Erro ao remover role', {
        description: error.message,
      });
    }
  };

  const handleOpenAddRoleModal = (user: UserWithRoles) => {
    setSelectedUser(user);
    setIsModalOpen(true);
  };

  const handleCloseModal = () => {
    setIsModalOpen(false);
    setSelectedUser(null);
  };

  const [usersWithRoles, setUsersWithRoles] = useState<UserWithRoles[]>([]);

  const loadUsersWithRoles = useCallback(async () => {
    if (profiles.length === 0) return;

    const { data: rolesData } = await supabase
      .from('user_roles')
      .select('user_id, role');

    // Agrupar roles por usuário
    const rolesMap = new Map<string, string[]>();
    rolesData?.forEach(r => {
      const existing = rolesMap.get(r.user_id) || [];
      rolesMap.set(r.user_id, [...existing, r.role]);
    });

    const users = profiles.map(profile => ({
      id: profile.id,
      nome: profile.nome,
      email: profile.email,
      roles: rolesMap.get(profile.id) || [],
    }));

    setUsersWithRoles(users);
  }, [profiles]);

  useEffect(() => {
    loadUsersWithRoles();
  }, [loadUsersWithRoles]);

  // Helper para definir cor do badge por role
  const getRoleBadgeVariant = (role: string): "default" | "secondary" | "destructive" | "outline" => {
    switch (role) {
      case 'admin':
        return 'default';
      case 'dev':
        return 'destructive';
      case 'coordenador':
        return 'outline';
      case 'corretor':
        return 'secondary';
      default:
        return 'secondary';
    }
  };

  const getRoleLabel = (role: string): string => {
    switch (role) {
      case 'admin':
        return 'Admin';
      case 'dev':
        return 'Dev';
      case 'coordenador':
        return 'Coordenador';
      case 'corretor':
        return 'Corretor';
      default:
        return role;
    }
  };

  if (isLoadingRole || !isAdmin) {
    return null;
  }

  return (
    <div className="container mx-auto py-6 sm:py-8 px-4 sm:px-6">
      <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3 mb-6 sm:mb-8">
        <Shield className="h-6 w-6 sm:h-8 sm:w-8 text-primary" />
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold">Administração</h1>
          <p className="text-sm text-muted-foreground">Gerencie roles de usuários</p>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <UserCog className="h-5 w-5" />
            Usuários com Roles Atribuídas
          </CardTitle>
          <CardDescription>
            Gerencie as roles dos usuários cadastrados no sistema
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isLoadingProfiles ? (
            <CardListSkeleton count={4} />
          ) : usersWithRoles.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              Nenhum usuário encontrado
            </div>
          ) : (
            <div className="space-y-4">
              {usersWithRoles.map((user) => (
                <div
                  key={user.id}
                  className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 sm:gap-4 p-4 border rounded-lg hover:bg-accent/50 transition-colors"
                >
                  <div className="flex-1 overflow-hidden w-full sm:w-auto min-w-0">
                    <p className="font-medium truncate">{user.nome}</p>
                    <p className="text-sm text-muted-foreground truncate">{user.email}</p>
                  </div>
                  <div className="flex items-center gap-2 flex-wrap">
                    {user.roles.length === 0 ? (
                      <Badge variant="outline" className="text-muted-foreground">
                        Sem roles
                      </Badge>
                    ) : (
                      user.roles.map((role) => (
                        <Badge
                          key={role}
                          variant={getRoleBadgeVariant(role)}
                          className={`flex items-center gap-1 ${
                            role === 'admin' ? 'bg-slate-700 hover:bg-slate-700/80 text-white border-slate-700' :
                            role === 'dev' ? 'bg-purple-600 hover:bg-purple-600/80 text-white border-purple-600' :
                            ''
                          }`}
                        >
                          {getRoleLabel(role)}
                          <button
                            onClick={() => handleRemoveRole(user.id, role)}
                            className="ml-1 hover:bg-background/20 rounded-full p-0.5 transition-colors"
                          >
                            <X className="h-3 w-3" />
                          </button>
                        </Badge>
                      ))
                    )}
                    <Button
                      size="icon"
                      variant="ghost"
                      className="h-8 w-8"
                      onClick={() => handleOpenAddRoleModal(user)}
                    >
                      <Plus className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {selectedUser && (
        <AdicionarRoleModal
          open={isModalOpen}
          onOpenChange={handleCloseModal}
          userId={selectedUser.id}
          userName={selectedUser.nome}
          currentRoles={selectedUser.roles}
          onSuccess={loadUsersWithRoles}
        />
      )}
    </div>
  );
}

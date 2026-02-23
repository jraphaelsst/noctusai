import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Plus, Mail, Phone, Calendar, Target } from "lucide-react";
import { format } from "date-fns";
import { ptBR } from "date-fns/locale";
import { NovoUsuarioModal } from "@/components/modals/NovoUsuarioModal";
import { UsuarioDetalhesModal } from "@/components/modals/UsuarioDetalhesModal";
import { useProfiles } from "@/hooks/useProfiles";
import { useMetas } from "@/hooks/useMetas";
import { useIsAdmin } from "@/hooks/useUserRole";
import { toast } from "sonner";
import { supabase } from "@/integrations/supabase/client";

export default function Usuarios() {
  const navigate = useNavigate();
  const { isAdmin, isLoading: isLoadingRole } = useIsAdmin();
  const { data: usuarios, isLoading: loadingUsuarios } = useProfiles();
  const { data: metas, isLoading: loadingMetas } = useMetas();
  const [selectedUsuario, setSelectedUsuario] = useState<typeof usuariosComStats[0] | null>(null);
  const [userRoles, setUserRoles] = useState<Map<string, string[]>>(new Map());
  
  useEffect(() => {
    if (!isLoadingRole && !isAdmin) {
      toast.error('Acesso negado', {
        description: 'Você não tem permissão para acessar esta página.',
      });
      navigate('/');
    }
  }, [isAdmin, isLoadingRole, navigate]);

  // Buscar roles dos usuários
  useEffect(() => {
    const fetchUserRoles = async () => {
      const { data: rolesData } = await supabase
        .from('user_roles')
        .select('user_id, role');

      const rolesMap = new Map<string, string[]>();
      rolesData?.forEach(r => {
        const existing = rolesMap.get(r.user_id) || [];
        rolesMap.set(r.user_id, [...existing, r.role]);
      });

      setUserRoles(rolesMap);
    };

    if (usuarios && usuarios.length > 0) {
      fetchUserRoles();
    }
  }, [usuarios]);

  // Helper para obter label da role
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
  
  const isLoading = loadingUsuarios || loadingMetas || isLoadingRole;
  
  if (!isAdmin && !isLoadingRole) {
    return null;
  }
  
  // Calcular estatísticas para cada usuário
  const usuariosComStats = (usuarios || []).map(usuario => {
    const metasDoUsuario = (metas || []).filter(meta => meta.usuario_id === usuario.id);
    const metasConcluidas = metasDoUsuario.filter(meta => meta.status === 'concluida');
    const metasAtrasadas = metasDoUsuario.filter(meta => meta.status === 'atrasada');
    
    return {
      ...usuario,
      totalMetas: metasDoUsuario.length,
      metasConcluidas: metasConcluidas.length,
      metasAtrasadas: metasAtrasadas.length,
      percentualConclusao: metasDoUsuario.length > 0 
        ? (metasConcluidas.length / metasDoUsuario.length) * 100 
        : 0
    };
  });

  return (
    <div className="space-y-4 sm:space-y-6">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold text-foreground">Usuários</h1>
          <p className="text-sm text-muted-foreground">
            Gerencie a equipe de usuários
          </p>
        </div>
        <NovoUsuarioModal />
      </div>

      {/* Lista de Usuários */}
      <div className="grid gap-4 sm:gap-6 grid-cols-1 md:grid-cols-2 lg:grid-cols-3">
        {isLoading ? (
          <>
            <Skeleton className="h-96" />
            <Skeleton className="h-96" />
            <Skeleton className="h-96" />
          </>
        ) : usuariosComStats.length === 0 ? (
          <Card className="col-span-full">
            <CardContent className="flex flex-col items-center justify-center py-12">
              <p className="text-muted-foreground mb-4">Nenhum usuário cadastrado ainda.</p>
              <NovoUsuarioModal />
            </CardContent>
          </Card>
        ) : (
          <>
            {usuariosComStats.map((usuario) => (
              <Card 
                key={usuario.id} 
                className="transition-all hover:shadow-md cursor-pointer"
                onClick={() => setSelectedUsuario(usuario)}
              >
            <CardHeader className="pb-4">
              <div className="flex items-center gap-4">
                <Avatar className="h-12 w-12">
                  <AvatarFallback className="bg-primary/10 text-primary text-lg font-semibold">
                    {usuario.nome.split(' ').map(n => n[0]).join('').substring(0, 2)}
                  </AvatarFallback>
                </Avatar>
                <div className="flex-1">
                  <CardTitle className="text-lg">{usuario.nome}</CardTitle>
                  <div className="flex items-center gap-2 mt-1 flex-wrap">
                    <Badge 
                      variant={usuario.percentualConclusao >= 80 ? "default" : "secondary"}
                      className="text-xs"
                    >
                      {usuario.percentualConclusao.toFixed(0)}% conclusão
                    </Badge>
                    {userRoles.get(usuario.id)?.map((role) => (
                      <Badge
                        key={role}
                        variant="outline"
                        className={`text-xs ${
                          role === 'admin' ? 'bg-slate-700 hover:bg-slate-700/80 text-white border-slate-700' :
                          role === 'dev' ? 'bg-purple-600 hover:bg-purple-600/80 text-white border-purple-600' :
                          role === 'coordenador' ? 'border-primary text-primary' :
                          'bg-secondary text-secondary-foreground'
                        }`}
                      >
                        {getRoleLabel(role)}
                      </Badge>
                    ))}
                  </div>
                </div>
              </div>
            </CardHeader>
            
            <CardContent className="space-y-4">
              {/* Informações de Contato */}
              <div className="space-y-2">
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Mail className="h-4 w-4" />
                  <span>{usuario.email}</span>
                </div>
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Phone className="h-4 w-4" />
                  <span>{usuario.telefone}</span>
                </div>
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Calendar className="h-4 w-4" />
                  <span>
                    Desde {format(new Date(usuario.created_at), "MMM yyyy", { locale: ptBR })}
                  </span>
                </div>
              </div>

              {/* Estatísticas de Metas */}
              <div className="bg-muted/50 rounded-lg p-3">
                <div className="flex items-center gap-2 mb-2">
                  <Target className="h-4 w-4 text-primary" />
                  <span className="text-sm font-medium">Performance</span>
                </div>
                <div className="grid grid-cols-3 gap-2 text-center">
                  <div>
                    <div className="text-lg font-bold text-primary">
                      {usuario.totalMetas}
                    </div>
                    <div className="text-xs text-muted-foreground">Total</div>
                  </div>
                  <div>
                    <div className="text-lg font-bold text-success">
                      {usuario.metasConcluidas}  
                    </div>
                    <div className="text-xs text-muted-foreground">Concluídas</div>
                  </div>
                  <div>
                    <div className={`text-lg font-bold ${
                      usuario.metasAtrasadas > 0 ? 'text-danger' : 'text-muted-foreground'
                    }`}>
                      {usuario.metasAtrasadas}
                    </div>
                    <div className="text-xs text-muted-foreground">Atrasadas</div>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}

        {/* Card para adicionar novo usuário */}
      <Card className="border-dashed border-2 border-muted-foreground/25 hover:border-primary/50 transition-colors">
        <CardContent className="flex flex-col items-center justify-center py-12">
          <div className="rounded-full bg-muted p-4 mb-4">
            <Plus className="h-8 w-8 text-muted-foreground" />
          </div>
          <h3 className="text-lg font-semibold text-foreground mb-2">
            Adicionar Novo Usuário
          </h3>
          <p className="text-sm text-muted-foreground text-center mb-4">
            Expanda sua equipe adicionando um novo usuário à plataforma
          </p>
          <NovoUsuarioModal />
        </CardContent>
      </Card>
          </>
        )}
      </div>

      {/* Modal de Detalhes */}
      {selectedUsuario && (
        <UsuarioDetalhesModal
          usuario={selectedUsuario}
          open={!!selectedUsuario}
          onOpenChange={(open) => !open && setSelectedUsuario(null)}
        />
      )}
    </div>
  );
}
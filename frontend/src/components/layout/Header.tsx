import { User, LogOut, Lock, Edit2, Moon, Sun } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { HoverCard, HoverCardContent, HoverCardTrigger } from "@/components/ui/hover-card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { useUserProfile } from "@/hooks/useUserProfile";
import { useUserRole, useIsAdmin } from "@/hooks/useUserRole";
import { useUserRoles } from "@/hooks/useUserRoles";
import { useUpdateProfile } from "@/hooks/useProfiles";
import { supabase } from "@/integrations/supabase/client";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { useState, useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";

export function Header() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data: profile, isLoading: isLoadingProfile } = useUserProfile();
  const { data: role, isLoading: isLoadingRole } = useUserRole();
  const { data: roles = [], isLoading: isLoadingRoles } = useUserRoles();
  const { isAdmin } = useIsAdmin();
  const updateProfile = useUpdateProfile();

  const [editMode, setEditMode] = useState<'profile' | 'password' | null>(null);
  const [formData, setFormData] = useState({
    nome: profile?.nome || "",
    email: profile?.email || "",
    telefone: profile?.telefone || "",
  });
  const [passwordData, setPasswordData] = useState({
    currentPassword: "",
    newPassword: "",
    confirmPassword: "",
  });
  const [theme, setTheme] = useState<'light' | 'dark'>('light');

  useEffect(() => {
    const isDark = document.documentElement.classList.contains('dark');
    setTheme(isDark ? 'dark' : 'light');
  }, []);

  const toggleTheme = () => {
    const newTheme = theme === 'light' ? 'dark' : 'light';
    setTheme(newTheme);
    document.documentElement.classList.toggle('dark');
  };

  const handleLogout = async () => {
    const { error } = await supabase.auth.signOut();
    if (error) {
      toast.error("Erro ao sair da conta");
      return;
    }
    toast.success("Logout realizado com sucesso");
    navigate("/");
  };

  const getInitials = (name: string) => {
    const names = name.split(" ");
    if (names.length >= 2) {
      return `${names[0][0]}${names[1][0]}`.toUpperCase();
    }
    return name.substring(0, 2).toUpperCase();
  };

  const formatNome = (nome: string) => {
    return nome
      .toLowerCase()
      .split(' ')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ');
  };

  const getRoleLabel = (roleValue: string | null) => {
    if (roleValue === "admin") return "Administrador";
    if (roleValue === "coordenador") return "Coordenador";
    if (roleValue === "dev") return "Desenvolvedor";
    return "Corretor";
  };

  const getRolesLabel = (rolesArray: string[]) => {
    if (rolesArray.length === 0) return "Corretor";
    return rolesArray
      .map(r => {
        if (r === "admin") return "Administrador";
        if (r === "coordenador") return "Coordenador";
        if (r === "dev") return "Desenvolvedor";
        return "Corretor";
      })
      .join(", ");
  };

  const handleUpdateProfile = async () => {
    if (!profile?.id) return;
    
    try {
      await updateProfile.mutateAsync({
        id: profile.id,
        nome: formData.nome,
        ...(isAdmin && { email: formData.email }),
        telefone: formData.telefone,
      });
      
      queryClient.invalidateQueries({ queryKey: ['user-profile'] });
      setEditMode(null);
      toast.success("Perfil atualizado com sucesso!");
    } catch (error) {
      console.error("Erro ao atualizar perfil:", error);
    }
  };

  const handleUpdatePassword = async () => {
    if (passwordData.newPassword !== passwordData.confirmPassword) {
      toast.error("As senhas não coincidem");
      return;
    }

    if (passwordData.newPassword.length < 8) {
      toast.error("A senha deve ter no mínimo 8 caracteres");
      return;
    }

    try {
      const { error } = await supabase.auth.updateUser({
        password: passwordData.newPassword,
      });

      if (error) throw error;

      toast.success("Senha atualizada com sucesso!");
      setPasswordData({ currentPassword: "", newPassword: "", confirmPassword: "" });
      setEditMode(null);
    } catch (error: any) {
      toast.error(error.message || "Erro ao atualizar senha");
    }
  };

  const isLoading = isLoadingProfile || isLoadingRole || isLoadingRoles;

  return (
    <header className="h-14 sm:h-16 bg-card border-b border-border px-4 sm:px-6 flex items-center justify-between">
      <div></div>
      
      <div className="flex items-center gap-2 sm:gap-4">
        {isLoading ? (
          <div className="text-right">
            <p className="text-sm font-medium text-muted-foreground">Carregando...</p>
          </div>
        ) : profile ? (
          <>
            <HoverCard openDelay={0} closeDelay={0}>
              <HoverCardTrigger asChild>
                <div className="flex items-center gap-3 cursor-pointer hover:opacity-80 transition-opacity">
                  <div className="text-right">
                    <p className="text-sm font-medium text-foreground">{formatNome(profile.nome)}</p>
                    <p className="text-xs text-muted-foreground">{getRolesLabel(roles)}</p>
                  </div>
                  <Avatar>
                    {profile.avatar && <AvatarImage src={profile.avatar} alt={profile.nome} />}
                    <AvatarFallback className="bg-primary text-primary-foreground">
                      {getInitials(profile.nome)}
                    </AvatarFallback>
                  </Avatar>
                </div>
              </HoverCardTrigger>
              <HoverCardContent className="w-80" align="end">
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <Avatar className="h-12 w-12">
                        {profile.avatar && <AvatarImage src={profile.avatar} alt={profile.nome} />}
                        <AvatarFallback className="bg-primary text-primary-foreground">
                          {getInitials(profile.nome)}
                        </AvatarFallback>
                      </Avatar>
                      <div>
                        <p className="font-semibold">{formatNome(profile.nome)}</p>
                        <p className="text-xs text-muted-foreground">{getRoleLabel(role)}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-1">
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={handleLogout}
                        className="h-8 w-8"
                      >
                        <LogOut className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={toggleTheme}
                        className="h-8 w-8"
                      >
                        {theme === 'light' ? (
                          <Moon className="h-4 w-4" />
                        ) : (
                          <Sun className="h-4 w-4" />
                        )}
                      </Button>
                    </div>
                  </div>

                  <Separator />

                  {editMode === 'profile' ? (
                    <div className="space-y-3">
                      <div>
                        <Label htmlFor="nome">Nome</Label>
                        <Input
                          id="nome"
                          value={formData.nome}
                          onChange={(e) => setFormData({ ...formData, nome: e.target.value })}
                          className="mt-1"
                        />
                      </div>
                      <div>
                        <Label htmlFor="email">Email</Label>
                        <Input
                          id="email"
                          type="email"
                          value={formData.email}
                          onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                          disabled={!isAdmin}
                          className="mt-1"
                        />
                        {!isAdmin && (
                          <p className="text-xs text-muted-foreground mt-1">
                            Apenas administradores podem alterar o email
                          </p>
                        )}
                      </div>
                      <div>
                        <Label htmlFor="telefone">Telefone</Label>
                        <Input
                          id="telefone"
                          value={formData.telefone}
                          onChange={(e) => setFormData({ ...formData, telefone: e.target.value })}
                          className="mt-1"
                        />
                      </div>
                      <div className="flex gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => {
                            setEditMode(null);
                            setFormData({
                              nome: profile.nome,
                              email: profile.email,
                              telefone: profile.telefone,
                            });
                          }}
                          className="flex-1"
                        >
                          Cancelar
                        </Button>
                        <Button
                          size="sm"
                          onClick={handleUpdateProfile}
                          disabled={updateProfile.isPending}
                          className="flex-1"
                        >
                          {updateProfile.isPending ? "Salvando..." : "Salvar"}
                        </Button>
                      </div>
                    </div>
                  ) : editMode === 'password' ? (
                    <div className="space-y-3">
                      <div>
                        <Label htmlFor="newPassword">Nova Senha</Label>
                        <Input
                          id="newPassword"
                          type="password"
                          value={passwordData.newPassword}
                          onChange={(e) => setPasswordData({ ...passwordData, newPassword: e.target.value })}
                          className="mt-1"
                        />
                      </div>
                      <div>
                        <Label htmlFor="confirmPassword">Confirmar Senha</Label>
                        <Input
                          id="confirmPassword"
                          type="password"
                          value={passwordData.confirmPassword}
                          onChange={(e) => setPasswordData({ ...passwordData, confirmPassword: e.target.value })}
                          className="mt-1"
                        />
                      </div>
                      <div className="flex gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => {
                            setEditMode(null);
                            setPasswordData({ currentPassword: "", newPassword: "", confirmPassword: "" });
                          }}
                          className="flex-1"
                        >
                          Cancelar
                        </Button>
                        <Button
                          size="sm"
                          onClick={handleUpdatePassword}
                          className="flex-1"
                        >
                          Atualizar Senha
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <div className="space-y-2">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => {
                          setFormData({
                            nome: profile.nome,
                            email: profile.email,
                            telefone: profile.telefone,
                          });
                          setEditMode('profile');
                        }}
                        className="w-full justify-start"
                      >
                        <Edit2 className="h-4 w-4 mr-2" />
                        Editar Perfil
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setEditMode('password')}
                        className="w-full justify-start"
                      >
                        <Lock className="h-4 w-4 mr-2" />
                        Trocar Senha
                      </Button>
                    </div>
                  )}
                </div>
              </HoverCardContent>
            </HoverCard>
          </>
        ) : null}
      </div>
    </header>
  );
}
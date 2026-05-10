import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@noctusai/seed/components/ui/dialog";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@noctusai/seed/components/ui/alert-dialog";
import { Button } from "@noctusai/seed/components/ui/button";
import { Input } from "@noctusai/seed/components/ui/input";
import { Label } from "@noctusai/seed/components/ui/label";
import { Avatar, AvatarFallback, AvatarImage } from "@noctusai/seed/components/ui/avatar";
import { User, Mail, Phone, Calendar, Edit2, X, Save, Key, Shield, Trash2 } from "lucide-react";
import { Profile } from "@/types";
import { formatDate } from "@/lib/utils";
import { useUpdateProfile, useDeleteProfile } from "@/hooks/useProfiles";
import { useRequisitarSenha } from "@/hooks/useRequisitarSenha";
import { useIsAdmin } from "@/hooks/useUserRole";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";

interface UsuarioDetalhesModalProps {
  usuario: Profile;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function UsuarioDetalhesModal({
  usuario,
  open,
  onOpenChange,
}: UsuarioDetalhesModalProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [formData, setFormData] = useState({
    nome: usuario.nome,
    telefone: usuario.telefone,
  });
  const [showPasswordDialog, setShowPasswordDialog] = useState(false);
  const [confirmationMethod, setConfirmationMethod] = useState<'email' | 'sms'>('email');
  const [showCodeDialog, setShowCodeDialog] = useState(false);
  const [confirmationCode, setConfirmationCode] = useState('');
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);

  const updateProfile = useUpdateProfile();
  const deleteProfile = useDeleteProfile();
  const requisitarSenha = useRequisitarSenha();
  const { isAdmin } = useIsAdmin();

  const handleEdit = () => {
    setIsEditing(true);
  };

  const handleCancel = () => {
    setIsEditing(false);
    setFormData({
      nome: usuario.nome,
      telefone: usuario.telefone,
    });
  };

  const handleSave = async () => {
    await updateProfile.mutateAsync({
      id: usuario.id,
      ...formData,
    });
    setIsEditing(false);
    // formData já reflete as alterações, não precisa fechar o modal
  };

  const handleInputChange = (field: string) => (
    e: React.ChangeEvent<HTMLInputElement>
  ) => {
    setFormData((prev) => ({ ...prev, [field]: e.target.value }));
  };

  const handleRequestPassword = () => {
    setShowPasswordDialog(true);
  };

  const handleConfirmMethod = async () => {
    setShowPasswordDialog(false);
    
    await requisitarSenha.mutateAsync({
      corretorId: usuario.id,
      corretorEmail: usuario.email,
      corretorNome: usuario.nome,
      confirmationMethod,
      step: 'request',
    });
    
    setShowCodeDialog(true);
  };

  const handleConfirmCode = async () => {
    await requisitarSenha.mutateAsync({
      corretorId: usuario.id,
      corretorEmail: usuario.email,
      corretorNome: usuario.nome,
      confirmationMethod,
      confirmationCode,
      step: 'confirm',
    });
    
    setShowCodeDialog(false);
    setConfirmationCode('');
    onOpenChange(false);
  };

  const handleDelete = async () => {
    await deleteProfile.mutateAsync(usuario.id);
    setShowDeleteDialog(false);
    onOpenChange(false);
  };

  const initials = usuario.nome
    .split(" ")
    .map((n) => n[0])
    .join("")
    .toUpperCase()
    .slice(0, 2);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-[95vw] sm:max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <User className="h-5 w-5 text-primary" />
            Detalhes do Usuário
          </DialogTitle>
          <DialogDescription>
            Visualize e edite as informações do usuário
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6">
          {isEditing ? (
            <form onSubmit={(e) => { e.preventDefault(); handleSave(); }} className="space-y-6">
              {/* Avatar e Nome */}
              <div className="flex items-center gap-4">
                <Avatar className="h-20 w-20">
                  <AvatarImage src={usuario.avatar} alt={usuario.nome} />
                  <AvatarFallback className="text-lg">{initials}</AvatarFallback>
                </Avatar>
                <div className="flex-1">
                  <div>
                    <Label htmlFor="nome">Nome</Label>
                    <Input
                      id="nome"
                      value={formData.nome}
                      onChange={handleInputChange("nome")}
                      className="mt-1"
                    />
                  </div>
                </div>
              </div>

              {/* Informações de Contato */}
              <div className="space-y-4">
                <div className="flex items-center gap-3 p-3 bg-muted/50 rounded-lg">
                  <Mail className="h-5 w-5 text-muted-foreground" />
                  <div>
                    <p className="text-sm text-muted-foreground">Email</p>
                    <p className="font-medium">{usuario.email}</p>
                  </div>
                </div>

                <div className="flex items-center gap-3 p-3 bg-muted/50 rounded-lg">
                  <Phone className="h-5 w-5 text-muted-foreground" />
                  <div className="flex-1">
                    <div>
                      <Label htmlFor="telefone">Telefone</Label>
                      <Input
                        id="telefone"
                        value={formData.telefone}
                        onChange={handleInputChange("telefone")}
                        className="mt-1"
                      />
                    </div>
                  </div>
                </div>
              </div>

              {/* Botões de Ação */}
              <div className="flex justify-between gap-2 pt-4 border-t">
                <Button
                  type="button"
                  variant="destructive"
                  onClick={() => setShowDeleteDialog(true)}
                  disabled={updateProfile.isPending}
                >
                  <Trash2 className="h-4 w-4 mr-2" />
                  Excluir
                </Button>
                <div className="flex gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    onClick={handleCancel}
                    disabled={updateProfile.isPending}
                  >
                    <X className="h-4 w-4 mr-2" />
                    Cancelar
                  </Button>
                  <Button
                    type="submit"
                    disabled={updateProfile.isPending}
                  >
                    <Save className="h-4 w-4 mr-2" />
                    {updateProfile.isPending ? "Salvando..." : "Salvar Alterações"}
                  </Button>
                </div>
              </div>
            </form>
          ) : (
            <>
              {/* Avatar e Nome */}
              <div className="flex items-center gap-4">
                <Avatar className="h-20 w-20">
                  <AvatarImage src={usuario.avatar} alt={formData.nome} />
                  <AvatarFallback className="text-lg">{initials}</AvatarFallback>
                </Avatar>
                <div className="flex-1">
                  <div>
                    <h3 className="text-2xl font-bold">{formData.nome}</h3>
                    <p className="text-sm text-muted-foreground mt-1">
                      ID: {usuario.id}
                    </p>
                  </div>
                </div>
              </div>

              {/* Informações de Contato */}
              <div className="space-y-4">
                <div className="flex items-center gap-3 p-3 bg-muted/50 rounded-lg">
                  <Mail className="h-5 w-5 text-muted-foreground" />
                  <div>
                    <p className="text-sm text-muted-foreground">Email</p>
                    <p className="font-medium">{usuario.email}</p>
                  </div>
                </div>

                <div className="flex items-center gap-3 p-3 bg-muted/50 rounded-lg">
                  <Phone className="h-5 w-5 text-muted-foreground" />
                  <div className="flex-1">
                    <>
                      <p className="text-sm text-muted-foreground">Telefone</p>
                      <p className="font-medium">{formData.telefone}</p>
                    </>
                  </div>
                </div>
              </div>

              {/* Informações Adicionais */}
              <div className="text-xs text-muted-foreground space-y-1 pt-4 border-t">
                <div className="flex items-center gap-2">
                  <Calendar className="h-3 w-3" />
                  <p>
                    Cadastrado em: {formatDate(usuario.created_at, true)}
                  </p>
                </div>
                <p className="ml-5">
                  Última atualização: {formatDate(usuario.updated_at, true)}
                </p>
              </div>

              {/* Botões de Ação */}
              <div className="flex justify-end gap-2 pt-4 border-t">
                <Button onClick={handleEdit}>
                  <Edit2 className="h-4 w-4 mr-2" />
                  Editar Usuário
                </Button>
                {isAdmin && (
                  <Button 
                    variant="destructive" 
                    onClick={handleRequestPassword}
                    disabled={requisitarSenha.isPending}
                  >
                    <Key className="h-4 w-4 mr-2" />
                    Requisitar Senha
                  </Button>
                )}
              </div>
            </>
          )}
        </div>
      </DialogContent>

      {/* Dialog de Confirmação de Método */}
      <AlertDialog open={showPasswordDialog} onOpenChange={setShowPasswordDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <Shield className="h-5 w-5 text-primary" />
              Confirmar Método de Verificação
            </AlertDialogTitle>
            <AlertDialogDescription>
              Para sua segurança, escolha como deseja receber o código de confirmação:
            </AlertDialogDescription>
          </AlertDialogHeader>
          
          <RadioGroup value={confirmationMethod} onValueChange={(value: 'email' | 'sms') => setConfirmationMethod(value)}>
            <div className="flex items-center space-x-2">
              <RadioGroupItem value="email" id="email" />
              <Label htmlFor="email" className="cursor-pointer">
                <div className="flex items-center gap-2">
                  <Mail className="h-4 w-4" />
                  <span>Email</span>
                </div>
              </Label>
            </div>
            <div className="flex items-center space-x-2">
              <RadioGroupItem value="sms" id="sms" />
              <Label htmlFor="sms" className="cursor-pointer">
                <div className="flex items-center gap-2">
                  <Phone className="h-4 w-4" />
                  <span>SMS</span>
                </div>
              </Label>
            </div>
          </RadioGroup>

          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction onClick={handleConfirmMethod}>
              Enviar Código
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Dialog de Confirmação de Código */}
      <AlertDialog open={showCodeDialog} onOpenChange={setShowCodeDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Confirmar Código</AlertDialogTitle>
            <AlertDialogDescription>
              Digite o código de 6 dígitos enviado por {confirmationMethod === 'email' ? 'email' : 'SMS'}:
            </AlertDialogDescription>
          </AlertDialogHeader>
          
          <form onSubmit={(e) => { e.preventDefault(); if (confirmationCode.length === 6) handleConfirmCode(); }}>
            <Input
              type="text"
              placeholder="000000"
              value={confirmationCode}
              onChange={(e) => setConfirmationCode(e.target.value)}
              maxLength={6}
              className="text-center text-2xl tracking-widest"
            />

            <AlertDialogFooter className="mt-4">
              <AlertDialogCancel type="button" onClick={() => {
                setConfirmationCode('');
                setShowCodeDialog(false);
              }}>
                Cancelar
              </AlertDialogCancel>
              <AlertDialogAction 
                type="submit"
                disabled={confirmationCode.length !== 6 || requisitarSenha.isPending}
              >
                {requisitarSenha.isPending ? 'Verificando...' : 'Confirmar'}
              </AlertDialogAction>
            </AlertDialogFooter>
          </form>
        </AlertDialogContent>
      </AlertDialog>

      {/* Dialog de Confirmação de Exclusão */}
      <AlertDialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2 text-destructive">
              <Trash2 className="h-5 w-5" />
              Confirmar Exclusão
            </AlertDialogTitle>
            <AlertDialogDescription>
              Tem certeza que deseja excluir o usuário <strong>{usuario.nome}</strong>?
              Esta ação é irreversível e todos os dados associados, incluindo metas e atividades, serão permanentemente removidos.
            </AlertDialogDescription>
          </AlertDialogHeader>
          
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction 
              onClick={handleDelete}
              disabled={deleteProfile.isPending}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {deleteProfile.isPending ? 'Excluindo...' : 'Excluir Usuário'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Dialog>
  );
}

import { useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@noctusai/seed/components/ui/dialog';
import { Button } from '@noctusai/seed/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@noctusai/seed/components/ui/select';
import { supabase } from '@noctusai/seed/infra';
import { toast } from 'sonner';
import { UserPlus } from 'lucide-react';

interface AdicionarRoleModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  userId: string;
  userName: string;
  currentRoles: string[];
  onSuccess: () => void;
}

export function AdicionarRoleModal({
  open,
  onOpenChange,
  userId,
  userName,
  currentRoles,
  onSuccess,
}: AdicionarRoleModalProps) {
  const [selectedRole, setSelectedRole] = useState<string>('');
  const [isLoading, setIsLoading] = useState(false);

  const availableRoles = ['admin', 'dev', 'corretor', 'coordenador'].filter(
    (role) => !currentRoles.includes(role)
  );

  const handleAddRole = async () => {
    if (!selectedRole) {
      toast.error('Selecione uma role');
      return;
    }

    setIsLoading(true);
    try {
      const { error } = await supabase
        .from('user_roles')
        .insert({
          user_id: userId,
          role: selectedRole as any,
        });

      if (error) throw error;

      toast.success('Role adicionada com sucesso');
      onSuccess();
      onOpenChange(false);
      setSelectedRole('');
    } catch (error: any) {
      console.error('Error adding role:', error);
      toast.error('Erro ao adicionar role', {
        description: error.message,
      });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <UserPlus className="h-5 w-5" />
            Adicionar Role
          </DialogTitle>
          <DialogDescription>
            Adicionar nova role para {userName}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          {availableRoles.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-4">
              Todas as roles já foram atribuídas a este usuário.
            </p>
          ) : (
            <>
              <div className="space-y-2">
                <label className="text-sm font-medium">Selecione a role</label>
                <Select value={selectedRole} onValueChange={setSelectedRole}>
                  <SelectTrigger>
                    <SelectValue placeholder="Selecione..." />
                  </SelectTrigger>
                  <SelectContent>
                    {availableRoles.map((role) => (
                      <SelectItem key={role} value={role}>
                        {role === 'admin' && 'Admin'}
                        {role === 'dev' && 'Dev'}
                        {role === 'corretor' && 'Corretor'}
                        {role === 'coordenador' && 'Coordenador'}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="flex gap-2 justify-end">
                <Button
                  variant="outline"
                  onClick={() => onOpenChange(false)}
                  disabled={isLoading}
                >
                  Cancelar
                </Button>
                <Button
                  onClick={handleAddRole}
                  disabled={isLoading || !selectedRole}
                >
                  {isLoading ? 'Adicionando...' : 'Adicionar'}
                </Button>
              </div>
            </>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

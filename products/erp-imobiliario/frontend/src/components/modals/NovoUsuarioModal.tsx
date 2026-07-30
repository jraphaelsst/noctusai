import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@noctusai/seed/components/ui/dialog";
import { Button } from "@noctusai/seed/components/ui/button";
import { Input } from "@noctusai/seed/components/ui/input";
import { Label } from "@noctusai/seed/components/ui/label";
import { UserPlus, Eye, EyeOff } from "lucide-react";
import { useCreateProfile } from "@/hooks/useProfiles";
import { corretorSchema } from "@/lib/validations";
import { formatPhoneNumber, normalizePhone } from "@/lib/utils";
import { toast } from "sonner";

interface NovoUsuarioModalProps {
  onSuccess?: () => void;
}

export function NovoUsuarioModal({ onSuccess }: NovoUsuarioModalProps) {
  const [open, setOpen] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [formData, setFormData] = useState({
    nome: "",
    email: "",
    telefone: "",
    password: "",
    confirmPassword: "",
  });
  const [errors, setErrors] = useState<Record<string, string>>({});

  const createProfile = useCreateProfile();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    // Validate form data
    const result = corretorSchema.safeParse(formData);
    
    if (!result.success) {
      const fieldErrors: Record<string, string> = {};
      result.error.errors.forEach((err) => {
        if (err.path[0]) {
          fieldErrors[err.path[0].toString()] = err.message;
        }
      });
      setErrors(fieldErrors);
      toast.error('Erro de validação', {
        description: 'Verifique os campos do formulário',
      });
      return;
    }
    
    setErrors({});
    // The masked value is for the EYE, never for storage: submitting
    // "(11) 99999-9999" wrote a third phone format into the database, one that
    // compares equal to neither the canonical form nor a WhatsApp id. Fall
    // back to what was typed when it cannot be canonicalized — refusing a
    // valid-looking number the user can see is worse than storing it for a
    // human to correct.
    await createProfile.mutateAsync({
      ...formData,
      telefone: normalizePhone(formData.telefone) ?? formData.telefone,
    });
    
    setFormData({
      nome: "",
      email: "",
      telefone: "",
      password: "",
      confirmPassword: "",
    });
    setShowPassword(false);
    setShowConfirmPassword(false);
    setOpen(false);
    onSuccess?.();
  };

  const formatNome = (value: string) => {
    return value
      .toLowerCase()
      .split(' ')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ');
  };

  const handleInputChange = (field: string) => (
    e: React.ChangeEvent<HTMLInputElement>
  ) => {
    let value = e.target.value;
    
    if (field === "telefone") {
      value = formatPhoneNumber(value);
    } else if (field === "nome") {
      value = formatNome(value);
    }
    
    setFormData((prev) => ({ ...prev, [field]: value }));
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>
          <UserPlus className="h-4 w-4 mr-2" />
          Novo Usuário
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-[95vw] sm:max-w-md max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Cadastrar Novo Usuário</DialogTitle>
          <DialogDescription>
            Preencha os dados para criar um novo usuário da plataforma
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="nome">Nome *</Label>
            <Input
              id="nome"
              value={formData.nome}
              onChange={handleInputChange("nome")}
              placeholder="Digite o nome"
              required
              className={errors.nome ? "border-destructive" : ""}
            />
            {errors.nome && (
              <p className="text-sm text-destructive">{errors.nome}</p>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="email">Email *</Label>
            <Input
              id="email"
              type="email"
              value={formData.email}
              onChange={handleInputChange("email")}
              placeholder="usuario@exemplo.com"
              required
              className={errors.email ? "border-destructive" : ""}
            />
            {errors.email && (
              <p className="text-sm text-destructive">{errors.email}</p>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="telefone">Telefone *</Label>
            <Input
              id="telefone"
              value={formData.telefone}
              onChange={handleInputChange("telefone")}
              placeholder="(00) 00000-0000"
              required
              className={errors.telefone ? "border-destructive" : ""}
            />
            {errors.telefone && (
              <p className="text-sm text-destructive">{errors.telefone}</p>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="password">Senha *</Label>
            <div className="relative">
              <Input
                id="password"
                type={showPassword ? "text" : "password"}
                value={formData.password}
                onChange={handleInputChange("password")}
                placeholder="Mínimo 6 caracteres"
                required
                minLength={6}
                className={`pr-10 ${errors.password ? "border-destructive" : ""}`}
              />
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="absolute right-0 top-0 h-full px-3 hover:bg-transparent"
                onClick={() => setShowPassword(!showPassword)}
                aria-label={showPassword ? "Ocultar senha" : "Mostrar senha"}
              >
                {showPassword ? (
                  <EyeOff className="h-4 w-4 text-muted-foreground" />
                ) : (
                  <Eye className="h-4 w-4 text-muted-foreground" />
                )}
              </Button>
            </div>
            {errors.password && (
              <p className="text-sm text-destructive">{errors.password}</p>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="confirmPassword">Confirmar Senha *</Label>
            <div className="relative">
              <Input
                id="confirmPassword"
                type={showConfirmPassword ? "text" : "password"}
                value={formData.confirmPassword}
                onChange={handleInputChange("confirmPassword")}
                placeholder="Digite a senha novamente"
                required
                minLength={6}
                className={`pr-10 ${errors.confirmPassword ? "border-destructive" : ""}`}
              />
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="absolute right-0 top-0 h-full px-3 hover:bg-transparent"
                onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                aria-label={showConfirmPassword ? "Ocultar confirmação de senha" : "Mostrar confirmação de senha"}
              >
                {showConfirmPassword ? (
                  <EyeOff className="h-4 w-4 text-muted-foreground" />
                ) : (
                  <Eye className="h-4 w-4 text-muted-foreground" />
                )}
              </Button>
            </div>
            {errors.confirmPassword && (
              <p className="text-sm text-destructive">{errors.confirmPassword}</p>
            )}
          </div>

          <div className="flex justify-end gap-2 pt-4">
            <Button
              type="button"
              variant="outline"
              onClick={() => setOpen(false)}
              disabled={createProfile.isPending}
            >
              Cancelar
            </Button>
            <Button
              type="submit"
              disabled={
                createProfile.isPending ||
                !formData.nome ||
                !formData.email ||
                !formData.telefone ||
                !formData.password ||
                !formData.confirmPassword ||
                formData.password !== formData.confirmPassword
              }
            >
              {createProfile.isPending ? "Cadastrando..." : "Cadastrar"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

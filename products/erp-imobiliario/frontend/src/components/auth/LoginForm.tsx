import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { supabase } from '@/integrations/supabase/client';
import { toast } from 'sonner';
import { loginSchema, signUpSchema } from '@/lib/validations';
import { Eye, EyeOff } from 'lucide-react';
import { useRecuperarSenha } from '@/hooks/useRecuperarSenha';
import { formatPhoneNumber, cleanPhoneNumber } from '@/lib/utils';

interface LoginFormProps {
  onToggleMode: () => void;
  isSignUp: boolean;
}

export function LoginForm({ onToggleMode, isSignUp }: LoginFormProps) {
  const [nome, setNome] = useState('');
  const [email, setEmail] = useState('');
  const [telefone, setTelefone] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [emailTouched, setEmailTouched] = useState(false);
  const [showRecuperarSenhaDialog, setShowRecuperarSenhaDialog] = useState(false);
  const [recuperarEmail, setRecuperarEmail] = useState('');
  const recuperarSenhaMutation = useRecuperarSenha();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    // Validate form data
    const schema = isSignUp ? signUpSchema : loginSchema;
    const data = isSignUp ? { nome, email, telefone, password, confirmPassword } : { email, password };
    const result = schema.safeParse(data);
    
    if (!result.success) {
      const fieldErrors: Record<string, string> = {};
      result.error.errors.forEach((err) => {
        if (err.path[0]) {
          fieldErrors[err.path[0].toString()] = err.message;
        }
      });
      setErrors(fieldErrors);
      return;
    }
    
    setErrors({});
    setLoading(true);

    try {
      if (isSignUp) {
        const { error } = await supabase.auth.signUp({
          email: email.trim(),
          password,
          options: {
            emailRedirectTo: `${window.location.origin}/`,
            data: {
              nome: nome.trim(),
              telefone: cleanPhoneNumber(telefone),
            },
          },
        });
        
        if (error) throw error;
        
        toast.success('Cadastro realizado!', { description: 'Verifique seu email para confirmar a conta.' });
      } else {
        const { error } = await supabase.auth.signInWithPassword({
          email: email.trim(),
          password,
        });
        
        if (error) throw error;
        
        toast.success('Login realizado!', { description: 'Bem-vindo de volta!' });
      }
    } catch (error: any) {
      const errorMessage = error.message.includes('Invalid login credentials')
        ? 'Email ou senha incorretos'
        : error.message.includes('already registered')
        ? 'Este email já está cadastrado'
        : 'Erro ao processar sua solicitação. Tente novamente.';
      
      toast.error('Erro', { description: errorMessage });
    } finally {
      setLoading(false);
    }
  };

  const formatNome = (value: string) => {
    return value
      .toLowerCase()
      .split(' ')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ');
  };

  const validateEmail = (email: string): boolean => {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email.trim());
  };

  const handleEmailChange = (value: string) => {
    setEmail(value);
    if (isSignUp && emailTouched && value.trim()) {
      if (!validateEmail(value)) {
        setErrors(prev => ({ ...prev, email: 'Email inválido' }));
      } else {
        setErrors(prev => {
          const { email, ...rest } = prev;
          return rest;
        });
      }
    }
  };

  const handleRecuperarSenha = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!recuperarEmail.trim()) {
      toast.error('Erro', { description: 'Por favor, informe seu email' });
      return;
    }

    await recuperarSenhaMutation.mutateAsync({ email: recuperarEmail });
    setShowRecuperarSenhaDialog(false);
    setRecuperarEmail('');
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-background to-muted p-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle className="text-2xl text-center">
            {isSignUp ? 'Criar Conta' : 'Entrar'}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            {isSignUp && (
              <div className="space-y-2">
                <Label htmlFor="nome">Nome</Label>
                <Input
                  id="nome"
                  type="text"
                  value={nome}
                  onChange={(e) => setNome(formatNome(e.target.value))}
                  placeholder="Digite seu nome"
                  required
                  disabled={loading}
                  className={errors.nome ? "border-destructive" : ""}
                />
                {errors.nome && (
                  <p className="text-sm text-destructive">{errors.nome}</p>
                )}
              </div>
            )}

            {isSignUp && (
              <div className="space-y-2">
                <Label htmlFor="telefone">Telefone</Label>
                <Input
                  id="telefone"
                  type="text"
                  value={telefone}
                  onChange={(e) => setTelefone(formatPhoneNumber(e.target.value))}
                  placeholder="(00) 00000-0000"
                  required
                  disabled={loading}
                  className={errors.telefone ? "border-destructive" : ""}
                />
                {errors.telefone && (
                  <p className="text-sm text-destructive">{errors.telefone}</p>
                )}
              </div>
            )}
            
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                value={email}
                onChange={(e) => handleEmailChange(e.target.value)}
                onBlur={() => isSignUp && setEmailTouched(true)}
                placeholder="seu@email.com"
                required
                disabled={loading}
                className={errors.email ? "border-destructive" : ""}
              />
              {errors.email && (
                <p className="text-sm text-destructive">{errors.email}</p>
              )}
            </div>
            
            <div className="space-y-2">
              <Label htmlFor="password">Senha</Label>
              <div className="relative">
                <Input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Mínimo 8 caracteres"
                  required
                  disabled={loading}
                  minLength={8}
                  className={errors.password ? "border-destructive pr-10" : "pr-10"}
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="absolute right-0 top-0 h-full px-3 hover:bg-transparent"
                  onClick={() => setShowPassword(!showPassword)}
                  disabled={loading}
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
            
            {isSignUp && (
              <div className="space-y-2">
                <Label htmlFor="confirmPassword">Confirmar Senha</Label>
                <div className="relative">
                  <Input
                    id="confirmPassword"
                    type={showConfirmPassword ? "text" : "password"}
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    placeholder="Digite a senha novamente"
                    required
                    disabled={loading}
                    minLength={8}
                    className={errors.confirmPassword ? "border-destructive pr-10" : "pr-10"}
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="absolute right-0 top-0 h-full px-3 hover:bg-transparent"
                    onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                    disabled={loading}
                    aria-label={showConfirmPassword ? "Ocultar senha" : "Mostrar senha"}
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
            )}
            
            <Button 
              type="submit" 
              className="w-full" 
              disabled={
                loading || 
                (isSignUp && (
                  !nome.trim() || 
                  !email.trim() || 
                  !password || 
                  !confirmPassword || 
                  password !== confirmPassword
                ))
              }
            >
              {loading ? 'Carregando...' : (isSignUp ? 'Criar Conta' : 'Entrar')}
            </Button>
          </form>
          
          <div className="mt-4 text-center space-y-2">
            <Button
              variant="link"
              onClick={onToggleMode}
              disabled={loading}
            >
              {isSignUp 
                ? 'Já tem uma conta? Faça login' 
                : 'Não tem conta? Cadastre-se'
              }
            </Button>
            
            {!isSignUp && (
              <div>
                <Button
                  variant="link"
                  onClick={() => {
                    setRecuperarEmail(email);
                    setShowRecuperarSenhaDialog(true);
                  }}
                  disabled={loading}
                  className="text-sm"
                >
                  Esqueci minha senha
                </Button>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      <Dialog open={showRecuperarSenhaDialog} onOpenChange={setShowRecuperarSenhaDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Recuperar Senha</DialogTitle>
            <DialogDescription>
              Informe seu email cadastrado. Você receberá instruções para recuperar sua senha.
            </DialogDescription>
          </DialogHeader>
          
          <form onSubmit={handleRecuperarSenha} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="recuperar-email">Email</Label>
              <Input
                id="recuperar-email"
                type="email"
                value={recuperarEmail}
                onChange={(e) => setRecuperarEmail(e.target.value)}
                placeholder="seu@email.com"
                required
                disabled={recuperarSenhaMutation.isPending}
              />
            </div>
            
            <div className="flex gap-2 justify-end">
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  setShowRecuperarSenhaDialog(false);
                  setRecuperarEmail('');
                }}
                disabled={recuperarSenhaMutation.isPending}
              >
                Cancelar
              </Button>
              <Button type="submit" disabled={recuperarSenhaMutation.isPending}>
                {recuperarSenhaMutation.isPending ? 'Enviando...' : 'Recuperar Senha'}
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
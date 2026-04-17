import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { supabase } from '@noctusai/seed/infra';
import { toast } from "sonner";
import { PublicLayout } from "@/components/layout/PublicLayout";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Heart, Users, Building2, UserCircle, ArrowLeft, Loader2, CheckCircle2, Eye, EyeOff } from "lucide-react";
import { cn } from "@/lib/utils";

type UserRole = "paciente" | "terapeuta" | "clinica";

// ── Schemas per role ────────────────────────────────────────

const baseSchema = z.object({
  nome: z.string().min(2, "Nome deve ter no minimo 2 caracteres"),
  email: z.string().email("Email invalido"),
  password: z.string().min(8, "Senha deve ter no minimo 8 caracteres"),
  confirmar_senha: z.string(),
}).refine((data) => data.password === data.confirmar_senha, {
  message: "As senhas nao coincidem",
  path: ["confirmar_senha"],
});

const patientSchema = baseSchema.and(z.object({
  telefone: z.string().optional(),
}));

const therapistSchema = baseSchema.and(z.object({
  crp: z.string().min(4, "CRP invalido"),
  bio: z.string().min(10, "Bio deve ter no minimo 10 caracteres").optional().or(z.literal("")),
}));

const clinicSchema = baseSchema.and(z.object({
  nome_clinica: z.string().min(2, "Nome da clinica obrigatorio"),
  cnpj: z.string().min(14, "CNPJ invalido"),
  responsavel: z.string().min(2, "Responsavel obrigatorio"),
  telefone: z.string().min(10, "Telefone obrigatorio"),
}));

type PatientForm = z.infer<typeof patientSchema>;
type TherapistForm = z.infer<typeof therapistSchema>;
type ClinicForm = z.infer<typeof clinicSchema>;

// ── Role cards ──────────────────────────────────────────────

const roleCards: { role: UserRole; icon: React.ElementType; title: string; description: string }[] = [
  {
    role: "paciente",
    icon: UserCircle,
    title: "Sou Paciente",
    description: "Quero encontrar um terapeuta e agendar sessoes",
  },
  {
    role: "terapeuta",
    icon: Users,
    title: "Sou Terapeuta",
    description: "Quero oferecer meus servicos e gerenciar minha agenda",
  },
  {
    role: "clinica",
    icon: Building2,
    title: "Sou uma Clinica",
    description: "Quero cadastrar minha clinica e gerenciar terapeutas",
  },
];

function PasswordField({
  id,
  label,
  register,
  error,
}: {
  id: string;
  label: string;
  register: React.InputHTMLAttributes<HTMLInputElement> & { ref: React.Ref<HTMLInputElement> };
  error?: string;
}) {
  const [visible, setVisible] = useState(false);
  return (
    <div className="space-y-2">
      <Label htmlFor={id}>{label}</Label>
      <div className="relative">
        <Input id={id} type={visible ? "text" : "password"} {...register} className="pr-10" />
        <button
          type="button"
          onClick={() => setVisible((v) => !v)}
          className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
          tabIndex={-1}
        >
          {visible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
        </button>
      </div>
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  );
}

export default function Register() {
  const navigate = useNavigate();
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [selectedRole, setSelectedRole] = useState<UserRole | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  // Use separate forms per role
  const patientForm = useForm<PatientForm>({ resolver: zodResolver(patientSchema) });
  const therapistForm = useForm<TherapistForm>({ resolver: zodResolver(therapistSchema) });
  const clinicForm = useForm<ClinicForm>({ resolver: zodResolver(clinicSchema) });

  const handleRoleSelect = (role: UserRole) => {
    setSelectedRole(role);
    setStep(2);
  };

  const handleBack = () => {
    if (step === 2) {
      setStep(1);
      setSelectedRole(null);
    }
  };

  const doSignUp = async (email: string, password: string, metadata: Record<string, unknown>) => {
    setIsLoading(true);
    try {
      const { error } = await supabase.auth.signUp({
        email,
        password,
        options: {
          data: {
            role: selectedRole,
            ...metadata,
          },
        },
      });

      if (error) {
        toast.error("Erro ao criar conta", { description: error.message });
        return;
      }

      setStep(3);
    } catch (err) {
      toast.error("Erro ao criar conta", {
        description: err instanceof Error ? err.message : "Failed to fetch",
      });
    } finally {
      setIsLoading(false);
    }
  };

  const onPatientSubmit = (data: PatientForm) => {
    doSignUp(data.email, data.password, { nome: data.nome, telefone: data.telefone });
  };

  const onTherapistSubmit = (data: TherapistForm) => {
    doSignUp(data.email, data.password, { nome: data.nome, crp: data.crp, bio: data.bio });
  };

  const onClinicSubmit = (data: ClinicForm) => {
    doSignUp(data.email, data.password, {
      nome: data.nome,
      nome_clinica: data.nome_clinica,
      cnpj: data.cnpj,
      responsavel: data.responsavel,
      telefone: data.telefone,
    });
  };

  const needsApproval = selectedRole === "terapeuta" || selectedRole === "clinica";

  return (
    <PublicLayout>
      <div className="flex items-center justify-center min-h-[calc(100vh-64px)] p-4">
        <Card className="w-full max-w-lg">
          <CardHeader className="text-center">
            <div className="flex justify-center mb-2">
              <Heart className="h-10 w-10 text-primary" />
            </div>
            <CardTitle className="text-2xl">
              {step === 1 && "Criar Conta"}
              {step === 2 && "Preencher Dados"}
              {step === 3 && "Conta Criada!"}
            </CardTitle>
            <CardDescription>
              {step === 1 && "Escolha seu perfil para comecar"}
              {step === 2 && `Cadastro como ${selectedRole === "paciente" ? "paciente" : selectedRole === "terapeuta" ? "terapeuta" : "clinica"}`}
              {step === 3 && (needsApproval ? "Aguardando aprovacao da plataforma." : "Voce ja pode acessar sua conta.")}
            </CardDescription>
          </CardHeader>

          <CardContent>
            {/* Step 1: Role selection */}
            {step === 1 && (
              <div className="grid gap-3">
                {roleCards.map(({ role, icon: Icon, title, description }) => (
                  <button
                    key={role}
                    onClick={() => handleRoleSelect(role)}
                    className={cn(
                      "flex items-start gap-4 p-4 rounded-lg border border-border text-left transition-colors hover:bg-accent hover:border-primary/50"
                    )}
                  >
                    <div className="p-2 rounded-md bg-primary/10">
                      <Icon className="h-6 w-6 text-primary" />
                    </div>
                    <div>
                      <p className="font-medium">{title}</p>
                      <p className="text-sm text-muted-foreground">{description}</p>
                    </div>
                  </button>
                ))}
              </div>
            )}

            {/* Step 2: Role-specific form */}
            {step === 2 && selectedRole === "paciente" && (
              <form onSubmit={patientForm.handleSubmit(onPatientSubmit)} className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="nome">Nome completo</Label>
                  <Input id="nome" {...patientForm.register("nome")} />
                  {patientForm.formState.errors.nome && (
                    <p className="text-xs text-destructive">{patientForm.formState.errors.nome.message}</p>
                  )}
                </div>
                <div className="space-y-2">
                  <Label htmlFor="email">Email</Label>
                  <Input id="email" type="email" {...patientForm.register("email")} />
                  {patientForm.formState.errors.email && (
                    <p className="text-xs text-destructive">{patientForm.formState.errors.email.message}</p>
                  )}
                </div>
                <PasswordField id="password" label="Senha" register={patientForm.register("password")} error={patientForm.formState.errors.password?.message} />
                <PasswordField id="confirmar_senha" label="Confirmar Senha" register={patientForm.register("confirmar_senha")} error={patientForm.formState.errors.confirmar_senha?.message} />
                <div className="space-y-2">
                  <Label htmlFor="telefone">Telefone (opcional)</Label>
                  <Input id="telefone" {...patientForm.register("telefone")} placeholder="(11) 99999-9999" />
                </div>
                <div className="flex gap-2">
                  <Button type="button" variant="outline" onClick={handleBack} className="flex-1">
                    <ArrowLeft className="h-4 w-4 mr-1" /> Voltar
                  </Button>
                  <Button type="submit" className="flex-1" disabled={isLoading}>
                    {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Criar Conta"}
                  </Button>
                </div>
              </form>
            )}

            {step === 2 && selectedRole === "terapeuta" && (
              <form onSubmit={therapistForm.handleSubmit(onTherapistSubmit)} className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="nome">Nome completo</Label>
                  <Input id="nome" {...therapistForm.register("nome")} />
                  {therapistForm.formState.errors.nome && (
                    <p className="text-xs text-destructive">{therapistForm.formState.errors.nome.message}</p>
                  )}
                </div>
                <div className="space-y-2">
                  <Label htmlFor="email">Email</Label>
                  <Input id="email" type="email" {...therapistForm.register("email")} />
                  {therapistForm.formState.errors.email && (
                    <p className="text-xs text-destructive">{therapistForm.formState.errors.email.message}</p>
                  )}
                </div>
                <PasswordField id="password" label="Senha" register={therapistForm.register("password")} error={therapistForm.formState.errors.password?.message} />
                <PasswordField id="confirmar_senha" label="Confirmar Senha" register={therapistForm.register("confirmar_senha")} error={therapistForm.formState.errors.confirmar_senha?.message} />
                <div className="space-y-2">
                  <Label htmlFor="crp">CRP</Label>
                  <Input id="crp" {...therapistForm.register("crp")} placeholder="06/123456" />
                  {therapistForm.formState.errors.crp && (
                    <p className="text-xs text-destructive">{therapistForm.formState.errors.crp.message}</p>
                  )}
                </div>
                <div className="space-y-2">
                  <Label htmlFor="bio">Bio (opcional)</Label>
                  <Input id="bio" {...therapistForm.register("bio")} placeholder="Fale um pouco sobre voce..." />
                </div>
                <div className="flex gap-2">
                  <Button type="button" variant="outline" onClick={handleBack} className="flex-1">
                    <ArrowLeft className="h-4 w-4 mr-1" /> Voltar
                  </Button>
                  <Button type="submit" className="flex-1" disabled={isLoading}>
                    {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Criar Conta"}
                  </Button>
                </div>
              </form>
            )}

            {step === 2 && selectedRole === "clinica" && (
              <form onSubmit={clinicForm.handleSubmit(onClinicSubmit)} className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="nome">Seu nome</Label>
                  <Input id="nome" {...clinicForm.register("nome")} />
                  {clinicForm.formState.errors.nome && (
                    <p className="text-xs text-destructive">{clinicForm.formState.errors.nome.message}</p>
                  )}
                </div>
                <div className="space-y-2">
                  <Label htmlFor="email">Email</Label>
                  <Input id="email" type="email" {...clinicForm.register("email")} />
                  {clinicForm.formState.errors.email && (
                    <p className="text-xs text-destructive">{clinicForm.formState.errors.email.message}</p>
                  )}
                </div>
                <PasswordField id="password" label="Senha" register={clinicForm.register("password")} error={clinicForm.formState.errors.password?.message} />
                <PasswordField id="confirmar_senha" label="Confirmar Senha" register={clinicForm.register("confirmar_senha")} error={clinicForm.formState.errors.confirmar_senha?.message} />
                <div className="space-y-2">
                  <Label htmlFor="nome_clinica">Nome da Clinica</Label>
                  <Input id="nome_clinica" {...clinicForm.register("nome_clinica")} />
                  {clinicForm.formState.errors.nome_clinica && (
                    <p className="text-xs text-destructive">{clinicForm.formState.errors.nome_clinica.message}</p>
                  )}
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="cnpj">CNPJ</Label>
                    <Input id="cnpj" {...clinicForm.register("cnpj")} placeholder="00.000.000/0000-00" />
                    {clinicForm.formState.errors.cnpj && (
                      <p className="text-xs text-destructive">{clinicForm.formState.errors.cnpj.message}</p>
                    )}
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="telefone">Telefone</Label>
                    <Input id="telefone" {...clinicForm.register("telefone")} placeholder="(11) 3333-3333" />
                    {clinicForm.formState.errors.telefone && (
                      <p className="text-xs text-destructive">{clinicForm.formState.errors.telefone.message}</p>
                    )}
                  </div>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="responsavel">Responsavel</Label>
                  <Input id="responsavel" {...clinicForm.register("responsavel")} />
                  {clinicForm.formState.errors.responsavel && (
                    <p className="text-xs text-destructive">{clinicForm.formState.errors.responsavel.message}</p>
                  )}
                </div>
                <div className="flex gap-2">
                  <Button type="button" variant="outline" onClick={handleBack} className="flex-1">
                    <ArrowLeft className="h-4 w-4 mr-1" /> Voltar
                  </Button>
                  <Button type="submit" className="flex-1" disabled={isLoading}>
                    {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Criar Conta"}
                  </Button>
                </div>
              </form>
            )}

            {/* Step 3: Success */}
            {step === 3 && (
              <div className="text-center space-y-4 py-4">
                <CheckCircle2 className="h-16 w-16 text-green-500 mx-auto" />
                <p className="text-muted-foreground">
                  {needsApproval
                    ? "Sua conta foi criada e esta aguardando aprovacao. Voce recebera um email quando for aprovada."
                    : "Sua conta foi criada com sucesso! Voce ja pode fazer login."}
                </p>
                <Button onClick={() => navigate("/login")} className="w-full">
                  Ir para Login
                </Button>
              </div>
            )}
          </CardContent>

          {step !== 3 && (
            <CardFooter className="justify-center">
              <p className="text-sm text-muted-foreground">
                Ja tem conta?{" "}
                <Link to="/login" className="text-primary hover:underline font-medium">
                  Entrar
                </Link>
              </p>
            </CardFooter>
          )}
        </Card>
      </div>
    </PublicLayout>
  );
}

import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Plus, Target } from "lucide-react";
import { Textarea } from "@/components/ui/textarea";
import { useAuthStore, api } from '@noctusai/seed/infra';
import { useCreateMeta } from "@/hooks/useMetas";
import { TipoMeta, CategoriaMeta } from "@/types";
import { useIsAdmin } from "@/hooks/useUserRole";
import { useProfiles } from "@/hooks/useProfiles";
import { categoriasDisponiveis, categoriaLabels } from "@/lib/categorias";

interface NovaMetaModalProps {
  onSuccess?: () => void;
}

export function NovaMetaModal({ onSuccess }: NovaMetaModalProps) {
  const [open, setOpen] = useState(false);
  const { user } = useAuthStore();
  const createMeta = useCreateMeta();
  const { isAdmin } = useIsAdmin();
  const { data: profiles, isLoading: isLoadingProfiles } = useProfiles();

  const [formData, setFormData] = useState({
    usuario_id: user?.id || '',
    tipo: 'diaria' as TipoMeta, // Não-admins só podem criar metas diárias
    categoria: 'captacao_imoveis' as CategoriaMeta, // Primeira categoria da lista
    categoria_custom: '',
    meta_pretendida: '' as number | string,
    detalhes: '',
    nome: '',
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!formData.usuario_id) {
      return;
    }

    const meta_pretendida = typeof formData.meta_pretendida === 'string' 
      ? parseInt(formData.meta_pretendida) || 0 
      : formData.meta_pretendida;

    // Calcular data_prazo automaticamente baseado no tipo de meta
    const prazoResult = await api.get("/api/metas/data-prazo", { tipo: formData.tipo });
    const dataPrazo = prazoResult.data.data_prazo;

    await createMeta.mutateAsync({
      ...formData,
      meta_pretendida,
      usuario_id: formData.usuario_id,
      categoria_custom: formData.categoria === 'outro' ? formData.categoria_custom : undefined,
      detalhes: formData.detalhes || undefined,
      nome: formData.nome || undefined,
      data_prazo: dataPrazo,
    });

    setFormData({
      usuario_id: user?.id || '',
      tipo: 'diaria',
      categoria: 'captacao_imoveis',
      categoria_custom: '',
      meta_pretendida: '',
      detalhes: '',
      nome: '',
    });
    setOpen(false);
    onSuccess?.();
  };

  const handleInputChange = (field: string) => (
    e: React.ChangeEvent<HTMLInputElement>
  ) => {
    let value: string | number = e.target.value;
    
    if (field === 'meta_pretendida') {
      // Permitir string vazia para poder apagar
      value = e.target.value === '' ? '' : e.target.value;
    }
    
    setFormData((prev) => ({ ...prev, [field]: value }));
  };

  const handleSelectChange = (field: string) => (value: string) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline">
          <Plus className="h-4 w-4 mr-2" />
          Nova Meta
        </Button>
      </DialogTrigger>

      <DialogContent className="max-w-[95vw] sm:max-w-md max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Target className="h-5 w-5 text-primary" />
            Cadastrar Nova Meta
          </DialogTitle>
          <DialogDescription>
            Crie uma nova meta pessoal para acompanhar seu desempenho
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="usuario">Usuário *</Label>
            {isAdmin ? (
              <Select
                value={formData.usuario_id}
                onValueChange={handleSelectChange('usuario_id')}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Selecione o usuário" />
                </SelectTrigger>
                <SelectContent>
                  {isLoadingProfiles ? (
                    <SelectItem value="loading" disabled>Carregando...</SelectItem>
                  ) : (
                    profiles?.map((profile) => (
                      <SelectItem key={profile.id} value={profile.id}>
                        {profile.nome} - {profile.email}
                      </SelectItem>
                    ))
                  )}
                </SelectContent>
              </Select>
            ) : (
              <>
                <Input
                  id="usuario"
                  value={user?.email || 'Usuário atual'}
                  disabled
                  className="bg-muted"
                />
                <p className="text-xs text-muted-foreground">
                  A meta será criada para o seu usuário
                </p>
              </>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="tipo">Tipo de Meta *</Label>
            <Select
              value={formData.tipo}
              onValueChange={handleSelectChange('tipo')}
              disabled={!isAdmin}
            >
              <SelectTrigger className={!isAdmin ? "bg-muted" : ""}>
                <SelectValue placeholder="Selecione a periodicidade" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="diaria">Diária</SelectItem>
                <SelectItem value="semanal">Semanal</SelectItem>
                <SelectItem value="mensal">Mensal</SelectItem>
                <SelectItem value="anual">Anual</SelectItem>
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              {isAdmin 
                ? "Escolha o tipo de meta que deseja criar"
                : "Apenas metas diárias podem ser criadas manualmente por não-admins"
              }
            </p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="categoria">Categoria de Meta *</Label>
            <Select
              value={formData.categoria}
              onValueChange={handleSelectChange('categoria')}
            >
              <SelectTrigger>
                <SelectValue placeholder="Selecione a categoria" />
              </SelectTrigger>
              <SelectContent>
                {categoriasDisponiveis.map(cat => (
                  <SelectItem key={cat} value={cat}>
                    {categoriaLabels[cat]}
                  </SelectItem>
                ))}
                <SelectItem value="outro">Outro</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {formData.categoria === 'outro' && (
            <div className="space-y-2">
              <Label htmlFor="categoria_custom">Nome da Categoria Personalizada *</Label>
              <Input
                id="categoria_custom"
                value={formData.categoria_custom}
                onChange={handleInputChange('categoria_custom')}
                placeholder="Ex: Networking"
                required
              />
            </div>
          )}

          <div className="space-y-2">
            <Label htmlFor="meta_pretendida">Meta Pretendida *</Label>
            <Input
              id="meta_pretendida"
              type="number"
              min="1"
              value={formData.meta_pretendida}
              onChange={handleInputChange('meta_pretendida')}
              placeholder="Ex: 10"
              required
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="nome">Nome da Meta (Opcional)</Label>
            <Input
              id="nome"
              value={formData.nome}
              onChange={handleInputChange('nome')}
              placeholder="Ex: Captação Q1 2025"
              maxLength={100}
            />
            <p className="text-xs text-muted-foreground">
              Dê um nome personalizado para esta meta
            </p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="detalhes">Detalhes (Opcional)</Label>
            <Textarea
              id="detalhes"
              value={formData.detalhes}
              onChange={(e) => setFormData(prev => ({ ...prev, detalhes: e.target.value }))}
              placeholder="Descreva os detalhes desta meta..."
              rows={3}
              className="resize-none"
            />
            <p className="text-xs text-muted-foreground">
              Adicione informações adicionais sobre esta meta
            </p>
          </div>

          <div className="flex justify-end gap-2 pt-4">
            <Button
              type="button"
              variant="outline"
              onClick={() => setOpen(false)}
              disabled={createMeta.isPending}
            >
              Cancelar
            </Button>
            <Button
              type="submit"
              disabled={
                createMeta.isPending ||
                !formData.usuario_id ||
                !formData.meta_pretendida ||
                (formData.categoria === 'outro' && !formData.categoria_custom)
              }
            >
              {createMeta.isPending ? "Cadastrando..." : "Cadastrar"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

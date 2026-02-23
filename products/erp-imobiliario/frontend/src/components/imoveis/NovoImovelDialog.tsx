import { useState, useEffect } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { imovelSchema, ImovelFormData, calcularQualidadeAnuncio } from "@/lib/imovelValidations";
import { useCreateImovel } from "@/hooks/useImoveis";
import { useCepSearch } from "@/hooks/useCepSearch";
import { formatCurrencyInput, cleanCurrencyInput } from "@/lib/utils";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { Search, AlertCircle } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";

interface NovoImovelDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function NovoImovelDialog({ open, onOpenChange }: NovoImovelDialogProps) {
  const createMutation = useCreateImovel();
  const { searchCep, loading: cepLoading } = useCepSearch();
  const [palavrasChave, setPalavrasChave] = useState<string[]>([]);
  const [novaPalavra, setNovaPalavra] = useState("");
  const [pontosInteresse, setPontosInteresse] = useState<string[]>([]);
  const [novoPonto, setNovoPonto] = useState("");
  const [precoFormatado, setPrecoFormatado] = useState("");

  const {
    register,
    handleSubmit,
    formState: { errors },
    setValue,
    watch,
    reset,
  } = useForm<ImovelFormData>({
    resolver: zodResolver(imovelSchema),
    defaultValues: {
      aceita_permutas: false,
      palavras_chave: [],
      pontos_de_interesse: [],
    },
  });

  const watchedFields = watch();
  const qualidade = calcularQualidadeAnuncio({ ...watchedFields, fotos: [] });
  const cepValue = watch("cep");

  const handleCepSearch = async () => {
    const cep = watchedFields.cep;
    if (!cep) return;

    const data = await searchCep(cep);
    if (data) {
      setValue("logradouro", data.logradouro);
      setValue("bairro", data.bairro);
      setValue("cidade", data.localidade);
      setValue("estado", data.uf);
    }
  };

  // Busca automática quando CEP tiver 8 dígitos
  useEffect(() => {
    const cleanCep = cepValue?.replace(/\D/g, "") || "";
    if (cleanCep.length === 8) {
      handleCepSearch();
    }
  }, [cepValue]);

  const adicionarPalavraChave = () => {
    if (novaPalavra && palavrasChave.length < 4) {
      const novasP = [...palavrasChave, novaPalavra];
      setPalavrasChave(novasP);
      setValue("palavras_chave", novasP);
      setNovaPalavra("");
    }
  };

  const removerPalavraChave = (index: number) => {
    const novasP = palavrasChave.filter((_, i) => i !== index);
    setPalavrasChave(novasP);
    setValue("palavras_chave", novasP);
  };

  const adicionarPontoInteresse = () => {
    if (novoPonto) {
      const novosP = [...pontosInteresse, novoPonto];
      setPontosInteresse(novosP);
      setValue("pontos_de_interesse", novosP);
      setNovoPonto("");
    }
  };

  const removerPontoInteresse = (index: number) => {
    const novosP = pontosInteresse.filter((_, i) => i !== index);
    setPontosInteresse(novosP);
    setValue("pontos_de_interesse", novosP);
  };

  const handlePrecoChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const formatted = formatCurrencyInput(e.target.value);
    setPrecoFormatado(formatted);
    const numericValue = cleanCurrencyInput(formatted);
    setValue("preco_pedido", numericValue);
  };

  const onSubmit = async (data: ImovelFormData) => {
    // Garantir que campos obrigatórios estão presentes
    const formData: any = {
      ...data,
      palavras_chave: palavrasChave,
      pontos_de_interesse: pontosInteresse,
    };

    await createMutation.mutateAsync(formData);
    reset();
    setPalavrasChave([]);
    setPontosInteresse([]);
    setPrecoFormatado("");
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Cadastrar Imóvel</DialogTitle>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
          {/* Alertas de Qualidade */}
          {qualidade.alertas.length > 0 && (
            <Alert>
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>
                <div className="font-medium mb-2">Score de Qualidade: {qualidade.score}/100</div>
                <ul className="space-y-1">
                  {qualidade.alertas.map((alerta, i) => (
                    <li key={i} className="text-sm">
                      {alerta}
                    </li>
                  ))}
                </ul>
              </AlertDescription>
            </Alert>
          )}

          {/* Comercial */}
          <div className="space-y-4">
            <h3 className="font-semibold text-lg">Informações Comerciais</h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <Label htmlFor="finalidade">Finalidade *</Label>
                <Select onValueChange={(v) => setValue("finalidade", v as any)}>
                  <SelectTrigger>
                    <SelectValue placeholder="Selecione" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="venda">Venda</SelectItem>
                    <SelectItem value="aluguel">Aluguel</SelectItem>
                  </SelectContent>
                </Select>
                {errors.finalidade && <p className="text-sm text-destructive">{errors.finalidade.message}</p>}
              </div>

              <div>
                <Label htmlFor="preco_pedido">Preço *</Label>
                <Input type="text" value={precoFormatado} onChange={handlePrecoChange} placeholder="R$ 0,00" />
                {errors.preco_pedido && <p className="text-sm text-destructive">{errors.preco_pedido.message}</p>}
              </div>

              <div className="flex items-center space-x-2 pt-8">
                <Switch
                  checked={watchedFields.aceita_permutas}
                  onCheckedChange={(v) => setValue("aceita_permutas", v)}
                />
                <Label>Aceita Permutas</Label>
              </div>
            </div>

            <div>
              <Label htmlFor="observacoes_negociacao">Observações de Negociação</Label>
              <Textarea {...register("observacoes_negociacao")} rows={2} />
            </div>
          </div>

          {/* Localização */}
          <div className="space-y-4">
            <h3 className="font-semibold text-lg">Localização</h3>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div className="md:col-span-2">
                <Label htmlFor="cep">CEP * (obrigatório)</Label>
                <div className="flex gap-2">
                  <Input {...register("cep")} placeholder="00000-000" />
                  <Button type="button" variant="outline" size="icon" onClick={handleCepSearch} disabled={cepLoading}>
                    <Search className="h-4 w-4" />
                  </Button>
                </div>
                {errors.cep && <p className="text-sm text-destructive">{errors.cep.message}</p>}
              </div>
              <div className="md:col-span-2">
                <Label htmlFor="logradouro">Logradouro</Label>
                <Input {...register("logradouro")} />
              </div>
              <div>
                <Label htmlFor="numero">Número</Label>
                <Input {...register("numero")} />
              </div>
              <div>
                <Label htmlFor="complemento">Complemento</Label>
                <Input {...register("complemento")} />
              </div>
              <div>
                <Label htmlFor="bairro">Bairro</Label>
                <Input {...register("bairro")} />
              </div>
              <div>
                <Label htmlFor="cidade">Cidade</Label>
                <Input {...register("cidade")} />
              </div>
            </div>
          </div>

          {/* Especificações */}
          <div className="space-y-4">
            <h3 className="font-semibold text-lg">Especificações</h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div>
                <Label htmlFor="tipo">Tipo *</Label>
                <Select onValueChange={(v) => setValue("tipo", v as any)}>
                  <SelectTrigger>
                    <SelectValue placeholder="Selecione" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="casa">Casa</SelectItem>
                    <SelectItem value="apartamento">Apartamento</SelectItem>
                    <SelectItem value="terreno">Terreno</SelectItem>
                    <SelectItem value="comercial">Comercial</SelectItem>
                    <SelectItem value="rural">Rural</SelectItem>
                    <SelectItem value="outro">Outro</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label htmlFor="area_total">Área Total (m²)</Label>
                <Input type="number" {...register("area_total")} />
              </div>
              <div>
                <Label htmlFor="quartos">Quartos</Label>
                <Input type="number" {...register("quartos")} />
              </div>
              <div>
                <Label htmlFor="vagas">Vagas</Label>
                <Input type="number" {...register("vagas")} />
              </div>
            </div>
          </div>

          {/* SEO */}
          <div className="space-y-4">
            <h3 className="font-semibold text-lg">Otimização para Portais</h3>
            <div>
              <Label htmlFor="titulo_anuncio">Título do Anúncio</Label>
              <Input {...register("titulo_anuncio")} placeholder="Ex: Apartamento 3 quartos no Centro" />
            </div>
            <div>
              <Label htmlFor="descricao_seo">Descrição</Label>
              <Textarea {...register("descricao_seo")} rows={3} />
            </div>

            <div>
              <Label>Palavras-chave (máx. 4)</Label>
              <div className="flex gap-2 mb-2">
                <Input
                  value={novaPalavra}
                  onChange={(e) => setNovaPalavra(e.target.value)}
                  placeholder="Digite uma palavra-chave"
                  disabled={palavrasChave.length >= 4}
                />
                <Button
                  type="button"
                  variant="outline"
                  onClick={adicionarPalavraChave}
                  disabled={palavrasChave.length >= 4}
                >
                  Adicionar
                </Button>
              </div>
              <div className="flex flex-wrap gap-2">
                {palavrasChave.map((palavra, i) => (
                  <Badge key={i} variant="secondary" className="cursor-pointer" onClick={() => removerPalavraChave(i)}>
                    {palavra} ×
                  </Badge>
                ))}
              </div>
            </div>

            <div>
              <Label>Pontos de Interesse</Label>
              <div className="flex gap-2 mb-2">
                <Input
                  value={novoPonto}
                  onChange={(e) => setNovoPonto(e.target.value)}
                  placeholder="Ex: Shopping, Escola, Parque"
                />
                <Button type="button" variant="outline" onClick={adicionarPontoInteresse}>
                  Adicionar
                </Button>
              </div>
              <div className="flex flex-wrap gap-2">
                {pontosInteresse.map((ponto, i) => (
                  <Badge
                    key={i}
                    variant="secondary"
                    className="cursor-pointer"
                    onClick={() => removerPontoInteresse(i)}
                  >
                    {ponto} ×
                  </Badge>
                ))}
              </div>
            </div>
          </div>

          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancelar
            </Button>
            <Button type="submit" disabled={createMutation.isPending}>
              {createMutation.isPending ? "Salvando..." : "Salvar"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

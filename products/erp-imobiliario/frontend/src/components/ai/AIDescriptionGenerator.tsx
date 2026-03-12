import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { useGenerateDescription } from "@/hooks/useAI";

interface PropertyData {
  tipo?: string;
  endereco?: string;
  cidade?: string;
  estado?: string;
  bairro?: string;
  area_total?: number;
  area_util?: number;
  quartos?: number;
  suites?: number;
  banheiros?: number;
  vagas?: number;
  valor_venda?: number;
  valor_locacao?: number;
  caracteristicas?: string[];
  [key: string]: any;
}

interface AIDescriptionGeneratorProps {
  propertyData: PropertyData;
  onDescriptionGenerated?: (description: string) => void;
  currentDescription?: string;
}

export function AIDescriptionGenerator({
  propertyData,
  onDescriptionGenerated,
  currentDescription,
}: AIDescriptionGeneratorProps) {
  const [description, setDescription] = useState(currentDescription || "");
  const generateMutation = useGenerateDescription();

  async function handleGenerate() {
    try {
      const result = await generateMutation.mutateAsync({
        imovel_data: propertyData,
      });
      const generated = result.descricao || "";
      setDescription(generated);
      onDescriptionGenerated?.(generated);
      toast.success("Descrição gerada", { description: "A descrição foi gerada com sucesso pela IA." });
    } catch (err: any) {
      toast.error("Erro ao gerar descrição", { description: err.message || "Não foi possível gerar a descrição. Verifique se a API de IA está configurada." });
    }
  }

  function handleCopy() {
    navigator.clipboard.writeText(description);
    toast.success("Copiado!", { description: "Descrição copiada para a área de transferência." });
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base flex items-center gap-2">
            Descrição com IA
            <Badge variant="secondary" className="text-xs">Beta</Badge>
          </CardTitle>
          <div className="flex gap-2">
            {description && (
              <Button variant="outline" size="sm" onClick={handleCopy}>
                Copiar
              </Button>
            )}
            <Button
              size="sm"
              onClick={handleGenerate}
              disabled={generateMutation.isPending}
            >
              {generateMutation.isPending ? "Gerando..." : "Gerar com IA"}
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <Textarea
          value={description}
          onChange={(e) => {
            setDescription(e.target.value);
            onDescriptionGenerated?.(e.target.value);
          }}
          placeholder="Clique em 'Gerar com IA' para criar uma descrição profissional do imóvel baseada nas características informadas..."
          rows={6}
          className="resize-y"
        />
        {!description && (
          <p className="text-xs text-muted-foreground mt-2">
            A IA irá gerar uma descrição com base no tipo, localização, área, cômodos e valor do imóvel.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

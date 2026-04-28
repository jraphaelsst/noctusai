import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useImovel } from '@/hooks/useImoveis';
import { ImovelResumo } from '@/components/imoveis/ImovelResumo';
import { ImovelFotos } from '@/components/imoveis/ImovelFotos';
import { ImovelPropostas } from '@/components/imoveis/ImovelPropostas';
import { ImovelVistorias } from '@/components/imoveis/ImovelVistorias';
import { ImovelMatches } from '@/components/imoveis/ImovelMatches';
import { ImovelDocumentos } from '@/components/imoveis/ImovelDocumentos';
import { PageBreadcrumb } from '@/components/ui/page-breadcrumb';
import { DetailPageSkeleton } from '@/components/ui/page-skeleton';
import { EmptyState } from '@/components/ui/empty-state';
import { formatCurrency } from '@/lib/utils';
import { MapPin, FileX } from 'lucide-react';
import { MetaEventoIndicator } from '@/components/MetaEventoIndicator';
import { AIIndicator } from '@noctusai/lib/design-system';

export default function ImovelDetalhes() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('resumo');

  const { data: imovel, isLoading } = useImovel(id);

  if (isLoading) return <DetailPageSkeleton />;

  if (!imovel) {
    return (
      <div className="container mx-auto p-6">
        <EmptyState
          icon={FileX}
          title="Imóvel não encontrado"
          action={{ label: 'Voltar para Imóveis', onClick: () => navigate('/imoveis') }}
        />
      </div>
    );
  }

  const location = [imovel.bairro, imovel.cidade, imovel.estado].filter(Boolean).join(', ');

  return (
    <div className="container mx-auto p-4 sm:p-6 max-w-6xl">
      <PageBreadcrumb items={[
        { label: 'Imóveis', href: '/imoveis' },
        { label: imovel.titulo_anuncio || 'Imóvel' },
      ]} />

      {/* Header */}
      <Card className="p-4 sm:p-6 mb-6">
        <div className="flex flex-col sm:flex-row items-start justify-between gap-4">
          <div className="flex-1 min-w-0 w-full">
            <div className="flex flex-wrap items-center gap-2 sm:gap-3 mb-2">
              <h1 className="text-2xl sm:text-3xl font-bold">
                {imovel.titulo_anuncio || `${(imovel.tipo_imovel || 'Imóvel').charAt(0).toUpperCase() + (imovel.tipo_imovel || 'imóvel').slice(1)}`}
              </h1>
              <Badge className="capitalize">{imovel.tipo_imovel || 'imóvel'}</Badge>
              <Badge variant="secondary" className="capitalize">{imovel.finalidade || 'venda'}</Badge>
              {imovel.aceita_permutas && <Badge variant="outline">Permuta</Badge>}
              <Badge variant="outline" className="capitalize">{imovel.status}</Badge>
              <AIIndicator refType="ativo" refId={imovel.id} showAll />
            </div>
            {location && (
              <p className="text-sm text-muted-foreground flex items-center gap-1">
                <MapPin className="w-3 h-3" />
                {location}
              </p>
            )}
          </div>

          <div className="text-right">
            <p className="text-2xl sm:text-3xl font-bold text-primary">
              {formatCurrency(imovel.valor)}
            </p>
            {imovel.ref && (
              <p className="text-xs text-muted-foreground">Ref: {imovel.ref}</p>
            )}
          </div>
        </div>
      </Card>

      <MetaEventoIndicator refType="ativo" refId={imovel.id} />

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="grid w-full grid-cols-3 sm:grid-cols-6">
          <TabsTrigger value="resumo">Resumo</TabsTrigger>
          <TabsTrigger value="fotos">Fotos</TabsTrigger>
          <TabsTrigger value="propostas">Propostas</TabsTrigger>
          <TabsTrigger value="vistorias">Vistorias</TabsTrigger>
          <TabsTrigger value="matches">Matches</TabsTrigger>
          <TabsTrigger value="documentos">Documentos</TabsTrigger>
        </TabsList>

        <TabsContent value="resumo" className="mt-6">
          <ImovelResumo imovel={imovel} />
        </TabsContent>

        <TabsContent value="fotos" className="mt-6">
          <ImovelFotos imovel={imovel} />
        </TabsContent>

        <TabsContent value="propostas" className="mt-6">
          <ImovelPropostas imovelId={imovel.id} />
        </TabsContent>

        <TabsContent value="vistorias" className="mt-6">
          <ImovelVistorias imovelId={imovel.id} />
        </TabsContent>

        <TabsContent value="matches" className="mt-6">
          <ImovelMatches imovelId={imovel.id} />
        </TabsContent>

        <TabsContent value="documentos" className="mt-6">
          <ImovelDocumentos imovelId={imovel.id} />
        </TabsContent>
      </Tabs>
    </div>
  );
}

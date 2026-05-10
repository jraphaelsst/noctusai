import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Card } from '@noctusai/seed/components/ui/card';
import { Badge } from '@noctusai/seed/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@noctusai/seed/components/ui/tabs';
import { usePerfilPermuta } from '@/hooks/usePermutas';
import { PermutaResumo } from '@/components/permutas/PermutaResumo';
import { PermutaCriterios } from '@/components/permutas/PermutaCriterios';
import { PermutaMatches } from '@/components/permutas/PermutaMatches';
import { PageBreadcrumb } from '@/components/ui/page-breadcrumb';
import { DetailPageSkeleton } from '@/components/ui/page-skeleton';
import { EmptyState } from '@/components/ui/empty-state';
import { Home, Car, FileX } from 'lucide-react';
import { formatCurrency } from '@/lib/utils';

export default function PermutaDetalhes() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('resumo');

  const { data: perfil, isLoading } = usePerfilPermuta(id);

  if (isLoading) return <DetailPageSkeleton />;

  if (!perfil) {
    return (
      <div className="container mx-auto p-6">
        <EmptyState
          icon={FileX}
          title="Perfil de permuta não encontrado"
          action={{ label: 'Voltar para Permutas', onClick: () => navigate('/permutas') }}
        />
      </div>
    );
  }

  const isImovel = perfil.natureza === 'permuta_imovel';

  return (
    <div className="container mx-auto p-4 sm:p-6 max-w-6xl">
      <PageBreadcrumb items={[
        { label: 'Permutas', href: '/permutas' },
        { label: `Perfil #${perfil.id.slice(0, 8)}` },
      ]} />

      {/* Header */}
      <Card className="p-4 sm:p-6 mb-6">
        <div className="flex flex-col sm:flex-row items-start justify-between gap-4">
          <div className="flex-1 min-w-0 w-full">
            <div className="flex flex-wrap items-center gap-2 sm:gap-3 mb-2">
              {isImovel ? <Home className="w-6 h-6 text-primary" /> : <Car className="w-6 h-6 text-primary" />}
              <h1 className="text-2xl sm:text-3xl font-bold">
                Perfil #{perfil.id.slice(0, 8)}
              </h1>
              <Badge variant="secondary">{isImovel ? 'Imóvel' : 'Automóvel'}</Badge>
              <Badge>{perfil.status}</Badge>
            </div>
          </div>

          <div className="text-right">
            <p className="text-2xl sm:text-3xl font-bold text-primary">
              {formatCurrency(perfil.valor)}
            </p>
          </div>
        </div>
      </Card>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="resumo">Resumo</TabsTrigger>
          <TabsTrigger value="criterios">Critérios</TabsTrigger>
          <TabsTrigger value="matches">Matches</TabsTrigger>
        </TabsList>

        <TabsContent value="resumo" className="mt-6">
          <PermutaResumo perfil={perfil} />
        </TabsContent>

        <TabsContent value="criterios" className="mt-6">
          <PermutaCriterios perfil={perfil} />
        </TabsContent>

        <TabsContent value="matches" className="mt-6">
          <PermutaMatches perfilId={perfil.id} />
        </TabsContent>
      </Tabs>
    </div>
  );
}

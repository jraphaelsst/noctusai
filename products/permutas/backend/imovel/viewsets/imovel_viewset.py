from rest_framework.viewsets import ModelViewSet
from django.db.models import Q

from imovel.models import Imovel
from imovel.serializers import ImovelSerializer, ImovelListSerializer


class ImovelViewSet(ModelViewSet):
    queryset = Imovel.objects.select_related(
        'condominio', 'proprietario', 'criado_por', 'tipo', 'zona', 'corretor'
    ).all()
    
    def get_serializer_class(self):
        if self.action == 'list':
            return ImovelListSerializer
        return ImovelSerializer
    
    def get_queryset(self):
        queryset = super().get_queryset()
        if self.action in ['retrieve', 'update', 'partial_update']:
            queryset = queryset.prefetch_related(
                'interesses_imoveis_rel__tipo_imovel',
                'interesses_imoveis_rel__zona',
                'interesses_automoveis_rel__tipo_automovel'
            )
        
        if self.action == 'list':
            ref = self.request.query_params.get('ref')
            corretor = self.request.query_params.get('corretor')
            tipo_nome = self.request.query_params.get('tipo_nome')
            zona_nome = self.request.query_params.get('zona_nome')
            condominio = self.request.query_params.get('condominio')
            proprietario = self.request.query_params.get('proprietario')
            
            if ref:
                queryset = queryset.filter(ref__icontains=ref)
            if corretor:
                queryset = queryset.filter(corretor__nome__icontains=corretor)
            if tipo_nome:
                queryset = queryset.filter(tipo__nome__icontains=tipo_nome)
            if zona_nome:
                queryset = queryset.filter(zona__nome__icontains=zona_nome)
            if condominio:
                queryset = queryset.filter(condominio__nome__icontains=condominio)
            if proprietario:
                queryset = queryset.filter(proprietario__nome__icontains=proprietario)
        
        return queryset

    def perform_create(self, serializer):
        imovel = serializer.save()
        from permuta.tasks import sync_matches_for_imovel
        sync_matches_for_imovel.delay(imovel.id, self.request.user.id)

    def perform_update(self, serializer):
        imovel = serializer.save()
        from permuta.tasks import sync_matches_for_imovel_update
        sync_matches_for_imovel_update.delay(imovel.id, self.request.user.id)

from rest_framework.viewsets import ModelViewSet
from rest_framework.permissions import IsAuthenticated

from permuta.models import PermutaImovel
from permuta.serializers import PermutaImovelSerializer, PermutaImovelListSerializer
from permuta.utils import generate_sequential_code


class PermutaImovelViewSet(ModelViewSet):
    queryset = PermutaImovel.objects.select_related(
        'tipo', 'zona', 'proprietario', 'corretor', 'criado_por'
    ).all()
    permission_classes = [IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action == 'list':
            return PermutaImovelListSerializer
        return PermutaImovelSerializer
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        if self.action == 'list':
            codigo = self.request.query_params.get('codigo')
            ref = self.request.query_params.get('ref')
            proprietario = self.request.query_params.get('proprietario')
            tipo_nome = self.request.query_params.get('tipo_nome')
            cidade = self.request.query_params.get('cidade')
            bairro = self.request.query_params.get('bairro')
            
            if codigo:
                queryset = queryset.filter(codigo__icontains=codigo)
            if ref:
                queryset = queryset.filter(ref__icontains=ref)
            if proprietario:
                queryset = queryset.filter(proprietario__nome__icontains=proprietario)
            if tipo_nome:
                queryset = queryset.filter(tipo__nome__icontains=tipo_nome)
            if cidade:
                queryset = queryset.filter(cidade__icontains=cidade)
            if bairro:
                queryset = queryset.filter(bairro__icontains=bairro)
        
        return queryset
    
    def perform_create(self, serializer):
        codigo = generate_sequential_code('PM', PermutaImovel)
        permuta = serializer.save(codigo=codigo, criado_por=self.request.user)
        from permuta.tasks import sync_matches_for_permuta_imovel
        sync_matches_for_permuta_imovel.delay(permuta.id, self.request.user.id)
    

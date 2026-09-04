from rest_framework.viewsets import ModelViewSet
from rest_framework.permissions import IsAuthenticated

from permuta.models import PermutaAutomovel
from permuta.serializers import PermutaAutomovelSerializer, PermutaAutomovelListSerializer
from permuta.utils import generate_sequential_code
from permuta.bilateral_matching import create_bilateral_matches_for_permuta_automovel


class PermutaAutomovelViewSet(ModelViewSet):
    queryset = PermutaAutomovel.objects.select_related(
        'tipo', 'proprietario', 'corretor', 'criado_por'
    ).all()
    permission_classes = [IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action == 'list':
            return PermutaAutomovelListSerializer
        return PermutaAutomovelSerializer
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        if self.action == 'list':
            codigo = self.request.query_params.get('codigo')
            proprietario = self.request.query_params.get('proprietario')
            tipo_nome = self.request.query_params.get('tipo_nome')
            marca = self.request.query_params.get('marca')
            modelo = self.request.query_params.get('modelo')
            
            if codigo:
                queryset = queryset.filter(codigo__icontains=codigo)
            if proprietario:
                queryset = queryset.filter(proprietario__nome__icontains=proprietario)
            if tipo_nome:
                queryset = queryset.filter(tipo__nome__icontains=tipo_nome)
            if marca:
                queryset = queryset.filter(marca__icontains=marca)
            if modelo:
                queryset = queryset.filter(modelo__icontains=modelo)
        
        return queryset
    
    def perform_create(self, serializer):
        codigo = generate_sequential_code('PM', PermutaAutomovel)
        permuta = serializer.save(codigo=codigo, criado_por=self.request.user)
        create_bilateral_matches_for_permuta_automovel(permuta, self.request.user)

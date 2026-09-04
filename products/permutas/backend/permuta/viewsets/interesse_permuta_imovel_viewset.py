from rest_framework import viewsets, permissions
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from permuta.models import InteressePermutaImovel
from permuta.serializers import (
    InteressePermutaImovelSerializer,
    InteressePermutaImovelListSerializer
)


class InteressePermutaImovelViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing reverse interests (property-in-exchange).
    
    This represents what the owner of a PermutaImovel accepts in return.
    Required for bilateral matching to work.
    
    Endpoints:
    - GET /api/permuta/interesse-imovel/ - List all
    - POST /api/permuta/interesse-imovel/ - Create new
    - GET /api/permuta/interesse-imovel/{id}/ - Retrieve
    - PUT /api/permuta/interesse-imovel/{id}/ - Update
    - PATCH /api/permuta/interesse-imovel/{id}/ - Partial update
    - DELETE /api/permuta/interesse-imovel/{id}/ - Delete
    """
    
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['permuta_imovel', 'tipo_imovel', 'zona']
    
    def get_queryset(self):
        return InteressePermutaImovel.objects.select_related(
            'permuta_imovel', 'tipo_imovel', 'zona', 'criado_por'
        ).all()
    
    def get_serializer_class(self):
        if self.action == 'list':
            return InteressePermutaImovelListSerializer
        return InteressePermutaImovelSerializer
    
    def perform_create(self, serializer):
        interesse = serializer.save(criado_por=self.request.user)
        from permuta.tasks import sync_matches_for_interesse_permuta_imovel
        sync_matches_for_interesse_permuta_imovel.delay(interesse.id, self.request.user.id)

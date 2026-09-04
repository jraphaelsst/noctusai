from rest_framework import viewsets, permissions
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from permuta.models import InteressePermutaAutomovel
from permuta.serializers import (
    InteressePermutaAutomovelSerializer,
    InteressePermutaAutomovelListSerializer
)


class InteressePermutaAutomovelViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing reverse interests (vehicle-in-exchange).
    
    This represents what the owner of a PermutaAutomovel accepts in return
    (typically property criteria since vehicles are exchanged for properties).
    Required for bilateral matching to work.
    
    Endpoints:
    - GET /api/permuta/interesse-automovel/ - List all
    - POST /api/permuta/interesse-automovel/ - Create new
    - GET /api/permuta/interesse-automovel/{id}/ - Retrieve
    - PUT /api/permuta/interesse-automovel/{id}/ - Update
    - PATCH /api/permuta/interesse-automovel/{id}/ - Partial update
    - DELETE /api/permuta/interesse-automovel/{id}/ - Delete
    """
    
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['permuta_automovel', 'tipo_imovel', 'zona']
    
    def get_queryset(self):
        return InteressePermutaAutomovel.objects.select_related(
            'permuta_automovel', 'tipo_imovel', 'zona', 'criado_por'
        ).all()
    
    def get_serializer_class(self):
        if self.action == 'list':
            return InteressePermutaAutomovelListSerializer
        return InteressePermutaAutomovelSerializer
    
    def perform_create(self, serializer):
        interesse = serializer.save(criado_por=self.request.user)
        from permuta.tasks import sync_matches_for_interesse_permuta_automovel
        sync_matches_for_interesse_permuta_automovel.delay(interesse.id, self.request.user.id)

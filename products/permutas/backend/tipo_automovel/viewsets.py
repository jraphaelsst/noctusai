from rest_framework.viewsets import ModelViewSet
from rest_framework.permissions import IsAuthenticated
from tipo_automovel.models import TipoAutomovel
from tipo_automovel.serializers import TipoAutomovelSerializer


class TipoAutomovelViewSet(ModelViewSet):
    queryset = TipoAutomovel.objects.all()
    serializer_class = TipoAutomovelSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None
    
    def get_queryset(self):
        queryset = TipoAutomovel.objects.all()
        search = self.request.query_params.get('search', None)
        if search:
            queryset = queryset.filter(nome__icontains=search)
        return queryset.order_by('nome')
    
    def perform_create(self, serializer):
        serializer.save(criado_por=self.request.user)

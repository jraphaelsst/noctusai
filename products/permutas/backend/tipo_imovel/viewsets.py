from rest_framework.viewsets import ModelViewSet
from rest_framework.permissions import IsAuthenticated
from tipo_imovel.models import TipoImovel
from tipo_imovel.serializers import TipoImovelSerializer


class TipoImovelViewSet(ModelViewSet):
    queryset = TipoImovel.objects.all()
    serializer_class = TipoImovelSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None
    
    def get_queryset(self):
        queryset = TipoImovel.objects.all()
        search = self.request.query_params.get('search', None)
        if search:
            queryset = queryset.filter(nome__icontains=search)
        return queryset.order_by('nome')
    
    def perform_create(self, serializer):
        serializer.save(criado_por=self.request.user)

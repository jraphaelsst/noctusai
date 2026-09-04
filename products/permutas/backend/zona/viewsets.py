from rest_framework.viewsets import ModelViewSet
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q

from zona.models import Zona
from zona.serializers import ZonaSerializer


class ZonaViewSet(ModelViewSet):
    serializer_class = ZonaSerializer
    queryset = Zona.objects.all()
    permission_classes = [IsAuthenticated]
    pagination_class = None
    
    def get_queryset(self):
        queryset = Zona.objects.all()
        search = self.request.query_params.get('search', None)
        
        if search:
            queryset = queryset.filter(
                Q(nome__icontains=search) |
                Q(descricao__icontains=search)
            )
        
        return queryset.order_by('nome')
    
    def perform_create(self, serializer):
        serializer.save(criado_por=self.request.user)

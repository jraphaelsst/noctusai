from rest_framework.viewsets import ModelViewSet
from django.db.models import Q

from backend.throttling import SearchRateThrottle
from condominio.models import Condominio
from condominio.serializers import CondominioSerializer


class CondominioViewSet(ModelViewSet):
    serializer_class = CondominioSerializer
    queryset = Condominio.objects.all()
    
    def get_throttles(self):
        if self.action == 'list' and any(
            self.request.query_params.get(param) 
            for param in ['search', 'nome', 'bairro', 'cidade']
        ):
            return [SearchRateThrottle()]
        return super().get_throttles()
    
    def get_queryset(self):
        queryset = Condominio.objects.all()
        search = self.request.query_params.get('search', None)
        
        if search:
            queryset = queryset.filter(
                Q(nome__icontains=search) |
                Q(bairro__icontains=search) |
                Q(cidade__icontains=search)
            )
        
        if self.action == 'list':
            nome = self.request.query_params.get('nome')
            bairro = self.request.query_params.get('bairro')
            cidade = self.request.query_params.get('cidade')
            
            if nome:
                queryset = queryset.filter(nome__icontains=nome)
            if bairro:
                queryset = queryset.filter(bairro__icontains=bairro)
            if cidade:
                queryset = queryset.filter(cidade__icontains=cidade)
        
        return queryset
